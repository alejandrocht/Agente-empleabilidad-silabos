function valorSimple(valor) {
  return ["string", "number", "boolean"].includes(typeof valor) || valor == null;
}

function titulo(texto) {
  const limpio = texto.replaceAll("_", " ");
  return limpio.charAt(0).toUpperCase() + limpio.slice(1);
}

export default function TablaFilas({ filas }) {
  if (!Array.isArray(filas) || filas.length === 0) return null;

  const columnas = Array.from(new Set(filas.flatMap((fila) => Object.keys(fila))));
  const unaFila = filas.length === 1 && columnas.length === 1;
  const unicoValor = unaFila ? filas[0][columnas[0]] : null;

  if (unaFila && valorSimple(unicoValor)) {
    return (
      <div className="mt-4 rounded-xl border border-orange-100 bg-orange-50 px-5 py-4 text-ink">
        <p className="font-mono text-xs font-semibold text-ulima">{titulo(columnas[0])}</p>
        <p className="mt-1 text-4xl font-extrabold">{String(unicoValor)}</p>
      </div>
    );
  }

  return (
    <div className="mt-4 overflow-hidden rounded-xl border border-line bg-white">
      <div className="flex items-center justify-between border-b border-line bg-ash/70 px-3 py-2">
        <p className="text-xs font-semibold text-muted">Resultados</p>
        <span className="rounded-full bg-white px-2 py-0.5 font-mono text-[10px] text-muted">
          {filas.length} {filas.length === 1 ? "fila" : "filas"}
        </span>
      </div>
      <div className="max-h-80 overflow-auto">
        <table className="min-w-full border-collapse text-sm">
          <thead className="sticky top-0 bg-orange-50 text-left text-ink shadow-[0_1px_0_#fed7aa]">
            <tr>
              {columnas.map((columna) => (
                <th key={columna} className="px-3 py-2 font-mono text-xs font-semibold">
                  {titulo(columna)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filas.map((fila, index) => (
              <tr key={index} className="border-t border-line transition hover:bg-orange-50/40">
                {columnas.map((columna) => (
                  <td key={columna} className="px-3 py-2 align-top text-ink">
                    {valorSimple(fila[columna])
                      ? String(fila[columna] ?? "—")
                      : JSON.stringify(fila[columna])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
