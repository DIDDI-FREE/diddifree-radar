# DiddiFree Pilotage — plan d'implémentation par sprints

**Dépôt officiel :** `https://github.com/DIDDI-FREE/diddifree-radar.git`  
**Application :** DiddiFree Pilotage  
**Cadence proposée :** un sprint d'une semaine  
**Fuseau métier :** `Africa/Abidjan`

## Objectif de la V1

La V1 doit permettre à la Direction générale et aux responsables autorisés de comprendre rapidement :

- l'activité de DiddiFree ;
- l'évolution des utilisateurs ;
- les courses et livraisons ;
- le volume d'affaires ;
- les encaissements et remboursements ;
- le revenu de DiddiFree ;
- les revenus dus et versés aux acteurs de la plateforme ;
- les anomalies et retards de synchronisation.

Pilotage reste en lecture seule. Les opérations sensibles sont réalisées dans le Backoffice ou dans le module propriétaire.

## État au 3 octobre 2026

| Sprint | État | Résultat |
| --- | --- | --- |
| Sprint 0 | terminé | Contrats, routes, scopes et KPI identifiés |
| Sprint 1 | terminé | DiddiFreeID, DiddiGo, DiddiSend et DiddiPay collectés en staging |
| Sprint 2 | terminé | Agrégations, ratios, corrections et backfill staging validés |
| Sprint 3 | terminé | Écran Direction générale, droits et API réutilisable |
| Sprint 4 | terminé côté Pilotage | Collecte, historique et vues livrés ; rapprochement dépend de deux contrats externes |
| Sprints 5 à 7 | à faire | Granularité, alertes et déploiement |

### Fondation déjà disponible

- API FastAPI ;
- authentification humaine DiddiFreeID ;
- rôles Pilotage locaux ;
- jetons S2S DiddiFreeID ;
- collecteur périodique ;
- stockage SQLite ou PostgreSQL ;
- historique quotidien ;
- états `fresh`, `stale` et `unavailable` ;
- interface jour, semaine et mois ;
- Docker et composition staging ;
- 51 tests réussis.

### Sources déjà validées

| Source | Route | KPI collectés | État |
| --- | --- | --- | --- |
| DiddiFreeID | `/identity/v1/internal/pilotage/identity-summary` | utilisateurs, inscriptions, vérifiés, actifs, DAU, MAU | `200` staging |
| DiddiGo | `/internal/pilotage/daily-summary` | courses demandées, terminées, valeur terminée | `200` staging |
| DiddiSend | `/internal/pilotage/daily-summary` | livraisons demandées, terminées, valeur terminée | `200` staging |
| DiddiPay | `/payfund/v1/internal/pilotage/daily-summary` | captures, remboursements, frais, settlements, payouts | `200` staging |

---

## Sprint 0 — cadrage des contrats

**État : terminé**

### Livré

- séparation entre Backoffice et Pilotage ;
- modèle commun `pilotage.v1` ;
- règles de fraîcheur ;
- journée métier en heure d'Abidjan ;
- routes, audiences et scopes des premières sources ;
- distinction entre valeur métier, encaissement et revenu ;
- règle : une panne ne devient jamais un faux zéro.

### Critère de fin

Chaque KPI possède une source propriétaire, une unité, une période et une définition minimale.

---

## Sprint 1 — intégration des sources principales

**État : terminé**

### Livré

- chemins journaliers configurables ;
- audience S2S configurable par source ;
- intégration DiddiFreeID ;
- intégration DiddiGo ;
- intégration DiddiSend ;
- intégration DiddiPay ;
- enrichissement des métriques avec leur mode d'agrégation ;
- collecte indépendante : la panne d'un module ne bloque pas les autres ;
- première collecte réelle des quatre sources ;
- overview consolidé avec quatre sources `fresh`.

### Critère de fin

Les quatre sources répondent et leur dernière valeur valide est disponible dans `GET /api/pilotage/overview`.

---

