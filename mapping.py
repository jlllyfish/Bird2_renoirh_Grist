# ─────────────────────────────────────────────────────────────
#  MAPPING CONFIGURATION — Bird 2
# ─────────────────────────────────────────────────────────────
#
# Contrairement à Bird 1 (jointure entre onglets d'UN MÊME fichier),
# Bird 2 joint des données réparties sur PLUSIEURS FICHIERS Excel
# déposés ensemble dans un même import.
#
# Chaque fichier est identifié par son onglet + une colonne
# "distinctive" (présente uniquement dans ce fichier), car certains
# fichiers partagent le même nom d'onglet.
#
# Un "cas" (CASE_A, CASE_B) regroupe les rôles de fichiers attendus :
#   - "principal" : une ligne = une ligne Grist (table de base), TOUJOURS requis
#   - "fusion"    : vient COMPLÉTER le principal, même clé complète
#                   (mêmes Libellé/Stage/Session/Présentation[/Numero_de_periode]).
#                   Peut être marqué "optional": True — si absent du batch,
#                   les données du principal partent quand même vers Grist.
#   - "lookup"    : vient AJOUTER des colonnes via une clé réduite
#                   (join_key propre, différente de la clé complète).
#                   Peut aussi être marqué "optional": True.
#
# Le cas utilisé est déterminé automatiquement selon les fichiers
# reconnus dans le batch déposé (voir excel_reader.py).

# ── MAPPING COLONNES Excel → Grist ────────────────────────────
# Toutes les colonnes de tous les fichiers/cas, centralisées ici.
COLUMN_MAP: dict[str, str] = {
    "Stage":                                   "Stage",
    "Libellé":                                 "Libelle",
    "Session":                                 "Session",
    "Identifiant de la période":               "Numero_de_periode",
    "Présentation nom réelle":                 "Presentation_du_nom",
    "Présentation nom":                        "Presentation_du_nom",
    "Présentation du nom":                     "Presentation_du_nom",
    "Etat d'inscription à la période":         "Registration_Status",
    "Registration Status":                     "Registration_Status",
    "Primary Assignment Title":                "Etablissement",
    "Nombre heures présence par salarié":      "Nbre_heures_suivies",
    "Paid Hours":                               "Nbre_heures_suivies",
    "Nom participant":                         "Presentation_du_nom",
    "Mail participant":                        "Mail_participant",
}

# ── FICHIER CSV OPTIONNEL : mails des participants ────────────
# Peut arriver en 4e fichier du cas A, en 3e fichier du cas B, ou seul.
# Onglet "__csv__" = marqueur interne pour les fichiers CSV (pas de vrai onglet).
CSV_MAIL_ROLE = {
    "sheet":      "__csv__",
    "detect_col": "Mail participant",
    "cols": ["Nom participant", "Mail participant"],
    "join_key": ["Presentation_du_nom"],
}

# ── CAS A : 3 fichiers (HRA-Par_période_de_formation / HRA-Par_session-periodes / HRA-Présence-Absence_periodes) ──
CASE_A = {
    "label": "3 fichiers (période de formation)",
    "full_key": ["Libelle", "Stage", "Session", "Presentation_du_nom", "Numero_de_periode"],
    "roles": {
        "principal": {
            "sheet":      "1.1 Inscription période de formation",
            "detect_col": "Etat d'inscription à la période",
            "cols": [
                "Libellé", "Stage", "Session",
                "Identifiant de la période",
                "Présentation nom réelle",
                "Etat d'inscription à la période",
            ],
        },
        "fusion": {
            "sheet":      "1.1 Inscription période de formation",
            "detect_col": "Nombre heures présence par salarié",
            "optional":   True,
            "cols": [
                "Libellé", "Stage", "Session",
                "Identifiant de la période",
                "Présentation nom",
                "Nombre heures présence par salarié",
            ],
        },
        "lookup": {
            "sheet":      "1.1 Individual Request",
            "detect_col": "Primary Assignment Title",
            "optional":   True,
            "cols": [
                "Libellé", "Stage", "Session",
                "Présentation du nom",
                "Primary Assignment Title",
            ],
            # Clé réduite utilisée pour ce lookup (sans Numero_de_periode)
            "join_key": ["Libelle", "Stage", "Session", "Presentation_du_nom"],
        },
    },
    "optional_roles": {
        "mail": CSV_MAIL_ROLE,
    },
}

# ── CAS B : 2 fichiers (HRA-Gérer_les_inscriptions / HRA-Présence-Absence_session) ──
CASE_B = {
    "label": "2 fichiers (session)",
    "full_key": ["Libelle", "Stage", "Session", "Presentation_du_nom"],
    "roles": {
        "principal": {
            # HRA-Gérer_les_inscriptions.xlsx
            "sheet":      "1.1 Individual Request",
            "detect_col": "Registration Status",
            "cols": [
                "Libellé", "Stage", "Session",
                "Présentation du nom",
                "Primary Assignment Title",
                "Registration Status",
            ],
        },
        "fusion": {
            # HRA-Présence-Absence_session.xlsx
            "sheet":      "1.1 Individual Request",
            "detect_col": "Paid Hours",
            "optional":   True,
            "cols": [
                "Libellé", "Stage", "Session",
                "Présentation du nom",
                "Paid Hours",
            ],
        },
    },
    "optional_roles": {
        "mail": CSV_MAIL_ROLE,
    },
}

# ── CAS C : le CSV de mails déposé seul ────────────────────────
CASE_C = {
    "label": "CSV mails seul",
    "full_key": ["Presentation_du_nom"],
    "roles": {
        "principal": CSV_MAIL_ROLE,
    },
}

CASES = [CASE_A, CASE_B, CASE_C]

BATCH_SIZE: int = 500

# Colonnes à ne pas envoyer si elles valent None
# (évite d'écraser des données existantes avec des blancs)
SKIP_NONE_COLS: set[str] = {"Numero_de_periode", "Nbre_heures_suivies", "Etablissement", "Mail_participant"}
