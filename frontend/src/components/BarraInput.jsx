import { SendHorizonal } from "lucide-react";
import { useState } from "react";

const SUGERIDAS = [
  "¿Cuántas carreras hay?",
  "¿Cuántos cursos tiene Ingeniería de Sistemas?",
  "¿Qué facultades existen?",
  "¿Qué carreras ofrece la Facultad de Ingeniería?",
  "¿Qué carrera tiene más cursos?",
  "Top 10 herramientas más solicitadas en ofertas dirigidas a Ingeniería de Sistemas.",
  "¿Qué herramientas piden las ofertas de Ingeniería Industrial que no se enseñan en su currícula?",
  "¿Y qué competencias desarrolla?",
  "Elimina la carrera de Derecho",
  "¿Cuál es el clima en Lima hoy?",
];

export default function BarraInput({ onEnviar, disabled }) {
  const [texto, setTexto] = useState("");

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
    <footer className="border-t border-line bg-white px-4 py-4">
      <div className="mx-auto max-w-5xl">
        <div className="mb-3 flex gap-2 overflow-x-auto pb-1">
          {SUGERIDAS.map((pregunta) => (
            <button
              type="button"
              key={pregunta}
              disabled={disabled}
              onClick={() => enviar(pregunta)}
              className="shrink-0 rounded-full border border-line bg-white px-3 py-2 text-sm font-semibold text-ink transition hover:border-ulima hover:text-ulima focus:outline-none focus:ring-2 focus:ring-ulima/40 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {pregunta}
            </button>
          ))}
        </div>
        <div className="flex items-end gap-3 rounded-2xl border border-line bg-white p-2 shadow-panel">
          <textarea
            value={texto}
            disabled={disabled}
            onChange={(event) => setTexto(event.target.value)}
            onKeyDown={onKeyDown}
            rows={1}
            placeholder="Pregunta al agente sobre carreras, cursos, ofertas o competencias..."
            className="max-h-40 min-h-12 flex-1 resize-none rounded-xl bg-transparent px-3 py-3 text-base outline-none placeholder:text-muted disabled:cursor-not-allowed"
          />
          <button
            type="button"
            onClick={() => enviar()}
            disabled={disabled || !texto.trim()}
            className="inline-flex h-12 w-12 items-center justify-center rounded-xl bg-ulima text-white transition hover:bg-orange-600 focus:outline-none focus:ring-2 focus:ring-ulima/40 disabled:cursor-not-allowed disabled:opacity-50"
            aria-label="Enviar pregunta"
          >
            <SendHorizonal size={20} />
          </button>
        </div>
      </div>
    </footer>
  );
}
