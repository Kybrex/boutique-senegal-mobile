"""Daily management screens, restricted to administrators."""
from datetime import date
import streamlit as st
import db
import v3_db as v3
import business_features as f
import daily_operations as ops
from workflow_service import whatsapp_url

def money(value):
    return f'{float(value):,.0f} FCFA'.replace(',',' ')

def payments_page(user):
    f.require_admin(user)
    st.header('Encaissements et décaissements')
    period=st.date_input('Période des paiements',value=(date.today().replace(day=1),date.today()))
    if len(period)!=2:
        st.info('Sélectionnez deux dates.')
        return
    rows=ops.journal(*period)
    st.dataframe(ops.totals(rows),hide_index=True)
    st.caption('Les règlements clients sont datés du paiement. Les remboursements, dépenses et règlements fournisseurs sont séparés des ventes. Le crédit non encaissé ne constitue pas une entrée.')
    st.caption('Les anciennes ventes modifiées ou les anciens retours peuvent nécessiter un rapprochement avec les reçus. « Hors caisse » désigne les dépenses payées en dehors des moyens suivis.')
    chosen=st.selectbox('Filtrer par mode',['Tous']+ops.METHODS+['Avoir','Hors caisse','À préciser'])
    shown=rows if chosen=='Tous' else rows[rows.Paiement==chosen]
    st.dataframe(shown,hide_index=True)
    st.download_button('Exporter le journal',shown.to_csv(index=False).encode('utf-8-sig'),file_name='journal_paiements.csv',mime='text/csv')
    expense_panel(user,rows)

def expense_panel(user,rows):
    expenses=rows[(rows.Origine=='Dépense')]
    if expenses.empty:
        return
    with st.expander('Préciser le paiement d’une dépense'):
        label=st.selectbox('Dépense',expenses['Référence'].tolist())
        identifier=int(label.split('#',1)[1].split(' · ',1)[0])
        mode=st.selectbox('Mode utilisé',ops.METHODS+['Hors caisse'])
        if st.button('Enregistrer le mode'):
            ops.classify_expense(identifier,mode,user)
            st.rerun()

def cash_page(user):
    f.require_admin(user)
    st.header('Caisse journalière')
    day=st.date_input('Journée de caisse',value=date.today())
    openings=ops.opened(day)
    closings=ops.closed(day)
    st.caption('Caisse commune à tous les vendeurs. Le fonds initial est le montant physiquement présent avant les ventes. Une clôture conserve un constat ; elle ne bloque pas les ventes ultérieures.')
    if not openings and not closings and day==date.today():
        with st.form('daily_open'):
            amount=st.number_input('Fonds initial en espèces',min_value=0.0,step=500.0)
            if st.form_submit_button('Ouvrir la caisse'):
                try:
                    ops.open_day(day,float(amount),user)
                    st.rerun()
                except ValueError as error:
                    st.error(str(error))
    rows=ops.journal(day,day)
    summary=ops.totals(rows)
    st.dataframe(summary,hide_index=True)
    expected=float(summary.set_index('Paiement').loc['Especes','Net'])
    st.metric('Espèces attendues',money(expected))
    unknown=(rows.Paiement=='À préciser').any()
    if unknown:
        st.warning('Des paiements restent à préciser avant de clôturer.')
    expense_panel(user,rows)
    if closings:
        saved=closings[-1]
        st.success('Clôture enregistrée pour cette journée.')
        st.metric('Espèces comptées à la clôture',money(saved['counted_cash']))
        st.metric('Écart constaté',money(saved['difference']))
        if abs(expected-float(saved['expected_cash']))>.005:
            st.warning('Des opérations ont changé depuis la clôture. Consultez le journal ; la clôture historique reste inchangée.')
    elif openings:
        with st.form('daily_close'):
            counted=st.number_input('Espèces réellement comptées',min_value=0.0,step=500.0)
            notes=st.text_area('Justification de l’écart / observations')
            if st.form_submit_button('Clôturer la journée',disabled=bool(unknown)):
                try:
                    ops.close_day(day,float(counted),notes,user)
                    st.rerun()
                except ValueError as error:
                    st.error(str(error))
        with st.form('daily_movement'):
            kind=st.selectbox('Mouvement exceptionnel',['ENTREE','SORTIE'])
            amount=st.number_input('Montant en espèces',min_value=1.0,step=500.0)
            label=st.text_input('Motif du mouvement')
            st.caption('Ne ressaisissez pas une vente, une dépense ou un remboursement déjà enregistré.')
            if st.form_submit_button('Enregistrer le mouvement'):
                if not label.strip():
                    st.error('Indiquez un motif.')
                elif ops.closed(day):
                    st.error('Cette caisse est déjà clôturée.')
                else:
                    v3.add_cash_movement(day,kind,float(amount),label,int(user['id']))
                    st.rerun()
    elif day!=date.today():
        st.info('Aucune ouverture enregistrée pour cette journée.')
    st.subheader('Journal de la journée')
    st.dataframe(rows,hide_index=True)
    st.subheader('Historique des clôtures')
    history=db.cash_closings()
    st.dataframe(history,hide_index=True)
    st.download_button('Exporter les clôtures',history.to_csv(index=False).encode('utf-8-sig'),file_name='clotures.csv',mime='text/csv')

def reminders_page(user):
    f.require_admin(user)
    st.header('Relances clients')
    debts=f.debt_rows('clients')
    due=debts[debts.Situation.isin(['À échéance','En retard'])]
    if due.empty:
        st.success('Aucune dette arrivée à échéance.')
        return
    st.dataframe(due,hide_index=True)
    labels={f"#{int(r['N°'])} · {r['Client']} · {money(r['Reste'])}":int(r['N°']) for _,r in due.iterrows()}
    identifier=labels[st.selectbox('Facture à relancer',list(labels))]
    try:
        phone,message=ops.reminder(identifier,user)
    except ValueError as error:
        st.info(str(error))
        return
    phone=st.text_input('Téléphone WhatsApp',value=phone,key=f'remind_phone_{identifier}')
    message=st.text_area('Message à vérifier',value=message,max_chars=2000,key=f'remind_text_{identifier}')
    if st.checkbox('J’ai vérifié le destinataire et le message',key=f'remind_confirm_{identifier}_{phone}_{message}'):
        try:
            st.link_button('Ouvrir WhatsApp',whatsapp_url(phone,message))
        except ValueError as error:
            st.error(str(error))
    st.caption('WhatsApp s’ouvre avec le texte préparé. Vous confirmez vous-même l’envoi.')
