"use client";

import Link from "next/link";
import {
  ArrowLeft,
  BriefcaseBusiness,
  Building2,
  GraduationCap,
  LineChart,
} from "lucide-react";
import { useMemo, useState } from "react";
import BarrasComparativasChart from "./BarrasComparativasChart";
import BrechaCurriculoMercadoChart from "./BrechaCurriculoMercadoChart";
import RankingDimensionChart from "./RankingDimensionChart";
import TarjetaGrafico from "./TarjetaGrafico";
import TendenciaOfertasChart from "./TendenciaOfertasChart";
import {
  MOCK_CARRERAS,
  MOCK_DASHBOARDS,
  MOCK_EMPRESAS,
  MOCK_FACULTADES,
  MOCK_FUNCIONES,
  MOCK_INDUSTRIAS,
  MOCK_PERIODOS,
} from "./mockData";

const seriesCursos = [
  { clave: "mercado", etiqueta: "Demanda del mercado", color: "#FF5117" },
  { clave: "curriculo", etiqueta: "Presencia en cursos", color: "#00C5D6" },
];

const seriesVigencia = [
  { clave: "actualizado", etiqueta: "Señales actualizadas", color: "#00C5D6" },
  { clave: "revisar", etiqueta: "Señales para revisar", color: "#FFB000" },
];

const seriesEmpresas = [
  { clave: "referencia", etiqueta: "Empresa de referencia", color: "#FF5117" },
  { clave: "comparada", etiqueta: "Empresa comparada", color: "#00C5D6" },
];

const modeloPorCarrera = {
  sistemas: "competencias",
  industrial: "habilidades",
  administracion: "herramientas",
  comunicacion: "habilidades",
};

function Selector({ etiqueta, valor, onChange, opciones }) {
  return (
    <label className="grid gap-1.5 text-sm font-semibold text-ink">
      {etiqueta}
      <select
        value={valor}
        onChange={onChange}
        className="h-10 rounded-xl border border-line bg-paper px-3 text-sm font-medium text-ink outline-none transition focus:border-ulima focus:ring-2 focus:ring-ulima/20"
      >
        {opciones.map((item) => (
          <option key={item.id || item} value={item.id || item}>
            {item.nombre || item}
          </option>
        ))}
      </select>
    </label>
  );
}

function Seccion({ icono: Icono, titulo, descripcion, children }) {
  return (
    <section className="mb-10">
      <div className="mb-4 flex items-start gap-3">
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-ash text-ulima">
          <Icono size={18} />
        </span>
        <div>
          <h2 className="text-xl font-extrabold tracking-tight text-ink">{titulo}</h2>
          <p className="mt-0.5 text-sm leading-6 text-muted">{descripcion}</p>
        </div>
      </div>
      {children}
    </section>
  );
}

function normalizarRanking(filas, campo, etiqueta = "elemento") {
  return filas.map((fila) => ({
    elemento: fila[etiqueta],
    ofertas: fila[campo],
  }));
}

