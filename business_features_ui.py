"""Simple entry points for daily business workflows."""
from datetime import date, timedelta
from io import BytesIO
import json
from zipfile import ZipFile, ZIP_DEFLATED
import pandas as pd
import streamlit as st
import db
import v3_db as v3
import business_features as features


def money(value):
    return f'{float(value):,.0f} FCFA'.replace(',', ' ')


def go(page):
    st.session_state.mobile_page = page
    st.rerun()


def search_box():
    with st.expander('Rechercher un produit, un client ou une facture'):
        with st.form('global_search_form'):
            term = st.text_input('Recherche', placeholder='Nom, téléphone, code-barres ou numéro de facture')
            submitted = st.form_submit_button('Rechercher')
        if submitted:
            if len(term.strip()) < 2:
                st.info('Saisissez au moins deux caractères.')
            else:
                results = features.search(term)
                if not results:
                    st.info('Aucun résultat.')
                for title, rows in results.items():
                    st.write(f'**{title} — {len(rows)} résultat(s)**')
                    st.dataframe(rows, hide_index=True)


def invoice_settings(user):
    features.require_admin(user)
    st.subheader('Identifiants sur les factures')
    settings = features.invoice_settings()
    with st.form('invoice_identifiers'):
        ninea = st.text_input('NINEA', value=settings.get('ninea',''), max_chars=100)
        rccm = st.text_input('RCCM', value=settings.get('rccm',''), max_chars=100)
        st.caption('Renseignez vos identifiants officiels. Les champs vides ne sont pas imprimés.')
        if st.form_submit_button('Enregistrer les identifiants'):
            features.save_invoice_settings(ninea, rccm, user)
            st.success('Identifiants enregistrés pour les prochains PDF.')


def debts_page(user, kind):
    features.require_admin(user)
    is_client = kind == 'clients'
    st.header('Sommes dues par les clients' if is_client else 'Sommes dues aux fournisseurs')
    debts = features.debt_rows(kind)
    a,b = st.columns(2)
    a.metric('Total restant', money(debts.Reste.sum()))
    b.metric('En retard', money(debts.loc[debts.Situation=='En retard', 'Reste'].sum()))
    situation = st.selectbox('Situation', ['Toutes', 'En retard', 'À échéance', 'À venir', 'Sans échéance'])
    shown = debts if situation == 'Toutes' else debts[debts.Situation == situation]
    if debts.empty:
        st.success('Aucune somme restant à payer.')
        return
    st.dataframe(shown, hide_index=True)
    st.download_button('Exporter les impayés', shown.to_csv(index=False).encode('utf-8-sig'), file_name=f'impayes_{kind}.csv', mime='text/csv')
    party = 'Client' if is_client else 'Fournisseur'
    labels = {f"#{int(r['N°'])} — {r[party]} — {money(r['Reste'])}":r for _,r in debts.iterrows()}
    row = labels[st.selectbox('Compte à gérer', list(labels))]
    current = date.fromisoformat(row['Échéance']) if row['Échéance'] else date.today()+timedelta(days=30)
    with st.form('debt_due_date'):
        due = st.date_input('Échéance de paiement', value=current)
        if st.form_submit_button('Enregistrer l’échéance'):
            if is_client:
                db.set_credit_due_date(int(row['N°']), due)
            else:
                features.save_supplier_due(int(row['N°']), due, user)
            st.rerun()
    st.caption('L’échéance fournisseur concerne le paiement ; la date de livraison reste indépendante.') if not is_client else None
    if st.button('Enregistrer un paiement'):
        go('Crédits' if is_client else 'Commandes')


