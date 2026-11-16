# Copyright 2026 Riccardo Di Maio - M0V3 S.r.l. Tutti i diritti riservati.
# Proprietary Sports Science & Clinical Performance Intelligence Architecture.
import os
import datetime
import importlib
import urllib.parse
import base64
import streamlit as st
import streamlit.components.v1 as components
from streamlit_option_menu import option_menu

import config
try:
    importlib.reload(config)
except Exception:
    pass

from config import (
    LOGO_PATH,
    LOGO_CIRCULAR_PATH,
    CYBER_BG_PATH,
    DB_PARQUET_PATH,
    LANG,
    tr,
    setup_plotly_theme,
    get_base64_image,
    add_custom_css,
    PAGINE_OPERATIVE,
    AREA_TO_PAGINA,
)

import utils
if (
    not hasattr(utils, "check_and_render_notifications")
    or not hasattr(utils, "set_notification")
    or not hasattr(utils, "render_m0v3_footer")
    or not hasattr(utils, "sync_binary_snapshots_on_cold_boot")
    or not hasattr(utils, "get_cloud_snapshot_status")
    or not hasattr(utils, "upload_binary_snapshot")
):
    try:
        import importlib
        importlib.reload(utils)
    except Exception:
        pass

try:
    from utils import render_m0v3_footer
except ImportError:
    from config import render_m0v3_footer

from utils import (
    supabase,
    supabase_admin,
    ensure_valid_session,
    get_atleta_dettagli_per_utente,
    get_lista_atleti_disponibili,
    check_stato_giornaliero_atleta,
)
check_and_render_notifications = getattr(
    utils,
    "check_and_render_notifications",
    lambda: None,
)
set_notification = getattr(
    utils,
    "set_notification",
    lambda *args, **kwargs: None,
)
notify_success = getattr(
    utils,
    "notify_success",
    lambda *args, **kwargs: None,
)
get_cloud_snapshot_status = getattr(
    utils,
    "get_cloud_snapshot_status",
    lambda: {"active": True, "max_date": "N/D", "total_rows": 0},
)
sync_binary_snapshots_on_cold_boot = getattr(
    utils,
    "sync_binary_snapshots_on_cold_boot",
    lambda: {"synced": False},
)

DEV_MODE = os.environ.get("MOV3_DEV_MODE", "1") == "1"

def _load_view(mod):
    if DEV_MODE:
        try:
            importlib.reload(mod)
        except Exception:
            pass
    return mod

try:
    from views import (
        render_home,
        render_profilo,
        render_admin,
        render_caricamento_dati,
        render_generatore_dati,
        render_gestione_file,
        render_medie,
        render_analisi_match,
        render_analisi_sessione,
        render_trend_settimanale,
        render_trend_stagionale,
        render_storico_match,
        render_statistiche_match,
    )
except ImportError:
    from views.home import render_home
    from views.profilo import render_profilo
    from views.admin import render_admin
    from views.caricamento_dati import render_caricamento_dati
    from views.statistiche_match import render_statistiche_match
    from views.generatore_dati import render_generatore_dati
    from views.gestione_file import render_gestione_file
    from views.medie import render_medie
    from views.analisi_match import render_analisi_match
    from views.analisi_sessione import render_analisi_sessione
    from views.trend_settimanale import render_trend_settimanale
    from views.trend_stagionale import render_trend_stagionale
    from views.storico_match import render_storico_match

# --- Stile unico per tutti i grafici Plotly ---
setup_plotly_theme()

# =========================================================================
# CONFIGURAZIONE PAGINA E CSS FONT/FILIGRANA/STAMPA
# =========================================================================
st.set_page_config(page_title="M0V3 Analytics", page_icon=LOGO_PATH, layout="wide", initial_sidebar_state="expanded")

if 'lang' not in st.session_state: st.session_state['lang'] = 'IT'
if 'user' not in st.session_state: st.session_state['user'] = None
if 'role' not in st.session_state: st.session_state['role'] = None
if 'privacy_accettata' not in st.session_state: st.session_state['privacy_accettata'] = False
if 'has_accepted_terms' not in st.session_state: st.session_state['has_accepted_terms'] = False
if 'terms_accepted_at' not in st.session_state: st.session_state['terms_accepted_at'] = ''
if 'terms_version' not in st.session_state: st.session_state['terms_version'] = 'M0V3_IP_GDPR_v2.0'

add_custom_css(LOGO_CIRCULAR_PATH)

# =========================================================================
# GESTIONE NOTIFICHE UNIFICATE M0V3 (OPZIONE 3: MODAL & TOAST HUD)
# =========================================================================
check_and_render_notifications()

