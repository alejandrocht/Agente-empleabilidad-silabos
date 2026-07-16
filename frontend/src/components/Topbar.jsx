import { Database, Menu } from "lucide-react";
import { useEffect, useState } from "react";

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
    <header className="z-20 shrink-0 border-b border-line bg-paper/85 px-4 backdrop-blur-xl sm:px-6">
      <div className="flex h-16 w-full items-center justify-between gap-4">
        <div className="flex min-w-0 items-center gap-2">
          <button
            type="button"
            onClick={onAbrirMenu}
            className="icon-button"
            aria-label="Mostrar u ocultar menú"
            title="Menú"
          >
            <Menu size={19} />
          </button>
          <div className="min-w-0">
            <p className="truncate text-sm font-bold text-ink sm:text-[15px]">
              {conversacion?.titulo ?? "Nueva conversación"}
            </p>
            <p className="truncate text-xs text-muted">Consultas académicas y de empleabilidad</p>
          </div>
        </div>

        <div
          className={`flex shrink-0 items-center gap-2 rounded-full px-3 py-1.5 text-xs font-semibold ${
            conectado
              ? "bg-emerald-500/10 text-emerald-700"
              : estado === "comprobando"
                ? "bg-ash text-muted"
                : "bg-red-500/10 text-red-700"
          }`}
          title="Estado de conexión con Neo4j"
        >
          <span
            className={`h-[7px] w-[7px] rounded-full ${
              conectado
                ? "animate-pulso bg-emerald-500"
                : estado === "comprobando"
                  ? "bg-muted/50"
                  : "bg-red-500"
            }`}
          />
          <Database size={13} />
          <span className="hidden sm:inline">
            {conectado ? "Neo4j" : estado === "comprobando" ? "Comprobando" : "Sin conexión"}
          </span>
        </div>
      </div>
    </header>
  );
}
