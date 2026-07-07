function valorSimple(valor) {
  return ["string", "number", "boolean"].includes(typeof valor) || valor == null;
}

export default function TablaFilas({ filas }) {
  if (!Array.isArray(filas) || filas.length === 0) return null;

  const columnas = Array.from(new Set(filas.flatMap((fila) => Object.keys(fila))));
  const unaFila = filas.length === 1 && columnas.length === 1;
  const unicoValor = unaFila ? filas[0][columnas[0]] : null;

  if (unaFila && valorSimple(unicoValor)) {
    return (
      <div className="mt-4 rounded-2xl bg-orange-50 px-5 py-4 text-ink">
        <p className="font-mono text-xs uppercase tracking-[0.16em] text-ulima">{columnas[0]}</p>
        <p className="mt-1 text-4xl font-extrabold">{String(unicoValor)}</p>
      </div>
    );
  }

  return (
    <div className="mt-4 overflow-hidden rounded-2xl border border-line">
      <div className="max-h-80 overflow-auto">
        <table className="min-w-full border-collapse text-sm">
          <thead className="sticky top-0 bg-orange-50 text-left text-ink">
            <tr>
              {columnas.map((columna) => (
                <th key={columna} className="px-3 py-2 font-mono text-xs uppercase tracking-[0.16em]">
                  {columna}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filas.map((fila, index) => (
              <tr key={index} className="border-t border-line">
                {columnas.map((columna) => (
                  <td key={columna} className="px-3 py-2 align-top">
                    {valorSimple(fila[columna])
                      ? String(fila[columna] ?? "")
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
