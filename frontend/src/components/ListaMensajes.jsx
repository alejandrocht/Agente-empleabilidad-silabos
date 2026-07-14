import { BriefcaseBusiness, Building2, GraduationCap, Wrench } from "lucide-react";
import BotAvatar from "./BotAvatar";
import Burbuja from "./Burbuja";

const SUGERENCIAS = [
  { icono: GraduationCap, etiqueta: "Carreras", pregunta: "¿Cuántas carreras hay?" },
  { icono: Building2, etiqueta: "Empresas", pregunta: "¿Qué empresas publican más ofertas?" },
  { icono: Wrench, etiqueta: "Herramientas", pregunta: "¿Cuáles son las herramientas más requeridas?" },
  { icono: BriefcaseBusiness, etiqueta: "Empleabilidad", pregunta: "¿Cuáles son los puestos más demandados?" },
];

export default function ListaMensajes({ mensajes, enviando, onSugerencia }) {
  if (mensajes.length === 0 && !enviando) {
    return (
      <div className="flex flex-1 items-center justify-center py-8 sm:py-12">
        <div className="w-full max-w-3xl animate-fade-in">
          <div className="flex flex-col items-start sm:flex-row sm:gap-5">
            <BotAvatar size="lg" />
            <div className="mt-5 min-w-0 sm:mt-0">
              <p className="text-xs font-bold uppercase tracking-[0.18em] text-ulima">Agente CIAR</p>
              <h1 className="mt-2 max-w-2xl text-3xl font-extrabold leading-[1.08] tracking-tight text-ink sm:text-5xl">
                Explora la conexión entre formación y empleo.
              </h1>
              <p className="mt-4 max-w-xl text-base leading-7 text-muted sm:text-lg">
                Consulta carreras, cursos y tendencias laborales mediante el grafo académico de Neo4j.
              </p>
            </div>
          </div>

          <div className="mt-8 grid gap-2 sm:grid-cols-2">
            {SUGERENCIAS.map(({ icono: Icono, etiqueta, pregunta }) => (
              <button
                type="button"
                key={pregunta}
                onClick={() => onSugerencia(pregunta)}
                className="group flex items-center gap-3 rounded-xl border border-line bg-white/90 p-3.5 text-left shadow-sm transition hover:-translate-y-0.5 hover:border-orange-200 hover:shadow-md focus:outline-none focus:ring-2 focus:ring-ulima/30"
              >
                <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-orange-50 text-ulima transition group-hover:bg-ulima group-hover:text-white">
                  <Icono size={18} />
                </span>
                <span className="min-w-0">
                  <span className="block text-[11px] font-bold uppercase tracking-wider text-muted">{etiqueta}</span>
                  <span className="mt-0.5 block text-sm font-semibold leading-5 text-ink">{pregunta}</span>
                </span>
              </button>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 space-y-5 pb-3">
      {mensajes.map((mensaje, index) => (
        <Burbuja key={`${mensaje.rol}-${index}`} mensaje={mensaje} />
      ))}
      {enviando ? <Burbuja mensaje={{ rol: "agente", cargando: true }} /> : null}
    </div>
  );
}
