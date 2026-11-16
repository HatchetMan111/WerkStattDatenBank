const TOKEN_KEY = "wdb_token";
let token = "";
try {
  token = sessionStorage.getItem(TOKEN_KEY) ?? "";
} catch {
  /* ohne Browserspeicher weiter */
}

interface Optionen { method?: string; body?: unknown }

function merkeToken(t: string) {
  token = t;
  try {
    sessionStorage.setItem(TOKEN_KEY, t);
  } catch {
    /* egal */
  }
}

/** Fragt einmal nach dem Zugangs-Token; liefert false, wenn der Benutzer abbricht. */
function frageToken(): boolean {
  const t = window.prompt("Zugangs-Token für Änderungen:");
  if (!t) return false;
  merkeToken(t);
  return true;
}

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
  if (r.status === 401 && retry && frageToken()) return api<T>(path, opt, false);
  if (!r.ok) throw new Error((data as { fehler?: string }).fehler ?? `Fehler ${r.status}`);
  return data as T;
}

/** Datei hochladen (roher Body, mit Fortschritt). Gibt die Job-Nummer zurück. */
export function uploadDatei(
  datei: File,
  params: { typ: string; quelle: string },
  onProgress: (geladen: number, gesamt: number) => void,
  retry = true,
): Promise<{ ok: boolean; job: number }> {
  return new Promise((resolve, reject) => {
    const q = new URLSearchParams({ typ: params.typ, quelle: params.quelle, name: datei.name });
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/import/upload?" + q.toString());
    xhr.setRequestHeader("Content-Type", "application/octet-stream");
    xhr.setRequestHeader("X-WDB-Upload", "1");
    if (token) xhr.setRequestHeader("X-WDB-Token", token);
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded, e.total);
    xhr.onerror = () => reject(new Error("Upload fehlgeschlagen (Verbindung unterbrochen oder Datei zu groß)"));
    xhr.onload = () => {
      let data: { fehler?: string; ok?: boolean; job?: number } = {};
      try {
        data = JSON.parse(xhr.responseText || "{}");
      } catch {
        /* leer */
      }
      if (xhr.status === 401 && retry && frageToken()) {
        uploadDatei(datei, params, onProgress, false).then(resolve, reject);
        return;
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(data as { ok: boolean; job: number });
      else reject(new Error(data.fehler ?? `Fehler ${xhr.status}`));
    };
    xhr.send(datei);
  });
}
