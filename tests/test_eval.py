from pathlib import Path

from agenttrace.eval import EvalDataset, compare_eval_runs, run_eval_dataset
from agenttrace.recorder import TraceRecorder
from examples.demo_agent import run_case_for_eval


def test_golden_eval_v1(tmp_path):
    rec = TraceRecorder(tmp_path / "eval.db")
    dataset = EvalDataset.load(Path("examples/eval/golden_v1.json"))
    summary = run_eval_dataset(dataset, lambda c: run_case_for_eval(c, rec), recorder=rec)
    assert summary.total == len(dataset.cases)
    assert summary.failed == 0, [r.failures for r in summary.results]
    assert summary.passed == summary.total


def test_eval_regression_compare(tmp_path):
    rec = TraceRecorder(tmp_path / "eval.db")
    v1 = EvalDataset.load(Path("examples/eval/golden_v1.json"))
    v2 = EvalDataset.load(Path("examples/eval/golden_v2_regression.json"))
    s1 = run_eval_dataset(v1, lambda c: run_case_for_eval(c, rec), recorder=rec)
    s2 = run_eval_dataset(v2, lambda c: run_case_for_eval(c, rec), recorder=rec)
    diff = compare_eval_runs(s1, s2)
    assert "regressions" in diff