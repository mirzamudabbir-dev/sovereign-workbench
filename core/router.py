"""L2 — automatic model selection. Filter first, then preference.

Routing is two stages and the order matters:
  STAGE 1  capability_filter()   — deterministic, no LLM, eliminates the impossible
  STAGE 2  _arch_router_select() — Arch-Router-1.5B picks the best fit among survivors

A preference model alone will happily hand a scanned drawing to a text-only model, or a
20 000-token document to a model with an 8 192-token context window. Those are not
preferences, they are hard constraints — that is why stage 1 exists and must never be skipped.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

from pydantic import BaseModel, Field

from core.config import SETTINGS
from core.schemas import (
    LicenceClass,
    Modality,
    ModelManifest,
    RouteDecision,
    TaskAffinity,
    TaskType,
    WorkbenchError,
)
from core.serving import REGISTRY, complete, complete_structured

logger = logging.getLogger(__name__)

ALLOWED_LICENCES = {LicenceClass.PERMISSIVE, LicenceClass.RESTRICTED}

INTERNAL_ONLY_AFFINITIES = {
    TaskAffinity.ROUTING, TaskAffinity.EMBEDDING, TaskAffinity.OCR_EXTRACTION,
}


def _is_internal_only(m: ModelManifest) -> bool:
    """True when EVERY affinity is internal. A VLM that also drafts is not internal."""
    return set(m.task_affinities) <= INTERNAL_ONLY_AFFINITIES


class RouteRequest(BaseModel):
    step_id: str
    task_type: TaskType
    instruction: str
    required_modalities: list[Modality] = [Modality.TEXT]
    estimated_tokens: int = 1024
    needs_structured_output: bool = False
    excluded_affinity: TaskAffinity = TaskAffinity.ROUTING


# ─────────────────────────── Stage 1 — capability filter ──────────────────────


def _modality_reason(m: ModelManifest, r: RouteRequest) -> str:
    missing = [mod.value for mod in r.required_modalities if mod not in m.modalities]
    return f"does not support required modality: {', '.join(missing)}"


def _context_reason(m: ModelManifest, r: RouteRequest) -> str:
    return (
        f"context window is {m.max_context} tokens, too small for this request's "
        f"estimated {r.estimated_tokens} tokens"
    )


def _grammar_reason(m: ModelManifest, r: RouteRequest) -> str:
    return "does not support constrained decoding, which this request requires for structured output"


def _licence_reason(m: ModelManifest, r: RouteRequest) -> str:
    return f"licence class '{m.licence_class.value.replace('_', ' ')}' is not permitted by org policy"


def _affinity_reason(m: ModelManifest, r: RouteRequest) -> str:
    affinities = ", ".join(a.value.replace("_", " ") for a in m.task_affinities)
    return f"reserved for internal use ({affinities} only) and not available for general routing"


# name, predicate(manifest, request) -> bool (True = passes), reason(manifest, request) -> str
CAPABILITY_FILTERS = [
    ("modality", lambda m, r: set(r.required_modalities) <= set(m.modalities), _modality_reason),
    ("context", lambda m, r: m.max_context >= r.estimated_tokens, _context_reason),
    ("grammar", lambda m, r: (not r.needs_structured_output) or m.supports_grammar, _grammar_reason),
    ("licence", lambda m, r: m.licence_class in ALLOWED_LICENCES, _licence_reason),
    ("affinity", lambda m, r: not _is_internal_only(m), _affinity_reason),
]


def capability_filter(req: RouteRequest) -> tuple[list[ModelManifest], dict[str, str]]:
    """Returns (survivors, rejected). Pure function, no I/O, fully unit-testable."""
    survivors: list[ModelManifest] = []
    rejected: dict[str, str] = {}
    for manifest in REGISTRY.all():
        reason = None
        for _name, predicate, reason_fn in CAPABILITY_FILTERS:
            if not predicate(manifest, req):
                reason = reason_fn(manifest, req)
                break
        if reason is None:
            survivors.append(manifest)
        else:
            rejected[manifest.id] = reason
    return survivors, rejected


# ─────────────────────────── Stage 2 — Arch-Router preference ─────────────────


class _ArchChoice(BaseModel):
    model_id: str
    reason: str = Field(max_length=200)


async def _arch_router_select(req: RouteRequest, candidates: list[ModelManifest]) -> tuple[str, str]:
    """Build the route-policy prompt from candidate manifests, call Arch-Router with
    guided_json against _ArchChoice, return (model_id, reason)."""
    model_lines = "\n".join(f"- {m.id}: {m.description.strip()}" for m in candidates)
    prompt = (
        "You are a model router. Choose exactly one model for the request below.\n\n"
        "AVAILABLE MODELS\n"
        f"{model_lines}\n\n"
        f"REQUEST TYPE: {req.task_type.value}\n"
        f"REQUEST: {req.instruction[:600]}\n\n"
        'Reply with JSON: {"model_id": "...", "reason": "<20 words on why>"}'
    )
    messages = [{"role": "user", "content": prompt}]

    try:
        choice = await complete_structured(SETTINGS.router_model_id, messages, _ArchChoice)
    except WorkbenchError as exc:
        logger.warning("router unavailable (%s); defaulting to first candidate", exc)
        return candidates[0].id, f"router unavailable ({type(exc).__name__}); defaulted to first candidate"

    candidate_ids = {m.id for m in candidates}
    if choice.model_id not in candidate_ids:
        logger.warning(
            "Arch-Router returned model_id %r not among candidates %s; defaulting to first candidate",
            choice.model_id,
            sorted(candidate_ids),
        )
        return candidates[0].id, "router returned invalid id; defaulted to first candidate"

    return choice.model_id, choice.reason


# ─────────────────────────── Public entry points ───────────────────────────────


async def route(req: RouteRequest) -> RouteDecision:
    """Full two-stage routing.

    - 0 survivors  -> raise WorkbenchError with the rejection table in the message.
    - 1 survivor   -> return it immediately, reason='only capable model', SKIP the LLM call.
    - 2+ survivors -> call Arch-Router.
    """
    start = time.monotonic()
    survivors, rejected = capability_filter(req)

    if not survivors:
        table = "; ".join(f"{model_id}: {reason}" for model_id, reason in rejected.items())
        raise WorkbenchError(
            f"no model survives the capability filter for step {req.step_id!r}: {table}"
        )

    candidates_considered = [m.id for m in survivors]

    if len(survivors) == 1:
        chosen_model = survivors[0].id
        reason = "only capable model"
    else:
        chosen_model, reason = await _arch_router_select(req, survivors)

    latency_ms = (time.monotonic() - start) * 1000
    return RouteDecision(
        step_id=req.step_id,
        required_modalities=req.required_modalities,
        estimated_tokens=req.estimated_tokens,
        needs_structured_output=req.needs_structured_output,
        candidates_considered=candidates_considered,
        rejected=rejected,
        chosen_model=chosen_model,
        reason=reason,
        latency_ms=latency_ms,
    )


async def route_and_complete(
    req: RouteRequest,
    messages: list[dict],
    *,
    schema_model: type[BaseModel] | None = None,
    images: list[Path] | None = None,
) -> tuple[str | BaseModel, RouteDecision]:
    """Convenience wrapper used by L4 for every LLM call. Routes, then dispatches to
    serving.complete() or serving.complete_structured(). Returns the result AND the
    decision so L4 can append it to the receipt."""
    decision = await route(req)
    if schema_model is not None:
        result = await complete_structured(decision.chosen_model, messages, schema_model, images=images)
    else:
        result = await complete(decision.chosen_model, messages, images=images)
    return result, decision
