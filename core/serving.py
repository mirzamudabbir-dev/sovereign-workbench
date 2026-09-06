"""L1 — model registry + unified inference client. No routing decisions here."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import mimetypes
import time
from pathlib import Path

import httpx
import openai
import yaml
from pydantic import BaseModel, ValidationError

from core.config import SETTINGS
from core.schemas import Modality, ModelManifest, WorkbenchError

logger = logging.getLogger(__name__)

_CONNECT_RETRIES = 2
_CONNECT_BACKOFF_S = 2.0
_CLIENT_TIMEOUT_S = 180.0


class ModelRegistry:
    """Loads every *.yaml in manifests_dir into ModelManifest. No model-specific code."""

    def __init__(self, manifests_dir: Path):
        self._manifests_dir = Path(manifests_dir)
        self._manifests: dict[str, ModelManifest] = {}
        self._paths: dict[str, Path] = {}
        self.reload()

    def reload(self) -> None:
        """Re-read every *.yaml in manifests_dir. Called at startup and by /admin/reload."""
        manifests: dict[str, ModelManifest] = {}
        paths: dict[str, Path] = {}
        for yaml_path in sorted(self._manifests_dir.glob("*.yaml")):
            raw = yaml.safe_load(yaml_path.read_text())
            manifest = ModelManifest(**raw)
            manifests[manifest.id] = manifest
            paths[manifest.id] = yaml_path
        self._manifests = manifests
        self._paths = paths
        if not manifests:
            logger.error("no manifests found in %s — every route will fail", self._manifests_dir)
        logger.info("registry reloaded: %d manifests from %s", len(manifests), self._manifests_dir)

    def all(self) -> list[ModelManifest]:
        """Enabled manifests only."""
        return [m for m in self._manifests.values() if m.enabled]

    def get(self, model_id: str, *, include_disabled: bool = False) -> ModelManifest:
        """Raise WorkbenchError if unknown, or disabled and include_disabled is False."""
        m = self._manifests.get(model_id)
        if m is None:
            raise WorkbenchError(f"unknown model_id: {model_id!r}")
        if not m.enabled and not include_disabled:
            raise WorkbenchError(f"model {model_id!r} is disabled in its manifest")
        return m

    def manifest_hashes(self) -> dict[str, str]:
        """model_id -> sha256 of the manifest file. Consumed by L8 receipts."""
        return {
            model_id: hashlib.sha256(path.read_bytes()).hexdigest()
            for model_id, path in self._paths.items()
        }


REGISTRY = ModelRegistry(SETTINGS.paths.manifests)   # module singleton

_clients: dict[str, openai.AsyncOpenAI] = {}


def _get_client(manifest: ModelManifest) -> openai.AsyncOpenAI:
    client = _clients.get(manifest.id)
    if client is None:
        client = openai.AsyncOpenAI(
            base_url=manifest.base_url, api_key="EMPTY", timeout=_CLIENT_TIMEOUT_S
        )
        _clients[manifest.id] = client
    return client


async def _call_with_retry(func, **kwargs):
    attempt = 0
    while True:
        try:
            return await func(**kwargs)
        except (httpx.ConnectError, openai.APIConnectionError) as exc:
            attempt += 1
            if attempt > _CONNECT_RETRIES:
                raise WorkbenchError(
                    f"connection to model server failed after {attempt} attempts: {exc}"
                ) from exc
            await asyncio.sleep(_CONNECT_BACKOFF_S)


def _image_to_data_url(path: Path) -> str:
    mime = mimetypes.guess_type(str(path))[0] or "image/png"
    data = base64.b64encode(Path(path).read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}"


def _inject_images(messages: list[dict], images: list[Path] | None) -> list[dict]:
    if not images:
        return messages
    messages = [dict(m) for m in messages]
    last = dict(messages[-1])
    content = last.get("content", "")
    parts = [{"type": "text", "text": content}] if isinstance(content, str) else list(content)
    for image_path in images:
        parts.append({"type": "image_url", "image_url": {"url": _image_to_data_url(image_path)}})
    last["content"] = parts
    messages[-1] = last
    return messages


def _content_to_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part.get("text", "") for part in content if isinstance(part, dict) and part.get("type") == "text"
        )
    return str(content)


def _structured_kwargs(schema: dict) -> dict:
    """Structured-output request shape varies by serving backend. One function, three
    branches — not an inference-engine abstraction layer. See PATCH_02_LOCAL_MODELS.md."""
    mode = SETTINGS.structured_output_mode
    if mode == "guided_json":
        return {"extra_body": {"guided_json": schema}}
    if mode == "response_format":
        return {
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "out", "schema": schema, "strict": True},
            }
        }
    return {"extra_body": {"format": schema}}          # ollama_format


def estimate_tokens(messages: list[dict], images: list[Path] | None = None) -> int:
    """len(text)//3.5 + 800 per image. Deliberately crude — L2 only needs it to filter
    models by max_context, not to bill anyone."""
    total_chars = sum(len(_content_to_text(m.get("content", ""))) for m in messages)
    return int(total_chars / 3.5) + 800 * len(images or [])


async def health() -> dict[str, bool]:
    """GET {base_url}/models for every manifest. Verify served_model_name is present.
    Used by preflight and the UI status bar."""

    async def check(manifest: ModelManifest) -> tuple[str, bool]:
        client = _get_client(manifest)
        try:
            page = await client.models.list()
            names = {m.id for m in page.data}
            return manifest.id, manifest.served_model_name in names
        except Exception as exc:
            logger.info("health check failed for %s: %s", manifest.id, exc)
            return manifest.id, False

    results = await asyncio.gather(*(check(m) for m in REGISTRY.all()))
    return dict(results)


async def complete(
    model_id: str,
    messages: list[dict],
    *,
    max_tokens: int = 2048,
    temperature: float = 0.2,
    images: list[Path] | None = None,
) -> str:
    """Free-text completion. `images` are base64-inlined as image_url content parts.
    Raise WorkbenchError if the manifest lacks Modality.IMAGE but images were passed."""
    manifest = REGISTRY.get(model_id)
    if images and Modality.IMAGE not in manifest.modalities:
        raise WorkbenchError(f"model {model_id!r} does not support image input")

    msgs = _inject_images(messages, images)
    tokens_est = estimate_tokens(messages, images)
    client = _get_client(manifest)

    start = time.monotonic()
    try:
        response = await _call_with_retry(
            client.chat.completions.create,
            model=manifest.served_model_name,
            messages=msgs,
            max_tokens=max_tokens,
            temperature=temperature,
        )
    except Exception:
        latency_ms = (time.monotonic() - start) * 1000
        logger.info("model=%s tokens_est=%d latency_ms=%.1f ok=False", model_id, tokens_est, latency_ms)
        raise
    latency_ms = (time.monotonic() - start) * 1000
    logger.info("model=%s tokens_est=%d latency_ms=%.1f ok=True", model_id, tokens_est, latency_ms)
    content = response.choices[0].message.content
    if content is None:
        raise WorkbenchError(f"model {model_id!r} returned empty content")
    return content


async def complete_structured(
    model_id: str,
    messages: list[dict],
    schema_model: type[BaseModel],
    *,
    max_tokens: int = 4096,
    images: list[Path] | None = None,
) -> BaseModel:
    """Grammar-constrained generation via vLLM's native guided_json (XGrammar backend).

    extra_body={"guided_json": schema_model.model_json_schema()}

    Then schema_model.model_validate_json(...). On ValidationError, retry ONCE with the
    validation error appended as a user message, then raise WorkbenchError.
    Raise immediately if manifest.supports_grammar is False.
    """
    manifest = REGISTRY.get(model_id)
    if not manifest.supports_grammar:
        raise WorkbenchError(f"model {model_id!r} does not support grammar-constrained output")
    if images and Modality.IMAGE not in manifest.modalities:
        raise WorkbenchError(f"model {model_id!r} does not support image input")

    msgs = _inject_images(messages, images)
    tokens_est = estimate_tokens(messages, images)
    client = _get_client(manifest)
    schema = schema_model.model_json_schema()

    async def call(current_messages: list[dict]):
        return await _call_with_retry(
            client.chat.completions.create,
            model=manifest.served_model_name,
            messages=current_messages,
            max_tokens=max_tokens,
            temperature=0.0,
            **_structured_kwargs(schema),
        )

    start = time.monotonic()
    try:
        response = await call(msgs)
        raw_text = response.choices[0].message.content
        if raw_text is None:
            raise WorkbenchError(f"model {model_id!r} returned empty content")
        try:
            result = schema_model.model_validate_json(raw_text)
        except ValidationError as first_error:
            retry_messages = msgs + [
                {"role": "assistant", "content": raw_text},
                {
                    "role": "user",
                    "content": (
                        "Your previous output failed schema validation with this error: "
                        f"{first_error}. Produce corrected JSON that matches the schema exactly."
                    ),
                },
            ]
            response = await call(retry_messages)
            raw_text = response.choices[0].message.content
            if raw_text is None:
                raise WorkbenchError(f"model {model_id!r} returned empty content") from None
            try:
                result = schema_model.model_validate_json(raw_text)
            except ValidationError as second_error:
                raise WorkbenchError(
                    f"structured output for {model_id!r} failed validation twice: {second_error}"
                ) from second_error
    except Exception:
        latency_ms = (time.monotonic() - start) * 1000
        logger.info("model=%s tokens_est=%d latency_ms=%.1f ok=False", model_id, tokens_est, latency_ms)
        raise

    latency_ms = (time.monotonic() - start) * 1000
    logger.info("model=%s tokens_est=%d latency_ms=%.1f ok=True", model_id, tokens_est, latency_ms)
    return result
