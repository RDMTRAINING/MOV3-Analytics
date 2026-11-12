import datetime
from datetime import timedelta
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from config import (
    LOGO_PATH,
    CATALOGO_REPORT,
    COLONNE_STANDARD,
    METRICHE_VOLUME,
    METRICHE_INTENSITA,
    LEGENDA_ACWR,
    tr,
    render_page_header,
    render_print_header,
)
from utils import (
    supabase,
    supabase_admin,
    get_tipologie_sessione,
    get_tipologia_badge_style,
    converti_durata_in_minuti,
    load_local_database,
    save_local_database,
    get_val,
    calcola_delta_percentuale,
    formatta_delta,
    get_color,
    get_bar_label,
    get_color_bt,
    get_bar_label_bt,
    riepilogo_match,
    acwr_pre_match,
    calcola_blocchi_baseline,
    stato_acwr,
    etichetta_scostamento,
    frase_riepilogo,
    card_kpi,
    delta_puro,
    delta_confronto,
    get_atleti_associati,
    get_tutti_gli_atleti,
    get_lista_atleti_disponibili,
    get_registro_medico,
    slugify_name,
)
from pdf_generator import (
    crea_pdf_m0v3,
    crea_pdf_sessione_m0v3,
    crea_pdf_weekly_m0v3,
    crea_pdf_storico_m0v3,
    crea_pdf_medie_m0v3,
)
from utils_livetennis import fetch_cobolli_live_stats
from views.calendario_medico import render_master_timeline

def _acwr_zone_style(pct_val, has_baseline=True):
    if not has_baseline or pd.isna(pct_val) or pct_val <= 0:
        return "#f1f5f9", "#64748b", "#94a3b8", "NO BASELINE"
    if pct_val < 80:
        return "#e0f2fe", "#0284c7", "#0ea5e9", "LOW (<80%)"
    if pct_val <= 125:
        return "#dcfce7", "#166534", "#10b981", "OPTIMAL (80-125%)"
    if pct_val <= 150:
        return "#fef3c7", "#b45309", "#f59e0b", "HIGH (125-150%)"
    return "#fee2e2", "#991b1b", "#ef4444", "OVERLOAD (>150%)"

def _render_mini_acwr_bar(pct_val, bar_col, has_baseline=True):
    fill_w = min(100.0, max(0.0, (float(pct_val) / 160.0) * 100.0)) if has_baseline and pct_val > 0 else 0.0
    return (
        "<div style='width:100%; height:8px; background:#f1f5f9; border:1px solid #e2e8f0; border-radius:4px; position:relative; overflow:hidden; margin-top:4px;'>"
        f"<div style='position:absolute; left:0; top:0; bottom:0; width:{fill_w:.1f}%; background:{bar_col}; border-radius:3px;'></div>"
        "<div style='position:absolute; left:62.5%; top:0; bottom:0; width:2px; background:#0f172a; z-index:2;' title='100% Baseline'></div>"
        "</div>"
    )

def _calcola_stato_clinico_atleta(ath_name, df_ath):
    """
    Determina lo stato clinico e operativo dell'atleta e i dettagli dell'evento attivo/recente.
    """
    today_real = datetime.date.today()
    
    all_db_recs = get_registro_medico() or []
    db_recs = [r for r in all_db_recs if ath_name.lower() in str(r.get('nome_giocatore', '')).lower()]
    mock_recs = st.session_state.get('mock_registro_medico', [])
    mock_ath = [r for r in mock_recs if ath_name.lower() in str(r.get('nome_giocatore', '')).lower()]
    all_recs = db_recs + mock_ath

    if not all_recs:
        return {
            "status": "DISPONIBILE",
            "color": "#10b981",
            "badge": tr("DISPONIBILE", "AVAILABLE"),
            "tag": "Full Training",
            "sub": tr("Nessuna limitazione medica attiva · Piena idoneità", "No active medical limitation · Fully fit"),
            "dettaglio": None
        }

    all_recs.sort(key=lambda x: str(x.get('data_inizio', '')), reverse=True)
    
    last_sess_d = df_ath['Date_obj'].max().date() if (df_ath is not None and not df_ath.empty and 'Date_obj' in df_ath.columns and pd.notna(df_ath['Date_obj'].max())) else today_real
    ref_dates = [today_real]
    if last_sess_d and last_sess_d != today_real:
        ref_dates.append(last_sess_d)

    active_events = []
    for r in all_recs:
        try:
            d_st = datetime.datetime.strptime(str(r.get('data_inizio'))[:10], "%Y-%m-%d").date()
            d_end = datetime.datetime.strptime(str(r.get('data_fine', r.get('data_inizio')))[:10], "%Y-%m-%d").date()
            for r_d in ref_dates:
                if d_st <= r_d <= d_end:
                    active_events.append(r)
                    break
        except Exception:
            pass

    priority = {
        'INDISPONIBILE': 4,
        'STOP': 4,
        'LIMITATO': 3,
        'RIPOSO_VIAGGIO': 2,
        'VIAGGIO': 2,
        'DISPONIBILE': 1
    }

    target_event = None
    if active_events:
        target_event = max(active_events, key=lambda x: priority.get(x.get('status_operativo', 'DISPONIBILE'), 1))
    else:
        eventi_non_tratt = [r for r in all_recs if r.get('tipo_scheda') != 'TRATTAMENTO']
        if eventi_non_tratt:
            target_event = eventi_non_tratt[0]
            try:
                d_end_ev = datetime.datetime.strptime(str(target_event.get('data_fine', target_event.get('data_inizio')))[:10], "%Y-%m-%d").date()
                if d_end_ev < min(ref_dates):
                    d_end_str = d_end_ev.strftime("%d/%m/%Y")
                    ev_lbl = target_event.get('sottotipo_evento', '')
                    lbl_ret = tr("Rientrato da limitazione il", "Returned to full load on")
                    return {
                        "status": "DISPONIBILE",
                        "color": "#10b981",
                        "badge": tr("DISPONIBILE", "AVAILABLE"),
                        "tag": "Full Training",
                        "sub": f"{lbl_ret} {d_end_str} ({ev_lbl})",
                        "dettaglio": target_event
                    }
            except Exception:
                pass

    if not target_event:
        return {
            "status": "DISPONIBILE",
            "color": "#10b981",
            "badge": tr("DISPONIBILE", "AVAILABLE"),
            "tag": "Full Training",
            "sub": tr("Nessuna limitazione medica attiva · Piena idoneità", "No active medical limitation · Fully fit"),
            "dettaglio": None
        }

    st_op = str(target_event.get('status_operativo', 'DISPONIBILE')).upper()
    sub_ev = target_event.get('sottotipo_evento', '')
    distr = target_event.get('distretto_anatomico', 'Sistemico')
    lato = target_event.get('lato', '')
    lato_str = f" ({lato})" if lato and lato not in ('N/A', 'Nessuno', '') else ""
    vas = target_event.get('scala_dolore_vas')
    vas_str = f" · VAS {vas}/10" if vas is not None else ""
    dt_fine = str(target_event.get('data_fine', ''))[:10]
    try:
        dt_fine_obj = datetime.datetime.strptime(dt_fine, "%Y-%m-%d").date()
        dt_fine_str = dt_fine_obj.strftime("%d/%m/%Y")
    except Exception:
        dt_fine_str = dt_fine

    if st_op in ('INDISPONIBILE', 'STOP'):
        lbl_rientro = tr("Rientro stimato", "Est. return")
        return {
            "status": "STOP",
            "color": "#e11d48",
            "badge": tr("STOP MEDICO", "MEDICAL STOP"),
            "tag": tr("Indisponibile", "Unavailable"),
            "sub": f"<b>{sub_ev}</b> · {distr}{lato_str}{vas_str} · {lbl_rientro}: {dt_fine_str}",
            "dettaglio": target_event
        }
    elif st_op == 'LIMITATO':
        lbl_rientro = tr("Rientro stimato", "Est. return")
        sub_desc = f"<b>{sub_ev}</b> · {distr}{lato_str}{vas_str} · {lbl_rientro}: {dt_fine_str}"
        
        # Alert Violazione Limite 70% Training Load in Carico Adattato
        if df_ath is not None and not df_ath.empty and 'Training Load' in df_ath.columns:
            tl_series = pd.to_numeric(df_ath['Training Load'], errors='coerce').dropna()
            tl_pos = tl_series[tl_series > 0]
            if len(tl_pos) > 1:
                tl_media = float(tl_pos.mean())
                soglia_70 = tl_media * 0.70
                last_tl = float(tl_series.iloc[-1])
                if last_tl > soglia_70:
                    pct_over = (last_tl / tl_media) * 100.0
                    sub_desc += f"<br><span style='background:rgba(225,29,72,0.12); color:#be123c; border:1px solid rgba(225,29,72,0.4); padding:2px 7px; border-radius:4px; font-weight:800; font-size:10.5px; display:inline-block; margin-top:4px;'><i class='bi bi-exclamation-octagon-fill' style='margin-right:3px;'></i>OVERLOAD >70% MEDIA ({last_tl:.0f} AU · {pct_over:.0f}%)</span>"

        return {
            "status": "LIMITATO",
            "color": "#f59e0b",
            "badge": tr("CARICO ADATTATO", "ADAPTED LOAD"),
            "tag": tr("Modificato / RTP", "Modified / RTP"),
            "sub": sub_desc,
            "dettaglio": target_event
        }
    elif st_op in ('RIPOSO_VIAGGIO', 'VIAGGIO'):
        lbl_fino = tr("Fino al", "Until")
        return {
            "status": "VIAGGIO",
            "color": "#0284c7",
            "badge": tr("VIAGGIO / RIPOSO", "TRAVEL / REST"),
            "tag": "Off",
            "sub": f"<b>{sub_ev}</b> · {lbl_fino} {dt_fine_str}",
            "dettaglio": target_event
        }
    else:
        return {
            "status": "DISPONIBILE",
            "color": "#10b981",
            "badge": tr("DISPONIBILE", "AVAILABLE"),
            "tag": "Full Training",
            "sub": tr("Nessuna limitazione medica attiva · Piena idoneità", "No active medical limitation · Fully fit"),
            "dettaglio": target_event
        }

