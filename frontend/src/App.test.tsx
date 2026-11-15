/**
 * Oberflächentest: Fahrzeugwahl → Filter → Suche → Detail → Zuordnung → neuer Artikel.
 *
 * Standard: Die API wird durch feste Testdaten ersetzt (läuft überall, ohne Server).
 * Gegen ein echtes Backend (mit `init_db.py --demo`):  WDB_E2E_BASE=http://127.0.0.1:8080 npm test
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

const BASE = process.env.WDB_E2E_BASE ?? "";

const ARTIKEL: { id: number; lieferant: string; artikelnr: string; bezeichnung: string; quelle: string; gruppe: string | null; ek_min: number | null }[] = [
  { id: 1, lieferant: "Demo-Teile", artikelnr: "DEMO-BB-1000", bezeichnung: "Bremsbelagsatz Vorderachse (Demo)", quelle: "demo", gruppe: "Bremsbeläge", ek_min: 24.9 },
  { id: 2, lieferant: "Demo-Teile", artikelnr: "DEMO-BS-2000", bezeichnung: "Bremsscheibe belüftet, Satz (Demo)", quelle: "demo", gruppe: "Bremsscheiben", ek_min: null },
  { id: 3, lieferant: "Demo-Teile", artikelnr: "DEMO-OF-3000", bezeichnung: "Ölfilter (Demo)", quelle: "demo", gruppe: "Ölfilter", ek_min: 4.5 },
];

function fixtureFetch(): typeof fetch {
  const passt = new Set<string>(["1:1", "3:1"]); // artikel:fahrzeug
  const json = (data: unknown, status = 200) =>
    Promise.resolve(new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } }));

  return vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), "http://x");
    const m = init?.method ?? "GET";
    const p = url.pathname;
    const sp = url.searchParams;
    if (p === "/api/stats") {
      return json({
        zahlen: { hersteller: 1, modelle: 1, fahrzeuge: 3, artikel: ARTIKEL.length, zuordnungen: passt.size },
        quellen: [{ key: "demo", name: "Demo-Daten", url: null, lizenz: "frei", stand: "2026-01", eintraege: 3 }],
        schreiben: true,
        token_noetig: false,
      });
    }
    if (p === "/api/hersteller") return json([{ id: 1, name: "Musterwagen (Demo)" }]);
    if (p === "/api/modelle") return json([{ id: 1, name: "Muster 1", varianten: 3 }]);
    if (p === "/api/fahrzeuge") {
      return json([{ id: 1, label: "Benzin 1197 ccm 81 kW", quelle: "demo", kraftstoff: "Benzin", hubraum_ccm: 1197, leistung_kw: 81 }]);
    }
    if (p === "/api/gruppen") {
      return json([
        { id: 1, name: "Bremsen", anzahl: 2, children: [{ id: 2, name: "Bremsbeläge", anzahl: 1, children: [] }] },
        { id: 8, name: "Ölfilter", anzahl: 1, children: [] },
      ]);
    }
    if (p === "/api/artikel" && m === "GET") {
      const fz = sp.get("fahrzeug_id");
      const q = (sp.get("q") ?? "").toLowerCase();
      const strikt = sp.get("strikt") !== "0";
      let r = ARTIKEL.map((a) => ({ ...a, passt: fz && passt.has(`${a.id}:${fz}`) ? 1 : 0 }));
      if (fz && strikt) r = r.filter((a) => a.passt);
      if (sp.get("gruppe_id") === "8") r = r.filter((a) => a.id === 3);
      if (q) r = r.filter((a) => (a.bezeichnung + a.artikelnr).toLowerCase().includes(q));
      return json(r);
    }
    const d = p.match(/^\/api\/artikel\/(\d+)$/);
    if (d) {
      const a = ARTIKEL.find((x) => x.id === Number(d[1]))!;
      const fahrzeuge = [...passt].filter((k) => k.startsWith(`${a.id}:`)).map(() => ({
        id: 1, hersteller: "Musterwagen (Demo)", modell: "Muster 1", label: "Benzin 1197 ccm 81 kW", bemerkung: null,
      }));
      return json({
        artikel: { ...a, ean: null },
        oe: [{ hersteller: "Musterwagen", nummer: "OE-DEMO-1" }],
        preise: a.ek_min ? [{ haendler: "Demo", ek_netto: a.ek_min, waehrung: "EUR", stand: "2026-01-01" }] : [],
        fahrzeuge,
        fahrzeuge_gesamt: fahrzeuge.length,
        verbaut: [],
      });
    }
    if (p === "/api/fitment" && m === "POST") {
      const b = JSON.parse(String(init?.body)) as { artikel_id: number; fahrzeug_id: number };
      passt.add(`${b.artikel_id}:${b.fahrzeug_id}`);
      return json({ ok: true });
    }
    if (p === "/api/artikel" && m === "POST") {
      const b = JSON.parse(String(init?.body)) as { lieferant: string; artikelnr: string; bezeichnung: string };
      ARTIKEL.push({ id: 4, lieferant: b.lieferant, artikelnr: b.artikelnr, bezeichnung: b.bezeichnung, quelle: "manuell", gruppe: null, ek_min: null });
      return json({ id: 4 }, 201);
    }
    return json({ fehler: `unbekannt: ${m} ${p}` }, 404);
  }) as unknown as typeof fetch;
}

const zeilen = () => within(screen.getByRole("table")).getAllByRole("row").slice(1);
const nummern = () => zeilen().map((r) => within(r).getAllByRole("cell")[1].textContent ?? "");

beforeEach(() => {
  if (BASE) {
    const echt = globalThis.fetch;
    vi.stubGlobal("fetch", (u: RequestInfo | URL, o?: RequestInit) => echt(new URL(String(u), BASE), o));
  } else {
    vi.stubGlobal("fetch", fixtureFetch());
  }
  HTMLDialogElement.prototype.showModal = function (this: HTMLDialogElement) {
    this.setAttribute("open", "");
  };
  HTMLDialogElement.prototype.close = function (this: HTMLDialogElement) {
    this.removeAttribute("open");
    this.dispatchEvent(new Event("close"));
  };
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("WerkstattDatenBank", () => {
  it("zeigt Kennzahlen, Gruppen und alle Artikel ohne Filter", async () => {
    render(<App />);
    await waitFor(() => expect(zeilen().length).toBeGreaterThanOrEqual(3));
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("WerkstattDatenBank");
    expect(await screen.findByText("Datenquellen")).toBeTruthy();
    expect(screen.getByText("Ölfilter", { selector: "button" })).toBeTruthy();
  });

  it("Fahrzeugwahl filtert, Haken zeigt alle, Detail + Zuordnung funktionieren", async () => {
    render(<App />);
    await waitFor(() => expect(zeilen().length).toBeGreaterThanOrEqual(3));

    const hersteller = (await screen.findByLabelText("Hersteller")) as HTMLSelectElement;
    await waitFor(() => expect(hersteller.options.length).toBeGreaterThan(1));
    fireEvent.change(hersteller, { target: { value: hersteller.options[1].value } });

    const modell = screen.getByLabelText("Modell") as HTMLSelectElement;
    await waitFor(() => expect(modell.options.length).toBeGreaterThan(1));
    fireEvent.change(modell, { target: { value: modell.options[1].value } });

    const variante = screen.getByLabelText("Variante") as HTMLSelectElement;
    await waitFor(() => expect(variante.options.length).toBeGreaterThan(1));
    fireEvent.change(variante, { target: { value: variante.options[1].value } });

    // Chip mit Fahrzeugtitel, nur passende Artikel
    await screen.findByRole("button", { name: /Filter entfernen: .*Muster 1/ });
    await waitFor(() => expect(document.querySelectorAll(".badge").length).toBeGreaterThan(0));
    expect(document.querySelectorAll(".badge.grau").length).toBe(0);

    // „Auch ohne Zuordnung zeigen“
    fireEvent.click(screen.getByLabelText(/Auch Artikel ohne Fahrzeugzuordnung/));
    await waitFor(() => expect(document.querySelectorAll(".badge.grau").length).toBeGreaterThan(0));

    // Detail eines nicht passenden Artikels öffnen → zuordnen
    const grau = document.querySelector(".badge.grau")!.parentElement!.querySelector("button.nr") as HTMLButtonElement;
    fireEvent.click(grau);
    const detail = await screen.findByLabelText("Artikeldetail");
    await within(detail).findByText("OE-Nummern");
    const btn = await within(detail).findByRole("button", { name: "Passt zum gewählten Fahrzeug" });
    fireEvent.click(btn);
    await within(detail).findByRole("button", { name: "Zuordnung entfernen" });

    // Fahrzeug zurücksetzen
    fireEvent.click(screen.getByRole("button", { name: "Fahrzeug zurücksetzen" }));
    await waitFor(() => expect(document.querySelectorAll(".badge").length).toBe(0));
  });

  it("Suche und Produktgruppe grenzen die Liste ein", async () => {
    render(<App />);
    await waitFor(() => expect(zeilen().length).toBeGreaterThanOrEqual(3));

    fireEvent.change(screen.getByLabelText(/Suche nach Teilenummer/), { target: { value: "scheibe" } });
    await waitFor(() => expect(nummern()).toEqual(["DEMO-BS-2000"]), { timeout: 3000 });
    fireEvent.click(screen.getByRole("button", { name: /Filter entfernen: Suche/ }));
    await waitFor(() => expect(zeilen().length).toBeGreaterThanOrEqual(3));

    fireEvent.click(screen.getByText("Ölfilter", { selector: "button" }));
    await waitFor(() => expect(nummern()).toEqual(["DEMO-OF-3000"]));
  });

  it("legt einen neuen Artikel an und öffnet dessen Detail", async () => {
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: "Neuer Artikel" }));
    const dlg = document.querySelector("dialog")!;
    expect(dlg.hasAttribute("open")).toBe(true);
    const nr = "TEST-" + Date.now();
    fireEvent.change(dlg.querySelector("input[name=lieferant]")!, { target: { value: "Testlieferant" } });
    fireEvent.change(dlg.querySelector("input[name=artikelnr]")!, { target: { value: nr } });
    fireEvent.change(dlg.querySelector("input[name=bezeichnung]")!, { target: { value: "Testteil" } });
    fireEvent.submit(dlg.querySelector("form")!);
    await waitFor(() => expect(dlg.hasAttribute("open")).toBe(false));
    const detail = await screen.findByLabelText("Artikeldetail");
    await within(detail).findByRole("heading", { name: "Testteil" });
  });
});
