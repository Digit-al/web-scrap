"""Test client : handshake MCP + appels d'outils contre le serveur local."""
import asyncio
import json
import sys

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

URL = "http://127.0.0.1:8123/mcp"
PAGE = "http://127.0.0.1:8099/test.html"
API = "http://127.0.0.1:8098"  # fixture api_fixture.py
PROXY = "http://127.0.0.1:8097"  # fixture proxy_fixture.py


async def main() -> int:
    failures = []
    async with streamablehttp_client(URL) as (r, w, _):
        async with ClientSession(r, w) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = sorted(t.name for t in tools.tools)
            print("Outils :", names)
            if set(names) != {"scrape", "search", "http_call"}:
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

            # 6. http_call GET (XML, body brut)
            r = await session.call_tool("http_call", {"url": f"{API}/api/xml"})
            data = json.loads(r.content[0].text)
            assert data["status"] == 200 and data["ok"] is True
            assert "<item>hello</item>" in data["body"]
            assert "application/xml" in data["content_type"]
            print("OK http_call GET : XML renvoyé tel quel")

            # 7. http_call POST (body dict → JSON, headers, echo vérifié)
            r = await session.call_tool(
                "http_call",
                {
                    "url": f"{API}/api/echo",
                    "method": "POST",
                    "headers": {"X-Test": "yep"},
                    "body": {"a": 1, "b": "x"},
                },
            )
            data = json.loads(r.content[0].text)
            echo = json.loads(data["body"])
            assert echo["method"] == "POST"
            assert echo["body"] == '{"a": 1, "b": "x"}'
            assert echo["received_headers"]["X-Test"] == "yep"
            assert echo["received_headers"]["Content-Type"] == "application/json"
            print("OK http_call POST : body JSON + headers transmis")

            # 8. http_call 404 → status dans le résultat (pas d'erreur MCP)
            r = await session.call_tool("http_call", {"url": f"{API}/api/notfound"})
            data = json.loads(r.content[0].text)
            assert data["status"] == 404 and data["ok"] is False
            assert json.loads(data["body"]) == {"error": "not found"}
            print("OK http_call 404 : statut + corps d'erreur renvoyés")

            # 9. http_call méthode invalide → erreur MCP propre (isError)
            r = await session.call_tool(
                "http_call", {"url": f"{API}/api/echo", "method": "FOO"}
            )
            assert r.isError, "méthode invalide doit renvoyer isError"
            print("OK http_call : méthode invalide → erreur MCP propre")

            # 10. http_call via proxy URL (le trafic passe par le proxy)
            r = await session.call_tool(
                "http_call", {"url": PAGE, "proxy": PROXY}
            )
            data = json.loads(r.content[0].text)
            assert data["status"] == 200 and data["ok"] is True
            marker = json.loads(data["body"])
            assert marker["via_proxy"] is True
            assert marker["requested"] == PAGE
            print("OK http_call proxy : trafic routé via le proxy")

            # 11. scrape via proxy (le paramètre existe sur tous les outils)
            r = await session.call_tool(
                "scrape",
                {"url": PAGE, "format": "json", "proxy": PROXY},
            )
            data = json.loads(r.content[0].text)
            assert json.loads(data["content"])["via_proxy"] is True
            print("OK scrape proxy : paramètre proxy opérationnel")

            # 12. proxy invalide (pas de scheme) → erreur MCP propre
            r = await session.call_tool(
                "http_call", {"url": PAGE, "proxy": "proxy.host:3128"}
            )
            assert r.isError, "proxy invalide doit renvoyer isError"
            print("OK proxy : URL invalide → erreur MCP propre")

            # 13. proxy injoignable → erreur MCP propre (isError)
            r = await session.call_tool(
                "http_call", {"url": PAGE, "proxy": "http://127.0.0.1:1"}
            )
            assert r.isError, "proxy injoignable doit renvoyer isError"
            print("OK proxy : proxy injoignable → erreur MCP propre")

            # 14. erreur propre sur URL inaccessible (résultat isError ou exception)
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
