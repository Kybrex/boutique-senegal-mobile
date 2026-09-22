# Gestion quotidienne de la boutique

- **Facturation** : les factures des ventes portent un numéro stable, le montant payé, le solde et l’état du paiement. Une échéance peut être définie. Les identifiants NINEA et RCCM se renseignent dans Réglages → Boutique ; aucune valeur fictive n’est enregistrée.
- **Recherche** : recherche par nom, téléphone, code-barres ou numéro de facture depuis le haut de l’écran administrateur, sans distinction d’accents.
- **Clients → Impayés et échéances** et **Fournisseurs → Sommes à payer** : total des dettes, retards, export et dates de paiement. L’échéance fournisseur est indépendante de la livraison prévue.
- **Stock → À commander** : suggestions calculées sur les ventes des 30 derniers jours, le minimum de stock et les commandes non encore reçues. Les quantités et coûts sont modifiables avant de créer un bon de commande. La création ne réceptionne pas les produits.
- **Tableau de bord → Bénéfice** : ventes après remises, coût enregistré des produits vendus, charges et commissions. Les achats de marchandises et règlements fournisseurs ne sont pas soustraits une seconde fois. Le résultat est estimatif et dépend des coûts et charges saisis ; il est distinct de la trésorerie.
- **Réglages → Sauvegarder et récupérer** : archive complète, contrôle du fichier et récupération des enregistrements manquants après authentification administrateur. La récupération ne remplace pas les enregistrements existants et ne constitue pas un retour intégral à une date antérieure.

Les coordonnées en pied de page et le logo sont conservés. Les nouveaux paramètres de facturation et échéances fournisseurs sont conservés dans les événements de configuration du journal existant et inclus dans les sauvegardes. Aucune migration de schéma supplémentaire n’est requise.

## Vérifications

Tests sur une base SQLite isolée : navigation des nouveaux écrans, restrictions vendeurs, recherche, factures sans création de vente supplémentaire, paiements partiels, échéances, calcul du bénéfice après remises, absence de double déduction des achats, commandes sans réception immédiate et sauvegarde/récupération sans doublon. Tests simulés du stockage distant : pagination et remontée des erreurs. Le PDF de facture enrichi a été inspecté visuellement.

La connexion et les écritures dans la base Supabase de production ne sont pas utilisées par les tests.

