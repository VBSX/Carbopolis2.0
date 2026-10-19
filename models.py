from datetime import datetime, timezone

from flask_login import UserMixin

from extensions import db


def utcnow():
    return datetime.now(timezone.utc)


class Role(db.Model):
    __tablename__ = "roles"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    display_name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=True)

    sessions = db.relationship("UserSession", backref="role", lazy=True)
    tasks = db.relationship("Task", backref="role", lazy=True)
    content_blocks = db.relationship("ContentBlock", backref="role", lazy=True)


class UserSession(UserMixin, db.Model):
    __tablename__ = "user_sessions"

    id = db.Column(db.Integer, primary_key=True)
    role_id = db.Column(db.Integer, db.ForeignKey("roles.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    last_active = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)
    members_text = db.Column(db.Text, nullable=True)

    def get_id(self):
        return str(self.id)

    @property
    def role_name(self):
        return self.role.name if self.role else None


class InterviewLog(db.Model):
    __tablename__ = "interview_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_session_id = db.Column(
        db.Integer, db.ForeignKey("user_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    npc_id = db.Column(db.String(40), nullable=False, index=True)
    user_message = db.Column(db.Text, nullable=False)
    assistant_message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)


class SavedQuote(db.Model):
    __tablename__ = "saved_quotes"

    id = db.Column(db.Integer, primary_key=True)
    role_id = db.Column(db.Integer, db.ForeignKey("roles.id"), nullable=False, index=True)
    character_name = db.Column(db.String(120), nullable=False)
    quote_text = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)


class ContentBlock(db.Model):
    __tablename__ = "content_blocks"

    id = db.Column(db.Integer, primary_key=True)
    role_id = db.Column(db.Integer, db.ForeignKey("roles.id"), nullable=True)
    section_key = db.Column(db.String(120), unique=True, nullable=False)
    title = db.Column(db.String(255), nullable=False)
    body_text = db.Column(db.Text, nullable=True)
    button_label = db.Column(db.String(120), nullable=True)
    hint_text = db.Column(db.Text, nullable=True)
    image_url = db.Column(db.String(500), nullable=True)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class MapPoint(db.Model):
    __tablename__ = "map_points"

    id = db.Column(db.String(80), primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    image_url = db.Column(db.String(500), nullable=True)
    icon = db.Column(db.String(24), nullable=False, default="📍")
    visible_roles = db.Column(db.String(255), nullable=False, default="termobr,hydrosul,comunidade,cientistas,admin")
    is_active = db.Column(db.Boolean, nullable=False, default=True)


class Task(db.Model):
    __tablename__ = "tasks"

    id = db.Column(db.Integer, primary_key=True)
    role_id = db.Column(db.Integer, db.ForeignKey("roles.id"), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    action_type = db.Column(db.String(40), nullable=False, default="text")
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    progress_entries = db.relationship(
        "StudentTaskProgress", backref="task", lazy=True, cascade="all, delete-orphan"
    )


class StudentTaskProgress(db.Model):
    __tablename__ = "student_task_progress"

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey("tasks.id"), nullable=False)
    role_id = db.Column(db.Integer, db.ForeignKey("roles.id"), nullable=False)
    answer_text = db.Column(db.Text, nullable=True)
    is_completed = db.Column(db.Boolean, default=False, nullable=False)
    completed_at = db.Column(db.DateTime, nullable=True)


class LabSample(db.Model):
    __tablename__ = "lab_samples"

    id = db.Column(db.Integer, primary_key=True)
    role_id = db.Column(db.Integer, db.ForeignKey("roles.id"), nullable=False)
    sample_type = db.Column(db.String(20), nullable=False)
    ph_value = db.Column(db.Float, nullable=True)
    so2_ppm = db.Column(db.Float, nullable=True)
    nox_ppm = db.Column(db.Float, nullable=True)
    co2_ppm = db.Column(db.Float, nullable=True)
    temp_celsius = db.Column(db.Float, nullable=True)
    od_value = db.Column(db.Float, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    saved_to_dossier = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)


class SimulationResult(db.Model):
    __tablename__ = "simulation_results"

    id = db.Column(db.Integer, primary_key=True)
    role_id = db.Column(db.Integer, db.ForeignKey("roles.id"), nullable=False)
    energy_choice = db.Column(db.String(30), nullable=False)
    has_filters = db.Column(db.Boolean, default=False, nullable=False)
    has_relocation_plan = db.Column(db.Boolean, default=False, nullable=False)
    has_fish_ladder = db.Column(db.Boolean, default=False, nullable=False)
    fuel_type = db.Column(db.String(20), nullable=True)
    dam_height = db.Column(db.Float, nullable=True)
    env_score = db.Column(db.Float, nullable=False)
    social_score = db.Column(db.Float, nullable=False)
    economic_score = db.Column(db.Float, nullable=False)
    energy_score = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)


class SimulationVariable(db.Model):
    __tablename__ = "simulation_variables"

    id = db.Column(db.Integer, primary_key=True)
    var_key = db.Column(db.String(80), unique=True, nullable=False)
    value = db.Column(db.Float, nullable=False)
    description = db.Column(db.Text, nullable=True)


class ReportDraft(db.Model):
    __tablename__ = "report_drafts"

    id = db.Column(db.Integer, primary_key=True)
    role_id = db.Column(db.Integer, db.ForeignKey("roles.id"), nullable=False, unique=True)
    guiding_answers = db.Column(db.Text, nullable=True)
    jury_question = db.Column(db.Text, nullable=True)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)
