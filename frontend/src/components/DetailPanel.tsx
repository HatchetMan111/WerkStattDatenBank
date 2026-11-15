import { useState, type FormEvent } from "react";
import { api } from "../api";
import { eur, quelleName } from "../format";
import type { ArtikelDetail, FahrzeugAuswahl } from "../types";

interface Props {
  detail: ArtikelDetail | null;
  fahrzeug: FahrzeugAuswahl | null;
  schreiben: boolean;
  passtListe: boolean;
  onClose: () => void;
  onGeaendert: (artikelId: number) => void;
  onMeldung: (text: string, fehler?: boolean) => void;
}

const MAX_FZ = 40;

function Liste({ leer, children }: { leer: string; children: React.ReactNode[] }) {
  return children.length ? <ul>{children}</ul> : <p>{leer}</p>;
}

export default function DetailPanel({ detail, fahrzeug, schreiben, passtListe, onClose, onGeaendert, onMeldung }: Props) {
  const [auftrag, setAuftrag] = useState("");
  const [km, setKm] = useState("");
  const [notiz, setNotiz] = useState("");

  if (!detail) return <aside id="detail" className="detail" aria-label="Artikeldetail" hidden />;

  const a = detail.artikel;
  const passt = !!fahrzeug && (passtListe || detail.fahrzeuge.some((f) => f.id === fahrzeug.id));

  async function aktion(fn: () => Promise<unknown>) {
    try {
      await fn();
      onGeaendert(a.id);
    } catch (e) {
      onMeldung((e as Error).message, true);
    }
  }

  const zuordnen = () =>
    aktion(() => api("/api/fitment", { method: "POST", body: { artikel_id: a.id, fahrzeug_id: fahrzeug!.id } }));

  const entfernen = () => {
    if (!window.confirm("Zuordnung zu diesem Fahrzeug entfernen?")) return;
    void aktion(() => api(`/api/fitment?artikel_id=${a.id}&fahrzeug_id=${fahrzeug!.id}`, { method: "DELETE" }));
  };

  const buchen = (ev: FormEvent) => {
    ev.preventDefault();
    void aktion(async () => {
      await api("/api/verbaut", {
        method: "POST",
        body: { artikel_id: a.id, fahrzeug_id: fahrzeug ? fahrzeug.id : null, auftrag, km, notiz },
      });
      setAuftrag("");
      setKm("");
      setNotiz("");
    });
  };

  return (
    <aside id="detail" className="detail" aria-label="Artikeldetail">
      <button type="button" className="close" aria-label="Schließen" onClick={onClose}>×</button>
      <h2>{a.bezeichnung}</h2>
      <dl>
        <dt>Lieferant</dt><dd>{a.lieferant}</dd>
        <dt>Artikelnr.</dt><dd>{a.artikelnr}</dd>
        {a.ean && (<><dt>EAN</dt><dd>{a.ean}</dd></>)}
        <dt>Gruppe</dt><dd>{a.gruppe ?? "–"}</dd>
        <dt>Quelle</dt><dd>{quelleName(a.quelle)}</dd>
      </dl>

      <h3>OE-Nummern</h3>
      <Liste leer="Keine hinterlegt.">
        {detail.oe.map((o, i) => (<li key={i}>{(o.hersteller ? o.hersteller + ": " : "") + o.nummer}</li>))}
      </Liste>

      <h3>Einkaufspreise</h3>
      <Liste leer="Keine hinterlegt.">
        {detail.preise.map((p, i) => (
          <li key={i}>{`${eur.format(p.ek_netto)} netto${p.haendler ? " bei " + p.haendler : ""} (Stand ${p.stand})`}</li>
        ))}
      </Liste>

      <h3>{`Passt zu (${detail.fahrzeuge_gesamt})`}</h3>
      {detail.fahrzeuge.length ? (
        <ul>
          {detail.fahrzeuge.slice(0, MAX_FZ).map((f) => (<li key={f.id}>{`${f.hersteller} ${f.modell} · ${f.label}`}</li>))}
        </ul>
      ) : (
        <p>Noch keine Fahrzeugzuordnung.</p>
      )}
      {detail.fahrzeuge_gesamt > MAX_FZ && <p>{`… und ${detail.fahrzeuge_gesamt - MAX_FZ} weitere`}</p>}

      {schreiben && fahrzeug && (
        <div className="row">
          {passt ? (
            <button type="button" className="danger" onClick={entfernen}>Zuordnung entfernen</button>
          ) : (
            <button type="button" onClick={() => void zuordnen()}>Passt zum gewählten Fahrzeug</button>
          )}
        </div>
      )}

      <h3>Zuletzt verbaut</h3>
      <Liste leer="Noch nicht gebucht.">
        {detail.verbaut.map((v, i) => (
          <li key={i}>
            {[v.datum, v.auftrag, v.km != null ? v.km + " km" : null, v.notiz].filter(Boolean).join(" · ")}
          </li>
        ))}
      </Liste>

      {schreiben && (
        <form className="inline" onSubmit={buchen}>
          <input value={auftrag} onChange={(e) => setAuftrag(e.target.value)} placeholder="Auftragsnummer (keine Kundendaten)" maxLength={60} aria-label="Auftragsnummer" />
          <input value={km} onChange={(e) => setKm(e.target.value)} placeholder="Kilometerstand" inputMode="numeric" aria-label="Kilometerstand" />
          <input value={notiz} onChange={(e) => setNotiz(e.target.value)} placeholder="Notiz" maxLength={300} aria-label="Notiz" />
          <button type="submit">{"Als verbaut buchen" + (fahrzeug ? " (gewähltes Fahrzeug)" : "")}</button>
        </form>
      )}
    </aside>
  );
}
