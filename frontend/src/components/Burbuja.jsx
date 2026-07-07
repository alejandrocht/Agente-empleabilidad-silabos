import PanelRazonamiento from "./PanelRazonamiento";
import TablaFilas from "./TablaFilas";
import BotAvatar from "./BotAvatar";

export default function Burbuja({ mensaje }) {
  const esUsuario = mensaje.rol === "usuario";

  if (mensaje.cargando) {
    return (
      <div className="flex justify-start gap-3">
        <BotAvatar />
        <div className="w-full max-w-2xl rounded-2xl border border-line bg-white p-5 shadow-panel">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-ulima">
            Generando Cypher...
          </p>
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
    <div className={`flex ${esUsuario ? "justify-end" : "justify-start gap-3"}`}>
      {!esUsuario ? <BotAvatar /> : null}
      <article
        className={`max-w-3xl rounded-2xl px-5 py-4 shadow-sm ${
          esUsuario
            ? "bg-ulima text-white"
            : "border border-line bg-white text-ink shadow-panel"
        }`}
      >
        <p className="whitespace-pre-wrap text-[1.03rem] leading-relaxed">{mensaje.texto}</p>

        {!esUsuario && mensaje.error ? (
          <div className="mt-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-semibold text-red-700">
            Consulta bloqueada por seguridad: {mensaje.error}
          </div>
        ) : null}

        {!esUsuario ? <TablaFilas filas={mensaje.filas ?? []} /> : null}

        {!esUsuario ? (
          <PanelRazonamiento
            pasos={mensaje.pasos ?? []}
            cypher={mensaje.cypher}
            entidades={mensaje.entidades ?? []}
            error={mensaje.error}
          />
        ) : null}
      </article>
    </div>
  );
}
