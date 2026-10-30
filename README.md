# Bird 2 — Bridge Import RenoirRH Datas

Application locale (Flask) qui importe des exports RenoirRH (Excel / CSV) dans une table Grist, avec **upsert**.

Contrairement à Bird 1 (jointure entre les onglets d'un même classeur), Bird 2 **joint les données réparties sur plusieurs fichiers** déposés ensemble, puis envoie le résultat en un seul lot vers Grist.

## Fonctionnement

Les fichiers ne sont **jamais reconnus par leur nom**, mais par le nom d'onglet + une colonne distinctive. Le cas est détecté automatiquement.

| Cas | Fichiers déposés | Rôle |
|---|---|---|
| **A** — période de formation | `HRA-Par_période_de_formation` (onglet `1.1 Inscription période de formation`, colonne `Etat d'inscription à la période`) | principal |
| | `HRA-Présence-Absence_périodes` (même onglet, colonne `Nombre heures présence par salarié`) | fusion, optionnel |
| | `HRA-Par_session-périodes` (onglet `1.1 Individual Request`, colonne `Primary Assignment Title`) | lookup, optionnel |
| **B** — session | `HRA-Gérer_les_inscriptions` (onglet `1.1 Individual Request`, colonne `Registration Status`) | principal |
| | `HRA-Présence-Absence_session` (même onglet, colonne `Paid Hours`) | fusion, optionnel |
| **C** — mails seuls | `Mails.csv` | principal |

Le **CSV des mails** (séparateur `;`, encodage cp1252) est optionnel dans les cas A et B : `Nom participant` est rapproché de `Présentation du nom`, et `Mail participant` alimente `Mail_participant`.

Si un fichier optionnel est absent, les données des autres fichiers partent quand même vers Grist. Les valeurs vides **n'écrasent pas** les données déjà présentes dans Grist (`SKIP_NONE_COLS`).

### Aperçu avant envoi

Dès que des fichiers sont déposés, Bird 2 affiche un aperçu **sans rien envoyer** : cas détecté, nombre de lignes, et pour chaque fichier les colonnes lues, leur **première valeur** et la **colonne Grist** de destination. Les rapprochements incomplets (lignes sans correspondance, colonne attendue absente, fichier non utilisé) sont signalés. Si aucun cas n'est reconnu, les onglets détectés sont listés. Le bouton « Envoyer vers Grist » n'est actif que si l'aperçu est valide.

> Limite connue : le fichier Présence-Absence déposé **seul** n'est pas importable (c'est un rôle de fusion, il lui faut un fichier principal).

### Colonnes Grist alimentées

`Stage`, `Libelle`, `Session`, `Numero_de_periode` (cas A), `Presentation_du_nom`, `Etablissement`, `Registration_Status`, `Nbre_heures_suivies`, `Mail_participant`.

Clés d'upsert : `Libelle`, `Stage`, `Session`, `Presentation_du_nom` (+ `Numero_de_periode` dans le cas A).

## Installation et lancement (Windows / Linux / macOS)

Python 3.10 ou supérieur.

```bash
python3 -m venv venv
source venv/bin/activate          # Windows : venv\Scripts\activate
pip install -r requirements.txt
python3 app.py
```

Puis ouvrir <http://localhost:5000> (le navigateur ne s'ouvre automatiquement qu'avec l'exe). Arrêt : `Ctrl+C`.

## Configuration Grist

Copier `.env.example` en `.env` à côté de `app.py` :

```dotenv
GRIST_URL=https://grist.numerique.gouv.fr
GRIST_API_KEY=...
GRIST_DOC_ID=...
GRIST_TABLE_ID=...
# PROXY_PAC_URL=...   (optionnel)
```

Le fichier `.env` est prioritaire sur les valeurs par défaut de `grist_client.py` (`_DEFAULT_GRIST_*`).

### Distribuer sans `.env` (exe)

Pour qu'un agent n'ait aucun fichier de configuration à gérer, renseigner **en local, juste avant le build**, les constantes `_DEFAULT_GRIST_URL`, `_DEFAULT_GRIST_API_KEY`, `_DEFAULT_GRIST_DOC_ID`, `_DEFAULT_GRIST_TABLE_ID` (et `_DEFAULT_PROXY_PAC_URL`) dans `grist_client.py`.

> ⚠️ **Ne jamais committer ces constantes remplies** : elles contiennent le jeton API. Dans git, elles doivent rester vides.

## Modifier le mapping

Tout est dans `mapping.py` : correspondance colonnes → Grist (`COLUMN_MAP`), cas (`CASE_A/B/C`), clés d'upsert, colonnes à ne pas écraser par du vide.

Avec l'exe, un `mapping.py` placé **à côté de `Bird2.exe`** est chargé à la place de celui embarqué : pas besoin de rebuilder pour corriger un mapping (le log indique la source utilisée).

## Build de l'exécutable (Windows)

```powershell
pip install pyinstaller
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
pyinstaller --clean bird.spec
```

Résultat : `dist/Bird2.exe`. Rappel : renseigner les `_DEFAULT_GRIST_*` avant le build (voir plus haut), et ne pas les committer.

## Diagnostic

```bash
python3 check_grist.py
```

Vérifie la connexion, la table et les identifiants de colonnes Grist (lit le `.env` à côté du script).

## Logs

`bird.log` est écrit à côté de `app.py` (ou de l'exe) : fichiers reçus, onglets lus, cas détecté, rôles optionnels absents, lots envoyés.

## Sécurité et données personnelles

- Les exports RenoirRH contiennent des données personnelles : le `.gitignore` exclut `*.xlsx`, `*.xls`, `*.xlsm` et `*.csv`. Ne jamais les versionner.
- Ne jamais committer `.env`, `bird.log` ni un `grist_client.py` contenant le jeton.

## Structure

```
app.py            Flask, routes, heartbeat, chargement de mapping.py externe
excel_reader.py   Lecture xlsx/csv, détection du cas, jointure entre fichiers
grist_client.py   Connexion API Grist, upsert par lots
mapping.py        Mapping colonnes, cas, clés
check_grist.py    Diagnostic Grist
bird.spec         Build PyInstaller
templates/ static/  Interface (palette jaune / noir)
```

## Évolutions prévues

- v5.0 : version navigateur (Nubo / ProConnect).

Draaf Occitanie — SRFD — 2026
