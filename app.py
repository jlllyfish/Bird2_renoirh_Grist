"""
Flask app — Bird 2 / Bridge Import RenoirRH Datas
"""

import os

# Désactiver le cache tldextract AVANT tout import pypac
os.environ["TLDEXTRACT_CACHE"] = "no"

import importlib.util
import logging
import sys
import tempfile
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

# ── base_dir + chargement dynamique de mapping.py ───────────────
# En exe (PyInstaller), mapping.py est normalement figé dans le
# bundle au moment du build. On le recharge ici depuis le disque
# (à côté de l'exe) AVANT tout import qui dépend de "mapping", pour
# pouvoir éditer le mapping sans devoir rebuilder.
base_dir = (
    Path(sys.executable).parent
    if getattr(sys, "frozen", False)
    else Path(__file__).parent
)

_external_mapping = base_dir / "mapping.py"
if _external_mapping.exists():
    _spec = importlib.util.spec_from_file_location("mapping", _external_mapping)
    _mapping_module = importlib.util.module_from_spec(_spec)
    sys.modules["mapping"] = _mapping_module
    _spec.loader.exec_module(_mapping_module)

from dotenv import load_dotenv  # noqa: E402
from excel_reader import aggregate_files_by_profile, build_preview  # noqa: E402
from flask import Flask, jsonify, render_template, request  # noqa: E402
from grist_client import (  # noqa: E402
    GRIST_TABLE,
    _build_session,
    _count_grist_rows,
    check_config,
    count_changes,
    fetch_records,
    send_rows,
)
from mapping import BATCH_SIZE, CASES, COLUMN_MAP  # noqa: E402

# ── Config ────────────────────────────────────────────────────
load_dotenv(base_dir / ".env", override=True)

# ── Logging ───────────────────────────────────────────────────
log_path = base_dir / "bird.log"
logging.basicConfig(
    filename=str(log_path),
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    encoding="utf-8",
)
log = logging.getLogger("bird")
log.info("=== Démarrage Bird 2 ===")
log.info(f"base_dir: {base_dir}")
log.info(f"mapping.py: {'externe (' + str(_external_mapping) + ')' if _external_mapping.exists() else 'embarqué dans le bundle'}")
log.info(f"GRIST_URL: {os.getenv('GRIST_URL', 'NON DÉFINI')}")
log.info(f"GRIST_DOC_ID: {os.getenv('GRIST_DOC_ID', 'NON DÉFINI')}")
log.info(f"GRIST_TABLE_ID: {os.getenv('GRIST_TABLE_ID', 'NON DÉFINI')}")
log.info(f"GRIST_API_KEY: {'défini' if os.getenv('GRIST_API_KEY') else 'NON DÉFINI'}")
log.info(f"PROXY_PAC_URL: {os.getenv('PROXY_PAC_URL', 'non défini')}")

# ── Flask ─────────────────────────────────────────────────────
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024

# ── Heartbeat ─────────────────────────────────────────────────
_last_ping = time.time()
_HEARTBEAT_TIMEOUT = 60


def _watch_heartbeat():
    global _HEARTBEAT_TIMEOUT
    time.sleep(30)
    _HEARTBEAT_TIMEOUT = 15
    while True:
        time.sleep(5)
        if time.time() - _last_ping > _HEARTBEAT_TIMEOUT:
            log.info("Heartbeat perdu — arrêt automatique")
            os._exit(0)


@app.route("/api/ping", methods=["POST"])
def ping():
    global _last_ping
    _last_ping = time.time()
    return "", 204


@app.route("/")
def index():
    ok, msg = check_config()
    log.info(f"check_config: ok={ok}, msg={msg}")
    all_sheets = []
    all_keys = []
    for case in CASES:
        for spec in case["roles"].values():
            all_sheets.append(spec["sheet"])
        all_keys.extend(case["full_key"])
    mapping_info = {
        "sheets": list(dict.fromkeys(all_sheets)),
        "columns": COLUMN_MAP,
        "upsert_keys": list(dict.fromkeys(all_keys)),
    }
    return render_template(
        "index.html", grist_ok=ok, grist_msg=msg, mapping=mapping_info
    )


@app.route("/api/status")
def api_status():
    ok, msg = check_config()
    return jsonify({"ok": ok, "message": msg})


