"""Shared sales exploration for mobile and owner pages."""
import streamlit as st
import db
import sales_insights as insights

def fcfa(value):
    return f'{value:,.0f} FCFA'.replace(',', ' ')

def filters(sales, key):
    search = st.text_input('Rechercher un client ou un numéro de vente', key=f'{key}_search')
    state = st.selectbox('État du paiement', insights.STATES, key=f'{key}_state')
    method = st.selectbox('Mode de paiement', ['Tous'] + sorted(sales.Paiement.dropna().astype(str).unique()) if not sales.empty else ['Tous'], key=f'{key}_method')
    seller = st.selectbox('Vendeur', ['Tous'] + sorted(sales.Vendeur.dropna().astype(str).unique()) if not sales.empty else ['Tous'], key=f'{key}_seller')
    result = insights.filter_sales(sales, search, state, method, seller)
    st.caption(f'{len(result)} vente(s) trouvée(s)')
    return result

def dashboard(start, end, key):
    previous_start, previous_end = insights.previous_period(start, end)
    current = insights.summarize(db.report(start, end), start, end)
    previous = insights.summarize(db.report(previous_start, previous_end), previous_start, previous_end)
    a, b = st.columns(2)
    a.metric('Chiffre d’affaires', fcfa(current['total']), delta=fcfa(current['total'] - previous['total']))
    b.metric('Tickets', current['tickets'], delta=current['tickets'] - previous['tickets'])
    st.caption(f'Comparaison avec le {previous_start:%d/%m/%Y} au {previous_end:%d/%m/%Y}, de même durée.')
    a, b = st.columns(2)
    a.metric('Panier moyen', fcfa(current['average']))
    b.metric('Reste sur ces ventes', fcfa(current['remaining']))
    st.caption('Le reste et les montants payés reflètent l’état actuel des ventes sélectionnées, y compris les paiements complémentaires. Ils ne représentent pas les mouvements de caisse de la période.')
    st.subheader('Évolution quotidienne des ventes')
    st.line_chart(current['daily'], y_label='FCFA')
    st.subheader('Répartition par mode de paiement')
    st.dataframe(current['payments'], hide_index=True, width='stretch')
    st.subheader('Ventes par vendeur')
    st.dataframe(current['sellers'], hide_index=True, width='stretch')
    st.download_button('Exporter les ventes quotidiennes', current['daily'].to_csv().encode('utf-8-sig'), file_name=f'ventes_quotidiennes_{start}_{end}.csv', mime='text/csv', key=f'{key}_export')
