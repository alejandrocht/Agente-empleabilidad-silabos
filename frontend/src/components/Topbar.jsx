import Link from "next/link";
import { BarChart3, Menu, Upload } from "lucide-react";
import Neo4jStatusIndicator from "./Neo4jStatusIndicator";

export default function Topbar({ conversacion, onAbrirMenu }) {
  return (
    <header className="z-20 shrink-0 border-b border-line bg-paper/85 px-4 backdrop-blur-xl sm:px-6">
      <div className="flex h-16 w-full items-center justify-between gap-4">
        <div className="flex min-w-0 items-center gap-2">
          <button
            type="button"
            onClick={onAbrirMenu}
            className="icon-button lg:hidden"
            aria-label="Abrir menú"
            title="Menú"
          >
            <Menu size={19} />
          </button>
          <div className="min-w-0">
            <p className="truncate text-sm font-bold text-ink sm:text-[15px]">
              {conversacion?.titulo ?? "Nueva conversación"}
            </p>
            <p className="truncate text-xs text-muted">
              Consultas académicas y de empleabilidad
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Neo4jStatusIndicator />
          <Link
            href="/normalizador"
            className="hidden items-center gap-1.5 rounded-xl border border-line px-3 py-2 text-xs font-bold text-ink transition hover:border-ulima hover:text-ulima focus:outline-none focus:ring-2 focus:ring-ulima/40 sm:inline-flex"
          >
            <Upload size={14} />
            Normalizar fuente
          </Link>
          <Link
            href="/dashboard"
            className="inline-flex items-center gap-1.5 rounded-xl bg-ink px-3 py-2 text-xs font-bold text-white transition hover:bg-ulima focus:outline-none focus:ring-2 focus:ring-ulima/40"
          >
            <BarChart3 size={14} />
            Dashboard
          </Link>
        </div>
      </div>
    </header>
  );
}
