import { useCallback, useMemo, useRef, useState } from "react";
import { useStream, FetchStreamTransport } from "@langchain/langgraph-sdk/react";

export function normalizeChatValues(values) {
  const source = values && typeof values === "object" && !Array.isArray(values) ? values : {};
  return {
    texto: typeof source.respuesta === "string" ? source.respuesta : "",
    cypher: typeof source.cypher === "string" ? source.cypher : "",
    fase: typeof source.fase === "string" ? source.fase : "",
    progreso: typeof source.progreso === "string" ? source.progreso : "",
    entidades: Array.isArray(source.entidades) ? source.entidades : [],
    error: typeof source.error === "string" ? source.error : "",
  };
}

function textoDeContenido(content) {
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return "";
  return content
    .filter((block) => block && (block.type === "text" || block.type === "output_text"))
    .map((block) => (typeof block.text === "string" ? block.text : block.content))
    .filter((text) => typeof text === "string")
    .join("");
}

export function textoUltimoMensajeAsistente(messages) {
  if (!Array.isArray(messages)) return "";
  const mensaje = [...messages].reverse().find((item) => {
    const type = typeof item?.getType === "function" ? item.getType() : item?.type;
    return type === "ai" || type === "assistant";
  });
  return mensaje ? textoDeContenido(mensaje.content) : "";
}

export function useChat({ conversacion, agregarMensaje }) {
  const agregarRef = useRef(agregarMensaje);
  const conversacionRef = useRef(conversacion);
  const valoresStreamingRef = useRef(normalizeChatValues(null));
  const [progresoStreaming, setProgresoStreaming] = useState("");
  const [faseStreaming, setFaseStreaming] = useState("");
  agregarRef.current = agregarMensaje;
  conversacionRef.current = conversacion;

  const transport = useMemo(
    () => new FetchStreamTransport({ apiUrl: "/chat/stream" }),
    []
  );

  const onCustomEvent = useCallback((event) => {
    if (!event || event.type !== "progress" || typeof event.texto !== "string") return;
    setProgresoStreaming(event.texto);
    setFaseStreaming(typeof event.fase === "string" ? event.fase : "");
  }, []);

  const { values, messages, submit, isLoading, error } = useStream({
    transport,
    threadId: conversacion?.id_sesion ?? null,
    onCustomEvent,
    onFinish: (finalState) => {
      const conv = conversacionRef.current;
      const finalValues = normalizeChatValues(finalState?.values);
      setProgresoStreaming("");
      setFaseStreaming("");
      if (!conv || !finalValues.texto) return;
      agregarRef.current(conv.id, {
        rol: "agente",
        texto: finalValues.texto,
        cypher: finalValues.cypher,
        fase: finalValues.fase,
        entidades: finalValues.entidades,
        error: finalValues.error,
        creado: Date.now(),
      });
    },
    onError: (streamError) => {
      const conv = conversacionRef.current;
      if (!conv) return;
      const current = valoresStreamingRef.current;
      setProgresoStreaming("");
      setFaseStreaming("");
      agregarRef.current(conv.id, {
        rol: "agente",
        texto: current.texto || "No pude completar la respuesta porque la conexión se interrumpió.",
        cypher: current.cypher,
        fase: "completado",
        entidades: current.entidades,
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
    setFaseStreaming("analizando");
    setProgresoStreaming("Analizando tu consulta…");
    submit({ pregunta });
  };

  const normalizedValues = normalizeChatValues(values);
  const streamingValues = {
    ...normalizedValues,
    texto: textoUltimoMensajeAsistente(messages) || normalizedValues.texto,
    fase: normalizedValues.fase || faseStreaming,
    progreso: progresoStreaming || normalizedValues.progreso,
  };
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
