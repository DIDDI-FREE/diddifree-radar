# Audit des API sources Pilotage — 5 octobre 2026

Cet audit compare les routes réellement déclarées dans les services avec les
collectes de Pilotage. Les dépôts sources ont été lus sans modification.

## DiddiFreeID

- Route : `GET /identity/v1/internal/pilotage/identity-summary`.
- Audience : `diddifree-id`.
- Scope : `identity:reporting:read`.
- Données disponibles : utilisateurs totaux, inscrits du jour, vérifiés,
  comptes au statut actif, utilisateurs actifs quotidiens et mensuels.
- État Pilotage : collecte quotidienne déjà branchée.

`users_active` désigne les comptes dont le statut est `active`.
`daily_active_users` et `monthly_active_users` reposent sur la table d'activité
quotidienne et mesurent donc une activité observée.

## DiddiGo

- Routes : `daily-summary`, `finance-summary`, `breakdown` et `health-summary`
  sous `/internal/pilotage`.
- Données quotidiennes : courses demandées, courses terminées et montant final
  des courses terminées.
- Finance actuelle : uniquement le montant final des courses terminées.
- Ventilations : heure, moyen de paiement, type de service et statut final,
  selon une matrice de 10 combinaisons.
- État Pilotage : résumé, finance et toutes les ventilations sont collectés.
- Manque externe : commission plateforme, revenu chauffeur et mouvements du
  ledger chauffeur ne sont pas encore exposés dans le résumé financier.

## DiddiSend

- Routes : `daily-summary`, `finance-summary`, `breakdown` et `health-summary`
  sous `/internal/pilotage`.
- Données quotidiennes : livraisons demandées, livraisons terminées et valeur
  finale des livraisons terminées.
- Finance : valeur brute, paiements numériques, cash collecté, cash à reverser,
  cash reversé, reste dû, commission plateforme, gains coursier, part partenaire,
  anomalies et cash en retard.
- Ventilations : heure, paiement, service, statut, villes de départ et d'arrivée,
  et catégorie de participant, selon une matrice de 19 combinaisons.
- État Pilotage : résumé, finance et toutes les ventilations sont collectés.

## DiddiPay

- Routes : `daily-summary`, `health-summary` et `capabilities` sous
  `/payfund/v1/internal/pilotage`.
- Scope : `diddipay:payment-summary:read`.
- Données : paiements confirmés, remboursements, frais processeur, delta net,
  settlements, créance non rapprochée et payouts.
- Source métier : journaux financiers confirmés. Les wallets historiques ne
  sont pas nécessaires pour ces chiffres.
- État Pilotage : résumé quotidien déjà collecté.
- Manque externe : aucune ventilation par `PaymentIntent.client_id`; Pilotage
  ne peut donc pas rapprocher proprement DiddiGo, DiddiSend et DiddiFood avec
  les totaux DiddiPay.

## DiddiFood

- Routes : `daily-summary`, `finance-summary` et `health-summary` sous
  `/food/v1/internal/pilotage`.
- Audience : `diddifood`.
- Scope : `food:pilotage:read`.
- Client attendu côté DiddiFood : `pilotage-staging-diddifood` en staging.
- Données quotidiennes : commandes placées, acceptées, prêtes, récupérées,
  livrées et annulées, restaurants actifs, livraisons demandées/livrées et
  retard de synchronisation DiddiSend.
- Finance : commandes et livraisons en XOF, commission DiddiFood, revenu net
  restaurants, soldes wallets restaurants, retraits, frais fournisseur et
  anomalies de rapprochement.
- État Pilotage avant cet audit : source déclarée mais absente des modules
  activés par défaut et de la collecte financière automatique.
- Correction Pilotage : activation par défaut et ajout à la collecte financière
  automatique. DiddiFood ne fournit pas encore de route de ventilation.

## Ce que Pilotage peut afficher après déploiement

- Accueil : les cinq modules, leurs KPI quotidiens et leur couverture réelle.
- Finance : DiddiGo, DiddiSend et DiddiFood pour les rôles financiers.
- Analyses ventilées : DiddiGo et DiddiSend.
- Utilisateurs : totaux, inscriptions et activité via DiddiFreeID.
- Paiements : flux confirmés et rapprochement global via DiddiPay.

## Reste à fournir par les services

1. DiddiPay : ventilation par `PaymentIntent.client_id` avec au minimum les
   montants capturés, remboursés, frais, settlements et payouts.
2. DiddiGo : commission plateforme et gains chauffeur agrégés.
3. DiddiFood : une route `breakdown` si les analyses par restaurant, statut,
   paiement, zone ou service sont requises.
4. Les quatre services qui exposent `health-summary` : Pilotage doit encore
   collecter et présenter ces états techniques dans une vue d'exploitation.
5. DiddiMap et DiddiFiles : contrats Pilotage dédiés à confirmer avant leur
   activation.
