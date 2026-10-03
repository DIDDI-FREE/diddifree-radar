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
