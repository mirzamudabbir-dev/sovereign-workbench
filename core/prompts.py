"""L4 — every prompt in the system, as a named constant. No f-strings scattered through
graph.py: graph.py only ever appends already-formed *data* (evidence, observations, task
instructions) around these static instruction blocks.
"""
from __future__ import annotations

from core.schemas import TaskType

CLASSIFY_PROMPT = """You are the Sovereign Workbench task agent — an automated executor for a \
single industrial engineering task, running entirely on the organisation's own premises \
against its own models, tools and documents. Nothing you do ever leaves this machine.

Rules you always follow, whatever kind of task this is:
- Never invent a fact, a measurement, a file path, an identifier, or a result you have not \
actually produced or observed.
- If the task involves the organisation's documents, ground every factual claim in a cited \
EvidenceSpan id from the EVIDENCE list — never a span id you have not seen.
- If the task is to write code, write a correct, complete, working solution — no unrelated \
imports, no filler, nothing left as a placeholder.
- If the task is a calculation, show the arithmetic steps; never estimate a number you can \
compute exactly.
- You have no memory beyond this task and no persona beyond "careful engineer." Do not adopt one.
- When you are unsure or lack what you need to be correct, say so plainly rather than guessing.
"""

_PLAN_SHAPE_INSTRUCTIONS = """Produce a plan: a JSON object {"steps": [...]}, at most 8 steps, \
at least 1 step. Each step is an object with:
  - "step_id": any short string (it will be renumbered)
  - "kind": one of "retrieve", "ingest", "execute_code", "llm_call", "render"
  - "description": one sentence describing what this step does
  - "payload": a JSON object of parameters this step needs (may be empty {})

Adapt the plan to what THIS task actually needs — skip steps the worked example below shows \
that aren't relevant, and add repeats of a kind if genuinely needed. The example is a shape to \
learn from, not a fixed pipeline to copy verbatim."""

PLAN_PROMPT_BY_TASKTYPE: dict[TaskType, str] = {
    TaskType.DOC_TO_DELIVERABLE: f"""{_PLAN_SHAPE_INSTRUCTIONS}

Worked example, for a task like "produce an approval note from this inspection report":
{{"steps": [
  {{"step_id": "s1", "kind": "ingest", "description": "Ingest the uploaded document", "payload": {{"path": "/abs/path/to/file.pdf"}}}},
  {{"step_id": "s2", "kind": "retrieve", "description": "Retrieve relevant SOP context", "payload": {{"query": "minimum thickness SOP"}}}},
  {{"step_id": "s3", "kind": "llm_call", "description": "Extract findings from the evidence", "payload": {{}}}},
  {{"step_id": "s4", "kind": "execute_code", "description": "Compute the average of the measured readings", "payload": {{"expression": "(a + b) / 2", "variables": {{"a": 12.4, "b": 12.3}}, "units": {{"a": "mm", "b": "mm"}}}}}},
  {{"step_id": "s5", "kind": "render", "description": "Render the approval note", "payload": {{"output_format": "docx"}}}}
]}}
If the task doesn't need a new document ingested (evidence already exists in the KB), skip the \
ingest step. If there is nothing to compute, skip the execute_code step.""",
    TaskType.CODING: f"""{_PLAN_SHAPE_INSTRUCTIONS}

Worked example, for a task like "write a function that does X":
{{"steps": [
  {{"step_id": "s1", "kind": "llm_call", "description": "Write the solution code", "payload": {{}}}},
  {{"step_id": "s2", "kind": "llm_call", "description": "Write pytest tests for the solution", "payload": {{}}}},
  {{"step_id": "s3", "kind": "execute_code", "description": "Run the tests in the sandbox", "payload": {{}}}}
]}}""",
    TaskType.DOC_QA: f"""{_PLAN_SHAPE_INSTRUCTIONS}

Worked example, for a task like "what does the SOP say about X":
{{"steps": [
  {{"step_id": "s1", "kind": "retrieve", "description": "Search the knowledge base for relevant spans", "payload": {{"query": "X"}}}},
  {{"step_id": "s2", "kind": "llm_call", "description": "Answer the question, citing span ids", "payload": {{}}}}
]}}""",
    TaskType.CALCULATION: f"""{_PLAN_SHAPE_INSTRUCTIONS}

Worked example, for a task like "compute X given these numbers":
{{"steps": [
  {{"step_id": "s1", "kind": "llm_call", "description": "Determine the expression, variables and units from the instruction", "payload": {{}}}},
  {{"step_id": "s2", "kind": "execute_code", "description": "Independently verify the calculation", "payload": {{}}}}
]}}""",
}

EXTRACT_FINDINGS_PROMPT = """From the EVIDENCE spans above, extract findings relevant to this \
task. Reply with JSON: {"findings": [{"title": "...", "detail": "...", \
"severity": "info"|"observation"|"concern"|"critical", "evidence_refs": ["<span_id>", ...]}, ...]}.
Every finding's evidence_refs MUST name real span ids from the EVIDENCE list above — never a \
span id you have not seen. Produce at least one finding. If the evidence is thin, say so in a \
single "observation"-severity finding rather than inventing detail."""

BUILD_RENDER_PLAN_PROMPT = """Build a RenderPlan for this deliverable as JSON, matching this \
shape: {"template_id": "...", "output_format": "docx"|"pptx"|"xlsx", "title": "...", \
"fields": {"<name>": {"value": ..., "unit": "...", "evidence_ref": "<span_id>", \
"computed_from": [], "calculation": null}, ...}, "findings": [...], "recommendation": "..."}.

Every value you assert must include an `evidence_ref` naming a span id from the EVIDENCE
list. If no span supports a value, omit the field entirely. Never invent a span id.
Never estimate a number. If a value must be computed, set `computed_from` to the span ids of
its inputs and put the arithmetic in `calculation`.

`findings` must reuse the findings already extracted above, with the same evidence_refs."""

WRITE_CODE_PROMPT = """Write the Python solution described by this task. Reply with JSON: \
{"code": "<the full contents of a single Python module>"}. The module must define whatever \
function(s) or class(es) the task asks for, with clear names. Keep it short and plain: no type \
hints, no docstrings, no comments, no __main__ block, no example usage, no assert statements, \
and no tests of any kind — tests are written in a separate step. Stop as soon as the \
function/class definition(s) are complete."""

WRITE_TESTS_PROMPT = """Write pytest tests for the SOLUTION CODE shown above. Reply with JSON: \
{"tests": "<the full contents of a single test module>"}. The test module MUST import from \
`solution` (e.g. `from solution import add`) — that is the exact filename the solution is saved \
as. Write AT MOST 2 test functions or assert statements total, covering exactly what the task \
specifies — do not add extra cases, do not enumerate additional inputs, no docstrings, no \
comments. Stop as soon as those assertions are written."""

ANSWER_QUESTION_PROMPT = """Answer the task's question using ONLY the EVIDENCE spans above. \
Cite every fact you state with the span id it came from, written inline like [insp-2214#p7.b1]. \
If the evidence does not answer the question, say so plainly rather than guessing."""

DERIVE_CALCULATION_PROMPT = """From the task instruction, determine the arithmetic needed. \
Reply with JSON: {"expression": "<a Python arithmetic expression using the variable names \
below>", "variables": {"<name>": <number>, ...}, "units": {"<name>": "<unit or empty string>", \
...}}. Use only +, -, *, /, parentheses and the named variables in `expression` — no function \
calls."""
