# Ventes, factures et tableau de bord

Dans **Historique** et **Factures des ventes**, recherchez un client (sans tenir compte des accents) ou un numéro de vente. Combinez cette recherche avec les filtres de paiement : payée, partiellement payée ou non payée, mode de paiement et vendeur. Les documents déjà émis restent conservés dans les archives.

La page Factures permet d’exporter en CSV la liste filtrée, avec son état et son reste à payer. Sélectionnez ensuite une vente pour utiliser le circuit habituel d’émission de facture.

Dans **Accueil → Analyser les ventes sur une période**, choisissez les dates pour afficher le chiffre d’affaires, les tickets, le panier moyen, les ventes quotidiennes et la répartition par vendeur et paiement. Les jours sans vente apparaissent avec zéro. La comparaison utilise la période précédente de même durée. Ces analyses sont aussi présentes dans le tableau de bord propriétaire. Un export CSV des ventes quotidiennes est disponible.

Les montants payés et restes reflètent l’état actuel des ventes de la période, avec leurs paiements complémentaires. Ils ne constituent pas un relevé des encaissements effectués durant cette période. Utilisez les écrans de caisse journalière et paiements pour ces mouvements. Le chiffre d’affaires repose sur les totaux actuels des ventes, après les corrections et retours enregistrés.

Les rapports de ventes et dépenses Supabase chargent maintenant toutes les pages de résultats, avec des limites de dates appliquées à la requête et un tri stable.

## Imprimer et exporter en PDF

Les écrans Historique, Rapports et Factures proposent **Imprimer / exporter les ventes en PDF**. Le document reprend uniquement les ventes actuellement sélectionnées, la période, les filtres, les totaux, les montants payés, les restes et l’état de paiement. La liste de facturation est un relevé des ventes ; chaque facture individuelle reste émise et archivée par le circuit habituel.

Les analyses de l’accueil et du tableau de bord propriétaire disposent de **Imprimer / exporter le tableau de bord en PDF**, avec les indicateurs, la comparaison de périodes, le graphique quotidien et les répartitions par paiement et vendeur.

Téléchargez le PDF, ouvrez-le puis choisissez **Imprimer** : Ctrl+P sur ordinateur, ou Partager → Imprimer sur iPhone. Pour les factures individuelles archivées, choisissez le format A4 ou A5 puis imprimez à taille réelle. Les documents comportent le logo, les coordonnées de la boutique, la pagination et des en-têtes répétés sur les longues listes.

Validation PDF : 5 tests supplémentaires couvrent les listes filtrées, les périodes comparées, les données vides, les longues listes et les boutons Streamlit. Les exemples de contrôle ont aussi été rendus en images et vérifiés visuellement.

Validation : 7 tests automatiques de filtres, calculs, périodes, pagination de 1 201 ventes et interaction Streamlit. Les suites existantes de facturation, gestion quotidienne et stockage cloud passent également. La validation utilise des données de test, sans modifier les données de production.