@app.route("/api/preview", methods=["POST"])
def api_preview():
    """Aperçu avant envoi : analyse les fichiers sans rien envoyer vers Grist."""
    files = request.files.getlist("files")
    if not files or all(f.filename == "" for f in files):
        return jsonify({"success": False, "error": "Aucun fichier reçu"}), 400

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = []
            for f in files:
                if not f.filename:
                    continue
                dest = Path(tmpdir) / Path(f.filename).name
                f.save(dest)
                paths.append(dest)
            preview = build_preview(paths)
        return jsonify({"success": True, **preview})
    except Exception as e:
        log.exception(f"Erreur aperçu: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/import", methods=["POST"])
def api_import():
    files = request.files.getlist("files")
    if not files or all(f.filename == "" for f in files):
        return jsonify({"success": False, "error": "Aucun fichier reçu"}), 400

    tmp_paths = []
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            for f in files:
                if not f.filename:
                    continue
                dest = Path(tmpdir) / Path(f.filename).name
                f.save(dest)
                tmp_paths.append(dest)
                log.info(f"Fichier reçu: {f.filename}")

            groups = aggregate_files_by_profile(tmp_paths)
            log.info(f"Groupes extraits: {len(groups)}")
            for i, (rows, keys) in enumerate(groups):
                log.info(f"  Groupe {i + 1}: {len(rows)} lignes, clés={keys}")

        if not groups:
            log.warning("Aucun groupe extrait")
            return jsonify(
                {
                    "success": False,
                    "error": "Aucune donnée extraite. Vérifiez que les fichiers déposés correspondent à un cas connu (voir mapping.py)",
                }
            ), 422

        # État actuel de la table : sert à compter lignes ajoutées / modifiées / inchangées
        existing = fetch_records()
        before_total = len(existing) if existing is not None else _count_grist_rows()
        log.info(f"Lignes Grist avant: {before_total}")
        planned_modified = None
        if existing is not None:
            planned_modified = sum(
                count_changes(existing, rows, keys)["modified"] for rows, keys in groups
            )

        total_sent = 0
        for rows, effective_keys in groups:
            for i in range(0, len(rows), BATCH_SIZE):
                batch = rows[i : i + BATCH_SIZE]
                send_rows(batch, effective_keys)
                total_sent += len(batch)
                log.info(f"Batch envoyé: {len(batch)} lignes")

        after_total = _count_grist_rows()
        total_inserted = max(after_total - before_total, 0)
        matched = max(total_sent - total_inserted, 0)
        if planned_modified is None:
            modified = unchanged = None
        else:
            modified = min(planned_modified, matched)
            unchanged = matched - modified
        # "À jour" seulement si les deux comptages Grist sont fiables
        up_to_date = (
            existing is not None and after_total > 0 and total_inserted == 0 and modified == 0
        )
        log.info(
            f"Résultat: {total_inserted} ajoutées, {modified} modifiées, "
            f"{unchanged} inchangées, à jour={up_to_date}"
        )

        all_keys_used = list(dict.fromkeys(k for _, keys in groups for k in keys))
        return jsonify(
            {
                "success": True,
                "rows_processed": total_sent,
                "inserted": total_inserted,
                "modified": modified,
                "unchanged": unchanged,
                "up_to_date": up_to_date,
                "table": GRIST_TABLE,
                "files_processed": len(tmp_paths),
                "upsert": bool(all_keys_used),
                "upsert_keys": all_keys_used,
            }
        )

    except Exception as e:
        log.error(f"Erreur import: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/quit", methods=["POST"])
def quit_app():
    log.info("Arrêt demandé")

    def _shutdown():
        os._exit(0)

    threading.Timer(0.5, _shutdown).start()
    return jsonify({"ok": True})


def _open_browser():
    for _ in range(40):
        try:
            urllib.request.urlopen("http://localhost:5000", timeout=0.5)
            webbrowser.open("http://localhost:5000")
            log.info("Navigateur ouvert")
            return
        except Exception:
            time.sleep(0.3)


def _init_session():
    log.info("Initialisation session Grist...")
    _build_session()
    log.info("Session Grist prête")


if __name__ == "__main__":
    if getattr(sys, "frozen", False):
        threading.Thread(target=_init_session, daemon=True).start()
        threading.Thread(target=_open_browser, daemon=True).start()
        threading.Thread(target=_watch_heartbeat, daemon=True).start()
    app.run(debug=False, port=5000)
