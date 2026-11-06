# Contexte du dépôt

Avant d’analyser ou de modifier le code, lire ce document. Le tenir à jour avec
les découvertes durables faites pendant les tâches, en privilégiant les
informations qui évitent de relire ou de retracer le dépôt. Ne pas y consigner
de secrets, de données personnelles ni de détails propres à une exécution.

## Vue d’ensemble

Le dépôt regroupe plusieurs outils, dont `paiements`, `swile` et `validation`.
Le projet CSE suivi par Git est actuellement à la racine du dépôt, avec les
répertoires `swile_active_directory`, `liste_salarie_active_directory`, `debug`,
`log`, et les packages `app`, `domain` et `services`. Les scripts Python à la
racine sont des points d’entrée conservés pour lancer les traitements.

- `services/active_directory_export.py` récupère les informations Microsoft
  Graph et génère l’export CSV; `liste_salarie_active_directory.py` est son
  point d’entrée.
- `domain/matching.py` compare l’export AD à l’export Swile.
- `domain/swile_additions.py` prépare les fichiers d’ajouts et d’ajouts ignorés.
- `app/ui/cse_desktop_app.py` fournit l’interface Tkinter.
  La fenêtre principale est optimisée paysage avec les listes Swile et Active
  Directory côte à côte, ainsi qu’un panneau de suivi/résultats redimensionnable
  à côté des onglets. La configuration Active Directory reste repliable et
  s’ouvre automatiquement si elle est absente ou invalide. Le complément
  facultatif d’export précédent est placé sous les contrôles de génération et
  de configuration Active Directory. Il est replié si un export précédent
  valide existe, déplié sinon; le dernier export généré est automatiquement
  utilisé comme export précédent à la prochaine collecte. L’export Active Directory transmet un
  callback de progression à l’interface, qui affiche une barre non bloquante
  basée sur le volume du dernier export valide (ou 500 personnes par défaut)
  et réévalue l’estimation si le volume dépasse la cible.
  Les contenus des onglets Active Directory et des deux sous-onglets Swile
  défilent verticalement avec une barre d’ascenseur et la molette.
- `app/cli/swile_active_directory.py` expose les traitements Swile en CLI.
- `services/swile_service.py` lit/écrit les CSV et orchestre les fonctions métier.
- `.github/workflows/release-gestion-cse.yml` exécute les tests unitaires et
  construit les exécutables Windows, macOS Intel (runner `macos-15-intel`) et
  Linux à chaque push de commit sur une branche, ainsi que pour les tags `v*`;
  il publie les archives ZIP sur une release GitHub uniquement pour les tags
  `v*`. Les artefacts incluent le modèle Swile, mais pas la configuration
  Active Directory. Une exécution manuelle depuis une branche permet aussi de
  valider tests et builds sans publier de release.
- `.github/workflows/copilot-issue-resolver.yml` assigne les issues à Copilot
  coding agent uniquement après l’ajout manuel du label `copilot-ready`.
  L’activation nécessite Copilot coding agent et le secret
  `COPILOT_ASSIGNMENT_TOKEN`; le token utilisateur sert à l’API REST
  d’assignation de GitHub. Le propriétaire du token doit avoir un accès en
  écriture au dépôt. En cas d’erreur HTTP, le workflow journalise le code et le
  message d’erreur API, sans exposer le token. La pull request proposée par
  l’agent doit être revue manuellement.
- `.github/agents/issue-triage.agent.md` contient les consignes du profil de
  triage : `needs-info` pour les issues à clarifier, `triaged` pour les demandes
  exploitables, jamais `copilot-ready` automatiquement. Le déclenchement
  automatique se configure séparément dans Copilot Automations sur GitHub;
  limiter ses outils aux commentaires, à l'édition de l'issue et aux labels.
- `run_cse_desktop_app.ps1` lance l’application avec l’interpréteur local
  `.venv/Scripts/python.exe`; `debug/debug_deploy.ps1` crée cet environnement
  et installe `requirements.txt`.

Les fichiers CSV sont généralement générés dans les dossiers `in` et `out`
propres aux flux. `services/csv_files.py` centralise leur lecture et la
sélection des fichiers d’entrée; `services/swile_service.py` gère les échanges
fichier/traitement pour le flux Swile.

## Repères — flux Swile / Active Directory

- `services/csv_files.py`
  - `read_csv` vérifie les colonnes requises et gère les fichiers CSV avec
    l’encodage `utf-8-sig`.
- `domain/matching.py`
  - Les exports Swile utilisent `;` et contiennent `Prénom`, `Nom`, `Email` et
    `Matricule`. L’export Active Directory utilise `,` et les champs `Nom`,
    `Email`, `Identifiant`, `Poste`, `Lieu de travail` (et autres colonnes
    d’enrichissement). `Identifiant` est le login avant `@` du
    `userPrincipalName` renvoyé par Microsoft Graph.
  - Le rapprochement inclut `Swile.Matricule` avec
    `Active Directory.Identifiant`, après normalisation.
  - `compare_users` compare des lignes en mémoire; l’écriture des résultats est
    prise en charge par `services/swile_service.py`.
- `domain/swile_additions.py`
  - `build_additions` applique les règles métier en mémoire; le service écrit
    les fichiers d’ajouts et d’ajouts ignorés.
  - Les filtres d’e-mail et de poste partagent `swile.config.json` avec le
    mapping des lieux. Chacun utilise `default_value` et des règles ordonnées
    `patterns` / `value` (`inclure` ou `exclure`). Les valeurs par défaut
    excluent `.ext` et les mots-clés de direction.
