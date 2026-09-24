import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import NormalizadorPanel, {
  formatearLatenciaLLM,
  normalizarProgresoSilabos,
} from "./NormalizadorPanel";
import {
  cancelarEjecucionNormalizador,
  iniciarNormalizadorSilabos,
  iniciarNormalizadorSilabosCactus,
  listarEjecucionesNormalizador,
  registrarCambioHitlNormalizador,
  obtenerCuarentenaNormalizador,
  obtenerEjecucionNormalizador,
  obtenerErroresNormalizador,
  obtenerPendientesNormalizador,
} from "../api/normalizador";

const navigation = vi.hoisted(() => ({
  push: vi.fn(),
  replace: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => navigation,
}));

vi.mock("../api/normalizador", () => ({
  cancelarEjecucionNormalizador: vi.fn(),
  iniciarNormalizadorSilabos: vi.fn(),
  iniciarNormalizadorSilabosCactus: vi.fn(),
  listarEjecucionesNormalizador: vi.fn(),
  registrarCambioHitlNormalizador: vi.fn().mockResolvedValue(undefined),
  decidirPendientesNormalizador: vi.fn(),
  obtenerReporteEjecucionNormalizador: vi.fn(),
  obtenerUrlReporteEjecucionNormalizador: vi.fn(
    (idEjecucion) => `/api/normalizador/ejecuciones/${idEjecucion}/reporte`,
  ),
  eliminarEjecucionHistorialNormalizador: vi.fn(),
  obtenerCuarentenaNormalizador: vi.fn(),
  obtenerEjecucionNormalizador: vi.fn(),
  obtenerErroresNormalizador: vi.fn(),
  obtenerPendientesNormalizador: vi.fn(),
  obtenerUrlOutputNormalizador: vi.fn(
    (idEjecucion, archivo) =>
      `/api/normalizador/ejecuciones/${idEjecucion}/outputs/${archivo}`,
  ),
}));

async function renderPanelAfterRecovery() {
  const rendered = render(<NormalizadorPanel />);
  await waitFor(() =>
    expect(screen.getByRole("switch", { name: "HITL técnico" }).disabled).toBe(
      false,
    ),
  );
  return rendered;
}

async function renderTechnicalResult({ id, outputs, gate }) {
  iniciarNormalizadorSilabos.mockResolvedValue({
    id_ejecucion: id,
    tipo: "silabos",
    archivo: "curriculo.zip",
    estado: "validando",
  });
  obtenerEjecucionNormalizador.mockResolvedValue({
    id_ejecucion: id,
    tipo: "silabos",
    archivo: "curriculo.zip",
    estado: "limpiado",
    configuracion_curricular: { modo_analista: "technical" },
    parametros: { carrera: "Marketing", periodo: "2026-1" },
    validacion_silabos: { valida: true, archivos: [] },
    release_gate: gate,
    outputs,
    hallazgos: [],
  });
  const rendered = await renderPanelAfterRecovery();
  fireEvent.click(screen.getByRole("tab", { name: "Sílabos" }));
  fireEvent.change(screen.getByRole("combobox", { name: "Carrera" }), {
    target: { value: "Marketing" },
  });
  fireEvent.change(screen.getByRole("combobox", { name: "Periodo" }), {
    target: { value: "2026-1" },
  });
  fireEvent.change(rendered.container.querySelector('input[type="file"]'), {
    target: {
      files: [new File(["zip"], "curriculo.zip", { type: "application/zip" })],
    },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "Iniciar limpieza curricular" }),
  );
  await waitFor(() =>
    expect(screen.getByRole("heading", { name: /^CSV técnicos/ })).toBeTruthy(),
  );
  return rendered;
}

