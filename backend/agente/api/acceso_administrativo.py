"""Guardia reemplazable para el plano administrativo local."""

from __future__ import annotations

import ipaddress

from fastapi import HTTPException, Request

MENSAJE_ACCESO_DENEGADO = "Acceso administrativo solo disponible desde loopback."


def peer_is_loopback(host: str | None) -> bool:
    """Return whether an address is a direct IPv4/IPv6 loopback peer."""
    if not isinstance(host, str):
        return False
    try:
        direccion = ipaddress.ip_address(host)
    except ValueError:
        return False
    if direccion.version == 6 and direccion.ipv4_mapped is not None:
        return direccion.ipv4_mapped.is_loopback
    return direccion.is_loopback


async def require_local_administrator(request: Request) -> None:
    """Reject administrative requests whose direct ASGI peer is not loopback."""
    host = request.client.host if request.client is not None else None
    if not peer_is_loopback(host):
        raise HTTPException(status_code=403, detail=MENSAJE_ACCESO_DENEGADO)
