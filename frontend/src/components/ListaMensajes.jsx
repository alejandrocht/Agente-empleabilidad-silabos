import Burbuja from "./Burbuja";

export default function ListaMensajes({ mensajes, enviando }) {
  if (mensajes.length === 0 && !enviando) {
    return (
      <div className="grid flex-1 place-items-center py-16">
        <div className="max-w-xl rounded-3xl border border-line bg-white p-8 text-center shadow-panel">
          <p className="font-mono text-xs uppercase tracking-[0.24em] text-ulima">
            Agente Ciar
          </p>
          <h2 className="mt-3 text-3xl font-extrabold leading-tight sm:text-4xl">
            Pregunta sobre carreras, cursos y empleabilidad.
          </h2>
          <p className="mt-4 text-base text-muted">
            La respuesta incluye el Cypher generado, las entidades resueltas y los pasos del agente.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 space-y-5">
      {mensajes.map((mensaje, index) => (
        <Burbuja key={`${mensaje.rol}-${index}`} mensaje={mensaje} />
      ))}
      {enviando ? <Burbuja mensaje={{ rol: "agente", cargando: true }} /> : null}
    </div>
  );
}
