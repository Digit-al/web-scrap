#!/usr/bin/env python3
"""
MCP web-scraping server — HTTP transport (streamable-http).

Serves MCP tools to fetch and extract web content.
Internal URLs are fetched directly from the host machine:
the HTTP client ignores proxy variables (trust_env=False),
so "no proxy" is guaranteed regardless of configuration.

Run:
    python server.py            # reads MCP_HOST / MCP_PORT
or:
    uvicorn server:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from markdownify import markdownify
from mcp.server.fastmcp import FastMCP

# --------------------------------------------------------------------------
# Configuration (environment variables)
# --------------------------------------------------------------------------
HOST = os.environ.get("MCP_HOST", "0.0.0.0")
PORT = int(os.environ.get("MCP_PORT", "8000"))
TIMEOUT = float(os.environ.get("SCRAPE_TIMEOUT", "30"))
MAX_BYTES = int(os.environ.get("SCRAPE_MAX_BYTES", str(10 * 1024 * 1024)))
USER_AGENT = os.environ.get(
    "SCRAPE_USER_AGENT", "mcp-scraping-server/1.0 (+local-vm)"
)
# Optional allowlist: "intranet.example.com,docs.example.com"
# (subdomains are allowed). Empty = all hosts.
ALLOWED_HOSTS = {
    h.strip().lower()
    for h in os.environ.get("SCRAPE_ALLOWED_HOSTS", "").split(",")
    if h.strip()
}
# Optional token: if set, every MCP call requires
# Authorization: Bearer <token>.
MCP_TOKEN = os.environ.get("MCP_TOKEN", "")
# Optional custom CA bundle (PEM file) used to verify HTTPS
# certificates, e.g. for a corporate internal CA. It REPLACES the
# default trust store (append certifi's bundle to also keep public CAs).
CA_BUNDLE = os.environ.get("SCRAPE_CA_BUNDLE", "").strip()
# If true (1/true/yes/on), skip TLS certificate verification.
INSECURE = os.environ.get("SCRAPE_INSECURE", "").strip().lower() in (
    "1", "true", "yes", "on"
)
if CA_BUNDLE and not os.path.isfile(CA_BUNDLE):
    raise SystemExit(f"SCRAPE_CA_BUNDLE does not exist: {CA_BUNDLE!r}")

mcp = FastMCP(
    "web-scraping",
    instructions=(
        "Web scraping tools. URLs are fetched directly from the VM "
        "(no proxy): internal/intranet addresses are therefore "
        "reachable. Formats available for `scrape`: text, markdown, "
        "html, links, tables, json. Use `http_call` for API calls "
        "(GET/POST/PUT/PATCH/DELETE, request body, JSON/XML responses)."
    ),
    host=HOST,
    port=PORT,
    stateless_http=True,  # stateless: simple behind a reverse proxy
)

_client: httpx.Client | None = None


def get_client() -> httpx.Client:
    """Shared HTTP client.

    trust_env=False => ignores HTTP(S)_PROXY etc. (direct fetching of
    internal URLs). TLS: custom CA bundle (SCRAPE_CA_BUNDLE) or
    verification disabled (SCRAPE_INSECURE).
    """
    global _client
    if _client is None:
        verify: str | bool = CA_BUNDLE or True
        if INSECURE:
            verify = False
        _client = httpx.Client(
            trust_env=False,
            verify=verify,
            timeout=TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )
    return _client


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _check_url(url: str) -> None:
    p = urlparse(url)
    if p.scheme not in ("http", "https"):
        raise ValueError(
            f"URL {p.scheme!r} not allowed: only http/https is accepted."
        )
    host = (p.hostname or "").lower()
    if not host:
        raise ValueError(f"URL without host: {url!r}")
    if ALLOWED_HOSTS:
        ok = host in ALLOWED_HOSTS or any(
            host.endswith("." + a) for a in ALLOWED_HOSTS
        )
        if not ok:
            raise ValueError(
                f"Host {host!r} not in SCRAPE_ALLOWED_HOSTS "
                f"({', '.join(sorted(ALLOWED_HOSTS))})."
            )


def _fetch(url: str, headers: dict | None = None) -> tuple[bytes, str]:
    """Fetch url; returns (content, content_type)."""
    _check_url(url)
    client = get_client()
    try:
        r = client.get(url, headers=headers or {})
        r.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise ValueError(
            f"HTTP {e.response.status_code} for {url} "
            f"(code {e.response.reason if hasattr(e.response, 'reason') else ''})"
        ) from None
    except httpx.RequestError as e:
        raise ValueError(f"Failed to fetch {url}: {e}") from None
    data = r.content
    if len(data) > MAX_BYTES:
        raise ValueError(
            f"Response of {len(data)} bytes > SCRAPE_MAX_BYTES ({MAX_BYTES})."
        )
    return data, r.headers.get("content-type", "")


def _raw_request(
    url: str,
    method: str,
    headers: dict | None = None,
    content: bytes | None = None,
) -> tuple[bytes, int, str]:
    """Perform an HTTP request; returns (body, status, content_type).

    Non-2xx statuses are returned as data, not raised: API callers
    often need the error body (e.g. a 4xx with a JSON message).
    """
    _check_url(url)
    client = get_client()
    try:
        r = client.request(method, url, headers=headers or {}, content=content)
    except httpx.RequestError as e:
        raise ValueError(f"Request failed for {url}: {e}") from None
    data = r.content
    if len(data) > MAX_BYTES:
        raise ValueError(
            f"Response of {len(data)} bytes > SCRAPE_MAX_BYTES ({MAX_BYTES})."
        )
    return data, r.status_code, r.headers.get("content-type", "")


def _soup(data: bytes, content_type: str) -> BeautifulSoup:
    return BeautifulSoup(data, "lxml")


def _clean_text(text: str) -> str:
    return re.sub(r"[ \t]+", " ", re.sub(r"\n{3,}", "\n\n", text)).strip()


def _truncate(text: str, max_chars: int) -> tuple[str, bool]:
    if max_chars > 0 and len(text) > max_chars:
        return text[:max_chars] + "\n…[truncated]", True
    return text, False


# --------------------------------------------------------------------------
# MCP tools
# --------------------------------------------------------------------------
@mcp.tool()
def scrape(
    url: str,
    format: str = "text",
    max_chars: int = 20000,
    headers: dict | None = None,
) -> str:
    """Fetch a URL and extract its content.

    Args:
        url: http/https URL to fetch (internal addresses are
            allowed, no proxy).
        format: `text` (readable text), `markdown` (HTML to Markdown),
            `html` (raw HTML), `links` (list of links), `tables`
            (tables as CSV), `json` (raw body).
        max_chars: max number of characters to return (0 = unlimited,
            otherwise 20000).
        headers: optional HTTP headers to send (e.g. Cookie,
            Authorization) for protected internal pages.
    """
    fmt = format.strip().lower()
    data, ctype = _fetch(url, headers)
    truncated = False

    if fmt == "json":
        body = data.decode("utf-8", errors="replace")
        try:
            body = json.dumps(
                json.loads(body), ensure_ascii=False, indent=2
            )
        except (json.JSONDecodeError, ValueError):
            pass  # return the raw body
    elif fmt == "html":
        body = data.decode("utf-8", errors="replace")
    elif fmt == "links":
        soup = _soup(data, ctype)
        lines = []
        for a in soup.find_all("a", href=True):
            href = urljoin(url, a["href"].strip())
            text = _clean_text(a.get_text(" ", strip=True))
            lines.append(f"{href}\t{text}" if text else href)
        body = "\n".join(lines) or "(no links)"
    elif fmt == "tables":
        soup = _soup(data, ctype)
        tables_out = []
        for i, table in enumerate(soup.find_all("table"), 1):
            buf = io.StringIO()
            writer = csv.writer(buf)
            for row in table.find_all("tr"):
                cells = [
                    _clean_text(c.get_text(" ", strip=True))
                    for c in row.find_all(["th", "td"])
                ]
                if cells:
                    writer.writerow(cells)
            tables_out.append(f"# table {i}\n" + buf.getvalue().strip())
        body = "\n\n".join(tables_out) or "(no tables)"
    elif fmt in ("text", "markdown"):
        soup = _soup(data, ctype)
        for tag in soup(["script", "style", "noscript", "template"]):
            tag.decompose()
        main = soup.find("main") or soup.find("article") or soup.body or soup
        if fmt == "markdown":
            body = markdownify(str(main), heading_style="#")
        else:
            body = main.get_text("\n")
        body = _clean_text(body)
    else:
        raise ValueError(
            f"Unknown format {format!r}. "
            "Use: text, markdown, html, links, tables, json."
        )

    body, truncated = _truncate(body, max_chars)
    out = {
        "url": url,
        "format": fmt,
        "content_type": ctype,
        "truncated": truncated,
        "content": body,
    }
    return json.dumps(out, ensure_ascii=False, indent=2)


@mcp.tool()
def search(
    url: str,
    pattern: str,
    ignore_case: bool = True,
    max_matches: int = 50,
    context_chars: int = 150,
    headers: dict | None = None,
) -> str:
    """Search for a pattern (Python regex) in a page's text.

    Args:
        url: http/https URL of the page to search.
        pattern: regex pattern (e.g. "\\d{3}-\\d{4}", "error|fail").
        ignore_case: case-insensitive (default true).
        max_matches: max number of matches (default 50).
        context_chars: number of context characters around
            each match (default 150).
        headers: optional HTTP headers.
    """
    data, ctype = _fetch(url, headers)
    soup = _soup(data, ctype)
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = _clean_text((soup.body or soup).get_text("\n"))
    flags = re.IGNORECASE if ignore_case else 0
    try:
        rx = re.compile(pattern, flags)
    except re.error as e:
        raise ValueError(f"Invalid regex {pattern!r}: {e}") from None

    matches = []
    for m in rx.finditer(text):
        start = max(0, m.start() - context_chars)
        end = min(len(text), m.end() + context_chars)
        matches.append(
            {
                "match": m.group(0)[:500],
                "context": (
                    ("…" if start > 0 else "")
                    + text[start:end]
                    + ("…" if end < len(text) else "")
                ),
            }
        )
        if len(matches) >= max_matches:
            break
    return json.dumps(
        {
            "url": url,
            "pattern": pattern,
            "count": len(matches),
            "truncated": len(matches) >= max_matches,
            "matches": matches,
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
def http_call(
    url: str,
    method: str = "GET",
    headers: dict | None = None,
    body: str | dict | list | None = None,
    max_chars: int = 20000,
) -> str:
    """Call an HTTP API endpoint and return its response.

    Use this for APIs (unlike `scrape`, which is a GET page extractor).
    Query parameters go in `url`. Non-2xx statuses are returned as
    normal results (with their body), not as tool errors.

    Args:
        url: http/https URL to call (query string included).
        method: HTTP method: GET, POST, PUT, PATCH or DELETE
            (default GET).
        headers: optional HTTP headers (e.g. Authorization, Accept,
            Content-Type, Cookie).
        body: optional request body. A string is sent as-is; a
            dict/list is sent as JSON (Content-Type: application/json
            is set automatically if not already given).
        max_chars: max number of characters of the response body to
            return (0 = unlimited, otherwise 20000).
    """
    m = method.strip().upper()
    if m not in ("GET", "POST", "PUT", "PATCH", "DELETE"):
        raise ValueError(
            f"Method {method!r} not supported. "
            "Use: GET, POST, PUT, PATCH, DELETE."
        )
    req_headers = dict(headers or {})
    content: bytes | None = None
    if body is not None:
        if isinstance(body, (dict, list)):
            content = json.dumps(body, ensure_ascii=False).encode("utf-8")
            if not any(k.lower() == "content-type" for k in req_headers):
                req_headers["Content-Type"] = "application/json"
        else:
            content = str(body).encode("utf-8")
    data, status, ctype = _raw_request(url, m, req_headers, content)
    text = data.decode("utf-8", errors="replace")
    # Pretty-print JSON responses when possible.
    try:
        text = json.dumps(json.loads(text), ensure_ascii=False, indent=2)
    except (json.JSONDecodeError, ValueError):
        pass
    text, truncated = _truncate(text, max_chars)
    return json.dumps(
        {
            "url": url,
            "method": m,
            "status": status,
            "ok": 200 <= status < 300,
            "content_type": ctype,
            "truncated": truncated,
            "body": text,
        },
        ensure_ascii=False,
        indent=2,
    )


# --------------------------------------------------------------------------
# HTTP application (FastAPI) + optional auth
# --------------------------------------------------------------------------
from starlette.responses import JSONResponse  # noqa: E402
from starlette.requests import Request  # noqa: E402

app = mcp.streamable_http_app()  # Starlette (not FastAPI): routes via add_route


def _health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


app.add_route("/health", _health, methods=["GET"])


if MCP_TOKEN:
    from starlette.middleware.base import BaseHTTPMiddleware

    class _TokenAuthMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            if request.url.path != "/health" and (
                request.headers.get("authorization", "") != f"Bearer {MCP_TOKEN}"
            ):
                return JSONResponse({"error": "unauthorized"}, status_code=401)
            return await call_next(request)

    app.add_middleware(_TokenAuthMiddleware)


if __name__ == "__main__":
    import uvicorn

    print(
        f"MCP web-scraping server: http://{HOST}:{PORT}/mcp "
        f"(transport: streamable-http)",
        flush=True,
    )
    if ALLOWED_HOSTS:
        print("Allowed hosts:", sorted(ALLOWED_HOSTS), flush=True)
    if MCP_TOKEN:
        print("Auth: Bearer token enabled", flush=True)
    if INSECURE:
        print(
            "TLS: certificate verification DISABLED (SCRAPE_INSECURE)",
            flush=True,
        )
    elif CA_BUNDLE:
        print("TLS: custom CA bundle:", CA_BUNDLE, flush=True)
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
