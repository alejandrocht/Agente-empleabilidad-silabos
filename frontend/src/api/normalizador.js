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

export async function iniciarNormalizadorSilabosCactus(carrera, periodo, usuario, contrasena) {
  const respuesta = await fetch("/api/normalizador/silabos/cactus", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ carrera, periodo, usuario, contrasena }),
  });
  const datos = await respuesta.json().catch(() => ({}));
  if (!respuesta.ok) {
    throw new Error(datos.detail || "No se pudo iniciar la extracción desde Cactus.");
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

export async function obtenerPendientesNormalizador(idEjecucion, opciones = {}) {
  const parametros = new URLSearchParams({
    desde: String(opciones.desde ?? 0),
    limite: String(opciones.limite ?? 200),
    incluir_resueltas: String(opciones.incluirResueltas ?? false),
  });
  const respuesta = await fetch(
    `/api/normalizador/ejecuciones/${encodeURIComponent(idEjecucion)}/pendientes?${parametros.toString()}`,
  );
  const datos = await respuesta.json().catch(() => ({}));
  if (!respuesta.ok) {
    throw new Error(datos.detail || "No se pudieron consultar las propuestas curriculares.");
  }
  return datos;
}

export async function decidirPendientesNormalizador(idEjecucion, decisiones, actor = "ejecutor", revision = null) {
  const respuesta = await fetch(
    `/api/normalizador/ejecuciones/${encodeURIComponent(idEjecucion)}/pendientes/decidir`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decisiones, actor, ...(revision ? { revision } : {}) }),
    },
  );
  const datos = await respuesta.json().catch(() => ({}));
  if (!respuesta.ok) {
    throw new Error(datos.detail || "No se pudieron guardar las decisiones curriculares.");
  }
  return datos;
}

export async function cancelarEjecucionNormalizador(idEjecucion) {
  const respuesta = await fetch(
    `/api/normalizador/ejecuciones/${encodeURIComponent(idEjecucion)}/cancelar`,
    { method: "POST" },
  );
  const datos = await respuesta.json().catch(() => ({}));
  if (!respuesta.ok) {
    throw new Error(datos.detail || "No se pudo cancelar la ejecución.");
  }
  return datos;
}

export async function listarEjecucionesNormalizador(limite = 20) {
  const parametros = new URLSearchParams({ limite: String(limite) });
  const respuesta = await fetch(`/api/normalizador/ejecuciones?${parametros.toString()}`);
  const datos = await respuesta.json().catch(() => ({}));
  if (!respuesta.ok) {
    throw new Error(datos.detail || "No se pudo cargar el historial.");
  }
  return datos;
}

export async function obtenerReporteEjecucionNormalizador(idEjecucion) {
  const respuesta = await fetch(
    `/api/normalizador/ejecuciones/${encodeURIComponent(idEjecucion)}/reporte`,
  );
  const datos = await respuesta.json().catch(() => ({}));
  if (!respuesta.ok) {
    throw new Error(datos.detail || "No se pudo cargar el reporte de la ejecución.");
  }
  return datos;
}

export function obtenerUrlReporteEjecucionNormalizador(idEjecucion) {
  return `/api/normalizador/ejecuciones/${encodeURIComponent(idEjecucion)}/reporte`;
}

export async function eliminarEjecucionHistorialNormalizador(idEjecucion) {
  const respuesta = await fetch(
    `/api/normalizador/ejecuciones/${encodeURIComponent(idEjecucion)}/historial`,
    { method: "DELETE" },
  );
  const datos = await respuesta.json().catch(() => ({}));
  if (!respuesta.ok) {
    throw new Error(datos.detail || "No se pudo eliminar la ejecución del historial.");
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
