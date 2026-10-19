"""Authenticated Gemini chat endpoints for RPG interviews and the role-based tutor."""
from flask import Blueprint, current_app, jsonify, render_template, request
from flask_login import current_user
from sqlalchemy.exc import SQLAlchemyError

from extensions import db
from helpers.gemini import GeminiConfigurationError, GeminiUnavailableError, generate_reply
from helpers.personas import NPC_PERSONAS, TUTOR_GLOBAL_INSTRUCTION, tutor_instruction_for
from models import InterviewLog, SavedQuote
from utils import STUDENT_ROLES, role_required

chat_bp = Blueprint("chat", __name__)
MAX_MESSAGE_LENGTH = 1500
MAX_HISTORY_MESSAGES = 12
MAX_QUOTE_LENGTH = 6000
INTERVIEW_ROLE_LABELS = {
    "termobr": "TermoBR",
    "hydrosul": "HydroSul",
    "comunidade": "Comunidade de Ivaí dos Campos",
    "cientistas": "Cientistas Ambientais",
}


def _request_message():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return None, "Envie uma mensagem válida."
    message = payload.get("message")
    if not isinstance(message, str) or not message.strip():
        return None, "Escreva uma mensagem antes de enviar."
    message = message.strip()
    if len(message) > MAX_MESSAGE_LENGTH:
        return None, f"A mensagem deve ter no máximo {MAX_MESSAGE_LENGTH} caracteres."
    return message, None


def _request_history(payload):
    raw_history = payload.get("history", [])
    if not isinstance(raw_history, list):
        return []
    history = []
    for item in raw_history[-MAX_HISTORY_MESSAGES:]:
        if not isinstance(item, dict):
            continue
        role, text = item.get("role"), item.get("text")
        if role in ("user", "model") and isinstance(text, str) and text.strip():
            history.append({"role": role, "text": text.strip()[:MAX_MESSAGE_LENGTH]})
    return history


def _gemini_error_response(error):
    current_app.logger.warning("Gemini chat unavailable: %s", error)
    if isinstance(error, GeminiConfigurationError):
        return jsonify(
            error="A IA não está configurada no servidor. Peça ao responsável para definir GEMINI_API_KEY."
        ), 503
    return jsonify(error="A IA está indisponível no momento."), 503


@chat_bp.route("/student/interview")
@role_required(*STUDENT_ROLES)
def interview_page():
    npcs = [
        {"id": npc_id, "name": persona["name"], "role": persona["role"], "seed": persona["seed"]}
        for npc_id, persona in NPC_PERSONAS.items()
    ]
    return render_template("student/interview.html", npcs=npcs)


@chat_bp.route("/api/chat/interview/history/<npc_id>")
@role_required(*STUDENT_ROLES)
def interview_history(npc_id):
    if npc_id not in NPC_PERSONAS:
        return jsonify(error="Personagem não encontrado."), 404
    entries = (
        InterviewLog.query.filter_by(user_session_id=current_user.id, npc_id=npc_id)
        .order_by(InterviewLog.created_at.desc(), InterviewLog.id.desc())
        .limit(30)
        .all()
    )
    entries.reverse()
    return jsonify(
        messages=[
            message
            for entry in entries
            for message in (
                {"role": "user", "text": entry.user_message},
                {"role": "model", "text": entry.assistant_message},
            )
        ]
    )


