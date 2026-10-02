"""Monthly and client summaries for printing, without issuing invoices."""
from html import escape
from datetime import date
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, Spacer
from sales_journal import _pdf
from sales_insights_pdf import section, money, NOTE

def profit_pdf(result,start,end,settings=None):
    styles=getSampleStyleSheet()
    rows=[['Ventes après remises',result['revenue']],['Coût des articles vendus',result['cost']],
          ['Marge brute',result['gross']],['Dépenses de fonctionnement',result['operating']],
          ['Commissions',result['commissions']],['Bénéfice net estimé',result['net']],
          ['Achats et règlements de stock (hors charges)',result['stock_payments']]]
    story=section('Bilan du bénéfice (FCFA)',['Indicateur','Montant'],[[label,money(value)] for label,value in rows],[340,190])
    story += [Spacer(1,10),Paragraph('Résultat = ventes après remises - coût des articles vendus - dépenses de fonctionnement - commissions. Les achats de stock et règlements fournisseurs ne sont pas déduits une seconde fois. Les ventes à crédit sont incluses ; ce résultat n’est pas le solde de caisse.',styles['Normal'])]
    story += [Spacer(1,8),Paragraph(f'Situation calculée au {date.today():%d/%m/%Y}. Le résultat dépend des coûts et charges enregistrés ; les corrections et retours peuvent modifier une ancienne période.',styles['Normal'])]
    if result['estimated']:
        story += [Spacer(1,8),Paragraph(f"{result['estimated']} ligne(s) sans coût historique utilisent le prix d’achat actuel.",styles['Normal'])]
    story += section('Dépenses et traitement',['Date','Libellé','Montant (FCFA)','Traitement'],[[str(r['Date'])[:10],r['Libellé'],money(r['Montant']),r['Traitement']] for _,r in result['expenses'].iterrows()],[70,180,100,180])
    return _pdf('Bilan et bénéfice de la boutique',f'Du {start:%d/%m/%Y} au {end:%d/%m/%Y}',story,settings)

def monthly_pdf(data,settings=None):
    profit=data['profit'];start,end=data['start'],data['end'];styles=getSampleStyleSheet()
    rows=[['Ventes',profit['revenue']],['Coût des produits vendus',profit['cost']],['Bénéfice brut',profit['gross']],
          ['Charges d’exploitation',profit['operating']],['Commissions',profit['commissions']],['Bénéfice net estimé',profit['net']],
          ['Achats / règlements de stock (hors charges)',profit['stock_payments']],['Objectif de ventes',data['goal']],
          ['Créances clients actuelles, toutes périodes',data['debt_total']]]
    story=section('Bilan (FCFA)',['Indicateur','Montant'],[[label,money(value)] for label,value in rows],[340,190])
    story += [Spacer(1,8),Paragraph(f"Situation calculée au {data['as_of']:%d/%m/%Y}. Les créances sont une situation actuelle, pas le solde à la fin du mois choisi.",styles['Normal']),Spacer(1,8),Paragraph('Le bénéfice net est une estimation à partir des coûts enregistrés, charges et commissions. Les achats de stock sont exclus des charges pour éviter de compter deux fois le coût des marchandises.',styles['Normal'])]
    if profit['estimated']: story += [Paragraph(f"{profit['estimated']} ligne(s) utilisent le coût d’achat actuel faute de coût historique.",styles['Normal'])]
    story += section('Produits vendus',['Produit','Quantité','Ventes (FCFA)'],[[r.Produit,r.Quantité,money(r.Ventes)] for r in data['top'].itertuples(index=False)],[300,80,150])
    story += section('Stock sans vente sur ce mois',['Produit','Stock actuel'],[[r.Produit,r.Stock] for r in data['unsold'].itertuples(index=False)],[380,150])
    expenses=profit['expenses']
    story += section('Dépenses du mois',['Libellé','Montant (FCFA)','Traitement'],[[r['Libellé'],money(r['Montant']),r['Traitement']] for _,r in expenses.iterrows()],[230,100,200])
    story += section('Impayés actuels',['Client','Vente','Reste (FCFA)','Échéance'],[[r['Client'],r['N°'],money(r['Reste']),r['Échéance']] for _,r in data['debts'].iterrows()],[250,50,130,100])
    return _pdf('Bilan mensuel',f'Du {start:%d/%m/%Y} au {end:%d/%m/%Y}',story,settings)

def client_pdf(profile,settings=None):
    client=profile['client'];styles=getSampleStyleSheet()
    story=[Paragraph(f'Situation au {date.today():%d/%m/%Y}',styles['Normal'])]
    for label,key in [('Téléphone','phone'),('E-mail','email'),('Adresse','address')]:
        if client.get(key): story.append(Paragraph(escape(f'{label} : {client[key]}'),styles['Normal']))
    story += section('Situation (FCFA)',['Indicateur','Montant'],[['Achats',money(profile['total'])],['Reste à payer',money(profile['debt'])],['Avoir disponible',money(client.get('store_credit') or 0)]],[330,200])
    story += [Spacer(1,8),Paragraph(escape(NOTE),styles['Normal'])]
    story += section('Achats',['Vente','Date','Total','Payé','Reste'],[[r['id'],str(r['created_at'])[:10],money(r['total']),money(r['paid']),money(max(float(r['total'])-float(r['paid']),0))] for r in profile['sales']],[50,100,130,130,120])
    story += section('Paiements',['Date','Vente','Montant','Mode','Origine'],[[str(r['Date'])[:10],r['Vente'],money(r['Montant']),r['Mode'],r['Origine']] for r in profile['payments']],[100,50,100,120,160])
    story += section('Factures archivées',['Numéro','Date'],[[r['number'],str(r['created_at'])[:10]] for r in profile['invoices']],[330,200])
    story += section('Autres documents',['Numéro','Type','Total','Statut'],[[r['id'],r['document_type'],money(r['total']),r['status']] for r in profile['documents']],[60,160,140,170])
    return _pdf('Fiche client - relevé de situation',str(client['name']),story,settings)
