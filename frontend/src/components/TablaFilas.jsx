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

const ANALISIS_POR_TIPO = {
  carrera: "La lista permite comparar las carreras relacionadas y su cobertura académica.",
  curso: "La lista reúne cursos de distintas áreas y permite comparar la cobertura curricular relacionada.",
  empresa: "La lista permite comparar las empresas relacionadas con el criterio consultado.",
  herramienta: "La lista permite comparar las herramientas asociadas a la consulta.",
  competencia: "La lista permite comparar las competencias identificadas en los resultados.",
  habilidad: "La lista permite comparar las habilidades asociadas al criterio consultado.",
  puesto: "La lista permite comparar los puestos relacionados y sus oportunidades.",
  oferta: "La lista permite comparar las ofertas relacionadas con la consulta.",
};

function valorSimple(valor) {
  return ["string", "number", "boolean"].includes(typeof valor) || valor == null;
}

function esIdentificador(nombre) {
  const clave = String(nombre || "").trim().toLowerCase();
  return clave === "id" || clave === "identificador" || clave.startsWith("id_") || clave.endsWith("_id") || clave.endsWith("_ids");
}

function columnasDe(filas) {
  return Array.from(new Set(filas.flatMap((fila) => (fila && typeof fila === "object" ? Object.keys(fila) : []))));
}

function columnasPresentables(filas) {
  return columnasDe(filas).filter((columna) => !esIdentificador(columna));
}

function esDatoUnico(filas) {
  const fila = filas[0];
  return filas.length === 1 && fila && typeof fila === "object" && Object.keys(fila).length === 1 && valorSimple(Object.values(fila)[0]);
}

function titulo(texto) {
  const limpio = texto.replaceAll("_", " ");
  return limpio.charAt(0).toUpperCase() + limpio.slice(1);
}

function valorSinIdentificadores(valor) {
  if (Array.isArray(valor)) return valor.map(valorSinIdentificadores);
  if (!valor || typeof valor !== "object") return valor;

  return Object.fromEntries(
    Object.entries(valor)
      .filter(([clave]) => !esIdentificador(clave))
      .map(([clave, valorInterno]) => [clave, valorSinIdentificadores(valorInterno)]),
  );
}

function formatearValor(valor) {
  if (valor == null) return "—";
  if (typeof valor === "number") return new Intl.NumberFormat("es-PE").format(valor);
  if (typeof valor === "boolean") return valor ? "SÍ" : "NO";
  if (typeof valor === "string") return valor.toLocaleUpperCase("es-PE");

  const valorSeguro = valorSinIdentificadores(valor);
  return JSON.stringify(valorSeguro).toLocaleUpperCase("es-PE");
}

export function resumenFilas(filas) {
  if (!Array.isArray(filas) || filas.length === 0 || esDatoUnico(filas)) return null;

  const primeraColumna = columnasPresentables(filas)[0] || "";
  const plural = ETIQUETAS_PLURAL[primeraColumna.toLowerCase()] || "resultados";
  if (filas.length === 1) {
    const singular = plural === "resultados" ? "resultado" : plural.slice(0, -1);
    return `Se encontró 1 ${singular}. Revisa el detalle en la tabla.`;
  }
  return `Se encontraron ${filas.length} ${plural}. Revisa el detalle en la tabla.`;
}

export function analisisFilas(filas) {
  if (!Array.isArray(filas) || filas.length === 0) return null;

  const primeraColumna = columnasPresentables(filas)[0] || "";
  if (!primeraColumna) return null;

  const plural = ETIQUETAS_PLURAL[primeraColumna.toLowerCase()] || "resultados";
  const detalle = ANALISIS_POR_TIPO[primeraColumna.toLowerCase()] || "La información está organizada para facilitar la comparación de los resultados.";
  return `Análisis breve: se encontraron ${filas.length} ${plural}. ${detalle}`;
}

export default function TablaFilas({ filas }) {
  const [expandida, setExpandida] = useState(false);

  if (!Array.isArray(filas) || filas.length === 0 || esDatoUnico(filas)) return null;

  const columnas = columnasPresentables(filas);
  if (columnas.length === 0) return null;

  const filasVisibles = expandida ? filas : filas.slice(0, LIMITE_INICIAL);
  const filasOcultas = filas.length - filasVisibles.length;

  return (
    <section className="mt-4 overflow-hidden rounded-2xl border border-line bg-paper shadow-sm" aria-label="Detalle de resultados">
      <div className="flex items-center justify-between gap-3 border-b border-line bg-ash px-4 py-3 sm:px-5">
        <div>
          <p className="text-[10.5px] font-bold uppercase tracking-[0.14em] text-muted">Detalle de resultados</p>
          <p className="mt-0.5 text-xs text-muted">{analisisFilas(filas)}</p>
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
