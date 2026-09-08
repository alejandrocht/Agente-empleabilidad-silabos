import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import BarraInput from "./BarraInput";
import Burbuja, { renderRespuesta } from "./Burbuja";
import PanelRazonamiento from "./PanelRazonamiento";
import TablaFilas from "./TablaFilas";
import { normalizeChatValues, textoUltimoMensajeAsistente } from "../hooks/useChat";

describe("interfaz del chat", () => {
  it("renderiza el formato Markdown básico de la respuesta como HTML", () => {
    const { container } = render(
      <div>{renderRespuesta("### ¿De qué trata?\n\nEs un curso **teórico-práctico**.\n\n- **Diseño**")}</div>,
    );

    expect(container.querySelector("h3")?.textContent).toBe("¿De qué trata?");
    expect(container.querySelector("strong")?.textContent).toBe("teórico-práctico");
    expect(container.querySelector("ul li strong")?.textContent).toBe("Diseño");
  });

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

  it("oculta identificadores, normaliza los valores y agrega un análisis breve", () => {
    render(
      <TablaFilas
        filas={[
          { curso_id: "CUR_INTERNO_1", curso: "Analítica de Negocios" },
          { curso_id: "CUR_INTERNO_2", curso: "Filosofía Aplicada" },
        ]}
      />,
    );

    expect(screen.queryByText(/CUR_INTERNO/)).toBeNull();
    expect(screen.queryByText("Curso id")).toBeNull();
    expect(screen.getByText("ANALÍTICA DE NEGOCIOS")).toBeTruthy();
    expect(screen.getByText("FILOSOFÍA APLICADA")).toBeTruthy();
    expect(screen.getByText(/Análisis breve: se encontraron 2 cursos/)).toBeTruthy();
  });

  it("muestra las tablas extensas de forma progresiva", () => {
    const filas = Array.from({ length: 10 }, (_, indice) => ({ herramienta: `Herramienta ${indice + 1}`, ofertas: indice + 1 }));
    render(<TablaFilas filas={filas} />);

    expect(screen.getByRole("button", { name: "Ver 2 resultados más" })).toBeTruthy();
    expect(screen.queryByText("HERRAMIENTA 10")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Ver 2 resultados más" }));
    expect(screen.getByText("HERRAMIENTA 10")).toBeTruthy();
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
        progreso: { etapa: "privado" },
        error: { message: "privado" },
      }),
    ).toEqual({
      texto: "",
      cypher: "",
      fase: "",
      progreso: "",
      entidades: [],
      error: "",
    });
  });

  it("lee la respuesta incremental del evento nativo messages", () => {
    expect(
      textoUltimoMensajeAsistente([
        { type: "ai", id: "1", content: "Parte final" },
        { type: "human", id: "2", content: "privado" },
      ]),
    ).toBe("Parte final");
  });

  it("muestra el progreso actual mientras llega la respuesta", () => {
    render(
      <Burbuja
        mensaje={{
          rol: "agente",
          streaming: true,
          fase: "preparando_consulta",
          progreso: "Identificando los conceptos clave…",
        }}
      />,
    );

    expect(screen.getByText("Identificando los conceptos clave…")).toBeTruthy();
    expect(screen.queryByText("Ruta ejecutada")).toBeNull();
    expect(screen.getByRole("status")).toBeTruthy();
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

  it("explica cuando una respuesta se detuvo por tiempo", () => {
    render(<Burbuja mensaje={{ rol: "agente", error: "graph_timeout" }} />);

    expect(screen.getByText(/tardó demasiado/)).toBeTruthy();
  });

  it("explica cuando la pregunta está fuera del alcance de CIAR", () => {
    render(<Burbuja mensaje={{ rol: "agente", error: "fuera_de_alcance" }} />);

    expect(screen.getByText(/fuera del alcance de CIAR/)).toBeTruthy();
  });

  it("explica cuando la fuente de datos no está disponible", () => {
    render(<Burbuja mensaje={{ rol: "agente", error: "schema_unavailable" }} />);

    expect(screen.getByText(/fuente de datos de empleabilidad/)).toBeTruthy();
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

  it("no muestra las filas internas del analista en el chat", () => {
    const { container } = render(
      <Burbuja
        mensaje={{
          rol: "agente",
          texto: "El curso trata sobre algoritmos.",
          filas: [{ nombre_curso: "Análisis y Diseño de Algoritmos" }],
        }}
      />,
    );

    expect(screen.getByText("El curso trata sobre algoritmos.")).toBeTruthy();
    expect(container.querySelector('[aria-label="Detalle de resultados"]')).toBeNull();
  });

  it("conserva el aviso de solo lectura para bloqueos Cypher", () => {
    render(<PanelRazonamiento error="cypher_injection" />);
    const toggles = screen.getAllByRole("button", { name: /Detalles de la consulta/ });
    fireEvent.click(toggles[toggles.length - 1]);

    expect(screen.getByText(/Consulta bloqueada por seguridad/)).toBeTruthy();
  });

});
