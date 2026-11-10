import os
import datetime
import importlib
import urllib.parse
import streamlit as st
import streamlit.components.v1 as components
from streamlit_option_menu import option_menu

from config import (
    LOGO_PATH,
    LOGO_CIRCULAR_PATH,
    LANG,
    tr,
    setup_plotly_theme,
    get_base64_image,
    add_custom_css,
    PAGINE_OPERATIVE,
    AREA_TO_PAGINA,
)
from utils import (
    supabase,
    supabase_admin,
    ensure_valid_session,
    get_atleta_dettagli_per_utente,
    get_lista_atleti_disponibili,
    check_stato_giornaliero_atleta,
)

DEV_MODE = os.environ.get("MOV3_DEV_MODE", "0") == "1"

def _load_view(mod):
    if DEV_MODE:
        importlib.reload(mod)
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

add_custom_css(LOGO_CIRCULAR_PATH)

# =========================================================================
# AUTENTICAZIONE E RICHIESTA SUPPORTO PASSWORD A M0V3
# =========================================================================
def auth_module():
    logo_b64 = get_base64_image(LOGO_CIRCULAR_PATH)
    if not logo_b64:
        logo_b64 = get_base64_image(LOGO_PATH)

    # SVG Campo da Tennis Geometrico Stilizzato (Opzione 3)
    svg_tennis_court = (
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1400 700' fill='none'>"
        "<defs>"
        "<radialGradient id='courtGlow' cx='50%' cy='50%' r='50%'>"
        "<stop offset='0%' stop-color='#0ea5e9' stop-opacity='0.09'/>"
        "<stop offset='70%' stop-color='#0ea5e9' stop-opacity='0.02'/>"
        "<stop offset='100%' stop-color='#0ea5e9' stop-opacity='0'/>"
        "</radialGradient>"
        "</defs>"
        "<rect x='100' y='60' width='1200' height='580' fill='url(#courtGlow)' rx='8'/>"
        "<rect x='100' y='60' width='1200' height='580' stroke='rgba(56, 189, 248, 0.22)' stroke-width='2'/>"
        "<line x1='100' y1='132' x2='1300' y2='132' stroke='rgba(56, 189, 248, 0.16)' stroke-width='1.5'/>"
        "<line x1='100' y1='568' x2='1300' y2='568' stroke='rgba(56, 189, 248, 0.16)' stroke-width='1.5'/>"
        "<line x1='700' y1='36' x2='700' y2='664' stroke='rgba(56, 189, 248, 0.35)' stroke-width='2.5' stroke-dasharray='6 4'/>"
        "<circle cx='700' cy='36' r='4' fill='#38bdf8' opacity='0.7'/>"
        "<circle cx='700' cy='664' r='4' fill='#38bdf8' opacity='0.7'/>"
        "<line x1='377' y1='132' x2='377' y2='568' stroke='rgba(56, 189, 248, 0.20)' stroke-width='1.5'/>"
        "<line x1='1023' y1='132' x2='1023' y2='568' stroke='rgba(56, 189, 248, 0.20)' stroke-width='1.5'/>"
        "<line x1='377' y1='350' x2='1023' y2='350' stroke='rgba(56, 189, 248, 0.20)' stroke-width='1.5'/>"
        "<line x1='100' y1='350' x2='125' y2='350' stroke='rgba(56, 189, 248, 0.30)' stroke-width='2'/>"
        "<line x1='1275' y1='350' x2='1300' y2='350' stroke='rgba(56, 189, 248, 0.30)' stroke-width='2'/>"
        "<circle cx='700' cy='350' r='5' fill='none' stroke='#38bdf8' stroke-width='1.5' opacity='0.4'/>"
        "<circle cx='700' cy='350' r='1.5' fill='#38bdf8' opacity='0.7'/>"
        "</svg>"
    )
    court_bg_encoded = urllib.parse.quote(svg_tennis_court)

    # Sfondo Geometric Tennis Grid & Grande Logo Circolare Perfettamente Centrato
    st.markdown(f"""
    <style>
    /* 1. Sfondo Dark con Campo da Tennis Geometrico Stilizzato (Opzione 3) */
    .stApp {{
        background-color: #060c18 !important;
        background-image: 
            url("data:image/svg+xml,{court_bg_encoded}"),
            radial-gradient(circle at 50% 50%, rgba(14, 165, 233, 0.16) 0%, transparent 60%),
            radial-gradient(circle at 15% 20%, rgba(14, 165, 233, 0.12) 0%, transparent 40%),
            radial-gradient(circle at 85% 80%, rgba(30, 58, 138, 0.25) 0%, transparent 45%),
            linear-gradient(145deg, #060c18 0%, #0b172a 50%, #080f1d 100%) !important;
        background-position: center center, center center, top left, bottom right, center center !important;
        background-repeat: no-repeat, no-repeat, no-repeat, no-repeat, no-repeat !important;
        background-size: min(1380px, 94vw) auto, cover, cover, cover, cover !important;
        min-height: 100vh !important;
        overflow-x: hidden !important;
    }}

    /* 2. Grande Logo Circolare di Sfondo Perfettamente Centrato Dietro la Card */
    [data-testid="stAppViewContainer"]::before {{
        content: "" !important;
        display: block !important;
        position: fixed !important;
        top: 50% !important;
        left: 50% !important;
        transform: translate(-50%, -50%) !important;
        width: 720px !important;
        height: 720px !important;
        background-image: url('data:image/png;base64,{logo_b64}') !important;
        background-size: contain !important;
        background-repeat: no-repeat !important;
        background-position: center !important;
        opacity: 0.14 !important;
        pointer-events: none !important;
        z-index: 0 !important;
        filter: drop-shadow(0 0 60px rgba(14, 165, 233, 0.35)) !important;
    }}

    @media (max-width: 900px) {{
        [data-testid="stAppViewContainer"]::before {{
            width: 440px !important;
            height: 440px !important;
            opacity: 0.10 !important;
        }}
    }}

    /* 3. Centratura e Dimensionamento Cockpit (3 Colonne) */
    .block-container {{
        max-width: 1380px !important;
        padding-top: 4vh !important;
        padding-bottom: 4vh !important;
        margin: 0 auto !important;
        position: relative !important;
        z-index: 10 !important;
    }}

    @media (max-width: 1080px) {{
        div[data-testid="column"]:nth-of-type(1),
        div[data-testid="column"]:nth-of-type(3) {{
            display: none !important;
        }}
        .block-container {{
            max-width: 480px !important;
            padding-top: 6vh !important;
        }}
    }}

    /* 4. Card Glassmorphism ad Alto Contrasto */
    div[data-testid="stVerticalBlockBorderWrapper"] {{
        background: linear-gradient(165deg, rgba(17, 28, 48, 0.90) 0%, rgba(10, 18, 34, 0.96) 100%) !important;
        backdrop-filter: blur(24px) !important;
        -webkit-backdrop-filter: blur(24px) !important;
        border: 1px solid rgba(255, 255, 255, 0.14) !important;
        border-radius: 20px !important;
        box-shadow: 0 25px 60px -15px rgba(0, 0, 0, 0.75), 0 0 40px rgba(14, 165, 233, 0.14) !important;
        padding: 34px 28px !important;
    }}

    [data-testid="stForm"] {{
        border: none !important;
        padding: 0 !important;
    }}

    /* 5. Campi Input ed Etichette (Altissima Leggibilità su Sfondo Scuro) */
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
        background-color: #0b1528 !important;
        color: #ffffff !important;
        -webkit-text-fill-color: #ffffff !important;
        caret-color: #38bdf8 !important;
        border: 1px solid rgba(56, 189, 248, 0.35) !important;
        border-radius: 10px !important;
        font-size: 14.5px !important;
        transition: all 0.2s ease !important;
    }}

    div[data-baseweb="input"]:focus-within,
    .stTextInput input:focus {{
        background-color: #0f1d36 !important;
        border-color: #0ea5e9 !important;
        box-shadow: 0 0 0 3px rgba(14, 165, 233, 0.35) !important;
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
        -webkit-box-shadow: 0 0 0px 1000px #0b1528 inset !important;
        box-shadow: 0 0 0px 1000px #0b1528 inset !important;
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

    /* 6. Pulsante "Accedi" Premium */
    .stFormSubmitButton button, button[kind="primaryFormSubmit"] {{
        background: linear-gradient(135deg, #0ea5e9 0%, #0284c7 100%) !important;
        color: #ffffff !important;
        font-weight: 800 !important;
        font-size: 15px !important;
        border: none !important;
        border-radius: 10px !important;
        padding: 12px 20px !important;
        letter-spacing: 0.5px !important;
        box-shadow: 0 4px 15px rgba(14, 165, 233, 0.35) !important;
        transition: all 0.2s ease !important;
        margin-top: 8px !important;
    }}
    .stFormSubmitButton button:hover, button[kind="primaryFormSubmit"]:hover {{
        background: linear-gradient(135deg, #38bdf8 0%, #0ea5e9 100%) !important;
        box-shadow: 0 6px 22px rgba(14, 165, 233, 0.55) !important;
        transform: translateY(-1px) !important;
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
        border: 1px solid rgba(255, 255, 255, 0.14) !important;
        border-radius: 12px !important;
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

    # Widget HUD Laterali con Grafici Neon Puri (Zero Numeri, 100% Visual High-Tech)
    hud_monitora = """<div style='background: linear-gradient(165deg, rgba(17, 28, 48, 0.90) 0%, rgba(10, 18, 34, 0.96) 100%); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px); border: 1px solid rgba(14, 165, 233, 0.32); border-radius: 14px; padding: 14px 16px; box-shadow: 0 12px 30px -10px rgba(0,0,0,0.6), 0 0 24px rgba(14, 165, 233, 0.12); margin-bottom: 12px;'>
<div style='display:flex; justify-content:space-between; align-items:center; margin-bottom: 3px;'>
<div style='font-size: 10.5px; font-weight: 800; letter-spacing: 2px; color: #38bdf8; text-transform: uppercase;'>
<i class="bi bi-activity" style='margin-right: 5px;'></i> MONITORA
</div>
<span style='background: rgba(14, 165, 233, 0.15); color: #38bdf8; font-size: 8.5px; font-weight: 800; padding: 2px 7px; border-radius: 5px; border: 1px solid rgba(14, 165, 233, 0.35); display: flex; align-items: center; gap: 5px;'>
<span style='width: 5px; height: 5px; border-radius: 50%; background: #38bdf8; box-shadow: 0 0 8px #38bdf8; display: inline-block;'></span> POST-MATCH SYNC
</span>
</div>
<div style='color: #ffffff; font-size: 12px; font-weight: 800; margin-bottom: 8px;'>Telemetria & Analisi Post-Sessione</div>
<div style='background: rgba(6, 12, 24, 0.85); border: 1px solid rgba(56, 189, 248, 0.20); border-radius: 8px; padding: 8px 10px; margin-bottom: 8px;'>
<svg viewBox='0 0 260 55' fill='none' xmlns='http://www.w3.org/2000/svg' style='width: 100%; height: 55px; display: block;'>
<line x1='0' y1='14' x2='260' y2='14' stroke='rgba(56, 189, 248, 0.10)' stroke-dasharray='3 3'/>
<line x1='0' y1='28' x2='260' y2='28' stroke='rgba(56, 189, 248, 0.14)' stroke-dasharray='3 3'/>
<line x1='0' y1='42' x2='260' y2='42' stroke='rgba(56, 189, 248, 0.10)' stroke-dasharray='3 3'/>
<line x1='65' y1='0' x2='65' y2='55' stroke='rgba(56, 189, 248, 0.08)' stroke-dasharray='3 3'/>
<line x1='130' y1='0' x2='130' y2='55' stroke='rgba(56, 189, 248, 0.08)' stroke-dasharray='3 3'/>
<line x1='195' y1='0' x2='195' y2='55' stroke='rgba(56, 189, 248, 0.08)' stroke-dasharray='3 3'/>
<path d='M0,38 Q25,38 45,34 T70,30 T85,12 T95,48 T105,24 T125,28 T145,22 T165,6 T178,44 T190,26 T215,28 T240,24 T260,20' stroke='rgba(14, 165, 233, 0.25)' stroke-width='6' fill='none'/>
<path d='M0,38 Q25,38 45,34 T70,30 T85,12 T95,48 T105,24 T125,28 T145,22 T165,6 T178,44 T190,26 T215,28 T240,24 T260,20' stroke='#38bdf8' stroke-width='2.2' fill='none' style='filter: drop-shadow(0 0 6px #0ea5e9);'/>
<path d='M0,32 Q35,26 70,33 T140,24 T210,30 T260,22' stroke='#60a5fa' stroke-width='1.2' stroke-dasharray='4 3' fill='none' opacity='0.75'/>
<circle cx='85' cy='12' r='3' fill='#ffffff' style='filter: drop-shadow(0 0 6px #ffffff);'/>
<circle cx='165' cy='6' r='3.5' fill='#34d399' style='filter: drop-shadow(0 0 8px #34d399);'/>
<circle cx='260' cy='20' r='3.5' fill='#38bdf8' style='filter: drop-shadow(0 0 8px #38bdf8);'/>
</svg>
</div>
<div style='background: rgba(6, 12, 24, 0.70); border: 1px solid rgba(56, 189, 248, 0.16); border-radius: 8px; padding: 7px 10px; display: grid; grid-template-columns: 1fr 1fr; gap: 8px;'>
<div>
<div style='font-size: 8px; font-weight: 800; letter-spacing: 1.5px; color: #94a3b8; text-transform: uppercase; margin-bottom: 4px;'>IMU TRI-AXIAL</div>
<svg viewBox='0 0 110 24' fill='none' xmlns='http://www.w3.org/2000/svg' style='width: 100%; height: 24px; display: block;'>
<path d='M0,6 Q18,2 35,6 T70,4 T110,6' stroke='#38bdf8' stroke-width='1.5' fill='none' style='filter: drop-shadow(0 0 4px #0ea5e9);'/>
<path d='M0,13 Q22,17 45,13 T85,11 T110,14' stroke='#34d399' stroke-width='1.5' fill='none' style='filter: drop-shadow(0 0 4px #34d399);'/>
<path d='M0,20 Q30,16 60,20 T95,18 T110,21' stroke='#818cf8' stroke-width='1.5' fill='none' style='filter: drop-shadow(0 0 4px #818cf8);'/>
</svg>
</div>
<div>
<div style='font-size: 8px; font-weight: 800; letter-spacing: 1.5px; color: #94a3b8; text-transform: uppercase; margin-bottom: 4px;'>IMPULSE BANDS</div>
<div style='display: flex; align-items: flex-end; justify-content: space-between; height: 24px; padding: 2px 0;'>
<div style='width: 5px; height: 8px; background: #0284c7; border-radius: 2px;'></div>
<div style='width: 5px; height: 14px; background: #0ea5e9; border-radius: 2px;'></div>
<div style='width: 5px; height: 20px; background: #38bdf8; border-radius: 2px; box-shadow: 0 0 6px #38bdf8;'></div>
<div style='width: 5px; height: 12px; background: #0ea5e9; border-radius: 2px;'></div>
<div style='width: 5px; height: 17px; background: #38bdf8; border-radius: 2px; box-shadow: 0 0 6px #38bdf8;'></div>
<div style='width: 5px; height: 23px; background: #ffffff; border-radius: 2px; box-shadow: 0 0 8px #ffffff;'></div>
<div style='width: 5px; height: 15px; background: #38bdf8; border-radius: 2px; box-shadow: 0 0 6px #38bdf8;'></div>
<div style='width: 5px; height: 9px; background: #0284c7; border-radius: 2px;'></div>
<div style='width: 5px; height: 18px; background: #34d399; border-radius: 2px; box-shadow: 0 0 6px #34d399;'></div>
<div style='width: 5px; height: 11px; background: #0ea5e9; border-radius: 2px;'></div>
</div>
</div>
</div>
</div>"""

    hud_analizza = """<div style='background: linear-gradient(165deg, rgba(17, 28, 48, 0.90) 0%, rgba(10, 18, 34, 0.96) 100%); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px); border: 1px solid rgba(14, 165, 233, 0.32); border-radius: 14px; padding: 14px 16px; box-shadow: 0 12px 30px -10px rgba(0,0,0,0.6), 0 0 24px rgba(14, 165, 233, 0.12);'>
<div style='display:flex; justify-content:space-between; align-items:center; margin-bottom: 3px;'>
<div style='font-size: 10.5px; font-weight: 800; letter-spacing: 2px; color: #38bdf8; text-transform: uppercase;'>
<i class="bi bi-bar-chart-line" style='margin-right: 5px;'></i> ANALIZZA
</div>
<span style='background: rgba(14, 165, 233, 0.15); color: #38bdf8; font-size: 8.5px; font-weight: 800; padding: 2px 7px; border-radius: 5px; border: 1px solid rgba(14, 165, 233, 0.35);'>
OPTIMAL ZONE
</span>
</div>
<div style='color: #ffffff; font-size: 12px; font-weight: 800; margin-bottom: 8px;'>Spettro Carichi & Distribuzione</div>
<div style='background: rgba(6, 12, 24, 0.85); border: 1px solid rgba(56, 189, 248, 0.20); border-radius: 8px; padding: 8px 10px; margin-bottom: 8px;'>
<svg viewBox='0 0 260 55' fill='none' xmlns='http://www.w3.org/2000/svg' style='width: 100%; height: 55px; display: block;'>
<line x1='0' y1='14' x2='260' y2='14' stroke='rgba(56, 189, 248, 0.08)' stroke-dasharray='2 2'/>
<line x1='0' y1='28' x2='260' y2='28' stroke='rgba(56, 189, 248, 0.12)' stroke-dasharray='2 2'/>
<line x1='0' y1='42' x2='260' y2='42' stroke='rgba(56, 189, 248, 0.08)' stroke-dasharray='2 2'/>
<!-- Segmented neon bars (11 columns) -->
<rect x='10' y='42' width='14' height='3.5' rx='1.5' fill='#0284c7'/>
<rect x='10' y='36' width='14' height='3.5' rx='1.5' fill='#0ea5e9'/>
<rect x='10' y='30' width='14' height='3.5' rx='1.5' fill='#38bdf8' style='filter: drop-shadow(0 0 5px #38bdf8);'/>

<rect x='32' y='42' width='14' height='3.5' rx='1.5' fill='#0284c7'/>
<rect x='32' y='36' width='14' height='3.5' rx='1.5' fill='#0ea5e9'/>
<rect x='32' y='30' width='14' height='3.5' rx='1.5' fill='#0ea5e9'/>
<rect x='32' y='24' width='14' height='3.5' rx='1.5' fill='#38bdf8'/>
<rect x='32' y='18' width='14' height='3.5' rx='1.5' fill='#ffffff' style='filter: drop-shadow(0 0 5px #ffffff);'/>

<rect x='54' y='42' width='14' height='3.5' rx='1.5' fill='#0284c7'/>
<rect x='54' y='36' width='14' height='3.5' rx='1.5' fill='#0ea5e9'/>
<rect x='54' y='30' width='14' height='3.5' rx='1.5' fill='#0ea5e9'/>
<rect x='54' y='24' width='14' height='3.5' rx='1.5' fill='#38bdf8'/>

<rect x='76' y='42' width='14' height='3.5' rx='1.5' fill='#0284c7'/>
<rect x='76' y='36' width='14' height='3.5' rx='1.5' fill='#0ea5e9'/>
<rect x='76' y='30' width='14' height='3.5' rx='1.5' fill='#0ea5e9'/>
<rect x='76' y='24' width='14' height='3.5' rx='1.5' fill='#38bdf8'/>
<rect x='76' y='18' width='14' height='3.5' rx='1.5' fill='#38bdf8'/>
<rect x='76' y='12' width='14' height='3.5' rx='1.5' fill='#ffffff' style='filter: drop-shadow(0 0 6px #ffffff);'/>

<rect x='98' y='42' width='14' height='3.5' rx='1.5' fill='#0284c7'/>
<rect x='98' y='36' width='14' height='3.5' rx='1.5' fill='#0ea5e9'/>
<rect x='98' y='30' width='14' height='3.5' rx='1.5' fill='#38bdf8'/>

<rect x='120' y='42' width='14' height='3.5' rx='1.5' fill='#0284c7'/>
<rect x='120' y='36' width='14' height='3.5' rx='1.5' fill='#0ea5e9'/>
<rect x='120' y='30' width='14' height='3.5' rx='1.5' fill='#0ea5e9'/>
<rect x='120' y='24' width='14' height='3.5' rx='1.5' fill='#38bdf8'/>
<rect x='120' y='18' width='14' height='3.5' rx='1.5' fill='#38bdf8'/>
<rect x='120' y='12' width='14' height='3.5' rx='1.5' fill='#38bdf8'/>
<rect x='120' y='6' width='14' height='3.5' rx='1.5' fill='#ffffff' style='filter: drop-shadow(0 0 6px #ffffff);'/>

<rect x='142' y='42' width='14' height='3.5' rx='1.5' fill='#0284c7'/>
<rect x='142' y='36' width='14' height='3.5' rx='1.5' fill='#0ea5e9'/>
<rect x='142' y='30' width='14' height='3.5' rx='1.5' fill='#0ea5e9'/>
<rect x='142' y='24' width='14' height='3.5' rx='1.5' fill='#38bdf8'/>

<rect x='164' y='42' width='14' height='3.5' rx='1.5' fill='#0284c7'/>
<rect x='164' y='36' width='14' height='3.5' rx='1.5' fill='#0ea5e9'/>
<rect x='164' y='30' width='14' height='3.5' rx='1.5' fill='#0ea5e9'/>
<rect x='164' y='24' width='14' height='3.5' rx='1.5' fill='#38bdf8'/>
<rect x='164' y='18' width='14' height='3.5' rx='1.5' fill='#38bdf8'/>

<rect x='186' y='42' width='14' height='3.5' rx='1.5' fill='#0284c7'/>
<rect x='186' y='36' width='14' height='3.5' rx='1.5' fill='#0ea5e9'/>
<rect x='186' y='30' width='14' height='3.5' rx='1.5' fill='#38bdf8'/>
<rect x='186' y='24' width='14' height='3.5' rx='1.5' fill='#38bdf8'/>

<rect x='208' y='42' width='14' height='3.5' rx='1.5' fill='#0284c7'/>
<rect x='208' y='36' width='14' height='3.5' rx='1.5' fill='#0ea5e9'/>
<rect x='208' y='30' width='14' height='3.5' rx='1.5' fill='#0ea5e9'/>
<rect x='208' y='24' width='14' height='3.5' rx='1.5' fill='#38bdf8'/>
<rect x='208' y='18' width='14' height='3.5' rx='1.5' fill='#ffffff' style='filter: drop-shadow(0 0 5px #ffffff);'/>

<rect x='230' y='42' width='14' height='3.5' rx='1.5' fill='#0284c7'/>
<rect x='230' y='36' width='14' height='3.5' rx='1.5' fill='#0ea5e9'/>
<rect x='230' y='30' width='14' height='3.5' rx='1.5' fill='#38bdf8'/>

<!-- Spline Trend Curve -->
<path d='M 17,28 Q 40,16 61,23 T 105,27 T 149,15 T 193,22 T 237,28' stroke='#34d399' stroke-width='2' fill='none' style='filter: drop-shadow(0 0 5px #34d399);'/>
</svg>
</div>
<div style='background: rgba(6, 12, 24, 0.70); border: 1px solid rgba(56, 189, 248, 0.16); border-radius: 8px; padding: 7px 10px; display: grid; grid-template-columns: 1fr 1fr; gap: 8px;'>
<div>
<div style='font-size: 8px; font-weight: 800; letter-spacing: 1.5px; color: #94a3b8; text-transform: uppercase; margin-bottom: 5px;'>SWEET SPOT RANGE</div>
<div style='position: relative; height: 16px; background: rgba(14, 165, 233, 0.10); border-radius: 8px; border: 1px solid rgba(56, 189, 248, 0.2); overflow: hidden;'>
<div style='position: absolute; left: 35%; width: 35%; top: 0; bottom: 0; background: rgba(16, 185, 129, 0.25); border-left: 1px dashed #34d399; border-right: 1px dashed #34d399;'></div>
<div style='position: absolute; left: 52%; top: 2px; width: 6px; height: 10px; border-radius: 3px; background: #ffffff; box-shadow: 0 0 8px #38bdf8, 0 0 12px #34d399;'></div>
</div>
<div style='display: flex; justify-content: space-between; margin-top: 3px;'>
<span style='font-size: 7px; color: #64748b; font-weight: 700;'>LOW</span>
<span style='font-size: 7px; color: #34d399; font-weight: 800;'>OPTIMAL</span>
<span style='font-size: 7px; color: #64748b; font-weight: 700;'>HIGH</span>
</div>
</div>
<div>
<div style='font-size: 8px; font-weight: 800; letter-spacing: 1.5px; color: #94a3b8; text-transform: uppercase; margin-bottom: 5px;'>LOAD MATRIX</div>
<div style='display: grid; grid-template-columns: repeat(6, 1fr); gap: 3.5px; padding-top: 2px;'>
<div style='height: 7px; border-radius: 2px; background: #0ea5e9;'></div>
<div style='height: 7px; border-radius: 2px; background: #38bdf8; box-shadow: 0 0 4px #38bdf8;'></div>
<div style='height: 7px; border-radius: 2px; background: #34d399; box-shadow: 0 0 5px #34d399;'></div>
<div style='height: 7px; border-radius: 2px; background: #38bdf8;'></div>
<div style='height: 7px; border-radius: 2px; background: #0284c7;'></div>
<div style='height: 7px; border-radius: 2px; background: #34d399; box-shadow: 0 0 5px #34d399;'></div>
<div style='height: 7px; border-radius: 2px; background: #38bdf8;'></div>
<div style='height: 7px; border-radius: 2px; background: #ffffff; box-shadow: 0 0 6px #ffffff;'></div>
<div style='height: 7px; border-radius: 2px; background: #34d399;'></div>
<div style='height: 7px; border-radius: 2px; background: #0ea5e9;'></div>
<div style='height: 7px; border-radius: 2px; background: #38bdf8; box-shadow: 0 0 4px #38bdf8;'></div>
<div style='height: 7px; border-radius: 2px; background: #0284c7;'></div>
</div>
</div>
</div>
</div>"""

    hud_programma = """<div style='background: linear-gradient(165deg, rgba(17, 28, 48, 0.90) 0%, rgba(10, 18, 34, 0.96) 100%); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px); border: 1px solid rgba(14, 165, 233, 0.32); border-radius: 14px; padding: 14px 16px; box-shadow: 0 12px 30px -10px rgba(0,0,0,0.6), 0 0 24px rgba(14, 165, 233, 0.12); margin-bottom: 12px;'>
<div style='display:flex; justify-content:space-between; align-items:center; margin-bottom: 3px;'>
<div style='font-size: 10.5px; font-weight: 800; letter-spacing: 2px; color: #38bdf8; text-transform: uppercase;'>
<i class="bi bi-calendar-check" style='margin-right: 5px;'></i> PROGRAMMA
</div>
<span style='background: rgba(14, 165, 233, 0.15); color: #38bdf8; font-size: 8.5px; font-weight: 800; padding: 2px 7px; border-radius: 5px; border: 1px solid rgba(14, 165, 233, 0.35);'>
TAPER PROTOCOL
</span>
</div>
<div style='color: #ffffff; font-size: 12px; font-weight: 800; margin-bottom: 8px;'>Periodizzazione & Microcicli</div>
<div style='background: rgba(6, 12, 24, 0.85); border: 1px solid rgba(56, 189, 248, 0.20); border-radius: 8px; padding: 8px 10px; margin-bottom: 8px;'>
<svg viewBox='0 0 260 55' fill='none' xmlns='http://www.w3.org/2000/svg' style='width: 100%; height: 55px; display: block;'>
<line x1='0' y1='14' x2='260' y2='14' stroke='rgba(56, 189, 248, 0.08)' stroke-dasharray='3 3'/>
<line x1='0' y1='28' x2='260' y2='28' stroke='rgba(56, 189, 248, 0.12)' stroke-dasharray='3 3'/>
<line x1='0' y1='42' x2='260' y2='42' stroke='rgba(56, 189, 248, 0.08)' stroke-dasharray='3 3'/>
<!-- Vertical Phase Dividers -->
<line x1='86' y1='0' x2='86' y2='55' stroke='rgba(56, 189, 248, 0.12)' stroke-dasharray='2 2'/>
<line x1='172' y1='0' x2='172' y2='55' stroke='rgba(56, 189, 248, 0.12)' stroke-dasharray='2 2'/>
<!-- Volume Curve (Tapering Descent) -->
<path d='M0,14 C40,14 70,20 100,28 C140,38 190,44 260,46' stroke='#0284c7' stroke-width='2' fill='none' opacity='0.75'/>
<!-- Intensity Curve (Sharp Match Waves) -->
<path d='M0,38 Q30,14 60,32 T120,24 T180,16 T220,10 T260,8' stroke='#38bdf8' stroke-width='2.2' fill='none' style='filter: drop-shadow(0 0 6px #0ea5e9);'/>
<!-- Chronic Load Baseline -->
<path d='M0,28 C70,26 140,24 210,21 C235,20 250,19 260,18' stroke='#34d399' stroke-width='1.8' stroke-dasharray='4 3' fill='none' style='filter: drop-shadow(0 0 5px #34d399);'/>
<!-- Highlights -->
<circle cx='220' cy='10' r='3' fill='#38bdf8' style='filter: drop-shadow(0 0 6px #38bdf8);'/>
<circle cx='260' cy='8' r='3.5' fill='#ffffff' style='filter: drop-shadow(0 0 8px #ffffff);'/>
</svg>
</div>
<div style='background: rgba(6, 12, 24, 0.70); border: 1px solid rgba(56, 189, 248, 0.16); border-radius: 8px; padding: 7px 10px; display: grid; grid-template-columns: 1fr 1fr; gap: 8px;'>
<div>
<div style='font-size: 8px; font-weight: 800; letter-spacing: 1.5px; color: #94a3b8; text-transform: uppercase; margin-bottom: 4px;'>CYCLE PROGRESSION</div>
<div style='display: flex; flex-direction: column; gap: 3.5px; padding-top: 1px;'>
<div style='display: flex; gap: 2.5px;'>
<div style='flex: 1; height: 5px; border-radius: 2px; background: #0ea5e9;'></div>
<div style='flex: 1; height: 5px; border-radius: 2px; background: #0ea5e9;'></div>
<div style='flex: 1; height: 5px; border-radius: 2px; background: #38bdf8; box-shadow: 0 0 5px #38bdf8;'></div>
<div style='flex: 1; height: 5px; border-radius: 2px; background: #38bdf8;'></div>
<div style='flex: 1; height: 5px; border-radius: 2px; background: rgba(14, 165, 233, 0.2);'></div>
</div>
<div style='display: flex; gap: 2.5px;'>
<div style='flex: 1; height: 5px; border-radius: 2px; background: #34d399;'></div>
<div style='flex: 1; height: 5px; border-radius: 2px; background: #34d399; box-shadow: 0 0 5px #34d399;'></div>
<div style='flex: 1; height: 5px; border-radius: 2px; background: #ffffff; box-shadow: 0 0 6px #ffffff;'></div>
<div style='flex: 1; height: 5px; border-radius: 2px; background: #34d399;'></div>
<div style='flex: 1; height: 5px; border-radius: 2px; background: #34d399;'></div>
</div>
<div style='display: flex; gap: 2.5px;'>
<div style='flex: 1; height: 5px; border-radius: 2px; background: #60a5fa;'></div>
<div style='flex: 1; height: 5px; border-radius: 2px; background: #60a5fa;'></div>
<div style='flex: 1; height: 5px; border-radius: 2px; background: #818cf8;'></div>
<div style='flex: 1; height: 5px; border-radius: 2px; background: rgba(14, 165, 233, 0.2);'></div>
<div style='flex: 1; height: 5px; border-radius: 2px; background: rgba(14, 165, 233, 0.2);'></div>
</div>
</div>
</div>
<div>
<div style='font-size: 8px; font-weight: 800; letter-spacing: 1.5px; color: #94a3b8; text-transform: uppercase; margin-bottom: 4px;'>SESSION DISTRIBUTION</div>
<div style='display: flex; align-items: flex-end; justify-content: space-between; height: 24px; padding: 2px 2px;'>
<div style='width: 8px; height: 10px; background: #0284c7; border-radius: 2px;'></div>
<div style='width: 8px; height: 16px; background: #0ea5e9; border-radius: 2px;'></div>
<div style='width: 8px; height: 22px; background: #38bdf8; border-radius: 2px; box-shadow: 0 0 6px #38bdf8;'></div>
<div style='width: 8px; height: 12px; background: #0284c7; border-radius: 2px;'></div>
<div style='width: 8px; height: 20px; background: #34d399; border-radius: 2px; box-shadow: 0 0 6px #34d399;'></div>
<div style='width: 8px; height: 24px; background: #ffffff; border-radius: 2px; box-shadow: 0 0 8px #ffffff;'></div>
<div style='width: 8px; height: 8px; background: rgba(14, 165, 233, 0.3); border-radius: 2px;'></div>
</div>
</div>
</div>
</div>"""

    hud_performa = """<div style='background: linear-gradient(165deg, rgba(17, 28, 48, 0.90) 0%, rgba(10, 18, 34, 0.96) 100%); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px); border: 1px solid rgba(14, 165, 233, 0.32); border-radius: 14px; padding: 14px 16px; box-shadow: 0 12px 30px -10px rgba(0,0,0,0.6), 0 0 24px rgba(14, 165, 233, 0.12);'>
<div style='display:flex; justify-content:space-between; align-items:center; margin-bottom: 3px;'>
<div style='font-size: 10.5px; font-weight: 800; letter-spacing: 2px; color: #38bdf8; text-transform: uppercase;'>
<i class="bi bi-trophy" style='margin-right: 5px;'></i> PERFORMA
</div>
<span style='background: rgba(16, 185, 129, 0.15); color: #34d399; font-size: 8.5px; font-weight: 800; padding: 2px 7px; border-radius: 5px; border: 1px solid rgba(16, 185, 129, 0.35);'>
MATCH READY
</span>
</div>
<div style='color: #ffffff; font-size: 12px; font-weight: 800; margin-bottom: 8px;'>Readiness & Athletic Radar</div>
<div style='background: rgba(6, 12, 24, 0.85); border: 1px solid rgba(56, 189, 248, 0.20); border-radius: 8px; padding: 6px 10px; margin-bottom: 8px;'>
<svg viewBox='0 0 260 88' fill='none' xmlns='http://www.w3.org/2000/svg' style='width: 100%; height: 88px; display: block;'>
<!-- Hexagonal Athletic Radar Chart (Expanded & Centered) -->
<!-- Concentric Web 1 (Outer - 100%) -->
<polygon points='130,12 161,30 161,64 130,82 99,64 99,30' stroke='rgba(56, 189, 248, 0.26)' stroke-width='1.2' fill='none'/>
<!-- Concentric Web 2 (Mid - 66%) -->
<polygon points='130,24 151,36 151,58 130,70 109,58 109,36' stroke='rgba(56, 189, 248, 0.16)' stroke-width='1' stroke-dasharray='2 2' fill='none'/>
<!-- Concentric Web 3 (Inner - 33%) -->
<polygon points='130,35 140,41 140,53 130,59 120,53 120,41' stroke='rgba(56, 189, 248, 0.10)' stroke-width='1' fill='none'/>
<!-- Axes -->
<line x1='130' y1='12' x2='130' y2='82' stroke='rgba(56, 189, 248, 0.20)' stroke-dasharray='2 2'/>
<line x1='99' y1='30' x2='161' y2='64' stroke='rgba(56, 189, 248, 0.20)' stroke-dasharray='2 2'/>
<line x1='99' y1='64' x2='161' y2='30' stroke='rgba(56, 189, 248, 0.20)' stroke-dasharray='2 2'/>
<!-- Radar Sweep Glow Line -->
<line x1='130' y1='47' x2='158' y2='33' stroke='#38bdf8' stroke-width='1.5' opacity='0.7' style='filter: drop-shadow(0 0 6px #38bdf8);'/>
<!-- Filled Athletic Polygon Shape -->
<polygon points='130,16 157,33 155,62 130,76 106,60 103,32' stroke='#38bdf8' stroke-width='2.2' fill='rgba(14, 165, 233, 0.28)' style='filter: drop-shadow(0 0 8px #0ea5e9);'/>
<!-- Glowing Vertices -->
<circle cx='130' cy='16' r='3' fill='#ffffff' style='filter: drop-shadow(0 0 6px #ffffff);'/>
<circle cx='157' cy='33' r='3' fill='#34d399' style='filter: drop-shadow(0 0 6px #34d399);'/>
<circle cx='155' cy='62' r='3' fill='#38bdf8' style='filter: drop-shadow(0 0 6px #38bdf8);'/>
<circle cx='130' cy='76' r='3' fill='#38bdf8' style='filter: drop-shadow(0 0 6px #38bdf8);'/>
<circle cx='106' cy='60' r='3' fill='#34d399' style='filter: drop-shadow(0 0 6px #34d399);'/>
<circle cx='103' cy='32' r='3' fill='#ffffff' style='filter: drop-shadow(0 0 6px #ffffff);'/>
<!-- Center Anchor -->
<circle cx='130' cy='47' r='2' fill='#38bdf8'/>
<!-- Radar Pillar Labels -->
<text x='130' y='9' fill='#38bdf8' font-size='8' font-weight='900' text-anchor='middle'>ACC</text>
<text x='168' y='29' fill='#e2e8f0' font-size='7.5' font-weight='800'>VEL</text>
<text x='168' y='67' fill='#e2e8f0' font-size='7.5' font-weight='800'>PWR</text>
<text x='130' y='92' fill='#38bdf8' font-size='8' font-weight='900' text-anchor='middle'>DEC</text>
<text x='92' y='67' fill='#e2e8f0' font-size='7.5' font-weight='800' text-anchor='end'>VOL</text>
<text x='92' y='29' fill='#e2e8f0' font-size='7.5' font-weight='800' text-anchor='end'>INT</text>
<!-- Lateral Cyber Accents -->
<path d='M8,47 Q22,25 38,47 T68,47' stroke='#0ea5e9' stroke-width='1.5' fill='none' opacity='0.55'/>
<path d='M192,47 Q222,47 238,25 T252,47' stroke='#34d399' stroke-width='1.5' fill='none' opacity='0.55'/>
</svg>
</div>
<div style='background: rgba(6, 12, 24, 0.70); border: 1px solid rgba(56, 189, 248, 0.16); border-radius: 8px; padding: 7px 10px; display: grid; grid-template-columns: 1fr 1fr; gap: 8px;'>
<div>
<div style='font-size: 8px; font-weight: 800; letter-spacing: 1.5px; color: #94a3b8; text-transform: uppercase; margin-bottom: 4px;'>NEUROMUSCULAR ARC</div>
<svg viewBox='0 0 110 24' fill='none' xmlns='http://www.w3.org/2000/svg' style='width: 100%; height: 24px; display: block;'>
<path d='M 15 20 A 18 18 0 0 1 95 20' stroke='rgba(14, 165, 233, 0.18)' stroke-width='4' stroke-linecap='round' fill='none'/>
<path d='M 15 20 A 18 18 0 0 1 88 10' stroke='#38bdf8' stroke-width='4' stroke-linecap='round' fill='none' style='filter: drop-shadow(0 0 5px #0ea5e9);'/>
<circle cx='88' cy='10' r='3' fill='#ffffff' style='filter: drop-shadow(0 0 6px #ffffff);'/>
</svg>
</div>
<div>
<div style='font-size: 8px; font-weight: 800; letter-spacing: 1.5px; color: #94a3b8; text-transform: uppercase; margin-bottom: 4px;'>INTENSITY SPECTRUM</div>
<div style='display: flex; align-items: flex-end; justify-content: space-between; height: 24px; padding: 2px 2px;'>
<div style='width: 6px; height: 10px; background: #0284c7; border-radius: 2px;'></div>
<div style='width: 6px; height: 15px; background: #0ea5e9; border-radius: 2px;'></div>
<div style='width: 6px; height: 21px; background: #38bdf8; border-radius: 2px; box-shadow: 0 0 5px #38bdf8;'></div>
<div style='width: 6px; height: 14px; background: #0ea5e9; border-radius: 2px;'></div>
<div style='width: 6px; height: 23px; background: #ffffff; border-radius: 2px; box-shadow: 0 0 7px #ffffff;'></div>
<div style='width: 6px; height: 18px; background: #34d399; border-radius: 2px; box-shadow: 0 0 5px #34d399;'></div>
<div style='width: 6px; height: 12px; background: #0ea5e9; border-radius: 2px;'></div>
<div style='width: 6px; height: 8px; background: #0284c7; border-radius: 2px;'></div>
</div>
</div>
</div>
</div>"""

    col_left, col_center, col_right = st.columns([1, 1.25, 1], gap="large")

    with col_left:
        st.html(hud_monitora)
        st.html(hud_analizza)

    with col_center:
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
                <img src='data:image/png;base64,{logo_b64}' style='width: 78px; height: 78px; border-radius: 50%; box-shadow: 0 0 28px rgba(14, 165, 233, 0.45); border: 2px solid rgba(255, 255, 255, 0.2); display: inline-block; margin-bottom: 12px;'>
                <div style='font-size: 10.5px; letter-spacing: 2.5px; text-transform: uppercase; color: #38bdf8; font-weight: 800; margin-bottom: 4px;'>PERFORMANCE ANALYTICS</div>
                <h1 style='color: #ffffff; font-size: 36px; font-weight: 900; line-height: 1.15; margin: 0 0 8px 0; letter-spacing: -0.8px; text-shadow: 0 0 24px rgba(14, 165, 233, 0.45);'>MOV3 Analytics</h1>
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
                        if hasattr(res, 'session') and res.session and hasattr(res.session, 'refresh_token'):
                            st.session_state['refresh_token'] = res.session.refresh_token

                        profilo = supabase.table('profili').select('ruolo, privacy_accettata').eq('id', res.user.id).execute()
                        if profilo.data:
                            st.session_state['role'] = profilo.data[0].get('ruolo', 'Atleta')
                            st.session_state['privacy_accettata'] = True if profilo.data[0].get('privacy_accettata') else False
                        else:
                            st.session_state['role'] = 'Atleta'
                            st.session_state['privacy_accettata'] = False
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

    with col_right:
        st.html(hud_programma)
        st.html(hud_performa)


# =========================================================================
# APP MAIN
# =========================================================================
def main():
    if not st.session_state.get('user'):
        # 1. Recupero sessione automatica da cookie persistente (anti-pull-to-refresh logout)
        # Se l'utente ha cliccato esplicitamente "Logout", non auto-ricollegare
        if not st.session_state.get('logged_out', False):
            rt_cookie = None
            if hasattr(st, 'context') and hasattr(st.context, 'cookies'):
                rt_cookie = st.context.cookies.get('m0v3_rt')
            if rt_cookie:
                try:
                    res = supabase.auth.refresh_session(rt_cookie)
                    if res and res.user:
                        st.session_state['user'] = res.user
                        if hasattr(res, 'session') and res.session and hasattr(res.session, 'refresh_token'):
                            st.session_state['refresh_token'] = res.session.refresh_token
                        profilo = supabase.table('profili').select('ruolo, privacy_accettata').eq('id', res.user.id).execute()
                        if profilo.data:
                            st.session_state['role'] = profilo.data[0].get('ruolo', 'Atleta')
                            st.session_state['privacy_accettata'] = bool(profilo.data[0].get('privacy_accettata'))
                        else:
                            st.session_state['role'] = 'Atleta'
                            st.session_state['privacy_accettata'] = False
                        st.rerun()
                except Exception:
                    pass

        auth_module()
        return

    # Iniezione cookie persistente e reset zoom / scroll su mobile
    if st.session_state.get('refresh_token'):
        rt = st.session_state['refresh_token']
        cookie_js = """
        <script>
        (function() {
            try {
                document.cookie = "m0v3_rt=__TOKEN__; path=/; max-age=2592000; SameSite=Lax";
                try { localStorage.setItem("m0v3_rt", "__TOKEN__"); } catch(e) {}
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

    if not st.session_state.get('privacy_accettata', False):
        st.title("Aggiornamento Privacy e Condizioni d'Uso")
        st.warning("Per continuare a utilizzare M0V3 Analytics, devi prendere visione e accettare l'Informativa sul Trattamento dei Dati Personali.")
        privacy_doc_path = "INFORMATIVA SUL TRATTAMENTO DEI DATI PERSONALI.docx"
        if os.path.exists(privacy_doc_path):
            with open(privacy_doc_path, "rb") as f_doc:
                st.download_button(
                    label="Scarica e leggi l'Informativa Privacy (.docx)",
                    data=f_doc.read(),
                    file_name="Informativa_Privacy_M0V3.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                )
        accetta = st.checkbox("Dichiaro di aver letto e accetto integralmente l'Informativa.")
        if st.button("Accetta e Continua", type="primary", disabled=not accetta):
            if user_id:
                supabase.table('profili').update({"privacy_accettata": True}).eq('id', user_id).execute()
            st.session_state['privacy_accettata'] = True
            st.rerun()
            return
        return

    if 'current_page' not in st.session_state: st.session_state.current_page = "Home"
    t = LANG[st.session_state.get('lang', 'IT')]

    # -------------------------------------------------------------
    # ROUTING ATLETA SMARTPHONE (Mobile-First Mini WebApp)
    # -------------------------------------------------------------
    device_param = st.query_params.get("device", "").lower()
    if device_param == 'desktop':
        st.session_state['view_mode'] = 'desktop'
    elif device_param == 'mobile':
        st.session_state['view_mode'] = 'mobile'

    is_mobile = (st.session_state.get('view_mode') == 'mobile')

    if is_mobile:
        import views.atleta_mobile
        _load_view(views.atleta_mobile)
        views.atleta_mobile.render_atleta_mobile(t)
        return

    # Se l'utente è un Atleta e non ha forzato la vista desktop, esegui check schermo client-side
    if st.session_state.get('role') == 'Atleta' and st.session_state.get('view_mode') != 'desktop':
        components.html("""
        <script>
        (function() {
            var isMobile = (window.innerWidth <= 768) || /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
            var url = new URL(window.parent.location.href);
            if (isMobile && url.searchParams.get('device') !== 'mobile' && url.searchParams.get('device') !== 'desktop') {
                url.searchParams.set('device', 'mobile');
                window.parent.location.replace(url.href);
            }
        })();
        </script>
        """, height=0)

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
            (tr("Carico Interno", "Internal Load"), "Carico Interno", "heart-pulse"),
            (tr("Test & Valutazioni", "Tests & Assessments"), "Test & Valutazioni", "clipboard2-pulse"),
            (tr("M0V3 Tennis Test", "M0V3 Tennis Test"), "M0V3 Tennis Test", "lightning-charge-fill"),
            (tr("Calendario & Area Medica", "Calendar & Medical Area"), "Calendario & Area Medica", "calendar-check"),
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
            st.session_state['privacy_accettata'] = False
            st.session_state['view_mode'] = None
            st.session_state['logged_out'] = True
            st.query_params.clear()
            components.html("""
            <script>
            (function() {
                try {
                    document.cookie = "m0v3_rt=; path=/; max-age=0;";
                    try { localStorage.removeItem("m0v3_rt"); } catch(e) {}
                } catch(e) {}
            })();
            </script>
            """, height=0)
            st.rerun()

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

    # ==================== ROUTING PAGINE ====================
    import pdf_generator
    if DEV_MODE:
        importlib.reload(pdf_generator)

    if not _is_menu_page_visible(active_page) and active_page not in ["Home", "Profilo Personale", "Supporto", "Diario Atleta", "Pannello Admin (Gestione Utenti)", "Statistiche Match"]:
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


if __name__ == "__main__":
    main()
