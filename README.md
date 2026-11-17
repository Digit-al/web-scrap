# MCP web-scraping server (HTTP, sans proxy)

Serveur **MCP** (Model Context Protocol) au transport **streamable HTTP** qui
expose des outils de web scraping. Le serveur tourne **sur la VM de votre
choix** : les URL internes (intranet) sont récupérées directement depuis cette
VM, **sans proxy** (le client HTTP ignore `HTTP_PROXY`/`HTTPS_PROXY` etc.
via `trust_env=False`).

## Outils exposés

| Outil | Description |
|---|---|
| `scrape(url, format, max_chars, headers, proxy)` | Récupère une URL. `format` : `text`, `markdown`, `html`, `links`, `tables` (CSV), `json`. `headers` pour pages protégées (Cookie, Authorization…). |
| `search(url, pattern, ignore_case, max_matches, context_chars, headers, proxy)` | Recherche regex dans le texte de la page, avec contexte. |
| `http_call(url, method, headers, body, max_chars, proxy)` | Appelle une API HTTP. `method` : `GET`/`POST`/`PUT`/`PATCH`/`DELETE` (query parameters dans `url`). `body` : string tel quel, ou dict/liste envoyé en JSON. Renvoie `status` + corps (JSON pretty-printé si possible) ; les 4xx/5xx sont renvoyés comme résultats normaux. |

> **Proxy (paramètre `proxy`, commun aux trois outils)** : `""` = direct
> (défaut, les variables `*_PROXY` de la VM sont ignorées), `"system"` =
> utiliser les variables `HTTP_PROXY`/`HTTPS_PROXY`/`NO_PROXY` de la VM,
> ou une URL de proxy (`http://user:pass@host:port`).

## Configuration (variables d'environnement)

| Variable | Défaut | Rôle |
|---|---|---|
| `MCP_HOST` / `MCP_PORT` | `0.0.0.0` / `8000` | Bind du serveur |
| `MCP_TRANSPORT_ALLOWED_HOSTS` | *(vide = auto)* | En-têtes `Host` acceptés sur `/mcp` (FQDN derrière reverse proxy) |
| `SCRAPE_TIMEOUT` | `30` | Timeout HTTP (s) |
| `SCRAPE_MAX_BYTES` | `10485760` | Taille max de réponse (octets) |
| `SCRAPE_USER_AGENT` | `mcp-scraping-server/1.0` | User-Agent envoyé |
| `SCRAPE_ALLOWED_HOSTS` | *(vide = tous)* | Liste blanche, host séparés par des virgules (sous-domaines inclus) |
| `SCRAPE_CA_BUNDLE` | *(vide = store par défaut)* | Bundle CA (PEM) pour vérifier les certificats HTTPS, ex. CA interne |
| `SCRAPE_INSECURE` | *(vide = vérif. active)* | Si vrai (`1`/`true`/`yes`) : ignore la vérification des certificats TLS |
| `MCP_TOKEN` | *(vide = sans auth)* | Si défini : le client doit envoyer `Authorization: Bearer <token>` |

> **Derrière un reverse proxy (HAProxy, nginx…)** : le transport
> streamable HTTP du SDK MCP valide l'en-tête `Host` (protection
> anti-DNS-rebinding). Si votre proxy transmet le FQDN public
> (`Host: mcp.monentreprise.fr`), le serveur renvoie
> `Invalid Host header` (421) sur `/mcp` à moins de l'autoriser :
> `MCP_TRANSPORT_ALLOWED_HOSTS=mcp.monentreprise.fr` puis `./run.sh restart`.

## Installation sur la VM

### Option A — Docker (recommandé)

```bash
git clone <ce-repo> mcp-scraping && cd mcp-scraping
# ou copier le dossier sur la VM
docker compose up -d --build
curl http://127.0.0.1:8000/health   # {"status":"ok"}
```

### Option B — userland (venv, sans root ni systemd)

```bash
./install.sh            # venv + .env + logs/ (option : ./install.sh --cron)
./run.sh start          # démarre en arrière-plan (nohup)
./run.sh status         # statut + health check
./run.sh logs           # suit les logs (Ctrl-C pour quitter)
./run.sh stop           # arrête le serveur
```

- Configuration : éditez `./.env` puis `./run.sh restart`.
- Démarrage au boot sans systemd : `./install.sh --cron` ajoute une
  entrée `@reboot` au crontab de l'utilisateur.
- Processus et fichiers : `./.mcp-scraping.pid`, `logs/mcp-scraping.log`
  (tout reste dans le dossier du projet).

> Les deux modes héritent du réseau de la VM : les URL internes sont
> accessibles.

## Configuration du client MCP

Exemple (Claude Desktop / Claude Code / tout client MCP HTTP) :

```json
{
  "mcpServers": {
    "scraping": {
      "url": "http://IP-DE-LA-VM:8000/mcp"
    }
  }
}
```

Avec token :

```json
{
  "mcpServers": {
    "scraping": {
      "url": "http://IP-DE-LA-VM:8000/mcp",
      "headers": { "Authorization": "Bearer MON_TOKEN" }
    }
  }
}
```

Exemples d'appels :

```json
{ "name": "scrape", "arguments": { "url": "http://intranet:8080/rapport", "format": "tables" } }
{ "name": "search", "arguments": { "url": "http://intranet:8080/rapport", "pattern": "erreur|fail" } }
{ "name": "http_call", "arguments": { "url": "https://api/ventes?mois=2026-01", "method": "POST", "headers": { "Authorization": "Bearer TOKEN" }, "body": { "code": "042" } } }
```

## Sécurité

- **Sans proxy** : `httpx(trust_env=False)` — les variables `*_PROXY` de la
  VM ne sont jamais utilisées ; les URL internes passent directement.
- **HTTPS** : la vérification des certificats est **active par défaut**.
  Pour une CA interne (certificats auto-signés de l'intranet), pointez
  `SCRAPE_CA_BUNDLE` vers votre bundle PEM (il *remplace* le store par
  défaut : concaténez-y le bundle `certifi` si vous voulez aussi garder
  les CAs publiques). `SCRAPE_INSECURE=1` désactive la vérification
  (à réserver aux cas très spécifiques).
- **Liste blanche** optionnelle via `SCRAPE_ALLOWED_HOSTS` (limitation
  SSRF : seul le trafic vers les hôtes listés est possible).
- **Token** optionnel via `MCP_TOKEN`.
- Serveur `stateless_http=True` : aucune session persistante, sûr derrière un
  reverse proxy / chargeur.
- En production, n'exposez le port qu'aux clients de confiance (firewall,
  reverse proxy TLS, VPN).

## Lancement manuel (dev)

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
MCP_PORT=8000 .venv/bin/python server.py
```

## Test rapide sans client

```bash
# health
curl http://127.0.0.1:8000/health
# handshake MCP manuel (streamable HTTP)
curl -s -N http://127.0.0.1:8000/mcp \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"t","version":"1"}}}'
```
