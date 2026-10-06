# Brief — robot DiddiPay vers Odoo

Date : 2026-10-06

## Décision d'intégration

Le robot Odoo doit lire une API DiddiPay dédiée en authentification S2S. Il ne
doit pas accéder directement à la base DiddiPay. L'API permet de stabiliser les
définitions comptables, de filtrer les données sensibles, de journaliser les
lectures et de faire évoluer le schéma interne sans casser Odoo.

La route globale existante est :

```http
GET /payfund/v1/internal/pilotage/daily-summary?date=YYYY-MM-DD
```

Elle expose captures, remboursements, frais processeur, settlements et payouts,
mais sans ventilation par service, processeur ou type métier. Elle reste utile
pour contrôler le total général, mais elle ne suffit pas pour l'écriture Odoo.

## Données déjà disponibles dans DiddiPay

- `PaymentIntent.client_id` : service propriétaire, par exemple DiddiGo,
  DiddiSend ou DiddiFood ;
- `PaymentIntent.business_reference` et `metadata` : référence métier ;
- `PaymentAttempt.processor`, `channel` et `network` : processeur et canal ;
- `FinancialJournal.event_type` : `capture`, `refund`, `processor_fee`,
  `settlement` ou `payout` ;
- `Payout.client_id`, `processor`, `beneficiary_reference` et `metadata` ;
- montants XOF et dates comptables des journaux financiers.

Les journaux financiers peuvent être reliés soit à un `PaymentIntent`, soit à
un `Payout`. La ventilation par service et processeur est donc dérivable dans
DiddiPay.

## Information à normaliser

DiddiPay ne possède pas encore un champ stable permettant de distinguer chaque
type d'opération métier. Les préfixes de `business_reference` peuvent aider à
migrer l'historique, mais ne doivent pas devenir le contrat permanent.

Chaque création de PaymentIntent ou de payout doit fournir dans `metadata` :

```json
{
  "owner_module": "diddisend",
  "operation_type": "courier_wallet_topup",
  "business_object_type": "wallet_topup",
  "business_object_id": "...",
  "participant_type": "courier"
}
```

Valeurs initiales de `operation_type` :

- `ride_payment` ;
- `delivery_payment` ;
- `food_order_payment` ;
- `driver_wallet_topup` ;
- `courier_wallet_topup` ;
- `restaurant_wallet_topup` si ce flux existe ;
- `driver_payout` ;
- `courier_payout` ;
- `partner_payout` ;
- `restaurant_payout` ;
- `refund` ;
- `other`, avec justification explicite.

## Nouvelle route recommandée

```http
GET /payfund/v1/internal/accounting/daily-export?date=2026-10-06
Authorization: Bearer <service token>
X-Client-ID: odoo-staging-diddipay
```

Audience recommandée : `diddipay`.

Scope recommandé :

```text
diddipay:accounting-export:read
```

Le client Odoo doit être distinct du client Pilotage.

## Réponse proposée

```json
{
  "contract_version": "diddipay.accounting.daily.v1",
  "date": "2026-10-06",
  "timezone": "Africa/Abidjan",
  "currency": "XOF",
  "is_final": false,
  "revision": 1,
  "calculated_at": "2026-10-06T12:00:00Z",
  "totals": {
    "captures_xof": 150000,
    "refunds_xof": 5000,
    "processor_fees_xof": 2500,
    "settlements_xof": 130000,
    "payouts_xof": 70000
  },
  "by_service": [
    {
      "service": "diddisend",
      "captures_xof": 60000,
      "refunds_xof": 0,
      "processor_fees_xof": 1000,
      "settlements_xof": 50000,
      "payouts_xof": 25000
    }
  ],
  "by_processor": [
    {
      "processor": "paystack",
      "channel": "mobile_money",
      "network": "wave",
      "captures_xof": 90000,
      "refunds_xof": 5000,
      "processor_fees_xof": 1500,
      "settlements_xof": 80000,
      "payouts_xof": 40000
    }
  ],
  "by_operation_type": [
    {
      "service": "diddisend",
      "operation_type": "courier_wallet_topup",
      "captures_count": 4,
      "captures_xof": 20000,
      "refunds_xof": 0
    },
    {
      "service": "diddisend",
      "operation_type": "delivery_payment",
      "captures_count": 12,
      "captures_xof": 40000,
      "refunds_xof": 0
    }
  ],
  "participant_payouts": [
    {
      "service": "diddisend",
      "participant_type": "courier",
      "payouts_count": 6,
      "payouts_xof": 18000
    }
  ],
  "controls": {
    "unclassified_operations_count": 0,
    "unclassified_operations_xof": 0,
    "missing_processor_count": 0
  }
}
```

## Séparations obligatoires

Le contrat ne doit jamais fusionner :

- top-ups et paiements de courses/livraisons/commandes ;
- captures et settlements reçus du processeur ;
- revenus gagnés et payouts effectivement versés ;
- remboursements et annulations métier ;
- frais processeur et commission DiddiFree ;
- montants bruts, montants nets et soldes instantanés de wallet.

## Part des chauffeurs, livreurs et autres participants

DiddiPay connaît le montant d'un payout réussi. Il ne connaît pas nécessairement
le montant économique gagné, dû ou encore disponible avant payout.

Il faut conserver deux familles de faits :

1. **Économie métier**, fournie par DiddiGo, DiddiSend et DiddiFood : valeur
   brute, commission plateforme, part participant gagnée, montant dû et solde ;
2. **Mouvement financier**, fourni par DiddiPay : capture, remboursement,
   settlement, frais processeur et payout effectivement exécuté.

Le robot Odoo rapproche les deux familles avec `service`, `operation_type`,
`business_object_id` et les références de payout. Il ne doit pas reconstruire
la part participant à partir du montant payé par le client.

## Ventilations supplémentaires recommandées

- par devise, même si la V1 est XOF ;
- par statut final ;
- par canal et réseau mobile money ;
- par type de participant ;
- par type d'opération ;
- par service propriétaire ;
- par processeur ;
- par journée de capture, remboursement, settlement et payout ;
- opérations non classées et anomalies de rapprochement.

## Exigences pour Odoo

- export stable et versionné ;
- montants en entiers XOF ;
- pagination si des lignes détaillées sont ajoutées ;
- `revision` ou empreinte permettant de rejouer une journée corrigée ;
- clé d'idempotence d'import : `contract_version + date + revision` ;
- aucune donnée personnelle ;
- historique d'accès ;
- une indisponibilité doit produire une erreur, jamais des totaux artificiellement nuls ;
- possibilité de relire une journée historique après correction tardive.

## Migration de l'historique

Pour les anciens PaymentIntents sans `operation_type`, DiddiPay peut effectuer
une classification transitoire à partir de `client_id`, `business_reference`
et `metadata`. Toute opération non déterministe doit rester dans `other` et
alimenter `unclassified_operations_count` au lieu d'être classée arbitrairement.

