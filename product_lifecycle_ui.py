"""Administrative product forms shared by mobile and desktop."""
import logging
from functools import partial
import pandas as pd
import streamlit as st
import db
import product_lifecycle as lifecycle


def notice():
    error = st.session_state.pop('product_lifecycle_error',None)
    if error:
        st.error(error)
    saved = st.session_state.pop('product_lifecycle_notice',None)
    if saved:
        message,warning = saved
        st.success(message)
        if warning:
            st.warning(warning)


def callback(action, message):
    # Run before the page is rebuilt, so an archive removing the final item
    # never leaves stale controls from the previous expander contents.
    try:
        warning = action()
    except ValueError as error:
        st.session_state['product_lifecycle_error'] = str(error)
        return
    except Exception:
        logging.getLogger(__name__).exception('Product operation failed')
        st.session_state['product_lifecycle_error'] = 'L’opération n’a pas pu être confirmée. Vérifiez l’état de la fiche avant de réessayer.'
        return
    st.session_state['product_lifecycle_notice'] = (message,warning if isinstance(warning,str) else None)


def perform(action, message):
    try:
        warning = action()
    except ValueError as error:
        st.error(str(error)); return
    except Exception:
        logging.getLogger(__name__).exception('Product operation failed')
        st.error('L’opération n’a pas pu être confirmée. Actualisez la fiche pour vérifier son état avant de réessayer.'); return
    st.session_state['product_lifecycle_notice'] = (message,warning if isinstance(warning,str) else None)
    st.rerun()


def creation_panel(user, suppliers):
    if not user or user.get('role') != 'admin': return
    with st.expander('Ajouter un produit',icon=':material/add_circle:'):
        name = st.text_input('Nom du nouveau produit',max_chars=150,key='new_product_name')
        matches = lifecycle.duplicate_candidates(name)
        exact = any(r['exact'] for r in matches)
        archived = lifecycle.archived_ids() if matches else set()
        if matches:
            st.warning('Des produits identiques ou proches existent. Vérifiez leur fiche avant de créer un nouveau produit.')
            st.dataframe(pd.DataFrame([{'Référence':r['id'],'Produit':r['name'],'Statut':'Archivé' if r['id'] in archived else 'Actif','Correspondance':'Identique' if r['exact'] else 'Nom proche'} for r in matches]),hide_index=True)
        if exact:
            st.info('Ce nom existe déjà, même si ses accents ou ses espaces diffèrent. Modifiez la fiche existante ou restaurez le produit archivé.')
        confirmed = st.checkbox('J’ai vérifié : il s’agit d’un produit différent',key='new_product_distinct_'+lifecycle.normalized_name(name)) if matches and not exact else True
        with st.form('new_product_form'):
            category = st.text_input('Catégorie',max_chars=100)
            purchase = st.number_input("Prix d'achat (FCFA)",min_value=0.0,step=100.0)
            sale = st.number_input('Prix de vente (FCFA)',min_value=1.0,step=100.0)
            stock = st.number_input('Quantité initiale',min_value=0,step=1)
            minimum = st.number_input("Seuil d'alerte",min_value=0,step=1)
            supplier_map = {'Sans fournisseur':None} | dict(zip(suppliers.Fournisseur,suppliers.id))
            supplier = st.selectbox('Fournisseur',list(supplier_map))
            if st.form_submit_button('Ajouter le produit',disabled=exact or not name.strip() or not confirmed,type='primary'):
                perform(lambda:db.add_product(name,category,purchase,sale,int(stock),int(minimum),supplier_map[supplier]),'Produit ajouté.')


