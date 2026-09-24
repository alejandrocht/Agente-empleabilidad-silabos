import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import InspeccionEjecucionNormalizador, {
  parseCsvPreview,
} from "./InspeccionEjecucionNormalizador";
import {
  cancelarEjecucionNormalizador,
  decidirPendientesNormalizador,
  obtenerPendientesNormalizador,
  obtenerReporteEjecucionNormalizador,
  obtenerUrlOutputNormalizador,
  obtenerUrlReporteEjecucionNormalizador,
} from "../api/normalizador";

vi.mock("../api/normalizador", () => ({
  cancelarEjecucionNormalizador: vi.fn(),
  decidirPendientesNormalizador: vi.fn(),
  obtenerPendientesNormalizador: vi.fn(),
  obtenerReporteEjecucionNormalizador: vi.fn(),
  obtenerUrlOutputNormalizador: vi.fn(
    (id, archivo) => `/outputs/${id}/${archivo}`,
  ),
  obtenerUrlReporteEjecucionNormalizador: vi.fn((id) => `/reports/${id}`),
}));

vi.mock("../api/neo4j", () => ({
  importarEnNeo4j: vi.fn(),
  listarImportacionesNeo4j: vi.fn().mockResolvedValue({ importaciones: [] }),
  revertirImportacionNeo4j: vi.fn(),
  validarImportacionNeo4j: vi.fn(),
}));

const ARCHIVOS_TECNICOS = [
  "curso.csv",
  "silabo.csv",
  "catalogo_competencias.csv",
  "catalogo_habilidades.csv",
  "catalogo_logros.csv",
  "cobertura_curricular.csv",
];

function salidasTecnicas(archivos = ARCHIVOS_TECNICOS) {
  return archivos.map((archivo) => ({
    archivo: `salidas/${archivo}`,
    tipo: "csv_curricular",
    registros: 1,
  }));
}

function reporteEnCurso(id, hitl) {
  return {
    manifest: {
      id_ejecucion: id,
      estado: "normalizando",
      parametros: {
        carrera: "Marketing",
        periodo: "2026-1",
        ...(hitl === undefined ? {} : { hitl }),
      },
    },
    reportes: {},
  };
}

function reporteTecnico({
  id = "NOR_TECHNICAL",
  outputs = salidasTecnicas(),
  decision = "ALLOW_IMPORT",
} = {}) {
  return {
    manifest: {
      id_ejecucion: id,
      tipo: "silabos",
      estado: "limpiado",
      configuracion_curricular: { modo_analista: "technical" },
      parametros: { carrera: "Marketing", periodo: "2026-1" },
      release_gate: { decision },
      outputs,
    },
    reportes: {},
  };
}

