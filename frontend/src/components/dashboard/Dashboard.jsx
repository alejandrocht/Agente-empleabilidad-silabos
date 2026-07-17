"use client";

import Link from "next/link";
import { ArrowLeft, BriefcaseBusiness, GraduationCap, LineChart } from "lucide-react";
import { useMemo, useState } from "react";
import BarrasComparativasChart from "./BarrasComparativasChart";
import BrechaCurriculoMercadoChart from "./BrechaCurriculoMercadoChart";
import MatrizIntensidad from "./MatrizIntensidad";
import RankingDimensionChart from "./RankingDimensionChart";
import TarjetaGrafico from "./TarjetaGrafico";
import TendenciaOfertasChart from "./TendenciaOfertasChart";
import {
  MOCK_CARRERAS,
  MOCK_DASHBOARDS,
  MOCK_FACULTADES,
  MOCK_INDUSTRIAS,
  MOCK_PERIODOS,
} from "./mockData";

const seriesCursos = [
  { clave: "mercado", etiqueta: "Lo que busca el mercado", color: "#FF5117" },
  { clave: "curriculo", etiqueta: "Presencia en cursos", color: "#00C5D6" },
];

function Selector({ etiqueta, valor, onChange, opciones }) {
  return (
    <label className="grid gap-1.5 text-sm font-semibold text-ink">
      {etiqueta}
      <select
        value={valor}
        onChange={onChange}
        className="h-10 rounded-xl border border-line bg-paper px-3 text-sm font-medium text-ink outline-none transition focus:border-ulima focus:ring-2 focus:ring-ulima/20"
      >
        {opciones.map((item) => <option key={item.id || item} value={item.id || item}>{item.nombre || item}</option>)}
      </select>
    </label>
  );
}

function Seccion({ icono: Icono, titulo, descripcion, children }) {
  return (
    <section className="mb-9">
      <div className="mb-4 flex items-start gap-3">
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-ash text-ulima"><Icono size={18} /></span>
        <div>
          <h2 className="text-xl font-extrabold tracking-tight text-ink">{titulo}</h2>
          <p className="mt-0.5 text-sm leading-6 text-muted">{descripcion}</p>
        </div>
      </div>
      {children}
    </section>
  );
}

