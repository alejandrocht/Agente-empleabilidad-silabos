import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Neo4jImportPanel from "./Neo4jImportPanel";
import {
  importarEnNeo4j,
  listarImportacionesNeo4j,
  revertirImportacionNeo4j,
  validarImportacionNeo4j,
} from "../api/neo4j";

vi.mock("../api/neo4j", () => ({
  importarEnNeo4j: vi.fn(),
  listarImportacionesNeo4j: vi.fn(),
  revertirImportacionNeo4j: vi.fn(),
  validarImportacionNeo4j: vi.fn(),
}));

const previewListo = {
  id_ejecucion: "NOR_0123456789abcdef",
  fingerprint: "a".repeat(64),
  puede_importar: true,
  mensaje: "La data está validada y lista para confirmar.",
  recomendacion: "Recomendamos revisar los datos antes de subirlos a la base de datos.",
  resumen: {
    nuevas_competencias: 1,
    nuevas_habilidades: 2,
    nuevas_herramientas: 1,
    nuevas_coberturas: 3,
    sin_cambios: 4,
  },
  archivos: [{ archivo: "catalogo_competencias.csv", nuevas: 1, sin_cambios: 0 }],
  conflictos: [],
  errores: [],
};

describe("publicación curricular en Neo4j", () => {
  afterEach(() => cleanup());

  beforeEach(() => {
    vi.clearAllMocks();
    listarImportacionesNeo4j.mockResolvedValue({ importaciones: [] });
    importarEnNeo4j.mockResolvedValue({
      mensaje: "La información nueva fue agregada a Neo4j.",
      id_importacion: "IMP_0123456789abcdef",
    });
  });

  it("valida, muestra el popup de confirmación y publica con fingerprint", async () => {
    validarImportacionNeo4j.mockResolvedValue(previewListo);
    render(<Neo4jImportPanel idEjecucion="NOR_0123456789abcdef" />);

    fireEvent.click(screen.getByRole("button", { name: "Subir datos a Neo4j" }));
    const dialogo = await screen.findByRole("dialog");
    expect(within(dialogo).getByText(/¿Estás seguro de que deseas agregar estos datos/)).toBeTruthy();
    expect(within(dialogo).getByText(/Recomendamos revisar los datos antes de subirlos a la base de datos/)).toBeTruthy();
    expect(within(dialogo).getByText("3", { exact: true })).toBeTruthy();

    fireEvent.click(within(dialogo).getByRole("button", { name: "Agregar a Neo4j" }));

    await waitFor(() => {
      expect(importarEnNeo4j).toHaveBeenCalledWith(
        "NOR_0123456789abcdef",
        "a".repeat(64),
        true,
      );
    });
    expect(await screen.findByText(/IMP_0123456789abcdef/)).toBeTruthy();
  });

  it("bloquea la confirmación cuando hay conflicto o no hay novedad", async () => {
    validarImportacionNeo4j.mockResolvedValue({
      ...previewListo,
      puede_importar: false,
      mensaje: "La data requiere correcciones antes de importarse.",
      conflictos: [{ codigo: "ID_DUPLICADO", mensaje: "El ID ya existe con otros atributos." }],
    });
    render(<Neo4jImportPanel idEjecucion="NOR_0123456789abcdef" />);

    fireEvent.click(screen.getByRole("button", { name: "Subir datos a Neo4j" }));
    const dialogo = await screen.findByRole("dialog");
    expect(within(dialogo).getByText("El ID ya existe con otros atributos.")).toBeTruthy();
    expect(within(dialogo).getByRole("button", { name: "Agregar a Neo4j" }).disabled).toBe(true);
    expect(importarEnNeo4j).not.toHaveBeenCalled();
  });

  it("permite revertir la última importación desde el segundo control", async () => {
    listarImportacionesNeo4j.mockResolvedValue({
      importaciones: [{ id_importacion: "IMP_0123456789abcdef", estado: "completada" }],
    });
    revertirImportacionNeo4j.mockResolvedValue({ mensaje: "La importación fue revertida." });
    render(<Neo4jImportPanel idEjecucion="NOR_0123456789abcdef" />);

    const boton = await screen.findByRole("button", { name: "Revertir última importación" });
    fireEvent.click(boton);
    const dialogo = await screen.findByRole("dialog");
    expect(within(dialogo).getByText(/Solo se eliminarán los nodos y relaciones/)).toBeTruthy();
    fireEvent.click(within(dialogo).getByRole("button", { name: "Revertir importación" }));

    await waitFor(() => {
      expect(revertirImportacionNeo4j).toHaveBeenCalledWith(
        "IMP_0123456789abcdef",
        true,
      );
    });
    expect(await screen.findByText("La importación fue revertida.")).toBeTruthy();
  });
});
