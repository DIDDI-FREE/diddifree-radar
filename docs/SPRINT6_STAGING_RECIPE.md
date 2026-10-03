# Recette staging du sprint 6

Cette recette est en lecture seule. Elle vérifie les objectifs, les alertes et
les rapports JSON, CSV et PDF sans modifier les données Pilotage.

## Préconditions

- API Pilotage déployée avec le commit du sprint 6 ;
- URL publique de l'API ;
- jeton DiddiFreeID d'un utilisateur `dg_global` de recette ;
- au moins une journée collectée.

Le jeton doit être placé dans une variable d'environnement et ne doit jamais
être écrit dans la commande, les logs ou Git.

```powershell
$env:PILOTAGE_RECIPE_TOKEN = '<jeton temporaire>'
python scripts/verify_sprint6_staging.py `
  --base-url 'https://<api-pilotage-staging>' `
  --anchor '2026-10-03'
```

La recette réussit lorsque les six contrôles affichent `200` et que le
processus termine avec le code `0`. Il faut ensuite supprimer la variable
d'environnement et vérifier manuellement dans l'interface :

1. l'onglet `Décisions` ;
2. le périmètre d'un `module_manager` ;
3. le masquage des montants pour `operations_manager` ;
4. l'historique après acquittement d'une alerte de test ;
5. l'audit d'un export financier.
