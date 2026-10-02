"""Admin monthly management and client exports."""
from datetime import date
from hashlib import sha256
import pandas as pd
import streamlit as st
import db
import business_features as features
import monthly_management as management
import monthly_management_pdf as pdf
import workflow_service as workflows
from sales_insights_ui import fcfa,print_help

def monthly_page(user):
    features.require_admin(user)
    st.header('Bilan et objectifs mensuels')
    chosen=st.date_input('Mois à consulter',value=date.today().replace(day=1),key='monthly_chosen')
    data=management.monthly_snapshot(chosen);profit=data['profit'];month=data['start']
    st.caption(f"Du {month:%d/%m/%Y} au {data['end']:%d/%m/%Y}")
    with st.container(horizontal=True):
        st.metric('Ventes',fcfa(profit['revenue']))
        st.metric('Bénéfice brut',fcfa(profit['gross']))
        st.metric('Bénéfice net estimé',fcfa(profit['net']))
    st.caption('Bénéfice net = ventes − coût des produits vendus − charges d’exploitation − commissions. Les achats de stock sont suivis séparément.')
    if profit['estimated']: st.warning(f"{profit['estimated']} ligne(s) utilisent le prix d’achat actuel faute de coût historique.")
    with st.expander('Détail de la rentabilité'):
        st.dataframe(pd.DataFrame([{'Indicateur':label,'FCFA':profit[field]} for label,field in [('Coût des produits vendus','cost'),('Charges d’exploitation','operating'),('Commissions','commissions'),('Achats et règlements de stock','stock_payments')]]),hide_index=True)
    st.subheader('Objectif du mois')
    progress=management.goal_progress(profit['revenue'],data['goal'])
    if data['goal']>0:
        st.progress(progress['ratio'],text=f"{progress['percent']:.1f} % de l’objectif de {fcfa(data['goal'])}")
        st.metric('Ventes restantes pour atteindre l’objectif',fcfa(progress['remaining']))
    else: st.info('Aucun objectif défini pour ce mois.')
    with st.form(f'goal_{month:%Y_%m}'):
        amount=st.number_input('Objectif de chiffre d’affaires (FCFA)',min_value=0.0,value=data['goal'],step=10000.0)
        if st.form_submit_button('Enregistrer l’objectif'):
            management.save_goal(month,amount,user);st.rerun()
    st.subheader('Produits les plus vendus')
    st.caption('Quantités nettes des retours. Les remises sont réparties proportionnellement entre les produits. Le stock affiché est le stock actuel de toutes les boutiques.')
    st.dataframe(data['top'],hide_index=True,width='stretch')
    st.subheader('Produits en stock sans vente sur ce mois')
    st.caption('Produits actifs avec un stock positif et aucune quantité vendue restante sur la période. Les nouveaux produits peuvent aussi apparaître.')
    st.dataframe(data['unsold'],hide_index=True,width='stretch')
    st.download_button('Exporter les produits vendus en CSV',data['top'].to_csv(index=False).encode('utf-8-sig'),file_name=f'produits_vendus_{month:%Y-%m}.csv',mime='text/csv')
    st.download_button('Exporter les invendus en CSV',data['unsold'].to_csv(index=False).encode('utf-8-sig'),file_name=f'invendus_{month:%Y-%m}.csv',mime='text/csv')
    st.subheader('Créances clients actuelles')
    st.metric('Total restant, toutes périodes',fcfa(data['debt_total']))
    st.caption('Situation actuelle : ce montant ne reconstitue pas les créances à la fin du mois choisi.')
    st.dataframe(data['debts'],hide_index=True,width='stretch')
    st.download_button('Imprimer / exporter le bilan mensuel en PDF',pdf.monthly_pdf(data,db.get_settings()),file_name=f'bilan_mensuel_{month:%Y-%m}.pdf',mime='application/pdf')
    print_help()
    a,b=st.columns(2)
    if a.button('Consulter une fiche client'): st.session_state.mobile_page='Fiche client';st.rerun()
    if b.button('Préparer une relance WhatsApp'): st.session_state.mobile_page='Relances';st.rerun()

def client_actions(profile,user):
    features.require_admin(user)
    identifier=int(profile['client']['id'])
    st.download_button('Imprimer / exporter la fiche client en PDF',pdf.client_pdf(profile,db.get_settings()),file_name=f'fiche_client_{identifier}.pdf',mime='application/pdf',key=f'client_profile_pdf_{identifier}')
    print_help()
    st.download_button('Exporter les achats du client en CSV',pd.DataFrame(profile['sales']).to_csv(index=False).encode('utf-8-sig'),file_name=f'achats_client_{identifier}.csv',mime='text/csv',key=f'client_sales_csv_{identifier}')
    if profile['debt']<=.005: return
    with st.expander('Préparer une relance regroupée pour ce client'):
        phone,message=management.client_reminder(identifier,user)
        version=sha256(message.encode()).hexdigest()[:12]
        phone=st.text_input('Téléphone WhatsApp du client',value=phone,key=f'client_phone_{identifier}_{version}')
        message=st.text_area('Message de relance à vérifier',value=message,max_chars=2000,key=f'client_message_{identifier}_{version}')
        verified=sha256((phone+message).encode()).hexdigest()[:12]
        if st.checkbox('J’ai vérifié le client, le solde et le message',key=f'client_confirm_{identifier}_{verified}'):
            try: st.link_button('Ouvrir WhatsApp avec la relance',workflows.whatsapp_url(phone,message))
            except ValueError as error: st.error(str(error))
        st.caption('Aucun envoi automatique. La relance regroupe tous les impayés du client, y compris ceux dont l’échéance n’est pas dépassée. Vous confirmez l’envoi dans WhatsApp.')

def grouped_reminders(user):
    features.require_admin(user)
    identifiers={r.get('client_id') for r in features.records('sales') if float(r['total'])-float(r['paid'])>.005}
    clients=[r for r in features.records('clients') if r['id'] in identifiers]
    if not clients:
        st.success('Aucun client avec un impayé.');return
    selected=st.selectbox('Client à relancer',sorted(clients,key=lambda r:r['name'].casefold()),format_func=lambda r:f"{r['name']} · #{r['id']}")
    profile=workflows.client_profile(selected['id'],user)
    st.metric('Solde total du client',fcfa(profile['debt']))
    client_actions(profile,user)
