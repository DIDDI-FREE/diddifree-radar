# Contrat de ventilation Pilotage v1

Route source cible :

```text
GET /internal/pilotage/breakdown?date=YYYY-MM-DD&dimension=payment_method&metric=rides_completed
```

Pour DiddiFood, le préfixe reste `/food/v1/internal/pilotage`.

## Réponse

```json
{
  "contract_version": "pilotage.breakdown.v1",
  "module": "diddigo",
  "date": "2026-10-03",
  "timezone": "Africa/Abidjan",
  "dimension": "payment_method",
  "metric": "rides_completed",
  "unit": "count",
  "total": 10,
  "items": [
    {"key": "cash", "label": "Espèces", "value": 6},
    {"key": "wave", "label": "Wave", "value": 4}
  ],
  "is_final": true,
  "calculated_at": "2026-10-04T00:00:00Z"
}
```

## Règles

- la somme des éléments correspond exactement à `total` ;
- aucune opération ni donnée personnelle n'est retournée ;
- une clé inconnue reste visible et n'est pas transformée en `other` par Pilotage ;
- les montants XOF conservent leur précision décimale ;
- une dimension indisponible répond `404` ou une erreur contractuelle, jamais un faux tableau vide ;
- les regroupements de personnes doivent rester des catégories métier agrégées.

## Dimensions proposées

| Dimension | DiddiGo | DiddiSend | DiddiFood |
| --- | --- | --- | --- |
| `hour` | création/fin course | création/fin livraison | commande/livraison |
| `payment_method` | disponible dans le modèle | disponible dans le modèle | disponible dans le modèle |
| `service_type` | catégorie véhicule | type de livraison | retrait/livraison |
| `city` | à confirmer | ville pickup/dropoff | adresse de livraison à normaliser |
| `zone` | modèle en cours | aucune zone canonique confirmée | quartiers configurés, à normaliser |
| `final_status` | disponible | disponible | disponible |
| `participant_category` | chauffeur | coursier/partenaire | restaurant/coursier |

La géographie doit utiliser des identifiants canoniques DiddiMap lorsqu'ils
seront disponibles. Les textes libres d'adresse ne doivent pas devenir des
dimensions de reporting.
