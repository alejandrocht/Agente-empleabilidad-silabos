function construirUrl(ruta, parametros = {}) {
  const busqueda = new URLSearchParams(
    Object.entries(parametros).flatMap(([clave, valor]) =>
      valor === undefined || valor === null || valor === "" ? [] : [[clave, String(valor)]],
    ),
  );
  const query = busqueda.toString();
  return query ? ruta + "?" + query : ruta;
}

async function solicitar(ruta, parametros, opciones = {}) {
  const respuesta = await fetch(construirUrl(ruta, parametros), opciones);
  const datos = await respuesta.json().catch(() => ({}));
  if (!respuesta.ok) {
    const error = new Error(datos.detail || "No se pudieron cargar los datos del dashboard.");
    error.status = respuesta.status;
    throw error;
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

export function obtenerCarrerasPorDemandaDashboard(parametros) {
  return solicitar("/api/dashboard/carreras/demanda", parametros);
}

export function obtenerIndustriasPorCarreraDashboard(carreraId, parametros) {
  return solicitar("/api/dashboard/carreras/" + encodeURIComponent(carreraId) + "/industrias", parametros);
}

export function obtenerEmpresasDashboard(parametros) {
  return solicitar("/api/dashboard/empresas", parametros);
}

export function esBackendNoDisponible(error) {
  return error instanceof TypeError || Number(error?.status) >= 500;
}

export const dashboardApi = {
  obtenerMetadatosDashboard,
  obtenerCarrerasDashboard,
  obtenerTendenciaDashboard,
  obtenerDemandaDashboard,
  obtenerCoberturaDashboard,
  obtenerBrechasDashboard,
  obtenerCarrerasPorDemandaDashboard,
  obtenerIndustriasPorCarreraDashboard,
  obtenerEmpresasDashboard,
};
