"""Regression coverage for activity reruns and interrupted PDF preparation."""
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import patch
import importlib.util
import sys
import pandas as pd


class Screen:
    def __init__(self):
        self.session_state = {}
        self.column_config = SimpleNamespace(NumberColumn=lambda *a, **kw: None)
        self.clicked = False
        self.phone = '771234567'
        self.downloads = []
        self.errors = []
    def caption(self, *a): pass
    def info(self, *a): pass
    def success(self, *a): pass
    def error(self, message): self.errors.append(message)
    def checkbox(self, *a, **kw): return True
    def multiselect(self, *a, **kw): return kw['default']
    def text_input(self, *a, **kw): return self.phone
    def date_input(self, *a, **kw): return kw['value']
    def data_editor(self, data, **kw): return data
    def button(self, *a, **kw):
        clicked, self.clicked = self.clicked, False
        return clicked
    def spinner(self, *a): return nullcontext()
    def download_button(self, label, data, **kw): self.downloads.append(data)


def run():
    screen = Screen()
    # Import the production panel with only Streamlit's UI surface substituted.
    spec = importlib.util.spec_from_file_location('panel_under_test', 'catalog_ui.py')
    panel = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {'streamlit': screen}):
        spec.loader.exec_module(panel)
    products = pd.DataFrame([{'id':1,'Produit':'Sac','Categorie':'Sacs','Vente':15000,'Stock':2,'Photo':''}])
    def render():
        screen.downloads.clear()
        panel.catalog_panel(products, {})
    with patch.object(panel, 'make_catalog_pdf', return_value=b'%PDF-test') as build:
        render()
        assert not screen.downloads
        screen.clicked = True
        render()
        assert screen.downloads == [b'%PDF-test']
        render()
        assert screen.downloads == [b'%PDF-test'] and build.call_count == 1
        products.loc[0, 'Vente'] = 16000
        render()
        assert not screen.downloads
        screen.clicked = True
        render()
        assert screen.downloads and build.call_count == 2
    with patch.object(panel, 'make_catalog_pdf', side_effect=ValueError('bad image')):
        screen.clicked = True
        render()
        assert screen.errors and not screen.downloads
    class Rerun(BaseException): pass
    with patch.object(panel, 'make_catalog_pdf', side_effect=Rerun):
        screen.clicked = True
        try:
            render()
        except Rerun:
            pass
    with patch.object(panel, 'make_catalog_pdf', return_value=b'%PDF-retry') as build:
        render()
        assert screen.downloads == [b'%PDF-retry'] and build.call_count == 1
    print('PASS: download persists, no duplicate build, changed prices invalidate, errors visible, interrupted build resumes')


if __name__ == '__main__':
    run()
