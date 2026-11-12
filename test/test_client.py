"""Test client : handshake MCP + appels d'outils contre le serveur local."""
import asyncio
import json
import sys

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

URL = "http://127.0.0.1:8123/mcp"
PAGE = "http://127.0.0.1:8099/test.html"


async def main() -> int:
    failures = []
    async with streamablehttp_client(URL) as (r, w, _):
        async with ClientSession(r, w) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = sorted(t.name for t in tools.tools)
            print("Outils :", names)
            if set(names) != {"scrape", "search"}:
                failures.append("liste d'outils inattendue")

            # 1. text
            r = await session.call_tool("scrape", {"url": PAGE, "format": "text"})
            data = json.loads(r.content[0].text)
            assert "Rapport interne 2026" in data["content"], data["content"][:200]
            print("OK text : page récupérée, contenu extrait")

            # 2. links
            r = await session.call_tool("scrape", {"url": PAGE, "format": "links"})
            data = json.loads(r.content[0].text)
            assert "http://10.0.0.5:9000/api/v1/statuts" in data["content"]
            assert "https://example.com/ext" in data["content"]
            print("OK links : liens absolus extraits")

            # 3. tables
            r = await session.call_tool("scrape", {"url": PAGE, "format": "tables"})
            data = json.loads(r.content[0].text)
            assert "paiement,DÉGRADÉ,1204" in data["content"]
            print("OK tables : tableau en CSV")

            # 4. markdown
            r = await session.call_tool("scrape", {"url": PAGE, "format": "markdown"})
            data = json.loads(r.content[0].text)
            assert "# Rapport interne 2026" in data["content"]
            print("OK markdown")

            # 5. search
            r = await session.call_tool(
                "search", {"url": PAGE, "pattern": "erreur"}
            )
            data = json.loads(r.content[0].text)
            assert data["count"] >= 1
            assert "ERREUR-4242" in data["matches"][0]["context"]
            print(f"OK search : {data['count']} correspondance(s)")

            # 6. erreur propre sur URL inaccessible (résultat isError ou exception)
            try:
                r = await session.call_tool(
                    "scrape",
                    {"url": "http://127.0.0.1:9/bloquant", "max_chars": 100},
                )
                if r.isError:
                    print("OK : URL inaccessible → erreur MCP propre (isError)")
                else:
                    failures.append(
                        f"erreur inattendue sur URL morte : {r.content[0].text[:200]}"
                    )
            except Exception:
                print("OK : URL inaccessible → erreur MCP propre (exception)")

    if failures:
        print("ÉCHECS :", failures)
        return 1
    print("\n✅ Tous les tests sont passés.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
