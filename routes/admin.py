"""Painel CMS do professor."""
import math
import secrets
from pathlib import Path

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from flask_login import logout_user
from extensions import db
from models import ContentBlock, Role, SimulationVariable, Task
from models import LabSample, SimulationResult, UserSession
from sqlalchemy.exc import SQLAlchemyError
from user_data import clear_user_data, get_user_data_counts
from utils import admin_required

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")
IMAGE_EXTENSIONS = {
    ".jpg": (".jpg", (b"\xff\xd8\xff",)),
    ".jpeg": (".jpg", (b"\xff\xd8\xff",)),
    ".png": (".png", (b"\x89PNG\r\n\x1a\n",)),
    ".webp": (".webp", (b"RIFF",)),
    ".gif": (".gif", (b"GIF87a", b"GIF89a")),
}
MAX_IMAGE_SIZE = 8 * 1024 * 1024
def _save_uploaded_image(upload):
    if not upload or not upload.filename:
        return None
    extension = Path(upload.filename).suffix.lower()
    image_type = IMAGE_EXTENSIONS.get(extension)
    if not image_type:
        raise ValueError("Use uma imagem JPG, PNG, WEBP ou GIF.")
    content = upload.stream.read(MAX_IMAGE_SIZE + 1)
    if len(content) > MAX_IMAGE_SIZE:
        raise ValueError("A imagem deve ter no máximo 8 MB.")
    signatures = image_type[1]
    if not any(content.startswith(signature) for signature in signatures):
        raise ValueError("O arquivo enviado não parece ser uma imagem válida.")
    if extension == ".webp" and content[8:12] != b"WEBP":
        raise ValueError("O arquivo WEBP enviado não é válido.")

    filename = f"{secrets.token_hex(16)}{image_type[0]}"
    upload_dir = Path(current_app.static_folder) / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    (upload_dir / filename).write_bytes(content)
    return url_for("static", filename=f"uploads/{filename}")


@admin_bp.route("/")
@admin_required
def dashboard():
    stats = {}
    stats["roles"] = Role.query.count()
    stats["tasks"] = Task.query.count()
    stats["samples"] = LabSample.query.count()
    stats["sims"] = SimulationResult.query.count()
    stats["contents"] = ContentBlock.query.count()
    stats["sessions"] = UserSession.query.count()
    roles = Role.query.all()
    tasks = Task.query.order_by(Task.id.desc()).limit(30).all()
    contents = ContentBlock.query.order_by(ContentBlock.id).all()
    simvars = SimulationVariable.query.order_by(SimulationVariable.var_key).all()
    return render_template("admin/dashboard.html", stats=stats, roles=roles, tasks=tasks, contents=contents, simvars=simvars)


@admin_bp.route("/reset-user-data", methods=["GET", "POST"])
@admin_required
def reset_user_data():
    if request.method == "POST":
        csrf_token = request.form.get("csrf_token", "")
        expected_token = session.get("reset_user_data_csrf", "")
        if (
            not expected_token
            or not secrets.compare_digest(csrf_token, expected_token)
            or request.form.get("confirmation") != "LIMPAR DADOS"
        ):
            flash(
                "Confirmação inválida. Nenhum dado foi apagado; revise a prévia e tente novamente.",
                "error",
            )
            return redirect(url_for("admin.reset_user_data"))

        try:
            counts = clear_user_data()
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.exception("Falha ao limpar dados de atividade pelo painel administrativo.")
            flash("A limpeza falhou e foi revertida. Nenhum dado foi confirmado como apagado.", "error")
            return redirect(url_for("admin.dashboard"))

        session.pop("reset_user_data_csrf", None)
        logout_user()
        current_app.logger.warning("Dados de atividade apagados pelo painel administrativo: %s", counts)
        flash(
            "Limpeza concluída. As senhas e configurações dos grupos foram preservadas; entre novamente.",
            "success",
        )
        return redirect(url_for("auth.login"))

    csrf_token = secrets.token_urlsafe(32)
    session["reset_user_data_csrf"] = csrf_token
    return render_template(
        "admin/reset_user_data.html",
        counts=get_user_data_counts(),
        csrf_token=csrf_token,
    )


@admin_bp.route("/content", methods=["GET", "POST"])
@admin_required
def content_editor():
    if request.method == "POST":
        content_id = request.form.get("id", type=int)
        b = db.session.get(ContentBlock, content_id) if content_id else None
        if b:
            try:
                uploaded_image = _save_uploaded_image(request.files.get("image_file"))
            except ValueError as error:
                flash(str(error), "error")
                return redirect(url_for("admin.content_editor"))
            b.title = request.form.get("title", b.title).strip()
            b.body_text = request.form.get("body_text", "").strip()
            b.button_label = request.form.get("button_label", "").strip()
            b.hint_text = request.form.get("hint_text", "").strip()
            b.image_url = uploaded_image or (
                None if request.form.get("remove_image") else request.form.get("image_url", "").strip() or None
            )
            db.session.commit()
            flash("Conteúdo atualizado com sucesso!", "success")
        return redirect(url_for("admin.content_editor"))
    contents = ContentBlock.query.order_by(ContentBlock.id).all()
    return render_template("admin/content_editor.html", contents=contents)


@admin_bp.route("/tasks", methods=["GET", "POST"])
@admin_required
def task_editor():
    roles = Role.query.all()
    if request.method == "POST":
        act = request.form.get("action", "save")
        if act == "delete":
            task_id = request.form.get("id", type=int)
            t = db.session.get(Task, task_id) if task_id else None
            if t:
                db.session.delete(t)
                db.session.commit()
                flash("Tarefa excluída.", "info")
        else:
            task_id = request.form.get("id", type=int)
            t = db.session.get(Task, task_id) if task_id else None
            if not t:
                t = Task(role_id=int(request.form.get("role_id")), title=request.form.get("title", "Nova tarefa"))
                db.session.add(t)
            t.role_id = int(request.form.get("role_id", t.role_id))
            t.title = request.form.get("title", t.title)
            t.description = request.form.get("description")
            t.action_type = request.form.get("action_type", "text")
            t.is_active = bool(request.form.get("is_active"))
            db.session.commit()
            flash("Tarefa salva com sucesso!", "success")
        return redirect(url_for("admin.task_editor"))
    tasks = Task.query.order_by(Task.id.desc()).all()
    return render_template("admin/task_editor.html", tasks=tasks, roles=roles)

@admin_bp.route("/simvars", methods=["POST"])
@admin_required
def simvars_update():
    for key, val in request.form.items():
        if key.startswith("var_"):
            vk = key[4:]
            row = SimulationVariable.query.filter_by(var_key=vk).first()
            if row:
                try:
                    value = float(val)
                except ValueError:
                    db.session.rollback()
                    flash(f"O parâmetro {vk} deve conter um número válido.", "error")
                    return redirect(url_for("admin.dashboard"))
                if not math.isfinite(value):
                    db.session.rollback()
                    flash(f"O parâmetro {vk} deve conter um número finito.", "error")
                    return redirect(url_for("admin.dashboard"))
                row.value = value
    db.session.commit()
    flash("Parâmetros do simulador atualizados!", "success")
    return redirect(url_for("admin.dashboard"))
