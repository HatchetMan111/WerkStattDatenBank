export const eur = new Intl.NumberFormat("de-DE", { style: "currency", currency: "EUR" });

export const QUELLE: Record<string, string> = { eea: "EEA", demo: "Demo", manuell: "eigen", csv: "CSV" };
export const quelleName = (k: string): string => QUELLE[k] ?? k;
