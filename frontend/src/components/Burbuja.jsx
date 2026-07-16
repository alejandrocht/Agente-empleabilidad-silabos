import { Check, Copy } from "lucide-react";
import { useState } from "react";
import BotAvatar from "./BotAvatar";
import PanelRazonamiento from "./PanelRazonamiento";
import TablaFilas from "./TablaFilas";

export default function Burbuja({ mensaje }) {
  const esUsuario = mensaje.rol === "usuario";
  const [copiado, setCopiado] = useState(false);

  const copiar = async () => {
    if (!mensaje.texto) return;
    await navigator.clipboard?.writeText(mensaje.texto);
    setCopiado(true);
    setTimeout(() => setCopiado(false), 1400);
  };

  const hora = mensaje.creado
    ? new Intl.DateTimeFormat("es-PE", { hour: "2-digit", minute: "2-digit" }).format(mensaje.creado)
    : null;

  if (mensaje.cargando) {
    return (
      <div className="flex animate-fade-in items-center gap-3 text-muted">
        <img src="/logo-ulima.png" alt="" className="h-6 w-6 animate-girar object-contain" />
        <p className="text-sm font-medium">Recorriendo el grafo…</p>
      </div>
    );
  }

  if (esUsuario) {
    return (
      <div className="flex w-full animate-fade-in justify-end">
        <div className="max-w-[70%] rounded-[16px] rounded-br-[4px] bg-ulima px-4 py-3 text-[15px] leading-relaxed text-white shadow-sm">
          <p className="whitespace-pre-wrap">{mensaje.texto}</p>
          {hora ? <time className="mt-1.5 block text-right text-[11px] text-white/70">{hora}</time> : null}
        </div>
      </div>
    );
  }

  return (
    <div className="flex w-full animate-fade-in justify-start gap-3">
      <BotAvatar />
      <article className="min-w-0 flex-1">
        <p className="whitespace-pre-wrap text-[15.5px] leading-[1.65] text-ink">{mensaje.texto}</p>

        {mensaje.error ? (
          <div className="mt-4 rounded-[10px] border border-red-200 bg-red-50 px-4 py-3 text-sm font-semibold text-red-700">
            Consulta bloqueada por seguridad: {mensaje.error}
          </div>
        ) : null}

        {mensaje.errorRed ? (
          <div className="mt-4 rounded-[10px] border border-amber-200 bg-amber-50 px-4 py-3 text-sm font-semibold text-amber-800">
            Error de conexión/API: {mensaje.errorRed}
          </div>
        ) : null}

        <TablaFilas filas={mensaje.filas ?? []} />

        <PanelRazonamiento
          pasos={mensaje.pasos ?? []}
          cypher={mensaje.cypher}
          entidades={mensaje.entidades ?? []}
          error={mensaje.error}
          errorRed={mensaje.errorRed}
        />

        <div className="mt-3 flex items-center gap-2">
          {mensaje.texto ? (
            <button
              type="button"
              onClick={copiar}
              className="inline-flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-xs font-semibold text-muted transition hover:bg-ash hover:text-ink focus:outline-none focus:ring-2 focus:ring-ulima/30"
              aria-label="Copiar respuesta"
            >
              {copiado ? <Check size={14} className="text-emerald-600" /> : <Copy size={14} />}
              {copiado ? "Copiado" : "Copiar"}
            </button>
          ) : null}
          {hora ? <time className="ml-auto text-[11px] text-muted">{hora}</time> : null}
        </div>
      </article>
    </div>
  );
}
