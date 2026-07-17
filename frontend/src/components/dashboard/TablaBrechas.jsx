function porcentaje(valor) {
  return new Intl.NumberFormat("es-PE", {
    style: "percent",
    maximumFractionDigits: 1,
  }).format(valor);
}

export default function TablaBrechas({ filas, disponible, onSeleccionar, seleccionadoId }) {
  if (!disponible || !filas?.length) return null;

  return (
    <div className="mt-5 overflow-x-auto rounded-xl border border-line">
      <table className="min-w-full text-left text-xs">
        <thead className="bg-ash text-muted">
          <tr>
            <th scope="col" className="px-3 py-2.5 font-bold">Elemento</th>
            <th scope="col" className="px-3 py-2.5 text-right font-bold">Demanda</th>
            <th scope="col" className="px-3 py-2.5 text-right font-bold">Cobertura</th>
            <th scope="col" className="px-3 py-2.5 text-right font-bold">Ofertas</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {filas.map((fila) => {
            const seleccionado = fila.id === seleccionadoId;
            return (
              <tr
                key={fila.id}
                className={seleccionado ? "bg-[#FFF0E9]" : "bg-paper hover:bg-fondo"}
              >
                <th scope="row" className="px-3 py-2 font-semibold text-ink">
                  <button
                    type="button"
                    onClick={() => onSeleccionar(fila)}
                    className="text-left underline-offset-2 hover:text-ulima hover:underline focus:outline-none focus:ring-2 focus:ring-ulima/40"
                  >
                    {fila.elemento}
                  </button>
                </th>
                <td className="px-3 py-2 text-right font-mono tabular-nums text-ink">{porcentaje(fila.demanda)}</td>
                <td className="px-3 py-2 text-right font-mono tabular-nums text-ink">{porcentaje(fila.cobertura)}</td>
                <td className="px-3 py-2 text-right font-mono tabular-nums text-muted">
                  {fila.ofertas_que_requieren.toLocaleString("es-PE")}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
