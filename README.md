# Gestion des fichiers CSE

Cette application graphique aide à préparer les fichiers CSE à partir des
listes Swile et Active Directory. Elle permet de générer un export des salariés,
de comparer les listes et de préparer les fichiers à importer dans Swile.

## Démarrage rapide

### 1. Télécharger et lancer l’application

Téléchargez l’archive correspondant à votre système depuis les
[versions publiées](https://github.com/GaLlaKk/scripts_cse/releases), puis
décompressez-la dans un dossier accessible.

Les archives disponibles sont destinées à Windows, macOS (Intel) et Linux.
L’application s’utilise avec une interface graphique; aucune installation de
Python n’est nécessaire avec ces archives.

### 2. Configurer l’accès à Active Directory

Dans l’onglet **liste_salarie_active_directory**, dépliez la section de
configuration si nécessaire, renseignez les paramètres fournis par votre
organisation, puis cliquez sur **Enregistrer la configuration**. Le fichier
`liste_salarie_active_directory.config.json` est enregistré à côté de
l’application. Il est nécessaire pour récupérer la liste des salariés depuis
Microsoft.

Les paramètres à demander à votre administrateur sont l’adresse de départ,
l’identifiant de l’application, l’autorité Microsoft, le domaine de rapport
et les autorisations (scopes). Ne partagez pas le fichier de configuration en
dehors de votre organisation.

Au premier accès, une connexion Microsoft peut être demandée. Suivez les
indications affichées dans la fenêtre et saisissez le code de vérification.

### 3. Générer et comparer les listes

1. Dans l’onglet **liste_salarie_active_directory**, cliquez sur
   **Générer la liste Active Directory**. La récupération des photos est
   facultative.
2. Dans l’onglet **swile_active_directory**, sélectionnez le fichier Swile et
   le fichier Active Directory avec **Parcourir…**, ou déposez-les dans les
   zones prévues. Le bouton **Copier le dernier export** permet de reprendre
   l’export Active Directory qui vient d’être généré.
3. Cliquez sur **Comparer les listes et préparer les ajouts Swile**.
4. Consultez le détail du traitement dans le panneau de suivi et ouvrez le
   dossier de résultats avec le bouton situé à côté de l’action.

Le fichier Swile utilise le séparateur `;`. L’export Active Directory utilise
le séparateur `,`.

### Générer les valeurs de lieu de travail

Dans l’onglet **swile_active_directory**, ouvrez le sous-onglet **Valeurs de
lieu de travail**, puis cliquez sur le bouton de génération. Cette opération
utilise les fichiers Swile et Active Directory sélectionnés dans le sous-onglet
**Comparer les listes**.

Le mapping peut être modifié dans la section **Configurer le mapping des
lieux** de ce sous-onglet : ajoutez, supprimez ou réordonnez les règles, puis
enregistrez avant de générer le fichier. Les mots-clés séparés par des
points-virgules doivent tous correspondre au lieu Active Directory. Le mapping
est également défini dans `lieux_travail.config.json`, à côté de
l’application, pour une modification directe. Les règles fournies par défaut
associent Courcelles à `Paris 145`, Wasquehal et l’avenue de la Marne à
`Lille 5.9`, et Paris 133 à `Paris 133`. Si aucune règle ne correspond, la
valeur `Autre` est produite.
Les règles sont évaluées dans l’ordre et la première correspondance est
utilisée. Si le fichier est absent, les règles par défaut restent disponibles.

## Fichiers et résultats

Les fichiers peuvent être sélectionnés dans l’interface ou déposés dans les
zones prévues. Les dossiers utilisés par l’application sont :

- Entrées et résultats Swile : `swile_active_directory/in` et
  `swile_active_directory/out`
- Export Active Directory : `liste_salarie_active_directory/out`
- Journaux de traitement : `log`

Les résultats peuvent inclure les listes d’utilisateurs trouvés et non trouvés,
les fichiers d’ajouts et d’ajouts ignorés, ainsi que le fichier des valeurs de
lieu de travail.

### Colonnes attendues

Le fichier Swile doit contenir au minimum les colonnes `Prénom`, `Nom`,
`Email` et `Matricule`.

Le fichier Active Directory doit contenir au minimum les colonnes `Nom`,
`Email`, `Identifiant` et `Poste` pour la comparaison et la préparation des
ajouts. La colonne `Lieu de travail` est utilisée pour générer les valeurs de
lieu; si elle est absente, la valeur par défaut est appliquée.

## Dépannage

- **La connexion Microsoft échoue** : vérifiez les paramètres Active Directory
  avec votre administrateur, puis réessayez.
- **Un message indique qu’une colonne manque** : vérifiez les en-têtes attendus
  ci-dessus ainsi que le séparateur du fichier.
- **Aucun résultat n’est produit** : vérifiez que les bons fichiers Swile et
  Active Directory ont été sélectionnés et qu’ils contiennent des données.
- **Le mapping des lieux ne s’applique pas comme prévu** : vérifiez les règles
  dans l’interface ou dans `lieux_travail.config.json`. Les termes sont
  recherchés sans tenir compte des majuscules ni des accents, et les règles les
  plus haut placées sont prioritaires.

## Avancé

Cette partie est destinée aux personnes qui souhaitent lancer le projet depuis
les sources, utiliser les commandes en ligne de commande ou exécuter les tests.
Pour l’utilisation habituelle, privilégiez l’application graphique téléchargée
ci-dessus.

### Installation et lancement depuis les sources

Python 3.12 est utilisé pour les tests et la compilation automatisée. Depuis la
racine du dépôt, créez un environnement virtuel et installez les dépendances.

Windows, avec PowerShell :

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\run_cse_desktop_app.ps1
```

Le script `.\debug\debug_deploy.ps1` peut également préparer l’environnement
local sous Windows.

macOS et Linux :

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
./.venv/bin/python ./cse_desktop_app.py
```

### Commandes en ligne de commande

Les commandes ci-dessous s’exécutent depuis la racine du dépôt et utilisent
l’environnement virtuel créé précédemment.

Générer l’export Active Directory :

```powershell
.\.venv\Scripts\python.exe .\liste_salarie_active_directory.py
```

Sur macOS ou Linux :

```bash
./.venv/bin/python ./liste_salarie_active_directory.py
```

Lancer les traitements Swile (comparaison et préparation des ajouts) :

```powershell
.\.venv\Scripts\python.exe .\swile_active_directory.py all
```

Sur macOS ou Linux :

```bash
./.venv/bin/python ./swile_active_directory.py all
```

Actions Swile disponibles : `compare`, `additions`, `all` et `location_values`.
Les fichiers d’entrée sont recherchés dans `swile_active_directory/in` par
défaut. Pour sélectionner explicitement des fichiers :

```powershell
.\.venv\Scripts\python.exe .\swile_active_directory.py compare `
  --swile-file .\swile_active_directory\in\collaborators.csv `
  --active-directory-file .\swile_active_directory\in\export_ad.csv
```

Sur macOS ou Linux :

```bash
./.venv/bin/python ./swile_active_directory.py compare \
  --swile-file ./swile_active_directory/in/collaborators.csv \
  --active-directory-file ./swile_active_directory/in/export_ad.csv
```

### Tests

```powershell
python -m unittest discover -s tests -v
```
