import { useState } from "react";

const LIMITE_INICIAL = 8;

const ETIQUETAS_PLURAL = {
  carrera: "carreras",
  curso: "cursos",
  empresa: "empresas",
  herramienta: "herramientas",
  competencia: "competencias",
  habilidad: "habilidades",
  puesto: "puestos",
  industria: "industrias",
  oferta: "ofertas",
};

function valorSimple(valor) {
  return ["string", "number", "boolean"].includes(typeof valor) || valor == null;
}

function esDatoUnico(filas) {
  return filas.length === 1 && Object.keys(filas[0]).length === 1 && valorSimple(Object.values(filas[0])[0]);
}

function titulo(texto) {
  const limpio = texto.replaceAll("_", " ");
  return limpio.charAt(0).toUpperCase() + limpio.slice(1);
}

function formatearValor(valor) {
  if (valor == null) return "—";
  if (typeof valor === "number") return new Intl.NumberFormat("es-PE").format(valor);
  if (typeof valor === "boolean") return valor ? "Sí" : "No";
  return valorSimple(valor) ? String(valor) : JSON.stringify(valor);
}

export function resumenFilas(filas) {
  if (!Array.isArray(filas) || filas.length === 0 || esDatoUnico(filas)) return null;

  const primeraColumna = Object.keys(filas[0])[0] || "";
  const plural = ETIQUETAS_PLURAL[primeraColumna.toLowerCase()] || "resultados";
  if (filas.length === 1) {
    const singular = plural === "resultados" ? "resultado" : plural.slice(0, -1);
    return `Se encontró 1 ${singular}. Revisa el detalle en la tabla.`;
  }
  return `Se encontraron ${filas.length} ${plural}. Revisa el detalle en la tabla.`;
}

export default function TablaFilas({ filas }) {
  const [expandida, setExpandida] = useState(false);

  if (!Array.isArray(filas) || filas.length === 0 || esDatoUnico(filas)) return null;

  const columnas = Array.from(new Set(filas.flatMap((fila) => Object.keys(fila))));
  const filasVisibles = expandida ? filas : filas.slice(0, LIMITE_INICIAL);
  const filasOcultas = filas.length - filasVisibles.length;

  return (
    <section className="mt-4 overflow-hidden rounded-2xl border border-line bg-paper shadow-sm" aria-label="Detalle de resultados">
      <div className="flex items-center justify-between gap-3 border-b border-line bg-ash px-4 py-3 sm:px-5">
        <div>
          <p className="text-[10.5px] font-bold uppercase tracking-[0.14em] text-muted">Detalle de resultados</p>
          <p className="mt-0.5 text-xs text-muted">Organizado para comparar con facilidad.</p>
        </div>
        <span className="shrink-0 rounded-full border border-line bg-paper px-2.5 py-1 font-mono text-[10px] text-muted">
          {filas.length} {filas.length === 1 ? "resultado" : "resultados"}
        </span>
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full border-collapse text-sm">
          <thead className="bg-paper text-left shadow-[0_1px_0_#EAE2D9]">
            <tr>
              {columnas.map((columna) => (
                <th
                  key={columna}
                  scope="col"
                  className="whitespace-nowrap px-4 py-3 text-[10.5px] font-bold uppercase tracking-[0.12em] text-muted sm:px-5"
                >
                  {titulo(columna)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filasVisibles.map((fila, index) => (
              <tr key={index} className="border-t border-line transition hover:bg-ulima/[0.025]">
                {columnas.map((columna) => {
                  const valor = fila[columna];
                  const esNumero = typeof valor === "number";
                  return (
                    <td
                      key={columna}
                      className={"px-4 py-3 align-top text-ink sm:px-5 " + (esNumero ? "text-right font-mono tabular-nums" : "font-medium")}
                    >
                      {formatearValor(valor)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {filas.length > LIMITE_INICIAL ? (
        <div className="border-t border-line bg-fondo px-4 py-2.5 sm:px-5">
          <button
            type="button"
            onClick={() => setExpandida((valor) => !valor)}
            className="text-xs font-bold text-ulima transition hover:text-[#D9410C] focus:outline-none focus:ring-2 focus:ring-ulima/40"
          >
            {expandida ? "Mostrar menos" : `Ver ${filasOcultas} resultados más`}
          </button>
        </div>
      ) : null}
    </section>
  );
}
