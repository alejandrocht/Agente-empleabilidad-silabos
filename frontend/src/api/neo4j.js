async function leerRespuesta(respuesta, mensaje) {
  const datos = await respuesta.json().catch(() => ({}));
  if (!respuesta.ok) {
    throw new Error(datos.detail || mensaje);
  }
  return datos;
}

export async function obtenerEstadoNeo4j({ signal } = {}) {
  const respuesta = await fetch("/api/neo4j/estado", { signal });
  return leerRespuesta(respuesta, "No se pudo consultar el estado de Neo4j.");
}

export async function validarImportacionNeo4j(idEjecucion) {
  const respuesta = await fetch("/api/neo4j/validar", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id_ejecucion: idEjecucion }),
  });
  return leerRespuesta(respuesta, "No se pudo validar la publicación en Neo4j.");
}

export async function importarEnNeo4j(idEjecucion, fingerprint, confirmar) {
  const respuesta = await fetch("/api/neo4j/importar", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id_ejecucion: idEjecucion, fingerprint, confirmar }),
  });
  return leerRespuesta(respuesta, "No se pudo agregar la data a Neo4j.");
}

export async function listarImportacionesNeo4j() {
  const respuesta = await fetch("/api/neo4j/importaciones");
  return leerRespuesta(respuesta, "No se pudo consultar el historial de importaciones.");
}

export async function revertirImportacionNeo4j(idImportacion, confirmar) {
  const respuesta = await fetch(
    `/api/neo4j/importaciones/${encodeURIComponent(idImportacion)}/revertir`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirmar }),
    },
  );
  return leerRespuesta(respuesta, "No se pudo revertir la importación.");
}
