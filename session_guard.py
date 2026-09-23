"""Idle lock: browser activity signals plus a server-side expiry gate."""
import time
from uuid import uuid4
from pathlib import Path
import streamlit as st

def start(user, timeout_seconds):
    st.session_state['_auth_nonce'] = uuid4().hex
    st.session_state['_auth_seen'] = time.monotonic()
    st.session_state['_auth_timeout'] = float(timeout_seconds)
    st.session_state['_auth_locked'] = False

def expired(state, now=None):
    now = time.monotonic() if now is None else now
    return bool(state.get('_auth_locked')) or now-float(state.get('_auth_seen', 0)) >= float(state.get('_auth_timeout', 300))

def clear_session(notice=False):
    # Remove receipts, generated downloads, draft forms and old passwords too.
    for key in list(st.session_state):
        del st.session_state[key]
    if notice:
        st.session_state['_lock_notice'] = True

def gate():
    if 'mobile_user' in st.session_state and expired(st.session_state):
        clear_session(notice=True)

def _activity():
    # A delayed/replayed event must never revive an expired session.
    if 'mobile_user' in st.session_state and not expired(st.session_state):
        st.session_state['_auth_seen'] = time.monotonic()
    else:
        st.session_state['_auth_locked'] = True

def _lock():
    st.session_state['_auth_locked'] = True

_activity_component = st.components.v2.component(
    'boutique_idle_guard', js=Path(__file__).with_name('idle_guard.js').read_text(encoding='utf-8'))

@st.fragment(run_every='10s')
def watch():
    if 'mobile_user' not in st.session_state or expired(st.session_state):
        clear_session(notice=True)
        st.rerun(scope='app')
    remaining = max(0, st.session_state['_auth_timeout']-(time.monotonic()-st.session_state['_auth_seen']))
    _activity_component(key='idle_guard_'+st.session_state['_auth_nonce'],
        data={'nonce':st.session_state['_auth_nonce'],'remaining_ms':int(remaining*1000), 'timeout_ms':int(st.session_state['_auth_timeout']*1000)},
        on_activity_change=_activity, on_locked_change=_lock)

def manual_lock():
    clear_session(notice=True)
