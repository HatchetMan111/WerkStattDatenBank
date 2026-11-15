import { eur } from "../format";
import type { ArtikelRow } from "../types";

interface Props {
  rows: ArtikelRow[];
  fahrzeugGewaehlt: boolean;
  detailId: number | null;
  onOeffne: (id: number) => void;
}

export default function ResultTable({ rows, fahrzeugGewaehlt, detailId, onOeffne }: Props) {
  return (
    <div className="tablewrap">
      <table id="tabelle">
        <thead>
          <tr>
            <th>Lieferant</th>
            <th>Artikelnr.</th>
            <th>Bezeichnung</th>
            <th>Gruppe</th>
            <th className="num">EK netto</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} className={r.id === detailId ? "sel" : undefined}>
              <td>{r.lieferant}</td>
              <td>
                <button type="button" className="nr" onClick={() => onOeffne(r.id)}>
                  {r.artikelnr}
                </button>
                {fahrzeugGewaehlt && (
                  <span className={r.passt ? "badge" : "badge grau"}>{r.passt ? "passt" : "ungeprüft"}</span>
                )}
              </td>
              <td>{r.bezeichnung}</td>
              <td>{r.gruppe ?? "–"}</td>
              <td className="num">{r.ek_min != null ? eur.format(r.ek_min) : "–"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
