const base = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

export type TraceSummary = {
  id: string;
  name: string;
  status: string;
  started_at: number;
  ended_at?: number;
  metadata: Record<string, unknown>;
};

async function parseJson(r: Response, fallback: string) {
  if (!r.ok) {
    const text = await r.text();
    throw new Error(`${fallback}: ${r.status} ${text.slice(0, 200)}`);
  }
  return r.json();
}

export async function listTraces(): Promise<TraceSummary[]> {
  const r = await fetch(`${base}/api/traces`);
  return parseJson(r, "Failed to list traces");
}

export async function getTrace(id: string) {
  const r = await fetch(`${base}/api/traces/${id}`);
  return parseJson(r, "trace not found");
}

export async function getTree(id: string) {
  const r = await fetch(`${base}/api/traces/${id}/tree`);
  return parseJson(r, "tree not found");
}

export async function getDiagnostics(id: string) {
  const r = await fetch(`${base}/api/traces/${id}/diagnostics`);
  return parseJson(r, "diagnostics failed");
}

export async function getContext(id: string) {
  const r = await fetch(`${base}/api/traces/${id}/context`);
  return parseJson(r, "context failed");
}

export async function replayTrace(
  id: string,
  spanId?: string
): Promise<{ mode: string; trace: { id: string } }> {
  const r = await fetch(`${base}/api/traces/${id}/replay`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ span_id: spanId ?? null, mode: "history" }),
  });
  return parseJson(r, "replay failed");
}

export async function runEval(datasetPath: string) {
  const r = await fetch(`${base}/api/eval/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ dataset_path: datasetPath }),
  });
  return parseJson(r, "eval failed");
}

export type RecoveryDemo = {
  failed_trace: string;
  history_trace: string;
  retry_trace: string;
  retry_status: string;
  diagnostics: { code: string; message: string }[];
  baseline: { passed: number; total: number };
  candidate: { passed: number; total: number };
};

export async function runRecoveryDemo(): Promise<RecoveryDemo> {
  const r = await fetch(`${base}/api/demo/order-recovery`, { method: "POST" });
  return parseJson(r, "Recovery demo failed");
}