def _calcola_ultimo_trattamento_atleta(ath_name):
    """
    Recupera l'ultimo trattamento fisioterapico eseguito per l'atleta.
    """
    all_db_recs = get_registro_medico() or []
    db_recs = [r for r in all_db_recs if ath_name.lower() in str(r.get('nome_giocatore', '')).lower()]
    mock_recs = st.session_state.get('mock_registro_medico', [])
    mock_ath = [r for r in mock_recs if ath_name.lower() in str(r.get('nome_giocatore', '')).lower()]
    all_recs = db_recs + mock_ath

    trattamenti = [
        r for r in all_recs
        if r.get('tipo_scheda') == 'TRATTAMENTO' or 'tecar' in str(r.get('sottotipo_evento', '')).lower()
        or 'fisioterap' in str(r.get('sottotipo_evento', '')).lower() or 'osteopat' in str(r.get('sottotipo_evento', '')).lower()
        or 'laser' in str(r.get('sottotipo_evento', '')).lower() or 'manuale' in str(r.get('sottotipo_evento', '')).lower()
    ]
    if not trattamenti:
        return {
            "has_trattamento": False,
            "color": "#94a3b8",
            "titolo": tr("Nessun Trattamento", "No Treatments"),
            "sub": tr("Nessuna seduta fisioterapica registrata nello storico", "No physiotherapy sessions recorded in history")
        }

    trattamenti.sort(key=lambda x: str(x.get('data_inizio', '')), reverse=True)
    t_last = trattamenti[0]
    dt_str = str(t_last.get('data_inizio', ''))[:10]
    
    today_real = datetime.date.today()
    try:
        dt_obj = datetime.datetime.strptime(dt_str, "%Y-%m-%d").date()
        diff_d = (today_real - dt_obj).days
        dt_formatted = dt_obj.strftime("%d/%m/%Y")
        if diff_d == 0: d_ago = tr("Oggi", "Today")
        elif diff_d == 1: d_ago = tr("Ieri", "Yesterday")
        elif diff_d > 1: d_ago = f"{diff_d} {tr('gg fa', 'd ago')}"
        else: d_ago = dt_formatted
    except Exception:
        dt_formatted = dt_str
        d_ago = dt_str

    t_nome = t_last.get('sottotipo_evento', tr('Trattamento Fisioterapico', 'Physiotherapy Treatment'))
    distr = t_last.get('distretto_anatomico', 'Sistemico')
    lato = t_last.get('lato', '')
    lato_str = f" ({lato})" if lato and lato not in ('N/A', 'Nessuno', '') else ""
    vas = t_last.get('scala_dolore_vas')
    vas_str = f" · VAS {vas}/10" if vas is not None else ""
    
    return {
        "has_trattamento": True,
        "color": "#10b981",
        "titolo": t_nome,
        "sub": f"<b>{dt_formatted}</b> ({d_ago}) · {distr}{lato_str}{vas_str}"
    }

