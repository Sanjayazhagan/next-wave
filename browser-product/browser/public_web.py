"""Opt-in public HTTPS navigation policy for agent-provided URLs.

This is defense in depth, NOT a complete network isolation boundary. Browser
workers processing untrusted pages must also run without internal-network
access (e.g., on a restricted egress network/VM) before production use.
"""
import asyncio
import ipaddress
import os
import re
import socket
from urllib.parse import urlsplit

from fastapi import HTTPException

NAV_MODE_ALLOWLIST = 'allowlist'
NAV_MODE_PUBLIC = 'public-web'
_BAD_SUFFIXES = (
    '.localhost', '.local', '.internal', '.lan', '.home', '.home.arpa',
    '.localdomain', '.test', '.invalid', '.example', '.onion',
)
_NAME = re.compile(r'^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$')


def navigation_mode() -> str:
    mode = os.getenv('BROWSER_NAVIGATION_MODE', NAV_MODE_ALLOWLIST).strip().lower()
    if mode not in (NAV_MODE_ALLOWLIST, NAV_MODE_PUBLIC):
        raise ValueError('BROWSER_NAVIGATION_MODE must be allowlist or public-web')
    return mode


def public_url_syntax(url: str) -> tuple[str, int]:
    """Enforce HTTPS-only, ordinary public DNS host, standard port, no userinfo.

    Rejects direct internal IPv4/IPv6, URL credentials, alternate ports, and
    ambiguous single-label/internal hostnames BEFORE any network request.
    """
    if not isinstance(url, str) or len(url) > 2000 or any(ord(c) < 33 for c in url):
        raise ValueError('Invalid URL')
    try:
        p = urlsplit(url)
        port = p.port
        host = (p.hostname or '').rstrip('.').lower()
    except ValueError as exc:
        raise ValueError('Invalid URL') from exc
    if p.scheme != 'https' or not host or p.username is not None or p.password is not None:
        raise ValueError('Only public HTTPS URLs without embedded credentials are supported')
    if port not in (None, 443):
        raise ValueError('Only HTTPS port 443 is supported')
    if '%' in host or '\\' in url or url.startswith('https:////'):
        raise ValueError('Ambiguous URL or zone identifier')
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if '.' not in host or host.endswith(_BAD_SUFFIXES):
            raise ValueError('Internal/single-label hostname is not permitted')
        # IDNA normalization is checked for syntactic validity; DNS resolution
        # happens later to reject private or otherwise non-global answers.
        try:
            ascii_host = host.encode('idna').decode('ascii').lower()
        except (UnicodeError, ValueError) as exc:
            raise ValueError('Invalid hostname') from exc
        if len(ascii_host) > 253 or not all(_NAME.fullmatch(label) for label in ascii_host.split('.')):
            raise ValueError('Invalid public hostname')
        if not ascii_host.split('.')[-1].isalpha() and not ascii_host.split('.')[-1].startswith('xn--'):
            raise ValueError('Invalid public domain suffix')
        return ascii_host, 443
    if not address.is_global:
        raise ValueError('Private, loopback, reserved or link-local IP is not allowed')
    return str(address), 443


async def assert_public_url(url: str) -> None:
    """Check every A/AAAA DNS result before routing a browser request.

    DNS is still subject to TOCTOU rebinding between the check and Chromium's
    connection. External egress firewall/proxy isolation is required for a
    fully hardened hosted browser.
    """
    try:
        host, port = public_url_syntax(url)
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            try:
                infos = await asyncio.wait_for(
                    asyncio.to_thread(socket.getaddrinfo, host, port, 0, socket.SOCK_STREAM),
                    timeout=5,
                )
            except (OSError, asyncio.TimeoutError) as exc:
                raise ValueError('Could not securely resolve public hostname') from exc
            if not infos:
                raise ValueError('No DNS addresses available')
            for info in infos:
                try:
                    resolved = ipaddress.ip_address(info[4][0])
                except ValueError as exc:
                    raise ValueError('Invalid DNS result') from exc
                if not resolved.is_global:
                    raise ValueError('Public hostname resolved to a non-public address')
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=f'Navigation blocked: {exc}') from exc
