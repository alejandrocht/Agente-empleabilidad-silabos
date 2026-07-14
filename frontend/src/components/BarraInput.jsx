import { ArrowUp, Sparkles } from "lucide-react";
import { useEffect, useRef, useState } from "react";

const MAX_CHARS = 500;

export default function BarraInput({ onEnviar, disabled }) {
  const [texto, setTexto] = useState("");
  const areaRef = useRef(null);

  useEffect(() => {
    const area = areaRef.current;
    if (!area) return;
    area.style.height = "auto";
    area.style.height = `${Math.min(area.scrollHeight, 128)}px`;
  }, [texto]);

  const enviar = (valor = texto) => {
    const pregunta = valor.trim();
    if (!pregunta) return;
    onEnviar(pregunta);
    setTexto("");
  };

  const onKeyDown = (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      enviar();
    }
  };

  return (
    <footer className="shrink-0 border-t border-line/80 bg-white/85 px-4 py-3 backdrop-blur-xl sm:px-6 sm:py-4">
      <div className="mx-auto w-full max-w-5xl">
        <div className="rounded-2xl border border-line bg-white p-2 shadow-[0_10px_35px_rgba(31,41,51,0.09)] transition focus-within:border-ulima/50 focus-within:ring-4 focus-within:ring-ulima/10">
          <div className="flex items-end gap-2">
            <span className="mb-3 ml-2 hidden text-ulima sm:block" aria-hidden="true">
              <Sparkles size={18} />
            </span>
          <textarea
            ref={areaRef}
            value={texto}
            disabled={disabled}
            onChange={(event) => setTexto(event.target.value)}
            onKeyDown={onKeyDown}
            rows={1}
            maxLength={MAX_CHARS}
            placeholder="Escribe tu pregunta..."
            className="max-h-32 min-h-12 flex-1 resize-none overflow-y-auto bg-transparent px-2 py-3 text-base leading-6 outline-none placeholder:text-muted disabled:cursor-not-allowed"
          />
          <button
            type="button"
            onClick={() => enviar()}
            disabled={disabled || !texto.trim()}
            className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-ulima text-white shadow-sm transition hover:-translate-y-0.5 hover:bg-orange-600 focus:outline-none focus:ring-2 focus:ring-ulima/40 disabled:cursor-not-allowed disabled:bg-orange-200 disabled:shadow-none"
            aria-label="Enviar pregunta"
            title="Enviar"
          >
            <ArrowUp size={20} strokeWidth={2.4} />
          </button>
          </div>
          <div className="flex items-center justify-between px-2 pb-1 pt-0.5 text-[11px] text-muted">
            <span>{disabled ? "Consultando el grafo…" : "Enter para enviar · Shift + Enter para una nueva línea"}</span>
            <span className={texto.length > 450 ? "font-semibold text-ulima" : ""}>
              {texto.length}/{MAX_CHARS}
            </span>
          </div>
        </div>
      </div>
    </footer>
  );
}
