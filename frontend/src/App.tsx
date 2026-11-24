import { Link, Route, Routes, useNavigate, useParams } from "react-router-dom";
import { useEffect, useState } from "react";
import {
  TraceSummary,
  getContext,
  getDiagnostics,
  getTrace,
  getTree,
  listTraces,
  replayTrace,
  runEval,
} from "./api";

function Layout({ children }: { children: React.ReactNode }) {
  return (
    <div className="layout">
      <header className="header">
        <Link to="/" className="brand">
          AgentTrace
        </Link>
        <nav>
          <Link to="/">Traces</Link>
          <Link to="/eval">Eval</Link>
        </nav>
      </header>
      <main className="main">{children}</main>
    </div>
  );
}

function TracesPage() {
  const [traces, setTraces] = useState<TraceSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listTraces()
      .then(setTraces)
      .catch((e) => setError(String(e)));
  }, []);

  return (
    <Layout>
      <h1>Execution traces</h1>
      <p className="muted">Local-first agent runs · tree + timeline + diagnostics</p>
      {error && <div className="banner error">{error}</div>}
      <table className="table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Status</th>
            <th>Started</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {traces.map((t) => (
            <tr key={t.id}>
              <td>{t.name}</td>
              <td>
                <span className={`pill ${t.status}`}>{t.status}</span>
              </td>
              <td>{new Date(t.started_at * 1000).toLocaleString()}</td>
              <td>
                <Link to={`/traces/${t.id}`}>Open</Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {traces.length === 0 && !error && <p className="muted">No traces yet. Run examples/demo_agent.py</p>}
    </Layout>
  );
}

function SpanTree({ nodes, depth = 0 }: { nodes: Array<{ span: Record<string, unknown>; children: unknown[] }>; depth?: number }) {
  return (
    <ul className="tree" style={{ marginLeft: depth * 12 }}>
      {nodes.map((n) => {
        const s = n.span as { id: string; name: string; kind: string; error?: string; duration_ms?: number };
        return (
          <li key={s.id}>
            <span className="kind">{s.kind}</span> {s.name}
            {s.duration_ms != null && <span className="muted"> · {s.duration_ms.toFixed(1)}ms</span>}
            {s.error && <span className="err"> — {s.error}</span>}
            {Array.isArray(n.children) && n.children.length > 0 && (
              <SpanTree nodes={n.children as typeof nodes} depth={depth + 1} />
            )}
          </li>
        );
      })}
    </ul>
  );
}

function TraceDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [trace, setTrace] = useState<Record<string, unknown> | null>(null);
  const [tree, setTree] = useState<{ tree: unknown[]; timeline: unknown[] } | null>(null);
  const [diag, setDiag] = useState<{ findings: Array<Record<string, string>> } | null>(null);
  const [ctx, setCtx] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [replaying, setReplaying] = useState(false);

  useEffect(() => {
    if (!id) return;
    Promise.all([getTrace(id), getTree(id), getDiagnostics(id), getContext(id)])
      .then(([t, tr, d, c]) => {
        setTrace(t);
        setTree(tr);
        setDiag(d);
        setCtx(c);
      })
      .catch((e) => setError(String(e)));
  }, [id]);

  async function onReplay() {
    if (!id) return;
    setReplaying(true);
    try {
      const result = await replayTrace(id);
      const newId = result.trace.id;
      if (newId) navigate(`/traces/${newId}`);
    } catch (e) {
      setError(String(e));
    } finally {
      setReplaying(false);
    }
  }

  if (!id) return null;
  return (
    <Layout>
      <Link to="/">← Back</Link>
      <h1>{String(trace?.name ?? id)}</h1>
      {error && <div className="banner error">{error}</div>}
      <div className="actions">
        <button disabled={replaying} onClick={onReplay}>
          {replaying ? "Replaying…" : "History replay"}
        </button>
        <span className="muted"> copies stored I/O — does not re-execute tools</span>
      </div>
      <div className="grid">
        <section className="card">
          <h2>Span tree</h2>
          {tree?.tree?.length ? (
            <SpanTree nodes={tree.tree as Parameters<typeof SpanTree>[0]["nodes"]} />
          ) : (
            <p className="muted">{error ? "Unavailable" : "Loading…"}</p>
          )}
        </section>
        <section className="card">
          <h2>Timeline</h2>
          <ol className="timeline">
            {(tree?.timeline as Array<Record<string, unknown>> | undefined)?.map((e) => (
              <li key={String(e.id)}>
                <strong>{String(e.name)}</strong> <span className="kind">{String(e.kind)}</span>
                {e.duration_ms != null && <span className="muted"> {Number(e.duration_ms).toFixed(1)}ms</span>}
              </li>
            ))}
          </ol>
        </section>
        <section className="card">
          <h2>Diagnostics</h2>
          {diag?.findings?.length ? (
            <ul>
              {diag.findings.map((f, i) => (
                <li key={i} className={f.severity}>
                  [{f.code}] {f.message}
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">No issues</p>
          )}
        </section>
        <section className="card">
          <h2>Context</h2>
          <pre className="code">{JSON.stringify(ctx, null, 2)}</pre>
        </section>
      </div>
    </Layout>
  );
}

function EvalPage() {
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onRun(path: string) {
    setLoading(true);
    setError(null);
    try {
      setResult(await runEval(path));
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <Layout>
      <h1>Eval</h1>
      <p className="muted">Golden datasets · batch assertions · version compare (CLI for diff)</p>
      {error && <div className="banner error">{error}</div>}
      <div className="actions">
        <button disabled={loading} onClick={() => onRun("examples/eval/golden_v1.json")}>
          Run golden v1
        </button>
      </div>
      {result && (
        <pre className="code">{JSON.stringify(result, null, 2)}</pre>
      )}
    </Layout>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<TracesPage />} />
      <Route path="/traces/:id" element={<TraceDetailPage />} />
      <Route path="/eval" element={<EvalPage />} />
    </Routes>
  );
}
