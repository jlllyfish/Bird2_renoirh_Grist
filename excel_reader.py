"""
Lecture et jointure des fichiers Excel/CSV — Bird 2.

Contrairement à Bird 1 (jointure entre onglets d'un même classeur),
ici la jointure se fait ENTRE PLUSIEURS FICHIERS déposés ensemble.
Chaque fichier est identifié par son onglet (ou "__csv__" pour un CSV)
+ une colonne distinctive (certains fichiers partagent le même nom
d'onglet).
"""

import csv
import logging
from datetime import time
from pathlib import Path

import openpyxl
from mapping import CASES, COLUMN_MAP, SKIP_NONE_COLS

log = logging.getLogger("bird")

HOUR_COLUMNS = {"Nbre_heures_suivies"}
TIME_COLUMNS: set[str] = set()

# Onglet virtuel utilisé pour représenter le contenu d'un fichier CSV
CSV_SHEET = "__csv__"


def _to_float_hours(val) -> float | None:
    if val is None:
        return None
    if isinstance(val, time):
        return round(val.hour + val.minute / 100, 2)
    if isinstance(val, str) and ":" in val:
        parts = val.strip().split(":")
        try:
            return round(int(parts[0]) + int(parts[1]) / 100, 2)
        except (ValueError, IndexError):
            return None
    if isinstance(val, float) and 0.0 <= val < 1.0:
        total = round(val * 24 * 60)
        h, m = divmod(total, 60)
        return round(h + m / 100, 2)
    if isinstance(val, (int, float)):
        return float(val)
    return None


def _to_str_time(val) -> str | None:
    if val is None:
        return None
    if isinstance(val, time):
        return val.strftime("%H:%M")
    if isinstance(val, str) and ":" in val:
        return val.strip()[:5]
    if isinstance(val, float) and 0.0 <= val < 1.0:
        total = round(val * 24 * 60)
        h, m = divmod(total, 60)
        return f"{h:02d}:{m:02d}"
    return str(val)


def _convert(grist_col: str, val):
    if val is None or val == "":
        return None
    if grist_col in HOUR_COLUMNS:
        return _to_float_hours(val)
    if grist_col in TIME_COLUMNS:
        return _to_str_time(val)
    if hasattr(val, "isoformat"):
        return val.isoformat()
    return val


def _read_xlsx(path: Path) -> dict:
    """Retourne {sheet_name: (headers, rows)} pour tout le classeur."""
    wb = openpyxl.load_workbook(path, read_only=False, data_only=True)
    out = {}
    for name in wb.sheetnames:
        ws = wb[name]
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            continue
        headers = [str(h).strip() if h is not None else "" for h in rows[0]]
        out[name] = (headers, rows[1:])
    wb.close()
    return out


def _read_csv(path: Path) -> dict:
    """
    Lit un CSV (délimiteur ';', encodage cp1252 — export RenoirRH).
    Retourne {CSV_SHEET: (headers, rows)} pour rester compatible avec
    le format xlsx.
    """
    with open(path, encoding="cp1252", newline="") as f:
        reader = csv.reader(f, delimiter=";")
        all_rows = [tuple(r) for r in reader]
    if not all_rows:
        return {}
    headers = [h.strip() for h in all_rows[0]]
    return {CSV_SHEET: (headers, all_rows[1:])}


def _read_file(path: Path) -> dict:
    if path.suffix.lower() == ".csv":
        return _read_csv(path)
    return _read_xlsx(path)


def _rows_to_records(headers: list[str], rows: list[tuple], wanted_cols: list[str]) -> list[dict]:
    col_indices = {h: i for i, h in enumerate(headers) if h in wanted_cols}
    records = []
    for row in rows:
        if all(c is None or c == "" for c in row):
            continue
        record: dict = {}
        for excel_col, idx in col_indices.items():
            grist_col = COLUMN_MAP.get(excel_col)
            if grist_col and idx < len(row):
                val = _convert(grist_col, row[idx])
                if val is not None or grist_col not in SKIP_NONE_COLS:
                    record[grist_col] = val
        if record:
            records.append(record)
    return records


def _norm(v) -> str:
    return str(v).strip().casefold()


def _key_of(record: dict, key_cols: list[str]) -> tuple | None:
    if not all(k in record and record[k] not in (None, "") for k in key_cols):
        return None
    return tuple(_norm(record[k]) for k in key_cols)


def _find_sheet(sheets: dict, wanted: str) -> str | None:
    """
    Retrouve le nom réel de l'onglet dans `sheets` correspondant à `wanted`.
    Tolère la troncature des noms d'onglets trop longs (RenoirRH/Excel
    coupent le nom et ajoutent "..." — ex: "1.1 Inscription période de
    formation" devient "1.1 Inscription période de f...").
    """
    if wanted in sheets:
        return wanted
    for name in sheets:
        if name.endswith("..."):
            core = name[:-3]
            if core and wanted.startswith(core):
                return name
        elif wanted.endswith("...") and wanted[:-3] and name.startswith(wanted[:-3]):
            return name
    return None


def _spec_matches_file(spec: dict, sheets: dict) -> bool:
    actual_sheet = _find_sheet(sheets, spec["sheet"])
    if actual_sheet is None:
        return False
    headers, _ = sheets[actual_sheet]
    return spec["detect_col"] in headers


