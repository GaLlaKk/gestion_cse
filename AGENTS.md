# Contexte du dépôt

Avant d’analyser ou de modifier le code, lire ce document. Le tenir à jour avec
les découvertes durables faites pendant les tâches, en privilégiant les
informations qui évitent de relire ou de retracer le dépôt. Ne pas y consigner
de secrets, de données personnelles ni de détails propres à une exécution.

## Vue d’ensemble

Le dépôt regroupe plusieurs outils Python, organisés par usage : `analyse`,
`conversion`, `experiences`, `paiements`, `scripts_CSE` et `validation`.
L’application `scripts_CSE` contient deux flux liés :

- `liste_salarie_active_directory.py` récupère des informations Microsoft
  Graph à partir de sa configuration JSON, puis génère un export CSV.
- `swile_active_directory.py` compare l’export AD à un export Swile et peut
  produire des fichiers d’ajouts et d’ajouts ignorés.
- `cse_desktop_app.py` fournit l’interface Tkinter pour lancer ces traitements
  et choisir les fichiers d’entrée.

Les fichiers CSV sont généralement générés dans les dossiers `in` et `out`
propres aux flux. Les scripts résolvent leurs chemins à partir de leur propre
emplacement.

## Repères — flux Swile / Active Directory

- `scripts_CSE/swile_active_directory.py`
  - `read_csv` vérifie les colonnes requises et gère les fichiers CSV avec
    l’encodage `utf-8-sig`.
  - Les exports Swile utilisent `;` et contiennent `Prénom`, `Nom`, `Email` et
    `Matricule`. L’export Active Directory utilise `,` et les champs `Nom`,
    `Email`, `Identifiant`, `Poste`. `Identifiant` est le login avant `@` du
    `userPrincipalName` renvoyé par Microsoft Graph.
  - `compare_users` écrit les fichiers `*-trouves.csv` et
    `*-non-trouves.csv`.
  - `generate_additions` prend les colonnes du modèle Swile, ajoute
    `Matricule` si elle manque, puis produit le fichier d’ajouts et celui des
    ajouts ignorés (postes de direction).
  - `active_directory_keys` normalise le login de `Identifiant` pour les
    rapprochements. `generate_additions` écrit le login d’origine (sans
    normalisation) dans `Matricule`; le nom complet reste une clé de
    rapprochement distincte.
  - Les clés de rapprochement existantes sont l’email, le matricule normalisé
    et le nom normalisé. Les exclusions comprennent les comptes externes
    `.ext`, les doublons et certains postes de direction.
- `scripts_CSE/cse_desktop_app.py` porte les colonnes requises et les
  délimiteurs affichés par l’interface ; garder ces paramètres cohérents si
  le format d’entrée change.
- `scripts_CSE/liste_salarie_active_directory.config.json` est la configuration
  lue par le script AD. Ne jamais recopier ses valeurs sensibles dans ce
  document ni dans les réponses.
- `scripts_CSE/requirements.txt` liste les dépendances Python, dont `requests`,
  `msal` et `tkinterdnd2`.

## Pratiques de travail

- Les noms des colonnes, les messages et les interfaces de ces scripts sont en
  français ; conserver cette convention et les délimiteurs propres à chaque
  CSV.
- Avant de modifier un export, vérifier les consommateurs du fichier et les
  en-têtes du modèle : le générateur d’ajouts et l’interface ont leurs propres
  listes de colonnes.
- Le dépôt peut contenir des CSV, journaux et autres entrées/sorties locales
  non suivis. Ne pas les supprimer, les écraser ni les ajouter au dépôt sans
  demande explicite ; éviter notamment un `git add` global.
- Aucun test automatisé n’a été repéré lors de la création de ce contexte.
  Vérifier les tests et les commandes disponibles avant de conclure qu’ils
  n’existent pas. Pour une modification Python ciblée, `python -m py_compile`
  sur le script concerné est une vérification minimale, pas un substitut à des
  tests fonctionnels.

## Historique de contexte

- 2026-10-26 : le générateur d’ajouts inclut toujours la colonne `Matricule`,
  alimentée à partir de `Identifiant` dans l’export Active Directory. La
  comparaison normalise ce login, tandis que le fichier d’ajouts conserve sa
  valeur d’origine.