@chat_bp.route("/api/chat/interview", methods=["POST"])
@role_required(*STUDENT_ROLES)
def interview_chat():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error="Envie uma mensagem válida."), 400
    npc_id = payload.get("npc")
    if not isinstance(npc_id, str) or npc_id not in NPC_PERSONAS:
        return jsonify(error="Escolha um personagem válido."), 400
    message, error = _request_message()
    if error:
        return jsonify(error=error), 400

    previous_entries = (
        InterviewLog.query.filter_by(user_session_id=current_user.id, npc_id=npc_id)
        .order_by(InterviewLog.created_at.desc(), InterviewLog.id.desc())
        .limit(MAX_HISTORY_MESSAGES // 2)
        .all()
    )
    history = []
    for entry in reversed(previous_entries):
        history.extend(
            [
                {"role": "user", "text": entry.user_message},
                {"role": "model", "text": entry.assistant_message},
            ]
        )

    user_role = INTERVIEW_ROLE_LABELS[current_user.role_name]
    system_instruction = (
        f"{NPC_PERSONAS[npc_id]['system_instruction']}\n\n"
        "INSTRUÇÃO OBRIGATÓRIA SOBRE QUEM ESTÁ FALANDO: "
        f"A pessoa conversando com você representa o grupo '{user_role}' "
        f"(identificador: '{current_user.role_name}') no Dilema de Ivaí dos Campos. "
        "Reconheça esse papel imediatamente e adapte sua reação, formalidade e "
        "proximidade ou hostilidade conforme as orientações da sua persona. "
        "Trate essa pessoa como um ator real do cenário: nunca a chame de estudante, "
        "aluno ou representante de trabalho escolar, e nunca mencione trabalho de escola.\n\n"
        "VOCÊ DEVE RESPONDER ESTRITAMENTE NESTE FORMATO JSON:\n"
        "{\n"
        '  "resposta": "Texto da sua fala como o personagem.",\n'
        '  "humor": "[Emoji] Estado de humor",\n'
        '  "sugestoes": ["Opção 1 de pergunta curta que o aluno poderia te fazer agora", "Opção 2 de pergunta"]\n'
        "}"
    )

    try:
        answer = generate_reply(
            system_instruction,
            message,
            history,
            response_mime_type="application/json",
        )
    except GeminiUnavailableError as error:
        return _gemini_error_response(error)
    except Exception:
        current_app.logger.exception("Gemini interview generation failed for NPC %s", npc_id)
        return jsonify(error="A IA está indisponível no momento."), 503

    db.session.add(
        InterviewLog(
            user_session_id=current_user.id,
            npc_id=npc_id,
            user_message=message,
            assistant_message=answer,
        )
    )
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Failed to save interview chat log.")
        return jsonify(error="Não foi possível salvar a entrevista. Tente novamente."), 503
    return jsonify(reply=answer)


@chat_bp.route("/api/dossier/save_quote", methods=["POST"])
@role_required(*STUDENT_ROLES)
def save_quote():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error="Envie um depoimento válido."), 400

    npc_id = payload.get("npc")
    quote_text = payload.get("quote_text")
    if not isinstance(npc_id, str) or npc_id not in NPC_PERSONAS:
        return jsonify(error="Escolha um personagem válido."), 400
    if not isinstance(quote_text, str) or not quote_text.strip():
        return jsonify(error="O depoimento não pode ficar vazio."), 400
    quote_text = quote_text.strip()
    if len(quote_text) > MAX_QUOTE_LENGTH:
        return jsonify(error=f"O depoimento deve ter no máximo {MAX_QUOTE_LENGTH} caracteres."), 400

    quote = SavedQuote(
        role_id=current_user.role_id,
        character_name=NPC_PERSONAS[npc_id]["name"],
        quote_text=quote_text,
    )
    db.session.add(quote)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Failed to save interview quote to dossier.")
        return jsonify(error="Não foi possível salvar o depoimento. Tente novamente."), 503
    return jsonify(id=quote.id, status="saved"), 201


@chat_bp.route("/api/chat/tutor", methods=["POST"])
@role_required(*STUDENT_ROLES)
def tutor_chat():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error="Envie uma mensagem válida."), 400
    message, error = _request_message()
    if error:
        return jsonify(error=error), 400

    role_instruction = tutor_instruction_for(current_user.role_name)
    if not role_instruction:
        return jsonify(error="O tutor não está disponível para este perfil."), 403
    instruction = f"{TUTOR_GLOBAL_INSTRUCTION}\n\n{role_instruction}"
    try:
        answer = generate_reply(instruction, message, _request_history(payload))
    except GeminiUnavailableError as error:
        return _gemini_error_response(error)
    except Exception:
        current_app.logger.exception("Gemini tutor generation failed for role %s", current_user.role_name)
        return jsonify(error="A IA está indisponível no momento."), 503
    return jsonify(reply=answer)
