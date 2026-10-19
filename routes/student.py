"""Rotas do aluno: tela inicial, laboratório, tarefas e relatório."""
from datetime import datetime, timezone
from io import BytesIO
import math
from html import escape
from flask import Blueprint, flash, jsonify, redirect, render_template, request, send_file, url_for
from extensions import db
from models import LabSample, ReportDraft, Role, SavedQuote, SimulationResult, StudentTaskProgress, Task
from utils import student_required, lab_required, termobr_required, hydrosul_required, scientists_required, get_content

student_bp = Blueprint("student", __name__)


def _pdf_escape(value):
    text = str(value).encode("cp1252", errors="replace").decode("cp1252")
    return escape(text)


def _public_lab_reports():
    from models import Role as _Role

    samples = (
        LabSample.query.join(_Role, LabSample.role_id == _Role.id)
        .filter(_Role.name == "cientistas", LabSample.saved_to_dossier.is_(True))
        .order_by(LabSample.created_at.desc(), LabSample.id.desc())
        .all()
    )
    reports = []
    for sample in samples:
        sample_name = "água" if sample.sample_type == "water" else "ar"
        title = "Laudo de análise da água" if sample.sample_type == "water" else "Laudo de análise do ar"
        measurements = []
        for label, field, unit in (
            ("pH", "ph_value", ""),
            ("SO₂", "so2_ppm", " ppm"),
            ("NOₓ", "nox_ppm", " ppm"),
            ("CO₂", "co2_ppm", " ppm"),
            ("Temperatura", "temp_celsius", " °C"),
            ("Oxigênio dissolvido", "od_value", " mg/L"),
        ):
            value = getattr(sample, field)
            if value is not None:
                measurements.append(f"{label}: {value:g}{unit}")
        conclusion_parts = [sample.notes.strip()] if sample.notes and sample.notes.strip() else []
        if measurements:
            conclusion_parts.append("; ".join(measurements))
        if not conclusion_parts:
            conclusion_parts.append(f"Análise de {sample_name} registrada pelo Instituto de Pesquisas.")
        reports.append(
            {
                "id": sample.id,
                "title": title,
                "conclusion": " — ".join(conclusion_parts),
                "timestamp": sample.created_at.strftime("%d/%m/%Y %H:%M"),
                "author": "Cientistas",
            }
        )
    return reports


@student_bp.route("/student/home")
@student_required
def home_view():
    intro = get_content(
        "map_intro",
        "Ivaí dos Campos",
        "Explore os espaços e reúna evidências para o júri.",
    )
    return render_template("student/home.html", intro=intro, public_reports=_public_lab_reports())


@student_bp.route("/api/lab/public_reports")
def public_lab_reports_api():
    return jsonify(_public_lab_reports())


@student_bp.route("/student/map")
@student_required
def legacy_map_redirect():
    return redirect(url_for("student.home_view"), code=301)


from flask_login import current_user as _cu
from datetime import datetime as _dt, timezone as _tz
@student_bp.route("/student/lab", methods=["GET", "POST"])
@lab_required
def lab_view():
    from extensions import db as _db
    from models import LabSample as _LS
    if request.method == "POST":
        measurements = {}
        try:
            for field in ("ph_value", "so2_ppm", "nox_ppm", "co2_ppm", "temp_celsius", "od_value"):
                value = request.form.get(field)
                measurement = float(value) if value not in (None, "") else None
                if measurement is not None and not math.isfinite(measurement):
                    raise ValueError
                measurements[field] = measurement
        except ValueError:
            flash("Valor numérico inválido. Confira os campos preenchidos.", "error")
            return redirect(url_for("student.lab_view"))
        sample_type = request.form.get("sample_type", "water")
        if sample_type not in ("water", "air"):
            flash("Tipo de amostra inválido.", "error")
            return redirect(url_for("student.lab_view"))
        s = _LS(
            role_id=_cu.role_id,
            sample_type=sample_type,
            **measurements,
            notes=request.form.get("notes"),
            saved_to_dossier=bool(request.form.get("saved_to_dossier")),
        )
        _db.session.add(s); _db.session.commit()
        flash("Amostra registrada e salva no dossiê!" if s.saved_to_dossier else "Amostra registrada com sucesso!", "success")
        return redirect(url_for("student.lab_view"))
    samples = _LS.query.filter_by(role_id=_cu.role_id).order_by(_LS.created_at.desc()).limit(20).all()
    released = _LS.query.filter_by(saved_to_dossier=True).order_by(_LS.created_at.desc()).limit(20).all()
    intro = get_content("lab_intro", "Laboratório Ambiental", "Analise amostras de água e ar nas bancadas guiadas passo a passo.")
    return render_template("student/lab.html", samples=samples, released=released, intro=intro)
