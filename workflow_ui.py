"""Simple admin screens for documents, clients and backup health."""
from datetime import date
from io import BytesIO
import json
from zipfile import ZipFile, ZIP_DEFLATED
import pandas as pd
import streamlit as st
import db
import business_features as features
import workflow_service as service

def money(value):
    return f'{float(value):,.0f} FCFA'.replace(',', ' ')

def show_error(error):
    if isinstance(error, ValueError):
        st.error(str(error))
    else:
        st.error('L’opération n’a pas abouti. Vérifiez la connexion et le stockage privé, puis réessayez.')

def invoice_downloads(envelope, user, key):
    features.require_admin(user)
    meta = envelope['meta']
    st.caption(f"Original conservé le {meta['created_at'][:19].replace('T',' ')} · {meta['number']}")
    fmt = st.radio('Format d’impression', ['A4','A5'], horizontal=True, key=key+'_format')
    pdf, name, mime = service.unpack_file(envelope, fmt)
    st.download_button('Télécharger la facture PDF', pdf, file_name=name, mime=mime, key=key+'_download')
    st.caption(f'Ouvrez le PDF et choisissez le papier {fmt}, à taille réelle (100 %).')
    with st.expander('Préparer un envoi WhatsApp'):
        st.caption('Téléchargez le PDF ci-dessus. Le message s’ouvrira dans WhatsApp ; joignez le PDF puis confirmez l’envoi là-bas.')
        phone = st.text_input('Numéro WhatsApp du destinataire', value=str(meta.get('phone') or ''), key=key+'_phone')
        default = f"Bonjour {meta.get('client','')}, voici votre facture {meta['number']} en pièce jointe. Merci pour votre achat."
        message = st.text_area('Message à envoyer', value=default, max_chars=2000, key=key+'_message')
        checked = st.checkbox('J’ai vérifié le destinataire et le message', key=key+'_confirm')
        if checked:
            try:
                url = service.whatsapp_url(phone, message)
                st.link_button('Ouvrir WhatsApp avec ce message', url)
                st.caption('Aucun message ni fichier n’est envoyé automatiquement.')
            except ValueError as error:
                st.info(str(error))

def invoice_panel(source, identifier, user):
    features.require_admin(user)
    key = f'invoice_{source}_{identifier}'
    object_key = f'{service.PREFIX}invoices/{source}/{int(identifier)}.json'
    try:
        existing = next((r for r in service.entries(user) if r['key']==object_key), None)
        if existing:
            invoice_downloads(service.get_document(object_key,user), user, key)
            st.caption('Ce PDF est l’original archivé. Les changements apportés ensuite à la vente ne le modifient pas.')
        else:
            st.info('La première émission conserve définitivement une copie A4 et A5 de cette facture.')
            if st.button('Émettre et archiver la facture', key=key+'_issue', type='primary'):
                service.issue_invoice(source, identifier, user)
                st.rerun()
    except Exception as error:
        show_error(error)

def archive_page(user):
    features.require_admin(user)
    st.header('Factures émises')
    st.caption('Retrouvez les PDF originaux, même si une vente ou les coordonnées de la boutique changent ensuite.')
    try:
        rows = [r for r in service.entries(user) if r['kind']=='invoice']
        term = st.text_input('Rechercher un numéro ou un client', key='archive_search').strip().casefold()
        rows = [r for r in rows if not term or term in (r['number']+' '+r['client']).casefold()]
        if not rows:
            st.info('Aucune facture archivée pour cette recherche. Émettez une facture depuis Factures des ventes ou Documents.')
            return
        st.dataframe(pd.DataFrame([{'Facture':r['number'],'Client':r['client'],'Émise le':r['created_at'][:19].replace('T',' '),'Total':money(r['total'])} for r in rows]),hide_index=True)
        selected = st.selectbox('Facture à ouvrir', rows, format_func=lambda r:f"{r['number']} · {r['client']}", key='archive_selected')
        invoice_downloads(service.get_document(selected['key'],user),user,'archive_'+selected['number'])
    except Exception as error:
        show_error(error)

