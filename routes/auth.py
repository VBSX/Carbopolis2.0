"""Login por senha do grupo e logout."""
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_user, logout_user, current_user

from extensions import db
from models import Role, UserSession

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        if current_user.role_name == "admin":
            return redirect(url_for("admin.dashboard"))
        return redirect(url_for("student.home_view"))

    if request.method == "POST":
        password = (request.form.get("password") or "").strip()
        members = (request.form.get("members_text") or "").strip()
        role = Role.query.filter_by(password=password).first()
        if not role:
            flash("Senha do grupo incorreta. Confira a senha do seu grupo.", "error")
            return render_template("login.html"), 401
        session = UserSession(role_id=role.id, members_text=members or None)
        db.session.add(session)
        db.session.commit()
        login_user(session)
        flash(f"Bem-vindo(a), {role.display_name}!", "success")
        if role.name == "admin":
            return redirect(url_for("admin.dashboard"))
        return redirect(url_for("student.home_view"))

    return render_template("login.html")


@auth_bp.route("/logout")
def logout():
    logout_user()
    flash("Sessão encerrada.", "info")
    return redirect(url_for("auth.login"))