def _read_role(spec: dict, sheets: dict) -> tuple[list[str], list[tuple]]:
    actual_sheet = _find_sheet(sheets, spec["sheet"])
    return sheets[actual_sheet]


def _match_case(files_content: dict[Path, dict]) -> tuple[dict, dict[str, Path]] | None:
    """
    Essaie de faire correspondre le batch de fichiers déposés à un cas.
    Retourne (case, {role: filepath}) où `role` couvre les rôles requis
    ET les rôles optionnels trouvés parmi les fichiers restants
    (roles marqués "optional": True, ou définis dans "optional_roles").
    """
    for case in CASES:
        assigned: dict[str, Path] = {}
        used_files: set[Path] = set()
        ok = True

        # Rôles requis (non marqués "optional")
        required = {r: s for r, s in case["roles"].items() if not s.get("optional")}
        for role, spec in required.items():
            found = None
            for path, sheets in files_content.items():
                if path in used_files:
                    continue
                if _spec_matches_file(spec, sheets):
                    found = path
                    break
            if not found:
                ok = False
                log.debug(
                    f"Cas '{case['label']}' — rôle '{role}' non trouvé "
                    f"(onglet attendu: '{spec['sheet']}', colonne distinctive: '{spec['detect_col']}')"
                )
                break
            assigned[role] = found
            used_files.add(found)
        if not ok:
            continue

        # Rôles optionnels (roles marqués "optional" + optional_roles) :
        # cherchés parmi les fichiers restants du batch
        optional = {r: s for r, s in case["roles"].items() if s.get("optional")}
        optional.update(case.get("optional_roles", {}))
        for role, spec in optional.items():
            for path, sheets in files_content.items():
                if path in used_files:
                    continue
                if _spec_matches_file(spec, sheets):
                    assigned[role] = path
                    used_files.add(path)
                    log.info(f"Rôle optionnel '{role}' détecté: {path.name}")
                    break
            else:
                log.info(f"Rôle optionnel '{role}' absent du batch — ignoré")

        return case, assigned
    return None


def _merge_full_key(merged: dict, records: list[dict], full_key: list[str]):
    for rec in records:
        key = _key_of(rec, full_key)
        if key is None:
            continue
        merged.setdefault(key, {}).update(rec)


def _apply_lookup(merged: dict, records: list[dict], join_key: list[str]):
    index: dict[tuple, dict] = {}
    for rec in records:
        key = _key_of(rec, join_key)
        if key is None:
            continue
        index[key] = rec
    for rec in merged.values():
        reduced = tuple(rec.get(k) for k in join_key)
        if any(v in (None, "") for v in reduced):
            continue
        reduced = tuple(_norm(v) for v in reduced)
        extra = index.get(reduced)
        if extra:
            rec.update(extra)


def aggregate_files_by_profile(filepaths: list[Path]) -> list[tuple[list[dict], list[str]]]:
    """
    Lit tous les fichiers du batch, détecte le cas et effectue la
    jointure entre fichiers. Retourne [(rows, effective_upsert_keys)].
    """
    files_content = {}
    for path in filepaths:
        try:
            content = _read_file(Path(path))
            files_content[Path(path)] = content
            log.info(f"{Path(path).name} — onglets: {list(content.keys())}")
        except Exception as e:
            log.warning(f"Impossible de lire {path}: {e}")

    match = _match_case(files_content)
    if not match:
        log.warning(f"Aucun cas reconnu pour le batch: {[p.name for p in filepaths]}")
        return []

    case, assigned = match
    full_key = case["full_key"]
    log.info(f"Cas détecté: {case['label']} — " + ", ".join(f"{r}={p.name}" for r, p in assigned.items()))

    # Table principale
    principal_spec = case["roles"]["principal"]
    headers, rows = _read_role(principal_spec, files_content[assigned["principal"]])
    merged: dict[tuple, dict] = {}
    _merge_full_key(merged, _rows_to_records(headers, rows, principal_spec["cols"]), full_key)

    # Fusion (même clé complète) — optionnelle si non trouvée dans le batch
    if "fusion" in assigned:
        fusion_spec = case["roles"]["fusion"]
        headers, rows = _read_role(fusion_spec, files_content[assigned["fusion"]])
        _merge_full_key(merged, _rows_to_records(headers, rows, fusion_spec["cols"]), full_key)

    # Lookups (clé réduite) : rôle "lookup" + tous les rôles optionnels trouvés
    lookup_roles = {
        r: spec for r, spec in case["roles"].items() if r not in ("principal", "fusion")
    }
    lookup_roles.update(case.get("optional_roles", {}))

    for role, spec in lookup_roles.items():
        if role not in assigned:
            continue
        headers, rows = _read_role(spec, files_content[assigned[role]])
        records = _rows_to_records(headers, rows, spec["cols"])
        _apply_lookup(merged, records, spec["join_key"])

    rows_out = list(merged.values())

    effective = [k for k in full_key if any(k in row and row[k] is not None for row in rows_out)]
    if not effective:
        effective = full_key

    log.info(f"{case['label']} → {len(rows_out)} lignes, clés: {effective}")
    return [(rows_out, effective)] if rows_out else []
