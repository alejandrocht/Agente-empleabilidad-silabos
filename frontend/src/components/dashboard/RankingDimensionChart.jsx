"use client";

import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "../ui/chart";
import EstadoGrafico from "./EstadoGrafico";

const configuraciones = {
  demanda: {
    valor: "ofertas",
    etiqueta: "Ofertas",
    color: "#FF5117",
  },
  cobertura: {
    valor: "cursos_con_cobertura",
    etiqueta: "Cursos",
    color: "#00C5D6",
  },
  destinos: {
    valor: "oportunidades",
    etiqueta: "Oportunidades",
    color: "#8A6FB8",
  },
  densidad: {
    valor: "indice",
    etiqueta: "Índice de preparación",
    color: "#2E8C7F",
  },
  empresas: {
    valor: "ofertas",
    etiqueta: "Oportunidades",
    color: "#3D7A9E",
  },
};

function abreviar(valor) {
  return valor.length > 24 ? valor.slice(0, 23) + "…" : valor;
}

export default function RankingDimensionChart({ tipo, filas, cargando, error, disponible = true, motivo }) {
  const configuracion = configuraciones[tipo];
  if (cargando || error || !disponible || !filas?.length) {
    return (
      <EstadoGrafico
        cargando={cargando}
        error={error}
        vacio={!disponible || !filas?.length}
        mensajeVacio={motivo || "No hay elementos registrados para estos filtros."}
      />
    );
  }

  const datos = [...filas].reverse();
  return (
    <ChartContainer
      config={{ [configuracion.valor]: { label: configuracion.etiqueta, color: configuracion.color } }}
      className="h-72 min-h-[18rem] w-full"
    >
      <BarChart accessibilityLayer data={datos} layout="vertical" margin={{ top: 2, right: 16, left: 6, bottom: 2 }}>
        <CartesianGrid horizontal={false} stroke="#EAE2D9" />
        <XAxis
          type="number"
          allowDecimals={false}
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
              formatter={(valor) => Number(valor).toLocaleString("es-PE")}
            />
          }
        />
        <Bar
          dataKey={configuracion.valor}
          fill={"var(--color-" + configuracion.valor + ")"}
          radius={[5, 5, 5, 5]}
        />
      </BarChart>
    </ChartContainer>
  );
}
