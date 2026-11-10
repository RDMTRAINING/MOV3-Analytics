import os
import re
import json
import datetime
from datetime import timedelta
import pandas as pd
import streamlit as st

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

    # Se l'atleta non è Cobolli, mostriamo info
    if not is_cobolli:
        st.info(tr(
            f"Al momento l'archivio dettagliato dei match punto-a-punto è configurato per Flavio Cobolli. Seleziona Flavio Cobolli dal menu laterale per esplorare lo storico.",
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
        
        # Filtro Data Inizio
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

        # Seconda riga filtri avanzati: ricerca testo e ranking
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
                [tr("Tutti i Match", "All Matches"), tr("Solo con GPS Abbinato", "Only with Linked GPS"), tr("Solo senza GPS Abbinato", "Only without Linked GPS")],
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

    # Filtro stato GPS
    if filtro_gps_link == tr("Solo con GPS Abbinato", "Only with Linked GPS"):
        df_f = df_f[df_f["match_id"].isin(gps_links.keys())]
    elif filtro_gps_link == tr("Solo senza GPS Abbinato", "Only without Linked GPS"):
        df_f = df_f[~df_f["match_id"].isin(gps_links.keys())]

    # Ordina per data decrescente (più recenti prima)
    df_f = df_f.sort_values("date_obj", ascending=False).reset_index(drop=True)

    # =========================================================================
    # KPI CARDS RIASSUNTIVE SUI MATCH FILTRATI
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

    tot_points = int(df_f["total_points"].sum())
    avg_points = (tot_points / tot_m) if tot_m > 0 else 0

    linked_gps_count = sum(1 for mid in df_f["match_id"] if mid in gps_links)
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
                f"{avg_points:.0f} {tr('punti medi giocati per partita', 'avg points played per match')}",
                "#f59e0b"
            ),
            unsafe_allow_html=True
        )
    with k4:
        st.markdown(
            card_kpi(
                tr("Abbinamento GPS / IMU", "GPS / IMU Linked"),
                f"<span style='font-size:25px; font-weight:900; color:#0f172a;'>{linked_gps_count} <span style='font-size:16px; color:#64748b;'>/ {tot_m}</span></span>",
                f"<span style='color:#0284c7; font-weight:800;'>{pct_gps_linked:.0f}%</span> {tr('match correlati con telemetria', 'matches paired with telemetry')}",
                "#8b5cf6"
            ),
            unsafe_allow_html=True
        )

    st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)

    if df_f.empty:
        st.info(tr("Nessun match corrisponde ai filtri selezionati.", "No matches match the selected filters."))
        return

    # =========================================================================
    # ELENCO DETTAGLIATO MATCH CON SEZIONE DI ABBINAMENTO GPS
    # =========================================================================
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

    # Paginazione per non sovraccaricare la visualizzazione con 400 righe tutte insieme
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

        # Colori e badge
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
            surf_bg = "#ffedd5"
            surf_fg = "#c2410c"
        elif surf == "Grass":
            surf_bg = "#ecfdf5"
            surf_fg = "#047857"
        else:
            surf_bg = "#e0f2fe"
            surf_fg = "#0369a1"

        rank_opp_str = f"#{int(opp_rank)}" if pd.notna(opp_rank) and opp_rank else "N/R"
        rank_cob_str = f"#{int(cob_rank)}" if pd.notna(cob_rank) and cob_rank else ""

        is_linked = m_id in gps_links
        gps_badge = "<span style='background:rgba(14,165,233,0.12); color:#0284c7; font-weight:800; font-size:10.5px; padding:2px 7px; border-radius:5px;'><i class='bi bi-broadcast-pin'></i> GPS LINKED</span>" if is_linked else "<span style='background:#f8fafc; color:#94a3b8; font-weight:700; font-size:10.5px; padding:2px 7px; border-radius:5px;'>NO GPS</span>"

        expander_title = f"{'🟢' if res == 'Vittoria' else '🔴'} {dt_str} · {tourn} ({surf}) — vs {opp} ({score})"

        with st.expander(expander_title, expanded=False):
            # Header info card
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

            # 2 Colonne: Sinistra Statistiche Tennis, Destra Telemetria GPS
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

                # Se già abbinato, mostriamo i dati salvati
                if is_linked:
                    link_info = gps_links[m_id]
                    sess_nm = link_info.get("session_name", "Sessione Match")
                    tl_val = link_info.get("tl", 0)
                    tlh_val = link_info.get("tl_high", 0)
                    pct_tlh = (tlh_val / tl_val * 100) if tl_val > 0 else 0.0
                    dist_val = link_info.get("dist", 0)
                    min_val = link_info.get("min", 0)
                    pl_val = link_info.get("player_load", 0)
                    acc_val = link_info.get("acc", 0)
                    dec_val = link_info.get("dec", 0)

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
                        f"<div style='font-size:9.5px; font-weight:800; color:#64748b;'>TL HIGH</div>"
                        f"<div style='font-size:16px; font-weight:900; color:#ea580c;'>{tlh_val:.0f} <span style='font-size:10px; font-weight:700;'>({pct_tlh:.0f}%)</span></div>"
                        f"</div>"
                        f"<div style='background:white; border:1px solid #e2e8f0; border-radius:6px; padding:6px;'>"
                        f"<div style='font-size:9.5px; font-weight:800; color:#64748b;'>DISTANZA GPS</div>"
                        f"<div style='font-size:16px; font-weight:900; color:#10b981;'>{dist_val:.0f} m</div>"
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
                    # Cerca sessioni GPS registrate in quella data
                    sess_in_date = df_gps_ath[df_gps_ath['Date'] == dt_str] if not df_gps_ath.empty else pd.DataFrame()

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

    # =========================================================================
    # PULSANTE DOWNLOAD DATI MATCH FILTRATI
    # =========================================================================
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
