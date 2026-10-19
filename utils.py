from functools import wraps

from flask import flash, redirect, url_for
from flask_login import current_user, login_required

from models import ContentBlock, SimulationVariable


STUDENT_ROLES = ("termobr", "hydrosul", "comunidade", "cientistas")
def role_required(*roles):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated or current_user.role_name not in roles:
                flash("Acesso negado: este módulo não pertence ao seu grupo.", "error")
                if current_user.is_authenticated and current_user.role_name == "admin":
                    return redirect(url_for("admin.dashboard"))
                if current_user.is_authenticated:
                    return redirect(url_for("student.home_view"))
                return redirect(url_for("auth.login"))
            return view(*args, **kwargs)

        return wrapped

    return decorator


def student_required(view):
    return role_required(*STUDENT_ROLES, "admin")(view)


def lab_required(view):
    """Apenas cientistas (e admin) manipulam o Laboratório Virtual."""
    return role_required("cientistas", "admin")(view)


def termobr_required(view):
    """Apenas termobr (e admin) acessam a sede da TermoBR."""
    return role_required("termobr", "admin")(view)


def hydrosul_required(view):
    """Apenas hydrosul (e admin) acessam o complexo da HydroSul."""
    return role_required("hydrosul", "admin")(view)


def scientists_required(view):
    """Apenas cientistas (e admin) acessam o Instituto de Pesquisas Científicas."""
    return role_required("cientistas", "admin")(view)


def admin_required(view):
    return role_required("admin")(view)


def get_content(section_key, default_title="", default_body=""):
    block = ContentBlock.query.filter_by(section_key=section_key).first()
    if block:
        return block
    return ContentBlock(
        section_key=section_key,
        title=default_title,
        body_text=default_body,
        button_label="",
        hint_text="",
    )


def get_sim_vars():
    rows = SimulationVariable.query.all()
    return {row.var_key: row.value for row in rows}


def clamp(value, minimum=0.0, maximum=100.0):
    return max(minimum, min(maximum, value))
