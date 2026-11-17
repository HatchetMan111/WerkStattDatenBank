import { useEffect, useState } from "react";
import { api } from "../api";
import { quelleName } from "../format";
import type { FahrzeugAuswahl, Hersteller, Modell, Variante } from "../types";

interface Props {
  fahrzeug: FahrzeugAuswahl | null;
  onChange: (f: FahrzeugAuswahl | null) => void;
  onMeldung: (text: string, fehler?: boolean) => void;
  /** Ändert sich nach einem Import → Herstellerliste neu laden. */
  neuLadenKey?: number;
}

/** Dreistufige Fahrzeugwahl: Hersteller → Modell → Variante. */
export default function VehiclePicker({ fahrzeug, onChange, onMeldung, neuLadenKey = 0 }: Props) {
  const [hersteller, setHersteller] = useState<Hersteller[] | null>(null);
  const [modelle, setModelle] = useState<Modell[]>([]);
  const [varianten, setVarianten] = useState<Variante[]>([]);
  const [hId, setHId] = useState("");
  const [mId, setMId] = useState("");
  const [vId, setVId] = useState("");

  useEffect(() => {
    api<Hersteller[]>("/api/hersteller")
      .then((hs) => {
        setHersteller(hs);
        if (!hs.length) {
          onMeldung("Noch keine Fahrzeugdaten. Über „Daten importieren“ (oben rechts) Beispieldaten laden oder EEA-Fahrzeugdaten importieren.");
        }
      })
      .catch((e: Error) => onMeldung(e.message, true));
    // beim Start und nach jedem Import
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [neuLadenKey]);

  // Auswahl von außen zurückgesetzt (Chip „×“) → Auswahlfelder leeren
  useEffect(() => {
    if (fahrzeug === null && vId !== "") {
      setHId("");
      setMId("");
      setVId("");
      setModelle([]);
      setVarianten([]);
    }
  }, [fahrzeug, vId]);

  async function waehleHersteller(id: string) {
    setHId(id);
    setMId("");
    setVId("");
    setVarianten([]);
    setModelle([]);
    onChange(null);
    if (!id) return;
    try {
      setModelle(await api<Modell[]>("/api/modelle?hersteller_id=" + encodeURIComponent(id)));
    } catch (e) {
      onMeldung((e as Error).message, true);
    }
  }

  async function waehleModell(id: string) {
    setMId(id);
    setVId("");
    setVarianten([]);
    onChange(null);
    if (!id) return;
    try {
      setVarianten(await api<Variante[]>("/api/fahrzeuge?modell_id=" + encodeURIComponent(id)));
    } catch (e) {
      onMeldung((e as Error).message, true);
    }
  }

  function waehleVariante(id: string) {
    setVId(id);
    const v = varianten.find((x) => String(x.id) === id);
    const h = hersteller?.find((x) => String(x.id) === hId);
    const m = modelle.find((x) => String(x.id) === mId);
    onChange(v && h && m ? { id: v.id, label: v.label, titel: `${h.name} ${m.name} · ${v.label}` } : null);
  }

  function zuruecksetzen() {
    setHId("");
    setMId("");
    setVId("");
    setModelle([]);
    setVarianten([]);
    onChange(null);
  }

  return (
    <section className="card">
      <h2>1. Fahrzeug</h2>
      <label htmlFor="selHersteller">Hersteller</label>
      <select
        id="selHersteller"
        value={hId}
        disabled={!hersteller?.length}
        onChange={(e) => void waehleHersteller(e.target.value)}
      >
        <option value="">
          {hersteller === null ? "Lade…" : hersteller.length ? "Hersteller wählen…" : "Noch keine Fahrzeugdaten"}
        </option>
        {hersteller?.map((h) => (
          <option key={h.id} value={h.id}>{h.name}</option>
        ))}
      </select>

      <label htmlFor="selModell">Modell</label>
      <select id="selModell" value={mId} disabled={!modelle.length} onChange={(e) => void waehleModell(e.target.value)}>
        <option value="">{modelle.length ? "Modell wählen…" : "Erst Hersteller wählen"}</option>
        {modelle.map((m) => (
          <option key={m.id} value={m.id}>{`${m.name} (${m.varianten})`}</option>
        ))}
      </select>

      <label htmlFor="selFahrzeug">Variante</label>
      <select id="selFahrzeug" value={vId} disabled={!varianten.length} onChange={(e) => waehleVariante(e.target.value)}>
        <option value="">{varianten.length ? "Variante wählen…" : "Erst Modell wählen"}</option>
        {varianten.map((v) => (
          <option key={v.id} value={v.id}>{`${v.label} [${quelleName(v.quelle)}]`}</option>
        ))}
      </select>

      {fahrzeug && (
        <button type="button" className="link" onClick={zuruecksetzen}>
          Fahrzeug zurücksetzen
        </button>
      )}
    </section>
  );
}