def profit_page(user):
    features.require_admin(user)
    st.header('Bénéfice de la boutique')
    period = st.date_input('Période du bénéfice', value=(date.today().replace(day=1), date.today()))
    if len(period) != 2:
        st.info('Choisissez le début et la fin de la période.')
        return
    result = features.profit_summary(*period)
    a,b,c = st.columns(3)
    a.metric('Ventes après remises', money(result['revenue']))
    b.metric('Coût des articles vendus', money(result['cost']))
    c.metric('Marge brute', money(result['gross']))
    a,b,c = st.columns(3)
    a.metric('Dépenses de fonctionnement', money(result['operating']))
    b.metric('Commissions des vendeurs', money(result['commissions']))
    c.metric('Résultat estimé', money(result['net']))
    st.caption('Résultat = ventes après remises − coût des articles vendus − dépenses de fonctionnement − commissions. Les achats de stock et règlements fournisseurs ne sont pas déduits une seconde fois. Les ventes à crédit sont incluses ; ce résultat n’est pas le solde de caisse.')
    st.caption('Le résultat dépend des coûts et charges saisis. Les commissions déjà calculées sur les ventes ne doivent pas être saisies à nouveau comme dépense.')
    if result['estimated']:
        st.warning(f"{result['estimated']} ligne(s) ancienne(s) sans coût historique : estimation au prix d’achat actuel.")
    if not result['expenses'].empty:
        st.subheader('Détail des dépenses et de leur traitement')
        st.dataframe(result['expenses'], hide_index=True)
    summary = pd.DataFrame([{'Indicateur':k,'FCFA':result[k]} for k in ['revenue','cost','gross','operating','commissions','net']])
    summary['Indicateur'] = ['Ventes après remises','Coût des articles vendus','Marge brute','Dépenses de fonctionnement','Commissions','Résultat estimé']
    st.download_button('Exporter le bilan', summary.to_csv(index=False).encode('utf-8-sig'), file_name='bilan_benefice.csv', mime='text/csv')


def reorder_page(user):
    features.require_admin(user)
    st.header('Alertes et réapprovisionnement')
    rows = features.reorder_rows()
    st.caption('Suggestions fondées sur les ventes des 30 derniers jours, le stock minimum et les quantités déjà commandées.')
    if rows.empty:
        st.success('Aucun produit à réapprovisionner.')
        return
    st.dataframe(rows.drop(columns=['id','supplier_id']), hide_index=True)
    available = rows[rows['À commander'] > 0]
    if available.empty:
        st.info('Les commandes en cours couvrent les besoins. Consultez Achats pour enregistrer les réceptions.')
        return
    suppliers = db.suppliers()
    if suppliers.empty:
        st.info('Ajoutez un fournisseur avant de préparer une commande.')
        return
    smap = dict(zip(suppliers.Fournisseur, suppliers.id))
    supplier = st.selectbox('Fournisseur de la commande', list(smap))
    suggested = available[(available.supplier_id == smap[supplier]) | available.supplier_id.isna()]
    edited = st.data_editor(suggested[['id','Produit','À commander','Coût unitaire']].copy(), hide_index=True,
                            disabled=['id','Produit'], key=f'reorder_editor_{smap[supplier]}',
                            column_config={'À commander':st.column_config.NumberColumn(min_value=0, step=1), 'Coût unitaire':st.column_config.NumberColumn(min_value=0)})
    if suggested.empty:
        st.info('Aucun besoin attribué à ce fournisseur. Les produits sans fournisseur sont proposés à chacun.')
        return
    expected = st.date_input('Livraison souhaitée', value=date.today()+timedelta(days=7))
    total = (edited['À commander'] * edited['Coût unitaire']).sum()
    st.metric('Montant de la commande à créer', money(total))
    if st.button('Créer cette commande fournisseur', type='primary'):
        items = []
        for _,r in edited.iterrows():
            qty, cost = float(r['À commander']), float(r['Coût unitaire'])
            if not pd.notna(qty) or not pd.notna(cost) or qty < 0 or cost < 0 or not qty.is_integer():
                st.error('Renseignez des quantités entières et des coûts positifs ou nuls.')
                return
            if qty:
                items.append({'product_id':int(r.id),'quantity':int(qty),'unit_cost':cost})
        if not items:
            st.error('Choisissez au moins un article à commander.')
            return
        identifier = v3.create_purchase_order(int(smap[supplier]), expected, 'Réapprovisionnement depuis les alertes de stock', items, int(user['id']))
        db.log_action(int(user['id']), 'COMMANDE_FOURNISSEUR', f'Commande #{identifier} depuis les alertes')
        st.session_state['reorder_success'] = f'Commande #{identifier} créée. Le stock augmentera à la réception.'
        st.rerun()


