import { notFound } from "next/navigation";

import InspeccionEjecucionNormalizador from "../../src/components/InspeccionEjecucionNormalizador";

const ID_EJECUCION = /^NOR_[0-9a-f]{16}$/;

export const metadata = {
  title: "Ejecución | Normalizador CIAR",
  description:
    "Seguimiento, revisión y publicación de una ejecución del normalizador.",
};

export default async function EjecucionNormalizadorPage({ params }) {
  const { id_ejecucion: idEjecucion } = await params;
  if (!ID_EJECUCION.test(idEjecucion)) notFound();

  return <InspeccionEjecucionNormalizador idEjecucion={idEjecucion} />;
}
