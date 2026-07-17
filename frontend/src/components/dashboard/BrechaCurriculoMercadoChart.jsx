"use client";

import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "../ui/chart";
import EstadoGrafico from "./EstadoGrafico";

const chartConfig = {
  demandaPct: { label: "Demanda laboral", color: "#FF5117" },
  coberturaPct: { label: "Cobertura declarada", color: "#00C5D6" },
};

function abreviar(valor) {
  return valor.length > 22 ? valor.slice(0, 21) + "…" : valor;
}

function Leyenda() {
  return (
    <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted">
      <span className="flex items-center gap-1.5">
        <i className="h-2.5 w-2.5 rounded-sm bg-ulima" /> Demanda laboral
      </span>
      <span className="flex items-center gap-1.5">
        <i className="h-2.5 w-2.5 rounded-sm bg-secundario-turquesa" /> Cobertura declarada
      </span>
    </div>
  );
}

export default function BrechaCurriculoMercadoChart({ filas, cargando, error, disponible, motivo }) {
  if (cargando || error || !disponible || !filas?.length) {
    return (
      <EstadoGrafico
        cargando={cargando}
        error={error}
        vacio={!disponible || !filas?.length}
        mensajeVacio={motivo || "No hay elementos comparables para estos filtros."}
      />
    );
  }

  const datos = [...filas]
    .map((fila) => ({
      ...fila,
      demandaPct: Math.round(fila.demanda * 1000) / 10,
      coberturaPct: Math.round(fila.cobertura * 1000) / 10,
    }))
    .reverse();

  return (
    <>
      <ChartContainer config={chartConfig} className="h-80 min-h-[20rem] w-full">
        <BarChart accessibilityLayer data={datos} layout="vertical" margin={{ top: 4, right: 12, left: 6, bottom: 2 }}>
          <CartesianGrid horizontal={false} stroke="#EAE2D9" />
          <XAxis
            type="number"
            domain={[0, 100]}
            tickFormatter={(valor) => String(valor) + "%"}
            axisLine={false}
            tickLine={false}
            tick={{ fill: "#7A6F66", fontSize: 11 }}
          />
          <YAxis
            dataKey="elemento"
            type="category"
            width={132}
            axisLine={false}
            tickLine={false}
            tick={{ fill: "#4F463F", fontSize: 11 }}
            tickFormatter={abreviar}
          />
          <ChartTooltip
            content={
              <ChartTooltipContent
                labelFormatter={(valor) => valor}
                formatter={(valor) => Number(valor).toLocaleString("es-PE", { maximumFractionDigits: 1 }) + "%"}
              />
            }
          />
          <Bar dataKey="demandaPct" fill="var(--color-demandaPct)" radius={[4, 4, 4, 4]} />
          <Bar dataKey="coberturaPct" fill="var(--color-coberturaPct)" radius={[4, 4, 4, 4]} />
        </BarChart>
      </ChartContainer>
      <Leyenda />
    </>
  );
}
