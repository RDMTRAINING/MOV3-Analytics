# Copyright 2026 Riccardo Di Maio - M0V3 S.r.l. Tutti i diritti riservati.
# Proprietary Sports Science & Clinical Performance Intelligence Architecture.
import os
import re
import secrets
import datetime
from datetime import timedelta
import pandas as pd
import numpy as np
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
    render_print_header,
    render_page_header,
    render_meta_bar,
    render_action_bar,
    render_tab_navigation,
    render_scientific_methodology_box,
)
from utils import (
    supabase,
    supabase_admin,
    CANONICAL_TIPOLOGIE_SESSIONE,
    COLORI_TIPOLOGIE_SESSIONE,
    get_tipologia_badge_style,
    get_tipologie_sessione,
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
    calcola_work_rate_acwr,
    render_acwr_executive_block,
    render_executive_chart_header,
    acwr_zone_meta,
    render_athlete_hero_strip,
    render_pct_progress_bar,
    render_pct_badge_cell,
    stato_acwr,
    etichetta_scostamento,
    frase_riepilogo,
    card_kpi,
    delta_puro,
    delta_confronto,
    get_atleti_associati,
    get_tutti_gli_atleti,
    slugify_name,
)
from pdf_generator import (
    crea_pdf_m0v3,
    crea_pdf_sessione_m0v3,
    crea_pdf_weekly_m0v3,
    crea_pdf_storico_m0v3,
    crea_pdf_medie_m0v3,
    crea_pdf_referto_settimanale,
)

