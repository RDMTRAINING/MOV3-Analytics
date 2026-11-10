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
    Associa a ciascun match in df_f i dati GPS/IMU (da abbinamento esplicito o per data comune).
    Restituisce un DataFrame con metriche point-by-point e di intensita.
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
            match_sess = df_gps_ath[(df_gps_ath['Date'] == dt) & (df_gps_ath['Tipologia Sessione'].astype(str).str.lower().isin(['match', 'match doppio', 'torneo', 'tennis match']))]
            if not match_sess.empty:
                if str(r.get('type', '')).lower() == 'doppio':
                    cand = match_sess[match_sess['Tipologia Sessione'].astype(str).str.lower() == 'match doppio']
                    if not cand.empty:
                        match_sess = cand
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

        if gps_data and gps_data['dist'] > 0:
            row_dict = r.to_dict()
            row_dict.update(gps_data)
            row_dict['m_per_point'] = (gps_data['dist'] / tot_pts) if tot_pts > 0 else 0
            row_dict['tl_per_point'] = (gps_data['tl'] / tot_pts) if tot_pts > 0 else 0
            row_dict['pl_per_point'] = (gps_data['pl'] / tot_pts) if tot_pts > 0 else 0
            row_dict['acc_dec_per_point'] = ((gps_data['acc'] + gps_data['dec']) / tot_pts) if tot_pts > 0 else 0
            row_dict['pct_tl_high'] = (gps_data['tl_high'] / gps_data['tl'] * 100) if gps_data['tl'] > 0 else 0
            row_dict['m_per_min'] = (gps_data['dist'] / gps_data['min']) if gps_data['min'] > 0 else 0
            rows.append(row_dict)

    df_out = pd.DataFrame(rows)
    if not df_out.empty:
        # Pulisce eventuali valori anomali
        df_out = df_out[df_out['m_per_point'] > 0].copy()
    return df_out


