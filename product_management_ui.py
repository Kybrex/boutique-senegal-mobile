"""Shared product deletion controls for desktop and mobile."""
import logging
import streamlit as st
from product_management import delete_product


def deletion_panel(user, inventory):
    if not user or user.get('role') != 'admin':
        return
    notice = st.session_state.pop('product_deleted_notice', None)
    if notice:
        message, warning = notice
        st.success(message)
        if warning:
            st.warning(warning)
    if inventory.empty:
        return
    with st.expander('Supprimer un produit', icon=':material/delete:'):
        st.caption('Les produits liés à des ventes, documents, commandes, inventaires, transferts, retours, lots ou variantes sont protégés.')
        rows = {int(row.id): row for _, row in inventory.iterrows()}
        product_id = st.selectbox('Produit à supprimer', list(rows),
                                  format_func=lambda value: f'{rows[value].Produit} — réf. {value}',
                                  key='delete_product_choice')
        row = rows[product_id]
        stock = int(row.Stock)
        st.warning(f'La fiche « {row.Produit} » et ses {stock} unité(s) en stock seront supprimées définitivement. Pour retirer seulement une quantité, utilisez « Retirer » dans la modification du stock.')
        suffix = f'{product_id}_{stock}'
        reason = st.text_input('Motif de la suppression', max_chars=200, key=f'delete_product_reason_{suffix}')
        confirmed = st.checkbox(f'Je confirme la suppression de {row.Produit} et de {stock} unité(s)', key=f'delete_product_confirm_{suffix}')
        if st.button('Supprimer le produit', icon=':material/delete:', disabled=not confirmed or not reason.strip(), key=f'delete_product_submit_{suffix}'):
            if not confirmed or not reason.strip():
                return
            try:
                warning = delete_product(user, product_id, stock, reason)
            except ValueError as error:
                st.error(str(error))
                return
            except Exception:
                logging.getLogger(__name__).exception('Product deletion failed')
                st.error('Impossible de terminer la suppression. Actualisez la liste pour vérifier le produit avant de réessayer.')
                return
            st.session_state['product_deleted_notice'] = (f'Produit « {row.Produit} » supprimé.', warning)
            st.rerun()
