import json
from pathlib import Path

import pytest

from agenttrace.eval import (
    EvalAssertion,
    EvalConfigError,
    EvalDataset,
    run_assertions,
    run_eval_dataset,
)


def test_unknown_assertion_type_fails():
    failures = run_assertions({"status": "ok"}, [EvalAssertion(type="not_a_real_type")], {})
    assert failures
    assert "unknown assertion type" in failures[0]


def test_missing_path_fails():
    failures = run_assertions({"status": "ok"}, [EvalAssertion(type="path_eq")], {})
    assert any("missing required field 'path'" in f for f in failures)


def test_missing_expected_output_contains_fails():
    failures = run_assertions("hello", [EvalAssertion(type="output_contains")], {})
    assert any("missing required field 'expected'" in f for f in failures)


def test_invalid_op_fails():
    failures = run_assertions(
        {"n": 1}, [EvalAssertion(type="path_op", path="n", op="bogus", expected=1)], {}
    )
    assert any("invalid assertion op" in f for f in failures)


def test_trace_status_non_dict_fails():
    failures = run_assertions("ok", [EvalAssertion(type="trace_status", expected="ok")], {})
    assert failures
    assert "trace status" in failures[0]


def test_bad_dataset_json_fails(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    with pytest.raises(EvalConfigError):
        EvalDataset.load(p)


def test_dataset_missing_name_fails(tmp_path):
    p = tmp_path / "noname.json"
    p.write_text(json.dumps({"cases": []}), encoding="utf-8")
    with pytest.raises(EvalConfigError):
        EvalDataset.load(p)


def test_run_eval_unknown_type_case_fails():
    dataset = EvalDataset.model_validate(
        {
            "name": "bad-assert",
            "cases": [
                {
                    "id": "c1",
                    "assertions": [{"type": "totally_unknown"}],
                }
            ],
        }
    )
    summary = run_eval_dataset(dataset, lambda c: ({"ok": True}, None))
    assert summary.failed == 1
    assert summary.passed == 0
    assert "unknown assertion type" in summary.results[0].failures[0]


def test_empty_dataset_fails():
    dataset = EvalDataset(name="empty", cases=[])
    summary = run_eval_dataset(dataset, lambda c: ({}, None))
    assert summary.failed >= 1
    assert summary.passed == 0


def test_known_path_eq_still_passes():
    dataset = EvalDataset.model_validate(
        {
            "name": "ok",
            "cases": [
                {
                    "id": "c1",
                    "assertions": [{"type": "path_eq", "path": "status", "expected": "ok"}],
                }
            ],
        }
    )
    summary = run_eval_dataset(dataset, lambda c: ({"status": "ok"}, None))
    assert summary.passed == 1
    assert summary.failed == 0


def test_golden_file_exists():
    assert Path("examples/eval/golden_v1.json").is_file()