## Sprint 2 — agrégations et historique fiables

**État : terminé**

**But :** garantir que les vues semaine et mois donnent des chiffres mathématiquement corrects.

### Avancement au 3 octobre 2026

- `sum`, `last`, `min` et `max` sont implémentés côté API et interface ;
- les ratios et moyennes pondérées sont recalculés depuis leurs composants déclarés ;
- les montants XOF décimaux sont additionnés avec `Decimal` côté backend ;
- les chaînes décimales sont affichées correctement dans l'interface ;
- le backfill du 28 septembre au 2 octobre a réussi pour les quatre sources ;
- les quatre routes d'historique et d'agrégats ont répondu `200` ;
- les journées provisoires, finales et corrigées sont distinguées avec un numéro de révision ;
- la première et la dernière collecte d'une journée sont conservées ;
- 51 tests passent.

La recette staging a confirmé `200` sur 20 appels : cinq journées pour chacune des quatre sources. Les routes d'historique et d'agrégats respectent le périmètre de chaque rôle ; une lecture anonyme répond `401` et un rôle sans module ou sans droit de collecte répond `403`.

### Travail backend

1. Appliquer les modes d'agrégation :
   - `sum` pour les flux ;
   - `last` pour les populations et soldes ;
   - `min` et `max` ;
   - `weighted_average` pour les moyennes ;
   - `ratio` recalculé depuis numérateur et dénominateur.
2. Conserver les montants XOF avec une précision décimale exacte.
3. Empêcher l'addition de `users_total`, DAU, MAU, soldes et taux.
4. Distinguer journées provisoires, finales et corrigées.
5. Conserver l'heure de dernière correction.
6. Effectuer le backfill des cinq derniers jours pour les quatre sources.
7. Rendre le backfill reprenable après une erreur.
8. Exposer les périodes incomplètes sans les présenter comme définitives.

### Travail interface

- afficher les XOF décimaux correctement ;
- afficher « période en cours » ;
- signaler les journées manquantes ;
- afficher la couverture, par exemple `5/7 jours disponibles`.

### Critères d'acceptation

- `users_total` mensuel correspond à la dernière valeur du mois ;
- les courses et paiements mensuels sont additionnés ;
- les montants DiddiSend gardent leurs décimales ;
- les taux ne sont jamais additionnés ;
- le changement de jour respecte `Africa/Abidjan` ;
- les cinq derniers jours sont disponibles pour chaque source prête.

### Démonstration

Afficher une journée, une semaine et un mois contenant une journée incomplète et une correction tardive.

---

## Sprint 3 — écran Direction générale et droits

**État : terminé**

**But :** rendre Pilotage compréhensible en moins d'une minute.

### Livré dans le premier lot

- bandeau avec heure d'Abidjan et nombre de sources par état ;
- libellés et descriptions métier pour les KPI principaux ;
- masquage des montants XOF pour les rôles non financiers ;
- filtrage de la page des sources selon les modules assignés ;
- indication des journées corrigées dans l'historique.
- comparaison quotidienne avec le même jour de la semaine précédente ;
- journal protégé des consultations financières ;
- affichage des liens profonds fournis par les modules.
- exécution API seule avec frontend déployable séparément ;
- contrat OpenAPI réutilisable par Odoo ;
- authentification S2S entrante avec audience `pilotage` et scopes séparés.

### Écran principal

#### Bandeau

- date et heure d'Abidjan ;
- dernière synchronisation ;
- nombre de sources fraîches, périmées et indisponibles ;
- alertes critiques.

#### Cartes Direction générale

- utilisateurs totaux, nouveaux, DAU et MAU ;
- courses demandées et terminées ;
- livraisons demandées et terminées ;
- taux de réalisation ;
- valeur des opérations terminées ;
- paiements confirmés ;
- remboursements ;
- net attendu et fonds non réglés.

#### Comparaisons

- veille ;
- même jour de la semaine précédente ;
- 7 jours précédents ;
- mois précédent.

