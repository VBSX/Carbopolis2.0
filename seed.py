"""Seed via URL direta (skill neon-postgres: migracoes/seed usam UNPOOLED)."""
import os
from app import create_app
from extensions import db
from models import ContentBlock, Role, SimulationVariable, Task

ROLES = [
    ("termobr", "termo", "TermoBR", "Equipe que representa a proposta de usina termelétrica"),
    ("hydrosul", "hidro", "HydroSul", "Equipe que representa a proposta de usina hidrelétrica"),
    ("comunidade", "ivai", "Comunidade de Ivaí", "Representantes dos moradores e agricultores de Ivaí dos Campos"),
    ("cientistas", "energia", "Cientistas Ambientais", "Equipe do Instituto de Pesquisas que modelará os impactos previstos pelas propostas"),
    ("admin", "admin", "Professor / Administração", "Administração do jogo"),
]

VARS = {
    "so2_gas_base": (45.0, "Concentração base de SO2 com gás natural (ppm)"),
    "nox_gas_base": (55.0, "Concentração base de NOx com gás natural (ppm)"),
    "co2_gas_base": (68.0, "Concentração base de CO2 com gás natural (ppm)"),
    "so2_coal_base": (180.0, "Concentração base de SO2 com carvão mineral (ppm)"),
    "nox_coal_base": (125.0, "Concentração base de NOx com carvão mineral (ppm)"),
    "co2_coal_base": (98.0, "Concentração base de CO2 com carvão mineral (ppm)"),
    "filter_so2_nox_reduction": (0.70, "Redução de SO2/NOx com filtros lavadores"),
    "filter_cost": (18.0, "Custo econômico da instalação de filtros"),
    "fish_ladder_cost": (10.0, "Custo econômico da escada de peixes"),
    "relocation_cost": (16.0, "Custo do plano de reassentamento justo"),
    "flooded_area_percent_per_meter": (0.35, "Área alagada (%) por metro de barragem"),
    "families_per_flood_percent": (4.2, "Famílias desapropriadas por % alagado"),
    "mw_per_dam_meter": (2.4, "Potência gerada (MW) por metro de barragem"),
    "thermal_base_mw": (180.0, "Potência base da termelétrica (MW)"),
    "hydro_build_time_penalty": (22.0, "Penalidade de tempo de obra da hidrelétrica"),
    "thermal_jobs": (28.0, "Empregos gerados pela termelétrica"),
    "hydro_jobs": (42.0, "Empregos gerados pela hidrelétrica"),
    "royalty_thermal": (22.0, "Royalties e impostos da termelétrica"),
    "royalty_hydro": (30.0, "Royalties da água da hidrelétrica"),
    "health_emission_weight": (0.18, "Peso dos problemas respiratórios na saúde"),
    "aquatic_fauna_penalty": (18.0, "Penalidade ambiental sobre a fauna aquática"),
    "mixed_thermal_share": (0.45, "Participação térmica no modelo misto"),
}

