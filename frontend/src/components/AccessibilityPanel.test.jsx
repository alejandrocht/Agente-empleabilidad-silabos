import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import AccessibilityPanel from "./AccessibilityPanel";

describe("centro de accesibilidad", () => {
  const store = new Map();
  const localStorage = {
    getItem: (key) => store.get(key) ?? null,
    setItem: (key, value) => store.set(key, String(value)),
    clear: () => store.clear(),
  };

  beforeEach(() => {
    Object.defineProperty(window, "localStorage", { configurable: true, value: localStorage });
    localStorage.clear();
    document.body.className = "";
  });

  afterEach(cleanup);

  it("abre los módulos y aplica un ajuste de contenido", () => {
    render(<AccessibilityPanel />);

    fireEvent.click(screen.getByRole("button", { name: "Abrir ajustes de accesibilidad" }));
    expect(screen.getByRole("dialog", { name: "Ajustes de accesibilidad" })).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Fuente legible" }));

    expect(document.body.classList.contains("a11y-readable-font")).toBe(true);
    expect(JSON.parse(localStorage.getItem("ciar-accessibility-settings")).readableFont).toBe(true);
  });

  it("restablece los ajustes activos", () => {
    render(<AccessibilityPanel />);

    fireEvent.click(screen.getByRole("button", { name: "Abrir ajustes de accesibilidad" }));
    fireEvent.click(screen.getByRole("button", { name: "Fuente legible" }));
    fireEvent.click(screen.getByRole("button", { name: "Reiniciar ajustes" }));

    expect(document.body.classList.contains("a11y-readable-font")).toBe(false);
  });
});
