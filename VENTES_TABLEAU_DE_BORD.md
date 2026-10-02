# Ventes, factures et tableau de bord

Dans **Historique** et **Factures des ventes**, recherchez un client (sans tenir compte des accents) ou un numéro de vente. Combinez cette recherche avec les filtres de paiement : payée, partiellement payée ou non payée, mode de paiement et vendeur. Les documents déjà émis restent conservés dans les archives.

La page Factures permet d’exporter en CSV la liste filtrée, avec son état et son reste à payer. Sélectionnez ensuite une vente pour utiliser le circuit habituel d’émission de facture.

Dans **Accueil → Analyser les ventes sur une période**, choisissez les dates pour afficher le chiffre d’affaires, les tickets, le panier moyen, les ventes quotidiennes et la répartition par vendeur et paiement. Les jours sans vente apparaissent avec zéro. La comparaison utilise la période précédente de même durée. Ces analyses sont aussi présentes dans le tableau de bord propriétaire. Un export CSV des ventes quotidiennes est disponible.

Les montants payés et restes reflètent l’état actuel des ventes de la période, avec leurs paiements complémentaires. Ils ne constituent pas un relevé des encaissements effectués durant cette période. Utilisez les écrans de caisse journalière et paiements pour ces mouvements. Le chiffre d’affaires repose sur les totaux actuels des ventes, après les corrections et retours enregistrés.

Les rapports de ventes et dépenses Supabase chargent maintenant toutes les pages de résultats, avec des limites de dates appliquées à la requête et un tri stable.

Validation : 7 tests automatiques de filtres, calculs, périodes, pagination de 1 201 ventes et interaction Streamlit. Les suites existantes de facturation, gestion quotidienne et stockage cloud passent également. La validation utilise des données de test, sans modifier les données de production.
