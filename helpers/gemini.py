"""Small, testable wrapper around AI text generation (Gemini, with Groq as last resort)."""
import json
import os
import time
import urllib.request

from flask import current_app

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
# A model that just failed (quota, overload, timeout) is tried last for this long,
# so every request does not wait on it again before reaching a working one.
FAILED_MODEL_COOLDOWN_SECONDS = 300
# shortcut: in-memory and per worker process; fine for one server, share via Redis if scaled out.
_failed_until = {}


class GeminiUnavailableError(Exception):
    """Raised when no AI provider is configured or can return a usable answer."""


class GeminiConfigurationError(GeminiUnavailableError):
    """Raised when the server has no AI API key configured."""


def _groq_reply(api_key, model, system_instruction, user_message, history, json_mode):
    messages = [{"role": "system", "content": system_instruction}]
    for entry in history or ():
        role = "user" if entry["role"] == "user" else "assistant"
        messages.append({"role": role, "content": entry["text"]})
    messages.append({"role": "user", "content": user_message})
    # gpt-oss spends hidden reasoning tokens from max_tokens; 600 cut JSON answers short (400 json_validate_failed).
    body = {"model": model, "messages": messages, "temperature": 0.7, "max_tokens": 2000}
    if model.startswith("openai/gpt-oss"):
        body["reasoning_effort"] = "low"
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    request = urllib.request.Request(
        GROQ_URL,
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            # Groq's CDN rejects the default Python-urllib user agent.
            "User-Agent": "Mozilla/5.0",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)["choices"][0]["message"]["content"]


def generate_reply(system_instruction, user_message, history=None, response_mime_type=None):
    gemini_key = os.environ.get("GEMINI_API_KEY")
    groq_key = os.environ.get("GROQ_API_KEY")
    if not gemini_key and not groq_key:
        raise GeminiConfigurationError("Neither GEMINI_API_KEY nor GROQ_API_KEY is configured.")

    # Each attempt is (model name, callable returning text); the first usable answer wins.
    attempts = []
    if gemini_key:
        from google import genai
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

        # Fail fast: no SDK-internal retries (our chain is the retry) and a hard timeout,
        # otherwise an overloaded model holds the request for 30-50s before the fallback runs.
        client = genai.Client(
            api_key=gemini_key,
            http_options=types.HttpOptions(
                timeout=15000,
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )
        generation_options = {
            "system_instruction": system_instruction,
            "temperature": 0.7,
            "max_output_tokens": 600,
        }
        if response_mime_type:
            generation_options["response_mime_type"] = response_mime_type
        generation_config = types.GenerateContentConfig(**generation_options)
        models = dict.fromkeys(
            [current_app.config["GEMINI_MODEL"], current_app.config["GEMINI_FALLBACK_MODEL"]]
        )
        for model in models:
            attempts.append((
                model,
                lambda model=model: client.models.generate_content(
                    model=model, contents=contents, config=generation_config
                ).text,
            ))
    if groq_key:
        groq_model = current_app.config["GROQ_MODEL"]
        # Groq goes first: ~1s answers versus 10-30s on Gemini's free tier.
        attempts.insert(0, (
            f"groq/{groq_model}",
            lambda: _groq_reply(
                groq_key, groq_model, system_instruction, user_message, history,
                response_mime_type == "application/json",
            ),
        ))

    now = time.monotonic()
    # Stable sort: healthy models keep their priority order; cooling-down ones go last, never skipped.
    attempts.sort(key=lambda attempt: _failed_until.get(attempt[0], 0) > now)
    for name, call in attempts:
        try:
            answer = (call() or "").strip()
        except Exception as error:
            _failed_until[name] = time.monotonic() + FAILED_MODEL_COOLDOWN_SECONDS
            current_app.logger.warning("AI model %s failed (%s); trying the next one.", name, error)
            continue
        if answer:
            _failed_until.pop(name, None)
            return answer
        _failed_until[name] = time.monotonic() + FAILED_MODEL_COOLDOWN_SECONDS
        current_app.logger.warning("AI model %s returned an empty response.", name)
    raise GeminiUnavailableError("All configured AI models failed.")
