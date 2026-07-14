import { useEffect, useRef } from "react";
import { useChat } from "../hooks/useChat";
import BarraInput from "./BarraInput";
import ListaMensajes from "./ListaMensajes";

export default function ChatWindow({ conversacion, agregarMensaje }) {
  const { enviar, enviando, errorRed } = useChat({ conversacion, agregarMensaje });
  const finRef = useRef(null);

  useEffect(() => {
    finRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [conversacion?.mensajes.length, enviando]);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto flex min-h-full w-full max-w-5xl flex-col px-4 py-6 sm:px-6 lg:py-8">
        {errorRed ? (
          <div className="mb-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-semibold text-red-700 shadow-sm">
            {errorRed}
          </div>
        ) : null}

        <ListaMensajes
          mensajes={conversacion?.mensajes ?? []}
          enviando={enviando}
          onSugerencia={enviar}
        />
        <div ref={finRef} />
        </div>
      </div>

      <BarraInput onEnviar={enviar} disabled={enviando} />
    </div>
  );
}
