import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent.parent
load_dotenv(ROOT_DIR / ".env.local", override=True)
load_dotenv(BASE_DIR / ".env", override=False)

DEFAULT_GEMINI_MODEL = "gemini-3.8-flash"
DEFAULT_GEMINI_FALLBACK_MODEL = "gemini-3.5-flash-lite"
RETIRED_GEMINI_MODELS = {"gemini-2.5-flash"}
RETIRED_GEMINI_FALLBACK_MODELS = {"gemini-2.5-flash-lite"}


def resolve_gemini_model(model):
    model = (model or "").strip()
    if not model or model in RETIRED_GEMINI_MODELS:
        return DEFAULT_GEMINI_MODEL
    return model


def resolve_gemini_fallback_model(model):
    model = (model or "").strip()
    if not model or model in RETIRED_GEMINI_FALLBACK_MODELS:
        return DEFAULT_GEMINI_FALLBACK_MODEL
    return model


def normalize_database_url(url: str) -> str:
    """Aceita URIs do Neon (postgres://) e forca o dialeto do SQLAlchemy."""
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg2://", 1)
    if url.startswith("postgresql://") and "+psycopg2" not in url:
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    if url.startswith("sqlite") and "carbopolis.db" in url and "://" in url:
        # forca caminho absoluto para nao cair em instance/
        return f"sqlite:///{BASE_DIR / 'carbopolis.db'}"
    return url


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "carbopolis-ivai-dev-key")
    GEMINI_MODEL = resolve_gemini_model(os.getenv("GEMINI_MODEL"))
    GEMINI_FALLBACK_MODEL = resolve_gemini_fallback_model(
        os.getenv("GEMINI_FALLBACK_MODEL", DEFAULT_GEMINI_FALLBACK_MODEL)
    )
    SQLALCHEMY_DATABASE_URI = normalize_database_url(
        os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'carbopolis.db'}")
    )
    # Skill neon-postgres: app usa a poolada (DATABASE_URL); seed usa a direta.
    SQLALCHEMY_DATABASE_URI_UNPOOLED = normalize_database_url(
        os.getenv("DATABASE_URL_UNPOOLED", os.getenv("DATABASE_URL", "sqlite"))
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = 9 * 1024 * 1024
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
    }
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_HTTPONLY = True
