import click
from flask import Flask, current_app, flash, redirect, url_for
from flask_login import current_user

from config import Config
from extensions import db, login_manager
from sqlalchemy.exc import SQLAlchemyError


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

    @app.cli.command("reset-user-data")
    @click.option(
        "--yes",
        is_flag=True,
        help="Confirma a exclusão permanente dos dados pessoais e de atividade.",
    )
    def reset_user_data(yes):
        """Apaga atividade das equipes, preservando conteúdo e configuração."""
        from user_data import clear_user_data, get_user_data_counts

        counts = get_user_data_counts()

        if not yes:
            click.echo("Prévia: estes dados seriam apagados:")
            for label, count in counts:
                click.echo(f"  {label}: {count}")
            click.echo(
                "Nada foi alterado. Para confirmar a limpeza, execute novamente "
                "com --yes."
            )
            return

        try:
            clear_user_data()
        except SQLAlchemyError as error:
            db.session.rollback()
            current_app.logger.exception("Falha ao limpar dados de atividade.")
            raise click.ClickException(
                "A limpeza falhou e a transação foi revertida; nenhum dado foi "
                "confirmado como apagado."
            ) from error

        click.echo("Dados de atividade apagados:")
        for label, count in counts:
            click.echo(f"  {label}: {count}")
        click.echo(
            "Grupos, senhas, missões, conteúdo e configurações do simulador foram preservados."
        )

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