### Droits

- `dg_global` : vue consolidée ;
- `finance_admin` : données financières ;
- `operations_manager` : activité opérationnelle ;
- `module_manager` : modules assignés ;
- `audit_read` : historique en lecture seule.

### Travail complémentaire

- ajouter les libellés métier manquants ;
- ajouter une description courte à chaque KPI ;
- masquer les données financières selon le rôle ;
- auditer les consultations financières ;
- ajouter les liens profonds vers le Backoffice.

### Critères d'acceptation

- une source indisponible ne bloque pas l'écran ;
- aucun manque de données n'est affiché comme zéro ;
- deux rôles différents voient des périmètres différents ;
- chaque carte affiche période, unité et fraîcheur ;
- l'écran fonctionne sur ordinateur et tablette.

---

## Sprint 4 — revenus et rapprochement financier

**État : terminé côté Pilotage, dépendances externes ouvertes**

**But :** séparer clairement ce que paie le client, ce que reçoit DiddiFree et ce qui revient aux participants.

### Premier lot livré

- route DiddiSend `/internal/pilotage/finance-summary` vérifiée dans le code propriétaire ;
- scope `diddisend:pilotage:finance-summary:read` vérifié ;
- collecte et stockage séparés sous le type `finance` ;
- route Pilotage `GET /api/pilotage/modules/diddisend/finance-summary` réservée aux rôles financiers ;
- recette staging `200` réussie pour le 2 octobre 2026.
- backfill financier DiddiSend de cinq jours réussi sans échec ;
- vue financière séparant économie DiddiSend et flux DiddiPay ;
- rapprochement marqué indisponible tant que DiddiPay ne fournit pas la dimension par service ;
- onglet Finance visible uniquement par la Direction générale et la Finance.
- backfill financier DiddiGo de cinq jours réussi sans échec ;
- audit confirmé : wallets métiers DiddiGo/DiddiSend actifs, wallet DiddiPay legacy ;
- découpage DiddiPay réalisable via `PaymentIntent.client_id`, mais absent de son agrégat actuel ;
- contrat financier DiddiGo encore incomplet malgré une route disponible.
- historique et agrégats financiers semaine/mois disponibles ;
- bilan détaillé consigné dans `docs/SPRINT_REPORTS.md`.

### Modèle financier cible

```text
Volume d'affaires brut
- remboursements et ajustements
= volume d'affaires net

Volume net
- revenus attribués aux participants
- frais processeur
- taxes et coûts connus
= revenu DiddiFree
```

### Travail

1. Collecter le `finance-summary` DiddiSend.
2. Définir ou obtenir la ventilation financière DiddiGo.
3. Conserver DiddiPay comme source officielle des captures, remboursements, settlements et payouts.
4. Distinguer :
   - commission générée ;
   - commission encaissée ;
   - montant dû aux participants ;
   - montant versé ;
   - montant restant à payer.
5. Ajouter les contrôles de rapprochement entre opérations métier et paiements.
6. Signaler les écarts sans les masquer.
7. Auditer l'historique DiddiPay pouvant manquer d'anciens journaux `capture`.

### Critères d'acceptation

- aucune opération économique n'est comptée deux fois ;
- chaque montant indique son propriétaire et sa définition ;
- une journée connue est rapprochée avec DiddiPay ;
- les écarts sont visibles ;
- une absence de settlement ne devient pas un encaissement nul définitif.

---

## Sprint 5 — granularité opérationnelle

**État : terminé pour DiddiGo et DiddiSend ; extensions DiddiFood et DiddiMap dépendantes des équipes externes**

**But :** permettre de comprendre où, quand et pourquoi les performances évoluent.

### Premier lot livré

