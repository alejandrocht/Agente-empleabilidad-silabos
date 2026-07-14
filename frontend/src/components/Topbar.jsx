import { Database, Menu } from "lucide-react";
import { useEffect, useState } from "react";
import BotAvatar from "./BotAvatar";

export default function Topbar({ conversacion, onAbrirMenu }) {
  const [estado, setEstado] = useState("comprobando");

  useEffect(() => {
    let activo = true;

    const comprobar = async () => {
      try {
        const respuesta = await fetch("/health", { cache: "no-store" });
        if (activo) setEstado(respuesta.ok ? "conectado" : "desconectado");
      } catch {
        if (activo) setEstado("desconectado");
      }
    };

    comprobar();
    const intervalo = setInterval(comprobar, 30000);
    return () => {
      activo = false;
      clearInterval(intervalo);
    };
  }, []);

  const conectado = estado === "conectado";

  return (
    <header className="z-20 shrink-0 border-b border-line/80 bg-white/85 px-4 backdrop-blur-xl sm:px-6">
      <div className="mx-auto flex h-16 w-full max-w-6xl items-center justify-between gap-4">
        <div className="flex min-w-0 items-center gap-3">
          <button
            type="button"
            onClick={onAbrirMenu}
            className="icon-button lg:hidden"
            aria-label="Abrir conversaciones"
          >
            <Menu size={19} />
          </button>
          <div className="hidden sm:block lg:hidden">
            <BotAvatar />
          </div>
          <div className="min-w-0">
            <p className="truncate text-sm font-bold text-ink sm:text-base">
              {conversacion?.titulo ?? "Nueva conversación"}
            </p>
            <p className="truncate text-xs text-muted">Consultas académicas y de empleabilidad</p>
          </div>
        </div>

        <div
          className={`flex shrink-0 items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-semibold ${
            conectado
              ? "border-emerald-200 bg-emerald-50 text-emerald-700"
              : estado === "comprobando"
                ? "border-line bg-white text-muted"
                : "border-red-200 bg-red-50 text-red-700"
          }`}
          title="Estado de conexión con Neo4j"
        >
          <span
            className={`h-2 w-2 rounded-full ${
              conectado ? "bg-emerald-500" : estado === "comprobando" ? "bg-slate-300" : "bg-red-500"
            }`}
          />
          <Database size={13} />
          <span className="hidden sm:inline">
            {conectado ? "Neo4j conectado" : estado === "comprobando" ? "Comprobando" : "Sin conexión"}
          </span>
        </div>
      </div>
    </header>
  );
}
