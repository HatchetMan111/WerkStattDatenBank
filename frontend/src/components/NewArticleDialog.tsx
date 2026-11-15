import { useEffect, useRef, useState, type FormEvent } from "react";
import { api } from "../api";
import type { FahrzeugAuswahl, Gruppe } from "../types";

interface Props {
  offen: boolean;
  baum: Gruppe[];
  fahrzeug: FahrzeugAuswahl | null;
  onClose: () => void;
  onGespeichert: (artikelId: number) => void;
}

function flach(nodes: Gruppe[], tiefe = 0): { id: number; name: string }[] {
  return nodes.flatMap((n) => [{ id: n.id, name: "  ".repeat(tiefe) + n.name }, ...flach(n.children, tiefe + 1)]);
}

function parseOe(text: string) {
  return text
    .split("\n")
    .map((z) => z.trim())
    .filter(Boolean)
    .map((z) => {
      const i = z.indexOf(":");
      return i > 0 ? { hersteller: z.slice(0, i).trim(), nummer: z.slice(i + 1).trim() } : { hersteller: "", nummer: z };
    });
}

export default function NewArticleDialog({ offen, baum, fahrzeug, onClose, onGespeichert }: Props) {
  const dlg = useRef<HTMLDialogElement>(null);
  const [fehler, setFehler] = useState("");

  useEffect(() => {
    const d = dlg.current;
    if (!d) return;
    if (offen && !d.open) {
      setFehler("");
      // jsdom kennt showModal teils nicht → Fallback auf das open-Attribut
      if (typeof d.showModal === "function") d.showModal();
      else d.setAttribute("open", "");
    } else if (!offen && d.open) {
      if (typeof d.close === "function") d.close();
      else d.removeAttribute("open");
    }
  }, [offen]);

  async function senden(ev: FormEvent<HTMLFormElement>) {
    ev.preventDefault();
    const form = ev.currentTarget;
    const f = new FormData(form);
    const s = (k: string) => String(f.get(k) ?? "");
    const body = {
      lieferant: s("lieferant"),
      artikelnr: s("artikelnr"),
      bezeichnung: s("bezeichnung"),
      produktgruppe_id: s("produktgruppe_id") || null,
      ean: s("ean"),
      oe: parseOe(s("oe")),
      ek_netto: s("ek_netto").replace(",", "."),
      haendler: s("haendler"),
      fahrzeug_ids: f.get("zuordnen") && fahrzeug ? [fahrzeug.id] : [],
    };
    try {
      const r = await api<{ id: number }>("/api/artikel", { method: "POST", body });
      form.reset();
      onGespeichert(r.id);
    } catch (e) {
      setFehler((e as Error).message);
    }
  }

  return (
    <dialog ref={dlg} aria-labelledby="dlgTitel" onClose={onClose}>
      <form onSubmit={(e) => void senden(e)}>
        <h2 id="dlgTitel">Neuer Artikel</h2>
        <div className="grid2">
          <label>Lieferant<input name="lieferant" required maxLength={80} /></label>
          <label>Artikelnummer<input name="artikelnr" required maxLength={60} /></label>
        </div>
        <label>Bezeichnung<input name="bezeichnung" required maxLength={200} /></label>
        <div className="grid2">
          <label>
            Produktgruppe
            <select name="produktgruppe_id" defaultValue="">
              <option value="">Keine Gruppe</option>
              {flach(baum).map((g) => (<option key={g.id} value={g.id}>{g.name}</option>))}
            </select>
          </label>
          <label>EAN<input name="ean" maxLength={20} inputMode="numeric" /></label>
        </div>
        <label>
          OE-Nummern (eine pro Zeile, Format: Hersteller:Nummer)
          <textarea name="oe" rows={3} placeholder="Musterwagen:OE-DEMO-1" />
        </label>
        <div className="grid2">
          <label>EK netto (EUR)<input name="ek_netto" inputMode="decimal" /></label>
          <label>Händler<input name="haendler" maxLength={80} /></label>
        </div>
        {fahrzeug && (
          <label className="check">
            <input type="checkbox" name="zuordnen" /> <span>{"Dem gewählten Fahrzeug zuordnen: " + fahrzeug.titel}</span>
          </label>
        )}
        <p className="fehler" role="alert">{fehler}</p>
        <div className="actions">
          <button type="button" className="ghost" onClick={onClose}>Abbrechen</button>
          <button type="submit">Speichern</button>
        </div>
      </form>
    </dialog>
  );
}