describe("panel del normalizador", () => {
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  beforeEach(() => {
    vi.clearAllMocks();
    listarEjecucionesNormalizador.mockResolvedValue({
      ejecuciones: [],
      retencion: null,
    });
    obtenerEjecucionNormalizador.mockResolvedValue({
      id_ejecucion: "NOR_0123456789abcdef",
      archivo: "fuente.xlsx",
      estado: "normalizado",
      normalizacion: {
        publicable: true,
        registros_procesados: { publicaciones: 1, informes: 0 },
        relaciones: 1,
        cuarentena: 0,
      },
      outputs: [
        {
          tipo: "csv",
          archivo: "salidas/requerimiento_laboral.csv",
          registros: 1,
        },
      ],
      hallazgos: [],
    });
    obtenerErroresNormalizador.mockResolvedValue({ hallazgos: [] });
    obtenerCuarentenaNormalizador.mockResolvedValue({ total: 0, filas: [] });
  });

  it("omite la tarjeta de progreso de la normalización en el panel principal", async () => {
    await renderPanelAfterRecovery();

    expect(
      screen.queryByRole("region", { name: "Seguimiento del flujo" }),
    ).toBeNull();
  });

  it("deja que Carga de fuente ocupe todo el ancho disponible", async () => {
    await renderPanelAfterRecovery();

    const sourcePanelWrapper = document.querySelector("#panel-fuente");
    expect(sourcePanelWrapper.className).not.toMatch(/\bgrid\b/);
    expect(sourcePanelWrapper.className).not.toContain("lg:grid-cols-");
  });

  it("ubica el switch HITL dentro de Carga de fuente y permite alternar los modos", async () => {
    await renderPanelAfterRecovery();

    const sourcePanel = screen.getByRole("region", { name: "Carga de fuente" });
    const switchControl = within(sourcePanel).getByRole("switch", {
      name: "HITL técnico",
    });
    expect(switchControl.getAttribute("aria-checked")).toBe("true");
    expect(within(sourcePanel).getByText("Revisión técnica manual")).toBeTruthy();
    expect(
      within(sourcePanel).getByText(
        "Las propuestas técnicas esperan tu revisión antes de agregarse.",
      ),
    ).toBeTruthy();
    expect(screen.queryByText(/HITL técnico:\s*[01]/)).toBeNull();
    expect(screen.queryByText(/Con 0/)).toBeNull();

    fireEvent.click(switchControl);

    expect(switchControl.getAttribute("aria-checked")).toBe("false");
    expect(
      within(sourcePanel).getByText("Aprobación técnica automática"),
    ).toBeTruthy();
    expect(
      within(sourcePanel).getByText(
        "Las propuestas técnicas válidas se agregan automáticamente (ADD).",
      ),
    ).toBeTruthy();
    await waitFor(() => {
      expect(registrarCambioHitlNormalizador).toHaveBeenCalledWith(0);
      expect(registrarCambioHitlNormalizador).toHaveBeenCalledTimes(1);
    });
    expect(screen.queryByText(/HITL técnico:\s*[01]/)).toBeNull();
    expect(iniciarNormalizadorSilabos).not.toHaveBeenCalled();
    expect(iniciarNormalizadorSilabosCactus).not.toHaveBeenCalled();

    fireEvent.click(switchControl);

    await waitFor(() => {
      expect(registrarCambioHitlNormalizador).toHaveBeenCalledWith(1);
      expect(registrarCambioHitlNormalizador).toHaveBeenCalledTimes(2);
    });
    expect(switchControl.getAttribute("aria-checked")).toBe("true");
    expect(iniciarNormalizadorSilabos).not.toHaveBeenCalled();
    expect(iniciarNormalizadorSilabosCactus).not.toHaveBeenCalled();
  });

  it("muestra un error accesible y conserva el valor elegido si falla el registro HITL", async () => {
    registrarCambioHitlNormalizador.mockRejectedValueOnce(
      new Error("detalle backend privado"),
    );

    await renderPanelAfterRecovery();
    const switchControl = screen.getByRole("switch", {
      name: "HITL técnico",
    });
    fireEvent.click(switchControl);

    const alerta = await screen.findByRole("alert");
    expect(alerta.textContent).toContain(
      "No se pudo registrar el cambio del control HITL. Intenta nuevamente.",
    );
    expect(alerta.textContent).not.toContain("detalle backend privado");
    expect(screen.queryByText("detalle backend privado")).toBeNull();
    expect(switchControl.getAttribute("aria-checked")).toBe("false");
    expect(iniciarNormalizadorSilabos).not.toHaveBeenCalled();
    expect(iniciarNormalizadorSilabosCactus).not.toHaveBeenCalled();

    iniciarNormalizadorSilabosCactus.mockResolvedValue({
      id_ejecucion: "NOR_cactus12345678",
      tipo: "silabos",
      archivo: "cactus.zip",
      estado: "extrayendo",
      parametros: { carrera: "Marketing", periodo: "2026-1", fuente: "cactus" },
    });
    obtenerEjecucionNormalizador.mockResolvedValue({
      id_ejecucion: "NOR_cactus12345678",
      tipo: "silabos",
      archivo: "cactus.zip",
      estado: "extrayendo",
      parametros: { carrera: "Marketing", periodo: "2026-1", fuente: "cactus" },
      fuente: { tipo: "cactus", estado: "extrayendo" },
      progreso_fuente: {
        fase: "autenticando",
        cursos_encontrados: 0,
        cursos_procesados: 0,
        archivos_descargados: 0,
        errores: 0,
        mensaje: "Abriendo una sesión autenticada en Cactus.",
      },
      outputs: [],
      hallazgos: [],
    });

    fireEvent.click(screen.getByRole("tab", { name: "Sílabos" }));
    fireEvent.change(screen.getByRole("combobox", { name: "Carrera" }), {
      target: { value: "Marketing" },
    });
    fireEvent.change(screen.getByRole("combobox", { name: "Periodo" }), {
      target: { value: "2026-1" },
    });
    fireEvent.change(screen.getByRole("textbox", { name: "Usuario ULima" }), {
      target: { value: "usuario.ulima" },
    });
    fireEvent.change(screen.getByLabelText("Contraseña ULima"), {
      target: { value: "secreto" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Extraer y normalizar sílabos" }),
    );

    await waitFor(() =>
      expect(iniciarNormalizadorSilabosCactus).toHaveBeenCalledWith(
        "Marketing",
        "2026-1",
        "usuario.ulima",
        "secreto",
        0,
      ),
    );
    expect(screen.queryByText("detalle backend privado")).toBeNull();
  });

  it("restablece HITL al modo de revisión manual al preparar una nueva ejecución", async () => {
    const { container } = await renderPanelAfterRecovery();
    fireEvent.click(screen.getByRole("button", { name: /Cargar archivo manual/ }));
    fireEvent.change(screen.getByRole("combobox", { name: "Carrera" }), {
      target: { value: "Marketing" },
    });
    fireEvent.change(screen.getByRole("combobox", { name: "Periodo" }), {
      target: { value: "2026-1" },
    });
    fireEvent.change(container.querySelector('input[type="file"]'), {
      target: {
        files: [new File(["zip"], "curriculo.zip", { type: "application/zip" })],
      },
    });
    fireEvent.click(screen.getByRole("switch", { name: "HITL técnico" }));
    fireEvent.click(screen.getByRole("button", { name: "Nueva fuente" }));

    expect(screen.getByRole("switch", { name: "HITL técnico" }).getAttribute("aria-checked")).toBe("true");
    expect(screen.getByText("Revisión técnica manual")).toBeTruthy();
  });

  it("inicia la extracción Cactus con carrera, periodo y credenciales", async () => {
    iniciarNormalizadorSilabosCactus.mockResolvedValue({
      id_ejecucion: "NOR_cactus12345678",
      tipo: "silabos",
      archivo: "cactus.zip",
      estado: "extrayendo",
      parametros: { carrera: "Marketing", periodo: "2026-1", fuente: "cactus" },
    });
    obtenerEjecucionNormalizador.mockResolvedValue({
      id_ejecucion: "NOR_cactus12345678",
      tipo: "silabos",
      archivo: "cactus.zip",
      estado: "extrayendo",
      parametros: { carrera: "Marketing", periodo: "2026-1", fuente: "cactus" },
      fuente: { tipo: "cactus", estado: "extrayendo" },
      progreso_fuente: {
        fase: "autenticando",
        cursos_encontrados: 0,
        cursos_procesados: 0,
        archivos_descargados: 0,
        errores: 0,
        mensaje: "Abriendo una sesión autenticada en Cactus.",
      },
      outputs: [],
      hallazgos: [],
    });

    await renderPanelAfterRecovery();
    fireEvent.click(screen.getByRole("tab", { name: "Sílabos" }));
    fireEvent.change(screen.getByRole("combobox", { name: "Carrera" }), {
      target: { value: "Marketing" },
    });
    fireEvent.change(screen.getByRole("combobox", { name: "Periodo" }), {
      target: { value: "2026-1" },
    });
    fireEvent.change(screen.getByRole("textbox", { name: "Usuario ULima" }), {
      target: { value: "usuario.ulima" },
    });
    fireEvent.change(screen.getByLabelText("Contraseña ULima"), {
      target: { value: "secreto" },
    });
    fireEvent.click(screen.getByRole("switch", { name: "HITL técnico" }));
    fireEvent.click(
      screen.getByRole("button", { name: "Extraer y normalizar sílabos" }),
    );

    await waitFor(() =>
      expect(iniciarNormalizadorSilabosCactus).toHaveBeenCalledWith(
        "Marketing",
        "2026-1",
        "usuario.ulima",
        "secreto",
        0,
      ),
    );
    expect(navigation.push).toHaveBeenCalledWith("/NOR_cactus12345678");
    expect(screen.getByLabelText("Progreso de extracción Cactus")).toBeTruthy();
  });

  it("recupera al montar una ejecución curricular activa y continúa su seguimiento", async () => {
    const idEjecucion = "NOR_restaurar12345678";
    let resolverDetalle;
    const detallePendiente = new Promise((resolve) => {
      resolverDetalle = resolve;
    });
    listarEjecucionesNormalizador.mockResolvedValue({
      ejecuciones: [
        {
          id_ejecucion: idEjecucion,
          tipo: "silabos",
          archivo: "marketing.zip",
          parametros: { carrera: "Marketing", periodo: "2026-1", hitl: 0 },
          estado: "limpiando",
          actualizada_en: "2026-08-18T12:00:00+00:00",
        },
      ],
      retencion: null,
    });
    obtenerEjecucionNormalizador.mockReturnValue(detallePendiente);

    render(<NormalizadorPanel />);

    expect(screen.getByRole("switch", { name: "HITL técnico" }).disabled).toBe(
      true,
    );
    expect(screen.getByRole("tab", { name: "Sílabos" }).disabled).toBe(true);
    await waitFor(() =>
      expect(obtenerEjecucionNormalizador).toHaveBeenCalledWith(idEjecucion),
    );
    expect(navigation.replace).not.toHaveBeenCalled();

    resolverDetalle({
      id_ejecucion: idEjecucion,
      tipo: "silabos",
      archivo: "marketing.zip",
      parametros: { carrera: "Marketing", periodo: "2026-1", hitl: 0 },
      estado: "limpiando",
      validacion_silabos: {
        valida: true,
        archivos: [{ nombre: "marketing.pdf" }],
      },
      outputs: [],
      hallazgos: [],
      progreso_llm: {
        fase: "analista",
        chunks_completados: 2,
        chunks_totales: 4,
        logros_detectados: 20,
        logros_procesados: 10,
        logros_totales: 20,
        silabos_detectados: 1,
        silabos_procesados: 1,
        silabos_totales: 1,
        decisiones_cacheadas: 0,
        reintentos: 0,
        eventos: [],
      },
    });

    await waitFor(() =>
      expect(screen.getByLabelText("Progreso de limpieza LLM")).toBeTruthy(),
    );
    expect(screen.queryByText("Progreso de la normalización")).toBeNull();
    expect(
      screen
        .getByRole("tab", { name: "Sílabos" })
        .getAttribute("aria-selected"),
    ).toBe("true");
    expect(screen.getByRole("combobox", { name: "Carrera" }).value).toBe(
      "Marketing",
    );
    expect(screen.getByRole("combobox", { name: "Periodo" }).value).toBe(
      "2026-1",
    );
    expect(
      screen.getByRole("switch", { name: "HITL técnico" }).getAttribute("aria-checked"),
    ).toBe("false");
    expect(screen.getByText("Aprobación técnica automática")).toBeTruthy();
    expect(screen.getByLabelText("Progreso de limpieza LLM")).toBeTruthy();
    expect(screen.getByRole("switch", { name: "HITL técnico" }).disabled).toBe(
      true,
    );
    expect(screen.getByRole("combobox", { name: "Carrera" }).disabled).toBe(
      true,
    );
    expect(
      await screen.findByRole("heading", { name: "Historial de ejecuciones" }),
    ).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "Inspeccionar" }).getAttribute("href"),
    ).toBe(`/${idEjecucion}`);
    expect(navigation.replace).not.toHaveBeenCalled();
  });

  it("limpia el polling al desmontar una ejecución restaurada", async () => {
    const idEjecucion = "NOR_timer12345678";
    const ejecucionActiva = {
      id_ejecucion: idEjecucion,
      tipo: "silabos",
      archivo: "marketing.zip",
      parametros: { carrera: "Marketing", periodo: "2026-1", hitl: 0 },
      estado: "limpiando",
      validacion_silabos: { valida: true, archivos: [] },
      outputs: [],
      hallazgos: [],
    };
    listarEjecucionesNormalizador.mockResolvedValue({
      ejecuciones: [ejecucionActiva],
      retencion: null,
    });
    obtenerEjecucionNormalizador.mockResolvedValue(ejecucionActiva);

    const { unmount } = render(<NormalizadorPanel />);
    await waitFor(() =>
      expect(screen.getByLabelText("Registro de actividad")).toBeTruthy(),
    );
    const llamadasAntesDeDesmontar =
      obtenerEjecucionNormalizador.mock.calls.length;

    unmount();
    await new Promise((resolve) => setTimeout(resolve, 1000));

    expect(obtenerEjecucionNormalizador).toHaveBeenCalledTimes(
      llamadasAntesDeDesmontar,
    );
  });

  it("expone únicamente la carga técnica de sílabos", async () => {
    await renderPanelAfterRecovery();

    expect(screen.getAllByRole("tab")).toHaveLength(1);
    expect(screen.getByRole("tab", { name: "Sílabos" })).toBeTruthy();
    expect(screen.queryByRole("tab", { name: "Empleabilidad" })).toBeNull();
    expect(
      screen.getByText("Cactus automático o archivo curricular"),
    ).toBeTruthy();
  });

  it("bloquea los controles mientras la ejecución curricular está activa", async () => {
    iniciarNormalizadorSilabos.mockResolvedValue({
      id_ejecucion: "NOR_fedcba9876543210",
      tipo: "silabos",
      archivo: "curriculo.zip",
      estado: "validando",
    });
    obtenerEjecucionNormalizador.mockResolvedValue({
      id_ejecucion: "NOR_fedcba9876543210",
      tipo: "silabos",
      archivo: "curriculo.zip",
      estado: "limpiando",
      validacion_silabos: { valida: true, archivos: [] },
      hallazgos: [],
    });

    const { container } = await renderPanelAfterRecovery();
    fireEvent.click(screen.getByRole("tab", { name: "Sílabos" }));
    fireEvent.change(screen.getByRole("combobox", { name: "Carrera" }), {
      target: { value: "Marketing" },
    });
    fireEvent.change(screen.getByRole("combobox", { name: "Periodo" }), {
      target: { value: "2026-1" },
    });
    const archivo = new File(["zip"], "curriculo.zip", {
      type: "application/zip",
    });
    fireEvent.change(container.querySelector('input[type="file"]'), {
      target: { files: [archivo] },
    });
    fireEvent.click(screen.getByRole("switch", { name: "HITL técnico" }));
    fireEvent.click(
      screen.getByRole("button", { name: "Iniciar limpieza curricular" }),
    );

    await waitFor(() =>
      expect(screen.getByLabelText("Registro de actividad")).toBeTruthy(),
    );
    expect(screen.getByRole("tab", { name: "Sílabos" }).disabled).toBe(true);
    expect(screen.getByRole("combobox", { name: "Carrera" }).disabled).toBe(
      true,
    );
    expect(screen.getByRole("combobox", { name: "Periodo" }).disabled).toBe(
      true,
    );
    expect(
      screen.getByRole("button", { name: "Iniciar limpieza curricular" })
        .disabled,
    ).toBe(true);
    expect(screen.getByRole("button", { name: "Nueva fuente" }).disabled).toBe(
      true,
    );
    expect(iniciarNormalizadorSilabos).toHaveBeenCalledWith(
      archivo,
      "Marketing",
      "2026-1",
      0,
    );
  });

  it("confirma la cancelación y mantiene el polling hasta el estado terminal", async () => {
    const confirmacion = vi.spyOn(window, "confirm").mockReturnValue(true);
    iniciarNormalizadorSilabos.mockResolvedValue({
      id_ejecucion: "NOR_cancelar12345678",
      tipo: "silabos",
      archivo: "curriculo.zip",
      estado: "validando",
    });
    obtenerEjecucionNormalizador.mockResolvedValueOnce({
      id_ejecucion: "NOR_cancelar12345678",
      tipo: "silabos",
      archivo: "curriculo.zip",
      estado: "limpiando",
      validacion_silabos: { valida: true, archivos: [] },
      outputs: [],
      hallazgos: [],
    });
    cancelarEjecucionNormalizador.mockResolvedValue({
      id_ejecucion: "NOR_cancelar12345678",
      tipo: "silabos",
      archivo: "curriculo.zip",
      estado: "limpiando",
      cancelacion_solicitada: true,
      hallazgos: [],
    });

    const { container } = await renderPanelAfterRecovery();
    fireEvent.click(screen.getByRole("tab", { name: "Sílabos" }));
    fireEvent.change(screen.getByRole("combobox", { name: "Carrera" }), {
      target: { value: "Marketing" },
    });
    fireEvent.change(screen.getByRole("combobox", { name: "Periodo" }), {
      target: { value: "2026-1" },
    });
    fireEvent.change(container.querySelector('input[type="file"]'), {
      target: {
        files: [
          new File(["zip"], "curriculo.zip", { type: "application/zip" }),
        ],
      },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Iniciar limpieza curricular" }),
    );

    const botonCancelar = await screen.findByRole("button", {
      name: "Cancelar procesamiento",
    });
    fireEvent.click(botonCancelar);
    obtenerEjecucionNormalizador.mockResolvedValueOnce({
      id_ejecucion: "NOR_cancelar12345678",
      tipo: "silabos",
      archivo: "curriculo.zip",
      estado: "cancelado",
      cancelacion_solicitada: true,
      validacion_silabos: { valida: true, archivos: [] },
      outputs: [],
      hallazgos: [],
    });

    await waitFor(() =>
      expect(cancelarEjecucionNormalizador).toHaveBeenCalledWith(
        "NOR_cancelar12345678",
      ),
    );
    await waitFor(
      () => expect(screen.getByLabelText("Registro de actividad")).toBeTruthy(),
      { timeout: 1600 },
    );
    expect(confirmacion).toHaveBeenCalledWith(
      "¿Estás seguro de que deseas cancelar el procesamiento?",
    );
    expect(
      screen.queryByRole("button", { name: "Cancelar procesamiento" }),
    ).toBeNull();
    confirmacion.mockRestore();
  });

  it("muestra el registro por etapas, hallazgos y una ejecución sin actividad reciente", async () => {
    const haceSeisMinutos = new Date(Date.now() - 6 * 60 * 1000).toISOString();
    iniciarNormalizadorSilabos.mockResolvedValue({
      id_ejecucion: "NOR_sin_actividad",
      tipo: "silabos",
      archivo: "curriculo.zip",
      estado: "validando",
    });
    obtenerEjecucionNormalizador.mockResolvedValue({
      id_ejecucion: "NOR_sin_actividad",
      tipo: "silabos",
      archivo: "curriculo.zip",
      estado: "limpiando",
      actualizada_en: haceSeisMinutos,
      validacion_silabos: { valida: true, archivos: [] },
      limpieza_silabos: null,
      outputs: [],
      hallazgos: [
        {
          codigo: "SILABO_CAMPO_FALTANTE",
          severidad: "warning",
          mensaje: "Falta una competencia en el sílabo.",
          hoja: "Marketing",
          fila: 8,
        },
      ],
    });

    const { container } = await renderPanelAfterRecovery();
    fireEvent.click(screen.getByRole("tab", { name: "Sílabos" }));
    fireEvent.change(screen.getByRole("combobox", { name: "Carrera" }), {
      target: { value: "Marketing" },
    });
    fireEvent.change(screen.getByRole("combobox", { name: "Periodo" }), {
      target: { value: "2026-1" },
    });
    const archivo = new File(["zip"], "curriculo.zip", {
      type: "application/zip",
    });
    fireEvent.change(container.querySelector('input[type="file"]'), {
      target: { files: [archivo] },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Iniciar limpieza curricular" }),
    );

    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: "Registro de actividad" }),
      ).toBeTruthy(),
    );
    const registro = screen.getByLabelText("Registro de actividad");
    expect(within(registro).getByText("Recepción")).toBeTruthy();
    expect(within(registro).getByText("Validación")).toBeTruthy();
    expect(within(registro).getByText("Limpieza")).toBeTruthy();
    expect(within(registro).getByText("Publicación curricular")).toBeTruthy();
    expect(within(registro).getByText("Sin actividad reciente")).toBeTruthy();
    expect(within(registro).getByText("Advertencia")).toBeTruthy();
    expect(within(registro).getByText("SILABO_CAMPO_FALTANTE")).toBeTruthy();
    expect(within(registro).getByText(/Falta una competencia/)).toBeTruthy();
  });

  it("muestra la revisión técnica antes de los CSV y mantiene separados los artefactos de auditoría", async () => {
    const idEjecucion = "NOR_pre_csv12345678";
    const aprobacionPendiente = {
      requiere_decision: true,
      total: 1,
      pendientes_por_decidir: 1,
      remaining_pending: 1,
      materializacion: {
        candidatos_persistidos: true,
        csv_canonicos_disponibles: false,
      },
    };
    iniciarNormalizadorSilabos.mockResolvedValue({
      id_ejecucion: idEjecucion,
      tipo: "silabos",
      archivo: "curriculo.zip",
      estado: "validando",
    });
    obtenerEjecucionNormalizador.mockResolvedValue({
      id_ejecucion: idEjecucion,
      tipo: "silabos",
      archivo: "curriculo.zip",
      estado: "limpiado",
      configuracion_curricular: { modo_analista: "technical" },
      parametros: { carrera: "Marketing", periodo: "2026-1" },
      validacion_silabos: { valida: true, archivos: [] },
      limpieza_silabos: { registros: 1, relaciones: 1 },
      release_gate: {
        decision: "BLOCK_IMPORT",
        checks: {
          approval: { pending_decision: 1, canonical_materialized: false },
        },
      },
      aprobacion_curricular: aprobacionPendiente,
      outputs: [
        {
          tipo: "propuestas_tecnicas",
          archivo: "salidas/reportes/propuestas_tecnicas.jsonl",
          registros: 1,
        },
        {
          tipo: "analisis_tecnico",
          archivo: "salidas/reportes/analisis_tecnico.json",
          registros: 1,
        },
        {
          tipo: "decisiones_tecnicas",
          archivo: "salidas/reportes/decisiones_tecnicas.jsonl",
          registros: 1,
        },
        {
          tipo: "release_gate",
          archivo: "salidas/reportes/release_gate.json",
          registros: 1,
        },
      ],
      hallazgos: [],
    });
    obtenerPendientesNormalizador.mockResolvedValue({
      filas: [
        {
          id_pendiente: "PEND_1",
          tipo: "competencia_tecnica",
          archivo: "marketing.pdf",
          id_curso: "MKT-101",
          id_silabo: "SIL-1",
          propuesta: {
            nombre: "Diseñar arquitecturas de software",
            descripcion: "Seleccionar patrones técnicos.",
          },
          evidencia: ["Analiza campañas con Google Analytics"],
          flags: [],
        },
      ],
      aprobacion: aprobacionPendiente,
    });

    const { container } = await renderPanelAfterRecovery();
    fireEvent.click(screen.getByRole("tab", { name: "Sílabos" }));
    fireEvent.change(screen.getByRole("combobox", { name: "Carrera" }), {
      target: { value: "Marketing" },
    });
    fireEvent.change(screen.getByRole("combobox", { name: "Periodo" }), {
      target: { value: "2026-1" },
    });
    fireEvent.change(container.querySelector('input[type="file"]'), {
      target: {
        files: [
          new File(["zip"], "curriculo.zip", { type: "application/zip" }),
        ],
      },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Iniciar limpieza curricular" }),
    );

    await waitFor(() =>
      expect(
        screen.getByText("Revisión técnica requerida antes de generar CSV"),
      ).toBeTruthy(),
    );
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: "Revisión técnica requerida" }),
      ).toBeTruthy(),
    );
    expect(
      screen.getByRole("heading", { name: "Auditoría y proveniencia" }),
    ).toBeTruthy();
    expect(screen.getByText("propuestas_tecnicas.jsonl")).toBeTruthy();
    expect(screen.getByText("Diseñar arquitecturas de software")).toBeTruthy();
    expect(
      screen.getByText(
        "Los CSV técnicos no están disponibles hasta que el release gate permita importar.",
      ),
    ).toBeTruthy();
    expect(
      screen.queryByRole("heading", { name: "CSV técnicos listos" }),
    ).toBeNull();
    expect(
      screen.queryByRole("heading", { name: "Subir catálogos a Neo4j" }),
    ).toBeNull();
  });

  it("expone la revisión técnica cuando una ejecución termina no publicada", async () => {
    const idEjecucion = "NOR_tecnico_no_publicado";
    iniciarNormalizadorSilabos.mockResolvedValue({
      id_ejecucion: idEjecucion,
      tipo: "silabos",
      archivo: "curriculo.zip",
      estado: "validando",
    });
    obtenerEjecucionNormalizador.mockResolvedValue({
      id_ejecucion: idEjecucion,
      tipo: "silabos",
      archivo: "curriculo.zip",
      estado: "no_publicado",
      configuracion_curricular: { modo_analista: "technical" },
      parametros: { carrera: "Marketing", periodo: "2026-1" },
      validacion_silabos: { valida: true, archivos: [] },
      aprobacion_curricular: {
        requiere_decision: true,
        pendientes_por_decidir: 1,
      },
      release_gate: {
        decision: "BLOCK_IMPORT",
        blockers: ["PENDING_TECHNICAL_APPROVAL"],
      },
      outputs: [],
      hallazgos: [],
    });
    obtenerPendientesNormalizador.mockResolvedValue({
      filas: [
        {
          id_pendiente: "PROP_TEC_1",
          tipo: "competencia_tecnica",
          nombre_competencia: "Diseñar arquitecturas de software",
          descripcion_breve_competencia: "Seleccionar patrones técnicos.",
          evidencia: ["Diseña arquitecturas de software."],
        },
      ],
      revision: "rev-technical",
      aprobacion: { requiere_decision: true, pendientes_por_decidir: 1 },
    });

    const { container } = await renderPanelAfterRecovery();
    fireEvent.click(screen.getByRole("tab", { name: "Sílabos" }));
    fireEvent.change(screen.getByRole("combobox", { name: "Carrera" }), {
      target: { value: "Marketing" },
    });
    fireEvent.change(screen.getByRole("combobox", { name: "Periodo" }), {
      target: { value: "2026-1" },
    });
    fireEvent.change(container.querySelector('input[type="file"]'), {
      target: {
        files: [
          new File(["zip"], "curriculo.zip", { type: "application/zip" }),
        ],
      },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Iniciar limpieza curricular" }),
    );

    expect(
      await screen.findByRole("heading", {
        name: "Revisión técnica requerida",
      }),
    ).toBeTruthy();
    expect(screen.getByText("Diseñar arquitecturas de software")).toBeTruthy();
    expect(
      screen.getByRole("button", { name: /Competencias técnicas/ }),
    ).toBeTruthy();
  });

  it("habilita la publicación en Neo4j solo con CSV materializados y release gate permitido", async () => {
    const idEjecucion = "NOR_allow_csv123456";
    iniciarNormalizadorSilabos.mockResolvedValue({
      id_ejecucion: idEjecucion,
      tipo: "silabos",
      archivo: "curriculo.zip",
      estado: "validando",
    });
    obtenerEjecucionNormalizador.mockResolvedValue({
      id_ejecucion: idEjecucion,
      tipo: "silabos",
      archivo: "curriculo.zip",
      estado: "limpiado",
      configuracion_curricular: { modo_analista: "technical" },
      parametros: { carrera: "Marketing", periodo: "2026-1" },
      validacion_silabos: { valida: true, archivos: [] },
      release_gate: {
        decision: "ALLOW_IMPORT",
        checks: {
          approval: { pending_decision: 0, canonical_materialized: true },
        },
      },
      aprobacion_curricular: {
        requiere_decision: false,
        pendientes_por_decidir: 0,
        materializacion: { csv_canonicos_disponibles: true },
      },
      outputs: [
        "curso.csv",
        "silabo.csv",
        "catalogo_competencias.csv",
        "catalogo_logros.csv",
        "cobertura_curricular.csv",
      ].map((archivo) => ({
        tipo: "csv_curricular",
        archivo: `salidas/${archivo}`,
        registros: 1,
      })),
      hallazgos: [],
    });
    obtenerPendientesNormalizador.mockResolvedValue({
      filas: [],
      aprobacion: null,
    });

    const { container } = await renderPanelAfterRecovery();
    fireEvent.click(screen.getByRole("tab", { name: "Sílabos" }));
    fireEvent.change(screen.getByRole("combobox", { name: "Carrera" }), {
      target: { value: "Marketing" },
    });
    fireEvent.change(screen.getByRole("combobox", { name: "Periodo" }), {
      target: { value: "2026-1" },
    });
    fireEvent.change(container.querySelector('input[type="file"]'), {
      target: {
        files: [
          new File(["zip"], "curriculo.zip", { type: "application/zip" }),
        ],
      },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Iniciar limpieza curricular" }),
    );

    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: "CSV técnicos listos" }),
      ).toBeTruthy(),
    );
    expect(
      screen.getByRole("heading", { name: "Subir catálogos a Neo4j" }),
    ).toBeTruthy();
    expect(
      screen.getByRole("link", { name: /catalogo_competencias\.csv/ }),
    ).toBeTruthy();
    expect(
      screen.queryByRole("heading", { name: "Revisión técnica requerida" }),
    ).toBeNull();
  });

  it("habilita una ejecución técnica solo con los cinco CSV y el gate técnico permitido", async () => {
    const outputs = [
      "curso.csv",
      "silabo.csv",
      "catalogo_competencias.csv",
      "catalogo_logros.csv",
      "cobertura_curricular.csv",
    ].map((archivo) => ({
      tipo: "csv_curricular",
      archivo: `salidas/${archivo}`,
      registros: 1,
    }));

    await renderTechnicalResult({
      id: "NOR_TECHNICAL_ALLOW",
      outputs,
      gate: { decision: "ALLOW_IMPORT" },
    });

    expect(
      screen.getByRole("heading", { name: "CSV técnicos listos" }),
    ).toBeTruthy();
    expect(
      screen.getByRole("heading", { name: "Subir catálogos a Neo4j" }),
    ).toBeTruthy();
    expect(screen.getAllByText(/CSV técnico canónico/)).toHaveLength(5);
  });

  it("mantiene bloqueada una ejecución técnica con gate bloqueado aunque declare los cinco CSV", async () => {
    const outputs = [
      "curso.csv",
      "silabo.csv",
      "catalogo_competencias.csv",
      "catalogo_logros.csv",
      "cobertura_curricular.csv",
    ].map((archivo) => ({ archivo: `salidas/${archivo}`, registros: 1 }));

    await renderTechnicalResult({
      id: "NOR_TECHNICAL_BLOCKED",
      outputs,
      gate: { decision: "BLOCK_IMPORT" },
    });

    expect(
      screen.getByRole("heading", {
        name: "CSV técnicos bloqueados por el release gate",
      }),
    ).toBeTruthy();
    expect(
      screen.queryByRole("heading", { name: "Subir catálogos a Neo4j" }),
    ).toBeNull();
  });

  it("mantiene bloqueada una ejecución técnica cuando falta un CSV del contrato", async () => {
    const outputs = [
      "curso.csv",
      "silabo.csv",
      "catalogo_competencias.csv",
      "cobertura_curricular.csv",
    ].map((archivo) => ({ archivo: `salidas/${archivo}`, registros: 1 }));

    await renderTechnicalResult({
      id: "NOR_TECHNICAL_MISSING",
      outputs,
      gate: { decision: "ALLOW_IMPORT" },
    });

    expect(
      screen.getByRole("heading", {
        name: "CSV técnicos bloqueados por el release gate",
      }),
    ).toBeTruthy();
    expect(
      screen.queryByRole("heading", { name: "Subir catálogos a Neo4j" }),
    ).toBeNull();
  });
});

