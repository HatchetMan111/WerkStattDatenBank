import type { Gruppe } from "../types";

interface Props {
  baum: Gruppe[];
  aktiv: number | null;
  onWaehle: (g: Gruppe | null) => void;
}

interface KnotenProps {
  nodes: Gruppe[];
  aktiv: number | null;
  onWaehle: (g: Gruppe | null) => void;
}

function Knoten({ nodes, aktiv, onWaehle }: KnotenProps) {
  return (
    <ul>
      {nodes.map((n) => {
        const klasse = aktiv === n.id ? "aktiv" : undefined;
        const text = (
          <>
            {n.name} <span className="n">({n.anzahl})</span>
          </>
        );
        return (
          <li key={n.id}>
            {n.children.length ? (
              <details>
                <summary className={klasse} data-gid={n.id} onClick={() => onWaehle(n)}>
                  {text}
                </summary>
                <Knoten nodes={n.children} aktiv={aktiv} onWaehle={onWaehle} />
              </details>
            ) : (
              <button
                type="button"
                className={klasse ? `leaf ${klasse}` : "leaf"}
                data-gid={n.id}
                onClick={() => onWaehle(n)}
              >
                {text}
              </button>
            )}
          </li>
        );
      })}
    </ul>
  );
}

export default function GroupTree({ baum, aktiv, onWaehle }: Props) {
  return (
    <section className="card">
      <h2>2. Produktgruppe</h2>
      <div className="tree">
        <Knoten nodes={baum} aktiv={aktiv} onWaehle={onWaehle} />
      </div>
    </section>
  );
}