def attachments_page(user):
    features.require_admin(user)
    st.header('Justificatifs')
    st.caption('Ajoutez une photo ou un PDF à une dépense, un achat reçu ou une commande fournisseur. Les fichiers restent privés.')
    target = st.radio('Rattacher à', ['expenses','purchase_orders'], horizontal=True,
                      format_func=lambda t:'Dépense ou achat reçu' if t=='expenses' else 'Commande fournisseur')
    try:
        records = sorted(features.records(target),key=lambda r:r['id'],reverse=True)
        if not records:
            st.info('Enregistrez d’abord une dépense ou une commande.')
            return
        selected = st.selectbox('Enregistrement concerné', records, key='attachment_target_'+target,
            format_func=lambda r:f"#{r['id']} · {str(r.get('created_at',''))[:10]} · {r.get('label','Commande fournisseur')} · {money(r.get('amount',r.get('total',0)))}")
        key = f"attachment_{target}_{selected['id']}"
        with st.form(key):
            upload = st.file_uploader('Photo ou document (5 Mo maximum)', type=['pdf','jpg','jpeg','png'], key=key+'_file')
            note = st.text_input('Note facultative', max_chars=500)
            if st.form_submit_button('Enregistrer le justificatif'):
                if upload is None:
                    st.error('Choisissez un fichier.')
                else:
                    service.add_attachment(target, selected['id'], upload.name, upload.getvalue(), note, user)
                    st.success('Justificatif enregistré et contrôlé.')
        matches = [r for r in service.entries(user) if r['kind']=='attachment' and r['target']==target and r['source_id']==selected['id']]
        st.subheader('Fichiers enregistrés')
        if not matches:
            st.caption('Aucun justificatif pour cet enregistrement.')
        for item in matches:
            with st.expander(item['filename']+' · '+item['created_at'][:10]):
                if item.get('note'):
                    st.write(item['note'])
                env = service.get_document(item['key'], user)
                data, filename, mime = service.unpack_file(env,'original')
                if mime.startswith('image/'):
                    st.image(data, width=320)
                st.download_button('Télécharger le justificatif', data, file_name=filename, mime=mime, key='file_'+item['key'])
    except Exception as error:
        show_error(error)

def client_page(user):
    features.require_admin(user)
    st.header('Fiche client complète')
    try:
        clients = features.records('clients')
        if not clients:
            st.info('Ajoutez d’abord un client.')
            return
        client = st.selectbox('Client à consulter', sorted(clients,key=lambda r:r['name'].casefold()),
                              format_func=lambda r:f"{r['name']} · {r.get('phone','')} · #{r['id']}")
        profile = service.client_profile(client['id'],user)
        st.subheader(client['name'])
        for label, field in [('Téléphone','phone'),('E-mail','email'),('Adresse','address')]:
            if client.get(field):
                st.text(f"{label} : {client[field]}")
        a,b,c = st.columns(3)
        a.metric('Achats',money(profile['total']))
        b.metric('Reste à payer',money(profile['debt']))
        c.metric('Avoir disponible',money(client.get('store_credit') or 0))
        tab = st.radio('Consulter',['Achats','Paiements','Dettes','Documents'],horizontal=True,key='client_detail_tab')
        if tab in ('Achats','Dettes'):
            rows = [{'Vente':r['id'],'Date':r['created_at'],'Total':float(r['total']), 'Payé':float(r['paid']),
                     'Reste':max(0,float(r['total'])-float(r['paid'])),'Échéance':r.get('due_date') or ''} for r in profile['sales']]
            if tab=='Dettes':
                rows = [r for r in rows if r['Reste']>.005]
            st.dataframe(pd.DataFrame(rows),hide_index=True) if rows else st.info('Aucune opération dans cette rubrique.')
        elif tab=='Paiements':
            st.dataframe(pd.DataFrame(profile['payments']),hide_index=True) if profile['payments'] else st.info('Aucun paiement enregistré.')
            st.caption('Les paiements à la vente et les règlements ultérieurs sont présentés séparément, sans double comptage.')
        else:
            documents = [{'N°':r['id'],'Type':r['document_type'],'Date':r['created_at'],'Total':r['total'],'Statut':r['status']} for r in profile['documents']]
            st.dataframe(pd.DataFrame(documents),hide_index=True) if documents else st.caption('Aucun devis ou document créé séparément.')
            if profile['invoices']:
                selected = st.selectbox('Facture originale à télécharger', profile['invoices'],format_func=lambda r:r['number'])
                invoice_downloads(service.get_document(selected['key'],user),user,'client_'+selected['number'])
            else:
                st.info('Aucune facture émise et archivée pour ce client.')
    except Exception as error:
        show_error(error)

def preferences_panel(user):
    features.require_admin(user)
    st.subheader('Verrouillage et rappels')
    current = service.preferences()
    with st.form('daily_preferences'):
        idle = st.number_input('Verrouiller après combien de minutes sans activité ?',min_value=1,max_value=60,value=current['idle_minutes'])
        days = st.number_input('Rappel de sauvegarde après combien de jours ?',min_value=1,max_value=30,value=current['backup_days'])
        if st.form_submit_button('Enregistrer ces réglages'):
            service.save_preferences(idle,days,user)
            st.session_state['_auth_timeout'] = float(idle)*60
            st.success('Réglages enregistrés. Le nouveau délai s’applique aux prochaines connexions et à cette session.')
    st.caption('Le verrouillage revient à la connexion et efface les formulaires non enregistrés de cette session.')

def backup_reminder(user):
    features.require_admin(user)
    try:
        status = service.backup_status()
        if status['due']:
            st.warning('Une nouvelle sauvegarde est recommandée. Ouvrez Réglages → Sauvegarder et récupérer.')
        elif status['latest']:
            st.caption('Dernière copie conservée ou automatique vérifiée : '+status['latest'][:19].replace('T',' '))
    except Exception:
        st.warning('La date de la dernière sauvegarde n’a pas pu être vérifiée.')