describe("progreso LLM del normalizador", () => {
  afterEach(() => cleanup());

  it("normaliza el avance por sílabo y formatea latencias sin inventar datos faltantes", () => {
    const silabos = normalizarProgresoSilabos({
      silabos: [
        {
          indice: 2,
          total: 3,
          id_silabo: "SIL_2",
          archivo: "dos.docx",
          estado_extraccion: "completado",
          estado_analisis: "procesando",
          logros_procesados: 2,
          logros_totales: 4,
          latencia_modelo_ms: 1250,
        },
        {
          id_silabo: "SIL_3",
          estado_analisis: "sin_propuesta",
          logros_totales: 0,
          latencia_modelo_ms: null,
        },
      ],
    });

    expect(silabos[0]).toMatchObject({
      indice: 2,
      porcentaje: 50,
      logrosProcesados: 2,
      logrosTotales: 4,
      latenciaModeloMs: 1250,
    });
    expect(silabos[1].porcentaje).toBe(100);
    expect(silabos[1].latenciaModeloMs).toBeNull();
    expect(formatearLatenciaLLM(1250)).toBe("1.3 s");
    expect(formatearLatenciaLLM(null)).toBe("—");
  });

  it("muestra el progreso serializado por el manifest sin requerir un endpoint adicional", async () => {
    iniciarNormalizadorSilabos.mockResolvedValue({
      id_ejecucion: "NOR_progreso_llm",
      tipo: "silabos",
      archivo: "curriculo.zip",
      estado: "limpiando",
    });
    obtenerEjecucionNormalizador.mockResolvedValue({
      id_ejecucion: "NOR_progreso_llm",
      tipo: "silabos",
      archivo: "curriculo.zip",
      estado: "limpiando",
      validacion_silabos: { valida: true, archivos: [] },
      limpieza_silabos: null,
      outputs: [],
      hallazgos: [],
      progreso_llm: {
        fase: "analista",
        chunks_completados: 3,
        chunks_totales: 5,
        logros_detectados: 40,
        logros_procesados: 24,
        logros_totales: 40,
        silabos_detectados: 10,
        silabos_procesados: 6,
        silabos_totales: 10,
        decisiones_cacheadas: 16,
        reintentos: 1,
        ultimo_chunk: { fase: "analista", logros: 8, silabos: 2 },
        reporte_final: "pendiente",
        eventos: [
          {
            secuencia: 7,
            fase: "analista",
            mensaje:
              "Chunk 3/5 de Analista LLM completado: 8 logros y 2 sílabos únicos.",
            chunks_completados: 3,
            chunks_totales: 5,
            logros_chunk: 8,
            silabos_chunk: 2,
            logros_detectados: 40,
            silabos_detectados: 10,
            silabos_procesados: 6,
            decisiones_cacheadas: 16,
            reintentos: 1,
          },
        ],
      },
    });

    const { container } = await renderPanelAfterRecovery();
    fireEvent.click(screen.getByRole("tab", { name: "Sílabos" }));
    fireEvent.change(screen.getByRole("combobox", { name: "Carrera" }), {
      target: { value: "Marketing" },
    });
    fireEvent.change(screen.getByRole("combobox", { name: "Periodo" }), {
      target: { value: "2026-1" },
    });
    const archivo = new File(["zip"], "curriculo.zip", {
      type: "application/zip",
    });
    fireEvent.change(container.querySelector('input[type="file"]'), {
      target: { files: [archivo] },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Iniciar limpieza curricular" }),
    );

    await waitFor(() =>
      expect(screen.getByLabelText("Progreso de limpieza LLM")).toBeTruthy(),
    );
    const progreso = screen.getByLabelText("Progreso de limpieza LLM");
    expect(within(progreso).getByText("Analista LLM")).toBeTruthy();
    expect(
      within(progreso).getByText("3/5 chunks de la fase actual."),
    ).toBeTruthy();
    expect(within(progreso).getByText("Logros detectados")).toBeTruthy();
    expect(within(progreso).getByText("40")).toBeTruthy();
    expect(within(progreso).getByText("24 / 40")).toBeTruthy();
    expect(within(progreso).getByText("6 / 10")).toBeTruthy();
    expect(within(progreso).getByText("Sílabos detectados")).toBeTruthy();
    expect(
      within(progreso).getByText("Sílabos procesados por LLM"),
    ).toBeTruthy();
    expect(
      within(progreso).getByText(/sílabos detectados 10 · sílabos LLM 6/),
    ).toBeTruthy();
    expect(within(progreso).getByText("16")).toBeTruthy();
    expect(
      within(progreso).getByText(
        "Último chunk de Analista LLM: 8 logros y 2 sílabos.",
      ),
    ).toBeTruthy();
    expect(
      within(progreso).getByText(
        "Chunk 3/5 de Analista LLM completado: 8 logros y 2 sílabos únicos.",
      ),
    ).toBeTruthy();
    const barra = within(progreso).getByRole("progressbar", {
      name: "Avance de chunks LLM",
    });
    expect(barra.getAttribute("aria-valuenow")).toBe("3");
    expect(barra.getAttribute("aria-valuetext")).toBe("3 de 5 chunks");
    expect(obtenerEjecucionNormalizador).toHaveBeenCalledWith(
      "NOR_progreso_llm",
    );
  });

  it("muestra extracción, latencia y avance individual por sílabo", async () => {
    iniciarNormalizadorSilabos.mockResolvedValue({
      id_ejecucion: "NOR_silabos_individuales",
      tipo: "silabos",
      archivo: "curriculo.zip",
      estado: "limpiando",
    });
    obtenerEjecucionNormalizador.mockResolvedValue({
      id_ejecucion: "NOR_silabos_individuales",
      tipo: "silabos",
      archivo: "curriculo.zip",
      estado: "limpiando",
      validacion_silabos: { valida: true, archivos: [] },
      outputs: [],
      hallazgos: [],
      progreso_llm: {
        fase: "analista",
        chunks_completados: 1,
        chunks_totales: 2,
        logros_procesados: 2,
        logros_totales: 4,
        silabos_procesados: 1,
        silabos_totales: 2,
        silabos: [
          {
            indice: 1,
            total: 2,
            id_silabo: "SIL_1",
            archivo: "uno.docx",
            curso: "Arquitectura de software",
            estado_extraccion: "completado",
            estado_analisis: "procesando",
            logros_procesados: 2,
            logros_totales: 4,
            latencia_extraccion_ms: 320,
            latencia_modelo_ms: 1250,
          },
          {
            indice: 2,
            total: 2,
            id_silabo: "SIL_2",
            archivo: "dos.pdf",
            curso: "Bases de datos",
            estado_extraccion: "completado",
            estado_analisis: "sin_propuesta",
            logros_procesados: 0,
            logros_totales: 0,
            latencia_extraccion_ms: 410,
            latencia_modelo_ms: 890,
          },
        ],
        eventos: [],
      },
    });

    const { container } = await renderPanelAfterRecovery();
    fireEvent.click(screen.getByRole("tab", { name: "Sílabos" }));
    fireEvent.change(screen.getByRole("combobox", { name: "Carrera" }), {
      target: { value: "Marketing" },
    });
    fireEvent.change(screen.getByRole("combobox", { name: "Periodo" }), {
      target: { value: "2026-1" },
    });
    fireEvent.change(container.querySelector('input[type="file"]'), {
      target: {
        files: [
          new File(["zip"], "curriculo.zip", { type: "application/zip" }),
        ],
      },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Iniciar limpieza curricular" }),
    );

    const individual = await screen.findByLabelText("Progreso por sílabo");
    expect(within(individual).getByText("Análisis por sílabo")).toBeTruthy();
    expect(within(individual).getByText("1/2 · 50%")).toBeTruthy();
    const filasSilabos = within(individual).getAllByRole("listitem");
    const primeraFila = within(filasSilabos[0]);
    const segundaFila = within(filasSilabos[1]);
    expect(primeraFila.getByText("Arquitectura de software")).toBeTruthy();
    expect(primeraFila.getByText("Extracción: completado")).toBeTruthy();
    expect(primeraFila.getByText("Modelo: en curso")).toBeTruthy();
    expect(primeraFila.getByText("Latencia extracción")).toBeTruthy();
    expect(primeraFila.getByText("320 ms")).toBeTruthy();
    expect(primeraFila.getByText("1.3 s")).toBeTruthy();
    expect(
      primeraFila
        .getByRole("progressbar", {
          name: "Avance de análisis de Arquitectura de software",
        })
        .getAttribute("aria-valuenow"),
    ).toBe("50");
    expect(segundaFila.getByText(/sin propuesta válida/)).toBeTruthy();
  });

  it("mantiene visible el seguimiento mientras el manifest aún no tiene progreso LLM", async () => {
    iniciarNormalizadorSilabos.mockResolvedValue({
      id_ejecucion: "NOR_preparando_llm",
      tipo: "silabos",
      archivo: "curriculo.zip",
      estado: "limpiando",
    });
    obtenerEjecucionNormalizador.mockResolvedValue({
      id_ejecucion: "NOR_preparando_llm",
      tipo: "silabos",
      archivo: "curriculo.zip",
      estado: "limpiando",
      validacion_silabos: { valida: true, archivos: [{ nombre: "uno.pdf" }] },
      limpieza_silabos: null,
      outputs: [],
      hallazgos: [],
      progreso_llm: null,
    });

    const { container } = await renderPanelAfterRecovery();
    fireEvent.click(screen.getByRole("tab", { name: "Sílabos" }));
    fireEvent.change(screen.getByRole("combobox", { name: "Carrera" }), {
      target: { value: "Marketing" },
    });
    fireEvent.change(screen.getByRole("combobox", { name: "Periodo" }), {
      target: { value: "2026-1" },
    });
    fireEvent.change(container.querySelector('input[type="file"]'), {
      target: {
        files: [
          new File(["zip"], "curriculo.zip", { type: "application/zip" }),
        ],
      },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Iniciar limpieza curricular" }),
    );

    await waitFor(() =>
      expect(screen.getByLabelText("Progreso de limpieza LLM")).toBeTruthy(),
    );
    expect(screen.getByText("Preparando…")).toBeTruthy();
    expect(
      screen.getAllByText(/El seguimiento aparecerá aquí enseguida/).length,
    ).toBeGreaterThan(0);
  });
});
