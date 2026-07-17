import { PanelLeft, Plus, SquarePen, Trash2, X } from "lucide-react";
import { useMemo } from "react";

function fechaCorta(timestamp) {
  return new Intl.DateTimeFormat("es-PE", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(timestamp);
}

function inicioDelDia(timestamp) {
  const fecha = new Date(timestamp);
  fecha.setHours(0, 0, 0, 0);
  return fecha.getTime();
}

function agruparPorFecha(conversaciones) {
  const hoy = inicioDelDia(Date.now());
  const ayer = hoy - 86400000;
  const grupos = { Hoy: [], Ayer: [], Anteriores: [] };

  for (const conv of conversaciones) {
    const dia = inicioDelDia(conv.actualizada);
    if (dia >= hoy) grupos.Hoy.push(conv);
    else if (dia >= ayer) grupos.Ayer.push(conv);
    else grupos.Anteriores.push(conv);
  }

  return Object.entries(grupos).filter(([, lista]) => lista.length > 0);
}

export default function Sidebar({
  estado,
  activa,
  nuevaConversacion,
  seleccionar,
  borrar,
  limpiar,
  abierto,
  visible,
  onCerrar,
  onAlternar,
}) {
  const activaVacia = !activa || activa.mensajes.length === 0;

  const crear = () => {
    if (activaVacia) return;
    nuevaConversacion();
    onCerrar();
  };

  const elegir = (id) => {
    seleccionar(id);
    onCerrar();
  };

  const confirmarBorrado = (conv) => {
    if (window.confirm(`¿Eliminar “${conv.titulo}”?`)) borrar(conv.id);
  };

  const confirmarLimpieza = () => {
    if (window.confirm("¿Eliminar todo el historial local?")) limpiar();
  };

  const grupos = useMemo(() => agruparPorFecha(estado.conversaciones), [estado.conversaciones]);

  return (
    <aside
      className={`fixed inset-y-0 left-0 z-50 flex w-[min(20rem,88vw)] shrink-0 flex-col overflow-hidden whitespace-nowrap border-r border-line bg-ash px-4 py-4 shadow-2xl transition-transform duration-300 lg:static lg:z-auto lg:translate-x-0 lg:shadow-none lg:[transition:width_.2s_ease-out,padding_.2s_ease-out] ${
        abierto ? "translate-x-0" : "-translate-x-full"
      } ${visible ? "lg:w-[17.5rem] lg:px-4" : "lg:w-16 lg:items-center lg:px-0"}`}
    >
      {/* Rail colapsado: solo escritorio cuando el sidebar está oculto */}
      <div className={`hidden flex-col items-center gap-1 ${visible ? "lg:hidden" : "lg:flex"}`}>
        <button
          type="button"
          onClick={onAlternar}
          className="group relative flex h-11 w-11 items-center justify-center rounded-xl transition hover:bg-paper"
          aria-label="Mostrar barra lateral"
          title="Mostrar barra lateral"
        >
          <img
            src="/logo-ulima.png"
            alt="Universidad de Lima"
            className="h-8 w-8 object-contain transition-opacity duration-150 group-hover:opacity-0"
          />
          <PanelLeft
            size={20}
            className="absolute text-ink opacity-0 transition-opacity duration-150 group-hover:opacity-100"
          />
        </button>
        <button
          type="button"
          onClick={crear}
          className="flex h-11 w-11 items-center justify-center rounded-xl text-ink transition hover:bg-paper focus:outline-none focus:ring-2 focus:ring-ulima/40"
          aria-label="Nueva conversación"
          aria-disabled={activaVacia}
          title={activaVacia ? "Ya estás en una conversación nueva" : "Nueva conversación"}
        >
          <SquarePen size={19} />
        </button>
      </div>

      {/* Panel expandido: móvil siempre; escritorio solo cuando visible */}
      <div className={`flex min-h-0 w-full flex-1 flex-col ${visible ? "lg:flex" : "lg:hidden"}`}>
      <div className="flex items-center justify-between gap-3 px-1">
        <div className="flex min-w-0 items-center gap-3">
          <img src="/logo-ulima.png" alt="Universidad de Lima" className="h-9 w-9 shrink-0 object-contain" />
          <div className="min-w-0">
            <p className="truncate text-[15px] font-extrabold tracking-tight">Agente CIAR</p>
            <p className="truncate text-[11px] font-semibold uppercase tracking-wider text-muted">
              Universidad de Lima
            </p>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <button
            type="button"
            onClick={onAlternar}
            className="icon-button hidden lg:inline-flex"
            aria-label="Ocultar barra lateral"
            title="Ocultar barra lateral"
          >
            <PanelLeft size={18} />
          </button>
          <button type="button" onClick={onCerrar} className="icon-button lg:hidden" aria-label="Cerrar menú">
            <X size={18} />
          </button>
        </div>
      </div>

      <button
        type="button"
        onClick={crear}
        className="mt-4 flex h-10 w-full items-center justify-center gap-2 rounded-[10px] bg-ulima px-4 text-sm font-bold text-white transition hover:-translate-y-px hover:shadow-[0_6px_18px_rgba(255,81,23,0.35)] focus:outline-none focus:ring-2 focus:ring-ulima/40"
      >
        <Plus size={16} strokeWidth={2.6} />
        Nueva conversación
      </button>

      <div className="min-h-0 flex-1 overflow-y-auto pr-1">
        {grupos.map(([nombre, lista]) => (
          <div key={nombre}>
            <p className="mb-1.5 mt-4 px-1 text-[10px] font-bold uppercase tracking-[0.16em] text-muted">
              {nombre}
            </p>
            <div className="space-y-0.5">
              {lista.map((conv) => {
                const seleccionada = conv.id === activa?.id;
                return (
                  <div
                    key={conv.id}
                    className={`group relative flex items-start gap-2 rounded-[10px] border p-2.5 transition ${
                      seleccionada
                        ? "border-ulima/30 bg-paper"
                        : "border-transparent hover:bg-paper"
                    }`}
                  >
                    {seleccionada ? (
                      <span className="absolute -left-px bottom-2 top-2 w-[3px] rounded-full bg-ulima" />
                    ) : null}
                    <button
                      type="button"
                      onClick={() => elegir(conv.id)}
                      className="min-w-0 flex-1 text-left focus:outline-none focus:ring-2 focus:ring-ulima/40"
                    >
                      <span className="block truncate text-[13px] font-semibold">{conv.titulo}</span>
                      <span className="mt-0.5 block truncate font-mono text-[11px] text-muted">
                        {fechaCorta(conv.actualizada)} · {conv.mensajes.length} mensajes
                      </span>
                    </button>
                    <button
                      type="button"
                      onClick={() => confirmarBorrado(conv)}
                      className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-muted opacity-0 transition hover:bg-ash hover:text-red-600 focus:opacity-100 focus:outline-none focus:ring-2 focus:ring-ulima/40 group-hover:opacity-100"
                      aria-label={`Borrar ${conv.titulo}`}
                      title="Borrar"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      <div className="mt-3 flex items-center justify-between border-t border-line pt-3">
        <button
          type="button"
          onClick={confirmarLimpieza}
          className="flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-xs font-semibold text-muted transition hover:text-red-600 focus:outline-none focus:ring-2 focus:ring-ulima/40"
        >
          <Trash2 size={13} />
          Limpiar historial
        </button>
        <span className="font-mono text-[11px] text-muted">v2.0</span>
      </div>
      </div>
    </aside>
  );
}
