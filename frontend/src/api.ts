const base = "";

export type TraceSummary = {
  id: string;
  name: string;
  status: string;
  started_at: number;
  ended_at?: number;
  metadata: Record<string, unknown>;
};

export async function listTraces(): Promise<TraceSummary[]> {
  const r = await fetch(`${base}/api/traces`);
  if (!r.ok) throw new Error("Failed to list traces");
  return r.json();
}

export async function getTrace(id: string) {
  const r = await fetch(`${base}/api/traces/${id}`);
  if (!r.ok) throw new Error("trace not found");
  return r.json();
}

export async function getTree(id: string) {
  const r = await fetch(`${base}/api/traces/${id}/tree`);
  if (!r.ok) throw new Error("tree not found");
  return r.json();
}

export async function getDiagnostics(id: string) {
  const r = await fetch(`${base}/api/traces/${id}/diagnostics`);
  return r.json();
}

export async function getContext(id: string) {
  const r = await fetch(`${base}/api/traces/${id}/context`);
  return r.json();
}

export async function runEval(datasetPath: string) {
  const r = await fetch(`${base}/api/eval/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ dataset_path: datasetPath }),
  });
  return r.json();
}