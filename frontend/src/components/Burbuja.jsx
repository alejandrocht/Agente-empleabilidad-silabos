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
      <div className="flex animate-fade-in justify-start gap-3">
        <BotAvatar />
        <div className="w-full max-w-2xl rounded-2xl border border-line bg-white p-5 shadow-sm">
          <p className="font-mono text-xs font-semibold text-ulima">Consultando el grafo…</p>
          <div className="mt-4 space-y-3">
            <div className="h-3 w-4/5 animate-pulse rounded-full bg-slate-200" />
            <div className="h-3 w-2/3 animate-pulse rounded-full bg-slate-200" />
            <div className="h-3 w-1/2 animate-pulse rounded-full bg-slate-200" />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={`flex w-full animate-fade-in ${esUsuario ? "justify-end" : "justify-start gap-3"}`}>
      {!esUsuario ? <BotAvatar /> : null}
      <article
        className={`min-w-0 rounded-2xl px-4 py-3.5 sm:px-5 sm:py-4 ${
          esUsuario
            ? "max-w-[min(38rem,88%)] rounded-br-md bg-ulima text-white shadow-sm"
            : "w-full max-w-3xl rounded-tl-md border border-line bg-white text-ink shadow-sm"
        }`}
      >
        <p className="whitespace-pre-wrap text-[1.02rem] leading-relaxed">{mensaje.texto}</p>

        {!esUsuario && mensaje.error ? (
          <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm font-semibold text-red-700">
            Consulta bloqueada por seguridad: {mensaje.error}
          </div>
        ) : null}

        {!esUsuario && mensaje.errorRed ? (
          <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm font-semibold text-amber-800">
            Error de conexión/API: {mensaje.errorRed}
          </div>
        ) : null}

        {!esUsuario ? <TablaFilas filas={mensaje.filas ?? []} /> : null}

        {!esUsuario ? (
          <PanelRazonamiento
            pasos={mensaje.pasos ?? []}
            cypher={mensaje.cypher}
            entidades={mensaje.entidades ?? []}
            error={mensaje.error}
            errorRed={mensaje.errorRed}
          />
        ) : null}

        <div className={`mt-3 flex items-center gap-2 ${esUsuario ? "justify-end" : "justify-between"}`}>
          {hora ? (
            <time className={`text-[11px] ${esUsuario ? "text-white/70" : "text-muted"}`}>{hora}</time>
          ) : (
            <span />
          )}
          {!esUsuario && mensaje.texto ? (
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
        </div>
      </article>
    </div>
  );
}
