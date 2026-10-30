"""
Script de diagnostic Grist
"""

import argparse
import os
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("pip install requests")

# .env local (à côté de ce script)
ENV_PATH = Path(__file__).parent / ".env"

try:
    from dotenv import load_dotenv

    if ENV_PATH.exists():
        load_dotenv(dotenv_path=ENV_PATH, override=True)
        print(f"\n  .env chargé : {ENV_PATH}")
    else:
        print(f"\n  ⚠ .env introuvable : {ENV_PATH}")
except ImportError:
    print("\n  ⚠ python-dotenv non installé — pip install python-dotenv")

p = argparse.ArgumentParser()
p.add_argument("--url", default=os.getenv("GRIST_URL", ""))
p.add_argument("--key", default=os.getenv("GRIST_API_KEY", ""))
p.add_argument("--doc", default=os.getenv("GRIST_DOC_ID", ""))
p.add_argument("--table", default=os.getenv("GRIST_TABLE_ID", ""))
args = p.parse_args()

URL = args.url.rstrip("/")
KEY = args.key
DOC = args.doc
TABLE = args.table

print(f"\n{'─' * 60}")
print(f"  URL   : {URL or '❌ manquant'}")
print(f"  KEY   : {'*' * 8 + '...' if KEY else '❌ manquant'}")
print(f"  DOC   : {DOC or '❌ manquant'}")
print(f"  TABLE : {TABLE or '(non spécifiée)'}")
print(f"{'─' * 60}\n")

if not all([URL, KEY, DOC]):
    sys.exit("Variables manquantes")

headers = {"Authorization": f"Bearer {KEY}"}

# Tables
print("── TABLES ──────────────────────────────────────────────")
r = requests.get(f"{URL}/api/docs/{DOC}/tables", headers=headers, timeout=10)
if r.status_code == 401:
    sys.exit("❌ API key invalide")
if r.status_code == 404:
    sys.exit("❌ Document introuvable")
r.raise_for_status()

tables = r.json().get("tables", [])
for t in tables:
    marker = " ◄" if t["id"] == TABLE else ""
    print(f"  {t['id']}{marker}")

# Colonnes
target = TABLE or (tables[0]["id"] if tables else None)
if not target:
    sys.exit("\nAucune table trouvée.")

print(f"\n── COLONNES de '{target}' ───────────────────────────────")
r2 = requests.get(
    f"{URL}/api/docs/{DOC}/tables/{target}/columns", headers=headers, timeout=10
)
if not r2.ok:
    sys.exit(f"❌ {r2.status_code} {r2.text}")

cols = r2.json().get("columns", [])
print(f"  {'ID (COLUMN_MAP)':<40} Label affiché")
print(f"  {'─' * 40} {'─' * 25}")
for c in cols:
    print(f"  {c['id']:<40} {c['fields'].get('label', c['id'])}")

print("\n→ Utilisez les IDs dans COLUMN_MAP et UPSERT_KEYS\n")
