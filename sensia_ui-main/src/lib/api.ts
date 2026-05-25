const API_BASE = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "") ?? "";

export type Turn = { user: string; bot: string };

export type GuardrailMeta = {
  guardrail_triggered?: boolean;
  guardrail_category?: string | null;
};

export type HealthResponse = { ok: boolean; redis_active: boolean };

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = (body as { detail?: string }).detail ?? JSON.stringify(body);
    } catch {
      /* noop */
    }
    throw new Error(detail || `Request failed (${res.status})`);
  }
  return res.json() as Promise<T>;
}

export async function fetchHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/api/health");
}

export async function createSession(): Promise<{ session_id: string; redis_active: boolean }> {
  return request("/api/sessions", { method: "POST" });
}

export async function fetchTurns(sessionId: string): Promise<Turn[]> {
  const data = await request<{ turns: Turn[] }>(`/api/sessions/${encodeURIComponent(sessionId)}/turns`);
  return data.turns ?? [];
}

export async function sendChat(
  sessionId: string,
  message: string,
): Promise<{ reply: string; turns: Turn[] } & GuardrailMeta> {
  return request(`/api/sessions/${encodeURIComponent(sessionId)}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
}

export async function sendMicAudio(sessionId: string, blob: Blob): Promise<{
  duplicate: boolean;
  transcription?: string | null;
  reply?: string | null;
  turns: Turn[];
  error?: string | null;
} & GuardrailMeta> {
  const form = new FormData();
  form.append("file", blob, "recording.wav");
  const res = await fetch(`${API_BASE}/api/sessions/${encodeURIComponent(sessionId)}/mic`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = (body as { detail?: string }).detail ?? JSON.stringify(body);
    } catch {
      /* noop */
    }
    throw new Error(detail || `Mic upload failed (${res.status})`);
  }
  return res.json();
}

export async function analyzeAudioFile(
  sessionId: string,
  file: File,
): Promise<{
  duplicate: boolean;
  transcription?: string | null;
  reply?: string | null;
  elapsed_seconds?: number | null;
  turns: Turn[];
} & GuardrailMeta> {
  const form = new FormData();
  form.append("file", file, file.name);
  const res = await fetch(`${API_BASE}/api/sessions/${encodeURIComponent(sessionId)}/audio/analyze`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = (body as { detail?: string }).detail ?? JSON.stringify(body);
    } catch {
      /* noop */
    }
    throw new Error(detail || `Audio analyze failed (${res.status})`);
  }
  return res.json();
}

export async function fetchTtsUrl(sessionId: string, text: string): Promise<string> {
  const res = await fetch(`${API_BASE}/api/sessions/${encodeURIComponent(sessionId)}/tts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: text }),
  });
  if (!res.ok) throw new Error(`TTS failed (${res.status})`);
  const blob = await res.blob();
  return URL.createObjectURL(blob);
}

export async function clearSession(sessionId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/sessions/${encodeURIComponent(sessionId)}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`Clear session failed (${res.status})`);
}

export function turnsToMessages(turns: Turn[]): { id: number; role: "user" | "ai"; text: string; time: string }[] {
  const out: { id: number; role: "user" | "ai"; text: string; time: string }[] = [];
  let seq = 0;
  const now = () => {
    const d = new Date();
    return `${d.getHours()}:${String(d.getMinutes()).padStart(2, "0")}`;
  };
  for (const t of turns) {
    out.push({ id: seq++, role: "user", text: t.user, time: now() });
    out.push({ id: seq++, role: "ai", text: t.bot, time: now() });
  }
  return out;
}
