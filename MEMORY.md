# MEMORY.md — mcp-scraping (serveur MCP HTTP de web scraping)

## Décisions
- [2026-11-12] Pin `mcp>=1.12,<2` — la 2.x a renommé `FastMCP` en
  `MCPServer` et cassé l'API ; la v1 est stable et documentée pour tous les
  clients MCP.
- [2026-11-12] `stateless_http=True` : pas de sessions MCP persistantes →
  sûr derrière reverse proxy / plusieurs clients, pas d'état à gérer.
- [2026-11-12] « sans proxy » = `httpx.Client(trust_env=False)` : les
  variables `*_PROXY` de la VM sont ignorées, les URL internes passent
  directement depuis la VM.
- [2026-11-12] `streamable_http_app()` renvoie un app **Starlette** (pas
  FastAPI) : routes ajoutées via `app.add_route(...)`, middleware via
  `app.add_middleware(BaseHTTPMiddleware)` (`.middleware()` / `@app.get`
  n'existent pas dans starlette 1.10).
- [2026-11-12] Deux modes d'install sur la VM : Docker (recommandé) ou
  userland : `install.sh` (venv + `./.env` + `logs/`, sans root) +
  `run.sh {start|stop|restart|status|logs}` (nohup + PID `./.mcp-scraping.pid`).
  `./.env` est sourceable par bash (valeurs à espaces entre guillemets).
  Auth Bearer optionnelle via `MCP_TOKEN`.
- [2026-11-12] **Userland imposé par l'utilisateur, pas de systemd** : unité
  `mcp-scraping.service` supprimée. Autodémarrage sans systemd via
  `./install.sh --cron` (entrée `@reboot` dans le crontab de l'user).

## Écueils
- [2026-11-12] `mcp==2.3.0` installé par défaut → `ModuleNotFoundError:
  mcp.server.fastmcp` → pinner `mcp<2` dans requirements.txt.
- [2026-11-12] `@app.get` / `app.middleware` sur le résultat de
  `streamable_http_app()` → `AttributeError` (Starlette) → `add_route` +
  `add_middleware`.
- [2026-11-12] Un outil MCP qui lève `ValueError` ne propage PAS une
  exception au client : FastMCP renvoie un résultat `isError=True`.
  Les tests doivent vérifier `isError`, pas `try/except`.
- [2026-11-12] `pkill -f 'mcp-scraping/server.py'` tue aussi le shell qui
  lance la commande (le pattern match la ligne de commande du bash) →
  tuer par PID explicite.

## État de la tâche
- Objectif : serveur MCP HTTP de web scraping (URL internes, sans proxy),
  installable sur une VM, **tournant en userland (sans systemd)**.
- Fait : projet complet dans `/home/d1f34069/mcp-scraping/` — `server.py`
  (outils `scrape` text/markdown/html/links/tables/json + `search` regex),
  Dockerfile, docker-compose, `install.sh` (userland), `run.sh`, README,
  tests. **Tous les tests passent** (`test/test_client.py` : formats,
  liens, tables, recherche, erreurs ; auth 401/200 validée) y compris
  via `run.sh start`.
- Prochain : déploiement sur la VM de l'utilisateur (Docker ou
  `install.sh` + `run.sh`), connexion du client MCP sur
  `http://IP-VM:8000/mcp`.

## Faits durs
- [2026-11-12] Versions testées : python 3.12.13, mcp 1.x (FastMCP),
  starlette 1.10.0, httpx 0.28.1, lxml 6.1.3, markdownify 1.2.3.
- [2026-11-12] Test local : serveur sur 8123 + page HTML locale sur 8099
  (`test/test.html`, serveur `python -m http.server`).