- inventaire des dimensions réellement présentes dans DiddiGo, DiddiSend et DiddiFood ;
- contrat `pilotage.breakdown.v1` avec contrôle que les éléments correspondent au total ;
- interdiction des opérations brutes et données personnelles dans les ventilations ;
- chemins DiddiFood corrigés vers `/food/v1/internal/pilotage` ;
- intégration DiddiFood préparée mais non activée après un `403` staging avec le client partagé ;
- absence de dépôt DiddiMap local enregistrée comme dépendance externe.
- collecteur générique de ventilations avec validation du contrat ;
- route de lecture `GET /api/pilotage/modules/{module}/breakdown` ;
- contrôle des droits par module et validation stricte des dimensions demandées.
- matrices DiddiGo et DiddiSend alignées sur leurs contrats mis à jour ;
- agrégation locale des ventilations par semaine et mois ;
- collecte groupée de toutes les combinaisons officiellement supportées ;
- recette staging réussie après mise à jour des deux API : 10 combinaisons DiddiGo et 19 combinaisons DiddiSend ;
- backfill de cinq jours réussi : 50 ventilations DiddiGo et 95 ventilations DiddiSend, sans échec ;
- concurrence de collecte limitée et configurable pour maîtriser la charge sur les modules ;
- onglet `Analyses` avec ventilations hebdomadaires par heure, paiement, service, ville et catégorie selon le module.

### Dimensions à exposer par les modules

- heure ou tranche horaire ;
- ville et commune ;
- zone opérationnelle ;
- type de service ;
- moyen de paiement ;
- statut final ;
- catégorie de participant.

### Travail Pilotage

- définir un contrat `breakdown` agrégé ;
- collecter les ventilations sans recopier les opérations individuelles ;
- ajouter filtres et graphiques ;
- garantir que la somme des ventilations correspond au total parent ;
- masquer les regroupements trop petits si nécessaire ;
- préparer l'intégration DiddiFood ;
- préparer les indicateurs géographiques DiddiMap.

Les filtres actuellement exposés dans l'interface couvrent les dimensions livrées
par DiddiGo et DiddiSend. Les revenus détaillés des participants, DiddiFood et
DiddiMap seront ajoutés quand leurs contrats et accès seront disponibles.

### Revenus des participants

Afficher par catégorie :

- montant attribué ;
- montant payé ;
- reste à payer ;
- nombre de bénéficiaires ;
- moyenne ;
- médiane.

Le détail personnel d'un chauffeur, coursier ou restaurant appartient à DiddiFree Pro.

### Critères d'acceptation

- aucune donnée personnelle n'apparaît dans la vue DG ;
- les filtres conservent la période et le fuseau ;
- les ventilations se rapprochent du total ;
- les modules absents restent `unavailable` sans bloquer les autres.

---

## Sprint 6 — objectifs, alertes et rapports

**État : en cours**

**But :** transformer les chiffres en décisions suivies.

### Lot déjà livré

- objectifs quotidiens et mensuels versionnés, avec réalisé, écart et progression ;
- contrôle des droits financiers et par module sur les objectifs ;
- alertes persistantes de source, dédupliquées, assignables et historisées ;
- résolution automatique d'une alerte quand la source redevient saine ;
- rapports JSON quotidiens, hebdomadaires et mensuels ;
- export CSV avec couverture, fraîcheur et audit des consultations financières ;
- seuils configurables et détection des baisses, annulations, fonds en retard et écarts financiers ;
- export PDF paginé et vérifié visuellement ;
- onglet `Décisions` affichant objectifs et alertes.

### Reste du sprint

- recette staging des objectifs, alertes et rapports.

### Objectifs

- valeur cible quotidienne et mensuelle ;
- objectif par module ;
- réalisé, écart et progression ;
- historique des modifications d'objectif.

### Alertes

- source périmée ou indisponible ;
- baisse inhabituelle d'activité ;
- taux d'annulation élevé ;
- écart entre activité et encaissements ;
- fonds non réglés ;
- backlog ou composant technique dégradé.

Chaque alerte possède une gravité, un propriétaire, un statut, une échéance et un historique.

### Rapports

