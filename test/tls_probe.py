"""TLS probe: initialize an MCP session and scrape one URL.

Exit codes: 0 = scraped OK, 2 = MCP error (isError).
"""
import asyncio
import json
import sys

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


async def main(url: str) -> int:
    async with streamablehttp_client("http://127.0.0.1:8123/mcp") as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            res = await s.call_tool(
                "scrape", {"url": url, "format": "text", "max_chars": 500}
            )
            if res.isError:
                text = res.content[0].text if res.content else ""
                print("isError:", text[:400])
                return 2
            data = json.loads(res.content[0].text)
            first = (
                data["content"].splitlines()[0][:80] if data["content"] else "(empty)"
            )
            print("OK:", data["url"], "| first line:", first)
            return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1])))
