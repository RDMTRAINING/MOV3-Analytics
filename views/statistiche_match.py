import os
import re
import json
import datetime
from datetime import timedelta
import pandas as pd
import numpy as np
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

from config import (
    LOGO_PATH,
    tr,
    render_page_header,
    card_kpi,
    render_scientific_methodology_box,
    render_tab_navigation,
    render_action_bar,
)
from utils import (
    load_local_database,
    get_lista_atleti_disponibili,
    get_val,
    render_athlete_hero_strip,
)
from utils_tennis_matches import (
    load_cobolli_matches,
    load_match_gps_links,
    save_match_gps_link,
    remove_match_gps_link,
)
from pdf_generator import crea_pdf_statistiche_match, slugify_name


def clean_match_opponent_name(opp_raw):
    """
    Estrae il cognome/denominazione pulita dell'avversario dai dati match ATP/ITF,
    eliminando qualificatori (es: '(2)', '(Q)', '(WC)', '(LL)', '(W)'), codici nazione
    (es: '[FRA]', '[ESP]', '(CRO)'), iniziali e spazi superflui.
    """
    s = str(opp_raw).strip()
    s = re.sub(r'\[.*?\]', '', s).strip()
    s = re.sub(r'\([A-Za-z0-9]+\)', '', s).strip()
    s = re.sub(r'^[a-zA-Z]\.\s*', '', s).strip()
    s = re.sub(r'\s+', ' ', s).strip()
    parts = s.split()
    if not parts:
        return 'Opp'
    if len(parts) == 1:
        return parts[0]
    if (len(parts[-1]) <= 2 and parts[-1].endswith('.')) or (len(parts[-1]) == 1 and parts[-1].isupper()):
        return parts[0]
    compound_prefixes = {'de', 'di', 'van', 'der', 'del', 'da', 'la', 'le'}
    if len(parts) >= 3 and parts[-2].lower() in compound_prefixes:
        return f"{parts[-2]} {parts[-1]}"
    if 'davidovich' in s.lower() and 'fokina' in s.lower():
        return 'Davidovich Fokina'
    if 'carballes' in s.lower() and 'baena' in s.lower():
        return 'Carballes Baena'
    if 'bautista' in s.lower() and 'agut' in s.lower():
        return 'Bautista Agut'
    if 'auger' in s.lower() and 'aliassime' in s.lower():
        return 'Auger-Aliassime'
    if 'struff' in s.lower():
        return 'Struff'
    return parts[-1]


def build_correlated_dataset(df_f, df_gps_ath, gps_links):
    """
    Associa a ciascun match singolo reale i dati GPS reali (da abbinamento esplicito o per data comune).
    Restituisce un DataFrame rigorosamente ordinato in senso cronologico, solo dati reali e match singoli.
    """
    rows = []
    for idx, r in df_f.iterrows():
        mid = str(r.get("match_id", ""))
        dt = str(r.get("date", ""))
        tot_pts = float(r.get("total_points", 0)) if pd.notna(r.get("total_points")) and r.get("total_points") else 0
        dur_min = float(r.get("duration_min", 0)) if pd.notna(r.get("duration_min")) and r.get("duration_min") else 0

        gps_data = None
        if mid in gps_links:
            l = gps_links[mid]
            gps_data = {
                'tl': float(l.get('tl', 0)),
                'tl_high': float(l.get('tl_high', 0)),
                'dist': float(l.get('dist', 0)),
                'min': float(l.get('min', 0)),
                'pl': float(l.get('player_load', 0)),
                'acc': float(l.get('acc', 0)),
                'dec': float(l.get('dec', 0)),
                'vhml': float(l.get('vhml', 0)),
                'dec_events': float(l.get('dec_events', 0)),
                'actions_imu_2s': float(l.get('actions_imu_2s', l.get('actions_imu', 0))),
                'is_manual': True
            }
        elif not df_gps_ath.empty:
            # Ricerca sessione reale di match singolo registrata in quella data
            match_sess = df_gps_ath[df_gps_ath['Date'] == dt]
            if not match_sess.empty:
                s_row = match_sess.sort_values(by='Training Load', ascending=False).iloc[0]
                gps_data = {
                    'tl': float(get_val(s_row, 'Training Load', 0)),
                    'tl_high': float(get_val(s_row, 'TL_High', 0)),
                    'dist': float(get_val(s_row, 'DISTANCE', 0)),
                    'min': float(get_val(s_row, 'Minuti', 0)),
                    'pl': float(get_val(s_row, 'Player Load', 0)),
                    'acc': float(get_val(s_row, 'High Accel IMU', 0)),
                    'dec': float(get_val(s_row, 'High Decel IMU', 0)),
                    'vhml': float(get_val(s_row, 'VHML Distance >50W', 0)),
                    'dec_events': float(get_val(s_row, 'High Dec Events <-3.5 m/s2', 0)),
                    'actions_imu_2s': float(get_val(s_row, 'Azioni Int. IMU >2', 0)),
                    'is_manual': False
                }

        has_valid_gps = gps_data is not None and tot_pts > 0 and (gps_data.get('tl', 0) > 0 or gps_data.get('dist', 0) > 0)
        if has_valid_gps:
            row_dict = r.to_dict()
            row_dict.update(gps_data)

            srv_pts = float(r.get("service_points", 0)) if pd.notna(r.get("service_points")) and r.get("service_points") else 0
            ret_pts = max(0.0, tot_pts - srv_pts)

            dist_val = float(gps_data.get('dist', 0))
            dur_mins = float(gps_data.get('min', 0))

            row_dict['m_per_point'] = (dist_val / tot_pts) if dist_val > 0 else np.nan
            row_dict['tl_per_point'] = gps_data['tl'] / tot_pts
            row_dict['pl_per_point'] = gps_data['pl'] / tot_pts
            row_dict['acc_dec_per_point'] = (gps_data['acc'] + gps_data['dec']) / tot_pts
            row_dict['pct_tl_high'] = (gps_data['tl_high'] / gps_data['tl'] * 100) if gps_data['tl'] > 0 else 0
            row_dict['m_per_min'] = (dist_val / dur_mins) if (dist_val > 0 and dur_mins > 0) else np.nan

            # Metriche Per-Point Validate (Costo Fisico Vivo & Work Rate)
            row_dict['tl_high_per_point'] = (gps_data['tl_high'] / tot_pts) if tot_pts > 0 else 0
            row_dict['tl_high_per_min'] = (gps_data['tl_high'] / dur_mins) if dur_mins > 0 else 0
            row_dict['tl_per_min'] = (gps_data['tl'] / dur_mins) if dur_mins > 0 else 0
            row_dict['imu_actions_per_10pt'] = (gps_data['actions_imu_2s'] / tot_pts * 10.0) if tot_pts > 0 else 0
            row_dict['actions_imu_2s'] = gps_data.get('actions_imu_2s', 0)

            # Scorporo Servizio vs Risposta (Modello Biomeccanico Tennis Elite)
            row_dict['service_points'] = srv_pts
            row_dict['return_points'] = ret_pts
            row_dict['pct_srv_points'] = (srv_pts / tot_pts * 100.0) if tot_pts > 0 else 50.0
            row_dict['pct_ret_points'] = (ret_pts / tot_pts * 100.0) if tot_pts > 0 else 50.0

            # In letteratura (Kovacs 2007; Reid 2016; Harper 2019):
            # La risposta comporta un carico eccentrico/decelerativo del ~40% superiore e metabolico del ~35% superiore rispetto al servizio
            weight_metab = (srv_pts * 1.0) + (ret_pts * 1.35)
            if weight_metab > 0:
                base_tlh = gps_data['tl_high'] / weight_metab
                row_dict['tl_high_per_srv_pt'] = round(base_tlh, 2)
                row_dict['tl_high_per_ret_pt'] = round(base_tlh * 1.35, 2)
            else:
                row_dict['tl_high_per_srv_pt'] = 0.0
                row_dict['tl_high_per_ret_pt'] = 0.0

            weight_mech = (srv_pts * 1.0) + (ret_pts * 1.40)
            tot_acc_dec = gps_data['acc'] + gps_data['dec']
            if weight_mech > 0:
                base_accdec = tot_acc_dec / weight_mech
                row_dict['acc_dec_per_srv_pt'] = round(base_accdec, 2)
                row_dict['acc_dec_per_ret_pt'] = round(base_accdec * 1.40, 2)
            else:
                row_dict['acc_dec_per_srv_pt'] = 0.0
                row_dict['acc_dec_per_ret_pt'] = 0.0

            rows.append(row_dict)

    df_out = pd.DataFrame(rows)
    if not df_out.empty:
        # Filtra eventuali righe prive di carico reale
        df_out = df_out[(df_out['tl'] > 0) | (df_out['dist'] > 0)].copy()
        # Ordinamento cronologico rigoroso per data reale
        try:
            df_out['date_dt'] = pd.to_datetime(df_out['date'], format='%d/%m/%Y', errors='coerce')
            df_out = df_out.sort_values(by='date_dt', ascending=True).reset_index(drop=True)
        except Exception:
            if 'date_obj' in df_out.columns:
                df_out = df_out.sort_values(by='date_obj', ascending=True).reset_index(drop=True)
    return df_out


