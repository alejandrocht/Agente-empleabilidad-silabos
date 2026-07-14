import { Check, ChevronDown, Clipboard, Code2, Route, ShieldAlert } from "lucide-react";
import { useState } from "react";

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
    <div className="mt-4 border-t border-line/80 pt-3">
      <button
        type="button"
        onClick={() => setAbierto((valor) => !valor)}
        aria-expanded={abierto}
        className="inline-flex h-9 items-center gap-2 rounded-lg px-2.5 text-xs font-semibold text-muted transition hover:bg-ash hover:text-ink focus:outline-none focus:ring-2 focus:ring-ulima/30"
      >
        <Code2 size={14} />
        Detalles técnicos
        <ChevronDown
          size={15}
          className={`transition ${abierto ? "rotate-180" : ""}`}
          aria-hidden="true"
        />
      </button>

      {abierto ? (
        <div className="mt-3 space-y-4 rounded-xl bg-ash/80 p-3.5 sm:p-4">
          {error ? (
            <div className="flex gap-2 rounded-lg bg-red-50 px-4 py-3 text-sm font-semibold text-red-700">
              <ShieldAlert size={18} />
              Consulta no permitida. El agente conserva la política de solo lectura.
            </div>
          ) : null}

          {pasos.length > 0 ? (
            <div>
              <p className="mb-2 flex items-center gap-1.5 font-mono text-xs font-semibold text-muted">
                <Route size={13} /> Ruta ejecutada
              </p>
              <div className="flex flex-wrap gap-2">
                {pasos.map((paso, index) => (
                  <span
                    key={`${paso}-${index}`}
                    className="rounded-full border border-orange-100 bg-orange-50 px-2.5 py-1 text-[11px] font-semibold text-ink"
                  >
                    {paso}
                  </span>
                ))}
              </div>
            </div>
          ) : null}

          {cypher ? (
            <div>
              <div className="mb-2 flex items-center justify-between gap-3">
                <p className="font-mono text-xs font-semibold text-muted">Cypher generado</p>
                <button
                  type="button"
                  onClick={copiar}
                  className="inline-flex h-8 items-center gap-1 rounded-lg border border-line px-3 text-xs font-semibold transition hover:border-ulima focus:outline-none focus:ring-2 focus:ring-ulima/40"
                >
                  {copiado ? <Check size={13} className="text-emerald-600" /> : <Clipboard size={13} />}
                  {copiado ? "Copiado" : "Copiar"}
                </button>
              </div>
              <pre className="overflow-x-auto rounded-xl bg-[#142019] p-4 font-mono text-xs leading-relaxed text-emerald-200 sm:text-sm">
                <code>{cypher}</code>
              </pre>
            </div>
          ) : null}

          {entidades.length > 0 ? (
            <div>
              <p className="mb-2 font-mono text-xs font-semibold text-muted">Entidades resueltas</p>
              <div className="flex flex-wrap gap-2">
                {entidades.map((entidad, index) => (
                  <span
                    key={`${entidad.id ?? entidad.nombre ?? index}`}
                    className="rounded-full bg-orange-50 px-3 py-1 text-sm font-semibold text-ink"
                  >
                    {entidad.label ?? "Entidad"} - {entidad.nombre ?? entidad.texto ?? entidad.id}
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
