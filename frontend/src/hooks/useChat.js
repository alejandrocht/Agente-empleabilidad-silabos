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
  const valoresStreamingRef = useRef(normalizeChatValues(null));
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
    onError: (streamError) => {
      const conv = conversacionRef.current;
      if (!conv) return;
      const current = valoresStreamingRef.current;
      agregarRef.current(conv.id, {
        rol: "agente",
        texto: current.texto || "No pude completar la respuesta porque la conexión se interrumpió.",
        cypher: current.cypher,
        fase: "completado",
        entidades: current.entidades,
        filas: current.filas,
        pasos: current.pasos,
        error: current.texto ? "stream_interrupted" : "stream_failed",
        errorRed:
          typeof streamError?.message === "string"
            ? streamError.message
            : "La conexión con el agente se interrumpió.",
        creado: Date.now(),
      });
    },
  });

  const enviar = (texto) => {
    const pregunta = texto.trim();
    if (!pregunta || isLoading || !conversacion) return;
    agregarMensaje(conversacion.id, { rol: "usuario", texto: pregunta, creado: Date.now() });
    valoresStreamingRef.current = normalizeChatValues(null);
    submit({ pregunta });
  };

  const streamingValues = normalizeChatValues(values);
  valoresStreamingRef.current = streamingValues;
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
