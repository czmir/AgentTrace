"""LangChain-style integration sketch (callback handler only — no langchain install required)."""

from agenttrace.adapters.langchain_callback import AgentTraceHandler
from agenttrace.recorder import TraceRecorder
from agenttrace.session import TraceSession

handler = AgentTraceHandler()


def demo() -> None:
    rec = TraceRecorder()
    with TraceSession("langchain_demo", recorder=rec) as session:
        run_id = "00000000-0000-0000-0000-000000000001"
        handler.on_chain_start({"name": "ResearchChain"}, {"question": "What is AgentTrace?"}, run_id=run_id)
        handler.on_llm_start({"name": "ChatOpenAI"}, ["Summarize AgentTrace"], run_id=run_id)
        handler.on_llm_end("AgentTrace is a lightweight tracing SDK.", run_id=run_id)
        handler.on_tool_start({"name": "search"}, "AgentTrace features", run_id=run_id)
        handler.on_tool_end('{"hits": 3}', run_id=run_id)
        handler.on_chain_end({"answer": "..."}, run_id=run_id)
    print("trace", session.trace.id, "spans", len(session.trace.spans))


if __name__ == "__main__":
    demo()