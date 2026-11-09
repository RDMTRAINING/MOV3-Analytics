import os
import re
import secrets
import datetime
from datetime import datetime, timedelta, date
import numpy as np
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
    render_action_bar,
    render_tab_navigation,
)
from utils import (
    supabase,
    supabase_admin,
    CANONICAL_TIPOLOGIE_SESSIONE,
    COLORI_TIPOLOGIE_SESSIONE,
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
    stato_acwr,
    etichetta_scostamento,
    frase_riepilogo,
    card_kpi,
    delta_puro,
    delta_confronto,
    calcola_blocchi_baseline,
    get_atleti_associati,
    get_tutti_gli_atleti,
    slugify_name,
    acwr_zone_meta,
    render_pct_progress_bar,
    render_pct_badge_cell,
    render_executive_chart_header,
    render_athlete_hero_strip,
    render_dual_athlete_strip,
)
from pdf_generator import (
    crea_pdf_m0v3,
    crea_pdf_sessione_m0v3,
    crea_pdf_weekly_m0v3,
    crea_pdf_storico_m0v3,
    crea_pdf_medie_m0v3,
)

def render_medie(t):
    render_page_header(t['avg_title'], t['avg_desc'], tr("BENCHMARK & CONFRONTI", "BENCHMARKS & COMPARISONS"))

    df_storico = load_local_database()
    if df_storico.empty: st.warning(t['am_no_db']); return

    if st.session_state['role'] != 'Super-Admin':
        atleti_assoc = get_atleti_associati(st.session_state['user'].id)
        if not atleti_assoc: st.warning(t['up_no_atl']); return
        df_storico = df_storico[df_storico['Players'].isin(atleti_assoc)]

    df_reale = df_storico[df_storico['Dato_Simulato'] == False].copy()
    if df_reale.empty: st.warning(tr("Nessun dato reale (non simulato) disponibile per generare le medie.", "No real (non-simulated) data available to generate averages.")); return

    # Ricava gli atleti direttamente dai dati presenti nel database reale
    atleti_consentiti = sorted(df_reale['Players'].dropna().unique().tolist())
    if not atleti_consentiti:
        st.warning(tr("Nessun giocatore trovato nel database.", "No players found in database."))
        return

    col_analisi = ['Minuti', 'Training Load', 'TL_High', 'High Accel IMU', 'High Decel IMU', 'Azioni Int. IMU >2', 'Azioni Int. IMU >10', 'Recuperi IMU 1-5m']
    for c in col_analisi:
        if c not in df_reale.columns: df_reale[c] = 0
        if c not in df_storico.columns: df_storico[c] = 0
    df_reale[col_analisi] = df_reale[col_analisi].apply(pd.to_numeric, errors='coerce').fillna(0)
    df_storico[col_analisi] = df_storico[col_analisi].apply(pd.to_numeric, errors='coerce').fillna(0)

    # Pre-calcolo settimane per il Testa a Testa Settimanale e Ranking Roster
    df_reale['Date_obj'] = pd.to_datetime(df_reale['Date'], format='%d/%m/%Y', errors='coerce')
    df_reale['Week_Start'] = df_reale['Date_obj'] - pd.to_timedelta(df_reale['Date_obj'].dt.dayofweek, unit='d')
    df_reale['Week_End'] = df_reale['Week_Start'] + pd.to_timedelta(6, unit='d')
    df_reale['Week_Label'] = df_reale['Week_Start'].dt.strftime('%d/%m/%Y') + " - " + df_reale['Week_End'].dt.strftime('%d/%m/%Y')

    df_storico['Date_obj'] = pd.to_datetime(df_storico['Date'], format='%d/%m/%Y', errors='coerce')
    df_storico['Week_Start'] = df_storico['Date_obj'] - pd.to_timedelta(df_storico['Date_obj'].dt.dayofweek, unit='d')
    df_storico['Week_End'] = df_storico['Week_Start'] + pd.to_timedelta(6, unit='d')
    df_storico['Week_Label'] = df_storico['Week_Start'].dt.strftime('%d/%m/%Y') + " - " + df_storico['Week_End'].dt.strftime('%d/%m/%Y')

    oggi_norm = pd.Timestamp.today().normalize()
    curr_w_start = oggi_norm - timedelta(days=oggi_norm.dayofweek)
    curr_w_end = curr_w_start + timedelta(days=6)
    curr_w_lbl = f"{curr_w_start.strftime('%d/%m/%Y')} - {curr_w_end.strftime('%d/%m/%Y')}"

    settimane_univoche = df_reale['Week_Label'].dropna().unique().tolist()
    settimane_univoche.sort(key=lambda x: pd.to_datetime(x.split(" - ")[0], format='%d/%m/%Y'), reverse=True)

    opt_cur_week = f"[{tr('Settimana Corrente', 'Current Week')}] {curr_w_lbl}"
    if curr_w_lbl in settimane_univoche:
        opts_settimane_h2h = [opt_cur_week] + [s for s in settimane_univoche if s != curr_w_lbl]
    else:
        opts_settimane_h2h = [opt_cur_week] + settimane_univoche

    if st.session_state.get('role') == 'Super-Admin':
        report_abilitati = CATALOGO_REPORT.get("Medie", [])
    else:
        try:
            res_rep = supabase.table('moduli_report').select('nome_report').eq('profilo_id', st.session_state['user'].id).eq('area', 'Medie').execute()
            report_abilitati = [r['nome_report'] for r in res_rep.data] if res_rep.data else []
        except Exception:
            report_abilitati = []

    st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)

    # Mostra le sei sottopagine (PERSISTENTI & REATTIVE M0V3)
    T_SING = tr("Analisi Singolo Atleta", "Single Athlete Analysis")
    T_COMP_M = tr("Testa a Testa Medie", "Head-to-Head Averages")
    T_COMP_W = tr("Testa a Testa Settimana", "Head-to-Head Weekly")
    T_RANK = tr("Ranking Roster Atleti", "Athlete Roster Ranking")
    T_DIST_R = tr("Distribuzione Lavoro Roster", "Roster Workload Distribution")
    T_STRESS_R = tr("Stress Roster 8 Settimane", "Roster Stress 8 Weeks")

    medie_tabs = [T_SING, T_COMP_M, T_COMP_W, T_RANK, T_DIST_R, T_STRESS_R]
    active_medie_tab = render_tab_navigation(medie_tabs, key="nav_medie_master")

    if active_medie_tab == T_SING:
        if "Analisi Singolo Atleta" not in report_abilitati and st.session_state.get('role') != 'Super-Admin':
            st.info(tr("Il modulo 'Analisi Singolo Atleta' non è abilitato per questo account. Contatta l'amministratore.", "The 'Analisi Singolo Atleta' module is not enabled for this account. Contact admin."))
        else:
            lbl_t1_h = tr("Profilo Medie Assolute per Tipologia di Sessione", "Absolute Averages Profile by Session Type")
        st.markdown(f"<h3 style='color:#0f172a; margin-top:10px;'>{lbl_t1_h}</h3>", unsafe_allow_html=True)
        glob_ath = st.session_state.get('selected_athlete')
        if glob_ath in atleti_consentiti:
            atleta_sel = glob_ath
        elif 'avg_ath' in st.session_state and st.session_state['avg_ath'] in atleti_consentiti:
            atleta_sel = st.session_state['avg_ath']
        else:
            atleta_sel = atleti_consentiti[0] if atleti_consentiti else None
        st.session_state['avg_ath'] = atleta_sel
        df_ath = df_reale[df_reale['Players'] == atleta_sel] if atleta_sel else pd.DataFrame()

        # Striscia Compatta Identità Atleta MOV3
        if atleta_sel:
            render_athlete_hero_strip(atleta_sel, df_atleta=df_ath)

        if df_ath.empty:
            st.info(tr("Nessun dato reale per questo atleta.", "No real data for this athlete."))
        else:
            df_grouped = df_ath.groupby('Tipologia Sessione')[col_analisi].mean().round(1)
            df_counts = df_ath.groupby('Tipologia Sessione').size()

            opzioni_pdf_sing = {
                tr("Profilo Medie Completo", "Full Averages Profile"): "Singolo"
            }
            render_action_bar(
                meta_items=[
                    (tr("Atleta", "Athlete"), atleta_sel),
                    (tr("Sessioni Totali Reali", "Total Real Sessions"), str(len(df_ath))),
                    (tr("Tipologie Mappate", "Mapped Types"), str(len(df_grouped))),
                ],
                pdf_options=opzioni_pdf_sing,
                pdf_key="avg_sing",
                generate_fn=lambda _: crea_pdf_medie_m0v3("singolo", atleta=atleta_sel, df_grouped=df_grouped),
                filename_fn=lambda _: f"M0V3_Medie_Profilo_Singolo_{slugify_name(atleta_sel)}.pdf"
            )

            col_meta_map = [
                ("Minuti", tr("Durata (min)", "Duration (min)"), "VOLUME", "#f59e0b"),
                ("Training Load", "Training Load", "VOLUME", "#f59e0b"),
                ("TL_High", "TL High", "HIGH INT", "#ef4444"),
                ("High Accel IMU", "High Accel", "HIGH INT", "#ef4444"),
                ("High Decel IMU", "High Decel", "HIGH INT", "#ef4444"),
                ("Azioni Int. IMU >2", tr('Azioni >2"', 'Actions >2"'), "VOLUME", "#f59e0b"),
                ("Azioni Int. IMU >10", tr('Azioni >10"', 'Actions >10"'), "VOLUME", "#f59e0b"),
                ("Recuperi IMU 1-5m", tr("Recuperi 1-5m", "Recoveries 1-5m"), "RECOVERY", "#10b981"),
            ]

            lbl_b1_title = tr("BENCHMARK PROFILO STORICO PER TIPOLOGIA DI SESSIONE", "HISTORICAL BENCHMARK PROFILE BY SESSION TYPE")
            lbl_b1_sub = tr(f"Atleta: {atleta_sel} • Valori medi calcolati su {len(df_ath)} sessioni reali", f"Athlete: {atleta_sel} • Mean values across {len(df_ath)} real sessions")
            th_sess_lbl = tr("Tipologia Sessione", "Session Type")
            th_cnt_lbl = tr("N° Sess.", "Sessions")

            th_cols_html = ""
            for col_k, col_lbl, cat_t, cat_c in col_meta_map:
                th_cols_html += (
                    f"<th style='text-align:center; padding:12px 8px; color:#0f172a; font-size:10.5px; font-weight:800; text-transform:uppercase; letter-spacing:0.04em;'>"
                    f"<div>{col_lbl}</div>"
                    f"<span style='display:inline-block; margin-top:2px; font-size:8.5px; font-weight:800; color:{cat_c}; background:{cat_c}14; padding:1px 5px; border-radius:4px;'>{cat_t}</span>"
                    f"</th>"
                )

            rows_b1_html = ""
            sess_palette = {
                "match": ("#ef4444", "#fef2f2"),
                "fisica": ("#f59e0b", "#fffbeb"),
                "tecnica": ("#0ea5e9", "#f0f9ff"),
                "recupero": ("#10b981", "#ecfdf5"),
            }
            for idx_s, (sess_name, row_vals) in enumerate(df_grouped.iterrows()):
                bg_r = "#ffffff" if idx_s % 2 == 0 else "#f8fafc"
                s_low = str(sess_name).lower()
                s_col, s_bg = sess_palette.get(s_low, ("#475569", "#f1f5f9"))
                cnt_s = int(df_counts.get(sess_name, 0))
                tds_vals = ""
                for col_k, _, _, _ in col_meta_map:
                    v_num = float(row_vals.get(col_k, 0.0))
                    tds_vals += f"<td style='padding:14px 8px; text-align:center; font-size:15.5px; font-weight:800; color:#0f172a;'>{v_num:.1f}</td>"
                rows_b1_html += (
                    f"<tr style='background:{bg_r}; border-bottom:1px solid #f1f5f9;'>"
                    f"<td style='padding:14px 16px;'>"
                    f"<span style='display:inline-block; background:{s_bg}; color:{s_col}; border:1px solid {s_col}35; font-size:12px; font-weight:900; padding:4px 10px; border-radius:6px; text-transform:uppercase; letter-spacing:0.04em;'>{sess_name}</span>"
                    f"</td>"
                    f"<td style='padding:14px 8px; text-align:center;'>"
                    f"<span style='background:#f1f5f9; color:#475569; font-size:11.5px; font-weight:800; padding:3px 8px; border-radius:999px;'>{cnt_s}</span>"
                    f"</td>"
                    f"{tds_vals}"
                    f"</tr>"
                )

            table_b1_html = (
                "<div style='background:#ffffff; border-radius:14px; border:1px solid #e2e8f0; box-shadow:0 4px 12px -2px rgba(15,23,42,0.05); overflow-x:auto; margin-top:10px; margin-bottom:22px; font-family:\"Inter\",sans-serif;'>"
                "<div style='background:linear-gradient(135deg, #0f172a 0%, #1e293b 100%); padding:14px 20px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;'>"
                "<div style='display:flex; align-items:center; gap:10px;'>"
                "<span style='width:8px; height:8px; border-radius:50%; background:#38bdf8; display:inline-block;'></span>"
                f"<span style='color:#ffffff; font-size:13px; font-weight:800; text-transform:uppercase; letter-spacing:0.06em;'>{lbl_b1_title}</span>"
                "</div>"
                f"<span style='color:#94a3b8; font-size:11px; font-weight:600;'>{lbl_b1_sub}</span>"
                "</div>"
                "<table style='width:100%; border-collapse:collapse;'>"
                "<thead><tr style='background:#f8fafc; border-bottom:2px solid #e2e8f0;'>"
                f"<th style='text-align:left; padding:12px 16px; color:#475569; font-size:10.5px; font-weight:800; text-transform:uppercase; letter-spacing:0.06em;'>{th_sess_lbl}</th>"
                f"<th style='text-align:center; padding:12px 8px; color:#64748b; font-size:10.5px; font-weight:800; text-transform:uppercase; letter-spacing:0.06em;'>{th_cnt_lbl}</th>"
                f"{th_cols_html}"
                "</tr></thead>"
                f"<tbody>{rows_b1_html}</tbody></table></div>"
            )
            st.markdown(table_b1_html, unsafe_allow_html=True)

            if len(df_grouped) > 0:
                c_ch1, c_ch2 = st.columns(2)
                sess_names_list = [str(x) for x in df_grouped.index.tolist()]
                tl_vals_list = [float(x) for x in df_grouped['Training Load'].tolist()]
                tlh_vals_list = [float(x) for x in df_grouped['TL_High'].tolist()]
                max_tl_g = max(tl_vals_list) * 1.25 if max(tl_vals_list) > 0 else 100
                max_tlh_g = max(tlh_vals_list) * 1.25 if max(tlh_vals_list) > 0 else 50

                with c_ch1:
                    with st.container(border=True):
                        st.markdown(render_executive_chart_header(
                            tr("Training Load Medio per Tipologia", "Mean Training Load by Session Type"),
                            pills=[(tr("Picco", "Peak"), f"{max(tl_vals_list):.0f} AU", "#38bdf8")],
                            accent="#0ea5e9"
                        ), unsafe_allow_html=True)
                        fig_b_tl = go.Figure(go.Bar(
                            x=sess_names_list, y=tl_vals_list,
                            marker_color="#0ea5e9", marker_line_width=0,
                            text=[f"{v:.0f}" for v in tl_vals_list], textposition="outside",
                            textfont=dict(size=12, color="#0f172a", weight="bold"), cliponaxis=False
                        ))
                        fig_b_tl.update_layout(
                            height=300, margin=dict(l=10, r=10, t=20, b=10),
                            plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                            xaxis=dict(showgrid=False, tickfont=dict(size=11, color="#0f172a", weight="bold")),
                            yaxis=dict(showgrid=True, gridcolor="#f1f5f9", range=[0, max_tl_g], zeroline=False)
                        )
                        st.plotly_chart(fig_b_tl, use_container_width=True, key="avg_bar_tl")

                with c_ch2:
                    with st.container(border=True):
                        st.markdown(render_executive_chart_header(
                            tr("TL High Medio per Tipologia", "Mean TL High by Session Type"),
                            pills=[(tr("Picco", "Peak"), f"{max(tlh_vals_list):.0f} AU", "#f87171")],
                            accent="#ef4444"
                        ), unsafe_allow_html=True)
                        fig_b_tlh = go.Figure(go.Bar(
                            x=sess_names_list, y=tlh_vals_list,
                            marker_color="#ef4444", marker_line_width=0,
                            text=[f"{v:.0f}" for v in tlh_vals_list], textposition="outside",
                            textfont=dict(size=12, color="#0f172a", weight="bold"), cliponaxis=False
                        ))
                        fig_b_tlh.update_layout(
                            height=300, margin=dict(l=10, r=10, t=20, b=10),
                            plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                            xaxis=dict(showgrid=False, tickfont=dict(size=11, color="#0f172a", weight="bold")),
                            yaxis=dict(showgrid=True, gridcolor="#f1f5f9", range=[0, max_tlh_g], zeroline=False)
                        )
                        st.plotly_chart(fig_b_tlh, use_container_width=True, key="avg_bar_tlh")

    elif active_medie_tab == T_COMP_M:
        lbl_t2_h = tr("Testa a Testa Medie — Confronto Storico tra Atleti", "Head to Head Averages — Historical Athlete Comparison")
        st.markdown(f"<h3 style='color:#0f172a; margin-top:10px;'>{lbl_t2_h}</h3>", unsafe_allow_html=True)
        glob_ath = st.session_state.get('selected_athlete')
        if glob_ath in atleti_consentiti:
            ath_a = glob_ath
        elif 'h2h_a' in st.session_state and st.session_state['h2h_a'] in atleti_consentiti:
            ath_a = st.session_state['h2h_a']
        else:
            ath_a = atleti_consentiti[0] if atleti_consentiti else None
        st.session_state['h2h_a'] = ath_a

        opzioni_ath_b = [a for a in atleti_consentiti if a != ath_a] or atleti_consentiti
        idx_hb = 0
        if 'h2h_b' in st.session_state and st.session_state['h2h_b'] in opzioni_ath_b:
            idx_hb = opzioni_ath_b.index(st.session_state['h2h_b'])

        col_a, col_b = st.columns(2)
        with col_a:
            lbl_ath1_tit = tr("Atleta 1 (Soggetto Analizzato)", "Athlete 1 (Analyzed Subject)")
            st.markdown(
                f"<div style='background:#f8fafc; border:1px solid #e2e8f0; border-radius:10px; padding:8px 14px; margin-bottom:8px;'>"
                f"<div style='font-size:10.5px; font-weight:800; color:#64748b; text-transform:uppercase; letter-spacing:0.5px;'>{lbl_ath1_tit}</div>"
                f"<div style='font-size:15px; font-weight:900; color:#0f172a; margin-top:2px;'><i class='bi bi-person-fill' style='color:#0284c7; margin-right:6px;'></i>{ath_a}</div>"
                f"</div>",
                unsafe_allow_html=True
            )
        with col_b:
            ath_b = st.selectbox(
                tr("Atleta 2 ( Riferimento 100% )", "Athlete 2 ( 100% Baseline )"),
                opzioni_ath_b,
                index=idx_hb,
                key="h2h_b"
            )
        
        df_a = df_reale[df_reale['Players'] == ath_a]
        df_b = df_reale[df_reale['Players'] == ath_b]
        
        sess_a = set(df_a['Tipologia Sessione'].dropna().unique())
        sess_b = set(df_b['Tipologia Sessione'].dropna().unique())
        sess_comuni = sorted(list(sess_a.intersection(sess_b)))
        
        if not sess_comuni:
            st.warning(tr("I due atleti selezionati non hanno tipologie di sessione in comune nel database reale.", "The two selected athletes have no common session types in the real database."))
        else:
            sess_sel = st.selectbox(tr("Seleziona la Tipologia di Sessione da confrontare", "Select Session Type to compare"), sess_comuni, key="h2h_sess")
            
            # Striscia Compatta Confronto Atleti MOV3 (Testa a Testa)
            render_dual_athlete_strip(ath_a, ath_b, session_type=sess_sel)

            df_a_s = df_a[df_a['Tipologia Sessione'] == sess_sel]
            df_b_s = df_b[df_b['Tipologia Sessione'] == sess_sel]
            mean_a = df_a_s[col_analisi].mean()
            mean_b = df_b_s[col_analisi].mean()

            opzioni_pdf_h2h = {
                tr("Report Testa a Testa", "Head to Head Report"): "Confronto"
            }
            render_action_bar(
                meta_items=[
                    (tr("Atleta 1", "Athlete 1"), f"{ath_a} ({len(df_a_s)} sess.)"),
                    (tr("Atleta 2 (Base 100%)", "Athlete 2 (100% Base)"), f"{ath_b} ({len(df_b_s)} sess.)"),
                    (tr("Tipologia", "Session Type"), sess_sel),
                ],
                pdf_options=opzioni_pdf_h2h,
                pdf_key="avg_h2h",
                generate_fn=lambda _: crea_pdf_medie_m0v3("confronto", ath_a=ath_a, ath_b=ath_b, sess_sel=sess_sel, mean_a=mean_a, mean_b=mean_b, col_analisi=col_analisi),
                filename_fn=lambda _: f"M0V3_Medie_Testa_a_Testa_{slugify_name(ath_a)}_vs_{slugify_name(ath_b)}_{slugify_name(sess_sel)}.pdf"
            )

            h2h_meta = [
                ("Minuti", tr("Durata Sessione (min)", "Session Duration (min)"), "VOLUME", "#f59e0b"),
                ("Training Load", "Training Load (AU)", "VOLUME", "#f59e0b"),
                ("TL_High", "Training Load High (AU)", "HIGH INTENSITY", "#ef4444"),
                ("High Accel IMU", "High Accelerations IMU", "HIGH INTENSITY", "#ef4444"),
                ("High Decel IMU", "High Decelerations IMU", "HIGH INTENSITY", "#ef4444"),
                ("Azioni Int. IMU >2", tr('Azioni Intense >2"', 'Intense Actions >2"'), "VOLUME", "#f59e0b"),
                ("Azioni Int. IMU >10", tr('Azioni Intense >10"', 'Intense Actions >10"'), "VOLUME", "#f59e0b"),
                ("Recuperi IMU 1-5m", tr("Recuperi Brevi 1-5m", "Short Recoveries 1-5m"), "RECOVERY", "#10b981"),
            ]

            lbl_vs_b = f"vs {ath_b}"
            html_rows = ""
            pct_map_h2h = {}
            for idx_h, (col_k, col_lbl, cat_t, cat_c) in enumerate(h2h_meta):
                va = 0.0 if pd.isna(mean_a[col_k]) else float(mean_a[col_k])
                vb = 0.0 if pd.isna(mean_b[col_k]) else float(mean_b[col_k])
                has_ref = vb > 0
                pct_v = (va / vb * 100.0) if has_ref else (100.0 if va == 0 else 0.0)
                diff_v = pct_v - 100.0
                pct_map_h2h[col_k] = pct_v if has_ref else 100.0

                bg_color = "#ffffff" if idx_h % 2 == 0 else "#f8fafc"
                badge_cell = render_pct_badge_cell(pct_v, diff_v, has_ref, lbl_vs_b)
                pbar_cell = render_pct_progress_bar(pct_v if has_ref else 0.0)

                html_rows += (
                    f"<tr style='background:{bg_color}; border-bottom:1px solid #f1f5f9;'>"
                    f"<td style='text-align:left; padding:13px 18px;'>"
                    f"<div style='font-weight:700; color:#0f172a; font-size:13.5px;'>{col_lbl}</div>"
                    f"<span style='display:inline-block; margin-top:2px; font-size:9px; font-weight:800; color:{cat_c}; background:{cat_c}14; padding:1px 6px; border-radius:4px; letter-spacing:0.05em;'>{cat_t}</span>"
                    f"</td>"
                    f"<td style='padding:13px 10px; font-size:18.5px; font-weight:900; color:#0ea5e9; text-align:center;'>{va:.1f}</td>"
                    f"<td style='padding:13px 10px; font-size:16.5px; font-weight:700; color:#8b5cf6; text-align:center;'>{vb:.1f}</td>"
                    f"<td style='padding:13px 10px; text-align:center;'>{badge_cell}</td>"
                    f"<td style='padding:13px 18px;'>{pbar_cell}</td>"
                    f"</tr>"
                )

            lbl_h2h_banner = tr(f"HEAD TO HEAD — CONFRONTO DIRETTO ({sess_sel.upper()})", f"HEAD TO HEAD — DIRECT COMPARISON ({sess_sel.upper()})")
            lbl_h2h_sub = f"{ath_a} vs {ath_b} (Base 100%)"
            th_h_p = tr("Parametro Analizzato", "Analyzed Parameter")
            th_h_pct = tr("% Raggiunta (Scostamento A&nbsp;vs&nbsp;B)", "% Reached (Delta A&nbsp;vs&nbsp;B)")
            th_h_bar = tr("Confronto Visivo (100%&nbsp;=&nbsp;Atleta&nbsp;2)", "Visual Comparison (100%&nbsp;=&nbsp;Athlete&nbsp;2)")

            html_table = (
                "<div style='background:#ffffff; border-radius:14px; border:1px solid #e2e8f0; box-shadow:0 4px 12px -2px rgba(15,23,42,0.05); margin-top:14px; margin-bottom:20px; overflow:hidden; font-family:\"Inter\",sans-serif;'>"
                "<div style='background:linear-gradient(135deg, #0f172a 0%, #1e293b 100%); padding:14px 20px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;'>"
                "<div style='display:flex; align-items:center; gap:10px;'>"
                "<span style='width:8px; height:8px; border-radius:50%; background:#38bdf8; display:inline-block;'></span>"
                f"<span style='color:#ffffff; font-size:13px; font-weight:800; text-transform:uppercase; letter-spacing:0.06em;'>{lbl_h2h_banner}</span>"
                "</div>"
                f"<span style='color:#94a3b8; font-size:11px; font-weight:600;'>{lbl_h2h_sub}</span>"
                "</div>"
                "<table style='width:100%; border-collapse:collapse;'>"
                "<thead><tr style='background:#f8fafc; border-bottom:2px solid #e2e8f0;'>"
                f"<th style='text-align:left; padding:12px 16px; color:#475569; font-size:10.5px; text-transform:uppercase; font-weight:800; letter-spacing:0.03em; width:22%;'>{th_h_p}</th>"
                f"<th style='text-align:center; padding:12px 8px; color:#0284c7; font-size:11px; text-transform:uppercase; font-weight:800; letter-spacing:0.03em; width:12%;'>{ath_a}</th>"
                f"<th style='text-align:center; padding:12px 8px; color:#7c3aed; font-size:11px; text-transform:uppercase; font-weight:800; letter-spacing:0.03em; width:13%;'>{ath_b} (100%)</th>"
                f"<th style='text-align:center; padding:12px 10px; color:#475569; font-size:10.5px; text-transform:uppercase; font-weight:800; letter-spacing:0.02em; width:26%; white-space:nowrap;'>{th_h_pct}</th>"
                f"<th style='text-align:left; padding:12px 16px; color:#475569; font-size:10.5px; text-transform:uppercase; font-weight:800; letter-spacing:0.02em; width:27%; white-space:nowrap;'>{th_h_bar}</th>"
                "</tr></thead>"
                f"<tbody>{html_rows}</tbody></table></div>"
            )
            st.markdown(html_table, unsafe_allow_html=True)

            # Esagono Head-to-Head + 3 Indici Sintetici
            hex_keys = ["Minuti", "Training Load", "TL_High", "High Decel IMU", "High Accel IMU", "Azioni Int. IMU >2"]
            hex_names = [
                tr("Durata", "Duration"),
                "Training Load",
                "TL High",
                "High Decel",
                "High Accel",
                tr('Azioni >2"', 'Actions >2"')
            ]
            hex_pcts_a = [pct_map_h2h.get(k, 100.0) for k in hex_keys]

            idx_vol_h2h = (pct_map_h2h.get("Minuti", 100.0) + pct_map_h2h.get("Training Load", 100.0) + pct_map_h2h.get("Azioni Int. IMU >2", 100.0)) / 3.0
            idx_hi_h2h = (pct_map_h2h.get("TL_High", 100.0) + pct_map_h2h.get("High Decel IMU", 100.0) + pct_map_h2h.get("High Accel IMU", 100.0)) / 3.0

            min_a_v = float(mean_a.get("Minuti", 0.0))
            min_b_v = float(mean_b.get("Minuti", 0.0))
            wr_ratios_h2h = []
            for k_wr in ["Training Load", "TL_High", "High Accel IMU", "High Decel IMU", "Azioni Int. IMU >2"]:
                ra = (float(mean_a.get(k_wr, 0.0)) / min_a_v) if min_a_v > 0 else 0.0
                rb = (float(mean_b.get(k_wr, 0.0)) / min_b_v) if min_b_v > 0 else 0.0
                wr_ratios_h2h.append((ra / rb * 100.0) if rb > 0 else 100.0)
            idx_wr_h2h = sum(wr_ratios_h2h) / len(wr_ratios_h2h)

            col_hex_h2h, col_idx_h2h = st.columns([1.35, 1])
            with col_hex_h2h:
                with st.container(border=True):
                    st.markdown(render_executive_chart_header(
                        tr("PROFILO ESAGONALE TESTA A TESTA (% A vs B)", "HEAD TO HEAD HEXAGONAL PROFILE (% A vs B)"),
                        pills=[(tr("Soggetto", "Subject"), ath_a, "#38bdf8"), (tr("Base 100%", "100% Base"), ath_b, "#c084fc")],
                        accent="#0ea5e9"
                    ), unsafe_allow_html=True)
                    lbl_axes_h2h = []
                    for nm_i, pv_i in zip(hex_names, hex_pcts_a):
                        dv_i = pv_i - 100.0
                        sd_i = f"+{dv_i:.0f}%" if dv_i > 0 else f"{dv_i:.0f}%"
                        _, col_z_i, _, _ = acwr_zone_meta(pv_i)
                        lbl_axes_h2h.append(f"<b>{nm_i}</b><br><span style='color:{col_z_i}; font-size:11px;'><b>{pv_i:.0f}%</b> ({sd_i})</span>")
                    theta_closed_h = lbl_axes_h2h + [lbl_axes_h2h[0]]
                    r_a_closed = [min(v, 160.0) for v in hex_pcts_a] + [min(hex_pcts_a[0], 160.0)]

                    fig_h2h_hex = go.Figure()
                    fig_h2h_hex.add_trace(go.Scatterpolar(
                        r=[100]*7, theta=theta_closed_h, mode='lines',
                        line=dict(color='#8b5cf6', width=2.5, dash='dash'),
                        name=f"{ath_b} (100%)", hoverinfo='skip'
                    ))
                    fig_h2h_hex.add_trace(go.Scatterpolar(
                        r=r_a_closed, theta=theta_closed_h, fill='toself',
                        fillcolor='rgba(14, 165, 233, 0.18)',
                        line=dict(color='#0ea5e9', width=3.5),
                        marker=dict(size=8, color='#0ea5e9', line=dict(width=2, color='#ffffff')),
                        name=ath_a
                    ))
                    fig_h2h_hex.update_layout(
                        polar=dict(
                            domain=dict(x=[0.16, 0.84], y=[0.08, 0.92]),
                            gridshape='linear',
                            bgcolor='#f8fafc',
                            radialaxis=dict(
                                visible=True, range=[0, 160],
                                tickvals=[50, 100, 150],
                                ticktext=['50%', '100%', '150%'],
                                tickfont=dict(size=9, color='#64748b'),
                                gridcolor='#e2e8f0', linecolor='#cbd5e1'
                            ),
                            angularaxis=dict(
                                tickfont=dict(size=11, color='#0f172a', family='Inter'),
                                rotation=90, direction='clockwise',
                                gridcolor='#e2e8f0', linecolor='#cbd5e1'
                            )
                        ),
                        showlegend=False,
                        height=420,
                        margin=dict(l=45, r=45, t=32, b=28),
                        paper_bgcolor='rgba(0,0,0,0)',
                        plot_bgcolor='rgba(0,0,0,0)'
                    )
                    st.plotly_chart(fig_h2h_hex, use_container_width=True, key="h2h_hex_chart")
                    st.markdown(
                        "<div style='display:flex; justify-content:center; gap:20px; padding:6px 10px 4px 10px; border-top:1px solid #f1f5f9; font-family:\"Inter\",sans-serif; font-size:11px; color:#334155;'>"
                        f"<span style='display:inline-flex; align-items:center; gap:6px; font-weight:800; color:#0284c7;'><span style='width:12px; height:12px; border-radius:50%; background:#0ea5e9; display:inline-block;'></span>{ath_a}</span>"
                        f"<span style='display:inline-flex; align-items:center; gap:6px; font-weight:800; color:#7c3aed;'><span style='width:18px; border-top:2.5px dashed #8b5cf6; display:inline-block;'></span>{ath_b} (100% Baseline)</span>"
                        "</div>",
                        unsafe_allow_html=True
                    )

            with col_idx_h2h:
                lbl_idx_h_title = tr("INDICI SINTETICI TESTA A TESTA", "HEAD TO HEAD SYNTHETIC INDICES")
                st.markdown(
                    f"<div style='font-size:12px; font-weight:800; color:#0f172a; text-transform:uppercase; letter-spacing:0.05em; margin-bottom:10px;'>{lbl_idx_h_title}</div>",
                    unsafe_allow_html=True
                )
                for idx_nm, idx_sub_txt, idx_val, idx_acc in [
                    (tr("INDICE VOLUME", "VOLUME INDEX"), tr('Media % di Durata, Training Load e Azioni >2"', 'Avg % of Duration, Training Load & Actions >2"'), idx_vol_h2h, "#f59e0b"),
                    (tr("INDICE ALTA INTENSITÀ", "HIGH INTENSITY INDEX"), tr("Media % di TL High, High Decel e High Accel", "Avg % of TL High, High Decel & High Accel"), idx_hi_h2h, "#ef4444"),
                    ("WORK RATE", tr("Media % dei 5 parametri intensivi calcolati al minuto", "Avg % of the 5 intensive parameters per minute"), idx_wr_h2h, "#8b5cf6"),
                ]:
                    d_idx = idx_val - 100.0
                    s_idx = f"+{d_idx:.0f}%" if d_idx > 0 else f"{d_idx:.0f}%"
                    z_lbl_i, z_col_i, z_bg_i, z_brd_i = acwr_zone_meta(idx_val)
                    pbar_idx = render_pct_progress_bar(idx_val, bar_col=idx_acc)
                    st.markdown(
                        f"<div style='background:#ffffff; border:1px solid #e2e8f0; border-left:5px solid {idx_acc}; border-radius:12px; padding:15px 18px; margin-bottom:12px; box-shadow:0 2px 6px rgba(15,23,42,0.04); font-family:\"Inter\",sans-serif;'>"
                        f"<div style='display:flex; justify-content:space-between; align-items:flex-start;'>"
                        f"<div>"
                        f"<div style='font-size:11px; font-weight:800; color:#475569; text-transform:uppercase; letter-spacing:0.06em;'>{idx_nm}</div>"
                        f"<div style='font-size:10.5px; color:#94a3b8; margin-top:2px;'>{idx_sub_txt}</div>"
                        f"</div>"
                        f"<span style='background:{z_bg_i}; color:{z_col_i}; border:1px solid {z_brd_i}; font-size:9.5px; font-weight:800; padding:2px 8px; border-radius:999px; letter-spacing:0.05em;'>{z_lbl_i}</span>"
                        f"</div>"
                        f"<div style='display:flex; align-items:baseline; gap:10px; margin-top:8px;'>"
                        f"<span style='font-size:32px; font-weight:900; color:#0f172a; line-height:1;'>{idx_val:.0f}%</span>"
                        f"<span style='font-size:13px; font-weight:800; color:{z_col_i};'>({s_idx} {lbl_vs_b})</span>"
                        f"</div>"
                        f"<div style='margin-top:8px;'>{pbar_idx}</div>"
                        f"</div>",
                        unsafe_allow_html=True
                    )

    # ---------------------------------------------------------
    # TAB 3: TESTA A TESTA SETTIMANA — CONFRONTO CARICHI SETTIMANALI TRA ATLETI
    # ---------------------------------------------------------
    elif active_medie_tab == T_COMP_W:
        lbl_t3_h = tr("Testa a Testa Settimana — Confronto Carichi tra Atleti", "Weekly Head to Head — Workload Comparison between Athletes")
        st.markdown(f"<h3 style='color:#0f172a; margin-top:10px;'>{lbl_t3_h}</h3>", unsafe_allow_html=True)
        glob_ath = st.session_state.get('selected_athlete')
        if glob_ath in atleti_consentiti:
            ath_wa = glob_ath
        elif 'h2h_w_a' in st.session_state and st.session_state['h2h_w_a'] in atleti_consentiti:
            ath_wa = st.session_state['h2h_w_a']
        else:
            ath_wa = atleti_consentiti[0] if atleti_consentiti else None
        st.session_state['h2h_w_a'] = ath_wa

        opzioni_ath_wb = [a for a in atleti_consentiti if a != ath_wa] or atleti_consentiti
        idx_hwb = 0
        if 'h2h_w_b' in st.session_state and st.session_state['h2h_w_b'] in opzioni_ath_wb:
            idx_hwb = opzioni_ath_wb.index(st.session_state['h2h_w_b'])

        col_wa, col_wb = st.columns(2)
        with col_wa:
            lbl_ath1_w_tit = tr("Atleta 1 (Soggetto Analizzato)", "Athlete 1 (Analyzed Subject)")
            st.markdown(
                f"<div style='background:#f8fafc; border:1px solid #e2e8f0; border-radius:10px; padding:8px 14px; margin-bottom:8px;'>"
                f"<div style='font-size:10.5px; font-weight:800; color:#64748b; text-transform:uppercase; letter-spacing:0.5px;'>{lbl_ath1_w_tit}</div>"
                f"<div style='font-size:15px; font-weight:900; color:#0f172a; margin-top:2px;'><i class='bi bi-person-fill' style='color:#0284c7; margin-right:6px;'></i>{ath_wa}</div>"
                f"</div>",
                unsafe_allow_html=True
            )
        with col_wb:
            ath_wb = st.selectbox(
                tr("Atleta 2 ( Riferimento 100% )", "Athlete 2 ( 100% Baseline )"),
                opzioni_ath_wb,
                index=idx_hwb,
                key="h2h_w_b"
            )

        c_w_flt1, c_w_flt2 = st.columns([1.5, 1.5])
        with c_w_flt1:
            sel_week_opt = st.selectbox(
                tr("Seleziona Settimana da confrontare", "Select Week to compare"),
                opts_settimane_h2h,
                index=0,
                key="h2h_w_week"
            )
            week_target = curr_w_lbl if sel_week_opt == opt_cur_week else sel_week_opt

        df_wa = df_reale[(df_reale['Players'] == ath_wa) & (df_reale['Week_Label'] == week_target)]
        df_wb = df_reale[(df_reale['Players'] == ath_wb) & (df_reale['Week_Label'] == week_target)]

        opt_all_types = tr("Tutte le Tipologie (Carico Settimanale Totale)", "All Types (Total Weekly Workload)")
        sess_wa_types = set(df_wa['Tipologia Sessione'].dropna().unique())
        sess_wb_types = set(df_wb['Tipologia Sessione'].dropna().unique())
        sess_w_all = sorted(list(sess_wa_types.union(sess_wb_types)))
        opts_sess_w = [opt_all_types] + sess_w_all

        with c_w_flt2:
            sel_sess_w = st.selectbox(
                tr("Tipologia di Sessione da confrontare", "Session Type to compare"),
                opts_sess_w,
                index=0,
                key="h2h_w_sess"
            )

        # Striscia Compatta Confronto Atleti MOV3 (Testa a Testa Settimanale)
        render_dual_athlete_strip(ath_wa, ath_wb, session_type=sel_sess_w, week=sel_week_opt)

        if sel_sess_w != opt_all_types:
            df_wa_s = df_wa[df_wa['Tipologia Sessione'] == sel_sess_w]
            df_wb_s = df_wb[df_wb['Tipologia Sessione'] == sel_sess_w]
        else:
            df_wa_s = df_wa
            df_wb_s = df_wb

        len_wa = len(df_wa_s)
        len_wb = len(df_wb_s)

        if len_wa == 0 and len_wb == 0:
            st.info(
                tr(
                    f"ℹ️ Nessuna sessione registrata per entrambi gli atleti ({ath_wa} e {ath_wb}) nella settimana {week_target}.",
                    f"ℹ️ No sessions recorded for either athlete ({ath_wa} and {ath_wb}) in week {week_target}."
                )
            )
        else:
            # Calcolo Carico Cumulato Settimanale (Somma)
            sum_wa = df_wa_s[col_analisi].sum() if not df_wa_s.empty else pd.Series(0.0, index=col_analisi)
            sum_wb = df_wb_s[col_analisi].sum() if not df_wb_s.empty else pd.Series(0.0, index=col_analisi)

            opzioni_pdf_h2h_w = {
                tr("Report Testa a Testa Settimana", "Weekly Head to Head Report"): "Confronto_Settimana"
            }
            render_action_bar(
                meta_items=[
                    (tr("Atleta 1", "Athlete 1"), f"{ath_wa} ({len_wa} sess.)"),
                    (tr("Atleta 2 (Base 100%)", "Athlete 2 (100% Base)"), f"{ath_wb} ({len_wb} sess.)"),
                    (tr("Settimana", "Week"), week_target),
                    (tr("Tipologia", "Session Type"), sel_sess_w),
                ],
                pdf_options=opzioni_pdf_h2h_w,
                pdf_key="avg_h2h_w",
                generate_fn=lambda _: crea_pdf_medie_m0v3("confronto", ath_a=ath_wa, ath_b=ath_wb, sess_sel=f"Sett. {week_target} - {sel_sess_w}", mean_a=sum_wa, mean_b=sum_wb, col_analisi=col_analisi),
                filename_fn=lambda _: f"M0V3_Testa_a_Testa_Settimana_{slugify_name(ath_wa)}_vs_{slugify_name(ath_wb)}_{slugify_name(week_target)}.pdf"
            )

            h2h_w_meta = [
                ("Minuti", tr("Durata Totale (min)", "Total Duration (min)"), "VOLUME", "#f59e0b"),
                ("Training Load", "Training Load Totale (AU)", "VOLUME", "#f59e0b"),
                ("TL_High", "Training Load High Totale (AU)", "HIGH INTENSITY", "#ef4444"),
                ("High Accel IMU", "High Accelerations Totali", "HIGH INTENSITY", "#ef4444"),
                ("High Decel IMU", "High Decelerations Totali", "HIGH INTENSITY", "#ef4444"),
                ("Azioni Int. IMU >2", tr('Azioni Intense >2" Totali', 'Total Actions >2"'), "VOLUME", "#f59e0b"),
                ("Azioni Int. IMU >10", tr('Azioni Intense >10" Totali', 'Total Actions >10"'), "VOLUME", "#f59e0b"),
                ("Recuperi IMU 1-5m", tr("Recuperi Brevi 1-5m Totali", "Total Short Recoveries 1-5m"), "RECOVERY", "#10b981"),
            ]

            lbl_vs_wb = f"vs {ath_wb}"
            html_w_rows = ""
            pct_map_h2h_w = {}
            for idx_h, (col_k, col_lbl, cat_t, cat_c) in enumerate(h2h_w_meta):
                va = 0.0 if pd.isna(sum_wa[col_k]) else float(sum_wa[col_k])
                vb = 0.0 if pd.isna(sum_wb[col_k]) else float(sum_wb[col_k])
                has_ref = vb > 0
                pct_v = (va / vb * 100.0) if has_ref else (100.0 if va == 0 else 0.0)
                diff_v = pct_v - 100.0
                pct_map_h2h_w[col_k] = pct_v if has_ref else 100.0

                bg_color = "#ffffff" if idx_h % 2 == 0 else "#f8fafc"
                badge_cell = render_pct_badge_cell(pct_v, diff_v, has_ref, lbl_vs_wb)
                pbar_cell = render_pct_progress_bar(pct_v if has_ref else 0.0)

                html_w_rows += (
                    f"<tr style='background:{bg_color}; border-bottom:1px solid #f1f5f9;'>"
                    f"<td style='text-align:left; padding:13px 18px;'>"
                    f"<div style='font-weight:700; color:#0f172a; font-size:13.5px;'>{col_lbl}</div>"
                    f"<span style='display:inline-block; margin-top:2px; font-size:9px; font-weight:800; color:{cat_c}; background:{cat_c}14; padding:1px 6px; border-radius:4px; letter-spacing:0.05em;'>{cat_t}</span>"
                    f"</td>"
                    f"<td style='padding:13px 10px; font-size:18.5px; font-weight:900; color:#0ea5e9; text-align:center;'>{va:,.0f}</td>"
                    f"<td style='padding:13px 10px; font-size:16.5px; font-weight:700; color:#8b5cf6; text-align:center;'>{vb:,.0f}</td>"
                    f"<td style='padding:13px 10px; text-align:center;'>{badge_cell}</td>"
                    f"<td style='padding:13px 18px;'>{pbar_cell}</td>"
                    f"</tr>"
                )

            lbl_h2h_w_banner = tr(f"HEAD TO HEAD SETTIMANALE — CONFRONTO CARICHI ({week_target})", f"WEEKLY HEAD TO HEAD — WORKLOAD COMPARISON ({week_target})")
            lbl_h2h_w_sub = f"{ath_wa} ({len_wa} sess.) vs {ath_wb} ({len_wb} sess. - Base 100%)"
            th_h_p = tr("Parametro Analizzato", "Analyzed Parameter")
            th_h_pct = tr("% Raggiunta (Scostamento A&nbsp;vs&nbsp;B)", "% Reached (Delta A&nbsp;vs&nbsp;B)")
            th_h_bar = tr("Confronto Visivo (100%&nbsp;=&nbsp;Atleta&nbsp;2)", "Visual Comparison (100%&nbsp;=&nbsp;Athlete&nbsp;2)")

            html_w_table = (
                "<div style='background:#ffffff; border-radius:14px; border:1px solid #e2e8f0; box-shadow:0 4px 12px -2px rgba(15,23,42,0.05); margin-top:14px; margin-bottom:20px; overflow:hidden; font-family:\"Inter\",sans-serif;'>"
                "<div style='background:linear-gradient(135deg, #0f172a 0%, #1e293b 100%); padding:14px 20px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;'>"
                "<div style='display:flex; align-items:center; gap:10px;'>"
                "<span style='width:8px; height:8px; border-radius:50%; background:#38bdf8; display:inline-block;'></span>"
                f"<span style='color:#ffffff; font-size:13px; font-weight:800; text-transform:uppercase; letter-spacing:0.06em;'>{lbl_h2h_w_banner}</span>"
                "</div>"
                f"<span style='color:#94a3b8; font-size:11px; font-weight:600;'>{lbl_h2h_w_sub}</span>"
                "</div>"
                "<table style='width:100%; border-collapse:collapse;'>"
                "<thead><tr style='background:#f8fafc; border-bottom:2px solid #e2e8f0;'>"
                f"<th style='text-align:left; padding:12px 16px; color:#475569; font-size:10.5px; text-transform:uppercase; font-weight:800; letter-spacing:0.03em; width:22%;'>{th_h_p}</th>"
                f"<th style='text-align:center; padding:12px 8px; color:#0284c7; font-size:11px; text-transform:uppercase; font-weight:800; letter-spacing:0.03em; width:12%;'>{ath_wa}</th>"
                f"<th style='text-align:center; padding:12px 8px; color:#7c3aed; font-size:11px; text-transform:uppercase; font-weight:800; letter-spacing:0.03em; width:13%;'>{ath_wb} (100%)</th>"
                f"<th style='text-align:center; padding:12px 10px; color:#475569; font-size:10.5px; text-transform:uppercase; font-weight:800; letter-spacing:0.02em; width:26%; white-space:nowrap;'>{th_h_pct}</th>"
                f"<th style='text-align:left; padding:12px 16px; color:#475569; font-size:10.5px; text-transform:uppercase; font-weight:800; letter-spacing:0.02em; width:27%; white-space:nowrap;'>{th_h_bar}</th>"
                "</tr></thead>"
                f"<tbody>{html_w_rows}</tbody></table></div>"
            )
            st.html(html_w_table)

            # Esagono Head-to-Head Settimanale + 3 Indici Sintetici
            hex_keys = ["Minuti", "Training Load", "TL_High", "High Decel IMU", "High Accel IMU", "Azioni Int. IMU >2"]
            hex_names = [
                tr("Durata", "Duration"),
                "Training Load",
                "TL High",
                "High Decel",
                "High Accel",
                tr('Azioni >2"', 'Actions >2"')
            ]
            hex_pcts_wa = [pct_map_h2h_w.get(k, 100.0) for k in hex_keys]

            idx_vol_h2h_w = (pct_map_h2h_w.get("Minuti", 100.0) + pct_map_h2h_w.get("Training Load", 100.0) + pct_map_h2h_w.get("Azioni Int. IMU >2", 100.0)) / 3.0
            idx_hi_h2h_w = (pct_map_h2h_w.get("TL_High", 100.0) + pct_map_h2h_w.get("High Decel IMU", 100.0) + pct_map_h2h_w.get("High Accel IMU", 100.0)) / 3.0

            min_wa_v = float(sum_wa.get("Minuti", 0.0))
            min_wb_v = float(sum_wb.get("Minuti", 0.0))
            wr_ratios_h2h_w = []
            for k_wr in ["Training Load", "TL_High", "High Accel IMU", "High Decel IMU", "Azioni Int. IMU >2"]:
                ra = (float(sum_wa.get(k_wr, 0.0)) / min_wa_v) if min_wa_v > 0 else 0.0
                rb = (float(sum_wb.get(k_wr, 0.0)) / min_wb_v) if min_wb_v > 0 else 0.0
                wr_ratios_h2h_w.append((ra / rb * 100.0) if rb > 0 else 100.0)
            idx_wr_h2h_w = sum(wr_ratios_h2h_w) / len(wr_ratios_h2h_w)

            col_hex_w, col_idx_w = st.columns([1.35, 1])
            with col_hex_w:
                with st.container(border=True):
                    st.markdown(render_executive_chart_header(
                        tr("PROFILO ESAGONALE TESTA A TESTA SETTIMANA (% A vs B)", "WEEKLY HEAD TO HEAD HEXAGONAL PROFILE (% A vs B)"),
                        pills=[(tr("Soggetto", "Subject"), ath_wa, "#38bdf8"), (tr("Base 100%", "100% Base"), ath_wb, "#c084fc")],
                        accent="#0ea5e9"
                    ), unsafe_allow_html=True)
                    lbl_axes_h2h_w = []
                    for nm_i, pv_i in zip(hex_names, hex_pcts_wa):
                        dv_i = pv_i - 100.0
                        sd_i = f"+{dv_i:.0f}%" if dv_i > 0 else f"{dv_i:.0f}%"
                        _, col_z_i, _, _ = acwr_zone_meta(pv_i)
                        lbl_axes_h2h_w.append(f"<b>{nm_i}</b><br><span style='color:{col_z_i}; font-size:11px;'><b>{pv_i:.0f}%</b> ({sd_i})</span>")
                    theta_closed_wh = lbl_axes_h2h_w + [lbl_axes_h2h_w[0]]
                    r_wa_closed = [min(v, 160.0) for v in hex_pcts_wa] + [min(hex_pcts_wa[0], 160.0)]

                    fig_h2h_w_hex = go.Figure()
                    fig_h2h_w_hex.add_trace(go.Scatterpolar(
                        r=[100]*7, theta=theta_closed_wh, mode='lines',
                        line=dict(color='#8b5cf6', width=2.5, dash='dash'),
                        name=f"{ath_wb} (100%)", hoverinfo='skip'
                    ))
                    fig_h2h_w_hex.add_trace(go.Scatterpolar(
                        r=r_wa_closed, theta=theta_closed_wh, fill='toself',
                        fillcolor='rgba(14, 165, 233, 0.18)',
                        line=dict(color='#0ea5e9', width=3.5),
                        marker=dict(size=8, color='#0ea5e9', line=dict(width=2, color='#ffffff')),
                        name=ath_wa
                    ))
                    fig_h2h_w_hex.update_layout(
                        polar=dict(
                            domain=dict(x=[0.16, 0.84], y=[0.08, 0.92]),
                            gridshape='linear',
                            bgcolor='#f8fafc',
                            radialaxis=dict(
                                visible=True, range=[0, 160],
                                tickvals=[50, 100, 150],
                                ticktext=['50%', '100%', '150%'],
                                tickfont=dict(size=9, color='#64748b'),
                                gridcolor='#e2e8f0', linecolor='#cbd5e1'
                            ),
                            angularaxis=dict(
                                tickfont=dict(size=11, color='#0f172a', family='Inter'),
                                rotation=90, direction='clockwise',
                                gridcolor='#e2e8f0', linecolor='#cbd5e1'
                            )
                        ),
                        showlegend=False,
                        height=420,
                        margin=dict(l=45, r=45, t=32, b=28),
                        paper_bgcolor='rgba(0,0,0,0)',
                        plot_bgcolor='rgba(0,0,0,0)'
                    )
                    st.plotly_chart(fig_h2h_w_hex, use_container_width=True, key="h2h_w_hex_chart")
                    st.html(
                        "<div style='display:flex; justify-content:center; gap:20px; padding:6px 10px 4px 10px; border-top:1px solid #f1f5f9; font-family:\"Inter\",sans-serif; font-size:11px; color:#334155;'>"
                        f"<span style='display:inline-flex; align-items:center; gap:6px; font-weight:800; color:#0284c7;'><span style='width:12px; height:12px; border-radius:50%; background:#0ea5e9; display:inline-block;'></span>{ath_wa}</span>"
                        f"<span style='display:inline-flex; align-items:center; gap:6px; font-weight:800; color:#7c3aed;'><span style='width:18px; border-top:2.5px dashed #8b5cf6; display:inline-block;'></span>{ath_wb} (100% Baseline)</span>"
                        "</div>"
                    )

            with col_idx_w:
                lbl_idx_hw_title = tr("INDICI SINTETICI SETTIMANA", "WEEKLY SYNTHETIC INDICES")
                st.html(
                    f"<div style='font-size:12px; font-weight:800; color:#0f172a; text-transform:uppercase; letter-spacing:0.05em; margin-bottom:10px;'>{lbl_idx_hw_title}</div>"
                )
                for idx_nm, idx_sub_txt, idx_val, idx_acc in [
                    (tr("INDICE VOLUME", "VOLUME INDEX"), tr('Totale % di Durata, Training Load e Azioni >2"', 'Total % of Duration, Training Load & Actions >2"'), idx_vol_h2h_w, "#f59e0b"),
                    (tr("INDICE ALTA INTENSITÀ", "HIGH INTENSITY INDEX"), tr("Totale % di TL High, High Decel e High Accel", "Total % of TL High, High Decel & High Accel"), idx_hi_h2h_w, "#ef4444"),
                    ("WORK RATE", tr("Media % dei 5 parametri intensivi calcolati al minuto", "Avg % of the 5 intensive parameters per minute"), idx_wr_h2h_w, "#8b5cf6"),
                ]:
                    d_idx = idx_val - 100.0
                    s_idx = f"+{d_idx:.0f}%" if d_idx > 0 else f"{d_idx:.0f}%"
                    z_lbl_i, z_col_i, z_bg_i, z_brd_i = acwr_zone_meta(idx_val)
                    pbar_idx = render_pct_progress_bar(idx_val, bar_col=idx_acc)
                    st.html(
                        f"<div style='background:#ffffff; border:1px solid #e2e8f0; border-left:5px solid {idx_acc}; border-radius:12px; padding:15px 18px; margin-bottom:12px; box-shadow:0 2px 6px rgba(15,23,42,0.04); font-family:\"Inter\",sans-serif;'>"
                        f"<div style='display:flex; justify-content:space-between; align-items:flex-start;'>"
                        f"<div>"
                        f"<div style='font-size:11px; font-weight:800; color:#475569; text-transform:uppercase; letter-spacing:0.06em;'>{idx_nm}</div>"
                        f"<div style='font-size:10.5px; color:#94a3b8; margin-top:2px;'>{idx_sub_txt}</div>"
                        f"</div>"
                        f"<span style='background:{z_bg_i}; color:{z_col_i}; border:1px solid {z_brd_i}; font-size:9.5px; font-weight:800; padding:2px 8px; border-radius:999px; letter-spacing:0.05em;'>{z_lbl_i}</span>"
                        f"</div>"
                        f"<div style='display:flex; align-items:baseline; gap:10px; margin-top:8px;'>"
                        f"<span style='font-size:32px; font-weight:900; color:#0f172a; line-height:1;'>{idx_val:.0f}%</span>"
                        f"<span style='font-size:13px; font-weight:800; color:{z_col_i};'>({s_idx} {lbl_vs_wb})</span>"
                        f"</div>"
                        f"<div style='margin-top:8px;'>{pbar_idx}</div>"
                        f"</div>"
                    )

    elif active_medie_tab == T_RANK:
        st.html(
            "<div style='margin-top:10px; margin-bottom:18px;'>"
            f"<h3 style='color:#0f172a; margin:0 0 4px 0; font-size:22px; font-weight:800;'><i class='bi bi-trophy-fill' style='color:#0284c7; margin-right:8px;'></i>{tr('Ranking Roster Atleti — Accelerometria & Carichi', 'Athlete Roster Ranking — Accelerometry & Workloads')}</h3>"
            f"<p style='color:#64748b; font-size:13px; margin:0;'>{tr('Graduatoria indipendente per Volume e Intensità dell’intero roster assegnato, su scala settimanale e stagionale con podio sintetico M0V3.', 'Independent ranking for Volume and Intensity across the entire assigned roster, weekly and seasonal with M0V3 synthetic podium.')}</p>"
            "</div>"
        )

        if st.session_state.get('role') == 'Super-Admin':
            roster_db = get_tutti_gli_atleti()
        else:
            roster_db = get_atleti_associati(st.session_state['user'].id)

        roster_dati = df_storico['Players'].dropna().unique().tolist()
        if roster_db:
            roster_totale = sorted(list(set(roster_db) | set(roster_dati)))
        else:
            roster_totale = sorted(list(set(roster_dati)))

        if not roster_totale:
            st.info(tr("Nessun atleta disponibile nel roster.", "No athletes available in roster."))
        else:
            n_roster = len(roster_totale)
            opt_mode_sett = tr("Singola Settimana", "Single Week")
            opt_mode_cust = tr("Periodo Personalizzato", "Custom Period")
            filtro_modo_rk = render_tab_navigation(
                [opt_mode_sett, opt_mode_cust],
                key="rk_filter_mode"
            )
            is_custom_rk = (filtro_modo_rk == opt_mode_cust)

            anni_disponibili = sorted(df_storico['Date_obj'].dt.year.dropna().unique().astype(int).tolist(), reverse=True)
            if not anni_disponibili:
                anni_disponibili = [datetime.now().year]

            if not is_custom_rk:
                c_rk_y, c_rk_w = st.columns([1, 2])
                with c_rk_y:
                    anno_rk_sel = st.selectbox(
                        tr("Stagione (Anno Solare)", "Season (Solar Year)"),
                        anni_disponibili,
                        index=0,
                        key="rk_roster_anno"
                    )

                df_anno_rk = df_storico[df_storico['Date_obj'].dt.year == anno_rk_sel].copy()
                settimane_anno_rk = df_anno_rk['Week_Label'].dropna().unique().tolist()
                settimane_anno_rk.sort(key=lambda x: pd.to_datetime(x.split(" - ")[0], format='%d/%m/%Y'), reverse=True)

                opt_cur_w_anno = f"[{tr('Settimana Corrente', 'Current Week')}] {curr_w_lbl}"
                if curr_w_start.year == anno_rk_sel:
                    if curr_w_lbl in settimane_anno_rk:
                        opts_w_rk = [opt_cur_w_anno] + [s for s in settimane_anno_rk if s != curr_w_lbl]
                    else:
                        opts_w_rk = [opt_cur_w_anno] + settimane_anno_rk
                else:
                    opts_w_rk = settimane_anno_rk if settimane_anno_rk else [curr_w_lbl]

                with c_rk_w:
                    settimana_rk_sel = st.selectbox(
                        tr("Settimana di Riferimento", "Reference Week"),
                        opts_w_rk,
                        index=0,
                        key="rk_roster_settimana"
                    )

                clean_week_rk = curr_w_lbl if opt_cur_w_anno in settimana_rk_sel else settimana_rk_sel
                df_period_data = df_storico[df_storico['Week_Label'] == clean_week_rk]
                lbl_t1 = tr("RANKING SETTIMANALE ROSTER ATLETI", "WEEKLY ATHLETE ROSTER RANKING")
                badge_w = f"Week {clean_week_rk} • {n_roster} {tr('Atleti', 'Athletes')}"
                col_podium_w = "WEEK BEST"
                badge_podium_sub = "Week Best vs Season Best"
                action_period_lbl = tr("Settimana", "Week")
            else:
                c_rk_d1, c_rk_d2, c_rk_y = st.columns([1.5, 1.5, 1])
                min_dt = df_storico['Date_obj'].dropna().min()
                max_dt = df_storico['Date_obj'].dropna().max()
                min_d = min_dt.date() if pd.notnull(min_dt) else (date.today() - timedelta(days=90))
                max_d = max_dt.date() if pd.notnull(max_dt) else date.today()
                def_start = max(min_d, max_d - timedelta(days=28))

                with c_rk_d1:
                    rk_d_start = st.date_input(
                        tr("Data Inizio Periodo", "Period Start Date"),
                        value=def_start,
                        min_value=min_d,
                        max_value=max_d,
                        key="rk_custom_d_start"
                    )
                with c_rk_d2:
                    rk_d_end = st.date_input(
                        tr("Data Fine Periodo", "Period End Date"),
                        value=max_d,
                        min_value=min_d,
                        max_value=max_d,
                        key="rk_custom_d_end"
                    )
                with c_rk_y:
                    anno_rk_sel = st.selectbox(
                        tr("Stagione (Anno Solare)", "Season (Solar Year)"),
                        anni_disponibili,
                        index=0,
                        key="rk_roster_anno_cust"
                    )

                if rk_d_start > rk_d_end:
                    rk_d_start, rk_d_end = rk_d_end, rk_d_start

                clean_week_rk = f"{rk_d_start.strftime('%d/%m/%Y')} - {rk_d_end.strftime('%d/%m/%Y')}"
                mask_period = (df_storico['Date_obj'].dt.date >= rk_d_start) & (df_storico['Date_obj'].dt.date <= rk_d_end)
                df_period_data = df_storico[mask_period]
                lbl_t1 = tr("PERIODO SELEZIONATO — RANKING ROSTER ATLETI", "SELECTED PERIOD — ATHLETE ROSTER RANKING")
                badge_w = f"{tr('Periodo', 'Period')}: {clean_week_rk} • {n_roster} {tr('Atleti', 'Athletes')}"
                col_podium_w = tr("PERIODO BEST", "PERIOD BEST")
                badge_podium_sub = tr("Period Best vs Season Best", "Period Best vs Season Best")
                action_period_lbl = tr("Periodo", "Period")

            def build_roster_metrics(df_sub, roster):
                res = []
                for ath in roster:
                    df_a = df_sub[df_sub['Players'] == ath]
                    tl = float(df_a['Training Load'].sum()) if not df_a.empty else 0.0
                    tlh = float(df_a['TL_High'].sum()) if not df_a.empty else 0.0
                    acc = float(df_a['High Accel IMU'].sum()) if not df_a.empty else 0.0
                    dec = float(df_a['High Decel IMU'].sum()) if not df_a.empty else 0.0
                    mech = acc + dec
                    dur = float(df_a['Minuti'].sum()) if not df_a.empty else 0.0
                    az2 = float(df_a['Azioni Int. IMU >2'].sum()) if not df_a.empty else 0.0
                    sess = len(df_a)
                    res.append({
                        'athlete': ath,
                        'tl': tl,
                        'tlh': tlh,
                        'mech': mech,
                        'dur': dur,
                        'az2': az2,
                        'sess': sess
                    })

                list_tl = sorted(res, key=lambda r: (1 if r['tl'] > 0 else 0, r['tl']), reverse=True)
                list_tlh = sorted(res, key=lambda r: (1 if r['tlh'] > 0 else 0, r['tlh']), reverse=True)
                list_mech = sorted(res, key=lambda r: (1 if r['mech'] > 0 else 0, r['mech']), reverse=True)

                max_tl = max([r['tl'] for r in res] or [1.0]) or 1.0
                max_dur = max([r['dur'] for r in res] or [1.0]) or 1.0
                max_az2 = max([r['az2'] for r in res] or [1.0]) or 1.0
                max_tlh = max([r['tlh'] for r in res] or [1.0]) or 1.0
                max_mech = max([r['mech'] for r in res] or [1.0]) or 1.0

                for r in res:
                    if r['tl'] > 0 or r['dur'] > 0 or r['az2'] > 0:
                        r['score_vol'] = round(((r['tl'] / max_tl) * 40.0) + ((r['dur'] / max_dur) * 35.0) + ((r['az2'] / max_az2) * 25.0), 1)
                    else:
                        r['score_vol'] = 0.0

                    if r['tlh'] > 0 or r['mech'] > 0:
                        r['score_int'] = round(((r['tlh'] / max_tlh) * 50.0) + ((r['mech'] / max_mech) * 50.0), 1)
                    else:
                        r['score_int'] = 0.0

                podio_vol = sorted(res, key=lambda r: (1 if r['score_vol'] > 0 else 0, r['score_vol']), reverse=True)
                podio_int = sorted(res, key=lambda r: (1 if r['score_int'] > 0 else 0, r['score_int']), reverse=True)

                return {
                    'list_tl': list_tl,
                    'list_tlh': list_tlh,
                    'list_mech': list_mech,
                    'podio_vol': podio_vol,
                    'podio_int': podio_int,
                    'records': res
                }

            df_season_data = df_storico[df_storico['Date_obj'].dt.year == anno_rk_sel]

            dati_w = build_roster_metrics(df_period_data, roster_totale)
            dati_s = build_roster_metrics(df_season_data, roster_totale)

            opzioni_pdf_rk = {
                tr("Report Ranking Roster", "Roster Ranking Report"): "Ranking_Roster"
            }
            render_action_bar(
                meta_items=[
                    (action_period_lbl, clean_week_rk),
                    (tr("Stagione", "Season"), str(anno_rk_sel)),
                    (tr("Atleti Roster", "Roster Athletes"), str(n_roster)),
                ],
                pdf_options=opzioni_pdf_rk,
                pdf_key=f"pdf_ranking_{clean_week_rk}_{anno_rk_sel}",
                generate_fn=lambda _: crea_pdf_medie_m0v3(
                    "ranking_roster",
                    clean_week=clean_week_rk,
                    anno_rk=anno_rk_sel,
                    dati_w=dati_w,
                    dati_s=dati_s,
                    n_roster=n_roster
                ),
                filename_fn=lambda _: f"M0V3_Ranking_Roster_{slugify_name(clean_week_rk)}_{anno_rk_sel}.pdf"
            )

            def generate_roster_table_html(header_title, header_badge, list_tl, list_tlh, list_mech, n_rows):
                rows_html = []
                for i in range(n_rows):
                    rank_num = i + 1
                    bg_row = "#fcfdfd" if i % 2 == 0 else "#ffffff"

                    if rank_num == 1:
                        badge_rank = "<span style='background:#fef3c7; color:#b45309; border:1px solid #fde68a; font-weight:900; font-size:11.5px; padding:3px 9px; border-radius:6px; display:inline-block;'>1 <i class='bi bi-award-fill' style='color:#b45309;'></i></span>"
                    elif rank_num == 2:
                        badge_rank = "<span style='background:#f1f5f9; color:#475569; border:1px solid #cbd5e1; font-weight:800; font-size:11.5px; padding:3px 9px; border-radius:6px; display:inline-block;'>2 <i class='bi bi-award-fill' style='color:#64748b;'></i></span>"
                    elif rank_num == 3:
                        badge_rank = "<span style='background:#ffedd5; color:#c2410c; border:1px solid #fed7aa; font-weight:800; font-size:11.5px; padding:3px 9px; border-radius:6px; display:inline-block;'>3 <i class='bi bi-award-fill' style='color:#c2410c;'></i></span>"
                    else:
                        badge_rank = f"<span style='color:#64748b; font-weight:700; font-size:11.5px;'>{rank_num}</span>"

                    item_tl = list_tl[i] if i < len(list_tl) else {'athlete': '-', 'tl': 0}
                    if item_tl['tl'] > 0:
                        name_tl = f"<span style='color:#0f172a; font-weight:700;'>{item_tl['athlete']}</span>"
                        val_tl = f"<span style='color:#0284c7; font-weight:800;'>{int(round(item_tl['tl'])):,}</span>".replace(",", ".")
                    else:
                        name_tl = f"<span style='color:#94a3b8;'>{item_tl['athlete']}</span>"
                        val_tl = "<span style='color:#94a3b8; font-weight:600;'>-</span>"

                    item_tlh = list_tlh[i] if i < len(list_tlh) else {'athlete': '-', 'tlh': 0}
                    if item_tlh['tlh'] > 0:
                        name_tlh = f"<span style='color:#0f172a; font-weight:700;'>{item_tlh['athlete']}</span>"
                        val_tlh = f"<span style='color:#dc2626; font-weight:800;'>{int(round(item_tlh['tlh'])):,}</span>".replace(",", ".")
                    else:
                        name_tlh = f"<span style='color:#94a3b8;'>{item_tlh['athlete']}</span>"
                        val_tlh = "<span style='color:#94a3b8; font-weight:600;'>-</span>"

                    item_mech = list_mech[i] if i < len(list_mech) else {'athlete': '-', 'mech': 0}
                    if item_mech['mech'] > 0:
                        name_mech = f"<span style='color:#0f172a; font-weight:700;'>{item_mech['athlete']}</span>"
                        val_mech = f"<span style='color:#7c3aed; font-weight:800;'>{int(round(item_mech['mech'])):,}</span>".replace(",", ".")
                    else:
                        name_mech = f"<span style='color:#94a3b8;'>{item_mech['athlete']}</span>"
                        val_mech = "<span style='color:#94a3b8; font-weight:600;'>-</span>"

                    rows_html.append(
                        f"<tr style='background:{bg_row}; border-bottom:1px solid #e2e8f0; font-family:\"Inter\",sans-serif;'>"
                        f"<td style='padding:8px 6px; text-align:center; border-right:1px solid #e2e8f0;'>{badge_rank}</td>"
                        f"<td style='padding:8px 12px; border-right:1px solid #e2e8f0; font-size:12.5px;'>{name_tl}</td>"
                        f"<td style='padding:8px 12px; text-align:right; border-right:2px solid #cbd5e1; font-size:13px;'>{val_tl}</td>"
                        f"<td style='padding:8px 12px; border-right:1px solid #e2e8f0; font-size:12.5px;'>{name_tlh}</td>"
                        f"<td style='padding:8px 12px; text-align:right; border-right:1px solid #e2e8f0; font-size:13px;'>{val_tlh}</td>"
                        f"<td style='padding:8px 12px; border-right:1px solid #e2e8f0; font-size:12.5px;'>{name_mech}</td>"
                        f"<td style='padding:8px 12px; text-align:right; font-size:13px;'>{val_mech}</td>"
                        f"</tr>"
                    )

                table_html = (
                    f"<div style='border:1px solid #cbd5e1; border-radius:12px; overflow:hidden; margin-bottom:24px; box-shadow:0 3px 10px rgba(15,23,42,0.04); font-family:\"Inter\",sans-serif;'>"
                    f"<div style='background:#0f172a; padding:12px 18px; display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #1e293b;'>"
                    f"<div style='display:flex; align-items:center; gap:10px;'>"
                    f"<span style='color:#38bdf8; font-size:13px; font-weight:900; letter-spacing:0.06em; text-transform:uppercase;'>{header_title}</span>"
                    f"</div>"
                    f"<span style='background:rgba(255,255,255,0.08); color:#f8fafc; font-size:11px; font-weight:700; padding:4px 10px; border-radius:6px; border:1px solid rgba(255,255,255,0.15);'>{header_badge}</span>"
                    f"</div>"
                    f"<div style='overflow-x:auto; background:#ffffff;'>"
                    f"<table style='width:100%; border-collapse:collapse;'>"
                    f"<thead>"
                    f"<tr>"
                    f"<th rowspan='2' style='width:7%; background:#0f172a; color:#f8fafc; font-size:11px; font-weight:800; text-align:center; padding:10px 4px; border:1px solid #1e293b; text-transform:uppercase; letter-spacing:0.05em;'>RANKING</th>"
                    f"<th colspan='2' style='width:31%; background:#fef3c7; color:#92400e; font-size:11px; font-weight:900; text-align:center; padding:9px 8px; border:1px solid #fde68a; text-transform:uppercase; letter-spacing:0.06em;'>VOLUME</th>"
                    f"<th colspan='4' style='width:62%; background:#fee2e2; color:#991b1b; font-size:11px; font-weight:900; text-align:center; padding:9px 8px; border:1px solid #fecaca; text-transform:uppercase; letter-spacing:0.06em;'>INTENSITÀ</th>"
                    f"</tr>"
                    f"<tr>"
                    f"<th colspan='2' style='background:#fffbeb; color:#b45309; font-size:11px; font-weight:800; text-align:center; padding:7px 8px; border:1px solid #fde68a; letter-spacing:0.04em;'>TRAINING LOAD</th>"
                    f"<th colspan='2' style='background:#fef2f2; color:#b91c1c; font-size:11px; font-weight:800; text-align:center; padding:7px 8px; border:1px solid #fecaca; letter-spacing:0.04em;'>TRAINING LOAD HIGH</th>"
                    f"<th colspan='2' style='background:#fef2f2; color:#b91c1c; font-size:11px; font-weight:800; text-align:center; padding:7px 8px; border:1px solid #fecaca; letter-spacing:0.04em;'>ACCELERAZIONI + DECELERAZIONI</th>"
                    f"</tr>"
                    f"<tr style='background:#f8fafc;'>"
                    f"<th style='padding:6px; border:1px solid #e2e8f0; font-size:10px; font-weight:800; color:#475569; text-align:center;'>POS</th>"
                    f"<th style='padding:6px 12px; border:1px solid #e2e8f0; font-size:10px; font-weight:800; color:#64748b; text-align:left;'>NOME</th>"
                    f"<th style='padding:6px 12px; border:1px solid #e2e8f0; font-size:10px; font-weight:800; color:#64748b; text-align:right; border-right:2px solid #cbd5e1;'>VALORE</th>"
                    f"<th style='padding:6px 12px; border:1px solid #e2e8f0; font-size:10px; font-weight:800; color:#64748b; text-align:left;'>NOME</th>"
                    f"<th style='padding:6px 12px; border:1px solid #e2e8f0; font-size:10px; font-weight:800; color:#64748b; text-align:right;'>VALORE</th>"
                    f"<th style='padding:6px 12px; border:1px solid #e2e8f0; font-size:10px; font-weight:800; color:#64748b; text-align:left;'>NOME</th>"
                    f"<th style='padding:6px 12px; border:1px solid #e2e8f0; font-size:10px; font-weight:800; color:#64748b; text-align:right;'>VALORE</th>"
                    f"</tr>"
                    f"</thead>"
                    f"<tbody>"
                    f"{''.join(rows_html)}"
                    f"</tbody>"
                    f"</table>"
                    f"</div>"
                    f"</div>"
                )
                return table_html

            def generate_podium_html(d_w, d_s, col_label="WEEK BEST", sub_badge="Week Best vs Season Best"):
                podium_rows = []
                for pos in [1, 2, 3]:
                    idx_p = pos - 1
                    bg_pod = "#ffffff" if pos % 2 != 0 else "#fcfdfd"

                    if pos == 1:
                        badge_pos = "<div style='font-size:22px; font-weight:900; color:#b45309; background:#fef3c7; border:2px solid #fbbf24; border-radius:50%; width:44px; height:44px; display:flex; align-items:center; justify-content:center; margin:0 auto; box-shadow:0 2px 6px rgba(245,158,11,0.25);'>1</div>"
                    elif pos == 2:
                        badge_pos = "<div style='font-size:20px; font-weight:900; color:#475569; background:#f1f5f9; border:2px solid #cbd5e1; border-radius:50%; width:40px; height:40px; display:flex; align-items:center; justify-content:center; margin:0 auto;'>2</div>"
                    else:
                        badge_pos = "<div style='font-size:19px; font-weight:900; color:#c2410c; background:#ffedd5; border:2px solid #fed7aa; border-radius:50%; width:38px; height:38px; display:flex; align-items:center; justify-content:center; margin:0 auto;'>3</div>"

                    item_wv = d_w['podio_vol'][idx_p] if idx_p < len(d_w['podio_vol']) else None
                    if item_wv and item_wv['score_vol'] > 0:
                        wv_cell = (
                            f"<div style='font-weight:800; font-size:14px; color:#0f172a;'>{item_wv['athlete']}</div>"
                            f"<div style='font-size:11px; color:#0284c7; font-weight:700; margin-top:2px;'>Score: {item_wv['score_vol']:.1f} pt "
                            f"<span style='color:#64748b; font-weight:500;'>({int(round(item_wv['tl'])):,} AU • {int(item_wv['dur'])}m • {int(item_wv['az2'])} az)</span></div>"
                        ).replace(",", ".")
                    else:
                        wv_cell = "<div style='font-weight:600; font-size:13px; color:#94a3b8;'>-</div>"

                    item_sv = d_s['podio_vol'][idx_p] if idx_p < len(d_s['podio_vol']) else None
                    if item_sv and item_sv['score_vol'] > 0:
                        sv_cell = (
                            f"<div style='font-weight:800; font-size:14px; color:#0f172a;'>{item_sv['athlete']}</div>"
                            f"<div style='font-size:11px; color:#0284c7; font-weight:700; margin-top:2px;'>Score: {item_sv['score_vol']:.1f} pt "
                            f"<span style='color:#64748b; font-weight:500;'>({int(round(item_sv['tl'])):,} AU • {int(item_sv['dur'])}m • {int(item_sv['az2'])} az)</span></div>"
                        ).replace(",", ".")
                    else:
                        sv_cell = "<div style='font-weight:600; font-size:13px; color:#94a3b8;'>-</div>"

                    item_wi = d_w['podio_int'][idx_p] if idx_p < len(d_w['podio_int']) else None
                    if item_wi and item_wi['score_int'] > 0:
                        wi_cell = (
                            f"<div style='font-weight:800; font-size:14px; color:#0f172a;'>{item_wi['athlete']}</div>"
                            f"<div style='font-size:11px; color:#dc2626; font-weight:700; margin-top:2px;'>Score: {item_wi['score_int']:.1f} pt "
                            f"<span style='color:#64748b; font-weight:500;'>({int(round(item_wi['tlh'])):,} AU • {int(item_wi['mech'])} acc/dec)</span></div>"
                        ).replace(",", ".")
                    else:
                        wi_cell = "<div style='font-weight:600; font-size:13px; color:#94a3b8;'>-</div>"

                    item_si = d_s['podio_int'][idx_p] if idx_p < len(d_s['podio_int']) else None
                    if item_si and item_si['score_int'] > 0:
                        si_cell = (
                            f"<div style='font-weight:800; font-size:14px; color:#0f172a;'>{item_si['athlete']}</div>"
                            f"<div style='font-size:11px; color:#dc2626; font-weight:700; margin-top:2px;'>Score: {item_si['score_int']:.1f} pt "
                            f"<span style='color:#64748b; font-weight:500;'>({int(round(item_si['tlh'])):,} AU • {int(item_si['mech'])} acc/dec)</span></div>"
                        ).replace(",", ".")
                    else:
                        si_cell = "<div style='font-weight:600; font-size:13px; color:#94a3b8;'>-</div>"

                    podium_rows.append(
                        f"<tr style='background:{bg_pod}; border-bottom:1px solid #e2e8f0; font-family:\"Inter\",sans-serif;'>"
                        f"<td style='padding:14px 16px; border-right:1px solid #e2e8f0;'>{wv_cell}</td>"
                        f"<td style='padding:14px 16px; border-right:2px solid #cbd5e1;'>{sv_cell}</td>"
                        f"<td style='padding:10px 4px; text-align:center; border-right:2px solid #cbd5e1; background:#f8fafc;'>{badge_pos}</td>"
                        f"<td style='padding:14px 16px; border-right:1px solid #e2e8f0;'>{wi_cell}</td>"
                        f"<td style='padding:14px 16px;'>{si_cell}</td>"
                        f"</tr>"
                    )

                podium_html = (
                    f"<div style='border:1px solid #cbd5e1; border-radius:12px; overflow:hidden; margin-top:10px; margin-bottom:24px; box-shadow:0 4px 14px rgba(15,23,42,0.06); font-family:\"Inter\",sans-serif;'>"
                    f"<div style='background:#0f172a; padding:12px 18px; display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #1e293b;'>"
                    f"<div style='display:flex; align-items:center; gap:8px;'>"
                    f"<i class='bi bi-trophy-fill' style='color:#38bdf8; font-size:18px;'></i>"
                    f"<span style='color:#ffffff; font-weight:900; font-size:13px; text-transform:uppercase; letter-spacing:0.06em;'>ROSTER BEST — PODIO VOLUME & INTENSITÀ</span>"
                    f"</div>"
                    f"<span style='background:rgba(255,255,255,0.08); color:#38bdf8; font-size:11px; font-weight:700; padding:4px 10px; border-radius:6px; border:1px solid rgba(56,189,248,0.25);'>{sub_badge}</span>"
                    f"</div>"
                    f"<div style='background:#f8fafc; border-bottom:1px solid #e2e8f0; padding:9px 18px; font-size:11px; color:#475569; display:flex; flex-wrap:wrap; gap:18px; align-items:center;'>"
                    f"<span><i class='bi bi-info-circle-fill' style='color:#0284c7; margin-right:5px;'></i><b style='color:#0369a1;'>CALCOLO VOLUME:</b> 40% Training Load + 35% Minuti + 25% Azioni >2\" (Normalizzato su max roster)</span>"
                    f"<span><i class='bi bi-fire' style='color:#dc2626; margin-right:5px;'></i><b style='color:#b91c1c;'>CALCOLO INTENSITÀ:</b> 50% TL High + 50% (Accelerazioni + Decelerazioni) (Normalizzato su max roster)</span>"
                    f"</div>"
                    f"<div style='overflow-x:auto; background:#ffffff;'>"
                    f"<table style='width:100%; border-collapse:collapse;'>"
                    f"<thead>"
                    f"<tr>"
                    f"<th colspan='2' style='width:45%; background:#eff6ff; color:#0369a1; font-size:12px; font-weight:900; text-align:center; padding:10px; border:1px solid #bfdbfe; letter-spacing:0.06em; text-transform:uppercase;'>VOLUME</th>"
                    f"<th rowspan='2' style='width:10%; background:#0f172a; color:#f8fafc; font-size:11px; font-weight:800; text-align:center; padding:8px 4px; border:1px solid #1e293b; letter-spacing:0.05em;'>PODIO</th>"
                    f"<th colspan='2' style='width:45%; background:#fef2f2; color:#b91c1c; font-size:12px; font-weight:900; text-align:center; padding:10px; border:1px solid #fecaca; letter-spacing:0.06em; text-transform:uppercase;'>INTENSITÀ</th>"
                    f"</tr>"
                    f"<tr>"
                    f"<th style='background:#f0fdf4; color:#15803d; font-size:11px; font-weight:800; text-align:left; padding:8px 16px; border:1px solid #e2e8f0; letter-spacing:0.04em;'>{col_label}</th>"
                    f"<th style='background:#f0fdf4; color:#15803d; font-size:11px; font-weight:800; text-align:left; padding:8px 16px; border:1px solid #e2e8f0; border-right:2px solid #cbd5e1; letter-spacing:0.04em;'>SEASON BEST</th>"
                    f"<th style='background:#fff1f2; color:#be123c; font-size:11px; font-weight:800; text-align:left; padding:8px 16px; border:1px solid #e2e8f0; letter-spacing:0.04em;'>{col_label}</th>"
                    f"<th style='background:#fff1f2; color:#be123c; font-size:11px; font-weight:800; text-align:left; padding:8px 16px; border:1px solid #e2e8f0; letter-spacing:0.04em;'>SEASON BEST</th>"
                    f"</tr>"
                    f"</thead>"
                    f"<tbody>"
                    f"{''.join(podium_rows)}"
                    f"</tbody>"
                    f"</table>"
                    f"</div>"
                    f"</div>"
                )
                return podium_html

            html_table_w = generate_roster_table_html(lbl_t1, badge_w, dati_w['list_tl'], dati_w['list_tlh'], dati_w['list_mech'], n_roster)
            st.html(html_table_w)

            lbl_t2 = tr("RANKING STAGIONALE ROSTER ATLETI", "SEASONAL ATHLETE ROSTER RANKING")
            badge_s = f"{tr('Stagione', 'Season')} {anno_rk_sel} • {n_roster} {tr('Atleti', 'Athletes')}"
            html_table_s = generate_roster_table_html(lbl_t2, badge_s, dati_s['list_tl'], dati_s['list_tlh'], dati_s['list_mech'], n_roster)
            st.html(html_table_s)

            html_podium = generate_podium_html(dati_w, dati_s, col_label=col_podium_w, sub_badge=badge_podium_sub)
            st.html(html_podium)

    elif active_medie_tab == T_DIST_R:
        st.html(
            "<div style='margin-top:10px; margin-bottom:18px;'>"
            f"<h3 style='color:#0f172a; margin:0 0 4px 0; font-size:22px; font-weight:800;'><i class='bi bi-pie-chart-fill' style='color:#0284c7; margin-right:8px;'></i>{tr('Distribuzione del Lavoro Roster (Tempo)', 'Roster Workload Distribution (Time)')}</h3>"
            f"<p style='color:#64748b; font-size:13px; margin:0;'>{tr('Ripartizione percentuale del tempo di allenamento per le tipologie di sessione condivise dall’intero roster, su scala settimanale e stagionale con grafico a barre sovrapposte al 100%.', 'Percentage distribution of training time across session types shared by the whole roster, weekly and seasonal with 100% stacked bar chart.')}</p>"
            "</div>"
        )

        if st.session_state.get('role') == 'Super-Admin':
            roster_dist_db = get_tutti_gli_atleti()
        else:
            roster_dist_db = get_atleti_associati(st.session_state['user'].id)

        roster_dist_dati = df_storico['Players'].dropna().unique().tolist()
        if roster_dist_db:
            roster_dist_totale = sorted(list(set(roster_dist_db) | set(roster_dist_dati)))
        else:
            roster_dist_totale = sorted(list(set(roster_dist_dati)))

        if not roster_dist_totale:
            st.info(tr("Nessun atleta disponibile nel roster.", "No athletes available in roster."))
        else:
            opt_mode_dist_sett = tr("Singola Settimana", "Single Week")
            opt_mode_dist_cust = tr("Periodo Personalizzato", "Custom Period")
            filtro_modo_dist = render_tab_navigation(
                [opt_mode_dist_sett, opt_mode_dist_cust],
                key="dist_filter_mode"
            )
            is_custom_dist = (filtro_modo_dist == opt_mode_dist_cust)

            anni_disp_dist = sorted(df_storico['Date_obj'].dt.year.dropna().unique().astype(int).tolist(), reverse=True)
            if not anni_disp_dist:
                anni_disp_dist = [datetime.now().year]

            if not is_custom_dist:
                c_dist_y, c_dist_w = st.columns([1, 2])
                with c_dist_y:
                    anno_dist_sel = st.selectbox(
                        tr("Stagione (Anno Solare)", "Season (Solar Year)"),
                        anni_disp_dist,
                        index=0,
                        key="dist_roster_anno"
                    )

                df_anno_dist = df_storico[df_storico['Date_obj'].dt.year == anno_dist_sel].copy()
                settimane_anno_dist = df_anno_dist['Week_Label'].dropna().unique().tolist()
                settimane_anno_dist.sort(key=lambda x: pd.to_datetime(x.split(" - ")[0], format='%d/%m/%Y'), reverse=True)

                opt_cur_w_dist = f"[{tr('Settimana Corrente', 'Current Week')}] {curr_w_lbl}"
                if curr_w_start.year == anno_dist_sel:
                    if curr_w_lbl in settimane_anno_dist:
                        opts_w_dist = [opt_cur_w_dist] + [s for s in settimane_anno_dist if s != curr_w_lbl]
                    else:
                        opts_w_dist = [opt_cur_w_dist] + settimane_anno_dist
                else:
                    opts_w_dist = settimane_anno_dist if settimane_anno_dist else [curr_w_lbl]

                with c_dist_w:
                    settimana_dist_sel = st.selectbox(
                        tr("Settimana di Riferimento", "Reference Week"),
                        opts_w_dist,
                        index=0,
                        key="dist_roster_settimana"
                    )

                clean_week_dist = curr_w_lbl if opt_cur_w_dist in settimana_dist_sel else settimana_dist_sel
                df_w_sub = df_storico[df_storico['Week_Label'] == clean_week_dist]
                lbl_dw = tr("DISTRIBUZIONE DEL LAVORO SETTIMANALE (TEMPO)", "WEEKLY WORKLOAD DISTRIBUTION (TIME)")
                badge_dw = f"Week {clean_week_dist} • {len(roster_dist_totale)} {tr('Atleti', 'Athletes')}"
                dist_action_lbl = tr("Settimana", "Week")
                chart_period_btn = f"{tr('Settimanale', 'Weekly')} ({clean_week_dist})"
            else:
                c_dist_d1, c_dist_d2, c_dist_y = st.columns([1.5, 1.5, 1])
                min_dt_dist = df_storico['Date_obj'].dropna().min()
                max_dt_dist = df_storico['Date_obj'].dropna().max()
                min_d_dist = min_dt_dist.date() if pd.notnull(min_dt_dist) else (date.today() - timedelta(days=90))
                max_d_dist = max_dt_dist.date() if pd.notnull(max_dt_dist) else date.today()
                def_start_dist = max(min_d_dist, max_d_dist - timedelta(days=28))

                with c_dist_d1:
                    dist_d_start = st.date_input(
                        tr("Data Inizio Periodo", "Period Start Date"),
                        value=def_start_dist,
                        min_value=min_d_dist,
                        max_value=max_d_dist,
                        key="dist_custom_d_start"
                    )
                with c_dist_d2:
                    dist_d_end = st.date_input(
                        tr("Data Fine Periodo", "Period End Date"),
                        value=max_d_dist,
                        min_value=min_d_dist,
                        max_value=max_d_dist,
                        key="dist_custom_d_end"
                    )
                with c_dist_y:
                    anno_dist_sel = st.selectbox(
                        tr("Stagione (Anno Solare)", "Season (Solar Year)"),
                        anni_disp_dist,
                        index=0,
                        key="dist_roster_anno_cust"
                    )

                if dist_d_start > dist_d_end:
                    dist_d_start, dist_d_end = dist_d_end, dist_d_start

                clean_week_dist = f"{dist_d_start.strftime('%d/%m/%Y')} - {dist_d_end.strftime('%d/%m/%Y')}"
                mask_dist = (df_storico['Date_obj'].dt.date >= dist_d_start) & (df_storico['Date_obj'].dt.date <= dist_d_end)
                df_w_sub = df_storico[mask_dist]
                lbl_dw = tr("PERIODO SELEZIONATO — DISTRIBUZIONE DEL LAVORO (TEMPO)", "SELECTED PERIOD — WORKLOAD DISTRIBUTION (TIME)")
                badge_dw = f"{tr('Periodo', 'Period')}: {clean_week_dist} • {len(roster_dist_totale)} {tr('Atleti', 'Athletes')}"
                dist_action_lbl = tr("Periodo", "Period")
                chart_period_btn = f"{tr('Periodo Selezionato', 'Selected Period')} ({clean_week_dist})"

            # Identificazione delle sole tipologie condivise da tutti gli atleti del roster con sessioni
            ath_types_map = {}
            for ath in roster_dist_totale:
                types_ath = set(df_storico[df_storico['Players'] == ath]['Tipologia Sessione'].dropna().unique())
                clean_types = {str(tp).strip() for tp in types_ath if str(tp).strip() and str(tp).strip() != "Non definita"}
                if clean_types:
                    ath_types_map[ath] = clean_types

            if ath_types_map:
                tipologie_condivise = sorted(list(set.intersection(*ath_types_map.values())))
                # Fallback: se l'intersezione comune a tutti è vuota, prendi quelle condivise da >= 2 atleti
                if not tipologie_condivise and len(ath_types_map) > 1:
                    all_seen_types = set().union(*ath_types_map.values())
                    tipologie_condivise = sorted([tp for tp in all_seen_types if sum(1 for ts in ath_types_map.values() if tp in ts) >= 2])
                if not tipologie_condivise:
                    tipologie_condivise = sorted(list(set().union(*ath_types_map.values())))
            else:
                tipologie_condivise = list(CANONICAL_TIPOLOGIE_SESSIONE)

            # Ordinamento logico canonico delle tipologie
            canonical_rank = {name.lower(): idx for idx, name in enumerate(CANONICAL_TIPOLOGIE_SESSIONE)}
            def sort_key_tipo(t_name):
                return canonical_rank.get(t_name.lower(), 99)

            tipologie_condivise = sorted(tipologie_condivise, key=sort_key_tipo)

            # Palette Cromatiche per tipologia
            palette_map = {
                "tennis base": "#0ea5e9",
                "1000 palle": "#0d9488",
                "tennis match": "#6366f1",
                "500 palle": "#8b5cf6",
                "servizio": "#0891b2",
                "torneo": "#f59e0b",
                "match": "#ef4444",
                "match doppio": "#ea580c",
                "workout": "#10b981",
                "calcio": "#84cc16",
            }
            fallback_cols = ["#ef4444", "#0ea5e9", "#10b981", "#8b5cf6", "#f59e0b", "#ec4899", "#14b8a6", "#6366f1"]
            tipo_colors = {}
            for idx_t, tp in enumerate(tipologie_condivise):
                low = tp.lower()
                if low in palette_map:
                    tipo_colors[tp] = palette_map[low]
                else:
                    tipo_colors[tp] = fallback_cols[idx_t % len(fallback_cols)]

            # Calcolo ripartizione tempo (Opzione A: Normalizzazione al 100% sulla somma delle tipologie condivise)
            def compute_dist(df_sub, roster, tipologie):
                records = []
                for ath in roster:
                    df_a = df_sub[df_sub['Players'] == ath]
                    m_map = {}
                    p_map = {}
                    for tp in tipologie:
                        m = float(df_a[df_a['Tipologia Sessione'] == tp]['Minuti'].sum()) if not df_a.empty else 0.0
                        m_map[tp] = m

                    # Denominatore calcolato sommando solo i minuti delle tipologie condivise
                    tot_min_shared = sum(m_map[tp] for tp in tipologie)
                    for tp in tipologie:
                        p_map[tp] = (m_map[tp] / tot_min_shared * 100.0) if tot_min_shared > 0 else 0.0

                    records.append({
                        'athlete': ath,
                        'tot_min': tot_min_shared,
                        'm_map': m_map,
                        'p_map': p_map,
                        'has_data': tot_min_shared > 0
                    })
                return records

            df_s_sub = df_storico[df_storico['Date_obj'].dt.year == anno_dist_sel]

            records_w = compute_dist(df_w_sub, roster_dist_totale, tipologie_condivise)
            records_s = compute_dist(df_s_sub, roster_dist_totale, tipologie_condivise)

            opzioni_pdf_dist = {
                tr("Report Distribuzione Lavoro", "Workload Distribution Report"): "Distribuzione_Roster"
            }
            render_action_bar(
                meta_items=[
                    (dist_action_lbl, clean_week_dist),
                    (tr("Stagione", "Season"), str(anno_dist_sel)),
                    (tr("Tipologie Condivise", "Shared Types"), f"{len(tipologie_condivise)} {tr('tipologie', 'types')}"),
                    (tr("Atleti Roster", "Roster Athletes"), str(len(roster_dist_totale))),
                ],
                pdf_options=opzioni_pdf_dist,
                pdf_key=f"pdf_dist_{clean_week_dist}_{anno_dist_sel}",
                generate_fn=lambda _: crea_pdf_medie_m0v3(
                    "distribuzione_roster",
                    clean_week=clean_week_dist,
                    anno_dist=anno_dist_sel,
                    records_w=records_w,
                    records_s=records_s,
                    tipologie=tipologie_condivise,
                    fig=fig_dist
                ),
                filename_fn=lambda _: f"M0V3_Distribuzione_Lavoro_Roster_{slugify_name(clean_week_dist)}_{anno_dist_sel}.pdf"
            )

            def generate_dist_table_html(title_text, badge_text, records, tipologie, color_theme="navy"):
                super_txt = "#fef3c7" if color_theme == "gold" else ("#38bdf8" if color_theme == "cyan" else "#38bdf8")

                th_tipi = []
                for tp in tipologie:
                    c_col = tipo_colors.get(tp, "#475569")
                    th_tipi.append(
                        f"<th style='padding:10px 8px; text-align:center; border:1px solid #e2e8f0; font-size:11.5px; font-weight:800; color:{c_col}; text-transform:uppercase; letter-spacing:0.05em; min-width:85px;'>"
                        f"<span style='display:inline-block; width:8px; height:8px; border-radius:50%; background:{c_col}; margin-right:6px;'></span>{tp}"
                        f"</th>"
                    )

                rows_html = []
                for i, r in enumerate(records):
                    bg_row = "#fcfdfd" if i % 2 == 0 else "#ffffff"
                    ath_style = "font-weight:800; color:#0f172a;" if r['has_data'] else "font-weight:600; color:#94a3b8;"
                    tot_badge = f"<span style='color:#64748b; font-size:11px; font-weight:600; margin-left:6px;'>({int(round(r['tot_min']))} min)</span>" if r['has_data'] else ""

                    td_tipi = []
                    for tp in tipologie:
                        if not r['has_data']:
                            td_tipi.append(
                                "<td style='padding:9px 10px; text-align:center; border:1px solid #e2e8f0; font-size:12px; color:#cbd5e1; font-weight:600;'>-</td>"
                            )
                        else:
                            pct = r['p_map'][tp]
                            if pct > 0:
                                td_tipi.append(
                                    f"<td style='padding:9px 10px; text-align:center; border:1px solid #e2e8f0; font-size:13px; font-weight:800; color:#0f172a; background:rgba(2,132,199,0.03);'>"
                                    f"{round(pct)}%"
                                    f"</td>"
                                )
                            else:
                                td_tipi.append(
                                    "<td style='padding:9px 10px; text-align:center; border:1px solid #e2e8f0; font-size:12px; font-weight:600; color:#94a3b8;'>0%</td>"
                                )

                    rows_html.append(
                        f"<tr style='background:{bg_row}; font-family:\"Inter\",sans-serif;'>"
                        f"<td style='padding:9px 14px; border:1px solid #e2e8f0; font-size:13px; {ath_style}'>{r['athlete']}{tot_badge}</td>"
                        f"{''.join(td_tipi)}"
                        f"</tr>"
                    )

                table_html = (
                    f"<div style='border:1px solid #cbd5e1; border-radius:12px; overflow:hidden; margin-bottom:24px; box-shadow:0 3px 10px rgba(15,23,42,0.04); font-family:\"Inter\",sans-serif;'>"
                    f"<div style='background:#0f172a; padding:12px 18px; display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #1e293b;'>"
                    f"<div style='display:flex; align-items:center; gap:10px;'>"
                    f"<span style='color:{super_txt}; font-size:13px; font-weight:900; letter-spacing:0.06em; text-transform:uppercase;'>{title_text}</span>"
                    f"</div>"
                    f"<span style='background:rgba(255,255,255,0.08); color:#f8fafc; font-size:11px; font-weight:700; padding:4px 10px; border-radius:6px; border:1px solid rgba(255,255,255,0.15);'>{badge_text}</span>"
                    f"</div>"
                    f"<div style='overflow-x:auto; background:#ffffff;'>"
                    f"<table style='width:100%; border-collapse:collapse;'>"
                    f"<thead>"
                    f"<tr style='background:#f8fafc;'>"
                    f"<th style='padding:10px 14px; text-align:left; border:1px solid #e2e8f0; font-size:11.5px; font-weight:800; color:#475569; text-transform:uppercase; letter-spacing:0.05em; width:25%;'>ATLETA</th>"
                    f"{''.join(th_tipi)}"
                    f"</tr>"
                    f"</thead>"
                    f"<tbody>"
                    f"{''.join(rows_html)}"
                    f"</tbody>"
                    f"</table>"
                    f"</div>"
                    f"</div>"
                )
                return table_html

            st.html(generate_dist_table_html(lbl_dw, badge_dw, records_w, tipologie_condivise, color_theme="gold"))

            lbl_ds = tr("DISTRIBUZIONE DEL LAVORO STAGIONALE (TEMPO)", "SEASONAL WORKLOAD DISTRIBUTION (TIME)")
            badge_ds = f"{tr('Stagione', 'Season')} {anno_dist_sel} • {len(roster_dist_totale)} {tr('Atleti', 'Athletes')}"
            st.html(generate_dist_table_html(lbl_ds, badge_ds, records_s, tipologie_condivise, color_theme="cyan"))

            # Grafico a Barre Impilate al 100%
            c_g_t, c_g_m = st.columns([2, 1.2])
            with c_g_t:
                st.html(
                    f"<div style='font-size:13px; font-weight:900; color:#0f172a; text-transform:uppercase; letter-spacing:0.05em; margin-top:8px; margin-bottom:4px;'>"
                    f"<i class='bi bi-bar-chart-steps' style='color:#0284c7; margin-right:8px;'></i>{tr('COMPOSIZIONE PERCENTUALE DEL LAVORO (100% STACKED)', 'PERCENTAGE WORKLOAD COMPOSITION (100% STACKED)')}"
                    f"</div>"
                    f"<div style='font-size:11.5px; color:#64748b; margin-bottom:12px;'>{tr('Ripartizione visiva per ciascun atleta delle quote di tempo dedicate alle tipologie condivise.', 'Visual breakdown per athlete of time share allocated to shared session types.')}</div>"
                )
            with c_g_m:
                mode_chart_dist = render_tab_navigation(
                    [f"{tr('Stagionale', 'Seasonal')} ({anno_dist_sel})", chart_period_btn],
                    key="radio_mode_dist_chart"
                )

            is_seasonal_chart = (f"({anno_dist_sel})" in mode_chart_dist)
            records_chart = records_s if is_seasonal_chart else records_w

            ath_labels = [r['athlete'] for r in records_chart]
            fig_dist = go.Figure()

            for tp in tipologie_condivise:
                c_tp = tipo_colors.get(tp, "#0284c7")
                y_pcts = [r['p_map'][tp] for r in records_chart]
                custom_mins = [int(round(r['m_map'][tp])) for r in records_chart]

                fig_dist.add_trace(go.Bar(
                    name=tp.upper(),
                    x=ath_labels,
                    y=y_pcts,
                    marker=dict(color=c_tp, line=dict(color='#ffffff', width=1.5)),
                    customdata=custom_mins,
                    hovertemplate="<b>%{x}</b><br>Tipologia: " + tp + "<br>Quota: %{y:.1f}%<br>Tempo: %{customdata} min<extra></extra>"
                ))

            fig_dist.update_layout(
                barmode='stack',
                height=380,
                margin=dict(l=40, r=20, t=28, b=40),
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                xaxis=dict(
                    tickfont=dict(size=12, color='#0f172a', family='Inter', weight='bold'),
                    showgrid=False,
                    linecolor='#cbd5e1'
                ),
                yaxis=dict(
                    ticksuffix="%",
                    range=[0, 100],
                    dtick=20,
                    tickfont=dict(size=11, color='#64748b', family='Inter'),
                    showgrid=True,
                    gridcolor='#f1f5f9',
                    linecolor='#cbd5e1'
                ),
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.22,
                    xanchor="center",
                    x=0.5,
                    font=dict(size=11, color='#0f172a', family='Inter')
                )
            )

            st.plotly_chart(fig_dist, use_container_width=True, key="fig_distribuzione_roster")

    elif active_medie_tab == T_STRESS_R:
        if "Stress Roster 8 settimane" not in report_abilitati and st.session_state.get('role') != 'Super-Admin':
            st.info(tr("Il modulo 'Stress Roster 8 settimane' non è abilitato per questo account. Contatta l'amministratore.", "The 'Stress Roster 8 settimane' module is not enabled for this account. Contact admin."))
        else:
            st.html(
                "<div style='margin-top:10px; margin-bottom:18px;'>"
                f"<h3 style='color:#0f172a; margin:0 0 4px 0; font-size:22px; font-weight:800;'><i class='bi bi-activity' style='color:#0284c7; margin-right:8px;'></i>{tr('Stress Roster 8 settimane — ACWR, Monotonia & Training Strain', 'Roster Stress 8 Weeks — ACWR, Monotony & Training Strain')}</h3>"
                f"<p style='color:#64748b; font-size:13px; margin:0;'>{tr('Monitoraggio longitudinale dell’intero roster nelle 8 settimane precedenti con curve interattive a zone fisiologiche (ACWR %, Monotonia, Strain) e matrice comparativa con sparklines.', 'Longitudinal monitoring of the whole roster across the 8 preceding weeks with interactive physiological-zone curves (ACWR %, Monotony, Strain) and comparative matrix with sparklines.')}</p>"
                "</div>"
            )

        if st.session_state.get('role') == 'Super-Admin':
            roster_st_db = get_tutti_gli_atleti()
        else:
            roster_st_db = get_atleti_associati(st.session_state['user'].id)

        roster_st_dati = df_storico['Players'].dropna().unique().tolist()
        if roster_st_db:
            roster_stress_totale = sorted(list(set(roster_st_db) | set(roster_st_dati)))
        else:
            roster_stress_totale = sorted(list(set(roster_st_dati)))

        if not roster_stress_totale:
            st.info(tr("Nessun atleta disponibile nel roster.", "No athletes available in roster."))
        else:
            c_st_wk, c_st_met, c_st_car = st.columns([1.6, 1.4, 1.2])

            settimane_tutte = df_storico['Week_Label'].dropna().unique().tolist()
            settimane_tutte.sort(key=lambda x: pd.to_datetime(x.split(" - ")[0], format='%d/%m/%Y'), reverse=True)
            opt_cur_w_st = f"[{tr('Settimana Corrente', 'Current Week')}] {curr_w_lbl}"
            if curr_w_lbl in settimane_tutte:
                opts_w_st = [opt_cur_w_st] + [s for s in settimane_tutte if s != curr_w_lbl]
            else:
                opts_w_st = [opt_cur_w_st] + settimane_tutte

            with c_st_wk:
                settimana_st_sel = st.selectbox(
                    tr("Settimana di Riferimento (8ª Settimana)", "Reference Week (8th Week)"),
                    opts_w_st,
                    index=0,
                    key="stress_sel_week"
                )
            clean_w_st = curr_w_lbl if opt_cur_w_st in settimana_st_sel else settimana_st_sel

            with c_st_met:
                st.caption(tr("Metrica da Analizzare", "Metric to Analyze"))
                metrica_st_sel = render_tab_navigation(
                    ["ACWR (Gabbett)", "Monotonia (Foster)", "Training Strain (Foster)"],
                    key="stress_radio_metrica"
                )

            with c_st_car:
                st.caption(tr("Base di Carico", "Workload Base"))
                carico_st_sel = render_tab_navigation(
                    [tr("Volume (TL)", "Volume (TL)"), tr("Intensità (TL High)", "Intensity (TL High)")],
                    key="stress_radio_carico"
                )

            is_tlh_st = ("TL High" in carico_st_sel)
            col_carico_st = "TL_High" if is_tlh_st else "Training Load"
            unit_carico = "AU (TL High)" if is_tlh_st else "AU (TL)"

            # Costruzione Timeline 8 Settimane Consecutive
            ref_dt_st = pd.to_datetime(clean_w_st.split(" - ")[0], format='%d/%m/%Y')
            weeks_8 = []
            for i in range(7, -1, -1):
                w_start = ref_dt_st - timedelta(weeks=i)
                w_end = w_start + timedelta(days=6)
                w_lbl = f"{w_start.strftime('%d/%m/%Y')} - {w_end.strftime('%d/%m/%Y')}"
                w_short = w_start.strftime('%d/%m')
                weeks_8.append({
                    'pos': 8 - i,
                    'start': w_start,
                    'end': w_end,
                    'label': w_lbl,
                    'short': w_short
                })

            ath_stress_data = {}
            for ath in roster_stress_totale:
                df_a = df_storico[df_storico['Players'] == ath]
                ath_w_records = []

                for w_info in weeks_8:
                    w_s = w_info['start']
                    w_e = w_info['end']

                    df_week_a = df_a[(df_a['Date_obj'] >= w_s) & (df_a['Date_obj'] <= w_e)]
                    day_map = df_week_a.groupby(df_week_a['Date_obj'].dt.date)[col_carico_st].sum().to_dict() if not df_week_a.empty else {}
                    daily_vals = [float(day_map.get((w_s + timedelta(days=d_off)).date(), 0.0)) for d_off in range(7)]

                    tot_w = sum(daily_vals)
                    mean_w = tot_w / 7.0
                    std_w = float(np.std(daily_vals, ddof=1)) if len(daily_vals) > 1 else 0.0

                    if std_w > 0:
                        mono_w = round(mean_w / std_w, 2)
                    elif mean_w > 0:
                        mono_w = 3.50
                    else:
                        mono_w = 0.00

                    strain_w = round(tot_w * mono_w, 1)

                    # Baseline cronica sui 28 giorni precedenti con gestione cold-start
                    b_end = w_s - timedelta(days=1)
                    b_start = b_end - timedelta(days=27)
                    df_base = df_a[(df_a['Date_obj'] >= b_start) & (df_a['Date_obj'] <= b_end)] if not df_a.empty else pd.DataFrame()
                    blocchi_w = calcola_blocchi_baseline(df_a, b_end, 7.0)
                    chronic_w = (float(df_base[col_carico_st].sum()) / blocchi_w) if not df_base.empty and blocchi_w > 0 else 0.0

                    # ACWR espresso in scala percentuale (100% = carico cronico di riferimento)
                    if chronic_w > 0:
                        acwr_w = round((tot_w / chronic_w) * 100.0, 1)
                    elif tot_w > 0:
                        acwr_w = 100.0
                    else:
                        acwr_w = 0.0

                    ath_w_records.append({
                        'pos': w_info['pos'],
                        'short': w_info['short'],
                        'label': w_info['label'],
                        'tot_w': tot_w,
                        'acwr': acwr_w,
                        'monotonia': mono_w,
                        'strain': strain_w,
                        'has_load': tot_w > 0
                    })

                ath_stress_data[ath] = ath_w_records

            if "ACWR" in metrica_st_sel:
                metric_key = 'acwr'
                metric_name = "ACWR (Rapporto Acuto:Cronico %)"
            elif "Monotonia" in metrica_st_sel:
                metric_key = 'monotonia'
                metric_name = "Indice di Monotonia (Foster)"
            else:
                metric_key = 'strain'
                metric_name = f"Training Strain (Foster) [{unit_carico}]"

            ath_strain_baselines = {}
            for ath in roster_stress_totale:
                strains_a = [r['strain'] for r in ath_stress_data.get(ath, []) if r['has_load'] and r['strain'] > 0]
                ath_strain_baselines[ath] = float(np.mean(strains_a)) if strains_a else 1500.0

            if metric_key == 'strain':
                opt_ath_soglia = [tr("Nessuna / Panoramica Roster", "None / Roster Overview")] + roster_stress_totale
                sel_ath_soglia = st.selectbox(
                    tr("Visualizza Soglia Individuale (+50% Allarme) per Atleta:", "Show Individual Threshold (+50% Alarm) for Athlete:"),
                    opt_ath_soglia,
                    index=0,
                    key="stress_sel_ref_ath"
                )

            def get_metric_badge(m_key, val, has_load, bl_strain=1000.0):
                if not has_load and val <= 0:
                    return "<span style='color:#cbd5e1; font-weight:600;'>-</span>"

                if m_key == 'acwr':
                    if val < 80.0:
                        return f"<span style='background:#e0f2fe; color:#0284c7; border:1px solid #bae6fd; font-weight:800; padding:3px 8px; border-radius:6px; font-size:12px; display:inline-block;'>{val:.0f}%</span>"
                    elif val <= 130.0:
                        return f"<span style='background:#dcfce7; color:#15803d; border:1px solid #bbf7d0; font-weight:800; padding:3px 8px; border-radius:6px; font-size:12px; display:inline-block;'>{val:.0f}%</span>"
                    elif val <= 150.0:
                        return f"<span style='background:#fef3c7; color:#b45309; border:1px solid #fde68a; font-weight:800; padding:3px 8px; border-radius:6px; font-size:12px; display:inline-block;'>{val:.0f}%</span>"
                    else:
                        return f"<span style='background:#fee2e2; color:#b91c1c; border:1px solid #fecaca; font-weight:800; padding:3px 8px; border-radius:6px; font-size:12px; display:inline-block;'>{val:.0f}% <i class='bi bi-exclamation-octagon-fill' style='margin-left:3px;'></i></span>"

                elif m_key == 'monotonia':
                    if val < 1.50:
                        return f"<span style='background:#dcfce7; color:#15803d; border:1px solid #bbf7d0; font-weight:800; padding:3px 8px; border-radius:6px; font-size:12px; display:inline-block;'>{val:.2f}</span>"
                    elif val <= 2.00:
                        return f"<span style='background:#fef3c7; color:#b45309; border:1px solid #fde68a; font-weight:800; padding:3px 8px; border-radius:6px; font-size:12px; display:inline-block;'>{val:.2f}</span>"
                    else:
                        return f"<span style='background:#fee2e2; color:#b91c1c; border:1px solid #fecaca; font-weight:800; padding:3px 8px; border-radius:6px; font-size:12px; display:inline-block;'>{val:.2f}</span>"

                else:
                    str_v = f"{int(round(val)):,}".replace(",", ".")
                    th_warn = bl_strain * 1.5
                    th_crit = bl_strain * 2.0
                    if val <= 0:
                        return "<span style='color:#cbd5e1; font-weight:600;'>-</span>"
                    elif val < th_warn:
                        return f"<span style='background:#dcfce7; color:#15803d; border:1px solid #bbf7d0; font-weight:800; padding:3px 8px; border-radius:6px; font-size:12px; display:inline-block;'>{str_v}</span>"
                    elif val <= th_crit:
                        return f"<span style='background:#fef3c7; color:#b45309; border:1px solid #fde68a; font-weight:800; padding:3px 8px; border-radius:6px; font-size:12px; display:inline-block;'>{str_v} <i class='bi bi-exclamation-triangle-fill' style='margin-left:3px;'></i></span>"
                    else:
                        return f"<span style='background:#fee2e2; color:#b91c1c; border:1px solid #fecaca; font-weight:800; padding:3px 8px; border-radius:6px; font-size:12px; display:inline-block;'>{str_v} <i class='bi bi-exclamation-octagon-fill' style='margin-left:3px;'></i></span>"

            def render_svg_sparkline(values, width=80, height=22, stroke_color="#0284c7"):
                if not values or all(v == 0 for v in values):
                    return f"<svg width='{width}' height='{height}' style='vertical-align:middle;'><line x1='0' y1='{height/2}' x2='{width}' y2='{height/2}' stroke='#cbd5e1' stroke-dasharray='2,2' stroke-width='1.5'/></svg>"
                min_v = min(values)
                max_v = max(values)
                span = max_v - min_v if max_v > min_v else 1.0
                points = []
                n = len(values)
                dx = (width - 8) / (n - 1) if n > 1 else width
                for idx, v in enumerate(values):
                    x = 4 + idx * dx
                    y = height - 4 - ((v - min_v) / span * (height - 8))
                    points.append(f"{x:.1f},{y:.1f}")
                poly = " ".join(points)
                last_x, last_y = points[-1].split(",")
                return (
                    f"<svg width='{width}' height='{height}' style='vertical-align:middle; overflow:visible;'>"
                    f"<polyline fill='none' stroke='{stroke_color}' stroke-width='2' stroke-linecap='round' stroke-linejoin='round' points='{poly}'/>"
                    f"<circle cx='{last_x}' cy='{last_y}' r='3' fill='{stroke_color}'/>"
                    f"</svg>"
                )

            roster_colors = [
                "#0284c7", "#ef4444", "#10b981", "#8b5cf6", "#f59e0b",
                "#06b6d4", "#ec4899", "#84cc16", "#f97316", "#6366f1",
                "#14b8a6", "#d97706", "#4f46e5", "#e11d48", "#059669"
            ]

            x_weeks_short = [w['short'] for w in weeks_8]
            fig_stress = go.Figure()

            for idx_a, ath in enumerate(roster_stress_totale):
                c_ath = roster_colors[idx_a % len(roster_colors)]
                records = ath_stress_data[ath]
                y_vals = [r[metric_key] for r in records]
                ath_bl = ath_strain_baselines.get(ath, 1500.0)
                ath_warn = ath_bl * 1.5

                if metric_key == 'strain':
                    tmpl = (
                        f"<b>{ath}</b><br>Settimana: %{{x}}<br>{metric_name}: <b>%{{y:,.0f}} AU</b><br>"
                        f"Baseline Indiv.: <b>{int(round(ath_bl)):,} AU</b><br>"
                        f"Soglia Allarme (+50%): <b>{int(round(ath_warn)):,} AU</b><extra></extra>"
                    ).replace(",", ".")
                elif metric_key == 'acwr':
                    tmpl = f"<b>{ath}</b><br>Settimana: %{{x}}<br>ACWR: <b>%{{y:.0f}}%</b><extra></extra>"
                else:
                    tmpl = f"<b>{ath}</b><br>Settimana: %{{x}}<br>Monotonia Foster: <b>%{{y:.2f}}</b><extra></extra>"

                fig_stress.add_trace(go.Scatter(
                    name=ath,
                    x=x_weeks_short,
                    y=y_vals,
                    mode='lines+markers',
                    line=dict(color=c_ath, width=2.5, shape='spline'),
                    marker=dict(size=7, color=c_ath, line=dict(color='#ffffff', width=1.5)),
                    hovertemplate=tmpl
                ))

            if metric_key == 'acwr':
                fig_stress.add_hrect(y0=80, y1=130, fillcolor="rgba(34, 197, 94, 0.10)", line_width=0,
                                     annotation_text="Sweet Spot (80% - 130%)", annotation_position="top left",
                                     annotation_font_size=10, annotation_font_color="#15803d")
                fig_stress.add_hrect(y0=130, y1=150, fillcolor="rgba(245, 158, 11, 0.08)", line_width=0,
                                     annotation_text="Attenzione (130% - 150%)", annotation_position="top left",
                                     annotation_font_size=10, annotation_font_color="#b45309")
                fig_stress.add_hline(y=150, line_dash="dash", line_color="#ef4444", line_width=1.5,
                                    annotation_text="Soglia Pericolo (> 150%)", annotation_position="top left",
                                    annotation_font_size=10, annotation_font_color="#b91c1c")
                fig_stress.add_hline(y=100, line_dash="dot", line_color="#0284c7", line_width=1.2,
                                    annotation_text="Baseline (100%)", annotation_position="bottom left",
                                    annotation_font_size=9, annotation_font_color="#0284c7")
                all_acwr = [r['acwr'] for records in ath_stress_data.values() for r in records]
                y_max_plot = max(max(all_acwr) if all_acwr else 150.0, 180.0) * 1.15
                fig_stress.update_layout(yaxis=dict(range=[0, y_max_plot], dtick=25, ticksuffix="%"))

            elif metric_key == 'monotonia':
                fig_stress.add_hrect(y0=0, y1=1.5, fillcolor="rgba(34, 197, 94, 0.10)", line_width=0,
                                     annotation_text="Ottimale (< 1.5)", annotation_position="top left",
                                     annotation_font_size=10, annotation_font_color="#15803d")
                fig_stress.add_hrect(y0=1.5, y1=2.0, fillcolor="rgba(245, 158, 11, 0.08)", line_width=0,
                                     annotation_text="Moderata (1.5 - 2.0)", annotation_position="top left",
                                     annotation_font_size=10, annotation_font_color="#b45309")
                fig_stress.add_hline(y=2.0, line_dash="dash", line_color="#ef4444", line_width=1.5,
                                    annotation_text="Allarme Monotonia Foster (> 2.0)", annotation_position="top left",
                                    annotation_font_size=10, annotation_font_color="#b91c1c")
                all_mono = [r['monotonia'] for records in ath_stress_data.values() for r in records]
                y_max_plot = max(max(all_mono) if all_mono else 2.0, 2.5) * 1.15
                fig_stress.update_layout(yaxis=dict(range=[0, y_max_plot], dtick=0.5))

            else:
                if sel_ath_soglia != opt_ath_soglia[0]:
                    ath_sel_bl = ath_strain_baselines.get(sel_ath_soglia, 1500.0)
                    ath_sel_warn = ath_sel_bl * 1.5
                    fig_stress.add_hline(y=ath_sel_bl, line_dash="dot", line_color="#0284c7", line_width=1.5,
                                        annotation_text=f"Baseline {sel_ath_soglia} ({int(round(ath_sel_bl)):,} AU)".replace(",", "."),
                                        annotation_position="bottom left", annotation_font_size=10, annotation_font_color="#0284c7")
                    fig_stress.add_hline(y=ath_sel_warn, line_dash="dash", line_color="#ef4444", line_width=1.8,
                                        annotation_text=f"Soglia Allarme {sel_ath_soglia} (+50%: {int(round(ath_sel_warn)):,} AU)".replace(",", "."),
                                        annotation_position="top left", annotation_font_size=10, annotation_font_color="#b91c1c")
                all_strains = [r['strain'] for records in ath_stress_data.values() for r in records]
                y_max_plot = max(max(all_strains) if all_strains else 1000.0, 1500.0) * 1.15
                fig_stress.update_layout(yaxis=dict(range=[0, y_max_plot]))

            fig_stress.update_layout(
                height=420,
                margin=dict(l=40, r=20, t=32, b=40),
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                xaxis=dict(
                    tickfont=dict(size=12, color='#0f172a', family='Inter', weight='bold'),
                    showgrid=True,
                    gridcolor='#f1f5f9',
                    linecolor='#cbd5e1'
                ),
                yaxis=dict(
                    tickfont=dict(size=11, color='#64748b', family='Inter'),
                    showgrid=True,
                    gridcolor='#f1f5f9',
                    linecolor='#cbd5e1'
                ),
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.20,
                    xanchor="center",
                    x=0.5,
                    font=dict(size=11, color='#0f172a', family='Inter')
                )
            )

            opzioni_pdf_stress = {
                f"Report Stress Roster — {metric_name}": "Stress_Roster"
            }
            render_action_bar(
                meta_items=[
                    (tr("Metrica Attiva", "Active Metric"), metric_name),
                    (tr("Base Carico", "Workload Base"), col_carico_st),
                    (tr("Settimana Rif.", "Ref Week"), clean_w_st),
                    (tr("Roster", "Roster"), f"{len(roster_stress_totale)} {tr('Atleti', 'Athletes')}"),
                ],
                pdf_options=opzioni_pdf_stress,
                pdf_key=f"pdf_stress_{metric_key}_{slugify_name(col_carico_st)}_{slugify_name(clean_w_st)}",
                generate_fn=lambda _: crea_pdf_medie_m0v3(
                    "stress_roster_8w",
                    fig=fig_stress,
                    metric_name=metric_name,
                    col_carico=col_carico_st,
                    clean_w=clean_w_st,
                    ath_stress_data=ath_stress_data,
                    weeks_8=weeks_8,
                    roster=roster_stress_totale,
                    metric_key=metric_key,
                    ath_strain_baselines=ath_strain_baselines
                ),
                filename_fn=lambda _: f"M0V3_Stress_Roster_8W_{slugify_name(metric_name)}_{slugify_name(col_carico_st)}_{slugify_name(clean_w_st)}.pdf"
            )

            st.html(
                f"<div style='border:1px solid #cbd5e1; border-radius:12px; overflow:hidden; margin-top:14px; margin-bottom:24px; box-shadow:0 3px 10px rgba(15,23,42,0.04); font-family:\"Inter\",sans-serif;'>"
                f"<div style='background:#0f172a; padding:12px 18px; display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #1e293b;'>"
                f"<div style='display:flex; align-items:center; gap:10px;'>"
                f"<span style='color:#38bdf8; font-size:13px; font-weight:900; letter-spacing:0.06em; text-transform:uppercase;'>CURVE LONGITUDINALI 8 SETTIMANE — {metric_name}</span>"
                f"</div>"
                f"<span style='background:rgba(255,255,255,0.08); color:#f8fafc; font-size:11px; font-weight:700; padding:4px 10px; border-radius:6px; border:1px solid rgba(255,255,255,0.15);'>{clean_w_st}</span>"
                f"</div>"
                f"<div style='background:#ffffff; padding:12px 16px 6px 16px;'>"
            )
            st.plotly_chart(fig_stress, use_container_width=True, key="fig_stress_roster_8w")
            st.html("</div></div>")

            # Tabella Matrice a 8 Settimane
            th_weeks = []
            for w in weeks_8:
                is_last_w = (w['pos'] == 8)
                bg_th = "#0f172a" if is_last_w else "#f8fafc"
                txt_th = "#38bdf8" if is_last_w else "#475569"
                tag_curr = f"<br><span style='font-size:9px; color:#38bdf8; font-weight:800;'>[W8 REF]</span>" if is_last_w else ""
                th_weeks.append(
                    f"<th style='padding:9px 6px; text-align:center; border:1px solid #e2e8f0; font-size:11px; font-weight:800; background:{bg_th}; color:{txt_th}; min-width:70px;'>"
                    f"{w['short']}{tag_curr}"
                    f"</th>"
                )

            table_rows_st = []
            for i, ath in enumerate(roster_stress_totale):
                bg_r = "#fcfdfd" if i % 2 == 0 else "#ffffff"
                records = ath_stress_data[ath]
                y_vals = [r[metric_key] for r in records]
                c_ath = roster_colors[i % len(roster_colors)]

                active_vals = [v for idx_w, v in enumerate(y_vals) if records[idx_w]['has_load'] and v > 0]
                avg_ath = float(np.mean(active_vals)) if active_vals else 0.0

                w8_val = y_vals[-1]
                w7_val = y_vals[-2] if len(y_vals) > 1 else 0.0
                if w8_val > 0 and w7_val > 0:
                    delta_pct = ((w8_val - w7_val) / w7_val) * 100.0
                    if delta_pct > 10:
                        trend_ico = f"<span style='color:#ef4444; font-weight:800; font-size:14px;' title='+{delta_pct:.0f}% vs W7'>↗</span>"
                    elif delta_pct < -10:
                        trend_ico = f"<span style='color:#10b981; font-weight:800; font-size:14px;' title='{delta_pct:.0f}% vs W7'>↘</span>"
                    else:
                        trend_ico = "<span style='color:#64748b; font-weight:800; font-size:14px;' title='Stabile vs W7'>→</span>"
                else:
                    trend_ico = "<span style='color:#cbd5e1;'>-</span>"

                sparkline_html = render_svg_sparkline(y_vals, width=80, height=22, stroke_color=c_ath)

                ath_bl_curr = ath_strain_baselines.get(ath, 1500.0)
                td_weeks = []
                for idx_w, r in enumerate(records):
                    is_last_col = (r['pos'] == 8)
                    bg_td = "rgba(2,132,199,0.03)" if is_last_col else "inherit"
                    b_badge = get_metric_badge(metric_key, r[metric_key], r['has_load'], ath_bl_curr)
                    td_weeks.append(
                        f"<td style='padding:8px 6px; text-align:center; border:1px solid #e2e8f0; background:{bg_td};'>{b_badge}</td>"
                    )

                avg_badge = get_metric_badge(metric_key, avg_ath, len(active_vals) > 0, ath_bl_curr)

                table_rows_st.append(
                    f"<tr style='background:{bg_r}; font-family:\"Inter\",sans-serif;'>"
                    f"<td style='padding:9px 12px; border:1px solid #e2e8f0; font-size:12.5px; font-weight:800; color:#0f172a;'>"
                    f"<span style='display:inline-block; width:8px; height:8px; border-radius:50%; background:{c_ath}; margin-right:8px;'></span>{ath}"
                    f"</td>"
                    f"{''.join(td_weeks)}"
                    f"<td style='padding:8px 8px; text-align:center; border:1px solid #e2e8f0; border-left:2px solid #cbd5e1;'>{avg_badge}</td>"
                    f"<td style='padding:6px 10px; text-align:center; border:1px solid #e2e8f0; white-space:nowrap;'>"
                    f"<div style='display:inline-flex; align-items:center; gap:6px;'>{sparkline_html} {trend_ico}</div>"
                    f"</td>"
                    f"</tr>"
                )

            matrix_table_html = (
                f"<div style='border:1px solid #cbd5e1; border-radius:12px; overflow:hidden; margin-bottom:24px; box-shadow:0 3px 10px rgba(15,23,42,0.04); font-family:\"Inter\",sans-serif;'>"
                f"<div style='background:#0f172a; padding:12px 18px; display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #1e293b;'>"
                f"<div style='display:flex; align-items:center; gap:10px;'>"
                f"<span style='color:#38bdf8; font-size:13px; font-weight:900; letter-spacing:0.06em; text-transform:uppercase;'>MATRICE COMPARATIVA ROSTER (ULTIME 8 SETTIMANE)</span>"
                f"</div>"
                f"<span style='background:rgba(255,255,255,0.08); color:#f8fafc; font-size:11px; font-weight:700; padding:4px 10px; border-radius:6px; border:1px solid rgba(255,255,255,0.15);'>{len(roster_stress_totale)} {tr('Atleti Monitorati', 'Monitored Athletes')}</span>"
                f"</div>"
                f"<div style='overflow-x:auto; background:#ffffff;'>"
                f"<table style='width:100%; border-collapse:collapse;'>"
                f"<thead>"
                f"<tr style='background:#f8fafc;'>"
                f"<th style='padding:10px 14px; text-align:left; border:1px solid #e2e8f0; font-size:11px; font-weight:800; color:#475569; text-transform:uppercase; letter-spacing:0.05em; width:18%;'>ATLETA</th>"
                f"{''.join(th_weeks)}"
                f"<th style='padding:10px 8px; text-align:center; border:1px solid #e2e8f0; border-left:2px solid #cbd5e1; font-size:11px; font-weight:800; color:#0f172a; text-transform:uppercase; letter-spacing:0.05em; width:9%;'>MEDIA 8W</th>"
                f"<th style='padding:10px 8px; text-align:center; border:1px solid #e2e8f0; font-size:11px; font-weight:800; color:#0f172a; text-transform:uppercase; letter-spacing:0.05em; width:13%;'>TREND 8W</th>"
                f"</tr>"
                f"</thead>"
                f"<tbody>"
                f"{''.join(table_rows_st)}"
                f"</tbody>"
                f"</table>"
                f"</div>"
                f"<div style='background:#f8fafc; border-top:1px solid #e2e8f0; padding:10px 18px; font-size:11px; color:#475569; display:flex; flex-wrap:wrap; gap:18px; align-items:center;'>"
                f"<span><b style='color:#0f172a;'>LEGENDA ZONE:</b></span>"
                f"<span><span style='background:#e0f2fe; color:#0284c7; border:1px solid #bae6fd; font-weight:800; padding:1px 6px; border-radius:4px;'>&lt;0.80</span> Scarico / Underload</span>"
                f"<span><span style='background:#dcfce7; color:#15803d; border:1px solid #bbf7d0; font-weight:800; padding:1px 6px; border-radius:4px;'>0.80 - 1.30</span> Sweet Spot (Ottimale)</span>"
                f"<span><span style='background:#fef3c7; color:#b45309; border:1px solid #fde68a; font-weight:800; padding:1px 6px; border-radius:4px;'>1.31 - 1.50</span> Attenzione / Elevato</span>"
                f"<span><span style='background:#fee2e2; color:#b91c1c; border:1px solid #fecaca; font-weight:800; padding:1px 6px; border-radius:4px;'>&gt;1.50</span> Danger Zone / Allarme</span>"
                f"<span style='margin-left:auto;'><i class='bi bi-info-circle' style='color:#0284c7; margin-right:4px;'></i>Monotonia Foster soglia &gt;2.0 | Base: <b>{col_carico_st}</b></span>"
                f"</div>"
                f"</div>"
            )
            st.html(matrix_table_html)






