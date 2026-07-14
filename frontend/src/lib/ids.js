export function crearId(prefijo) {
  const aleatorio =
    typeof crypto !== "undefined" && crypto.randomUUID
      ? crypto.randomUUID()
      : `${Date.now().toString(16)}-${Math.random().toString(16).slice(2)}`;
  return `${prefijo}-${aleatorio}`;
}
