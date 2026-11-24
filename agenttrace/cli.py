from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agenttrace.diagnostics import analyze_trace
from agenttrace.eval import EvalDataset, run_eval_dataset
from agenttrace.recorder import TraceRecorder


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agenttrace", description="AgentTrace CLI")
    parser.add_argument("--db", default=None, help="SQLite database path")
    sub = parser.add_subparsers(dest="cmd", required=True)

    ls = sub.add_parser("list", help="List recent traces")
    ls.add_argument("--limit", type=int, default=20)

    show = sub.add_parser("show", help="Show trace JSON")
    show.add_argument("trace_id")

    diag = sub.add_parser("diagnose", help="Run diagnostics on a trace")
    diag.add_argument("trace_id")

    ev = sub.add_parser("eval", help="Run eval dataset")
    ev.add_argument("dataset", type=Path)
    ev.add_argument("--example", action="store_true", help="Use built-in example runner")

    args = parser.parse_args(argv)
    rec = TraceRecorder(args.db)

    if args.cmd == "list":
        for t in rec.list_traces(args.limit):
            print(f"{t['id']}\t{t['status']}\t{t['name']}")
        return 0

    if args.cmd == "show":
        tr = rec.get_trace(args.trace_id)
        if not tr:
            print("trace not found", file=sys.stderr)
            return 1
        print(json.dumps(tr.to_dict(), indent=2, default=str))
        return 0

    if args.cmd == "diagnose":
        tr = rec.get_trace(args.trace_id)
        if not tr:
            print("trace not found", file=sys.stderr)
            return 1
        for f in analyze_trace(tr):
            print(f"[{f.severity}] {f.code}: {f.message}")
        return 0

    if args.cmd == "eval":
        dataset = EvalDataset.load(args.dataset)
        if args.example:
            from examples.demo_agent import run_case_for_eval

            summary = run_eval_dataset(dataset, lambda c: run_case_for_eval(c, rec), recorder=rec)
        else:
            print("Provide --example or integrate your own runner", file=sys.stderr)
            return 1
        print(json.dumps(summary.model_dump(mode="json"), indent=2))
        return 0 if summary.failed == 0 else 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())