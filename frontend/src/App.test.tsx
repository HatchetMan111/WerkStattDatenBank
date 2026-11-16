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
  let fahrzeugAnzahl = 3;
  let job: Record<string, unknown> = { id: 0, state: "leer", phase: "", fortschritt: 0, name: "", ergebnis: null, fehler: null, details: null };
  let abfragen = 0;
  let naechstesFehler = false;
  const gemerkt: { id: number; typ: string; name: string; url: string; letzter_lauf: string | null; ergebnis: string | null }[] = [];
  const json = (data: unknown, status = 200) =>
    Promise.resolve(new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } }));

  return vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), "http://x");
    const m = init?.method ?? "GET";
    const p = url.pathname;
    const sp = url.searchParams;
    if (p === "/api/stats") {
      return json({
        zahlen: { hersteller: 1, modelle: 1, fahrzeuge: fahrzeugAnzahl, artikel: ARTIKEL.length, zuordnungen: passt.size },
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
    if (p === "/api/import/quellen" && m === "GET") {
      return json({
        katalog: [{ key: "eea", typ: "eea", name: "EEA – CO2-Überwachung neuer Pkw (Fahrzeugdaten)", seite: "https://www.eea.europa.eu/x", lizenz: "CC BY 4.0", hinweis: "Download öffnen." }],
        gespeichert: gemerkt,
      });
    }
    if (p === "/api/import/status") {
      abfragen += 1;
      if (job.state === "laeuft" && abfragen >= 2) {
        if (naechstesFehler) job = { ...job, state: "fehler", phase: "Fehlgeschlagen", fehler: "Download fehlgeschlagen: HTTP 404", details: "Traceback (most recent call last): …" };
        else {
          fahrzeugAnzahl = 4200;
          job = { ...job, state: "fertig", phase: "Fertig", ergebnis: { typ: "eea", zeilen: 9000, in_datenbank: 4200 } };
        }
      }
      return json(job);
    }
    if (p === "/api/import/url" && m === "POST") {
      const b = JSON.parse(String(init?.body)) as { url: string; name: string; merken: boolean };
      naechstesFehler = b.url.includes("fehler");
      abfragen = 0;
      job = { id: Number(job.id) + 1, state: "laeuft", phase: "Herunterladen", fortschritt: 1048576, name: b.name || "Download", ergebnis: null, fehler: null, details: null };
      if (b.merken) gemerkt.push({ id: 1, typ: "eea", name: b.name, url: b.url, letzter_lauf: null, ergebnis: null });
      return json({ ok: true, job: job.id });
    }
    return json({ fehler: `unbekannt: ${m} ${p}` }, 404);
  }) as unknown as typeof fetch;
}

/** Ersatz für XMLHttpRequest (jsdom würde sonst ins Netz gehen): meldet Fortschritt und antwortet mit Job 1. */
class FakeXhr {
  static gesendet: { url: string; headers: Record<string, string>; groesse: number }[] = [];
  upload: { onprogress: ((e: { lengthComputable: boolean; loaded: number; total: number }) => void) | null } = { onprogress: null };
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  status = 200;
  responseText = '{"ok":true,"job":1}';
  private url = "";
  private headers: Record<string, string> = {};
  open(_m: string, url: string) { this.url = url; }
  setRequestHeader(k: string, v: string) { this.headers[k] = v; }
  send(f: File) {
    FakeXhr.gesendet.push({ url: this.url, headers: this.headers, groesse: f.size });
    this.upload.onprogress?.({ lengthComputable: true, loaded: f.size, total: f.size });
    setTimeout(() => this.onload?.(), 0);
  }
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
    const dlg = document.querySelector("dialog:not(.import)")!;
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

  describe.skipIf(!!BASE)("Daten importieren (Testdaten)", () => {
    async function oeffneImport() {
      fireEvent.click(await screen.findByRole("button", { name: "Daten importieren" }));
      await waitFor(() => expect(document.querySelector("dialog.import[open]")).toBeTruthy());
      return document.querySelector("dialog.import") as HTMLElement;
    }

    it("lädt von einer Adresse, merkt sie und aktualisiert die Zahlen", async () => {
      render(<App />);
      const dlg = await oeffneImport();
      await within(dlg).findByText(/EEA – CO2-Überwachung/);
      expect(within(dlg).getByRole("link", { name: "Download-Seite öffnen" }).getAttribute("rel")).toContain("noopener");
      fireEvent.change(within(dlg).getByLabelText(/Direkter Download-Link/), { target: { value: "https://example.org/eea.csv" } });
      fireEvent.change(within(dlg).getByLabelText("Name der Quelle"), { target: { value: "EEA 2024" } });
      fireEvent.click(within(dlg).getByRole("button", { name: "Laden und importieren" }));
      await within(dlg).findByText(/Fertig:/, {}, { timeout: 5000 });
      await within(dlg).findByText("Gemerkte Quellen");
      await waitFor(() => expect(document.querySelector(".zahlen")!.textContent).toContain("4.200"), { timeout: 3000 });
    });

    it("zeigt Fehler samt technischen Details", async () => {
      render(<App />);
      const dlg = await oeffneImport();
      fireEvent.change(within(dlg).getByLabelText(/Direkter Download-Link/), { target: { value: "https://example.org/fehler.csv" } });
      fireEvent.click(within(dlg).getByRole("button", { name: "Laden und importieren" }));
      await within(dlg).findByText(/HTTP 404/, {}, { timeout: 5000 });
      expect(within(dlg).getByText(/vollständige Fehlerkette/)).toBeTruthy();
    });

    it("lädt eine Datei hoch (mit Schutz-Header) und zeigt das Ergebnis", async () => {
      vi.stubGlobal("XMLHttpRequest", FakeXhr);
      FakeXhr.gesendet = [];
      render(<App />);
      const dlg = await oeffneImport();
      const input = within(dlg).getByLabelText(/CSV-Datei/) as HTMLInputElement;
      const datei = new File(["Mk;Cn\nBMW;320D\n"], "eea.csv", { type: "text/csv" });
      fireEvent.change(input, { target: { files: [datei] } });
      fireEvent.click(within(dlg).getByRole("button", { name: "Hochladen und importieren" }));
      await waitFor(() => expect(FakeXhr.gesendet.length).toBe(1));
      expect(FakeXhr.gesendet[0].headers["X-WDB-Upload"]).toBe("1");
      expect(FakeXhr.gesendet[0].url).toContain("typ=auto");
      expect(FakeXhr.gesendet[0].url).toContain("name=eea.csv");
    });
  });
});
