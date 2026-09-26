from copy import deepcopy
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from test_catalog_ui import APP, check


def run():
    saved = {}
    def save(user, name, preset): saved[name] = deepcopy(preset)
    source = APP.replace("{'phone':'771234567'})", "{'phone':'771234567'}, {'id':1,'role':'admin'})")
    with patch('catalog_library.list_catalogs', side_effect=lambda user: deepcopy(saved)), patch('catalog_library.save_catalog', side_effect=save):
        app = AppTest.from_string(source, default_timeout=30)
        app.session_state['catalog_saved_options'] = {'details':{'1':{'Description':'Tissu résistant','Tailles':'M, L','Couleurs':'Bleu'}}}
        app.run()
        check(app)
        app.checkbox(key='catalog_show_prices').uncheck().run()
        app.text_input(key='catalog_title').set_value('Collection revendeurs').run()
        app.text_area(key='catalog_zones').set_value('Dakar').run()
        app.text_input(key='catalog_name').set_value('Revendeurs').run()
        app.button(key='catalog_save').click().run()
        check(app)
        assert saved['Revendeurs']['options']['details']['1']['Description'] == 'Tissu résistant'
        assert 'Revendeurs' in app.selectbox(key='catalog_library_choice').options
        # Reconnect with a fresh session and restore durable settings.
        app = AppTest.from_string(source, default_timeout=30).run()
        app.selectbox(key='catalog_library_choice').select('Revendeurs').run()
        app.button(key='load_catalog_preset').click().run()
        check(app)
        assert app.text_input(key='catalog_title').value == 'Collection revendeurs'
        assert app.checkbox(key='catalog_show_prices').value is False
        assert app.text_area(key='catalog_zones').value == 'Dakar'
        assert app.dataframe[0].value.iloc[0].Description == 'Tissu résistant'
        app.button(key='catalog_build').click().run()
        check(app)
        assert len(app.get('download_button')) == 1
        app.run()
        check(app)
        assert len(app.get('download_button')) == 1
    print('PASS: descriptions, save, fresh-session load, no-price setting and persistent download')


if __name__ == '__main__': run()
