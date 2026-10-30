"""
Grist API client — INSERT et UPSERT
Gestion du proxy PAC optionnel via .env
"""

import os
import sys
import threading
from pathlib import Path

import requests
import urllib3
from dotenv import load_dotenv

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Désactiver le cache tldextract AVANT import pypac
os.environ["TLDEXTRACT_CACHE"] = "no"

try:
    from pypac import get_pac
    from pypac.resolver import ProxyResolver

    PYPAC_AVAILABLE = True
except ImportError:
    PYPAC_AVAILABLE = False

base_dir = (
    Path(sys.executable).parent
    if getattr(sys, "frozen", False)
    else Path(__file__).parent
)
load_dotenv(base_dir / ".env", override=True)

# ── Valeurs par défaut intégrées au build ───────────────────────
# Utilisées UNIQUEMENT si absentes du .env / de l'environnement.
# Permet de distribuer l'exe SANS fichier .env à côté (le jeton est
# alors figé dans le binaire au moment du build → à rebuilder si le
# jeton change). Laisser vide pour garder le comportement .env-only.
# ⚠ À remplir juste avant le build, ne pas committer avec une vraie valeur.
_DEFAULT_GRIST_URL = ""
_DEFAULT_GRIST_API_KEY = ""
_DEFAULT_GRIST_DOC_ID = ""
_DEFAULT_GRIST_TABLE_ID = ""
_DEFAULT_PROXY_PAC_URL = ""

GRIST_URL = os.getenv("GRIST_URL", _DEFAULT_GRIST_URL).rstrip("/")
GRIST_API_KEY = os.getenv("GRIST_API_KEY", _DEFAULT_GRIST_API_KEY)
GRIST_DOC_ID = os.getenv("GRIST_DOC_ID", _DEFAULT_GRIST_DOC_ID)
GRIST_TABLE = os.getenv("GRIST_TABLE_ID", _DEFAULT_GRIST_TABLE_ID)
PROXY_PAC_URL = os.getenv("PROXY_PAC_URL", _DEFAULT_PROXY_PAC_URL)

# Propager les valeurs résolues (avec fallback appliqué) dans
# l'environnement, pour que le reste de l'app (logs de app.py) les voie.
os.environ.setdefault("GRIST_URL", GRIST_URL)
os.environ.setdefault("GRIST_API_KEY", GRIST_API_KEY)
os.environ.setdefault("GRIST_DOC_ID", GRIST_DOC_ID)
os.environ.setdefault("GRIST_TABLE_ID", GRIST_TABLE)
os.environ.setdefault("PROXY_PAC_URL", PROXY_PAC_URL)

_session = None
_session_lock = threading.Lock()


def _build_session() -> requests.Session:
    global _session
    with _session_lock:
        if _session is not None:
            return _session

        if PROXY_PAC_URL and PYPAC_AVAILABLE:
            try:
                pac = get_pac(url=PROXY_PAC_URL)
                resolver = ProxyResolver(pac=pac)
                proxies = resolver.get_proxy_for_requests(GRIST_URL)
                print(f"[INFO] Proxies détectés: {proxies}")

                proxy_url = (
                    proxies.get("https") or proxies.get("http") if proxies else None
                )

                if not proxy_url or proxy_url == "DIRECT":
                    print("[INFO] PAC indique DIRECT — connexion directe")
                    _session = requests.Session()
                else:
                    # Utiliser requests directement avec le proxy — évite tldextract
                    sess = requests.Session()
                    sess.proxies.update({"http": proxy_url, "https": proxy_url})
                    sess.get(GRIST_URL, timeout=5)
                    print(f"[INFO] Proxy actif : {proxy_url}")
                    _session = sess

            except Exception as e:
                print(f"[WARN] Proxy PAC échoué ({e}) — connexion directe")
                _session = requests.Session()

        elif PROXY_PAC_URL and not PYPAC_AVAILABLE:
            print("[WARN] pypac non installé — connexion directe")
            _session = requests.Session()
        else:
            print("[INFO] Connexion directe")
            _session = requests.Session()

        return _session


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {GRIST_API_KEY}",
        "Content-Type": "application/json",
    }


