import { MessageSquare, MessageSquarePlus, Trash2, X } from "lucide-react";
import BotAvatar from "./BotAvatar";

function fechaCorta(timestamp) {
  return new Intl.DateTimeFormat("es-PE", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(timestamp);
}

export default function Sidebar({
  estado,
  activa,
  nuevaConversacion,
  seleccionar,
  borrar,
  limpiar,
  abierto,
  onCerrar,
}) {
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

  return (
    <aside
      className={`fixed inset-y-0 left-0 z-50 flex w-[min(20rem,88vw)] shrink-0 flex-col border-r border-line bg-white px-4 py-4 shadow-2xl transition-transform duration-300 lg:static lg:z-auto lg:w-[19rem] lg:translate-x-0 lg:px-5 lg:shadow-none ${
        abierto ? "translate-x-0" : "-translate-x-full"
      }`}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <BotAvatar size="lg" />
          <div className="min-w-0">
            <p className="truncate text-lg font-extrabold tracking-tight">Agente CIAR</p>
            <p className="text-xs text-muted">Universidad de Lima</p>
          </div>
        </div>
        {estado.conversaciones.length > 0 ? (
          <span className="rounded-full bg-orange-50 px-2.5 py-1 text-xs font-semibold text-ulima">
            {estado.conversaciones.length}
          </span>
        ) : null}
        <button type="button" onClick={onCerrar} className="icon-button lg:hidden" aria-label="Cerrar menú">
          <X size={18} />
        </button>
      </div>

      <button
        type="button"
        onClick={crear}
        className="mt-5 flex h-11 w-full items-center justify-center gap-2 rounded-xl bg-ulima px-4 font-semibold text-white shadow-sm transition hover:-translate-y-0.5 hover:bg-orange-600 hover:shadow-md focus:outline-none focus:ring-2 focus:ring-ulima/40"
      >
        <MessageSquarePlus size={18} />
        Nueva conversación
      </button>

      <div className="mb-2 mt-6 flex items-center justify-between px-1">
        <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-muted">Conversaciones</p>
        <MessageSquare size={14} className="text-muted" />
      </div>

      <div className="min-h-0 flex-1 space-y-1.5 overflow-y-auto pr-1">
        {estado.conversaciones.map((conv) => {
          const seleccionada = conv.id === activa?.id;
          return (
            <div
              key={conv.id}
              className={`group flex items-start gap-2 rounded-xl border p-3 transition ${
                seleccionada
                  ? "border-orange-200 bg-orange-50"
                  : "border-transparent bg-white hover:border-line hover:bg-ash"
              }`}
            >
              <button
                type="button"
                onClick={() => elegir(conv.id)}
                className="min-w-0 flex-1 text-left focus:outline-none focus:ring-2 focus:ring-ulima/40"
              >
                <span className="line-clamp-2 text-sm font-semibold">{conv.titulo}</span>
                <span className="mt-1 block truncate font-mono text-[11px] text-muted">
                  {fechaCorta(conv.actualizada)} · {conv.mensajes.length} mensajes
                </span>
              </button>
              <button
                type="button"
                onClick={() => confirmarBorrado(conv)}
                className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-muted opacity-60 transition hover:bg-white hover:text-red-600 focus:opacity-100 focus:outline-none focus:ring-2 focus:ring-ulima/40 group-hover:opacity-100"
                aria-label={`Borrar ${conv.titulo}`}
                title="Borrar"
              >
                <Trash2 size={15} />
              </button>
            </div>
          );
        })}
      </div>

      <button
        type="button"
        onClick={confirmarLimpieza}
        className="mt-4 flex h-10 w-full items-center justify-center gap-2 rounded-xl border border-line bg-white px-4 text-sm font-semibold text-muted transition hover:border-red-200 hover:bg-red-50 hover:text-red-600 focus:outline-none focus:ring-2 focus:ring-ulima/40"
      >
        <Trash2 size={15} />
        Limpiar historial
      </button>
    </aside>
  );
}
