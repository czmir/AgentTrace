from agenttrace.cli import main
from agenttrace.recorder import TraceRecorder
from examples.demo_agent import run_scenario


def test_cli_list_and_show(tmp_path, capsys):
    db = tmp_path / "t.db"
    rec = TraceRecorder(db)
    tr = run_scenario("normal_call", rec)
    assert main(["--db", str(db), "list"]) == 0
    out = capsys.readouterr().out
    assert tr.id in out
    assert main(["--db", str(db), "show", tr.id]) == 0
    assert main(["--db", str(db), "diagnose", tr.id]) == 0
    assert main(["--db", str(db), "replay", tr.id]) == 0


def test_cli_eval_example(tmp_path):
    db = tmp_path / "t.db"
    code = main(["--db", str(db), "eval", "examples/eval/golden_v1.json", "--example"])
    assert code in (0, 2)


def test_cli_eval_bad_config(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{", encoding="utf-8")
    assert main(["eval", str(p), "--example"]) == 2