# =========================================================================
# AUTENTICAZIONE E RICHIESTA SUPPORTO PASSWORD A M0V3
# =========================================================================
def auth_module():
    # Se il server ha rilevato un token non valido o scaduto, pulisci localStorage e cookie per evitare loop
    if st.session_state.get('clear_invalid_token'):
        st.session_state['clear_invalid_token'] = False
        components.html("""
        <script>
        (function() {
            try {
                var p = window.parent || window;
                try { p.localStorage.removeItem("m0v3_rt"); } catch(e) {}
                try { localStorage.removeItem("m0v3_rt"); } catch(e) {}
                try { sessionStorage.removeItem("m0v3_auth_tried"); } catch(e) {}
                try { document.cookie = "m0v3_rt=; path=/; max-age=0;"; } catch(e) {}
                if (p.document) { try { p.document.cookie = "m0v3_rt=; path=/; max-age=0;"; } catch(e) {} }
            } catch(e) {}
        })();
        </script>
        """, height=0)
    else:
        # Auto-ripristino sessione persistente via localStorage/parent-cookie su reload/refresh (solo una volta per tab)
        if not st.session_state.get('logged_out', False) and st.query_params.get('logged_out') != '1':
            components.html("""
            <script>
            (function() {
                try {
                    var p = window.parent || window;
                    var tried = null;
                    try { tried = sessionStorage.getItem("m0v3_auth_tried"); } catch(e) {}
                    if (tried === "1") return;

                    var token = null;
                    try { token = p.localStorage.getItem("m0v3_rt"); } catch(e) {}
                    if (!token) {
                        try { token = localStorage.getItem("m0v3_rt"); } catch(e) {}
                    }
                    if (!token) {
                        try {
                            var m = (p.document.cookie || document.cookie).match(/(?:^|; )m0v3_rt=([^;]*)/);
                            if (m) token = decodeURIComponent(m[1]);
                        } catch(e) {}
                    }
                    if (token && token.length > 10) {
                        try { sessionStorage.setItem("m0v3_auth_tried", "1"); } catch(e) {}
                        var curUrl = new URL(p.location.href);
                        if (!curUrl.searchParams.has("m0v3_rt") && !curUrl.searchParams.has("logged_out")) {
                            curUrl.searchParams.set("m0v3_rt", token);
                            p.location.replace(curUrl.href);
                        }
                    }
                } catch(e) {}
            })();
            </script>
            """, height=0)

    logo_b64 = get_base64_image(LOGO_CIRCULAR_PATH)
    if not logo_b64:
        logo_b64 = get_base64_image(LOGO_PATH)

    # SVG Campo da Tennis Stilizzato Wireframe Neon (Blueprint M0V3)
    svg_tennis_court = (
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1400 700' fill='none'>"
        "<defs>"
        "<radialGradient id='courtGlow' cx='50%' cy='50%' r='50%'>"
        "<stop offset='0%' stop-color='#0ea5e9' stop-opacity='0.16'/>"
        "<stop offset='65%' stop-color='#0ea5e9' stop-opacity='0.04'/>"
        "<stop offset='100%' stop-color='#0ea5e9' stop-opacity='0'/>"
        "</radialGradient>"
        "<linearGradient id='courtLine' x1='0%' y1='0%' x2='100%' y2='0%'>"
        "<stop offset='0%' stop-color='#38bdf8' stop-opacity='0.35'/>"
        "<stop offset='50%' stop-color='#38bdf8' stop-opacity='0.55'/>"
        "<stop offset='100%' stop-color='#38bdf8' stop-opacity='0.35'/>"
        "</linearGradient>"
        "</defs>"
        "<rect x='100' y='60' width='1200' height='580' fill='url(#courtGlow)' rx='14'/>"
        "<rect x='100' y='60' width='1200' height='580' stroke='url(#courtLine)' stroke-width='2'/>"
        "<line x1='100' y1='132' x2='1300' y2='132' stroke='rgba(56, 189, 248, 0.28)' stroke-width='1.5'/>"
        "<line x1='100' y1='568' x2='1300' y2='568' stroke='rgba(56, 189, 248, 0.28)' stroke-width='1.5'/>"
        "<line x1='700' y1='36' x2='700' y2='664' stroke='#38bdf8' stroke-width='2.5' stroke-dasharray='7 4' opacity='0.7'/>"
        "<circle cx='700' cy='36' r='5' fill='#38bdf8' opacity='0.9'/>"
        "<circle cx='700' cy='664' r='5' fill='#38bdf8' opacity='0.9'/>"
        "<line x1='377' y1='132' x2='377' y2='568' stroke='rgba(56, 189, 248, 0.32)' stroke-width='1.5'/>"
        "<line x1='1023' y1='132' x2='1023' y2='568' stroke='rgba(56, 189, 248, 0.32)' stroke-width='1.5'/>"
        "<line x1='377' y1='350' x2='1023' y2='350' stroke='rgba(56, 189, 248, 0.32)' stroke-width='1.5'/>"
        "<line x1='100' y1='350' x2='125' y2='350' stroke='rgba(56, 189, 248, 0.45)' stroke-width='2.2'/>"
        "<line x1='1275' y1='350' x2='1300' y2='350' stroke='rgba(56, 189, 248, 0.45)' stroke-width='2.2'/>"
        "<circle cx='700' cy='350' r='7' fill='none' stroke='#38bdf8' stroke-width='1.5' opacity='0.6'/>"
        "<circle cx='700' cy='350' r='2.5' fill='#38bdf8' opacity='0.95'/>"
        "</svg>"
    )
    court_b64 = base64.b64encode(svg_tennis_court.encode('utf-8')).decode('utf-8')

    # Sfondo Dark Cyber High-Tech M0V3 & Minimal Executive Glassmorphism Card
    st.markdown(f"""
    <style>
    /* 1. Sfondo Dark Cyber High-Tech M0V3 con Blueprint Campo Tennis */
    .stApp {{
        background-color: #060b14 !important;
        background-image: 
            radial-gradient(ellipse at 50% 12%, rgba(14, 165, 233, 0.18) 0%, rgba(6, 11, 20, 0.88) 60%, #030712 100%),
            url("data:image/svg+xml;base64,{court_b64}") !important;
        background-position: center top, center center !important;
        background-repeat: no-repeat, no-repeat !important;
        background-size: 100% 100%, min(1280px, 92vw) auto !important;
        background-attachment: fixed, fixed !important;
        min-height: 100vh !important;
        overflow-x: hidden !important;
    }}

    /* 2. Disabilita watermark aggiuntivo */
    [data-testid="stAppViewContainer"]::before {{
        display: none !important;
        content: "" !important;
    }}

    /* 3. Centratura e Dimensionamento Minimal Executive */
    .block-container {{
        max-width: 500px !important;
        padding-top: 7vh !important;
        padding-bottom: 5vh !important;
        margin: 0 auto !important;
        position: relative !important;
        z-index: 10 !important;
    }}

    @media (max-width: 640px) {{
        .block-container {{
            max-width: 94% !important;
            padding-top: 4vh !important;
            padding-bottom: 3vh !important;
        }}
    }}

    /* 4. Card Glassmorphism ad Alto Contrasto Dark */
    div[data-testid="stVerticalBlockBorderWrapper"] {{
        background: linear-gradient(165deg, rgba(13, 23, 42, 0.94) 0%, rgba(8, 15, 28, 0.98) 100%) !important;
        backdrop-filter: blur(28px) !important;
        -webkit-backdrop-filter: blur(28px) !important;
        border: 1px solid rgba(56, 189, 248, 0.28) !important;
        border-radius: 24px !important;
        box-shadow: 0 25px 60px -15px rgba(0, 0, 0, 0.85), 0 0 50px rgba(14, 165, 233, 0.16) !important;
        padding: 36px 30px !important;
    }}

    [data-testid="stForm"] {{
        border: none !important;
        padding: 0 !important;
    }}

    /* 5. Campi Input ed Etichette */
    .stTextInput label, [data-testid="stWidgetLabel"] p {{
        color: #e2e8f0 !important;
        font-weight: 700 !important;
        font-size: 13px !important;
        letter-spacing: 0.3px !important;
        margin-bottom: 4px !important;
    }}

    div[data-baseweb="input"],
    div[data-baseweb="base-input"],
    .stTextInput > div > div,
    .stTextInput input {{
        background-color: #081120 !important;
        color: #ffffff !important;
        -webkit-text-fill-color: #ffffff !important;
        caret-color: #38bdf8 !important;
        border: 1px solid rgba(56, 189, 248, 0.35) !important;
        border-radius: 12px !important;
        font-size: 14.5px !important;
        transition: all 0.2s ease !important;
    }}

    div[data-baseweb="input"]:focus-within,
    .stTextInput input:focus {{
        background-color: #0d1a32 !important;
        border-color: #38bdf8 !important;
        box-shadow: 0 0 0 3px rgba(14, 165, 233, 0.35), 0 0 15px rgba(56, 189, 248, 0.2) !important;
        outline: none !important;
    }}

    .stTextInput input::placeholder {{
        color: #64748b !important;
        -webkit-text-fill-color: #64748b !important;
    }}

    /* Previene lo sfondo bianco/giallo dell'autofill di Chrome/Safari */
    .stTextInput input:-webkit-autofill,
    .stTextInput input:-webkit-autofill:hover, 
    .stTextInput input:-webkit-autofill:focus,
    .stTextInput input:-webkit-autofill:active {{
        -webkit-text-fill-color: #ffffff !important;
        -webkit-box-shadow: 0 0 0px 1000px #081120 inset !important;
        box-shadow: 0 0 0px 1000px #081120 inset !important;
        transition: background-color 5000s ease-in-out 0s !important;
    }}

    .stTextInput button {{
        color: #94a3b8 !important;
    }}
    .stTextInput button:hover {{
        color: #38bdf8 !important;
    }}

    /* Previene auto-zoom su iOS Safari forzando font-size >= 16px */
    input, select, textarea,
    .stTextInput input, .stNumberInput input {{
        font-size: 16px !important;
    }}

    /* 6. Pulsante "Accedi" Premium con Glow Neon dinamico */
    .stFormSubmitButton button, button[kind="primaryFormSubmit"] {{
        background: linear-gradient(135deg, #0284c7 0%, #0ea5e9 50%, #38bdf8 100%) !important;
        color: #ffffff !important;
        font-weight: 800 !important;
        font-size: 15px !important;
        border: 1px solid rgba(255, 255, 255, 0.2) !important;
        border-radius: 12px !important;
        padding: 13px 22px !important;
        letter-spacing: 0.6px !important;
        box-shadow: 0 4px 20px rgba(14, 165, 233, 0.35), 0 0 10px rgba(56, 189, 248, 0.2) !important;
        transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1) !important;
        margin-top: 10px !important;
    }}
    .stFormSubmitButton button:hover, button[kind="primaryFormSubmit"]:hover {{
        background: linear-gradient(135deg, #0ea5e9 0%, #38bdf8 100%) !important;
        box-shadow: 0 8px 30px rgba(14, 165, 233, 0.65), 0 0 25px rgba(56, 189, 248, 0.5) !important;
        transform: translateY(-2px) !important;
        border-color: rgba(255, 255, 255, 0.4) !important;
    }}
    .stFormSubmitButton button:active, button[kind="primaryFormSubmit"]:active {{
        transform: translateY(0px) !important;
        box-shadow: 0 3px 12px rgba(14, 165, 233, 0.4) !important;
    }}

    /* 7. Link e Box "Password Dimenticata?" */
    [data-testid="stExpander"] {{
        border: none !important;
        background: transparent !important;
        margin-top: 14px !important;
    }}
    [data-testid="stExpander"] summary {{
        color: #38bdf8 !important;
        font-size: 13.5px !important;
        font-weight: 700 !important;
        justify-content: center !important;
        border-radius: 8px !important;
        padding: 6px 12px !important;
        transition: all 0.15s ease !important;
    }}
    [data-testid="stExpander"] summary:hover {{
        color: #7dd3fc !important;
        background-color: rgba(56, 189, 248, 0.10) !important;
    }}
    [data-testid="stExpander"] summary svg {{
        fill: #38bdf8 !important;
    }}
    [data-testid="stExpander"] [data-testid="stExpanderDetails"] {{
        background: rgba(8, 15, 28, 0.95) !important;
        border: 1px solid rgba(56, 189, 248, 0.22) !important;
        border-radius: 14px !important;
        padding: 18px !important;
        margin-top: 8px !important;
        box-shadow: 0 10px 25px rgba(0, 0, 0, 0.5) !important;
    }}

    [data-testid="stAlert"] {{
        background-color: rgba(14, 165, 233, 0.15) !important;
        border: 1px solid rgba(56, 189, 248, 0.35) !important;
        border-radius: 10px !important;
        color: #e2e8f0 !important;
    }}
    [data-testid="stAlert"] p, [data-testid="stAlert"] span {{
        color: #e2e8f0 !important;
        font-size: 12.5px !important;
    }}
    [data-testid="stAlert"] svg {{
        fill: #38bdf8 !important;
    }}

    /* Pulsante secondario invio richiesta dentro expander */
    [data-testid="stExpander"] .stButton button {{
        background: linear-gradient(135deg, #0ea5e9 0%, #0284c7 100%) !important;
        color: #ffffff !important;
        font-weight: 800 !important;
        font-size: 13.5px !important;
        border: none !important;
        border-radius: 8px !important;
        margin-top: 6px !important;
    }}
    </style>
    """, unsafe_allow_html=True)

    with st.container(border=True):
        col_auth_sp, col_auth_lang = st.columns([3, 1.2])
        with col_auth_lang:
            curr_l = st.session_state.get('lang', 'IT')
            sel_auth_l = st.radio(
                "Auth Lang",
                ["IT", "EN"],
                index=0 if curr_l == 'IT' else 1,
                horizontal=True,
                key="auth_lang_switch",
                label_visibility="collapsed"
            )
            if sel_auth_l != curr_l:
                st.session_state['lang'] = sel_auth_l
                st.rerun()

        st.markdown(f"""
        <div style='text-align: center; margin-bottom: 22px;'>
            <img src='data:image/png;base64,{logo_b64}' style='width: 82px; height: 82px; border-radius: 50%; box-shadow: 0 0 32px rgba(14, 165, 233, 0.55); border: 2px solid rgba(56, 189, 248, 0.35); display: inline-block; margin-bottom: 12px;'>
            <div style='font-size: 11px; letter-spacing: 2.8px; text-transform: uppercase; color: #38bdf8; font-weight: 800; margin-bottom: 4px;'>PERFORMANCE ANALYTICS</div>
            <h1 style='color: #ffffff; font-size: 34px; font-weight: 900; line-height: 1.15; margin: 0 0 8px 0; letter-spacing: -0.8px; text-shadow: 0 0 24px rgba(14, 165, 233, 0.45);'>MOV3 Analytics</h1>
            <p style='color: #94a3b8; font-size: 13.5px; margin: 0;'>{tr("Improve your Game · Inserisci le credenziali", "Improve your Game · Enter your credentials")}</p>
        </div>
        """, unsafe_allow_html=True)

        with st.form("login_form"):
            email = st.text_input(tr("Email", "Email"), autocomplete="username", key="login_email")
            password = st.text_input(tr("Password", "Password"), type="password", autocomplete="current-password", key="login_password")
            if st.form_submit_button(tr("Accedi", "Sign In"), type="primary", use_container_width=True):
                try:
                    try: supabase.auth.sign_out()
                    except: pass

                    res = supabase.auth.sign_in_with_password({"email": email, "password": password})
                    st.session_state['user'] = res.user
                    st.session_state['logged_out'] = False
                    if 'logged_out' in st.query_params:
                        del st.query_params['logged_out']
                    if hasattr(res, 'session') and res.session and hasattr(res.session, 'refresh_token'):
                        st.session_state['refresh_token'] = res.session.refresh_token

                    profilo = supabase.table('profili').select('*').eq('id', res.user.id).execute()
                    if profilo.data:
                        p_row = profilo.data[0]
                        st.session_state['role'] = p_row.get('ruolo', 'Atleta')
                        has_acc = bool(p_row.get('has_accepted_terms') or p_row.get('privacy_accettata', False))
                        st.session_state['has_accepted_terms'] = has_acc
                        st.session_state['privacy_accettata'] = has_acc
                        st.session_state['terms_accepted_at'] = p_row.get('terms_accepted_at', '')
                        st.session_state['terms_version'] = p_row.get('terms_version', 'M0V3_IP_GDPR_v2.0')
                    else:
                        st.session_state['role'] = 'Atleta'
                        st.session_state['has_accepted_terms'] = False
                        st.session_state['privacy_accettata'] = False
                        st.session_state['terms_accepted_at'] = ''
                        st.session_state['terms_version'] = 'M0V3_IP_GDPR_v2.0'
                    st.rerun()
                except Exception as e:
                    st.error(tr("Credenziali errate o sessione scaduta. Riprova.", "Invalid credentials or session expired. Try again."))

        with st.expander(tr("Password dimenticata?", "Forgot password?")):
            st.info(tr("Inserisci la tua email e invia la richiesta al team M0V3. Verrai ricontattato con una password provvisoria.", "Enter your email to send a request to M0V3. You will receive a temporary password shortly."))
            req_email = st.text_input(tr("La tua Email registrata", "Your registered Email"), key="req_mail_m0v3")

            if st.button(tr("Invia richiesta a M0V3", "Send request to M0V3"), type="primary", use_container_width=True):
                if req_email:
                    try:
                        supabase.table('richieste_reset').insert({"email": req_email.strip()}).execute()
                        st.success(tr("Richiesta inviata. L'amministratore resetterà la tua password al più presto.", "Request sent. The administrator will reset your password shortly."))
                    except Exception as e:
                        err_lbl = tr("Errore durante l'invio della richiesta:", "Error sending request:")
                        st.error(f"{err_lbl} {e}")
                else:
                    st.warning(tr("Inserisci un indirizzo email valido.", "Please enter a valid email address."))

        components.html("""
            <script>
            (function() {
                const doc = window.parent.document;
                function bindAutofillAttrs() {
                    const emailInput = doc.querySelector('input[aria-label="Email"]');
                    const pwdInput = doc.querySelector('input[aria-label="Password"]');
                    if (emailInput) {
                        emailInput.setAttribute('type', 'email');
                        emailInput.setAttribute('name', 'username');
                        emailInput.setAttribute('autocomplete', 'username');
                    }
                    if (pwdInput) {
                        pwdInput.setAttribute('name', 'password');
                        pwdInput.setAttribute('autocomplete', 'current-password');
                    }
                }
                bindAutofillAttrs();
                setTimeout(bindAutofillAttrs, 150);
                setTimeout(bindAutofillAttrs, 500);
            })();
            </script>
        """, height=0)