export default function Dashboard() {
  const [facultadId, setFacultadId] = useState(MOCK_FACULTADES[0].id);
  const [carreraId, setCarreraId] = useState(MOCK_CARRERAS[0].id);
  const [industriaId, setIndustriaId] = useState(MOCK_INDUSTRIAS[0].id);
  const [periodo, setPeriodo] = useState(MOCK_PERIODOS[0]);

  const carrerasDeFacultad = useMemo(
    () => MOCK_CARRERAS.filter((item) => item.facultad_id === facultadId),
    [facultadId],
  );
  const carrera = MOCK_CARRERAS.find((item) => item.id === carreraId) || carrerasDeFacultad[0] || MOCK_CARRERAS[0];
  const industria = MOCK_INDUSTRIAS.find((item) => item.id === industriaId) || MOCK_INDUSTRIAS[0];
  const modelo = MOCK_DASHBOARDS.competencias;

  function cambiarFacultad(evento) {
    const siguienteFacultad = evento.target.value;
    const siguienteCarrera = MOCK_CARRERAS.find((item) => item.facultad_id === siguienteFacultad);
    setFacultadId(siguienteFacultad);
    if (siguienteCarrera) setCarreraId(siguienteCarrera.id);
  }

  return (
    <div className="fixed inset-0 overflow-y-auto bg-fondo text-ink">
      <header className="sticky top-0 z-30 border-b border-line bg-paper/95 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-[1440px] items-center justify-between gap-4 px-4 sm:px-6 lg:px-8">
          <Link href="/" className="flex min-w-0 items-center gap-3 rounded-xl focus:outline-none focus:ring-2 focus:ring-ulima/40">
            <img src="/logo-ulima.png" alt="Universidad de Lima" className="h-9 w-9 shrink-0 object-contain" />
            <span className="min-w-0">
              <span className="block truncate text-sm font-extrabold tracking-tight text-ink">Dashboard de empleabilidad</span>
              <span className="block truncate text-[10px] font-bold uppercase tracking-[0.13em] text-muted">Universidad de Lima · CIAR</span>
            </span>
          </Link>
          <div className="flex items-center gap-2">
            <span className="hidden rounded-lg bg-ulima/10 px-2.5 py-1.5 text-xs font-bold text-ulima sm:inline">Datos de demostración</span>
            <Link href="/" className="inline-flex items-center gap-1.5 rounded-xl border border-line px-3 py-2 text-xs font-bold text-ink transition hover:border-ulima hover:text-ulima focus:outline-none focus:ring-2 focus:ring-ulima/40"><ArrowLeft size={14} /> Chat</Link>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[1440px] px-4 py-6 sm:px-6 lg:px-8">
        <section className="mb-7">
          <p className="text-xs font-bold uppercase tracking-[0.14em] text-ulima">Información académica y laboral</p>
          <h1 className="mt-2 text-2xl font-extrabold tracking-tight text-ink sm:text-3xl">Panorama de formación y mercado laboral</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-muted">Consulta las tendencias del mercado y su relación con la oferta académica de la Universidad de Lima.</p>
        </section>

        <section aria-label="Filtros del dashboard" className="mb-9 rounded-2xl border border-line bg-paper p-4 shadow-sm sm:p-5">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <Selector etiqueta="Facultad" valor={facultadId} onChange={cambiarFacultad} opciones={MOCK_FACULTADES} />
            <Selector etiqueta="Carrera" valor={carrera.id} onChange={(evento) => setCarreraId(evento.target.value)} opciones={carrerasDeFacultad} />
            <Selector etiqueta="Sector laboral" valor={industriaId} onChange={(evento) => setIndustriaId(evento.target.value)} opciones={MOCK_INDUSTRIAS} />
            <Selector etiqueta="Periodo académico" valor={periodo} onChange={(evento) => setPeriodo(evento.target.value)} opciones={MOCK_PERIODOS} />
          </div>
          <p className="mt-3 text-xs leading-5 text-muted">Los resultados son simulados en esta versión. La cobertura indica presencia declarada en cursos y no mide trayectorias individuales.</p>
        </section>

        <Seccion icono={LineChart} titulo="Panorama general" descripcion="Una lectura rápida de las oportunidades y los conocimientos que aparecen con mayor frecuencia.">
          <div className="grid gap-5 xl:grid-cols-12">
            <TarjetaGrafico titulo="Evolución de oportunidades" descripcion="Comportamiento mensual de las oportunidades del periodo seleccionado." className="xl:col-span-7" accion={<span className="rounded-lg bg-ulima/10 px-2 py-1 text-[11px] font-bold text-ulima">{periodo}</span>}>
              <TendenciaOfertasChart filas={modelo.tendencia} />
            </TarjetaGrafico>
            <TarjetaGrafico titulo="Conocimientos más solicitados" descripcion="Temas que aparecen con mayor frecuencia en las oportunidades analizadas." className="xl:col-span-5">
              <RankingDimensionChart tipo="demanda" filas={modelo.demanda} />
            </TarjetaGrafico>
          </div>
        </Seccion>

        <Seccion icono={GraduationCap} titulo="Formación académica" descripcion={"Cómo se conectan los cursos de " + carrera.nombre + " con las señales de " + industria.nombre.toLowerCase() + "."}>
          <div className="grid gap-5 xl:grid-cols-12">
            <TarjetaGrafico titulo="Temas que requieren atención" descripcion="Compara lo que pide el mercado con la presencia declarada en los cursos." className="xl:col-span-7">
              <BrechaCurriculoMercadoChart filas={modelo.brechas} disponible />
            </TarjetaGrafico>
            <TarjetaGrafico titulo="Cursos con mayor conexión" descripcion="Cursos donde la oferta formativa se relaciona con las señales del mercado." className="xl:col-span-5">
              <BarrasComparativasChart filas={modelo.cursos} series={seriesCursos} />
            </TarjetaGrafico>
          </div>
        </Seccion>

        <Seccion icono={BriefcaseBusiness} titulo="Mercado laboral" descripcion="Empresas y sectores que concentran las oportunidades del periodo seleccionado.">
          <div className="grid gap-5 xl:grid-cols-12">
            <TarjetaGrafico titulo="Top 5 empresas con más oportunidades" descripcion="Empresas con mayor volumen de oportunidades en el escenario de demostración." className="xl:col-span-5">
              <RankingDimensionChart tipo="empresas" filas={modelo.empresasTop} />
            </TarjetaGrafico>
            <TarjetaGrafico titulo="Oportunidades por sector laboral" descripcion="Sectores que reúnen más oportunidades vinculadas al contexto seleccionado." className="xl:col-span-7">
              <RankingDimensionChart tipo="destinos" filas={modelo.destinos} />
            </TarjetaGrafico>
            <TarjetaGrafico titulo="Temas destacados por sector" descripcion="La intensidad muestra qué temas aparecen con mayor presencia en cada sector laboral." className="xl:col-span-12">
              <MatrizIntensidad filas={modelo.perfilSector} columnas={["Digital", "Banca", "Consultoría", "Retail", "Telecom"]} etiquetaBaja="Menor presencia" etiquetaAlta="Mayor presencia" />
            </TarjetaGrafico>
          </div>
        </Seccion>
      </main>
    </div>
  );
}
