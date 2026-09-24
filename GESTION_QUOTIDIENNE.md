# Gestion quotidienne

Cette version complète les écrans existants, sans nouvelle migration Supabase.

- **Ventes → Retours et échanges** : motif obligatoire, remboursement ou avoir limité au trop-perçu après réduction de la dette, remise répartie proportionnellement sur les articles conservés et remise en stock. L'échange se fait en deux opérations : retour avec remboursement, puis nouvelle vente. Un avoir exige un client enregistré. Les retours de variantes, de plusieurs lignes d'un même produit ou d'autres boutiques sont refusés pour éviter de corriger le mauvais stock.
- **Ventes → Caisse journalière** : ouverture avec fonds initial, mouvements exceptionnels motivés, montant attendu, montant compté, justification des écarts et historique exportable. La caisse est commune aux vendeurs. La clôture est un constat, elle ne bloque pas les ventes ultérieures ; une différence ultérieure est signalée. Une ouverture/clôture par jour utilise un identifiant déterministe pour prévenir les doubles enregistrements.
- **Ventes → Paiements par mode** : espèces, Wave, Orange Money, carte ; recettes, sorties et net séparés. Les paiements tardifs sont datés du règlement. Les remboursements ne sont pas comptés une seconde fois dans les mouvements. Les règlements fournisseurs ne doublonnent pas leurs dépenses associées. Les dépenses doivent recevoir un mode de paiement ; sinon la clôture est bloquée.
- **Stock → À commander** : alertes de rupture et de seuil, suggestions de quantités et commandes fournisseur, fonctionnalité existante conservée.
- **Tableau de bord → Bénéfice** : chiffre d'affaires après remises, coût des articles, charges, commissions et résultat estimé, fonctionnalité existante conservée. La commission est ajustée lors d'un retour. Il ne s'agit pas du solde de caisse.
- **Stock → Inventaire** : comptage physique, correction du stock et historique ; motif obligatoire en cas d'écart.
- **Stock → Codes-barres et impressions** : accès au centre d'impression existant et aux étiquettes. La lecture avec un lecteur ou la caméra reste dans Nouvelle vente.
- **Clients → Relances WhatsApp** : dettes échues, destinataire et message modifiables, confirmation avant ouverture de WhatsApp ; aucun message n'est envoyé automatiquement.

## Précisions
Le journal reconstitue les encaissements initiaux depuis les ventes et leurs règlements/retours. Des corrections manuelles ou d'anciens retours enregistrés avant cette version peuvent nécessiter un rapprochement avec les reçus. Les montants rendus en monnaie sur les nouvelles ventes ne sont plus enregistrés comme chiffre encaissé. Pour un acompte, choisir son véritable moyen de paiement ; « Credit » correspond à une vente entièrement à crédit.

La clôture est réservée à l'administrateur et concerne une caisse commune. Les dépenses payées sur un moyen extérieur peuvent être classées « Hors caisse ». Ne pas saisir à nouveau les ventes, dépenses ou remboursements comme mouvements exceptionnels.

Les opérations de retour sur Supabase utilisent les appels existants et ne constituent pas une transaction unique. En cas d'interruption réseau, contrôler la vente, le stock et l'historique avant de reprendre. Les avoirs sont conservés sur la fiche client ; cette version n'ajoute pas leur utilisation automatique comme moyen de paiement.

## Tests
`test_daily_operations.py` vérifie les dates d'encaissement, les différents moyens de paiement, les remboursements, la dette, les avoirs, la caisse, les relances et les calculs de l'adaptateur distant simulé.
`test_daily_ui.py` vérifie les huit accès, l'ouverture/clôture, la confirmation WhatsApp et les restrictions vendeur via Streamlit AppTest.
Les tests utilisent des données fictives et aucun compte de production.
