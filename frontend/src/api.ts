const TOKEN_KEY = "wdb_token";
let token = "";
try {
  token = sessionStorage.getItem(TOKEN_KEY) ?? "";
} catch {
  /* ohne Browserspeicher weiter */
}

interface Optionen { method?: string; body?: unknown }

/** JSON-API mit Token-Abfrage: Bei 401 wird einmal nach dem Zugangs-Token gefragt. */
export async function api<T>(path: string, opt: Optionen = {}, retry = true): Promise<T> {
  const headers: Record<string, string> = {};
  if (opt.body !== undefined) headers["Content-Type"] = "application/json";
  if (token) headers["X-WDB-Token"] = token;
  const r = await fetch(path, {
    method: opt.method ?? "GET",
    headers,
    body: opt.body !== undefined ? JSON.stringify(opt.body) : undefined,
  });
  const data: unknown = await r.json().catch(() => ({}));
  if (r.status === 401 && retry) {
    const t = window.prompt("Zugangs-Token für Änderungen:");
    if (t) {
      token = t;
      try {
        sessionStorage.setItem(TOKEN_KEY, t);
      } catch {
        /* egal */
      }
      return api<T>(path, opt, false);
    }
  }
  if (!r.ok) throw new Error((data as { fehler?: string }).fehler ?? `Fehler ${r.status}`);
  return data as T;
}
