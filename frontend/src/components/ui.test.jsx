import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import BarraInput from "./BarraInput";
import TablaFilas from "./TablaFilas";

describe("interfaz del chat", () => {
  it("envía una pregunta escrita y limpia el campo", () => {
    const enviar = vi.fn();
    render(<BarraInput onEnviar={enviar} disabled={false} />);

    const campo = screen.getByPlaceholderText(
      "Pregunta sobre carreras, cursos, empresas o empleabilidad…",
    );
    fireEvent.change(campo, { target: { value: "¿Cuántas carreras hay?" } });
    fireEvent.click(screen.getByRole("button", { name: "Enviar pregunta" }));

    expect(enviar).toHaveBeenCalledWith("¿Cuántas carreras hay?");
    expect(campo.value).toBe("");
  });

  it("presenta una métrica única como tarjeta", () => {
    render(<TablaFilas filas={[{ total: 14 }]} />);

    expect(screen.getByText("Total")).toBeTruthy();
    expect(screen.getByText("14")).toBeTruthy();
  });

  it("presenta tablas con encabezados legibles y nulos explícitos", () => {
    render(<TablaFilas filas={[{ nombre_puesto: null, ofertas: 10 }]} />);

    expect(screen.getByText("Nombre puesto")).toBeTruthy();
    expect(screen.getByText("Ofertas")).toBeTruthy();
    expect(screen.getByText("—")).toBeTruthy();
  });
});
