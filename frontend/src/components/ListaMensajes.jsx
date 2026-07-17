import Burbuja from "./Burbuja";

const SUGERENCIAS = [
  {
    etiqueta: "Carreras",
    pregunta: "¿Cuántas carreras hay?",
    acento: "text-secundario-turquesa",
    borde: "border-secundario-turquesa/35 hover:border-secundario-turquesa/70 hover:bg-secundario-turquesa/5",
    punto: "border-secundario-turquesa/40 group-hover:border-secundario-turquesa group-hover:bg-secundario-turquesa",
  },
  {
    etiqueta: "Empresas",
    pregunta: "¿Qué empresas publican más ofertas?",
    acento: "text-secundario-verde",
    borde: "border-secundario-verde/35 hover:border-secundario-verde/70 hover:bg-secundario-verde/5",
    punto: "border-secundario-verde/40 group-hover:border-secundario-verde group-hover:bg-secundario-verde",
  },
  {
    etiqueta: "Herramientas",
    pregunta: "¿Cuáles son las herramientas más requeridas?",
    acento: "text-secundario-naranja",
    borde: "border-secundario-naranja/35 hover:border-secundario-naranja/70 hover:bg-secundario-naranja/5",
    punto: "border-secundario-naranja/40 group-hover:border-secundario-naranja group-hover:bg-secundario-naranja",
  },
  {
    etiqueta: "Empleabilidad",
    pregunta: "¿Cuáles son los puestos más demandados?",
    acento: "text-secundario-rosa",
    borde: "border-secundario-rosa/35 hover:border-secundario-rosa/70 hover:bg-secundario-rosa/5",
    punto: "border-secundario-rosa/40 group-hover:border-secundario-rosa group-hover:bg-secundario-rosa",
  },
];

export default function ListaMensajes({ mensajes, enviando, onSugerencia }) {
  if (mensajes.length === 0 && !enviando) {
    return (
      <div className="flex flex-1 items-center justify-center py-8 sm:py-12">
        <div className="w-full max-w-3xl animate-fade-in">
          <h1 className="max-w-2xl text-3xl font-extrabold leading-[1.08] tracking-tight text-ink sm:text-5xl [text-wrap:balance]">
            Explora la conexión entre <span className="text-ulima">formación</span> y{" "}
            <span className="text-ulima">empleo</span>.
          </h1>
          <p className="mt-4 max-w-xl text-base leading-7 text-muted sm:text-lg">
            Pregunta en español. El agente recorre el grafo académico de la Universidad de Lima y te
            muestra cómo llegó a cada respuesta.
          </p>

          <div className="mt-8 grid gap-2.5 sm:grid-cols-2">
            {SUGERENCIAS.map(({ etiqueta, pregunta, acento, borde, punto }) => (
              <button
                type="button"
                key={pregunta}
                onClick={() => onSugerencia(pregunta)}
                className={`group relative rounded-[14px] border bg-paper p-4 text-left transition hover:-translate-y-0.5 hover:shadow-panel focus:outline-none focus:ring-2 focus:ring-ulima/30 ${borde}`}
              >
                <span
                  className={`absolute right-4 top-4 h-2 w-2 rounded-full border-2 bg-paper transition ${punto}`}
                  aria-hidden="true"
                />
                <span className={`block text-[10px] font-bold uppercase tracking-[0.15em] ${acento}`}>
                  {etiqueta}
                </span>
                <span className="mt-1.5 block pr-6 text-sm font-semibold leading-5 text-ink">
                  {pregunta}
                </span>
              </button>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 space-y-6 pb-3">
      {mensajes.map((mensaje, index) => (
        <Burbuja key={`${mensaje.rol}-${index}`} mensaje={mensaje} />
      ))}
      {enviando ? <Burbuja mensaje={{ rol: "agente", cargando: true }} /> : null}
    </div>
  );
}
