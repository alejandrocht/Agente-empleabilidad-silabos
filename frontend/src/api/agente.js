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
