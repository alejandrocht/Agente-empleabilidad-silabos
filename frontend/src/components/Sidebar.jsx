import { Plus, Search, Trash2, X } from "lucide-react";
import { useMemo, useState } from "react";

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
}) {
  const [busqueda, setBusqueda] = useState("");

  const crear = () => {
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

  const filtradas = useMemo(() => {
    const termino = busqueda.trim().toLowerCase();
    if (!termino) return estado.conversaciones;
    return estado.conversaciones.filter((conv) => conv.titulo.toLowerCase().includes(termino));
  }, [estado.conversaciones, busqueda]);

  const grupos = useMemo(() => agruparPorFecha(filtradas), [filtradas]);

  return (
    <aside
      className={`fixed inset-y-0 left-0 z-50 flex w-[min(20rem,88vw)] shrink-0 flex-col overflow-hidden whitespace-nowrap border-r border-line bg-ash px-4 py-4 shadow-2xl transition-all duration-300 lg:static lg:z-auto lg:translate-x-0 lg:shadow-none ${
        abierto ? "translate-x-0" : "-translate-x-full"
      } ${visible ? "lg:w-[17.5rem] lg:px-4" : "lg:w-0 lg:border-r-0 lg:px-0"}`}
    >
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
        <button type="button" onClick={onCerrar} className="icon-button lg:hidden" aria-label="Cerrar menú">
          <X size={18} />
        </button>
      </div>

      <label className="mt-4 flex items-center gap-2 rounded-[10px] border border-line bg-paper px-3 py-2 text-sm text-muted focus-within:border-ulima/50">
        <Search size={14} className="shrink-0" />
        <input
          type="text"
          value={busqueda}
          onChange={(event) => setBusqueda(event.target.value)}
          placeholder="Buscar conversaciones…"
          className="w-full min-w-0 bg-transparent text-ink outline-none placeholder:text-muted"
          aria-label="Buscar conversaciones"
        />
      </label>

      <button
        type="button"
        onClick={crear}
        className="mt-2.5 flex h-10 w-full items-center justify-center gap-2 rounded-[10px] bg-ulima px-4 text-sm font-bold text-white transition hover:-translate-y-px hover:shadow-[0_6px_18px_rgba(242,106,33,0.35)] focus:outline-none focus:ring-2 focus:ring-ulima/40"
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
    </aside>
  );
}
