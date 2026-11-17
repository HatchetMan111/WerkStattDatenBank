import { useCallback, useEffect, useRef, useState } from "react";
import { api, uploadDatei } from "../api";
import type { ImportQuellen, ImportStatus } from "../types";

interface Props {
  offen: boolean;
  onClose: () => void;
  /** Wird nach jedem erfolgreich beendeten Import aufgerufen (Zahlen, Fahrzeuge, Artikel neu laden). */
  onFertig: () => void;
  /** Sind erfundene Beispieldaten in der Datenbank? */
  demoVorhanden: boolean;
}

const TYPEN = [
  { wert: "auto", text: "Automatisch erkennen" },
  { wert: "eea", text: "Fahrzeugdaten (EEA-Format)" },
  { wert: "artikel", text: "Artikelliste (lieferant;artikelnr;bezeichnung …)" },
];

const mb = (n: number) => (n / 1048576).toLocaleString("de-DE", { maximumFractionDigits: 1 }) + " MB";

function fortschrittText(s: ImportStatus): string {
  if (s.phase === "Herunterladen") return mb(s.fortschritt);
  return s.fortschritt ? s.fortschritt.toLocaleString("de-DE") + " Zeilen/Artikel" : "";
}

export default function ImportDialog({ offen, onClose, onFertig, demoVorhanden }: Props) {
  const dlg = useRef<HTMLDialogElement>(null);
  const gemeldet = useRef(0);
  const [quellen, setQuellen] = useState<ImportQuellen | null>(null);
  const [status, setStatus] = useState<ImportStatus | null>(null);
  const [fehler, setFehler] = useState("");
  const [info, setInfo] = useState("");
  const [datei, setDatei] = useState<File | null>(null);
  const [typ, setTyp] = useState("auto");
  const [herkunft, setHerkunft] = useState("");
  const [up, setUp] = useState<{ geladen: number; gesamt: number } | null>(null);
  const [url, setUrl] = useState("");
  const [urlName, setUrlName] = useState("");
  const [merken, setMerken] = useState(true);

  const laeuft = status?.state === "laeuft" || up !== null;

  const ladeQuellen = useCallback(
    () => api<ImportQuellen>("/api/import/quellen").then(setQuellen).catch((e: Error) => setFehler(e.message)),
    [],
  );
  const ladeStatus = useCallback(
    () => api<ImportStatus>("/api/import/status").then(setStatus).catch((e: Error) => setFehler(e.message)),
    [],
  );

  // Dialog öffnen/schließen
  useEffect(() => {
    const d = dlg.current;
    if (!d) return;
    if (offen && !d.open) {
      setFehler("");
      if (typeof d.showModal === "function") d.showModal();
      else d.setAttribute("open", "");
      void ladeQuellen();
      void ladeStatus();
    } else if (!offen && d.open) {
      if (typeof d.close === "function") d.close();
      else d.removeAttribute("open");
    }
  }, [offen, ladeQuellen, ladeStatus]);

  // Während ein Import läuft: jede Sekunde nachfragen
  useEffect(() => {
    if (!offen || status?.state !== "laeuft") return;
    const t = setInterval(() => void ladeStatus(), 1000);
    return () => clearInterval(t);
  }, [offen, status?.state, ladeStatus]);

  // Fertigmeldung genau einmal je Import
  useEffect(() => {
    if (status && status.state === "fertig" && status.id !== gemeldet.current) {
      gemeldet.current = status.id;
      onFertig();
      void ladeQuellen();
    }
    if (status && status.state === "fehler") void ladeQuellen();
  }, [status, onFertig, ladeQuellen]);

  async function demo(aktion: "laden" | "entfernen") {
    if (aktion === "entfernen" && !window.confirm("Beispieldaten entfernen? Eigene und importierte Daten bleiben erhalten.")) return;
    setFehler("");
    setInfo("");
    try {
      await api("/api/import/demo", { method: "POST", body: { aktion } });
      setInfo(aktion === "laden" ? "Beispieldaten geladen." : "Beispieldaten entfernt.");
      onFertig();
    } catch (e) {
      setFehler((e as Error).message);
    }
  }

  async function hochladen() {
    if (!datei) return;
    setFehler("");
    setUp({ geladen: 0, gesamt: datei.size });
    try {
      await uploadDatei(datei, { typ, quelle: herkunft.trim() }, (geladen, gesamt) => setUp({ geladen, gesamt }));
      setDatei(null);
      await ladeStatus();
    } catch (e) {
      setFehler((e as Error).message);
    } finally {
      setUp(null);
    }
  }

  async function ausUrl() {
    setFehler("");
    try {
      await api("/api/import/url", { method: "POST", body: { url: url.trim(), typ, name: urlName.trim(), merken, quelle: herkunft.trim() } });
      await ladeStatus();
      await ladeQuellen();
    } catch (e) {
      setFehler((e as Error).message);
    }
  }

  async function aktualisieren(id: number) {
    setFehler("");
    try {
      await api(`/api/import/quellen/${id}/aktualisieren`, { method: "POST", body: {} });
      await ladeStatus();
    } catch (e) {
      setFehler((e as Error).message);
    }
  }

  async function entfernen(id: number) {
    try {
      await api(`/api/import/quellen/${id}`, { method: "DELETE" });
      await ladeQuellen();
    } catch (e) {
      setFehler((e as Error).message);
    }
  }

  return (
    <dialog ref={dlg} className="import" aria-labelledby="impTitel" onClose={onClose}>
      <h2 id="impTitel">Daten importieren und aktualisieren</h2>
      <p className="status">
        Nur Daten verwenden, die du verwenden darfst: offene Daten mit Quellenangabe, eigene Listen oder Händlerlisten im Rahmen der
        Händlerbedingungen. Importe sind wiederholbar – vorhandene Einträge werden aktualisiert, nicht doppelt angelegt.
      </p>

      <h3>Zum Ausprobieren: Beispieldaten</h3>
      <p className="status">
        Erfundene Fahrzeuge („Musterwagen“) und Teile („DEMO-…“), damit du sofort siehst, wie Suche, Fahrzeugwahl, Zuordnung und „verbaut“ funktionieren.
      </p>
      <div className="actions">
        {demoVorhanden ? (
          <button type="button" className="danger" disabled={laeuft} onClick={() => void demo("entfernen")}>Beispieldaten entfernen</button>
        ) : (
          <button type="button" disabled={laeuft} onClick={() => void demo("laden")}>Beispieldaten laden</button>
        )}
      </div>
      {info && <p className="status" role="status">{info}</p>}

      <h3>1. Datei hochladen</h3>
      <div className="row2">
        <label>
          CSV-Datei (auch .zip oder .gz)
          <input
            type="file"
            accept=".csv,.txt,.tsv,.zip,.gz"
            disabled={laeuft}
            onChange={(e) => setDatei(e.target.files?.[0] ?? null)}
          />
        </label>
        <label>
          Art der Daten
          <select value={typ} onChange={(e) => setTyp(e.target.value)} disabled={laeuft}>
            {TYPEN.map((t) => (<option key={t.wert} value={t.wert}>{t.text}</option>))}
          </select>
        </label>
      </div>
      <label>
        Herkunft für die Quellenliste (z. B. „Großhandel Müller“, nur bei Artikellisten)
        <input value={herkunft} onChange={(e) => setHerkunft(e.target.value)} maxLength={120} disabled={laeuft} />
      </label>
      {up && <progress value={up.geladen} max={up.gesamt} aria-label="Upload-Fortschritt" />}
      <div className="actions">
        <button type="button" disabled={!datei || laeuft} onClick={() => void hochladen()}>
          Hochladen und importieren
        </button>
      </div>

      <h3>2. Aus dem Internet laden (frei zugängliche Daten)</h3>
      {quellen?.katalog.map((k) => (
        <div className="src" key={k.key}>
          <p className="name">{k.name}</p>
          <p>Lizenz: {k.lizenz}</p>
          <p>{k.hinweis}</p>
          <p>
            <a href={k.seite} target="_blank" rel="noopener noreferrer">Download-Seite öffnen</a>{" · "}
            <button
              type="button"
              className="link"
              onClick={() => {
                setTyp(k.typ);
                setUrlName(k.name.split(" (")[0]);
              }}
            >
              Art und Name für den Link unten übernehmen
            </button>
          </p>
        </div>
      ))}
      <label>
        Direkter Download-Link (https://…, CSV, ZIP oder GZ)
        <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…" disabled={laeuft} />
      </label>
      <div className="row2">
        <label>
          Name der Quelle
          <input value={urlName} onChange={(e) => setUrlName(e.target.value)} maxLength={120} disabled={laeuft} />
        </label>
        <label className="check">
          <input type="checkbox" checked={merken} onChange={(e) => setMerken(e.target.checked)} /> Link merken (für spätere Aktualisierung)
        </label>
      </div>
      <div className="actions">
        <button type="button" disabled={!url.trim() || laeuft} onClick={() => void ausUrl()}>
          Laden und importieren
        </button>
      </div>

      {quellen && quellen.gespeichert.length > 0 && (
        <>
          <h3>Gemerkte Quellen</h3>
          {quellen.gespeichert.map((g) => (
            <div className="saved" key={g.id}>
              <div>
                <strong>{g.name}</strong>
                <div className="status">
                  {g.letzter_lauf ? `Letzter Lauf: ${g.letzter_lauf} – ${g.ergebnis ?? ""}` : "Noch nicht ausgeführt"}
                </div>
              </div>
              <div className="actions">
                <button type="button" disabled={laeuft} onClick={() => void aktualisieren(g.id)}>Aktualisieren</button>
                <button type="button" className="danger" disabled={laeuft} onClick={() => void entfernen(g.id)}>Entfernen</button>
              </div>
            </div>
          ))}
        </>
      )}

      {status && status.state !== "leer" && (
        <div className={status.state === "fehler" ? "job fehler" : "job"} role="status" aria-live="polite">
          <strong>{status.name}</strong>
          {status.state === "laeuft" && (
            <>
              <div>{status.phase} {fortschrittText(status)}</div>
              <progress aria-label="Import läuft" />
            </>
          )}
          {status.state === "fertig" && status.ergebnis && (
            <div>
              Fertig:{" "}
              {Object.entries(status.ergebnis)
                .filter(([k]) => k !== "typ")
                .map(([k, v]) => `${k.replace(/_/g, " ")}: ${typeof v === "number" ? v.toLocaleString("de-DE") : v}`)
                .join(" · ")}
            </div>
          )}
          {status.state === "fehler" && (
            <>
              <div className="fehler">{status.fehler}</div>
              {status.details && (
                <details>
                  <summary>Technische Details (vollständige Fehlerkette)</summary>
                  <pre>{status.details}</pre>
                </details>
              )}
            </>
          )}
        </div>
      )}

      <p className="fehler" role="alert">{fehler}</p>
      <div className="actions">
        <button type="button" className="ghost" onClick={onClose}>Schließen</button>
      </div>
    </dialog>
  );
}