export default function Dashboard() {
  const [facultadId, setFacultadId] = useState(MOCK_FACULTADES[0].id);
  const [carreraId, setCarreraId] = useState(MOCK_CARRERAS[0].id);
  const [industriaId, setIndustriaId] = useState(MOCK_INDUSTRIAS[0].id);
  const [periodo, setPeriodo] = useState(MOCK_PERIODOS[0]);
  const [empresaReferenciaId, setEmpresaReferenciaId] = useState(MOCK_EMPRESAS[0].id);
  const [empresaComparadaId, setEmpresaComparadaId] = useState(MOCK_EMPRESAS[1].id);
  const [funcionId, setFuncionId] = useState(MOCK_FUNCIONES[0].id);

  const carrerasDeFacultad = useMemo(
    () => MOCK_CARRERAS.filter((item) => item.facultad_id === facultadId),
    [facultadId],
  );
  const carrera = MOCK_CARRERAS.find((item) => item.id === carreraId)
    || carrerasDeFacultad[0]
    || MOCK_CARRERAS[0];
  const industria = MOCK_INDUSTRIAS.find((item) => item.id === industriaId) || MOCK_INDUSTRIAS[0];
  const empresaReferencia = MOCK_EMPRESAS.find((item) => item.id === empresaReferenciaId) || MOCK_EMPRESAS[0];
  const empresaComparada = MOCK_EMPRESAS.find((item) => item.id === empresaComparadaId) || MOCK_EMPRESAS[1];
  const funcion = MOCK_FUNCIONES.find((item) => item.id === funcionId) || MOCK_FUNCIONES[0];
  const modelo = MOCK_DASHBOARDS[modeloPorCarrera[carrera.id] || "competencias"];

  const carrerasPorDemanda = normalizarRanking(modelo.carreras, "indice");
  const industriasPorCarrera = modelo.industrias.map((fila) => ({
    elemento: fila.industria,
    oportunidades: fila.ofertas,
  }));
  const coberturaCurricular = modelo.cobertura;
  const funcionesPorTipoEmpresa = modelo.destinos;
  const diferenciadores = modelo.diferenciadores.map((fila) => ({
    ...fila,
    referencia: fila.referencia,
    comparada: fila.comparada,
  }));

  function cambiarFacultad(evento) {
    const siguienteFacultad = evento.target.value;
    const siguienteCarrera = MOCK_CARRERAS.find((item) => item.facultad_id === siguienteFacultad);

    setFacultadId(siguienteFacultad);
    if (siguienteCarrera) setCarreraId(siguienteCarrera.id);
  }

  function cambiarEmpresaReferencia(evento) {
    const siguienteEmpresa = evento.target.value;
    setEmpresaReferenciaId(siguienteEmpresa);
    if (siguienteEmpresa === empresaComparadaId) {
      const alternativa = MOCK_EMPRESAS.find((item) => item.id !== siguienteEmpresa);
      if (alternativa) setEmpresaComparadaId(alternativa.id);
    }
  }

  function cambiarEmpresaComparada(evento) {
    const siguienteEmpresa = evento.target.value;
    setEmpresaComparadaId(siguienteEmpresa);
    if (siguienteEmpresa === empresaReferenciaId) {
      const alternativa = MOCK_EMPRESAS.find((item) => item.id !== siguienteEmpresa);
      if (alternativa) setEmpresaReferenciaId(alternativa.id);
    }
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
            <Link href="/" className="inline-flex items-center gap-1.5 rounded-xl border border-line px-3 py-2 text-xs font-bold text-ink transition hover:border-ulima hover:text-ulima focus:outline-none focus:ring-2 focus:ring-ulima/40">
              <ArrowLeft size={14} /> Chat
            </Link>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[1440px] px-4 py-6 sm:px-6 lg:px-8">
        <section className="mb-7">
          <p className="text-xs font-bold uppercase tracking-[0.14em] text-ulima">Información académica y laboral</p>
          <h1 className="mt-2 text-2xl font-extrabold tracking-tight text-ink sm:text-3xl">Tendencias de empleabilidad y formación</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-muted">
            Empezá con una lectura macro del mercado y profundizá con filtros por facultad, carrera, industria, empresa y función.
          </p>
        </section>

        <section aria-label="Filtros del dashboard" className="mb-9 rounded-2xl border border-line bg-paper p-4 shadow-sm sm:p-5">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <Selector etiqueta="Facultad" valor={facultadId} onChange={cambiarFacultad} opciones={MOCK_FACULTADES} />
            <Selector etiqueta="Carrera" valor={carrera.id} onChange={(evento) => setCarreraId(evento.target.value)} opciones={carrerasDeFacultad} />
            <Selector etiqueta="Industria" valor={industriaId} onChange={(evento) => setIndustriaId(evento.target.value)} opciones={MOCK_INDUSTRIAS} />
            <Selector etiqueta="Periodo" valor={periodo} onChange={(evento) => setPeriodo(evento.target.value)} opciones={MOCK_PERIODOS} />
            <Selector etiqueta="Empresa de referencia" valor={empresaReferencia.id} onChange={cambiarEmpresaReferencia} opciones={MOCK_EMPRESAS} />
            <Selector etiqueta="Empresa comparada" valor={empresaComparada.id} onChange={cambiarEmpresaComparada} opciones={MOCK_EMPRESAS} />
            <Selector etiqueta="Función" valor={funcion.id} onChange={(evento) => setFuncionId(evento.target.value)} opciones={MOCK_FUNCIONES} />
          </div>
          <p className="mt-3 text-xs leading-5 text-muted">
            Esta pantalla usa datos de demostración. La versión conectada ejecutará las consultas generales para la vista macro y las específicas cuando se apliquen filtros.
          </p>
        </section>

        <Seccion icono={LineChart} titulo="Panorama laboral" descripcion="Responde dónde está la demanda, cómo evoluciona y qué conocimientos concentra el mercado.">
          <div className="grid gap-5 xl:grid-cols-12">
            <TarjetaGrafico titulo="¿Cómo evolucionan las ofertas laborales?" descripcion="Volumen mensual de oportunidades para el período seleccionado." className="xl:col-span-6" accion={<span className="rounded-lg bg-ulima/10 px-2 py-1 text-[11px] font-bold text-ulima">{periodo}</span>}>
              <TendenciaOfertasChart filas={modelo.tendencia} />
            </TarjetaGrafico>
            <TarjetaGrafico titulo="¿Qué carreras concentran mayor demanda?" descripcion="Ranking de carreras según las oportunidades vinculadas." className="xl:col-span-6">
              <RankingDimensionChart tipo="demanda" filas={carrerasPorDemanda} />
            </TarjetaGrafico>
            <TarjetaGrafico titulo={`¿En qué industrias se publican ofertas para ${carrera.nombre}?`} descripcion="Sectores laborales con mayor cantidad de oportunidades para la carrera seleccionada." className="xl:col-span-6">
              <RankingDimensionChart tipo="destinos" filas={industriasPorCarrera} />
            </TarjetaGrafico>
            <TarjetaGrafico titulo="¿Qué conocimientos demanda más el mercado?" descripcion="Conocimientos con mayor presencia en las ofertas analizadas." className="xl:col-span-6">
              <RankingDimensionChart tipo="demanda" filas={modelo.demanda} />
            </TarjetaGrafico>
          </div>
        </Seccion>

        <Seccion icono={GraduationCap} titulo="Alineación curricular" descripcion={`Muestra cómo ${carrera.nombre} se relaciona con las señales de ${industria.nombre.toLowerCase()}.`}>
          <div className="grid gap-5 xl:grid-cols-12">
            <TarjetaGrafico titulo="¿Qué conocimientos ya cubre el currículo?" descripcion="Presencia de conocimientos en los cursos de la carrera seleccionada." className="xl:col-span-6">
              <RankingDimensionChart tipo="cobertura" filas={coberturaCurricular} />
            </TarjetaGrafico>
            <TarjetaGrafico titulo="¿Qué conocimientos demandados presentan una brecha?" descripcion="Comparación entre la demanda laboral y la presencia declarada en cursos." className="xl:col-span-6">
              <BrechaCurriculoMercadoChart filas={modelo.brechas} disponible />
            </TarjetaGrafico>
            <TarjetaGrafico titulo="¿Qué cursos requieren revisar su vigencia?" descripcion="Señales de actualización frente a señales que requieren revisión." className="xl:col-span-6">
              <BarrasComparativasChart filas={modelo.vigencia} series={seriesVigencia} />
            </TarjetaGrafico>
            <TarjetaGrafico titulo="¿Qué cursos tienen mayor correspondencia con el mercado?" descripcion="Cursos donde la oferta formativa se conecta con las señales de demanda." className="xl:col-span-6">
              <BarrasComparativasChart filas={modelo.cursos} series={seriesCursos} />
            </TarjetaGrafico>
          </div>
        </Seccion>

        <Seccion icono={BriefcaseBusiness} titulo="Empresas y funciones" descripcion="Permite contrastar empresas y entender los conocimientos y funciones que demandan.">
          <div className="grid gap-5 xl:grid-cols-12">
            <TarjetaGrafico titulo="¿Qué empresas concentran oportunidades y conocimientos?" descripcion="Empresas con mayor volumen de oportunidades en el contexto seleccionado." className="xl:col-span-6">
              <RankingDimensionChart tipo="empresas" filas={modelo.empresasTop} />
            </TarjetaGrafico>
            <TarjetaGrafico titulo={`¿Qué conocimientos diferencian a ${empresaReferencia.nombre} de ${empresaComparada.nombre}?`} descripcion="Comparación de presencia de conocimientos entre las empresas seleccionadas." className="xl:col-span-6">
              <BarrasComparativasChart filas={diferenciadores} series={seriesEmpresas} />
            </TarjetaGrafico>
            <TarjetaGrafico titulo={`¿Cuáles son los conocimientos núcleo para ${funcion.nombre}?`} descripcion="Conocimientos más conectados con las oportunidades de la función seleccionada." className="xl:col-span-6">
              <RankingDimensionChart tipo="demanda" filas={modelo.demanda} />
            </TarjetaGrafico>
            <TarjetaGrafico titulo={`¿Cómo varían las funciones para ${carrera.nombre} según el tipo de empresa?`} descripcion="Funciones con mayor presencia por tipo o sector de empresa." className="xl:col-span-6">
              <RankingDimensionChart tipo="destinos" filas={funcionesPorTipoEmpresa} />
            </TarjetaGrafico>
          </div>
        </Seccion>

        <section className="mb-8 rounded-2xl border border-line bg-ash/50 p-4 text-sm leading-6 text-muted">
          <div className="flex items-start gap-3">
            <Building2 className="mt-0.5 shrink-0 text-ulima" size={18} />
            <p>
              Las visualizaciones corresponden a las 12 preguntas del catálogo validado. Cada una tendrá una vista general y, cuando aplique, una vista específica según los filtros elegidos.
            </p>
          </div>
        </section>
      </main>
    </div>
  );
}