@student_bp.route("/student/community")
@student_required
def community_view():
    from models import LabSample as _LS4
    released = _LS4.query.filter_by(saved_to_dossier=True).order_by(_LS4.created_at.desc()).limit(20).all()
    return render_template("student/community.html", released=released)


@student_bp.route("/student/termobr")
@termobr_required
def termobr_view():
    return render_template("student/termobr.html")


@student_bp.route("/student/hydrosul")
@hydrosul_required
def hydrosul_view():
    return render_template("student/hydrosul.html")


@student_bp.route("/student/scientists")
@scientists_required
def scientists_view():
    return render_template("student/scientists.html")


@student_bp.route("/student/tasks", methods=["GET", "POST"])
@student_required
def tasks_view():
    from extensions import db as _db2
    from models import StudentTaskProgress as _P
    if request.method == "POST":
        task_id = request.form.get("task_id", type=int)
        t = db.session.get(Task, task_id) if task_id else None
        if not t or t.role_id != _cu.role_id:
            flash("Tarefa inválida para o seu grupo.", "error"); return redirect(url_for("student.tasks_view"))
        p = _P.query.filter_by(task_id=t.id, role_id=_cu.role_id).first()
        if not p:
            p = _P(task_id=t.id, role_id=_cu.role_id); _db2.session.add(p)
        p.answer_text = request.form.get("answer_text",""); p.is_completed = True; p.completed_at = _dt.now(_tz.utc)
        _db2.session.commit()
        flash("Missão cumprida! Resposta salva com sucesso.", "success"); return redirect(url_for("student.tasks_view"))
    tasks = Task.query.filter_by(role_id=_cu.role_id, is_active=True).all()
    prog = {x.task_id: x for x in _P.query.filter_by(role_id=_cu.role_id).all()}
    return render_template("student/tasks.html", tasks=tasks, progress=prog)
@student_bp.route("/student/report", methods=["GET", "POST"])
@student_required
def report_view():
    from extensions import db as _db3
    from models import ReportDraft as _R, SimulationResult as _S
    d = _R.query.filter_by(role_id=_cu.role_id).first()
    if request.method == "POST":
        if not d:
            d = _R(role_id=_cu.role_id); _db3.session.add(d)
        if request.form.get("guiding_answers"): d.guiding_answers = request.form.get("guiding_answers")
        if request.form.get("jury_question") is not None: d.jury_question = request.form.get("jury_question")
        if request.form.get("members_text") is not None: _cu.members_text = request.form.get("members_text")
        _db3.session.commit()
        flash("Dossiê atualizado com sucesso!", "success"); return redirect(url_for("student.report_view"))
    samp = _LS2.query.filter_by(role_id=_cu.role_id, saved_to_dossier=True).all() if False else None
    from models import LabSample as _LS3
    samp = _LS3.query.filter_by(role_id=_cu.role_id, saved_to_dossier=True).all()
    quotes = SavedQuote.query.filter_by(role_id=_cu.role_id).order_by(
        SavedQuote.timestamp.desc(), SavedQuote.id.desc()
    ).all()
    last = _S.query.filter_by(role_id=_cu.role_id).order_by(_S.created_at.desc()).first()
    from models import Role as _Role, Task as _T, StudentTaskProgress as _P
    role = db.session.get(_Role, _cu.role_id)
    tasks = _T.query.filter_by(role_id=_cu.role_id, is_active=True).order_by(_T.id).all()
    prog = {x.task_id: x for x in _P.query.filter_by(role_id=_cu.role_id).all()}
    return render_template("student/report.html", draft=d, samples=samp, last_sim=last, role=role, tasks=tasks, progress=prog, quotes=quotes)


