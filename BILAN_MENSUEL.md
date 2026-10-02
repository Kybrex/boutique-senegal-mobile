# Bilan, objectifs, produits et clients

## Bilan et objectifs

Ouvrez **Tableau de bord → Bilan et objectifs** et choisissez une date du mois à consulter. L’écran affiche les ventes, le bénéfice brut et le bénéfice net estimé, avec le détail des coûts, charges et commissions. Les achats ou règlements de marchandises restent séparés des charges, car les coûts des produits vendus sont déjà déduits.

Définissez un objectif de chiffre d’affaires pour chaque mois. Il est conservé dans le journal de configuration existant, pour SQLite et Supabase, et inclus dans les sauvegardes. Un objectif de zéro désactive le suivi pour ce mois. La progression peut dépasser 100 %, tandis que la barre s’arrête à 100 %.

Le coût historique enregistré dans les lignes de vente est utilisé pour la rentabilité. Une indication apparaît si certaines lignes nécessitent le prix d’achat actuel. Le bilan constitue une estimation de gestion à partir des opérations enregistrées ; les corrections et retours peuvent modifier les chiffres d’un ancien mois.

## Produits vendus et sans vente

Le classement indique les quantités restantes après retours et le chiffre d’affaires réparti proportionnellement après remises. Les produits archivés ayant été vendus restent dans l’historique. La liste sans vente comprend uniquement les produits actifs avec du stock actuel positif dans les boutiques et aucune quantité vendue restante sur le mois. Les nouveaux produits peuvent donc y figurer. Les deux listes s’exportent en CSV.

## Fiche client et relances

Dans **Clients → Fiche complète**, les achats, paiements, dettes et documents existants sont complétés par un relevé PDF imprimable et un export CSV des achats. Le relevé ne remplace pas les factures originales archivées.

Dans **Clients → Relances WhatsApp**, choisissez une relance par vente échue ou **Par client : tous les impayés**. La relance regroupée utilise le solde actuel du client et peut inclure des ventes non encore échues. Vérifiez le destinataire, le solde et le message avant d’ouvrir WhatsApp. Modifier le téléphone ou le texte impose une nouvelle vérification. L’application prépare le message ; l’utilisateur confirme lui-même son envoi dans WhatsApp.

## Bilan mensuel PDF

Le bouton du bilan exporte les ventes, coûts, charges, commissions, résultat estimé, objectif, produits vendus, stock sans vente, dépenses et impayés. Les créances et le stock représentent la situation actuelle, même pour un ancien mois. Le document est daté, comporte le logo et les coordonnées, et peut être imprimé depuis le lecteur PDF.

Les nouvelles fonctions sont réservées aux administrateurs. Aucune migration SQL n’est nécessaire.

Validation : 25 tests passent, dont 13 nouveaux tests de périodes, objectifs, autorisations, rentabilité, produits, retours, données cloud simulées, PDF et interactions Streamlit. Les suites existantes de facturation, gestion quotidienne et stockage cloud passent aussi. Les PDF de contrôle ont été rendus et vérifiés visuellement. Les tests utilisent des données isolées.
