import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import CatalogoHabTecPanel from "./CatalogoHabTecPanel";
import {
  cargarCatalogoHabTec,
  obtenerCatalogoHabTec,
  vectorizarCatalogoHabTec,
} from "../api/normalizador";

vi.mock("../api/normalizador", () => ({
  cargarCatalogoHabTec: vi.fn(),
  obtenerCatalogoHabTec: vi.fn(),
  vectorizarCatalogoHabTec: vi.fn(),
}));

const catalogoValidado = {
  id_catalogo: "HABTEC_0123456789abcdef",
  archivo: "hab_tec.xlsx",
  estado: "listo_para_vectorizar",
  hoja: "HAB_TEC",
  resumen: { habilidades: 1, errores: 0, advertencias: 0 },
  preview: [
    {
      id: "HAB_TEC_001",
      nombre: "Inteligencia Artificial",
      carrera: "Ingeniería de Sistemas",
      descripcion: "Modelos predictivos",
      fila: 2,
    },
  ],
  hallazgos: [],
};

describe("CatalogoHabTecPanel", () => {
  afterEach(() => vi.clearAllMocks());

  it("valida un XLSX y permite iniciar la vectorización", async () => {
    cargarCatalogoHabTec.mockResolvedValue(catalogoValidado);
    vectorizarCatalogoHabTec.mockResolvedValue({
      ...catalogoValidado,
      estado: "vectorizando",
      resumen: { ...catalogoValidado.resumen, modelo_embedding: "qwen3-embedding:0.6b" },
    });
    obtenerCatalogoHabTec.mockResolvedValue(catalogoValidado);
    const { container } = render(<CatalogoHabTecPanel />);
    const archivo = new File(["xlsx"], "hab_tec.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });

    fireEvent.change(container.querySelector('input[type="file"]'), {
      target: { files: [archivo] },
    });
    fireEvent.click(screen.getByRole("button", { name: "Validar catálogo" }));

    await waitFor(() => expect(cargarCatalogoHabTec).toHaveBeenCalledWith(archivo));
    expect(screen.getByText("Inteligencia Artificial")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Vectorizar con Qwen local" }));
    await waitFor(() =>
      expect(vectorizarCatalogoHabTec).toHaveBeenCalledWith("HABTEC_0123456789abcdef"),
    );
    expect(screen.getByText("Creando vectores y sincronizando catálogo…")).toBeTruthy();
  });
});
