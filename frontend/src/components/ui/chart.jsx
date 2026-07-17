"use client";

import * as React from "react";
import { ResponsiveContainer, Tooltip } from "recharts";

const ChartContext = React.createContext(null);

function unirClases(...clases) {
  return clases.filter(Boolean).join(" ");
}

function useChart() {
  const contexto = React.useContext(ChartContext);
  if (!contexto) {
    throw new Error("Los componentes de chart deben estar dentro de ChartContainer.");
  }
  return contexto;
}

function ChartStyle({ id, config }) {
  const colores = Object.entries(config)
    .filter(([, valor]) => valor?.color || valor?.theme)
    .map(([clave, valor]) => {
      const color = valor.theme?.light || valor.color;
      const colorOscuro = valor.theme?.dark || color;
      return (
        '[data-chart="' +
        id +
        '"] { --color-' +
        clave +
        ": " +
        color +
        "; }\n.dark [data-chart=\"" +
        id +
        '"] { --color-' +
        clave +
        ": " +
        colorOscuro +
        "; }"
      );
    })
    .join("\n");

  return colores ? <style>{colores}</style> : null;
}

export function ChartContainer({ id, className, config, children, ...props }) {
  const uniqueId = React.useId().replace(/:/g, "");
  const chartId = "chart-" + (id || uniqueId);
  const [estaMontado, setEstaMontado] = React.useState(false);

  React.useEffect(() => {
    setEstaMontado(true);
  }, []);

  return (
    <ChartContext.Provider value={{ config }}>
      <div
        data-chart={chartId}
        className={unirClases(
          "relative flex w-full justify-center text-xs [&_.recharts-layer]:outline-none [&_.recharts-surface]:outline-none",
          className,
        )}
        {...props}
      >
        <ChartStyle id={chartId} config={config} />
        {estaMontado ? (
          <ResponsiveContainer width="100%" height="100%">
            {children}
          </ResponsiveContainer>
        ) : null}
      </div>
    </ChartContext.Provider>
  );
}

export const ChartTooltip = Tooltip;

export function ChartTooltipContent({
  active,
  payload,
  label,
  labelFormatter,
  formatter,
  hideLabel = false,
  className,
}) {
  const { config } = useChart();

  if (!active || !payload?.length) return null;

  const etiqueta = labelFormatter ? labelFormatter(label, payload) : label;
  return (
    <div
      className={unirClases(
        "min-w-[9rem] rounded-xl border border-line bg-paper px-3 py-2 text-xs shadow-panel",
        className,
      )}
    >
      {!hideLabel && etiqueta ? <p className="mb-1.5 font-semibold text-ink">{etiqueta}</p> : null}
      <div className="space-y-1.5">
        {payload
          .filter((entrada) => entrada.type !== "none")
          .map((entrada, indice) => {
            const clave = String(entrada.dataKey || entrada.name || "valor");
            const configuracion = config[clave];
            const valor = entrada.value;
            return (
              <div key={clave + "-" + indice} className="flex items-center justify-between gap-5">
                <span className="flex min-w-0 items-center gap-1.5 text-muted">
                  <span
                    className="h-2 w-2 shrink-0 rounded-full"
                    style={{ backgroundColor: entrada.color || configuracion?.color }}
                  />
                  <span className="truncate">{configuracion?.label || entrada.name || clave}</span>
                </span>
                <span className="font-mono font-semibold tabular-nums text-ink">
                  {formatter
                    ? formatter(valor, entrada.name, entrada)
                    : typeof valor === "number"
                      ? valor.toLocaleString("es-PE")
                      : String(valor)}
                </span>
              </div>
            );
          })}
      </div>
    </div>
  );
}