- `services/swile_service.py`
  - `generate_work_location_values` produit un CSV Swile d’attribut
    (`Prénom`, `Nom de famille`, `E-mail`, `Matricule`, `Valeur`) ; les
    informations d’identité viennent du CSV Swile et la valeur est déduite du
    `Lieu de travail` dans l’export Active Directory.
  - Toutes les lignes du CSV Swile sont conservées dans ce fichier (pas de
    filtre de domaine ni d’exclusion `.ext`).
  - Le mapping de lieu est lu depuis `swile.config.json` à la racine du
    projet. Les règles sont
    évaluées dans l’ordre; les termes d’un motif sont tous requis et les motifs
    d’une règle sont alternatifs. Si le fichier est absent, les valeurs
    intégrées restent Courcelles -> `Paris 145`, Wasquehal / avenue de la
    Marne -> `Lille 5.9`, Paris 133 -> `Paris 133`, sinon `Autre`.
    L’interface de l’onglet « Valeurs de lieu de travail » édite le mapping;
    les filtres d’ajouts sont dans « Comparer les listes », chacun avec une
    case pour afficher/masquer sa configuration. Le fichier partagé conserve
    mapping et filtres lors de l’enregistrement. L’ancien fichier
    `lieux_travail.config.json` est lu en repli pour faciliter la migration.
    Elle permet d’ajouter, supprimer et réordonner les motifs puis
    d’enregistrer le mapping.
    Les archives d’exécutables incluent ce fichier à la racine, à côté de
    l’application.
- `domain/normalization.py`
  - `active_directory_keys` normalise le login de `Identifiant` pour les
    rapprochements. L’export garde le login original dans `Matricule`; le nom
    complet reste une clé de rapprochement distincte.
  - Les clés de rapprochement existantes sont l’email, le matricule normalisé
    et le nom normalisé. Les ajouts filtrent les suffixes e-mail configurés,
    les doublons et les mots-clés de poste configurés; `.ext` et les postes
    de direction sont les valeurs par défaut.
- `app/ui/cse_desktop_app.py` porte les colonnes requises et les délimiteurs
  affichés par l’interface; les garder cohérents si le format d’entrée change.
  L’onglet `liste_salarie_active_directory` accepte aussi un CSV Active
  Directory précédent (glisser-déposer dans
  `liste_salarie_active_directory/in`) pour compléter le nouvel export avec les
  comptes absents mais encore visibles dans Microsoft Graph.
- `services/active_directory_export.py` lit
  `liste_salarie_active_directory.config.json`. L’interface Tkinter affiche
  les paramètres de cette configuration dans des champs éditables séparés,
  repliés par défaut quand le fichier est valide et ouverts quand la
  configuration est absente ou incomplète. Elle les place avant la zone
  facultative d’export précédent et valide les champs requis avant un
  enregistrement atomique.
  Ne jamais recopier les valeurs sensibles de cette configuration dans ce
  document ni dans les réponses.
- L’authentification Microsoft utilise le flux d’appareil MSAL. Le service
  transmet le lien et le code à l’interface Tkinter via un callback pour
  permettre la copie du code; en lancement CLI, le message MSAL reste affiché
  dans la console.
- L’export Active Directory met en cache les photos Graph existantes dans
  `liste_salarie_active_directory/out/photos`, sous le nom
  `{Identifiant}_{user-id}.jpg`; les fichiers déjà présents ne sont pas
  re-téléchargés. Leur récupération est désactivée par défaut et peut être
  activée avec la case à cocher de l’interface.
- L’export configure un journal distinct à chaque lancement dans `log/` et y
  trace les étapes de configuration, d’authentification, de collecte, de
  récupération des photos et d’écriture du CSV, ainsi que les erreurs.
- Les événements de collecte et de photo identifient le compte concerné
  (adresse, identifiant, ou ID Graph en dernier recours) pour faciliter le
  diagnostic des entrées individuelles.
- L’export Active Directory écrit chaque ligne au fur et à mesure dans un CSV
  temporaire, puis le publie sous son nom final uniquement si la collecte
  réussit; cela évite de conserver tout l’export en mémoire et de présenter un
  fichier partiel comme valide.
- `requirements.txt` liste les dépendances Python, dont `requests`, `msal` et
  `tkinterdnd2`.

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
  Les tests unitaires sont maintenant dans `tests/` et se lancent avec
  `python -m unittest discover -s tests -v`. Ils couvrent normalisation,
  rapprochements, règles d’ajout, chemins d’exécution et services CSV.
  Pour une modification Python ciblée, `python -m py_compile` sur le script
  concerné est une vérification minimale, pas un substitut à ces tests.

## Historique de contexte

- 2026-10-26 : le générateur d’ajouts inclut toujours la colonne `Matricule`,
  alimentée à partir de `Identifiant` dans l’export Active Directory. La
  comparaison normalise ce login, tandis que le fichier d’ajouts conserve sa
  valeur d’origine.
- 2026-10-26 : le projet a été déplacé hors du dossier `swile/` vers la racine
  du dépôt, puis réorganisé en packages `app`, `domain` et `services`. Les
  wrappers Python à la racine préservent les commandes de lancement existantes.
