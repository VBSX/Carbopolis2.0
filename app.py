from flask import Flask, flash, redirect, url_for
from flask_login import current_user

from config import Config
from extensions import db, login_manager


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    login_manager.init_app(app)

    from models import UserSession  # noqa: F401
    from routes.admin import admin_bp
    from routes.auth import auth_bp
    from routes.chat import chat_bp
    from routes.simulator import simulator_bp
    from routes.student import student_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(student_bp)
    app.register_blueprint(simulator_bp)
    app.register_blueprint(admin_bp)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(UserSession, int(user_id))

    @app.before_request
    def touch_session():
        if current_user.is_authenticated:
            from datetime import datetime, timezone

            current_user.last_active = datetime.now(timezone.utc)
            db.session.commit()

    @app.context_processor
    def inject_globals():
        role_labels = {
            "termobr": "TermoBR",
            "hydrosul": "HydroSul",
            "comunidade": "Comunidade de Ivaí",
            "cientistas": "Cientistas Ambientais",
            "admin": "Professor / Administração",
        }
        return {
            "role_labels": role_labels,
            "current_role": current_user.role_name if current_user.is_authenticated else None,
        }

    @app.route("/")
    def index():
        if current_user.is_authenticated:
            if current_user.role_name == "admin":
                return redirect(url_for("admin.dashboard"))
            return redirect(url_for("student.home_view"))
        return redirect(url_for("auth.login"))

    @app.errorhandler(403)
    def forbidden(_error):
        flash("Acesso negado para o seu grupo: este conteúdo pertence a outro grupo.", "error")
        if current_user.is_authenticated and current_user.role_name == "admin":
            return redirect(url_for("admin.dashboard"))
        if current_user.is_authenticated:
            return redirect(url_for("student.home_view"))
        return redirect(url_for("auth.login"))

    with app.app_context():
        db.create_all()

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
