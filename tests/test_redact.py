from agenttrace.core import SpanKind
from agenttrace.recorder import TraceRecorder
from agenttrace.redact import REDACTED, redact_value
from agenttrace.session import TraceSession


def test_redact_api_keys_and_auth():
    payload = {
        "api_key": "sk-secret-should-go",
        "headers": {"Authorization": "Bearer abcdefghijklmnop"},
        "messages": [{"role": "user", "content": "my key is sk-abcdefghijklmnopqrstuvwxyz123456"}],
        "ok": True,
    }
    out = redact_value(payload)
    assert out["api_key"] == REDACTED
    assert REDACTED in str(out["headers"]["Authorization"])
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in str(out["messages"])
    assert out["ok"] is True


def test_recorder_persists_redacted(tmp_path):
    rec = TraceRecorder(tmp_path / "t.db")
    with TraceSession("sec", recorder=rec) as session:
        with session.span(
            "call",
            SpanKind.MODEL,
            input={"api_key": "sk-proj-AAAAAAAAAAAAAAAAAAAA", "prompt": "hi"},
        ) as span:
            span.output = {"token": "ghp_abcdefghijklmnopqrstuv", "result": "weather 22C"}
    tr = rec.get_trace(session.trace.id)
    blob = tr.to_dict()
    text = str(blob)
    assert "sk-proj-AAAAAAAAAAAAAAAAAAAA" not in text
    assert "ghp_abcdefghijklmnopqrstuv" not in text
    assert REDACTED in text
    toolish = tr.spans[0].output
    assert "weather 22C" in str(toolish)


def test_password_field():
    assert redact_value({"password": "hunter2"})["password"] == REDACTED