def backups_page(user):
    features.require_admin(user)
    st.header('Sauvegarder et récupérer les données')
    st.caption('Téléchargez une copie avant une modification importante. La récupération ajoute les enregistrements manquants sans remplacer ceux qui existent déjà.')
    if st.button('Préparer une sauvegarde complète', type='primary'):
        try:
            bundle = features.complete_backup()
            output = BytesIO()
            with ZipFile(output,'w',ZIP_DEFLATED) as archive:
                archive.writestr('boutique_backup.json', json.dumps(bundle,ensure_ascii=False,default=str))
            st.session_state['backup_download'] = output.getvalue()
            st.session_state['backup_count'] = sum(len(r) for r in bundle['tables'].values())
        except Exception:
            st.session_state.pop('backup_download',None)
            st.error('La sauvegarde n’a pas pu lire toutes les données. Aucun fichier incomplet n’est proposé. Réessayez après vérification de la connexion.')
    if st.session_state.get('backup_download'):
        st.success(f"Copie prête : {st.session_state['backup_count']} enregistrements.")
        st.download_button('Télécharger la sauvegarde', st.session_state['backup_download'], file_name=f'boutique_{date.today()}.zip', mime='application/zip')
        st.caption('Conservez cette copie dans un endroit privé : elle contient les données et les comptes de la boutique.')
    st.subheader('Récupérer une sauvegarde')
    uploaded = st.file_uploader('Fichier de sauvegarde', type=['zip','json'], key='simple_backup_upload')
    if uploaded is None:
        return
    try:
        if uploaded.size > 50*1024*1024:
            raise ValueError('Le fichier dépasse 50 Mo.')
        if uploaded.name.lower().endswith('.zip'):
            with ZipFile(BytesIO(uploaded.getvalue())) as archive:
                if archive.getinfo('boutique_backup.json').file_size > 100*1024*1024:
                    raise ValueError('La sauvegarde décompressée dépasse 100 Mo.')
                bundle = json.loads(archive.read('boutique_backup.json'))
        else:
            bundle = json.loads(uploaded.getvalue())
        counts = features.validate_backup(bundle)
    except Exception as error:
        st.error(f'Sauvegarde non utilisable : {error}')
        return
    st.write(f"Sauvegarde du {bundle.get('created_at','date inconnue')} — {sum(counts.values())} enregistrements")
    st.dataframe(pd.DataFrame([{'Données':table,'Enregistrements':n} for table,n in counts.items()]),hide_index=True)
    if set(counts) != set(db.BACKUP_TABLES):
        st.warning('Cette ancienne sauvegarde ne contient pas toutes les catégories de données.')
    with st.form('simple_restore'):
        password = st.text_input('Mot de passe administrateur',type='password')
        confirmed = st.checkbox('Récupérer les données manquantes de cette sauvegarde')
        if st.form_submit_button('Récupérer les données'):
            authenticated = db.authenticate(str(user['username']),password)
            if not authenticated or authenticated.get('role') != 'admin':
                st.error('Mot de passe administrateur incorrect.')
            elif not confirmed:
                st.error('Cochez la confirmation pour continuer.')
            else:
                try:
                    result = db.restore_backup(bundle)
                    restored = result.get('restored',result)
                    st.success(f"Récupération terminée : {sum(int(v) for v in restored.values())} enregistrements ajoutés.")
                except Exception:
                    st.error('La récupération a été interrompue. Certaines données peuvent avoir été récupérées ; vérifiez la connexion avant de réessayer.')

