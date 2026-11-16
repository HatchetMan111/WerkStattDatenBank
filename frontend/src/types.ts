export interface Quelle {
  key: string;
  name: string;
  url: string | null;
  lizenz: string | null;
  stand: string | null;
  eintraege: number | null;
}

export interface Stats {
  zahlen: { hersteller: number; modelle: number; fahrzeuge: number; artikel: number; zuordnungen: number };
  quellen: Quelle[];
  schreiben: boolean;
  token_noetig: boolean;
}

export interface Hersteller { id: number; name: string }
export interface Modell { id: number; name: string; varianten: number }

export interface Variante {
  id: number;
  label: string;
  quelle: string;
  kraftstoff: string;
  hubraum_ccm: number;
  leistung_kw: number;
}

export interface Gruppe { id: number; name: string; anzahl: number; children: Gruppe[] }

export interface ArtikelRow {
  id: number;
  lieferant: string;
  artikelnr: string;
  bezeichnung: string;
  quelle: string;
  gruppe: string | null;
  passt: number;
  ek_min: number | null;
}

export interface ArtikelDetail {
  artikel: {
    id: number;
    lieferant: string;
    artikelnr: string;
    bezeichnung: string;
    ean: string | null;
    quelle: string;
    gruppe: string | null;
  };
  oe: { hersteller: string; nummer: string }[];
  preise: { haendler: string; ek_netto: number; waehrung: string; stand: string }[];
  fahrzeuge: { id: number; hersteller: string; modell: string; label: string; bemerkung: string | null }[];
  fahrzeuge_gesamt: number;
  verbaut: { datum: string; auftrag: string | null; km: number | null; notiz: string | null }[];
}

/** Das gewählte Fahrzeug samt Anzeigetitel (Hersteller, Modell, Variante). */
export interface FahrzeugAuswahl { id: number; label: string; titel: string }

export interface KatalogQuelle {
  key: string;
  typ: string;
  name: string;
  seite: string;
  lizenz: string;
  hinweis: string;
}

export interface GemerkteQuelle {
  id: number;
  typ: string;
  name: string;
  url: string;
  letzter_lauf: string | null;
  ergebnis: string | null;
}

export interface ImportQuellen { katalog: KatalogQuelle[]; gespeichert: GemerkteQuelle[] }

export interface ImportStatus {
  id: number;
  state: "leer" | "laeuft" | "fertig" | "fehler";
  phase: string;
  fortschritt: number;
  name: string;
  ergebnis: Record<string, string | number> | null;
  fehler: string | null;
  details: string | null;
}
