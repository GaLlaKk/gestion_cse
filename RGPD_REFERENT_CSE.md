# Référentiel RGPD — Gestion CSE

Ce document est destiné au **référent RGPD du CSE** pour consultation interne et transmission en cas de besoin (audit, contrôle, demande de conformité).

## 1) Périmètre de l’application

L’application **Gestion CSE** sert à :
- générer un export salariés depuis Active Directory,
- comparer cet export avec les fichiers Swile,
- préparer des fichiers d’ajouts et de valeurs de lieu de travail,
- générer un export Ekie (`.xlsx`) des salariés,
- récupérer la liste des salariés via l’API Swile (POC).

Ce document couvre les traitements de données personnelles opérés par l’application dans ce périmètre.

## 2) Données personnelles traitées

### Données utilisées
- Nom / Prénom
- Adresse e-mail professionnelle
- Identifiant / matricule
- Lieu de travail (si disponible)
- Données de rapprochement entre fichiers (résultats de comparaison)
- Identifiant salarié Swile (`id`) dans le cadre du POC API (affichage UI)

### Données explicitement supprimées du périmètre (mise en conformité #49)
- **Photos des salariés** (collecte supprimée)
- **Pôle / département** (collecte supprimée)
- **Fonction / poste** (collecte et filtrage supprimés)

## 3) Finalités et minimisation

Les traitements sont limités aux finalités suivantes :
1. comparaison de listes salariés (AD vs Swile),
2. préparation des ajouts nécessaires,
3. production des valeurs de lieu de travail,
4. production de l’export salariés Ekie,
5. consultation de la liste des salariés Swile (POC API).

Principe appliqué : **minimisation des données** (article 5.1.c RGPD).  
Les données non nécessaires aux finalités (photos, pôle, fonction) ne sont plus collectées.

## 4) Base légale (à confirmer par l’organisation)

À renseigner/valider par le responsable de traitement (CSE / employeur selon organisation) :
- **Obligation légale** et/ou
- **Intérêt légitime** pour la gestion administrative des bénéficiaires CSE.

Le référent RGPD doit confirmer la base légale retenue dans le registre de traitements.

## 5) Conservation et suppression

Mesure technique en place :
- **suppression automatique des fichiers de traitement de plus de 3 mois (90 jours)** avant génération AD.

Répertoires concernés :
- `swile_active_directory/in`
- `swile_active_directory/out`
- `ekie/out`
- `liste_salarie_active_directory/in`
- `liste_salarie_active_directory/out`
- `log`

Objectif : limiter la durée de conservation opérationnelle et réduire l’exposition des données.

## 6) Mesures de sécurité (techniques et organisationnelles)

Mesures techniques déjà appliquées :
- limitation des données collectées (minimisation),
- purge automatique des fichiers anciens,
- journalisation technique de traitement,
- séparation des dossiers d’entrée/sortie,
- configuration locale des paramètres (fichiers de config),
- stockage local chiffré du `client_secret` Swile API.

Mesures organisationnelles recommandées :
- accès restreint aux dossiers de traitement (principe du moindre privilège),
- chiffrement disque poste utilisateur,
- sauvegarde maîtrisée des exports,
- interdiction d’envoi non sécurisé d’exports contenant des données personnelles.

## 7) Droits des personnes concernées

Les droits RGPD (accès, rectification, effacement, limitation, opposition selon base légale) doivent être traités via le processus interne du CSE / DPO.

Recommandation :
- centraliser les demandes dans une boîte dédiée,
- tracer date de réception, qualification, réponse et clôture.

## 8) Registre de traitement (actions référent RGPD)

Le référent RGPD doit vérifier que le registre mentionne :
- finalités exactes de l’outil,
- catégories de données réellement traitées (sans photo/pôle/fonction),
- durée de conservation (90 jours max pour fichiers de traitement),
- destinataires internes,
- mesures de sécurité en place,
- procédure de gestion des incidents.

## 9) Gestion des incidents de données

En cas de suspicion de violation :
1. isoler les fichiers/systèmes concernés,
2. qualifier les données exposées et le volume,
3. informer immédiatement le DPO / responsable,
4. documenter l’incident,
5. notifier l’autorité compétente si requis (délais légaux),
6. mettre en place les mesures correctives.

## 10) Points de contrôle opérationnels (checklist)

- [ ] Export AD sans colonnes photo/pôle/fonction
- [ ] Filtrage par poste absent de la configuration et du traitement
- [ ] Purge > 90 jours active
- [ ] Purge > 90 jours active sur `ekie/out`
- [ ] Dossiers d’export à accès restreint
- [ ] Accès restreint au fichier `swile_api.config.json`
- [ ] Registre de traitement mis à jour
- [ ] Procédure d’exercice des droits documentée
- [ ] Procédure de violation de données connue et testée

## 11) Historique de conformité (référence interne)

Mise en conformité RGPD #49 :
1. purge automatique des fichiers de traitement > 3 mois,
2. suppression de la récupération des photos,
3. suppression de la récupération du pôle,
4. suppression de la récupération de la fonction (poste),
5. suppression du filtrage basé sur les postes.
6. extension de la purge RGPD à `ekie/out` (exports `.xlsx` salariés).

---

**Document de référence interne** — à maintenir à jour à chaque évolution fonctionnelle impactant les données personnelles.
