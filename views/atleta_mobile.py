import datetime
import urllib.parse
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from config import LOGO_CIRCULAR_PATH, LOGO_PATH, tr, LANG
from utils import (
    supabase,
    load_local_database,
    get_atleta_dettagli_per_utente,
    get_wellness_mattutino,
    upsert_wellness_mattutino,
    get_rpe_sessioni,
    upsert_rpe_sessione,
    delete_rpe_sessione,
    check_stato_giornaliero_atleta,
    get_sessioni_test,
    get_catalogo_protocolli,
    valuta_readiness_test,
)


def genera_promemoria_ics(time_wellness, time_srpe, app_url):
    """
    Genera un file iCalendar (.ics, RFC 5545) con due sveglie/promemoria giornalieri:
    1. Wellness mattutino
    2. sRPE serale
    Entrambi con allarme sonoro e link diretto all'applicazione.
    """
    d_today = datetime.date.today().strftime('%Y%m%d')
    w_start = time_wellness.strftime('%H%M%S')
    w_end = (datetime.datetime.combine(datetime.date.today(), time_wellness) + datetime.timedelta(minutes=15)).strftime('%H%M%S')
    r_start = time_srpe.strftime('%H%M%S')
    r_end = (datetime.datetime.combine(datetime.date.today(), time_srpe) + datetime.timedelta(minutes=15)).strftime('%H%M%S')

    summary_w = tr("M0V3: Compila Wellness Mattutino", "M0V3: Complete Morning Wellness")
    desc_w = tr(
        f"Compila i 5 parametri del tuo benessere prima di allenarti.\\nApri M0V3: {app_url}",
        f"Complete your 5 wellness parameters before training.\\nOpen M0V3: {app_url}"
    )
    valarm_w = tr("M0V3: E ora di compilare il Wellness Mattutino!", "M0V3: Time to complete your Morning Wellness!")

    summary_r = tr("M0V3: Registra Carico Sedute (sRPE)", "M0V3: Log Session Load (sRPE)")
    desc_r = tr(
        f"Registra durata e RPE delle sedute di oggi.\\nApri M0V3: {app_url}",
        f"Log duration and RPE for today's sessions.\\nOpen M0V3: {app_url}"
    )
    valarm_r = tr("M0V3: E ora di registrare il tuo sRPE di oggi!", "M0V3: Time to log your session sRPE!")

    ics = (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//M0V3 Analytics//Promemoria Atleta//IT\r\n"
        "CALSCALE:GREGORIAN\r\n"
        "METHOD:PUBLISH\r\n"
        "X-WR-CALNAME:M0V3 Promemoria Atleta\r\n"
        "BEGIN:VEVENT\r\n"
        "UID:m0v3-wellness-daily@m0v3analytics.com\r\n"
        f"DTSTAMP:{d_today}T080000Z\r\n"
        f"DTSTART:{d_today}T{w_start}\r\n"
        f"DTEND:{d_today}T{w_end}\r\n"
        "RRULE:FREQ=DAILY\r\n"
        f"SUMMARY:{summary_w}\r\n"
        f"DESCRIPTION:{desc_w}\r\n"
        f"URL:{app_url}\r\n"
        "BEGIN:VALARM\r\n"
        "TRIGGER:-PT0M\r\n"
        "ACTION:DISPLAY\r\n"
        f"DESCRIPTION:{valarm_w}\r\n"
        "END:VALARM\r\n"
        "END:VEVENT\r\n"
        "BEGIN:VEVENT\r\n"
        "UID:m0v3-srpe-daily@m0v3analytics.com\r\n"
        f"DTSTAMP:{d_today}T180000Z\r\n"
        f"DTSTART:{d_today}T{r_start}\r\n"
        f"DTEND:{d_today}T{r_end}\r\n"
        "RRULE:FREQ=DAILY\r\n"
        f"SUMMARY:{summary_r}\r\n"
        f"DESCRIPTION:{desc_r}\r\n"
        f"URL:{app_url}\r\n"
        "BEGIN:VALARM\r\n"
        "TRIGGER:-PT0M\r\n"
        "ACTION:DISPLAY\r\n"
        f"DESCRIPTION:{valarm_r}\r\n"
        "END:VALARM\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )
    return ics


def make_gcal_url(title, start_time, duration_min, desc, app_url):
    """Genera URL per aggiungere un evento ricorrente quotidiano a Google Calendar."""
    d_today = datetime.date.today().strftime('%Y%m%d')
    start_dt = f"{d_today}T{start_time.strftime('%H%M%S')}"
    end_t = (datetime.datetime.combine(datetime.date.today(), start_time) + datetime.timedelta(minutes=duration_min)).time()
    end_dt = f"{d_today}T{end_t.strftime('%H%M%S')}"
    params = {
        'action': 'TEMPLATE',
        'text': title,
        'dates': f"{start_dt}/{end_dt}",
        'details': f"{desc}\n\nApri M0V3: {app_url}",
        'recur': 'RRULE:FREQ=DAILY',
        'location': 'M0V3 Analytics'
    }
    return f"https://calendar.google.com/calendar/render?{urllib.parse.urlencode(params)}"


def _desc_sonno(val):
    if val <= 3:
        return tr("Pessimo / Notte insonne o molto frammentata", "Poor / Sleepless or fragmented night")
    if val <= 6:
        return tr("Sufficiente / Qualche risveglio", "Fair / Some awakenings")
    if val <= 8:
        return tr("Buono e rigenerante", "Good and restful")
    return tr("Sonno profondo e ottimale", "Deep and optimal sleep")


def _desc_fatica(val):
    if val <= 2:
        return tr("Fresco, reattivo e brillante (OTTIMO)", "Fresh, reactive and energetic (OPTIMAL)")
    if val <= 5:
        return tr("Fatica moderata / Fisiologica", "Moderate fatigue / Normal")
    if val <= 7:
        return tr("Affaticato / Gambe pesanti", "Fatigued / Heavy legs")
    return tr("Esaurimento fisico / Stanchezza acuta (ATTENZIONE)", "Physical exhaustion / Acute fatigue (WARNING)")


def _desc_stress(val):
    if val <= 2:
        return tr("Calmo, sereno e rilassato (OTTIMO)", "Calm, serene and relaxed (OPTIMAL)")
    if val <= 5:
        return tr("Tensione gestibile / Normale", "Manageable tension / Normal")
    if val <= 7:
        return tr("Stress elevato / Pressione", "High stress / Under pressure")
    return tr("Massimo stress / Ansia acuta (ATTENZIONE)", "Maximum stress / Acute anxiety (WARNING)")


def _desc_umore(val):
    if val <= 3:
        return tr("Demotivato / Umore a terra", "Demotivated / Low mood")
    if val <= 6:
        return tr("Neutro / Giornata normale", "Neutral / Normal day")
    if val <= 8:
        return tr("Positivo e concentrato", "Positive and focused")
    return tr("Motivazione al massimo / Super focalizzato", "Peak motivation / Highly focused")


def _desc_doms(val):
    if val <= 2:
        return tr("Muscoli sciolti / Zero indolenzimento (OTTIMO)", "Loose muscles / Zero soreness (OPTIMAL)")
    if val <= 5:
        return tr("Lieve indolenzimento fisiologico", "Mild physiological soreness")
    if val <= 7:
        return tr("Dolore muscolare marcato", "Marked muscle soreness")
    return tr("Dolore severo / Movimento limitato (ATTENZIONE)", "Severe pain / Limited movement (WARNING)")


def _desc_rpe(val):
    if val == 0:
        return "0 · " + tr("Riposo assoluto", "Absolute rest")
    if val <= 2:
        return f"{val} · " + tr("Molto leggero (Riscaldamento / Attivazione)", "Very light (Warm-up / Activation)")
    if val <= 4:
        return f"{val} · " + tr("Moderato (Aerobico fluido)", "Moderate (Smooth aerobic)")
    if val <= 6:
        return f"{val} · " + tr("Duro (Ritmo sostenuto / Impegnativo)", "Hard (Sustained pace / Demanding)")
    if val <= 8:
        return f"{val} · " + tr("Molto duro (Alta intensita agonistica)", "Very hard (High match intensity)")
    if val == 9:
        return "9 · " + tr("Estremamente duro (Quasi massimale)", "Extremely hard (Near maximal)")
    return "10 · " + tr("Massimale (Esaurimento totale)", "Maximal (Total exhaustion)")


def render_atleta_mobile(t=None):
    """
    Mini WebApp Mobile-First per Atleta:
    - Diario Quotidiano (Wellness Mattutino con polarita chiara + sRPE doppio slot).
    - Eliminazione di tutte le sedute (Slot 1 e Slot 2).
    - Sintesi rapida prestazioni GPS.
    - Test Fisici & Neuromuscolari.
    - Switch Lingua IT/EN integrato e Zero Emoji Policy.
    """
    user = st.session_state.get('user')
    if not user:
        st.error(tr("Sessione non valida.", "Invalid session."))
        st.stop()

    # 1. Recupero anagrafica atleta
    atleta = get_atleta_dettagli_per_utente(user.id)
    if not atleta:
        role = st.session_state.get('role', '')
        if role in ['Super-Admin', 'Coach', 'Staff']:
            st.info(tr("Modalita Test Coach: anteprima smartphone attiva.", "Coach Test Mode: smartphone preview active."))
            df_loc = load_local_database()
            player_col = 'Players' if (not df_loc.empty and 'Players' in df_loc.columns) else ('Player_Name' if (not df_loc.empty and 'Player_Name' in df_loc.columns) else None)
            nomi_loc = sorted(df_loc[player_col].dropna().unique().tolist()) if player_col else []
            try:
                res_all = supabase.table("atleti").select("id, nome, cognome").execute()
                nomi_db = [f"{a.get('nome','')} {a.get('cognome','')}".strip() for a in (res_all.data or []) if a]
            except Exception:
                nomi_db = []
            nomi = sorted(list(set([n for n in (nomi_loc + nomi_db) if n])))

            if nomi:
                glob_ath = st.session_state.get('selected_athlete')
                idx_def = nomi.index(glob_ath) if glob_ath in nomi else 0
                sel_nome = st.selectbox(tr("Seleziona atleta per testare:", "Select athlete to test:"), nomi, index=idx_def, key="sel_test_atl")
                st.session_state['selected_athlete'] = sel_nome
                parts = sel_nome.split(' ', 1)
                nome_p = parts[0]
                cognome_p = parts[1] if len(parts) > 1 else ""
                try:
                    resp = supabase.table("atleti").select("id, nome, cognome").eq("nome", nome_p).execute()
                    if resp.data:
                        a_row = resp.data[0]
                        atleta = {'id': a_row['id'], 'nome_completo': f"{a_row.get('nome','')} {a_row.get('cognome','')}".strip()}
                    else:
                        atleta = {'id': '00000000-0000-0000-0000-000000000000', 'nome_completo': sel_nome}
                except Exception:
                    atleta = {'id': '00000000-0000-0000-0000-000000000000', 'nome_completo': sel_nome}
            else:
                atleta = {'id': '00000000-0000-0000-0000-000000000000', 'nome_completo': 'Atleta Demo'}
        else:
            st.warning(tr("Nessun atleta associato al tuo profilo. Contatta il tuo coach per associare il tuo account.", "No athlete linked to your profile. Contact your coach to link your account."))
            if st.button(tr("Esci / Logout", "Exit / Logout"), key="logout_no_atl", use_container_width=True):
                try: supabase.auth.sign_out()
                except: pass
                st.session_state['user'] = None
                st.session_state['view_mode'] = None
                st.session_state['logged_out'] = True
                st.query_params.clear()
                st.rerun()
            st.stop()

    atleta_id = atleta['id']
    nome_atleta = atleta['nome_completo']

    # 2. Iniezione Stile M0V3 Executive Dark Cyber per Mobile (Zero Blocchi Bianchi, Contrasto Perfetto)
    st.markdown("""
    <style>
    /* Sfondo Scuro Iconico M0V3 */
    .stApp {
        background: linear-gradient(165deg, #060c18 0%, #0a1424 50%, #0d1b30 100%) !important;
        background-color: #060c18 !important;
        background-attachment: fixed !important;
        color: #e2e8f0 !important;
    }
    
    /* Previene auto-zoom su iOS Safari forzando font-size >= 16px su tutti i campi */
    input, select, textarea,
    .stTextInput input, .stNumberInput input, .stDateInput input, .stTimeInput input {
        font-size: 16px !important;
    }
    
    /* Layout Mobile Ottimizzato */
    .block-container {
        max-width: 520px !important;
        padding-top: 0.8rem !important;
        padding-bottom: 2.5rem !important;
        padding-left: 0.8rem !important;
        padding-right: 0.8rem !important;
        background: transparent !important;
    }
    
    /* Override TOTALE pulsanti su mobile: NESSUN BLOCCO BIANCO */
    .block-container .stButton > button,
    .block-container .stButton > button[kind="secondary"] {
        background: rgba(14, 165, 233, 0.12) !important;
        color: #ffffff !important;
        border: 1px solid rgba(56, 189, 248, 0.35) !important;
        border-radius: 10px !important;
        font-weight: 700 !important;
        font-size: 14px !important;
        min-height: 44px !important;
        transition: all 0.2s ease !important;
    }
    .block-container .stButton > button:hover,
    .block-container .stButton > button[kind="secondary"]:hover {
        background: rgba(14, 165, 233, 0.24) !important;
        border-color: #38bdf8 !important;
        color: #ffffff !important;
    }
    .block-container .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #0ea5e9 0%, #0284c7 100%) !important;
        color: #ffffff !important;
        border: 1px solid #38bdf8 !important;
        box-shadow: 0 4px 15px rgba(14, 165, 233, 0.35) !important;
        font-weight: 800 !important;
    }

    /* Etichette e Titoli Widget in Bianco / Ciano Visibile */
    [data-testid="stWidgetLabel"] p,
    [data-testid="stWidgetLabel"] label,
    [data-testid="stWidgetLabel"] span,
    label {
        color: #e2e8f0 !important;
        font-weight: 700 !important;
    }
    
    /* Card Container Dark Glass M0V3 */
    .m-card {
        background: linear-gradient(165deg, rgba(13, 24, 44, 0.95) 0%, rgba(8, 15, 30, 0.98) 100%) !important;
        border: 1px solid rgba(14, 165, 233, 0.30) !important;
        border-radius: 14px !important;
        padding: 15px 16px !important;
        margin-bottom: 14px !important;
        box-shadow: 0 10px 30px rgba(0,0,0,0.6), 0 0 15px rgba(14, 165, 233, 0.1) !important;
    }

    /* CONTENITORI INPUT (Date, Select, Number, Time, Text): Sfondo Scuro e Testo Bianco Visibile */
    div[data-testid="stDateInput"] input,
    div[data-testid="stDateInput"] div[data-baseweb="input"],
    div[data-testid="stDateInput"] div[data-baseweb="input"] > div,
    div[data-testid="stDateInput"] [data-baseweb="base-input"],
    div[data-testid="stTextInput"] input,
    div[data-testid="stTextInput"] div[data-baseweb="input"],
    div[data-testid="stNumberInput"] input,
    div[data-testid="stNumberInput"] div[data-baseweb="input"],
    div[data-testid="stTimeInput"] input,
    div[data-testid="stTimeInput"] div[data-baseweb="input"],
    div[data-testid="stTimeInput"] div[data-baseweb="select"] > div,
    div[data-baseweb="input"],
    div[data-baseweb="base-input"],
    .stTextInput input,
    .stNumberInput input,
    .stDateInput input,
    .stTimeInput input {
        background-color: #0b1528 !important;
        background: #0b1528 !important;
        color: #ffffff !important;
        -webkit-text-fill-color: #ffffff !important;
        border: 1px solid rgba(56, 189, 248, 0.40) !important;
        border-radius: 8px !important;
        font-weight: 700 !important;
    }

    /* SELECTBOX (Tipologia Seduta, Selezione Dropdown su Mobile) */
    div[data-testid="stSelectbox"] div[data-baseweb="select"],
    div[data-testid="stSelectbox"] div[data-baseweb="select"] > div,
    div[data-testid="stSelectbox"] div[data-baseweb="select"] div,
    div[data-testid="stSelectbox"] [role="combobox"],
    div[data-baseweb="select"],
    div[data-baseweb="select"] > div {
        background-color: #0b1528 !important;
        background: #0b1528 !important;
        color: #ffffff !important;
        border: 1px solid rgba(56, 189, 248, 0.40) !important;
        border-radius: 8px !important;
    }
    div[data-testid="stSelectbox"] span,
    div[data-testid="stSelectbox"] div[role="combobox"] span,
    div[data-testid="stSelectbox"] div[data-baseweb="select"] div[aria-selected="true"],
    div[data-testid="stSelectbox"] [data-baseweb="select"] div,
    div[data-baseweb="select"] div {
        color: #ffffff !important;
        -webkit-text-fill-color: #ffffff !important;
        font-weight: 700 !important;
    }
    div[data-testid="stSelectbox"] svg,
    div[data-baseweb="select"] svg {
        fill: #38bdf8 !important;
        color: #38bdf8 !important;
    }

    /* POPUP & DROPDOWN (Quando si apre la tendina della select o del calendario) */
    div[data-baseweb="popover"],
    div[data-baseweb="popover"] > div,
    div[data-baseweb="menu"],
    ul[role="listbox"],
    div[data-baseweb="calendar"],
    div[data-baseweb="calendar"] * {
        background-color: #0b1528 !important;
        color: #ffffff !important;
    }
    li[role="option"] {
        background-color: #0b1528 !important;
        color: #ffffff !important;
        font-weight: 700 !important;
    }
    li[role="option"]:hover,
    li[role="option"][aria-selected="true"] {
        background-color: rgba(14, 165, 233, 0.25) !important;
        color: #38bdf8 !important;
    }
    div[data-baseweb="calendar"] button {
        color: #ffffff !important;
    }
    div[data-baseweb="calendar"] [aria-label*="day"] {
        color: #ffffff !important;
    }

    /* PULSANTI STEPPER + E - DEL NUMBER INPUT */
    div[data-testid="stNumberInput"] button,
    div[data-testid="stNumberInput"] div[data-baseweb="input"] button,
    div[data-baseweb="input"] button {
        background-color: #1e293b !important;
        background: #1e293b !important;
        color: #38bdf8 !important;
        border: 1px solid rgba(56, 189, 248, 0.35) !important;
    }
    div[data-testid="stNumberInput"] button svg,
    div[data-baseweb="input"] button svg {
        fill: #38bdf8 !important;
        color: #38bdf8 !important;
    }
    div[data-testid="stNumberInput"] button:hover {
        background-color: #0284c7 !important;
        color: #ffffff !important;
    }

    /* STYLING DEL SELETTORE LINGUA COMPATTO (IT / EN) */
    div[data-testid="stRadio"] div[role="radiogroup"] {
        background: rgba(11, 21, 40, 0.90) !important;
        border: 1px solid rgba(56, 189, 248, 0.35) !important;
        border-radius: 8px !important;
        padding: 2px 6px !important;
        gap: 6px !important;
        display: flex !important;
        justify-content: center !important;
        align-items: center !important;
    }
    div[data-testid="stRadio"] div[role="radiogroup"] label {
        margin: 0 !important;
        font-size: 11.5px !important;
        font-weight: 800 !important;
        color: #ffffff !important;
        padding: 2px 4px !important;
    }
    div[data-testid="stRadio"] div[role="radiogroup"] label p,
    div[data-testid="stRadio"] div[role="radiogroup"] label span {
        color: #ffffff !important;
        -webkit-text-fill-color: #ffffff !important;
        font-weight: 800 !important;
    }

    /* EXPANDER (Wellness Mattutino, Carico Sessioni, Promemoria: Zero Header Bianco) */
    div[data-testid="stExpander"] {
        background: rgba(13, 24, 44, 0.90) !important;
        border: 1px solid rgba(56, 189, 248, 0.35) !important;
        border-radius: 12px !important;
        margin-bottom: 12px !important;
        overflow: hidden !important;
    }
    div[data-testid="stExpander"] > details,
    div[data-testid="stExpander"] details {
        border-radius: 12px !important;
        background: transparent !important;
    }
    div[data-testid="stExpander"] summary,
    div[data-testid="stExpander"] > details > summary,
    div[data-testid="stExpander"] details summary,
    div[data-testid="stExpander"] summary:hover,
    div[data-testid="stExpander"] summary:focus,
    div[data-testid="stExpander"] summary:active {
        background-color: #0d1b30 !important;
        background: #0d1b30 !important;
        color: #ffffff !important;
        font-weight: 800 !important;
        font-size: 14px !important;
        border-radius: 10px !important;
        border: none !important;
    }
    div[data-testid="stExpander"] summary p,
    div[data-testid="stExpander"] summary span,
    div[data-testid="stExpander"] summary div,
    div[data-testid="stExpander"] details summary p,
    div[data-testid="stExpander"] details summary span {
        color: #ffffff !important;
        -webkit-text-fill-color: #ffffff !important;
        font-weight: 800 !important;
    }
    div[data-testid="stExpander"] summary svg,
    div[data-testid="stExpander"] details summary svg {
        fill: #38bdf8 !important;
        color: #38bdf8 !important;
    }
    div[data-testid="stExpander"] div[data-testid="stExpanderDetails"] {
        padding: 12px 14px !important;
        background: rgba(13, 24, 44, 0.60) !important;
        border-top: 1px solid rgba(56, 189, 248, 0.20) !important;
    }

    /* TESTI E CAPTION DI SUPPORTO (Descrizioni Sliders e Sottotitoli) */
    [data-testid="stCaptionContainer"],
    [data-testid="stCaptionContainer"] p,
    .stCaption,
    small {
        color: #cbd5e1 !important;
        font-size: 12px !important;
        font-weight: 600 !important;
    }

    /* SLIDERS */
    .stSlider label, .stSlider div {
        color: #cbd5e1 !important;
    }

    /* CHECKBOX */
    div[data-testid="stCheckbox"] label,
    div[data-testid="stCheckbox"] label p,
    div[data-testid="stCheckbox"] label span {
        color: #e2e8f0 !important;
        font-weight: 700 !important;
        font-size: 13.5px !important;
    }

    /* PLACEHOLDER */
    input::placeholder,
    textarea::placeholder {
        color: #64748b !important;
        opacity: 1 !important;
    }
    </style>
    """, unsafe_allow_html=True)

    # Reset automatico dello scroll in cima e blocco zoom Safari
    st.components.v1.html("""
    <script>
    (function() {
        try {
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
    """, height=0)

    # 3. Header Top Bar Compatta con Switcher Lingua & Logout
    col_h1, col_h_lang, col_h2 = st.columns([2.3, 1.2, 1.1])
    with col_h1:
        st.markdown(f"""
        <div style='display: flex; align-items: center; gap: 8px;'>
            <div style='background: rgba(14, 165, 233, 0.2); width: 36px; height: 36px; border-radius: 50%; display: flex; align-items: center; justify-content: center; border: 1px solid #38bdf8; flex-shrink: 0;'>
                <span style='color: #38bdf8; font-size: 17px; font-weight: 900;'>M</span>
            </div>
            <div style='min-width: 0;'>
                <div style='font-size: 9px; color: #38bdf8; font-weight: 800; letter-spacing: 1px; text-transform: uppercase;'>MOV3 ATHLETE</div>
                <div style='font-size: 15px; color: #ffffff; font-weight: 900; line-height: 1.1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;'>{nome_atleta}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with col_h_lang:
        lang_curr = st.session_state.get('lang', 'IT')
        scelta_lang_mob = st.radio(
            "Lang",
            ["IT", "EN"],
            index=0 if lang_curr == 'IT' else 1,
            horizontal=True,
            key="mobile_lang_switch",
            label_visibility="collapsed"
        )
        if scelta_lang_mob != lang_curr:
            st.session_state['lang'] = scelta_lang_mob
            st.rerun()

    with col_h2:
        if st.button(tr("Esci", "Logout"), key="btn_logout_mobile", use_container_width=True):
            try: supabase.auth.sign_out()
            except: pass
            st.session_state['user'] = None
            st.session_state['refresh_token'] = None
            st.session_state['view_mode'] = None
            st.session_state['logged_out'] = True
            st.query_params.clear()
            st.query_params['logged_out'] = '1'
            st.components.v1.html("""
            <script>
            (function() {
                try {
                    document.cookie = "m0v3_rt=; path=/; max-age=0;";
                    try { localStorage.removeItem("m0v3_rt"); } catch(e) {}
                    if (window.parent && window.parent !== window) {
                        try { window.parent.document.cookie = "m0v3_rt=; path=/; max-age=0;"; } catch(e) {}
                        try { window.parent.localStorage.removeItem("m0v3_rt"); } catch(e) {}
                    }
                } catch(e) {}
            })();
            </script>
            """, height=0)
            st.rerun()

    st.markdown("<div style='margin-bottom: 10px;'></div>", unsafe_allow_html=True)

    # 4. Navigazione Data con pulsanti espliciti
    oggi = datetime.date.today()
    if 'data_mobile_sel' not in st.session_state:
        st.session_state['data_mobile_sel'] = oggi

    def _step_date(offset_days):
        curr = st.session_state.get('data_mobile_sel', datetime.date.today())
        st.session_state['data_mobile_sel'] = curr + datetime.timedelta(days=offset_days)

    col_btn_prev, col_btn_next = st.columns(2)
    with col_btn_prev:
        st.button("< " + tr("Giorno Prec.", "Prev Day"), key="btn_prev_day", on_click=_step_date, args=(-1,), use_container_width=True)
    with col_btn_next:
        st.button(tr("Giorno Succ.", "Next Day") + " >", key="btn_next_day", on_click=_step_date, args=(1,), use_container_width=True)

    st.date_input(
        tr("Data Selezionata", "Selected Date"),
        key="data_mobile_sel"
    )

    data_str = st.session_state['data_mobile_sel'].strftime('%Y-%m-%d')
    data_label = st.session_state['data_mobile_sel'].strftime('%d/%m/%Y')
    is_oggi = (st.session_state['data_mobile_sel'] == oggi)

    # 5. Navigazione Sezioni (Tre Pulsanti Tab ad Altissima Visibilita)
    if 'tab_mobile_nav_key' not in st.session_state:
        st.session_state['tab_mobile_nav_key'] = "diario"

    col_t1, col_t2, col_t3 = st.columns(3)
    with col_t1:
        type_t1 = "primary" if st.session_state['tab_mobile_nav_key'] == "diario" else "secondary"
        if st.button(tr("Diario", "Diary"), key="btn_nav_diario", use_container_width=True, type=type_t1):
            st.session_state['tab_mobile_nav_key'] = "diario"
            st.rerun()
    with col_t2:
        type_t2 = "primary" if st.session_state['tab_mobile_nav_key'] == "prestazioni" else "secondary"
        if st.button(tr("Prestazioni", "Performance"), key="btn_nav_prestazioni", use_container_width=True, type=type_t2):
            st.session_state['tab_mobile_nav_key'] = "prestazioni"
            st.rerun()
    with col_t3:
        type_t3 = "primary" if st.session_state['tab_mobile_nav_key'] == "test" else "secondary"
        if st.button(tr("I Miei Test", "My Tests"), key="btn_nav_test", use_container_width=True, type=type_t3):
            st.session_state['tab_mobile_nav_key'] = "test"
            st.rerun()

    tab_scelta = st.session_state['tab_mobile_nav_key']

    st.markdown("<div style='margin-bottom: 10px;'></div>", unsafe_allow_html=True)

    # =========================================================================
    # SEZIONE 1: DIARIO QUOTIDIANO (Wellness Mattutino + sRPE Serale)
    # =========================================================================
    if tab_scelta == "diario":
        stato_giorno = check_stato_giornaliero_atleta(atleta_id, data_str)
        w_fatto = stato_giorno['wellness_compilato']
        w_data = stato_giorno['wellness_dati']
        r_fatto = stato_giorno['rpe_compilato']
        r_sessioni = stato_giorno['rpe_sessioni']

        lbl_oggi = tr("OGGI", "TODAY")
        lbl_storico = tr("STORICO", "HISTORY")
        data_badge = f"<span style='color: #38bdf8; font-weight:800;'>{lbl_oggi} ({data_label})</span>" if is_oggi else f"<span style='color: #f59e0b; font-weight:800;'>{lbl_storico} ({data_label})</span>"
        st.markdown(f"<div style='font-size: 13px; color: #94a3b8; text-align: center; margin-bottom: 8px;'>{tr('Rilevazione:', 'Log Entry:')} {data_badge}</div>", unsafe_allow_html=True)

        # Rilevamento URL base per i promemoria calendario
        app_url = "https://webapptennisgps.streamlit.app?device=mobile"
        if hasattr(st, 'secrets') and 'app' in st.secrets and 'base_url' in st.secrets['app']:
            app_url = f"{st.secrets['app']['base_url']}?device=mobile"
        elif hasattr(st, 'context') and hasattr(st.context, 'headers') and st.context.headers.get('host'):
            host = st.context.headers.get('host')
            proto = "https" if ("streamlit.app" in host or "https" in host) else "http"
            app_url = f"{proto}://{host}?device=mobile"

        # Promemoria Notifiche Calendario Smartphone
        with st.expander(tr("Promemoria Notifiche Calendario (iPhone / Android)", "Calendar Notification Reminders (iPhone / Android)"), expanded=False):
            st.markdown(f"""
            <div style='background: rgba(14, 165, 233, 0.08); border: 1px solid rgba(14, 165, 233, 0.22); border-radius: 8px; padding: 10px 12px; margin-bottom: 12px; font-size: 12px; color: #cbd5e1; line-height: 1.45;'>
                {tr("Imposta una notifica/sveglia automatica quotidiana sul calendario del tuo smartphone (iPhone o Android). La notifica suonera all'orario scelto con il <b>link diretto all'app</b> per compilare in 20 secondi.", "Set a daily recurring notification on your smartphone calendar (iPhone or Android). The notification alerts you at chosen times with a <b>direct link to the app</b> to complete in 20 seconds.")}
            </div>
            """, unsafe_allow_html=True)

            c_t1, c_t2 = st.columns(2)
            with c_t1:
                t_well = st.time_input(tr("Wellness Mattutino", "Morning Wellness"), value=datetime.time(8, 30), key="rem_time_w")
            with c_t2:
                t_srpe = st.time_input(tr("sRPE Serale", "Evening sRPE"), value=datetime.time(20, 30), key="rem_time_r")

            ics_bytes = genera_promemoria_ics(t_well, t_srpe, app_url).encode('utf-8')

            st.download_button(
                label=tr("Aggiungi a Calendario (iPhone / Apple / Outlook)", "Add to Calendar (iPhone / Apple / Outlook)"),
                data=ics_bytes,
                file_name="m0v3_promemoria_diario.ics",
                mime="text/calendar",
                type="primary",
                use_container_width=True,
                key="btn_dl_ics_reminders"
            )

            st.markdown(f"""
            <div style='font-size: 11px; color: #94a3b8; margin-top: -4px; margin-bottom: 10px;'>
                {tr("<b>Su iPhone</b>: tocca il pulsante sopra, poi conferma <i>'Aggiungi tutti'</i> per salvare i promemoria con allarme in Calendario.", "<b>On iPhone</b>: tap the button above, then confirm <i>'Add all'</i> to save the reminders with alarms in Calendar.")}
            </div>
            """, unsafe_allow_html=True)

            col_g1, col_g2 = st.columns(2)
            with col_g1:
                gcal_w = make_gcal_url(tr("M0V3: Wellness Mattutino", "M0V3: Morning Wellness"), t_well, 15, tr("Compila il tuo wellness quotidiano su M0V3", "Complete your daily wellness on M0V3"), app_url)
                st.link_button(tr("Google Cal: Wellness", "Google Cal: Wellness"), gcal_w, use_container_width=True)
            with col_g2:
                gcal_r = make_gcal_url(tr("M0V3: Registra Carico sRPE", "M0V3: Log Session sRPE"), t_srpe, 15, tr("Registra la durata e l'RPE della seduta su M0V3", "Log session duration and RPE on M0V3"), app_url)
                st.link_button(tr("Google Cal: sRPE", "Google Cal: sRPE"), gcal_r, use_container_width=True)

        st.markdown("<div style='margin-bottom: 8px;'></div>", unsafe_allow_html=True)

        # -------------------------------------------------------------
        # A. WELLNESS MATTUTINO (Reattivo in Tempo Reale)
        # -------------------------------------------------------------
        w_badge_txt = tr("COMPILATO", "COMPLETED") if w_fatto else tr("DA COMPILARE", "PENDING")
        w_badge = f"<span style='background: rgba(16, 185, 129, 0.2); color: #34d399; font-size: 10px; font-weight: 800; padding: 3px 8px; border-radius: 6px; border: 1px solid rgba(16, 185, 129, 0.4);'>{w_badge_txt}</span>" if w_fatto else f"<span style='background: rgba(239, 68, 68, 0.2); color: #f87171; font-size: 10px; font-weight: 800; padding: 3px 8px; border-radius: 6px; border: 1px solid rgba(239, 68, 68, 0.4);'>{w_badge_txt}</span>"

        exp_w_title = f"{tr('Wellness Mattutino', 'Morning Wellness')} { '· ' + str(stato_giorno['wellness_score']) + '/10' if w_fatto else '' }"
        with st.expander(exp_w_title, expanded=True):
            st.markdown(f"""
            <div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;'>
                <div style='font-size: 12px; color: #94a3b8; font-weight: 700;'>{tr("Check-in del risveglio (1-10)", "Morning check-in (1-10)")}</div>
                {w_badge}
            </div>
            """, unsafe_allow_html=True)

            k_sonno = f"sl_sonno_{data_str}"
            k_fatica = f"sl_fatica_{data_str}"
            k_stress = f"sl_stress_{data_str}"
            k_umore = f"sl_umore_{data_str}"
            k_doms = f"sl_doms_{data_str}"
            k_note = f"txt_note_{data_str}"

            if k_sonno not in st.session_state:
                st.session_state[k_sonno] = int(w_data['sonno_qualita']) if w_fatto else 8
            if k_fatica not in st.session_state:
                st.session_state[k_fatica] = int(w_data['fatica']) if w_fatto else 2
            if k_stress not in st.session_state:
                st.session_state[k_stress] = int(w_data['stress']) if w_fatto else 2
            if k_umore not in st.session_state:
                st.session_state[k_umore] = int(w_data['umore']) if w_fatto else 8
            if k_doms not in st.session_state:
                st.session_state[k_doms] = int(w_data['doms']) if w_fatto else 2
            if k_note not in st.session_state:
                st.session_state[k_note] = str(w_data.get('note', '') or '') if w_fatto else ""

            # Slider 1: Sonno
            st.markdown(f"<div style='font-size: 13px; font-weight: 700; color: #ffffff; margin-top: 4px;'>{tr('1. Qualita del Sonno', '1. Sleep Quality')} <span style='font-size: 11px; color:#38bdf8;'>{tr('(1 = Pessimo <-> 10 = Perfetto)', '(1 = Poor <-> 10 = Perfect)')}</span></div>", unsafe_allow_html=True)
            v_sonno = st.slider("Sonno", 1, 10, key=k_sonno, label_visibility="collapsed")
            st.caption(_desc_sonno(v_sonno))

            # Slider 2: Fatica
            st.markdown(f"<div style='font-size: 13px; font-weight: 700; color: #ffffff; margin-top: 8px;'>{tr('2. Fatica Generale', '2. General Fatigue')} <span style='font-size: 11px; color:#34d399;'>{tr('(1 = Fresco [Ottimo] <-> 10 = Esausto [Allerta])', '(1 = Fresh [Optimal] <-> 10 = Exhausted [Alert])')}</span></div>", unsafe_allow_html=True)
            v_fatica = st.slider("Fatica", 1, 10, key=k_fatica, label_visibility="collapsed")
            st.caption(_desc_fatica(v_fatica))

            # Slider 3: Stress
            st.markdown(f"<div style='font-size: 13px; font-weight: 700; color: #ffffff; margin-top: 8px;'>{tr('3. Livello di Stress', '3. Stress Level')} <span style='font-size: 11px; color:#34d399;'>{tr('(1 = Sereno [Ottimo] <-> 10 = Massimo Stress [Allerta])', '(1 = Calm [Optimal] <-> 10 = Maximum Stress [Alert])')}</span></div>", unsafe_allow_html=True)
            v_stress = st.slider("Stress", 1, 10, key=k_stress, label_visibility="collapsed")
            st.caption(_desc_stress(v_stress))

            # Slider 4: Umore
            st.markdown(f"<div style='font-size: 13px; font-weight: 700; color: #ffffff; margin-top: 8px;'>{tr('4. Umore / Motivazione', '4. Mood / Motivation')} <span style='font-size: 11px; color:#38bdf8;'>{tr('(1 = Demotivato <-> 10 = Massima Carica)', '(1 = Demotivated <-> 10 = Peak Drive)')}</span></div>", unsafe_allow_html=True)
            v_umore = st.slider("Umore", 1, 10, key=k_umore, label_visibility="collapsed")
            st.caption(_desc_umore(v_umore))

            # Slider 5: DOMS
            st.markdown(f"<div style='font-size: 13px; font-weight: 700; color: #ffffff; margin-top: 8px;'>{tr('5. Indolenzimento Muscolare (DOMS)', '5. Muscle Soreness (DOMS)')} <span style='font-size: 11px; color:#34d399;'>{tr('(1 = Zero Dolore [Ottimo] <-> 10 = Dolore Severo [Allerta])', '(1 = Zero Pain [Optimal] <-> 10 = Severe Pain [Alert])')}</span></div>", unsafe_allow_html=True)
            v_doms = st.slider("DOMS", 1, 10, key=k_doms, label_visibility="collapsed")
            st.caption(_desc_doms(v_doms))

            v_note = st.text_input(
                tr("Note o fastidi fisici (opzionale):", "Notes or physical discomfort (optional):"),
                key=k_note,
                placeholder=tr("Es. Lieve fastidio spalla destra...", "E.g. Slight right shoulder tightness...")
            )

            # Calcolo Live Indice Wellness Globale (1-10)
            score_pos_live = v_sonno + v_umore
            score_neg_live = (11 - v_fatica) + (11 - v_stress) + (11 - v_doms)
            score_calc_live = round((score_pos_live + score_neg_live) / 5.0, 1)

            colore_live = "#34d399" if score_calc_live >= 7.0 else ("#f59e0b" if score_calc_live >= 5.0 else "#ef4444")
            giudizio_live = tr("Ottimale / Pronto", "Optimal / Ready") if score_calc_live >= 7.0 else (tr("Attenzione / Monitorare", "Caution / Monitor") if score_calc_live >= 5.0 else tr("Affaticamento Marcato", "Marked Fatigue"))

            st.markdown(f"""
            <div style='background: rgba(14, 165, 233, 0.1); border: 1px solid rgba(14, 165, 233, 0.3); border-radius: 10px; padding: 10px 14px; margin: 12px 0; display:flex; justify-content:space-between; align-items:center;'>
                <div>
                    <div style='font-size: 11px; color: #94a3b8; font-weight: 700; text-transform: uppercase;'>{tr("Indice Wellness Calcolato", "Calculated Wellness Index")}</div>
                    <div style='font-size: 12px; color: {colore_live}; font-weight: 800;'>{giudizio_live}</div>
                </div>
                <div style='font-size: 22px; font-weight: 900; color: {colore_live};'>{score_calc_live} <span style='font-size: 12px; color: #94a3b8;'>/ 10</span></div>
            </div>
            """, unsafe_allow_html=True)

            btn_label_w = tr("Aggiorna Wellness", "Update Wellness") if w_fatto else tr("Salva Wellness Mattutino", "Save Morning Wellness")
            if st.button(btn_label_w, key="btn_save_w_direct", type="primary", use_container_width=True):
                payload = {
                    "atleta_id": atleta_id,
                    "profilo_id": user.id,
                    "data": data_str,
                    "sonno_qualita": v_sonno,
                    "fatica": v_fatica,
                    "stress": v_stress,
                    "umore": v_umore,
                    "doms": v_doms,
                    "note": v_note.strip() if v_note else None
                }
                ok, res = upsert_wellness_mattutino(payload)
                if ok:
                    st.success(tr("Wellness registrato correttamente!", "Wellness saved successfully!"))
                    st.rerun()
                else:
                    st.error(f"{tr('Errore:', 'Error:')} {res}")

        st.markdown("<div style='margin-bottom: 12px;'></div>", unsafe_allow_html=True)

        # -------------------------------------------------------------
        # B. CARICO DI SESSIONE (sRPE SERALE) - Doppio Slot & Eliminazione
        # -------------------------------------------------------------
        tot_carico = stato_giorno['rpe_tot_carico']
        r_badge_txt = f"{tr('REGISTRATO', 'LOGGED')} ({tot_carico} TL)" if r_fatto else tr("DA REGISTRARE", "PENDING")
        r_badge = f"<span style='background: rgba(16, 185, 129, 0.2); color: #34d399; font-size: 10px; font-weight: 800; padding: 3px 8px; border-radius: 6px; border: 1px solid rgba(16, 185, 129, 0.4);'>{r_badge_txt}</span>" if r_fatto else f"<span style='background: rgba(239, 68, 68, 0.2); color: #f87171; font-size: 10px; font-weight: 800; padding: 3px 8px; border-radius: 6px; border: 1px solid rgba(239, 68, 68, 0.4);'>{r_badge_txt}</span>"

        exp_r_title = f"{tr('Carico Sessioni (sRPE)', 'Session Load (sRPE)')} { '· ' + str(tot_carico) + ' TL' if r_fatto else '' }"
        with st.expander(exp_r_title, expanded=True):
            st.markdown(f"""
            <div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;'>
                <div style='font-size: 12px; color: #94a3b8; font-weight: 700;'>{tr("Durata (min) x Intensita RPE (0-10)", "Duration (min) x RPE Intensity (0-10)")}</div>
                {r_badge}
            </div>
            """, unsafe_allow_html=True)

            tipologie_opzioni = ["Tennis", "Preparazione Fisica", "Gym", "Recupero", "Altro"]
            tipologie_labels = [tr("Tennis", "Tennis"), tr("Preparazione Fisica", "Fitness / Conditioning"), tr("Gym", "Gym / Strength"), tr("Recupero", "Recovery"), tr("Altro", "Other")]
            tipo_map = dict(zip(tipologie_opzioni, tipologie_labels))
            inv_tipo_map = dict(zip(tipologie_labels, tipologie_opzioni))

            slot1_data = next((s for s in r_sessioni if s.get('slot') == 1), None)
            slot2_data = next((s for s in r_sessioni if s.get('slot') == 2), None)

            # --- SLOT 1 ---
            st.markdown(f"<div style='font-size: 13.5px; font-weight: 800; color: #38bdf8; margin-top: 6px; margin-bottom: 6px;'>{tr('Seduta 1 (Slot Principale)', 'Session 1 (Primary Slot)')}</div>", unsafe_allow_html=True)

            k_s1_tipo = f"s1_tipo_{data_str}"
            k_s1_dur = f"s1_dur_{data_str}"
            k_s1_rpe = f"s1_rpe_{data_str}"

            curr_tipo1 = slot1_data['tipologia'] if slot1_data else "Tennis"
            def_tipo_idx1 = tipologie_opzioni.index(curr_tipo1) if curr_tipo1 in tipologie_opzioni else 0

            s1_tipo_lbl = st.selectbox(tr("Tipologia Seduta 1", "Session 1 Type"), tipologie_labels, index=def_tipo_idx1, key=k_s1_tipo)
            s1_tipo = inv_tipo_map.get(s1_tipo_lbl, "Tennis")

            s1_durata = st.number_input(
                tr("Durata Seduta 1 (minuti)", "Session 1 Duration (minutes)"),
                min_value=1,
                max_value=360,
                value=int(slot1_data['durata_minuti']) if slot1_data else 90,
                step=5,
                key=k_s1_dur
            )

            s1_rpe = st.slider(
                tr("Intensita RPE Seduta 1 (Scala Borg 0-10)", "Session 1 RPE Intensity (Borg Scale 0-10)"),
                0, 10,
                value=int(slot1_data['rpe']) if slot1_data else 6,
                key=k_s1_rpe
            )
            st.caption(f"{tr('Intensita percepita:', 'Perceived intensity:')} **{_desc_rpe(s1_rpe)}**")

            s1_tl = int(s1_durata) * int(s1_rpe)
            st.markdown(f"""
            <div style='background: rgba(14, 165, 233, 0.12); border: 1px solid rgba(14, 165, 233, 0.3); border-radius: 8px; padding: 7px 12px; margin-bottom: 10px; font-size: 13px; font-weight: 800; color: #38bdf8;'>
                {tr("Carico Seduta 1:", "Session 1 Load:")} {s1_durata} min x {s1_rpe} RPE = {s1_tl} TL
            </div>
            """, unsafe_allow_html=True)

            col_s1_save, col_s1_del = st.columns([2, 1]) if slot1_data else (st.container(), None)
            with (col_s1_save if slot1_data else st.container()):
                btn_s1_lbl = tr("Aggiorna Seduta 1", "Update Session 1") if slot1_data else tr("Salva Seduta 1", "Save Session 1")
                if st.button(btn_s1_lbl, key="btn_save_s1_direct", type="primary", use_container_width=True):
                    payload1 = {
                        "atleta_id": atleta_id,
                        "profilo_id": user.id,
                        "data": data_str,
                        "slot": 1,
                        "tipologia": s1_tipo,
                        "durata_minuti": int(s1_durata),
                        "rpe": int(s1_rpe)
                    }
                    ok, res = upsert_rpe_sessione(payload1)
                    if ok:
                        st.success(tr("Seduta 1 registrata!", "Session 1 saved!"))
                        st.rerun()
                    else:
                        st.error(f"{tr('Errore:', 'Error:')} {res}")

            if slot1_data and col_s1_del:
                with col_s1_del:
                    if st.button(tr("Elimina", "Delete"), key="btn_del_s1_direct", use_container_width=True):
                        delete_rpe_sessione(slot1_data['id'])
                        st.success(tr("Seduta 1 eliminata!", "Session 1 deleted!"))
                        st.rerun()

            st.markdown("<hr style='border: none; border-top: 1px dashed rgba(255,255,255,0.12); margin: 16px 0;'>", unsafe_allow_html=True)

            # --- SLOT 2 (Doppia Seduta) ---
            chk_slot2_key = f"chk_attiva_slot2_{data_str}"
            attiva_slot2 = st.checkbox(
                tr("Aggiungi / Modifica Seconda Seduta (Slot 2)", "Add / Edit Second Session (Slot 2)"),
                value=slot2_data is not None,
                key=chk_slot2_key
            )

            if attiva_slot2:
                st.markdown(f"<div style='font-size: 13.5px; font-weight: 800; color: #34d399; margin-top: 6px; margin-bottom: 6px;'>{tr('Seduta 2 (Doppia Seduta)', 'Session 2 (Double Session)')}</div>", unsafe_allow_html=True)

                k_s2_tipo = f"s2_tipo_{data_str}"
                k_s2_dur = f"s2_dur_{data_str}"
                k_s2_rpe = f"s2_rpe_{data_str}"

                curr_tipo2 = slot2_data['tipologia'] if slot2_data else "Preparazione Fisica"
                def_tipo_idx2 = tipologie_opzioni.index(curr_tipo2) if curr_tipo2 in tipologie_opzioni else 1

                s2_tipo_lbl = st.selectbox(tr("Tipologia Seduta 2", "Session 2 Type"), tipologie_labels, index=def_tipo_idx2, key=k_s2_tipo)
                s2_tipo = inv_tipo_map.get(s2_tipo_lbl, "Preparazione Fisica")

                s2_durata = st.number_input(
                    tr("Durata Seduta 2 (minuti)", "Session 2 Duration (minutes)"),
                    min_value=1,
                    max_value=360,
                    value=int(slot2_data['durata_minuti']) if slot2_data else 60,
                    step=5,
                    key=k_s2_dur
                )

                s2_rpe = st.slider(
                    tr("Intensita RPE Seduta 2 (Scala Borg 0-10)", "Session 2 RPE Intensity (Borg Scale 0-10)"),
                    0, 10,
                    value=int(slot2_data['rpe']) if slot2_data else 5,
                    key=k_s2_rpe
                )
                st.caption(f"{tr('Intensita percepita:', 'Perceived intensity:')} **{_desc_rpe(s2_rpe)}**")

                s2_tl = int(s2_durata) * int(s2_rpe)
                st.markdown(f"""
                <div style='background: rgba(16, 185, 129, 0.12); border: 1px solid rgba(16, 185, 129, 0.3); border-radius: 8px; padding: 7px 12px; margin-bottom: 10px; font-size: 13px; font-weight: 800; color: #34d399;'>
                    {tr("Carico Seduta 2:", "Session 2 Load:")} {s2_durata} min x {s2_rpe} RPE = {s2_tl} TL
                </div>
                """, unsafe_allow_html=True)

                col_s2_save, col_s2_del = st.columns([2, 1]) if slot2_data else (st.container(), None)
                with (col_s2_save if slot2_data else st.container()):
                    btn_s2_lbl = tr("Aggiorna Seduta 2", "Update Session 2") if slot2_data else tr("Salva Seduta 2", "Save Session 2")
                    if st.button(btn_s2_lbl, key="btn_save_s2_direct", type="primary", use_container_width=True):
                        payload2 = {
                            "atleta_id": atleta_id,
                            "profilo_id": user.id,
                            "data": data_str,
                            "slot": 2,
                            "tipologia": s2_tipo,
                            "durata_minuti": int(s2_durata),
                            "rpe": int(s2_rpe)
                        }
                        ok, res = upsert_rpe_sessione(payload2)
                        if ok:
                            st.success(tr("Seduta 2 registrata!", "Session 2 saved!"))
                            st.rerun()
                        else:
                            st.error(f"{tr('Errore:', 'Error:')} {res}")

                if slot2_data and col_s2_del:
                    with col_s2_del:
                        if st.button(tr("Elimina", "Delete"), key="btn_del_s2_direct", use_container_width=True):
                            delete_rpe_sessione(slot2_data['id'])
                            st.success(tr("Seduta 2 eliminata!", "Session 2 deleted!"))
                            st.rerun()

    # =========================================================================
    # SEZIONE 2: LE MIE PRESTAZIONI (Sintesi GPS Mobile-First)
    # =========================================================================
    elif tab_scelta == "prestazioni":
        df_all = load_local_database()
        df_atleta = pd.DataFrame()

        if not df_all.empty and 'Players' in df_all.columns:
            df_atleta = df_all[df_all['Players'].astype(str).str.strip().str.lower() == nome_atleta.strip().lower()].copy()

        st.markdown(f"<div style='font-size: 13px; color: #94a3b8; font-weight: 700; margin-bottom: 10px;'>{tr('Riepilogo Rapido Prestazioni GPS', 'GPS Performance Quick Summary')}</div>", unsafe_allow_html=True)

        if df_atleta.empty:
            st.info(tr("Nessun dato GPS storico trovato per il tuo nominativo. I dati compariranno automaticamente non appena il tuo coach carichera le sessioni GPS.", "No historical GPS data found for your profile. Data will appear automatically as soon as your coach uploads GPS sessions."))
        else:
            if 'Date_obj' in df_atleta.columns:
                df_atleta = df_atleta.sort_values('Date_obj', ascending=False)
            
            ultima_sess = df_atleta.iloc[0]
            data_ult = ultima_sess.get('Date', 'N/D')
            tipo_ult = str(ultima_sess.get('Tipologia Sessione', ultima_sess.get('Session', 'Sessione'))).strip()

            # Riconoscimento rigoroso match vs allenamento
            is_curr_match = tipo_ult.lower() in ['match', 'match doppio']
            is_match_all = df_atleta['Tipologia Sessione'].astype(str).str.strip().str.lower().isin(['match', 'match doppio'])
            df_matches = df_atleta[is_match_all]
            df_tipo = df_atleta[df_atleta['Tipologia Sessione'].astype(str).str.strip().str.lower() == tipo_ult.lower()]

            badge_tipo_sess = tr("MATCH", "MATCH") if is_curr_match else tr("ALLENAMENTO", "TRAINING")
            header_card_html = (
                f"<div class='m-card' style='margin-bottom:12px;'>"
                f"<div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;'>"
                f"<span style='font-size:11px; color:#38bdf8; font-weight:800; text-transform:uppercase;'>{tr('Ultima Sessione Registrata', 'Latest Logged Session')}</span>"
                f"<span style='font-size:11px; color:#94a3b8; font-weight:700;'>{data_ult}</span>"
                f"</div>"
                f"<div style='display:flex; justify-content:space-between; align-items:center;'>"
                f"<div style='font-size:17px; font-weight:900; color:#ffffff;'>{tipo_ult}</div>"
                f"<span style='background:rgba(14,165,233,0.15); border:1px solid rgba(14,165,233,0.35); border-radius:6px; padding:2px 8px; font-size:10.5px; font-weight:800; color:#38bdf8;'>{badge_tipo_sess}</span>"
                f"</div>"
                f"</div>"
            )
            st.markdown(header_card_html, unsafe_allow_html=True)

            def _format_delta_badge(delta):
                if delta is None:
                    return "<span style='color: #64748b; font-weight: 700;'>N/D</span>"
                if delta > 0:
                    return f"<span style='color: #34d399; font-weight: 800;'>+ {delta:.1f}%</span>"
                elif delta < 0:
                    return f"<span style='color: #f87171; font-weight: 800;'>- {abs(delta):.1f}%</span>"
                else:
                    return "<span style='color: #94a3b8; font-weight: 700;'>= 0.0%</span>"

            # 5 Metriche Richieste con Benchmark
            metriche_config = [
                (tr("1. TRAINING LOAD", "1. TRAINING LOAD"), "Training Load", "TL"),
                (tr("2. TRAINING LOAD HIGH", "2. TRAINING LOAD HIGH"), "TL_High", "TL"),
                (tr("3. ACCELERAZIONI IMU", "3. IMU ACCELERATIONS"), "High Accel IMU", "ev"),
                (tr("4. DECELERAZIONI IMU", "4. IMU DECELERATIONS"), "High Decel IMU", "ev"),
                (tr('5. AZIONI >2"', '5. INTENSE ACTIONS >2"'), "Azioni Int. IMU >2", "ev")
            ]

            def _to_f(val_raw):
                try:
                    if pd.isna(val_raw): return 0.0
                    return float(val_raw)
                except Exception:
                    return 0.0

            for titolo, col_name, unita in metriche_config:
                val_raw = ultima_sess.get(col_name)
                if val_raw is None and col_name == "Azioni Int. IMU >2":
                    val_raw = ultima_sess.get('Azioni Int. IMU >2"') or ultima_sess.get('Azioni Int. >2')

                val = _to_f(val_raw)

                c_target = col_name
                if col_name not in df_atleta.columns and col_name == "Azioni Int. IMU >2":
                    for alt_c in ['Azioni Int. IMU >2"', 'Azioni Int. >2']:
                        if alt_c in df_atleta.columns: 
                            c_target = alt_c
                            break

                s_tipo = pd.to_numeric(df_tipo[c_target], errors='coerce').dropna() if (not df_tipo.empty and c_target in df_tipo.columns) else pd.Series(dtype=float)
                s_match = pd.to_numeric(df_matches[c_target], errors='coerce').dropna() if (not df_matches.empty and c_target in df_matches.columns) else pd.Series(dtype=float)

                avg_tipo = float(s_tipo.mean()) if not s_tipo.empty else 0.0
                avg_match = float(s_match.mean()) if not s_match.empty else 0.0

                delta_tipo = ((val - avg_tipo) / avg_tipo * 100) if avg_tipo > 0 else None
                delta_match = ((val - avg_match) / avg_match * 100) if avg_match > 0 else None

                lbl_vs_match = tr("vs Media Match:", "vs Match Avg:")
                lbl_vs_tipo = tr(f"vs Media {tipo_ult}:", f"vs {tipo_ult} Avg:")

                if is_curr_match:
                    bench_row = (
                        f"<div style='display:flex; justify-content:space-between; align-items:center; font-size:11.5px; color:#94a3b8;'>"
                        f"<span>{lbl_vs_match}</span>{_format_delta_badge(delta_match)}"
                        f"</div>"
                    )
                else:
                    bench_row = (
                        f"<div style='display:flex; justify-content:space-between; align-items:center; color:#94a3b8; font-size:11.5px; margin-bottom:4px;'>"
                        f"<span>{lbl_vs_tipo}</span>{_format_delta_badge(delta_tipo)}"
                        f"</div>"
                        f"<div style='display:flex; justify-content:space-between; align-items:center; color:#94a3b8; font-size:11.5px;'>"
                        f"<span>{lbl_vs_match}</span>{_format_delta_badge(delta_match)}"
                        f"</div>"
                    )

                card_html = (
                    f"<div style='background:rgba(14,165,233,0.06); border:1px solid rgba(14,165,233,0.2); border-radius:10px; padding:10px 14px; margin-bottom:8px;'>"
                    f"<div style='display:flex; justify-content:space-between; align-items:center;'>"
                    f"<span style='font-size:11px; font-weight:800; color:#38bdf8; text-transform:uppercase;'>{titolo}</span>"
                    f"<span style='font-size:20px; font-weight:900; color:#ffffff;'>{val:,.0f} <span style='font-size:11px; color:#94a3b8; font-weight:600;'>{unita}</span></span>"
                    f"</div>"
                    f"<div style='margin-top:6px; padding-top:6px; border-top:1px solid rgba(255,255,255,0.06);'>"
                    f"{bench_row}"
                    f"</div>"
                    f"</div>"
                )
                st.markdown(card_html, unsafe_allow_html=True)

            # Mini Grafico Training Load Ultimi 7 Giorni (Plotly Mobile-Friendly)
            ultimi_7 = df_atleta.head(7).iloc[::-1]
            if len(ultimi_7) >= 1:
                tl_vals = pd.to_numeric(ultimi_7['Training Load'], errors='coerce').fillna(0).tolist()
                fig = go.Figure()
                fig.add_trace(go.Bar(
                    x=ultimi_7['Date'],
                    y=tl_vals,
                    text=[f"{int(v):,}" if v > 0 else "0" for v in tl_vals],
                    textposition='auto',
                    marker=dict(
                        color="#0ea5e9",
                        line=dict(color="#38bdf8", width=1)
                    )
                ))
                fig.update_layout(
                    height=220,
                    margin=dict(l=10, r=10, t=30, b=10),
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    title=dict(text=tr("Training Load Ultime 7 Sessioni (TL)", "Training Load Last 7 Sessions (TL)"), font=dict(size=12, color="#94a3b8")),
                    xaxis=dict(tickfont=dict(size=9, color="#94a3b8"), type='category'),
                    yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.06)", tickfont=dict(size=9, color="#94a3b8")),
                    showlegend=False
                )
                st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

    # =========================================================================
    # SEZIONE 3: I MIEI TEST (Test Fisici & Neuromuscolari Atleta Mobile)
    # =========================================================================
    elif tab_scelta == "test":
        _render_sezione_test_atleta(atleta_id, nome_atleta)

    # Link / Pulsante per passare alla vista Desktop
    st.markdown("<div style='margin-top:25px; text-align:center;'></div>", unsafe_allow_html=True)
    if st.button(tr("Passa alla Vista Desktop Completa", "Switch to Full Desktop View"), key="btn_switch_to_desktop", use_container_width=True):
        st.session_state['view_mode'] = 'desktop'
        st.query_params['device'] = 'desktop'
        st.rerun()


def _render_sezione_test_atleta(atleta_id, nome_atleta):
    """Visualizzazione mobile ad alto impatto dei Test Fisici e Neuromuscolari dell'atleta."""
    st.markdown(f"""
    <div style="background: rgba(14, 165, 233, 0.08); border-left: 4px solid #0ea5e9; border-radius: 8px; padding: 10px 14px; margin-bottom: 14px;">
        <div style="font-size: 11px; font-weight: 800; color: #38bdf8; text-transform: uppercase; letter-spacing: 0.5px;">{tr("I Miei Test & Valutazioni", "My Tests & Assessments")}</div>
        <div style="font-size: 13px; color: #cbd5e1; margin-top: 2px;">{tr("Monitoraggio longitudinale, personal best e asimmetrie registrate.", "Longitudinal monitoring, personal bests and recorded asymmetries.")}</div>
    </div>
    """, unsafe_allow_html=True)

    sessioni = get_sessioni_test(atleta_id=atleta_id)
    if not sessioni:
        st.info(tr("Nessun test fisico registrato al momento. I test effettuati con il tuo staff tecnico appariranno qui.", "No physical tests recorded yet. Testing done with your coaching staff will appear here."))
        return

    catalogo = get_catalogo_protocolli()
    cat_map = {p.get('id'): p for p in catalogo}

    # 1. Flagship: Ultimo M0V3 Tennis Test
    sess_m0v3 = [s for s in sessioni if cat_map.get(s.get('protocollo_id'), {}).get('codice_univoco') == 'm0v3_tennis_test']
    if sess_m0v3:
        sess_m0v3_latest = sorted(sess_m0v3, key=lambda x: str(x.get('data')), reverse=True)[0]
        vals = sess_m0v3_latest.get('valori', {})
        d_test = sess_m0v3_latest.get('data', 'N/D')

        grs = vals.get('game_readiness_score')
        tps = vals.get('tennis_profile_score')
        edi = vals.get('explosivity_decay_index')
        cmj_s = vals.get('cmj_internal_score')
        pci = vals.get('physiological_cost_index')

        def _fmt_score(val, suffix="", invert=False):
            if val is None or pd.isna(val): return "<span style='color:#64748b;'>-</span>"
            try:
                v = float(val)
                c = "#10b981" if (v >= 80 if not invert else v <= 10) else ("#f59e0b" if (v >= 65 if not invert else v <= 20) else "#ef4444")
                return f"<span style='color:{c}; font-weight:900;'>{v:.1f}{suffix}</span>"
            except Exception:
                return f"{val}{suffix}"

        st.markdown(f"""
        <div class="m-card" style="border: 1px solid rgba(56, 189, 248, 0.45); background: linear-gradient(165deg, rgba(14,165,233,0.12) 0%, rgba(8,15,30,0.95) 100%);">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                <div style="font-size:12px; font-weight:900; color:#38bdf8; text-transform:uppercase;"><i class='bi bi-activity' style='margin-right:5px;'></i>M0V3 Tennis Test</div>
                <div style="font-size:10.5px; color:#94a3b8; font-weight:700;">{d_test}</div>
            </div>
            <div style="font-size:11px; color:#cbd5e1; margin-bottom:12px;">{tr("Profilo combinato metabolico, neuromuscolare ed efficienza di campo.", "Combined metabolic, neuromuscular and on-court efficiency profile.")}</div>
            
            <div style="display:grid; grid-template-columns: repeat(2, 1fr); gap:8px;">
                <div style="background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.06); border-radius:8px; padding:8px 10px;">
                    <div style="font-size:9.5px; color:#94a3b8; font-weight:700; text-transform:uppercase;">Game Readiness (GRS)</div>
                    <div style="font-size:16px; margin-top:2px;">{_fmt_score(grs, "/100")}</div>
                </div>
                <div style="background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.06); border-radius:8px; padding:8px 10px;">
                    <div style="font-size:9.5px; color:#94a3b8; font-weight:700; text-transform:uppercase;">Tennis Profile (TPS)</div>
                    <div style="font-size:16px; margin-top:2px;">{_fmt_score(tps, "/100")}</div>
                </div>
                <div style="background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.06); border-radius:8px; padding:8px 10px;">
                    <div style="font-size:9.5px; color:#94a3b8; font-weight:700; text-transform:uppercase;">{tr("Decay Esplosivo %", "Explosive Decay %")}</div>
                    <div style="font-size:16px; margin-top:2px;">{_fmt_score(edi, "%", invert=True)}</div>
                </div>
                <div style="background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.06); border-radius:8px; padding:8px 10px;">
                    <div style="font-size:9.5px; color:#94a3b8; font-weight:700; text-transform:uppercase;">CMJ Internal Score</div>
                    <div style="font-size:16px; margin-top:2px;">{_fmt_score(cmj_s, "/100")}</div>
                </div>
            </div>
            {f"<div style='margin-top:8px; font-size:10px; color:#94a3b8; text-align:right;'>Physiological Cost Index (PCI): <b style='color:#f1f5f9;'>{float(pci):.2f}</b> b/m</div>" if pci is not None and not pd.isna(pci) else ""}
        </div>
        """, unsafe_allow_html=True)

    # 2. Personal Best & Ultimi Test Salienti (CMJ, Sprint, NordBord)
    pb_cards = []
    # CMJ
    cmj_vals = [s.get('valori', {}).get('jump_height') for s in sessioni if s.get('valori', {}).get('jump_height') is not None]
    if cmj_vals:
        max_cmj = max(float(v) for v in cmj_vals)
        latest_cmj = float(cmj_vals[0])
        pb_cards.append({
            "titolo": tr("Salto CMJ", "CMJ Jump"),
            "pb": f"{max_cmj:.1f} cm",
            "latest": f"{latest_cmj:.1f} cm",
            "icon": "<i class='bi bi-lightning-charge' style='color:#38bdf8;'></i>"
        })

    # Sprint 10m / 20m
    s10_vals = [s.get('valori', {}).get('split_10m') or s.get('valori', {}).get('sprint_10m') for s in sessioni if (s.get('valori', {}).get('split_10m') or s.get('valori', {}).get('sprint_10m'))]
    if s10_vals:
        best_s10 = min(float(v) for v in s10_vals)
        pb_cards.append({
            "titolo": "Sprint 10m",
            "pb": f"{best_s10:.2f} s",
            "latest": f"{float(s10_vals[0]):.2f} s",
            "icon": "<i class='bi bi-speedometer2' style='color:#10b981;'></i>"
        })

    if pb_cards:
        st.markdown(f"<div style='font-size:11px; font-weight:800; color:#94a3b8; text-transform:uppercase; margin-top:10px; margin-bottom:6px;'><i class='bi bi-trophy' style='margin-right:5px;'></i>{tr('Personal Best & Prestazioni Chiave', 'Personal Best & Key Metrics')}</div>", unsafe_allow_html=True)
        cols_pb = st.columns(min(len(pb_cards), 2))
        for card, col in zip(pb_cards[:2], cols_pb):
            with col:
                st.markdown(f"""
                <div class="m-card" style="padding:10px 12px; margin-bottom:8px;">
                    <div style="font-size:10px; color:#94a3b8; font-weight:700;">{card['icon']} {card['titolo']}</div>
                    <div style="font-size:18px; font-weight:900; color:#38bdf8; margin-top:2px;">{card['pb']} <span style="font-size:9px; color:#10b981; font-weight:800;">PB</span></div>
                    <div style="font-size:10px; color:#64748b; margin-top:2px;">{tr('Ultimo:', 'Latest:')} <b style="color:#cbd5e1;">{card['latest']}</b></div>
                </div>
                """, unsafe_allow_html=True)

    # 3. Asimmetrie Rilevate (Alert > 15%)
    asym_items = []
    for s in sessioni[:10]:
        valori = s.get('valori', {})
        for k, v in valori.items():
            if k.endswith('_asym_pct') and v is not None and not pd.isna(v):
                try:
                    pct = float(v)
                    base_k = k.replace('_asym_pct', '')
                    dir_val = valori.get(f"{base_k}_asym_dir", "")
                    p_info = cat_map.get(s.get('protocollo_id'), {})
                    p_name = p_info.get('nome_protocollo', 'Test')
                    asym_items.append({
                        "test": p_name,
                        "metrica": base_k.replace('_', ' ').capitalize(),
                        "pct": pct,
                        "dir": dir_val,
                        "data": s.get('data')
                    })
                except Exception:
                    pass

    if asym_items:
        st.markdown(f"<div style='font-size:11px; font-weight:800; color:#94a3b8; text-transform:uppercase; margin-top:10px; margin-bottom:6px;'><i class='bi bi-arrow-left-right' style='margin-right:5px;'></i>{tr('Asimmetrie Recenti (Dx / Sx)', 'Recent Asymmetries (R / L)')}</div>", unsafe_allow_html=True)
        for a in asym_items[:3]:
            is_alert = a['pct'] > 15.0
            border_c = "#ef4444" if is_alert else "#10b981"
            bg_badge = "rgba(239,68,68,0.2)" if is_alert else "rgba(16,185,129,0.2)"
            text_badge = "#f87171" if is_alert else "#34d399"
            label_alert = tr("ATTENZIONE (>15%)", "CAUTION (>15%)") if is_alert else tr("Simmetria Ottimale", "Optimal Symmetry")

            st.markdown(f"""
            <div style="background:rgba(13,24,44,0.7); border:1px solid {border_c}; border-radius:10px; padding:10px 12px; margin-bottom:8px;">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <div style="font-size:11px; font-weight:800; color:#f1f5f9;">{a['test']} - {a['metrica']}</div>
                    <span style="background:{bg_badge}; color:{text_badge}; font-size:9.5px; font-weight:800; padding:2px 6px; border-radius:4px;">{label_alert}</span>
                </div>
                <div style="display:flex; justify-content:space-between; align-items:center; margin-top:4px;">
                    <span style="font-size:14px; font-weight:900; color:#ffffff;">{a['pct']:.1f}% {f'({a["dir"]})' if a['dir'] else ''}</span>
                    <span style="font-size:10px; color:#64748b;">{tr('Rilevazione:', 'Recorded:')} {a['data']}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

    # 4. Storico Sessioni
    st.markdown(f"<div style='font-size:11px; font-weight:800; color:#94a3b8; text-transform:uppercase; margin-top:12px; margin-bottom:6px;'><i class='bi bi-card-checklist' style='margin-right:5px;'></i>{tr('Storico Tutte le Valutazioni', 'All Assessments History')}</div>", unsafe_allow_html=True)
    sess_ordinate = sorted(sessioni, key=lambda x: str(x.get('data')), reverse=True)
    for s in sess_ordinate[:10]:
        p_info = cat_map.get(s.get('protocollo_id'), {})
        p_nome = p_info.get('nome_protocollo', 'Protocollo Test')
        data_s = s.get('data', '')
        vals = s.get('valori', {})

        with st.expander(f"{data_s} - {p_nome}"):
            st.markdown(f"<div style='font-size:10.5px; color:#94a3b8; margin-bottom:6px;'>{tr('Strumento:', 'Instrument:')} <b style='color:#38bdf8;'>{s.get('strumentazione') or 'Standard'}</b> | {tr('Ambiente:', 'Environment:')} <b style='color:#cbd5e1;'>{s.get('condizione_ambiente') or 'N/D'}</b></div>", unsafe_allow_html=True)
            for k, v in vals.items():
                if not k.endswith('_mean') and not k.endswith('_max') and not k.endswith('_dir'):
                    st.markdown(f"<div style='display:flex; justify-content:space-between; font-size:11.5px; border-bottom:1px solid rgba(255,255,255,0.05); padding:3px 0;'><span style='color:#94a3b8;'>{k.replace('_', ' ').capitalize()}</span><span style='color:#ffffff; font-weight:700;'>{v}</span></div>", unsafe_allow_html=True)
            if s.get('note'):
                st.markdown(f"<div style='font-size:10.5px; color:#64748b; margin-top:6px; font-style:italic;'>{tr('Note Coach:', 'Coach Notes:')} {s.get('note')}</div>", unsafe_allow_html=True)
