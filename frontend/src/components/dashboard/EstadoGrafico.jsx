export default function EstadoGrafico({ cargando, error, vacio, mensajeVacio = "No hay datos para estos filtros." }) {
  if (cargando) {
    return (
      <div className="flex h-64 items-center justify-center rounded-xl bg-fondo text-sm font-medium text-muted">
        <span className="mr-2 h-4 w-4 animate-girar rounded-full border-2 border-ulima border-t-transparent" />
        Cargando datos del grafo…
      </div>
    );
  }
  if (error) {
    return <p className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</p>;
  }
  if (vacio) {
    return <p className="flex h-64 items-center justify-center rounded-xl bg-fondo p-4 text-center text-sm text-muted">{mensajeVacio}</p>;
  }
  return null;
}
