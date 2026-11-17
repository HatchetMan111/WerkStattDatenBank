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
                {q.key === "eea" &&
                  ". Daten aggregiert und in der Schreibweise angepasst; sie geben nicht notwendig die Meinung der EEA wieder, die EEA übernimmt keine Haftung"}
              </li>
            ))}
          </ul>
        </div>
      )}
      <p>
        © LichtValleyApps · Quellcode unter MIT-Lizenz · <a href="/third-party-licenses.txt" target="_blank" rel="noopener noreferrer">Lizenzen der verwendeten Bibliotheken</a>
      </p>
    </footer>
  );
}