def render_statistiche_match(t):
    render_page_header(
        tr("Statistiche Match Ufficiali (Singolari)", "Official Match Statistics (Singles)"),
        tr("Archivio storico dei match singoli ATP/ITF, statistiche di gioco e correlazione con dati reali GPS/IMU.",
           "Historical ATP/ITF singles match database, match statistics, and correlation with real GPS/IMU telemetry."),
        "OFFICIAL SINGLES MATCH STATS"
    )

    atleti_visibili = get_lista_atleti_disponibili(st.session_state.get('user'), st.session_state.get('role'))
    ath_sel = st.session_state.get('selected_athlete')
    if not ath_sel or (atleti_visibili and ath_sel not in atleti_visibili):
        ath_sel = atleti_visibili[0] if atleti_visibili else "Flavio Cobolli"

    is_cobolli = "cobolli" in str(ath_sel).lower()

    if not is_cobolli:
        st.info(tr(
            f"Al momento l'archivio dettagliato dei match e configurato per Flavio Cobolli. Seleziona Flavio Cobolli dal menu laterale.",
            f"Currently the detailed official match history is configured for Flavio Cobolli. Select Flavio Cobolli from the sidebar."
        ))
        return

    # Carica dataset match ufficiali - RIGOROSAMENTE SOLO MATCH SINGOLI
    df_matches_all = load_cobolli_matches()
    if df_matches_all.empty:
        st.warning(tr("Nessun match trovato nel file di storico Cobolli.", "No matches found in Cobolli history file."))
        return

    # Filtro solo match singoli
    df_matches = df_matches_all[df_matches_all['type'].astype(str).str.lower() == 'singolare'].copy()

    # Carica database GPS - RIGOROSAMENTE SOLO DATI REALI (NO SIMULATI) E SOLO MATCH SINGOLI
    df_gps_all = load_local_database()
    df_gps_ath = df_gps_all[df_gps_all['Players'].astype(str).str.lower().str.contains("cobolli", na=False)].copy() if not df_gps_all.empty else pd.DataFrame()
    
    if not df_gps_ath.empty:
        # Escludi categoricamente dati simulati o generati
        if 'Dato_Simulato' in df_gps_ath.columns:
            df_gps_ath = df_gps_ath[df_gps_ath['Dato_Simulato'] != True].copy()
        df_gps_ath = df_gps_ath[~df_gps_ath['Session'].astype(str).str.strip().str.endswith('*')].copy()
        if 'File_Name' in df_gps_ath.columns:
            df_gps_ath = df_gps_ath[df_gps_ath['File_Name'] != 'Generato_dal_Sistema_M0V3'].copy()
        # Solo sessioni match singoli
        df_gps_ath = df_gps_ath[df_gps_ath['Tipologia Sessione'].astype(str).str.strip().str.lower() == 'match'].copy()

    gps_links = load_match_gps_links()

    # =========================================================================
    # PANNELLO FILTRI & RICERCA AVANZATA
    # =========================================================================
    with st.container(border=True):
        st.markdown(
            f"<div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; flex-wrap:wrap; gap:8px;'>"
            f"<div style='display:flex; align-items:center; gap:8px;'>"
            f"<i class='bi bi-funnel-fill' style='color:#0ea5e9; font-size:17px;'></i>"
            f"<span style='font-size:14px; font-weight:800; color:#0f172a; text-transform:uppercase; letter-spacing:0.5px;'>"
            f"{tr('Pannello Ricerca & Filtri Match Singolari', 'Singles Match Search & Filters Panel')}</span>"
            f"</div>"
            f"<span style='background:#e0f2fe; color:#0369a1; font-weight:800; font-size:11px; padding:3px 10px; border-radius:6px;'>"
            f"<i class='bi bi-shield-check'></i> SOLO MATCH SINGOLI & DATI REALI"
            f"</span>"
            f"</div>",
            unsafe_allow_html=True
        )

        f_c1, f_c2, f_c3, f_c4 = st.columns([1.2, 1.1, 1.1, 1.1])
        
        min_date_val = df_matches["date_obj"].min() if "date_obj" in df_matches.columns else datetime.date(2019, 1, 1)
        max_date_val = df_matches["date_obj"].max() if "date_obj" in df_matches.columns else datetime.date.today()
        default_start = datetime.date(2024, 1, 1) if min_date_val <= datetime.date(2024, 1, 1) else min_date_val

        with f_c1:
            data_inizio = st.date_input(
                tr("Match a partire dal:", "Matches starting from:"),
                value=default_start,
                min_value=min_date_val,
                max_value=max_date_val,
                key="filter_match_date_start"
            )

        with f_c2:
            opzioni_surf = [tr("Tutte le Superfici", "All Surfaces"), "Hard", "Clay", "Grass"]
            sel_surf = st.selectbox(tr("Superficie", "Surface"), opzioni_surf, index=0, key="filter_match_surface")

        with f_c3:
            opzioni_res = [tr("Tutti gli Esiti", "All Results"), tr("Solo Vittorie (W)", "Wins Only (W)"), tr("Solo Sconfitte (L)", "Losses Only (L)")]
            sel_res = st.selectbox(tr("Esito Partita", "Match Result"), opzioni_res, index=0, key="filter_match_res")

        with f_c4:
            filtro_gps_link = st.selectbox(
                tr("Stato Telemetria GPS", "GPS Telemetry Status"),
                [tr("Tutti i Match Singoli", "All Singles Matches"), tr("Solo con Telemetria GPS Reale", "Only with Real GPS Data"), tr("Solo senza GPS", "Only without GPS")],
                index=0,
                key="filter_match_gps_link"
            )

        f_r2_1, f_r2_2 = st.columns([1.6, 1.2])
        with f_r2_1:
            search_query = st.text_input(
                tr("Cerca Avversario o Torneo", "Search Opponent or Tournament"),
                placeholder=tr("Es: Shelton, Vienna, Australian Open, Baez...", "E.g. Shelton, Vienna, Australian Open, Baez..."),
                key="filter_match_search"
            ).strip().lower()

        with f_r2_2:
            opzioni_rank = [
                tr("Qualsiasi Ranking Avversario", "Any Opponent Rank"),
                "Top 10",
                "Top 20",
                "Top 50",
                "Top 100",
                "Oltre i Top 100"
            ]
            sel_rank = st.selectbox(tr("Ranking Avversario", "Opponent Ranking"), opzioni_rank, index=0, key="filter_match_rank")

    # =========================================================================
    # APPLICAZIONE DEI FILTRI
    # =========================================================================
    df_f = df_matches.copy()
    if data_inizio:
        df_f = df_f[df_f["date_obj"] >= data_inizio]

    if sel_surf != tr("Tutte le Superfici", "All Surfaces"):
        df_f = df_f[df_f["surface"] == sel_surf]

    if sel_res == tr("Solo Vittorie (W)", "Wins Only (W)"):
        df_f = df_f[df_f["result"] == "Vittoria"]
    elif sel_res == tr("Solo Sconfitte (L)", "Losses Only (L)"):
        df_f = df_f[df_f["result"] == "Sconfitta"]

    if search_query:
        df_f = df_f[
            df_f["opponent"].astype(str).str.lower().str.contains(search_query) |
            df_f["tournament"].astype(str).str.lower().str.contains(search_query) |
            df_f["matchup"].astype(str).str.lower().str.contains(search_query)
        ]

    if sel_rank == "Top 10":
        df_f = df_f[df_f["opponent_rank"].fillna(999) <= 10]
    elif sel_rank == "Top 20":
        df_f = df_f[df_f["opponent_rank"].fillna(999) <= 20]
    elif sel_rank == "Top 50":
        df_f = df_f[df_f["opponent_rank"].fillna(999) <= 50]
    elif sel_rank == "Top 100":
        df_f = df_f[df_f["opponent_rank"].fillna(999) <= 100]
    elif sel_rank == "Oltre i Top 100":
        df_f = df_f[df_f["opponent_rank"].fillna(0) > 100]

    # Costruisci dataset correlato Tennis <-> GPS reale
    df_corr = build_correlated_dataset(df_f, df_gps_ath, gps_links)
    linked_mids = set(df_corr["match_id"].tolist()) if not df_corr.empty else set()

    if filtro_gps_link == tr("Solo con Telemetria GPS Reale", "Only with Real GPS Data"):
        df_f = df_f[df_f["match_id"].isin(linked_mids)]
    elif filtro_gps_link == tr("Solo senza GPS", "Only without GPS"):
        df_f = df_f[~df_f["match_id"].isin(linked_mids)]

    # Ordina per data decrescente per l'archivio
    df_f = df_f.sort_values("date_obj", ascending=False).reset_index(drop=True)

    # =========================================================================
    # KPI DI TESTATA SUI MATCH SELEZIONATI
    # =========================================================================
    tot_m = len(df_f)
    vittorie = len(df_f[df_f["result"] == "Vittoria"])
    sconfitte = len(df_f[df_f["result"] == "Sconfitta"])
    win_rate = (vittorie / tot_m * 100) if tot_m > 0 else 0.0

    tot_dur_min = df_f["duration_min"].sum()
    avg_dur_min = (tot_dur_min / tot_m) if tot_m > 0 else 0
    h_avg, m_avg = divmod(int(avg_dur_min), 60)
    dur_avg_str = f"{h_avg}h {m_avg:02d}m" if h_avg > 0 else f"{m_avg}m"

    tot_aces = int(df_f["aces"].sum())
    avg_aces = (tot_aces / tot_m) if tot_m > 0 else 0.0

    linked_gps_count = len(df_corr)
    pct_gps_linked = (linked_gps_count / tot_m * 100) if tot_m > 0 else 0.0

    # Barra di azione istituzionale per esportazione PDF senza tagli
    slug_ath = slugify_name(ath_sel)
    render_action_bar(
        meta_items=[
            (tr("Atleta", "Athlete"), ath_sel),
            (tr("Match Filtrati", "Filtered Matches"), f"{tot_m} ({win_rate:.1f}% Win)"),
            (tr("Telemetrie Reali GPS", "Real GPS Data"), f"{linked_gps_count} match"),
            (tr("Superficie", "Surface"), sel_surf),
            (tr("Esito", "Result"), sel_res)
        ],
        pdf_options={tr("Report Completo Statistiche Match", "Full Match Statistics Report"): "Tutte"},
        pdf_key=f"sm_pdf_{slug_ath}_{slugify_name(sel_surf)}_{slugify_name(sel_res)}",
        generate_fn=lambda _: crea_pdf_statistiche_match(ath_sel, df_corr, df_f, df_matches),
        filename_fn=lambda _: f"M0V3_Statistiche_Match_{slug_ath}_{slugify_name(sel_surf)}_{datetime.date.today().strftime('%Y%m%d')}.pdf"
    )

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(
            card_kpi(
                tr("Win Rate Match Singoli", "Singles Match Win Rate"),
                f"<span style='font-size:25px; font-weight:900; color:#0f172a;'>{win_rate:.1f}%</span> "
                f"<span style='font-size:11.5px; font-weight:800; color:#16a34a; background:#dcfce7; padding:2px 7px; border-radius:6px;'>{vittorie}W - {sconfitte}L</span>",
                f"{tot_m} {tr('match singoli filtrati', 'filtered singles matches')}",
                "#10b981"
            ),
            unsafe_allow_html=True
        )
    with k2:
        st.markdown(
            card_kpi(
                tr("Durata Media Partita", "Average Match Duration"),
                f"<span style='font-size:25px; font-weight:900; color:#0f172a;'>{dur_avg_str}</span>",
                f"{int(tot_dur_min // 60)} {tr('ore totali in campo', 'total hours on court')}",
                "#0284c7"
            ),
            unsafe_allow_html=True
        )
    with k3:
        st.markdown(
            card_kpi(
                tr("Ace Totali & Media", "Total Aces & Average"),
                f"<span style='font-size:25px; font-weight:900; color:#0f172a;'>{tot_aces}</span> "
                f"<span style='font-size:12px; font-weight:700; color:#64748b;'>({avg_aces:.1f} / match)</span>",
                f"{int(df_f['total_points'].sum() / tot_m) if tot_m > 0 else 0} {tr('punti medi disputati', 'avg points played')}",
                "#f59e0b"
            ),
            unsafe_allow_html=True
        )
    with k4:
        st.markdown(
            card_kpi(
                tr("Telemetria GPS Reale", "Real GPS Telemetry"),
                f"<span style='font-size:25px; font-weight:900; color:#0f172a;'>{linked_gps_count} <span style='font-size:16px; color:#64748b;'>/ {tot_m}</span></span>",
                f"<span style='color:#0284c7; font-weight:800;'>{pct_gps_linked:.0f}%</span> {tr('acquisizioni reali abbinate', 'real acquisitions paired')}",
                "#8b5cf6"
            ),
            unsafe_allow_html=True
        )

    # SPAZIATURA GENEROSA SOTTO LE KPI CARDS
    st.markdown("<div style='margin-top: 30px; margin-bottom: 10px;'></div>", unsafe_allow_html=True)

    # =========================================================================
    # STRUTTURA A SUB-PAGINE / TAB (CON PERSISTENZA)
    # =========================================================================
    lbl_tab_analisi = tr("📊 Analisi Prestazione Tennis ↔ GPS", "📊 Tennis ↔ GPS Performance Analysis")
    lbl_tab_archivio = tr("🎾 Archivio Partite & Abbinamento Telemetria", "🎾 Match Archive & Telemetry Pairing")
    active_sm_tab = render_tab_navigation(
        [lbl_tab_analisi, lbl_tab_archivio],
        key="nav_sub_statistiche_match",
        default=lbl_tab_analisi
    )

    # -------------------------------------------------------------------------
    # TAB 1: ANALISI PRESTAZIONE TENNIS <-> GPS (SOLO MATCH SINGOLI & DATI REALI)
    # -------------------------------------------------------------------------
    if active_sm_tab == lbl_tab_analisi:
        if df_corr.empty:
            st.info(tr(
                "Nessuna sessione GPS reale corrisponde ai match singoli filtrati nel periodo selezionato. Prova ad allargare i filtri temporali o di superficie.",
                "No real GPS sessions match the filtered singles matches in the selected period. Try broadening the date or surface filters."
            ))
        else:
            n_corr = len(df_corr)
            tot_dist_km = df_corr['dist'].sum() / 1000.0
            tot_ore_gps = df_corr['min'].sum() / 60.0
            tot_pts_gps = int(df_corr['total_points'].sum())

            # Banner Informativo Dataset Correlato Reale
            st.markdown(f"""
            <div style='background: linear-gradient(135deg, rgba(14, 165, 233, 0.08) 0%, rgba(30, 41, 59, 0.02) 100%); border: 1px solid rgba(14, 165, 233, 0.25); border-radius: 10px; padding: 14px 18px; margin-bottom: 28px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px;'>
                <div>
                    <span style='font-weight: 800; color: #0284c7; text-transform: uppercase; font-size: 11px; letter-spacing: 0.6px;'><i class='bi bi-cpu-fill'></i> TELEMETRIA FISICO-TECNICA REALE · SOLO MATCH SINGOLI</span>
                    <div style='font-weight: 800; font-size: 15px; color: #0f172a; margin-top: 2px;'>
                        Analisi condotta su <b>{n_corr} match singoli ufficiali</b> ({tot_pts_gps:,} punti · {tot_dist_km:.1f} km reali · {tot_ore_gps:.1f} ore di gara)
                    </div>
                </div>
                <div>
                    <span style='background: white; border: 1px solid #cbd5e1; border-radius: 6px; padding: 5px 12px; font-size: 11.5px; font-weight: 700; color: #15803d; box-shadow: 0 1px 2px rgba(0,0,0,0.04);'>
                        <i class='bi bi-check2-circle' style='color:#16a34a;'></i> 100% Dati Reali da Tracker GPS
                    </span>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # =================================================================
            # 1. COSTO FISICO DEL PUNTO (METRICHE PER-POINT & WORK RATE)
            # =================================================================
            st.markdown(f"""
            <div style='font-size: 16px; font-weight: 900; color: #0f172a; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 14px; display: flex; align-items: center; gap: 8px;'>
                <i class='bi bi-speedometer2' style='color: #0ea5e9;'></i>
                {tr("1. Costo Fisico del Punto nei Match Singoli", "1. Physical Cost of the Point in Singles Matches")}
            </div>
            """, unsafe_allow_html=True)

            tl_high_min_avg = df_corr['tl_high_per_min'].mean() if 'tl_high_per_min' in df_corr.columns else 0.0
            tl_high_pt_avg = df_corr['tl_high_per_point'].mean() if 'tl_high_per_point' in df_corr.columns else 0.0
            acc_dec_pt_avg = df_corr['acc_dec_per_point'].mean() if 'acc_dec_per_point' in df_corr.columns else 0.0
            imu_actions_avg = df_corr['imu_actions_per_10pt'].mean() if 'imu_actions_per_10pt' in df_corr.columns else 0.0

            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.markdown(card_kpi(
                    tr("TL High al Minuto", "TL High per Minute"),
                    f"<span style='font-size:25px; font-weight:900; color:#0f172a;'>{tl_high_min_avg:.1f} <span style='font-size:15px; font-weight:700; color:#64748b;'>AU/min</span></span>",
                    f"{tr('Work rate metabolico ad alta intensità', 'High intensity metabolic work rate')}",
                    "#0284c7"
                ), unsafe_allow_html=True)
            with c2:
                st.markdown(card_kpi(
                    tr("Costo Vivo (TL High / pt)", "Active Cost (TL High / pt)"),
                    f"<span style='font-size:25px; font-weight:900; color:#0f172a;'>{tl_high_pt_avg:.2f} <span style='font-size:15px; font-weight:700; color:#64748b;'>AU/pt</span></span>",
                    f"{tr('Costo metabolico attivo dello scambio', 'Active rally metabolic cost')}",
                    "#ef4444"
                ), unsafe_allow_html=True)
            with c3:
                st.markdown(card_kpi(
                    tr("Acc + Dec IMU / Punto", "High Acc + Dec / Point"),
                    f"<span style='font-size:25px; font-weight:900; color:#0f172a;'>{acc_dec_pt_avg:.2f} <span style='font-size:15px; font-weight:700; color:#64748b;'>ev/pt</span></span>",
                    f"~1 {tr('azione intensa ogni', 'intense action every')} {1.0 / acc_dec_pt_avg:.1f} {tr('punti', 'pts')}" if acc_dec_pt_avg > 0 else "N/D",
                    "#ea580c"
                ), unsafe_allow_html=True)
            with c4:
                st.markdown(card_kpi(
                    tr("Densità Scambi IMU >2\"", "Rally Density IMU >2\""),
                    f"<span style='font-size:25px; font-weight:900; color:#0f172a;'>{imu_actions_avg:.1f} <span style='font-size:15px; font-weight:700; color:#64748b;'>/ 10 pt</span></span>",
                    f"{tr('Scambi prolungati (Outdoor + Indoor)', 'Prolonged rallies (Outdoor + Indoor)')}",
                    "#8b5cf6"
                ), unsafe_allow_html=True)

            # SPAZIATURA PULITA TRA LE 4 CARD E IL GRAFICO
            st.markdown("<div style='margin-top: 24px; margin-bottom: 8px;'></div>", unsafe_allow_html=True)

            # SELETTORE METRICA PER-POINT DINAMICA (METRI PER PUNTO RIMOSSI PER CONFRONTO INDOOR/OUTDOOR ROBUSTO)
            opt_metrics = [
                tr("Costo Fisico Vivo (TL High / pt)", "Active Physical Cost (TL High / pt)"),
                tr("Training Load High al Minuto (TL High / min)", "High Training Load per Minute (TL High / min)"),
                tr("Acc + Dec IMU per Punto (ev/pt)", "High Acc + Dec per Point (ev/pt)"),
                tr("Densità Scambi (Azioni IMU >2\" / 10 pt)", "Rally Density (IMU Actions >2\" / 10 pt)")
            ]
            sel_metric_lbl = st.radio(
                tr("Seleziona Metrica Per-Point da visualizzare:", "Select Per-Point Metric to display:"),
                opt_metrics,
                index=0,
                horizontal=True,
                key="sm_metric_radio"
            )

            if "TL High / min" in sel_metric_lbl:
                target_plot_col = 'tl_high_per_min'
                y_axis_title = tr("TL High / min (AU/min)", "TL High / min (AU/min)")
                metric_unit = "AU/min"
                metric_avg_val = tl_high_min_avg
            elif "Acc + Dec" in sel_metric_lbl:
                target_plot_col = 'acc_dec_per_point'
                y_axis_title = tr("Acc + Dec IMU per Punto (ev/pt)", "High Acc + Dec per Point (ev/pt)")
                metric_unit = "ev/pt"
                metric_avg_val = acc_dec_pt_avg
            elif "IMU >2" in sel_metric_lbl or "Densità" in sel_metric_lbl:
                target_plot_col = 'imu_actions_per_10pt'
                y_axis_title = tr("Azioni Intense IMU >2\" ogni 10 punti", "High IMU Actions >2\" per 10 pts")
                metric_unit = "azioni/10pt"
                metric_avg_val = imu_actions_avg
            else:
                target_plot_col = 'tl_high_per_point'
                y_axis_title = tr("Costo Vivo (TL High / pt)", "Active Cost (TL High / pt)")
                metric_unit = "AU/pt"
                metric_avg_val = tl_high_pt_avg

            # GRAFICO A BARRE CRONOLOGICHE ORDINATE PER MATCH SINGOLO (ZERO LINEE INCROCIATE)
            with st.container(border=True):
                st.markdown(f"""
                <div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px;'>
                    <div style='font-size: 13.5px; font-weight: 800; color: #0f172a;'>
                        {sel_metric_lbl} {tr("per ciascun Match Ufficiale (Cronologico)", "for each Official Match (Chronological)")}
                    </div>
                    <div style='font-size: 11.5px; font-weight: 700; color: #64748b;'>
                        <span style='color: #10b981;'><i class='bi bi-square-fill'></i> Vittoria</span> &nbsp;
                        <span style='color: #ef4444;'><i class='bi bi-square-fill'></i> Sconfitta</span> &nbsp;
                        <span style='color: #0284c7;'><i class='bi bi-dash-lg'></i> Media Mobile (3 Match)</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                # Prepara etichette pulite per ciascuna barra basate sul match ufficiale dal database
                bar_labels = []
                bar_colors = []
                bar_borders = []

                # Mappa di lookup rapido per data dai match singoli ufficiali
                match_by_date = {}
                if 'df_matches' in locals() and not df_matches.empty:
                    for _, m_row in df_matches.iterrows():
                        m_dt = str(m_row.get('date', '')).strip()
                        if m_dt and m_dt not in match_by_date:
                            match_by_date[m_dt] = m_row

                for _, r in df_corr.iterrows():
                    r_dt = str(r.get('date', '')).strip()
                    m_official = match_by_date.get(r_dt)

                    opp_val = r.get('opponent')
                    if (not opp_val or str(opp_val).strip() in ['', 'None', 'nan', 'Opp']) and m_official is not None:
                        opp_val = m_official.get('opponent', '')
                    opp_clean = clean_match_opponent_name(opp_val)

                    tourn_val = str(r.get('tournament', '')).strip()
                    if (not tourn_val or tourn_val in ['None', 'nan']) and m_official is not None:
                        tourn_val = str(m_official.get('tournament', '')).strip()

                    if tourn_val and tourn_val not in ['None', 'nan']:
                        label_txt = f"{r_dt} · vs {opp_clean} ({tourn_val})"
                    else:
                        label_txt = f"{r_dt} · vs {opp_clean}"
                    bar_labels.append(label_txt)

                    if r['result'] == 'Vittoria':
                        bar_colors.append('#10b981')
                        bar_borders.append('#059669')
                    else:
                        bar_colors.append('#ef4444')
                        bar_borders.append('#dc2626')

                # Calcolo media mobile a 3 match per trend fluido
                rolling_trend = df_corr[target_plot_col].rolling(window=3, min_periods=1).mean()

                fig_m_pt = go.Figure()

                # Barre singole per ogni match
                fig_m_pt.add_trace(go.Bar(
                    x=bar_labels,
                    y=df_corr[target_plot_col],
                    marker=dict(
                        color=bar_colors,
                        line=dict(color=bar_borders, width=1)
                    ),
                    name=sel_metric_lbl,
                    customdata=np.stack((
                        df_corr['tournament'],
                        df_corr['surface'],
                        df_corr['opponent'].apply(clean_match_opponent_name),
                        df_corr['score'],
                        df_corr['tl'],
                        df_corr['duration_str'],
                        df_corr['total_points'],
                        df_corr['tl_high_per_point'],
                        df_corr['result'],
                        df_corr['tl_high'],
                        df_corr['imu_actions_per_10pt'],
                        df_corr['acc_dec_per_point']
                    ), axis=-1),
                    hovertemplate=(
                        "<b>%{customdata[0]}</b> (%{customdata[1]})<br>"
                        "vs <b>%{customdata[2]}</b> · %{customdata[3]}<br>"
                        "<b>Esito: %{customdata[8]}</b><br>"
                        "<b>Valore: %{y:.2f} " + metric_unit + "</b><br>"
                        "Training Load: %{customdata[4]:.0f} TL (High: %{customdata[9]:.0f})<br>"
                        "Costo Vivo TL High: %{customdata[7]:.2f} AU/pt<br>"
                        "Acc+Dec IMU: %{customdata[11]:.2f} ev/pt<br>"
                        "Azioni IMU &gt;2\": %{customdata[10]:.1f} / 10pt<br>"
                        "Durata: %{customdata[5]} · Punti: %{customdata[6]}<extra></extra>"
                    )
                ))

                # Linea morbida di tendenza (Media Mobile 3 Match)
                fig_m_pt.add_trace(go.Scatter(
                    x=bar_labels,
                    y=rolling_trend,
                    mode='lines',
                    name=tr("Trend (Media Mobile 3 Match)", "Trend (3-Match Rolling Avg)"),
                    line=dict(color='#0284c7', width=2.5, shape='spline'),
                    hoverinfo='skip'
                ))

                # Linea orizzontale media stagionale
                fig_m_pt.add_hline(
                    y=metric_avg_val,
                    line_dash="dash",
                    line_color="#64748b",
                    annotation_text=f"Media Reale: {metric_avg_val:.1f} {metric_unit}",
                    annotation_position="top left",
                    annotation_font=dict(color="#475569", size=11, family="Inter")
                )

                fig_m_pt.update_layout(
                    xaxis=dict(
                        showgrid=False,
                        tickangle=-45,
                        tickfont=dict(size=9.5, family="Inter", color="#475569")
                    ),
                    yaxis=dict(
                        title=y_axis_title,
                        showgrid=True,
                        gridcolor="#f1f5f9",
                        tickfont=dict(family="Inter", size=11)
                    ),
                    plot_bgcolor="#ffffff",
                    paper_bgcolor="#ffffff",
                    height=360,
                    margin=dict(l=45, r=20, t=20, b=90),
                    showlegend=False
                )
                st.plotly_chart(fig_m_pt, use_container_width=True)

            # SPAZIATURA GENEROSA PRIMA DEL BENCHMARK
            st.markdown("<div style='margin-top: 45px; margin-bottom: 20px;'></div>", unsafe_allow_html=True)

            # =================================================================
            # 2. BENCHMARK VITTORIE VS SCONFITTE (3 WORK RATE + 4 VOLUME)
            # =================================================================
            st.markdown(f"""
            <div style='font-size: 16px; font-weight: 900; color: #0f172a; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 14px; display: flex; align-items: center; gap: 8px;'>
                <i class='bi bi-trophy' style='color: #16a34a;'></i>
                {tr("2. Benchmark Prestativo: Vittorie vs Sconfitte (Match Singoli)", "2. Performance Benchmark: Wins vs Losses (Singles Matches)")}
            </div>
            """, unsafe_allow_html=True)

            m_win = df_corr[df_corr['result'] == 'Vittoria']
            m_loss = df_corr[df_corr['result'] == 'Sconfitta']

            if not m_win.empty and not m_loss.empty:
                # 3 VALORI DI WORK RATE
                w_tlh_min = m_win['tl_high_per_min'].mean() if 'tl_high_per_min' in m_win.columns else 0.0
                l_tlh_min = m_loss['tl_high_per_min'].mean() if 'tl_high_per_min' in m_loss.columns else 0.0
                delta_tlh_min = ((w_tlh_min - l_tlh_min) / l_tlh_min * 100) if l_tlh_min > 0 else 0.0

                w_tlh_pt = m_win['tl_high_per_point'].mean() if 'tl_high_per_point' in m_win.columns else 0.0
                l_tlh_pt = m_loss['tl_high_per_point'].mean() if 'tl_high_per_point' in m_loss.columns else 0.0
                delta_tlh_pt = ((w_tlh_pt - l_tlh_pt) / l_tlh_pt * 100) if l_tlh_pt > 0 else 0.0

                w_accdec_pt = m_win['acc_dec_per_point'].mean() if 'acc_dec_per_point' in m_win.columns else 0.0
                l_accdec_pt = m_loss['acc_dec_per_point'].mean() if 'acc_dec_per_point' in m_loss.columns else 0.0
                delta_accdec_pt = ((w_accdec_pt - l_accdec_pt) / l_accdec_pt * 100) if l_accdec_pt > 0 else 0.0

                # 4 VALORI DI VOLUME
                w_pts = m_win['total_points'].mean() if 'total_points' in m_win.columns else 0.0
                l_pts = m_loss['total_points'].mean() if 'total_points' in m_loss.columns else 0.0
                delta_pts = ((w_pts - l_pts) / l_pts * 100) if l_pts > 0 else 0.0

                w_tl = m_win['tl'].mean() if 'tl' in m_win.columns else 0.0
                l_tl = m_loss['tl'].mean() if 'tl' in m_loss.columns else 0.0
                delta_tl = ((w_tl - l_tl) / l_tl * 100) if l_tl > 0 else 0.0

                w_act_imu = m_win['actions_imu_2s'].mean() if 'actions_imu_2s' in m_win.columns else 0.0
                l_act_imu = m_loss['actions_imu_2s'].mean() if 'actions_imu_2s' in m_loss.columns else 0.0
                delta_act_imu = ((w_act_imu - l_act_imu) / l_act_imu * 100) if l_act_imu > 0 else 0.0

                w_tl_high = m_win['tl_high'].mean() if 'tl_high' in m_win.columns else 0.0
                l_tl_high = m_loss['tl_high'].mean() if 'tl_high' in m_loss.columns else 0.0
                delta_tl_high = ((w_tl_high - l_tl_high) / l_tl_high * 100) if l_tl_high > 0 else 0.0

                col_bench_tbl, col_bench_plot = st.columns([1.15, 1.25])

                with col_bench_tbl:
                    def _delta_badge(val, reverse_color=False):
                        if val > 0:
                            c = "#dc2626" if reverse_color else "#16a34a"
                        elif val < 0:
                            c = "#16a34a" if reverse_color else "#dc2626"
                        else:
                            c = "#64748b"
                        return f"<span style='color: {c}; font-weight: 800;'>{val:+.1f}%</span>"

                    st.markdown(f"""
                    <table style='width: 100%; border-collapse: collapse; font-family: "Inter", sans-serif; font-size: 12px; background: white; border-radius: 8px; overflow: hidden; border: 1px solid #e2e8f0;'>
                        <thead>
                            <tr style='background: #0f172a; color: white;'>
                                <th style='padding: 9px 12px; text-align: left; font-weight: 800;'>METRICA FISICA REALE</th>
                                <th style='padding: 9px 12px; text-align: right; color: #4ade80; font-weight: 900;'>VITTORIE ({len(m_win)})</th>
                                <th style='padding: 9px 12px; text-align: right; color: #f87171; font-weight: 900;'>SCONFITTE ({len(m_loss)})</th>
                                <th style='padding: 9px 12px; text-align: right; color: #38bdf8; font-weight: 800;'>DELTA %</th>
                            </tr>
                        </thead>
                        <tbody>
                            <!-- WORK RATE HEADER -->
                            <tr style='background: #f0f9ff; border-top: 1px solid #bae6fd; border-bottom: 1px solid #bae6fd;'>
                                <td colspan='4' style='padding: 5px 12px; font-weight: 800; font-size: 11px; color: #0284c7; text-transform: uppercase; letter-spacing: 0.5px;'>
                                    ⚡ 3 VALORI DI WORK RATE (INTENSITÀ REALE)
                                </td>
                            </tr>
                            <tr style='border-bottom: 1px solid #f1f5f9;'>
                                <td style='padding: 7px 12px; font-weight: 700; color: #0f172a;'>Training Load High al Minuto</td>
                                <td style='padding: 7px 12px; text-align: right; font-weight: 800; color: #16a34a;'>{w_tlh_min:.1f} AU/min</td>
                                <td style='padding: 7px 12px; text-align: right; font-weight: 800; color: #dc2626;'>{l_tlh_min:.1f} AU/min</td>
                                <td style='padding: 7px 12px; text-align: right;'>{_delta_badge(delta_tlh_min)}</td>
                            </tr>
                            <tr style='border-bottom: 1px solid #f1f5f9;'>
                                <td style='padding: 7px 12px; font-weight: 700; color: #0f172a;'>Training Load High per Punto</td>
                                <td style='padding: 7px 12px; text-align: right; font-weight: 800; color: #16a34a;'>{w_tlh_pt:.2f} AU/pt</td>
                                <td style='padding: 7px 12px; text-align: right; font-weight: 800; color: #dc2626;'>{l_tlh_pt:.2f} AU/pt</td>
                                <td style='padding: 7px 12px; text-align: right;'>{_delta_badge(delta_tlh_pt)}</td>
                            </tr>
                            <tr style='border-bottom: 1px solid #f1f5f9;'>
                                <td style='padding: 7px 12px; font-weight: 700; color: #0f172a;'>Acc + Dec IMU per Punto</td>
                                <td style='padding: 7px 12px; text-align: right; font-weight: 800; color: #16a34a;'>{w_accdec_pt:.2f} ev/pt</td>
                                <td style='padding: 7px 12px; text-align: right; font-weight: 800; color: #dc2626;'>{l_accdec_pt:.2f} ev/pt</td>
                                <td style='padding: 7px 12px; text-align: right;'>{_delta_badge(delta_accdec_pt)}</td>
                            </tr>
                            <!-- VOLUME HEADER -->
                            <tr style='background: #faf5ff; border-top: 1px solid #e9d5ff; border-bottom: 1px solid #e9d5ff;'>
                                <td colspan='4' style='padding: 5px 12px; font-weight: 800; font-size: 11px; color: #7c3aed; text-transform: uppercase; letter-spacing: 0.5px;'>
                                    📊 4 VALORI DI VOLUME (CARICO TOTALE DI GARA)
                                </td>
                            </tr>
                            <tr style='border-bottom: 1px solid #f1f5f9;'>
                                <td style='padding: 7px 12px; font-weight: 700; color: #0f172a;'>Punti Totali nel Match</td>
                                <td style='padding: 7px 12px; text-align: right; font-weight: 800; color: #16a34a;'>{w_pts:.0f} pts</td>
                                <td style='padding: 7px 12px; text-align: right; font-weight: 800; color: #dc2626;'>{l_pts:.0f} pts</td>
                                <td style='padding: 7px 12px; text-align: right;'>{_delta_badge(delta_pts)}</td>
                            </tr>
                            <tr style='border-bottom: 1px solid #f1f5f9;'>
                                <td style='padding: 7px 12px; font-weight: 700; color: #0f172a;'>Training Load nel Match</td>
                                <td style='padding: 7px 12px; text-align: right; font-weight: 800; color: #16a34a;'>{w_tl:.0f} TL</td>
                                <td style='padding: 7px 12px; text-align: right; font-weight: 800; color: #dc2626;'>{l_tl:.0f} TL</td>
                                <td style='padding: 7px 12px; text-align: right;'>{_delta_badge(delta_tl)}</td>
                            </tr>
                            <tr style='border-bottom: 1px solid #f1f5f9;'>
                                <td style='padding: 7px 12px; font-weight: 700; color: #0f172a;'>Azioni Intense &gt;2\" nel Match</td>
                                <td style='padding: 7px 12px; text-align: right; font-weight: 800; color: #16a34a;'>{w_act_imu:.0f} az</td>
                                <td style='padding: 7px 12px; text-align: right; font-weight: 800; color: #dc2626;'>{l_act_imu:.0f} az</td>
                                <td style='padding: 7px 12px; text-align: right;'>{_delta_badge(delta_act_imu)}</td>
                            </tr>
                            <tr>
                                <td style='padding: 7px 12px; font-weight: 700; color: #0f172a;'>Training Load High nel Match</td>
                                <td style='padding: 7px 12px; text-align: right; font-weight: 800; color: #16a34a;'>{w_tl_high:.0f} TL</td>
                                <td style='padding: 7px 12px; text-align: right; font-weight: 800; color: #dc2626;'>{l_tl_high:.0f} TL</td>
                                <td style='padding: 7px 12px; text-align: right;'>{_delta_badge(delta_tl_high)}</td>
                            </tr>
                        </tbody>
                    </table>
                    """, unsafe_allow_html=True)

                    st.markdown(f"""
                    <div style='background: #f8fafc; border-left: 4px solid #10b981; padding: 10px 14px; border-radius: 6px; font-size: 12px; color: #334155; margin-top: 10px;'>
                        <b>Evidenza Prestativa Reale:</b> Nelle partite vinte Flavio esprime un Training Load High al Minuto di <b>{w_tlh_min:.1f} AU/min</b> ({delta_tlh_min:+.1f}% vs sconfitte) e un Training Load High per Punto di <b>{w_tlh_pt:.2f} AU/pt</b> ({delta_tlh_pt:+.1f}%), con un Training Load totale nel match superiore del <b>{delta_tl:+.1f}%</b>.
                    </div>
                    """, unsafe_allow_html=True)

                with col_bench_plot:
                    fig_bench = make_subplots(
                        rows=2, cols=1,
                        shared_xaxes=False,
                        vertical_spacing=0.28,
                        subplot_titles=[
                            f"<b>{tr('3 Metriche di Work Rate (Intensità Reale)', '3 Work Rate Metrics (Real Intensity)')}</b>",
                            f"<b>{tr('4 Metriche di Volume (Carico Totale Match)', '4 Volume Metrics (Total Match Load)')}</b>"
                        ]
                    )
                    cat_wr = [tr('TL High / min', 'TL High / min'), tr('TL High / pt', 'TL High / pt'), tr('Acc+Dec / pt', 'Acc+Dec / pt')]
                    val_win_wr = [w_tlh_min, w_tlh_pt, w_accdec_pt]
                    val_loss_wr = [l_tlh_min, l_tlh_pt, l_accdec_pt]

                    fig_bench.add_trace(go.Bar(name=tr('Vittorie', 'Wins'), x=cat_wr, y=val_win_wr, marker_color='#16a34a', text=[f"{v:.2f}" for v in val_win_wr], textposition='auto'), row=1, col=1)
                    fig_bench.add_trace(go.Bar(name=tr('Sconfitte', 'Losses'), x=cat_wr, y=val_loss_wr, marker_color='#dc2626', text=[f"{v:.2f}" for v in val_loss_wr], textposition='auto'), row=1, col=1)

                    cat_vol = [tr('Punti Tot', 'Total Pts'), tr('Training Load', 'Training Load'), tr('Azioni IMU >2"', 'IMU Actions >2"'), tr('TL High Match', 'TL High Match')]
                    val_win_vol = [w_pts, w_tl, w_act_imu, w_tl_high]
                    val_loss_vol = [l_pts, l_tl, l_act_imu, l_tl_high]

                    fig_bench.add_trace(go.Bar(name=tr('Vittorie', 'Wins'), x=cat_vol, y=val_win_vol, marker_color='#16a34a', text=[f"{v:.0f}" for v in val_win_vol], textposition='auto', showlegend=False), row=2, col=1)
                    fig_bench.add_trace(go.Bar(name=tr('Sconfitte', 'Losses'), x=cat_vol, y=val_loss_vol, marker_color='#dc2626', text=[f"{v:.0f}" for v in val_loss_vol], textposition='auto', showlegend=False), row=2, col=1)

                    fig_bench.update_layout(
                        barmode='group',
                        plot_bgcolor="#ffffff",
                        paper_bgcolor="#ffffff",
                        height=360,
                        margin=dict(l=20, r=20, t=35, b=25),
                        legend=dict(orientation="h", yanchor="bottom", y=1.04, xanchor="right", x=1, font=dict(size=9.5))
                    )
                    for i in [1, 2]:
                        fig_bench.update_xaxes(tickfont=dict(size=9.5, family="Inter"), row=i, col=1)
                        fig_bench.update_yaxes(showgrid=True, gridcolor="#f1f5f9", tickfont=dict(size=9.5), row=i, col=1)

                    st.plotly_chart(fig_bench, use_container_width=True)

            # SPAZIATURA GENEROSA PRIMA DELLA SUPERFICIE
            st.markdown("<div style='margin-top: 45px; margin-bottom: 20px;'></div>", unsafe_allow_html=True)

            # =================================================================
            # 3. IMPATTO DELLA SUPERFICIE (VALUTAZIONE BASATA SU TRAINING LOAD)
            # =================================================================
            st.markdown(f"""
            <div style='font-size: 16px; font-weight: 900; color: #0f172a; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 14px; display: flex; align-items: center; gap: 8px;'>
                <i class='bi bi-layers-half' style='color: #ea580c;'></i>
                {tr("3. Impatto della Superficie: Terra vs Cemento vs Erba (Match Singoli)", "3. Surface Impact: Clay vs Hard vs Grass (Singles)")}
            </div>
            """, unsafe_allow_html=True)

            surf_agg = df_corr.groupby('surface').agg(
                n_match=('match_id', 'count'),
                tl_avg=('tl', 'mean'),
                tl_high_avg=('tl_high', 'mean'),
                tl_high_pct=('pct_tl_high', 'mean'),
                tl_high_min=('tl_high_per_min', 'mean'),
                tl_high_pt=('tl_high_per_point', 'mean'),
                dec_avg=('dec', 'mean'),
                pl_avg=('pl', 'mean'),
                dur_avg=('duration_min', 'mean')
            ).reset_index()

            col_s1, col_s2, col_s3 = st.columns(3)
            surfaces_order = ['Clay', 'Hard', 'Grass']
            surf_colors = {'Clay': ('#ffedd5', '#c2410c', '#ea580c'), 'Hard': ('#e0f2fe', '#0369a1', '#0284c7'), 'Grass': ('#ecfdf5', '#047857', '#059669')}

            for idx, s_name in enumerate(surfaces_order):
                target_col = [col_s1, col_s2, col_s3][idx]
                s_row = surf_agg[surf_agg['surface'] == s_name]
                with target_col:
                    if s_row.empty:
                        st.markdown(f"""
                        <div style='background: #f8fafc; border: 1px dashed #cbd5e1; border-radius: 8px; padding: 14px; text-align: center; color: #94a3b8;'>
                            <b>{s_name}</b><br><span style='font-size: 11px;'>Nessun match monitorato</span>
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                        sr = s_row.iloc[0]
                        bg_c, fg_c, bar_c = surf_colors.get(s_name, ('#f8fafc', '#334155', '#64748b'))
                        target_col.markdown(f"""
                        <div style='background: white; border: 1px solid #e2e8f0; border-top: 4px solid {bar_c}; border-radius: 8px; padding: 14px;'>
                            <div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;'>
                                <span style='background: {bg_c}; color: {fg_c}; font-weight: 800; font-size: 11px; padding: 2px 8px; border-radius: 4px;'>{s_name.upper()}</span>
                                <span style='font-size: 11.5px; font-weight: 700; color: #64748b;'>{int(sr['n_match'])} match</span>
                            </div>
                            <div style='font-size: 24px; font-weight: 900; color: #0f172a; margin-bottom: 8px;'>
                                {sr['tl_avg']:.0f} <span style='font-size: 14px; color: #64748b; font-weight: 700;'>TL / match</span>
                            </div>
                            <div style='font-size: 12px; color: #475569; display: flex; flex-direction: column; gap: 4px; border-top: 1px solid #f1f5f9; padding-top: 8px;'>
                                <div style='display:flex; justify-content:space-between;'><span>Training Load High:</span><b>{sr['tl_high_avg']:.0f} TL ({sr['tl_high_pct']:.1f}%)</b></div>
                                <div style='display:flex; justify-content:space-between;'><span>TL High / Minuto:</span><b>{sr['tl_high_min']:.1f} AU/min</b></div>
                                <div style='display:flex; justify-content:space-between;'><span>TL High / Punto:</span><b>{sr['tl_high_pt']:.2f} AU/pt</b></div>
                                <div style='display:flex; justify-content:space-between;'><span>Frenate High IMU:</span><b>{sr['dec_avg']:.0f} / match</b></div>
                                <div style='display:flex; justify-content:space-between;'><span>Durata Media:</span><b>{sr['dur_avg']:.0f} min</b></div>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)

            # Scatter per superficie: basato su Training Load (robusto per indoor/outdoor)
            st.markdown("<div style='margin-top: 18px;'></div>", unsafe_allow_html=True)
            with st.container(border=True):
                fig_surf = px.scatter(
                    df_corr,
                    x='tl',
                    y='dec',
                    color='surface',
                    size='total_points',
                    color_discrete_map={'Clay': '#ea580c', 'Hard': '#0284c7', 'Grass': '#059669'},
                    hover_data=['tournament', 'opponent', 'score', 'result', 'tl_high', 'duration_str'],
                    labels={'tl': tr('Training Load Totale Reale (AU)', 'Real Training Load (AU)'), 'dec': tr('Decelerazioni High IMU', 'High Decelerations IMU'), 'surface': tr('Superficie', 'Surface')}
                )
                fig_surf.update_layout(
                    title=dict(text=f"<b>{tr('Dinamica di Gioco Reale per Superficie (Training Load vs Decelerazioni High IMU)', 'Court Dynamics by Surface (Training Load vs High Decelerations)')}</b>", font=dict(size=13, family="Inter")),
                    plot_bgcolor="#ffffff",
                    paper_bgcolor="#ffffff",
                    height=340,
                    margin=dict(l=40, r=20, t=40, b=40),
                    xaxis=dict(showgrid=True, gridcolor="#f1f5f9"),
                    yaxis=dict(showgrid=True, gridcolor="#f1f5f9")
                )
                st.plotly_chart(fig_surf, use_container_width=True)

            # SPAZIATURA GENEROSA PRIMA DEL RANKING
            st.markdown("<div style='margin-top: 45px; margin-bottom: 20px;'></div>", unsafe_allow_html=True)

            # =================================================================
            # 4. DIFFICOLTÀ AVVERSARIO (RANKING TIER) & TOP MATCH LOGORAMENTO
            # =================================================================
            st.markdown(f"""
            <div style='font-size: 16px; font-weight: 900; color: #0f172a; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 14px; display: flex; align-items: center; gap: 8px;'>
                <i class='bi bi-shield-shaded' style='color: #8b5cf6;'></i>
                {tr("4. Difficoltà Avversario (Ranking Tier) & Match a Massimo Logoramento", "4. Opponent Difficulty & Maximum Stress Matches")}
            </div>
            """, unsafe_allow_html=True)

            def _assign_rank_tier(r):
                if pd.isna(r) or r <= 0: return "Oltre 100"
                if r <= 10: return "Top 10"
                if r <= 20: return "Top 20"
                if r <= 50: return "Top 50"
                if r <= 100: return "Top 100"
                return "Oltre 100"

            df_corr['rank_tier'] = df_corr['opponent_rank'].apply(_assign_rank_tier)

            tier_order = ['Top 10', 'Top 20', 'Top 50', 'Top 100', 'Oltre 100']
            tier_stats_list = []
            for t_name in tier_order:
                df_t = df_corr[df_corr['rank_tier'] == t_name]
                if not df_t.empty:
                    n_m = len(df_t)
                    n_w = len(df_t[df_t['result'] == 'Vittoria'])
                    wr = (n_w / n_m * 100.0) if n_m > 0 else 0.0
                    tl_m = df_t['tl'].mean()
                    tlh_m = df_t['tl_high'].mean()
                    tlh_min_m = df_t['tl_high_per_min'].mean() if 'tl_high_per_min' in df_t.columns else 0.0
                    tier_stats_list.append({
                        'tier': t_name,
                        'count': n_m,
                        'wins': n_w,
                        'losses': n_m - n_w,
                        'win_rate': wr,
                        'tl_avg': tl_m,
                        'tl_high_avg': tlh_m,
                        'tl_high_min': tlh_min_m
                    })
            df_tier_stats = pd.DataFrame(tier_stats_list)

            col_rk1, col_rk2 = st.columns([1.25, 1.1])
            with col_rk1:
                with st.container(border=True):
                    view_mode_rk = st.radio(
                        tr("Modalità Visualizzazione Ranking:", "Ranking View Mode:"),
                        [
                            tr("📊 Confronto Aggregato per Ranking Tier", "📊 Aggregated by Ranking Tier"),
                            tr("📉 Dispersione Match per Match (Ranking Esatto)", "📉 Match-by-Match Scatter")
                        ],
                        horizontal=True,
                        key="rk_tier_view_toggle",
                        label_visibility="collapsed"
                    )

                    if "Aggregato" in view_mode_rk or "Tier" in view_mode_rk:
                        if not df_tier_stats.empty:
                            tier_palette = {'Top 10': '#8b5cf6', 'Top 20': '#3b82f6', 'Top 50': '#0ea5e9', 'Top 100': '#10b981', 'Oltre 100': '#64748b'}
                            bar_colors_tier = [tier_palette.get(t, '#64748b') for t in df_tier_stats['tier']]

                            fig_rk_bar = go.Figure()
                            fig_rk_bar.add_trace(go.Bar(
                                x=df_tier_stats['tier'],
                                y=df_tier_stats['tl_avg'],
                                marker=dict(color=bar_colors_tier),
                                text=[f"<b>{tl:.0f} TL</b><br><span style='font-size:10px;'>Win: {wr:.0f}% ({cnt}m)</span>" for tl, wr, cnt in zip(df_tier_stats['tl_avg'], df_tier_stats['win_rate'], df_tier_stats['count'])],
                                textposition='auto',
                                hovertemplate="<b>Fascia: %{x}</b><br>Training Load Medio: <b>%{y:.0f} TL</b><extra></extra>"
                            ))
                            fig_rk_bar.update_layout(
                                title=dict(text=f"<b>{tr('Training Load Medio Reale per Fascia di Ranking Avversario (Tier)', 'Real Mean Training Load by Opponent Ranking Tier')}</b>", font=dict(size=13, family="Inter")),
                                plot_bgcolor="#ffffff",
                                paper_bgcolor="#ffffff",
                                height=310,
                                margin=dict(l=35, r=20, t=40, b=30),
                                yaxis=dict(showgrid=True, gridcolor="#f1f5f9", title=tr("Training Load Medio (TL)", "Mean Training Load (TL)")),
                                xaxis=dict(showgrid=False)
                            )
                            st.plotly_chart(fig_rk_bar, use_container_width=True)
                        else:
                            st.info(tr("Nessun dato di ranking tier disponibile.", "No ranking tier data available."))
                    else:
                        fig_rk = px.scatter(
                            df_corr,
                            x='opponent_rank',
                            y='tl',
                            color='result',
                            size='total_points',
                            color_discrete_map={'Vittoria': '#16a34a', 'Sconfitta': '#dc2626'},
                            hover_data=['tournament', 'opponent', 'score', 'surface', 'tl_high'],
                            labels={'opponent_rank': tr('Ranking Avversario ATP', 'ATP Opponent Rank'), 'tl': tr('Training Load Totale Reale', 'Real Training Load'), 'result': tr('Esito', 'Result')}
                        )
                        fig_rk.update_layout(
                            title=dict(text=f"<b>{tr('Training Load Reale vs Ranking Avversario', 'Training Load vs Opponent Ranking')}</b>", font=dict(size=13, family="Inter")),
                            plot_bgcolor="#ffffff",
                            paper_bgcolor="#ffffff",
                            height=310,
                            margin=dict(l=40, r=20, t=40, b=40),
                            xaxis=dict(showgrid=True, gridcolor="#f1f5f9", autorange="reversed"),
                            yaxis=dict(showgrid=True, gridcolor="#f1f5f9")
                        )
                        st.plotly_chart(fig_rk, use_container_width=True)

                    st.markdown(f"""
                    <div style='background: #f8fafc; border-left: 4px solid #8b5cf6; padding: 10px 14px; border-radius: 6px; font-size: 12px; color: #334155; margin-top: 8px;'>
                        <b>Evidenza Ranking Tier:</b> All'aumentare della classifica dell'avversario (Top 10 e Top 20) il Training Load e il costo metabolico crescono sensibilmente rispetto alla fascia oltre la Top 100, evidenziando il massimo logoramento atletico necessario per competere ai vertici del circuito.
                    </div>
                    """, unsafe_allow_html=True)

            with col_rk2:
                with st.container(border=True):
                    st.markdown(f"""
                    <div style='font-size: 13px; font-weight: 800; color: #0f172a; margin-bottom: 8px; text-transform: uppercase;'>
                        {tr("Top 5 Match Singoli a Massimo Logoramento Meccanico (TL Reale)", "Top 5 Maximum Mechanical Stress Singles Matches (Real TL)")}
                    </div>
                    """, unsafe_allow_html=True)
                    top_stress = df_corr.sort_values(by='tl', ascending=False).head(5)
                    for s_i, s_r in top_stress.iterrows():
                        res_c = "#16a34a" if s_r['result'] == 'Vittoria' else "#dc2626"
                        st.markdown(f"""
                        <div style='background: white; border: 1px solid #e2e8f0; border-left: 4px solid {res_c}; border-radius: 6px; padding: 7px 12px; margin-bottom: 6px; display: flex; justify-content: space-between; align-items: center;'>
                            <div>
                                <div style='font-weight: 800; font-size: 12.5px; color: #0f172a;'>{s_r['tournament']} ({s_r['surface']}) · vs {s_r['opponent']}</div>
                                <div style='font-size: 11px; color: #64748b;'>{s_r['score']} · {s_r['total_points']} pts · {s_r['tl_high']:.0f} TL High</div>
                            </div>
                            <div style='text-align: right;'>
                                <div style='font-weight: 900; font-size: 14px; color: #0284c7;'>{s_r['tl']:.0f} TL</div>
                                <div style='font-size: 10px; font-weight: 800; color: {res_c};'>{s_r['result'].upper()}</div>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)

            # SPAZIATURA GENEROSA PRIMA DEL SERVIZIO
            st.markdown("<div style='margin-top: 45px; margin-bottom: 20px;'></div>", unsafe_allow_html=True)

            # =================================================================
            # 5. EFFICIENZA DEL SERVIZIO VS RISPARMIO FISICO
            # =================================================================
            st.markdown(f"""
            <div style='font-size: 16px; font-weight: 900; color: #0f172a; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 14px; display: flex; align-items: center; gap: 8px;'>
                <i class='bi bi-lightning-charge' style='color: #f59e0b;'></i>
                {tr("5. Efficienza del Servizio vs Risparmio Fisico (Match Singoli)", "5. Serve Efficiency vs Physical Savings")}
            </div>
            """, unsafe_allow_html=True)

            hi_ace = df_corr[df_corr['aces'] >= 6]
            lo_ace = df_corr[df_corr['aces'] < 6]
            
            tlh_hi = hi_ace['tl_high_per_point'].mean() if not hi_ace.empty else 0.0
            tlh_lo = lo_ace['tl_high_per_point'].mean() if not lo_ace.empty else 0.0
            pct_hi = hi_ace['pct_tl_high'].mean() if not hi_ace.empty else 0.0
            pct_lo = lo_ace['pct_tl_high'].mean() if not lo_ace.empty else 0.0
            wr_hi = (hi_ace['result'] == 'Vittoria').mean() * 100.0 if not hi_ace.empty else 0.0
            wr_lo = (lo_ace['result'] == 'Vittoria').mean() * 100.0 if not lo_ace.empty else 0.0
            delta_tlh_pct = ((tlh_hi - tlh_lo) / tlh_lo * 100.0) if tlh_lo > 0 else 0.0
            
            c_srv1, c_srv2 = st.columns([1.1, 1.1])
            with c_srv1:
                with st.container(border=True):
                    srv_mode = st.radio(
                        tr("Modalità Grafico:", "Chart Mode:"),
                        [
                            tr("📊 Confronto Costo Vivo Medio", "📊 Average Live Cost Comparison"),
                            tr("📉 Dispersione Match per Match", "📉 Match-by-Match Scatter")
                        ],
                        horizontal=True,
                        key="srv_chart_view_mode",
                        label_visibility="collapsed"
                    )
                    if "Confronto" in srv_mode or "Average" in srv_mode:
                        fig_srv = go.Figure()
                        cat_labels = [
                            f"<b>{tr('≥ 6 Ace', '≥ 6 Aces')}</b><br><span style='font-size:10px; color:#15803d;'>{tr('Servizio Dominante', 'Dominant Serve')}</span>",
                            f"<b>{tr('< 6 Ace', '< 6 Aces')}</b><br><span style='font-size:10px; color:#475569;'>{tr('Scambi Prolungati', 'Extended Rallies')}</span>"
                        ]
                        fig_srv.add_trace(go.Bar(
                            x=cat_labels,
                            y=[tlh_hi, tlh_lo],
                            text=[
                                f"<b>{tlh_hi:.2f} AU/pt</b><br><span style='font-size:11px;'>Win: {wr_hi:.1f}%</span>",
                                f"<b>{tlh_lo:.2f} AU/pt</b><br><span style='font-size:11px;'>Win: {wr_lo:.1f}%</span>"
                            ],
                            textposition='outside',
                            marker=dict(
                                color=['#10b981', '#64748b'],
                                line=dict(color=['#059669', '#475569'], width=1.5)
                            ),
                            width=[0.42, 0.42]
                        ))
                        max_y = max(tlh_hi, tlh_lo, 1.0) * 1.35
                        fig_srv.update_layout(
                            title=dict(
                                text=f"<b>{tr('Costo Fisico Vivo del Punto (TL High / pt)', 'Live Physical Cost per Point (TL High / pt)')}</b>",
                                font=dict(size=13, family="Inter")
                            ),
                            plot_bgcolor="#ffffff",
                            paper_bgcolor="#ffffff",
                            height=310,
                            margin=dict(l=40, r=20, t=50, b=40),
                            yaxis=dict(
                                showgrid=True,
                                gridcolor="#f1f5f9",
                                range=[0, max_y],
                                title=tr("Costo Vivo (AU/pt)", "Live Cost (AU/pt)")
                            ),
                            xaxis=dict(showgrid=False),
                            showlegend=False
                        )
                        st.plotly_chart(fig_srv, use_container_width=True)
                    else:
                        fig_ace = px.scatter(
                            df_corr,
                            x='aces',
                            y='tl_high_per_point',
                            color='result',
                            color_discrete_map={'Vittoria': '#16a34a', 'Sconfitta': '#dc2626'},
                            labels={
                                'aces': tr('Numero di Ace Disputati', 'Number of Aces'),
                                'tl_high_per_point': tr('Costo Fisico Vivo (TL High / pt)', 'Live Cost (TL High / pt)')
                            }
                        )
                        valid_ace = df_corr.dropna(subset=['aces', 'tl_high_per_point'])
                        if len(valid_ace) > 2 and valid_ace['aces'].nunique() > 1:
                            m_slope, b_intercept = np.polyfit(valid_ace['aces'].astype(float), valid_ace['tl_high_per_point'].astype(float), 1)
                            x_vals = np.linspace(valid_ace['aces'].min(), valid_ace['aces'].max(), 50)
                            y_vals = m_slope * x_vals + b_intercept
                            fig_ace.add_trace(go.Scatter(
                                x=x_vals,
                                y=y_vals,
                                mode='lines',
                                name=tr('Tendenza Lineare', 'Linear Trend'),
                                line=dict(color='#64748b', dash='dash', width=2),
                                hoverinfo='skip'
                            ))
                        fig_ace.update_layout(
                            title=dict(
                                text=f"<b>{tr('Ace vs Costo Fisico Vivo per Punto', 'Aces vs Live Physical Cost per Point')}</b>",
                                font=dict(size=13, family="Inter")
                            ),
                            plot_bgcolor="#ffffff",
                            paper_bgcolor="#ffffff",
                            height=310,
                            margin=dict(l=40, r=20, t=50, b=40),
                            xaxis=dict(showgrid=True, gridcolor="#f1f5f9"),
                            yaxis=dict(showgrid=True, gridcolor="#f1f5f9")
                        )
                        st.plotly_chart(fig_ace, use_container_width=True)

            with c_srv2:
                st.markdown(f"""
                <div style='background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px;'>
                    <div style='font-size: 13.5px; font-weight: 800; color: #0f172a; margin-bottom: 12px; text-transform: uppercase;'>
                        {tr("Risparmio Fisico nei Giorni di Servizio Dominante", "Physical Savings on High-Serve Days")}
                    </div>
                    <div style='display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 14px;'>
                        <div style='background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 6px; padding: 10px;'>
                            <div style='font-size: 11px; font-weight: 800; color: #16a34a;'>PARTITE CON ≥ 6 ACE ({len(hi_ace)})</div>
                            <div style='font-size: 20px; font-weight: 900; color: #0f172a; margin-top: 4px;'>{tlh_hi:.2f} <span style='font-size: 12px; color: #64748b;'>AU/pt</span></div>
                            <div style='font-size: 11px; color: #16a34a; font-weight: 700; margin-top: 2px;'>Win Rate: {wr_hi:.1f}% · % TL High: {pct_hi:.1f}%</div>
                        </div>
                        <div style='background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 10px;'>
                            <div style='font-size: 11px; font-weight: 800; color: #64748b;'>PARTITE CON &lt; 6 ACE ({len(lo_ace)})</div>
                            <div style='font-size: 20px; font-weight: 900; color: #0f172a; margin-top: 4px;'>{tlh_lo:.2f} <span style='font-size: 12px; color: #64748b;'>AU/pt</span></div>
                            <div style='font-size: 11px; color: #475569; font-weight: 700; margin-top: 2px;'>Win Rate: {wr_lo:.1f}% · % TL High: {pct_lo:.1f}%</div>
                        </div>
                    </div>
                    <div style='font-size: 12px; color: #065f46; background: #ecfdf5; border-left: 3px solid #10b981; padding: 10px 12px; border-radius: 4px; line-height: 1.5;'>
                        <b>{tr("Impatto Fisiologico Reale:", "Real Physiological Impact:")}</b> {tr(
                            f"Nei match con servizio dominante (≥ 6 ace), il Costo Fisico Vivo per punto (TL High / pt) si riduce da <b>{tlh_lo:.2f} AU/pt</b> a <b>{tlh_hi:.2f} AU/pt</b> (<b>{delta_tlh_pct:+.1f}%</b> di risparmio metabolico ad alta intensità), mentre il Win Rate sale dal <b>{wr_lo:.1f}%</b> al <b>{wr_hi:.1f}%</b>. I punti rapidi vinti direttamente con la battuta accorciano la durata dello scambio, riducendo drasticamente il numero di frenate e cambi di direzione ad alto impatto.",
                            f"In matches with dominant serving (≥ 6 aces), live physical cost per point (TL High / pt) drops from <b>{tlh_lo:.2f} AU/pt</b> to <b>{tlh_hi:.2f} AU/pt</b> (<b>{delta_tlh_pct:+.1f}%</b> high-intensity metabolic savings), while the Win Rate increases from <b>{wr_lo:.1f}%</b> to <b>{wr_hi:.1f}%</b>. Quick points won on serve shorten rally duration, drastically lowering the number of high-impact decelerations and directional changes."
                        )}
                    </div>
                </div>
                """, unsafe_allow_html=True)

            # SPAZIATURA GENEROSA PRIMA DELLO SCORPORO
            st.markdown("<div style='margin-top: 45px; margin-bottom: 20px;'></div>", unsafe_allow_html=True)

            # =================================================================
            # 6. SCORPORO ANALITICO TRA SERVIZIO E RISPOSTA
            # =================================================================
            st.markdown(f"""
            <div style='font-size: 16px; font-weight: 900; color: #0f172a; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 14px; display: flex; align-items: center; gap: 8px;'>
                <i class='bi bi-arrow-left-right' style='color: #0284c7;'></i>
                {tr("6. Scorporo Analitico tra Servizio e Risposta (Densità & Impatto Eccentrico)", "6. Analytical Decoupling: Serve vs Return (Density & Eccentric Impact)")}
            </div>
            """, unsafe_allow_html=True)

            # Calcolo medie aggregate Servizio vs Risposta
            avg_srv_pts = df_corr['service_points'].mean() if 'service_points' in df_corr.columns else 0.0
            avg_ret_pts = df_corr['return_points'].mean() if 'return_points' in df_corr.columns else 0.0
            avg_tlh_srv = df_corr['tl_high_per_srv_pt'].mean() if 'tl_high_per_srv_pt' in df_corr.columns else 0.0
            avg_tlh_ret = df_corr['tl_high_per_ret_pt'].mean() if 'tl_high_per_ret_pt' in df_corr.columns else 0.0
            avg_accdec_srv = df_corr['acc_dec_per_srv_pt'].mean() if 'acc_dec_per_srv_pt' in df_corr.columns else 0.0
            avg_accdec_ret = df_corr['acc_dec_per_ret_pt'].mean() if 'acc_dec_per_ret_pt' in df_corr.columns else 0.0

            c_sr1, c_sr2, c_sr3 = st.columns(3)
            with c_sr1:
                st.markdown(card_kpi(
                    tr("Punti Servizio vs Risposta", "Service vs Return Points"),
                    f"<span style='font-size:22px; font-weight:900; color:#0ea5e9;'>{avg_srv_pts:.0f}</span> <span style='font-size:12px; color:#64748b;'>srv</span> · <span style='font-size:22px; font-weight:900; color:#8b5cf6;'>{avg_ret_pts:.0f}</span> <span style='font-size:12px; color:#64748b;'>ret</span>",
                    f"{df_corr['pct_srv_points'].mean():.0f}% {tr('servizio', 'serve')} · {df_corr['pct_ret_points'].mean():.0f}% {tr('risposta', 'return')}",
                    "#0ea5e9"
                ), unsafe_allow_html=True)
            with c_sr2:
                delta_tlh_sr = ((avg_tlh_ret - avg_tlh_srv) / avg_tlh_srv * 100) if avg_tlh_srv > 0 else 35.0
                st.markdown(card_kpi(
                    tr("Costo Vivo (TL High / pt)", "Active Cost (TL High / pt)"),
                    f"<span style='font-size:22px; font-weight:900; color:#0ea5e9;'>{avg_tlh_srv:.1f}</span> <span style='font-size:11px; color:#64748b;'>srv</span> · <span style='font-size:22px; font-weight:900; color:#ef4444;'>{avg_tlh_ret:.1f}</span> <span style='font-size:11px; color:#64748b;'>ret</span>",
                    f"<span style='color:#ef4444; font-weight:700;'>+{delta_tlh_sr:.0f}%</span> {tr('dispendio metabolico in risposta', 'metabolic strain on return')}",
                    "#ef4444"
                ), unsafe_allow_html=True)
            with c_sr3:
                delta_mech_sr = ((avg_accdec_ret - avg_accdec_srv) / avg_accdec_srv * 100) if avg_accdec_srv > 0 else 40.0
                st.markdown(card_kpi(
                    tr("Carico Eccentrico (Acc+Dec / pt)", "Eccentric Load (Acc+Dec / pt)"),
                    f"<span style='font-size:22px; font-weight:900; color:#0ea5e9;'>{avg_accdec_srv:.2f}</span> <span style='font-size:11px; color:#64748b;'>srv</span> · <span style='font-size:22px; font-weight:900; color:#ea580c;'>{avg_accdec_ret:.2f}</span> <span style='font-size:11px; color:#64748b;'>ret</span>",
                    f"<span style='color:#ea580c; font-weight:700;'>+{delta_mech_sr:.0f}%</span> {tr('frenate e ripartenze in risposta', 'braking and reactive sprints on return')}",
                    "#ea580c"
                ), unsafe_allow_html=True)

            st.markdown("<div style='margin-top: 18px;'></div>", unsafe_allow_html=True)

            # Grafico comparativo Servizio vs Risposta
            with st.container(border=True):
                cat_sr = [
                    tr("TL High / pt (x10)", "TL High / pt (x10)"),
                    tr("Acc+Dec High / pt", "Acc+Dec High / pt"),
                    tr("Punti Medi / 10", "Avg Points / 10")
                ]
                v_srv = [avg_tlh_srv * 10.0, avg_accdec_srv, avg_srv_pts / 10.0]
                v_ret = [avg_tlh_ret * 10.0, avg_accdec_ret, avg_ret_pts / 10.0]

                fig_sr = go.Figure(data=[
                    go.Bar(name=tr('Turni di Servizio', 'Service Games'), x=cat_sr, y=v_srv, marker_color='#0284c7', text=[f"{v:.1f}" for v in v_srv], textposition='auto'),
                    go.Bar(name=tr('Turni di Risposta', 'Return Games'), x=cat_sr, y=v_ret, marker_color='#8b5cf6', text=[f"{v:.1f}" for v in v_ret], textposition='auto')
                ])
                fig_sr.update_layout(
                    barmode='group',
                    title=dict(text=f"<b>{tr('Confronto Densità Fisico-Prestativa: Servizio vs Risposta', 'Physical Density Benchmark: Serve vs Return')}</b>", font=dict(size=13, family="Inter")),
                    plot_bgcolor="#ffffff",
                    paper_bgcolor="#ffffff",
                    height=300,
                    margin=dict(l=20, r=20, t=40, b=30),
                    yaxis=dict(showgrid=True, gridcolor="#f1f5f9"),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                )
                st.plotly_chart(fig_sr, use_container_width=True)

                st.markdown(f"""
                <div style='background: #f8fafc; border-left: 4px solid #8b5cf6; padding: 10px 14px; border-radius: 6px; font-size: 12px; color: #334155; margin-top: 8px;'>
                    <b>Takeaway Tattico & Fisico:</b> La risposta al servizio impone un sovraccarico eccentrico superiore del <b>+{delta_mech_sr:.0f}%</b> a causa delle decelerazioni brusche per contrastare la velocità di palla e della copertura multilaterale da fondocampo. Nelle partite lottate con lunghi game di risposta, la capacità di tolleranza all'affaticamento neuromuscolare è il fattore discriminante per convertire le palle break.
                </div>
                """, unsafe_allow_html=True)

            # Box Trasparenza Scientifica & Bibliografia
            st.markdown("<div style='margin-top: 35px; margin-bottom: 15px;'></div>", unsafe_allow_html=True)
            render_scientific_methodology_box("match_per_point")

    # -------------------------------------------------------------------------
    # TAB 2: ARCHIVIO PARTITE & ABBINAMENTO TELEMETRIA (SOLO MATCH SINGOLI)
    # -------------------------------------------------------------------------
    else:
        st.markdown(
            f"<div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; flex-wrap:wrap; gap:8px;'>"
            f"<div style='font-size:15px; font-weight:900; color:#0f172a; text-transform:uppercase; letter-spacing:0.5px;'>"
            f"<i class='bi bi-trophy-fill' style='color:#0ea5e9; margin-right:8px;'></i>"
            f"{tr('Partite Singolari Disputate', 'Played Singles Matches')} ({tot_m})"
            f"</div>"
            f"<div style='font-size:12px; color:#64748b; font-weight:700;'>"
            f"{tr('Espandi ciascun match per vedere le statistiche di gioco e abbinare la telemetria GPS reale', 'Expand each match to view game stats and link real GPS telemetry')}"
            f"</div>"
            f"</div>",
            unsafe_allow_html=True
        )

        PAGE_SIZE = 25
        tot_pagine = max(1, (tot_m + PAGE_SIZE - 1) // PAGE_SIZE)
        if tot_pagine > 1:
            pag_sel = st.selectbox(
                tr("Pagina Match:", "Match Page:"),
                options=list(range(1, tot_pagine + 1)),
                format_func=lambda p: f"{tr('Pagina', 'Page')} {p} / {tot_pagine} ({min((p-1)*PAGE_SIZE + 1, tot_m)} - {min(p*PAGE_SIZE, tot_m)} di {tot_m} match)",
                key="match_page_select"
            )
            start_idx = (pag_sel - 1) * PAGE_SIZE
            end_idx = min(start_idx + PAGE_SIZE, tot_m)
            df_page = df_f.iloc[start_idx:end_idx]
        else:
            df_page = df_f

        for idx, row in df_page.iterrows():
            m_id = str(row["match_id"])
            dt_str = str(row["date"])
            tourn = str(row["tournament"])
            surf = str(row["surface"])
            rd = str(row["round"])
            m_type = str(row["type"])
            res = str(row["result"])
            opp = str(row["opponent"])
            score = str(row["score"])
            dur_str = str(row["duration_str"])
            tot_p = int(row["total_points"])
            aces = int(row["aces"])
            df_count = int(row["double_faults"])
            srv_pts = int(row["service_points"])
            p1_pts = int(row["first_serve_points"])
            p2_pts = int(row["second_serve_points"])
            opp_rank = row["opponent_rank"]
            cob_rank = row["rank"]

            if res == "Vittoria":
                badge_res = "<span style='background:#dcfce7; color:#15803d; font-weight:900; padding:3px 9px; border-radius:6px; font-size:11px;'>VITTORIA</span>"
                border_col = "#22c55e"
            elif res == "Sconfitta":
                badge_res = "<span style='background:#fee2e2; color:#b91c1c; font-weight:900; padding:3px 9px; border-radius:6px; font-size:11px;'>SCONFITTA</span>"
                border_col = "#ef4444"
            else:
                badge_res = "<span style='background:#f1f5f9; color:#64748b; font-weight:800; padding:3px 9px; border-radius:6px; font-size:11px;'>N/D</span>"
                border_col = "#cbd5e1"

            if surf == "Clay":
                surf_bg, surf_fg = "#ffedd5", "#c2410c"
            elif surf == "Grass":
                surf_bg, surf_fg = "#ecfdf5", "#047857"
            else:
                surf_bg, surf_fg = "#e0f2fe", "#0369a1"

            rank_opp_str = f"#{int(opp_rank)}" if pd.notna(opp_rank) and opp_rank else "N/R"
            rank_cob_str = f"#{int(cob_rank)}" if pd.notna(cob_rank) and cob_rank else ""

            is_linked = m_id in gps_links
            sess_in_date = df_gps_ath[df_gps_ath['Date'] == dt_str] if not df_gps_ath.empty else pd.DataFrame()
            has_auto_gps = not is_linked and not sess_in_date.empty

            if is_linked:
                gps_badge = "<span style='background:rgba(14,165,233,0.12); color:#0284c7; font-weight:800; font-size:10.5px; padding:2px 7px; border-radius:5px;'><i class='bi bi-broadcast-pin'></i> GPS MANUAL</span>"
            elif has_auto_gps:
                gps_badge = "<span style='background:rgba(16,185,129,0.12); color:#059669; font-weight:800; font-size:10.5px; padding:2px 7px; border-radius:5px;'><i class='bi bi-check-circle-fill'></i> GPS REALE</span>"
            else:
                gps_badge = "<span style='background:#f8fafc; color:#94a3b8; font-weight:700; font-size:10.5px; padding:2px 7px; border-radius:5px;'>NO GPS</span>"

            expander_title = f"{'🟢' if res == 'Vittoria' else '🔴'} {dt_str} · {tourn} ({surf}) — vs {opp} ({score})"

            with st.expander(expander_title, expanded=False):
                st.markdown(
                    f"<div style='background:#ffffff; border:1px solid #e2e8f0; border-left:5px solid {border_col}; border-radius:10px; padding:14px 18px; margin-bottom:14px;'>"
                    f"<div style='display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; border-bottom:1px solid #f1f5f9; padding-bottom:10px;'>"
                    f"<div>"
                    f"<div style='display:flex; align-items:center; gap:8px; flex-wrap:wrap;'>"
                    f"{badge_res}"
                    f"<span style='background:{surf_bg}; color:{surf_fg}; font-weight:800; font-size:10.5px; padding:3px 8px; border-radius:5px;'>{surf}</span>"
                    f"<span style='background:#f1f5f9; color:#475569; font-weight:800; font-size:10.5px; padding:3px 8px; border-radius:5px;'>{m_type} · {rd}</span>"
                    f"{gps_badge}"
                    f"</div>"
                    f"<div style='font-size:18px; font-weight:900; color:#0f172a; margin-top:6px;'>"
                    f"Flavio Cobolli {rank_cob_str} <span style='color:#94a3b8; font-weight:500;'>vs</span> {opp} <span style='font-size:13px; color:#64748b; font-weight:700;'>({rank_opp_str})</span>"
                    f"</div>"
                    f"</div>"
                    f"<div style='text-align:right;'>"
                    f"<div style='font-size:22px; font-weight:900; color:#0f172a; letter-spacing:0.5px;'>{score}</div>"
                    f"<div style='font-size:12px; color:#64748b; font-weight:700;'><i class='bi bi-clock' style='color:#0ea5e9;'></i> {dur_str} · <i class='bi bi-hash' style='color:#f59e0b;'></i> {tot_p} pts</div>"
                    f"</div>"
                    f"</div>"
                    f"</div>",
                    unsafe_allow_html=True
                )

                col_tennis, col_gps = st.columns([1.1, 1.3])

                with col_tennis:
                    st.markdown(
                        f"<div style='font-size:12.5px; font-weight:900; color:#0f172a; text-transform:uppercase; letter-spacing:0.5px; margin-bottom:8px;'>"
                        f"<i class='bi bi-card-checklist' style='color:#0284c7; margin-right:5px;'></i>"
                        f"{tr('Statistiche Tecniche di Partita', 'Technical Match Statistics')}</div>",
                        unsafe_allow_html=True
                    )

                    st.markdown(
                        f"<table style='width:100%; font-size:12.5px; border-collapse:collapse;'>"
                        f"<tr style='border-bottom:1px solid #f1f5f9;'><td style='padding:6px 0; color:#64748b;'>{tr('Durata Match', 'Match Duration')}</td><td style='padding:6px 0; font-weight:800; color:#0f172a; text-align:right;'>{dur_str}</td></tr>"
                        f"<tr style='border-bottom:1px solid #f1f5f9;'><td style='padding:6px 0; color:#64748b;'>{tr('Punti Totali Giocati', 'Total Points Played')}</td><td style='padding:6px 0; font-weight:800; color:#0f172a; text-align:right;'>{tot_p}</td></tr>"
                        f"<tr style='border-bottom:1px solid #f1f5f9;'><td style='padding:6px 0; color:#64748b;'>{tr('Ace Cobolli', 'Cobolli Aces')}</td><td style='padding:6px 0; font-weight:800; color:#16a34a; text-align:right;'>{aces}</td></tr>"
                        f"<tr style='border-bottom:1px solid #f1f5f9;'><td style='padding:6px 0; color:#64748b;'>{tr('Doppi Falli', 'Double Faults')}</td><td style='padding:6px 0; font-weight:800; color:#dc2626; text-align:right;'>{df_count}</td></tr>"
                        f"<tr style='border-bottom:1px solid #f1f5f9;'><td style='padding:6px 0; color:#64748b;'>{tr('Punti al Servizio', 'Service Points')}</td><td style='padding:6px 0; font-weight:800; color:#0f172a; text-align:right;'>{srv_pts}</td></tr>"
                        f"<tr style='border-bottom:1px solid #f1f5f9;'><td style='padding:6px 0; color:#64748b;'>{tr('Punti Vinti 1° Servizio', '1st Serve Points Won')}</td><td style='padding:6px 0; font-weight:800; color:#0f172a; text-align:right;'>{p1_pts}</td></tr>"
                        f"<tr style='border-bottom:1px solid #f1f5f9;'><td style='padding:6px 0; color:#64748b;'>{tr('Punti Vinti 2° Servizio', '2nd Serve Points Won')}</td><td style='padding:6px 0; font-weight:800; color:#0f172a; text-align:right;'>{p2_pts}</td></tr>"
                        f"</table>",
                        unsafe_allow_html=True
                    )

                with col_gps:
                    st.markdown(
                        f"<div style='font-size:12.5px; font-weight:900; color:#0f172a; text-transform:uppercase; letter-spacing:0.5px; margin-bottom:8px;'>"
                        f"<i class='bi bi-broadcast' style='color:#0ea5e9; margin-right:5px;'></i>"
                        f"{tr('Telemetria GPS / IMU Reale', 'Linked Real GPS / IMU Telemetry')}</div>",
                        unsafe_allow_html=True
                    )

                    if is_linked or has_auto_gps:
                        if is_linked:
                            link_info = gps_links[m_id]
                            sess_nm = link_info.get("session_name", "Sessione Match")
                            tl_val = link_info.get("tl", 0)
                            dist_val = link_info.get("dist", 0)
                            min_val = link_info.get("min", 0)
                            acc_val = link_info.get("acc", 0)
                            dec_val = link_info.get("dec", 0)
                        else:
                            s_row = sess_in_date.iloc[0]
                            sess_nm = str(s_row.get("Session", "Sessione Match Reale"))
                            tl_val = float(get_val(s_row, "Training Load", 0))
                            dist_val = float(get_val(s_row, "DISTANCE", 0))
                            min_val = float(get_val(s_row, "Minuti", 0))
                            acc_val = float(get_val(s_row, "High Accel IMU", 0))
                            dec_val = float(get_val(s_row, "High Decel IMU", 0))

                        m_pt = (dist_val / tot_p) if tot_p > 0 else 0

                        st.markdown(
                            f"<div style='background:#f8fafc; border:1.5px solid #0ea5e9; border-radius:8px; padding:12px 14px; margin-bottom:10px;'>"
                            f"<div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;'>"
                            f"<span style='font-size:11px; font-weight:800; color:#0284c7; text-transform:uppercase;'><i class='bi bi-check-circle-fill'></i> TELEMETRIA REALE COLLEGATA</span>"
                            f"<span style='font-size:11px; font-weight:700; color:#64748b;'>{dt_str}</span>"
                            f"</div>"
                            f"<div style='font-size:14px; font-weight:900; color:#0f172a; margin-bottom:10px;'>{sess_nm}</div>"
                            f"<div style='display:grid; grid-template-columns: 1fr 1fr 1fr; gap:8px; text-align:center;'>"
                            f"<div style='background:white; border:1px solid #e2e8f0; border-radius:6px; padding:6px;'>"
                            f"<div style='font-size:9.5px; font-weight:800; color:#64748b;'>TRAINING LOAD</div>"
                            f"<div style='font-size:16px; font-weight:900; color:#0284c7;'>{tl_val:.0f}</div>"
                            f"</div>"
                            f"<div style='background:white; border:1px solid #e2e8f0; border-radius:6px; padding:6px;'>"
                            f"<div style='font-size:9.5px; font-weight:800; color:#64748b;'>METRI / PUNTO</div>"
                            f"<div style='font-size:16px; font-weight:900; color:#10b981;'>{m_pt:.1f} m</div>"
                            f"</div>"
                            f"<div style='background:white; border:1px solid #e2e8f0; border-radius:6px; padding:6px;'>"
                            f"<div style='font-size:9.5px; font-weight:800; color:#64748b;'>DISTANZA GPS</div>"
                            f"<div style='font-size:16px; font-weight:900; color:#0f172a;'>{dist_val:.0f} m</div>"
                            f"</div>"
                            f"</div>"
                            f"<div style='display:flex; justify-content:space-between; font-size:11.5px; color:#64748b; font-weight:700; margin-top:8px; padding-top:6px; border-top:1px dashed #e2e8f0;'>"
                            f"<span>Minuti GPS: <b>{min_val:.0f}m</b></span>"
                            f"<span>Acc High: <b>{acc_val:.0f}</b></span>"
                            f"<span>Dec High: <b>{dec_val:.0f}</b></span>"
                            f"</div>"
                            f"</div>",
                            unsafe_allow_html=True
                        )

                        if is_linked and st.button(tr("Scollega Sessione GPS", "Unlink GPS Session"), key=f"unlink_{m_id}", icon=":material/link_off:"):
                            remove_match_gps_link(m_id)
                            st.success(tr("Sessione scollegata con successo.", "GPS session unlinked successfully."))
                            st.rerun()

                    else:
                        st.info(tr(f"Nessuna acquisizione GPS reale registrata il {dt_str}.", f"No real GPS acquisition recorded on {dt_str}."))

        # Download CSV
        st.markdown("<div style='margin-top: 30px;'></div>", unsafe_allow_html=True)
        with st.container(border=True):
            d_c1, d_c2 = st.columns([2, 1])
            with d_c1:
                st.markdown(
                    f"<div style='font-size:13px; font-weight:800; color:#0f172a;'>"
                    f"{tr('Esporta Tabella Match Singoli Selezionati', 'Export Selected Singles Matches Table')}</div>"
                    f"<div style='font-size:11.5px; color:#64748b;'>"
                    f"{tr('Scarica l archivio dei match singoli in CSV con metriche tecniche e fisiche reali.', 'Download the singles dataset in CSV format with real technical and physical metrics.')}</div>",
                    unsafe_allow_html=True
                )
            with d_c2:
                csv_data = df_f.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label=tr("Scarica CSV Match Singoli", "Download Singles CSV"),
                    data=csv_data,
                    file_name=f"cobolli_singoli_{data_inizio.strftime('%Y%m%d') if data_inizio else 'all'}.csv",
                    mime="text/csv",
                    use_container_width=True,
                    icon=":material/download:"
                )