def render_home(t):
    render_page_header(
        "Executive Locker Room",
        tr("Monitoraggio in tempo reale del roster, stato di forma (ACWR) e ultime acquisizioni.", "Real-time roster monitoring, readiness status (ACWR), and latest uploads."),
        "EXECUTIVE LOCKER ROOM"
    )

    df_storico = load_local_database()
    atleti_visibili = get_lista_atleti_disponibili(st.session_state.get('user'), st.session_state.get('role'))
    if not df_storico.empty and atleti_visibili and st.session_state.get('role') != 'Super-Admin':
        df_storico = df_storico[df_storico['Players'].isin(atleti_visibili)]

    ath_home_sel = st.session_state.get('selected_athlete')
    if not ath_home_sel or (atleti_visibili and ath_home_sel not in atleti_visibili):
        ath_home_sel = atleti_visibili[0] if atleti_visibili else "Flavio Cobolli"

    if not df_storico.empty and 'Date' in df_storico.columns:
        df_storico['Date_obj'] = pd.to_datetime(df_storico['Date'], format='%d/%m/%Y', errors='coerce')

    # =========================================================================
    # SEZIONE FOCUS GIOCATORE: HERO CARD, CLINICA & IDONEITÀ (STILE MOV3)
    # COLLOCATA ALL'INIZIO DELLA PAGINA SUBITO SOTTO EXECUTIVE LOCKER ROOM
    # =========================================================================
    if ath_home_sel:
        # Header Bar Focus Atleta
        c_hdr_tit, c_hdr_sel = st.columns([1.6, 1.4])
        with c_hdr_tit:
            lbl_tit_focus = tr("FOCUS ATLETA & MONITORAGGIO INDIVIDUALE", "ATHLETE FOCUS & INDIVIDUAL MONITORING")
            lbl_sub_focus = tr("Scheda completa, stato clinico e carichi rolling dell'atleta attivo selezionato nel menu laterale.", "Complete profile, clinical status, and rolling loads for the active athlete selected in the sidebar.")
            st.markdown(
                f"<div style='display:flex; align-items:center; gap:12px; padding:4px 0;'>"
                f"<div style='background:linear-gradient(135deg, #0f172a 0%, #1e293b 100%); border:1.5px solid #0ea5e9; width:44px; height:44px; border-radius:10px; display:flex; align-items:center; justify-content:center; flex-shrink:0; box-shadow:0 3px 10px rgba(14,165,233,0.2);'>"
                f"<i class='bi bi-person-bounding-box' style='color:#38bdf8; font-size:22px;'></i>"
                f"</div>"
                f"<div>"
                f"<div style='font-size:14.5px; font-weight:900; color:#0f172a; text-transform:uppercase; letter-spacing:0.6px;'>{lbl_tit_focus}</div>"
                f"<div style='font-size:12px; color:#64748b; margin-top:2px;'>{lbl_sub_focus}</div>"
                f"</div>"
                f"</div>",
                unsafe_allow_html=True
            )

        with c_hdr_sel:
            lbl_act_ath = tr("Atleta Attivo", "Active Athlete")
            st.markdown(
                f"<div style='display:flex; justify-content:flex-end; align-items:center; height:100%; padding-top:6px;'>"
                f"<div style='background:rgba(14,165,233,0.08); border:1.5px solid #0ea5e9; border-radius:10px; padding:6px 14px; display:inline-flex; align-items:center; gap:8px;'>"
                f"<i class='bi bi-person-fill' style='color:#0284c7; font-size:16px;'></i>"
                f"<div style='text-align:right;'>"
                f"<div style='font-size:10px; font-weight:800; color:#64748b; text-transform:uppercase; letter-spacing:0.5px;'>{lbl_act_ath}</div>"
                f"<div style='font-size:14.5px; font-weight:900; color:#0f172a;'>{ath_home_sel}</div>"
                f"</div>"
                f"</div>"
                f"</div>",
                unsafe_allow_html=True
            )

        # Calcolo Iniziali Atleta per Avatar Monogramma
        parts = [p for p in str(ath_home_sel).strip().split() if p]
        if len(parts) >= 2:
            ath_initials = f"{parts[0][0]}{parts[1][0]}".upper()
        elif len(parts) == 1 and len(parts[0]) > 0:
            ath_initials = parts[0][:2].upper()
        else:
            ath_initials = "AT"

        # Recupero Dati e Statistiche dell'Atleta
        df_ath_sel = df_storico[df_storico['Players'] == ath_home_sel] if not df_storico.empty else pd.DataFrame()
        info_st = _calcola_stato_clinico_atleta(ath_home_sel, df_ath_sel)
        info_fis = _calcola_ultimo_trattamento_atleta(ath_home_sel)

        num_sessioni_tot = len(df_ath_sel)
        data_ultima_sess = "-"
        diff_gg_sess = "-"
        nome_ultima_sess = "-"
        if not df_ath_sel.empty and 'Date_obj' in df_ath_sel.columns:
            df_ath_sorted = df_ath_sel.dropna(subset=['Date_obj']).sort_values('Date_obj', ascending=False)
            if not df_ath_sorted.empty:
                r_last = df_ath_sorted.iloc[0]
                dt_last = r_last['Date_obj']
                data_ultima_sess = dt_last.strftime("%d/%m/%Y")
                diff_days = (datetime.date.today() - dt_last.date()).days
                if diff_days == 0:
                    diff_gg_sess = tr("Oggi", "Today")
                elif diff_days == 1:
                    diff_gg_sess = tr("Ieri", "Yesterday")
                elif diff_days > 1:
                    diff_gg_sess = f"{diff_days} {tr('gg fa', 'd ago')}"
                else:
                    diff_gg_sess = data_ultima_sess
                tit_s = str(r_last.get('Session_Title', ''))
                typ_s = str(r_last.get('Activity Type', ''))
                nome_ultima_sess = tit_s if tit_s else (typ_s if typ_s else tr("Sessione Registrata", "Recorded Session"))

        lbl_atleta_attivo = tr("M0V3 ATLETA ATTIVO", "M0V3 ACTIVE ATHLETE")
        lbl_ult_sess = tr("Ultima Sessione:", "Latest Session:")
        lbl_sess_nel_db = tr("sessioni nel database", "sessions in database")
        lbl_stat_clin = tr("STATO CLINICO & IDONEITÀ OPERATIVA", "CLINICAL STATUS & OPERATIONAL READINESS")
        lbl_ult_fis = tr("ULTIMO TRATTAMENTO FISIOTERAPICO", "LATEST PHYSIOTHERAPY SESSION")
        lbl_area_fis = tr("Area Fisioterapica", "Physiotherapy Area")

        color_st = info_st['color']
        icon_st = info_st.get('icon', 'bi-shield-check')
        badge_st = info_st['badge']
        tag_st = info_st['tag']
        sub_st = info_st['sub']

        color_fis = info_fis['color']
        titolo_fis = info_fis['titolo']
        sub_fis = info_fis['sub']

        # GRANDE HERO CARD ATLETA (Alta Evidenza Visiva & Dettaglio Immediato)
        hero_card_html = (
            f"<div style='background:white; border:1px solid #e2e8f0; border-left:6px solid #0ea5e9; border-radius:14px; "
            f"padding:22px 24px; box-shadow:0 4px 16px -2px rgba(15,23,42,0.06); margin-top:14px; margin-bottom:20px; font-family:\"Inter\", -apple-system, sans-serif;'>"
            f"<div style='display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:16px; border-bottom:1px solid #f1f5f9; padding-bottom:18px;'>"
            f"<div style='display:flex; align-items:center; gap:18px;'>"
            f"<div style='width:62px; height:62px; border-radius:14px; background:linear-gradient(135deg, #0f172a 0%, #1e293b 100%); "
            f"border:2.5px solid #0ea5e9; display:flex; align-items:center; justify-content:center; color:#38bdf8; font-size:24px; "
            f"font-weight:900; box-shadow:0 4px 14px rgba(14,165,233,0.30); flex-shrink:0; letter-spacing:0.5px;'>{ath_initials}</div>"
            f"<div>"
            f"<div style='display:flex; align-items:center; gap:10px; flex-wrap:wrap;'>"
            f"<span style='font-size:28px; font-weight:900; color:#0f172a; letter-spacing:-0.6px; line-height:1.15; text-transform:uppercase;'>{ath_home_sel}</span>"
            f"<span style='background:rgba(14,165,233,0.12); color:#0284c7; font-size:11px; font-weight:800; padding:4px 10px; border-radius:6px; border:1px solid rgba(14,165,233,0.3); text-transform:uppercase;'>"
            f"<i class='bi bi-person-badge-fill' style='margin-right:4px;'></i>{lbl_atleta_attivo}</span>"
            f"</div>"
            f"<div style='color:#64748b; font-size:12.5px; margin-top:5px; display:flex; align-items:center; gap:8px; flex-wrap:wrap;'>"
            f"<span><i class='bi bi-calendar3' style='color:#0ea5e9; margin-right:4px;'></i>{lbl_ult_sess} <b>{data_ultima_sess}</b> ({diff_gg_sess} · {nome_ultima_sess})</span>"
            f"<span style='color:#cbd5e1;'>&bull;</span>"
            f"<span><i class='bi bi-database' style='color:#0ea5e9; margin-right:4px;'></i><b>{num_sessioni_tot}</b> {lbl_sess_nel_db}</span>"
            f"</div>"
            f"</div>"
            f"</div>"
            f"<div>"
            f"<div style='background:{color_st}15; color:{color_st}; border:2px solid {color_st}60; font-size:14.5px; font-weight:900; padding:8px 18px; border-radius:10px; display:flex; align-items:center; gap:8px; box-shadow:0 2px 8px {color_st}20;'>"
            f"<i class='bi {icon_st}' style='font-size:18px;'></i>"
            f"<span>{badge_st} &middot; {tag_st}</span>"
            f"</div>"
            f"</div>"
            f"</div>"
            f"<div style='display:grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap:16px; margin-top:16px;'>"
            f"<div style='background:#f8fafc; border:1px solid #e2e8f0; border-radius:10px; padding:15px 18px; border-left:4px solid {color_st};'>"
            f"<div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;'>"
            f"<span style='font-size:11px; font-weight:800; color:#64748b; text-transform:uppercase; letter-spacing:0.5px;'>"
            f"<i class='bi bi-heart-pulse-fill' style='color:#0ea5e9; margin-right:5px;'></i>{lbl_stat_clin}</span>"
            f"<span style='font-size:11px; font-weight:800; color:{color_st}; background:{color_st}18; padding:2px 8px; border-radius:6px;'>{tag_st}</span>"
            f"</div>"
            f"<div style='font-size:19px; font-weight:900; color:{color_st}; display:flex; align-items:center; gap:8px;'>"
            f"<i class='bi {icon_st}'></i>{badge_st}</div>"
            f"<div style='font-size:12px; color:#475569; margin-top:5px; line-height:1.4;'>{sub_st}</div>"
            f"</div>"
            f"<div style='background:#f8fafc; border:1px solid #e2e8f0; border-radius:10px; padding:15px 18px; border-left:4px solid {color_fis};'>"
            f"<div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;'>"
            f"<span style='font-size:11px; font-weight:800; color:#64748b; text-transform:uppercase; letter-spacing:0.5px;'>"
            f"<i class='bi bi-bandaid-fill' style='color:#0ea5e9; margin-right:5px;'></i>{lbl_ult_fis}</span>"
            f"<span style='font-size:11px; font-weight:800; color:{color_fis}; background:{color_fis}18; padding:2px 8px; border-radius:6px;'>{lbl_area_fis}</span>"
            f"</div>"
            f"<div style='font-size:19px; font-weight:900; color:#0f172a; display:flex; align-items:center; gap:8px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;'>"
            f"<i class='bi bi-bandaid-fill' style='color:{color_fis}; font-size:17px;'></i>"
            f"<span style='overflow:hidden; text-overflow:ellipsis;'>{titolo_fis}</span>"
            f"</div>"
            f"<div style='font-size:12px; color:#475569; margin-top:5px; line-height:1.4;'>{sub_fis}</div>"
            f"</div>"
            f"</div>"
            f"</div>"
        )
        st.markdown(hero_card_html, unsafe_allow_html=True)

    # =========================================================================
    # LIVE TENNIS API STATS: FLAVIO COBOLLI
    # =========================================================================
    if 'cobolli' in str(ath_home_sel).lower() or any('cobolli' in str(a).lower() for a in atleti_visibili):
        live_st = fetch_cobolli_live_stats()
        atp_rank = live_st.get("ranking", 6)
        atp_pts = live_st.get("ranking_points", 3690)
        tb_pct = live_st.get("tiebreak_pct", 80.0)
        tb_rec = live_st.get("tiebreak_record", "120W - 30L")
        ds_pct = live_st.get("deciding_set_pct", 61.9)
        ds_rec = live_st.get("deciding_set_record", "91W - 56L")
        vl_pct = live_st.get("vs_lefty_pct", 60.3)
        last_sync_h = live_st.get("last_sync", "22:00")
        sync_dt = live_st.get("sync_date", "Oggi")

        st.markdown(
            f"<div style='background:white; border:1px solid #e2e8f0; border-radius:12px; padding:16px 18px; margin-top:4px; margin-bottom:18px; box-shadow:0 2px 8px -2px rgba(15,23,42,0.06); font-family:\"Inter\", sans-serif;'>"
            f"<div style='display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; border-bottom:1px solid #f1f5f9; padding-bottom:10px; margin-bottom:14px;'>"
            f"<div style='display:flex; align-items:center; gap:8px;'>"
            f"<div style='background:linear-gradient(135deg, #0f172a 0%, #1e293b 100%); border:1.5px solid #0ea5e9; width:34px; height:34px; border-radius:8px; display:flex; align-items:center; justify-content:center; flex-shrink:0;'>"
            f"<i class='bi bi-broadcast' style='color:#38bdf8; font-size:16px;'></i>"
            f"</div>"
            f"<div>"
            f"<span style='font-size:13.5px; font-weight:900; color:#0f172a; text-transform:uppercase; letter-spacing:0.6px;'>"
            f"{tr('STATISTICHE ATP TOUR (LIVE API)', 'ATP TOUR STATS (LIVE API)')} — <span style='color:#0ea5e9;'>FLAVIO COBOLLI</span></span>"
            f"</div>"
            f"</div>"
            f"<div style='display:flex; align-items:center; gap:8px;'>"
            f"<span style='background:rgba(16,185,129,0.12); color:#059669; font-size:10.5px; font-weight:800; padding:3px 9px; border-radius:6px;'>"
            f"<i class='bi bi-check-circle-fill' style='margin-right:4px;'></i>LIVE SYNC · 1 check/giorno ({sync_dt} {last_sync_h})</span>"
            f"</div>"
            f"</div>"
            f"<div style='display:grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap:12px;'>"
            f"<div style='background:#f8fafc; border:1px solid #e2e8f0; border-left:4px solid #0ea5e9; border-radius:8px; padding:10px 14px;'>"
            f"<div style='font-size:10px; font-weight:800; color:#64748b; text-transform:uppercase;'>RANKING ATP LIVE</div>"
            f"<div style='font-size:22px; font-weight:900; color:#0284c7; margin-top:2px;'>#{atp_rank} <span style='font-size:12px; font-weight:700; color:#475569;'>({atp_pts:,} pts)</span></div>"
            f"<div style='font-size:11px; color:#64748b; margin-top:3px;'>Posizione ufficiale ATP</div>"
            f"</div>"
            f"<div style='background:#f8fafc; border:1px solid #e2e8f0; border-left:4px solid #10b981; border-radius:8px; padding:10px 14px;'>"
            f"<div style='font-size:10px; font-weight:800; color:#64748b; text-transform:uppercase;'>CLUTCH: TIEBREAK</div>"
            f"<div style='font-size:22px; font-weight:900; color:#059669; margin-top:2px;'>{tb_pct:.1f}% <span style='font-size:11.5px; font-weight:700; color:#64748b;'>({tb_rec})</span></div>"
            f"<div style='font-size:11px; color:#64748b; margin-top:3px;'>Freddezza momenti decisivi</div>"
            f"</div>"
            f"<div style='background:#f8fafc; border:1px solid #e2e8f0; border-left:4px solid #f59e0b; border-radius:8px; padding:10px 14px;'>"
            f"<div style='font-size:10px; font-weight:800; color:#64748b; text-transform:uppercase;'>SET DECISIVI (3°/5° SET)</div>"
            f"<div style='font-size:22px; font-weight:900; color:#d97706; margin-top:2px;'>{ds_pct:.1f}% <span style='font-size:11.5px; font-weight:700; color:#64748b;'>({ds_rec})</span></div>"
            f"<div style='font-size:11px; color:#64748b; margin-top:3px;'>Resilienza lunga distanza</div>"
            f"</div>"
            f"<div style='background:#f8fafc; border:1px solid #e2e8f0; border-left:4px solid #8b5cf6; border-radius:8px; padding:10px 14px;'>"
            f"<div style='font-size:10px; font-weight:800; color:#64748b; text-transform:uppercase;'>VS MANCINI</div>"
            f"<div style='font-size:22px; font-weight:900; color:#7c3aed; margin-top:2px;'>{vl_pct:.1f}%</div>"
            f"<div style='font-size:11px; color:#64748b; margin-top:3px;'>Win rate avversari mancini</div>"
            f"</div>"
            f"</div>"
            f"</div>",
            unsafe_allow_html=True
        )

    df_storico = load_local_database()
    atleti_visibili = get_lista_atleti_disponibili(st.session_state.get('user'), st.session_state.get('role'))
    if not df_storico.empty and atleti_visibili and st.session_state.get('role') != 'Super-Admin':
        df_storico = df_storico[df_storico['Players'].isin(atleti_visibili)]

    tot_atleti = len(atleti_visibili)
    tot_sessioni = len(df_storico) if not df_storico.empty else 0
    n_sim = int(df_storico['Dato_Simulato'].sum()) if (not df_storico.empty and 'Dato_Simulato' in df_storico.columns) else 0
    n_reali = tot_sessioni - n_sim
    tot_match = len(df_storico[df_storico['Tipologia Sessione'].astype(str).str.strip().str.lower().isin(['match', 'match doppio'])]) if not df_storico.empty else 0

    ultima_data_str = "N/D"
    ultimo_dettaglio = tr("Data acquisizione più recente", "Most recent acquisition date")
    n_optimal = 0

    if not df_storico.empty and 'Date' in df_storico.columns:
        df_storico['Date_obj'] = pd.to_datetime(df_storico['Date'], format='%d/%m/%Y', errors='coerce')
        max_dt = df_storico['Date_obj'].max()
        if pd.notna(max_dt):
            ultima_data_str = max_dt.strftime('%d/%m/%Y')
            df_last = df_storico[df_storico['Date_obj'] == max_dt]
            if not df_last.empty:
                last_r = df_last.iloc[-1]
                ultimo_dettaglio = f"{last_r.get('Players', '')} · {last_r.get('Tipologia Sessione', '')}"

        for ath in atleti_visibili:
            df_a = df_storico[df_storico['Players'] == ath].dropna(subset=['Date_obj']).sort_values('Date_obj')
            if not df_a.empty:
                last_dt_a = df_a['Date_obj'].max()
                w_start = last_dt_a - timedelta(days=1)
                b_end = w_start - timedelta(days=1)
                b_start = b_end - timedelta(days=27)
                tl_acute = float(pd.to_numeric(df_a[(df_a['Date_obj'] >= w_start) & (df_a['Date_obj'] <= last_dt_a)]['Training Load'], errors='coerce').fillna(0).sum())
                df_base = df_a[(df_a['Date_obj'] >= b_start) & (df_a['Date_obj'] <= b_end)]
                blocchi = calcola_blocchi_baseline(df_a, b_end, 2.0)
                tl_avg = float(pd.to_numeric(df_base['Training Load'], errors='coerce').fillna(0).sum()) / blocchi if not df_base.empty else 0
                if tl_avg > 0:
                    acwr_pct = (tl_acute / tl_avg * 100)
                    if 80 <= acwr_pct <= 125:
                        n_optimal += 1

    # =========================================================================
    # CALENDARIO & MASTER TIMELINE INTEGRATA (FOCUS ATLETA)
    # =========================================================================
    render_master_timeline(t, atleta_sel=ath_home_sel, key_prefix="home_cal", show_hero_strip=False)
    st.markdown("<div style='margin-top: 25px;'></div>", unsafe_allow_html=True)

    # =========================================================================
    # SEZIONE PRINCIPALE: ROSTER READINESS & ACWR OVERVIEW
    # =========================================================================
    lbl_sec_roster = tr("ROSTER READINESS & ACWR OVERVIEW", "ROSTER READINESS & ACWR OVERVIEW")
    lbl_sec_sub = tr(
        "Monitoraggio integrato del carico acuto (2gg), rolling (7gg) e della settimana corrente per ciascun atleta.",
        "Integrated monitoring of acute load (2d), rolling (7d), and current week for each athlete."
    )

    roster_rows_html = ""
    today_ts = pd.Timestamp.today().normalize()
    curr_monday = today_ts - timedelta(days=today_ts.weekday())
    curr_sunday = curr_monday + timedelta(days=6)

    for idx, ath in enumerate(atleti_visibili):
        df_a = df_storico[df_storico['Players'] == ath].dropna(subset=['Date_obj']).sort_values('Date_obj') if not df_storico.empty else pd.DataFrame()
        if df_a.empty:
            roster_rows_html += (
                "<tr style='border-bottom:1px solid #f1f5f9;'>"
                f"<td style='padding:12px 14px;'><div style='font-weight:800; color:#0f172a; font-size:14.5px;'>{ath}</div>"
                f"<div style='font-size:11px; color:#94a3b8;'>{tr('Nessuna sessione registrata', 'No recorded sessions')}</div></td>"
                "<td style='padding:12px 10px; text-align:center;'><span style='background:#f1f5f9; color:#64748b; padding:4px 8px; border-radius:6px; font-size:10px; font-weight:800;'>NO DATA</span></td>"
                "<td style='padding:12px 14px; text-align:center; color:#94a3b8; font-size:12px;'>—</td>"
                "<td style='padding:12px 14px; text-align:center; color:#94a3b8; font-size:12px;'>—</td>"
                "<td style='padding:12px 14px; text-align:center; color:#94a3b8; font-size:12px;'>0 sess · 0 min</td>"
                "</tr>"
            )
            continue

        last_row = df_a.iloc[-1]
        last_dt = last_row['Date_obj']
        last_dt_str = last_dt.strftime('%d/%m/%Y')
        last_sess_name = str(last_row.get('Session', 'N/D'))
        last_sess_type = str(last_row.get('Tipologia Sessione', 'N/D'))
        last_is_sim = bool(last_row.get('Dato_Simulato', False))
        sim_tag = " <span style='background:#fef3c7; color:#b45309; font-size:9px; font-weight:800; padding:1px 5px; border-radius:4px;'>SIM</span>" if last_is_sim else ""

        days_ago = max(0, int((today_ts - last_dt.normalize()).days))
        if days_ago == 0:
            fresh_bg, fresh_fg, fresh_txt = "#dcfce7", "#166534", tr("OGGI", "TODAY")
        elif days_ago == 1:
            fresh_bg, fresh_fg, fresh_txt = "#e0f2fe", "#0369a1", tr("IERI", "YESTERDAY")
        elif days_ago <= 7:
            fresh_bg, fresh_fg, fresh_txt = "#f1f5f9", "#475569", f"{days_ago} {tr('gg fa', 'd ago')}"
        else:
            fresh_bg, fresh_fg, fresh_txt = "#fef3c7", "#b45309", last_dt_str

        # 1. ACWR 2 Giorni (Acute Load)
        w2_start = last_dt - timedelta(days=1)
        b2_end = w2_start - timedelta(days=1)
        b2_start = b2_end - timedelta(days=27)
        tl_ac_2 = float(pd.to_numeric(df_a[(df_a['Date_obj'] >= w2_start) & (df_a['Date_obj'] <= last_dt)]['Training Load'], errors='coerce').fillna(0).sum())
        df_b2 = df_a[(df_a['Date_obj'] >= b2_start) & (df_a['Date_obj'] <= b2_end)]
        blocchi_2 = calcola_blocchi_baseline(df_a, b2_end, 2.0)
        tl_ch_2 = float(pd.to_numeric(df_b2['Training Load'], errors='coerce').fillna(0).sum()) / blocchi_2 if not df_b2.empty else 0.0
        has_b2 = tl_ch_2 > 0
        pct_2 = (tl_ac_2 / tl_ch_2 * 100.0) if has_b2 else 0.0
        diff_2 = pct_2 - 100.0 if has_b2 else 0.0
        z2_bg, z2_fg, z2_bar, z2_lbl = _acwr_zone_style(pct_2, has_b2)

        if has_b2:
            cell_2d = (
                f"<div style='display:flex; justify-content:space-between; align-items:center;'>"
                f"<span style='background:{z2_bg}; color:{z2_fg}; padding:2px 7px; border-radius:5px; font-weight:900; font-size:13px;'>{pct_2:.0f}% <span style='font-size:10.5px; font-weight:700;'>({diff_2:+.0f}%)</span></span>"
                f"<span style='font-size:11px; color:#64748b; font-weight:700;'><b>{tl_ac_2:.0f}</b> / {tl_ch_2:.0f} TL</span>"
                f"</div>"
                f"{_render_mini_acwr_bar(pct_2, z2_bar, True)}"
            )
        else:
            cell_2d = (
                f"<div style='display:flex; justify-content:space-between; align-items:center;'>"
                f"<span style='background:#f1f5f9; color:#64748b; padding:2px 7px; border-radius:5px; font-weight:800; font-size:10px;'>NO BASELINE</span>"
                f"<span style='font-size:11px; color:#64748b; font-weight:700;'><b>{tl_ac_2:.0f}</b> TL (2gg)</span>"
                f"</div>"
                f"{_render_mini_acwr_bar(0, z2_bar, False)}"
            )

        # 2. ACWR 7 Giorni (7-Day Rolling)
        w7_start = last_dt - timedelta(days=6)
        b7_end = w7_start - timedelta(days=1)
        b7_start = b7_end - timedelta(days=27)
        tl_ac_7 = float(pd.to_numeric(df_a[(df_a['Date_obj'] >= w7_start) & (df_a['Date_obj'] <= last_dt)]['Training Load'], errors='coerce').fillna(0).sum())
        df_b7 = df_a[(df_a['Date_obj'] >= b7_start) & (df_a['Date_obj'] <= b7_end)]
        blocchi_7 = calcola_blocchi_baseline(df_a, b7_end, 7.0)
        tl_ch_7 = float(pd.to_numeric(df_b7['Training Load'], errors='coerce').fillna(0).sum()) / blocchi_7 if not df_b7.empty else 0.0
        has_b7 = tl_ch_7 > 0
        pct_7 = (tl_ac_7 / tl_ch_7 * 100.0) if has_b7 else 0.0
        diff_7 = pct_7 - 100.0 if has_b7 else 0.0
        z7_bg, z7_fg, z7_bar, z7_lbl = _acwr_zone_style(pct_7, has_b7)

        if has_b7:
            cell_7d = (
                f"<div style='display:flex; justify-content:space-between; align-items:center;'>"
                f"<span style='background:{z7_bg}; color:{z7_fg}; padding:2px 7px; border-radius:5px; font-weight:900; font-size:13px;'>{pct_7:.0f}% <span style='font-size:10.5px; font-weight:700;'>({diff_7:+.0f}%)</span></span>"
                f"<span style='font-size:11px; color:#64748b; font-weight:700;'><b>{tl_ac_7:.0f}</b> / {tl_ch_7:.0f} TL</span>"
                f"</div>"
                f"{_render_mini_acwr_bar(pct_7, z7_bar, True)}"
            )
        else:
            cell_7d = (
                f"<div style='display:flex; justify-content:space-between; align-items:center;'>"
                f"<span style='background:#f1f5f9; color:#64748b; padding:2px 7px; border-radius:5px; font-weight:800; font-size:10px;'>NO BASELINE</span>"
                f"<span style='font-size:11px; color:#64748b; font-weight:700;'><b>{tl_ac_7:.0f}</b> TL (7gg)</span>"
                f"</div>"
                f"{_render_mini_acwr_bar(0, z7_bar, False)}"
            )

        # 3. Carico Settimana Corrente (Lun-Dom)
        df_cw = df_a[(df_a['Date_obj'] >= curr_monday) & (df_a['Date_obj'] <= curr_sunday)]
        n_sess_cw = len(df_cw)
        min_cw = float(pd.to_numeric(df_cw['Minuti'], errors='coerce').fillna(0).sum()) if not df_cw.empty else 0.0
        tl_cw = float(pd.to_numeric(df_cw['Training Load'], errors='coerce').fillna(0).sum()) if not df_cw.empty else 0.0

        if n_sess_cw > 0:
            cell_cw = (
                f"<div style='font-weight:900; font-size:13.5px; color:#0f172a;'>{tl_cw:.0f} TL</div>"
                f"<div style='font-size:11px; color:#64748b; margin-top:2px;'>{n_sess_cw} sess · {min_cw:.0f} min</div>"
            )
        else:
            cell_cw = (
                "<div style='font-weight:700; font-size:12px; color:#94a3b8;'>0 TL</div>"
                "<div style='font-size:10.5px; color:#94a3b8; margin-top:2px;'>0 sess · 0 min</div>"
            )

        roster_rows_html += (
            "<tr style='border-bottom:1px solid #f1f5f9;'>"
            f"<td style='padding:12px 14px;'>"
            f"<div style='font-weight:900; color:#0f172a; font-size:14.5px;'>{ath}</div>"
            f"<div style='font-size:11px; color:#64748b; margin-top:2px;'>{tr('Ultima', 'Latest')}: <b style='color:#334155;'>{last_sess_name}</b> "
            f"<span style='color:#0ea5e9; font-weight:700;'>[{last_sess_type}]</span>{sim_tag}</div>"
            "</td>"
            f"<td style='padding:12px 10px; text-align:center;'><span style='background:{fresh_bg}; color:{fresh_fg}; padding:3px 9px; border-radius:6px; font-size:10.5px; font-weight:800; display:inline-block;'>{fresh_txt}</span><div style='font-size:10px; color:#94a3b8; margin-top:3px;'>{last_dt_str}</div></td>"
            f"<td style='padding:12px 14px;'>{cell_2d}</td>"
            f"<td style='padding:12px 14px;'>{cell_7d}</td>"
            f"<td style='padding:12px 14px; text-align:center;'>{cell_cw}</td>"
            "</tr>"
        )

    roster_box_html = (
        "<div style='background:white; border:1px solid #e2e8f0; border-radius:12px; overflow:hidden; box-shadow:0 2px 6px -1px rgba(15,23,42,0.04); margin-bottom:16px; font-family:\"Inter\", sans-serif;'>"
        f"<div style='background:#0f172a; border-bottom:2px solid #0ea5e9; padding:13px 18px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;'>"
        "<div>"
        f"<div style='color:white; font-weight:900; font-size:15px; text-transform:uppercase; letter-spacing:0.8px;'>{lbl_sec_roster}</div>"
        f"<div style='color:#94a3b8; font-size:11.5px; margin-top:2px;'>{lbl_sec_sub}</div>"
        "</div>"
        "<div style='display:flex; gap:6px; flex-wrap:wrap;'>"
        "<span style='background:#e0f2fe; color:#0284c7; font-size:10px; font-weight:800; padding:3px 8px; border-radius:5px;'>&lt;80% LOW</span>"
        "<span style='background:#dcfce7; color:#166534; font-size:10px; font-weight:800; padding:3px 8px; border-radius:5px;'>80-125% OPTIMAL</span>"
        "<span style='background:#fef3c7; color:#b45309; font-size:10px; font-weight:800; padding:3px 8px; border-radius:5px;'>125-150% HIGH</span>"
        "<span style='background:#fee2e2; color:#991b1b; font-size:10px; font-weight:800; padding:3px 8px; border-radius:5px;'>&gt;150% OVERLOAD</span>"
        "</div>"
        "</div>"
        "<table style='width:100%; border-collapse:collapse;'>"
        "<tr style='background:#f8fafc; border-bottom:2px solid #e2e8f0;'>"
        f"<th style='text-align:left; padding:10px 14px; font-size:11px; font-weight:800; color:#475569; text-transform:uppercase; letter-spacing:0.5px; width:25%;'>{tr('Atleta & Ultima Sessione', 'Athlete & Latest Session')}</th>"
        f"<th style='text-align:center; padding:10px 10px; font-size:11px; font-weight:800; color:#475569; text-transform:uppercase; letter-spacing:0.5px; width:11%;'>{tr('Stato Dati', 'Data Status')}</th>"
        f"<th style='text-align:center; padding:10px 14px; font-size:11px; font-weight:800; color:#0f172a; text-transform:uppercase; letter-spacing:0.5px; width:24%;'>{tr('Readiness 2 Giorni (Acute Load)', '2-Day Readiness (Acute Load)')}</th>"
        f"<th style='text-align:center; padding:10px 14px; font-size:11px; font-weight:800; color:#0f172a; text-transform:uppercase; letter-spacing:0.5px; width:24%;'>{tr('Carico 7 Giorni (7-Day Rolling)', '7-Day Load (7-Day Rolling)')}</th>"
        f"<th style='text-align:center; padding:10px 14px; font-size:11px; font-weight:800; color:#475569; text-transform:uppercase; letter-spacing:0.5px; width:16%;'>{tr('Settimana Corrente (Lun-Dom)', 'Current Week (Mon-Sun)')}</th>"
        "</tr>"
        f"{roster_rows_html}"
        "</table>"
        "</div>"
    )

    if not atleti_visibili:
        st.info(tr("Nessun atleta associato al tuo profilo.", "No athletes linked to your profile."))
    elif df_storico.empty:
        st.info(tr("Carica il primo file CSV per attivare il monitoraggio del roster.", "Upload your first CSV file to activate roster monitoring."))
    else:
        st.markdown(roster_box_html, unsafe_allow_html=True)

    st.markdown("<div style='margin-top: 20px;'></div>", unsafe_allow_html=True)

    # =========================================================================
    # SEZIONE INTERMEDIA: TREND CARICHI ULTIMO MESE ROLLING (30 GG) - DUAL Y-AXIS
    # =========================================================================
    if ath_home_sel:
        with st.container(border=True):
            lbl_trend_title = tr("TREND CARICHI ULTIMO MESE ROLLING (30 GIORNI)", "ROLLING LAST MONTH LOAD TREND (30 DAYS)")
            lbl_trend_sub = tr(
                "Confronto a due scale di misura tra Training Load (Volume - Asse Sinistro) e Training Load High (Intensità - Asse Destro).",
                "Dual-axis comparison between Training Load (Volume - Left Axis) and Training Load High (Intensity - Right Axis)."
            )
            st.markdown(
                f"<div style='display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; margin-bottom:12px;'>"
                f"<div>"
                f"<div style='display:flex; align-items:center; gap:8px;'>"
                f"<i class='bi bi-activity' style='color:#0ea5e9; font-size:18px;'></i>"
                f"<span style='font-size:15px; font-weight:900; color:#0f172a; text-transform:uppercase; letter-spacing:0.6px;'>"
                f"{lbl_trend_title} — <span style='color:#0ea5e9;'>{ath_home_sel}</span>"
                f"</span></div>"
                f"<div style='font-size:11.5px; color:#64748b; margin-top:2px;'>{lbl_trend_sub}</div>"
                f"</div>"
                f"<div style='display:flex; gap:6px; flex-wrap:wrap;'>"
                f"<span style='background:rgba(14,165,233,0.12); color:#0284c7; font-size:10px; font-weight:800; padding:3px 8px; border-radius:5px;'><i class='bi bi-bar-chart-fill' style='margin-right:3px;'></i>Training Load (Y1)</span>"
                f"<span style='background:rgba(249,115,22,0.12); color:#ea580c; font-size:10px; font-weight:800; padding:3px 8px; border-radius:5px;'><i class='bi bi-bar-chart-fill' style='margin-right:3px;'></i>TL High (Y2)</span>"
                f"</div></div>",
                unsafe_allow_html=True
            )

            df_ath_roll = df_storico[df_storico['Players'] == ath_home_sel].dropna(subset=['Date_obj']).sort_values('Date_obj') if not df_storico.empty else pd.DataFrame()

            if df_ath_roll.empty:
                st.info(tr("Nessuna sessione registrata per questo atleta.", "No recorded sessions for this athlete."))
            else:
                max_dt_roll = df_ath_roll['Date_obj'].max().normalize()
                min_dt_roll = max_dt_roll - timedelta(days=29)
                date_range_roll = [min_dt_roll + timedelta(days=i) for i in range(30)]

                daily_roll_data = []
                for d_cur in date_range_roll:
                    d_df = df_ath_roll[df_ath_roll['Date_obj'].dt.normalize() == d_cur]
                    tl_sum = float(pd.to_numeric(d_df['Training Load'], errors='coerce').fillna(0).sum())
                    tlh_sum = float(pd.to_numeric(d_df.get('TL_High', 0), errors='coerce').fillna(0).sum())
                    s_types = list(d_df['Tipologia Sessione'].dropna().unique())
                    s_names = list(d_df['Session'].dropna().unique())
                    s_str = ", ".join(s_names) if s_names else tr("Nessuna sessione (Riposo)", "No session (Rest)")
                    t_str = ", ".join(s_types) if s_types else "-"
                    daily_roll_data.append({
                        'date': d_cur,
                        'date_str': d_cur.strftime('%d/%m'),
                        'tl': tl_sum,
                        'tl_high': tlh_sum,
                        'has_sess': len(d_df) > 0,
                        'sess_str': s_str,
                        'types_str': t_str
                    })

                tot_tl_30 = sum(d['tl'] for d in daily_roll_data)
                tot_tlh_30 = sum(d['tl_high'] for d in daily_roll_data)
                ratio_tlh = (tot_tlh_30 / tot_tl_30 * 100.0) if tot_tl_30 > 0 else 0.0
                act_days = sum(1 for d in daily_roll_data if d['has_sess'])

                # 4 Mini KPI Cards riassuntive del mese
                ck1, ck2, ck3, ck4 = st.columns(4)
                with ck1:
                    st.markdown(
                        f"<div style='background:#f8fafc; border:1px solid #e2e8f0; border-left:4px solid #0ea5e9; border-radius:8px; padding:7px 12px; margin-bottom:8px;'>"
                        f"<div style='font-size:10px; font-weight:800; color:#64748b; text-transform:uppercase;'>{tr('Training Load Totale (30gg)', 'Total Training Load (30d)')}</div>"
                        f"<div style='font-size:18px; font-weight:900; color:#0284c7;'>{tot_tl_30:.0f} <span style='font-size:10.5px; font-weight:700;'>AU</span></div>"
                        f"</div>",
                        unsafe_allow_html=True
                    )
                with ck2:
                    st.markdown(
                        f"<div style='background:#f8fafc; border:1px solid #e2e8f0; border-left:4px solid #f97316; border-radius:8px; padding:7px 12px; margin-bottom:8px;'>"
                        f"<div style='font-size:10px; font-weight:800; color:#64748b; text-transform:uppercase;'>{tr('TL High Totale (Neuromuscolare)', 'Total TL High (Neuromuscular)')}</div>"
                        f"<div style='font-size:18px; font-weight:900; color:#ea580c;'>{tot_tlh_30:.0f} <span style='font-size:10.5px; font-weight:700;'>AU</span></div>"
                        f"</div>",
                        unsafe_allow_html=True
                    )
                with ck3:
                    st.markdown(
                        f"<div style='background:#f8fafc; border:1px solid #e2e8f0; border-left:4px solid #8b5cf6; border-radius:8px; padding:7px 12px; margin-bottom:8px;'>"
                        f"<div style='font-size:10px; font-weight:800; color:#64748b; text-transform:uppercase;'>{tr('Rapporto Intensità / Volume', 'Intensity / Volume Ratio')}</div>"
                        f"<div style='font-size:18px; font-weight:900; color:#7c3aed;'>{ratio_tlh:.1f}% <span style='font-size:10.5px; font-weight:700;'>TL High/TL</span></div>"
                        f"</div>",
                        unsafe_allow_html=True
                    )
                with ck4:
                    st.markdown(
                        f"<div style='background:#f8fafc; border:1px solid #e2e8f0; border-left:4px solid #10b981; border-radius:8px; padding:7px 12px; margin-bottom:8px;'>"
                        f"<div style='font-size:10px; font-weight:800; color:#64748b; text-transform:uppercase;'>{tr('Giorni con Attività', 'Active Days')}</div>"
                        f"<div style='font-size:18px; font-weight:900; color:#059669;'>{act_days} <span style='font-size:10.5px; font-weight:700;'>/ 30 {tr('gg', 'days')}</span></div>"
                        f"</div>",
                        unsafe_allow_html=True
                    )

                # Costruzione Grafico Plotly Dual Y-Axis
                fig_roll = go.Figure()
                cdata_list = [[d['sess_str'], d['types_str'], d['tl'], d['tl_high']] for d in daily_roll_data]

                # Traccia 1: Training Load (Scala Sinistra - Y1)
                lbl_tr_tl = tr("Training Load (Volume)", "Training Load (Volume)")
                fig_roll.add_trace(go.Bar(
                    x=[d['date'] for d in daily_roll_data],
                    y=[d['tl'] for d in daily_roll_data],
                    name=lbl_tr_tl,
                    marker=dict(
                        color="rgba(14, 165, 233, 0.85)",
                        line=dict(color="#0284c7", width=1.2)
                    ),
                    yaxis="y1",
                    offsetgroup=1,
                    customdata=cdata_list,
                    hovertemplate=f"<b>%{{x|%d %b %Y}}</b><br>{tr('Sessioni', 'Sessions')}: %{{customdata[0]}} (%{{customdata[1]}})<br><b>Training Load: %{{customdata[2]:.0f}} AU</b><extra></extra>"
                ))

                # Traccia 2: Training Load High (Scala Destra - Y2)
                lbl_tr_tlh = tr("Training Load High (Intensità)", "Training Load High (Intensity)")
                fig_roll.add_trace(go.Bar(
                    x=[d['date'] for d in daily_roll_data],
                    y=[d['tl_high'] for d in daily_roll_data],
                    name=lbl_tr_tlh,
                    marker=dict(
                        color="rgba(249, 115, 22, 0.90)",
                        line=dict(color="#ea580c", width=1.2)
                    ),
                    yaxis="y2",
                    offsetgroup=2,
                    customdata=cdata_list,
                    hovertemplate=f"<b>%{{x|%d %b %Y}}</b><br><b>TL High: %{{customdata[3]:.0f}} AU</b><extra></extra>"
                ))

                max_tl_v = max([d['tl'] for d in daily_roll_data] + [100.0])
                max_tlh_v = max([d['tl_high'] for d in daily_roll_data] + [20.0])

                fig_roll.update_layout(
                    barmode="group",
                    bargap=0.28,
                    bargroupgap=0.08,
                    height=350,
                    margin=dict(l=20, r=20, t=35, b=25),
                    plot_bgcolor="white",
                    paper_bgcolor="white",
                    font=dict(family="Inter, sans-serif", color="#0f172a"),
                    xaxis=dict(
                        showgrid=True,
                        gridcolor="#f1f5f9",
                        tickformat="%d %b",
                        dtick=86400000.0 * 2,
                        tickfont=dict(size=10.5, color="#64748b")
                    ),
                    yaxis=dict(
                        title=dict(text="<b>Training Load (AU)</b>", font=dict(size=11.5, color="#0284c7")),
                        tickfont=dict(size=10.5, color="#0284c7"),
                        showgrid=True,
                        gridcolor="#f1f5f9",
                        range=[0, max_tl_v * 1.15]
                    ),
                    yaxis2=dict(
                        title=dict(text="<b>Training Load High (AU)</b>", font=dict(size=11.5, color="#ea580c")),
                        tickfont=dict(size=10.5, color="#ea580c"),
                        overlaying="y",
                        side="right",
                        showgrid=False,
                        range=[0, max_tlh_v * 1.25]
                    ),
                    legend=dict(
                        orientation="h",
                        yanchor="bottom",
                        y=1.04,
                        xanchor="right",
                        x=1,
                        font=dict(size=11, family="Inter")
                    )
                )
                st.plotly_chart(fig_roll, use_container_width=True)

    st.markdown("<div style='margin-top: 20px;'></div>", unsafe_allow_html=True)

    # =========================================================================
    # SEZIONE: AZIONI RAPIDE & COLLEGAMENTI OPERATIVI (QUICK LAUNCH)
    # =========================================================================
    st.markdown(
        f"<div style='margin-top:20px; margin-bottom:8px; font-weight:800; color:#0f172a; font-size:13px; text-transform:uppercase; letter-spacing:0.5px;'>"
        f"<i class='bi bi-lightning-charge' style='color:#0ea5e9; margin-right:6px;'></i>"
        f"{tr('Accesso Rapido Funzionalità Operative', 'Quick Launch Operational Actions')}"
        f"</div>",
        unsafe_allow_html=True
    )
    # --- BARRA AZIONI RAPIDE (QUICK LAUNCH) ---
    with st.container(border=True):
        b1, b2, b3, b4, b5 = st.columns([1.1, 1.2, 1.1, 1.1, 1.1])
        with b1:
            if st.button(tr("Carica Nuovi CSV", "Upload New CSV"), icon=":material/cloud_upload:", use_container_width=True, type="primary", key="home_btn_upload"):
                st.session_state.current_page = "Caricamento Dati"
                st.rerun()
        with b2:
            if st.button(tr("Generatore (No GPS)", "Generator (No GPS)"), icon=":material/tune:", use_container_width=True, key="home_btn_gen"):
                st.session_state.current_page = "Generatore Dati (No GPS)"
                st.rerun()
        with b3:
            if st.button(tr("Gestione File DB", "File & DB Manager"), icon=":material/folder_open:", use_container_width=True, key="home_btn_manage"):
                st.session_state.current_page = "Gestione File Caricati"
                st.rerun()
        with b4:
            if st.button(tr("Medie & Roster", "Averages & Roster"), icon=":material/bar_chart:", use_container_width=True, key="home_btn_medie"):
                st.session_state.current_page = "Medie"
                st.rerun()
        with b5:
            if st.button(tr("Manuale REPORT", "Reports Manual"), icon=":material/menu_book:", use_container_width=True, key="home_btn_manuale"):
                st.session_state.current_page = "Manuale Report"
                st.rerun()
