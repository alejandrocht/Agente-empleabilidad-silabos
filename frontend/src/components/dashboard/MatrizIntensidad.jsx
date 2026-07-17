const periodos = ["Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];

function tono(valor) {
  const opacidad = 0.16 + valor * 0.14;
  return "rgba(255, 81, 23, " + opacidad + ")";
}

export default function MatrizIntensidad({ filas, columnas = periodos, etiquetaBaja = "Menor intensidad", etiquetaAlta = "Mayor intensidad" }) {
  return (
    <div className="overflow-x-auto">
      <div className="min-w-[28rem]">
        <div
          className="grid gap-1.5 text-center text-[10px] font-bold text-muted"
          style={{ gridTemplateColumns: "8rem repeat(" + columnas.length + ", minmax(2.25rem, 1fr))" }}
        >
          <span />
          {columnas.map((columna) => <span key={columna}>{columna}</span>)}
          {filas.map((fila) => (
            <div className="contents" key={fila.elemento}>
              <span className="self-center pr-2 text-left text-xs font-semibold text-ink">{fila.elemento}</span>
              {fila.valores.map((valor, indice) => (
                <span
                  key={fila.elemento + indice}
                  title={fila.elemento + " · " + columnas[indice] + " · nivel " + valor}
                  className="h-9 rounded-lg border border-white/60 shadow-[inset_0_1px_0_rgba(255,255,255,0.8)]"
                  style={{ backgroundColor: tono(valor) }}
                />
              ))}
            </div>
          ))}
        </div>
      </div>
      <div className="mt-4 flex items-center justify-between text-[11px] text-muted">
        <span>{etiquetaBaja}</span>
        <span className="flex gap-1">
          {[1, 2, 3, 4, 5].map((valor) => (
            <i key={valor} className="h-3 w-3 rounded-[4px]" style={{ backgroundColor: tono(valor) }} />
          ))}
        </span>
        <span>{etiquetaAlta}</span>
      </div>
    </div>
  );
}
