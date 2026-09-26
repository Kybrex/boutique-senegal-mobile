"""Configure and download a customer catalogue without changing sale prices."""
from datetime import date, timedelta
import hashlib
import json
import logging
import pandas as pd
import streamlit as st
from catalog_options import prepare_catalog, whatsapp_number, reference
from v4_pdf import make_catalog_pdf


def catalog_panel(products, settings, user=None):
    st.caption('Composez votre catalogue avec photos, références, promotions et commande WhatsApp.')
    if st.session_state.pop('catalog_saved_notice', False):
        st.success('Catalogue enregistré. Vous pourrez le recharger lors d’une prochaine connexion.')
    if user and user.get('role') == 'admin':
        from catalog_library import list_catalogs, restore_catalog, CatalogDataError
        try:
            saved = list_catalogs(user)
        except CatalogDataError as exc:
            saved = exc.recovered
            st.warning(str(exc))
        except Exception:
            saved = {}
            st.warning('Les catalogues enregistrés sont momentanément indisponibles.')
        choice = st.selectbox('Catalogues enregistrés', ['Nouveau catalogue'] + sorted(saved), key='catalog_library_choice')
        if choice in saved and st.button('Charger ce catalogue', key='load_catalog_preset'):
            missing = restore_catalog(st.session_state, saved[choice], products)
            st.session_state['catalog_name'] = choice
            st.success('Catalogue chargé. Vérifiez les disponibilités, promotions et la date de validité avant de préparer le PDF.')
            if missing:
                st.info(f'{missing} produit(s) supprimé(s) ont été retirés de la sélection.')
    only_stock = st.checkbox('Uniquement les produits en stock', value=True, key='catalog_stock')
    available = products[products.Stock > 0].copy() if only_stock and not products.empty else products.copy()
    if available.empty:
        st.info('Aucun produit disponible pour ce catalogue.')
        return
    available['Categorie'] = available.Categorie.fillna('').replace('', 'Autres produits')
    categories = sorted(available.Categorie.unique())
    if 'catalog_categories' in st.session_state:
        st.session_state['catalog_categories'] = [x for x in st.session_state['catalog_categories'] if x in categories]
    chosen = st.multiselect('Catégories à inclure', categories, default=categories, key='catalog_categories')
    available = available[available.Categorie.isin(chosen)]
    labels = {int(r.id): f'{r.Produit} (réf. {reference(r)})' for _, r in available.iterrows()}
    if 'catalog_products' in st.session_state:
        st.session_state['catalog_products'] = [x for x in st.session_state['catalog_products'] if x in labels]
    selected = st.multiselect('Produits à inclure', list(labels), default=list(labels), format_func=labels.get, key='catalog_products')
    selected_products = available[available.id.isin(selected)].copy()
    phone = st.text_input('Numéro WhatsApp pour les commandes', value=str(settings.get('phone') or ''), key='catalog_whatsapp', help='Un numéro sénégalais de 9 chiffres reçoit automatiquement l’indicatif +221. Pour un autre pays, renseignez son indicatif.')
    expiry = st.date_input('Prix valables jusqu’au', value=date.today() + timedelta(days=30), min_value=date.today(), key='catalog_expiry')
    show_prices = st.checkbox('Afficher les prix dans le PDF', value=True, key='catalog_show_prices')
    cover = st.checkbox('Ajouter une page de couverture', value=True, key='catalog_cover')
    title = st.text_input('Titre du catalogue', value='Catalogue produits', max_chars=100, key='catalog_title')
    st.subheader('Conditions de livraison')
    zones = st.text_area('Zones de livraison', max_chars=300, key='catalog_zones')
    fees = st.text_area('Frais de livraison', max_chars=300, key='catalog_fees')
    times = st.text_area('Délais de livraison', max_chars=300, key='catalog_times')
    st.subheader('Descriptions et variantes disponibles')
    st.caption('Indiquez les dimensions, matières, tailles et couleurs réellement disponibles. Enregistrez le catalogue pour retrouver ces textes.')
    saved_options = st.session_state.get('catalog_saved_options', {})
    details = saved_options.get('details', {})
    detail_rows = selected_products[['id', 'Produit']].copy()
    for field in ('Description', 'Tailles', 'Couleurs'):
        detail_rows[field] = pd.Series([details.get(str(int(i)), {}).get(field, '') for i in detail_rows.id], index=detail_rows.index, dtype='string')
    edited_details = st.data_editor(detail_rows, hide_index=True, disabled=['id', 'Produit'], key='catalog_details',
        column_config={'id':None, 'Description':st.column_config.TextColumn('Description', max_chars=300),
                       'Tailles':st.column_config.TextColumn('Tailles disponibles', max_chars=100),
                       'Couleurs':st.column_config.TextColumn('Couleurs disponibles', max_chars=100)}, width='stretch')
    st.caption('Les promotions ci-dessous concernent ce PDF. Elles ne changent pas les prix enregistrés en caisse.')
    edited = st.data_editor(selected_products[['id', 'Produit', 'Vente']].assign(Promotion=[saved_options.get('promotions', {}).get(str(int(i)), float('nan')) for i in selected_products.id]),
        hide_index=True, disabled=['id', 'Produit', 'Vente'], key='catalog_promotions',
        column_config={'id': None, 'Vente': st.column_config.NumberColumn('Prix normal (FCFA)'),
                       'Promotion': st.column_config.NumberColumn('Prix promotionnel (FCFA)', min_value=1, step=1)}, width='stretch')
    if selected_products.empty:
        st.info('Sélectionnez au moins un produit.')
        return
    options = {'whatsapp': phone, 'valid_until': expiry.isoformat(),
               'show_prices':show_prices, 'cover':cover, 'title':title,
               'delivery_zones':zones, 'delivery_fees':fees, 'delivery_times':times,
               'details':{str(int(r.id)): {field:str(r[field]) if pd.notna(r[field]) else '' for field in ('Description','Tailles','Couleurs')} for _,r in edited_details.iterrows()},
               'promotions': {str(int(r.id)): float(r.Promotion) for _, r in edited.iterrows() if pd.notna(r.Promotion)}}
    try:
        whatsapp_number(phone)
        prepare_catalog(selected_products, options)
    except ValueError as exc:
        st.error(str(exc))
        return
    if user and user.get('role') == 'admin':
        name = st.text_input('Nom du catalogue à enregistrer', max_chars=80, key='catalog_name')
        st.caption('Enregistrer sous le même nom remplace les réglages de ce catalogue.')
        if st.button('Enregistrer ce catalogue', key='catalog_save'):
            from catalog_library import save_catalog
            try:
                save_catalog(user, name, {'product_ids': [int(i) for i in selected_products.id], 'only_stock':only_stock, 'options':options})
                st.session_state['catalog_saved_notice'] = True
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
            except Exception:
                st.error('L’enregistrement a échoué. Réessayez ; vos réglages restent affichés.')
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
