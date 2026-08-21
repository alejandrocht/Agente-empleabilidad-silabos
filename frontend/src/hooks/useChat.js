import { useMemo, useRef } from "react";
import { useStream, FetchStreamTransport } from "@langchain/langgraph-sdk/react";

export function normalizeChatValues(values) {
  const source = values && typeof values === "object" && !Array.isArray(values) ? values : {};
  return {
    texto: typeof source.respuesta === "string" ? source.respuesta : "",
    cypher: typeof source.cypher === "string" ? source.cypher : "",
    fase: typeof source.fase === "string" ? source.fase : "",
    entidades: Array.isArray(source.entidades) ? source.entidades : [],
    filas: Array.isArray(source.filas) ? source.filas : [],
    pasos: Array.isArray(source.pasos) ? source.pasos : [],
    error: typeof source.error === "string" ? source.error : "",
  };
}

export function useChat({ conversacion, agregarMensaje }) {
  const agregarRef = useRef(agregarMensaje);
  const conversacionRef = useRef(conversacion);
  agregarRef.current = agregarMensaje;
  conversacionRef.current = conversacion;

  const transport = useMemo(
    () => new FetchStreamTransport({ apiUrl: "/chat/stream" }),
    []
  );

  const { values, submit, isLoading, error } = useStream({
    transport,
    threadId: conversacion?.id_sesion ?? null,
    onFinish: (finalState) => {
      const conv = conversacionRef.current;
      const finalValues = normalizeChatValues(finalState?.values);
      if (!conv || !finalValues.texto) return;
      agregarRef.current(conv.id, {
        rol: "agente",
        texto: finalValues.texto,
        cypher: finalValues.cypher,
        fase: finalValues.fase,
        entidades: finalValues.entidades,
        filas: finalValues.filas,
        pasos: finalValues.pasos,
        error: finalValues.error,
        creado: Date.now(),
      });
    },
  });

  const enviar = (texto) => {
    const pregunta = texto.trim();
    if (!pregunta || isLoading || !conversacion) return;
    agregarMensaje(conversacion.id, { rol: "usuario", texto: pregunta, creado: Date.now() });
    submit({ pregunta });
  };

  const streamingValues = normalizeChatValues(values);
  const mensajeStreaming = isLoading
    ? { ...streamingValues, streaming: true }
    : null;

  return {
    enviar,
    enviando: isLoading,
    errorRed: typeof error?.message === "string" ? error.message : "",
    mensajeStreaming,
  };
}
