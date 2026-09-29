# Supprimer un produit

Avec un compte administrateur, ouvrir **Produits et stock → Supprimer un produit**.
Sélectionner le produit, vérifier la quantité affichée, indiquer le motif,
cocher la confirmation puis cliquer sur **Supprimer le produit**.

La suppression retire définitivement la fiche et son stock. Pour retirer
seulement quelques unités, utiliser **Retirer** dans la modification du stock.

Un produit lié à des ventes, devis, factures, commandes, retours, inventaires,
transferts, lots ou variantes ne peut pas être supprimé. Le stock présent
dans une autre boutique bloque également la suppression. Ces vérifications
préservent les historiques. Une quantité modifiée exige une nouvelle confirmation.

Le nom, la référence, la quantité et le motif sont enregistrés dans le journal.
Sur Supabase, si cette écriture échoue après la suppression, un avertissement
signale que le produit a été supprimé mais que le journal n'a pas pu être mis à jour.
Les photos stockées ne sont pas effacées et aucune migration Supabase n'est requise.

Tests : `python -m unittest test_product_management` et
`python test_product_management_ui.py` (Streamlit requis).