# =========================================================================
# APP MAIN
# =========================================================================
def main():
    if not st.session_state.get('user'):
        # 1. Recupero sessione automatica da cookie persistente o query param (anti-pull-to-refresh / reload)
        # Se l'utente ha cliccato esplicitamente "Logout", non auto-ricollegare
        if not st.session_state.get('logged_out', False) and st.query_params.get('logged_out') != '1':
            rt_cookie = None
            if hasattr(st, 'context') and hasattr(st.context, 'cookies'):
                rt_cookie = st.context.cookies.get('m0v3_rt')
            if not rt_cookie and 'm0v3_rt' in st.query_params:
                rt_cookie = st.query_params.get('m0v3_rt')
            if rt_cookie:
                try:
                    res = supabase.auth.refresh_session(rt_cookie)
                    if res and res.user:
                        st.session_state['user'] = res.user
                        st.session_state['logged_out'] = False
                        if hasattr(res, 'session') and res.session and hasattr(res.session, 'refresh_token'):
                            st.session_state['refresh_token'] = res.session.refresh_token
                        profilo = supabase.table('profili').select('*').eq('id', res.user.id).execute()
                        if profilo.data:
                            p_row = profilo.data[0]
                            st.session_state['role'] = p_row.get('ruolo', 'Atleta')
                            has_acc = bool(p_row.get('has_accepted_terms') or p_row.get('privacy_accettata', False))
                            st.session_state['has_accepted_terms'] = has_acc
                            st.session_state['privacy_accettata'] = has_acc
                            st.session_state['terms_accepted_at'] = p_row.get('terms_accepted_at', '')
                            st.session_state['terms_version'] = p_row.get('terms_version', 'M0V3_IP_GDPR_v2.0')
                        else:
                            st.session_state['role'] = 'Atleta'
                            st.session_state['has_accepted_terms'] = False
                            st.session_state['privacy_accettata'] = False
                            st.session_state['terms_accepted_at'] = ''
                            st.session_state['terms_version'] = 'M0V3_IP_GDPR_v2.0'
                        if 'm0v3_rt' in st.query_params:
                            del st.query_params['m0v3_rt']
                        st.rerun()
                except Exception:
                    st.session_state['clear_invalid_token'] = True
                    if 'm0v3_rt' in st.query_params:
                        del st.query_params['m0v3_rt']

        auth_module()
        return

    # Iniezione cookie persistente e reset zoom / scroll su mobile
    if st.session_state.get('refresh_token'):
        rt = st.session_state['refresh_token']
        cookie_js = """
        <script>
        (function() {
            try {
                var token = "__TOKEN__";
                var cookieStr = "m0v3_rt=" + encodeURIComponent(token) + "; path=/; max-age=2592000; SameSite=Lax";
                document.cookie = cookieStr;
                try { localStorage.setItem("m0v3_rt", token); } catch(e) {}
                try { sessionStorage.removeItem("m0v3_auth_tried"); } catch(e) {}
                if (window.parent && window.parent !== window) {
                    try { window.parent.document.cookie = cookieStr; } catch(e) {}
                    try { window.parent.localStorage.setItem("m0v3_rt", token); } catch(e) {}
                    try { window.parent.sessionStorage.removeItem("m0v3_auth_tried"); } catch(e) {}
                }
                window.scrollTo(0, 0);
                if (window.parent) {
                    window.parent.scrollTo(0, 0);
                    var meta = window.parent.document.querySelector('meta[name="viewport"]');
                    if (meta) {
                        meta.setAttribute('content', 'width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no');
                    }
                }
            } catch(e) {}
        })();
        </script>
        """.replace("__TOKEN__", str(rt))
        components.html(cookie_js, height=0)

    if not ensure_valid_session() or not st.session_state.get('user'):
        st.session_state['user'] = None
        st.session_state['role'] = None
        st.session_state['refresh_token'] = None
        auth_module()
        return

    user_obj = st.session_state.get('user')
    user_id = getattr(user_obj, 'id', None) if user_obj else None

    user_has_accepted = bool(st.session_state.get('has_accepted_terms') or st.session_state.get('privacy_accettata', False))

    if not user_has_accepted:
        # BLOCCO ESCLUSIVO DI ACCETTAZIONE AL PRIMO ACCESSO (CLICKWRAP AGREEMENT)
        target_logo = LOGO_CIRCULAR_PATH if os.path.exists(LOGO_CIRCULAR_PATH) else (LOGO_PATH if os.path.exists(LOGO_PATH) else None)
        if target_logo:
            logo_b64 = get_base64_image(target_logo)
            st.markdown(f"""
            <div style='text-align: center; padding: 10px 0 16px 0;'>
                <img src='data:image/png;base64,{logo_b64}'
                     alt='M0V3 Analytics'
                     style='width: 140px; max-width: 80%; height: auto; display: block; margin: 0 auto; filter: drop-shadow(0 4px 14px rgba(14, 165, 233, 0.4));'>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("""
        <div style='text-align: center; margin-bottom: 24px;'>
            <div style='font-size: 22px; font-weight: 900; color: #0f172a; font-family: "Inter", sans-serif; letter-spacing: -0.5px;'>
                Termini d'Uso, Riservatezza Clinica e Proprietà Intellettuale — M0V3 Analytics Enterprise
            </div>
            <div style='font-size: 13px; color: #0284c7; font-weight: 700; margin-top: 4px; text-transform: uppercase; letter-spacing: 0.8px;'>
                Accordo Obbligatorio al Primo Accesso (Versione Normativa: M0V3_IP_GDPR_v2.0)
            </div>
        </div>
        """, unsafe_allow_html=True)

        with st.container(border=True):
            st.markdown("""
            <div style='font-size: 13.5px; line-height: 1.6; color: #1e293b; font-family: "Inter", sans-serif; margin-bottom: 16px;'>
                Benvenuto nella piattaforma scientifica <b>M0V3 Analytics Enterprise</b>. L'accesso a questo sistema è strettamente personale, tracciato e riservato agli utenti autorizzati. Prima di procedere, ti invitiamo a leggere e accettare le seguenti condizioni operative:
            </div>
            """, unsafe_allow_html=True)

            st.markdown("""
            <div style='background: rgba(2, 132, 199, 0.04); border-left: 4px solid #0284c7; padding: 14px 16px; border-radius: 6px; margin-bottom: 14px;'>
                <div style='font-size: 14px; font-weight: 800; color: #0f172a; margin-bottom: 6px;'>
                    1. Proprietà Intellettuale e Licenza d'Uso
                </div>
                <div style='font-size: 12.5px; line-height: 1.55; color: #334155; text-align: justify;'>
                    Questa piattaforma web, incluse le architetture di database, le logiche di calcolo del microciclo e macrociclo, gli algoritmi proprietari (Readiness SWC, Pure I:E Ratio, Metriche Per-Point, ACWR Uncoupled EWMA, ripartizione carichi 70/30 e matrici di correlazione clinica) e le interfacce grafiche, costituisce tecnologia proprietaria esclusiva di <b>Riccardo Di Maio — M0V3 S.r.l.</b> Il sistema è concesso in mero utilizzo funzionale temporaneo. È severamente vietato riprodurre, copiare, catturare schermate a fini divulgativi, analizzare (reverse engineering) o cedere l'accesso a terze parti senza l'esplicita autorizzazione scritta dell'autore.
                </div>
            </div>
            """, unsafe_allow_html=True)

            st.markdown("""
            <div style='background: rgba(16, 185, 129, 0.04); border-left: 4px solid #10b981; padding: 14px 16px; border-radius: 6px; margin-bottom: 14px;'>
                <div style='font-size: 14px; font-weight: 800; color: #0f172a; margin-bottom: 6px;'>
                    2. Trattamento dei Dati Sensibili, Biometrici e Sanitari (Art. 9 Reg. UE 2016/679 - GDPR)
                </div>
                <div style='font-size: 12.5px; line-height: 1.55; color: #334155; text-align: justify;'>
                    Il database contiene categorie particolari di dati personali (Art. 9 GDPR), tra cui parametri fisici, telemetria GPS/IMU, profili neuromuscolari, questionari di benessere psicofisico (Wellness/sRPE) e cartelle clinico-fisioterapiche (diagnosi, trattamenti e scale del dolore VAS).<br/>
                    <div style='margin-top: 6px;'>• <b>Per lo Staff Tecnico, Atletico e Medico:</b> L'utente si impegna al rigoroso rispetto del segreto professionale, a trattare i dati esclusivamente per finalità tecniche, atletiche e mediche interne, e a non diffondere dati o report PDF al di fuori degli ambienti protetti autorizzati.</div>
                    <div style='margin-top: 4px;'>• <b>Per l'Atleta:</b> L'utente prende atto e acconsente al conferimento dei propri parametri giornalieri di benessere e carico percepito affinché lo staff tecnico e sanitario autorizzato possa monitorare il recupero e prevenire gli infortuni.</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            st.markdown("""
            <div style='background: rgba(239, 68, 68, 0.04); border-left: 4px solid #ef4444; padding: 14px 16px; border-radius: 6px; margin-bottom: 16px;'>
                <div style='font-size: 14px; font-weight: 800; color: #0f172a; margin-bottom: 6px;'>
                    3. Sicurezza delle Credenziali e Tracciabilità
                </div>
                <div style='font-size: 12.5px; line-height: 1.55; color: #334155; text-align: justify;'>
                    L'utente è l'unico responsabile della segretezza della propria password. Ogni esportazione PDF riporta a piè di pagina l'identificativo dell'account che l'ha generata. Eventuali Data Breach derivanti da gestione negligente o condivisione del proprio account ricadranno sotto la responsabilità esclusiva dell'utente stesso.
                </div>
            </div>
            """, unsafe_allow_html=True)

            # Download button PDF Informativa Ufficiale
            doc_path = os.path.join(os.path.dirname(__file__), "assets", "Atto_Privacy_IP_MOV3_v2.pdf")
            pdf_bytes = None
            if os.path.exists(doc_path):
                try:
                    with open(doc_path, "rb") as f_pdf:
                        pdf_bytes = f_pdf.read()
                except Exception:
                    pdf_bytes = None

            if not pdf_bytes:
                try:
                    import pdf_generator
                    u_mail = getattr(user_obj, 'email', '') or (user_obj.get('email', '') if isinstance(user_obj, dict) else '') or "utente-autorizzato"
                    pdf_bytes = pdf_generator.genera_pdf_informativa_privacy_mov3(user_email=u_mail)
                except Exception:
                    pdf_bytes = None

            if pdf_bytes:
                st.download_button(
                    label="Scarica l'Informativa Completa Privacy & Proprietà Intellettuale M0V3 (PDF)",
                    data=pdf_bytes,
                    file_name="Atto_Privacy_IP_MOV3_v2.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                    key="btn_download_informativa_pdf"
                )

            st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)

            chk_label = "Dichiaro di aver letto, compreso e accettato i Termini d'Uso, i vincoli di Proprietà Intellettuale (Tecnologia Riccardo Di Maio — M0V3 S.r.l.) e le direttive GDPR sulla Privacy dei dati biometrici e sanitari."
            accepted = st.checkbox(chk_label, key="chk_clickwrap_m0v3")

            st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)

            col_act1, col_act2 = st.columns([3, 1.2])
            with col_act1:
                btn_confirm = st.button(
                    "Accedi alla Piattaforma",
                    type="primary",
                    use_container_width=True,
                    disabled=not accepted,
                    key="btn_conferma_accesso_clickwrap"
                )
                if btn_confirm:
                    if accepted:
                        now_iso = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        if user_id:
                            upd = {
                                "has_accepted_terms": True,
                                "privacy_accettata": True,
                                "terms_accepted_at": now_iso,
                                "terms_version": "M0V3_IP_GDPR_v2.0"
                            }
                            db_t = supabase_admin if supabase_admin else supabase
                            try:
                                db_t.table('profili').update(upd).eq('id', user_id).execute()
                            except Exception:
                                try:
                                    db_t.table('profili').update({"privacy_accettata": True}).eq('id', user_id).execute()
                                except Exception:
                                    pass
                        st.session_state['has_accepted_terms'] = True
                        st.session_state['privacy_accettata'] = True
                        st.session_state['terms_accepted_at'] = now_iso
                        st.session_state['terms_version'] = "M0V3_IP_GDPR_v2.0"
                        st.success("Accettazione registrata con successo! Accesso alla piattaforma in corso...")
                        st.rerun()
                    else:
                        st.warning("È obbligatorio spuntare la casella di accettazione prima di accedere.")

            with col_act2:
                if st.button("Esci / Logout", type="secondary", use_container_width=True, key="btn_logout_clickwrap"):
                    try: supabase.auth.sign_out()
                    except Exception: pass
                    st.session_state['user'] = None
                    st.session_state['role'] = None
                    st.session_state['refresh_token'] = None
                    st.session_state['has_accepted_terms'] = False
                    st.session_state['privacy_accettata'] = False
                    st.session_state['terms_accepted_at'] = ''
                    st.session_state['view_mode'] = None
                    st.session_state['logged_out'] = True
                    st.rerun()

        render_m0v3_footer(is_sidebar=False)
        return

    if 'current_page' not in st.session_state: st.session_state.current_page = "Home"
    t = LANG[st.session_state.get('lang', 'IT')]

    # -------------------------------------------------------------
    # ROUTING ATLETA SMARTPHONE (Mobile-First Mini WebApp)
    # -------------------------------------------------------------
    device_param = st.query_params.get("device", "").lower()
    user_role = st.session_state.get('role')

    if device_param == 'desktop':
        st.session_state['view_mode'] = 'desktop'
    elif device_param == 'mobile':
        st.session_state['view_mode'] = 'mobile'
    elif 'view_mode' not in st.session_state:
        st.session_state['view_mode'] = 'mobile' if user_role == 'Atleta' else 'desktop'

    is_mobile = (st.session_state.get('view_mode') == 'mobile')

    if is_mobile:
        col_m1, col_m2 = st.columns([3, 1.5])
        with col_m1:
            st.markdown(
                f"<div style='font-size:12px; font-weight:700; color:#64748b; padding-top:6px;'>"
                f"<i class='bi bi-phone' style='color:#0ea5e9; margin-right:4px;'></i>"
                f"{tr('Vista Smartphone Attiva', 'Smartphone View Active')}"
                f"</div>",
                unsafe_allow_html=True
            )
        with col_m2:
            if st.button(tr("Passa a Desktop", "Switch to Desktop"), key="btn_quick_switch_desktop", type="secondary", use_container_width=True):
                st.session_state['view_mode'] = 'desktop'
                st.query_params['device'] = 'desktop'
                st.rerun()

        import views.atleta_mobile
        _load_view(views.atleta_mobile)
        views.atleta_mobile.render_atleta_mobile(t)
        return

    # --- SIDEBAR ENTERPRISE ---
    with st.sidebar:
        def _on_global_athlete_change():
            sel = st.session_state.get('global_athlete_selector')
            if sel:
                st.session_state['selected_athlete'] = sel
                # Propaga la selezione a tutte le pagine
                st.session_state['home_focus_athlete'] = sel
                st.session_state['as_sel_player'] = sel
                st.session_state['am_sel_player'] = sel
                st.session_state['test_fisici_atleta_sel'] = sel
                st.session_state['cal_atleta_sel'] = sel
                st.session_state['sel_atleta_carico_interno'] = sel
                st.session_state['avg_ath'] = sel
                st.session_state['h2h_a'] = sel
                st.session_state['h2h_w_a'] = sel
                st.session_state['storico_match_sel_player'] = sel

        with st.container(key="sidebar_fixed_header"):
            target_logo = LOGO_CIRCULAR_PATH if os.path.exists(LOGO_CIRCULAR_PATH) else (LOGO_PATH if os.path.exists(LOGO_PATH) else None)
            if target_logo:
                sb_logo_b64 = get_base64_image(target_logo)
                st.markdown(f"""
                <div style='text-align: center; padding: 6px 0 12px 0;'>
                    <img src='data:image/png;base64,{sb_logo_b64}' 
                         alt='MOV3 Logo' 
                         style='width: 145px; max-width: 85%; height: auto; display: block; margin: 0 auto; filter: drop-shadow(0 4px 14px rgba(14, 165, 233, 0.4));'>
                </div>
                """, unsafe_allow_html=True)

            # --- SELETTORE ATLETA GLOBALE (ATTIVO) ---
            lista_atleti_globale = get_lista_atleti_disponibili(st.session_state.get('user'), st.session_state.get('role'))
            
            # Inizializzazione session_state per l'atleta globale
            if 'selected_athlete' not in st.session_state or st.session_state['selected_athlete'] not in lista_atleti_globale:
                st.session_state['selected_athlete'] = lista_atleti_globale[0] if lista_atleti_globale else "prova uno"

            curr_lang = st.session_state.get('lang', 'IT')
            lbl_atl_tit = "Atleta Attivo" if curr_lang == 'IT' else "Active Athlete"
            lbl_atl_sub = "Atleta Profilato" if curr_lang == 'IT' else "Profiled Athlete"

            if st.session_state.get('role') == 'Atleta':
                st.markdown(f"""
                <div style='background: rgba(30, 41, 59, 0.65); border: 1px solid rgba(56, 189, 248, 0.35); border-radius: 8px; padding: 10px 12px; margin-bottom: 4px;'>
                    <div style='font-size: 10px; text-transform: uppercase; letter-spacing: 0.8px; color: #94a3b8; font-weight: 700; display: flex; align-items: center; gap: 6px;'>
                        <i class="bi bi-person-badge" style="color: #38bdf8; font-size: 13px;"></i> {lbl_atl_sub}
                    </div>
                    <div style='font-weight: 700; font-size: 13.5px; color: #ffffff; margin-top: 4px; word-break: break-word;'>
                        {st.session_state['selected_athlete']}
                    </div>
                </div>
                """, unsafe_allow_html=True)
            else:
                idx_atl = 0
                if st.session_state['selected_athlete'] in lista_atleti_globale:
                    idx_atl = lista_atleti_globale.index(st.session_state['selected_athlete'])
                
                st.markdown(f"""
                <div style='font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.8px; color: #94a3b8; font-weight: 700; margin-bottom: 4px; display: flex; align-items: center; gap: 6px;'>
                    <i class="bi bi-person-bounding-box" style="color: #38bdf8; font-size: 13px;"></i> {lbl_atl_tit}
                </div>
                """, unsafe_allow_html=True)

                st.selectbox(
                    lbl_atl_tit,
                    lista_atleti_globale,
                    index=idx_atl,
                    key="global_athlete_selector",
                    on_change=_on_global_athlete_change,
                    label_visibility="collapsed"
                )

        # --- SEZIONE CORPO SCORREVOLE DELLA SIDEBAR (Scorre liberamente sotto l'header) ---
        scelta_lingua = st.radio("Lingua / Language", ["IT", "EN"], index=0 if st.session_state['lang'] == 'IT' else 1, horizontal=True)
        if scelta_lingua != st.session_state['lang']: 
            st.session_state['lang'] = scelta_lingua
            st.rerun()
        
        t = LANG[st.session_state['lang']]

        user_obj = st.session_state.get('user')
        if not user_obj:
            auth_module()
            return

        user_email = getattr(user_obj, 'email', '') or (user_obj.get('email', '') if isinstance(user_obj, dict) else '')
        curr_role = st.session_state.get('role', 'Staff')
        curr_uid = getattr(user_obj, 'id', '') or (user_obj.get('id', '') if isinstance(user_obj, dict) else '')

        st.markdown(f"""
        <div style='background-color: rgba(255,255,255,0.06); padding: 12px; border-radius: 8px; margin-top: 10px; margin-bottom: 15px; border: 1px solid rgba(255,255,255,0.1); color: #e6f1ff; font-family: "Inter", sans-serif;'>
            <div style='font-size: 11px; text-transform: uppercase; letter-spacing: 1px; opacity: 0.7;'>{t['user']}</div>
            <div style='font-weight: 700; font-size: 13px; margin-bottom: 6px; word-break: break-all;'>{user_email}</div>
            <div style='font-size: 11px; text-transform: uppercase; letter-spacing: 1px; opacity: 0.7;'>{t['role']}</div>
            <div style='font-weight: 700; font-size: 13px; color: #38bdf8 !important;'>{curr_role}</div>
        </div>
        """, unsafe_allow_html=True)

        # Recupero permessi moduli per visibilità menu personalizzata (RLS / Admin)

        if curr_role == 'Super-Admin':
            permessi_utente_set = None  # Super-Admin vede tutte le aree e pagine
        else:
            if 'user_permessi_moduli' not in st.session_state or st.session_state.get('refresh_permessi'):
                try:
                    db_p = supabase_admin if supabase_admin is not None else supabase
                    res_p = db_p.table('moduli_report').select('area, nome_report').eq('profilo_id', curr_uid).execute()
                    if res_p.data:
                        st.session_state['user_permessi_moduli'] = set((r['area'], r['nome_report']) for r in res_p.data)
                    else:
                        st.session_state['user_permessi_moduli'] = None
                    st.session_state['refresh_permessi'] = False
                except Exception:
                    st.session_state['user_permessi_moduli'] = None

            permessi_utente_set = st.session_state.get('user_permessi_moduli')

        def _is_menu_page_visible(page_key):
            # Esclusione assoluta area medica per ruolo Atleta
            if st.session_state.get('role') == 'Atleta' and page_key == "Calendario & Area Medica":
                return False

            if permessi_utente_set is None:
                return True

            # 1. Aree con sottomoduli analitici
            for area_n, pag_t in AREA_TO_PAGINA.items():
                if pag_t == page_key:
                    return any(ar == area_n for (ar, _) in permessi_utente_set)

            # 2. Pagine operative dirette
            for pag_op in PAGINE_OPERATIVE:
                if pag_op['chiave'] == page_key:
                    return ('Pagine Operative', page_key) in permessi_utente_set

            # Fallback per Carico Interno se salvato precedentemente nelle Pagine Operative
            if page_key == "Carico Interno" and ('Pagine Operative', 'Carico Interno') in permessi_utente_set:
                return True

            # 3. Pagine sempre disponibili (Home, Profilo, Supporto, Diario)
            return True

        # Configurazione voci menu statico ultra-veloce con Icone Vettoriali Monocromatiche Bootstrap
        # Carico Interno posizionato sotto le analisi GPS e rinominato
        menu_items_raw = [
            (tr("Dashboard Home", "Home Dashboard"), "Home", "grid-1x2"),
            (tr("Analisi Match", "Match Analysis"), "Analisi Match", "trophy"),
            (tr("Analisi Sessione", "Session Analysis"), "Analisi Sessione", "activity"),
            (tr("Trend Settimanale", "Weekly Trend"), "Trend Settimanale", "calendar-week"),
            (tr("Trend Stagionale", "Seasonal Trend"), "Trend Stagionale", "calendar-range"),
            (tr("Storico Match", "Match History"), "Storico Match", "graph-up-arrow"),
            (tr("Statistiche Match", "Match Statistics"), "Statistiche Match", "card-checklist"),
            (tr("Medie & Confronti", "Averages & H2H"), "Medie", "bar-chart-line"),
            (tr("Analisi Wellness-RPE-GPS", "Wellness-RPE-GPS Analysis"), "Carico Interno", "heart-pulse"),
            (tr("Test & Valutazioni", "Tests & Assessments"), "Test & Valutazioni", "clipboard2-pulse"),
            (tr("M0V3 Tennis Test", "M0V3 Tennis Test"), "M0V3 Tennis Test", "lightning-charge-fill"),
            (tr("Medico & Extra Tennis", "Medical & Extra-Tennis"), "Calendario & Area Medica", "calendar-plus"),
            (tr("Caricamento Dati", "Data Upload"), "Caricamento Dati", "cloud-arrow-up"),
            (tr("Generatore (No GPS)", "Data Generator"), "Generatore Dati (No GPS)", "sliders"),
            (tr("Gestione File", "File Manager"), "Gestione File Caricati", "folder2-open"),
            (tr("Manuale Report", "Reports Manual"), "Manuale Report", "journal-bookmark-fill"),
            (tr("Manuale Test", "Test Protocols Manual"), "Manuale Test", "journal-text"),
            (tr("Supporto & Assistenza", "Support & Help"), "Supporto", "headset"),
            (tr("Profilo Personale", "Personal Profile"), "Profilo Personale", "person"),
        ]

        if st.session_state['role'] == 'Atleta':
            menu_items_raw.insert(1, (tr("Diario Wellness & sRPE", "Wellness & sRPE Diary"), "Diario Atleta", "journal-check"))

        if st.session_state['role'] == 'Super-Admin':
            menu_items_raw.append((tr("Pannello Admin", "Admin Panel"), "Pannello Admin (Gestione Utenti)", "shield-lock"))

        # Filtra solo le pagine abilitate per l'utente corrente
        menu_items = [it for it in menu_items_raw if _is_menu_page_visible(it[1])]
        if not menu_items:
            menu_items = [(tr("Dashboard Home", "Home Dashboard"), "Home", "grid-1x2")]

        menu_labels = [item[0] for item in menu_items]
        menu_icons = [item[2] for item in menu_items]
        page_mapping = {item[0]: item[1] for item in menu_items}
        inv_mapping = {item[1]: item[0] for item in menu_items}

        if st.session_state.current_page not in inv_mapping:
            st.session_state.current_page = menu_items[0][1]

        target_lbl = inv_mapping.get(st.session_state.current_page, menu_labels[0])
        default_idx = menu_labels.index(target_lbl) if target_lbl in menu_labels else 0

        selected_label = option_menu(
            menu_title=None,
            options=menu_labels,
            icons=menu_icons,
            default_index=default_idx,
            styles={
                "container": {
                    "padding": "0!important", 
                    "background-color": "#0A192F !important",
                    "background": "#0A192F !important"
                },
                "icon": {"color": "#94a3b8", "font-size": "14px"},
                "nav": {
                    "background-color": "#0A192F !important",
                    "background": "#0A192F !important"
                },
                "nav-link": {
                    "font-family": "'Inter', -apple-system, sans-serif !important",
                    "font-size": "13px", 
                    "text-align": "left", 
                    "margin": "1px 0px", 
                    "padding": "7px 12px", 
                    "border-radius": "7px", 
                    "color": "#94a3b8", 
                    "font-weight": "600", 
                    "letter-spacing": "0.2px",
                    "--hover-color": "rgba(255,255,255,0.06)",
                    "background-color": "#0A192F !important"
                },
                "nav-link-selected": {
                    "font-family": "'Inter', -apple-system, sans-serif !important",
                    "background-color": "#0ea5e9 !important", 
                    "color": "white !important", 
                    "font-weight": "800 !important"
                },
            }
        )

        if page_mapping[selected_label] != st.session_state.current_page:
            st.session_state.current_page = page_mapping[selected_label]
            st.session_state['force_scroll_top'] = True
            st.rerun()

        # --- MODULO 1.4: INDICATORE DI STATO CLOUD & DOWNLOAD MASTER PARQUET PER MAC ---
        sync_binary_snapshots_on_cold_boot()
        if curr_role in ('Super-Admin', 'Admin', 'Coach', 'Preparatore'):
            snap_stat = get_cloud_snapshot_status()
            max_dt_lbl = snap_stat.get('max_date', 'N/D')
            tot_r_lbl = snap_stat.get('total_rows', 0)
            st.markdown(
                f"<div style='background:rgba(16,185,129,0.10); border:1px solid rgba(16,185,129,0.35); border-radius:8px; padding:8px 10px; margin-top:12px; margin-bottom:6px; font-family:\"Inter\",sans-serif;'>"
                f"<div style='font-size:10.5px; font-weight:800; color:#34d399; display:flex; align-items:center; gap:5px;'>"
                f"<i class='bi bi-cloud-check-fill'></i> Cloud Snapshot Attivo</div>"
                f"<div style='font-size:10px; color:#cbd5e1; margin-top:3px; line-height:1.35;'>"
                f"Cloud Snapshot Attivo | Ultima Data GPS Salvata: <b style='color:#ffffff;'>{max_dt_lbl}</b> | Totale Righe: <b style='color:#38bdf8;'>{tot_r_lbl}</b>"
                f"</div></div>",
                unsafe_allow_html=True
            )
            if curr_role == 'Super-Admin' and os.path.exists(DB_PARQUET_PATH):
                try:
                    with open(DB_PARQUET_PATH, "rb") as f_parq:
                        parq_bytes = f_parq.read()
                    st.download_button(
                        label="Scarica database_storico.parquet Consolidato",
                        data=parq_bytes,
                        file_name="database_storico.parquet",
                        mime="application/octet-stream",
                        key="btn_dl_master_parquet_sidebar",
                        use_container_width=True
                    )
                except Exception:
                    pass

        # Switcher manuale per testare la vista smartphone da PC
        st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)
        if st.button(tr("Vista Smartphone", "Smartphone View"), key="btn_switch_mobile", use_container_width=True):
            st.session_state['view_mode'] = 'mobile'
            st.query_params['device'] = 'mobile'
            st.rerun()

        st.divider()
        if st.button(t['logout'], key="btn_logout_sidebar", use_container_width=True):
            try: supabase.auth.sign_out()
            except: pass
            st.session_state['user'] = None
            st.session_state['role'] = None
            st.session_state['refresh_token'] = None
            st.session_state['has_accepted_terms'] = False
            st.session_state['privacy_accettata'] = False
            st.session_state['terms_accepted_at'] = ''
            st.session_state['view_mode'] = None
            st.session_state['logged_out'] = True
            st.query_params.clear()
            st.query_params['logged_out'] = '1'
            components.html("""
            <script>
            (function() {
                try {
                    document.cookie = "m0v3_rt=; path=/; max-age=0;";
                    try { localStorage.removeItem("m0v3_rt"); } catch(e) {}
                    try { sessionStorage.removeItem("m0v3_auth_tried"); } catch(e) {}
                    if (window.parent && window.parent !== window) {
                        try { window.parent.document.cookie = "m0v3_rt=; path=/; max-age=0;"; } catch(e) {}
                        try { window.parent.localStorage.removeItem("m0v3_rt"); } catch(e) {}
                        try { window.parent.sessionStorage.removeItem("m0v3_auth_tried"); } catch(e) {}
                    }
                } catch(e) {}
            })();
            </script>
            """, height=0)
            st.rerun()

        # Footer istituzionale con Logo M0V3 e Copyright nella sidebar
        render_m0v3_footer(is_sidebar=True)

        components.html("""
        <script>
        (function() {
            function pinSidebarHeader() {
                try {
                    var p = window.parent;
                    if (!p || !p.document) return;
                    var hdr = p.document.querySelector('[class*="st-key-sidebar_fixed_header"]');
                    if (hdr) {
                        var el = hdr;
                        while (el && el.parentElement && el.parentElement.getAttribute('data-testid') !== 'stVerticalBlock') {
                            el = el.parentElement;
                        }
                        var target = el || hdr;
                        target.style.position = '-webkit-sticky';
                        target.style.position = 'sticky';
                        target.style.top = '0px';
                        target.style.zIndex = '99999';
                        target.style.backgroundColor = '#0A192F';
                        target.style.width = '100%';
                        target.style.boxSizing = 'border-box';
                        target.style.paddingTop = '1.25rem';
                        target.style.paddingBottom = '12px';
                        target.style.marginBottom = '10px';
                        target.style.borderBottom = '1px solid rgba(255, 255, 255, 0.12)';
                        target.style.boxShadow = '0 4px 16px rgba(0, 0, 0, 0.45)';

                        var scrollContainer = p.document.querySelector('[data-testid="stSidebarContent"]');
                        if (scrollContainer) {
                            scrollContainer.style.overflowY = 'auto';
                            scrollContainer.style.paddingTop = '0px';
                        }
                        var userContent = p.document.querySelector('[data-testid="stSidebarUserContent"]');
                        if (userContent) {
                            userContent.style.paddingTop = '0px';
                            userContent.style.overflow = 'visible';
                        }
                    }
                } catch(e) {}
            }
            pinSidebarHeader();
            setTimeout(pinSidebarHeader, 100);
            setTimeout(pinSidebarHeader, 300);
            setTimeout(pinSidebarHeader, 800);
            setTimeout(pinSidebarHeader, 1500);
        })();
        </script>
        """, height=0)

    active_page = st.session_state.current_page
    # --- FIX: Forza lo scroll in cima alla pagina al cambio pagina ---
    page_changed = (st.session_state.get('last_rendered_page') != active_page) or st.session_state.get('force_scroll_top', False)
    st.session_state['last_rendered_page'] = active_page
    st.session_state['force_scroll_top'] = False

    if page_changed:
        components.html("""
            <script>
            (function() {
                function scrollToTop() {
                    try {
                        var p = window.parent;
                        if (!p || !p.document) return;
                        p.window.scrollTo(0, 0);
                        var selectors = [
                            'section.main',
                            '[data-testid="stMain"]',
                            '[data-testid="stAppViewContainer"]',
                            '.main',
                            '[data-testid="stMainBlockContainer"]',
                            'div[data-testid="stAppViewBlockContainer"]'
                        ];
                        selectors.forEach(function(sel) {
                            var el = p.document.querySelector(sel);
                            if (el) {
                                el.scrollTop = 0;
                                try { el.scrollTo({top: 0, left: 0, behavior: 'instant'}); } catch(err) { el.scrollTo(0, 0); }
                            }
                        });
                        var allScrollables = p.document.querySelectorAll('section.main, [data-testid="stMain"], [data-testid="stAppViewContainer"], .main');
                        allScrollables.forEach(function(el) {
                            el.scrollTop = 0;
                        });
                        var topAnchor = p.document.getElementById('top-of-page');
                        if (topAnchor && topAnchor.scrollIntoView) {
                            topAnchor.scrollIntoView({block: 'start', inline: 'nearest', behavior: 'instant'});
                        }
                    } catch(e) {}
                }
                scrollToTop();
                setTimeout(scrollToTop, 40);
                setTimeout(scrollToTop, 120);
                setTimeout(scrollToTop, 250);
                setTimeout(scrollToTop, 500);
            })();
            </script>
        """, height=0)
    # -----------------------------------------------------------------

    # Banner stato giornaliero Wellness/sRPE per Atleta su Desktop
    if st.session_state.get('role') == 'Atleta' and active_page != "Diario Atleta":
        u_obj = st.session_state.get('user')
        u_id = getattr(u_obj, 'id', None) if u_obj else None
        atl_info = get_atleta_dettagli_per_utente(u_id) if u_id else None
        if atl_info:
            oggi_d = datetime.date.today()
            oggi_iso = oggi_d.strftime('%Y-%m-%d')
            st_oggi = check_stato_giornaliero_atleta(atl_info['id'], oggi_iso)
            w_label = f"<span style='color:#10b981; font-weight:800;'><i class='bi bi-check-circle-fill' style='margin-right:4px;'></i>{tr('Wellness: Compilato', 'Wellness: Logged')}</span>" if st_oggi['wellness_compilato'] else f"<span style='color:#ef4444; font-weight:800;'><i class='bi bi-x-circle-fill' style='margin-right:4px;'></i>{tr('Wellness: Da compilare', 'Wellness: Pending')}</span>"
            r_label = f"<span style='color:#10b981; font-weight:800;'><i class='bi bi-check-circle-fill' style='margin-right:4px;'></i>{tr('sRPE: Registrato', 'sRPE: Logged')} ({st_oggi['rpe_tot_carico']} TL)</span>" if st_oggi['rpe_compilato'] else f"<span style='color:#ef4444; font-weight:800;'><i class='bi bi-x-circle-fill' style='margin-right:4px;'></i>{tr('sRPE: Da registrare', 'sRPE: Pending')}</span>"

            col_b1, col_b2 = st.columns([3, 1.2])
            with col_b1:
                st.markdown(f"""
                <div style='background: linear-gradient(135deg, rgba(14, 165, 233, 0.12) 0%, rgba(10, 18, 34, 0.4) 100%); border: 1px solid rgba(14, 165, 233, 0.28); border-radius: 10px; padding: 10px 14px; margin-bottom: 12px;'>
                    <div style='font-size: 11px; color: #94a3b8; font-weight: 700; text-transform: uppercase;'>{tr("Stato Diario di Oggi", "Today's Diary Status")} ({oggi_d.strftime('%d/%m/%Y')}):</div>
                    <div style='font-size: 13.5px; font-weight: 800; color: #ffffff; margin-top: 3px;'>
                        <span style='margin-right: 15px;'>{w_label}</span> <span>{r_label}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
            with col_b2:
                if st.button(tr("Diario Wellness & sRPE", "Wellness & sRPE Diary"), key="btn_apri_diario_desktop", use_container_width=True, type="primary"):
                    st.session_state.current_page = "Diario Atleta"
                    st.rerun()

    # ==================== ROUTING PAGINE & NOTIFICHE M0V3 ====================
    check_and_render_notifications()
    import pdf_generator
    if DEV_MODE:
        importlib.reload(pdf_generator)

    if not _is_menu_page_visible(active_page) and active_page not in ["Home", "Profilo Personale", "Supporto", "Diario Atleta", "Pannello Admin (Gestione Utenti)"]:
        st.warning(tr("Non disponi dei permessi per accedere a questa sezione. Contatta l'amministratore.", "You do not have permissions to access this section. Contact the administrator."))
        st.stop()

    if active_page == "Home":
        import views.home
        _load_view(views.home)
        views.home.render_home(t)
    elif active_page == "Diario Atleta":
        import views.atleta_mobile
        _load_view(views.atleta_mobile)
        views.atleta_mobile.render_atleta_mobile(t)
    elif active_page == "Carico Interno":
        import views.carico_interno
        _load_view(views.carico_interno)
        views.carico_interno.render_carico_interno(t)
    elif active_page == "Test & Valutazioni":
        import views.test_fisici
        _load_view(views.test_fisici)
        views.test_fisici.render_test_fisici(t)
    elif active_page == "M0V3 Tennis Test":
        import views.move_tennis_test
        _load_view(views.move_tennis_test)
        views.move_tennis_test.render_move_tennis_test(t)
    elif active_page == "Calendario & Area Medica":
        if st.session_state.get('role') == 'Atleta':
            st.warning(tr("Accesso non autorizzato all'area medica.", "Unauthorized access to medical area."))
        else:
            import views.calendario_medico
            _load_view(views.calendario_medico)
            views.calendario_medico.render_calendario_medico(t)
    elif active_page == "Profilo Personale":
        import views.profilo
        _load_view(views.profilo)
        views.profilo.render_profilo(t)
    elif active_page == "Pannello Admin (Gestione Utenti)":
        import views.admin
        _load_view(views.admin)
        views.admin.render_admin(t)
    elif active_page == "Caricamento Dati":
        import views.caricamento_dati
        _load_view(views.caricamento_dati)
        views.caricamento_dati.render_caricamento_dati(t)
    elif active_page == "Generatore Dati (No GPS)":
        import views.generatore_dati
        _load_view(views.generatore_dati)
        views.generatore_dati.render_generatore_dati(t)
    elif active_page == "Gestione File Caricati":
        import views.gestione_file
        _load_view(views.gestione_file)
        views.gestione_file.render_gestione_file(t)
    elif active_page == "Medie":
        import views.medie
        _load_view(views.medie)
        views.medie.render_medie(t)
    elif active_page == "Analisi Match":
        import views.analisi_match
        _load_view(views.analisi_match)
        views.analisi_match.render_analisi_match(t)
    elif active_page == "Analisi Sessione":
        import views.analisi_sessione
        _load_view(views.analisi_sessione)
        views.analisi_sessione.render_analisi_sessione(t)
    elif active_page == "Trend Settimanale":
        import views.trend_settimanale
        _load_view(views.trend_settimanale)
        views.trend_settimanale.render_trend_settimanale(t)
    elif active_page == "Trend Stagionale":
        import views.trend_stagionale
        _load_view(views.trend_stagionale)
        views.trend_stagionale.render_trend_stagionale(t)
    elif active_page == "Storico Match":
        import views.storico_match
        _load_view(views.storico_match)
        views.storico_match.render_storico_match(t)
    elif active_page == "Statistiche Match":
        import views.statistiche_match
        _load_view(views.statistiche_match)
        views.statistiche_match.render_statistiche_match(t)
    elif active_page == "Manuale Report":
        import views.manuale_report
        _load_view(views.manuale_report)
        views.manuale_report.render_manuale_report(t)
    elif active_page == "Manuale Test":
        import views.manuale_test
        _load_view(views.manuale_test)
        views.manuale_test.render_manuale_test(t)
    elif active_page == "Supporto":
        import views.supporto
        _load_view(views.supporto)
        views.supporto.render_supporto(t)

    # Footer Istituzionale M0V3 Analytics con Logo e Copyright a fondo pagina
    render_m0v3_footer(is_sidebar=False)


if __name__ == "__main__":
    main()