def stock_panel(user, inventory):
    if not user or user.get('role') != 'admin' or inventory.empty: return
    with st.container(border=True):
        entries = {int(r.id):r for _,r in inventory.iterrows()}
        pid = st.selectbox('Produit à modifier',list(entries),format_func=lambda i:entries[i].Produit,key='movement_product')
        row = entries[pid]
        mode = st.segmented_control('Modification',['Définir','Ajouter','Retirer'],default='Définir',key='movement_mode') or 'Définir'
        amount = st.number_input('Quantité',min_value=0 if mode=='Définir' else 1,value=int(row.Stock) if mode=='Définir' else 1,step=1,key=f'movement_amount_{pid}_{int(row.Stock)}_{mode}')
        target = int(amount) if mode=='Définir' else int(row.Stock)+(int(amount) if mode=='Ajouter' else -int(amount))
        st.caption(f'Stock actuel : {int(row.Stock)} → après modification : {target}')
        reason = st.selectbox('Motif de sortie',lifecycle.EXIT_REASONS,key=f'movement_reason_{pid}') if target < int(row.Stock) else 'Entrée / correction'
        note = st.text_input('Précision du mouvement',max_chars=200,key=f'movement_note_{pid}')
        if st.button('Enregistrer le stock',type='primary',disabled=target < 0 or target==int(row.Stock),key='save_product_movement'):
            perform(lambda:lifecycle.change_stock(user,pid,mode,int(amount),int(row.Stock),reason,note),'Mouvement de stock enregistré.')


def management_panel(user):
    if not user or user.get('role') != 'admin': return
    all_products = lifecycle.all_products()
    if all_products.empty: return
    archived = lifecycle.archived_ids()
    entries = {int(r.id):r for _,r in all_products.iterrows()}
    def label(pid): return f"{entries[pid].Produit} — réf. {pid}" + (' (archivé)' if pid in archived else '')
    with st.expander('Modifier le nom et la catégorie',icon=':material/edit:'):
        pid = st.selectbox('Fiche à modifier',list(entries),format_func=label,key='identity_product')
        row = entries[pid]
        with st.form(f'identity_form_{pid}_{row.Produit}_{row.Categorie}'):
            name = st.text_input('Nouveau nom',value=str(row.Produit),max_chars=150)
            category = st.text_input('Nouvelle catégorie',value=str(row.Categorie or ''),max_chars=100)
            st.caption('La référence du produit reste identique. Les changements sont conservés dans son historique.')
            if st.form_submit_button('Enregistrer la fiche'):
                perform(lambda:lifecycle.update_identity(user,pid,name,category,str(row.Produit),row.Categorie),'Fiche produit mise à jour.')
    with st.expander('Archiver ou restaurer un produit',icon=':material/archive:'):
        view = st.radio('Afficher',['Produits actifs','Produits archivés'],horizontal=True,key='archive_view')
        restoring = view == 'Produits archivés'
        choices = [pid for pid in entries if (pid in archived)==restoring]
        if not choices:
            st.info('Aucun produit dans cette liste.')
        else:
            pid = st.selectbox('Produit à restaurer' if restoring else 'Produit à archiver',choices,format_func=label,key='archive_product_'+str(restoring))
            st.caption(f'Stock conservé : {int(entries[pid].Stock)} unité(s). Les ventes et justificatifs restent accessibles.')
            if not restoring: st.info('Le produit sera masqué dans la caisse, les listes de stock actif et les nouveaux catalogues.')
            reason = st.text_input('Motif de restauration' if restoring else 'Motif d’archivage',max_chars=200,key=f'archive_reason_{pid}_{restoring}')
            confirmed = st.checkbox('Je confirme la restauration' if restoring else 'Je confirme l’archivage',key=f'archive_confirm_{pid}_{restoring}')
            st.button('Restaurer le produit' if restoring else 'Archiver le produit',disabled=not confirmed or not reason.strip(),key=f'archive_submit_{pid}_{restoring}',
                      on_click=callback,args=(partial(lifecycle.set_archived,user,pid,not restoring,reason),'Produit restauré.' if restoring else 'Produit archivé.'))
    with st.expander('Historique par produit',icon=':material/history:'):
        pid = st.selectbox('Produit à consulter',list(entries),format_func=label,key='history_product')
        st.caption('Ventes, retours, inventaires, transferts et modifications. Les mouvements anciens sans date précise sont signalés ; ce tableau ne reconstitue pas un solde comptable.')
        if st.button('Afficher / actualiser l’historique',key='load_product_history'):
            from product_history import history
            try:
                frame = history(pid)
                st.dataframe(frame,hide_index=True,width='stretch')
                st.download_button('Exporter cet historique',frame.to_csv(index=False).encode('utf-8-sig'),file_name=f'historique_produit_{pid}.csv',mime='text/csv',on_click='ignore')
            except Exception:
                logging.getLogger(__name__).exception('Product history failed')
                st.error('L’historique est momentanément indisponible. Réessayez après actualisation.')
