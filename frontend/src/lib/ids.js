export function crearId(prefijo) {
  const aleatorio =
    typeof crypto !== "undefined" && crypto.randomUUID
      ? crypto.randomUUID().slice(0, 8)
      : Math.random().toString(16).slice(2, 10);
  return `${prefijo}-${aleatorio}`;
}
