"""Connexion Supabase privée pour Boutique Senegal.

Les identifiants restent uniquement dans les Secrets Streamlit et ne sont
jamais enregistrés dans GitHub.
"""
from __future__ import annotations

from functools import lru_cache


def configuration_error() -> str | None:
    """Valide les secrets avant de créer les en-têtes HTTP Supabase."""
    try:
        import streamlit as st
        url = str(st.secrets.get("SUPABASE_URL", "")).strip()
        key = str(st.secrets.get("SUPABASE_KEY", "")).strip()
    except Exception:
        return None
    if not url and not key:
        return None
    if not url or not key:
        return "SUPABASE_URL et SUPABASE_KEY doivent être renseignés ensemble."
    if not url.startswith("https://") or ".supabase.co" not in url:
        return "SUPABASE_URL n'est pas une URL de projet Supabase valide."
    try:
        key.encode("ascii")
    except UnicodeEncodeError:
        return "SUPABASE_KEY contient des accents ou des caractères spéciaux. Collez la vraie clé secrète Supabase, sans texte d'exemple."
    if "nouvelle" in key.lower() or "votre" in key.lower() or len(key) < 30:
        return "SUPABASE_KEY semble être un texte d'exemple. Collez la vraie clé sb_secret_ créée dans Supabase."
    return None


def is_configured() -> bool:
    try:
        import streamlit as st
        return bool(st.secrets.get("SUPABASE_URL") and st.secrets.get("SUPABASE_KEY") and not configuration_error())
    except Exception:
        return False


@lru_cache(maxsize=1)
def client():
    """Retourne le client serveur Supabase, créé une seule fois."""
    import streamlit as st
    from supabase import create_client

    url = str(st.secrets["SUPABASE_URL"]).strip()
    key = str(st.secrets["SUPABASE_KEY"]).strip()
    error = configuration_error()
    if error:
        raise ValueError(error)
    return create_client(url, key)
