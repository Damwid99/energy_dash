import json
import os
import re
from typing import TypeVar

import litellm
from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)

API_BASE = os.getenv("OLLAMA_API_BASE", "http://localhost:11434")
MODEL = os.getenv("LLM_MODEL", "ollama_chat/gpt-oss:20b-cloud")
USE_RESPONSE_FORMAT = os.getenv("LLM_USE_RESPONSE_FORMAT", "1") == "1"


def _extract_json(text: str) -> str:
    """Wyciąga pierwszy blok {...}, gdy model dopisze komentarz lub ```json."""
    m = re.search(r"\{.*\}", text, re.S)
    return m.group(0) if m else text


def ask_structured(system: str, user: str, schema: type[T], max_retries: int = 1) -> T:
    schema_hint = json.dumps(schema.model_json_schema(), ensure_ascii=False)
    messages = [
        {
            "role": "system",
            "content": f"{system}\n\nOdpowiadaj WYŁĄCZNIE poprawnym JSON-em zgodnym ze schematem:\n{schema_hint}",
        },
        {"role": "user", "content": user},
    ]
    extra = {"response_format": schema} if USE_RESPONSE_FORMAT else {}

    last_error = None
    for _ in range(max_retries + 1):
        resp = litellm.completion(
            model=MODEL,
            api_base=API_BASE,
            messages=messages,
            temperature=0.2,
            timeout=180,
            **extra,
        )
        content = resp.choices[0].message.content or ""
        try:
            return schema.model_validate_json(_extract_json(content))
        except ValidationError as e:
            last_error = e
            messages += [
                {"role": "assistant", "content": content},
                {
                    "role": "user",
                    "content": f"Odpowiedź nie przeszła walidacji:\n{e}\nPopraw ją i zwróć sam JSON.",
                },
            ]
    raise RuntimeError(f"LLM nie zwrócił poprawnego JSON-a: {last_error}")
