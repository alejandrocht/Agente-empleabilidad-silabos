import { useEffect, useState } from "react";
import { crearId } from "../lib/ids";

const CLAVE = "ciar.conversaciones";
const LIMITE_CONVERSACIONES = 30;
const LIMITE_MENSAJES = 100;
const ESTADO_VACIO = { conversaciones: [], activa: null };

function crearConversacion() {
  const ahora = Date.now();
  const id = crearId("conv");
  return {
    id,
    id_sesion: crearId("sesion"),
    titulo: "Nueva conversación",
    creada: ahora,
    actualizada: ahora,
    mensajes: [],
  };
}

function cargar() {
  try {
    const cache = JSON.parse(localStorage.getItem(CLAVE));
    if (cache?.conversaciones?.length) return cache;
  } catch {
    // Si el cache esta corrupto, se reinicia la demo.
  }

  const inicial = crearConversacion();
  return { conversaciones: [inicial], activa: inicial.id };
}

function titular(texto) {
  const limpio = texto.trim().replace(/\s+/g, " ");
  if (!limpio) return "Nueva conversación";
  return limpio.length > 42 ? `${limpio.slice(0, 42)}...` : limpio;
}

export function useConversaciones() {
  const [estado, setEstado] = useState(ESTADO_VACIO);
  const [listo, setListo] = useState(false);

  useEffect(() => {
    setEstado(cargar());
    setListo(true);
  }, []);

  useEffect(() => {
    if (!listo) return;
    try {
      localStorage.setItem(CLAVE, JSON.stringify(estado));
    } catch {
      // La conversación sigue disponible en RAM si el navegador agotó su almacenamiento.
    }
  }, [estado, listo]);

  const nuevaConversacion = () => {
    const conversacion = crearConversacion();
    setEstado((actual) => ({
      conversaciones: [conversacion, ...actual.conversaciones].slice(0, LIMITE_CONVERSACIONES),
      activa: conversacion.id,
    }));
    return conversacion.id;
  };

  const seleccionar = (convId) => {
    setEstado((actual) => ({ ...actual, activa: convId }));
  };

  const agregarMensaje = (convId, mensaje) => {
    setEstado((actual) => ({
      ...actual,
      conversaciones: actual.conversaciones
        .map((conv) => {
          if (conv.id !== convId) return conv;
          const primerMensaje = conv.mensajes.length === 0 && mensaje.rol === "usuario";
          return {
            ...conv,
            titulo: primerMensaje ? titular(mensaje.texto) : conv.titulo,
            actualizada: Date.now(),
            mensajes: [...conv.mensajes, mensaje].slice(-LIMITE_MENSAJES),
          };
        })
        .sort((a, b) => b.actualizada - a.actualizada)
        .slice(0, LIMITE_CONVERSACIONES),
    }));
  };

  const borrar = (convId) => {
    setEstado((actual) => {
      const restantes = actual.conversaciones.filter((conv) => conv.id !== convId);
      if (restantes.length === 0) {
        const conversacion = crearConversacion();
        return { conversaciones: [conversacion], activa: conversacion.id };
      }
      const activa = actual.activa === convId ? restantes[0].id : actual.activa;
      return { conversaciones: restantes, activa };
    });
  };

  const limpiar = () => {
    const conversacion = crearConversacion();
    setEstado({ conversaciones: [conversacion], activa: conversacion.id });
  };

  const activa = estado.conversaciones.find((conv) => conv.id === estado.activa) ?? estado.conversaciones[0] ?? null;

  return {
    estado,
    activa,
    listo,
    nuevaConversacion,
    seleccionar,
    agregarMensaje,
    borrar,
    limpiar,
  };
}
