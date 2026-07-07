import { Clipboard, ShieldAlert } from "lucide-react";
import { useState } from "react";

export default function PanelRazonamiento({ cypher, entidades, error, errorRed }) {
  const [abierto, setAbierto] = useState(false);
  const [copiado, setCopiado] = useState(false);
  const tieneDetalle = cypher || entidades.length > 0 || error || errorRed;

  if (!tieneDetalle) return null;

  const copiar = async () => {
    if (!cypher) return;
    await navigator.clipboard?.writeText(cypher);
    setCopiado(true);
    setTimeout(() => setCopiado(false), 1400);
  };

  return (
    <div className="mt-4 border-t border-line pt-4">
      <button
        type="button"
        onClick={() => setAbierto((valor) => !valor)}
        className="font-mono text-xs font-semibold uppercase tracking-[0.18em] text-ulima transition hover:text-orange-700 focus:outline-none focus:ring-2 focus:ring-ulima/40"
      >
        {abierto ? "Ocultar razonamiento" : "Ver razonamiento del agente"}
      </button>

      {abierto ? (
        <div className="mt-4 space-y-4">
          {error ? (
            <div className="flex gap-2 rounded-xl bg-red-50 px-4 py-3 text-sm font-semibold text-red-700">
              <ShieldAlert size={18} />
              Consulta no permitida. El agente conserva la politica de solo lectura.
            </div>
          ) : null}

          {cypher ? (
            <div>
              <div className="mb-2 flex items-center justify-between gap-3">
                <p className="font-mono text-xs uppercase tracking-[0.16em] text-muted">
                  Cypher generado
                </p>
                <button
                  type="button"
                  onClick={copiar}
                  className="inline-flex items-center gap-1 rounded-full border border-line px-3 py-1 text-xs font-semibold transition hover:border-ulima focus:outline-none focus:ring-2 focus:ring-ulima/40"
                >
                  <Clipboard size={13} />
                  {copiado ? "Copiado" : "Copiar"}
                </button>
              </div>
              <pre className="overflow-x-auto rounded-2xl bg-[#0c1510] p-4 font-mono text-sm leading-relaxed text-emerald-300">
                <code>{cypher}</code>
              </pre>
            </div>
          ) : null}

          {entidades.length > 0 ? (
            <div>
                <p className="mb-2 font-mono text-xs uppercase tracking-[0.16em] text-muted">
                  Entidades resueltas
                </p>
              <div className="flex flex-wrap gap-2">
                {entidades.map((entidad, index) => (
                  <span
                    key={`${entidad.id ?? entidad.nombre ?? index}`}
                    className="rounded-full bg-orange-50 px-3 py-1 text-sm font-semibold text-ink"
                  >
                    {entidad.label ?? "Entidad"} · {entidad.nombre ?? entidad.texto ?? entidad.id}
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
