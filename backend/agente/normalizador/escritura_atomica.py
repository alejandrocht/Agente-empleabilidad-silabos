"""Escritura atómica con temporales independientes y tolerancia a bloqueos de Windows."""

from pathlib import Path
from tempfile import NamedTemporaryFile
from time import sleep

_ESPERAS_BLOQUEO_WINDOWS = (0.05, 0.1, 0.2, 0.4, 0.8, 1.0, 1.0)


def escribir_texto_atomico(ruta: Path, contenido: str) -> None:
    """Conserva la versión anterior hasta completar el reemplazo del archivo."""

    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=ruta.parent,
            prefix=f".{ruta.name}.",
            suffix=".tmp",
            delete=False,
        ) as archivo:
            temporal = Path(archivo.name)
            archivo.write(contenido)
        # Windows exige cerrar el temporal antes del reemplazo. Un lector o escáner
        # puede mantener el destino bloqueado brevemente aunque tengamos permisos.
        for intento in range(len(_ESPERAS_BLOQUEO_WINDOWS) + 1):
            try:
                temporal.replace(ruta)
                return
            except PermissionError as exc:
                if (
                    getattr(exc, "winerror", None) not in {5, 32, 33}
                    or intento == len(_ESPERAS_BLOQUEO_WINDOWS)
                ):
                    raise
                sleep(_ESPERAS_BLOQUEO_WINDOWS[intento])
    finally:
        if temporal is not None:
            try:
                temporal.unlink(missing_ok=True)
            except OSError:
                # Un bloqueo del temporal tampoco debe ocultar el error original.
                pass
