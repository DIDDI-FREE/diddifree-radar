# Audit des sources financières Pilotage

## Principe retenu

Le suivi actuel doit partir des `PaymentIntent` DiddiPay et des ledgers métiers
de chaque module. Le wallet utilisateur historique DiddiPay reste hors du
calcul des nouveaux paiements de services.

## DiddiPay

Le modèle actif est `payments.payment_intents`. Chaque intention porte un
`client_id` et une `business_reference`. Le journal financier référence le
`payment_intent_id`, ce qui permet techniquement de regrouper captures,
remboursements, frais et settlements par client émetteur.

L'agrégat Pilotage actuel interroge seulement `financial_journals` et ne joint
pas `payment_intents`. Il retourne donc des totaux globaux. DiddiPay doit
ajouter une ventilation par `PaymentIntent.client_id` ou un filtre `service`.

Les tables et routes du wallet DiddiPay sont legacy. Elles restent utiles pour
l'audit des anciens soldes et certains flux DiddiFund, mais ne doivent pas
alimenter les revenus courants DiddiGo ou DiddiSend.

## DiddiGo

DiddiGo possède un wallet chauffeur et un ledger actifs. Les mouvements
confirmés incluent notamment :

- recharge chauffeur via un `PaymentIntent` ;
- débit de commission plateforme pour une course cash ;
- crédit du revenu chauffeur pour une course numérique réussie.

La route `/internal/pilotage/finance-summary` existe, mais elle ne renvoie que
`completed_fare_total_xof`. Elle doit également agréger au minimum la
commission plateforme, le revenu chauffeur, les recharges, les soldes dus et
les mouvements cash pertinents depuis le ledger chauffeur.

## DiddiSend

DiddiSend possède des wallets coursier et partenaire, un ledger, des
settlements par livraison et des reversements. Sa route
`/internal/pilotage/finance-summary` expose déjà valeur brute, commission,
revenus coursiers, part partenaires, espèces à reverser, reversements et
retards. C'est actuellement le contrat financier métier le plus complet.

## Rapprochement cible

Pour une date et un module :

1. le module propriétaire fournit la valeur métier et sa ventilation ;
2. DiddiPay fournit les captures et remboursements des `PaymentIntent` du
   `client_id` correspondant ;
3. les paiements cash restent issus du module métier ;
4. Pilotage compare les deux sources et montre l'écart ;
5. aucun wallet legacy DiddiPay n'est inclus dans ce calcul.
