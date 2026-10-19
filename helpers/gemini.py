"""Small, testable wrapper around the Google GenAI text generation client."""
from flask import current_app


class GeminiUnavailableError(Exception):
    """Raised when Gemini is not configured or cannot return a usable answer."""


class GeminiConfigurationError(GeminiUnavailableError):
    """Raised when the server has no Gemini API key configured."""


def generate_reply(system_instruction, user_message, history=None, response_mime_type=None):
    import os

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise GeminiConfigurationError("GEMINI_API_KEY is not configured.")

    from google import genai
    from google.genai.errors import ServerError
    from google.genai import types

    contents = []
    for entry in history or ():
        role = "user" if entry["role"] == "user" else "model"
        contents.append(
            types.Content(role=role, parts=[types.Part.from_text(text=entry["text"])])
        )
    contents.append(
        types.Content(role="user", parts=[types.Part.from_text(text=user_message)])
    )

    client = genai.Client(api_key=api_key)
    generation_options = {
        "system_instruction": system_instruction,
        "temperature": 0.7,
        "max_output_tokens": 600,
    }
    if response_mime_type:
        generation_options["response_mime_type"] = response_mime_type
    generation_config = types.GenerateContentConfig(**generation_options)
    model = current_app.config["GEMINI_MODEL"]
    try:
        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=generation_config,
        )
    except ServerError as error:
        fallback_model = current_app.config["GEMINI_FALLBACK_MODEL"]
        if error.code != 503 or fallback_model == model:
            raise
        current_app.logger.warning(
            "Gemini model %s returned 503; retrying with fallback model %s.",
            model,
            fallback_model,
        )
        response = client.models.generate_content(
            model=fallback_model,
            contents=contents,
            config=generation_config,
        )

    answer = (response.text or "").strip()
    if not answer:
        raise GeminiUnavailableError("Gemini returned an empty response.")
    return answer
