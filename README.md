# scripts_cse - Guide utilisateur

Ce projet aide a preparer des fichiers CSE a partir de deux sources:

- export Swile
- export Active Directory (Microsoft Graph)

## 0) Utilisation recommandee: runner genere par le deploiement

Le mode le plus simple pour les utilisateurs finaux est d'utiliser
l'executable (runner) genere par le pipeline CI de deploiement.

Artefacts generes selon la plateforme:

- GestionCSE-windows-x64
- GestionCSE-macos
- GestionCSE-linux

Chaque artefact contient:

- le binaire de l'application
- un fichier LIRE_AVANT_LANCEMENT.txt

Important:

- placez le fichier liste_salarie_active_directory.config.json a cote du binaire
- le modele CSV Swile est deja embarque dans le runner

Vous pouvez l'utiliser:

- via une interface graphique (recommande)
- via des commandes en ligne de commande (avance)

## 1) Prerequis

- Windows, macOS ou Linux
- Python 3.10 ou plus recent
- Acces Microsoft pour generer l'export Active Directory

Notes:

- Windows est la plateforme la plus simple a utiliser dans ce depot (scripts PowerShell prets a l'emploi).
- macOS et Linux sont supportes via Python directement.

## 2) Installation locale (optionnelle)

Cette section est utile uniquement si vous n'utilisez pas le runner genere par
le deploiement.

Depuis la racine du projet:

### Windows

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Alternative (script fourni):

```powershell
.\debug\debug_deploy.ps1
```

### macOS / Linux

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
```

## 3) Lancement de l'application (interface graphique)

### Windows

```powershell
.\run_cse_desktop_app.ps1
```

Ou:

```powershell
.\.venv\Scripts\python.exe .\cse_desktop_app.py
```

### macOS / Linux

```bash
./.venv/bin/python ./cse_desktop_app.py
```

## 4) Utilisation conseillee (pas a pas)

1. Ouvrez l'onglet `liste_salarie_active_directory`.
2. Cliquez sur `Generer la liste Active Directory`.
3. Suivez la connexion Microsoft (code de verification) si demandee.
4. Deposez les CSV requis dans l'onglet `swile_active_directory`:
   - fichier Swile (separateur `;`)
   - fichier Active Directory (separateur `,`)
5. Cliquez sur `Comparer les listes et preparer les ajouts Swile`.
6. Recuperez les resultats dans le dossier de sortie.

## 5) Emplacements des fichiers

- Entree Swile: `swile_active_directory/in`
- Sortie Swile: `swile_active_directory/out`
- Sortie export Active Directory: `liste_salarie_active_directory/out`
- Journal d'execution: `log`

## 6) Formats CSV attendus

### Fichier Swile (separateur `;`)

Colonnes minimales:

- `Prenom`
- `Nom`
- `Email`
- `Matricule`

### Fichier Active Directory (separateur `,`)

Colonnes minimales pour comparaison/ajouts:

- `Nom`
- `Email`
- `Identifiant`
- `Poste`

Pour la generation des valeurs de lieu de travail, la colonne `Lieu de travail`
est utilisee quand elle est disponible.

## 7) Fichiers generes

Selon l'action, vous obtiendrez notamment:

- `*-trouves.csv`
- `*-non-trouves.csv`
- `collaborators-additions-YYYYMMDDtHHMMSS.csv`
- `collaborators-ignored-additions-...csv`
- `collaborators-attribute-values-YYYYMMDDtHHMMSS.csv`

## 8) Utilisation en ligne de commande (avance)

### Generer l'export Active Directory

Windows:

```powershell
.\.venv\Scripts\python.exe .\liste_salarie_active_directory.py
```

macOS / Linux:

```bash
./.venv/bin/python ./liste_salarie_active_directory.py
```

### Traitements Swile

Windows:

```powershell
.\.venv\Scripts\python.exe .\swile_active_directory.py all
```

macOS / Linux:

```bash
./.venv/bin/python ./swile_active_directory.py all
```

Actions disponibles:

- `compare`
- `additions`
- `all`
- `location_values`

Exemple avec fichiers explicites:

```powershell
.\.venv\Scripts\python.exe .\swile_active_directory.py compare \
  --swile-file .\swile_active_directory\in\collaborators.csv \
  --active-directory-file .\swile_active_directory\in\20261103_liste_salarie_active_directory.csv
```

Equivalent macOS / Linux:

```bash
./.venv/bin/python ./swile_active_directory.py compare \
  --swile-file ./swile_active_directory/in/collaborators.csv \
  --active-directory-file ./swile_active_directory/in/20261103_liste_salarie_active_directory.csv
```

## 9) Configuration Active Directory

Le fichier `liste_salarie_active_directory.config.json` doit etre renseigne.
Champs obligatoires:

- `start_user_email`
- `client_id`
- `authority`
- `scopes`
- `report_domain`

Important: ne partagez pas ce fichier en dehors de votre organisation.

## 10) Depannage rapide

- Message `Environnement Python introuvable`:
  - executez `.\debug\debug_deploy.ps1`
- Erreur de colonnes CSV:
  - verifiez les noms de colonnes attendus et le bon separateur
- Aucun resultat:
  - verifiez que les fichiers ont bien ete deposes dans les dossiers `in`
- Probleme de connexion Microsoft:
  - relancez et verifiez la configuration `liste_salarie_active_directory.config.json`
