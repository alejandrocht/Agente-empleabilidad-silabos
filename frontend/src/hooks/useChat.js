import { useRef, useState } from "react";
import { enviarPregunta } from "../api/agente";

export function useChat({ conversacion, agregarMensaje }) {
  const [enviando, setEnviando] = useState(false);
  const [errorRed, setErrorRed] = useState(null);
  const bloqueo = useRef(false);

  const enviar = async (texto) => {
    const pregunta = texto.trim();
    if (!pregunta || bloqueo.current || !conversacion) return;

    bloqueo.current = true;
    setErrorRed(null);
    agregarMensaje(conversacion.id, { rol: "usuario", texto: pregunta, creado: Date.now() });
    setEnviando(true);

    try {
      const data = await enviarPregunta({
        pregunta,
        idSesion: conversacion.id_sesion,
      });
      agregarMensaje(conversacion.id, {
        rol: "agente",
        texto: data.respuesta,
        cypher: data.cypher,
        entidades: data.entidades ?? [],
        filas: data.filas ?? [],
        pasos: data.pasos ?? [],
        error: data.error ?? null,
        creado: Date.now(),
      });
    } catch (err) {
      const mensaje = err.message || "No se pudo contactar al agente.";
      setErrorRed(mensaje);
      agregarMensaje(conversacion.id, {
        rol: "agente",
        texto: "No se pudo contactar al agente.",
        errorRed: mensaje,
        pasos: [],
        filas: [],
        entidades: [],
        cypher: null,
        creado: Date.now(),
      });
    } finally {
      bloqueo.current = false;
      setEnviando(false);
    }
  };

  return { enviar, enviando, errorRed };
}
