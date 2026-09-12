import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import CurricularApprovalPanel from "./CurricularApprovalPanel";
import {
  decidirPendientesNormalizador,
  obtenerPendientesNormalizador,
} from "../api/normalizador";

vi.mock("../api/normalizador", () => ({
  decidirPendientesNormalizador: vi.fn(),
  obtenerPendientesNormalizador: vi.fn(),
}));

const propuestas = [
  {
    id_pendiente: "PEN_EXACT_1",
    tipo: "competencia",
    archivo: "marketing.docx",
    id_curso: "MKT-101",
    id_silabo: "SIL-1",
    propuesta: { nombre: "Diseño omnicanal", descripcion: "Diseñar campañas omnicanal." },
    descripcion_fuente: "La fuente declara diseño omnicanal.",
    evidencia: ["Diseñar campañas omnicanal."],
    flags: ["EXACT_DUPLICATE"],
    duplicado_exacto: true,
    grupo_duplicado_exacto: "EXACT_123",
    exact_duplicate_representative_id: "PEN_EXACT_1",
    auto_deduplicated: false,
  },
  {
    id_pendiente: "PEN_EXACT_2",
    tipo: "competencia",
    archivo: "marketing.docx",
    id_curso: "MKT-102",
    id_silabo: "SIL-2",
    propuesta: { nombre: "Diseño omnicanal", descripcion: "Gestionar campañas omnicanal." },
    evidencia: ["Gestionar campañas omnicanal."],
    flags: ["EXACT_DUPLICATE"],
    duplicado_exacto: true,
    grupo_duplicado_exacto: "EXACT_123",
    exact_duplicate_representative_id: "PEN_EXACT_1",
    auto_deduplicated: true,
    auto_deduplication_state: "AUTO_DEDUPLICATED",
  },
  {
    id_pendiente: "PEN_SEM_1",
    tipo: "habilidad",
    archivo: "marketing.docx",
    id_curso: "MKT-201",
    id_silabo: "SIL-3",
    etiqueta_logro: "L1",
    propuesta: { nombre: "Análisis de datos empresariales", descripcion: "Analizar datos." },
    evidencia: ["Analizar datos."],
    flags: ["POSSIBLE_SEMANTIC_DUPLICATE"],
    posible_duplicado_semantico: true,
    grupo_duplicado_semantico: "SEM_456",
  },
  {
    id_pendiente: "PEN_SEM_2",
    tipo: "habilidad",
    archivo: "marketing.docx",
    id_curso: "MKT-202",
    id_silabo: "SIL-4",
    propuesta: { nombre: "Análisis de datos comerciales", descripcion: "Analizar datos." },
    evidencia: ["Analizar datos."],
    flags: ["POSSIBLE_SEMANTIC_DUPLICATE"],
    posible_duplicado_semantico: true,
    grupo_duplicado_semantico: "SEM_456",
  },
  {
    id_pendiente: "PEN_TOOL",
    tipo: "herramienta",
    archivo: "marketing.docx",
    id_curso: "MKT-301",
    id_silabo: "SIL-5",
    propuesta: { nombre: "Slack", descripcion: "Herramienta de colaboración." },
    descripcion_fuente: "La actividad evalúa estados financieros.",
    evidencia: ["Evaluar estados financieros."],
    flags: ["SUSPICIOUS_UNRELATED_TOOL"],
    herramienta_no_relacionada: true,
    relevancia_herramienta: "SUSPICIOUS_UNRELATED",
  },
];

const resumen = {
  requiere_decision: true,
  total: propuestas.length,
  pendientes_por_decidir: propuestas.length - 1,
  remaining_pending: propuestas.length - 1,
  clasificacion: {
    exact_duplicate_rows: 2,
    semantic_duplicate_rows: 2,
    suspicious_unrelated_tool_rows: 1,
  },
};

