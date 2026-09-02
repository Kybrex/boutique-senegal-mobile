# Boutique Senegal

Application de gestion de magasin en FCFA : caisse, tickets PDF/WhatsApp, stock,
codes-barres, crédits clients, clôture de caisse, vendeurs, inventaires,
multi-boutiques, dépenses, sauvegardes et rapports.

## Lancer sur Windows

    python -m pip install -r requirements.txt
    streamlit run app.py

Les donnees sont enregistrees localement dans `boutique.db`. Pour l'hebergement en ligne durable, il faudra connecter une base de donnees cloud avant la mise en production.

## Version iPhone

La version adaptee a l'iPhone est `iphone_app.py` :

    streamlit run iphone_app.py

## Publication sur Streamlit Community Cloud

1. Creez un depot GitHub avec ce dossier (la base locale `boutique.db` est volontairement exclue).
2. Dans Streamlit Community Cloud, choisissez le depot, la branche `main` et le fichier `iphone_app.py`.
3. Configurez les secrets `SUPABASE_URL` et `SUPABASE_KEY` dans Streamlit Cloud.
4. Dans Supabase → SQL Editor, exécutez entièrement `supabase_schema.sql`. Le
   script est réexécutable et ajoute la migration V2 sans effacer les données.
5. Redémarrez l'application Streamlit.

## Modules V2

- remboursements et historique des crédits clients ;
- clôture quotidienne par vendeur et par mode de paiement ;
- saisie ou scan caméra des codes-barres ;
- tickets personnalisés HTML/PDF et partage WhatsApp ;
- alertes de rupture et quantités de réapprovisionnement suggérées ;
- tableau de bord des ventes, bénéfices, dépenses, produits et vendeurs ;
- activation des comptes, réinitialisation des mots de passe et journal d'activité ;
- sauvegarde ZIP (CSV + JSON relationnel) et restauration sécurisée par fusion ;
- inventaire physique avec correction et historique des écarts ;
- boutiques multiples, stocks séparés et transferts.
- échéances de crédits avec alertes automatiques à J-5, 24 h et après retard ;
- fiche d'inventaire PDF A4 prête à imprimer et remplir ;
- photos de produits importées depuis la galerie ou l'appareil photo du téléphone.
