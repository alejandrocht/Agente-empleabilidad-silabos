# Dependencias del frontend — 2026-10-09

La auditoría obligatoria de producción detectó cuatro alertas en las dependencias
ya bloqueadas: Next, Sharp, source-map-js y baseline-browser-mapping. Se aplicó
`rtk npm audit fix --include=dev` dentro de los rangos existentes, sin --force.
El lockfile usa Next 16.4.0, Sharp 0.35.5, source-map-js 1.2.2 y
baseline-browser-mapping 2.11.28; package.json conserva sus rangos.

- `rtk npm audit --omit=dev`: **found 0 vulnerabilities**.
- `rtk npm run check`: **101 passed**, producción compilada correctamente.
- Harness Playwright escritorio/móvil del normalizador en Next 16.4.0: **PASS**.
- Next actualizó automáticamente el nivel del encabezado de frontend/AGENTS.md.

La auditoría completa, incluyendo herramientas de desarrollo, sigue mostrando
diez alertas cuya resolución propuesta requiere cambios mayores de Vitest/Tailwind.
Esos cambios quedan fuera de esta actualización compatible.

Reversión independiente: revertir frontend/package-lock.json y el encabezado
generado de frontend/AGENTS.md, ejecutar npm ci y recompilar. No afecta la lógica
multicarrera ni los catálogos del backend.