- rapport quotidien ;
- rapport hebdomadaire ;
- rapport mensuel ;
- export CSV ;
- export PDF ;
- audit des exports financiers.

### Critères d'acceptation

- une même anomalie n'est pas recréée toutes les 30 secondes ;
- les seuils sont configurables ;
- le rapport indique les données absentes ou périmées ;
- les exports respectent les droits.

---

## Sprint 7 — staging, recette et mise en service

**État : en cours**

**But :** rendre Pilotage exploitable durablement.

### Lot déjà livré

- CI GitHub : compilation, 87 tests et construction Docker ;
- image Docker construite et démarrée localement ;
- sondes `/health` et `/ready`, cette dernière vérifiant réellement la base ;
- composition staging validée par `docker compose config` ;
- API déployée sur `https://supervision.diddifree.com` avec PostgreSQL prêt ;
- recette publique réussie sur `/health`, `/ready`, `/openapi.json` et le frontend ;
- routes métier anonymes protégées par `401` et origines CORS inconnues refusées ;
- trois exécutions CI consécutives réussies jusqu'au commit `2be4152` ;
- variables du sprint 6 et authentification S2S propagées aux conteneurs ;
- collecte automatique toutes les 60 secondes des résumés, finances et ventilations disponibles ;
- accueil et `GET /api/pilotage/overview` enrichis avec finance, extraits ventilés et couverture reçue/attendue ;
- onglet `Analyses` et routes API conservés pour les ventilations complètes ;
- 96 tests automatisés réussis ;
- scripts de sauvegarde et restauration PostgreSQL ;
- procédure de déploiement, sauvegarde, restauration, retour arrière et rotation.

### Reste du sprint

- installer les secrets dans le coffre après réponse Auth ;
- exécuter la recette authentifiée des rôles, données, objectifs, alertes et exports ;
- configurer les sauvegardes planifiées et les alertes d'exploitation ;
- protéger `main` et obtenir la validation DG.

### Dépôt et CI

- conserver le remote `diddifree-radar.git` ;
- pousser la branche `main` ;
- ajouter lint, tests et construction Docker dans la CI ;
- protéger la branche principale selon les règles de l'équipe.

### Déploiement

- PostgreSQL staging ;
- conteneur API ;
- conteneur collecteur ;
- domaine Pilotage ;
- CORS et JWKS DiddiFreeID ;
- variables et secrets dans le coffre ;
- sauvegarde et restauration ;
- logs et alertes d'exploitation ;
- procédure de retour arrière.

### Recette métier

- comparer chaque KPI à des opérations connues ;
- vérifier une opération créée avant minuit et terminée après minuit ;
- vérifier remboursement partiel et correction tardive ;
- vérifier journée vide et panne de source ;
- vérifier tous les rôles ;
- vérifier jour, semaine et mois.

### Sécurité avant mise en service

- renouveler les secrets Pilotage DiddiGo et DiddiSend ;
- mettre à jour le coffre ;
- redéployer ;
- confirmer les nouveaux jetons ;
- vérifier qu'aucun secret n'est présent dans Git ou les logs.

### Critères de mise en service

- quatre sources validées avec des données connues ;
- agrégations approuvées ;
- rôles approuvés ;
- sauvegarde et retour arrière documentés ;
- rotation terminée ;
- Direction générale valide le premier écran.

---

## Ordre d'exécution immédiat

1. Sprint 6 : objectifs, alertes et rapports.
2. Préparer DiddiFood et DiddiMap comme nouvelles sources dès réception des accès.
3. Sprint 7 : déploiement et recette.
4. Brancher les compléments DiddiPay et DiddiGo dès livraison externe.

## Définition de terminé

Un élément est terminé lorsque :

- le contrat métier est documenté ;
- le code est versionné ;
- les états d'erreur sont gérés ;
- les tests pertinents passent ;
- une recette staging utilise des données connues ;
- la documentation d'exploitation est mise à jour ;
- la démonstration du sprint est acceptée.