describe("aprobación de propuestas curriculares", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => cleanup());

  it("muestra filtros, badges con explicación y proveniencia sin ocultar filas", async () => {
    obtenerPendientesNormalizador.mockResolvedValue({ filas: propuestas, aprobacion: resumen });

    render(<CurricularApprovalPanel idEjecucion="NOR_0123456789abcdef" />);

    expect(await screen.findByRole("heading", { name: "Revisión curricular requerida" })).toBeTruthy();
    expect(screen.getByText(/Las coincidencias exactas se deduplican automáticamente/)).toBeTruthy();
    expect(screen.getAllByTestId("curricular-proposal-card")).toHaveLength(5);
    expect(screen.getAllByText("Duplicado exacto")).toHaveLength(2);
    expect(screen.getAllByText(/deduplicó automáticamente/)).toHaveLength(2);
    expect(screen.getAllByText(/fusionó automáticamente/)).toHaveLength(2);
    expect(screen.getAllByText("Posible duplicado semántico")).toHaveLength(2);
    expect(screen.getAllByText("Proveniencia y evidencia de fuente")).toHaveLength(5);
    expect(screen.getAllByText("marketing.docx")).toHaveLength(5);
    expect(screen.getAllByText("Diseñar campañas omnicanal.")).toHaveLength(2);
    const autoCard = screen.getAllByTestId("curricular-proposal-card").find(
      (card) => card.dataset.pendingId === "PEN_EXACT_2",
    );
    expect(autoCard).toBeTruthy();
    expect(within(autoCard).queryByRole("button", { name: /ADD:/ })).toBeNull();
    expect(within(autoCard).getByText(/Deduplicada automáticamente/)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /Duplicados exactos/ }));
    expect(screen.getAllByTestId("curricular-proposal-card")).toHaveLength(2);
    expect(screen.queryByText("Análisis de datos empresariales")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /Todas/ }));
    fireEvent.change(screen.getByRole("searchbox", { name: "Buscar propuestas curriculares" }), {
      target: { value: "Slack" },
    });
    expect(screen.getAllByTestId("curricular-proposal-card")).toHaveLength(1);
    expect(screen.getByText("Herramienta sospechosa / no relacionada")).toBeTruthy();
    expect(screen.getByText(/La evidencia no relaciona claramente la herramienta/)).toBeTruthy();
  });

  it("permite decisiones ADD y KEEP_PENDING explícitas y envía solo lo seleccionado", async () => {
    obtenerPendientesNormalizador
      .mockResolvedValueOnce({ filas: propuestas.slice(2, 4), aprobacion: { ...resumen, total: 2, pendientes_por_decidir: 2 } })
      .mockResolvedValueOnce({ filas: [], aprobacion: { requiere_decision: false, accepted: 1, remaining_pending: 1 } });
    decidirPendientesNormalizador.mockResolvedValue({
      aprobacion: { accepted_in_request: 1, kept_pending_in_request: 1, remaining_pending: 1 },
    });
    const onResolved = vi.fn();

    render(<CurricularApprovalPanel idEjecucion="NOR_0123456789abcdef" onResolved={onResolved} />);

    expect(await screen.findAllByText("Análisis de datos empresariales")).toHaveLength(1);
    const cards = screen.getAllByTestId("curricular-proposal-card");
    fireEvent.click(within(cards[0]).getByRole("button", { name: /Agregar al perfil para Análisis de datos empresariales/ }));
    fireEvent.click(within(cards[1]).getByRole("button", { name: /Mantener pendiente para Análisis de datos comerciales/ }));
    fireEvent.click(screen.getByRole("button", { name: "Guardar decisiones (2)" }));

    await waitFor(() => {
      expect(decidirPendientesNormalizador).toHaveBeenCalledWith(
        "NOR_0123456789abcdef",
        [
          { id_pendiente: "PEN_SEM_1", decision: "ADD" },
          { id_pendiente: "PEN_SEM_2", decision: "KEEP_PENDING" },
        ],
      );
      expect(onResolved).toHaveBeenCalled();
    });
    expect(await screen.findByRole("status")).toBeTruthy();
    expect(within(screen.getByRole("status")).getByText(/Decisiones guardadas/)).toBeTruthy();
  });

  it("no permite guardar un lote vacío y conserva visibles las propuestas sin decisión", async () => {
    obtenerPendientesNormalizador.mockResolvedValue({
      filas: [propuestas[0]],
      aprobacion: { requiere_decision: true, total: 1, pendientes_por_decidir: 1 },
    });

    render(<CurricularApprovalPanel idEjecucion="NOR_0123456789abcdef" />);

    const guardar = await screen.findByRole("button", { name: "Guardar decisiones" });
    expect(guardar.disabled).toBe(true);
    expect(screen.getByText("Sin decisión; seguirá pendiente.")).toBeTruthy();
    expect(screen.getByTestId("curricular-proposal-card")).toBeTruthy();
  });

  it("renderiza el paquete completo y envía una sola decisión atómica", async () => {
    const paquete = {
      id_paquete_chh: "PKG_CHH_123",
      source_identity: { carrera: "MARKETING", periodo: "2026-1", id_curso: "MKT-101", id_silabo: "SIL-1" },
      componentes: {
        competencias: [{ nombre: "Diseño omnicanal" }],
        habilidades: [{ nombre: "Diseñar campañas" }],
        herramientas: [],
      },
      relaciones_canonicas: [{
        competencia: { id: "COMP_1", nombre: "Diseño omnicanal" },
        habilidad: { id: "HAB_1", nombre: "Diseñar campañas" },
        herramienta: { id: "", nombre: "" },
      }],
      filas: [{ id_pendiente: "PEN_COMP", evidencia: ["Diseñar campañas omnicanal."] }],
      relaciones: [{ id_competencia: "COMP_1", id_habilidad: "HAB_1", id_herramienta: "" }],
    };
    obtenerPendientesNormalizador.mockResolvedValueOnce({
      filas: [],
      paquetes: [paquete],
      revision: "rev-1",
      aprobacion: { requiere_decision: true, pendientes_por_decidir: 1 },
    }).mockResolvedValueOnce({ filas: [], paquetes: [], aprobacion: { requiere_decision: false } });
    decidirPendientesNormalizador.mockResolvedValue({ aprobacion: { accepted_in_request: 1 } });

    render(<CurricularApprovalPanel idEjecucion="NOR_0123456789abcdef" />);
    const card = await screen.findByTestId("curricular-package-card");
    const summaryPanel = card.firstElementChild;
    expect(summaryPanel).toBeTruthy();
    expect(card.querySelector("details")?.open).toBe(false);
    expect(within(summaryPanel).getByText("Diseño omnicanal → Diseñar campañas")).toBeTruthy();
    expect(within(card).getByText("Proveniencia y evidencia de fuente")).toBeTruthy();
    fireEvent.click(within(card).getByRole("button", { name: /Agregar al perfil para paquete PKG_CHH_123/ }));

    await waitFor(() => expect(decidirPendientesNormalizador).toHaveBeenCalledWith(
      "NOR_0123456789abcdef",
      [{ id_paquete_chh: "PKG_CHH_123", decision: "ADD" }],
      "ejecutor",
      "rev-1",
    ));
    await waitFor(() => expect(screen.queryByTestId("curricular-package-card")).toBeNull());
  });

  it("muestra competencia, habilidad y herramienta en la tarjeta principal sin triple canónica", async () => {
    const paquete = {
      id_paquete_chh: "PKG_CHH_VISIBLE_COMPONENTS",
      source_identity: { carrera: "MARKETING", periodo: "2026-1", id_curso: "MKT-406", id_silabo: "SIL-406" },
      componentes: {
        competencias: [{ nombre: "Diseño de experiencias omnicanal" }],
        habilidades: [{ nombre: "Analizar necesidades comerciales" }],
        herramientas: [{ nombre: "HubSpot CRM" }],
      },
      relaciones_canonicas: [],
      propuestas_pendientes: [{
        id_pendiente: "PEN_PENDING_SKILL",
        tipo: "habilidad",
        nombre: "Planificar seguimiento comercial",
        descripcion: "Propuesta pendiente de validación.",
      }],
      filas: [],
      relaciones: [],
    };
    obtenerPendientesNormalizador.mockResolvedValue({
      filas: [],
      paquetes: [paquete],
      aprobacion: { requiere_decision: true, pendientes_por_decidir: 1 },
    });

    render(<CurricularApprovalPanel idEjecucion="NOR_VISIBLE_COMPONENTS" />);

    const card = await screen.findByTestId("curricular-package-card");
    const summaryPanel = card.firstElementChild;
    expect(summaryPanel).toBeTruthy();
    const evidencePanel = card.querySelector("details");
    expect(evidencePanel).toBeTruthy();
    expect(evidencePanel.open).toBe(false);
    expect(within(summaryPanel).getByText("Diseño de experiencias omnicanal")).toBeTruthy();
    expect(within(summaryPanel).getByText("Analizar necesidades comerciales")).toBeTruthy();
    expect(within(summaryPanel).getByText("HubSpot CRM")).toBeTruthy();
    expect(within(summaryPanel).getByRole("heading", { name: "Propuestas pendientes" })).toBeTruthy();
    expect(within(summaryPanel).getByText("Planificar seguimiento comercial")).toBeTruthy();
  });

  it("muestra una herramienta cuyo nombre coincide con su descripción, la deduplica visualmente y conserva su auditoría pendiente", async () => {
    const paquete = {
      id_paquete_chh: "PKG_CHH_TOOL_FALLBACK",
      source_identity: { carrera: "MARKETING", periodo: "2026-1", id_curso: "MKT-407", id_silabo: "SIL-407" },
      componentes: {
        competencias: [],
        habilidades: [],
        herramientas: [
          { nombre: "Excel", descripcion: "Excel" },
          { source: { nombre_herramienta: "Excel", descripcion: "Excel" } },
          { source: { nombre_herramienta: "Power BI", descripcion: "Power BI" } },
        ],
      },
      relaciones_canonicas: [],
      source_evidence: {
        rows: [{ id_pendiente: "PEN_TOOL_1", evidencia: ["El sílabo exige el uso de Excel."] }],
        relationships: [{ id_cob_curricular: "COB_407", id_silabo: "SIL-407", id_herramienta_fuente: "HERR_SRC_EXCEL" }],
      },
      filas: [],
      relaciones: [],
    };
    obtenerPendientesNormalizador.mockResolvedValue({
      filas: [],
      paquetes: [paquete],
      aprobacion: { requiere_decision: true, pendientes_por_decidir: 1 },
    });

    render(<CurricularApprovalPanel idEjecucion="NOR_TOOL_FALLBACK" />);

    const card = await screen.findByTestId("curricular-package-card");
    const summaryPanel = card.firstElementChild;
    expect(summaryPanel).toBeTruthy();
    const componentes = within(summaryPanel).getByRole("region", { name: /Componentes curriculares/ });
    expect(within(componentes).getAllByText("Excel", { exact: true })).toHaveLength(1);
    expect(within(componentes).getAllByText("Power BI", { exact: true })).toHaveLength(1);
    expect(within(summaryPanel).getByText("No hay una triple canónica publicada para este paquete.")).toBeTruthy();

    fireEvent.click(within(card).getByText("Ver evidencia, proveniencia y relaciones"));

    const evidencePanel = card.querySelector("details");
    expect(evidencePanel).toBeTruthy();
    expect(within(evidencePanel).getByText("SIL-407", { exact: true })).toBeTruthy();
    expect(within(evidencePanel).getByText(/\"id_cob_curricular\":\"COB_407\"/)).toBeTruthy();
    expect(within(evidencePanel).getByText("El sílabo exige el uso de Excel.")).toBeTruthy();
  });

  it("muestra nombres de componentes en la tarjeta y detalles solo al expandir", async () => {
    const descriptions = {
      competencia: "Integra canales para diseñar experiencias de cliente.",
      habilidad: "Analiza necesidades y traduce hallazgos en acciones.",
      herramienta: "Plataforma para gestionar campañas y contactos.",
    };
    const paquete = {
      id_paquete_chh: "PKG_CHH_COMPONENT_DETAILS",
      source_identity: { carrera: "MARKETING", periodo: "2026-1", id_curso: "MKT-405", id_silabo: "SIL-405" },
      componentes: {
        competencias: [
          { display_name: "Diseño de experiencias", descripcion: descriptions.competencia },
          { id_fuente: "COMP_REF_OMIT", nombre: "" },
        ],
        habilidades: [
          { display_name: "Analizar necesidades", descripcion: descriptions.habilidad },
          { id_fuente: "HAB_SRC_OMIT", nombre: "" },
        ],
        herramientas: [
          { display_name: "HubSpot", descripcion: descriptions.herramienta },
          { id_fuente: "HERR_REF_OMIT", nombre: "" },
        ],
      },
      relaciones_canonicas: [{
        competencia: { id: "COMP_1", nombre: "Diseño de experiencias" },
        habilidad: { id: "HAB_1", nombre: "Analizar necesidades" },
        herramienta: { id: "HERR_1", nombre: "HubSpot" },
      }],
      filas: [],
      relaciones: [{ id_competencia: "COMP_REF_OMIT", id_habilidad: "HAB_SRC_OMIT", id_herramienta: "HERR_REF_OMIT" }],
    };
    obtenerPendientesNormalizador.mockResolvedValue({
      filas: [],
      paquetes: [paquete],
      aprobacion: { requiere_decision: true, pendientes_por_decidir: 1 },
    });

    render(<CurricularApprovalPanel idEjecucion="NOR_COMPONENT_DETAILS" />);

    const card = await screen.findByTestId("curricular-package-card");
    const summaryPanel = card.firstElementChild;
    expect(summaryPanel).toBeTruthy();
    expect(within(summaryPanel).getByText("Diseño de experiencias", { exact: true })).toBeTruthy();
    expect(within(summaryPanel).getByText("Analizar necesidades", { exact: true })).toBeTruthy();
    expect(within(summaryPanel).getByText("HubSpot", { exact: true })).toBeTruthy();
    expect(within(summaryPanel).getByText("Diseño de experiencias → Analizar necesidades → HubSpot")).toBeTruthy();
    expect(summaryPanel.textContent).not.toContain(descriptions.competencia);
    expect(summaryPanel.textContent).not.toContain("COMP_REF_OMIT");
    const evidencePanel = card.querySelector("details");
    expect(evidencePanel).toBeTruthy();
    expect(evidencePanel.open).toBe(false);

    fireEvent.click(within(card).getByText("Ver evidencia, proveniencia y relaciones"));

    expect(evidencePanel.open).toBe(true);
    const details = within(evidencePanel).getByRole("region", { name: /Detalles de componentes/ });
    expect(within(details).getByRole("heading", { name: "Detalle de componentes" })).toBeTruthy();
    expect(within(details).getByText("Competencia")).toBeTruthy();
    expect(within(details).getByText("Habilidad")).toBeTruthy();
    expect(within(details).getByText("Herramienta")).toBeTruthy();
    expect(within(details).getByText("Diseño de experiencias")).toBeTruthy();
    expect(within(details).getByText(descriptions.competencia)).toBeTruthy();
    expect(within(details).getByText("Analizar necesidades")).toBeTruthy();
    expect(within(details).getByText(descriptions.habilidad)).toBeTruthy();
    expect(within(details).getByText("HubSpot")).toBeTruthy();
    expect(within(details).getByText(descriptions.herramienta)).toBeTruthy();
    expect(within(details).queryByText("COMP_REF_OMIT")).toBeNull();
    expect(within(details).queryByText("HAB_SRC_OMIT")).toBeNull();
    expect(within(details).queryByText("HERR_REF_OMIT")).toBeNull();
    expect(within(card).getByText("Datos técnicos (IDs y metadatos)")).toBeTruthy();
    expect(card.textContent).toContain('"id_competencia":"COMP_REF_OMIT"');
  });

  it("no usa el ID fuente ni la descripción del sílabo como nombre de habilidad pendiente", async () => {
    const sourceDescription = "Diseña un plan de comunicación para clientes B2B.";
    const paquete = {
      id_paquete_chh: "PKG_CHH_PENDING_SKILL",
      source_identity: { carrera: "MARKETING", periodo: "2026-1", id_curso: "MKT-401", id_silabo: "SIL-401" },
      componentes: {
        competencias: [{ nombre: "Creación de marcas competitivas" }],
        habilidades: [
          {
            tipo: "habilidad",
            id_pendiente: "PEN_SKILL",
            id_fuente: "HAB_SRC_abcdef1234567890",
            nombre: "",
            descripcion: sourceDescription,
          },
          {
            tipo: "habilidad",
            id_fuente: "HAB_SRC_abcdef1234567890",
            nombre: sourceDescription,
            descripcion: sourceDescription,
            source: {
              id_habilidad_fuente: "HAB_SRC_abcdef1234567890",
              descripcion_fuente: sourceDescription,
            },
          },
        ],
        herramientas: [],
      },
      filas: [],
      relaciones: [],
    };
    obtenerPendientesNormalizador.mockResolvedValue({
      filas: [],
      paquetes: [paquete],
      aprobacion: { requiere_decision: true, pendientes_por_decidir: 1 },
    });

    render(<CurricularApprovalPanel idEjecucion="NOR_PENDING_SKILL" />);

    const card = await screen.findByTestId("curricular-package-card");
    const summaryPanel = card.firstElementChild;
    expect(summaryPanel).toBeTruthy();
    expect(within(summaryPanel).getByText("No hay una triple canónica publicada para este paquete.")).toBeTruthy();
    expect(within(summaryPanel).queryByText("HAB_SRC_abcdef1234567890")).toBeNull();
    expect(within(summaryPanel).queryByText(sourceDescription)).toBeNull();
  });

  it("conserva visibles los nombres de habilidad propuestos y canónicos", async () => {
    const paquete = {
      id_paquete_chh: "PKG_CHH_NAMED_SKILLS",
      source_identity: { carrera: "MARKETING", periodo: "2026-1", id_curso: "MKT-402", id_silabo: "SIL-402" },
      componentes: {
        competencias: [{ nombre: "Creación de marcas competitivas" }],
        habilidades: [
          {
            tipo: "habilidad",
            id_pendiente: "PEN_LLM_SKILL",
            id_fuente: "HAB_SRC_1234567890abcdef",
            id_canonico: "HAB_LLM",
            nombre: "Planificación de comunicación",
          },
          {
            tipo: "habilidad",
            id_fuente: "HAB_SRC_1234567890abcdef",
            id_canonico: "HAB_CAN",
            nombre: "Análisis de campañas",
            canonical: true,
          },
        ],
        herramientas: [],
      },
      relaciones_canonicas: [
        {
          competencia: { id: "COMP_1", nombre: "Creación de marcas competitivas" },
          habilidad: { id: "HAB_LLM", nombre: "Planificación de comunicación" },
          herramienta: { id: "", nombre: "" },
        },
        {
          competencia: { id: "COMP_1", nombre: "Creación de marcas competitivas" },
          habilidad: { id: "HAB_CAN", nombre: "Análisis de campañas" },
          herramienta: { id: "", nombre: "" },
        },
      ],
      filas: [],
      relaciones: [],
    };
    obtenerPendientesNormalizador.mockResolvedValue({
      filas: [],
      paquetes: [paquete],
      aprobacion: { requiere_decision: true, pendientes_por_decidir: 1 },
    });

    render(<CurricularApprovalPanel idEjecucion="NOR_NAMED_SKILLS" />);

    const card = await screen.findByTestId("curricular-package-card");
    const summaryPanel = card.firstElementChild;
    expect(summaryPanel).toBeTruthy();
    expect(within(summaryPanel).getByText("Creación de marcas competitivas → Planificación de comunicación")).toBeTruthy();
    expect(within(summaryPanel).getByText("Creación de marcas competitivas → Análisis de campañas")).toBeTruthy();
    expect(summaryPanel.textContent).not.toContain("HAB_SRC_1234567890abcdef");
  });

  it("muestra el nombre catalogado de una habilidad canónica persistida sin exponer metadatos fuente", async () => {
    const sourceDescription = "Diseña un plan de comunicación para clientes B2B.";
    const sourceHash = "sha256:source-skill-123";
    const paquete = {
      id_paquete_chh: "PKG_CHH_PERSISTED_SKILL",
      source_identity: { carrera: "MARKETING", periodo: "2026-1", id_curso: "MKT-403", id_silabo: "SIL-403" },
      componentes: {
        competencias: [{ nombre: "Creación de marcas competitivas" }],
        habilidades: [
          {
            tipo: "habilidad",
            id_fuente: "HAB_SRC_1234567890abcdef",
            id_canonico: "HAB_CAN",
            nombre: "Planificación de comunicación",
            descripcion: sourceDescription,
            canonical: true,
            source: {
              id_habilidad_fuente: "HAB_SRC_1234567890abcdef",
              descripcion_fuente: sourceDescription,
              hash: sourceHash,
            },
          },
        ],
        herramientas: [],
      },
      relaciones_canonicas: [{
        competencia: { id: "COMP_1", nombre: "Creación de marcas competitivas" },
        habilidad: { id: "HAB_CAN", nombre: "Planificación de comunicación" },
        herramienta: { id: "", nombre: "" },
      }],
      filas: [],
      relaciones: [],
    };
    obtenerPendientesNormalizador.mockResolvedValue({
      filas: [],
      paquetes: [paquete],
      aprobacion: { requiere_decision: true, pendientes_por_decidir: 1 },
    });

    render(<CurricularApprovalPanel idEjecucion="NOR_PERSISTED_SKILL" />);

    const card = await screen.findByTestId("curricular-package-card");
    const summaryPanel = card.firstElementChild;
    expect(summaryPanel).toBeTruthy();
    expect(within(summaryPanel).getByText("Creación de marcas competitivas → Planificación de comunicación")).toBeTruthy();
    expect(within(summaryPanel).queryByText(sourceDescription)).toBeNull();
    expect(within(summaryPanel).queryByText(sourceHash)).toBeNull();
  });

  it("renderiza solo triples canónicas y no combina componentes independientes", async () => {
    const longSkillName = "Diseño de estrategias omnicanal para experiencias de cliente sostenibles";
    const paquete = {
      id_paquete_chh: "PKG_CHH_LAYOUT_CONTRACT",
      source_identity: { carrera: "MARKETING", periodo: "2026-1", id_curso: "MKT-404", id_silabo: "SIL-404" },
      componentes: {
        competencias: [{ nombre: "Diseño de experiencias" }],
        habilidades: [
          { nombre: "Analizar necesidades" },
          { nombre: longSkillName },
        ],
        herramientas: [
          { nombre: "Beetrack" },
          { nombre: "VTEX" },
        ],
      },
      relaciones_canonicas: [{
        competencia: { id: "COMP_1", nombre: "Diseño de experiencias" },
        habilidad: { id: "HAB_1", nombre: "Analizar necesidades" },
        herramienta: { id: "HERR_1", nombre: "Beetrack" },
      }],
      filas: [],
      relaciones: [
        { id_competencia: "COMP_1", id_habilidad: "HAB_1", id_herramienta: "HERR_1" },
        { id_competencia: "COMP_1", id_habilidad: "HAB_1", id_herramienta: "HERR_2" },
        { id_competencia: "COMP_2", id_habilidad: "HAB_1", id_herramienta: "HERR_1" },
      ],
    };
    obtenerPendientesNormalizador.mockResolvedValue({
      filas: [],
      paquetes: [paquete],
      aprobacion: { requiere_decision: true, pendientes_por_decidir: 1 },
    });

    render(<CurricularApprovalPanel idEjecucion="NOR_LAYOUT_CONTRACT" />);

    const card = await screen.findByTestId("curricular-package-card");
    const summaryPanel = card.firstElementChild;
    expect(summaryPanel).toBeTruthy();
    expect(within(summaryPanel).getByText(longSkillName, { exact: true })).toBeTruthy();
    expect(within(summaryPanel).getByText("VTEX", { exact: true })).toBeTruthy();
    const canonicalSection = within(summaryPanel).getByRole("region", { name: /Relaciones canónicas/ });
    expect(within(canonicalSection).getByText("Diseño de experiencias → Analizar necesidades → Beetrack")).toBeTruthy();
    expect(canonicalSection.textContent).not.toContain(longSkillName);
    expect(canonicalSection.textContent).not.toContain("VTEX");
    expect(canonicalSection.textContent).not.toContain("Diseño de experiencias → Analizar necesidades → VTEX");
    fireEvent.click(within(card).getByText("Ver evidencia, proveniencia y relaciones"));
    const evidencePanel = card.querySelector("details");
    expect(evidencePanel).toBeTruthy();
    const details = within(evidencePanel).getByRole("region", { name: /Detalles de componentes/ });
    expect(within(details).getByText(longSkillName)).toBeTruthy();
    expect(card.textContent).toContain('"id_herramienta":"HERR_2"');
    expect(card.querySelector("summary")?.textContent).not.toContain("3 relaciones");
    expect(card.querySelector("summary")?.textContent).not.toContain("relación(es) conservada(s)");
  });

  it("oculta referencias COMP_REF y descripciones fuente sin mezclar la jerarquía", async () => {
    const sourceDescription = "Diseña un plan de comunicación para clientes B2B.";
    const sourceName = "Nombre de habilidad aún no catalogado";
    const paquete = {
      id_paquete_chh: "PKG_CHH_EMPTY_REFERENCES",
      componentes: {
        competencias: [
          { tipo: "competencia", id_fuente: "COMP_REF_A", nombre: "" },
          { tipo: "competencia", id_fuente: "COMP_REF_B", nombre: "COMP_REF_B" },
          { tipo: "competencia", nombre: "Creación de marcas competitivas" },
        ],
        habilidades: [
          {
            tipo: "habilidad",
            id_pendiente: "PEN_NAMED_SKILL",
            nombre: "Analizar necesidades",
          },
          {
            tipo: "habilidad",
            id_fuente: "HAB_SRC_abcdef1234567890",
            nombre_habilidad_fuente: sourceName,
            nombre: sourceDescription,
            descripcion: sourceDescription,
          },
        ],
        herramientas: [],
      },
      relaciones_canonicas: [{
        competencia: { id: "COMP_1", nombre: "Creación de marcas competitivas" },
        habilidad: { id: "HAB_1", nombre: "Analizar necesidades" },
        herramienta: { id: "", nombre: "" },
      }],
      filas: [],
      relaciones: [],
    };
    obtenerPendientesNormalizador.mockResolvedValue({
      filas: [],
      paquetes: [paquete],
      aprobacion: { requiere_decision: true, pendientes_por_decidir: 1 },
    });

    render(<CurricularApprovalPanel idEjecucion="NOR_EMPTY_REFERENCES" />);

    const card = await screen.findByTestId("curricular-package-card");
    const summaryPanel = card.firstElementChild;
    expect(summaryPanel).toBeTruthy();
    expect(within(summaryPanel).getByText("Creación de marcas competitivas → Analizar necesidades")).toBeTruthy();
    expect(within(summaryPanel).queryByText("COMP_REF_A")).toBeNull();
    expect(within(summaryPanel).queryByText("COMP_REF_B")).toBeNull();
    expect(within(summaryPanel).queryByText(sourceName)).toBeNull();
    expect(within(summaryPanel).queryByText(sourceDescription)).toBeNull();
  });

  it("compacta paquetes, pagina de 15 en 15 y conserva decisiones de todas las páginas", async () => {
    const paquetes = Array.from({ length: 31 }, (_item, indice) => ({
      id_paquete_chh: `PKG_${indice + 1}`,
      source_identity: { carrera: "MARKETING", periodo: "2026-1", id_curso: `MKT-${indice + 1}`, id_silabo: `SIL-${indice + 1}` },
      componentes: {
        competencias: [{ nombre: `Competencia ${indice + 1}` }],
        habilidades: [{ nombre: `Habilidad ${indice + 1}` }],
        herramientas: [{ nombre: `Herramienta ${indice + 1}` }],
      },
      filas: [{ id_pendiente: `PEN_${indice + 1}`, evidencia: [`Evidencia ${indice + 1}`] }],
      relaciones: [{ id_competencia: `COMP_${indice + 1}` }],
    }));
    obtenerPendientesNormalizador.mockResolvedValue({
      filas: [],
      paquetes,
      revision: "rev-bulk",
      aprobacion: { requiere_decision: true, pendientes_por_decidir: paquetes.length },
    });
    decidirPendientesNormalizador.mockResolvedValue({ aprobacion: { accepted_in_request: 2 } });

    render(<CurricularApprovalPanel idEjecucion="NOR_BULK_PACKAGES" />);

    expect(await screen.findAllByTestId("curricular-package-card")).toHaveLength(15);
    expect(screen.getByText(/Paquetes 1–15 de 31/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Página siguiente de paquetes" }));
    expect(await screen.findAllByTestId("curricular-package-card")).toHaveLength(15);
    expect(screen.getByText(/Paquetes 16–30 de 31/)).toBeTruthy();
    const pageTwoCard = screen.getAllByTestId("curricular-package-card")[0];
    expect(pageTwoCard.dataset.packageId).toBe("PKG_16");
    fireEvent.click(within(pageTwoCard).getByRole("button", { name: /Agregar al perfil para paquete PKG_16/ }));

    await waitFor(() => expect(decidirPendientesNormalizador).toHaveBeenCalledWith(
      "NOR_BULK_PACKAGES",
      [{ id_paquete_chh: "PKG_16", decision: "ADD" }],
      "ejecutor",
      "rev-bulk",
    ));
    await waitFor(() => expect(screen.getByText(/Paquetes 1–15 de 31/)).toBeTruthy());
    const pageOneCard = screen.getAllByTestId("curricular-package-card")[0];
    fireEvent.click(within(pageOneCard).getByRole("button", { name: /Agregar al perfil para paquete PKG_1/ }));

    await waitFor(() => expect(decidirPendientesNormalizador).toHaveBeenCalledWith(
      "NOR_BULK_PACKAGES",
      [{ id_paquete_chh: "PKG_1", decision: "ADD" }],
      "ejecutor",
      "rev-bulk",
    ));
  });

  it("reinicia la página de paquetes al cambiar la búsqueda", async () => {
    const paquetes = Array.from({ length: 31 }, (_item, indice) => ({
      id_paquete_chh: `PKG_SEARCH_${indice + 1}`,
      componentes: { competencias: [{ nombre: `Competencia ${indice + 1}` }] },
      filas: [],
    }));
    obtenerPendientesNormalizador.mockResolvedValue({
      filas: [],
      paquetes,
      aprobacion: { requiere_decision: true, pendientes_por_decidir: paquetes.length },
    });

    render(<CurricularApprovalPanel idEjecucion="NOR_SEARCH_PACKAGES" />);
    await screen.findAllByTestId("curricular-package-card");
    fireEvent.click(screen.getByRole("button", { name: "Página siguiente de paquetes" }));
    expect(screen.getByText(/Paquetes 16–30 de 31/)).toBeTruthy();
    fireEvent.change(screen.getByRole("searchbox", { name: "Buscar paquetes curriculares" }), { target: { value: "PKG_SEARCH_30" } });
    await waitFor(() => expect(screen.getByText(/Paquetes 1–1 de 1/)).toBeTruthy());
    expect(screen.getAllByTestId("curricular-package-card")).toHaveLength(1);
  });

  it("usa el fallback legacy cuando el API devuelve paquetes vacío", async () => {
    obtenerPendientesNormalizador
      .mockResolvedValueOnce({
        filas: [propuestas[0]],
        paquetes: [],
        aprobacion: { requiere_decision: true, pendientes_por_decidir: 1 },
      })
      .mockResolvedValueOnce({ filas: [], paquetes: [], aprobacion: { requiere_decision: false } });
    decidirPendientesNormalizador.mockResolvedValue({ aprobacion: { accepted_in_request: 1 } });

    render(<CurricularApprovalPanel idEjecucion="NOR_0123456789abcdef" />);

    const card = await screen.findByTestId("curricular-proposal-card");
    expect(within(card).getByText("Diseño omnicanal")).toBeTruthy();
    expect(screen.queryByTestId("curricular-package-card")).toBeNull();
    fireEvent.click(within(card).getByRole("button", { name: /Agregar al perfil para Diseño omnicanal/ }));
    fireEvent.click(screen.getByRole("button", { name: "Guardar decisiones (1)" }));

    await waitFor(() => expect(decidirPendientesNormalizador).toHaveBeenCalledWith(
      "NOR_0123456789abcdef",
      [{ id_pendiente: "PEN_EXACT_1", decision: "ADD" }],
    ));
  });

  it("confirma el descarte de un paquete, exige motivo y lo retira tras refrescar", async () => {
    const paquete = {
      id_paquete_chh: "PKG_DISCARD",
      componentes: { competencias: [{ nombre: "Gestión de campañas" }], habilidades: [{ nombre: "Analizar campañas" }], herramientas: [] },
      relaciones_canonicas: [{ competencia: { id: "COMP_1", nombre: "Gestión de campañas" }, habilidad: { id: "HAB_1", nombre: "Analizar campañas" }, herramienta: { id: "", nombre: "" } }],
      propuestas_pendientes: [{ id_pendiente: "PEN_1", tipo: "habilidad", nombre: "Analizar campañas", descripcion: "Propuesta pendiente." }],
      source_evidence: { rows: [{ evidencia: ["Analizar campañas."] }], relationships: [{ id_habilidad_fuente: "HAB_SRC_1" }] },
      filas: [],
    };
    obtenerPendientesNormalizador
      .mockResolvedValueOnce({ filas: [], paquetes: [paquete], revision: "rev-discard", aprobacion: { requiere_decision: true, pendientes_por_decidir: 1 } })
      .mockResolvedValueOnce({ filas: [], paquetes: [], aprobacion: { requiere_decision: false } });
    decidirPendientesNormalizador.mockResolvedValue({ aprobacion: { discarded_in_request: 1 } });

    render(<CurricularApprovalPanel idEjecucion="NOR_DISCARD" />);
    const card = await screen.findByTestId("curricular-package-card");
    expect(within(card).getByText("Gestión de campañas → Analizar campañas")).toBeTruthy();
    expect(within(card.firstElementChild).getByText("Propuestas pendientes")).toBeTruthy();
    fireEvent.click(within(card).getByRole("button", { name: "Descartar paquete" }));

    await waitFor(() => expect(decidirPendientesNormalizador).toHaveBeenCalledWith(
      "NOR_DISCARD",
      [{ id_paquete_chh: "PKG_DISCARD", decision: "DISCARD", reason: "Descarte manual desde la revisión HITL." }],
      "ejecutor",
      "rev-discard",
    ));
    await waitFor(() => expect(screen.queryByTestId("curricular-package-card")).toBeNull());
  });

  it("no muestra el checkpoint cuando no hay propuestas abiertas", async () => {
    obtenerPendientesNormalizador.mockResolvedValue({
      filas: [],
      aprobacion: { requiere_decision: false, total: 0 },
    });

    render(<CurricularApprovalPanel idEjecucion="NOR_0123456789abcdef" />);

    await waitFor(() => expect(obtenerPendientesNormalizador).toHaveBeenCalled());
    expect(screen.queryByRole("heading", { name: "Revisión curricular requerida" })).toBeNull();
  });
});
