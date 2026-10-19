import os
import re
import shutil
import subprocess
import sys
import unittest
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch
from google.genai.errors import ServerError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from config import Config, resolve_gemini_fallback_model, resolve_gemini_model

Config.SQLALCHEMY_DATABASE_URI = "sqlite://"
Config.SQLALCHEMY_ENGINE_OPTIONS = {}
Config.SECRET_KEY = "automated-test-secret"

from app import app as default_app
from app import create_app
from extensions import db
from helpers.gemini import GeminiUnavailableError, generate_reply
from helpers.personas import NPC_PERSONAS, TUTOR_GLOBAL_INSTRUCTION, tutor_instruction_for
from seed import CONTENTS, ROLES, TASKS
from models import (
    ContentBlock,
    InterviewLog,
    LabSample,
    ReportDraft,
    Role,
    SavedQuote,
    SimulationResult,
    SimulationVariable,
    StudentTaskProgress,
    Task,
    UserSession,
)


ROLE_PASSWORDS = {
    "termobr": "termo",
    "hydrosul": "hidro",
    "comunidade": "ivai",
    "cientistas": "energia",
    "admin": "admin",
}
STUDENT_ROLES = ("termobr", "hydrosul", "comunidade", "cientistas")
COMMON_STUDENT_PAGES = (
    "/student/home",
    "/student/simulator",
    "/student/tasks",
    "/student/report",
    "/student/interview",
    "/student/community",
)


class CarbopolisApplicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app(Config)
        cls.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)

    @classmethod
    def tearDownClass(cls):
        with cls.app.app_context():
            cls.app.extensions["sqlalchemy"].engine.dispose()
        with default_app.app_context():
            default_app.extensions["sqlalchemy"].engine.dispose()

    def setUp(self):
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.drop_all()
        db.create_all()
        self.roles = {}
        self.sessions = {}
        for name, password in ROLE_PASSWORDS.items():
            role = Role(
                name=name,
                password=password,
                display_name=name.title(),
                description=f"Grupo {name}",
            )
            db.session.add(role)
            self.roles[name] = role
        db.session.flush()
        for name, role in self.roles.items():
            session = UserSession(role_id=role.id, members_text=f"Equipe {name}")
            db.session.add(session)
            self.sessions[name] = session
        for key, value in (
            ("so2_gas_base", 45),
            ("nox_gas_base", 55),
            ("co2_gas_base", 68),
            ("so2_coal_base", 180),
            ("nox_coal_base", 125),
            ("co2_coal_base", 98),
        ):
            db.session.add(SimulationVariable(var_key=key, value=value))
        for key, title in (
            ("map_intro", "Início"),
            ("lab_intro", "Laboratório"),
            ("sim_intro", "Simulador"),
        ):
            db.session.add(
                ContentBlock(
                    section_key=key,
                    title=title,
                    body_text=f"Texto de {title}",
                    button_label="Abrir",
                    hint_text="Explore",
                )
            )
        for name, role in self.roles.items():
            if name != "admin":
                db.session.add(
                    Task(
                        role_id=role.id,
                        title=f"Missão de {name}",
                        description="Investigue o dilema.",
                        action_type="text",
                        is_active=True,
                    )
                )
        db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def login(self, role_name):
        self.client.get("/logout")
        response = self.client.post(
            "/login",
            data={
                "password": ROLE_PASSWORDS[role_name],
                "members_text": f"Equipe {role_name}",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        return response

    def test_login_page_does_not_reveal_a_group_password_example(self):
        response = self.client.get("/login")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'placeholder="Digite a senha do grupo"', response.data)
        self.assertNotIn(b"Ex.: energia", response.data)

    def test_reset_user_data_cli_previews_and_clears_activity_only_when_confirmed(self):
        role = self.roles["comunidade"]
        session = self.sessions["comunidade"]
        session.members_text = "Nome de teste"
        task = Task.query.filter_by(role_id=role.id).one()
        db.session.add_all(
            [
                InterviewLog(
                    user_session_id=session.id,
                    npc_id="agricultora",
                    user_message="Pergunta de teste",
                    assistant_message="Resposta de teste",
                ),
                SavedQuote(
                    role_id=role.id,
                    character_name="Dona Maria",
                    quote_text="Depoimento pessoal de teste",
                ),
                LabSample(role_id=role.id, sample_type="water", ph_value=6.8),
                SimulationResult(
                    role_id=role.id,
                    energy_choice="thermal",
                    env_score=50,
                    social_score=50,
                    economic_score=50,
                    energy_score=50,
                ),
                ReportDraft(role_id=role.id, jury_question="Pergunta de teste"),
                StudentTaskProgress(
                    task_id=task.id,
                    role_id=role.id,
                    answer_text="Resposta pessoal de teste",
                    is_completed=True,
                ),
            ]
        )
        db.session.commit()

        runner = self.app.test_cli_runner()
        preview = runner.invoke(args=["reset-user-data"])
        self.assertEqual(preview.exit_code, 0, preview.output)
        self.assertIn("Nada foi alterado", preview.output)
        self.assertEqual(InterviewLog.query.count(), 1)
        self.assertEqual(UserSession.query.count(), len(STUDENT_ROLES) + 1)

        result = runner.invoke(args=["reset-user-data", "--yes"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Grupos, senhas, missões, conteúdo e configurações", result.output)
        for model in (
            InterviewLog,
            LabSample,
            SavedQuote,
            SimulationResult,
            ReportDraft,
            StudentTaskProgress,
            UserSession,
        ):
            with self.subTest(model=model.__name__):
                self.assertEqual(model.query.count(), 0)
        self.assertEqual(Role.query.count(), len(STUDENT_ROLES) + 1)
        self.assertEqual(Task.query.count(), len(STUDENT_ROLES))
        self.assertEqual(ContentBlock.query.count(), 3)
        self.assertEqual(SimulationVariable.query.count(), 6)

    def get_as(self, role_name, path):
        self.login(role_name)
        return self.client.get(path, follow_redirects=False)

    def test_login_rejects_unknown_password_and_logout_clears_session(self):
        response = self.client.get("/login")
        self.assertEqual(response.status_code, 200)
        response = self.client.post("/login", data={"password": "incorreta"})
        self.assertEqual(response.status_code, 401)
        self.assertIn("Senha do grupo incorreta".encode(), response.data)

        self.login("comunidade")
        response = self.client.get("/logout", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get("/").location, "/login")

    def test_each_group_password_opens_the_expected_group_session(self):
        for role_name in ROLE_PASSWORDS:
            with self.subTest(role=role_name):
                self.login(role_name)
                with self.client.session_transaction() as session_cookie:
                    session_id = int(session_cookie["_user_id"])
                self.assertEqual(db.session.get(UserSession, session_id).role_name, role_name)

    def test_protected_student_and_admin_pages_redirect_anonymous_visitors(self):
        paths = (
            "/student/home",
            "/student/lab",
            "/student/community",
            "/student/termobr",
            "/student/hydrosul",
            "/student/scientists",
            "/student/tasks",
            "/student/report",
            "/student/simulator",
            "/student/interview",
            "/admin/",
            "/admin/content",
            "/admin/tasks",
        )
        for path in paths:
            with self.subTest(path=path):
                response = self.client.get(path, follow_redirects=False)
                self.assertEqual(response.status_code, 302)
                self.assertIn("/login", response.location)

    def test_local_stylesheets_and_scripts_are_served(self):
        for path in (
            "/static/css/style.css",
            "/static/css/chat.css",
            "/static/js/lab.js",
            "/static/js/simulator.js",
            "/static/js/interview.js",
            "/static/js/tutor.js",
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.data)
                response.close()

    def test_every_role_can_open_shared_pages(self):
        for role in STUDENT_ROLES:
            for path in COMMON_STUDENT_PAGES:
                with self.subTest(role=role, path=path):
                    response = self.get_as(role, path)
                    self.assertEqual(response.status_code, 200)

    def test_group_specific_pages_are_restricted(self):
        protected = {
            "/student/termobr": "termobr",
            "/student/hydrosul": "hydrosul",
            "/student/scientists": "cientistas",
            "/student/lab": "cientistas",
        }
        for path, allowed_role in protected.items():
            for role in (*STUDENT_ROLES, "admin"):
                with self.subTest(path=path, role=role):
                    response = self.get_as(role, path)
                    if role in (allowed_role, "admin"):
                        self.assertEqual(response.status_code, 200)
                    else:
                        self.assertEqual(response.status_code, 302)
                        self.assertEqual(response.location, "/student/home")

    def test_home_page_uses_configured_image_instead_of_a_map(self):
        self.login("comunidade")
        content = ContentBlock.query.filter_by(section_key="map_intro").one()
        content.image_url = "/static/uploads/ivai.png"
        db.session.commit()

        response = self.client.get("/student/home")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'src="/static/uploads/ivai.png"', response.data)
        self.assertIn(b"object-contain", response.data)
        self.assertNotIn(b'id="map"', response.data)
        self.assertNotIn(b"leaflet", response.data.lower())
        self.assertNotIn(b"Pontos de Interesse", response.data)
        self.assertIn(b">In\xc3\xadcio</a>", response.data)

        content.image_url = None
        db.session.commit()
        response = self.client.get("/student/home")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b'src="/static/uploads/ivai.png"', response.data)
        self.assertNotIn(b'id="map"', response.data)
        self.assertNotIn(b"min-h-[280px]", response.data)

    def test_dossier_pdf_opens_inline_and_contains_dossier_content(self):
        self.login("comunidade")
        db.session.add(
            LabSample(
                role_id=self.roles["comunidade"].id,
                sample_type="air",
                so2_ppm=12,
                notes="Projeção — verificação",
                saved_to_dossier=True,
            )
        )
        db.session.add(
            SavedQuote(
                role_id=self.roles["comunidade"].id,
                character_name="Dona Maria",
                quote_text="Eu protegeria minha terra 🌱.",
            )
        )
        db.session.commit()
        db.session.add(
            LabSample(
                role_id=self.roles["comunidade"].id,
                sample_type="air",
                so2_ppm=12,
                notes="Projeção — verificação",
                saved_to_dossier=True,
            )
        )
        db.session.add(
            SavedQuote(
                role_id=self.roles["comunidade"].id,
                character_name="Dona Maria",
                quote_text="Eu protegeria minha terra 🌱.",
            )
        )
        db.session.commit()
        page = self.client.get("/student/report")
        self.assertIn(b"Abrir Dossi\xc3\xaa em PDF", page.data)
        self.assertIn(b'target="_blank"', page.data)

        pdf = self.client.get("/student/report/pdf")
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(pdf.mimetype, "application/pdf")
        self.assertIn(b"%PDF", pdf.data[:10])
        self.assertIn("inline", pdf.headers["Content-Disposition"])

    def test_lab_sample_options_do_not_reveal_the_expected_ph_values(self):
        self.login("cientistas")
        response = self.client.get("/student/lab")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b"pH de refer\xc3\xaancia", response.data)
        self.assertNotIn(b"pH ~", response.data)


    def test_project_pages_and_laboratory_describe_proposals_not_existing_plants(self):
        for role_name, path, expected in (
            ("termobr", "/student/termobr", "PROPOSTA DE USINA TERMELÉTRICA"),
            ("hydrosul", "/student/hydrosul", "PROPOSTA DE USINA HIDRELÉTRICA"),
            ("comunidade", "/student/community", "Nenhuma das usinas existe"),
            ("cientistas", "/student/scientists", "possíveis efeitos das propostas"),
            ("cientistas", "/student/lab", "testes preditivos e simulações"),
        ):
            with self.subTest(role=role_name, path=path):
                response = self.get_as(role_name, path)
                self.assertEqual(response.status_code, 200)
                self.assertIn(expected.encode(), response.data)

        lab_page = self.client.get("/student/lab")
        self.assertIn(
            b"Realize testes preditivos e simula\xc3\xa7\xc3\xb5es baseadas nos Estudos de Impacto Ambiental (EIA) submetidos pelas empresas para prever o que acontecer\xc3\xa1 com Iva\xc3\xad dos Campos se os projetos forem aprovados.",
            lab_page.data,
        )
        self.assertIn(b"Rio Iva\xc3\xad (Cen\xc3\xa1rio Atual - \xc3\x81gua Limpa)", lab_page.data)
        self.assertIn(b"Proje\xc3\xa7\xc3\xa3o EIA: Efluentes de Resfriamento (Projeto TermoBR)", lab_page.data)
        self.assertIn(b"Proje\xc3\xa7\xc3\xa3o EIA: Emiss\xc3\xb5es Atmosf\xc3\xa9ricas (Projeto TermoBR", lab_page.data)

    def test_seed_keeps_the_default_passwords_for_each_group(self):
        passwords = {name: password for name, password, _display, _description in ROLES}
        self.assertEqual(
            passwords,
            {
                "termobr": "termo",
                "hydrosul": "hidro",
                "comunidade": "ivai",
                "cientistas": "energia",
                "admin": "admin",
            },
        )

    def test_seed_content_and_missions_use_preapproval_context(self):
        contents = {section: (title, body, button, hint) for section, title, body, button, hint in CONTENTS}
        self.assertEqual(
            contents["map_intro"][0],
            "Comitê de Avaliação de Propostas Energéticas",
        )
        self.assertIn("Júri Simulado", contents["map_intro"][1])
        self.assertIn("não medições", contents["lab_intro"][3])
        self.assertIn("Nenhuma usina foi aprovada ou construída", contents["sim_intro"][1])
        conditional_markers = ("poder", "dever", "caso", "se ", "simule", "registre")
        self.assertTrue(
            all(
                any(marker in description.lower() for marker in conditional_markers)
                for role, title, description, action_type in TASKS
            )
        )

    def test_legacy_map_url_redirects_to_home(self):
        self.login("comunidade")
        response = self.client.get("/student/map")
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response.location, "/student/home")

    def test_sponsored_energy_article_is_labeled_as_sponsored(self):
        for role_name, path in (
            ("comunidade", "/student/community"),
            ("termobr", "/student/termobr"),
        ):
            with self.subTest(role=role_name):
                response = self.get_as(role_name, path)
                self.assertIn(b"conte\xc3\xbado patrocinado", response.data.lower())

    def test_lab_rejects_invalid_measurement_without_saving(self):
        self.login("cientistas")
        response = self.client.post(
            "/student/lab",
            data={"sample_type": "water", "ph_value": "not-a-number"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(LabSample.query.count(), 0)
        flashed = self.client.get("/student/lab")
        self.assertIn(b"Valor num\xc3\xa9rico inv\xc3\xa1lido", flashed.data)

    def test_lab_saves_valid_sample_for_scientist_group(self):
        self.login("cientistas")
        response = self.client.post(
            "/student/lab",
            data={
                "sample_type": "air",
                "so2_ppm": "45.5",
                "nox_ppm": "55",
                "co2_ppm": "68",
                "saved_to_dossier": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        sample = LabSample.query.one()
        self.assertEqual(sample.sample_type, "air")
        self.assertEqual(sample.so2_ppm, 45.5)
        self.assertTrue(sample.saved_to_dossier)
        self.assertIsNotNone(sample.created_at)
        public_report = self.client.get("/api/lab/public_reports").get_json()[0]
        self.assertEqual(public_report["id"], sample.id)
        self.assertEqual(public_report["author"], "Cientistas")

        lab_page = self.client.get("/student/lab")
        self.assertIn(b'fa-floppy-disk"></i> Salvar Laudo no Dossi\xc3\xaa', lab_page.data)
        self.assertNotIn(b'fa-floppy-disk"></i> \xf0\x9f\x92\xbe', lab_page.data)
        self.assertIn(b"#1 Ar", lab_page.data)
        self.assertIn(b"SO<sub>2</sub> 45.5 ppm", lab_page.data)
        self.assertIn(b"NO<sub>x</sub> 55.0 ppm", lab_page.data)
        self.assertIn(b"CO<sub>2</sub> 68.0 ppm", lab_page.data)
        self.assertIn(b"Laudos dispon", lab_page.data)
        self.assertNotIn(b"#1 air", lab_page.data)
        self.assertNotIn(b"None", lab_page.data)

        report_page = self.client.get("/student/report")
        self.assertIn(b"#1 Ar", report_page.data)
        self.assertIn(b"CO<sub>2</sub> 68.0 ppm", report_page.data)
        self.assertNotIn(b"None", report_page.data)

    def test_scientist_reports_are_public_on_home_and_api_for_every_group(self):
        published = LabSample(
            role_id=self.roles["cientistas"].id,
            sample_type="water",
            ph_value=4.5,
            notes="Risco de chuva ácida detectado",
            saved_to_dossier=True,
        )
        unpublished = LabSample(
            role_id=self.roles["cientistas"].id,
            sample_type="air",
            so2_ppm=12,
            saved_to_dossier=False,
        )
        other_group_report = LabSample(
            role_id=self.roles["termobr"].id,
            sample_type="air",
            so2_ppm=99,
            saved_to_dossier=True,
        )
        db.session.add_all((published, unpublished, other_group_report))
        db.session.commit()

        api_response = self.client.get("/api/lab/public_reports")
        self.assertEqual(api_response.status_code, 200)
        reports = api_response.get_json()
        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0]["id"], published.id)
        self.assertEqual(reports[0]["title"], "Laudo de análise da água")
        self.assertIn("Risco de chuva ácida detectado", reports[0]["conclusion"])
        self.assertIn("pH: 4.5", reports[0]["conclusion"])
        self.assertTrue(reports[0]["timestamp"])
        self.assertEqual(reports[0]["author"], "Cientistas")
        self.assertIsNotNone(published.created_at)

        for role_name in STUDENT_ROLES:
            with self.subTest(role=role_name):
                page = self.get_as(role_name, "/student/home")
                self.assertEqual(page.status_code, 200)
                self.assertIn(b"Dados gerais das propostas", page.data)
                self.assertIn(b"Projeto TermoBR", page.data)
                self.assertIn(b"Projeto HydroSul", page.data)
                self.assertIn(b"Poss\xc3\xadveis benef\xc3\xadcios", page.data)
                self.assertIn(b"Riscos a avaliar", page.data)
                self.assertIn(b"ainda n\xc3\xa3o aprovados nem constru\xc3\xaddos", page.data)
                self.assertIn(b"Mural de Transpar\xc3\xaancia", page.data)
                self.assertIn(b"Laudo de an\xc3\xa1lise da \xc3\xa1gua", page.data)
                self.assertIn(b"Publicado por: Cientistas", page.data)
                self.assertIn(b"notifications.js", page.data)
                self.assertEqual(self.client.get("/api/lab/public_reports").status_code, 200)

    def test_water_sample_history_is_translated_and_omits_empty_values(self):
        self.login("cientistas")
        sample = LabSample(
            role_id=self.roles["cientistas"].id,
            sample_type="water",
            ph_value=4.5,
            temp_celsius=28,
            od_value=6.2,
            saved_to_dossier=True,
        )
        db.session.add(sample)
        db.session.commit()

        response = self.client.get("/student/lab")
        self.assertIn(b"#1 \xc3\x81gua", response.data)
        self.assertIn(b"pH 4.5", response.data)
        self.assertIn(b"Temperatura 28.0\xc2\xb0C", response.data)
        self.assertIn(b"OD 6.2 mg/L", response.data)
        self.assertNotIn(b"#1 water", response.data)
        self.assertNotIn(b"None", response.data)

    def test_missions_and_dossier_persist_only_current_groups_answers(self):
        role = self.roles["comunidade"]
        task = Task.query.filter_by(role_id=role.id).one()
        self.login("comunidade")
        response = self.client.post(
            "/student/tasks",
            data={"task_id": task.id, "answer_text": "Proteger as famílias."},
        )
        self.assertEqual(response.status_code, 302)
        progress = StudentTaskProgress.query.one()
        self.assertTrue(progress.is_completed)
        self.assertEqual(progress.answer_text, "Proteger as famílias.")

        response = self.client.post(
            "/student/report",
            data={
                "members_text": "Ana e Beto",
                "jury_question": "Qual será o plano de compensação?",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ReportDraft.query.one().jury_question, "Qual será o plano de compensação?")
        with self.client.session_transaction() as session_cookie:
            logged_in_session_id = int(session_cookie["_user_id"])
        self.assertEqual(db.session.get(UserSession, logged_in_session_id).members_text, "Ana e Beto")

        other_task = Task.query.filter_by(role_id=self.roles["termobr"].id).one()
        response = self.client.post(
            "/student/tasks",
            data={"task_id": other_task.id, "answer_text": "Resposta indevida"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(StudentTaskProgress.query.count(), 1)

    def test_inactive_missions_are_consistent_between_quest_log_and_dossier(self):
        role = self.roles["comunidade"]
        inactive = Task(
            role_id=role.id,
            title="Missão desativada",
            description="Não deve aparecer para alunos.",
            is_active=False,
        )
        db.session.add(inactive)
        db.session.commit()
        self.login("comunidade")
        quest_log = self.client.get("/student/tasks")
        dossier = self.client.get("/student/report")
        self.assertNotIn(b"Miss\xc3\xa3o desativada", quest_log.data)
        self.assertNotIn(b"Miss\xc3\xa3o desativada", dossier.data)

    def test_simulator_supports_each_energy_choice_and_persists_results(self):
        self.login("hydrosul")
        page = self.client.get("/student/simulator")
        self.assertEqual(page.status_code, 200)
        self.assertNotIn(b"TermoBR e HydroSul ainda s\xc3\xa3o propostas", page.data)
        self.assertIn(b"Proposta TermoBR", page.data)
        self.assertIn(b"Proposta HydroSul", page.data)
        self.assertNotIn(b"Cen\xc3\xa1rio misto hipot\xc3\xa9tico", page.data)
        self.assertIn(b"simulator.js?v=2", page.data)
        simulator_script = (PROJECT_ROOT / "static" / "js" / "simulator.js").read_text(encoding="utf-8")
        self.assertIn('group.style.display = visible ? "block" : "none"', simulator_script)
        self.assertIn("payload.has_filters", simulator_script)
        self.assertIn("payload.has_fish_ladder", simulator_script)
        self.assertIn(b"Passagem para peixes (escada de peixes)", page.data)
        self.assertIn("contornar a barragem", page.data.decode("utf-8"))
        for choice in ("thermal", "hydro"):
            with self.subTest(energy_choice=choice):
                response = self.client.post(
                    "/api/simulate",
                    json={
                        "energy_choice": choice,
                        "fuel_type": "gas",
                        "dam_height": 40,
                        "has_filters": True,
                        "has_relocation_plan": True,
                        "has_fish_ladder": True,
                    },
                )
                self.assertEqual(response.status_code, 200)
                result = response.get_json()
                self.assertEqual(result["energy_choice"], choice)
                if choice == "thermal":
                    self.assertFalse(result["has_relocation_plan"])
                    self.assertFalse(result["has_fish_ladder"])
                    self.assertTrue(result["has_filters"])
                else:
                    self.assertFalse(result["has_filters"])
                    self.assertTrue(result["has_relocation_plan"])
                    self.assertTrue(result["has_fish_ladder"])
                for score_key in ("env_score", "social_score", "economic_score", "energy_score"):
                    self.assertGreaterEqual(result[score_key], 0)
                    self.assertLessEqual(result[score_key], 100)
        self.assertEqual(SimulationResult.query.filter_by(role_id=self.roles["hydrosul"].id).count(), 2)

    def test_simulator_rejects_malformed_payloads_and_unknown_options(self):
        self.login("termobr")
        for payload in (
            None,
            {"energy_choice": "nuclear"},
            {"energy_choice": "mixed"},
            {"fuel_type": "wood"},
            {"has_filters": "false"},
        ):
            with self.subTest(payload=payload):
                response = self.client.post("/api/simulate", json=payload)
                self.assertEqual(response.status_code, 400)
        self.assertEqual(SimulationResult.query.count(), 0)

    def test_interviews_persist_per_character_and_tutor_uses_group_prompt(self):
        self.login("cientistas")
        with patch("routes.chat.generate_reply", return_value="Resposta de teste.") as generate:
            for npc_id in ("agricultora", "eng_termo", "eng_hidro", "cientista"):
                response = self.client.post(
                    "/api/chat/interview",
                    json={"npc": npc_id, "message": "Qual é sua preocupação?"},
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.get_json()["reply"], "Resposta de teste.")
                self.assertEqual(
                    generate.call_args.kwargs["response_mime_type"],
                    "application/json",
                )
                self.assertIn("VOCÊ DEVE RESPONDER ESTRITAMENTE NESTE FORMATO JSON", generate.call_args.args[0])
                self.assertIn('"sugestoes":', generate.call_args.args[0])
                history = self.client.get(f"/api/chat/interview/history/{npc_id}")
                self.assertEqual(history.status_code, 200)
                self.assertEqual(len(history.get_json()["messages"]), 2)
            self.assertEqual(InterviewLog.query.count(), 4)

        for role_name in STUDENT_ROLES:
            self.login(role_name)
            with patch("routes.chat.generate_reply", return_value="Pista por grupo.") as generate:
                response = self.client.post(
                    "/api/chat/tutor",
                    json={"message": "Como avalio a amostra?", "history": []},
                )
                self.assertEqual(response.status_code, 200)
                prompt = generate.call_args.args[0]
                self.assertTrue(prompt.startswith(TUTOR_GLOBAL_INSTRUCTION))
                self.assertTrue(prompt.endswith(tutor_instruction_for(role_name)))
                self.assertIn("Página inicial (antigo Mapa)", prompt)
                self.assertIn("mapa interativo foi removido", prompt)
                self.assertIn("exclusivo do grupo Cientistas", prompt)
                self.assertIn("Dossiê Final", prompt)

    def test_interview_prompts_identify_authenticated_group_and_include_persona_biases(self):
        role_labels = {
            "termobr": "TermoBR",
            "hydrosul": "HydroSul",
            "comunidade": "Comunidade de Ivaí dos Campos",
            "cientistas": "Cientistas Ambientais",
        }
        for role_name in STUDENT_ROLES:
            self.login(role_name)
            for npc_id, persona in NPC_PERSONAS.items():
                with self.subTest(role=role_name, npc=npc_id):
                    with patch("routes.chat.generate_reply", return_value="Resposta.") as generate:
                        response = self.client.post(
                            "/api/chat/interview",
                            json={"npc": npc_id, "message": "Como você vê este projeto?"},
                        )

                    self.assertEqual(response.status_code, 200)
                    system_instruction = generate.call_args.args[0]
                    self.assertIn(f"representa o grupo '{role_labels[role_name]}'", system_instruction)
                    self.assertIn(f"identificador: '{role_name}'", system_instruction)
                    self.assertIn("nunca a chame de estudante", system_instruction)
                    self.assertNotIn("entrevista escolar", system_instruction)
                    self.assertTrue(
                        system_instruction.startswith(persona["system_instruction"])
                    )

        self.assertIn("desconfiada e hostil", NPC_PERSONAS["agricultora"]["system_instruction"])
        self.assertIn("raivosa e defensiva", NPC_PERSONAS["agricultora"]["system_instruction"])
        self.assertIn("vizinho ou vizinha", NPC_PERSONAS["agricultora"]["system_instruction"])
        self.assertIn("colega de diretoria", NPC_PERSONAS["eng_termo"]["system_instruction"])
        self.assertIn("concorrente direta", NPC_PERSONAS["eng_termo"]["system_instruction"])
        self.assertIn("colega de equipe", NPC_PERSONAS["eng_hidro"]["system_instruction"])
        self.assertIn("concorrente poluidora", NPC_PERSONAS["eng_hidro"]["system_instruction"])

    def test_personas_cover_every_interview_character_and_reject_unknown_history(self):
        self.assertEqual(
            set(NPC_PERSONAS),
            {"agricultora", "eng_termo", "eng_hidro", "cientista"},
        )
        self.assertEqual(NPC_PERSONAS["eng_termo"]["name"], "Eng. Carla")
        self.assertEqual(NPC_PERSONAS["eng_termo"]["role"], "Engenheira da TermoBR")
        self.assertIn("Engenheira Carla", NPC_PERSONAS["eng_termo"]["system_instruction"])
        for role_name in STUDENT_ROLES:
            self.assertTrue(tutor_instruction_for(role_name))
        self.assertIsNone(tutor_instruction_for("admin"))

        self.login("cientistas")
        page = self.client.get("/student/interview")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Eng. Carla", page.data)
        self.assertIn(b"Engenheira da TermoBR", page.data)
        self.assertNotIn(b"Eng. Carlos", page.data)

        response = self.client.get("/api/chat/interview/history/unknown")
        self.assertEqual(response.status_code, 404)

    def test_interview_quotes_are_saved_and_only_shown_in_the_own_group_dossier(self):
        self.login("comunidade")
        response = self.client.post(
            "/api/dossier/save_quote",
            json={"npc": "agricultora", "quote_text": "Eu temeria perder minha terra."},
        )
        self.assertEqual(response.status_code, 201)
        quote = SavedQuote.query.one()
        self.assertEqual(quote.role_id, self.roles["comunidade"].id)
        self.assertEqual(quote.character_name, NPC_PERSONAS["agricultora"]["name"])
        self.assertEqual(quote.quote_text, "Eu temeria perder minha terra.")
        self.assertIsNotNone(quote.timestamp)

        community_dossier = self.client.get("/student/report")
        self.assertIn(b"Depoimentos e Evid\xc3\xaancias Recolhidas", community_dossier.data)
        self.assertIn(b"Eu temeria perder minha terra.", community_dossier.data)
        self.assertIn("Dona Maria".encode(), community_dossier.data)

        self.login("termobr")
        termobr_dossier = self.client.get("/student/report")
        self.assertNotIn(b"Eu temeria perder minha terra.", termobr_dossier.data)

    def test_save_quote_rejects_invalid_npc_or_empty_text(self):
        self.login("cientistas")
        for payload in (
            {"npc": "unknown", "quote_text": "fala"},
            {"npc": "cientista", "quote_text": "  "},
            None,
        ):
            with self.subTest(payload=payload):
                response = self.client.post("/api/dossier/save_quote", json=payload)
                self.assertEqual(response.status_code, 400)
        self.assertEqual(SavedQuote.query.count(), 0)

    def test_gemini_wrapper_handles_missing_key_and_uses_configured_model(self):
        self.assertEqual(resolve_gemini_model(None), "gemini-3.8-flash")
        self.assertEqual(resolve_gemini_model("gemini-2.5-flash"), "gemini-3.8-flash")
        self.assertEqual(resolve_gemini_model("gemini-custom"), "gemini-custom")
        self.assertEqual(
            resolve_gemini_fallback_model(None),
            "gemini-3.5-flash-lite",
        )
        self.assertEqual(
            resolve_gemini_fallback_model("gemini-2.5-flash-lite"),
            "gemini-3.5-flash-lite",
        )

        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
            with self.assertRaises(GeminiUnavailableError):
                generate_reply("Instrução", "Pergunta")

        fake_client = MagicMock()
        fake_client.models.generate_content.return_value.text = "  Resposta de teste  "
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            with patch("google.genai.Client", return_value=fake_client) as client_factory:
                answer = generate_reply(
                    "Instrução do sistema",
                    "Pergunta atual",
                    [{"role": "user", "text": "Pergunta anterior"}],
                )
        self.assertEqual(answer, "Resposta de teste")
        client_factory.assert_called_once_with(api_key="test-key")
        call = fake_client.models.generate_content.call_args
        self.assertEqual(call.kwargs["model"], self.app.config["GEMINI_MODEL"])
        self.assertEqual(
            call.kwargs["config"].system_instruction,
            "Instrução do sistema",
        )
        self.assertFalse(hasattr(call.kwargs["config"], "response_mime_type") and call.kwargs["config"].response_mime_type)
        self.assertEqual(len(call.kwargs["contents"]), 2)

    def test_gemini_retries_with_fallback_model_on_overload(self):
        fake_client = MagicMock()
        fake_client.models.generate_content.side_effect = [
            ServerError(503, {"error": {"message": "high demand"}}),
            MagicMock(text="Resposta pelo modelo alternativo"),
        ]
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            with patch("google.genai.Client", return_value=fake_client):
                answer = generate_reply("Instrução", "Pergunta")

        self.assertEqual(answer, "Resposta pelo modelo alternativo")
        self.assertEqual(
            [
                call.kwargs["model"]
                for call in fake_client.models.generate_content.call_args_list
            ],
            [
                self.app.config["GEMINI_MODEL"],
                self.app.config["GEMINI_FALLBACK_MODEL"],
            ],
        )

    def test_gemini_wrapper_can_request_json_response_format(self):
        fake_client = MagicMock()
        fake_client.models.generate_content.return_value.text = '{"resposta":"Olá","humor":"🙂 Calma","sugestoes":[]}'
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            with patch("google.genai.Client", return_value=fake_client):
                generate_reply(
                    "Instrução",
                    "Pergunta",
                    response_mime_type="application/json",
                )
        config = fake_client.models.generate_content.call_args.kwargs["config"]
        self.assertEqual(config.response_mime_type, "application/json")

    def test_gemini_does_not_retry_fallback_for_non_overload_errors(self):
        fake_client = MagicMock()
        fake_client.models.generate_content.side_effect = ServerError(
            404,
            {"error": {"message": "model not found"}},
        )
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            with patch("google.genai.Client", return_value=fake_client):
                with self.assertRaises(ServerError):
                    generate_reply("Instrução", "Pergunta")

        fake_client.models.generate_content.assert_called_once()

    def test_ai_routes_handle_missing_key_and_invalid_inputs(self):
        self.login("comunidade")
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
            response = self.client.post(
                "/api/chat/interview",
                json={"npc": "agricultora", "message": "Pergunta"},
            )
            self.assertEqual(response.status_code, 503)
            self.assertIn("GEMINI_API_KEY", response.get_json()["error"])

            response = self.client.post(
                "/api/chat/tutor",
                json={"message": "Pergunta", "history": []},
            )
            self.assertEqual(response.status_code, 503)
            self.assertIn("GEMINI_API_KEY", response.get_json()["error"])

        for payload in (
            {"npc": "inexistente", "message": "Pergunta"},
            {"npc": "agricultora", "message": "x" * 1501},
            {"npc": "agricultora", "message": ""},
        ):
            with self.subTest(payload=payload):
                response = self.client.post("/api/chat/interview", json=payload)
                self.assertEqual(response.status_code, 400)

    def test_admin_dashboard_and_editors_support_core_actions(self):
        self.login("admin")
        for path in (
            "/admin/",
            "/admin/content",
            "/admin/tasks",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

        content = ContentBlock.query.filter_by(section_key="map_intro").one()
        response = self.client.post(
            "/admin/content",
            data={
                "id": content.id,
                "title": "Tela inicial revisada",
                "body_text": "Conteúdo atualizado.",
                "button_label": "Investigar",
                "hint_text": "Dica",
                "image_url": "https://example.test/mapa.png",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(content.title, "Tela inicial revisada")
        self.assertEqual(content.image_url, "https://example.test/mapa.png")
        dashboard = self.client.get("/admin/")
        self.assertNotIn(b"Layout do mapa", dashboard.data)
        self.assertEqual(self.client.get("/admin/map-layout").status_code, 404)

        role_id = self.roles["comunidade"].id
        response = self.client.post(
            "/admin/tasks",
            data={
                "role_id": role_id,
                "title": "Missão criada pelo professor",
                "description": "Nova pergunta.",
                "action_type": "text",
                "is_active": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        created_task = Task.query.filter_by(title="Missão criada pelo professor").one()
        response = self.client.post(
            "/admin/tasks",
            data={
                "id": created_task.id,
                "role_id": role_id,
                "title": "Missão atualizada",
                "description": "Pergunta revisada.",
                "action_type": "action",
                "is_active": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(created_task.title, "Missão atualizada")
        response = self.client.post(
            "/admin/tasks",
            data={"id": created_task.id, "action": "delete"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(db.session.get(Task, created_task.id))

    def test_admin_rejects_invalid_content_image_uploads(self):
        self.login("admin")
        content = ContentBlock.query.filter_by(section_key="map_intro").one()
        response = self.client.post(
            "/admin/content",
            data={
                "id": content.id,
                "title": "Início",
                "image_file": (bytes("not-an-image", "utf-8"), "fake.png"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(content.image_url)

    def test_admin_uploads_valid_image_to_static_uploads(self):
        self.login("admin")
        content = ContentBlock.query.filter_by(section_key="map_intro").one()
        png_header = b"\x89PNG\r\n\x1a\n" + b"test image bytes"
        with TemporaryDirectory() as upload_directory:
            with patch.object(self.app, "_static_folder", upload_directory):
                response = self.client.post(
                    "/admin/content",
                    data={
                        "id": content.id,
                        "title": content.title,
                        "image_file": (BytesIO(png_header), "map.png"),
                    },
                    content_type="multipart/form-data",
                )
            self.assertEqual(response.status_code, 302)
            self.assertRegex(content.image_url, r"^/static/uploads/[0-9a-f]+\.png$")
            stored_image = os.path.join(upload_directory, "uploads", content.image_url.rsplit("/", 1)[1])
            with open(stored_image, "rb") as uploaded:
                self.assertEqual(uploaded.read(), png_header)

    def test_all_modal_buttons_reference_existing_dialogs(self):
        page_roles = {
            "/student/community": "comunidade",
            "/student/termobr": "termobr",
            "/student/hydrosul": "hydrosul",
            "/student/scientists": "cientistas",
        }
        for path, role_name in page_roles.items():
            with self.subTest(path=path, role=role_name):
                self.login(role_name)
                response = self.client.get(path)
                html = response.get_data(as_text=True)
                targets = set(re.findall(r"openModal\(['\"]([^'\"]+)", html))
                element_ids = set(re.findall(r'\bid="([^"]+)"', html))
                self.assertTrue(targets)
                self.assertTrue(targets.issubset(element_ids), targets - element_ids)
                for target in targets:
                    self.assertRegex(
                        html,
                        rf"closeModal\(['\"]{re.escape(target)}['\"]\)",
                    )

    def test_admin_can_update_simulation_parameters(self):
        self.login("admin")
        variable = SimulationVariable.query.filter_by(var_key="so2_gas_base").one()
        response = self.client.post(
            "/admin/simvars",
            data={"var_so2_gas_base": "50.5"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(variable.value, 50.5)

        response = self.client.post(
            "/admin/simvars",
            data={"var_so2_gas_base": "not-a-number"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(variable.value, 50.5)
        dashboard = self.client.get("/admin/")
        self.assertIn(b"deve conter um n\xc3\xbamero v\xc3\xa1lido", dashboard.data)

    def test_javascript_modules_pass_node_syntax_checks_when_node_is_available(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js is not installed.")
        scripts_directory = os.path.join(os.path.dirname(__file__), "..", "static", "js")
        for filename in os.listdir(scripts_directory):
            if not filename.endswith(".js"):
                continue
            script_path = os.path.join(scripts_directory, filename)
            with self.subTest(script=filename):
                result = subprocess.run(
                    [node, "--check", script_path],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

if __name__ == "__main__":
    unittest.main()
