import os
import re
import secrets
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
    render_meta_bar,
    render_action_bar,
    render_print_header,
    render_tab_navigation,
    render_scientific_methodology_box,
)
from utils import (
    supabase,
    supabase_admin,
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
    render_delta_bar,
    riepilogo_match,
    acwr_pre_match,
    calcola_blocchi_baseline,
    calcola_work_rate_acwr,
    render_acwr_executive_block,
    acwr_zone_meta,
    render_pct_progress_bar,
    render_athlete_hero_strip,
    render_pct_badge_cell,
    render_executive_hexagon_profile,
    render_executive_bands_section,
    render_executive_chart_header,
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
)

def render_analisi_match(t):
    render_page_header(
        tr("Analisi Match", "Match Analysis"),
        tr("Seleziona i parametri per analizzare le prestazioni della partita rispetto alle medie storiche.", "Select parameters to analyze match performance against historical averages."),
        "MATCH PERFORMANCE"
    )
    
    df_storico = load_local_database()
    if df_storico.empty: st.warning(t['am_no_db']); return

    if st.session_state['role'] != 'Super-Admin':
        atleti_consentiti = get_atleti_associati(st.session_state['user'].id)
        if not atleti_consentiti: st.warning(t['up_no_atl']); return
        df_storico = df_storico[df_storico['Players'].isin(atleti_consentiti)]
        if df_storico.empty: st.warning(t['gen_no_data']); return

    df_match = df_storico[df_storico['Tipologia Sessione'].astype(str).str.strip().str.lower().isin(['match', 'match doppio'])].copy()
    if df_match.empty: st.warning(t['am_no_match']); return

    giocatori_disponibili = df_match['Players'].unique().tolist()
    if not giocatori_disponibili:
        st.warning(t['am_no_match'])
        return

    glob_ath = st.session_state.get('selected_athlete')
    if glob_ath in giocatori_disponibili:
        giocatore_selezionato = glob_ath
    elif 'am_sel_player' in st.session_state and st.session_state['am_sel_player'] in giocatori_disponibili:
        giocatore_selezionato = st.session_state['am_sel_player']
    else:
        giocatore_selezionato = giocatori_disponibili[0]
    st.session_state['am_sel_player'] = giocatore_selezionato

    df_match_ply = df_match[df_match['Players'] == giocatore_selezionato].copy()
    if 'Date_obj' not in df_match_ply.columns or df_match_ply['Date_obj'].isna().all():
        df_match_ply['Date_obj'] = pd.to_datetime(df_match_ply['Date'], format='%d/%m/%Y', errors='coerce')
    # Ordina cronologicamente dal più recente al più datato (most recent first)
    df_match_ply = df_match_ply.sort_values(by=['Date_obj', 'Minuti'], ascending=[False, False])
    sessioni_disponibili = df_match_ply['Session'].unique().tolist()

    if not sessioni_disponibili:
        st.warning(t['am_no_data_ply'])
        return

    if 'am_sel_session' not in st.session_state or st.session_state['am_sel_session'] not in sessioni_disponibili:
        st.session_state['am_sel_session'] = sessioni_disponibili[0]

    st.markdown(f'<h3 class="no-print" style="margin-top:0px;">{t["am_filters"]}</h3>', unsafe_allow_html=True)
    col_f1, col_f2 = st.columns([1.5, 1.2])

    sim_map_match = {
        s_k: bool(df_match_ply[df_match_ply['Session'] == s_k]['Dato_Simulato'].iloc[0])
        for s_k in sessioni_disponibili
    }
    date_map_match = {
        s_k: str(df_match_ply[df_match_ply['Session'] == s_k]['Date'].iloc[0])
        for s_k in sessioni_disponibili
    }

    tipo_map_match = {
        s_k: str(df_match_ply[df_match_ply['Session'] == s_k]['Tipologia Sessione'].iloc[0]).strip()
        for s_k in sessioni_disponibili
    }

    def _format_match_item(s_k):
        d_str = date_map_match.get(s_k, '')
        tipo_k = tipo_map_match.get(s_k, 'Match').title()
        badge_tipo = " [Doppio]" if "doppio" in tipo_k.lower() else " [Singolo]"
        s_tag = " [SIMULATO]" if sim_map_match.get(s_k, False) else ""
        if s_k.startswith(d_str.replace('/', '_')) or s_k.startswith(d_str):
            return f"{s_k}{badge_tipo}{s_tag}"
        return f"{d_str} — {s_k}{badge_tipo}{s_tag}" if d_str else f"{s_k}{badge_tipo}{s_tag}"

    with col_f1: 
        sessione_selezionata = st.selectbox(
            t['am_sel_match'], 
            sessioni_disponibili, 
            index=sessioni_disponibili.index(st.session_state['am_sel_session']),
            format_func=_format_match_item,
            key="widget_session_match"
        )
    st.session_state['am_sel_session'] = sessione_selezionata

    superfici_disponibili = sorted([
        str(s).strip() for s in df_match_ply['Tipologia Campo'].dropna().unique()
        if str(s).strip() and str(s).lower() not in ['nan', '0', 'n/d']
    ])
    lbl_all_sup = tr("Tutte le Superfici", "All Surfaces")
    opzioni_sup = [lbl_all_sup] + superfici_disponibili
    with col_f2:
        filtro_superficie = st.selectbox(
            tr("Filtro Medie Superficie", "Surface Avg Filter"),
            opzioni_sup,
            index=0,
            key="widget_surface_match"
        )

    dati_sessione = df_match_ply[df_match_ply['Session'] == sessione_selezionata]
    if dati_sessione.empty: st.error(t['am_no_data_ply']); return
        
    dati_sessione = dati_sessione.iloc[0].fillna(0)
    is_sim_match = bool(dati_sessione.get('Dato_Simulato', False))
    tipo_sess_corrente = str(dati_sessione.get('Tipologia Sessione', 'Match')).strip().lower()
    is_match_doppio = ('doppio' in tipo_sess_corrente)
    lbl_disciplina = "Match Doppio" if is_match_doppio else "Match Singolo"

    # CONFRONTO COERENTE: Se la sessione e' Doppio confronta con media Match Doppio (Reali);
    # se e' Singolo confronta con media Match Singolo (Reali)
    df_match_reale_tipo = df_match_ply[
        (df_match_ply['Dato_Simulato'] == False) &
        (df_match_ply['Tipologia Sessione'].astype(str).str.strip().str.lower() == tipo_sess_corrente)
    ].copy()

    if df_match_reale_tipo.empty:
        df_match_reale = df_match_ply[df_match_ply['Tipologia Sessione'].astype(str).str.strip().str.lower() == tipo_sess_corrente].copy()
        if df_match_reale.empty:
            df_match_reale = df_match_ply.copy()
    else:
        df_match_reale = df_match_reale_tipo

    col_num_std = [c for c in COLONNE_STANDARD if c not in ["Date", "Session", "Players"]]
    for c_s in col_num_std:
        if c_s in df_match_reale.columns:
            df_match_reale[c_s] = pd.to_numeric(df_match_reale[c_s], errors='coerce').fillna(0.0)

    # Filtraggio su superficie per le medie storiche di riferimento
    if filtro_superficie != lbl_all_sup:
        df_match_reale_ref = df_match_reale[df_match_reale['Tipologia Campo'].astype(str).str.strip().str.lower() == filtro_superficie.strip().lower()].copy()
        if df_match_reale_ref.empty:
            df_match_reale_ref = df_match_reale.copy()
    else:
        df_match_reale_ref = df_match_reale.copy()

    df_match_gps = df_match_reale_ref[df_match_reale_ref['Ambiente'].astype(str).str.lower() != 'indoor'].copy()
    
    medie_storiche = df_match_reale_ref.mean(numeric_only=True).fillna(0)
    medie_storiche_gps = df_match_gps.mean(numeric_only=True).fillna(0) if not df_match_gps.empty else pd.Series(0.0, index=medie_storiche.index)

    # Striscia Compatta Identità Atleta MOV3 con tag match e confronto media coerente
    sim_tag = f"[{tr('SIMULATO', 'SIMULATED')}]" if sim_map_match.get(sessione_selezionata, False) else ""
    lbl_m_tag = f"{lbl_disciplina}: {sessione_selezionata} {sim_tag}".strip()
    extra_badges_m = [
        lbl_m_tag,
        f"{tr('Confronto', 'Benchmark')}: Media {lbl_disciplina} (Reale, N={len(df_match_reale_ref)})"
    ]
    if filtro_superficie != lbl_all_sup:
        extra_badges_m.append(f"{tr('Filtro Superficie', 'Surface Filter')}: {filtro_superficie}")
    render_athlete_hero_strip(giocatore_selezionato, df_atleta=df_match_ply, extra_badges=extra_badges_m)
    
    campo = dati_sessione.get('Tipologia Campo', 'N/D')
    ambiente = dati_sessione.get('Ambiente', 'N/D')
    sparring = dati_sessione.get('Minuti Sparring', 0)
    data_match = dati_sessione.get('Date', 'N/D')
    
    if pd.isna(campo) or str(campo).lower() == 'nan' or campo == 0: campo = "N/D"
    if pd.isna(ambiente) or str(ambiente).lower() == 'nan' or ambiente == 0: ambiente = "N/D"
    if pd.isna(sparring): sparring = 0
    
    if is_sim_match:
        st.warning(t['am_sim_alert'])

    meta_items_match = [
        (tr("Disciplina", "Discipline"), lbl_disciplina),
        (tr("Superficie", "Surface"), campo),
        (tr("Ambiente", "Environment"), ambiente),
        ("Sparring", f"{sparring} min"),
        (tr("Data", "Date"), data_match),
    ]
    if is_sim_match:
        meta_items_match.append((tr("Origine Dato", "Data Source"), "SIMULATO", True))

    opzioni_sub_match = {
        tr("Tutte le Sottoaree (Completo)", "All Sections (Full Report)"): "Tutte",
        tr("1. Sintesi & Delta", "1. Summary & Delta"): "Sintesi_Delta",
        tr("2. Carico Energetico", "2. Energy Load"): "Carico_Energetico",
        tr("3. Dati Meccanici & GPS", "3. Mechanical & GPS Data"): "Dati_Meccanici_GPS",
        tr("4. Readiness (Acuto/Cronico)", "4. Readiness (Acute/Chronic)"): "Readiness"
    }
    render_action_bar(
        meta_items=meta_items_match,
        pdf_options=opzioni_sub_match,
        pdf_key="match",
        generate_fn=lambda codice_sub_m: crea_pdf_m0v3(
            giocatore_selezionato, data_match, sessione_selezionata, campo, ambiente, sparring,
            dati_sessione, medie_storiche, medie_storiche_gps, df_storico=df_storico, sottoarea=codice_sub_m
        ),
        filename_fn=lambda codice_sub_m: f"M0V3_Match_{codice_sub_m}_{slugify_name(giocatore_selezionato)}_{str(data_match).replace('/', '-')}.pdf",
    )

    if st.session_state['role'] == 'Super-Admin': report_abilitati = CATALOGO_REPORT["Analisi Match"]
    else:
        try:
            res_rep = supabase.table('moduli_report').select('nome_report').eq('profilo_id', st.session_state['user'].id).eq('area', 'Analisi Match').execute()
            report_abilitati = [r['nome_report'] for r in res_rep.data] if res_rep.data else []
        except: report_abilitati = []

    is_first_report = True
    # --- RIEPILOGO IN CIMA: card + frase automatica ---
    if "Distance from the average" in report_abilitati:
        mostra_acwr = "2 Days Before the Match (Acute)" in report_abilitati
        r_vol, r_int, r_den = riepilogo_match(dati_sessione, medie_storiche)
        r_acwr = acwr_pre_match(df_storico, giocatore_selezionato, data_match, giorni=2) if mostra_acwr else None

        cols_k = st.columns(4 if mostra_acwr else 3)
        with cols_k[0]:
            st.markdown(card_kpi(tr("Volume", "Volume"), formatta_delta(r_vol, size=30), tr("Tempo, Training Load, azioni intense", "Duration, Training Load, intense actions"), "#0ea5e9"), unsafe_allow_html=True)
        with cols_k[1]:
            st.markdown(card_kpi(tr("Intensità", "Intensity"), formatta_delta(r_int, size=30), tr("TL High, accelerazioni, decelerazioni", "TL High, accelerations, decelerations"), "#ef4444"), unsafe_allow_html=True)
        with cols_k[2]:
            st.markdown(card_kpi("Work Rate", formatta_delta(r_den, size=30), tr("Carico e azioni al minuto", "Load and actions per minute"), "#f59e0b"), unsafe_allow_html=True)
        if mostra_acwr:
            with cols_k[3]:
                if r_acwr is None:
                    val_html = "<span style='color:#94a3b8; font-size:26px; font-weight:800;'>N/D</span>"
                    sub = tr("Storico insufficiente", "Insufficient history")
                    accento = "#94a3b8"
                else:
                    testo_s, bg_s, fg_s = stato_acwr(r_acwr)
                    val_html = f"<span style='background:{bg_s}; color:{fg_s}; padding:3px 12px; border-radius:20px; font-size:24px; font-weight:900;'>{r_acwr:.0f}%</span>"
                    sub = f"{tr('Carico acuto 2 gg', '2-day acute load')}: {testo_s}"
                    accento = fg_s
                st.markdown(card_kpi("Readiness", val_html, sub, accento), unsafe_allow_html=True)

        st.markdown(
            f"<div style='background:#f0f9ff; border:1px solid #bae6fd; border-radius:10px; padding:12px 16px; margin:14px 0 22px 0; color:#0f172a; font-size:15px;'>{frase_riepilogo(r_vol, r_int, r_den, r_acwr)}</div>",
            unsafe_allow_html=True
        )
    # --- TABS DI NAVIGAZIONE (PERSISTENTI & REATTIVI M0V3) ---
    T_SINTESI = tr("Sintesi & Delta", "Summary & Delta")
    T_ENERGIA = tr("Carico Energetico", "Energy Load")
    T_MECC = tr("Dati Meccanici & GPS", "Mechanical & GPS Data")
    T_READINESS = tr("Readiness (Acuto/Cronico)", "Readiness (Acute/Chronic)")

    match_tabs = [T_SINTESI, T_ENERGIA, T_MECC, T_READINESS]
    active_match_tab = render_tab_navigation(match_tabs, key="nav_analisi_match")

    # =========================================================================
    # TAB 1: SINTESI & DELTA (Infografica + Distance from average)
    # =========================================================================
    if active_match_tab == T_SINTESI:
        if "Distance from the average" in report_abilitati:
            render_print_header(is_first_report, giocatore_selezionato, data_match, sessione_selezionata, campo, ambiente, sparring)
            is_first_report = False
            
            st.markdown(f"<h3 style='color:#0f172a; margin-bottom: 20px;'>{tr('Scostamento dalle Medie Match', 'Distance from Match Averages')}</h3>", unsafe_allow_html=True)
            
            cur_min = get_val(dati_sessione, 'Minuti')
            cur_tl = get_val(dati_sessione, 'Training Load')
            cur_az2 = get_val(dati_sessione, 'Azioni Int. IMU >2')
            
            cur_tlh = get_val(dati_sessione, 'TL_High')
            cur_acc = get_val(dati_sessione, 'High Accel IMU')
            cur_dec = get_val(dati_sessione, 'High Decel IMU')
            
            avg_min = get_val(medie_storiche, 'Minuti')
            avg_tl = get_val(medie_storiche, 'Training Load')
            avg_az2 = get_val(medie_storiche, 'Azioni Int. IMU >2')
            
            avg_tlh = get_val(medie_storiche, 'TL_High')
            avg_acc = get_val(medie_storiche, 'High Accel IMU')
            avg_dec = get_val(medie_storiche, 'High Decel IMU')
            
            def calc_pm(val, mins): return val / mins if mins > 0 else 0
            
            cur_tl_pm, cur_acc_pm, cur_dec_pm, cur_tlh_pm, cur_az2_pm = calc_pm(cur_tl, cur_min), calc_pm(cur_acc, cur_min), calc_pm(cur_dec, cur_min), calc_pm(cur_tlh, cur_min), calc_pm(cur_az2, cur_min)
            avg_tl_pm, avg_acc_pm, avg_dec_pm, avg_tlh_pm, avg_az2_pm = calc_pm(avg_tl, avg_min), calc_pm(avg_acc, avg_min), calc_pm(avg_dec, avg_min), calc_pm(avg_tlh, avg_min), calc_pm(avg_az2, avg_min)
            
            p_min, p_tl, p_az2 = calcola_delta_percentuale(cur_min, avg_min), calcola_delta_percentuale(cur_tl, avg_tl), calcola_delta_percentuale(cur_az2, avg_az2)
            p_tlh, p_acc, p_dec = calcola_delta_percentuale(cur_tlh, avg_tlh), calcola_delta_percentuale(cur_acc, avg_acc), calcola_delta_percentuale(cur_dec, avg_dec)
            p_tl_pm, p_acc_pm, p_dec_pm = calcola_delta_percentuale(cur_tl_pm, avg_tl_pm), calcola_delta_percentuale(cur_acc_pm, avg_acc_pm), calcola_delta_percentuale(cur_dec_pm, avg_dec_pm)
            p_tlh_pm, p_az2_pm = calcola_delta_percentuale(cur_tlh_pm, avg_tlh_pm), calcola_delta_percentuale(cur_az2_pm, avg_az2_pm)
            
            avg_vol = (p_min + p_tl + p_az2) / 3
            avg_int = (p_tlh + p_acc + p_dec) / 3
            avg_den = (p_tl_pm + p_acc_pm + p_dec_pm + p_tlh_pm + p_az2_pm) / 5

            lbl_vs_m = tr("vs media match", "vs match avg")

            def riga_stat_exec(label, cat_tag, cat_fg, cat_bg, val_c, val_m, decimals, diff_pct):
                val_c_str = f"{val_c:.{decimals}f}".replace('.', ',')
                val_m_str = f"{val_m:.{decimals}f}".replace('.', ',')
                has_r = val_m > 0
                pct_v = (val_c / val_m * 100.0) if has_r else 0.0
                return (
                    "<tr style='border-bottom: 1px solid #f1f5f9;'>"
                    "<td style='padding: 13px 14px;'>"
                    f"<div style='font-weight: 700; color: #0f172a; font-size: 14px;'>{label}</div>"
                    f"<span style='display:inline-block; margin-top:3px; background:{cat_bg}; color:{cat_fg}; font-size:9px; font-weight:800; padding:2px 7px; border-radius:4px; letter-spacing:0.5px;'>{cat_tag}</span>"
                    "</td>"
                    f"<td style='padding: 13px 14px; text-align: center; font-weight: 900; font-size: 19px; color: #0f172a;'>{val_c_str}</td>"
                    f"<td style='padding: 13px 14px; text-align: center; font-weight: 700; font-size: 16px; color: #64748b;'>{val_m_str}</td>"
                    f"<td style='padding: 13px 14px; text-align: center;'>{render_pct_badge_cell(pct_v, diff_pct, has_r, lbl_vs_m)}</td>"
                    f"<td style='padding: 13px 14px;'>{render_pct_progress_bar(pct_v)}</td>"
                    "</tr>"
                )

            def riga_sunto_exec(label, avg_diff_pct, color):
                pct_tot = max(0.0, 100.0 + avg_diff_pct)
                return (
                    "<tr style='background-color: #f8fafc; border-top: 1px solid #e2e8f0; border-bottom: 2px solid #e2e8f0;'>"
                    f"<td colspan='3' style='padding: 14px 14px; font-weight: 800; color: {color}; text-transform: uppercase; font-size: 12px; letter-spacing: 0.6px; border-left: 4px solid {color};'>{label}</td>"
                    f"<td style='padding: 14px 14px; text-align: center;'>{render_pct_badge_cell(pct_tot, avg_diff_pct, True, lbl_vs_m)}</td>"
                    f"<td style='padding: 14px 14px;'>{render_pct_progress_bar(pct_tot, color)}</td>"
                    "</tr>"
                )

            lbl_bn_match = tr("EXECUTIVE MATCH REPORT — CONFRONTO VS MEDIA STORICA MATCH", "EXECUTIVE MATCH REPORT — COMPARISON VS HISTORICAL MATCH AVERAGE")
            html_table = (
                "<div style='background: white; border-radius: 12px; border: 1px solid #e2e8f0; overflow: hidden; box-shadow: 0 2px 6px -1px rgba(15,23,42,0.04); margin-bottom: 22px; font-family: \"Inter\", sans-serif;'>"
                "<div style='background:#0f172a; border-bottom:2px solid #0ea5e9; padding:13px 18px; display:flex; justify-content:space-between; align-items:center;'>"
                f"<span style='color:white; font-weight:900; font-size:14px; text-transform:uppercase; letter-spacing:0.8px;'>{lbl_bn_match}</span>"
                f"<span style='background:rgba(255,255,255,0.1); color:#38bdf8; font-size:11px; font-weight:800; padding:4px 10px; border-radius:6px;'>{data_match} · {sessione_selezionata}</span>"
                "</div>"
                "<table style='width: 100%; border-collapse: collapse;'>"
                "<tr style='background-color: #f8fafc; border-bottom: 2px solid #e2e8f0;'>"
                f"<th style='text-align: left; padding: 12px 14px; font-size: 11px; font-weight: 700; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; width:28%;'>{tr('Parametro & Area', 'Parameter & Area')}</th>"
                f"<th style='text-align: center; padding: 12px 14px; font-size: 11px; font-weight: 700; color: #0f172a; text-transform: uppercase; letter-spacing: 0.5px; width:16%;'>{tr('Valore Match', 'Match Score')}</th>"
                f"<th style='text-align: center; padding: 12px 14px; font-size: 11px; font-weight: 700; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; width:16%;'>{tr('Media Match', 'Match Avg')}</th>"
                f"<th style='text-align: center; padding: 12px 14px; font-size: 11px; font-weight: 800; color: #0ea5e9; text-transform: uppercase; letter-spacing: 0.5px; width:22%;'>{tr('% Raggiunta (Scostamento)', 'Percentage Reached (Delta)')}</th>"
                f"<th style='text-align: center; padding: 12px 14px; font-size: 11px; font-weight: 700; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; width:18%;'>{tr('Fascia (Tacca = 100%)', 'Zone (Tick = 100%)')}</th>"
                "</tr>"
            )

            html_table += riga_stat_exec(tr("Durata (min)", "Time (min)"), "VOLUME", "#0284c7", "#e0f2fe", cur_min, avg_min, 0, p_min)
            html_table += riga_stat_exec("Training Load", "VOLUME", "#0284c7", "#e0f2fe", cur_tl, avg_tl, 0, p_tl)
            html_table += riga_stat_exec(tr('Azioni Intense >2"', 'Intense Actions >2"'), "VOLUME", "#0284c7", "#e0f2fe", cur_az2, avg_az2, 0, p_az2)
            html_table += riga_sunto_exec(tr("Sintesi Volume Generale", "Total General Volume Achievement"), avg_vol, "#0ea5e9")
            html_table += "<tr><td colspan='5' style='height: 10px; border:none;'></td></tr>"
            html_table += riga_stat_exec("Training Load High", "HIGH INTENSITY", "#dc2626", "#fee2e2", cur_tlh, avg_tlh, 0, p_tlh)
            html_table += riga_stat_exec(tr("Accelerazioni Alta Int.", "High Acc Events"), "HIGH INTENSITY", "#dc2626", "#fee2e2", cur_acc, avg_acc, 0, p_acc)
            html_table += riga_stat_exec(tr("Decelerazioni Alta Int.", "High Dec Events"), "HIGH INTENSITY", "#dc2626", "#fee2e2", cur_dec, avg_dec, 0, p_dec)
            html_table += riga_sunto_exec(tr("Sintesi Volume Alta Intensità", "Total High Intensity Volume Achievement"), avg_int, "#ef4444")
            html_table += "<tr><td colspan='5' style='height: 10px; border:none;'></td></tr>"
            html_table += riga_stat_exec("TL / min", "WORK RATE", "#b45309", "#fef3c7", cur_tl_pm, avg_tl_pm, 1, p_tl_pm)
            html_table += riga_stat_exec("High Acc / min", "WORK RATE", "#b45309", "#fef3c7", cur_acc_pm, avg_acc_pm, 1, p_acc_pm)
            html_table += riga_stat_exec("High Dec / min", "WORK RATE", "#b45309", "#fef3c7", cur_dec_pm, avg_dec_pm, 1, p_dec_pm)
            html_table += riga_stat_exec("TL High / min", "WORK RATE", "#b45309", "#fef3c7", cur_tlh_pm, avg_tlh_pm, 1, p_tlh_pm)
            html_table += riga_stat_exec(tr("Azioni Intense / min", "Intense Actions / min"), "WORK RATE", "#b45309", "#fef3c7", cur_az2_pm, avg_az2_pm, 1, p_az2_pm)
            html_table += riga_sunto_exec(tr("Sintesi Work Rate", "Total Work Rate Achievement"), avg_den, "#f59e0b")
            html_table += "</table></div>"
            st.markdown(html_table, unsafe_allow_html=True)

            # Densità Oraria Standardizzata (Normalizzazione su 60 Minuti di Gioco)
            norm_tl_c = (cur_tl / cur_min * 60) if cur_min > 0 else 0
            norm_tl_m = (avg_tl / avg_min * 60) if avg_min > 0 else 0
            d_norm_tl = calcola_delta_percentuale(norm_tl_c, norm_tl_m)

            norm_tlh_c = (cur_tlh / cur_min * 60) if cur_min > 0 else 0
            norm_tlh_m = (avg_tlh / avg_min * 60) if avg_min > 0 else 0
            d_norm_tlh = calcola_delta_percentuale(norm_tlh_c, norm_tlh_m)

            norm_acc_c = (cur_acc / cur_min * 60) if cur_min > 0 else 0
            norm_acc_m = (avg_acc / avg_min * 60) if avg_min > 0 else 0
            d_norm_acc = calcola_delta_percentuale(norm_acc_c, norm_acc_m)

            norm_dec_c = (cur_dec / cur_min * 60) if cur_min > 0 else 0
            norm_dec_m = (avg_dec / avg_min * 60) if avg_min > 0 else 0
            d_norm_dec = calcola_delta_percentuale(norm_dec_c, norm_dec_m)

            norm_az2_c = (cur_az2 / cur_min * 60) if cur_min > 0 else 0
            norm_az2_m = (avg_az2 / avg_min * 60) if avg_min > 0 else 0
            d_norm_az2 = calcola_delta_percentuale(norm_az2_c, norm_az2_m)

            # Dati GPS Outdoor opzionali (Distanza, HML)
            cur_dist = get_val(dati_sessione, 'DISTANCE', 0)
            avg_dist = get_val(medie_storiche_gps, 'DISTANCE', 0)
            norm_dist_c = (cur_dist / cur_min * 60) if cur_min > 0 else 0
            norm_dist_m = (avg_dist / avg_min * 60) if avg_min > 0 else 0
            d_norm_dist = calcola_delta_percentuale(norm_dist_c, norm_dist_m)

            cur_hml = get_val(dati_sessione, 'HML Distance >25.5W', 0)
            avg_hml = get_val(medie_storiche_gps, 'HML Distance >25.5W', 0)
            norm_hml_c = (cur_hml / cur_min * 60) if cur_min > 0 else 0
            norm_hml_m = (avg_hml / avg_min * 60) if avg_min > 0 else 0
            d_norm_hml = calcola_delta_percentuale(norm_hml_c, norm_hml_m)

            def _badge_norm(d_pct):
                sign = "+" if d_pct > 0 else ""
                bg = "#dcfce7" if abs(d_pct) <= 10 else ("#fef3c7" if abs(d_pct) <= 20 else "#fee2e2")
                fg = "#15803d" if abs(d_pct) <= 10 else ("#b45309" if abs(d_pct) <= 20 else "#b91c1c")
                d_str = f"{d_pct:.1f}"
                return f"<span style='background:{bg}; color:{fg}; padding:2px 7px; border-radius:4px; font-weight:800; font-size:11px;'>{sign}{d_str}%</span>"

            b_tl = _badge_norm(d_norm_tl)
            b_tlh = _badge_norm(d_norm_tlh)
            b_acc = _badge_norm(d_norm_acc)
            b_dec = _badge_norm(d_norm_dec)
            b_az2 = _badge_norm(d_norm_az2)
            b_dist = _badge_norm(d_norm_dist)
            b_hml = _badge_norm(d_norm_hml)
            lbl_norm_title = tr('Densità Oraria Standardizzata (Normalizzazione su 60 Minuti di Gioco)', 'Standardized Hourly Density (Normalized to 60 Min of Play)')
            lbl_norm_sub = tr('Consente il confronto oggettivo tra match di durata differente', 'Enables objective comparison across matches of different durations')

            gps_cards_html = ""
            if cur_dist > 0:
                gps_cards_html = f"""
                    <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px 14px;">
                        <div style="font-size: 11px; font-weight: 700; color: #64748b; text-transform: uppercase;">Distanza / 60 min</div>
                        <div style="font-size: 20px; font-weight: 900; color: #0284c7; margin-top: 2px;">{norm_dist_c:.0f} <span style="font-size:12px; font-weight:600; color:#64748b;">m</span></div>
                        <div style="font-size: 11px; color: #64748b; margin-top: 4px;">Media: {norm_dist_m:.0f} m · {b_dist}</div>
                    </div>
                    <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px 14px;">
                        <div style="font-size: 11px; font-weight: 700; color: #64748b; text-transform: uppercase;">HML Dist / 60 min</div>
                        <div style="font-size: 20px; font-weight: 900; color: #b45309; margin-top: 2px;">{norm_hml_c:.0f} <span style="font-size:12px; font-weight:600; color:#64748b;">m</span></div>
                        <div style="font-size: 11px; color: #64748b; margin-top: 4px;">Media: {norm_hml_m:.0f} m · {b_hml}</div>
                    </div>
                """

            st.markdown(f"""
            <div style="background: white; border-radius: 12px; border: 1px solid #e2e8f0; padding: 16px 20px; margin-bottom: 22px; box-shadow: 0 2px 6px -1px rgba(15,23,42,0.04);">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 14px; border-bottom: 1px solid #f1f5f9; padding-bottom: 8px;">
                    <div style="font-weight: 800; font-size: 13px; color: #0f172a; text-transform: uppercase; letter-spacing: 0.6px;">
                        <i class="bi bi-clock-history" style="color: #0284c7; margin-right: 6px;"></i>
                        {lbl_norm_title}
                    </div>
                    <span style="font-size: 11px; color: #64748b; font-weight: 600;">
                        {lbl_norm_sub}
                    </span>
                </div>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px;">
                    <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px 14px;">
                        <div style="font-size: 11px; font-weight: 700; color: #64748b; text-transform: uppercase;">TL / 60 min</div>
                        <div style="font-size: 20px; font-weight: 900; color: #0f172a; margin-top: 2px;">{norm_tl_c:.0f} <span style="font-size:12px; font-weight:600; color:#64748b;">AU</span></div>
                        <div style="font-size: 11px; color: #64748b; margin-top: 4px;">Media: {norm_tl_m:.0f} AU · {b_tl}</div>
                    </div>
                    <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px 14px;">
                        <div style="font-size: 11px; font-weight: 700; color: #64748b; text-transform: uppercase;">TL High / 60 min</div>
                        <div style="font-size: 20px; font-weight: 900; color: #dc2626; margin-top: 2px;">{norm_tlh_c:.0f} <span style="font-size:12px; font-weight:600; color:#64748b;">AU</span></div>
                        <div style="font-size: 11px; color: #64748b; margin-top: 4px;">Media: {norm_tlh_m:.0f} AU · {b_tlh}</div>
                    </div>
                    <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px 14px;">
                        <div style="font-size: 11px; font-weight: 700; color: #64748b; text-transform: uppercase;">High Acc / 60 min</div>
                        <div style="font-size: 20px; font-weight: 900; color: #b45309; margin-top: 2px;">{norm_acc_c:.0f}</div>
                        <div style="font-size: 11px; color: #64748b; margin-top: 4px;">Media: {norm_acc_m:.0f} · {b_acc}</div>
                    </div>
                    <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px 14px;">
                        <div style="font-size: 11px; font-weight: 700; color: #64748b; text-transform: uppercase;">High Dec / 60 min</div>
                        <div style="font-size: 20px; font-weight: 900; color: #b45309; margin-top: 2px;">{norm_dec_c:.0f}</div>
                        <div style="font-size: 11px; color: #64748b; margin-top: 4px;">Media: {norm_dec_m:.0f} · {b_dec}</div>
                    </div>
                    <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px 14px;">
                        <div style="font-size: 11px; font-weight: 700; color: #64748b; text-transform: uppercase;">Azioni Int. / 60 min</div>
                        <div style="font-size: 20px; font-weight: 900; color: #0284c7; margin-top: 2px;">{norm_az2_c:.0f}</div>
                        <div style="font-size: 11px; color: #64748b; margin-top: 4px;">Media: {norm_az2_m:.0f} · {b_az2}</div>
                    </div>
                    {gps_cards_html}
                </div>
            </div>
            """, unsafe_allow_html=True)

            render_executive_hexagon_profile(
                val_cur=dati_sessione,
                val_ref=medie_storiche,
                lbl_ref_legend=tr("Media Storica Match (100%)", "Historical Match Avg (100%)"),
                lbl_vs=lbl_vs_m,
                chart_key=f"hex_match_main_{sessione_selezionata}",
            )

        if "Infografica Delta Match" in report_abilitati:
            st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)
            v_r3_30 = get_val(dati_sessione, 'Recuperi IMU 3-30s'); m_r3_30 = get_val(medie_storiche, 'Recuperi IMU 3-30s')
            v_r30_60 = get_val(dati_sessione, 'Recuperi IMU 30-60s'); m_r30_60 = get_val(medie_storiche, 'Recuperi IMU 30-60s')
            v_r1_5 = get_val(dati_sessione, 'Recuperi IMU 1-5m'); m_r1_5 = get_val(medie_storiche, 'Recuperi IMU 1-5m')

            def _rec_card_exec(lbl_r, sub_r, vc_r, vm_r, acc_c):
                pv_r = (vc_r / vm_r * 100.0) if vm_r > 0 else 0.0
                dv_r = pv_r - 100.0 if vm_r > 0 else 0.0
                z_bg_r, z_fg_r, _, _ = acwr_zone_meta(pv_r)
                d_str_r = f"{dv_r:+.0f}%" if vm_r > 0 else "N/A"
                return (
                    f"<div style='background:white; border:1px solid #e2e8f0; border-top:4px solid {acc_c}; border-radius:10px; padding:16px; box-shadow:0 1px 3px rgba(15,23,42,0.03);'>"
                    "<div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;'>"
                    f"<span style='font-size:12px; font-weight:800; color:#0f172a; text-transform:uppercase;'>{lbl_r}</span>"
                    f"<span style='font-size:10px; font-weight:700; color:#64748b;'>{sub_r}</span>"
                    "</div>"
                    "<div style='display:flex; align-items:baseline; justify-content:space-between; margin-bottom:10px;'>"
                    f"<span style='font-size:28px; font-weight:900; color:#0f172a;'>{vc_r:.0f}</span>"
                    f"<span style='font-size:12px; font-weight:700; color:#64748b;'>{tr('Media', 'Avg')}: {vm_r:.0f}</span>"
                    "</div>"
                    "<div style='display:flex; align-items:center; justify-content:space-between; margin-bottom:8px;'>"
                    f"<span style='background:{z_bg_r}; color:{z_fg_r}; font-size:14px; font-weight:900; padding:3px 9px; border-radius:6px;'>{pv_r:.0f}%</span>"
                    f"<span style='font-size:12px; font-weight:800; color:{z_fg_r};'>({d_str_r})</span>"
                    "</div>"
                    f"{render_pct_progress_bar(pv_r, acc_c)}"
                    "</div>"
                )

            lbl_rec_hdr = tr("FASI DI RECUPERO IMU (RECOVERY PHASES — CONFRONTO VS MEDIA MATCH)", "IMU RECOVERY PHASES (COMPARISON VS MATCH AVERAGE)")
            lbl_rec_sub = tr("Distribuzione pause brevi, medie e lunghe", "Short, medium and long recovery distribution")
            inf_html = (
                "<div style='background:#0f172a; border-bottom:2px solid #10b981; border-radius:12px 12px 0 0; padding:13px 18px; display:flex; justify-content:space-between; align-items:center; font-family:\"Inter\", sans-serif;'>"
                f"<span style='color:white; font-weight:900; font-size:14px; text-transform:uppercase; letter-spacing:0.8px;'>{lbl_rec_hdr}</span>"
                f"<span style='background:rgba(255,255,255,0.1); color:#34d399; font-size:11px; font-weight:800; padding:4px 10px; border-radius:6px;'>{lbl_rec_sub}</span>"
                "</div>"
                "<div style='display:grid; grid-template-columns:repeat(3, 1fr); gap:14px; padding:16px; background:#f8fafc; border:1px solid #e2e8f0; border-top:none; border-radius:0 0 12px 12px; margin-bottom:24px; font-family:\"Inter\", sans-serif;'>"
                + _rec_card_exec('Rec 3" - 30"', tr("Recupero Breve (Tra i punti)", "Short Recovery (Between points)"), v_r3_30, m_r3_30, "#ef4444")
                + _rec_card_exec('Rec 30" - 60"', tr("Recupero Medio", "Medium Recovery"), v_r30_60, m_r30_60, "#f59e0b")
                + _rec_card_exec("Rec 1' - 5'", tr("Cambio Campo / Fine Set", "Changeover / Set Break"), v_r1_5, m_r1_5, "#10b981")
                + "</div>"
            )
            st.markdown(inf_html, unsafe_allow_html=True)

    # =========================================================================
    # TAB 2: CARICO ENERGETICO
    # =========================================================================
    elif active_match_tab == T_ENERGIA:
        if "Training Load Bands" in report_abilitati:
            tl_totale = get_val(dati_sessione, 'Training Load', 0.0)
            val_stand = get_val(dati_sessione, 'TL_Stand', 0.0)
            val_low = get_val(dati_sessione, 'TL_Low', 0.0)
            val_med = get_val(dati_sessione, 'TL_Medium', 0.0)
            val_high = get_val(dati_sessione, 'TL_High', get_val(dati_sessione, 'TL High', 0.0))

            med_stand = get_val(medie_storiche, 'TL_Stand', 0.0)
            med_low = get_val(medie_storiche, 'TL_Low', 0.0)
            med_med = get_val(medie_storiche, 'TL_Medium', 0.0)
            med_high = get_val(medie_storiche, 'TL_High', 0.0)

            bands_tl_match = [
                ("STAND", "TL Stand", val_stand, med_stand, "#64748b", "#f1f5f9"),
                ("LOW", "TL Low", val_low, med_low, "#0ea5e9", "#e0f2fe"),
                ("MEDIUM", "TL Medium", val_med, med_med, "#f59e0b", "#fef3c7"),
                ("HIGH", "TL High", val_high, med_high, "#ef4444", "#fee2e2"),
            ]
            render_executive_bands_section(
                title_banner=tr("FASCE DI CARICO (TRAINING LOAD BANDS)", "TRAINING LOAD BANDS"),
                subtitle_ctx=f"Training Load Totale: {tl_totale:.0f}",
                bands_data=bands_tl_match,
                lbl_cur=tr("Match", "Match"),
                lbl_ref=tr("Media Match", "Match Avg"),
                unit_suffix="",
                chart_key_prefix=f"match_tl_bands_{sessione_selezionata}",
            )

        if "Training Load Time% Bends" in report_abilitati:
            st.markdown("<div style='height: 18px;'></div>", unsafe_allow_html=True)
            val_t_stand = get_val(dati_sessione, 'TL_T_Stand', 0.0); med_t_stand = get_val(medie_storiche, 'TL_T_Stand', 0.0)
            val_t_low = get_val(dati_sessione, 'TL_T_Low', 0.0); med_t_low = get_val(medie_storiche, 'TL_T_Low', 0.0)
            val_t_med = get_val(dati_sessione, 'TL_T_Medium', 0.0); med_t_med = get_val(medie_storiche, 'TL_T_Medium', 0.0)
            val_t_high = get_val(dati_sessione, 'TL_T_High', 0.0); med_t_high = get_val(medie_storiche, 'TL_T_High', 0.0)

            bands_t_match = [
                ("STAND %T", "TL Stand %T", val_t_stand, med_t_stand, "#64748b", "#f1f5f9"),
                ("LOW %T", "TL Low %T", val_t_low, med_t_low, "#0ea5e9", "#e0f2fe"),
                ("MED %T", "TL Medium %T", val_t_med, med_t_med, "#f59e0b", "#fef3c7"),
                ("HIGH %T", "TL High %T", val_t_high, med_t_high, "#ef4444", "#fee2e2"),
            ]
            render_executive_bands_section(
                title_banner=tr("DISTRIBUZIONE % TEMPO IN FASCIA (TIME % BANDS)", "TRAINING LOAD TIME % BANDS"),
                subtitle_ctx=tr("% Tempo sul Totale Sessione", "% Time of Total Session"),
                bands_data=bands_t_match,
                lbl_cur=tr("Match", "Match"),
                lbl_ref=tr("Media Match", "Match Avg"),
                unit_suffix="%",
                chart_key_prefix=f"match_t_bands_{sessione_selezionata}",
            )

    # =========================================================================
    # TAB 3: DATI MECCANICI E GPS
    # =========================================================================
    elif active_match_tab == T_MECC:
        lbl_vs_m3 = tr("vs media match", "vs match avg")
        if "Dati volumetrici IMU" in report_abilitati:
            val_minuti = get_val(dati_sessione, 'Minuti', 0); med_minuti = get_val(medie_storiche, 'Minuti', 0)
            val_pl = get_val(dati_sessione, 'Player Load', 0); med_pl = get_val(medie_storiche, 'Player Load', 0)
            val_tl = get_val(dati_sessione, 'Training Load', 0); med_tl = get_val(medie_storiche, 'Training Load', 0)
            val_acc = get_val(dati_sessione, 'High Accel IMU', 0); med_acc = get_val(medie_storiche, 'High Accel IMU', 0)
            val_dec = get_val(dati_sessione, 'High Decel IMU', 0); med_dec = get_val(medie_storiche, 'High Decel IMU', 0)

            imu_rows_m = [
                (tr("Durata (min)", "Duration (min)"), "IMU VOLUME", "#0284c7", "#e0f2fe", val_minuti, med_minuti, ""),
                ("Player Load", "IMU VOLUME", "#0284c7", "#e0f2fe", val_pl, med_pl, ""),
                ("Training Load", "IMU VOLUME", "#0284c7", "#e0f2fe", val_tl, med_tl, ""),
                ("High Acceleration IMU", "MECHANICAL", "#dc2626", "#fee2e2", val_acc, med_acc, ""),
                ("High Deceleration IMU", "MECHANICAL", "#dc2626", "#fee2e2", val_dec, med_dec, ""),
            ]
            lbl_imu_bn = tr("DATI VOLUMETRICI & MECCANICI IMU — CONFRONTO VS MEDIA MATCH", "IMU VOLUMETRIC & MECHANICAL DATA — COMPARISON VS MATCH AVG")
            html_imu_match = (
                "<div style='background:white; border:1px solid #e2e8f0; border-radius:12px; overflow:hidden; box-shadow:0 2px 6px -1px rgba(15,23,42,0.04); margin-bottom:18px; font-family:\"Inter\", sans-serif;'>"
                "<div style='background:#0f172a; border-bottom:2px solid #0ea5e9; padding:13px 18px; display:flex; justify-content:space-between; align-items:center;'>"
                f"<span style='color:white; font-weight:900; font-size:14px; text-transform:uppercase; letter-spacing:0.8px;'>{lbl_imu_bn}</span>"
                "<span style='background:rgba(255,255,255,0.1); color:#38bdf8; font-size:11px; font-weight:800; padding:4px 10px; border-radius:6px;'>IMU SENSOR</span>"
                "</div>"
                "<table style='width:100%; border-collapse:collapse;'>"
                "<tr style='background:#f8fafc; border-bottom:2px solid #e2e8f0;'>"
                f"<th style='padding:12px 14px; text-align:left; color:#64748b; font-size:11px; font-weight:700; text-transform:uppercase; width:28%;'>{tr('Metrica IMU & Area', 'IMU Metric & Area')}</th>"
                f"<th style='padding:12px 14px; text-align:center; color:#0f172a; font-size:11px; font-weight:700; text-transform:uppercase; width:16%;'>{tr('Valore Match', 'Match Score')}</th>"
                f"<th style='padding:12px 14px; text-align:center; color:#64748b; font-size:11px; font-weight:700; text-transform:uppercase; width:16%;'>{tr('Media Match', 'Match Avg')}</th>"
                f"<th style='padding:12px 14px; text-align:center; color:#0ea5e9; font-size:11px; font-weight:800; text-transform:uppercase; width:22%;'>{tr('% Raggiunta (Scostamento)', 'Percentage Reached (Delta)')}</th>"
                f"<th style='padding:12px 14px; text-align:center; color:#64748b; font-size:11px; font-weight:700; text-transform:uppercase; width:18%;'>{tr('Fascia (Tacca = 100%)', 'Zone (Tick = 100%)')}</th>"
                "</tr>"
            )
            for lbl_i, tag_i, fg_i, bg_i, vc_i, vm_i, suf_i in imu_rows_m:
                has_ri = vm_i > 0
                pv_i = (vc_i / vm_i * 100.0) if has_ri else 0.0
                dv_i = pv_i - 100.0 if has_ri else 0.0
                html_imu_match += (
                    "<tr style='border-bottom:1px solid #f1f5f9;'>"
                    "<td style='padding:13px 14px;'>"
                    f"<div style='font-weight:700; color:#0f172a; font-size:14px;'>{lbl_i}</div>"
                    f"<span style='display:inline-block; margin-top:3px; background:{bg_i}; color:{fg_i}; font-size:9px; font-weight:800; padding:2px 7px; border-radius:4px;'>{tag_i}</span>"
                    "</td>"
                    f"<td style='padding:13px 14px; text-align:center; font-weight:900; font-size:19px; color:#0f172a;'>{vc_i:.0f}{suf_i}</td>"
                    f"<td style='padding:13px 14px; text-align:center; font-weight:700; font-size:16px; color:#64748b;'>{vm_i:.0f}{suf_i}</td>"
                    f"<td style='padding:13px 14px; text-align:center;'>{render_pct_badge_cell(pv_i, dv_i, has_ri, lbl_vs_m3)}</td>"
                    f"<td style='padding:13px 14px;'>{render_pct_progress_bar(pv_i)}</td>"
                    "</tr>"
                )
            html_imu_match += "</table></div>"
            st.markdown(html_imu_match, unsafe_allow_html=True)

            col_g1, col_g2 = st.columns(2, gap="medium")
            with col_g1:
                with st.container(border=True):
                    st.markdown(render_executive_chart_header(tr("Carico Globale (Player Load & Training Load)", "Global Load (Player Load & Training Load)"), accent="#0ea5e9"), unsafe_allow_html=True)
                    fig_load = go.Figure(data=[
                        go.Bar(name=tr('Match', 'Match'), x=['Player Load', 'Training Load'], y=[val_pl, val_tl], marker_color='#0ea5e9', text=[f"{val_pl:.0f}", f"{val_tl:.0f}"], textposition='outside', cliponaxis=False),
                        go.Bar(name=tr('Media Storica', 'Historical Avg'), x=['Player Load', 'Training Load'], y=[med_pl, med_tl], marker_color='#cbd5e1', text=[f"{med_pl:.0f}", f"{med_tl:.0f}"], textposition='outside', cliponaxis=False)
                    ])
                    fig_load.update_layout(height=280, barmode='group', showlegend=False, yaxis=dict(range=[0, max(val_pl, val_tl, med_pl, med_tl, 10)*1.25], gridcolor='#f1f5f9'), margin=dict(l=10, r=10, t=15, b=10), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                    st.plotly_chart(fig_load, use_container_width=True, key=f"m_imu_load_{sessione_selezionata}")
            with col_g2:
                with st.container(border=True):
                    st.markdown(render_executive_chart_header(tr("Eventi Meccanici IMU (Acc & Dec)", "IMU Mechanical Events (Acc & Dec)"), accent="#10b981"), unsafe_allow_html=True)
                    fig_imu = go.Figure(data=[
                        go.Bar(name=tr('Match', 'Match'), x=['High Acc IMU', 'High Dec IMU'], y=[val_acc, val_dec], marker_color='#10b981', text=[f"{val_acc:.0f}", f"{val_dec:.0f}"], textposition='outside', cliponaxis=False),
                        go.Bar(name=tr('Media Storica', 'Historical Avg'), x=['High Acc IMU', 'High Dec IMU'], y=[med_acc, med_dec], marker_color='#cbd5e1', text=[f"{med_acc:.0f}", f"{med_dec:.0f}"], textposition='outside', cliponaxis=False)
                    ])
                    fig_imu.update_layout(height=280, barmode='group', showlegend=False, yaxis=dict(range=[0, max(val_acc, val_dec, med_acc, med_dec, 10)*1.25], gridcolor='#f1f5f9'), margin=dict(l=10, r=10, t=15, b=10), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                    st.plotly_chart(fig_imu, use_container_width=True, key=f"m_imu_mech_{sessione_selezionata}")

        if "Dati GPS" in report_abilitati:
            st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)
            if ambiente == "Indoor":
                st.warning(t['am_indoor_warn'])
            else:
                val_dist = get_val(dati_sessione, 'DISTANCE', 0); med_dist = get_val(medie_storiche_gps, 'DISTANCE', 0)
                val_hml = get_val(dati_sessione, 'HML Distance >25.5W', 0); med_hml = get_val(medie_storiche_gps, 'HML Distance >25.5W', 0)
                val_vhml = get_val(dati_sessione, 'VHML Distance >50W', 0); med_vhml = get_val(medie_storiche_gps, 'VHML Distance >50W', 0)
                val_hdec = get_val(dati_sessione, 'High Dec Events <-3.5 m/s2', 0); med_hdec = get_val(medie_storiche_gps, 'High Dec Events <-3.5 m/s2', 0)
                val_rec = get_val(dati_sessione, 'Recovery Time <5W %', 0); med_rec = get_val(medie_storiche_gps, 'Recovery Time <5W %', 0)
                val_eq_dist = get_val(dati_sessione, 'Equivalent Distance %', 0); med_eq_dist = get_val(medie_storiche_gps, 'Equivalent Distance %', 0)
                val_an_idx = get_val(dati_sessione, 'Anaerobic index %', 0); med_an_idx = get_val(medie_storiche_gps, 'Anaerobic index %', 0)

                gps_rows_m = [
                    ("DISTANCE (m)", "GPS VOLUME", "#0284c7", "#e0f2fe", val_dist, med_dist, " m"),
                    ("HML Distance >25.5W", "GPS METABOLIC", "#b45309", "#fef3c7", val_hml, med_hml, " m"),
                    ("VHML Distance >50W", "GPS HIGH INTENSITY", "#dc2626", "#fee2e2", val_vhml, med_vhml, " m"),
                    ("High Dec Events <-3.5 m/s²", "GPS MECHANICAL", "#dc2626", "#fee2e2", val_hdec, med_hdec, ""),
                    ("Recovery Time <5W %", "METABOLIC INDEX", "#166534", "#dcfce7", val_rec, med_rec, "%"),
                    ("Equivalent Distance %", "METABOLIC INDEX", "#166534", "#dcfce7", val_eq_dist, med_eq_dist, "%"),
                    ("Anaerobic Index %", "METABOLIC INDEX", "#166534", "#dcfce7", val_an_idx, med_an_idx, "%"),
                ]
                lbl_gps_bn = tr("DATI GPS & SATELLITARI OUTDOOR — CONFRONTO VS MEDIA MATCH", "OUTDOOR GPS & SATELLITE DATA — COMPARISON VS MATCH AVG")
                html_gps_match = (
                    "<div style='background:white; border:1px solid #e2e8f0; border-radius:12px; overflow:hidden; box-shadow:0 2px 6px -1px rgba(15,23,42,0.04); margin-bottom:18px; font-family:\"Inter\", sans-serif;'>"
                    "<div style='background:#0f172a; border-bottom:2px solid #f59e0b; padding:13px 18px; display:flex; justify-content:space-between; align-items:center;'>"
                    f"<span style='color:white; font-weight:900; font-size:14px; text-transform:uppercase; letter-spacing:0.8px;'>{lbl_gps_bn}</span>"
                    "<span style='background:rgba(255,255,255,0.1); color:#fbbf24; font-size:11px; font-weight:800; padding:4px 10px; border-radius:6px;'>OUTDOOR GPS</span>"
                    "</div>"
                    "<table style='width:100%; border-collapse:collapse;'>"
                    "<tr style='background:#f8fafc; border-bottom:2px solid #e2e8f0;'>"
                    f"<th style='padding:12px 14px; text-align:left; color:#64748b; font-size:11px; font-weight:700; text-transform:uppercase; width:28%;'>{tr('Metrica GPS & Area', 'GPS Metric & Area')}</th>"
                    f"<th style='padding:12px 14px; text-align:center; color:#0f172a; font-size:11px; font-weight:700; text-transform:uppercase; width:16%;'>{tr('Valore Match', 'Match Score')}</th>"
                    f"<th style='padding:12px 14px; text-align:center; color:#64748b; font-size:11px; font-weight:700; text-transform:uppercase; width:16%;'>{tr('Media Match', 'Match Avg')}</th>"
                    f"<th style='padding:12px 14px; text-align:center; color:#0ea5e9; font-size:11px; font-weight:800; text-transform:uppercase; width:22%;'>{tr('% Raggiunta (Scostamento)', 'Percentage Reached (Delta)')}</th>"
                    f"<th style='padding:12px 14px; text-align:center; color:#64748b; font-size:11px; font-weight:700; text-transform:uppercase; width:18%;'>{tr('Fascia (Tacca = 100%)', 'Zone (Tick = 100%)')}</th>"
                    "</tr>"
                )
                for lbl_g, tag_g, fg_g, bg_g, vc_g, vm_g, suf_g in gps_rows_m:
                    has_rg = vm_g > 0
                    pv_g = (vc_g / vm_g * 100.0) if has_rg else 0.0
                    dv_g = pv_g - 100.0 if has_rg else 0.0
                    html_gps_match += (
                        "<tr style='border-bottom:1px solid #f1f5f9;'>"
                        "<td style='padding:13px 14px;'>"
                        f"<div style='font-weight:700; color:#0f172a; font-size:14px;'>{lbl_g}</div>"
                        f"<span style='display:inline-block; margin-top:3px; background:{bg_g}; color:{fg_g}; font-size:9px; font-weight:800; padding:2px 7px; border-radius:4px;'>{tag_g}</span>"
                        "</td>"
                        f"<td style='padding:13px 14px; text-align:center; font-weight:900; font-size:19px; color:#0f172a;'>{vc_g:.0f}{suf_g}</td>"
                        f"<td style='padding:13px 14px; text-align:center; font-weight:700; font-size:16px; color:#64748b;'>{vm_g:.0f}{suf_g}</td>"
                        f"<td style='padding:13px 14px; text-align:center;'>{render_pct_badge_cell(pv_g, dv_g, has_rg, lbl_vs_m3)}</td>"
                        f"<td style='padding:13px 14px;'>{render_pct_progress_bar(pv_g)}</td>"
                        "</tr>"
                    )
                html_gps_match += "</table></div>"
                st.markdown(html_gps_match, unsafe_allow_html=True)

                with st.container(border=True):
                    st.markdown(render_executive_chart_header(tr("Indici Metabolici e Tempi di Recupero GPS (%)", "GPS Metabolic & Recovery Indices (%)"), accent="#f59e0b"), unsafe_allow_html=True)
                    fig_gps_pct = go.Figure(data=[
                        go.Bar(name=tr('Match', 'Match'), x=['Recovery <5W %', 'Equivalent Dist %', 'Anaerobic Index %'], y=[val_rec, val_eq_dist, val_an_idx], marker_color='#f59e0b', text=[f"{val_rec:.0f}%", f"{val_eq_dist:.0f}%", f"{val_an_idx:.0f}%"], textposition='outside', cliponaxis=False),
                        go.Bar(name=tr('Media Storica', 'Historical Avg'), x=['Recovery <5W %', 'Equivalent Dist %', 'Anaerobic Index %'], y=[med_rec, med_eq_dist, med_an_idx], marker_color='#cbd5e1', text=[f"{med_rec:.0f}%", f"{med_eq_dist:.0f}%", f"{med_an_idx:.0f}%"], textposition='outside', cliponaxis=False)
                    ])
                    fig_gps_pct.update_layout(height=280, barmode='group', showlegend=False, yaxis=dict(range=[0, max(val_rec, val_eq_dist, val_an_idx, med_rec, med_eq_dist, med_an_idx, 10)*1.25], gridcolor='#f1f5f9'), margin=dict(l=10, r=10, t=15, b=10), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                    st.plotly_chart(fig_gps_pct, use_container_width=True, key=f"m_gps_pct_{sessione_selezionata}")

    # =========================================================================
    # TAB 4: READINESS (ACUTO / CRONICO)
    # =========================================================================
    elif active_match_tab == T_READINESS:
        if "2 Days Before the Match (Acute)" in report_abilitati or "7 Days Before the Match (Chronic)" in report_abilitati:
            st.markdown(f"<h3 style='color:#0f172a; margin-bottom:6px;'>{tr('Readiness Pre-Match (Carico Acuto / Cronico)', 'Pre-Match Readiness (Acute / Chronic Load)')}</h3>", unsafe_allow_html=True)
            st.markdown(f"<p style='color:#64748b; font-size:13px; margin-bottom:18px;'>{tr('Valutazione del carico nei 2 giorni (Acuto) e 7 giorni (Cronico) precedenti al match rispetto ai 28 giorni antecedenti.', 'Evaluation of the load in the 2 days (Acute) and 7 days (Chronic) prior to the match compared to the preceding 28-day baseline.')}</p>", unsafe_allow_html=True)
            df_ath_all = df_storico[df_storico['Players'] == giocatore_selezionato].copy()
            df_ath_all['Date_obj'] = pd.to_datetime(df_ath_all['Date'], format="%d/%m/%Y", errors='coerce')

            target_date = pd.to_datetime(data_match, format="%d/%m/%Y", errors='coerce')

            if pd.isna(target_date):
                st.warning(tr("Impossibile generare Acuto e Cronico: la data della sessione non è valida.", "Unable to generate Acute/Chronic: invalid session date."))
            else:
                col_rtm = ['Minuti', 'Training Load', 'TL_High', 'High Decel IMU', 'High Accel IMU', 'Azioni Int. IMU >2']
                for c_r in col_rtm:
                    if c_r not in df_ath_all.columns:
                        df_ath_all[c_r] = 0
                df_ath_all[col_rtm] = df_ath_all[col_rtm].apply(pd.to_numeric, errors='coerce').fillna(0)

                readiness_configs = [
                    (
                        "2 Days Before the Match (Acute)",
                        2,
                        tr("BEFORE MATCH — CARICO ACUTO (2 GIORNI)", "BEFORE MATCH — ACUTE LOAD (2 DAYS)"),
                        "#0f172a",
                        tr("Carico 2 Giorni Pre-Match", "2-Day Pre-Match Load"),
                        tr("Media 28 gg (blocchi 2 gg)", "28d Baseline Avg (2d blocks)"),
                        tr("Finestra Acuta (2 gg pre-match)", "Acute Window (2d pre-match)"),
                        tr("vs media 2 gg", "vs 2d avg"),
                    ),
                    (
                        "7 Days Before the Match (Chronic)",
                        7,
                        tr("BEFORE MATCH — CARICO CRONICO (7 GIORNI)", "BEFORE MATCH — CHRONIC LOAD (7 DAYS)"),
                        "#0ea5e9",
                        tr("Carico 7 Giorni Pre-Match", "7-Day Pre-Match Load"),
                        tr("Media 4 Settimane (28 gg / 7 gg)", "4-Week Baseline Avg (28d / 7d)"),
                        tr("Finestra Settimanale (7 gg pre-match)", "Weekly Window (7d pre-match)"),
                        tr("vs media 7 gg", "vs 7d avg"),
                    ),
                ]

                for report_type, days_window, title_bn, accent_col, lbl_ac_col, lbl_ch_col, lbl_ctx_ac, lbl_vs_txt in readiness_configs:
                    if report_type in report_abilitati:
                        window_start = target_date - timedelta(days=days_window)
                        window_end = target_date - timedelta(days=1)
                        baseline_end = window_start - timedelta(days=1)
                        baseline_start = baseline_end - timedelta(days=27)

                        mask_window = (df_ath_all['Date_obj'] >= window_start) & (df_ath_all['Date_obj'] <= window_end)
                        mask_baseline = (df_ath_all['Date_obj'] >= baseline_start) & (df_ath_all['Date_obj'] <= baseline_end)

                        val_window = df_ath_all[mask_window][col_rtm].sum().fillna(0)
                        df_base = df_ath_all[mask_baseline]

                        blocchi_disponibili = calcola_blocchi_baseline(df_ath_all, baseline_end, days_window)

                        val_avg = (df_base[col_rtm].sum() / blocchi_disponibili).fillna(0) if not df_base.empty else pd.Series(0.0, index=col_rtm)

                        str_win_r = f"{window_start.strftime('%d/%m/%Y')} - {window_end.strftime('%d/%m/%Y')}"
                        str_base_r = f"{baseline_start.strftime('%d/%m/%Y')} - {baseline_end.strftime('%d/%m/%Y')}"

                        render_acwr_executive_block(
                            val_acute=val_window,
                            val_chronic=val_avg,
                            str_win_range=str_win_r,
                            str_base_range=str_base_r,
                            lbl_hdr_acute=lbl_ac_col,
                            lbl_hdr_chronic=lbl_ch_col,
                            lbl_ctx_acute=lbl_ctx_ac,
                            lbl_vs=lbl_vs_txt,
                            chart_key=f"hex_match_readiness_{days_window}_{sessione_selezionata}",
                            title_banner=title_bn,
                            title_accent=accent_col,
                        )
                        st.markdown("<div style='height: 18px;'></div>", unsafe_allow_html=True)

    st.markdown("<div style='margin-top: 30px;'></div>", unsafe_allow_html=True)
    render_scientific_methodology_box("match_per_point")