def render_statistiche_match(t):
    render_page_header(
        tr("Statistiche Match Ufficiali", "Official Match Statistics"),
        tr("Archivio storico dei match ATP/ITF, statistiche di gioco e correlazione diretta con la telemetria GPS/IMU.",
           "Historical ATP/ITF match database, match statistics, and direct correlation with GPS/IMU telemetry."),
        "OFFICIAL MATCH STATS"
    )

    atleti_visibili = get_lista_atleti_disponibili(st.session_state.get('user'), st.session_state.get('role'))
    ath_sel = st.session_state.get('selected_athlete')
    if not ath_sel or (atleti_visibili and ath_sel not in atleti_visibili):
        ath_sel = atleti_visibili[0] if atleti_visibili else "Flavio Cobolli"

    is_cobolli = "cobolli" in str(ath_sel).lower()

    if not is_cobolli:
        st.info(tr(
            f"Al momento l'archivio dettagliato dei match punto-a-punto e configurato per Flavio Cobolli. Seleziona Flavio Cobolli dal menu laterale per esplorare lo storico.",
            f"Currently the detailed official match history is configured for Flavio Cobolli. Select Flavio Cobolli from the sidebar to explore his history."
        ))
        return

    # Carica il dataset dei match ufficiali
    df_matches = load_cobolli_matches()
    if df_matches.empty:
        st.warning(tr("Nessun match trovato nel file di storico Cobolli.", "No matches found in Cobolli history file."))
        return

    # Carica database GPS locale per abbinamento
    df_gps_all = load_local_database()
    df_gps_ath = df_gps_all[df_gps_all['Players'].astype(str).str.lower().str.contains("cobolli", na=False)].copy() if not df_gps_all.empty else pd.DataFrame()
    gps_links = load_match_gps_links()

    # =========================================================================
    # PANNELLO FILTRI & RICERCA AVANZATA
    # =========================================================================
    with st.container(border=True):
        st.markdown(
            f"<div style='display:flex; align-items:center; gap:8px; margin-bottom:12px;'>"
            f"<i class='bi bi-funnel-fill' style='color:#0ea5e9; font-size:17px;'></i>"
            f"<span style='font-size:14px; font-weight:800; color:#0f172a; text-transform:uppercase; letter-spacing:0.5px;'>"
            f"{tr('Pannello Ricerca & Filtri Match', 'Match Search & Filters Panel')}</span>"
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
            opzioni_tipo = [tr("Tutti (Singolo + Doppio)", "All (Singles + Doubles)"), "Singolare", "Doppio"]
            sel_tipo = st.selectbox(tr("Tipologia Gara", "Competition Type"), opzioni_tipo, index=0, key="filter_match_type")

        with f_c3:
            opzioni_surf = [tr("Tutte le Superfici", "All Surfaces"), "Hard", "Clay", "Grass"]
            sel_surf = st.selectbox(tr("Superficie", "Surface"), opzioni_surf, index=0, key="filter_match_surface")

        with f_c4:
            opzioni_res = [tr("Tutti gli Esiti", "All Results"), tr("Solo Vittorie (W)", "Wins Only (W)"), tr("Solo Sconfitte (L)", "Losses Only (L)")]
            sel_res = st.selectbox(tr("Esito Partita", "Match Result"), opzioni_res, index=0, key="filter_match_res")

        f_r2_1, f_r2_2, f_r2_3 = st.columns([1.5, 1.2, 1.3])
        with f_r2_1:
            search_query = st.text_input(
                tr("Cerca Avversario o Torneo", "Search Opponent or Tournament"),
                placeholder=tr("Es: Shelton, Vienna, Australian Open...", "E.g. Shelton, Vienna, Australian Open..."),
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

        with f_r2_3:
            filtro_gps_link = st.selectbox(
                tr("Stato Telemetria GPS", "GPS Telemetry Status"),
                [tr("Tutti i Match", "All Matches"), tr("Solo con GPS Abbinato/Presente", "Only with GPS Data"), tr("Solo senza GPS", "Only without GPS")],
                index=0,
                key="filter_match_gps_link"
            )

    # =========================================================================
    # APPLICAZIONE DEI FILTRI
    # =========================================================================
    df_f = df_matches.copy()
    if data_inizio:
        df_f = df_f[df_f["date_obj"] >= data_inizio]

    if sel_tipo == "Singolare":
        df_f = df_f[df_f["type"] == "Singolare"]
    elif sel_tipo == "Doppio":
        df_f = df_f[df_f["type"] == "Doppio"]

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

    # Costruisci dataset correlato Tennis <-> GPS
    df_corr = build_correlated_dataset(df_f, df_gps_ath, gps_links)
    linked_mids = set(df_corr["match_id"].tolist()) if not df_corr.empty else set()

    if filtro_gps_link == tr("Solo con GPS Abbinato/Presente", "Only with GPS Data"):
        df_f = df_f[df_f["match_id"].isin(linked_mids)]
    elif filtro_gps_link == tr("Solo senza GPS", "Only without GPS"):
        df_f = df_f[~df_f["match_id"].isin(linked_mids)]

    # Ordina per data decrescente
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
                tr("Win Rate Match", "Match Win Rate"),
                f"<span style='font-size:25px; font-weight:900; color:#0f172a;'>{win_rate:.1f}%</span> "
                f"<span style='font-size:11.5px; font-weight:800; color:#16a34a; background:#dcfce7; padding:2px 7px; border-radius:6px;'>{vittorie}W - {sconfitte}L</span>",
                f"{tot_m} {tr('match nel periodo selezionato', 'matches in selected period')}",
                "#10b981"
            ),
            unsafe_allow_html=True
        )
    with k2:
        st.markdown(
            card_kpi(
                tr("Durata Media Partita", "Average Match Duration"),
                f"<span style='font-size:25px; font-weight:900; color:#0f172a;'>{dur_avg_str}</span>",
                f"{int(tot_dur_min // 60)} {tr('ore totali di match disputate', 'total match hours played')}",
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
                f"{int(df_f['total_points'].sum() / tot_m) if tot_m > 0 else 0} {tr('punti medi giocati per partita', 'avg points played per match')}",
                "#f59e0b"
            ),
            unsafe_allow_html=True
        )
    with k4:
        st.markdown(
            card_kpi(
                tr("Correlazione Telemetria GPS", "GPS Telemetry Correlation"),
                f"<span style='font-size:25px; font-weight:900; color:#0f172a;'>{linked_gps_count} <span style='font-size:16px; color:#64748b;'>/ {tot_m}</span></span>",
                f"<span style='color:#0284c7; font-weight:800;'>{pct_gps_linked:.0f}%</span> {tr('partite con telemetria fisica attiva', 'matches with active physical telemetry')}",
                "#8b5cf6"
            ),
            unsafe_allow_html=True
        )

    st.markdown("<div style='margin-top: 20px;'></div>", unsafe_allow_html=True)

    # =========================================================================
    # STRUTTURA A TAB: 1) ANALISI PRESTAZIONE GPS <-> TENNIS  2) ARCHIVIO PARTITE
    # =========================================================================
    tab_analisi, tab_archivio = st.tabs([
        tr("📊 Analisi Prestazione Tennis ↔ GPS", "📊 Tennis ↔ GPS Performance Analysis"),
        tr("🎾 Archivio Partite & Abbinamento Telemetria", "🎾 Match Archive & Telemetry Pairing")
    ])

    # -------------------------------------------------------------------------
    # TAB 1: ANALISI PRESTAZIONE TENNIS <-> GPS
    # -------------------------------------------------------------------------
    with tab_analisi:
        if df_corr.empty:
            st.info(tr(
                "Nessuna sessione GPS corrisponde ai match filtrati nel periodo selezionato. Rimuovi o allarga i filtri per visualizzare le analisi correlate.",
                "No GPS sessions match the filtered matches in the selected period. Broaden your filters to view correlated analytics."
            ))
        else:
            n_corr = len(df_corr)
            tot_dist_km = df_corr['dist'].sum() / 1000.0
            tot_ore_gps = df_corr['min'].sum() / 60.0
            tot_pts_gps = int(df_corr['total_points'].sum())

            # Banner Informativo Dataset Correlato
            st.markdown(f"""
            <div style='background: linear-gradient(135deg, rgba(14, 165, 233, 0.08) 0%, rgba(30, 41, 59, 0.03) 100%); border: 1px solid rgba(14, 165, 233, 0.25); border-radius: 10px; padding: 12px 18px; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px;'>
                <div>
                    <span style='font-weight: 800; color: #0284c7; text-transform: uppercase; font-size: 11px; letter-spacing: 0.5px;'><i class='bi bi-cpu-fill'></i> MOTORE CORRELAZIONE FISICO-TECNICA</span>
                    <div style='font-weight: 800; font-size: 15px; color: #0f172a; margin-top: 2px;'>
                        Analisi integrata su <b>{n_corr} match</b> ({tot_pts_gps:,} punti disputati · {tot_dist_km:.1f} km percorsi · {tot_ore_gps:.1f} ore di gara)
                    </div>
                </div>
                <div style='display: flex; gap: 8px;'>
                    <span style='background: white; border: 1px solid #cbd5e1; border-radius: 6px; padding: 4px 10px; font-size: 11.5px; font-weight: 700; color: #475569;'>
                        <i class='bi bi-geo-alt-fill' style='color:#0284c7;'></i> Cobolli GPS Tracker
                    </span>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # =================================================================
            # 1. COSTO FISICO DEL PUNTO (METRICHE PER-POINT)
            # =================================================================
            st.markdown(f"""
            <div style='font-size: 16px; font-weight: 900; color: #0f172a; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 12px; display: flex; align-items: center; gap: 8px;'>
                <i class='bi bi-speedometer2' style='color: #0ea5e9;'></i>
                {tr("1. Costo Fisico del Punto (Metriche 'Per Point')", "1. Physical Cost of the Point ('Per Point' Metrics)")}
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
                    f"~1 {tr('cambio di direzione ogni', 'change of direction every')} {1.0 / acc_dec_pt_avg:.1f} {tr('punti', 'pts')}" if acc_dec_pt_avg > 0 else "N/D",
                    "#ea580c"
                ), unsafe_allow_html=True)

            # Grafico Temporale Metri per Punto
            df_corr_sorted = df_corr.sort_values('date_obj', ascending=True).copy()
            fig_m_pt = go.Figure()

            # Linea media
            fig_m_pt.add_hline(
                y=m_pt_avg,
                line_dash="dash",
                line_color="#94a3b8",
                annotation_text=f"Media: {m_pt_avg:.1f} m/pt",
                annotation_position="top left",
                annotation_font=dict(color="#64748b", size=11, family="Inter")
            )

            # Scatter vittorie
            df_w = df_corr_sorted[df_corr_sorted['result'] == 'Vittoria']
            if not df_w.empty:
                fig_m_pt.add_trace(go.Scatter(
                    x=df_w['date'],
                    y=df_w['m_per_point'],
                    mode='markers+lines',
                    name=tr('Vittorie (W)', 'Wins (W)'),
                    marker=dict(size=8, color='#16a34a', symbol='circle', line=dict(color='#ffffff', width=1)),
                    line=dict(color='rgba(22, 163, 74, 0.3)', width=1.5),
                    customdata=df_w[['tournament', 'opponent', 'score', 'surface', 'total_points', 'duration_str']],
                    hovertemplate="<b>%{customdata[0]}</b> (%{customdata[3]})<br>vs %{customdata[1]} · %{customdata[2]}<br><b>Metri/Punto: %{y:.1f} m</b><br>Punti: %{customdata[4]} · Durata: %{customdata[5]}<extra></extra>"
                ))

            # Scatter sconfitte
            df_l = df_corr_sorted[df_corr_sorted['result'] == 'Sconfitta']
            if not df_l.empty:
                fig_m_pt.add_trace(go.Scatter(
                    x=df_l['date'],
                    y=df_l['m_per_point'],
                    mode='markers+lines',
                    name=tr('Sconfitte (L)', 'Losses (L)'),
                    marker=dict(size=8, color='#dc2626', symbol='circle', line=dict(color='#ffffff', width=1)),
                    line=dict(color='rgba(220, 38, 38, 0.3)', width=1.5),
                    customdata=df_l[['tournament', 'opponent', 'score', 'surface', 'total_points', 'duration_str']],
                    hovertemplate="<b>%{customdata[0]}</b> (%{customdata[3]})<br>vs %{customdata[1]} · %{customdata[2]}<br><b>Metri/Punto: %{y:.1f} m</b><br>Punti: %{customdata[4]} · Durata: %{customdata[5]}<extra></extra>"
                ))

            fig_m_pt.update_layout(
                title=dict(
                    text=f"<b>{tr('Evoluzione Metri per Punto nei Match Ufficiali', 'Meters per Point Evolution in Official Matches')}</b>",
                    font=dict(size=14, color="#0f172a", family="Inter")
                ),
                xaxis=dict(showgrid=True, gridcolor="#f1f5f9", tickangle=-45, tickfont=dict(size=10, family="Inter")),
                yaxis=dict(title=tr("Metri / Punto (m)", "Meters / Point (m)"), showgrid=True, gridcolor="#f1f5f9", tickfont=dict(family="Inter")),
                plot_bgcolor="#ffffff",
                paper_bgcolor="#ffffff",
                height=350,
                margin=dict(l=40, r=20, t=50, b=50),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            st.plotly_chart(fig_m_pt, use_container_width=True)

            st.markdown("<div style='margin-top: 25px;'></div>", unsafe_allow_html=True)

            # =================================================================
            # 2. BENCHMARK VITTORIE VS SCONFITTE
            # =================================================================
            st.markdown(f"""
            <div style='font-size: 16px; font-weight: 900; color: #0f172a; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 12px; display: flex; align-items: center; gap: 8px;'>
                <i class='bi bi-trophy' style='color: #16a34a;'></i>
                {tr("2. Benchmark Prestativo: Vittorie vs Sconfitte", "2. Performance Benchmark: Wins vs Losses")}
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
                                <th style='padding: 10px 12px; text-align: left; color: #475569; font-weight: 800;'>METRICA FISICA</th>
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

                    # Box Insight Prestativo
                    st.markdown(f"""
                    <div style='background: #f8fafc; border-left: 4px solid #10b981; padding: 10px 14px; border-radius: 6px; font-size: 12px; color: #334155; margin-top: 10px;'>
                        <b>Key Takeaway:</b> Nelle partite vinte Flavio percorre <b>{w_mpt:.1f} m/punto</b> ({delta_mpt:+.1f}% rispetto alle sconfitte), confermando come la capacità di allungare lo scambio e coprire più campo sia direttamente associata all'esito positivo del match.
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
                        title=dict(text=f"<b>{tr('Confronto Profilo Fisico per Esito Match', 'Physical Profile Comparison by Outcome')}</b>", font=dict(size=13, family="Inter")),
                        plot_bgcolor="#ffffff",
                        paper_bgcolor="#ffffff",
                        height=310,
                        margin=dict(l=20, r=20, t=40, b=30),
                        yaxis=dict(showgrid=True, gridcolor="#f1f5f9"),
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                    )
                    st.plotly_chart(fig_bench, use_container_width=True)

            st.markdown("<div style='margin-top: 25px;'></div>", unsafe_allow_html=True)

            # =================================================================
            # 3. IMPATTO DELLA SUPERFICIE (CLAY VS HARD VS GRASS)
            # =================================================================
            st.markdown(f"""
            <div style='font-size: 16px; font-weight: 900; color: #0f172a; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 12px; display: flex; align-items: center; gap: 8px;'>
                <i class='bi bi-layers-half' style='color: #ea580c;'></i>
                {tr("3. Impatto della Superficie: Terra vs Cemento vs Erba", "3. Surface Impact: Clay vs Hard vs Grass")}
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

            # Grafico a dispersione Metri/Punto vs Decelerazioni per Superficie
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
                title=dict(text=f"<b>{tr('Dinamica di Gioco per Superficie (Metri/Punto vs Richiesta Eccentrica di Frenata)', 'Court Dynamics by Surface (Meters/Pt vs Decelerations)')}</b>", font=dict(size=13, family="Inter")),
                plot_bgcolor="#ffffff",
                paper_bgcolor="#ffffff",
                height=340,
                margin=dict(l=40, r=20, t=40, b=40),
                xaxis=dict(showgrid=True, gridcolor="#f1f5f9"),
                yaxis=dict(showgrid=True, gridcolor="#f1f5f9")
            )
            st.plotly_chart(fig_surf, use_container_width=True)

            st.markdown("<div style='margin-top: 25px;'></div>", unsafe_allow_html=True)

            # =================================================================
            # 4. DIFFICOLTÀ AVVERSARIO & TOP MATCH LOGORAMENTO
            # =================================================================
            st.markdown(f"""
            <div style='font-size: 16px; font-weight: 900; color: #0f172a; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 12px; display: flex; align-items: center; gap: 8px;'>
                <i class='bi bi-shield-shaded' style='color: #8b5cf6;'></i>
                {tr("4. Difficoltà Avversario (Ranking Tier) & Match a Massimo Logoramento", "4. Opponent Difficulty & Maximum Stress Matches")}
            </div>
            """, unsafe_allow_html=True)

            # Creazione Tier Ranking per raggruppamento
            def _assign_rank_tier(r):
                if pd.isna(r) or r <= 0: return "Oltre 100"
                if r <= 10: return "Top 10"
                if r <= 20: return "Top 20"
                if r <= 50: return "Top 50"
                if r <= 100: return "Top 100"
                return "Oltre 100"

            df_corr['rank_tier'] = df_corr['opponent_rank'].apply(_assign_rank_tier)

            tier_order = ["Top 10", "Top 20", "Top 50", "Top 100", "Oltre 100"]
            tier_agg = df_corr.groupby('rank_tier').agg(
                n=('match_id', 'count'),
                m_pt=('m_per_point', 'mean'),
                tl=('tl', 'mean'),
                pct_high=('pct_tl_high', 'mean'),
                w_rate=('result', lambda s: (s == 'Vittoria').sum() / len(s) * 100)
            ).reindex(tier_order).dropna(subset=['n']).reset_index()

            col_rk1, col_rk2 = st.columns([1.2, 1.1])
            with col_rk1:
                # Scatter Ranking Opponent vs Training Load
                fig_rk = px.scatter(
                    df_corr,
                    x='opponent_rank',
                    y='tl',
                    color='result',
                    size='total_points',
                    color_discrete_map={'Vittoria': '#16a34a', 'Sconfitta': '#dc2626'},
                    hover_data=['tournament', 'opponent', 'score', 'surface', 'm_per_point'],
                    labels={'opponent_rank': tr('Ranking Avversario ATP', 'ATP Opponent Rank'), 'tl': tr('Training Load Totale', 'Total Training Load'), 'result': tr('Esito', 'Result')}
                )
                fig_rk.update_layout(
                    title=dict(text=f"<b>{tr('Training Load in Funzione del Ranking Avversario', 'Training Load vs Opponent Ranking')}</b>", font=dict(size=13, family="Inter")),
                    plot_bgcolor="#ffffff",
                    paper_bgcolor="#ffffff",
                    height=320,
                    margin=dict(l=40, r=20, t=40, b=40),
                    xaxis=dict(showgrid=True, gridcolor="#f1f5f9", autorange="reversed"),
                    yaxis=dict(showgrid=True, gridcolor="#f1f5f9")
                )
                st.plotly_chart(fig_rk, use_container_width=True)

            with col_rk2:
                st.markdown(f"""
                <div style='font-size: 13px; font-weight: 800; color: #0f172a; margin-bottom: 8px; text-transform: uppercase;'>
                    {tr("Top 5 Match a Massimo Logoramento Meccanico (TL)", "Top 5 Maximum Mechanical Stress Matches (TL)")}
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

            st.markdown("<div style='margin-top: 25px;'></div>", unsafe_allow_html=True)

            # =================================================================
            # 5. EFFICIENZA DEL SERVIZIO VS RISPARMIO FISICO
            # =================================================================
            st.markdown(f"""
            <div style='font-size: 16px; font-weight: 900; color: #0f172a; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 12px; display: flex; align-items: center; gap: 8px;'>
                <i class='bi bi-lightning-charge' style='color: #f59e0b;'></i>
                {tr("5. Efficienza del Servizio vs Risparmio Fisico", "5. Serve Efficiency vs Physical Savings")}
            </div>
            """, unsafe_allow_html=True)

            # Calcolo % Punti Vinti sulla 1° Servizio
            df_corr['pct_1st_won'] = (df_corr['first_serve_points'] / df_corr['service_points'].replace(0, np.nan) * 100).fillna(0)
            
            c_srv1, c_srv2 = st.columns([1.1, 1.1])
            with c_srv1:
                # Scatter Ace vs Metri per Punto
                fig_ace = px.scatter(
                    df_corr,
                    x='aces',
                    y='m_per_point',
                    color='result',
                    trendline="ols",
                    color_discrete_map={'Vittoria': '#16a34a', 'Sconfitta': '#dc2626'},
                    labels={'aces': tr('Numero di Ace Disputati', 'Number of Aces'), 'm_per_point': tr('Metri per Punto (m/pt)', 'Meters per Point (m/pt)')}
                )
                fig_ace.update_layout(
                    title=dict(text=f"<b>{tr('Impatto degli Ace sul Volume Fisico (Metri/Punto)', 'Aces Impact on Physical Volume (Meters/Pt)')}</b>", font=dict(size=13, family="Inter")),
                    plot_bgcolor="#ffffff",
                    paper_bgcolor="#ffffff",
                    height=310,
                    margin=dict(l=40, r=20, t=40, b=40),
                    xaxis=dict(showgrid=True, gridcolor="#f1f5f9"),
                    yaxis=dict(showgrid=True, gridcolor="#f1f5f9")
                )
                st.plotly_chart(fig_ace, use_container_width=True)

            with c_srv2:
                # Confronto Match con >6 Ace vs <=6 Ace
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
    # TAB 2: ARCHIVIO PARTITE & ABBINAMENTO TELEMETRIA
    # -------------------------------------------------------------------------
    with tab_archivio:
        st.markdown(
            f"<div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; flex-wrap:wrap; gap:8px;'>"
            f"<div style='font-size:15px; font-weight:900; color:#0f172a; text-transform:uppercase; letter-spacing:0.5px;'>"
            f"<i class='bi bi-trophy-fill' style='color:#0ea5e9; margin-right:8px;'></i>"
            f"{tr('Partite Disputate', 'Played Matches')} ({tot_m})"
            f"</div>"
            f"<div style='font-size:12px; color:#64748b; font-weight:700;'>"
            f"{tr('Espandi ciascun match per vedere le statistiche di gioco e abbinare la telemetria GPS', 'Expand each match to view game stats and link GPS telemetry')}"
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
            has_auto_gps = False
            sess_in_date = df_gps_ath[df_gps_ath['Date'] == dt_str] if not df_gps_ath.empty else pd.DataFrame()
            if not is_linked and not sess_in_date.empty:
                has_auto_gps = any(t in str(sess_in_date['Tipologia Sessione'].values).lower() for t in ['match', 'torneo'])

            if is_linked:
                gps_badge = "<span style='background:rgba(14,165,233,0.12); color:#0284c7; font-weight:800; font-size:10.5px; padding:2px 7px; border-radius:5px;'><i class='bi bi-broadcast-pin'></i> GPS MANUAL</span>"
            elif has_auto_gps:
                gps_badge = "<span style='background:rgba(16,185,129,0.12); color:#059669; font-weight:800; font-size:10.5px; padding:2px 7px; border-radius:5px;'><i class='bi bi-check-circle-fill'></i> GPS AUTO</span>"
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
                        f"{tr('Telemetria GPS / IMU Abbinata', 'Linked GPS / IMU Telemetry')}</div>",
                        unsafe_allow_html=True
                    )

                    if is_linked:
                        link_info = gps_links[m_id]
                        sess_nm = link_info.get("session_name", "Sessione Match")
                        tl_val = link_info.get("tl", 0)
                        tlh_val = link_info.get("tl_high", 0)
                        pct_tlh = (tlh_val / tl_val * 100) if tl_val > 0 else 0.0
                        dist_val = link_info.get("dist", 0)
                        min_val = link_info.get("min", 0)
                        acc_val = link_info.get("acc", 0)
                        dec_val = link_info.get("dec", 0)
                        m_pt = (dist_val / tot_p) if tot_p > 0 else 0

                        st.markdown(
                            f"<div style='background:#f8fafc; border:1.5px solid #0ea5e9; border-radius:8px; padding:12px 14px; margin-bottom:10px;'>"
                            f"<div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;'>"
                            f"<span style='font-size:11px; font-weight:800; color:#0284c7; text-transform:uppercase;'><i class='bi bi-check-circle-fill'></i> SESSIONE COLLEGATA</span>"
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

                        if st.button(tr("Scollega Sessione GPS", "Unlink GPS Session"), key=f"unlink_{m_id}", icon=":material/link_off:"):
                            remove_match_gps_link(m_id)
                            st.success(tr("Sessione scollegata con successo.", "GPS session unlinked successfully."))
                            st.rerun()

                    else:
                        if sess_in_date.empty:
                            st.info(tr(f"Nessuna acquisizione GPS registrata nel database il {dt_str}.", f"No GPS acquisition recorded in database on {dt_str}."))
                        else:
                            st.markdown(
                                f"<div style='font-size:11.5px; color:#475569; margin-bottom:6px;'>"
                                f"{tr('Trovate', 'Found')} <b>{len(sess_in_date)}</b> {tr('sessioni GPS in questa data. Seleziona quella da abbinare:', 'GPS sessions on this date. Select which one to pair:')}</div>",
                                unsafe_allow_html=True
                            )

                            opzioni_sess = []
                            for s_idx, s_row in sess_in_date.iterrows():
                                s_name = str(s_row.get("Session", f"Sessione {s_idx}"))
                                s_tipo = str(s_row.get("Tipologia Sessione", ""))
                                s_tl = get_val(s_row, "Training Load", 0)
                                s_min = get_val(s_row, "Minuti", 0)
                                label_opt = f"{s_name} [{s_tipo}] · {s_min:.0f}min · TL {s_tl:.0f}"
                                opzioni_sess.append((label_opt, s_row))

                            sel_opt_label = st.selectbox(
                                tr("Seleziona Sessione GPS:", "Select GPS Session:"),
                                options=[opt[0] for opt in opzioni_sess],
                                key=f"sel_sess_{m_id}"
                            )

                            if st.button(tr("Abbina Sessione GPS a questo Match", "Pair GPS Session to this Match"), key=f"link_{m_id}", type="primary", icon=":material/link:"):
                                chosen_row = next(opt[1] for opt in opzioni_sess if opt[0] == sel_opt_label)
                                link_data = {
                                    "session_name": str(chosen_row.get("Session", "")),
                                    "tipologia": str(chosen_row.get("Tipologia Sessione", "")),
                                    "tl": float(get_val(chosen_row, "Training Load", 0)),
                                    "tl_high": float(get_val(chosen_row, "TL_High", 0)),
                                    "dist": float(get_val(chosen_row, "DISTANCE", 0)),
                                    "min": float(get_val(chosen_row, "Minuti", 0)),
                                    "player_load": float(get_val(chosen_row, "Player Load", 0)),
                                    "acc": float(get_val(chosen_row, "High Accel IMU", 0)),
                                    "dec": float(get_val(chosen_row, "High Decel IMU", 0)),
                                    "date": dt_str
                                }
                                save_match_gps_link(m_id, link_data)
                                st.success(tr("Sessione GPS abbinata con successo!", "GPS Session paired successfully!"))
                                st.rerun()

        # Download CSV
        st.markdown("<div style='margin-top: 25px;'></div>", unsafe_allow_html=True)
        with st.container(border=True):
            d_c1, d_c2 = st.columns([2, 1])
            with d_c1:
                st.markdown(
                    f"<div style='font-size:13px; font-weight:800; color:#0f172a;'>"
                    f"{tr('Esporta Tabella Match Selezionati', 'Export Selected Matches Table')}</div>"
                    f"<div style='font-size:11.5px; color:#64748b;'>"
                    f"{tr('Scarica l archivio filtrato in formato CSV con tutte le metriche tecniche e i link GPS.', 'Download the filtered dataset in CSV format with all technical metrics and GPS links.')}</div>",
                    unsafe_allow_html=True
                )
            with d_c2:
                csv_data = df_f.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label=tr("Scarica CSV Match", "Download Matches CSV"),
                    data=csv_data,
                    file_name=f"cobolli_matches_{data_inizio.strftime('%Y%m%d') if data_inizio else 'all'}.csv",
                    mime="text/csv",
                    use_container_width=True,
                    icon=":material/download:"
                )
