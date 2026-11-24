from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from agenttrace.core import Trace
from agenttrace.recorder import TraceRecorder


class EvalAssertion(BaseModel):
    type: str
    path: str | None = None
    expected: Any = None
    op: str = "eq"


class EvalCase(BaseModel):
    id: str
    input: dict[str, Any] = Field(default_factory=dict)
    expected: dict[str, Any] = Field(default_factory=dict)
    assertions: list[EvalAssertion] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class EvalDataset(BaseModel):
    name: str
    version: str = "1"
    model: str | None = None
    prompt_version: str | None = None
    cases: list[EvalCase] = Field(default_factory=list)

    @classmethod
    def load(cls, path: str | Path) -> EvalDataset:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.model_validate(data)


class EvalCaseResult(BaseModel):
    case_id: str
    passed: bool
    trace_id: str | None = None
    failures: list[str] = Field(default_factory=list)
    output: Any = None


class EvalRunSummary(BaseModel):
    id: str
    dataset: str
    passed: int
    failed: int
    total: int
    duration_ms: float
    results: list[EvalCaseResult] = Field(default_factory=list)
    model_version: str | None = None
    prompt_version: str | None = None


def _get_path(obj: Any, path: str) -> Any:
    cur = obj
    for part in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def run_assertions(output: Any, assertions: list[EvalAssertion], expected: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for a in assertions:
        if a.type == "output_contains":
            text = str(output)
            if a.expected not in text:
                failures.append(f"output does not contain {a.expected!r}")
        elif a.type == "path_eq":
            actual = _get_path(output if isinstance(output, dict) else {"value": output}, a.path or "")
            exp = a.expected if a.expected is not None else _get_path(expected, a.path or "")
            if actual != exp:
                failures.append(f"{a.path}: expected {exp!r}, got {actual!r}")
        elif a.type == "no_error":
            if isinstance(output, dict) and output.get("error"):
                failures.append(f"unexpected error: {output['error']}")
        elif a.type == "trace_status" and isinstance(output, dict) and output.get("status") != a.expected:
            failures.append(f"trace status {output.get('status')} != {a.expected}")
    return failures


def run_eval_dataset(
    dataset: EvalDataset,
    runner: Callable[[EvalCase], tuple[Any, Trace | None]],
    *,
    recorder: TraceRecorder | None = None,
) -> EvalRunSummary:
    run_id = uuid.uuid4().hex[:12]
    start = time.time()
    results: list[EvalCaseResult] = []

    for case in dataset.cases:
        try:
            output, trace = runner(case)
            failures = run_assertions(output, case.assertions, case.expected)
            if (
                trace is not None
                and case.expected.get("status")
                and trace.status.value != case.expected["status"]
            ):
                failures.append(f"trace status {trace.status.value} != {case.expected['status']}")
            passed = len(failures) == 0
            results.append(
                EvalCaseResult(
                    case_id=case.id,
                    passed=passed,
                    trace_id=trace.id if trace else None,
                    failures=failures,
                    output=output,
                )
            )
        except Exception as e:
            results.append(
                EvalCaseResult(case_id=case.id, passed=False, failures=[str(e)])
            )

    passed = sum(1 for r in results if r.passed)
    failed = len(results) - passed
    duration_ms = (time.time() - start) * 1000
    summary = EvalRunSummary(
        id=run_id,
        dataset=dataset.name,
        passed=passed,
        failed=failed,
        total=len(results),
        duration_ms=duration_ms,
        results=results,
        model_version=dataset.model,
        prompt_version=dataset.prompt_version,
    )
    if recorder:
        recorder.save_eval_run(run_id, dataset.name, summary.model_dump(mode="json"))
    return summary


def compare_eval_runs(a: EvalRunSummary, b: EvalRunSummary) -> dict[str, Any]:
    """Regression diff between two eval runs (e.g. prompt/model versions)."""
    by_case_a = {r.case_id: r for r in a.results}
    by_case_b = {r.case_id: r for r in b.results}
    regressions = []
    fixes = []
    for cid, ra in by_case_a.items():
        rb = by_case_b.get(cid)
        if rb is None:
            continue
        if ra.passed and not rb.passed:
            regressions.append({"case_id": cid, "failures": rb.failures})
        if not ra.passed and rb.passed:
            fixes.append(cid)
    return {
        "baseline": a.id,
        "candidate": b.id,
        "regressions": regressions,
        "fixes": fixes,
        "pass_rate_delta": (b.passed / b.total if b.total else 0) - (a.passed / a.total if a.total else 0),
    }