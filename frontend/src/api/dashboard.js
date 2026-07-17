function construirUrl(ruta, parametros = {}) {
  const busqueda = new URLSearchParams(
    Object.entries(parametros).flatMap(([clave, valor]) =>
      valor === undefined || valor === null || valor === "" ? [] : [[clave, String(valor)]],
    ),
  );
  const query = busqueda.toString();
  return query ? ruta + "?" + query : ruta;
}

async function solicitar(ruta, parametros) {
  const respuesta = await fetch(construirUrl(ruta, parametros));
  const datos = await respuesta.json().catch(() => ({}));
  if (!respuesta.ok) {
    throw new Error(datos.detail || "No se pudieron cargar los datos del dashboard.");
  }
  return datos;
}

export function obtenerMetadatosDashboard() {
  return solicitar("/api/dashboard/metadata");
}

export function obtenerCarrerasDashboard() {
  return solicitar("/api/dashboard/filtros/carreras");
}

export function obtenerTendenciaDashboard(parametros) {
  return solicitar("/api/dashboard/ofertas/tendencia", parametros);
}

export function obtenerDemandaDashboard(tipo, parametros) {
  return solicitar("/api/dashboard/dimensiones/" + tipo + "/demanda", parametros);
}

export function obtenerCoberturaDashboard(tipo, parametros) {
  return solicitar("/api/dashboard/dimensiones/" + tipo + "/cobertura", parametros);
}

export function obtenerBrechasDashboard(tipo, parametros) {
  return solicitar("/api/dashboard/dimensiones/" + tipo + "/brechas", parametros);
}

export function obtenerIndustriasDashboard(tipo, parametros) {
  return solicitar("/api/dashboard/dimensiones/" + tipo + "/industrias", parametros);
}
