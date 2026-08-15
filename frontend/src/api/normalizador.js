export async function iniciarNormalizadorEmpleabilidad(archivo) {
  const formulario = new FormData();
  formulario.append("archivo", archivo);

  const respuesta = await fetch("/api/normalizador/empleabilidad", {
    method: "POST",
    body: formulario,
  });
  const datos = await respuesta.json().catch(() => ({}));
  if (!respuesta.ok) {
    throw new Error(datos.detail || "No se pudo iniciar la normalización.");
  }
  return datos;
}

export async function iniciarNormalizadorSilabos(archivo, carrera, periodo) {
  const formulario = new FormData();
  formulario.append("archivo", archivo);
  formulario.append("carrera", carrera);
  formulario.append("periodo", periodo);

  const respuesta = await fetch("/api/normalizador/silabos", {
    method: "POST",
    body: formulario,
  });
  const datos = await respuesta.json().catch(() => ({}));
  if (!respuesta.ok) {
    throw new Error(datos.detail || "No se pudo iniciar la limpieza curricular.");
  }
  return datos;
}

export async function obtenerEjecucionNormalizador(idEjecucion) {
  const respuesta = await fetch(`/api/normalizador/ejecuciones/${idEjecucion}`);
  const datos = await respuesta.json().catch(() => ({}));
  if (!respuesta.ok) {
    throw new Error(datos.detail || "No se pudo consultar la ejecución.");
  }
  return datos;
}

export async function obtenerErroresNormalizador(idEjecucion) {
  const respuesta = await fetch(`/api/normalizador/ejecuciones/${idEjecucion}/errores`);
  const datos = await respuesta.json().catch(() => ({}));
  if (!respuesta.ok) {
    throw new Error(datos.detail || "No se pudieron consultar los errores.");
  }
  return datos;
}

export async function obtenerCuarentenaNormalizador(idEjecucion, opciones = {}) {
  const parametros = new URLSearchParams({
    desde: String(opciones.desde ?? 0),
    limite: String(opciones.limite ?? 50),
  });
  const respuesta = await fetch(
    `/api/normalizador/ejecuciones/${idEjecucion}/cuarentena?${parametros.toString()}`,
  );
  const datos = await respuesta.json().catch(() => ({}));
  if (!respuesta.ok) {
    throw new Error(datos.detail || "No se pudo consultar la cuarentena.");
  }
  return datos;
}

export function obtenerUrlOutputNormalizador(idEjecucion, archivo) {
  const ruta = String(archivo || "")
    .split("/")
    .filter(Boolean)
    .map((segmento) => encodeURIComponent(segmento))
    .join("/");
  return `/api/normalizador/ejecuciones/${encodeURIComponent(idEjecucion)}/outputs/${ruta}`;
}
