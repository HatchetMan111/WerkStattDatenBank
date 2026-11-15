import type { Quelle } from "../types";

export default function Footer({ quellen }: { quellen: Quelle[] }) {
  return (
    <footer className="foot">
      <p>
        <strong>Hinweis:</strong> Der Datenbestand besteht aus öffentlichen Quellen und eigenen Einträgen. Er ersetzt keine
        Herstellerfreigabe. Vor der Bestellung Passgenauigkeit über Fahrgestellnummer und Teilenummer prüfen.
      </p>
      {quellen.length > 0 && (
        <div>
          <strong>Datenquellen</strong>
          <ul>
            {quellen.map((q) => (
              <li key={q.key}>
                {q.url && q.url.startsWith("https://") ? (
                  <a href={q.url} rel="noopener noreferrer" target="_blank">{q.name}</a>
                ) : (
                  q.name
                )}
                {q.lizenz ? " – " + q.lizenz : ""}
                {q.stand ? ` (Stand ${q.stand})` : ""}
              </li>
            ))}
          </ul>
        </div>
      )}
    </footer>
  );
}
