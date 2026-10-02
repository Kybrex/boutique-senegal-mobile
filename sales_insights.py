"""Read-only sales filters and dashboard calculations."""
from datetime import timedelta
import unicodedata
import pandas as pd

COLUMNS = ['Ticket', 'Date', 'Vendeur', 'Client', 'Total', 'Reduction', 'Encaisse', 'Paiement']
STATES = ['Tous', 'Payée', 'Partiellement payée', 'Non payée']

def normalize(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(value)).casefold() if not unicodedata.combining(c))

def prepare(sales):
    result = sales.reindex(columns=COLUMNS).copy()
    for col in ('Total', 'Reduction', 'Encaisse'):
        result[col] = pd.to_numeric(result[col], errors='coerce').fillna(0)
    result['Reste'] = (result.Total - result.Encaisse).clip(lower=0)
    result['Etat'] = 'Payée'
    result.loc[result.Reste.gt(0) & result.Encaisse.gt(0), 'Etat'] = 'Partiellement payée'
    result.loc[result.Reste.gt(0) & result.Encaisse.le(0), 'Etat'] = 'Non payée'
    return result

def filter_sales(sales, search='', state='Tous', method='Tous', seller='Tous'):
    result = prepare(sales)
    if result.empty: return result
    if state != 'Tous': result = result.loc[result.Etat.eq(state)]
    if method != 'Tous': result = result.loc[result.Paiement.eq(method)]
    if seller != 'Tous': result = result.loc[result.Vendeur.eq(seller)]
    term = normalize(search.strip().lstrip('#'))
    if term:
        mask = result.Client.fillna('').map(normalize).str.contains(term, regex=False)
        mask |= result.Ticket.map(lambda x: str(int(x)) if pd.notna(x) else '').str.contains(term, regex=False)
        result = result.loc[mask]
    return result

def previous_period(start, end):
    if end < start: raise ValueError('La fin doit suivre le début de la période.')
    days = (end - start).days + 1
    return start - timedelta(days=days), start - timedelta(days=1)

def summarize(sales, start, end):
    data = prepare(sales)
    days = pd.date_range(start, end, freq='D')
    dates = pd.to_datetime(data.Date.astype(str).str[:10], errors='coerce')
    daily = data.assign(Jour=dates).groupby('Jour').Total.sum().reindex(days, fill_value=0)
    daily.index.name = 'Jour'
    payments = data.groupby('Paiement', dropna=False).agg(Ventes=('Total', 'sum'), Montant_paye=('Encaisse', 'sum'), Tickets=('Ticket', 'count')).reset_index()
    sellers = data.groupby('Vendeur', dropna=False).agg(Ventes=('Total', 'sum'), Tickets=('Ticket', 'count')).reset_index().sort_values('Ventes', ascending=False)
    return dict(total=float(data.Total.sum()), paid=float(data.Encaisse.sum()), remaining=float(data.Reste.sum()), tickets=len(data), average=float(data.Total.mean()) if len(data) else 0, daily=daily, payments=payments, sellers=sellers)