TASKS = [
    # (papel, título, pergunta norteadora oficial, tipo)
    ("cientistas", "Q1 — Fauna local", "Quais impactos sobre a fauna local poderiam ocorrer em cada proposta caso fosse aprovada?", "text"),
    ("cientistas", "Q2 — Qualidade do ar", "Como as emissões previstas poderiam afetar a qualidade do ar caso a proposta TermoBR fosse aprovada?", "text"),
    ("cientistas", "Q3 — Alagamento × vida aquática", "Como o alagamento previsto poderia afetar a vida aquática caso a proposta HydroSul fosse aprovada?", "text"),
    ("cientistas", "Bancada — Análise de pH do Rio", "Simule um cenário de pH no laboratório e registre a projeção didática no dossiê.", "action"),
    ("cientistas", "Bancada — Medir SO2/NOx/CO2", "Execute a simulação de emissões e registre as concentrações projetadas.", "action"),
    ("comunidade", "Q1 — Renda agrícola e saúde", "Se uma das propostas for aprovada, como a possível perda de área agrícola e as emissões previstas poderão afetar a renda e a saúde da comunidade?", "text"),
    ("comunidade", "Q2 — Indenização", "Se a proposta HydroSul for aprovada e famílias precisarem ser realocadas, quais garantias e indenizações deverão ser previstas?", "text"),
    ("comunidade", "Q3 — Prejuízo à rotina", "Qual dos projetos poderá trazer maior prejuízo à rotina da comunidade caso seja aprovado? Justifique com evidências.", "text"),
    ("termobr", "Q1 — Rapidez da termelétrica", "Se a proposta TermoBR for aprovada, em quanto tempo a construção poderia começar a contribuir para reduzir os apagões de Ivaí dos Campos?", "text"),
    ("termobr", "Q2 — Empregos e polo industrial", "Quantos empregos e quais benefícios econômicos a proposta poderia gerar, e como eles poderiam ser comparados aos impactos previstos?", "text"),
    ("termobr", "Q3 — Gás × hidrelétrica", "Quais argumentos técnicos e econômicos poderiam sustentar a proposta a gás diante da alternativa hidrelétrica e da dependência de chuvas?", "text"),
    ("termobr", "Q4 — Longo prazo e soluções", "Se a proposta for aprovada, como a implantação e a operação poderiam afetar a população a longo prazo e quais medidas poderiam reduzir esses riscos?", "text"),
    ("hydrosul", "Q1 — Hidro renovável e limpa", "Se aprovada, como a proposta hidrelétrica poderia gerar energia renovável e quais emissões de gases de efeito estufa ainda precisariam ser avaliadas?", "text"),
    ("hydrosul", "Q2 — Royalties e empregos", "Quais benefícios econômicos futuros, como royalties e empregos, poderiam ser gerados se a proposta fosse aprovada?", "text"),
    ("hydrosul", "Q3 — Mitigação e compensação", "Se a proposta HydroSul for aprovada e famílias precisarem ser realocadas, que plano de mitigação, compensação e apoio deverá ser oferecido?", "text"),
]

CONTENTS = [
    ("map_intro", "Comitê de Avaliação de Propostas Energéticas", "Ivaí dos Campos enfrenta apagões e avaliará duas propostas ainda não aprovadas: a termelétrica da TermoBR e a hidrelétrica da HydroSul. Analise os Estudos de Impacto Ambiental e reúna evidências para o Júri Simulado, onde a decisão final será debatida.", "Avaliar propostas", "Compare os cenários antes do Júri Simulado."),
    ("lab_intro", "Laboratório de Modelagem Ambiental", "Realize testes preditivos e simulações baseadas nos Estudos de Impacto Ambiental (EIA) submetidos pelas empresas para prever o que acontecerá com Ivaí dos Campos se os projetos forem aprovados.", "Simular cenários", "Os resultados são projeções, não medições de usinas existentes."),
    ("sim_intro", "Simulador de Cenários Energéticos", "Compare as consequências possíveis das propostas TermoBR e HydroSul e do modelo misto. Nenhuma usina foi aprovada ou construída; os índices são projeções para apoiar o Júri Simulado.", "Simular cenários", "Avalie os cenários antes da decisão final."),
]


def run():
    # Seed usa a conexao direta (UNPOOLED) conforme skill neon-postgres.
    direct = os.getenv("DATABASE_URL_UNPOOLED")
    if direct:
        os.environ["DATABASE_URL"] = direct
    app = create_app()
    with app.app_context():
        db.create_all()
        for name, pwd, disp, desc in ROLES:
            r = Role.query.filter_by(name=name).first()
            if not r:
                r = Role(name=name, password=pwd, display_name=disp, description=desc)
                db.session.add(r)
            else:
                r.password = pwd
                r.display_name = disp
                r.description = desc
        db.session.commit()
        for key, (val, desc) in VARS.items():
            row = SimulationVariable.query.filter_by(var_key=key).first()
            if not row:
                db.session.add(SimulationVariable(var_key=key, value=val, description=desc))
            else:
                row.description = desc
        for sec, title, body, btn, hint in CONTENTS:
            b = ContentBlock.query.filter_by(section_key=sec).first()
            if not b:
                db.session.add(ContentBlock(role_id=None, section_key=sec, title=title, body_text=body, button_label=btn, hint_text=hint))
            else:
                b.title = title
                b.body_text = body
                b.button_label = btn
                b.hint_text = hint
        for rname, title, desc, atype in TASKS:
            role = Role.query.filter_by(name=rname).first()
            exists = Task.query.filter_by(role_id=role.id, title=title).first()
            if not exists:
                db.session.add(Task(role_id=role.id, title=title, description=desc, action_type=atype, is_active=True))
            else:
                # atualiza a descricao caso o titulo antigo (sem acento) coincida pelo prefixo Q
                exists.description = desc
                exists.action_type = atype
        db.session.commit()
        print("Seed OK: roles, vars, tasks, contents.")

if __name__ == "__main__":
    run()
