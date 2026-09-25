"""Configure and download a customer catalogue without changing sale prices."""
from datetime import date, timedelta
import hashlib
import json
import logging
import pandas as pd
import streamlit as st
from catalog_options import prepare_catalog, whatsapp_number, reference
from v4_pdf import make_catalog_pdf


def catalog_panel(products, settings):
    st.caption('Composez votre catalogue avec photos, références, promotions et commande WhatsApp.')
    only_stock = st.checkbox('Uniquement les produits en stock', value=True, key='catalog_stock')
    available = products[products.Stock > 0].copy() if only_stock and not products.empty else products.copy()
    if available.empty:
        st.info('Aucun produit disponible pour ce catalogue.')
        return
    available['Categorie'] = available.Categorie.fillna('').replace('', 'Autres produits')
    categories = sorted(available.Categorie.unique())
    chosen = st.multiselect('Catégories à inclure', categories, default=categories, key='catalog_categories')
    available = available[available.Categorie.isin(chosen)]
    labels = {int(r.id): f'{r.Produit} (réf. {reference(r)})' for _, r in available.iterrows()}
    selected = st.multiselect('Produits à inclure', list(labels), default=list(labels), format_func=labels.get, key='catalog_products')
    selected_products = available[available.id.isin(selected)].copy()
    phone = st.text_input('Numéro WhatsApp pour les commandes', value=str(settings.get('phone') or ''), key='catalog_whatsapp', help='Un numéro sénégalais de 9 chiffres reçoit automatiquement l’indicatif +221. Pour un autre pays, renseignez son indicatif.')
    expiry = st.date_input('Prix valables jusqu’au', value=date.today() + timedelta(days=30), min_value=date.today(), key='catalog_expiry')
    st.caption('Les promotions ci-dessous concernent ce PDF. Elles ne changent pas les prix enregistrés en caisse.')
    edited = st.data_editor(selected_products[['id', 'Produit', 'Vente']].assign(Promotion=pd.Series(index=selected_products.index, dtype=float)),
        hide_index=True, disabled=['id', 'Produit', 'Vente'], key='catalog_promotions',
        column_config={'id': None, 'Vente': st.column_config.NumberColumn('Prix normal (FCFA)'),
                       'Promotion': st.column_config.NumberColumn('Prix promotionnel (FCFA)', min_value=1, step=1)}, width='stretch')
    if selected_products.empty:
        st.info('Sélectionnez au moins un produit.')
        return
    options = {'whatsapp': phone, 'valid_until': expiry.isoformat(),
               'promotions': {str(int(r.id)): float(r.Promotion) for _, r in edited.iterrows() if pd.notna(r.Promotion)}}
    try:
        whatsapp_number(phone)
        prepare_catalog(selected_products, options)
    except ValueError as exc:
        st.error(str(exc))
        return
    if not phone.strip():
        st.info('Renseignez le numéro WhatsApp pour ajouter le lien de commande et le QR code.')
    signature = hashlib.sha256((selected_products.to_json() + json.dumps(
        {'settings': settings, 'options': options}, sort_keys=True, default=str)).encode()).hexdigest()
    # Keep the request and result through activity-triggered reruns. Changing the
    # selection or prices must never offer a stale catalogue for download.
    if st.button('Préparer le catalogue PDF', key='catalog_build', icon=':material/menu_book:'):
        st.session_state['catalog_request'] = signature
        st.session_state.pop('catalog_result', None)
    result = st.session_state.get('catalog_result')
    if st.session_state.get('catalog_request') == signature and (not result or result['signature'] != signature):
        try:
            with st.spinner('Préparation du catalogue et des photos…'):
                data = make_catalog_pdf(selected_products, settings, options)
            result = {'signature': signature, 'data': data, 'filename': f'catalogue_{date.today()}.pdf'}
            st.session_state['catalog_result'] = result
            st.session_state.pop('catalog_request', None)
        except Exception:
            logging.getLogger(__name__).exception('Catalogue PDF generation failed')
            st.session_state.pop('catalog_request', None)
            st.error('Le catalogue n’a pas pu être préparé. Réessayez avec moins de produits ou contactez-nous si le problème persiste.')
            return
    if result and result['signature'] == signature:
        st.success('Le catalogue PDF est prêt. Cliquez ci-dessous pour le télécharger.')
        st.download_button('Télécharger le catalogue PDF', result['data'], file_name=result['filename'], mime='application/pdf', width='stretch', on_click='ignore', key='catalog_download')
