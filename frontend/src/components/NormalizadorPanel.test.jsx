import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import NormalizadorPanel from "./NormalizadorPanel";
import {
  iniciarNormalizadorSilabos,
  iniciarNormalizadorSilabosCactus,
  listarEjecucionesNormalizador,
  obtenerEjecucionNormalizador,
  registrarCambioHitlNormalizador,
} from "../api/normalizador";

const navigation = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }));

vi.mock("next/navigation", () => ({
  useRouter: () => navigation,
}));

vi.mock("../api/normalizador", () => ({
  iniciarNormalizadorSilabos: vi.fn(),
  iniciarNormalizadorSilabosCactus: vi.fn(),
  listarEjecucionesNormalizador: vi.fn(),
  registrarCambioHitlNormalizador: vi.fn().mockResolvedValue(undefined),
  obtenerEjecucionNormalizador: vi.fn(),
  eliminarEjecucionHistorialNormalizador: vi.fn(),
}));

const activa = (id = "NOR_active12345678", extra = {}) => ({
  id_ejecucion: id,
  tipo: "silabos",
  archivo: "curriculo.zip",
  estado: "limpiando",
  parametros: { carrera: "Marketing", periodo: "2026-1", hitl: 0 },
  ...extra,
});

async function renderPanel() {
  const rendered = render(<NormalizadorPanel />);
  await waitFor(() =>
    expect(screen.getByRole("switch", { name: "HITL técnico" }).disabled).toBe(
      false,
    ),
  );
  return rendered;
}

function completarFormularioManual(container) {
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
}

describe("panel del normalizador", () => {
  afterEach(() => cleanup());

  beforeEach(() => {
    vi.clearAllMocks();
    listarEjecucionesNormalizador.mockResolvedValue({ ejecuciones: [] });
    obtenerEjecucionNormalizador.mockResolvedValue(activa());
  });

  it("mantiene el formulario Cactus/manual y aplica HITL seleccionado al iniciar", async () => {
    iniciarNormalizadorSilabosCactus.mockResolvedValue(activa("NOR_cactus12345678"));
    const { container } = await renderPanel();

    expect(screen.getByRole("button", { name: /Extraer desde Cactus/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Cargar archivo manual/ })).toBeTruthy();
    expect(screen.getByText(/próxima ejecución/)).toBeTruthy();
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
    fireEvent.click(screen.getByRole("button", { name: "Extraer y normalizar sílabos" }));

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
    expect(container.querySelector('input[type="file"]')).toBeTruthy();
    expect(screen.queryByLabelText("Registro de actividad")).toBeNull();
    expect(screen.queryByLabelText("Progreso de limpieza LLM")).toBeNull();
    expect(screen.queryByRole("heading", { name: /CSV técnicos/ })).toBeNull();
  });

  it("inicia una carga manual, navega al inspector y no duplica detalles de ejecución", async () => {
    iniciarNormalizadorSilabos.mockResolvedValue(activa("NOR_manual12345678"));
    const { container } = await renderPanel();
    completarFormularioManual(container);
    fireEvent.click(screen.getByRole("button", { name: "Iniciar limpieza curricular" }));

    await waitFor(() =>
      expect(iniciarNormalizadorSilabos).toHaveBeenCalledWith(
        expect.any(File),
        "Marketing",
        "2026-1",
        1,
      ),
    );
    expect(navigation.push).toHaveBeenCalledWith("/NOR_manual12345678");
    expect(screen.getByRole("link", { name: "Abrir inspección de ejecución" }).getAttribute("href"))
      .toBe("/NOR_manual12345678");
    expect(screen.queryByLabelText("Registro de actividad")).toBeNull();
    expect(screen.queryByLabelText("Progreso de limpieza LLM")).toBeNull();
    expect(screen.queryByLabelText("Progreso por sílabo")).toBeNull();
    expect(screen.queryByRole("button", { name: "Cancelar procesamiento" })).toBeNull();
    expect(screen.queryByRole("heading", { name: /CSV técnicos/ })).toBeNull();
  });

  it("registra la selección HITL y conserva el modo manual antes de iniciar", async () => {
    iniciarNormalizadorSilabos.mockResolvedValue(activa("NOR_hitl12345678"));
    const { container } = await renderPanel();
    completarFormularioManual(container);
    fireEvent.click(screen.getByRole("switch", { name: "HITL técnico" }));
    expect(registrarCambioHitlNormalizador).toHaveBeenCalledWith(0);
    fireEvent.click(screen.getByRole("button", { name: "Iniciar limpieza curricular" }));

    await waitFor(() =>
      expect(iniciarNormalizadorSilabos).toHaveBeenCalledWith(
        expect.any(File),
        "Marketing",
        "2026-1",
        0,
      ),
    );
  });

  it("restaura una ejecución activa sin redirigir y enlaza solo a su inspección", async () => {
    const id = "NOR_restaurar12345678";
    listarEjecucionesNormalizador.mockResolvedValue({ ejecuciones: [activa(id)] });
    obtenerEjecucionNormalizador.mockResolvedValue(activa(id));

    render(<NormalizadorPanel />);

    const inspectionLink = await screen.findByRole("link", {
      name: "Abrir inspección de ejecución",
    });
    expect(inspectionLink.getAttribute("href")).toBe(`/${id}`);
    expect(navigation.push).not.toHaveBeenCalled();
    expect(navigation.replace).not.toHaveBeenCalled();
    expect(screen.getByRole("switch", { name: "HITL técnico" }).disabled).toBe(true);
    expect(screen.getByRole("combobox", { name: "Carrera" }).disabled).toBe(true);
    expect(screen.getByRole("link", { name: "Inspeccionar" }).getAttribute("href")).toBe(`/${id}`);
    expect(screen.queryByText("Aprobación técnica automática")).toBeNull();
    expect(screen.queryByLabelText("Registro de actividad")).toBeNull();
    expect(screen.queryByLabelText("Progreso de limpieza LLM")).toBeNull();
  });

  it("bloquea la entrada durante una ejecución y la desbloquea al quedar terminal", async () => {
    const id = "NOR_lock123456789";
    listarEjecucionesNormalizador.mockResolvedValue({ ejecuciones: [activa(id)] });
    obtenerEjecucionNormalizador
      .mockResolvedValueOnce(activa(id))
      .mockResolvedValueOnce({ ...activa(id), estado: "limpiado" });

    render(<NormalizadorPanel />);

    await waitFor(() =>
      expect(screen.getByRole("switch", { name: "HITL técnico" }).disabled).toBe(
        true,
      ),
    );
    await waitFor(
      () =>
        expect(screen.getByRole("switch", { name: "HITL técnico" }).disabled).toBe(
          false,
        ),
      { timeout: 2500 },
    );
    expect(screen.queryByRole("link", { name: "Abrir inspección de ejecución" })).toBeNull();
  });

  it("mantiene el historial debajo del formulario", async () => {
    await renderPanel();

    const history = screen.getByRole("region", { name: "Historial de ejecuciones" });
    expect(screen.getByRole("heading", { name: "Paquete curricular" }).compareDocumentPosition(history) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByRole("button", { name: "Actualizar" })).toBeTruthy();
  });
});
