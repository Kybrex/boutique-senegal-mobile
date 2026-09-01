# Boutique Senegal

Application de gestion de magasin en FCFA: caisse, ticket, stock, vendeurs, depenses et rapports.

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
3. Avant une utilisation reelle, configurez une base de donnees cloud. SQLite locale ne conserve pas de facon fiable les ventes et les stocks sur l'hebergement en ligne.
