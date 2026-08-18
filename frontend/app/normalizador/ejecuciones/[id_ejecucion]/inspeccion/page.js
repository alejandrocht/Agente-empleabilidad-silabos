import InspeccionEjecucionNormalizador from "../../../../../src/components/InspeccionEjecucionNormalizador";

export const metadata = {
  title: "Inspección de ejecución | Normalizador CIAR",
  description: "Consulta de solo lectura de resultados, CSV y eventos de una ejecución histórica.",
};

export default async function InspeccionEjecucionPage({ params }) {
  const { id_ejecucion: idEjecucion } = await params;
  return <InspeccionEjecucionNormalizador idEjecucion={idEjecucion} />;
}
