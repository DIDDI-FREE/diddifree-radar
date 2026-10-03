# Pilotage - exploitation staging

## Déploiement

1. Utiliser un commit identifié de la branche `main`.
2. Copier `.env.example` vers un fichier d'environnement situé hors de Git.
3. Renseigner PostgreSQL, OIDC, CORS et les secrets S2S depuis le coffre.
   Utiliser `PILOTAGE_OIDC_ISSUER=diddifree-id`; les jetons humains n'ont pas
   d'audience. Définir le périmètre des consommateurs S2S dans
   `PILOTAGE_TRUSTED_SERVICE_MODULES_JSON`.
   Le port hôte par défaut est `38090`; il reste modifiable avec
   `PILOTAGE_HTTP_PORT` si ce port est déjà utilisé sur le serveur.
4. Valider la composition :

   ```bash
   docker compose --env-file /chemin/secret/pilotage.env -f docker-compose.staging.yml config --quiet
   ```

5. Construire sans modifier les services actifs :

   ```bash
   docker compose --env-file /chemin/secret/pilotage.env -f docker-compose.staging.yml build
   ```

6. Créer une sauvegarde, puis démarrer :

   ```bash
   docker compose --env-file /chemin/secret/pilotage.env -f docker-compose.staging.yml up -d
   ```

7. Vérifier `/health`, `/ready`, puis exécuter la recette du sprint 6.

## Sauvegarde

Avec `POSTGRES_DB` et `POSTGRES_USER` chargés dans l'environnement :

```bash
python scripts/postgres_backup.py --output-dir /var/backups/pilotage
```

Conserver les sauvegardes chiffrées hors du serveur et tester régulièrement
leur restauration sur une base isolée.

## Restauration

La restauration remplace le contenu de la base ciblée. Arrêter l'API et le
collecteur, vérifier le fichier, puis confirmer explicitement le nom de base :

```bash
docker compose -f docker-compose.staging.yml stop api collector
python scripts/postgres_restore.py /var/backups/pilotage/pilotage-YYYYMMDDTHHMMSSZ.dump --confirm-database pilotage
docker compose -f docker-compose.staging.yml start api collector
```

Vérifier ensuite `/ready`, les sources, un rapport connu et le journal des
accès financiers.

## Retour arrière applicatif

1. Ne pas restaurer la base si aucune migration incompatible n'a été appliquée.
2. Revenir au tag ou au SHA précédent de l'image.
3. Redémarrer `api` et `collector` avec la même configuration.
4. Vérifier `/ready` et les routes de lecture.
5. Restaurer la base uniquement si une migration de données l'exige.

## Rotation des secrets

1. Générer le nouveau secret dans DiddiFreeID.
2. Ajouter le secret au coffre staging.
3. Redéployer Pilotage.
4. Vérifier l'obtention des jetons et les collectes.
5. Révoquer l'ancien secret.
6. Confirmer qu'aucun secret n'apparaît dans Git ou les logs.