def _records_url() -> str:
    return f"{GRIST_URL}/api/docs/{GRIST_DOC_ID}/tables/{GRIST_TABLE}/records"


def _count_grist_rows() -> int:
    try:
        resp = _build_session().get(
            _records_url(),
            headers=_headers(),
            params={"fields": "id"},
            timeout=15,
        )
        if not resp.ok:
            return 0
        return len(resp.json().get("records", []))
    except Exception:
        return 0


def fetch_records() -> list[dict] | None:
    """Toutes les lignes de la table Grist ({colonne: valeur}). None si la lecture échoue."""
    try:
        resp = _build_session().get(_records_url(), headers=_headers(), timeout=60)
        if not resp.ok:
            return None
        return [r.get("fields", {}) for r in resp.json().get("records", [])]
    except Exception:
        return None


def _cmp(value):
    """Valeur normalisée pour comparer une valeur à envoyer avec celle de Grist."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value)
    return value


def count_changes(existing: list[dict], rows: list[dict], upsert_keys: list[str]) -> dict:
    """
    Compare les lignes à envoyer avec la table Grist actuelle, sans rien écrire.
    Retourne {"added": n, "modified": n, "unchanged": n}.
    """
    index: dict[tuple, list[dict]] = {}
    for rec in existing:
        key = tuple(_cmp(rec.get(k)) for k in upsert_keys)
        index.setdefault(key, []).append(rec)

    added = modified = unchanged = 0
    for row in rows:
        matches = index.get(tuple(_cmp(row.get(k)) for k in upsert_keys))
        if not matches:
            added += 1
        elif any(_cmp(row[c]) != _cmp(rec.get(c)) for rec in matches for c in row):
            modified += 1
        else:
            unchanged += 1
    return {"added": added, "modified": modified, "unchanged": unchanged}


def send_rows(rows: list[dict], upsert_keys: list[str]) -> dict:
    if not rows:
        return {"rows_sent": 0}

    session = _build_session()

    if upsert_keys:
        records = []
        for row in rows:
            require = {k: row[k] for k in upsert_keys if k in row}
            fields = {k: v for k, v in row.items() if k not in upsert_keys}
            records.append({"require": require, "fields": fields})
        payload = {"records": records}
        params = {"allow_empty_require": "1"}
        resp = session.put(
            _records_url(), json=payload, headers=_headers(), params=params, timeout=30
        )
    else:
        payload = {"records": [{"fields": r} for r in rows]}
        resp = session.post(
            _records_url(), json=payload, headers=_headers(), timeout=30
        )

    if not resp.ok:
        raise RuntimeError(f"Grist {resp.status_code}: {resp.text}")

    return {"rows_sent": len(rows)}


def fetch_columns() -> list[str]:
    url = f"{GRIST_URL}/api/docs/{GRIST_DOC_ID}/tables/{GRIST_TABLE}/columns"
    resp = _build_session().get(url, headers=_headers(), timeout=10)
    if not resp.ok:
        raise RuntimeError(f"Grist {resp.status_code}: {resp.text}")
    return [c["id"] for c in resp.json().get("columns", [])]


def fetch_doc_name() -> str:
    url = f"{GRIST_URL}/api/docs/{GRIST_DOC_ID}"
    resp = _build_session().get(url, headers=_headers(), timeout=10)
    if not resp.ok:
        return GRIST_DOC_ID
    return resp.json().get("name", GRIST_DOC_ID)


def check_config() -> tuple[bool, str]:
    missing = []
    if not GRIST_URL:
        missing.append("GRIST_URL")
    if not GRIST_API_KEY:
        missing.append("GRIST_API_KEY")
    if not GRIST_DOC_ID:
        missing.append("GRIST_DOC_ID")
    if not GRIST_TABLE:
        missing.append("GRIST_TABLE_ID")
    if missing:
        return False, f"Variables manquantes : {', '.join(missing)}"
    try:
        fetch_columns()
        doc_name = fetch_doc_name()
        return True, f"{doc_name}\n{GRIST_TABLE}"
    except Exception as e:
        return False, str(e)
