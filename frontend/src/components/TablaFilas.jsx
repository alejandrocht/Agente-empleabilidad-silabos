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
      <div className="mt-4 rounded-[12px] border border-ulima/25 bg-ulima/5 px-5 py-4 text-ink">
        <p className="text-[10.5px] font-bold uppercase tracking-[0.14em] text-ulima">
          {titulo(columnas[0])}
        </p>
        <p className="mt-1 font-mono text-4xl font-bold tabular-nums">{String(unicoValor)}</p>
      </div>
    );
  }

  return (
    <div className="mt-4 overflow-hidden rounded-[12px] border border-line bg-paper">
      <div className="flex items-center justify-between border-b border-line bg-ash px-4 py-2">
        <p className="text-[10.5px] font-bold uppercase tracking-[0.14em] text-muted">Resultados</p>
        <span className="rounded-full bg-paper px-2 py-0.5 font-mono text-[10px] text-muted">
          {filas.length} {filas.length === 1 ? "fila" : "filas"}
        </span>
      </div>
      <div className="max-h-80 overflow-auto">
        <table className="min-w-full border-collapse text-sm">
          <thead className="sticky top-0 bg-ash text-left shadow-[0_1px_0_#EAE2D9]">
            <tr>
              {columnas.map((columna) => (
                <th
                  key={columna}
                  className="px-4 py-2.5 text-[10.5px] font-bold uppercase tracking-[0.12em] text-muted"
                >
                  {titulo(columna)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filas.map((fila, index) => (
              <tr key={index} className="border-t border-line transition hover:bg-ash/50">
                {columnas.map((columna) => (
                  <td
                    key={columna}
                    className={`px-4 py-2.5 align-top text-ink ${
                      typeof fila[columna] === "number" ? "text-right font-mono tabular-nums" : ""
                    }`}
                  >
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
