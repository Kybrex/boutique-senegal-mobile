"""Connexion Supabase privée pour Boutique Senegal.

Les identifiants restent uniquement dans les Secrets Streamlit et ne sont
jamais enregistrés dans GitHub.
"""
from __future__ import annotations

from functools import lru_cache


def is_configured() -> bool:
    try:
        import streamlit as st
        return bool(st.secrets.get("SUPABASE_URL") and st.secrets.get("SUPABASE_KEY"))
    except Exception:
        return False


@lru_cache(maxsize=1)
def client():
    """Retourne le client serveur Supabase, créé une seule fois."""
    import streamlit as st
    from supabase import create_client

    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
