# Gestion des produits

Les nouveaux outils sont accessibles avec un compte administrateur dans
**Produits et stock**, sur mobile et ordinateur.

## Archiver et restaurer

Dans **Archiver ou restaurer un produit**, choisir la liste des produits actifs,
sélectionner le produit, saisir le motif et confirmer l’archivage. La fiche est
masquée dans les listes opérationnelles, la caisse, la recherche par code-barres,
les alertes de stock faible et les nouveaux catalogues. Les quantités, variantes,
ventes, retours et justificatifs restent conservés. Un panier déjà préparé est
revérifié à son enregistrement ; les ventes hors connexion sont également
refusées à la synchronisation si elles contiennent un produit archivé.

Choisir **Produits archivés** pour restaurer une fiche. Les quantités conservées
redeviennent visibles. Un retour ou une réception sur une ancienne commande
peut encore modifier le stock archivé. La valorisation du stock propriétaire
inclut toujours ces quantités physiques.

Les catalogues déjà téléchargés restent inchangés. Au rechargement d’un catalogue
enregistré, les produits archivés sont exclus de la nouvelle sélection.

## Modifier une fiche et éviter les doublons

**Modifier le nom et la catégorie** conserve la référence du produit et journalise
l’ancien et le nouveau nom. Les listes et les documents régénérés utilisent le
nom actuel ; les copies de factures déjà archivées restent inchangées.

À la création, les noms identiques après normalisation des accents, de la casse,
des espaces et de la ponctuation sont refusés. Les noms proches sont signalés
et demandent de confirmer qu’il s’agit d’un produit distinct. Les fiches archivées
sont aussi vérifiées. L’import ignore un produit archivé ou une variation de nom
équivalente ; il ne restaure pas implicitement une fiche.

## Mouvements de stock

Choisir **Définir**, **Ajouter** ou **Retirer**. Toute diminution demande un motif :
**Casse**, **Perte**, **Don**, **Usage personnel**, **Correction d’inventaire** ou
**Autre**. Le motif **Autre** demande une précision. La quantité avant et après,
le motif et le compte administrateur sont enregistrés. Un stock négatif ou une
quantité devenue obsolète sont refusés. Les mouvements concernent le stock
principal ; les transferts entre boutiques conservent leur écran dédié.

## Historique par produit

Sélectionner un produit actif ou archivé puis cliquer sur
**Afficher / actualiser l’historique**. Le tableau exportable en CSV réunit les
ventes initiales, retours, inventaires, transferts, achats reçus, réceptions et
changements de fiche ou de statut. Les sorties sont négatives et les entrées
positives ; un transfert n’est pas une variation du stock total.

Les anciens achats non reliés à une référence et les quantités initiales non
journalisées ne sont pas inventés. Les anciennes réceptions sans dates détaillées
sont indiquées comme cumul ancien. Il s’agit d’un historique des informations
disponibles, pas d’une reconstitution exhaustive du solde.

## Conservation et limites techniques

L’état d’archivage et les nouveaux événements sont stockés intégralement dans le
journal existant et inclus dans les sauvegardes. Aucune nouvelle migration SQL
n’est nécessaire. La suppression définitive est refusée après un mouvement de
stock journalisé ; utiliser l’archivage pour conserver cet historique.

En local, modifications et journal sont transactionnels. Sur Supabase, certains
traitements utilisent plusieurs requêtes : une écriture réussie suivie d’une
erreur de journalisation ou de synchronisation affiche un avertissement distinct
et demande de vérifier l’état, sans répéter l’opération. La vérification d’archivage
précède la RPC de vente cloud ; elle n’est pas un verrou serveur entre sessions.

Validation : tests SQLite isolés, adaptateur Supabase simulé, tests Streamlit des
formulaires et tests de non-régression. Les tests ne modifient aucune donnée réelle.
