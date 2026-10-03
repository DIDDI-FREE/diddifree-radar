# API Pilotage pour les consommateurs internes

Pilotage expose un read model central. Odoo et les autres consommateurs lisent
ce modèle via HTTP et ne contactent pas directement DiddiGo, DiddiSend,
DiddiPay ou DiddiFreeID.

## Base et contrat

- préfixe : `/api/pilotage` ;
- contrat machine : `/openapi.json` ;
- santé : `/health` ;
- fuseau métier : `Africa/Abidjan` ;
- montants : unité `XOF`, parfois sérialisés comme chaîne décimale exacte ;
- données manquantes : absentes ou `unavailable`, jamais transformées en zéro.

## Routes de lecture

- `GET /overview` : dernière vue consolidée autorisée ;
- `GET /modules/{module}/daily-summary?date=YYYY-MM-DD` ;
- `GET /modules/{module}/history?days=30` ;
- `GET /modules/{module}/aggregates?period=week&count=8` ;
- `GET /sources` : fraîcheur des sources autorisées.

Les réponses portent `X-Request-ID`. Un consommateur doit le conserver dans
ses journaux pour faciliter le diagnostic.

## Authentification Odoo

Créer dans DiddiFreeID un client de service propre à Odoo, destiné à
`pilotage`. Le contrat cible utilise :

- audience : `pilotage` ;
- scope opérationnel : `pilotage:read` ;
- scope financier séparé : `pilotage:finance:read` ;
- `X-Client-ID` strictement identique au `client_id` du jeton.

L'acceptation entrante de ces jetons doit être activée seulement après
provisionnement du client et validation en staging. Les secrets restent dans
le coffre du déploiement Odoo.
