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
- [2026-11-12] **HTTPS / TLS** : vérification des certificats active par
  défaut (bundle `certifi` d'httpx). `SCRAPE_CA_BUNDLE=<pem>` = bundle CA
  custom (il *remplace* le store par défaut : concaténer le bundle
  certifi si on veut aussi les CAs publiques) ; `SCRAPE_INSECURE=1` =
  désactiver la vérification (cas très spécifiques). Fail-fast au
  démarrage si le bundle n'existe pas. Testé avec une CA auto-signée
  (https local 8443, certs `/tmp/scrape_tls`, probe `test/tls_probe.py`) :
  rejet sans bundle (`CERTIFICATE_VERIFY_FAILED`), OK avec bundle, OK
  avec `SCRAPE_INSECURE=1`, https public OK.
- [2026-11-12] Code publié : repo GitHub public **Digit-al/web-scrap**
  (branche `main`, init `571b66e` + commit TLS). Identité de commit locale :
  David Rossignol <david@rsgnl.fr>. `.gitignore` : `.venv/`, `__pycache__/`,
  `logs/`, `*.log`, `.env` (réel), `.mcp-scraping.pid`. Remote `origin`
  = URL propre sans token (token jamais stocké dans `.git/config`).

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
- [2026-11-12] `git log`/`git show` bloquent sur le pager (less attend un
  RETURN, TTY partiel) → toujours `git --no-pager` ici.
- [2026-11-12] `git -c http.extraHeader="Authorization: token ..." push`
  → `fatal: could not read Username` (GitHub challenge ignoré) → push fiable
  via `GIT_ASKPASS` (script /tmp/askpass.sh : user `x-access-token`,
  password = contenu de `~/.github_token`) vers `origin` URL propre.
- [2026-11-12] Redémarrage du serveur de test sur le même port : après un
  `kill` (SIGTERM) le port 8123 restait bindé par l'ancien process
  (nouveau serveur : `[Errno 98] address already in use`) → tuer avec
  `kill -9 <pid>` et vérifier que le process est mort avant de relancer.
- [2026-11-12] Dans une commande one-shot, un `cd ... && nohup ... &`
  met le `cd` dans le job background : le shell principal reste dans son
  cwd initial → les chemins relatifs `.venv/bin/python` suivants échouent
  (`Permission denied`). Toujours `cd` en foreground d'abord, ou chemins
  absolus.

## État de la tâche
- Objectif : serveur MCP HTTP de web scraping (URL internes, sans proxy),
  installable sur une VM, **tournant en userland (sans systemd)**.
- Fait : projet complet dans `/home/d1f34069/mcp-scraping/` — `server.py`
  (outils `scrape` text/markdown/html/links/tables/json + `search` regex,
  options TLS `SCRAPE_CA_BUNDLE`/`SCRAPE_INSECURE`), Dockerfile,
  docker-compose, `install.sh` (userland), `run.sh`, README, tests.
  **Tous les tests passent** (`test/test_client.py` : formats, liens,
  tables, recherche, erreurs ; auth 401/200 validée ; matrice TLS) y
  compris via `run.sh start`.
- Prochain : déploiement sur la VM de l'utilisateur (Docker ou
  `install.sh` + `run.sh`), connexion du client MCP sur
  `http://IP-VM:8000/mcp`. Code poussé sur GitHub : Digit-al/web-scrap.

## Faits durs
- [2026-11-12] Versions testées : python 3.12.13, mcp 1.x (FastMCP),
  starlette 1.10.0, httpx 0.28.1, lxml 6.1.3, markdownify 1.2.3.
- [2026-11-12] Test local : serveur sur 8123 + page HTML locale sur 8099
  (`test/test.html`, serveur `python -m http.server`).
