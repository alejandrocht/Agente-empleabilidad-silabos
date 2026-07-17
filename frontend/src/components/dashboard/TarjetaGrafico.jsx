export default function TarjetaGrafico({ id, titulo, descripcion, accion, children, className = "" }) {
  return (
    <section id={id} className={"scroll-mt-24 rounded-2xl border border-line bg-paper p-4 shadow-sm sm:p-5 " + className}>
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-extrabold tracking-tight text-ink">{titulo}</h2>
          {descripcion ? <p className="mt-1 max-w-2xl text-sm leading-5 text-muted">{descripcion}</p> : null}
        </div>
        {accion}
      </div>
      {children}
    </section>
  );
}