def render_trend_settimanale(t):
    render_page_header(
        tr("Trend Settimanale", "Weekly Trend"),
        tr("Analizza il carico degli ultimi 7 giorni reali (Rolling) o lo storico delle settimane di calendario.", "Analyze the load of the last 7 real days (Rolling) or historical calendar weeks."),
        "WEEKLY WORKLOAD"
    )

    df_storico = load_local_database()
    if df_storico.empty: st.warning(t['am_no_db']); return

    if st.session_state['role'] != 'Super-Admin':
        atleti_consentiti = get_atleti_associati(st.session_state['user'].id)
        if not atleti_consentiti: st.warning(t['up_no_atl']); return
        df_storico = df_storico[df_storico['Players'].isin(atleti_consentiti)]

    giocatori_disponibili = df_storico['Players'].dropna().unique().tolist()
    if not giocatori_disponibili:
        st.warning(tr("Nessun dato disponibile.", "No data available."))
        return

    # --- Atleta Attivo (ereditato dalla Sidebar) ---
    glob_ath = st.session_state.get('selected_athlete')
    if glob_ath in giocatori_disponibili:
        giocatore_selezionato = glob_ath
    elif 'am_sel_player' in st.session_state and st.session_state['am_sel_player'] in giocatori_disponibili:
        giocatore_selezionato = st.session_state['am_sel_player']
    else:
        giocatore_selezionato = giocatori_disponibili[0]
    st.session_state['am_sel_player'] = giocatore_selezionato
    
    df_ath = df_storico[df_storico['Players'] == giocatore_selezionato].copy()
    df_ath['Date_obj'] = pd.to_datetime(df_ath['Date'], format='%d/%m/%Y', errors='coerce')
    df_ath = df_ath.dropna(subset=['Date_obj']).copy()
    
    if df_ath.empty:
        st.warning(tr("Nessuna data valida per questo atleta.", "No valid date for this athlete."))
        return

    # Striscia Compatta Identità Atleta MOV3
    render_athlete_hero_strip(giocatore_selezionato, df_atleta=df_ath)

    # --- GESTIONE PERMESSI GLOBALE TREND SETTIMANALE ---
    if st.session_state['role'] == 'Super-Admin': 
        report_abilitati = CATALOGO_REPORT.get("Trend Settimanale", [])
    else:
        try:
            res_rep = supabase.table('moduli_report').select('nome_report').eq('profilo_id', st.session_state['user'].id).eq('area', 'Trend Settimanale').execute()
            report_abilitati = [r['nome_report'] for r in res_rep.data] if res_rep.data else []
        except: 
            report_abilitati = []
    if not report_abilitati:
        report_abilitati = CATALOGO_REPORT.get("Trend Settimanale", [])

    # Pre-calcolo settimane di calendario e dataset reale per ACWR
    df_ath['Week_Start'] = df_ath['Date_obj'] - pd.to_timedelta(df_ath['Date_obj'].dt.dayofweek, unit='d')
    df_ath['Week_End'] = df_ath['Week_Start'] + pd.to_timedelta(6, unit='d')
    df_ath['Week_Label'] = df_ath['Week_Start'].dt.strftime('%d/%m/%Y') + " - " + df_ath['Week_End'].dt.strftime('%d/%m/%Y')

    oggi_d = datetime.date.today()
    curr_mon_d = oggi_d - timedelta(days=oggi_d.weekday())
    
    if not df_ath.empty:
        min_date_d = df_ath['Date_obj'].min().date()
        min_mon_d = min_date_d - timedelta(days=min_date_d.weekday())
    else:
        min_mon_d = curr_mon_d - timedelta(weeks=26)
    
    all_week_labels_set = set(df_ath['Week_Label'].unique().tolist())
    cur_iter_d = min_mon_d
    while cur_iter_d <= curr_mon_d:
        w_end_d = cur_iter_d + timedelta(days=6)
        all_week_labels_set.add(f"{cur_iter_d.strftime('%d/%m/%Y')} - {w_end_d.strftime('%d/%m/%Y')}")
        cur_iter_d += timedelta(days=7)

    settimane_disponibili = sorted(
        list(all_week_labels_set),
        key=lambda x: pd.to_datetime(x.split(" - ")[0], format='%d/%m/%Y'),
        reverse=True
    )

    # Include sia sessioni reali che simulate per ricostruire il carico effettivo sostenuto dall'atleta
    df_ath_real = df_ath.copy()
    col_acwr = ['Minuti', 'Training Load', 'TL_High', 'High Decel IMU', 'High Accel IMU', 'Azioni Int. IMU >2']
    for c_a in col_acwr:
        if c_a not in df_ath_real.columns:
            df_ath_real[c_a] = 0
    df_ath_real[col_acwr] = df_ath_real[col_acwr].apply(pd.to_numeric, errors='coerce').fillna(0)

    day_names_full = [
        tr("Lunedì", "Monday"), tr("Martedì", "Tuesday"), tr("Mercoledì", "Wednesday"),
        tr("Giovedì", "Thursday"), tr("Venerdì", "Friday"), tr("Sabato", "Saturday"), tr("Domenica", "Sunday")
    ]
    day_names_short = [
        tr("Lun", "Mon"), tr("Mar", "Tue"), tr("Mer", "Wed"),
        tr("Gio", "Thu"), tr("Ven", "Fri"), tr("Sab", "Sat"), tr("Dom", "Sun")
    ]

    def _compute_acwr_window(ac_start, ac_end):
        b_end = ac_start - timedelta(days=1)
        b_start = b_end - timedelta(days=27)
        df_w = df_ath_real[(df_ath_real['Date_obj'] >= ac_start) & (df_ath_real['Date_obj'] <= ac_end)]
        df_b = df_ath_real[(df_ath_real['Date_obj'] >= b_start) & (df_ath_real['Date_obj'] <= b_end)]
        val_ac = df_w[col_acwr].sum().fillna(0)
        if not df_b.empty:
            blocchi = calcola_blocchi_baseline(df_ath_real, b_end, 7.0)
            val_ch = (df_b[col_acwr].sum() / blocchi).fillna(0)
        else:
            val_ch = pd.Series(0.0, index=col_acwr)
        return val_ac, val_ch, b_start, b_end

    def _render_progressive_week_strip(w_start_dt, selected_day_idx, val_ch_week):
        cards_html = ""
        for d_i in range(7):
            d_cur = w_start_dt + timedelta(days=d_i)
            df_cum = df_ath_real[(df_ath_real['Date_obj'] >= w_start_dt) & (df_ath_real['Date_obj'] <= d_cur)]
            v_cum = df_cum[col_acwr].sum().fillna(0)
            pct_tl_d = (v_cum['Training Load'] / val_ch_week['Training Load'] * 100.0) if val_ch_week['Training Load'] > 0 else 0.0
            pct_min_d = (v_cum['Minuti'] / val_ch_week['Minuti'] * 100.0) if val_ch_week['Minuti'] > 0 else 0.0
            pct_az_d = (v_cum['Azioni Int. IMU >2'] / val_ch_week['Azioni Int. IMU >2'] * 100.0) if val_ch_week['Azioni Int. IMU >2'] > 0 else 0.0
            pct_vol_d = (pct_min_d + pct_tl_d + pct_az_d) / 3.0 if any(val_ch_week[k] > 0 for k in ['Minuti', 'Training Load', 'Azioni Int. IMU >2']) else 0.0
            _, z_col_d, _, _ = acwr_zone_meta(pct_tl_d)
            is_sel = (d_i == selected_day_idx)
            is_sun = (d_i == 6)
            brd_style = "2px solid #0ea5e9" if is_sel else ("1.5px dashed #10b981" if is_sun else "1px solid #e2e8f0")
            bg_card = "#f0f9ff" if is_sel else "#ffffff"
            sun_tag = "<span style='font-size:8.5px; font-weight:800; color:#10b981; background:#ecfdf5; padding:1px 5px; border-radius:4px; margin-left:4px;'>= 7d ROLLING</span>" if is_sun else ""
            cards_html += (
                f"<div style='flex:1; min-width:105px; background:{bg_card}; border:{brd_style}; border-radius:10px; padding:10px 10px; text-align:center; box-shadow:0 1px 3px rgba(15,23,42,0.04);'>"
                f"<div style='font-size:10.5px; font-weight:800; color:#0f172a; text-transform:uppercase;'>{day_names_short[d_i]} {d_cur.strftime('%d/%m')}{sun_tag}</div>"
                f"<div style='font-size:9.5px; color:#64748b; font-weight:600; margin-top:1px;'>{tr('Giorno', 'Day')} {d_i+1}/7</div>"
                f"<div style='font-size:20px; font-weight:900; color:{z_col_d}; margin:5px 0 2px 0;'>{pct_tl_d:.0f}%</div>"
                f"<div style='font-size:9.5px; font-weight:700; color:#475569;'>TL: {v_cum['Training Load']:.0f} | Vol: {pct_vol_d:.0f}%</div>"
                f"</div>"
            )

        lbl_strip_hdr = tr(
            "PROGRESSIONE GIORNALIERA % RAGGIUNGIMENTO CARICO CRONICO (DA LUNEDÌ A DOMENICA)",
            "DAILY PROGRESSIVE % OF CHRONIC LOAD REACHED (MONDAY TO SUNDAY)"
        )
        lbl_strip_note = tr(
            "Da Lunedì a Sabato mostra il carico cumulato della settimana; la Domenica (7/7 gg) coincide al 100% con l'analisi 7 Days Rolling.",
            "From Monday to Saturday shows cumulative week-to-date load; on Sunday (7/7 days) it coincides 100% with the 7 Days Rolling analysis."
        )
        st.markdown(
            "<div style='background:#f8fafc; border:1px solid #e2e8f0; border-radius:12px; padding:12px 16px; margin-bottom:16px; font-family:\"Inter\",sans-serif;'>"
            "<div style='display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; margin-bottom:10px;'>"
            f"<span style='font-size:11px; font-weight:800; color:#0f172a; text-transform:uppercase; letter-spacing:0.05em;'>{lbl_strip_hdr}</span>"
            f"<span style='font-size:11px; font-weight:600; color:#0284c7;'>{lbl_strip_note}</span>"
            "</div>"
            f"<div style='display:flex; gap:8px; flex-wrap:wrap;'>{cards_html}</div>"
            "</div>",
            unsafe_allow_html=True
        )

    def _render_daily_7d_table_and_charts(df_plot_days, banner_title, banner_sub, key_prefix):
        th_d = tr("Giorno & Data", "Day & Date")
        th_az = tr('Azioni >2"', 'Actions >2"')
        th_tot = tr("TOTALE PERIODO", "PERIOD TOTAL")
        rows_d_html = ""
        for idx_r, r_d in df_plot_days.iterrows():
            bg_d = "#ffffff" if idx_r % 2 == 0 else "#f8fafc"
            is_active = float(r_d['Minuti']) > 0 or float(r_d['Training Load']) > 0
            op_txt = "#0f172a" if is_active else "#94a3b8"
            rows_d_html += (
                f"<tr style='background:{bg_d}; border-bottom:1px solid #f1f5f9;'>"
                f"<td style='padding:11px 16px; font-weight:800; color:#0f172a; font-size:13px;'>{r_d['DayName']} <span style='color:#64748b; font-weight:600;'>({r_d['ShortDate']})</span></td>"
                f"<td style='padding:11px 10px; text-align:center; font-weight:800; color:{op_txt}; font-size:14.5px;'>{r_d['Minuti']:.0f} min</td>"
                f"<td style='padding:11px 10px; text-align:center; font-weight:900; color:#0ea5e9; font-size:15.5px;'>{r_d['Training Load']:.0f}</td>"
                f"<td style='padding:11px 10px; text-align:center; font-weight:800; color:#ef4444; font-size:14.5px;'>{r_d['TL_High']:.0f}</td>"
                f"<td style='padding:11px 10px; text-align:center; font-weight:800; color:#10b981; font-size:14.5px;'>{r_d['High Accel IMU']:.0f}</td>"
                f"<td style='padding:11px 10px; text-align:center; font-weight:800; color:#f59e0b; font-size:14.5px;'>{r_d['High Decel IMU']:.0f}</td>"
                f"<td style='padding:11px 10px; text-align:center; font-weight:800; color:#8b5cf6; font-size:14.5px;'>{r_d['Azioni Int. IMU >2']:.0f}</td>"
                f"</tr>"
            )
        rows_d_html += (
            "<tr style='background:#f0f9ff; border-top:2px solid #bae6fd;'>"
            f"<td style='padding:12px 16px; font-weight:900; color:#0284c7; font-size:12.5px; text-transform:uppercase;'>{th_tot}</td>"
            f"<td style='padding:12px 10px; text-align:center; font-weight:900; color:#0f172a; font-size:16px;'>{df_plot_days['Minuti'].sum():.0f} min</td>"
            f"<td style='padding:12px 10px; text-align:center; font-weight:900; color:#0284c7; font-size:17px;'>{df_plot_days['Training Load'].sum():.0f}</td>"
            f"<td style='padding:12px 10px; text-align:center; font-weight:900; color:#dc2626; font-size:16px;'>{df_plot_days['TL_High'].sum():.0f}</td>"
            f"<td style='padding:12px 10px; text-align:center; font-weight:900; color:#059669; font-size:16px;'>{df_plot_days['High Accel IMU'].sum():.0f}</td>"
            f"<td style='padding:12px 10px; text-align:center; font-weight:900; color:#d97706; font-size:16px;'>{df_plot_days['High Decel IMU'].sum():.0f}</td>"
            f"<td style='padding:12px 10px; text-align:center; font-weight:900; color:#7c3aed; font-size:16px;'>{df_plot_days['Azioni Int. IMU >2'].sum():.0f}</td>"
            "</tr>"
        )
        st.markdown(
            "<div style='background:#ffffff; border-radius:14px; border:1px solid #e2e8f0; box-shadow:0 4px 12px -2px rgba(15,23,42,0.05); overflow:hidden; margin-top:16px; margin-bottom:18px; font-family:\"Inter\",sans-serif;'>"
            "<div style='background:linear-gradient(135deg, #0f172a 0%, #1e293b 100%); padding:13px 18px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;'>"
            f"<span style='color:#ffffff; font-size:13px; font-weight:800; text-transform:uppercase; letter-spacing:0.06em;'>{banner_title}</span>"
            f"<span style='color:#38bdf8; font-size:11px; font-weight:700;'>{banner_sub}</span>"
            "</div>"
            "<table style='width:100%; border-collapse:collapse;'>"
            "<thead><tr style='background:#f8fafc; border-bottom:2px solid #e2e8f0;'>"
            f"<th style='text-align:left; padding:11px 16px; color:#475569; font-size:10.5px; font-weight:800; text-transform:uppercase;'>{th_d}</th>"
            "<th style='text-align:center; padding:11px 10px; color:#475569; font-size:10.5px; font-weight:800; text-transform:uppercase;'>Time (min)</th>"
            "<th style='text-align:center; padding:11px 10px; color:#0284c7; font-size:10.5px; font-weight:800; text-transform:uppercase;'>Training Load</th>"
            "<th style='text-align:center; padding:11px 10px; color:#dc2626; font-size:10.5px; font-weight:800; text-transform:uppercase;'>TL High</th>"
            "<th style='text-align:center; padding:11px 10px; color:#059669; font-size:10.5px; font-weight:800; text-transform:uppercase;'>High Acc</th>"
            "<th style='text-align:center; padding:11px 10px; color:#d97706; font-size:10.5px; font-weight:800; text-transform:uppercase;'>High Dec</th>"
            f"<th style='text-align:center; padding:11px 10px; color:#7c3aed; font-size:10.5px; font-weight:800; text-transform:uppercase;'>{th_az}</th>"
            f"</tr></thead><tbody>{rows_d_html}</tbody></table></div>",
            unsafe_allow_html=True
        )

        c_r1, c_r2 = st.columns(2)
        with c_r1:
            with st.container(border=True):
                st.markdown(render_executive_chart_header(
                    tr("Carico Energetico Giornaliero (TL vs TL High)", "Daily Energy Load (TL vs TL High)"),
                    pills=[
                        ("Tot TL", f"{df_plot_days['Training Load'].sum():.0f}", "#38bdf8"),
                        ("Tot TL High", f"{df_plot_days['TL_High'].sum():.0f}", "#f87171"),
                    ],
                    accent="#0ea5e9"
                ), unsafe_allow_html=True)
                max_tl_y = max(float(df_plot_days['Training Load'].max()), 10.0) * 1.25
                fig_tl_7 = go.Figure()
                fig_tl_7.add_trace(go.Bar(name='Training Load', x=df_plot_days['Label'], y=df_plot_days['Training Load'], marker_color='#0ea5e9', text=[f"{v:.0f}" if v > 0 else "" for v in df_plot_days['Training Load']], textposition='outside', cliponaxis=False))
                fig_tl_7.add_trace(go.Bar(name='TL High', x=df_plot_days['Label'], y=df_plot_days['TL_High'], marker_color='#ef4444', text=[f"{v:.0f}" if v > 0 else "" for v in df_plot_days['TL_High']], textposition='outside', cliponaxis=False))
                fig_tl_7.update_layout(height=310, barmode='group', paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', margin=dict(l=10, r=10, t=20, b=20), yaxis=dict(showgrid=True, gridcolor='#f1f5f9', range=[0, max_tl_y]), showlegend=False)
                st.plotly_chart(fig_tl_7, use_container_width=True, key=f"{key_prefix}_tl_bar")
        with c_r2:
            with st.container(border=True):
                st.markdown(render_executive_chart_header(
                    tr("Impatto Biomeccanico & Alta Intensità", "Biomechanical Impact & High Intensity"),
                    pills=[
                        ("Acc", f"{df_plot_days['High Accel IMU'].sum():.0f}", "#34d399"),
                        ("Dec", f"{df_plot_days['High Decel IMU'].sum():.0f}", "#fbbf24"),
                        (th_az, f"{df_plot_days['Azioni Int. IMU >2'].sum():.0f}", "#c084fc"),
                    ],
                    accent="#8b5cf6"
                ), unsafe_allow_html=True)
                max_mc_y = max(float(df_plot_days['High Accel IMU'].max()), float(df_plot_days['High Decel IMU'].max()), float(df_plot_days['Azioni Int. IMU >2'].max()), 10.0) * 1.25
                fig_mec_7 = go.Figure()
                fig_mec_7.add_trace(go.Bar(name='Acc', x=df_plot_days['Label'], y=df_plot_days['High Accel IMU'], marker_color='#10b981', text=[f"{v:.0f}" if v > 0 else "" for v in df_plot_days['High Accel IMU']], textposition='outside', cliponaxis=False))
                fig_mec_7.add_trace(go.Bar(name='Dec', x=df_plot_days['Label'], y=df_plot_days['High Decel IMU'], marker_color='#f97316', text=[f"{v:.0f}" if v > 0 else "" for v in df_plot_days['High Decel IMU']], textposition='outside', cliponaxis=False))
                fig_mec_7.add_trace(go.Bar(name=th_az, x=df_plot_days['Label'], y=df_plot_days['Azioni Int. IMU >2'], marker_color='#8b5cf6', text=[f"{v:.0f}" if v > 0 else "" for v in df_plot_days['Azioni Int. IMU >2']], textposition='outside', cliponaxis=False))
                fig_mec_7.update_layout(height=310, barmode='group', paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', margin=dict(l=10, r=10, t=20, b=20), yaxis=dict(showgrid=True, gridcolor='#f1f5f9', range=[0, max_mc_y]), showlegend=False)
                st.plotly_chart(fig_mec_7, use_container_width=True, key=f"{key_prefix}_mec_bar")

    # --- MASTER TABS (PERSISTENTI & REATTIVI M0V3) ---
    T_STORICO = tr("Analisi per Settimana (Storico)", "Weekly Analysis (Historical)")
    T_ROLLING = tr("Last 7 Days (Rolling)", "Last 7 Days (Rolling)")
    T_CUR_WEEK = tr("Current Week (Progressivo Settimana)", "Current Week (Progressive)")
    T_BENCHMARK = tr("Benchmark Giornaliero vs Medie", "Daily Benchmark vs Averages")
    T_REFERTO = tr("Referto Descrittivo Settimanale", "Weekly Descriptive Report")

    master_tabs = [T_STORICO, T_ROLLING, T_CUR_WEEK, T_BENCHMARK, T_REFERTO]
    active_master_tab = render_tab_navigation(master_tabs, key="nav_weekly_master")

    # ---------------------------------------------------------
    # TAB 1 (PRIMA PAGINA ALL'APERTURA): ANALISI PER SETTIMANA (STORICO + 5 SOTTOAREE)
    # ---------------------------------------------------------
    if active_master_tab == T_STORICO:
        settimana_selezionata = st.selectbox(tr("Seleziona Settimana Storica", "Select Historical Week"), settimane_disponibili, key="sel_week_storico")
        
        df_week = df_ath[df_ath['Week_Label'] == settimana_selezionata].copy()
        
        # Struttura fissa di 7 giorni
        week_start_date = pd.to_datetime(settimana_selezionata.split(" - ")[0], format='%d/%m/%Y')
        all_days = [week_start_date + timedelta(days=i) for i in range(7)]
        day_names = [
            tr("Lunedì", "Monday"), tr("Martedì", "Tuesday"), tr("Mercoledì", "Wednesday"),
            tr("Giovedì", "Thursday"), tr("Venerdì", "Friday"), tr("Sabato", "Saturday"), tr("Domenica", "Sunday")
        ]
        df_days = pd.DataFrame({'Date_obj': all_days, 'DayName': day_names, 'ShortDate': [d.strftime('%d/%m') for d in all_days]})
        
        # Filtro Outdoor per metriche GPS
        df_week['DISTANCE_out'] = df_week.apply(lambda r: r.get('DISTANCE', 0) if str(r.get('Ambiente', 'Outdoor')).lower() != 'indoor' else 0, axis=1)
        df_week['HML_out'] = df_week.apply(lambda r: r.get('HML Distance >25.5W', 0) if str(r.get('Ambiente', 'Outdoor')).lower() != 'indoor' else 0, axis=1)
        df_week['VHML_out'] = df_week.apply(lambda r: r.get('VHML Distance >50W', 0) if str(r.get('Ambiente', 'Outdoor')).lower() != 'indoor' else 0, axis=1)
        
        num_cols = ['Minuti', 'Training Load', 'TL_High', 'High Accel IMU', 'High Decel IMU', 'Azioni Int. IMU >2', 'Azioni Int. IMU >10', 'DISTANCE_out', 'HML_out', 'VHML_out']
        for c in num_cols:
            if c not in df_week.columns: df_week[c] = 0
        df_week[num_cols] = df_week[num_cols].apply(pd.to_numeric, errors='coerce').fillna(0)
        
        # Raggruppamento dati giornalieri
        df_grouped = df_week.groupby('Date_obj')[num_cols].sum().reset_index()
        df_plot = pd.merge(df_days, df_grouped, on='Date_obj', how='left').fillna(0)
        
        df_plot['Pct_10'] = df_plot.apply(lambda r: (r['Azioni Int. IMU >10'] / r['Azioni Int. IMU >2'] * 100) if r['Azioni Int. IMU >2'] > 0 else 0, axis=1)
        df_plot['Label'] = df_plot['DayName'] + "<br><span style='font-size:12px; color:gray;'>" + df_plot['ShortDate'] + "</span>"

        # --- CALCOLO INDICI COMPOSITI SETTIMANALI (Giorno più leggero = 1) ---
        try:
            res_pesi_w = supabase.table('impostazioni_pesi').select('pesi').eq('profilo_id', st.session_state['user'].id).execute()
            pesi_w = res_pesi_w.data[0]['pesi'] if res_pesi_w.data else {}
        except Exception:
            pesi_w = {}

        w_min = float(pesi_w.get('w_min', 1.0)); w_tl = float(pesi_w.get('w_tl', 1.0))
        w_az2 = float(pesi_w.get('w_az2', 1.0)); w_mech = float(pesi_w.get('w_mech', 1.0))
        w_tlmin = float(pesi_w.get('w_tlmin', 1.0)); w_tlhmin = float(pesi_w.get('w_tlhmin', 1.0))
        w_accmin = float(pesi_w.get('w_accmin', pesi_w.get('w_mechmin', 1.0)))
        w_decmin = float(pesi_w.get('w_decmin', pesi_w.get('w_mechmin', 1.0)))
        w_az2min = float(pesi_w.get('w_az2min', 1.0))

        df_plot['Mech_Tot'] = df_plot['High Accel IMU'] + df_plot['High Decel IMU']
        df_plot['TL/min'] = df_plot.apply(lambda r: r['Training Load'] / r['Minuti'] if r['Minuti'] > 0 else 0, axis=1)
        df_plot['TL_High/min'] = df_plot.apply(lambda r: r['TL_High'] / r['Minuti'] if r['Minuti'] > 0 else 0, axis=1)
        df_plot['Acc/min'] = df_plot.apply(lambda r: r['High Accel IMU'] / r['Minuti'] if r['Minuti'] > 0 else 0, axis=1)
        df_plot['Dec/min'] = df_plot.apply(lambda r: r['High Decel IMU'] / r['Minuti'] if r['Minuti'] > 0 else 0, axis=1)
        df_plot['Az2/min'] = df_plot.apply(lambda r: r['Azioni Int. IMU >2'] / r['Minuti'] if r['Minuti'] > 0 else 0, axis=1)
        df_plot['Mech/min'] = df_plot.apply(lambda r: r['Mech_Tot'] / r['Minuti'] if r['Minuti'] > 0 else 0, axis=1)

        # Massimi storici giornalieri dell'atleta (raggruppati per giorno come df_plot: somma parametro / somma minuti)
        df_ath_num = df_ath.copy()
        cols_idx_base = ['Minuti', 'Training Load', 'TL_High', 'High Accel IMU', 'High Decel IMU', 'Azioni Int. IMU >2']
        for c_k in cols_idx_base:
            if c_k not in df_ath_num.columns: df_ath_num[c_k] = 0
        df_ath_num[cols_idx_base] = df_ath_num[cols_idx_base].apply(pd.to_numeric, errors='coerce').fillna(0)
        df_ath_num = df_ath_num.groupby('Date_obj')[cols_idx_base].sum().reset_index()
        df_ath_num['Mech_Tot'] = df_ath_num['High Accel IMU'] + df_ath_num['High Decel IMU']
        df_ath_num['TL/min'] = df_ath_num.apply(lambda r: r['Training Load'] / r['Minuti'] if r['Minuti'] > 0 else 0, axis=1)
        df_ath_num['TL_High/min'] = df_ath_num.apply(lambda r: r['TL_High'] / r['Minuti'] if r['Minuti'] > 0 else 0, axis=1)
        df_ath_num['Acc/min'] = df_ath_num.apply(lambda r: r['High Accel IMU'] / r['Minuti'] if r['Minuti'] > 0 else 0, axis=1)
        df_ath_num['Dec/min'] = df_ath_num.apply(lambda r: r['High Decel IMU'] / r['Minuti'] if r['Minuti'] > 0 else 0, axis=1)
        df_ath_num['Az2/min'] = df_ath_num.apply(lambda r: r['Azioni Int. IMU >2'] / r['Minuti'] if r['Minuti'] > 0 else 0, axis=1)
        df_ath_num['Mech/min'] = df_ath_num.apply(lambda r: r['Mech_Tot'] / r['Minuti'] if r['Minuti'] > 0 else 0, axis=1)

        m_min = max(1.0, float(df_ath_num['Minuti'].max()))
        m_tl = max(1.0, float(df_ath_num['Training Load'].max()))
        m_az = max(1.0, float(df_ath_num['Azioni Int. IMU >2'].max()))
        m_mech = max(1.0, float(df_ath_num['Mech_Tot'].max()))
        m_tlmin = max(1.0, float(df_ath_num['TL/min'].max()))
        m_tlhmin = max(1.0, float(df_ath_num['TL_High/min'].max()))
        m_accmin = max(1.0, float(df_ath_num['Acc/min'].max()))
        m_decmin = max(1.0, float(df_ath_num['Dec/min'].max()))
        m_az2min = max(1.0, float(df_ath_num['Az2/min'].max()))

        tot_w_vol = (w_min + w_tl + w_az2 + w_mech) if (w_min + w_tl + w_az2 + w_mech) > 0 else 1.0
        tot_w_wr = (w_tlmin + w_tlhmin + w_accmin + w_decmin + w_az2min) if (w_tlmin + w_tlhmin + w_accmin + w_decmin + w_az2min) > 0 else 1.0

        df_plot['Vol_Raw'] = (((df_plot['Minuti']/m_min)*100*w_min) + ((df_plot['Training Load']/m_tl)*100*w_tl) + ((df_plot['Azioni Int. IMU >2']/m_az)*100*w_az2) + ((df_plot['Mech_Tot']/m_mech)*100*w_mech)) / tot_w_vol
        df_plot['WR_Raw'] = (((df_plot['TL/min']/m_tlmin)*100*w_tlmin) + ((df_plot['TL_High/min']/m_tlhmin)*100*w_tlhmin) + ((df_plot['Acc/min']/m_accmin)*100*w_accmin) + ((df_plot['Dec/min']/m_decmin)*100*w_decmin) + ((df_plot['Az2/min']/m_az2min)*100*w_az2min)) / tot_w_wr

        pos_vol = df_plot.loc[df_plot['Minuti'] > 0, 'Vol_Raw']
        min_vol_pos = pos_vol.min() if not pos_vol.empty and pos_vol.min() > 0 else 1.0
        df_plot['Vol_Index_W'] = df_plot.apply(lambda r: (r['Vol_Raw'] / min_vol_pos) if r['Minuti'] > 0 else 0.0, axis=1)

        pos_wr = df_plot.loc[df_plot['Minuti'] > 0, 'WR_Raw']
        min_wr_pos = pos_wr.min() if not pos_wr.empty and pos_wr.min() > 0 else 1.0
        df_plot['WR_Index_W'] = df_plot.apply(lambda r: (r['WR_Raw'] / min_wr_pos) if r['Minuti'] > 0 else 0.0, axis=1)

        # --- TASTO STAMPA E VISUALIZZAZIONE ---
        if any(r_w in report_abilitati for r_w in [
            "Andamento Settimanale (Tutte le Metriche)",
            "Indici Compositi Settimanali (Volume & Work Rate)",
            "ACWR Settimanale (Acuto/Cronico)"
        ]):
            opzioni_sub_week = {
                tr("Tutte le Sottoaree (Completo)", "All Sub-areas (Full)"): "Tutte",
                tr("1. Volumi Generali", "1. General Volumes"): "Volumi_Generali",
                tr("2. Intensità & Meccanica", "2. Intensity & Mechanics"): "Intensita_Meccanica",
                tr("3. Dati GPS Outdoor", "3. Outdoor GPS Data"): "Dati_GPS_Outdoor",
                tr("4. Indici (Volume & Work Rate)", "4. Indices (Volume & Work Rate)"): "Indici_Settimanali",
                tr("5. ACWR Settimanale (Acuto/Cronico)", "5. Weekly ACWR (Acute/Chronic)"): "ACWR_Settimanale"
            }
            render_action_bar(
                meta_items=[
                    (tr("Atleta", "Athlete"), giocatore_selezionato),
                    (tr("Settimana", "Week"), settimana_selezionata)
                ],
                pdf_options=opzioni_sub_week,
                pdf_key="week",
                generate_fn=lambda codice_sub_w: crea_pdf_weekly_m0v3(
                    giocatore_selezionato, settimana_selezionata, df_plot, sottoarea=codice_sub_w, df_ath=df_ath
                ),
                filename_fn=lambda codice_sub_w: f"M0V3_Weekly_{codice_sub_w}_{slugify_name(giocatore_selezionato)}_{settimana_selezionata.replace('/', '-').replace(' ', '')}.pdf"
            )
            
            # --- TABS DI NAVIGAZIONE TREND (PERSISTENTI & REATTIVI M0V3) ---
            SUB_VOLUMI = tr("Volumi Generali", "General Volumes")
            SUB_INTENSITA = tr("Intensità & Meccanica", "Intensity & Mechanics")
            SUB_GPS = tr("Dati GPS Outdoor", "Outdoor GPS Data")
            SUB_INDICI = tr("Indici (Volume & Work Rate)", "Indices (Volume & Work Rate)")
            SUB_ACWR = tr("ACWR Settimanale (Acuto/Cronico)", "Weekly ACWR (Acute/Chronic)")

            sub_tabs = [SUB_VOLUMI, SUB_INTENSITA, SUB_GPS, SUB_INDICI, SUB_ACWR]
            active_sub_tab = render_tab_navigation(sub_tabs, key="nav_weekly_sub")

            def render_exec_weekly_bar(x_data, y_data, color, title, total_val, suffix="", chart_key=""):
                pos_vals = [float(v) for v in y_data if float(v) > 0]
                avg_active = (sum(pos_vals) / len(pos_vals)) if pos_vals else 0.0
                peak_val = max(pos_vals) if pos_vals else 0.0
                max_y_v = max(peak_val * 1.25, 10.0)

                pills = [
                    (tr("Totale 7 gg", "7d Total"), f"{total_val:.0f}{suffix}", "#38bdf8"),
                    (tr("Media Attiva", "Active Avg"), f"{avg_active:.0f}{suffix}", "#34d399"),
                    (tr("Picco", "Peak"), f"{peak_val:.0f}{suffix}", "#fbbf24"),
                ]
                with st.container(border=True):
                    st.markdown(render_executive_chart_header(title, pills=pills, accent=color), unsafe_allow_html=True)
                    fig = go.Figure(go.Bar(
                        x=x_data, y=y_data,
                        marker_color=color,
                        text=[f"<b>{v:.0f}{suffix}</b>" if v > 0 else "" for v in y_data],
                        textposition='outside',
                        cliponaxis=False,
                        textfont=dict(size=12, color='#0f172a'),
                        hovertemplate=f"%{{x}}<br>{tr('Valore', 'Value')}: <b>%{{y:.0f}}{suffix}</b><extra></extra>"
                    ))
                    if avg_active > 0:
                        fig.add_hline(
                            y=avg_active,
                            line_dash="dot",
                            line_color="#64748b",
                            annotation_text=f"{tr('Media', 'Avg')}: {avg_active:.0f}{suffix}",
                            annotation_position="top right",
                            annotation_font=dict(size=10, color="#64748b")
                        )
                    fig.update_layout(
                        height=300, margin=dict(l=10, r=10, t=20, b=20),
                        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                        yaxis=dict(showgrid=True, gridcolor='#f1f5f9', zeroline=True, zerolinecolor='#e2e8f0', range=[0, max_y_v])
                    )
                    st.plotly_chart(fig, use_container_width=True, key=chart_key)

            if active_sub_tab == SUB_VOLUMI:
                tot_min = df_plot['Minuti'].sum()
                render_exec_weekly_bar(df_plot['Label'], df_plot['Minuti'], '#10b981', tr('Tempo (Durata Giornaliera in min)', 'Daily Duration (min)'), tot_min, ' min', "w_bar_min")
                tot_tl = df_plot['Training Load'].sum()
                render_exec_weekly_bar(df_plot['Label'], df_plot['Training Load'], '#0ea5e9', tr('Training Load Globale Giornaliero', 'Daily Global Training Load'), tot_tl, '', "w_bar_tl")

            elif active_sub_tab == SUB_INTENSITA:
                tot_tlh = df_plot['TL_High'].sum()
                render_exec_weekly_bar(df_plot['Label'], df_plot['TL_High'], '#ef4444', tr('Training Load High (Alta Intensità)', 'Training Load High (High Intensity)'), tot_tlh, '', "w_bar_tlh")

                tot_acc = df_plot['High Accel IMU'].sum()
                tot_dec = df_plot['High Decel IMU'].sum()
                with st.container(border=True):
                    pills_mech = [
                        (tr("Totale High Acc", "Total High Acc"), f"{tot_acc:.0f}", "#34d399"),
                        (tr("Totale High Dec", "Total High Dec"), f"{tot_dec:.0f}", "#f87171"),
                        (tr("Rapporto Acc/Dec", "Acc/Dec Ratio"), f"{(tot_acc/tot_dec):.2f}" if tot_dec > 0 else "N/A", "#38bdf8"),
                    ]
                    st.markdown(render_executive_chart_header(tr("Accelerazioni & Decelerazioni Meccaniche IMU", "IMU Mechanical Accelerations & Decelerations"), pills=pills_mech, accent="#10b981"), unsafe_allow_html=True)
                    max_m_y = max(float(df_plot['High Accel IMU'].max()), float(df_plot['High Decel IMU'].max()), 10.0) * 1.25
                    fig_mech = go.Figure()
                    fig_mech.add_trace(go.Bar(name='High Acc IMU', x=df_plot['Label'], y=df_plot['High Accel IMU'], marker_color='#10b981', text=[f"{v:.0f}" if v > 0 else "" for v in df_plot['High Accel IMU']], textposition='outside', cliponaxis=False, textfont=dict(size=11, weight='bold', color='#0f172a'), hovertemplate="%{x}<br>Acc: %{y:.0f}<extra></extra>"))
                    fig_mech.add_trace(go.Bar(name='High Dec IMU', x=df_plot['Label'], y=df_plot['High Decel IMU'], marker_color='#ef4444', text=[f"{v:.0f}" if v > 0 else "" for v in df_plot['High Decel IMU']], textposition='outside', cliponaxis=False, textfont=dict(size=11, weight='bold', color='#0f172a'), hovertemplate="%{x}<br>Dec: %{y:.0f}<extra></extra>"))
                    fig_mech.update_layout(
                        barmode='group', height=320, showlegend=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                        yaxis=dict(showgrid=True, gridcolor='#f1f5f9', zeroline=True, zerolinecolor='#e2e8f0', range=[0, max_m_y]), margin=dict(l=10, r=10, t=20, b=15)
                    )
                    st.plotly_chart(fig_mech, use_container_width=True, key="w_bar_mech")
                    st.markdown(
                        "<div style='display:flex; justify-content:center; gap:18px; padding:7px 10px; background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; font-size:11px; font-weight:700; color:#475569;'>"
                        "<div style='display:flex; align-items:center; gap:6px;'><span style='width:12px; height:10px; border-radius:3px; background:#10b981; display:inline-block;'></span>High Accelerations IMU</div>"
                        "<div style='display:flex; align-items:center; gap:6px;'><span style='width:12px; height:10px; border-radius:3px; background:#ef4444; display:inline-block;'></span>High Decelerations IMU</div>"
                        "</div>",
                        unsafe_allow_html=True
                    )

                tot_az2 = df_plot['Azioni Int. IMU >2'].sum()
                tot_az10 = df_plot['Azioni Int. IMU >10'].sum()
                avg_pct10 = (tot_az10 / tot_az2 * 100) if tot_az2 > 0 else 0
                with st.container(border=True):
                    pills_az = [
                        (tr('Totale Azioni >2"', 'Total Actions >2"'), f"{tot_az2:.0f}", "#c084fc"),
                        (tr('Totale Azioni >10"', 'Total Actions >10"'), f"{tot_az10:.0f}", "#fbbf24"),
                        (tr('Quota >10"', 'Share >10"'), f"{avg_pct10:.1f}%", "#38bdf8"),
                    ]
                    st.markdown(render_executive_chart_header(tr('Azioni Intense IMU (>2" & Quota >10")', 'Intense IMU Actions (>2" & Share >10")'), pills=pills_az, accent="#8b5cf6"), unsafe_allow_html=True)
                    fig_az = go.Figure()
                    fig_az.add_trace(go.Bar(
                        name=tr('Azioni Totali (> 2")', 'Total Actions (> 2")'), x=df_plot['Label'], y=df_plot['Azioni Int. IMU >2'], marker_color='#8b5cf6', yaxis='y1', hovertemplate="%{x}<br>Azioni >2\": %{y:.0f}<extra></extra>"
                    ))
                    fig_az.add_trace(go.Scatter(
                        name=tr('% Azioni Lunghissime (> 10")', '% Very Long Actions (> 10")'), x=df_plot['Label'], y=df_plot['Pct_10'], mode='lines+markers+text', marker=dict(size=10, color='#f59e0b'), line=dict(width=3, color='#f59e0b'), yaxis='y2', text=[f"{v:.0f}%" if v > 0 else "" for v in df_plot['Pct_10']], textposition='top center', textfont=dict(color='#f59e0b', size=12, weight='bold'), hovertemplate="%{x}<br>Percentuale: %{y:.1f}%<extra></extra>"
                    ))
                    fig_az.update_layout(
                        height=330, showlegend=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', margin=dict(l=10, r=10, t=20, b=15),
                        yaxis=dict(title=tr('Volume Azioni (>2")', 'Actions Volume (>2")'), showgrid=True, gridcolor='#f1f5f9', rangemode='tozero'),
                        yaxis2=dict(title=tr('Percentuale (>10")', 'Percentage (>10")'), overlaying='y', side='right', range=[0, max(110, df_plot['Pct_10'].max()+10) if not df_plot['Pct_10'].empty else 110], showgrid=False),
                    )
                    st.plotly_chart(fig_az, use_container_width=True, key="w_bar_az")

            elif active_sub_tab == SUB_GPS:
                tot_dist = df_plot['DISTANCE_out'].sum()
                if tot_dist > 0:
                    tot_hml = df_plot['HML_out'].sum()
                    tot_vhml = df_plot['VHML_out'].sum()
                    c_gps1, c_gps2, c_gps3 = st.columns(3, gap="medium")
                    with c_gps1:
                        render_exec_weekly_bar(df_plot['Label'], df_plot['DISTANCE_out'], '#0ea5e9', tr('Distanza Totale (m)', 'Total Distance (m)'), tot_dist, ' m', "w_gps_dist")
                    with c_gps2:
                        render_exec_weekly_bar(df_plot['Label'], df_plot['HML_out'], '#f59e0b', 'HML >25.5W (m)', tot_hml, ' m', "w_gps_hml")
                    with c_gps3:
                        render_exec_weekly_bar(df_plot['Label'], df_plot['VHML_out'], '#ef4444', 'VHML >50W (m)', tot_vhml, ' m', "w_gps_vhml")
                else:
                    st.info(tr("Nessun dato GPS Outdoor registrato in questa settimana specifica. I dati Indoor non vengono conteggiati per le distanze.", "No Outdoor GPS data recorded in this specific week. Indoor data is not counted for distances."))

            elif active_sub_tab == SUB_INDICI:
                st.markdown(f"<h3 style='color:#0f172a;'>{tr('Indici Compositi Settimanali (Volume & Work Rate)', 'Weekly Composite Indices (Volume & Work Rate)')}</h3>", unsafe_allow_html=True)

                def create_weekly_index_chart(df_p, y_col, index_title, metrics_list):
                    import numpy as np

                    x_num = np.arange(len(df_p))
                    y_vals = df_p[y_col].values.astype(float)
                    day_labels = df_p['DayName'].tolist()

                    x_smooth = np.linspace(0, len(df_p) - 1, 350)
                    try:
                        from scipy.interpolate import make_interp_spline
                        spl = make_interp_spline(x_num, y_vals, k=3)
                        y_smooth = spl(x_smooth)
                        for idx_s, xv in enumerate(x_smooth):
                            near_i = int(round(xv))
                            if y_vals[near_i] == 0 and abs(xv - near_i) < 0.35:
                                y_smooth[idx_s] = max(0.0, y_smooth[idx_s])
                        y_smooth = np.clip(y_smooth, 0, None)
                    except Exception:
                        y_smooth = np.interp(x_smooth, x_num, y_vals)

                    max_y = max(float(np.max(y_vals)), 2.0)
                    y_top = max_y * 1.28

                    fig = go.Figure()

                    for i, v in enumerate(y_vals):
                        if v > 0:
                            fig.add_shape(
                                type="line", x0=i, y0=0, x1=i, y1=v,
                                line=dict(color="rgba(14, 165, 233, 0.35)", width=1.5)
                            )

                    fig.add_shape(
                        type="line", x0=-0.3, y0=0, x1=6.3, y1=0,
                        line=dict(color="#cbd5e1", width=1.5)
                    )

                    fig.add_trace(go.Scatter(
                        x=x_smooth, y=y_smooth,
                        mode='markers',
                        marker=dict(
                            size=9,
                            color=y_smooth,
                            colorscale=[
                                [0.0, '#34d399'],
                                [0.25, '#10b981'],
                                [0.55, '#f59e0b'],
                                [0.80, '#f97316'],
                                [1.0, '#ef4444']
                            ],
                            cmin=0, cmax=max_y,
                            showscale=False
                        ),
                        hoverinfo='skip',
                        showlegend=False
                    ))

                    text_labels = ["0" if v == 0 else ("1" if abs(v - 1.0) < 0.05 else f"{v:.1f}".replace('.', ',')) for v in y_vals]
                    fig.add_trace(go.Scatter(
                        x=x_num, y=y_vals,
                        mode='markers+text',
                        marker=dict(size=10, color='rgba(0,0,0,0)'),
                        text=text_labels,
                        textposition='top center',
                        textfont=dict(size=14, color='#334155', family='Inter, sans-serif', weight='bold'),
                        hovertemplate="<b>%{customdata}</b><br>Score: %{text}<extra></extra>",
                        customdata=day_labels,
                        showlegend=False
                    ))

                    fig.add_trace(go.Scatter(
                        x=[x_num[-1]], y=[y_vals[-1]],
                        mode='markers',
                        marker=dict(symbol='triangle-right', size=18, color='#34d399' if y_vals[-1] <= 1 else '#f59e0b'),
                        hoverinfo='skip',
                        showlegend=False
                    ))

                    metrics_html = f"<b>{index_title}</b> is a normalization of:<br>" + "<br>".join([f"- {m}" for m in metrics_list])
                    fig.add_annotation(
                        x=0.0, y=1.10, xref="paper", yref="paper", 
                        yanchor="bottom", xanchor="left",
                        text=metrics_html, showarrow=False, align="left",
                        font=dict(size=11, color="#1e293b", family="Inter, sans-serif"),
                        bgcolor="rgba(255,255,255,0.85)", bordercolor="#e2e8f0", borderwidth=1, borderpad=6
                    )

                    fig.add_annotation(
                        x=1.0, y=1.10, xref="paper", yref="paper", 
                        yanchor="bottom", xanchor="right",
                        text="<b>Day with score 1 is the lightest of the week</b>",
                        showarrow=False, align="right",
                        font=dict(size=13, color="#0f172a", family="Inter, sans-serif")
                    )

                    fig.update_layout(
                        height=420,
                        margin=dict(l=20, r=20, t=115, b=55),
                        paper_bgcolor='rgba(0,0,0,0)',
                        plot_bgcolor='rgba(0,0,0,0)',
                        xaxis=dict(
                            tickmode='array', tickvals=list(range(7)), ticktext=day_labels,
                            tickangle=-90, tickfont=dict(size=12, color='#475569', weight='bold'),
                            showgrid=False, zeroline=False, range=[-0.4, 6.4]
                        ),
                        yaxis=dict(
                            showgrid=False, zeroline=False, showticklabels=False,
                            range=[-max_y * 0.12, y_top]
                        )
                    )
                    return fig

                def render_banner_index(vertical_title, fig_obj, key_chart):
                    col_strip, col_chart = st.columns([0.06, 0.94], gap="small")
                    with col_strip:
                        st.markdown(f"""
                        <div style='background-color: #1e293b; color: white; height: 420px; border-radius: 10px 0 0 10px; display: flex; align-items: center; justify-content: center; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);'>
                            <div style='transform: rotate(-90deg); white-space: nowrap; font-weight: 800; font-size: 18px; letter-spacing: 3px; color: #f8fafc;'>{vertical_title}</div>
                        </div>
                        """, unsafe_allow_html=True)
                    with col_chart:
                        with st.container(border=True):
                            st.plotly_chart(fig_obj, use_container_width=True, key=key_chart)

                if "Indici Compositi Settimanali (Volume & Work Rate)" not in report_abilitati:
                    st.info(tr("Non hai i permessi per visualizzare questo report.", "You do not have permission to view this report."))
                else:
                    fig_vol_w = create_weekly_index_chart(
                        df_plot, 'Vol_Index_W', "VOLUME INDEX",
                        ["Duration (Time)", "Training Load", "Intense Actions >2\"", "High Accelerations & Decelerations"]
                    )
                    render_banner_index("VOLUME INDEX", fig_vol_w, "chart_vol_idx_w")

                    st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)

                    fig_wr_w = create_weekly_index_chart(
                        df_plot, 'WR_Index_W', "WORK RATE INDEX",
                        ["TL / min", "TL High / min", "High Acc / min", "High Dec / min", "Intense Actions >2\" / min"]
                    )
                    render_banner_index("WORK RATE INDEX", fig_wr_w, "chart_wr_idx_w")

            elif active_sub_tab == SUB_ACWR:
                if "ACWR Settimanale (Acuto/Cronico)" not in report_abilitati:
                    st.info(tr("Non hai i permessi per visualizzare il report ACWR Settimanale.", "You do not have permission to view the Weekly ACWR report."))
                else:
                    lbl_acwr_main_t = tr("Analisi ACWR: 7 Days Rolling vs Settimana Selezionata", "ACWR Analysis: 7 Days Rolling vs Selected Week")
                    lbl_acwr_main_p = tr(
                        "Seleziona il giorno della settimana per confrontare i 7 giorni rolling precedenti con il carico progressivo della settimana selezionata (Lunedì → Giorno scelto). Solo la Domenica (7/7 gg) le due analisi coincidono esattamente.",
                        "Select the day of the week to compare the preceding 7 rolling days with the progressive load of the selected week (Monday → Selected Day). Only on Sunday (7/7 days) do both analyses coincide."
                    )
                    st.markdown(f"<h3 style='color:#0f172a; margin-bottom:4px;'>{lbl_acwr_main_t}</h3>", unsafe_allow_html=True)
                    st.markdown(f"<p style='color:#64748b; font-size:13px; margin-bottom:14px;'>{lbl_acwr_main_p}</p>", unsafe_allow_html=True)

                    day_opts_labels = [
                        f"{day_names_full[i]} ({(week_start_date + timedelta(days=i)).strftime('%d/%m/%Y')}) — {tr('Giorno', 'Day')} {i+1}/7"
                        for i in range(7)
                    ]
                    sel_day_str = st.selectbox(
                        tr("Giorno di Riferimento nella Settimana (per Progressione Giornaliera vs 7d Rolling)", "Reference Day in Week (for Daily Progression vs 7d Rolling)"),
                        day_opts_labels,
                        index=6,
                        key="acwr_w_day_sel"
                    )
                    sel_day_idx = day_opts_labels.index(sel_day_str)
                    d_ref_w = week_start_date + timedelta(days=sel_day_idx)

                    # 1. PRIMA ANALISI: 7 DAYS ROLLING (7 giorni precedenti a d_ref_w)
                    r7_start = d_ref_w - timedelta(days=6)
                    r7_end = d_ref_w
                    val_ac_r7, val_ch_r7, b_r7_start, b_r7_end = _compute_acwr_window(r7_start, r7_end)

                    render_acwr_executive_block(
                        val_acute=val_ac_r7,
                        val_chronic=val_ch_r7,
                        str_win_range=f"{r7_start.strftime('%d/%m/%Y')} - {r7_end.strftime('%d/%m/%Y')}",
                        str_base_range=f"{b_r7_start.strftime('%d/%m/%Y')} - {b_r7_end.strftime('%d/%m/%Y')}",
                        lbl_hdr_acute=tr("Carico 7 Giorni Rolling", "7-Day Rolling Load"),
                        lbl_hdr_chronic=tr("Chronic Load 7 days / last month", "Chronic Load 7 days / last month"),
                        lbl_ctx_acute=tr("Finestra 7 gg Rolling", "7d Rolling Window"),
                        lbl_vs=tr("vs media 4 sett.", "vs 4-wk avg"),
                        chart_key="chart_acwr_hex_rolling_in_storico",
                        title_banner=tr("7 DAYS ACUTE / CHRONIC WORKLOAD RATIO (7 GIORNI ROLLING)", "7 DAYS ACUTE / CHRONIC WORKLOAD RATIO (7 DAYS ROLLING)"),
                        title_accent="#ef4444",
                    )

                    st.markdown("<div style='height: 22px;'></div>", unsafe_allow_html=True)

                    # 2. SECONDA ANALISI POSTA SOTTO: SETTIMANA SELEZIONATA (Lunedì -> d_ref_w)
                    val_ac_wk, val_ch_wk, b_wk_start, b_wk_end = _compute_acwr_window(week_start_date, d_ref_w)
                    _render_progressive_week_strip(week_start_date, sel_day_idx, val_ch_wk)

                    render_acwr_executive_block(
                        val_acute=val_ac_wk,
                        val_chronic=val_ch_wk,
                        str_win_range=f"{week_start_date.strftime('%d/%m/%Y')} - {d_ref_w.strftime('%d/%m/%Y')} ({sel_day_idx+1}/7 gg)",
                        str_base_range=f"{b_wk_start.strftime('%d/%m/%Y')} - {b_wk_end.strftime('%d/%m/%Y')}",
                        lbl_hdr_acute=tr(f"Carico Settimana ({sel_day_idx+1}/7 gg)", f"Week Load ({sel_day_idx+1}/7 d)"),
                        lbl_hdr_chronic=tr("Chronic Load 4 Weeks (28 gg / 7 gg)", "Chronic Load 4 Weeks (28d / 7d)"),
                        lbl_ctx_acute=tr("Progressivo Settimana Selezionata", "Selected Week Progressive"),
                        lbl_vs=tr("vs media 4 sett.", "vs 4-wk avg"),
                        chart_key="chart_acwr_hex_weekly_prog",
                        title_banner=tr(
                            f"WEEKLY ACUTE / CHRONIC WORKLOAD RATIO — SETTIMANA SELEZIONATA (LUN → {day_names_short[sel_day_idx].upper()})",
                            f"WEEKLY ACUTE / CHRONIC WORKLOAD RATIO — SELECTED WEEK (MON → {day_names_short[sel_day_idx].upper()})"
                        ),
                        title_accent="#0ea5e9",
                    )

    # ---------------------------------------------------------
    # TAB 2: LAST 7 DAYS (ROLLING) — STILE EXECUTIVE M0V3
    # ---------------------------------------------------------
    elif active_master_tab == T_ROLLING:
        if "Last 7 Days Load (Rolling)" not in report_abilitati:
            st.info(tr("Non hai i permessi per visualizzare il report Last 7 Days.", "You do not have permission to view the Last 7 Days report."))
        else:
            oggi_dt = pd.Timestamp.today().normalize()
            max_ath_dt = df_ath['Date_obj'].max().normalize()
            default_ref_r7 = oggi_dt if (oggi_dt - max_ath_dt).days <= 6 else max_ath_dt

            c_r7_flt1, c_r7_flt2 = st.columns([1.4, 2.6])
            with c_r7_flt1:
                sel_ref_r7_date = st.date_input(
                    tr("Data di Riferimento (Fine 7 Giorni Rolling)", "Reference Date (End of 7 Rolling Days)"),
                    value=default_ref_r7.date(),
                    key="dt_ref_last7_rolling"
                )
            d_ref_rolling = pd.Timestamp(sel_ref_r7_date).normalize()
            r7_win_start = d_ref_rolling - timedelta(days=6)
            r7_win_end = d_ref_rolling

            date_7 = [r7_win_start + timedelta(days=i) for i in range(7)]
            df_days_7 = pd.DataFrame({
                'Date_obj': date_7,
                'DayName': [day_names_short[d.dayofweek] for d in date_7],
                'ShortDate': [d.strftime('%d/%m') for d in date_7]
            })
            df_days_7['Label'] = df_days_7['DayName'] + "<br><span style='font-size:12px; color:gray;'>" + df_days_7['ShortDate'] + "</span>"

            df_7 = df_ath[(df_ath['Date_obj'] >= r7_win_start) & (df_ath['Date_obj'] <= r7_win_end)].copy()
            df_7['DISTANCE_out'] = df_7.apply(lambda r: r.get('DISTANCE', 0) if str(r.get('Ambiente', 'Outdoor')).lower() != 'indoor' else 0, axis=1)
            df_7['HML_out'] = df_7.apply(lambda r: r.get('HML Distance >25.5W', 0) if str(r.get('Ambiente', 'Outdoor')).lower() != 'indoor' else 0, axis=1)
            df_7['VHML_out'] = df_7.apply(lambda r: r.get('VHML Distance >50W', 0) if str(r.get('Ambiente', 'Outdoor')).lower() != 'indoor' else 0, axis=1)
            num_cols_7 = ['Minuti', 'Training Load', 'TL_High', 'High Accel IMU', 'High Decel IMU', 'Azioni Int. IMU >2', 'Azioni Int. IMU >10', 'DISTANCE_out', 'HML_out', 'VHML_out']
            for c in num_cols_7:
                if c not in df_7.columns:
                    df_7[c] = 0
            df_7[num_cols_7] = df_7[num_cols_7].apply(pd.to_numeric, errors='coerce').fillna(0)

            df_grouped_7 = df_7.groupby('Date_obj')[num_cols_7].sum().reset_index()
            df_plot_7 = pd.merge(df_days_7, df_grouped_7, on='Date_obj', how='left').fillna(0)

            lbl_r7_period = f"{r7_win_start.strftime('%d/%m/%Y')} - {r7_win_end.strftime('%d/%m/%Y')}"
            render_action_bar(
                meta_items=[
                    (tr("Atleta", "Athlete"), giocatore_selezionato),
                    (tr("Finestra 7 gg Rolling", "7d Rolling Window"), lbl_r7_period, True),
                ],
                pdf_options={tr("Report Last 7 Days (Rolling)", "Last 7 Days Report (Rolling)"): "Last_7_Days"},
                pdf_key="last7_roll",
                generate_fn=lambda _: crea_pdf_weekly_m0v3(
                    giocatore_selezionato, lbl_r7_period, df_plot_7, sottoarea="Last_7_Days", df_ath=df_ath, ref_date_acwr=d_ref_rolling
                ),
                filename_fn=lambda _: f"M0V3_Last7Days_{slugify_name(giocatore_selezionato)}_{d_ref_rolling.strftime('%d-%m-%Y')}.pdf"
            )

            val_ac_7r, val_ch_7r, b_7r_start, b_7r_end = _compute_acwr_window(r7_win_start, r7_win_end)
            render_acwr_executive_block(
                val_acute=val_ac_7r,
                val_chronic=val_ch_7r,
                str_win_range=lbl_r7_period,
                str_base_range=f"{b_7r_start.strftime('%d/%m/%Y')} - {b_7r_end.strftime('%d/%m/%Y')}",
                lbl_hdr_acute=tr("Carico 7 Giorni Rolling", "7-Day Rolling Load"),
                lbl_hdr_chronic=tr("Chronic Load 7 days / last month", "Chronic Load 7 days / last month"),
                lbl_ctx_acute=tr("Ultimi 7 Giorni (Rolling)", "Last 7 Days (Rolling)"),
                lbl_vs=tr("vs media 4 sett.", "vs 4-wk avg"),
                chart_key="chart_acwr_hex_tab_rolling",
                title_banner=tr("7 DAYS ACUTE / CHRONIC WORKLOAD RATIO (LAST 7 DAYS ROLLING)", "7 DAYS ACUTE / CHRONIC WORKLOAD RATIO (LAST 7 DAYS ROLLING)"),
                title_accent="#ef4444",
            )

            _render_daily_7d_table_and_charts(
                df_plot_7,
                tr("DETTAGLIO GIORNALIERO — LAST 7 DAYS ROLLING", "DAILY BREAKDOWN — LAST 7 DAYS ROLLING"),
                lbl_r7_period,
                "tab_r7"
            )

    # ---------------------------------------------------------
    # TAB 3: CURRENT WEEK (PROGRESSIVO SETTIMANA SELEZIONATA) — STILE EXECUTIVE M0V3
    # ---------------------------------------------------------
    elif active_master_tab == T_CUR_WEEK:
        if "Current Week Load (ACWR Progressivo)" not in report_abilitati and "ACWR Settimanale (Acuto/Cronico)" not in report_abilitati:
            st.info(tr("Non hai i permessi per visualizzare il report Current Week.", "You do not have permission to view the Current Week report."))
        else:
            c_cw1, c_cw2 = st.columns([1.5, 1.8])
            with c_cw1:
                settimana_cw = st.selectbox(
                    tr("Seleziona Settimana (Current / Selected Week)", "Select Week (Current / Selected Week)"),
                    settimane_disponibili,
                    index=0,
                    key="sel_week_current_tab"
                )
            cw_start_dt = pd.to_datetime(settimana_cw.split(" - ")[0], format='%d/%m/%Y')
            cw_end_dt = cw_start_dt + timedelta(days=6)

            oggi_norm = pd.Timestamp.today().normalize()
            if cw_start_dt <= oggi_norm <= cw_end_dt:
                default_cw_day_idx = int((oggi_norm - cw_start_dt).days)
            else:
                df_in_cw = df_ath_real[(df_ath_real['Date_obj'] >= cw_start_dt) & (df_ath_real['Date_obj'] <= cw_end_dt)]
                if not df_in_cw.empty:
                    default_cw_day_idx = int((df_in_cw['Date_obj'].max().normalize() - cw_start_dt).days)
                else:
                    default_cw_day_idx = 6

            cw_day_opts = [
                f"{day_names_full[i]} {(cw_start_dt + timedelta(days=i)).strftime('%d/%m/%Y')} ({tr('Giorno', 'Day')} {i+1}/7)"
                for i in range(7)
            ]
            with c_cw2:
                sel_cw_day_lbl = st.selectbox(
                    tr("Giorno della Settimana (Progressione Cumulata da Lunedì)", "Day of Week (Cumulative Progression from Monday)"),
                    cw_day_opts,
                    index=min(max(default_cw_day_idx, 0), 6),
                    key="sel_day_current_tab"
                )
            cw_day_idx = cw_day_opts.index(sel_cw_day_lbl)
            d_ref_cw = cw_start_dt + timedelta(days=cw_day_idx)

            all_cw_days = [cw_start_dt + timedelta(days=i) for i in range(7)]
            df_days_cw = pd.DataFrame({
                'Date_obj': all_cw_days,
                'DayName': day_names_short,
                'ShortDate': [d.strftime('%d/%m') for d in all_cw_days]
            })
            df_days_cw['Label'] = df_days_cw['DayName'] + "<br><span style='font-size:12px; color:gray;'>" + df_days_cw['ShortDate'] + "</span>"

            df_cw_sub = df_ath[(df_ath['Date_obj'] >= cw_start_dt) & (df_ath['Date_obj'] <= d_ref_cw)].copy()
            df_cw_sub['DISTANCE_out'] = df_cw_sub.apply(lambda r: r.get('DISTANCE', 0) if str(r.get('Ambiente', 'Outdoor')).lower() != 'indoor' else 0, axis=1)
            df_cw_sub['HML_out'] = df_cw_sub.apply(lambda r: r.get('HML Distance >25.5W', 0) if str(r.get('Ambiente', 'Outdoor')).lower() != 'indoor' else 0, axis=1)
            df_cw_sub['VHML_out'] = df_cw_sub.apply(lambda r: r.get('VHML Distance >50W', 0) if str(r.get('Ambiente', 'Outdoor')).lower() != 'indoor' else 0, axis=1)
            num_cols_cw = ['Minuti', 'Training Load', 'TL_High', 'High Accel IMU', 'High Decel IMU', 'Azioni Int. IMU >2', 'Azioni Int. IMU >10', 'DISTANCE_out', 'HML_out', 'VHML_out']
            for c in num_cols_cw:
                if c not in df_cw_sub.columns:
                    df_cw_sub[c] = 0
            df_cw_sub[num_cols_cw] = df_cw_sub[num_cols_cw].apply(pd.to_numeric, errors='coerce').fillna(0)

            df_grouped_cw = df_cw_sub.groupby('Date_obj')[num_cols_cw].sum().reset_index()
            df_plot_cw = pd.merge(df_days_cw, df_grouped_cw, on='Date_obj', how='left').fillna(0)

            render_action_bar(
                meta_items=[
                    (tr("Atleta", "Athlete"), giocatore_selezionato),
                    (tr("Settimana", "Week"), settimana_cw),
                    (tr("Progressione", "Progression"), f"Lun → {day_names_short[cw_day_idx]} ({cw_day_idx+1}/7 gg)", True),
                ],
                pdf_options={tr("Report Current Week (ACWR Progressivo)", "Current Week Report (Progressive ACWR)"): "Current_Week"},
                pdf_key="cur_week_prog",
                generate_fn=lambda _: crea_pdf_weekly_m0v3(
                    giocatore_selezionato, settimana_cw, df_plot_cw, sottoarea="Current_Week", df_ath=df_ath, ref_date_acwr=d_ref_cw
                ),
                filename_fn=lambda _: f"M0V3_CurrentWeek_{slugify_name(giocatore_selezionato)}_{d_ref_cw.strftime('%d-%m-%Y')}.pdf"
            )

            val_ac_cw, val_ch_cw, b_cw_start, b_cw_end = _compute_acwr_window(cw_start_dt, d_ref_cw)
            _render_progressive_week_strip(cw_start_dt, cw_day_idx, val_ch_cw)

            render_acwr_executive_block(
                val_acute=val_ac_cw,
                val_chronic=val_ch_cw,
                str_win_range=f"{cw_start_dt.strftime('%d/%m/%Y')} - {d_ref_cw.strftime('%d/%m/%Y')} ({cw_day_idx+1}/7 gg)",
                str_base_range=f"{b_cw_start.strftime('%d/%m/%Y')} - {b_cw_end.strftime('%d/%m/%Y')}",
                lbl_hdr_acute=tr(f"Carico Settimana ({cw_day_idx+1}/7 gg)", f"Week Load ({cw_day_idx+1}/7 d)"),
                lbl_hdr_chronic=tr("Chronic Load 4 Weeks (28 gg / 7 gg)", "Chronic Load 4 Weeks (28d / 7d)"),
                lbl_ctx_acute=tr("Settimana Selezionata (Progressivo)", "Selected Week (Progressive)"),
                lbl_vs=tr("vs media 4 sett.", "vs 4-wk avg"),
                chart_key="chart_acwr_hex_tab_cur_week",
                title_banner=tr(
                    f"WEEKLY ACUTE / CHRONIC WORKLOAD RATIO — CURRENT WEEK (LUN → {day_names_short[cw_day_idx].upper()})",
                    f"WEEKLY ACUTE / CHRONIC WORKLOAD RATIO — CURRENT WEEK (MON → {day_names_short[cw_day_idx].upper()})"
                ),
                title_accent="#0ea5e9",
            )

            _render_daily_7d_table_and_charts(
                df_plot_cw,
                tr(f"DETTAGLIO GIORNALIERO SETTIMANA (LUNEDÌ → {day_names_full[cw_day_idx].upper()})", f"WEEKLY DAILY BREAKDOWN (MONDAY → {day_names_full[cw_day_idx].upper()})"),
                f"{cw_start_dt.strftime('%d/%m/%Y')} - {d_ref_cw.strftime('%d/%m/%Y')}",
                "tab_cw"
            )

    # ---------------------------------------------------------
    # TAB 4: BENCHMARK GIORNALIERO VS MEDIE (TIPOLOGIA & MATCH)
    # ---------------------------------------------------------
    elif active_master_tab == T_BENCHMARK:
        if "Benchmark Giornaliero vs Medie" not in report_abilitati and st.session_state.get('role') != 'Super-Admin':
            st.info(tr("Non hai i permessi per visualizzare il report Benchmark Giornaliero vs Medie.", "You do not have permission to view the Daily Benchmark vs Averages report."))
        else:
            c_bm1, c_bm2 = st.columns([1.5, 1.8])
            with c_bm1:
                settimana_bm = st.selectbox(
                    tr("Seleziona Settimana da Analizzare", "Select Week to Analyze"),
                    settimane_disponibili,
                    index=0,
                    key="sel_week_benchmark_tab"
                )
            bm_start_dt = pd.to_datetime(settimana_bm.split(" - ")[0], format='%d/%m/%Y')
            bm_end_dt = bm_start_dt + timedelta(days=6)
            df_bm_week = df_ath[(df_ath['Date_obj'] >= bm_start_dt) & (df_ath['Date_obj'] <= bm_end_dt)].copy()
            df_bm_week['Minuti'] = pd.to_numeric(df_bm_week['Minuti'], errors='coerce').fillna(0)
            df_bm_week['Training Load'] = pd.to_numeric(df_bm_week['Training Load'], errors='coerce').fillna(0)

            # 1. Medie Storiche dell'Atleta
            is_match_all = df_ath['Tipologia Sessione'].astype(str).str.strip().str.lower().isin(['match', 'match doppio'])
            df_all_matches = df_ath[is_match_all].copy()
            hist_match_tl_avg = float(df_all_matches['Training Load'].mean()) if not df_all_matches.empty else 0.0
            hist_match_time_avg = float(df_all_matches['Minuti'].mean()) if not df_all_matches.empty else 0.0
            hist_match_count = len(df_all_matches)

            dict_tipologia_tl_avg = df_ath.groupby('Tipologia Sessione')['Training Load'].mean().to_dict()
            dict_tipologia_time_avg = df_ath.groupby('Tipologia Sessione')['Minuti'].mean().to_dict()

            with c_bm2:
                st.markdown(
                    f"<div style='display:flex; justify-content:flex-end; gap:10px; align-items:center; padding-top:24px; font-family:\"Inter\",sans-serif;'>"
                    f"<div style='background:#f0f9ff; border:1px solid #bae6fd; border-radius:8px; padding:6px 14px; text-align:right;'>"
                    f"<div style='font-size:10px; font-weight:800; color:#0369a1; text-transform:uppercase; letter-spacing:0.04em;'>{tr('Media Storica Match (Gold Standard)', 'Historical Match Avg (Gold Standard)')}</div>"
                    f"<div style='font-size:16px; font-weight:900; color:#0284c7;'>{hist_match_tl_avg:,.0f} TL <span style='font-size:11px; font-weight:700; color:#64748b;'>({hist_match_count} match analizzati)</span></div>"
                    f"</div>"
                    f"</div>",
                    unsafe_allow_html=True
                )

            # 2. Distribuzione del Lavoro (Superfici & Tipologie) della Settimana
            tot_min_w = float(df_bm_week['Minuti'].sum())
            tot_tl_w = float(df_bm_week['Training Load'].sum())
            tot_denom_min = tot_min_w if tot_min_w > 0 else 1.0

            # Superfici
            min_hard = float(df_bm_week[df_bm_week['Tipologia Campo'].astype(str).str.strip().str.lower() == 'hard']['Minuti'].sum())
            min_clay = float(df_bm_week[df_bm_week['Tipologia Campo'].astype(str).str.strip().str.lower() == 'clay']['Minuti'].sum())
            min_grass = float(df_bm_week[df_bm_week['Tipologia Campo'].astype(str).str.strip().str.lower() == 'grass']['Minuti'].sum())

            pct_hard = (min_hard / tot_denom_min * 100) if tot_min_w > 0 else 0.0
            pct_clay = (min_clay / tot_denom_min * 100) if tot_min_w > 0 else 0.0
            pct_grass = (min_grass / tot_denom_min * 100) if tot_min_w > 0 else 0.0

            # Tipologie
            is_match_w = df_bm_week['Tipologia Sessione'].astype(str).str.strip().str.lower().isin(['match', 'match doppio'])
            df_w_matches = df_bm_week[is_match_w]
            df_w_sparring = df_bm_week[~is_match_w]

            n_matches_w = len(df_w_matches)
            min_match_w = float(df_w_matches['Minuti'].sum())
            min_sparring_w = float(df_w_sparring['Minuti'].sum())

            pct_match_w = (min_match_w / tot_denom_min * 100) if tot_min_w > 0 else 0.0

            # Calcolo percentuali tipologie presenti nella settimana dai tipi canonici
            tipo_w_min = {}
            for t_name in CANONICAL_TIPOLOGIE_SESSIONE:
                m_t = float(df_bm_week[df_bm_week['Tipologia Sessione'].astype(str).str.strip().str.lower() == t_name.lower()]['Minuti'].sum())
                if m_t > 0:
                    tipo_w_min[t_name] = m_t

            if not tipo_w_min:
                tipo_w_min = {"Match": 0.0, "Tennis Base": 0.0, "Tennis Match": 0.0, "1000 Palle": 0.0}
            elif len(tipo_w_min) < 3:
                for fallback_t in ["Match", "Tennis Base", "Tennis Match", "1000 Palle"]:
                    if fallback_t not in tipo_w_min:
                        tipo_w_min[fallback_t] = 0.0
                    if len(tipo_w_min) >= 4:
                        break

            match_equiv = (tot_tl_w / hist_match_tl_avg) if hist_match_tl_avg > 0 else 0.0

            opzioni_pdf_bm = {
                tr("Report Benchmark Giornaliero vs Medie", "Daily Benchmark vs Averages Report"): "Benchmark_Giornaliero"
            }
            render_action_bar(
                meta_items=[
                    (tr("Atleta", "Athlete"), giocatore_selezionato),
                    (tr("Settimana", "Week"), settimana_bm),
                    (tr("Match Equivalenti", "Match Equiv."), f"{match_equiv:.1f} Eq."),
                    (tr("Carico Totale", "Total Load"), f"{tot_tl_w:,.0f} TL"),
                ],
                pdf_options=opzioni_pdf_bm,
                pdf_key=f"pdf_bm_{slugify_name(giocatore_selezionato)}_{slugify_name(settimana_bm)}",
                generate_fn=lambda _: crea_pdf_weekly_m0v3(
                    giocatore_selezionato, settimana_bm, df_bm_week, sottoarea="Benchmark_Giornaliero", df_ath=df_ath
                ),
                filename_fn=lambda _: f"M0V3_Benchmark_Giornaliero_{slugify_name(giocatore_selezionato)}_{settimana_bm.replace('/', '-').replace(' ', '')}.pdf"
            )

            # Render Blocco Distribuzione del Lavoro (Ispirato al Foglio)
            def _render_vertical_gauge(label, pct, fill_color):
                pct_clamped = min(max(pct, 0.0), 100.0)
                return (
                    f"<div style='flex:1; min-width:64px; background:#ffffff; border:1px solid #e2e8f0; border-radius:8px; padding:6px 5px; text-align:center; box-shadow:0 1px 2px rgba(15,23,42,0.02);'>"
                    f"<div style='font-size:9.5px; font-weight:800; color:#64748b; text-transform:uppercase; margin-bottom:4px; letter-spacing:0.04em;'>{label}</div>"
                    f"<div style='height:44px; width:100%; background:#f1f5f9; border-radius:6px; position:relative; overflow:hidden; display:flex; align-items:flex-end; border:1px solid #e2e8f0;'>"
                    f"<div style='width:100%; height:{pct_clamped:.0f}%; background:{fill_color}; transition:height 0.3s;'></div>"
                    f"<div style='position:absolute; width:100%; top:0; bottom:0; display:flex; align-items:center; justify-content:center; font-size:11.5px; font-weight:900; color:#0f172a;'>{pct:.0f}%</div>"
                    f"</div>"
                    f"</div>"
                )

            gauges_surf_html = (
                f"<div style='display:flex; gap:6px; flex:1; min-width:210px;'>"
                f"{_render_vertical_gauge('Hard', pct_hard, '#0ea5e9')}"
                f"{_render_vertical_gauge('Clay', pct_clay, '#ea580c')}"
                f"{_render_vertical_gauge('Grass', pct_grass, '#16a34a')}"
                f"</div>"
            )

            gauges_tipo_list = []
            for t_name, m_t in list(tipo_w_min.items())[:5]:
                pct_t = (m_t / tot_denom_min * 100) if tot_denom_min > 0 else 0.0
                t_col = COLORI_TIPOLOGIE_SESSIONE.get(t_name, "#0ea5e9")
                gauges_tipo_list.append(_render_vertical_gauge(t_name, pct_t, t_col))
            gauges_tipo_html = f"<div style='display:flex; gap:6px; flex:1.5; min-width:280px; flex-wrap:wrap;'>{''.join(gauges_tipo_list)}</div>"

            h_sparring = int(min_sparring_w // 60)
            m_sparring = int(min_sparring_w % 60)
            str_sparring = f"{h_sparring}h {m_sparring:02d}m" if min_sparring_w > 0 else "0m"

            distr_block_html = (
                f"<div style='background:#f8fafc; border:1px solid #e2e8f0; border-radius:12px; padding:14px 18px; margin-bottom:20px; font-family:\"Inter\",-apple-system,BlinkMacSystemFont,sans-serif; box-shadow:0 1px 3px rgba(15,23,42,0.03);'>"
                f"<div style='display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; margin-bottom:12px;'>"
                f"<span style='font-size:12px; font-weight:900; color:#0f172a; text-transform:uppercase; letter-spacing:0.05em;'><i class='bi bi-pie-chart' style='color:#0ea5e9; margin-right:6px;'></i>{tr('Distribuzione del Lavoro (Superfici & Tipologie)', 'Workload Distribution (Surfaces & Session Types)')} — {settimana_bm}</span>"
                f"<span style='font-size:11px; font-weight:700; color:#0284c7;'>{tr('Superfici, tipologie e match disputati nella settimana', 'Surfaces, session types and matches played this week')}</span>"
                f"</div>"
                f"<div style='display:flex; gap:14px; align-items:center; flex-wrap:wrap;'>"
                f"<div style='flex:1; display:flex; flex-direction:column; gap:4px; min-width:210px;'>"
                f"<span style='font-size:10px; font-weight:800; color:#475569; text-transform:uppercase;'>SUPERFICI DI GIOCO</span>"
                f"{gauges_surf_html}"
                f"</div>"
                f"<div style='flex:1.4; display:flex; flex-direction:column; gap:4px; min-width:280px;'>"
                f"<span style='font-size:10px; font-weight:800; color:#475569; text-transform:uppercase;'>TIPOLOGIA SESSIONI</span>"
                f"{gauges_tipo_html}"
                f"</div>"
                f"<div style='display:flex; gap:8px; align-items:center; flex-wrap:wrap;'>"
                f"<div style='background:#ffffff; border:1px solid #e2e8f0; border-radius:8px; padding:8px 12px; text-align:center; min-width:85px; box-shadow:0 1px 2px rgba(15,23,42,0.02);'>"
                f"<div style='font-size:9.5px; font-weight:800; color:#64748b; text-transform:uppercase; margin-bottom:2px;'>N° MATCH</div>"
                f"<div style='font-size:22px; font-weight:900; color:#dc2626;'>{n_matches_w}</div>"
                f"</div>"
                f"<div style='background:#ffffff; border:1px solid #e2e8f0; border-radius:8px; padding:8px 12px; text-align:center; min-width:110px; box-shadow:0 1px 2px rgba(15,23,42,0.02);'>"
                f"<div style='font-size:9.5px; font-weight:800; color:#64748b; text-transform:uppercase; margin-bottom:2px;'>T SPARRING/ALL.</div>"
                f"<div style='font-size:16px; font-weight:900; color:#0f172a; margin-top:2px;'>{str_sparring}</div>"
                f"<div style='font-size:9.5px; color:#64748b; font-weight:600;'>{int(round(min_sparring_w))} min</div>"
                f"</div>"
                f"<div style='background:#f0fdf4; border:1px solid #bbf7d0; border-radius:8px; padding:8px 12px; text-align:center; min-width:125px; box-shadow:0 1px 2px rgba(15,23,42,0.02);'>"
                f"<div style='font-size:9.5px; font-weight:800; color:#166534; text-transform:uppercase; margin-bottom:2px;'>MATCH EQUIVALENTI</div>"
                f"<div style='font-size:20px; font-weight:900; color:#15803d;'>{match_equiv:.1f} Eq.</div>"
                f"<div style='font-size:9.5px; color:#166534; font-weight:700;'>{tot_tl_w:,.0f} TL Totali</div>"
                f"</div>"
                f"</div>"
                f"</div>"
                f"</div>"
            )
            st.html(distr_block_html)

            # 3. Tabella Dettagliata Giornaliera con Doppio Benchmark (Lun -> Dom)
            all_bm_days = [bm_start_dt + timedelta(days=i) for i in range(7)]
            day_names_it = [
                tr("Lunedì", "Monday"), tr("Martedì", "Tuesday"), tr("Mercoledì", "Wednesday"),
                tr("Giovedì", "Thursday"), tr("Venerdì", "Friday"), tr("Sabato", "Saturday"), tr("Domenica", "Sunday")
            ]

            rows_bm_html = ""
            plot_bar_data = []

            for i, d_cur in enumerate(all_bm_days):
                d_str = d_cur.strftime("%d/%m/%Y")
                d_short = d_cur.strftime("%d/%m")
                d_name = day_names_it[i]
                df_day = df_bm_week[df_bm_week['Date_obj'].dt.date == d_cur.date()]

                if df_day.empty:
                    # Giorno di Riposo
                    bg_row = "#fcfdfd" if i % 2 == 0 else "#ffffff"
                    rows_bm_html += (
                        f"<tr style='background:{bg_row}; border-bottom:1px solid #f1f5f9;'>"
                        f"<td style='padding:12px 14px; font-weight:800; color:#475569; font-size:13px; white-space:nowrap;'>{d_name} <span style='color:#94a3b8; font-weight:600;'>({d_short})</span></td>"
                        f"<td style='padding:12px 12px;'><span style='background:#f1f5f9; color:#64748b; font-size:11px; font-weight:700; padding:4px 9px; border-radius:4px; display:inline-block; white-space:nowrap;'>Riposo / Scarico</span></td>"
                        f"<td style='padding:12px 10px; text-align:center; color:#94a3b8; font-size:12px;'>-</td>"
                        f"<td style='padding:12px 10px; text-align:center; color:#94a3b8; font-size:13px; white-space:nowrap;'>0 min</td>"
                        f"<td style='padding:12px 10px; text-align:center; font-weight:800; color:#94a3b8; font-size:14px;'>0</td>"
                        f"<td style='padding:12px 12px; text-align:center; color:#94a3b8; font-size:12px;'>-</td>"
                        f"<td style='padding:12px 12px; text-align:center; color:#94a3b8; font-size:12px; white-space:nowrap;'>0% Match</td>"
                        f"<td style='padding:12px 14px; text-align:center;'><span style='background:#f8fafc; color:#94a3b8; padding:4px 9px; border-radius:4px; font-size:11px; font-weight:700; border:1px solid #e2e8f0; display:inline-block; white-space:nowrap;'>Riposo Programmato</span></td>"
                        f"</tr>"
                    )
                    plot_bar_data.append({
                        "label": f"{d_name[:3]} {d_short}",
                        "tl": 0.0,
                        "pct_match": 0.0,
                        "color": "#cbd5e1"
                    })
                else:
                    # Giorno con 1 o più sessioni
                    day_tot_tl = float(df_day['Training Load'].sum())
                    pct_day_match = (day_tot_tl / hist_match_tl_avg * 100) if hist_match_tl_avg > 0 else 0.0
                    col_bar_plot = "#ef4444" if pct_day_match > 110 else ("#f59e0b" if pct_day_match > 90 else ("#10b981" if pct_day_match >= 60 else "#0ea5e9"))

                    plot_bar_data.append({
                        "label": f"{d_name[:3]} {d_short}",
                        "tl": day_tot_tl,
                        "pct_match": pct_day_match,
                        "color": col_bar_plot
                    })

                    for idx_s, (_, r_s) in enumerate(df_day.iterrows()):
                        s_name = str(r_s.get('Session', '')).strip()
                        s_tipo = str(r_s.get('Tipologia Sessione', 'Allenamento')).strip()
                        s_campo = str(r_s.get('Tipologia Campo', '-')).strip()
                        s_min = float(r_s.get('Minuti', 0.0))
                        s_tl = float(r_s.get('Training Load', 0.0))

                        # Colore badge campo
                        if s_campo.lower() == 'clay':
                            campo_badge = "<span style='background:#ffedd5; color:#c2410c; font-size:10px; font-weight:800; padding:2px 7px; border-radius:4px; display:inline-block; white-space:nowrap;'>CLAY</span>"
                        elif s_campo.lower() == 'hard':
                            campo_badge = "<span style='background:#e0f2fe; color:#0284c7; font-size:10px; font-weight:800; padding:2px 7px; border-radius:4px; display:inline-block; white-space:nowrap;'>HARD</span>"
                        elif s_campo.lower() == 'grass':
                            campo_badge = "<span style='background:#dcfce7; color:#15803d; font-size:10px; font-weight:800; padding:2px 7px; border-radius:4px; display:inline-block; white-space:nowrap;'>GRASS</span>"
                        else:
                            campo_badge = f"<span style='background:#f1f5f9; color:#475569; font-size:10px; font-weight:800; padding:2px 7px; border-radius:4px; display:inline-block; white-space:nowrap;'>{s_campo.upper()}</span>"

                        # Colore badge tipologia
                        t_bg, t_fg = get_tipologia_badge_style(s_tipo)
                        tipo_badge = f"<span style='background:{t_bg}; color:{t_fg}; font-size:10.5px; font-weight:800; padding:3px 7px; border-radius:4px; display:inline-block; white-space:nowrap;'>{s_tipo.upper()}</span>"

                        # Benchmark 1: vs Media Tipologia
                        avg_tipo_tl = dict_tipologia_tl_avg.get(s_tipo, 0.0)
                        if avg_tipo_tl > 0:
                            delta_tl = s_tl - avg_tipo_tl
                            delta_pct = (delta_tl / avg_tipo_tl * 100)
                            ratio_tipo = min(max(s_tl / avg_tipo_tl * 100, 0.0), 150.0)

                            if delta_pct > 25:
                                bg_d, fg_d, arr_d = "#fee2e2", "#991b1b", "⬆"
                                bar_col = "#ef4444"
                            elif 5 <= delta_pct <= 25:
                                bg_d, fg_d, arr_d = "#fef3c7", "#b45309", "↗"
                                bar_col = "#f59e0b"
                            elif -10 <= delta_pct < 5:
                                bg_d, fg_d, arr_d = "#dcfce7", "#166534", "<i class='bi bi-arrow-right'></i>"
                                bar_col = "#10b981"
                            else:
                                bg_d, fg_d, arr_d = "#e0f2fe", "#0369a1", "⬇"
                                bar_col = "#0ea5e9"

                            cell_tipo_html = (
                                f"<div style='display:flex; flex-direction:column; align-items:center; white-space:nowrap;'>"
                                f"<div style='display:flex; align-items:center; gap:5px; white-space:nowrap;'>"
                                f"<span style='font-size:13px; font-weight:900; color:#0f172a;'>{s_tl:,.0f}</span>"
                                f"<span style='background:{bg_d}; color:{fg_d}; font-size:10px; font-weight:800; padding:2px 6px; border-radius:4px; display:inline-block; white-space:nowrap;'>{arr_d} {delta_pct:+.0f}%</span>"
                                f"</div>"
                                f"<div style='width:90px; background:#f1f5f9; height:5px; border-radius:3px; margin-top:4px; overflow:hidden;'>"
                                f"<div style='width:{min(ratio_tipo, 100):.0f}%; background:{bar_col}; height:5px; border-radius:3px;'></div>"
                                f"</div>"
                                f"<span style='font-size:9.5px; color:#64748b; font-weight:600; margin-top:2px; white-space:nowrap;'>Media {s_tipo}: {avg_tipo_tl:,.0f}</span>"
                                f"</div>"
                            )
                        else:
                            cell_tipo_html = "<span style='color:#94a3b8;'>-</span>"

                        # Benchmark 2: vs Media Match (Match Benchmark %)
                        if hist_match_tl_avg > 0:
                            pct_match = (s_tl / hist_match_tl_avg * 100)
                            bar_pct_w = min(max(pct_match, 0.0), 100.0)

                            if pct_match > 110:
                                m_col = "#ef4444"
                                m_status = tr("Superiore a Match", "Exceeds Match")
                            elif pct_match >= 85:
                                m_col = "#f59e0b"
                                m_status = tr("Intensità Match", "Match Intensity")
                            elif pct_match >= 60:
                                m_col = "#10b981"
                                m_status = tr("Carico Ottimale", "Optimal Training")
                            else:
                                m_col = "#0ea5e9"
                                m_status = tr("Rigenerante", "Regenerative")

                            cell_match_html = (
                                f"<div style='display:flex; flex-direction:column; align-items:center; white-space:nowrap;'>"
                                f"<div style='display:flex; align-items:center; gap:5px; white-space:nowrap;'>"
                                f"<span style='font-size:13.5px; font-weight:900; color:{m_col};'>{pct_match:.0f}%</span>"
                                f"<span style='font-size:10px; font-weight:700; color:#64748b; white-space:nowrap;'>di un Match</span>"
                                f"</div>"
                                f"<div style='width:95px; background:#f1f5f9; height:5px; border-radius:3px; margin-top:4px; overflow:hidden;'>"
                                f"<div style='width:{bar_pct_w:.0f}%; background:{m_col}; height:5px; border-radius:3px;'></div>"
                                f"</div>"
                                f"<span style='font-size:9.5px; color:#64748b; font-weight:600; margin-top:2px; white-space:nowrap;'>{s_tl:,.0f} / {hist_match_tl_avg:,.0f} TL</span>"
                                f"</div>"
                            )

                            cell_status_html = f"<span style='background:#ffffff; border:1px solid {m_col}; color:{m_col}; font-size:11px; font-weight:800; padding:4px 9px; border-radius:5px; display:inline-block; white-space:nowrap;'>{m_status}</span>"
                        else:
                            cell_match_html = "<span style='color:#94a3b8;'>-</span>"
                            cell_status_html = "<span style='color:#94a3b8;'>-</span>"

                        bg_s_row = "#ffffff" if i % 2 == 0 else "#f8fafc"
                        lbl_giorno_display = f"<span style='white-space:nowrap;'>{d_name} <span style='color:#64748b; font-weight:600;'>({d_short})</span></span>" if idx_s == 0 else f"<span style='color:#94a3b8; font-size:11.5px; font-weight:700; white-space:nowrap;'>↳ Sess. {idx_s+1}</span>"

                        # Sessione: stack verticale con badge tipo e nome sessione troncato con tooltip
                        session_cell_content = (
                            f"<div style='display:flex; flex-direction:column; gap:3px; max-width:210px;'>"
                            f"<div style='display:flex; align-items:center; gap:6px;'>{tipo_badge}</div>"
                            f"<span style='font-size:12px; font-weight:700; color:#0f172a; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;' title='{s_name}'>{s_name}</span>"
                            f"</div>"
                        )

                        rows_bm_html += (
                            f"<tr style='background:{bg_s_row}; border-bottom:1px solid #f1f5f9;'>"
                            f"<td style='padding:12px 14px; font-weight:800; color:#0f172a; font-size:13px; white-space:nowrap;'>{lbl_giorno_display}</td>"
                            f"<td style='padding:12px 12px;'>{session_cell_content}</td>"
                            f"<td style='padding:12px 10px; text-align:center;'>{campo_badge}</td>"
                            f"<td style='padding:12px 10px; text-align:center; font-weight:800; color:#0f172a; font-size:13.5px; white-space:nowrap;'>{s_min:.0f} min</td>"
                            f"<td style='padding:12px 10px; text-align:center; font-weight:900; color:#0284c7; font-size:15px; white-space:nowrap;'>{s_tl:,.0f}</td>"
                            f"<td style='padding:12px 12px; text-align:center;'>{cell_tipo_html}</td>"
                            f"<td style='padding:12px 12px; text-align:center;'>{cell_match_html}</td>"
                            f"<td style='padding:12px 14px; text-align:center;'>{cell_status_html}</td>"
                            f"</tr>"
                        )

            # Riga Totale Settimana
            rows_bm_html += (
                f"<tr style='background:#f0f9ff; border-top:2px solid #bae6fd; font-family:\"Inter\",sans-serif;'>"
                f"<td style='padding:14px 14px; font-weight:900; color:#0284c7; font-size:13px; text-transform:uppercase; white-space:nowrap;'>TOTALE SETTIMANA</td>"
                f"<td style='padding:14px 12px; font-weight:800; color:#0369a1; font-size:12.5px; white-space:nowrap;'>{len(df_bm_week)} sessioni totali</td>"
                f"<td style='padding:14px 10px; text-align:center; color:#0369a1; font-size:11.5px; font-weight:700;'>-</td>"
                f"<td style='padding:14px 10px; text-align:center; font-weight:900; color:#0f172a; font-size:15px; white-space:nowrap;'>{tot_min_w:.0f} min</td>"
                f"<td style='padding:14px 10px; text-align:center; font-weight:900; color:#0284c7; font-size:16px; white-space:nowrap;'>{tot_tl_w:,.0f}</td>"
                f"<td style='padding:14px 12px; text-align:center; font-weight:800; color:#0369a1; font-size:12px; white-space:nowrap;'>Media Giorn: {tot_tl_w/7.0:,.0f} TL</td>"
                f"<td style='padding:14px 12px; text-align:center; white-space:nowrap;'><span style='background:#0284c7; color:#ffffff; font-size:12.5px; font-weight:900; padding:4px 9px; border-radius:6px; display:inline-block; white-space:nowrap;'>{match_equiv:.1f} Match Eq.</span></td>"
                f"<td style='padding:14px 14px; text-align:center; font-weight:800; color:#0f172a; font-size:12px; white-space:nowrap;'>Volume Settimanale</td>"
                f"</tr>"
            )

            table_full_html = (
                f"<div style='background:#ffffff; border-radius:14px; border:1px solid #e2e8f0; box-shadow:0 4px 12px -2px rgba(15,23,42,0.05); overflow:hidden; margin-bottom:20px; font-family:\"Inter\",sans-serif;'>"
                f"<div style='background:linear-gradient(135deg, #0f172a 0%, #1e293b 100%); padding:13px 18px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;'>"
                f"<span style='color:#ffffff; font-size:13px; font-weight:800; text-transform:uppercase; letter-spacing:0.06em;'><i class='bi bi-table' style='color:#38bdf8; margin-right:8px;'></i>{tr('BENCHMARK GIORNALIERO VS MEDIE (TIPOLOGIA & MATCH)', 'DAILY BENCHMARK VS AVERAGES (SESSION TYPE & MATCH)')}</span>"
                f"<span style='color:#38bdf8; font-size:11.5px; font-weight:700;'>{settimana_bm}</span>"
                f"</div>"
                f"<div style='overflow-x:auto; width:100%; -webkit-overflow-scrolling:touch;'>"
                f"<table style='width:100%; border-collapse:collapse; min-width:1150px;'>"
                f"<thead><tr style='background:#f8fafc; border-bottom:2px solid #e2e8f0;'>"
                f"<th style='text-align:left; padding:12px 14px; color:#475569; font-size:11px; font-weight:800; text-transform:uppercase; white-space:nowrap; width:130px;'>Giorno & Data</th>"
                f"<th style='text-align:left; padding:12px 12px; color:#475569; font-size:11px; font-weight:800; text-transform:uppercase; white-space:nowrap; width:220px;'>Sessione</th>"
                f"<th style='text-align:center; padding:12px 10px; color:#475569; font-size:11px; font-weight:800; text-transform:uppercase; white-space:nowrap; width:90px;'>Superficie</th>"
                f"<th style='text-align:center; padding:12px 10px; color:#475569; font-size:11px; font-weight:800; text-transform:uppercase; white-space:nowrap; width:85px;'>Durata</th>"
                f"<th style='text-align:center; padding:12px 10px; color:#0284c7; font-size:11px; font-weight:800; text-transform:uppercase; white-space:nowrap; width:110px;'>Training Load</th>"
                f"<th style='text-align:center; padding:12px 12px; color:#475569; font-size:11px; font-weight:800; text-transform:uppercase; white-space:nowrap; width:170px;'>vs Media Tipologia</th>"
                f"<th style='text-align:center; padding:12px 12px; color:#0284c7; font-size:11px; font-weight:800; text-transform:uppercase; white-space:nowrap; width:180px;'>vs Media Match (% Match)</th>"
                f"<th style='text-align:center; padding:12px 14px; color:#475569; font-size:11px; font-weight:800; text-transform:uppercase; white-space:nowrap; width:150px;'>Valutazione</th>"
                f"</tr></thead>"
                f"<tbody>{rows_bm_html}</tbody>"
                f"</table></div></div>"
            )
            st.html(table_full_html)

            # 4. Grafico Visuale a Barre: Training Load Giornaliero vs Benchmark Match
            with st.container(border=True):
                st.markdown(
                    render_executive_chart_header(
                        tr("Training Load Giornaliero con Benchmark Media Match", "Daily Training Load with Match Benchmark"),
                        pills=[
                            (tr("Carico Totale", "Total Load"), f"{tot_tl_w:,.0f} TL", "#0ea5e9"),
                            (tr("Media Match", "Match Avg"), f"{hist_match_tl_avg:,.0f} TL", "#10b981"),
                            (tr("Match Equivalenti", "Match Equiv."), f"{match_equiv:.1f} Eq.", "#8b5cf6")
                        ],
                        accent="#0ea5e9"
                    ),
                    unsafe_allow_html=True
                )

                x_b_lbls = [d['label'] for d in plot_bar_data]
                y_b_tls = [d['tl'] for d in plot_bar_data]
                c_b_colors = [d['color'] for d in plot_bar_data]
                txt_b = [f"<b>{d['tl']:,.0f}</b><br><span style='font-size:10px;'>({d['pct_match']:.0f}% Match)</span>" if d['tl'] > 0 else "" for d in plot_bar_data]

                max_bar_y = max(max(y_b_tls or [10.0]), hist_match_tl_avg) * 1.25

                fig_bm_bar = go.Figure()
                fig_bm_bar.add_trace(go.Bar(
                    x=x_b_lbls,
                    y=y_b_tls,
                    marker_color=c_b_colors,
                    text=txt_b,
                    textposition='outside',
                    cliponaxis=False,
                    textfont=dict(size=11, color='#0f172a', family='Inter, sans-serif'),
                    hovertemplate="<b>%{x}</b><br>Training Load: <b>%{y:,.0f}</b><extra></extra>"
                ))

                if hist_match_tl_avg > 0:
                    fig_bm_bar.add_hline(
                        y=hist_match_tl_avg,
                        line_dash="dash",
                        line_color="#10b981",
                        line_width=1.5,
                        annotation_text=f"Media Match Storica: {hist_match_tl_avg:,.0f} TL (100% Gold Standard)",
                        annotation_position="top right",
                        annotation_font=dict(size=10.5, color="#10b981", family='Inter, sans-serif')
                    )

                fig_bm_bar.update_layout(
                    height=320,
                    margin=dict(l=20, r=20, t=30, b=30),
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(248,250,252,0.6)',
                    xaxis=dict(
                        tickfont=dict(size=10.5, color='#475569', family='Inter, sans-serif'),
                        showgrid=False,
                        linecolor='#cbd5e1'
                    ),
                    yaxis=dict(
                        showgrid=True,
                        gridcolor='#f1f5f9',
                        range=[0, max_bar_y],
                        tickfont=dict(size=9.5, color='#64748b'),
                        zerolinecolor='#cbd5e1'
                    ),
                    showlegend=False
                )

                st.plotly_chart(fig_bm_bar, use_container_width=True, key="chart_bm_daily_bar", config={'displayModeBar': False})

    # ---------------------------------------------------------
    # TAB 5: REFERTO DESCRITTIVO SETTIMANALE (CLINICO & PERFORMANCE)
    # ---------------------------------------------------------
    elif active_master_tab == T_REFERTO:
        if "Referto Descrittivo Settimanale" not in report_abilitati:
            st.info(tr("Il modulo 'Referto Descrittivo Settimanale' non è abilitato per questo account. Contatta l'amministratore.", "The 'Weekly Descriptive Report' module is not enabled for this account. Contact admin."))
        else:
            oggi_norm = pd.Timestamp.today().normalize()
            curr_w_start = oggi_norm - timedelta(days=oggi_norm.dayofweek)
            curr_w_end = curr_w_start + timedelta(days=6)
            curr_w_lbl = f"{curr_w_start.strftime('%d/%m/%Y')} - {curr_w_end.strftime('%d/%m/%Y')}"

            # Verifica se la settimana corrente ha sessioni registrate per questo giocatore
            df_cur_w_check = df_ath_real[(df_ath_real['Date_obj'] >= curr_w_start) & (df_ath_real['Date_obj'] <= curr_w_end)]
            has_cur_week_data = not df_cur_w_check.empty

            opt_corrente = f"[{tr('Settimana Corrente (In Corso)', 'Current Week (In Progress)')}] {curr_w_lbl}"

            # Se la settimana corrente ha dati, la mettiamo per prima e selezionata di default
            # Se la settimana corrente non ha ancora dati, selezioniamo di default l'ultima settimana con dati reali
            if has_cur_week_data:
                opts_referto = [opt_corrente] + [s for s in settimane_disponibili if s != curr_w_lbl]
                default_idx_ref = 0
            else:
                settimane_con_dati = [s for s in settimane_disponibili if s != curr_w_lbl]
                opts_referto = settimane_con_dati + [opt_corrente]
                default_idx_ref = 0 if settimane_con_dati else 0

            c_rf_w, c_rf_d = st.columns([1.6, 1.4])
            with c_rf_w:
                sel_ref_opt = st.selectbox(
                    tr("Seleziona Settimana per il Referto", "Select Week for Report"),
                    opts_referto,
                    index=default_idx_ref,
                    key="sel_week_referto_tab"
                )

            is_cur_week = (sel_ref_opt == opt_corrente)

            if is_cur_week:
                settimana_valutata = curr_w_lbl
                w_start_ref = curr_w_start
                # Calcola default day index (oggi oppure ultimo giorno con dati della settimana)
                df_curr_w = df_ath_real[(df_ath_real['Date_obj'] >= curr_w_start) & (df_ath_real['Date_obj'] <= curr_w_end)]
                if not df_curr_w.empty:
                    max_d_cw = df_curr_w['Date_obj'].max().normalize()
                    def_day_idx = min(max(int((max_d_cw - curr_w_start).days), 0), 6)
                else:
                    def_day_idx = min(max(int(oggi_norm.dayofweek), 0), 6)

                opts_giorni_prog = [
                    f"{day_names_full[i]} {(curr_w_start + timedelta(days=i)).strftime('%d/%m/%Y')} ({tr('Giorno', 'Day')} {i+1}/7)"
                    for i in range(7)
                ]
                with c_rf_d:
                    sel_prog_day_lbl = st.selectbox(
                        tr("Rilevazione Live fino a:", "Live Assessment up to:"),
                        opts_giorni_prog,
                        index=def_day_idx,
                        key="sel_day_prog_referto"
                    )
                giorno_rif_idx = opts_giorni_prog.index(sel_prog_day_lbl)
                d_ref_eval = curr_w_start + timedelta(days=giorno_rif_idx)
                giorni_trascorsi = giorno_rif_idx + 1
            else:
                settimana_valutata = sel_ref_opt
                w_start_ref = pd.to_datetime(settimana_valutata.split(" - ")[0], format='%d/%m/%Y')
                d_ref_eval = w_start_ref + timedelta(days=6)
                giorni_trascorsi = 7
                with c_rf_d:
                    st.text_input(
                        tr("Stato Microciclo", "Microcycle Status"),
                        value=tr("Settimana Conclusa (7/7 Giorni)", "Concluded Week (7/7 Days)"),
                        disabled=True,
                        key="txt_status_microciclo_ref"
                    )

            # --- Calcolo Dati e Metriche per il Referto ---
            df_w_sub = df_ath_real[(df_ath_real['Date_obj'] >= w_start_ref) & (df_ath_real['Date_obj'] <= d_ref_eval)].copy()
            tot_sessioni_w = len(df_w_sub)

            if tot_sessioni_w == 0:
                st.info(
                    tr(
                        f"ℹ️ **Nessuna sessione registrata per {giocatore_selezionato} nel microciclo selezionato ({settimana_valutata})**.\n\n"
                        f"Non risultano dati GPS caricati per questo intervallo temporale. "
                        f"Seleziona una settimana con dati registrati dal menu sopra oppure carica nuovi file dalla sezione 'Caricamento Dati'.",
                        f"ℹ️ **No sessions recorded for {giocatore_selezionato} in the selected microcycle ({settimana_valutata})**.\n\n"
                        f"Please select a week with recorded data from the dropdown above or upload new GPS files."
                    )
                )
            else:
                tot_tl_w = float(df_w_sub['Training Load'].sum()) if 'Training Load' in df_w_sub.columns else 0.0
                tot_tlh_w = float(df_w_sub['TL_High'].sum()) if 'TL_High' in df_w_sub.columns else 0.0
                tot_acc_w = float(df_w_sub['High Accel IMU'].sum()) if 'High Accel IMU' in df_w_sub.columns else 0.0
                tot_dec_w = float(df_w_sub['High Decel IMU'].sum()) if 'High Decel IMU' in df_w_sub.columns else 0.0
                pct_tlh_w = (tot_tlh_w / tot_tl_w * 100.0) if tot_tl_w > 0 else 0.0

                # Vettori giornalieri sui 7 giorni (Lunedì-Domenica)
                tl_days_w = []
                tlh_days_w = []
                for i in range(7):
                    d_target = w_start_ref + timedelta(days=i)
                    if d_target <= d_ref_eval:
                        df_target_d = df_w_sub[df_w_sub['Date_obj'].dt.date == d_target.date()]
                        val_tl_d = float(df_target_d['Training Load'].sum()) if not df_target_d.empty else 0.0
                        val_tlh_d = float(df_target_d['TL_High'].sum()) if not df_target_d.empty else 0.0
                    else:
                        val_tl_d = 0.0
                        val_tlh_d = 0.0
                    tl_days_w.append(val_tl_d)
                    tlh_days_w.append(val_tlh_d)

                # 1. ACWR Settimanale
                b_end_w = w_start_ref - timedelta(days=1)
                b_start_w = b_end_w - timedelta(days=27)
                df_b_w = df_ath_real[(df_ath_real['Date_obj'] >= b_start_w) & (df_ath_real['Date_obj'] <= b_end_w)]
                blocchi_w = calcola_blocchi_baseline(df_ath_real, b_end_w, 7.0)
                ch_tl_w = (df_b_w['Training Load'].sum() / blocchi_w) if not df_b_w.empty and blocchi_w > 0 else 0.0
                ch_tlh_w = (df_b_w['TL_High'].sum() / blocchi_w) if not df_b_w.empty and blocchi_w > 0 else 0.0

                acwr_sett_tl_dec = (tot_tl_w / ch_tl_w) if ch_tl_w > 0 else (1.0 if tot_tl_w > 0 else 0.0)
                acwr_sett_tl_pct = acwr_sett_tl_dec * 100.0
                acwr_sett_tlh_dec = (tot_tlh_w / ch_tlh_w) if ch_tlh_w > 0 else (1.0 if tot_tlh_w > 0 else 0.0)
                acwr_sett_tlh_pct = acwr_sett_tlh_dec * 100.0

                # 2. ACWR Rolling 7 Giorni (alla data d_ref_eval)
                r_start_w = d_ref_eval - timedelta(days=6)
                df_r7_w = df_ath_real[(df_ath_real['Date_obj'] >= r_start_w) & (df_ath_real['Date_obj'] <= d_ref_eval)]
                tot_tl_r7 = float(df_r7_w['Training Load'].sum()) if 'Training Load' in df_r7_w.columns else 0.0
                tot_tlh_r7 = float(df_r7_w['TL_High'].sum()) if 'TL_High' in df_r7_w.columns else 0.0
                r_b_end_w = r_start_w - timedelta(days=1)
                r_b_start_w = r_b_end_w - timedelta(days=27)
                df_rb_w = df_ath_real[(df_ath_real['Date_obj'] >= r_b_start_w) & (df_ath_real['Date_obj'] <= r_b_end_w)]
                r_blocchi_w = calcola_blocchi_baseline(df_ath_real, r_b_end_w, 7.0)
                ch_tl_r7 = (df_rb_w['Training Load'].sum() / r_blocchi_w) if not df_rb_w.empty and r_blocchi_w > 0 else 0.0
                acwr_roll_tl_dec = (tot_tl_r7 / ch_tl_r7) if ch_tl_r7 > 0 else (1.0 if tot_tl_r7 > 0 else 0.0)
                acwr_roll_tl_pct = acwr_roll_tl_dec * 100.0

                # 3. Monotonia e Training Strain (Foster)
                mean_tl_w = tot_tl_w / 7.0
                std_tl_w = float(np.std(tl_days_w, ddof=1)) if len(tl_days_w) > 1 else 0.0
                mono_tl = (mean_tl_w / std_tl_w) if std_tl_w > 0 else (3.5 if mean_tl_w > 0 else 0.0)
                strain_tl = tot_tl_w * mono_tl

                mean_tlh_w = tot_tlh_w / 7.0
                std_tlh_w = float(np.std(tlh_days_w, ddof=1)) if len(tlh_days_w) > 1 else 0.0
                mono_tlh = (mean_tlh_w / std_tlh_w) if std_tlh_w > 0 else (3.5 if mean_tlh_w > 0 else 0.0)
                strain_tlh = tot_tlh_w * mono_tlh

                # 4. Spaziatura Neuromuscolare (TL High Peaks)
                th_peak_tlh = max(mean_tlh_w * 1.20, 60.0) if mean_tlh_w > 0 else 60.0
                peak_indices_tlh = [idx for idx, v in enumerate(tlh_days_w[:giorni_trascorsi]) if v >= th_peak_tlh and v > 0]
                has_consecutive_tlh = any(peak_indices_tlh[k] - peak_indices_tlh[k-1] == 1 for k in range(1, len(peak_indices_tlh)))
                min_gap_tlh = min([peak_indices_tlh[k] - peak_indices_tlh[k-1] for k in range(1, len(peak_indices_tlh))]) if len(peak_indices_tlh) > 1 else 99

                # Deterministic variant selector
                seed_v = int(w_start_ref.timestamp()) % 3

                # --- GENERATORE TESTI NLG ---
                # SEZIONE 1: VOLUME (TL) & ACWR
                if acwr_sett_tl_dec < 0.80:
                    v_opts = [
                        f"Il volume di lavoro complessivo registrato in questa settimana si attesta al di sotto della soglia allenante minima (ACWR {acwr_sett_tl_dec:.2f} / {acwr_sett_tl_pct:.0f}%). Questa condizione prolungata espone l'atleta a un de-training globale, riducendo la base aerobica e la capacità di tollerare i carichi futuri. Si consiglia di incrementare gradualmente i volumi di carico.",
                        f"Il carico volumetrico globale risulta marcatamente contenuto rispetto alla baseline cronica (ACWR {acwr_sett_tl_dec:.2f}). Se non inserita in una fase pianificata di tapering pre-gara, questa sotto-esposizione cronica determina un impoverimento delle riserve funzionali e un decondizionamento della resistenza specifica al tennis.",
                        f"Dall'analisi volumetrica emerge un volume cumulato inferiore al range fisiologico target (ACWR settimanale pari a {acwr_sett_tl_dec:.2f}). L'atleta lavora sotto il limite di mantenimento del carico cronico, richiedendo un rialzo progressivo dei volumi per non renderlo vulnerabile a repentini balzi di intensità."
                    ]
                elif acwr_sett_tl_dec <= 1.30:
                    v_opts = [
                        f"Il volume di lavoro si colloca perfettamente nella sweet spot fisiologica ottimale (ACWR {acwr_sett_tl_dec:.2f} / {acwr_sett_tl_pct:.0f}%). Questo livello garantisce una potente stimolazione degli adattamenti fisiologici e cardiovascolari, massimizzando lo sviluppo della fitness e proteggendo al contempo le strutture tendinee e legamentose dal sovraccarico.",
                        f"Microciclo volumetrico ideale: il rapporto tra carico acuto e cronico ({acwr_sett_tl_dec:.2f}) rispetta in pieno i canoni ideali di Gabbett. La progressione volumetrica sostiene la cilindrata atletica del tennista, costruendo una robusta barriera protettiva contro i microtraumi da stress cumulativo.",
                        f"Gestione impeccabile del volume globale di lavoro, posizionato nella zona di sicurezza e massima resa prestazionale (ACWR {acwr_sett_tl_dec:.2f}). La risposta adattativa dell'organismo è ideale, con un perfetto equilibrio tra stress indotto e capacità di recupero organico."
                    ]
                elif acwr_sett_tl_dec <= 1.50:
                    v_opts = [
                        f"Il volume settimanale è entrato nella fascia di allerta alta (ACWR {acwr_sett_tl_dec:.2f} / {acwr_sett_tl_pct:.0f}%). Sebbene il carico sia ancora gestibile, l'organismo è sollecitato intensamente e comincia ad accumulare stanchezza residua. È raccomandato monitorare il sonno e la percezione soggettiva di fatica.",
                        f"Si rileva un incremento volumetrico marcato (ACWR {acwr_sett_tl_dec:.2f}), vicino alla soglia critica. Il sovraccarico acuto richiede un'attenta calibrazione delle pause tra le sessioni per prevenire l'insorgere di microlesioni da sovradosaggio chilometrico.",
                        f"Volume in decisa salita rispetto al consueto storico (ACWR {acwr_sett_tl_dec:.2f}). L'atleta sta sostenendo una fase di overreaching funzionale: lo stimolo è produttivo solo se seguito da un microciclo di opportuno assorbimento e scarico."
                    ]
                else:
                    v_opts = [
                        f"ATTENZIONE — Spike di carico acuto critico (ACWR {acwr_sett_tl_dec:.2f} / {acwr_sett_tl_pct:.0f}%). L'impennata del volume supera la soglia di sicurezza di 1.50, esponendo l'atleta a un incremento esponenziale del rischio di infortunio muscolare e tendineo (danger zone). È categoricamente raccomandato ridurre i volumi nei giorni a seguire.",
                        f"ALLARME SOVRACCARICO: picco di volume eccessivo e repentino con ACWR a {acwr_sett_tl_dec:.2f}. Il delta tra il carico acuto erogato e la preparazione cronica pregressa è troppo ampio, esponendo l'apparato muscolo-scheletrico a stress meccanico anomalo.",
                        f"Criticità sul fronte volumetrico: l'indice ACWR schizza a quota {acwr_sett_tl_dec:.2f}, configurando una situazione di acuto iper-affaticamento. Senza un tempestivo e programmato scarico, le probabilità di problematiche da overuse aumentano sensibilmente."
                    ]
                testo_vol_base = v_opts[seed_v]

                # Analisi comparativa Rolling 7 Giorni
                delta_roll = abs(acwr_sett_tl_dec - acwr_roll_tl_dec)
                if delta_roll >= 0.15:
                    testo_vol_roll = f" In parallelo, l'ACWR Rolling a 7 giorni ({acwr_roll_tl_dec:.2f}) diverge rispetto al calendario standard ({acwr_sett_tl_dec:.2f}), segnalando una concentrazione disomogenea degli sforzi a ridosso dell'inizio o della fine del microciclo."
                else:
                    testo_vol_roll = f" L'indice ACWR Rolling a 7 giorni ({acwr_roll_tl_dec:.2f}) conferma la piena coerenza e stabilità del carico su finestra mobile continua."
                testo_volume_totale = testo_vol_base + testo_vol_roll

                # SEZIONE 2: INTENSITÀ (TL High) & GESTIONE NEUROMUSCOLARE
                if pct_tlh_w < 18.0 or tot_tlh_w < 200:
                    i_opts = [
                        f"L'esposizione al lavoro ad Alta Intensità (TL High) è decisamente carente ({pct_tlh_w:.1f}% del carico totale, pari a {tot_tlh_w:,.0f} AU). L'atleta sta perdendo il necessario adattamento neuromuscolare agli sforzi massimali e alle alte velocità. Questa assenza cronica di stimoli di picco lo rende estremamente e pericolosamente vulnerabile in caso di richieste esplosive improvvise durante la gara.",
                        f"Quota di Alta Intensità sotto-soglia ({pct_tlh_w:.1f}% del Training Load). Gli stimoli neuromuscolari qualitativi e le accelerazioni ad alto wattaggio sono insufficienti per mantenere l'efficienza della stiffness tendinea e la reattività dei pattern motori specifici da match.",
                        f"Carenza di stimoli anaerobici ed esplosivi: solo il {pct_tlh_w:.1f}% del lavoro settimanale è stato speso in fascia TL High. È opportuno reintrodurre gradualmente blocchi ad alta intensità per riabituare il sistema neuromuscolare alla velocità di gioco."
                    ]
                elif pct_tlh_w <= 35.0:
                    i_opts = [
                        f"Ottimo bilanciamento dell'alta intensità ({pct_tlh_w:.1f}% del Training Load, {tot_tlh_w:,.0f} AU). La percentuale di carico ad alto impatto neuromuscolare stimola efficacemente le fibre a contrazione rapida e mantiene intatta la reattività dinamica senza intasare la fisiologia muscolare.",
                        f"Distribuzione dell'intensità eseguita a regola d'arte: con il {pct_tlh_w:.1f}% di TL High, l'atleta stimola la velocità e la potenza metabolica nel rispetto delle capacità di assorbimento del microciclo.",
                        f"Profilo d'intensità ideale: la quota di carico esplosivo ({pct_tlh_w:.1f}%) fornisce il corretto transfer qualitativo alle situazioni agonistiche, preservando la freschezza e la lucidità decisionale."
                    ]
                else:
                    i_opts = [
                        f"Esposizione molto spinta al lavoro ad Alta Intensità ({pct_tlh_w:.1f}% del volume totale, {tot_tlh_w:,.0f} AU). L'atleta ha sostenuto un elevatissimo stress anaerobico ed esplosivo, che richiede un monitoraggio serrato dell'estensibilità e del tono dei muscoli flessori e degli estensori del ginocchio.",
                        f"Intensità preponderante nel microciclo ({pct_tlh_w:.1f}% TL High). Le richieste meccaniche su decelerazioni e frenate hanno raggiunto quote ragguardevoli; fondamentale programmare idratazione profonda e decontrattura miofasciale.",
                        f"Spiccata sollecitazione neuromuscolare ({pct_tlh_w:.1f}% TL High). Un dosaggio così elevato di alta intensità richiede che le prossime sessioni concedano pieno spazio al defaticamento metabolico."
                    ]
                testo_int_base = i_opts[seed_v]

                # Spaziatura neuromuscolare
                if has_consecutive_tlh:
                    testo_int_spacing = " ALLARME GESTIONE PICCHI: Si riscontrano sessioni ad alta intensità neuromuscolare ravvicinate o consecutive (distanza < 48 ore). Questa sovrapposizione priva il sistema muscolare e il sistema nervoso periferico delle canoniche 48/72 ore necessarie per riparare i microtraumi e ripristinare il glicogeno, innalzando bruscamente la vulnerabilità a contratture e sovraccarichi mio-tendinei."
                elif len(peak_indices_tlh) >= 2:
                    testo_int_spacing = " La gestione dei picchi di intensità è magistrale. Le sessioni ad alto impatto neuromuscolare sono state spaziate e isolate con estrema intelligenza, garantendo al muscolo e al sistema nervoso le canoniche 48/72 ore per riparare i microtraumi. Questa strategia previene efficacemente l'irrigidimento muscolare cronico e tutela nel tempo la performance."
                elif len(peak_indices_tlh) == 1:
                    testo_int_spacing = " Il picco settimanale di intensità risulta unico e perfettamente isolato nel microciclo, garantendo una completa assimilazione dello stimolo neuromuscolare senza alcun attrito con le altre sedute."
                else:
                    testo_int_spacing = " Il microciclo non ha presentato picchi isolati ad altissima richiesta neuromuscolare, mantenendo un profilo uniforme e privo di stress meccanici improvvisi."
                testo_intensita_totale = testo_int_base + " " + testo_int_spacing

                # SEZIONE 3: VARIABILITÀ, MONOTONIA & TRAINING STRAIN (Foster)
                if mono_tlh < 1.50:
                    testo_mono = f"L'Indice di Monotonia di Foster ({mono_tlh:.2f} su TL High) si attesta su livelli eccellenti (< 1.50). La distribuzione quotidiana del lavoro è caratterizzata da una spiccata e fisiologica alternanza tra giornate di carico importante e giornate di recupero attivo o riposo. Questa variabilità strutturale protegge il sistema nervoso centrale dall'esaurimento e garantisce un'ottima fase di supercompensazione."
                elif mono_tlh <= 2.00:
                    testo_mono = f"La variabilità del carico si mantiene su livelli controllati e soddisfacenti (Monotonia Foster = {mono_tlh:.2f}). Il microciclo alterna stimoli e recupero in modo bilanciato, pur con margini per accentuare ulteriormente il contrasto tra le giornate ad alto impatto e i momenti di reale scarico rigenerativo."
                else:
                    testo_mono = f"ALLERTA MONOTONIA: L'indice di Foster supera la soglia critica ({mono_tlh:.2f} > 2.00). La somministrazione del carico è risultata eccessivamente uniforme e piatta giorno dopo giorno, senza una reale alternanza con giornate di riposo completo o netto scarico. Questo pattern monotono rappresenta uno dei fattori di rischio primari per l'overtraining sindrome e il calo prestativo."

                if strain_tlh <= 1800:
                    testo_strain = f" L'indice di Training Strain ({strain_tlh:,.0f} AU) riflette uno stress biologico moltiplicativo ben tollerato, perfettamente compatibile con la fisiologia dell'atleta."
                elif strain_tlh <= 3000:
                    testo_strain = f" Il Training Strain ({strain_tlh:,.0f} AU) segnala un carico moltiplicativo importante: la combinazione di volume e intensità costante consiglia di inserire un giorno di completo riposo passivo per favorire il recupero sistemico."
                else:
                    testo_strain = f" ATTENZIONE STRAIN: L'indice di Training Strain raggiunge valori acuti elevati ({strain_tlh:,.0f} AU), moltiplicando il carico per la rigidità dello stimolo. Si raccomanda prudenza e decompressione immediata."
                testo_monotonia_totale = testo_mono + testo_strain

                if is_cur_week:
                    testo_cur_extra = f" [STATO SETTIMANA IN CORSO]: Rilevazione condotta ad oggi ({day_names_full[giorno_rif_idx]} {d_ref_eval.strftime('%d/%m')}) con {tot_sessioni_w} sessioni registrate su {giorni_trascorsi}/7 giorni. Per completare il microciclo senza superare la soglia di allerta (ACWR 1.30 e Monotonia 2.0), si raccomanda di preservare almeno un giorno di scarico attivo o riposo nelle restanti giornate."
                    testo_monotonia_totale += f"<br><br><span style='color:#0284c7; font-weight:700;'>{testo_cur_extra}</span>"

                # Testo formattato WhatsApp
                badge_sett_txt = f"{settimana_valutata} (IN CORSO - {day_names_short[giorno_rif_idx]} {d_ref_eval.strftime('%d/%m')})" if is_cur_week else f"{settimana_valutata} (CONCLUSA)"
                
                opzioni_pdf_ref = {
                    tr("Referto Clinico & Prestazionale", "Clinical & Performance Report"): "Referto"
                }
                render_action_bar(
                    meta_items=[
                        (tr("Atleta", "Athlete"), giocatore_selezionato),
                        (tr("Microciclo", "Microcycle"), badge_sett_txt),
                        (tr("ACWR Sett.", "Weekly ACWR"), f"{acwr_sett_tl_dec:.2f}"),
                        (tr("Monotonia", "Monotony"), f"{mono_tlh:.2f}"),
                        (tr("Training Strain", "Training Strain"), f"{strain_tlh:,.0f} AU"),
                    ],
                    pdf_options=opzioni_pdf_ref,
                    pdf_key=f"pdf_referto_{slugify_name(giocatore_selezionato)}_{slugify_name(settimana_valutata)}",
                    generate_fn=lambda _: crea_pdf_referto_settimanale(
                        giocatore=giocatore_selezionato,
                        settimana_label=badge_sett_txt,
                        testo_volume=testo_volume_totale,
                        testo_intensita=testo_intensita_totale,
                        testo_monotonia=testo_monotonia_totale,
                        kpis={
                            'minuti': tot_min_w,
                            'tl': tot_tl_w,
                            'tlh': tot_tlh_w,
                            'acc': tot_acc_w,
                            'dec': tot_dec_w,
                            'acwr': acwr_sett_tl_dec,
                            'mono': mono_tlh,
                            'strain': strain_tlh
                        }
                    ),
                    filename_fn=lambda _: f"M0V3_Referto_Settimanale_{slugify_name(giocatore_selezionato)}_{slugify_name(settimana_valutata)}.pdf"
                )

                testo_whatsapp = (
                    f"*M0V3 ANALYTICS — REFERTO CLINICO & PRESTAZIONALE*\n"
                    f"*Atleta:* {giocatore_selezionato}\n"
                    f"*Microciclo:* {badge_sett_txt}\n\n"
                    f"*KPI SINTETICI:*\n"
                    f"• ACWR Settimanale: {acwr_sett_tl_dec:.2f} ({acwr_sett_tl_pct:.0f}%)\n"
                    f"• ACWR Rolling 7D: {acwr_roll_tl_dec:.2f}\n"
                    f"• TL Totale: {tot_tl_w:,.0f} AU | TL High: {tot_tlh_w:,.0f} AU ({pct_tlh_w:.1f}%)\n"
                    f"• Monotonia Foster (TL High): {mono_tlh:.2f}\n"
                    f"• Training Strain: {strain_tlh:,.0f} AU\n\n"
                    f"*VOLUME (TL) & ACWR:*\n{testo_volume_totale}\n\n"
                    f"*INTENSITÀ (TL High) & GESTIONE NEUROMUSCOLARE:*\n{testo_intensita_totale}\n\n"
                    f"*VARIABILITÀ, MONOTONIA & TRAINING STRAIN:*\n{testo_monotonia_totale}\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"Generato con M0V3 Analytics GPS & IMU"
                )

                # --- HEADER & RIBBON KPI ---
                badge_status_lbl = tr('IN CORSO', 'IN PROGRESS') if is_cur_week else tr('MICROCICLO CONCLUSO', 'CONCLUDED MICROCYCLE')
                badge_bg = 'rgba(245, 158, 11, 0.2)' if is_cur_week else 'rgba(16, 185, 129, 0.2)'
                badge_col = '#f59e0b' if is_cur_week else '#10b981'

                html_ribbon = f"""<div style="background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); border-radius: 12px; padding: 18px 24px; margin-bottom: 20px; box-shadow: 0 4px 14px rgba(0,0,0,0.12); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;">
<div>
<div style="color: #38bdf8; font-size: 11.5px; font-weight: 800; letter-spacing: 1px; text-transform: uppercase;">
<i class="bi bi-file-earmark-medical" style="margin-right:6px;"></i>{tr('REFERTO CLINICO & VALUTAZIONE DEL CARICO', 'CLINICAL & LOAD REPORT')}
</div>
<div style="color: #ffffff; font-size: 20px; font-weight: 900; margin-top: 2px;">
{giocatore_selezionato} — <span style="color:#f59e0b;">{settimana_valutata}</span>
</div>
</div>
<div style="display: flex; gap: 10px; align-items: center;">
<span style="background: {badge_bg}; color: {badge_col}; border: 1px solid {badge_col}; padding: 6px 14px; border-radius: 20px; font-size: 12px; font-weight: 800;">
{badge_status_lbl}
</span>
</div>
</div>"""
                st.html(html_ribbon)

                # 4 Card KPI Orizzontali
                k_col1, k_col2, k_col3, k_col4 = st.columns(4)
                with k_col1:
                    col_ac_s = "#10b981" if 0.8 <= acwr_sett_tl_dec <= 1.3 else ("#f59e0b" if acwr_sett_tl_dec <= 1.5 else "#ef4444")
                    st.markdown(
                        card_kpi(
                            tr("ACWR Settimanale", "Weekly ACWR"),
                            f"<span style='font-size:22px; font-weight:900; color:{col_ac_s};'>{acwr_sett_tl_dec:.2f}</span>",
                            f"{tot_tl_w:,.0f} TL ({acwr_sett_tl_pct:.0f}%)",
                            col_ac_s
                        ),
                        unsafe_allow_html=True
                    )
                with k_col2:
                    col_ac_r = "#10b981" if 0.8 <= acwr_roll_tl_dec <= 1.3 else ("#f59e0b" if acwr_roll_tl_dec <= 1.5 else "#ef4444")
                    st.markdown(
                        card_kpi(
                            tr("ACWR Rolling 7D", "Rolling 7D ACWR"),
                            f"<span style='font-size:22px; font-weight:900; color:{col_ac_r};'>{acwr_roll_tl_dec:.2f}</span>",
                            f"{tot_tl_r7:,.0f} TL (7 gg)",
                            col_ac_r
                        ),
                        unsafe_allow_html=True
                    )
                with k_col3:
                    col_mono = "#10b981" if mono_tlh < 2.0 else "#ef4444"
                    lbl_mono = tr("Variabilità Ottimale", "Optimal") if mono_tlh < 2.0 else tr("Carico Piatto (Allarme)", "Flat Alert")
                    st.markdown(
                        card_kpi(
                            tr("Monotonia TL High", "TL High Monotony"),
                            f"<span style='font-size:22px; font-weight:900; color:{col_mono};'>{mono_tlh:.2f}</span>",
                            f"{lbl_mono}",
                            col_mono
                        ),
                        unsafe_allow_html=True
                    )
                with k_col4:
                    col_str = "#ef4444" if strain_tlh > 3000 else ("#f59e0b" if strain_tlh > 1800 else "#0284c7")
                    st.markdown(
                        card_kpi(
                            tr("Training Strain (TL High)", "TL High Strain"),
                            f"<span style='font-size:22px; font-weight:900; color:{col_str};'>{strain_tlh:,.0f}</span>",
                            f"{tot_tlh_w:,.0f} TLH ({pct_tlh_w:.0f}%)",
                            col_str
                        ),
                        unsafe_allow_html=True
                    )

                st.markdown("<div style='margin-top: 20px;'></div>", unsafe_allow_html=True)

                # --- BOX REFERTO CLINICO & PRESTAZIONALE (STILE EXECUTIVE M0V3) ---
                titolo_box = tr("REFERTO SETTIMANA IN CORSO", "CURRENT WEEK REPORT") if is_cur_week else tr("REFERTO ULTIMA SETTIMANA", "WEEKLY CLINICAL REPORT")
                html_card = f"""<div style="background: #ffffff; border: 1.5px solid #e2e8f0; border-top: 4px solid #0ea5e9; border-radius: 12px; padding: 24px 28px; box-shadow: 0 4px 16px rgba(15, 23, 42, 0.05); font-family: 'Inter', sans-serif;">
<div style="text-align: center; border-bottom: 2px solid #f1f5f9; padding-bottom: 14px; margin-bottom: 22px;">
<div style="font-size: 11.5px; font-weight: 800; color: #ef4444; text-transform: uppercase; letter-spacing: 1.5px;">{tr("Analisi descrittiva e riassuntiva dell'analisi", "Descriptive and Summary Performance Analysis")}</div>
<div style="font-size: 18px; font-weight: 900; color: #0f172a; text-transform: uppercase; letter-spacing: 0.8px; margin-top: 4px;">ACWR • MONOTONIA • TRAINING STRAIN</div>
</div>
<div style="text-align: center; margin-bottom: 24px;">
<span style="font-size: 13.5px; font-weight: 800; color: #0f172a; letter-spacing: 0.5px; background: #f8fafc; padding: 6px 18px; border-radius: 20px; border: 1px solid #cbd5e1; display: inline-flex; align-items: center; gap: 8px;"><i class="bi bi-file-earmark-text-fill" style="color:#0ea5e9;"></i>{titolo_box}</span>
</div>
<div style="margin-bottom: 20px; line-height: 1.7; font-size: 14px; color: #0f172a; text-align: justify;">
<span style="display:inline-flex; align-items:center; justify-content:center; width:22px; height:22px; border-radius:50%; background:#e0f2fe; color:#0284c7; font-size:11px; margin-right:8px; vertical-align:middle;"><i class="bi bi-speedometer2"></i></span> <b style="color: #0284c7; font-weight: 800; text-transform: uppercase;">VOLUME (TL) & ACWR:</b> <span style="font-style: italic; color: #334155;">{testo_volume_totale}</span>
</div>
<div style="margin-bottom: 20px; line-height: 1.7; font-size: 14px; color: #0f172a; text-align: justify;">
<span style="display:inline-flex; align-items:center; justify-content:center; width:22px; height:22px; border-radius:50%; background:#fee2e2; color:#dc2626; font-size:11px; margin-right:8px; vertical-align:middle;"><i class="bi bi-lightning-charge-fill"></i></span> <b style="color: #dc2626; font-weight: 800; text-transform: uppercase;">INTENSITÀ (TL High) & GESTIONE NEUROMUSCOLARE:</b> <span style="font-style: italic; color: #334155;">{testo_intensita_totale}</span>
</div>
<div style="margin-bottom: 8px; line-height: 1.7; font-size: 14px; color: #0f172a; text-align: justify;">
<span style="display:inline-flex; align-items:center; justify-content:center; width:22px; height:22px; border-radius:50%; background:#fef3c7; color:#b45309; font-size:11px; margin-right:8px; vertical-align:middle;"><i class="bi bi-activity"></i></span> <b style="color: #b45309; font-weight: 800; text-transform: uppercase;">VARIABILITÀ, MONOTONIA & TRAINING STRAIN (Foster):</b> <span style="font-style: italic; color: #334155;">{testo_monotonia_totale}</span>
</div>
</div>"""
                st.html(html_card)

                st.markdown("<div style='margin-top: 18px;'></div>", unsafe_allow_html=True)

                # --- PULSANTE CONDIVISIONE / WHATSAPP PER LO STAFF TECNICO ---
                c_sh1, c_sh2 = st.columns([1, 1])
                with c_sh1:
                    with st.expander(tr("Copia Referto per WhatsApp / Staff Tecnico", "Copy Report for WhatsApp / Technical Staff"), expanded=True, icon=":material/send:"):
                        st.caption(tr("Testo pre-formattato con sintassi WhatsApp (grassetto, elenchi). Clicca sull'icona di copia in alto a destra del box sottostante:", "Pre-formatted text for WhatsApp (bold, lists). Click the copy icon in the top right of the code box:"))
                        st.code(testo_whatsapp, language="markdown")
                with c_sh2:
                    with st.expander(tr("Note Metodologiche & Parametri di Riferimento", "Methodological Notes & Reference Parameters"), expanded=False, icon=":material/info:"):
                        st.markdown(
                            f"""
                            <div style="font-size: 13px; color: #334155; line-height: 1.6;">
                                <b>Parametri Fisici Analizzati nel Referto:</b><br>
                                • <b>ACWR Uncoupled EWMA (Williams / Impellizzeri)</b>: Modello matematico ponderato esponenzialmente (7d acuto / 28d cronico disaccoppiato). Sweet spot: <b>0.80 - 1.25 (80-125%)</b>.<br>
                                • <b>TL High & Spaziatura Neuromuscolare</b>: Monitoraggio della quota di alta intensità e intervallo minimo di <b>48-72 ore</b> tra i picchi per la rigenerazione del SNC e la prevenzione microtraumi.<br>
                                • <b>Monotonia di Foster (&mu; / &sigma;)</b>: Calcolata sui dati reali giornalieri del microciclo (inclusi giorni di riposo = 0). Soglia allerta: <b>> 2.0</b>.<br>
                                • <b>Training Strain (Carico &times; Monotonia)</b>: Indice moltiplicativo dello stress biologico complessivo.
                            </div>
                            """,
                            unsafe_allow_html=True
                        )

            st.markdown("<div style='margin-top: 25px;'></div>", unsafe_allow_html=True)
            render_scientific_methodology_box("acwr")