@student_bp.route("/student/report/pdf")
@student_required
def report_pdf():
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    role = db.session.get(Role, _cu.role_id)
    tasks = Task.query.filter_by(role_id=_cu.role_id, is_active=True).order_by(Task.id).all()
    progress = {
        item.task_id: item
        for item in StudentTaskProgress.query.filter_by(role_id=_cu.role_id).all()
    }
    samples = LabSample.query.filter_by(
        role_id=_cu.role_id, saved_to_dossier=True
    ).order_by(LabSample.created_at.desc()).all()
    quotes = SavedQuote.query.filter_by(role_id=_cu.role_id).order_by(
        SavedQuote.timestamp.desc(), SavedQuote.id.desc()
    ).all()
    draft = ReportDraft.query.filter_by(role_id=_cu.role_id).first()
    simulation = SimulationResult.query.filter_by(role_id=_cu.role_id).order_by(
        SimulationResult.created_at.desc()
    ).first()

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="DossierTitle",
        parent=styles["Title"],
        alignment=TA_CENTER,
        textColor=colors.HexColor("#12304a"),
        spaceAfter=8 * mm,
    ))
    styles.add(ParagraphStyle(
        name="DossierSection",
        parent=styles["Heading2"],
        textColor=colors.HexColor("#125b68"),
        spaceBefore=5 * mm,
        spaceAfter=2 * mm,
    ))
    story = [
        Paragraph("Dossiê da Audiência Pública", styles["DossierTitle"]),
        Paragraph(f"Grupo: {_pdf_escape(role.display_name)}", styles["Normal"]),
        Paragraph(f"Integrantes: {_pdf_escape(_cu.members_text or '—')}", styles["Normal"]),
        Spacer(1, 4 * mm),
    ]

    if simulation:
        energy_name = {
            "thermal": "Proposta TermoBR — Termelétrica",
            "hydro": "Proposta HydroSul — Hidrelétrica",
        }.get(simulation.energy_choice, "Cenário energético")
        story.append(Paragraph("Simulação de decisão", styles["DossierSection"]))
        story.append(Paragraph(
            f"{energy_name}: ambiental {simulation.env_score}, social "
            f"{simulation.social_score}, econômico {simulation.economic_score}, "
            f"energético {simulation.energy_score}.",
            styles["BodyText"],
        ))

    story.append(Paragraph("Respostas às perguntas norteadoras", styles["DossierSection"]))
    for task in tasks:
        answer = progress.get(task.id)
        text = answer.answer_text if answer and answer.answer_text else "Ainda sem resposta."
        story.append(Paragraph(f"<b>{_pdf_escape(task.title)}</b>", styles["BodyText"]))
        story.append(Paragraph(_pdf_escape(text), styles["BodyText"]))
        story.append(Spacer(1, 2 * mm))

    story.append(Paragraph("Laudos do Laboratório", styles["DossierSection"]))
    for sample in samples:
        sample_name = "Água" if sample.sample_type == "water" else "Ar"
        values = []
        for label, value, unit in (
            ("pH", sample.ph_value, ""),
            ("SO2", sample.so2_ppm, " ppm"),
            ("NOx", sample.nox_ppm, " ppm"),
            ("CO2", sample.co2_ppm, " ppm"),
            ("Temperatura", sample.temp_celsius, " °C"),
            ("Oxigênio dissolvido", sample.od_value, " mg/L"),
        ):
            if value is not None:
                values.append(f"{label}: {value:g}{unit}")
        text = _pdf_escape("; ".join(values) or "Sem valores numéricos registrados.")
        if sample.notes:
            text = f"{text}<br/>Observações: {_pdf_escape(sample.notes)}"
        story.append(Paragraph(
            f"<b>#{sample.id} {sample_name}</b> — {text}",
            styles["BodyText"],
        ))
        story.append(Spacer(1, 2 * mm))
    if not samples:
        story.append(Paragraph("Nenhum laudo salvo.", styles["BodyText"]))

    story.append(Paragraph("Depoimentos e evidências recolhidas", styles["DossierSection"]))
    for quote in quotes:
        story.append(Paragraph(
            f"“{_pdf_escape(quote.quote_text)}” — {_pdf_escape(quote.character_name)} "
            f"({quote.timestamp.strftime('%d/%m/%Y %H:%M')})",
            styles["BodyText"],
        ))
        story.append(Spacer(1, 2 * mm))
    if not quotes:
        story.append(Paragraph("Nenhum depoimento salvo.", styles["BodyText"]))

    if draft and draft.jury_question:
        story.append(Paragraph("Pergunta ao Júri", styles["DossierSection"]))
        story.append(Paragraph(_pdf_escape(draft.jury_question), styles["BodyText"]))

    pdf_buffer = BytesIO()
    document = SimpleDocTemplate(
        pdf_buffer,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="Dossiê da Audiência Pública",
        author="Carbópolis 2.0",
    )
    document.build(story)
    pdf_buffer.seek(0)
    return send_file(
        pdf_buffer,
        mimetype="application/pdf",
        as_attachment=False,
        download_name=f"dossie_{role.name}.pdf",
        max_age=0,
    )
