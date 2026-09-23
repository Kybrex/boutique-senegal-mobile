# Nouveautés : documents et suivi quotidien

- **Verrouillage** : retour à la connexion après 5 minutes d'inactivité par défaut. Le délai se règle entre 1 et 60 minutes dans Réglages → Sécurité des comptes. Le bouton « Verrouiller maintenant » est dans la barre latérale. Les formulaires non enregistrés et les fichiers préparés de la session sont effacés. Les événements d'activité ne lisent ni les touches ni le contenu des champs.
- **Factures émises** : à la première émission, conservation des PDF A4 et A5, des coordonnées et des lignes de la facture. Les téléchargements suivants rendent les mêmes octets. Une modification de vente ne remplace pas l'original. Accès dans Facturation → Factures émises. Les factures téléchargées avant cette version ne peuvent pas être reconstituées rétroactivement à l'identique.
- **WhatsApp** : téléchargement du PDF, choix du destinataire et du texte, confirmation puis ouverture de WhatsApp. L'utilisateur joint le PDF et confirme l'envoi dans WhatsApp. Aucun envoi automatique ni lien public vers les fichiers.
- **Justificatifs** : Achats → Justificatifs. PDF, JPG ou PNG de 5 Mo maximum, associés à une dépense (y compris les achats reçus) ou à une commande fournisseur.
- **Fiche client** : Clients → Fiche complète. Achats, paiements initiaux et ultérieurs, dettes, devis et originaux des factures du client. Les règlements ultérieurs ne sont pas comptés deux fois.
- **Sauvegardes** : les copies complètes incluent les documents privés. Dates distinctes pour copie préparée, conservation confirmée par l'utilisateur, contrôle d'un fichier et copie automatique vérifiée. Le rappel est de 7 jours par défaut, réglable dans Sécurité des comptes. La préparation seule n'est pas une preuve de conservation sur l'appareil.

## Stockage et accès
Les nouveaux écrans de documents et de suivi sont réservés à l'administrateur. Les métadonnées utilisent les événements persistants existants. Les fichiers sont conservés comme objets JSON privés dans le compartiment Supabase existant `automatic-backups`, sous `documents-v1/`. Le code refuse un compartiment public, n'écrase pas les originaux et contrôle leur empreinte SHA-256. La configuration V4 doit déjà avoir créé ce compartiment privé. En local, les fichiers se trouvent à côté de la base SQLite, dans `private_documents/`.

## Sauvegarde et récupération
Les anciens fichiers sans documents privés restent acceptés. Une sauvegarde qui référence des documents mais omet leurs contenus est refusée. La récupération ajoute les objets et les données manquants et refuse d'écraser un original différent. Elle n'efface pas les données actuelles et ne remplace pas une base existante. Les opérations distantes peuvent être partiellement réalisées si la connexion est interrompue.

Les sauvegardes automatiques sont déclenchées à l'ouverture d'une session administrateur lorsque la fréquence est dépassée, et non par une tâche exécutée en permanence. Les objets stockés sont relus avant de marquer la copie comme contrôlée. Une vérification de fichier contrôle la structure et les empreintes, sans garantir à elle seule une restauration opérationnelle. Limites : copie automatique 48 Mo, export/import manuel 100 Mo.

## Validation
- `python test_workflows.py` : base SQLite et fichiers temporaires, immutabilité, autorisations, pièces jointes, calculs clients, préparation WhatsApp, sauvegarde/récupération.
- `python test_cloud_workflows.py` : adaptateur distant simulé, écriture sans remplacement, stockage privé, erreurs et pagination.
- `python test_workflow_ui.py` : Streamlit AppTest sur données fictives, connexion, écrans, verrouillage, rôle vendeur, archives A5 et confirmation WhatsApp.
- `node test_idle_guard.mjs` : minuterie et nettoyage du composant navigateur.
Les tests ne se connectent pas à Supabase et ne lisent aucun secret de production.
