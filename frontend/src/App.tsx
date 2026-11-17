import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { api } from "./api";
import DetailPanel from "./components/DetailPanel";
import Footer from "./components/Footer";
import GroupTree from "./components/GroupTree";
import ImportDialog from "./components/ImportDialog";
import NewArticleDialog from "./components/NewArticleDialog";
import ResultTable from "./components/ResultTable";
import VehiclePicker from "./components/VehiclePicker";
import type { ArtikelDetail, ArtikelRow, FahrzeugAuswahl, Gruppe, Stats } from "./types";

interface Meldung { text: string; fehler: boolean }

const LIMIT = 200;

export default function App() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [baum, setBaum] = useState<Gruppe[]>([]);
  const [fahrzeug, setFahrzeug] = useState<FahrzeugAuswahl | null>(null);
  const [gruppe, setGruppe] = useState<{ id: number; name: string } | null>(null);
  const [eingabe, setEingabe] = useState("");
  const [q, setQ] = useState("");
  const [alle, setAlle] = useState(false);
  const [rows, setRows] = useState<ArtikelRow[]>([]);
  const [geladen, setGeladen] = useState(false);
  const [meldung, setMeldung] = useState<Meldung>({ text: "", fehler: false });
  const [detailId, setDetailId] = useState<number | null>(null);
  const [detail, setDetail] = useState<ArtikelDetail | null>(null);
  const [neu, setNeu] = useState(false);
  const [importOffen, setImportOffen] = useState(false);
  const [version, setVersion] = useState(0); // erhöht sich nach Änderungen → Liste neu laden
  const req = useRef(0);

  const zeige = useCallback((text: string, fehler = false) => setMeldung({ text, fehler }), []);

  const ladeStats = useCallback(
    () => api<Stats>("/api/stats").then(setStats).catch((e: Error) => zeige("Server nicht erreichbar: " + e.message, true)),
    [zeige],
  );
  const ladeGruppen = useCallback(
    () => api<Gruppe[]>("/api/gruppen").then(setBaum).catch((e: Error) => zeige(e.message, true)),
    [zeige],
  );

  useEffect(() => {
    void ladeStats();
    void ladeGruppen();
  }, [ladeStats, ladeGruppen]);

  // Suchfeld: 300 ms warten, bevor gesucht wird
  useEffect(() => {
    const t = setTimeout(() => setQ(eingabe.trim()), 300);
    return () => clearTimeout(t);
  }, [eingabe]);

  // Artikelliste
  useEffect(() => {
    const p = new URLSearchParams();
    if (fahrzeug) p.set("fahrzeug_id", String(fahrzeug.id));
    if (gruppe) p.set("gruppe_id", String(gruppe.id));
    if (q) p.set("q", q);
    if (fahrzeug && alle) p.set("strikt", "0");
    const mine = ++req.current;
    api<ArtikelRow[]>("/api/artikel?" + p.toString())
      .then((r) => {
        if (mine !== req.current) return; // veraltete Antwort verwerfen
        setRows(r);
        setGeladen(true);
        const filterAktiv = !!(fahrzeug || gruppe || q);
        zeige(
          r.length
            ? `${r.length} Artikel${r.length >= LIMIT ? " (Anzeige begrenzt, Filter eingrenzen)" : ""}`
            : filterAktiv
              ? "Keine Artikel für diese Auswahl. Bei Fahrzeugwahl: Zuordnungen stammen aus eigenen Einträgen oder Importen."
              : "Noch keine Artikel. Über „Daten importieren“ Beispieldaten laden oder eine Artikelliste hochladen, oder „Neuer Artikel“.",
        );
      })
      .catch((e: Error) => {
        if (mine === req.current) zeige(e.message, true);
      });
  }, [fahrzeug, gruppe, q, alle, version, zeige]);

  // Detail
  useEffect(() => {
    if (detailId === null) {
      setDetail(null);
      return;
    }
    let aktuell = true;
    api<ArtikelDetail>("/api/artikel/" + detailId)
      .then((d) => aktuell && setDetail(d))
      .catch((e: Error) => zeige(e.message, true));
    return () => {
      aktuell = false;
    };
  }, [detailId, version, zeige]);

  const neuLaden = () => setVersion((v) => v + 1);

  const nachImport = useCallback(() => {
    void ladeStats();
    void ladeGruppen();
    setVersion((v) => v + 1);
  }, [ladeStats, ladeGruppen]);

  function suchen(e: FormEvent) {
    e.preventDefault();
    setQ(eingabe.trim());
  }

  function aendern(artikelId: number) {
    void ladeStats();
    void ladeGruppen();
    setDetailId(artikelId);
    neuLaden();
  }

  const z = stats?.zahlen;
  const passtListe = detail ? rows.find((r) => r.id === detail.artikel.id)?.passt === 1 : false;

  return (
    <>
      <header className="top">
        <div className="brand">
          <span className="logo" aria-hidden="true" />
          <h1>WerkstattDatenBank</h1>
        </div>
        <form className="search" role="search" onSubmit={suchen}>
          <label className="sr" htmlFor="q">Suche nach Teilenummer, OE-Nummer, EAN oder Bezeichnung</label>
          <input
            id="q"
            type="search"
            placeholder="Teilenummer, OE-Nummer, EAN oder Bezeichnung"
            autoComplete="off"
            value={eingabe}
            onChange={(e) => setEingabe(e.target.value)}
          />
          <button type="submit">Suchen</button>
        </form>
        {stats?.schreiben && (
          <>
            <button type="button" className="ghost" onClick={() => setNeu(true)}>Neuer Artikel</button>
            <button type="button" className="ghost" onClick={() => setImportOffen(true)}>Daten importieren</button>
          </>
        )}
      </header>

      <div className="zahlen" aria-live="polite">
        {z &&
          (
            [
              ["Hersteller", z.hersteller],
              ["Modelle", z.modelle],
              ["Fahrzeugvarianten", z.fahrzeuge],
              ["Artikel", z.artikel],
              ["Zuordnungen", z.zuordnungen],
            ] as const
          ).map(([name, wert]) => (
            <span key={name}>
              <b>{wert.toLocaleString("de-DE")}</b> {name}
            </span>
          ))}
      </div>

      <main className="layout">
        <aside className="side" aria-label="Fahrzeug und Produktgruppen">
          <VehiclePicker fahrzeug={fahrzeug} onChange={setFahrzeug} onMeldung={zeige} neuLadenKey={version} />
          <GroupTree baum={baum} aktiv={gruppe?.id ?? null} onWaehle={(g) => setGruppe(g && (g.id === gruppe?.id ? null : { id: g.id, name: g.name }))} />
        </aside>

        <section className="main" aria-label="Ergebnisse">
          <div className="chips">
            {fahrzeug && <Chip text={fahrzeug.titel} onClose={() => setFahrzeug(null)} />}
            {gruppe && <Chip text={gruppe.name} onClose={() => setGruppe(null)} />}
            {q && (
              <Chip
                text={"Suche: " + q}
                onClose={() => {
                  setEingabe("");
                  setQ("");
                }}
              />
            )}
          </div>
          {fahrzeug && (
            <label className="check">
              <input type="checkbox" checked={alle} onChange={(e) => setAlle(e.target.checked)} /> Auch Artikel ohne
              Fahrzeugzuordnung zeigen
            </label>
          )}
          <p className={meldung.fehler ? "status fehler" : "status"} role="status">{meldung.text}</p>
          {geladen && (
            <ResultTable rows={rows} fahrzeugGewaehlt={!!fahrzeug} detailId={detailId} onOeffne={setDetailId} />
          )}
        </section>

        <DetailPanel
          detail={detail}
          fahrzeug={fahrzeug}
          schreiben={!!stats?.schreiben}
          passtListe={passtListe}
          onClose={() => setDetailId(null)}
          onGeaendert={aendern}
          onMeldung={zeige}
        />
      </main>

      <Footer quellen={stats?.quellen ?? []} />

      <ImportDialog
        offen={importOffen}
        onClose={() => setImportOffen(false)}
        onFertig={nachImport}
        demoVorhanden={!!stats?.quellen.some((q) => q.key === "demo")}
      />

      <NewArticleDialog
        offen={neu}
        baum={baum}
        fahrzeug={fahrzeug}
        onClose={() => setNeu(false)}
        onGespeichert={(id) => {
          setNeu(false);
          aendern(id);
        }}
      />
    </>
  );
}

function Chip({ text, onClose }: { text: string; onClose: () => void }) {
  return (
    <span className="chip">
      {text}
      <button type="button" aria-label={"Filter entfernen: " + text} onClick={onClose}>×</button>
    </span>
  );
}
