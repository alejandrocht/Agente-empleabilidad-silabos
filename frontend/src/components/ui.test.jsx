import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import BarraInput from "./BarraInput";
import Burbuja from "./Burbuja";
import PanelRazonamiento from "./PanelRazonamiento";
import TablaFilas from "./TablaFilas";
import { normalizeChatValues } from "../hooks/useChat";

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

  it("no duplica un valor único que ya se presenta en la respuesta", () => {
    render(<TablaFilas filas={[{ total: 14 }]} />);

    expect(screen.queryByLabelText("Detalle de resultados")).toBeNull();
  });

  it("presenta tablas con encabezados legibles y nulos explícitos", () => {
    render(<TablaFilas filas={[{ nombre_puesto: null, ofertas: 10 }]} />);

    expect(screen.getByText("Nombre puesto")).toBeTruthy();
    expect(screen.getByText("Ofertas")).toBeTruthy();
    expect(screen.getByText("—")).toBeTruthy();
  });

  it("muestra las tablas extensas de forma progresiva", () => {
    const filas = Array.from({ length: 10 }, (_, indice) => ({ herramienta: `Herramienta ${indice + 1}`, ofertas: indice + 1 }));
    render(<TablaFilas filas={filas} />);

    expect(screen.getByRole("button", { name: "Ver 2 resultados más" })).toBeTruthy();
    expect(screen.queryByText("Herramienta 10")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Ver 2 resultados más" }));
    expect(screen.getByText("Herramienta 10")).toBeTruthy();
  });

  it("ignora texto no textual sin renderizar objetos internos", () => {
    const { rerender } = render(
      <Burbuja mensaje={{ rol: "agente", texto: { type: "reasoning", content: "privado" } }} />,
    );

    expect(screen.queryByText("privado")).toBeNull();

    rerender(<Burbuja mensaje={{ rol: "agente", texto: "Respuesta pública" }} />);
    expect(screen.getByText("Respuesta pública")).toBeTruthy();
  });

  it("normaliza escalares y colecciones malformadas del stream", () => {
    expect(
      normalizeChatValues({
        respuesta: { type: "reasoning", content: "privado" },
        cypher: ["MATCH (n)"],
        entidades: { nombre: "privado" },
        filas: "privado",
        pasos: null,
        error: { message: "privado" },
      }),
    ).toEqual({
      texto: "",
      cypher: "",
      fase: "",
      entidades: [],
      filas: [],
      pasos: [],
      error: "",
    });
  });

  it("no entrega errores ni colecciones malformadas a React", () => {
    render(
      <Burbuja
        mensaje={{
          rol: "agente",
          texto: ["privado"],
          error: { message: "privado" },
          errorRed: ["privado"],
          cypher: { query: "privado" },
          entidades: { nombre: "privado" },
          filas: { total: 1 },
          pasos: { etapa: "privado" },
        }}
      />,
    );

    expect(screen.queryByText(/privado/)).toBeNull();
  });

  it("presenta planner_failed como un error de interpretación", () => {
    render(<Burbuja mensaje={{ rol: "agente", error: "planner_failed" }} />);

    expect(screen.getByText(/No pude interpretar la consulta/)).toBeTruthy();
    expect(screen.queryByText(/Consulta bloqueada por seguridad/)).toBeNull();
  });

  it("muestra el Cypher validado en la respuesta del agente", () => {
    render(
      <Burbuja
        mensaje={{
          rol: "agente",
          texto: "Encontré resultados.",
          cypher: "MATCH (n:Carrera) RETURN n.nombre AS nombre LIMIT $limit",
        }}
      />,
    );

    expect(screen.getByText("Cypher generado")).toBeTruthy();
    expect(screen.getByText(/MATCH/)).toBeTruthy();
  });

  it("conserva el aviso de solo lectura para bloqueos Cypher", () => {
    render(<PanelRazonamiento error="cypher_injection" />);
    const toggles = screen.getAllByRole("button", { name: /Traza del grafo/ });
    fireEvent.click(toggles[toggles.length - 1]);

    expect(screen.getByText(/Consulta bloqueada por seguridad/)).toBeTruthy();
  });

});
