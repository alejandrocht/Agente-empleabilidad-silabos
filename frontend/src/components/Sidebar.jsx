import { MessageSquarePlus, Trash2 } from "lucide-react";
import BotAvatar from "./BotAvatar";

function fechaCorta(timestamp) {
  return new Intl.DateTimeFormat("es-PE", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(timestamp);
}

export default function Sidebar({
  estado,
  activa,
  nuevaConversacion,
  seleccionar,
  borrar,
  limpiar,
}) {
  return (
    <aside className="border-b border-line bg-white px-4 py-5 lg:min-h-screen lg:w-80 lg:border-b-0 lg:border-r">
      <div className="mb-6 flex items-center gap-3">
        <BotAvatar size="lg" />
        <div>
          <p className="text-lg font-extrabold">Agente Ciar</p>
          <p className="text-sm text-muted">Historial</p>
        </div>
      </div>

      <button
        type="button"
        onClick={nuevaConversacion}
        className="mb-4 flex w-full items-center justify-center gap-2 rounded-xl bg-ulima px-4 py-3 font-semibold text-white transition hover:bg-orange-600 focus:outline-none focus:ring-2 focus:ring-ulima/40"
      >
        <MessageSquarePlus size={18} />
        Nueva conversacion
      </button>

      <div className="max-h-72 space-y-2 overflow-y-auto pr-1 lg:max-h-[calc(100vh-17rem)]">
        {estado.conversaciones.map((conv) => {
          const seleccionada = conv.id === activa?.id;
          return (
            <div
              key={conv.id}
              className={`group rounded-2xl border p-3 transition ${
                seleccionada
                  ? "border-ulima bg-orange-50"
                  : "border-line bg-white hover:border-ulima/30"
              }`}
            >
              <button
                type="button"
                onClick={() => seleccionar(conv.id)}
                className="block w-full text-left focus:outline-none focus:ring-2 focus:ring-ulima/40"
              >
                <span className="line-clamp-2 text-sm font-semibold">{conv.titulo}</span>
                <span className="mt-1 block font-mono text-[11px] text-muted">
                  {fechaCorta(conv.actualizada)} · {conv.mensajes.length} mensajes
                </span>
              </button>
              <button
                type="button"
                onClick={() => borrar(conv.id)}
                className="mt-2 inline-flex items-center gap-1 rounded-full px-2 py-1 text-xs text-muted transition hover:bg-orange-50 hover:text-ulima focus:outline-none focus:ring-2 focus:ring-ulima/40"
                aria-label={`Borrar ${conv.titulo}`}
              >
                <Trash2 size={13} />
                Borrar
              </button>
            </div>
          );
        })}
      </div>

      <button
        type="button"
        onClick={limpiar}
        className="mt-5 w-full rounded-xl border border-line px-4 py-2 text-sm font-semibold text-muted transition hover:border-ulima hover:text-ulima focus:outline-none focus:ring-2 focus:ring-ulima/40"
      >
        Limpiar historial
      </button>
    </aside>
  );
}
