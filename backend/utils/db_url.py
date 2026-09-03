"""
db_url.py — Database URL sanitizer for asyncpg compatibility.

Cloud providers (Neon.tech, Supabase, Render) append extra query parameters to
PostgreSQL connection strings (e.g. sslmode=require, channel_binding=require,
options=endpoint%3D...) that asyncpg does NOT understand as keyword arguments.

This module strips all query params from the URL and returns them separately
so they can be passed as proper connect_args to SQLAlchemy.

Usage
-----
    from utils.db_url import make_async_url, make_connect_args

    engine = create_async_engine(
        make_async_url(settings.DATABASE_URL),
        connect_args=make_connect_args(settings.DATABASE_URL),
    )
"""
import ssl
from urllib.parse import urlparse, parse_qs, urlunparse


def make_async_url(database_url: str) -> str:
    """
    Convert a synchronous PostgreSQL URL into one safe for asyncpg:

    1. Replaces the scheme with postgresql+asyncpg.
    2. Strips ALL query-string parameters (asyncpg rejects unknown params).

    Examples:
        "postgresql://user:pass@host/db?sslmode=require&channel_binding=require"
        → "postgresql+asyncpg://user:pass@host/db"
    """
    url = database_url.strip()

    # Normalise scheme
    for old, new in [
        ("postgresql+asyncpg://", "postgresql+asyncpg://"),  # already correct, no-op
        ("postgresql://", "postgresql+asyncpg://"),
        ("postgres://", "postgresql+asyncpg://"),
    ]:
        if url.startswith(old) and old != "postgresql+asyncpg://":
            url = url.replace(old, new, 1)
            break

    # Strip every query parameter — asyncpg does not accept them as kwargs
    parsed = urlparse(url)
    clean = urlunparse(parsed._replace(query=""))
    return clean


def make_connect_args(database_url: str) -> dict:
    """
    Build an asyncpg-compatible connect_args dict from a cloud database URL.

    Specifically handles SSL: if the original URL contains any ssl-related param
    (sslmode, ssl, sslcert, …) with a non-'disable' value, this returns
    {"ssl": <verified SSLContext>} so the connection is properly secured.

    Returns an empty dict when SSL is not required, which preserves local
    development behaviour (no SSL for a local Postgres container).
    """
    parsed = urlparse(database_url)
    params = {k: v[0] for k, v in parse_qs(parsed.query).items()}

    # Detect whether SSL should be enabled
    ssl_param = params.get("sslmode") or params.get("ssl") or ""
    ssl_required = ssl_param.lower() not in ("", "disable", "allow", "prefer")

    if ssl_required:
        ctx = ssl.create_default_context()
        return {"ssl": ctx}

    return {}
