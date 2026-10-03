# Bilans de sprints Pilotage

Chaque sprint terminé utilise les rubriques suivantes : réalisé, blocages
rencontrés, reste côté Pilotage et reste externe.

## Sprint 2 — agrégations et historique

### Réalisé

- historique quotidien et agrégats semaine/mois ;
- modes `sum`, `last`, `min`, `max`, ratio et moyenne pondérée ;
- précision décimale XOF ;
- corrections historisées par révision ;
- backfill des quatre sources principales validé en staging.

### Blocages rencontrés

- les premiers contrats ne déclaraient pas les composants des taux ;
- les montants DiddiSend sont parfois des chaînes décimales.

### Reste côté Pilotage

- aucun élément bloquant pour ce sprint.

### Reste externe

- aucun élément nécessaire à la clôture de ce sprint.

## Sprint 3 — écran Direction générale, droits et API réutilisable

### Réalisé

- vue jour, semaine et mois avec fraîcheur et périodes partielles ;
- heure d'Abidjan, état des sources et comparaisons ;
- rôles, périmètres par module et masquage des montants financiers ;
- audit des consultations financières ;
- frontend découplable et API OpenAPI consommable par Odoo ;
- authentification entrante S2S avec scopes général et financier.

### Blocages rencontrés

- le frontend et l'API étaient initialement servis par le même processus ;
- l'authentification ne gérait initialement que les utilisateurs humains.

### Reste côté Pilotage

- aucun élément bloquant pour ce sprint.

### Reste externe

- provisionner le client Odoo dans DiddiFreeID avant sa recette staging ;
- fournir le domaine définitif du frontend pour la configuration CORS.

## Sprint 4 — revenus et rapprochement financier

### Réalisé

- collecte financière DiddiGo et DiddiSend séparée des KPI opérationnels ;
- backfill de cinq jours réussi pour les deux modules ;
- vue financière réservée aux rôles autorisés ;
- historique et agrégats financiers semaine/mois ;
- audit des sources wallets et `PaymentIntent` ;
- séparation explicite entre économie métier et flux DiddiPay ;
- absence de rapprochement signalée au lieu d'afficher un faux écart nul.

### Blocages rencontrés

- DiddiPay agrège les journaux de tous les modules ;
- DiddiGo expose seulement la valeur des courses dans son résumé financier ;
- le wallet DiddiPay est legacy tandis que les ledgers DiddiGo et DiddiSend
  restent actifs et nécessaires.

### Reste côté Pilotage

- brancher automatiquement les nouveaux champs dès que les contrats externes
  sont disponibles ;
- activer le calcul d'écart par module après réception de ces dimensions.

### Reste externe

- DiddiPay : ventiler les journaux par `PaymentIntent.client_id` ;
- DiddiGo : exposer commission plateforme, revenu chauffeur et mouvements
  agrégés de son ledger chauffeur ;
- équipes Finance : valider les définitions de revenu généré, encaissé, dû et
  versé.

## Sprint 5 — granularité opérationnelle

### Réalisé

- contrat agrégé `pilotage.breakdown.v1`, sans opération brute ni donnée personnelle ;
- collecte et stockage des ventilations DiddiGo et DiddiSend ;
- agrégats semaine et mois, avec contrôle exact du total parent ;
- concurrence limitée à cinq requêtes par défaut et configurable ;
- routes de lecture, collecte groupée et backfill protégées par les droits Pilotage ;
- onglet `Analyses` pour les dimensions réellement disponibles ;
- recette staging des 29 combinaisons supportées ;
- backfill de cinq jours : 50 ventilations DiddiGo et 95 DiddiSend, aucun échec ;
- 71 tests automatisés réussis.

### Blocages rencontrés

- les premières versions staging répondaient `404` pour DiddiGo et `403` pour DiddiSend ;
- l'accès DiddiFood exige un client de service dédié ;
- aucun dépôt DiddiMap n'est disponible dans la composition locale.

### Reste côté Pilotage

- aucun élément bloquant pour les ventilations DiddiGo et DiddiSend ;
- brancher DiddiFood et DiddiMap dès que leurs contrats et accès sont fournis ;
- ajouter les revenus détaillés des participants quand les modules les exposent.

### Reste externe

- DiddiFood : fournir le client staging dédié et son contrat de ventilations ;
- DiddiMap : fournir le dépôt ou le contrat API et l'accès staging ;
- DiddiGo et DiddiSend : exposer les montants attribués, payés et dus par catégorie de participant si cette vue est souhaitée ;
- renouveler les secrets DiddiGo et DiddiSend avant la production, comme déjà planifié.

## Sprint 7 — collecte continue et écran d'accueil

### Réalisé

- collecte automatique des résumés quotidiens, finances et ventilations DiddiGo/DiddiSend ;
- cadence indépendante et configurable, fixée à 60 secondes par défaut ;
- finance et extraits ventilés ajoutés à l'accueil et à `GET /api/pilotage/overview` ;
- couverture par module exposée : résumé, finance et ventilations reçues/attendues ;
- ventilations détaillées disponibles dans l'onglet `Analyses` et par les routes API ;
- 96 tests automatisés réussis.

### Blocages rencontrés

- aucun blocage de code pour DiddiGo et DiddiSend ;
- la recette authentifiée de la nouvelle couverture dépend du redéploiement staging.

### Reste côté Pilotage

- redéployer le dernier commit puis contrôler que la couverture DiddiGo et DiddiSend atteint le nombre attendu ;
- comparer les valeurs affichées à quelques opérations métier connues ;
- terminer la recette des rôles, exports, sauvegardes et alertes d'exploitation.

### Reste externe

- DiddiFood et DiddiMap : fournir les contrats et accès nécessaires ;
- DiddiPay : fournir la ventilation par module fondée sur `PaymentIntent.client_id` ;
- effectuer la rotation planifiée des secrets exposés avant la production.
