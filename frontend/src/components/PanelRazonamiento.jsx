import { Check, ChevronDown, Clipboard, Hexagon, ShieldAlert } from "lucide-react";
import { useState } from "react";

const COLOR_LABEL = {
  empresa: "#3D7A9E",
  herramienta: "#2E8C7F",
  puesto: "#8A6FB8",
  carrera: "#FF5117",
  curso: "#FF5117",
  oferta: "#7A6F66",
};

function colorDeLabel(label) {
  return COLOR_LABEL[String(label ?? "").toLowerCase()] ?? "#7A6F66";
}

const TOKEN_CYPHER =
  /('[^']*'|"[^"]*"|\b(?:OPTIONAL MATCH|ORDER BY|MATCH|RETURN|WHERE|WITH|DESC|ASC|LIMIT|SKIP|AS|AND|OR|NOT|IN|DISTINCT|UNWIND|COUNT|EXISTS|CONTAINS|NULL)\b|:[A-Za-z_][A-Za-z0-9_]*|\b\d+(?:\.\d+)?\b)/gi;

function claseDeToken(token) {
  if (/^['"]/.test(token) || /^\d/.test(token)) return "text-nodo-empresa";
  if (token.startsWith(":")) return "text-nodo-herramienta";
  return "font-semibold text-[#D9410C]";
}

function resaltarCypher(cypher) {
  return cypher.split(TOKEN_CYPHER).map((parte, index) =>
    index % 2 === 1 ? (
      <span key={index} className={claseDeToken(parte)}>
        {parte}
      </span>
    ) : (
      parte
    ),
  );
}

export default function PanelRazonamiento({ pasos = [], cypher, entidades, error, errorRed }) {
  const [abierto, setAbierto] = useState(false);
  const [copiado, setCopiado] = useState(false);
  const tieneDetalle = cypher || entidades.length > 0 || error || errorRed || pasos.length > 0;

  if (!tieneDetalle) return null;

  const copiar = async () => {
    if (!cypher) return;
    await navigator.clipboard?.writeText(cypher);
    setCopiado(true);
    setTimeout(() => setCopiado(false), 1400);
  };

  return (
    <div className="mt-4 overflow-hidden rounded-[14px] border border-line bg-paper">
      <button
        type="button"
        onClick={() => setAbierto((valor) => !valor)}
        aria-expanded={abierto}
        className="flex w-full items-center justify-between px-4 py-2.5 text-[11px] font-bold uppercase tracking-[0.1em] text-muted transition hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-ulima/30"
      >
        <span className="flex items-center gap-2">
          <Hexagon size={13} />
          Traza del grafo{pasos.length > 0 ? ` · ${pasos.length} pasos` : ""}
        </span>
        <ChevronDown size={15} className={`transition ${abierto ? "rotate-180" : ""}`} aria-hidden="true" />
      </button>

      {abierto ? (
        <div className="border-t border-line px-4 pb-4 pt-1 sm:px-5">
          {error ? (
            <div className="mt-3 flex gap-2 rounded-[10px] bg-red-50 px-4 py-3 text-sm font-semibold text-red-700">
              <ShieldAlert size={18} className="shrink-0" />
              Consulta no permitida. El agente conserva la política de solo lectura.
            </div>
          ) : null}

          {pasos.length > 0 ? (
            <div>
              <p className="mb-2.5 mt-4 text-[10.5px] font-bold uppercase tracking-[0.14em] text-muted">
                Ruta ejecutada
              </p>
              <ol className="relative ml-1.5 border-l-2 border-line pl-6">
                {pasos.map((paso, index) => (
                  <li key={`${paso}-${index}`} className="relative pb-3.5 text-[13.5px] last:pb-0.5">
                    <span
                      className="absolute -left-[31px] top-1 h-3 w-3 rounded-full border-[2.5px] border-ulima bg-paper"
                      aria-hidden="true"
                    />
                    <span className="font-semibold text-ink">{paso}</span>
                  </li>
                ))}
              </ol>
            </div>
          ) : null}

          {cypher ? (
            <div>
              <div className="mb-2 mt-4 flex items-center justify-between gap-3">
                <p className="text-[10.5px] font-bold uppercase tracking-[0.14em] text-muted">
                  Cypher generado
                </p>
                <button
                  type="button"
                  onClick={copiar}
                  className="inline-flex h-7 items-center gap-1 rounded-lg border border-line px-2.5 text-xs font-semibold text-muted transition hover:border-ulima hover:text-ink focus:outline-none focus:ring-2 focus:ring-ulima/40"
                >
                  {copiado ? <Check size={13} className="text-emerald-600" /> : <Clipboard size={13} />}
                  {copiado ? "Copiado" : "Copiar"}
                </button>
              </div>
              <pre className="overflow-x-auto rounded-[10px] border border-line bg-ash p-4 font-mono text-xs leading-[1.7] text-ink">
                <code>{resaltarCypher(cypher)}</code>
              </pre>
            </div>
          ) : null}

          {entidades.length > 0 ? (
            <div>
              <p className="mb-2 mt-4 text-[10.5px] font-bold uppercase tracking-[0.14em] text-muted">
                Entidades resueltas
              </p>
              <div className="flex flex-wrap gap-1.5">
                {entidades.map((entidad, index) => (
                  <span
                    key={`${entidad.id ?? entidad.nombre ?? index}`}
                    className="inline-flex items-center gap-1.5 rounded-full border border-line bg-paper py-1 pl-2 pr-3 text-xs font-semibold text-ink"
                  >
                    <span
                      className="h-2 w-2 rounded-[3px]"
                      style={{ background: colorDeLabel(entidad.label) }}
                      aria-hidden="true"
                    />
                    <span className="text-[10px] font-bold uppercase tracking-wide text-muted">
                      {entidad.label ?? "Entidad"}
                    </span>
                    {entidad.nombre ?? entidad.texto ?? entidad.id}
                  </span>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
