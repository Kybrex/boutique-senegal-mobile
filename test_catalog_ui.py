from streamlit.testing.v1 import AppTest

APP = '''
import pandas as pd
from catalog_ui import catalog_panel
catalog_panel(pd.DataFrame([
    {'id':1,'Produit':'Sac','Categorie':'Bagagerie','Vente':15000.,'Stock':3,'Photo':''},
    {'id':2,'Produit':'Casque','Categorie':'Audio','Vente':10000.,'Stock':0,'Photo':''},
]), {'phone':'771234567'})
'''

def check(app):
    assert not app.exception, [x.message for x in app.exception]

def run():
    app = AppTest.from_string(APP, default_timeout=30).run()
    check(app)
    assert app.multiselect[1].value == [1]
    app.checkbox[0].uncheck().run()
    check(app)
    app.multiselect[0].set_value(['Audio','Bagagerie']).run()
    app.multiselect[1].set_value([2]).run()
    check(app)
    app.button[0].click().run()
    check(app)
    assert len(app.get('download_button')) == 1
    app.text_input[0].set_value('invalid').run()
    check(app)
    assert app.error and not app.button
    app.text_input[0].set_value('771234567').run()
    app.multiselect[1].set_value([]).run()
    check(app)
    assert not app.button
    print('PASS: stock filter, categories, product selection, PDF generation and invalid phone')

if __name__ == '__main__':
    run()
