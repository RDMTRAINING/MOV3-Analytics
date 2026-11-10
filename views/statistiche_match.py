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

from config import (
    LOGO_PATH,
    tr,
    render_page_header,
    card_kpi,
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
                    'is_manual': False
                }

        if gps_data and gps_data['dist'] > 0 and tot_pts > 0:
            row_dict = r.to_dict()
            row_dict.update(gps_data)
            row_dict['m_per_point'] = gps_data['dist'] / tot_pts
            row_dict['tl_per_point'] = gps_data['tl'] / tot_pts
            row_dict['pl_per_point'] = gps_data['pl'] / tot_pts
            row_dict['acc_dec_per_point'] = (gps_data['acc'] + gps_data['dec']) / tot_pts
            row_dict['pct_tl_high'] = (gps_data['tl_high'] / gps_data['tl'] * 100) if gps_data['tl'] > 0 else 0
            row_dict['m_per_min'] = (gps_data['dist'] / gps_data['min']) if gps_data['min'] > 0 else 0
            rows.append(row_dict)

    df_out = pd.DataFrame(rows)
    if not df_out.empty:
        # Filtra eventuali valori anomali
        df_out = df_out[df_out['m_per_point'] > 0].copy()
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
    # STRUTTURA A TAB
    # =========================================================================
    tab_analisi, tab_archivio = st.tabs([
        tr("📊 Analisi Prestazione Tennis ↔ GPS", "📊 Tennis ↔ GPS Performance Analysis"),
        tr("🎾 Archivio Partite & Abbinamento Telemetria", "🎾 Match Archive & Telemetry Pairing")
    ])

    # -------------------------------------------------------------------------
    # TAB 1: ANALISI PRESTAZIONE TENNIS <-> GPS (SOLO MATCH SINGOLI & DATI REALI)
    # -------------------------------------------------------------------------
    with tab_analisi:
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
            # 1. COSTO FISICO DEL PUNTO (METRICHE PER-POINT)
            # =================================================================
            st.markdown(f"""
            <div style='font-size: 16px; font-weight: 900; color: #0f172a; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 14px; display: flex; align-items: center; gap: 8px;'>
                <i class='bi bi-speedometer2' style='color: #0ea5e9;'></i>
                {tr("1. Costo Fisico del Punto nei Match Singoli", "1. Physical Cost of the Point in Singles Matches")}
            </div>
            """, unsafe_allow_html=True)

            m_pt_avg = df_corr['m_per_point'].mean()
            tl_pt_avg = df_corr['tl_per_point'].mean()
            pl_pt_avg = df_corr['pl_per_point'].mean()
            acc_dec_pt_avg = df_corr['acc_dec_per_point'].mean()

            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.markdown(card_kpi(
                    tr("Metri per Punto", "Meters per Point"),
                    f"<span style='font-size:25px; font-weight:900; color:#0f172a;'>{m_pt_avg:.1f} <span style='font-size:15px; font-weight:700; color:#64748b;'>m/pt</span></span>",
                    f"Min: {df_corr['m_per_point'].min():.1f}m · Max: {df_corr['m_per_point'].max():.1f}m",
                    "#0ea5e9"
                ), unsafe_allow_html=True)
            with c2:
                st.markdown(card_kpi(
                    tr("Training Load / Punto", "Training Load / Point"),
                    f"<span style='font-size:25px; font-weight:900; color:#0f172a;'>{tl_pt_avg:.1f} <span style='font-size:15px; font-weight:700; color:#64748b;'>TL/pt</span></span>",
                    f"{df_corr['tl'].mean():.0f} TL {tr('medio per match', 'avg per match')}",
                    "#6366f1"
                ), unsafe_allow_html=True)
            with c3:
                st.markdown(card_kpi(
                    tr("Player Load / Punto", "Player Load / Point"),
                    f"<span style='font-size:25px; font-weight:900; color:#0f172a;'>{pl_pt_avg:.2f} <span style='font-size:15px; font-weight:700; color:#64748b;'>PL/pt</span></span>",
                    f"{tr('Stress neuromuscolare triassiale', 'Triaxial neuromuscular stress')}",
                    "#0284c7"
                ), unsafe_allow_html=True)
            with c4:
                st.markdown(card_kpi(
                    tr("Acc + Dec High / Punto", "High Acc + Dec / Point"),
                    f"<span style='font-size:25px; font-weight:900; color:#0f172a;'>{acc_dec_pt_avg:.2f} <span style='font-size:15px; font-weight:700; color:#64748b;'>ev/pt</span></span>",
                    f"~1 {tr('azione intensa ogni', 'intense action every')} {1.0 / acc_dec_pt_avg:.1f} {tr('punti', 'pts')}" if acc_dec_pt_avg > 0 else "N/D",
                    "#ea580c"
                ), unsafe_allow_html=True)

            # SPAZIATURA PULITA TRA LE 4 CARD E IL GRAFICO
            st.markdown("<div style='margin-top: 28px; margin-bottom: 12px;'></div>", unsafe_allow_html=True)

            # GRAFICO A BARRE CRONOLOGICHE ORDINATE PER MATCH SINGOLO (ZERO LINEE INCROCIATE)
            with st.container(border=True):
                st.markdown(f"""
                <div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;'>
                    <div style='font-size: 13.5px; font-weight: 800; color: #0f172a;'>
                        {tr("Distanza per Singolo Punto Disputato per ciascun Match Ufficiale (m/pt)", "Meters per Single Point in each Official Match (m/pt)")}
                    </div>
                    <div style='font-size: 11.5px; font-weight: 700; color: #64748b;'>
                        <span style='color: #10b981;'><i class='bi bi-square-fill'></i> Vittoria</span> &nbsp;
                        <span style='color: #ef4444;'><i class='bi bi-square-fill'></i> Sconfitta</span> &nbsp;
                        <span style='color: #0284c7;'><i class='bi bi-dash-lg'></i> Media Mobile (3 Match)</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                # Prepara etichette pulite per ciascuna barra
                bar_labels = []
                bar_colors = []
                bar_borders = []
                for _, r in df_corr.iterrows():
                    opp_nm = str(r['opponent']).split('[')[0].strip()
                    parts = opp_nm.split()
                    opp_short = parts[-1] if parts else "Opp"
                    bar_labels.append(f"{r['date']} · {opp_short}")
                    if r['result'] == 'Vittoria':
                        bar_colors.append('#10b981')
                        bar_borders.append('#059669')
                    else:
                        bar_colors.append('#ef4444')
                        bar_borders.append('#dc2626')

                # Calcolo media mobile a 3 match per trend fluido
                rolling_trend = df_corr['m_per_point'].rolling(window=3, min_periods=1).mean()

                fig_m_pt = go.Figure()

                # Barre singole per ogni match
                fig_m_pt.add_trace(go.Bar(
                    x=bar_labels,
                    y=df_corr['m_per_point'],
                    marker=dict(
                        color=bar_colors,
                        line=dict(color=bar_borders, width=1)
                    ),
                    name=tr("Metri / Punto", "Meters / Point"),
                    customdata=np.stack((
                        df_corr['tournament'],
                        df_corr['surface'],
                        df_corr['opponent'],
                        df_corr['score'],
                        df_corr['dist'],
                        df_corr['total_points'],
                        df_corr['duration_str'],
                        df_corr['tl'],
                        df_corr['result']
                    ), axis=-1),
                    hovertemplate=(
                        "<b>%{customdata[0]}</b> (%{customdata[1]})<br>"
                        "vs %{customdata[2]} · %{customdata[3]}<br>"
                        "<b>Esito: %{customdata[8]}</b><br>"
                        "<b>Metri/Punto: %{y:.1f} m/pt</b><br>"
                        "Distanza Totale: %{customdata[4]:.0f} m · Punti: %{customdata[5]}<br>"
                        "Durata: %{customdata[6]} · TL: %{customdata[7]:.0f}<extra></extra>"
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
                    y=m_pt_avg,
                    line_dash="dash",
                    line_color="#64748b",
                    annotation_text=f"Media Reale: {m_pt_avg:.1f} m/pt",
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
                        title=tr("Metri / Punto (m)", "Meters / Point (m)"),
                        showgrid=True,
                        gridcolor="#f1f5f9",
                        tickfont=dict(family="Inter", size=11)
                    ),
                    plot_bgcolor="#ffffff",
                    paper_bgcolor="#ffffff",
                    height=360,
                    margin=dict(l=45, r=20, t=20, b=75),
                    showlegend=False
                )
                st.plotly_chart(fig_m_pt, use_container_width=True)

            # SPAZIATURA GENEROSA PRIMA DEL BENCHMARK
            st.markdown("<div style='margin-top: 45px; margin-bottom: 20px;'></div>", unsafe_allow_html=True)

            # =================================================================
            # 2. BENCHMARK VITTORIE VS SCONFITTE
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
                w_mpt = m_win['m_per_point'].mean()
                l_mpt = m_loss['m_per_point'].mean()
                delta_mpt = ((w_mpt - l_mpt) / l_mpt * 100) if l_mpt > 0 else 0

                w_tl = m_win['tl'].mean()
                l_tl = m_loss['tl'].mean()
                delta_tl = ((w_tl - l_tl) / l_tl * 100) if l_tl > 0 else 0

                w_tlh = m_win['pct_tl_high'].mean()
                l_tlh = m_loss['pct_tl_high'].mean()
                delta_tlh = (w_tlh - l_tlh)

                w_pl = m_win['pl'].mean()
                l_pl = m_loss['pl'].mean()

                w_dec = m_win['dec'].mean()
                l_dec = m_loss['dec'].mean()

                w_pts = m_win['total_points'].mean()
                l_pts = m_loss['total_points'].mean()

                col_bench_tbl, col_bench_plot = st.columns([1.1, 1.2])

                with col_bench_tbl:
                    st.markdown(f"""
                    <table style='width: 100%; border-collapse: collapse; font-family: "Inter", sans-serif; font-size: 12.5px; background: white; border-radius: 8px; overflow: hidden; border: 1px solid #e2e8f0;'>
                        <thead>
                            <tr style='background: #f8fafc; border-bottom: 2px solid #e2e8f0;'>
                                <th style='padding: 10px 12px; text-align: left; color: #475569; font-weight: 800;'>METRICA FISICA REALE</th>
                                <th style='padding: 10px 12px; text-align: right; color: #16a34a; font-weight: 900;'>VITTORIE ({len(m_win)})</th>
                                <th style='padding: 10px 12px; text-align: right; color: #dc2626; font-weight: 900;'>SCONFITTE ({len(m_loss)})</th>
                                <th style='padding: 10px 12px; text-align: right; color: #0284c7; font-weight: 800;'>DELTA %</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr style='border-bottom: 1px solid #f1f5f9;'>
                                <td style='padding: 8px 12px; font-weight: 700; color: #0f172a;'>Metri per Punto</td>
                                <td style='padding: 8px 12px; text-align: right; font-weight: 800; color: #16a34a;'>{w_mpt:.1f} m</td>
                                <td style='padding: 8px 12px; text-align: right; font-weight: 800; color: #dc2626;'>{l_mpt:.1f} m</td>
                                <td style='padding: 8px 12px; text-align: right; font-weight: 800; color: {"#16a34a" if delta_mpt > 0 else "#dc2626"};'>{delta_mpt:+.1f}%</td>
                            </tr>
                            <tr style='border-bottom: 1px solid #f1f5f9;'>
                                <td style='padding: 8px 12px; font-weight: 700; color: #0f172a;'>Training Load Medio</td>
                                <td style='padding: 8px 12px; text-align: right; font-weight: 800; color: #16a34a;'>{w_tl:.0f}</td>
                                <td style='padding: 8px 12px; text-align: right; font-weight: 800; color: #dc2626;'>{l_tl:.0f}</td>
                                <td style='padding: 8px 12px; text-align: right; font-weight: 800; color: {"#16a34a" if delta_tl > 0 else "#dc2626"};'>{delta_tl:+.1f}%</td>
                            </tr>
                            <tr style='border-bottom: 1px solid #f1f5f9;'>
                                <td style='padding: 8px 12px; font-weight: 700; color: #0f172a;'>% TL High (&gt;Alta Intensità)</td>
                                <td style='padding: 8px 12px; text-align: right; font-weight: 800; color: #16a34a;'>{w_tlh:.1f}%</td>
                                <td style='padding: 8px 12px; text-align: right; font-weight: 800; color: #dc2626;'>{l_tlh:.1f}%</td>
                                <td style='padding: 8px 12px; text-align: right; font-weight: 800; color: {"#16a34a" if delta_tlh > 0 else "#dc2626"};'>{delta_tlh:+.1f} pt</td>
                            </tr>
                            <tr style='border-bottom: 1px solid #f1f5f9;'>
                                <td style='padding: 8px 12px; font-weight: 700; color: #0f172a;'>Player Load Meccanico</td>
                                <td style='padding: 8px 12px; text-align: right; font-weight: 800; color: #16a34a;'>{w_pl:.0f}</td>
                                <td style='padding: 8px 12px; text-align: right; font-weight: 800; color: #dc2626;'>{l_pl:.0f}</td>
                                <td style='padding: 8px 12px; text-align: right; font-weight: 800; color: #475569;'>{((w_pl-l_pl)/l_pl*100) if l_pl>0 else 0:+.1f}%</td>
                            </tr>
                            <tr style='border-bottom: 1px solid #f1f5f9;'>
                                <td style='padding: 8px 12px; font-weight: 700; color: #0f172a;'>Decelerazioni High IMU</td>
                                <td style='padding: 8px 12px; text-align: right; font-weight: 800; color: #16a34a;'>{w_dec:.0f}</td>
                                <td style='padding: 8px 12px; text-align: right; font-weight: 800; color: #dc2626;'>{l_dec:.0f}</td>
                                <td style='padding: 8px 12px; text-align: right; font-weight: 800; color: #475569;'>{((w_dec-l_dec)/l_dec*100) if l_dec>0 else 0:+.1f}%</td>
                            </tr>
                            <tr>
                                <td style='padding: 8px 12px; font-weight: 700; color: #0f172a;'>Punti Totali per Match</td>
                                <td style='padding: 8px 12px; text-align: right; font-weight: 800; color: #16a34a;'>{w_pts:.0f}</td>
                                <td style='padding: 8px 12px; text-align: right; font-weight: 800; color: #dc2626;'>{l_pts:.0f}</td>
                                <td style='padding: 8px 12px; text-align: right; font-weight: 800; color: #475569;'>{((w_pts-l_pts)/l_pts*100) if l_pts>0 else 0:+.1f}%</td>
                            </tr>
                        </tbody>
                    </table>
                    """, unsafe_allow_html=True)

                    st.markdown(f"""
                    <div style='background: #f8fafc; border-left: 4px solid #10b981; padding: 10px 14px; border-radius: 6px; font-size: 12px; color: #334155; margin-top: 10px;'>
                        <b>Evidenza Prestativa:</b> Nelle partite vinte Flavio percorre <b>{w_mpt:.1f} m/punto</b> ({delta_mpt:+.1f}% rispetto alle sconfitte), sostenendo un Training Load superiore del <b>{delta_tl:+.1f}%</b>.
                    </div>
                    """, unsafe_allow_html=True)

                with col_bench_plot:
                    categories = [tr('Metri/Punto (m)', 'Meters/Pt (m)'), tr('% TL High', '% TL High'), tr('Decel High / 10', 'High Dec / 10'), tr('Punti / 10', 'Points / 10')]
                    val_win = [w_mpt, w_tlh, w_dec / 10.0, w_pts / 10.0]
                    val_loss = [l_mpt, l_tlh, l_dec / 10.0, l_pts / 10.0]

                    fig_bench = go.Figure(data=[
                        go.Bar(name=tr('Vittorie', 'Wins'), x=categories, y=val_win, marker_color='#16a34a', text=[f"{v:.1f}" for v in val_win], textposition='auto'),
                        go.Bar(name=tr('Sconfitte', 'Losses'), x=categories, y=val_loss, marker_color='#dc2626', text=[f"{v:.1f}" for v in val_loss], textposition='auto')
                    ])
                    fig_bench.update_layout(
                        barmode='group',
                        title=dict(text=f"<b>{tr('Profilo Fisico Reale per Esito Match', 'Real Physical Profile by Outcome')}</b>", font=dict(size=13, family="Inter")),
                        plot_bgcolor="#ffffff",
                        paper_bgcolor="#ffffff",
                        height=310,
                        margin=dict(l=20, r=20, t=40, b=30),
                        yaxis=dict(showgrid=True, gridcolor="#f1f5f9"),
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                    )
                    st.plotly_chart(fig_bench, use_container_width=True)

            # SPAZIATURA GENEROSA PRIMA DELLA SUPERFICIE
            st.markdown("<div style='margin-top: 45px; margin-bottom: 20px;'></div>", unsafe_allow_html=True)

            # =================================================================
            # 3. IMPATTO DELLA SUPERFICIE
            # =================================================================
            st.markdown(f"""
            <div style='font-size: 16px; font-weight: 900; color: #0f172a; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 14px; display: flex; align-items: center; gap: 8px;'>
                <i class='bi bi-layers-half' style='color: #ea580c;'></i>
                {tr("3. Impatto della Superficie: Terra vs Cemento vs Erba (Match Singoli)", "3. Surface Impact: Clay vs Hard vs Grass (Singles)")}
            </div>
            """, unsafe_allow_html=True)

            surf_agg = df_corr.groupby('surface').agg(
                n_match=('match_id', 'count'),
                m_pt=('m_per_point', 'mean'),
                tl_avg=('tl', 'mean'),
                tl_high_pct=('pct_tl_high', 'mean'),
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
                                {sr['m_pt']:.1f} <span style='font-size: 14px; color: #64748b; font-weight: 700;'>m/punto</span>
                            </div>
                            <div style='font-size: 12px; color: #475569; display: flex; flex-direction: column; gap: 4px; border-top: 1px solid #f1f5f9; padding-top: 8px;'>
                                <div style='display:flex; justify-content:space-between;'><span>Training Load medio:</span><b>{sr['tl_avg']:.0f} TL</b></div>
                                <div style='display:flex; justify-content:space-between;'><span>% Alta Intensità:</span><b>{sr['tl_high_pct']:.1f}%</b></div>
                                <div style='display:flex; justify-content:space-between;'><span>Frenate High IMU:</span><b>{sr['dec_avg']:.0f} / match</b></div>
                                <div style='display:flex; justify-content:space-between;'><span>Durata Media:</span><b>{sr['dur_avg']:.0f} min</b></div>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)

            # Scatter per superficie
            st.markdown("<div style='margin-top: 18px;'></div>", unsafe_allow_html=True)
            with st.container(border=True):
                fig_surf = px.scatter(
                    df_corr,
                    x='m_per_point',
                    y='dec',
                    color='surface',
                    size='total_points',
                    color_discrete_map={'Clay': '#ea580c', 'Hard': '#0284c7', 'Grass': '#059669'},
                    hover_data=['tournament', 'opponent', 'score', 'result'],
                    labels={'m_per_point': tr('Metri per Punto (m/pt)', 'Meters per Point (m/pt)'), 'dec': tr('Decelerazioni High IMU', 'High Decelerations IMU'), 'surface': tr('Superficie', 'Surface')}
                )
                fig_surf.update_layout(
                    title=dict(text=f"<b>{tr('Dinamica di Gioco Reale per Superficie (Metri/Punto vs Decelerazioni)', 'Court Dynamics by Surface')}</b>", font=dict(size=13, family="Inter")),
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
            # 4. DIFFICOLTÀ AVVERSARIO & TOP MATCH LOGORAMENTO
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

            col_rk1, col_rk2 = st.columns([1.2, 1.1])
            with col_rk1:
                with st.container(border=True):
                    fig_rk = px.scatter(
                        df_corr,
                        x='opponent_rank',
                        y='tl',
                        color='result',
                        size='total_points',
                        color_discrete_map={'Vittoria': '#16a34a', 'Sconfitta': '#dc2626'},
                        hover_data=['tournament', 'opponent', 'score', 'surface', 'm_per_point'],
                        labels={'opponent_rank': tr('Ranking Avversario ATP', 'ATP Opponent Rank'), 'tl': tr('Training Load Totale Reale', 'Real Training Load'), 'result': tr('Esito', 'Result')}
                    )
                    fig_rk.update_layout(
                        title=dict(text=f"<b>{tr('Training Load Reale vs Ranking Avversario', 'Training Load vs Opponent Ranking')}</b>", font=dict(size=13, family="Inter")),
                        plot_bgcolor="#ffffff",
                        paper_bgcolor="#ffffff",
                        height=320,
                        margin=dict(l=40, r=20, t=40, b=40),
                        xaxis=dict(showgrid=True, gridcolor="#f1f5f9", autorange="reversed"),
                        yaxis=dict(showgrid=True, gridcolor="#f1f5f9")
                    )
                    st.plotly_chart(fig_rk, use_container_width=True)

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
                                <div style='font-size: 11px; color: #64748b;'>{s_r['score']} · {s_r['total_points']} pts · {s_r['m_per_point']:.1f} m/pt</div>
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

            df_corr['pct_1st_won'] = (df_corr['first_serve_points'] / df_corr['service_points'].replace(0, np.nan) * 100).fillna(0)
            
            c_srv1, c_srv2 = st.columns([1.1, 1.1])
            with c_srv1:
                with st.container(border=True):
                    fig_ace = px.scatter(
                        df_corr,
                        x='aces',
                        y='m_per_point',
                        color='result',
                        color_discrete_map={'Vittoria': '#16a34a', 'Sconfitta': '#dc2626'},
                        labels={'aces': tr('Numero di Ace Disputati', 'Number of Aces'), 'm_per_point': tr('Metri per Punto (m/pt)', 'Meters per Point (m/pt)')}
                    )
                    valid_ace = df_corr.dropna(subset=['aces', 'm_per_point'])
                    if len(valid_ace) > 2 and valid_ace['aces'].nunique() > 1:
                        m_slope, b_intercept = np.polyfit(valid_ace['aces'].astype(float), valid_ace['m_per_point'].astype(float), 1)
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
                        title=dict(text=f"<b>{tr('Impatto degli Ace sul Volume Fisico (Metri/Punto)', 'Aces Impact on Physical Volume')}</b>", font=dict(size=13, family="Inter")),
                        plot_bgcolor="#ffffff",
                        paper_bgcolor="#ffffff",
                        height=310,
                        margin=dict(l=40, r=20, t=40, b=40),
                        xaxis=dict(showgrid=True, gridcolor="#f1f5f9"),
                        yaxis=dict(showgrid=True, gridcolor="#f1f5f9")
                    )
                    st.plotly_chart(fig_ace, use_container_width=True)

            with c_srv2:
                hi_ace = df_corr[df_corr['aces'] >= 6]
                lo_ace = df_corr[df_corr['aces'] < 6]
                
                mpt_hi = hi_ace['m_per_point'].mean() if not hi_ace.empty else 0
                mpt_lo = lo_ace['m_per_point'].mean() if not lo_ace.empty else 0
                wr_hi = (hi_ace['result'] == 'Vittoria').mean() * 100 if not hi_ace.empty else 0
                wr_lo = (lo_ace['result'] == 'Vittoria').mean() * 100 if not lo_ace.empty else 0

                st.markdown(f"""
                <div style='background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px;'>
                    <div style='font-size: 13.5px; font-weight: 800; color: #0f172a; margin-bottom: 12px; text-transform: uppercase;'>
                        {tr("Risparmio Fisico nei Giorni di Servizio Dominante", "Physical Savings on High-Serve Days")}
                    </div>
                    <div style='display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 14px;'>
                        <div style='background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 10px;'>
                            <div style='font-size: 11px; font-weight: 800; color: #16a34a;'>PARTITE CON ≥ 6 ACE ({len(hi_ace)})</div>
                            <div style='font-size: 20px; font-weight: 900; color: #0f172a; margin-top: 4px;'>{mpt_hi:.1f} <span style='font-size: 12px; color: #64748b;'>m/pt</span></div>
                            <div style='font-size: 11px; color: #16a34a; font-weight: 700; margin-top: 2px;'>Win Rate: {wr_hi:.1f}%</div>
                        </div>
                        <div style='background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 10px;'>
                            <div style='font-size: 11px; font-weight: 800; color: #64748b;'>PARTITE CON &lt; 6 ACE ({len(lo_ace)})</div>
                            <div style='font-size: 20px; font-weight: 900; color: #0f172a; margin-top: 4px;'>{mpt_lo:.1f} <span style='font-size: 12px; color: #64748b;'>m/pt</span></div>
                            <div style='font-size: 11px; color: #475569; font-weight: 700; margin-top: 2px;'>Win Rate: {wr_lo:.1f}%</div>
                        </div>
                    </div>
                    <div style='font-size: 12px; color: #475569; background: #fffbeb; border-left: 3px solid #f59e0b; padding: 8px 12px; border-radius: 4px;'>
                        <b>Impatto Fisiologico:</b> Nei match in cui Flavio realizza almeno 6 ace, la distanza per punto si riduce e il Win Rate sale dal <b>{wr_lo:.1f}%</b> al <b>{wr_hi:.1f}%</b>, riducendo l'affaticamento eccentrico sulle decelerazioni.
                    </div>
                </div>
                """, unsafe_allow_html=True)

    # -------------------------------------------------------------------------
    # TAB 2: ARCHIVIO PARTITE & ABBINAMENTO TELEMETRIA (SOLO MATCH SINGOLI)
    # -------------------------------------------------------------------------
    with tab_archivio:
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
