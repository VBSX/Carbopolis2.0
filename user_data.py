"""Operations for clearing group activity while preserving shared configuration."""

from extensions import db
from models import (
    InterviewLog,
    LabSample,
    ReportDraft,
    SavedQuote,
    SimulationResult,
    StudentTaskProgress,
    UserSession,
)

RECORDS_TO_CLEAR = (
    ("Conversas de entrevistas", InterviewLog),
    ("Laudos e amostras", LabSample),
    ("Depoimentos salvos", SavedQuote),
    ("Resultados do simulador", SimulationResult),
    ("Rascunhos do dossiê", ReportDraft),
    ("Respostas às missões", StudentTaskProgress),
    ("Sessões e nomes dos integrantes", UserSession),
)


def get_user_data_counts():
    return [
        (label, model.query.count())
        for label, model in RECORDS_TO_CLEAR
    ]


def clear_user_data():
    counts = get_user_data_counts()
    for _label, model in RECORDS_TO_CLEAR:
        db.session.query(model).delete(synchronize_session=False)
    db.session.commit()
    return counts
