import { redirect } from "next/navigation";

export default async function InspeccionEjecucionPage({ params }) {
  const { id_ejecucion: idEjecucion } = await params;
  redirect(`/${encodeURIComponent(idEjecucion)}`);
}