def parse_backup(data, filename):
    if len(data) > service.MAX_BACKUP:
        raise ValueError('Le fichier dépasse 100 Mo.')
    if filename.lower().endswith('.zip'):
        with ZipFile(BytesIO(data)) as archive:
            members = [i for i in archive.infolist() if i.filename=='boutique_backup.json']
            if len(members)!=1 or members[0].file_size > service.MAX_BACKUP:
                raise ValueError('Contenu de sauvegarde invalide ou trop volumineux.')
            data = archive.read(members[0])
    bundle = json.loads(data)
    counts = features.validate_backup(bundle)
    return bundle, counts

def backups_page(user):
    features.require_admin(user)
    st.header('Sauvegarder et récupérer')
    st.caption('La copie complète inclut les données, les factures originales et les justificatifs privés.')
    try:
        status = service.backup_status()
        labels = {'prepared':'Copie préparée','confirmed':'Copie conservée (confirmée par vous)',
                  'verified':'Fichier contrôlé','automatic_verified':'Copie automatique contrôlée'}
        for stage,label in labels.items():
            if status[stage]:
                st.text(label+' : '+status[stage]['at'][:19].replace('T',' '))
        if status['due']:
            st.warning('Préparez et conservez une nouvelle copie de sauvegarde.')
        if st.button('Préparer une sauvegarde complète',type='primary'):
            st.session_state.pop('backup_prepared',None)
            bundle = features.complete_backup()
            features.validate_backup(bundle)
            raw = service.encode(bundle)
            if len(raw)>service.MAX_BACKUP:
                raise ValueError('La sauvegarde dépasse 100 Mo. Contactez l’administrateur pour un export volumineux.')
            output = BytesIO()
            with ZipFile(output,'w',ZIP_DEFLATED) as archive:
                archive.writestr('boutique_backup.json',raw)
            payload = output.getvalue()
            service.record_backup('prepared',service.digest(payload),bundle['created_at'],user)
            st.session_state['backup_prepared'] = {'data':payload,'sha':service.digest(payload),'created_at':bundle['created_at'],
                                                   'count':sum(len(r) for r in bundle['tables'].values()),'files':len(bundle['private_documents'])}
        prepared = st.session_state.get('backup_prepared')
        if prepared:
            st.success(f"Copie prête : {prepared['count']} enregistrements et {prepared['files']} archives de documents.")
            st.download_button('Télécharger la sauvegarde',prepared['data'],file_name=f"boutique_{prepared['created_at'][:10]}.zip",mime='application/zip')
            st.caption('Le logiciel ne peut pas vérifier que le téléchargement a été conservé sur votre appareil.')
            if st.button('J’ai téléchargé et conservé cette copie'):
                service.record_backup('confirmed',prepared['sha'],prepared['created_at'],user)
                st.success('Conservation confirmée. Vous pouvez contrôler le fichier ci-dessous.')
        st.subheader('Contrôler ou récupérer un fichier')
        uploaded = st.file_uploader('Sauvegarde ZIP ou JSON',type=['zip','json'],key='verified_backup_upload')
        if uploaded is None:
            return
        bundle, counts = parse_backup(uploaded.getvalue(),uploaded.name)
        st.write(f"Copie du {bundle.get('created_at','date inconnue')} · {sum(counts.values())} enregistrements · {len(bundle.get('private_documents',{}))} archives de documents")
        st.dataframe(pd.DataFrame([{'Données':k,'Nombre':v} for k,v in counts.items()]),hide_index=True)
        complete = set(counts)==set(db.BACKUP_TABLES)
        if not complete:
            st.warning('Cette sauvegarde est partielle : toutes les catégories ne sont pas présentes.')
        if st.button('Vérifier cette sauvegarde',disabled=not complete):
            service.record_backup('verified',service.digest(uploaded.getvalue()),bundle['created_at'],user)
            st.success('Structure, catégories et intégrité des fichiers contrôlées. Cette vérification ne remplace pas un essai de récupération.')
        st.caption('La récupération ajoute les éléments manquants sans remplacer les données ou les PDF originaux existants.')
        with st.form('verified_restore'):
            password = st.text_input('Mot de passe administrateur',type='password',autocomplete='off')
            confirmed = st.checkbox('Récupérer les éléments manquants de cette copie')
            if st.form_submit_button('Récupérer les données'):
                authenticated = db.authenticate(str(user['username']),password)
                if not authenticated or authenticated.get('role')!='admin':
                    st.error('Mot de passe administrateur incorrect.')
                elif not confirmed:
                    st.error('Cochez la confirmation pour continuer.')
                else:
                    result = db.restore_backup(bundle)
                    restored = result.get('restored',result)
                    st.success(f"Récupération terminée : {sum(int(v) for v in restored.values())} enregistrements ajoutés.")
    except Exception as error:
        show_error(error)
