const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

export interface ProblemSummary {
  problem_id: string;
  title: string;
  category: string;
  score: number;
  snippet: string;
  lat: number | null;
  lon: number | null;
}

export interface SearchResponse {
  results: ProblemSummary[];
  total: number;
  query: { text: string; limit: number; offset: number };
}

export async function searchProblems(
  text: string,
  options?: { limit?: number; offset?: number }
): Promise<SearchResponse> {
  const params = new URLSearchParams();
  if (text) params.set("text", text);
  if (options?.limit) params.set("limit", String(options.limit));
  if (options?.offset) params.set("offset", String(options.offset));

  const resp = await fetch(`${API_BASE}/search?${params}`);
  if (!resp.ok) throw new Error(`Search failed: ${resp.statusText}`);
  return resp.json();
}

export async function listArtifacts(): Promise<any[]> {
  const resp = await fetch(`${API_BASE}/artifacts`);
  if (!resp.ok) throw new Error(`Failed to fetch artifacts: ${resp.statusText}`);
  return resp.json();
}

export async function getArtifact(id: string): Promise<any> {
  const resp = await fetch(`${API_BASE}/artifacts/${id}`);
  if (!resp.ok) throw new Error(`Failed to fetch artifact: ${resp.statusText}`);
  return resp.json();
}

export async function ingestArtifacts(
  limit: number = 3,
  org: string = ""
): Promise<{ ingested: number }> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (org) params.set("org", org);
  const resp = await fetch(`${API_BASE}/artifacts/ingest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  if (!resp.ok) throw new Error(`Ingest failed: ${resp.statusText}`);
  return resp.json();
}
