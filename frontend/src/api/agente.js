export async function enviarPregunta({ pregunta, idSesion }) {
  const respuesta = await fetch("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pregunta, id_sesion: idSesion }),
  });

  const data = await respuesta.json().catch(() => ({}));
  if (!respuesta.ok) {
    throw new Error(data.detail || "No se pudo contactar al agente.");
  }
  return data;
}

export async function enviarPreguntaStream({ pregunta, idSesion, onDelta, onFin, onError }) {
  const response = await fetch("/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pregunta, id_sesion: idSesion }),
  });

  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || "No se pudo contactar al agente.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      try {
        const event = JSON.parse(line.slice(6));
        if (event.tipo === "delta") onDelta?.(event.texto);
        else if (event.tipo === "fin") onFin?.(event);
        else if (event.tipo === "error") onError?.(event.mensaje);
      } catch {
        // línea malformada, ignorar
      }
    }
  }
}