describe("inspección de ejecución normalizada", () => {
  it("mantiene la navegación al normalizador mientras carga", () => {
    obtenerReporteEjecucionNormalizador.mockImplementationOnce(
      () => new Promise(() => {}),
    );

    render(<InspeccionEjecucionNormalizador idEjecucion="NOR_LOADING" />);

    const navegacion = screen.getByRole("navigation", {
      name: "Navegación de ejecución",
    });
    const enlace = within(navegacion).getByRole("link", {
      name: "Volver al normalizador",
    });
    expect(enlace.getAttribute("href")).toBe("/normalizador");
  });

  it("mantiene la navegación al normalizador cuando falla la carga", async () => {
    obtenerReporteEjecucionNormalizador.mockRejectedValueOnce(
      new Error("No se pudo cargar"),
    );

    render(<InspeccionEjecucionNormalizador idEjecucion="NOR_ERROR" />);

    expect(await screen.findByRole("alert")).toBeTruthy();
    const navegacion = screen.getByRole("navigation", {
      name: "Navegación de ejecución",
    });
    expect(
      within(navegacion)
        .getByRole("link", { name: "Volver al normalizador" })
        .getAttribute("href"),
    ).toBe("/normalizador");
  });

  it("mantiene la navegación al normalizador después de cargar", async () => {
    render(<InspeccionEjecucionNormalizador idEjecucion="NOR_READY" />);

    await screen.findByRole("heading", {
      name: "Inspección técnica curricular",
    });
    const navegacion = screen.getByRole("navigation", {
      name: "Navegación de ejecución",
    });
    expect(
      within(navegacion)
        .getByRole("link", { name: "Volver al normalizador" })
        .getAttribute("href"),
    ).toBe("/normalizador");
  });

  it.each([1, "1"])(
    "indica de forma accesible que la revisión técnica humana está activa para HITL=%s",
    async (hitl) => {
      obtenerReporteEjecucionNormalizador.mockResolvedValueOnce(
        reporteEnCurso("NOR_HITL_ON", hitl),
      );

      render(<InspeccionEjecucionNormalizador idEjecucion="NOR_HITL_ON" />);

      expect(
        (await screen.findByLabelText("Estado de revisión técnica humana"))
          .textContent,
      ).toBe("Revisión técnica humana: activa.");
    },
  );

  it.each([0, "0"])(
    "indica cuando las decisiones técnicas son automáticas para HITL=%s",
    async (hitl) => {
      obtenerReporteEjecucionNormalizador.mockResolvedValueOnce(
        reporteEnCurso("NOR_HITL_OFF", hitl),
      );

      render(<InspeccionEjecucionNormalizador idEjecucion="NOR_HITL_OFF" />);

      expect(
        (await screen.findByLabelText("Estado de revisión técnica humana"))
          .textContent,
      ).toBe(
        "Revisión técnica humana: desactivada; decisiones técnicas automáticas.",
      );
    },
  );

  it.each([undefined, null, 2, "2", " 1"])(
    "no inventa un estado HITL para el valor %s",
    async (hitl) => {
      obtenerReporteEjecucionNormalizador.mockResolvedValueOnce(
        reporteEnCurso("NOR_HITL_UNKNOWN", hitl),
      );

      render(
        <InspeccionEjecucionNormalizador idEjecucion="NOR_HITL_UNKNOWN" />,
      );

      await screen.findByRole("heading", {
        name: "Inspección técnica curricular",
      });
      expect(
        screen.queryByLabelText("Estado de revisión técnica humana"),
      ).toBeNull();
    },
  );

  it("no deja que una cancelación pendiente de A oculte la acción de B", async () => {
    let resolverCancelacion;
    cancelarEjecucionNormalizador.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolverCancelacion = resolve;
        }),
    );
    obtenerReporteEjecucionNormalizador.mockImplementation((id) =>
      Promise.resolve(reporteEnCurso(id, 0)),
    );

    const { rerender } = render(
      <InspeccionEjecucionNormalizador idEjecucion="NOR_A" />,
    );
    const botonCancelarA = await screen.findByRole("button", {
      name: "Cancelar ejecución",
    });
    fireEvent.click(botonCancelarA);
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Enviando solicitud…" }).disabled,
      ).toBe(true),
    );

    rerender(<InspeccionEjecucionNormalizador idEjecucion="NOR_B" />);

    const botonCancelarB = await screen.findByRole("button", {
      name: "Cancelar ejecución",
    });
    expect(botonCancelarB.disabled).toBe(false);
    resolverCancelacion({ cancelacion_solicitada: true });
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Cancelar ejecución" }).disabled,
      ).toBe(false),
    );
  });

  beforeEach(() => {
    vi.clearAllMocks();
    obtenerReporteEjecucionNormalizador.mockResolvedValue({
      manifest: {
        id_ejecucion: "NOR_0123456789abcdef",
        tipo: "silabos",
        estado: "limpiado",
        configuracion_curricular: { modo_analista: "technical" },
        parametros: { carrera: "Marketing", periodo: "2026-1" },
        validacion_silabos: { valida: true },
        release_gate: { decision: "ALLOW_IMPORT" },
        outputs: salidasTecnicas(),
        hallazgos: [
          {
            codigo: "ARCHIVO_NO_CURRICULAR",
            severidad: "warning",
            mensaje: "Se omitió un archivo accesorio.",
          },
        ],
        progreso_llm: {
          eventos: [
            {
              secuencia: 1,
              fase: "completado",
              mensaje: "Reporte LLM disponible.",
            },
          ],
        },
      },
      reportes: {},
    });
    obtenerPendientesNormalizador.mockResolvedValue({
      filas: [],
      aprobacion: null,
    });
    decidirPendientesNormalizador.mockResolvedValue({ aprobacion: null });
    cancelarEjecucionNormalizador.mockResolvedValue({
      cancelacion_solicitada: true,
    });
    vi.stubGlobal(
      "confirm",
      vi.fn(() => true),
    );
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async (_url) => ({
        ok: true,
        text: async () => {
          return "id_requerimiento,descripcion\nREQ_1,Analizar datos\n";
        },
      })),
    );
  });

  it("reconoce el contrato técnico de seis CSV antes de habilitar Neo4j", async () => {
    obtenerReporteEjecucionNormalizador.mockResolvedValueOnce(reporteTecnico());

    render(<InspeccionEjecucionNormalizador idEjecucion="NOR_TECHNICAL" />);

    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(6));
    expect(
      screen.getByRole("heading", { name: "Inspección técnica curricular" }),
    ).toBeTruthy();
    await waitFor(() =>
      expect(
        screen.getByRole("tab", { name: "CSV" }).getAttribute("aria-selected"),
      ).toBe("true"),
    );
    expect(screen.getByText("curso.csv")).toBeTruthy();
    expect(screen.getByText("silabo.csv")).toBeTruthy();
    expect(screen.getByText("catalogo_habilidades.csv")).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "Descargar catalogo_habilidades.csv" }),
    ).toBeTruthy();
    fireEvent.click(screen.getByRole("tab", { name: "Progreso" }));
    expect(screen.getByText("cursos")).toBeTruthy();
    expect(screen.getByText("competencias técnicas")).toBeTruthy();
    fireEvent.click(screen.getByRole("tab", { name: "Neo4j" }));
    expect(
      await screen.findByRole("button", { name: "Subir datos a Neo4j" }),
    ).toBeTruthy();
  });

  it("bloquea Neo4j cuando falta catalogo_habilidades.csv aunque existan los otros cinco", async () => {
    const idEjecucion = "NOR_MISSING_SKILLS";
    obtenerReporteEjecucionNormalizador.mockResolvedValueOnce(
      reporteTecnico({ id: idEjecucion, outputs: salidasTecnicas(ARCHIVOS_TECNICOS.filter((archivo) => archivo !== "catalogo_habilidades.csv")) }),
    );

    render(<InspeccionEjecucionNormalizador idEjecucion={idEjecucion} />);

    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(5));
    fireEvent.click(await screen.findByRole("tab", { name: "Neo4j" }));
    expect(screen.queryByRole("button", { name: "Subir datos a Neo4j" })).toBeNull();
    expect(screen.getByText(/release gate todavía no certifica/i)).toBeTruthy();
  });

  it("muestra borradores CSV descargables sin habilitar importación cuando no_publicado", async () => {
    const idEjecucion = "NOR_BLOCKED_DRAFTS";
    obtenerReporteEjecucionNormalizador.mockResolvedValueOnce({
      manifest: {
        id_ejecucion: idEjecucion,
        tipo: "silabos",
        estado: "no_publicado",
        outputs: [],
        draft_outputs: salidasTecnicas().map((salida) => ({ ...salida, borrador: true })),
        release_gate: {
          decision: "BLOCK_IMPORT",
          blockers: ["TECHNICAL_ANALYSIS_INCOMPLETE", "UNLINKED_SOURCE_OUTCOME"],
        },
      },
      reportes: {},
    });

    render(<InspeccionEjecucionNormalizador idEjecucion={idEjecucion} />);
    fireEvent.click(await screen.findByRole("tab", { name: "CSV" }));

    expect(await screen.findByText(/borradores.*no son\s+importables/i)).toBeTruthy();
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(6));
    expect(screen.getAllByRole("columnheader", { name: "id_requerimiento" })).toHaveLength(6);
    for (const nombre of ARCHIVOS_TECNICOS) {
      expect(screen.getByRole("link", { name: `Descargar ${nombre}` })).toBeTruthy();
    }
    fireEvent.click(screen.getByRole("tab", { name: "Neo4j" }));
    expect(screen.queryByRole("button", { name: "Subir datos a Neo4j" })).toBeNull();
  });

  it("explica el bloqueo técnico sin inventar decisiones humanas pendientes", async () => {
    const idEjecucion = "NOR_TECHNICAL_ANALYSIS_FAILED";
    obtenerReporteEjecucionNormalizador.mockResolvedValueOnce({
      manifest: {
        id_ejecucion: idEjecucion,
        tipo: "silabos",
        estado: "no_publicado",
        parametros: { carrera: "Marketing", periodo: "2026-1" },
        limpieza_silabos: { publicable: false, outputs: [] },
        release_gate: {
          decision: "BLOCK_IMPORT",
          blockers: ["TECHNICAL_ANALYSIS_FAILED"],
          checks: {
            deterministic_outputs: { ok: true },
            analysis: { ok: false, state: "FALLBACK_DETERMINISTA" },
            approval: { ok: true, pending_count: 0 },
          },
        },
        hallazgos: [
          {
            codigo: "ANALISTA_TECNICO_NO_DISPONIBLE",
            severidad: "warning",
            mensaje: "El analista técnico no estuvo disponible.",
          },
        ],
      },
      reportes: {
        "analisis_tecnico.json": {
          estado: "FALLBACK_DETERMINISTA",
          propuestas_pendientes: 0,
        },
        "propuestas_tecnicas.jsonl": [],
      },
    });

    render(<InspeccionEjecucionNormalizador idEjecucion={idEjecucion} />);

    expect(
      await screen.findByText(
        "El análisis técnico no estuvo disponible; la publicación quedó bloqueada por el release gate.",
      ),
    ).toBeTruthy();
    fireEvent.click(screen.getByRole("tab", { name: "Revisión" }));
    expect(
      screen.getByText("No hay decisiones humanas pendientes para esta ejecución."),
    ).toBeTruthy();
    expect(screen.queryByText(/Resolver .* decisión curricular/)).toBeNull();
  });

  it("activa Revisión cuando el release gate reporta pending_count sin resumen de aprobación", async () => {
    const idEjecucion = "NOR_APPROVAL_PENDING_COUNT";
    obtenerReporteEjecucionNormalizador.mockResolvedValueOnce({
      manifest: {
        id_ejecucion: idEjecucion,
        tipo: "silabos",
        estado: "limpiado",
        parametros: { carrera: "Marketing", periodo: "2026-1" },
        release_gate: {
          decision: "BLOCK_IMPORT",
          checks: { approval: { pending_count: 2 } },
        },
      },
      reportes: {},
    });
    obtenerPendientesNormalizador.mockResolvedValueOnce({
      filas: [],
      aprobacion: null,
    });

    render(<InspeccionEjecucionNormalizador idEjecucion={idEjecucion} />);

    await waitFor(() =>
      expect(
        screen.getByRole("tab", { name: "Revisión" }).getAttribute("aria-selected"),
      ).toBe("true"),
    );
  });

  it("prefiere el resumen de aprobación resuelto sobre propuestas técnicas legadas y abre CSV", async () => {
    const idEjecucion = "NOR_TECHNICAL_RESOLVED";
    obtenerReporteEjecucionNormalizador.mockResolvedValueOnce({
      ...reporteTecnico({ id: idEjecucion }),
      manifest: {
        ...reporteTecnico({ id: idEjecucion }).manifest,
        aprobacion_curricular: {
          requiere_decision: false,
          pendientes_por_decidir: 0,
          remaining_pending: 0,
          release_gate: { decision: "ALLOW_IMPORT", blockers: [] },
          materializacion: { csv_canonicos_disponibles: true },
        },
      },
      reportes: {
        "propuestas_tecnicas.jsonl": [
          { id_propuesta: "PROP_LEGACY", estado: "PENDIENTE" },
        ],
      },
    });
    obtenerPendientesNormalizador.mockResolvedValueOnce({
      filas: [],
      aprobacion: {
        requiere_decision: false,
        pendientes_por_decidir: 0,
        remaining_pending: 0,
      },
    });

    render(<InspeccionEjecucionNormalizador idEjecucion={idEjecucion} />);

    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(6));
    await waitFor(() =>
      expect(
        screen.getByRole("tab", { name: "CSV" }).getAttribute("aria-selected"),
      ).toBe("true"),
    );
    expect(
      screen.queryByRole("heading", { name: "Revisión técnica requerida" }),
    ).toBeNull();
  });

  it("muestra el checkpoint humano histórico y explica por qué no habilita Neo4j sin CSV canónicos", async () => {
    const idEjecucion = "NOR_b468b1fb2b9c4268";
    obtenerReporteEjecucionNormalizador.mockResolvedValueOnce({
      manifest: {
        id_ejecucion: idEjecucion,
        tipo: "silabos",
        estado: "limpiado_con_advertencias",
        parametros: { carrera: "Marketing", periodo: "2026-1" },
        limpieza_silabos: {
          outputs: [
            {
              archivo: "salidas/reportes/propuestas_tecnicas.jsonl",
              tipo: "propuestas_tecnicas",
              registros: 174,
            },
            {
              archivo: "salidas/reportes/release_gate.json",
              tipo: "release_gate",
              registros: 1,
            },
          ],
        },
        aprobacion_curricular: {
          requiere_decision: true,
          pendientes_por_decidir: 174,
          remaining_pending: 174,
          materializacion: { csv_canonicos_disponibles: false },
        },
        release_gate: {
          decision: "BLOCK_IMPORT",
          blockers: ["PENDING_DECISIONS", "CANONICAL_MATERIALIZATION_PENDING"],
          checks: {
            approval: { pending_decision: 174, canonical_materialized: false },
          },
        },
      },
      reportes: {},
    });
    obtenerPendientesNormalizador.mockResolvedValueOnce({
      filas: [
        {
          id_pendiente: "PEND_1",
          tipo: "competencia_tecnica",
          propuesta: {
            nombre: "Analítica digital",
            descripcion: "Propuesta curricular",
          },
          evidencia: ["Evidencia del sílabo"],
        },
      ],
      aprobacion: {
        requiere_decision: true,
        pendientes_por_decidir: 174,
        remaining_pending: 174,
      },
    });

    render(<InspeccionEjecucionNormalizador idEjecucion={idEjecucion} />);

    expect(
      await screen.findByRole("heading", {
        name: "Revisión técnica requerida",
      }),
    ).toBeTruthy();
    expect(
      screen.getByRole("button", {
        name: /Agregar al catálogo para Analítica digital/i,
      }),
    ).toBeTruthy();
    expect(
      screen.queryByRole("button", { name: "Subir datos a Neo4j" }),
    ).toBeNull();
    expect(
      screen
        .getByRole("tab", { name: "Revisión" })
        .getAttribute("aria-selected"),
    ).toBe("true");
    expect(
      within(screen.getByRole("tabpanel", { name: "Revisión" })).getByText(
        "174",
        { exact: true },
      ),
    ).toBeTruthy();
    expect(
      screen.queryByRole("heading", { name: "Qué falta para publicar" }),
    ).toBeNull();
    expect(
      screen.queryByText("Resolver 174 decisiones curriculares"),
    ).toBeNull();
    expect(screen.queryByText(/CSV listos con advertencias/i)).toBeNull();
  });

  it("mantiene Neo4j bloqueado aunque existan tres CSV cuando quedan decisiones sin resolver", async () => {
    const idEjecucion = "NOR_BLOCKED_CSV123456";
    obtenerReporteEjecucionNormalizador.mockResolvedValueOnce({
      manifest: {
        id_ejecucion: idEjecucion,
        tipo: "silabos",
        estado: "limpiado",
        parametros: { carrera: "Marketing", periodo: "2026-1" },
        validacion_silabos: { valida: true },
        limpieza_silabos: {
          outputs: [
            {
              archivo: "salidas/catalogo_competencias.csv",
              tipo: "csv_curricular",
              registros: 1,
            },
            {
              archivo: "salidas/catalogo_logros.csv",
              tipo: "csv_curricular",
              registros: 1,
            },
            {
              archivo: "salidas/cobertura_curricular.csv",
              tipo: "csv_curricular",
              registros: 1,
            },
          ],
        },
        aprobacion_curricular: {
          requiere_decision: true,
          pendientes_por_decidir: 1,
          materializacion: { csv_canonicos_disponibles: false },
        },
        release_gate: {
          decision: "BLOCK_IMPORT",
          blockers: ["PENDING_DECISIONS"],
          checks: {
            approval: { pending_decision: 1, canonical_materialized: false },
          },
        },
      },
      reportes: {},
    });
    obtenerPendientesNormalizador.mockResolvedValueOnce({
      filas: [
        {
          id_pendiente: "PEND_BLOCKED",
          tipo: "competencia_tecnica",
          propuesta: { nombre: "Habilidad pendiente" },
        },
      ],
      aprobacion: { requiere_decision: true, pendientes_por_decidir: 1 },
    });

    render(<InspeccionEjecucionNormalizador idEjecucion={idEjecucion} />);

    expect(
      await screen.findByRole("heading", {
        name: "Revisión técnica requerida",
      }),
    ).toBeTruthy();
    expect(
      screen.queryByRole("button", { name: "Subir datos a Neo4j" }),
    ).toBeNull();
    expect(
      screen.queryByRole("heading", { name: "Qué falta para publicar" }),
    ).toBeNull();
    expect(screen.queryByText("Resolver 1 decisión curricular")).toBeNull();
    expect(screen.queryByRole("tab", { name: "Logs" })).toBeNull();
    expect(screen.queryByText("BLOCK_IMPORT")).toBeNull();
    expect(screen.queryByText("PENDING_DECISIONS")).toBeNull();
    expect(screen.queryByRole("tabpanel", { name: "Logs" })).toBeNull();
  });

  it("tolera hallazgos malformados en reportes legados sin renderizar logs internos", async () => {
    obtenerReporteEjecucionNormalizador.mockResolvedValueOnce({
      manifest: {
        id_ejecucion: "NOR_TECHNICAL_SHAPES",
        tipo: "silabos",
        configuracion_curricular: { modo_analista: "technical" },
        estado: "limpiado",
        carrera: "Marketing legacy",
        periodo: "2025-2",
        hallazgos: [
          null,
          {
            codigo: "LEGACY_WARNING",
            severidad: "warning",
            mensaje: "Advertencia legada.",
          },
        ],
      },
      reportes: {
        "decisiones_llm.jsonl": [
          null,
          { estado: "ACEPTADA", justificacion: "Decisión legada." },
        ],
        eventos_llm: {
          eventos: [null, { fase: "legacy", mensaje: "Evento legado." }],
        },
      },
    });

    render(
      <InspeccionEjecucionNormalizador idEjecucion="NOR_TECHNICAL_SHAPES" />,
    );

    await screen.findByRole("tab", { name: "Auditoría" });
    expect(screen.queryByText("Decisión legada.")).toBeNull();
    expect(screen.queryByText("Evento legado.")).toBeNull();
    fireEvent.click(screen.getByRole("tab", { name: "Auditoría" }));
    const warnings = screen.getByRole("tabpanel", {
      name: "Auditoría",
    });
    expect(within(warnings).getByText("Advertencia legada.")).toBeTruthy();
  });

  it("expone solo las vistas humanas y mantiene los artefactos técnicos fuera del frontend", async () => {
    render(
      <InspeccionEjecucionNormalizador idEjecucion="NOR_0123456789abcdef" />,
    );

    const tablist = await screen.findByRole("tablist", {
      name: "Secciones de la inspección",
    });
    expect(within(tablist).getAllByRole("tab")).toHaveLength(5);
    fireEvent.click(screen.getByRole("tab", { name: "CSV" }));
    const csv = screen.getByRole("tabpanel", { name: "CSV" });
    expect(csv.hidden).toBe(false);
    expect(
      within(csv).getByRole("heading", { name: "Archivos CSV" }),
    ).toBeTruthy();
    expect(within(csv).getByText("curso.csv")).toBeTruthy();
    expect(
      within(csv).getByRole("link", {
        name: /Descargar curso\.csv/,
      }),
    ).toBeTruthy();
    expect(within(csv).queryByText("Decisiones LLM aceptadas")).toBeNull();
    expect(
      screen.getByRole("tab", { name: "CSV" }).getAttribute("aria-selected"),
    ).toBe("true");
    expect(screen.queryByRole("tab", { name: "Logs" })).toBeNull();
    expect(screen.queryByRole("tabpanel", { name: "Logs" })).toBeNull();
    expect(screen.queryByText("Salidas generadas")).toBeNull();
    expect(screen.queryByText("Logs y eventos")).toBeNull();
  });

  it("agrupa hallazgos accionables desde el payload y no duplica la extracción cactus incompleta", async () => {
    obtenerReporteEjecucionNormalizador.mockResolvedValueOnce({
      manifest: {
        id_ejecucion: "NOR_GROUPED_FINDINGS",
        tipo: "silabos",
        estado: "limpiado_con_advertencias",
        hallazgos: [
          {
            codigo: "LOGRO_CODIGO_INCONSISTENTE",
            severidad: "warning",
            mensaje: "Código distinto.",
          },
          {
            codigo: "COMPETENCIA_REFERENCIADA_NO_DECLARADA",
            severidad: "error",
            mensaje: "Falta declaración.",
          },
          {
            codigo: "COMPETENCIA_DECLARADA_SIN_LOGRO",
            severidad: "warning",
            mensaje: "Falta logro.",
          },
          {
            codigo: "EXTRACCION_CACTUS_INCOMPLETA",
            severidad: "warning",
            mensaje: "Extracción parcial.",
          },
        ],
      },
      reportes: {
        "extraccion_cactus.json": {
          errores: [
            {
              codigo: "CACTUS_SIN_SILABO",
              mensaje: "No se descargó el sílabo del curso 1.",
            },
            {
              codigo: "CACTUS_SIN_SILABO",
              mensaje: "No se descargó el sílabo del curso 2.",
            },
          ],
        },
      },
    });

    render(
      <InspeccionEjecucionNormalizador idEjecucion="NOR_GROUPED_FINDINGS" />,
    );
    fireEvent.click(await screen.findByRole("tab", { name: "Auditoría" }));

    const panel = screen.getByRole("tabpanel", {
      name: "Auditoría",
    });
    const logros = within(panel)
      .getByRole("heading", { name: "Logros tienen un código inconsistente" })
      .closest("article");
    const competencias = within(panel)
      .getByRole("heading", { name: "Inconsistencias en competencias" })
      .closest("article");
    const cactus = within(panel)
      .getByRole("heading", { name: "Cursos sin sílabo descargable" })
      .closest("article");
    expect(within(logros).getByText("1 aviso")).toBeTruthy();
    expect(within(competencias).getByText("2 avisos")).toBeTruthy();
    expect(within(cactus).getByText("2 avisos")).toBeTruthy();
    expect(cactus.className).toContain("border-line");
    expect(
      within(competencias).getByText("Competencia referenciada no declarada"),
    ).toBeTruthy();
    expect(
      within(competencias).getByText("Competencia declarada sin logro"),
    ).toBeTruthy();
    expect(
      within(cactus).queryByText("EXTRACCION_CACTUS_INCOMPLETA"),
    ).toBeNull();
    expect(
      within(panel).queryByRole("heading", {
        name: "Otros avisos registrados",
      }),
    ).toBeNull();
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("muestra resultados positivos, conteos y alertas sin exponer artefactos técnicos", async () => {
    render(
      <InspeccionEjecucionNormalizador idEjecucion="NOR_0123456789abcdef" />,
    );

    expect(await screen.findByText("Inspección de ejecución")).toBeTruthy();
    await waitFor(() =>
      expect(screen.getByRole("tab", { name: "CSV" })).toBeTruthy(),
    );
    fireEvent.click(screen.getByRole("tab", { name: "Progreso" }));
    expect(screen.getByText("Validación técnica aprobada")).toBeTruthy();
    const parametros = screen.getByRole("region", {
      name: "Parámetros de la ejecución",
    });
    expect(within(parametros).getByText("Marketing")).toBeTruthy();
    expect(within(parametros).getByText("2026-1")).toBeTruthy();
    const main = screen.getByRole("main");
    expect(main.className).toContain("h-[100dvh]");
    expect(main.className).toContain("overflow-y-auto");
    expect(main.className).toContain("overscroll-y-contain");
    expect(main.className).toContain("pb-24");
    expect(main.className).toContain("sm:pb-32");
    const conteos = screen
      .getByRole("heading", { name: "Conteos de la normalización" })
      .closest("section");
    expect(within(conteos).getByText("cursos")).toBeTruthy();
    expect(within(conteos).getAllByText("1", { exact: true })).toHaveLength(6);
    expect(within(conteos).getByText("relaciones de cobertura")).toBeTruthy();
    expect(within(conteos).getByText("habilidades técnicas")).toBeTruthy();
    const progreso = screen.getByRole("tabpanel", { name: "Progreso" });
    expect(within(progreso).queryByText("Salidas generadas")).toBeNull();
    expect(within(progreso).queryByText("Decisiones LLM aceptadas")).toBeNull();
    expect(within(progreso).queryByText("Logs y eventos")).toBeNull();
    expect(
      within(progreso).queryByRole("heading", {
        name: "Qué falta para publicar",
      }),
    ).toBeNull();
    expect(
      within(progreso).queryByRole("heading", {
        name: "Avisos que requieren atención",
      }),
    ).toBeNull();
    expect(screen.queryByRole("tab", { name: "Logs" })).toBeNull();
    expect(screen.queryByRole("tabpanel", { name: "Logs" })).toBeNull();
    expect(
      within(progreso).queryByText("Se omitió un archivo accesorio."),
    ).toBeNull();
    fireEvent.click(screen.getByRole("tab", { name: "Auditoría" }));
    const warnings = screen.getByRole("tabpanel", {
      name: "Auditoría",
    });
    expect(within(warnings).getByText("Advertencias y errores")).toBeTruthy();
    expect(
      within(warnings).getByText("Se omitió un archivo accesorio."),
    ).toBeTruthy();
    const reporte = within(warnings).getByRole("link", {
      name: /Descargar reporte/,
    });
    expect(reporte.getAttribute("href")).toBe("/reports/NOR_0123456789abcdef");
    expect(obtenerUrlReporteEjecucionNormalizador).toHaveBeenCalledWith(
      "NOR_0123456789abcdef",
    );
    fireEvent.click(screen.getByRole("tab", { name: "CSV" }));
    const csv = screen.getByRole("tabpanel", { name: "CSV" });
    expect(within(csv).getByText("curso.csv")).toBeTruthy();
    expect(
      within(csv).getByRole("link", {
        name: /Descargar curso\.csv/,
      }),
    ).toBeTruthy();
    fireEvent.click(screen.getByRole("tab", { name: "Neo4j" }));
    expect(
      within(screen.getByRole("tabpanel", { name: "Neo4j" })).getByRole(
        "heading",
        { name: "Subir catálogos a Neo4j" },
      ),
    ).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Subir datos a Neo4j" }),
    ).toBeTruthy();
    expect(obtenerUrlOutputNormalizador).toHaveBeenCalled();
  });

  it("muestra solo el sílabo procesando en fase analista y oculta los demás", async () => {
    obtenerReporteEjecucionNormalizador.mockResolvedValueOnce({
      manifest: {
        id_ejecucion: "NOR_CURRENT_ANALYSIS",
        estado: "limpiando",
        progreso_llm: {
          fase: "analista",
          chunks_completados: 4,
          chunks_totales: 9,
          logros_procesados: 12,
          logros_totales: 20,
          silabos_procesados: 1,
          silabos_totales: 3,
          reintentos: 2,
          decisiones_cacheadas: 5,
          reporte_final: "pendiente",
          eventos: [{ mensaje: "Se analiza el curso activo." }],
          silabos: [
            { curso: "Curso completado", estado_analisis: "completado" },
            { curso: "Curso actual", estado_analisis: "procesando", indice: 2, total: 3, logros_procesados: 3, logros_totales: 8 },
            { curso: "Curso en cola", estado_analisis: "pendiente" },
          ],
        },
      },
      reportes: {},
    });

    render(<InspeccionEjecucionNormalizador idEjecucion="NOR_CURRENT_ANALYSIS" />);

    const progreso = await screen.findByRole("region", { name: "Progreso de limpieza LLM" });
    expect(within(progreso).getByText(/Limpiando ahora: Curso actual \(2\/3\) · 3\/8 logros/)).toBeTruthy();
    expect(within(progreso).queryByText(/Curso completado|Curso en cola/)).toBeNull();
    expect(within(progreso).getByText(/4\/9 chunks · 12\/20 logros · 1\/3 sílabos · 2 reintentos · 5 decisiones en caché · Reporte: pendiente/)).toBeTruthy();
    expect(within(progreso).getByText("Último evento: Se analiza el curso activo.")).toBeTruthy();
  });

  it("muestra el fallback cuando el sílabo procesando no tiene curso ni archivo", async () => {
    obtenerReporteEjecucionNormalizador.mockResolvedValueOnce({
      manifest: {
        id_ejecucion: "NOR_CURRENT_UNNAMED",
        estado: "limpiando",
        progreso_llm: {
          fase: "analista",
          silabos: [
            { curso: "", archivo: "", estado_analisis: "procesando" },
          ],
        },
      },
      reportes: {},
    });

    render(<InspeccionEjecucionNormalizador idEjecucion="NOR_CURRENT_UNNAMED" />);

    const progreso = await screen.findByRole("region", { name: "Progreso de limpieza LLM" });
    expect(within(progreso).getByText("Limpiando ahora: Nombre aún no disponible")).toBeTruthy();
    expect(within(progreso).queryByText(/Salida sin nombre/)).toBeNull();
  });

  it("identifica por nombre de archivo el sílabo en extracción mientras curso todavía no se conoce", async () => {
    obtenerReporteEjecucionNormalizador.mockResolvedValueOnce({
      manifest: {
        id_ejecucion: "NOR_CURRENT_EXTRACTION",
        estado: "limpiando",
        progreso_llm: {
          fase: "extrayendo",
          silabos: [
            { curso: "", archivo: "fuentes/actual.pdf", estado_extraccion: "procesando" },
            { curso: "Anterior", archivo: "anterior.pdf", estado_extraccion: "completado" },
          ],
        },
      },
      reportes: {},
    });

    render(<InspeccionEjecucionNormalizador idEjecucion="NOR_CURRENT_EXTRACTION" />);

    const progreso = await screen.findByRole("region", { name: "Progreso de limpieza LLM" });
    expect(within(progreso).getByText("Limpiando ahora: actual.pdf")).toBeTruthy();
    expect(within(progreso).queryByText(/Anterior|anterior\.pdf/)).toBeNull();
  });

  it.each([
    { fase: "analista", silabos: [{ curso: "Pendiente", estado_analisis: "pendiente" }] },
    { fase: "analista", silabos: [{ curso: "Uno", estado_analisis: "procesando" }, { curso: "Dos", estado_analisis: "procesando" }] },
    { fase: "finalizando", silabos: [{ curso: "Terminado", estado_analisis: "completado" }] },
  ])("no inventa un sílabo actual si no hay un único activo en la fase $fase", async ({ fase, silabos }) => {
    obtenerReporteEjecucionNormalizador.mockResolvedValueOnce({
      manifest: { id_ejecucion: "NOR_NO_UNIQUE_CURRENT", estado: "limpiando", progreso_llm: { fase, silabos } },
      reportes: {},
    });

    render(<InspeccionEjecucionNormalizador idEjecucion="NOR_NO_UNIQUE_CURRENT" />);

    const progreso = await screen.findByRole("region", { name: "Progreso de limpieza LLM" });
    expect(within(progreso).getByText("No se puede identificar un único sílabo en procesamiento ahora.")).toBeTruthy();
    expect(within(progreso).queryByText(/Limpiando ahora:/)).toBeNull();
  });

  it("muestra contadores Cactus sin tratar el mensaje de última descarga como curso actual", async () => {
    obtenerReporteEjecucionNormalizador.mockResolvedValueOnce({
      manifest: {
        id_ejecucion: "NOR_CACTUS_PROGRESS",
        estado: "extrayendo",
        progreso_fuente: {
          fase: "descargando",
          cursos_encontrados: 6,
          cursos_procesados: 2,
          archivos_descargados: 2,
          mensaje: "Última descarga completada: Curso anterior",
        },
      },
      reportes: {},
    });

    render(<InspeccionEjecucionNormalizador idEjecucion="NOR_CACTUS_PROGRESS" />);

    const fuente = await screen.findByRole("region", { name: "Progreso de extracción Cactus" });
    expect(within(fuente).getByText("Fuente Cactus · descargando")).toBeTruthy();
    expect(within(fuente).getByText("6 cursos encontrados · 2 cursos procesados · 2 archivos descargados")).toBeTruthy();
    expect(within(fuente).queryByText(/Curso anterior/)).toBeNull();
    expect(screen.getByText("No se puede identificar un único sílabo en procesamiento ahora.")).toBeTruthy();
  });

  it("actualiza el sílabo actual cuando el polling recibe una nueva fase activa", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    obtenerReporteEjecucionNormalizador.mockReset();
    const reporteActivo = (curso) => ({
      manifest: {
        id_ejecucion: "NOR_CURRENT_POLL",
        estado: "limpiando",
        progreso_llm: { fase: "analista", silabos: [{ curso, estado_analisis: "procesando" }] },
      },
      reportes: {},
    });
    obtenerReporteEjecucionNormalizador
      .mockResolvedValueOnce(reporteActivo("Curso uno"))
      .mockResolvedValueOnce(reporteActivo("Curso dos"));

    render(<InspeccionEjecucionNormalizador idEjecucion="NOR_CURRENT_POLL" />);
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    expect(screen.getByText("Limpiando ahora: Curso uno")).toBeTruthy();

    await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
    expect(screen.getByText("Limpiando ahora: Curso dos")).toBeTruthy();
    expect(screen.queryByText("Limpiando ahora: Curso uno")).toBeNull();
  });

  it("muestra el progreso activo, no trata la ausencia temporal de CSV como fallo y hace polling hasta el estado terminal", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    obtenerReporteEjecucionNormalizador.mockReset();
    obtenerReporteEjecucionNormalizador
      .mockResolvedValueOnce({
        manifest: {
          id_ejecucion: "NOR_ACTIVA",
          estado: "limpiando",
          parametros: { carrera: "Marketing", periodo: "2026-1" },
          progreso_llm: {
            chunks_completados: 29,
            chunks_totales: 38,
            eventos: [{ secuencia: 29, mensaje: "Chunk 29 completado." }],
          },
        },
        reportes: {},
      })
      .mockResolvedValueOnce({
        manifest: {
          id_ejecucion: "NOR_ACTIVA",
          estado: "limpiado",
          parametros: { carrera: "Marketing", periodo: "2026-1" },
          outputs: [
            {
              archivo: "salidas/final.csv",
              tipo: "csv_curricular",
              registros: 1,
            },
          ],
        },
        reportes: {},
      });

    try {
      render(<InspeccionEjecucionNormalizador idEjecucion="NOR_ACTIVA" />);

      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
      });

      const progreso = screen.getByRole("status", {
        name: "Progreso de la ejecución",
      });
      expect(progreso).toBeTruthy();
      expect(screen.getByText("Ejecución en curso")).toBeTruthy();
      expect(within(progreso).getByText("Limpiando datos")).toBeTruthy();
      expect(screen.getByText(/29 de 38 chunks completados/)).toBeTruthy();
      expect(
        within(progreso).getByText(/Las salidas se habilitarán al finalizar\./),
      ).toBeTruthy();
      expect(
        screen.queryByText("Esta ejecución no declara salidas CSV accesibles."),
      ).toBeNull();
      expect(obtenerReporteEjecucionNormalizador).toHaveBeenCalledTimes(1);

      await act(async () => {
        await vi.advanceTimersByTimeAsync(3000);
      });

      expect(obtenerReporteEjecucionNormalizador).toHaveBeenCalledTimes(2);
      expect(screen.queryByRole("tab", { name: "Logs" })).toBeNull();
      expect(screen.getByText("final.csv")).toBeTruthy();
      const llamadasTrasEstadoTerminal =
        obtenerReporteEjecucionNormalizador.mock.calls.length;

      await act(async () => {
        await vi.advanceTimersByTimeAsync(3000);
      });

      expect(obtenerReporteEjecucionNormalizador).toHaveBeenCalledTimes(
        llamadasTrasEstadoTerminal,
      );
    } finally {
      vi.useRealTimers();
    }
  });

  it("solicita una cancelación confirmada una sola vez y evita duplicados durante el request", async () => {
    obtenerReporteEjecucionNormalizador.mockResolvedValue({
      manifest: {
        id_ejecucion: "NOR_CANCEL_ACTIVE",
        estado: "limpiando",
        cancelacion_solicitada: false,
      },
      reportes: {},
    });
    let resolverCancelacion;
    cancelarEjecucionNormalizador.mockImplementation(
      () => new Promise((resolve) => { resolverCancelacion = resolve; }),
    );

    render(<InspeccionEjecucionNormalizador idEjecucion="NOR_CANCEL_ACTIVE" />);
    const cancelar = await screen.findByRole("button", { name: "Cancelar ejecución" });
    fireEvent.click(cancelar);

    expect(confirm).toHaveBeenCalledWith(
      "¿Solicitar la cancelación de esta ejecución? El procesamiento puede tardar en detenerse.",
    );
    expect(cancelarEjecucionNormalizador).toHaveBeenCalledTimes(1);
    expect(cancelarEjecucionNormalizador).toHaveBeenCalledWith("NOR_CANCEL_ACTIVE");
    expect(cancelar.disabled).toBe(true);
    expect(cancelar.textContent).toContain("Enviando solicitud");
    fireEvent.click(cancelar);
    expect(cancelarEjecucionNormalizador).toHaveBeenCalledTimes(1);

    await act(async () => {
      resolverCancelacion({ cancelacion_solicitada: true });
    });
    expect(await screen.findByText(/Se solicitó cancelar esta ejecución/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Cancelar ejecución" })).toBeNull();
  });

  it("no solicita cancelación si se rechaza la confirmación", async () => {
    confirm.mockReturnValue(false);
    obtenerReporteEjecucionNormalizador.mockResolvedValue({
      manifest: { id_ejecucion: "NOR_CANCEL_DENIED", estado: "validando" },
      reportes: {},
    });

    render(<InspeccionEjecucionNormalizador idEjecucion="NOR_CANCEL_DENIED" />);
    fireEvent.click(await screen.findByRole("button", { name: "Cancelar ejecución" }));

    expect(confirm).toHaveBeenCalledTimes(1);
    expect(cancelarEjecucionNormalizador).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Cancelar ejecución" }).disabled).toBe(false);
  });

  it("muestra una solicitud persistida tras cargar y no ofrece cancelar en estado terminal", async () => {
    obtenerReporteEjecucionNormalizador.mockResolvedValueOnce({
      manifest: {
        id_ejecucion: "NOR_CANCEL_PERSISTED",
        estado: "normalizando",
        cancelacion_solicitada: true,
      },
      reportes: {},
    });
    const { rerender } = render(
      <InspeccionEjecucionNormalizador idEjecucion="NOR_CANCEL_PERSISTED" />,
    );
    expect(await screen.findByText(/Se solicitó cancelar esta ejecución/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Cancelar ejecución" })).toBeNull();

    obtenerReporteEjecucionNormalizador.mockResolvedValueOnce({
      manifest: { id_ejecucion: "NOR_CANCEL_TERMINAL", estado: "cancelado" },
      reportes: {},
    });
    rerender(<InspeccionEjecucionNormalizador idEjecucion="NOR_CANCEL_TERMINAL" />);
    await waitFor(() =>
      expect(
        screen.getByText("Procesamiento cancelado"),
      ).toBeTruthy(),
    );
    expect(screen.queryByRole("button", { name: "Cancelar ejecución" })).toBeNull();
  });

  it.each(["validado", "validado_con_advertencias"])(
    "continúa el polling en %s sin ofrecer ni solicitar cancelación",
    async (estado) => {
      vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
      obtenerReporteEjecucionNormalizador.mockReset();
      const reporte = () => ({
        manifest: { id_ejecucion: "NOR_VALIDATED_POLL", estado },
        reportes: {},
      });
      obtenerReporteEjecucionNormalizador
        .mockResolvedValueOnce(reporte())
        .mockResolvedValueOnce(reporte());

      render(
        <InspeccionEjecucionNormalizador idEjecucion="NOR_VALIDATED_POLL" />,
      );
      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
      });
      expect(
        screen.getByText(
          estado === "validado"
            ? "Validación completada"
            : "Validación completada con advertencias",
          { selector: "p" },
        ),
      ).toBeTruthy();
      expect(
        screen.queryByRole("button", { name: "Cancelar ejecución" }),
      ).toBeNull();

      await act(async () => {
        await vi.advanceTimersByTimeAsync(3000);
      });
      expect(obtenerReporteEjecucionNormalizador).toHaveBeenCalledTimes(2);
      expect(cancelarEjecucionNormalizador).not.toHaveBeenCalled();
      expect(
        screen.queryByRole("button", { name: "Cancelar ejecución" }),
      ).toBeNull();
    },
  );

  it("mantiene extrayendo como estado activo cancelable y continúa el polling", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    obtenerReporteEjecucionNormalizador.mockReset();
    obtenerReporteEjecucionNormalizador
      .mockResolvedValueOnce({
        manifest: { id_ejecucion: "NOR_EXTRAYENDO", estado: "extrayendo" },
        reportes: {},
      })
      .mockResolvedValueOnce({
        manifest: { id_ejecucion: "NOR_EXTRAYENDO", estado: "cancelado" },
        reportes: {},
      });

    render(<InspeccionEjecucionNormalizador idEjecucion="NOR_EXTRAYENDO" />);
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(screen.getByText("Extrayendo sílabos", { selector: "p" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Cancelar ejecución" })).toBeTruthy();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(obtenerReporteEjecucionNormalizador).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole("button", { name: "Cancelar ejecución" })).toBeNull();
  });

  it("permite reintentar si falla la solicitud y conserva el estado de ejecución", async () => {
    obtenerReporteEjecucionNormalizador.mockResolvedValue({
      manifest: { id_ejecucion: "NOR_CANCEL_RETRY", estado: "limpiando" },
      reportes: {},
    });
    cancelarEjecucionNormalizador
      .mockRejectedValueOnce(new Error("Cancelación no disponible."))
      .mockResolvedValueOnce({ cancelacion_solicitada: true });

    render(<InspeccionEjecucionNormalizador idEjecucion="NOR_CANCEL_RETRY" />);
    fireEvent.click(await screen.findByRole("button", { name: "Cancelar ejecución" }));
    expect((await screen.findByRole("alert")).textContent).toContain(
      "Cancelación no disponible.",
    );
    expect(screen.getByText("Limpiando datos", { selector: "p" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Cancelar ejecución" }).disabled).toBe(false);

    fireEvent.click(screen.getByRole("button", { name: "Cancelar ejecución" }));
    expect(await screen.findByText(/Se solicitó cancelar esta ejecución/)).toBeTruthy();
    expect(cancelarEjecucionNormalizador).toHaveBeenCalledTimes(2);
  });

  it("parsea celdas CSV con comillas y respeta el límite solicitado", () => {
    const contenido = [
      "id,nombre,detalle",
      '1,"Competencia, datos","Texto con ""comillas"""',
      ...Array.from(
        { length: 120 },
        (_item, indice) => `${indice + 2},Nombre ${indice + 2},Detalle`,
      ),
    ].join("\n");

    const preview = parseCsvPreview(contenido, 100);

    expect(preview.encabezados).toEqual(["id", "nombre", "detalle"]);
    expect(preview.filas[0]).toEqual([
      "1",
      "Competencia, datos",
      'Texto con "comillas"',
    ]);
    expect(preview.filas).toHaveLength(100);
    expect(preview.truncado).toBe(true);
  });
});
