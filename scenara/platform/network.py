from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit


class UnsafeNetworkTarget(ValueError):
    pass


def _public_address(value: str) -> bool:
    address = ipaddress.ip_address(value)
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


async def validate_external_url(
    url: str,
    *,
    allowed_schemes: frozenset[str],
    allow_private: bool = False,
    allow_credentials: bool = False,
) -> str:
    parsed = urlsplit(url)
    scheme = parsed.scheme.lower()
    if scheme not in allowed_schemes or not parsed.hostname:
        raise UnsafeNetworkTarget(f"URL must use one of: {', '.join(sorted(allowed_schemes))}")
    if (parsed.username or parsed.password) and not allow_credentials:
        raise UnsafeNetworkTarget("credentials must be stored separately from the source URL")
    if allow_private:
        return url
    try:
        literal = ipaddress.ip_address(parsed.hostname)
        addresses = {str(literal)}
    except ValueError:
        loop = asyncio.get_running_loop()
        try:
            records = await loop.getaddrinfo(parsed.hostname, parsed.port, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise UnsafeNetworkTarget("URL host could not be resolved") from exc
        addresses = {record[4][0] for record in records}
    if not addresses or any(not _public_address(address) for address in addresses):
        raise UnsafeNetworkTarget("URL resolves to a private or special-use address")
    return url


__all__ = ["UnsafeNetworkTarget", "validate_external_url"]
