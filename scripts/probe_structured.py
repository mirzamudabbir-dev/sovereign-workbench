"""Probe which structured-output request shape this Ollama build actually accepts.

vLLM's guided_json extra_body param is not guaranteed to work against Ollama's
OpenAI-compatible endpoint. Do not guess which of the three candidate shapes it honours —
run this once per machine and read off the recommended `config.yaml` value.

See docs/PATCH_02_LOCAL_MODELS.md.
"""
from __future__ import annotations

import asyncio
import sys

import openai
from pydantic import BaseModel, ValidationError

from core.config import SETTINGS

_MODES = ["guided_json", "response_format", "ollama_format"]

_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "confidence": {"type": "number"},
    },
    "required": ["answer", "confidence"],
}


class _TwoField(BaseModel):
    answer: str
    confidence: float


def _kwargs_for(mode: str) -> dict:
    """Mirrors core/serving.py::_structured_kwargs exactly — this script is how that
    function's three branches get validated, not a second implementation of them."""
    if mode == "guided_json":
        return {"extra_body": {"guided_json": _SCHEMA}}
    if mode == "response_format":
        return {
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "out", "schema": _SCHEMA, "strict": True},
            }
        }
    return {"extra_body": {"format": _SCHEMA}}  # ollama_format


async def _probe_one(client: openai.AsyncOpenAI, model: str, mode: str) -> tuple[bool, str]:
    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Reply with a JSON object with an 'answer' string field set to "
                        "'yes' and a 'confidence' number field set to 0.9."
                    ),
                }
            ],
            max_tokens=200,
            temperature=0.0,
            **_kwargs_for(mode),
        )
    except Exception as exc:  # server rejected the request shape outright
        return False, f"request error: {exc!r}"

    raw = response.choices[0].message.content
    if raw is None:
        return False, "empty content"
    try:
        _TwoField.model_validate_json(raw)
    except ValidationError as exc:
        return False, f"invalid json for schema: {raw!r} ({exc.errors()[0]['msg']})"
    except ValueError as exc:  # not valid JSON at all
        return False, f"not valid json: {raw!r} ({exc})"
    return True, "ok"


async def main() -> int:
    model = "gemma4:e2b"
    base_url = "http://127.0.0.1:11434/v1"
    client = openai.AsyncOpenAI(base_url=base_url, api_key="EMPTY", timeout=60.0)

    print(f"Probing structured-output modes against {base_url} (model={model})")
    print("-" * 70)
    results: dict[str, tuple[bool, str]] = {}
    for mode in _MODES:
        ok, detail = await _probe_one(client, model, mode)
        results[mode] = (ok, detail)
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {mode:<16} {detail}")
    print("-" * 70)

    passing = [m for m, (ok, _) in results.items() if ok]
    if not passing:
        print(
            "No structured-output mode succeeded. Check the Ollama server is running "
            "and the model is pulled (`ollama pull gemma4:e2b`)."
        )
        return 1

    recommended = passing[0]
    print(f"Recommended config.yaml value: structured_output_mode: {recommended}")
    if recommended != SETTINGS.structured_output_mode:
        print(
            f"NOTE: config.yaml currently has structured_output_mode: "
            f"{SETTINGS.structured_output_mode!r} — update it to {recommended!r}."
        )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
