import { ArrowUp } from "lucide-react";
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
    <footer className="shrink-0 border-t border-line bg-paper/85 px-4 py-3 backdrop-blur-xl sm:px-6 sm:py-4">
      <div className="mx-auto w-full max-w-3xl">
        <div className="flex items-end gap-2 rounded-[16px] border-[1.5px] border-line bg-paper py-1.5 pl-4 pr-1.5 shadow-input transition focus-within:border-ulima">
          <textarea
            ref={areaRef}
            value={texto}
            disabled={disabled}
            onChange={(event) => setTexto(event.target.value)}
            onKeyDown={onKeyDown}
            rows={1}
            maxLength={MAX_CHARS}
            placeholder="Pregunta sobre carreras, cursos, empresas o empleabilidad…"
            className="max-h-32 min-h-11 flex-1 resize-none overflow-y-auto bg-transparent py-2.5 text-[15px] leading-6 outline-none placeholder:text-muted disabled:cursor-not-allowed"
          />
          <button
            type="button"
            onClick={() => enviar()}
            disabled={disabled || !texto.trim()}
            className="mb-0.5 inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-ulima text-white shadow-sm transition hover:-translate-y-px focus:outline-none focus:ring-2 focus:ring-ulima/40 disabled:cursor-not-allowed disabled:bg-ulima/30 disabled:shadow-none"
            aria-label="Enviar pregunta"
            title="Enviar"
          >
            <ArrowUp size={19} strokeWidth={2.4} />
          </button>
        </div>
        <div className="flex items-center justify-between px-1.5 pt-2 text-[11px] text-muted">
          <span>{disabled ? "Recorriendo el grafo…" : "Enter para enviar · Shift + Enter para una nueva línea"}</span>
          <span className={`font-mono ${texto.length > 450 ? "font-semibold text-ulima" : ""}`}>
            {texto.length}/{MAX_CHARS}
          </span>
        </div>
      </div>
    </footer>
  );
}
