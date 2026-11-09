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

def render_analisi_sessione(t):
    render_page_header(
        tr("Analisi Sessione (Non-Match)", "Session Analysis (Training)"),
        tr("Seleziona una sessione di allenamento per analizzarne le prestazioni rispetto alle medie di tipologia e Match.", "Select a training session to analyze performance against session-type and Match averages."),
        "SESSION PERFORMANCE"
    )

    df_completo = load_local_database()
    if df_completo.empty:
        st.warning(t['am_no_db'])
        return
    df_valido = df_completo[df_completo['Tipologia Sessione'].astype(str).str.lower() != 'match'].copy()
    
    if df_valido.empty:
        st.warning(tr("Nessuna sessione di allenamento (Non-Match) disponibile nel database.", "No training sessions (Non-Match) available in the database."))
    else:
        if st.session_state['role'] != 'Super-Admin':
            atleti_consentiti = get_atleti_associati(st.session_state['user'].id)
            if not atleti_consentiti: st.warning(t['up_no_atl']); return
            df_valido = df_valido[df_valido['Players'].isin(atleti_consentiti)]
            if df_valido.empty: st.warning(tr("Nessun dato per i tuoi atleti.", "No data available for your athletes.")); return

        giocatori_disponibili = df_valido['Players'].dropna().unique().tolist()
        glob_ath = st.session_state.get('selected_athlete')
        if glob_ath in giocatori_disponibili:
            giocatore_selezionato = glob_ath
        elif 'as_sel_player' in st.session_state and st.session_state['as_sel_player'] in giocatori_disponibili:
            giocatore_selezionato = st.session_state['as_sel_player']
        else:
            giocatore_selezionato = giocatori_disponibili[0] if giocatori_disponibili else None
            
        st.session_state['as_sel_player'] = giocatore_selezionato

        df_giocatore = df_valido[df_valido['Players'] == giocatore_selezionato].copy()
        if 'Date_obj' not in df_giocatore.columns or df_giocatore['Date_obj'].isna().all():
            df_giocatore['Date_obj'] = pd.to_datetime(df_giocatore['Date'], format='%d/%m/%Y', errors='coerce')
        # Ordina cronologicamente dal più recente al più datato (most recent first)
        df_giocatore = df_giocatore.sort_values(by=['Date_obj', 'Minuti'], ascending=[False, False])
        sessioni_disp = df_giocatore['Session'].unique().tolist()
        
        if 'as_sel_session' not in st.session_state or st.session_state['as_sel_session'] not in sessioni_disp:
            st.session_state['as_sel_session'] = sessioni_disp[0] if sessioni_disp else None

        sim_map_sess = {
            s_k: bool(df_giocatore[df_giocatore['Session'] == s_k]['Dato_Simulato'].iloc[0])
            for s_k in sessioni_disp
        }
        date_map_sess = {
            s_k: str(df_giocatore[df_giocatore['Session'] == s_k]['Date'].iloc[0])
            for s_k in sessioni_disp
        }

        def _format_session_item(s_k):
            d_str = date_map_sess.get(s_k, '')
            s_tag = f" [{tr('SIMULATO', 'SIMULATED')}]" if sim_map_sess.get(s_k, False) else ""
            if s_k.startswith(d_str.replace('/', '_')) or s_k.startswith(d_str):
                return f"{s_k}{s_tag}"
            return f"{d_str} — {s_k}{s_tag}" if d_str else f"{s_k}{s_tag}"

        st.markdown(f'<h3 class="no-print" style="margin-top:0px;">{t["am_filters"]}</h3>', unsafe_allow_html=True)
        idx_sess_def = sessioni_disp.index(st.session_state['as_sel_session']) if st.session_state['as_sel_session'] in sessioni_disp else 0
        sessione_selezionata = st.selectbox(
            tr("Seleziona Sessione", "Select Session"),
            sessioni_disp,
            index=idx_sess_def,
            format_func=_format_session_item,
            key="widget_as_session"
        )
        st.session_state['as_sel_session'] = sessione_selezionata

        # Striscia Compatta Identità Atleta MOV3 con tag sessione
        sim_tag = f"[{tr('SIMULATO', 'SIMULATED')}]" if sim_map_sess.get(sessione_selezionata, False) else ""
        lbl_sess_tag = f"{tr('Sessione', 'Session')}: {sessione_selezionata} {sim_tag}".strip()
        render_athlete_hero_strip(giocatore_selezionato, df_atleta=df_giocatore, extra_badges=[lbl_sess_tag])

        if sessione_selezionata:
            
            if st.session_state['role'] == 'Super-Admin': 
                report_abilitati = CATALOGO_REPORT.get("Analisi Sessione", [])
            else:
                try:
                    res_rep = supabase.table('moduli_report').select('nome_report').eq('profilo_id', st.session_state['user'].id).eq('area', 'Analisi Sessione').execute()
                    report_abilitati = [r['nome_report'] for r in res_rep.data] if res_rep.data else []
                except: report_abilitati = []

            dati_sessione = df_giocatore[df_giocatore['Session'] == sessione_selezionata].iloc[0]
            tipologia_corrente = dati_sessione.get('Tipologia Sessione', 'Sconosciuta')
            data_sessione_str = dati_sessione.get('Date', 'N/D')
            is_sim_sess = bool(dati_sessione.get('Dato_Simulato', False))

            col_num_std = [c for c in COLONNE_STANDARD if c not in ["Date", "Session", "Players"]]

            df_tipo = df_completo[(df_completo['Players'] == giocatore_selezionato) & (df_completo['Tipologia Sessione'] == tipologia_corrente) & (df_completo['Dato_Simulato'] == False)].copy()
            if df_tipo.empty:
                df_tipo = df_completo[(df_completo['Players'] == giocatore_selezionato) & (df_completo['Dato_Simulato'] == False)].copy()
            for c_s in col_num_std:
                if c_s in df_tipo.columns:
                    df_tipo[c_s] = pd.to_numeric(df_tipo[c_s], errors='coerce').fillna(0.0)
            medie_tipo = df_tipo.mean(numeric_only=True).fillna(0)
            
            df_tipo_gps = df_tipo[df_tipo['Ambiente'].astype(str).str.lower() != 'indoor'].copy()
            medie_tipo_gps = df_tipo_gps.mean(numeric_only=True).fillna(0) if not df_tipo_gps.empty else pd.Series(0.0, index=medie_tipo.index)
            
            df_match = df_completo[(df_completo['Players'] == giocatore_selezionato) & (df_completo['Tipologia Sessione'].astype(str).str.lower() == 'match') & (df_completo['Dato_Simulato'] == False)].copy()
            for c_s in col_num_std:
                if c_s in df_match.columns:
                    df_match[c_s] = pd.to_numeric(df_match[c_s], errors='coerce').fillna(0.0)
            medie_match = df_match.mean(numeric_only=True).fillna(0)

            campo = dati_sessione.get('Tipologia Campo', 'N/D')
            ambiente = dati_sessione.get('Ambiente', 'N/D')
            sparring = dati_sessione.get('Minuti Sparring', 0)
            
            if pd.isna(campo) or str(campo).lower() == 'nan' or campo == 0: campo = "N/D"
            if pd.isna(ambiente) or str(ambiente).lower() == 'nan' or ambiente == 0: ambiente = "N/D"
            if pd.isna(sparring): sparring = 0
            
            if is_sim_sess:
                st.warning(t['am_sim_alert'])

            meta_items_sess = [
                (tr("Superficie", "Surface"), campo),
                (tr("Ambiente", "Environment"), ambiente),
                ("Sparring", f"{sparring} min"),
                (tr("Data", "Date"), data_sessione_str),
                (tr("Tipo", "Type"), tipologia_corrente, True),
            ]
            if is_sim_sess:
                meta_items_sess.append((tr("Origine Dato", "Data Source"), "SIMULATO", True))

            opzioni_sub_sess = {
                tr("Tutte le Sottoaree (Completo)", "All Sections (Full Report)"): "Tutte",
                tr("1. Sintesi & Delta", "1. Summary & Delta"): "Sintesi_Delta",
                tr("2. Carico Energetico", "2. Energy Load"): "Carico_Energetico",
                tr("3. Dati Meccanici, GPS & Metab.", "3. Mechanical, GPS & Metabolic"): "Dati_Meccanici_GPS",
                tr("4. Readiness (Acuto/Cronico)", "4. Readiness (Acute/Chronic)"): "Readiness"
            }
            render_action_bar(
                meta_items=meta_items_sess,
                pdf_options=opzioni_sub_sess,
                pdf_key="sess",
                generate_fn=lambda codice_sub_s: crea_pdf_sessione_m0v3(
                    giocatore_selezionato, data_sessione_str, sessione_selezionata,
                    tipologia_corrente, campo, ambiente, sparring,
                    dati_sessione, medie_tipo, medie_match, medie_tipo_gps=medie_tipo_gps, df_completo=df_completo, sottoarea=codice_sub_s
                ),
                filename_fn=lambda codice_sub_s: f"M0V3_Sessione_{codice_sub_s}_{slugify_name(giocatore_selezionato)}_{str(data_sessione_str).replace('/', '-')}.pdf",
            )

            is_first_report = True

            # --- RIEPILOGO IN CIMA: card + frase automatica (allineato con Before Tomorrow [T-1, T]) ---
            if "Distance from the averages (Session)" in report_abilitati:
                mostra_acwr_s = "Before Tomorrow (Acute 2 Days)" in report_abilitati
                r_vol_s, r_int_s, r_den_s = riepilogo_match(dati_sessione, medie_tipo)
                r_acwr_s = acwr_pre_match(df_completo, giocatore_selezionato, data_sessione_str, giorni=2, include_target=True) if mostra_acwr_s else None

                cols_ks = st.columns(4 if mostra_acwr_s else 3)
                with cols_ks[0]:
                    st.markdown(card_kpi(tr("Volume vs Tipo", "Volume vs Type"), formatta_delta(r_vol_s, size=30), tr("Tempo, Training Load, azioni intense", "Duration, Training Load, intense actions"), "#0ea5e9"), unsafe_allow_html=True)
                with cols_ks[1]:
                    st.markdown(card_kpi(tr("Intensità vs Tipo", "Intensity vs Type"), formatta_delta(r_int_s, size=30), tr("TL High, accelerazioni, decelerazioni", "TL High, accelerations, decelerations"), "#ef4444"), unsafe_allow_html=True)
                with cols_ks[2]:
                    st.markdown(card_kpi(tr("Work Rate vs Tipo", "Work Rate vs Type"), formatta_delta(r_den_s, size=30), tr("Carico e azioni al minuto", "Load and actions per minute"), "#f59e0b"), unsafe_allow_html=True)
                if mostra_acwr_s:
                    with cols_ks[3]:
                        if r_acwr_s is None:
                            val_html_s = "<span style='color:#94a3b8; font-size:26px; font-weight:800;'>N/D</span>"
                            sub_s = tr("Storico insufficiente", "Insufficient history")
                            acc_s = "#94a3b8"
                        else:
                            testo_ss, bg_ss, fg_ss = stato_acwr(r_acwr_s)
                            val_html_s = f"<span style='background:{bg_ss}; color:{fg_ss}; padding:3px 12px; border-radius:20px; font-size:24px; font-weight:900;'>{r_acwr_s:.0f}%</span>"
                            sub_s = f"{tr('Carico acuto 2 gg', '2-day acute load')}: {testo_ss}"
                            acc_s = fg_ss
                        st.markdown(card_kpi("Readiness", val_html_s, sub_s, acc_s), unsafe_allow_html=True)

                st.markdown(
                    f"<div style='background:#f0f9ff; border:1px solid #bae6fd; border-radius:10px; padding:12px 16px; margin:14px 0 22px 0; color:#0f172a; font-size:15px;'>{frase_riepilogo(r_vol_s, r_int_s, r_den_s, r_acwr_s)}</div>",
                    unsafe_allow_html=True
                )

            # --- TABS DI NAVIGAZIONE (PERSISTENTI & REATTIVI M0V3) ---
            T_SINTESI = tr("Sintesi & Delta", "Summary & Delta")
            T_ENERGIA = tr("Carico Energetico", "Energy Load")
            T_MECC = tr("Dati Meccanici & GPS", "Mechanical & GPS Data")
            T_READINESS = tr("Readiness (Acuto/Cronico)", "Readiness (Acute/Chronic)")

            session_tabs = [T_SINTESI, T_ENERGIA, T_MECC, T_READINESS]
            active_sess_tab = render_tab_navigation(session_tabs, key="nav_analisi_sessione")

            def calc_pm(val, mins): return val / mins if mins > 0 else 0
            def calcola_delta(curr, avg): return ((curr - avg) / avg * 100) if avg > 0 else 0

            c_min = get_val(dati_sessione, 'Minuti')
            c_tl = get_val(dati_sessione, 'Training Load')
            c_az2 = get_val(dati_sessione, 'Azioni Int. IMU >2')
            c_tlh = get_val(dati_sessione, 'TL_High')
            c_acc = get_val(dati_sessione, 'High Accel IMU')
            c_dec = get_val(dati_sessione, 'High Decel IMU')
            c_tl_pm, c_acc_pm, c_dec_pm, c_tlh_pm, c_az2_pm = calc_pm(c_tl, c_min), calc_pm(c_acc, c_min), calc_pm(c_dec, c_min), calc_pm(c_tlh, c_min), calc_pm(c_az2, c_min)

            # =========================================================================
            # TAB 1: SINTESI & DELTA (Distance from the averages)
            # =========================================================================
            if active_sess_tab == T_SINTESI:
                if "Distance from the averages (Session)" in report_abilitati:
                    render_print_header(is_first_report, giocatore_selezionato, data_sessione_str, sessione_selezionata, campo, ambiente, sparring)
                    is_first_report = False

                    t_min = get_val(medie_tipo, 'Minuti')
                    t_tl, t_az2 = get_val(medie_tipo, 'Training Load'), get_val(medie_tipo, 'Azioni Int. IMU >2')
                    t_tlh, t_acc, t_dec = get_val(medie_tipo, 'TL_High'), get_val(medie_tipo, 'High Accel IMU'), get_val(medie_tipo, 'High Decel IMU')
                    t_tl_pm, t_acc_pm, t_dec_pm, t_tlh_pm, t_az2_pm = calc_pm(t_tl, t_min), calc_pm(t_acc, t_min), calc_pm(t_dec, t_min), calc_pm(t_tlh, t_min), calc_pm(t_az2, t_min)

                    m_min = get_val(medie_match, 'Minuti')
                    m_tl, m_az2 = get_val(medie_match, 'Training Load'), get_val(medie_match, 'Azioni Int. IMU >2')
                    m_tlh, m_acc, m_dec = get_val(medie_match, 'TL_High'), get_val(medie_match, 'High Accel IMU'), get_val(medie_match, 'High Decel IMU')
                    m_tl_pm, m_acc_pm, m_dec_pm, m_tlh_pm, m_az2_pm = calc_pm(m_tl, m_min), calc_pm(m_acc, m_min), calc_pm(m_dec, m_min), calc_pm(m_tlh, m_min), calc_pm(m_az2, m_min)

                    pt_min, pt_tl, pt_az2 = calcola_delta(c_min, t_min), calcola_delta(c_tl, t_tl), calcola_delta(c_az2, t_az2)
                    pt_tlh, pt_acc, pt_dec = calcola_delta(c_tlh, t_tlh), calcola_delta(c_acc, t_acc), calcola_delta(c_dec, t_dec)
                    pt_tl_pm, pt_acc_pm, pt_dec_pm, pt_tlh_pm, pt_az2_pm = calcola_delta(c_tl_pm, t_tl_pm), calcola_delta(c_acc_pm, t_acc_pm), calcola_delta(c_dec_pm, t_dec_pm), calcola_delta(c_tlh_pm, t_tlh_pm), calcola_delta(c_az2_pm, t_az2_pm)

                    pm_min, pm_tl, pm_az2 = calcola_delta(c_min, m_min), calcola_delta(c_tl, m_tl), calcola_delta(c_az2, m_az2)
                    pm_tlh, pm_acc, pm_dec = calcola_delta(c_tlh, m_tlh), calcola_delta(c_acc, m_acc), calcola_delta(c_dec, m_dec)
                    pm_tl_pm, pm_acc_pm, pm_dec_pm, pm_tlh_pm, pm_az2_pm = calcola_delta(c_tl_pm, m_tl_pm), calcola_delta(c_acc_pm, m_acc_pm), calcola_delta(c_dec_pm, m_dec_pm), calcola_delta(c_tlh_pm, m_tlh_pm), calcola_delta(c_az2_pm, m_az2_pm)

                    avg_vol_t, avg_vol_m = (pt_min + pt_tl + pt_az2) / 3, (pm_min + pm_tl + pm_az2) / 3
                    avg_int_t, avg_int_m = (pt_tlh + pt_acc + pt_dec) / 3, (pm_tlh + pm_acc + pm_dec) / 3
                    avg_den_t, avg_den_m = (pt_tl_pm + pt_acc_pm + pt_dec_pm + pt_tlh_pm + pt_az2_pm) / 5, (pm_tl_pm + pm_acc_pm + pm_dec_pm + pm_tlh_pm + pm_az2_pm) / 5

                    lbl_vs_t = tr("vs tipo", "vs type")
                    lbl_vs_m = tr("vs match", "vs match")

                    def riga_stat_sess(label, cat_tag, cat_fg, cat_bg, val, vt_ref, vm_ref, dec, pt, pm):
                        val_s = f"{val:.{dec}f}".replace('.', ',')
                        vt_s = f"{vt_ref:.{dec}f}".replace('.', ',')
                        vm_s = f"{vm_ref:.{dec}f}".replace('.', ',')
                        has_t = vt_ref > 0
                        has_m = vm_ref > 0
                        pct_t_v = (val / vt_ref * 100.0) if has_t else 0.0
                        pct_m_v = (val / vm_ref * 100.0) if has_m else 0.0
                        return (
                            "<tr style='border-bottom: 1px solid #f1f5f9;'>"
                            "<td style='padding: 13px 12px;'>"
                            f"<div style='font-weight: 700; color: #0f172a; font-size: 14px;'>{label}</div>"
                            f"<span style='display:inline-block; margin-top:3px; background:{cat_bg}; color:{cat_fg}; font-size:9px; font-weight:800; padding:2px 7px; border-radius:4px;'>{cat_tag}</span>"
                            "</td>"
                            f"<td style='padding: 13px 10px; text-align: center; font-weight: 900; font-size: 19px; color: #0f172a;'>{val_s}</td>"
                            f"<td style='padding: 13px 10px; text-align: center;'>"
                            f"{render_pct_badge_cell(pct_t_v, pt, has_t, lbl_vs_t)}"
                            f"<div style='font-size:10px; color:#94a3b8; margin-top:2px;'>Ref: {vt_s}</div>"
                            "</td>"
                            f"<td style='padding: 13px 10px;'>{render_pct_progress_bar(pct_t_v)}</td>"
                            f"<td style='padding: 13px 10px; text-align: center;'>"
                            f"{render_pct_badge_cell(pct_m_v, pm, has_m, lbl_vs_m)}"
                            f"<div style='font-size:10px; color:#94a3b8; margin-top:2px;'>Ref: {vm_s}</div>"
                            "</td>"
                            f"<td style='padding: 13px 10px;'>{render_pct_progress_bar(pct_m_v, '#64748b')}</td>"
                            "</tr>"
                        )

                    def riga_sunto_sess(label, pt_avg, pm_avg, color):
                        pct_t_tot = max(0.0, 100.0 + pt_avg)
                        pct_m_tot = max(0.0, 100.0 + pm_avg)
                        return (
                            "<tr style='background-color: #f8fafc; border-top: 1px solid #e2e8f0; border-bottom: 2px solid #e2e8f0;'>"
                            f"<td colspan='2' style='padding: 14px 12px; font-weight: 800; color: {color}; text-transform: uppercase; font-size: 12px; letter-spacing: 0.6px; border-left: 4px solid {color};'>{label}</td>"
                            f"<td style='padding: 14px 10px; text-align: center;'>{render_pct_badge_cell(pct_t_tot, pt_avg, True, lbl_vs_t)}</td>"
                            f"<td style='padding: 14px 10px;'>{render_pct_progress_bar(pct_t_tot, color)}</td>"
                            f"<td style='padding: 14px 10px; text-align: center;'>{render_pct_badge_cell(pct_m_tot, pm_avg, True, lbl_vs_m)}</td>"
                            f"<td style='padding: 14px 10px;'>{render_pct_progress_bar(pct_m_tot, '#64748b')}</td>"
                            "</tr>"
                        )

                    lbl_bn_sess = tr("EXECUTIVE SESSION REPORT — CONFRONTO VS MEDIA TIPOLOGIA & MEDIA MATCH", "EXECUTIVE SESSION REPORT — COMPARISON VS SESSION TYPE & MATCH AVG")
                    html_table = (
                        "<div style='background: white; border-radius: 12px; border: 1px solid #e2e8f0; overflow: hidden; box-shadow: 0 2px 6px -1px rgba(15,23,42,0.04); margin-bottom: 22px; font-family: \"Inter\", sans-serif;'>"
                        "<div style='background:#0f172a; border-bottom:2px solid #0ea5e9; padding:13px 18px; display:flex; justify-content:space-between; align-items:center;'>"
                        f"<span style='color:white; font-weight:900; font-size:14px; text-transform:uppercase; letter-spacing:0.8px;'>{lbl_bn_sess}</span>"
                        f"<span style='background:rgba(255,255,255,0.1); color:#38bdf8; font-size:11px; font-weight:800; padding:4px 10px; border-radius:6px;'>{tipologia_corrente} · {data_sessione_str}</span>"
                        "</div>"
                        "<table style='width: 100%; border-collapse: collapse;'>"
                        "<tr style='background-color: #f8fafc; border-bottom: 2px solid #e2e8f0;'>"
                        f"<th style='text-align: left; padding: 12px 12px; font-size: 11px; font-weight: 700; color: #64748b; text-transform: uppercase; width:24%;'>{tr('Parametro & Area', 'Parameter & Area')}</th>"
                        f"<th style='text-align: center; padding: 12px 10px; font-size: 11px; font-weight: 700; color: #0f172a; text-transform: uppercase; width:12%;'>{tr('Valore Sessione', 'Session Score')}</th>"
                        f"<th colspan='2' style='text-align: center; padding: 12px 10px; font-size: 11px; font-weight: 800; color: #0ea5e9; text-transform: uppercase; width:32%;'>{tr('% Raggiunta vs Media Tipologia', '% Reached vs Session Type Avg')}</th>"
                        f"<th colspan='2' style='text-align: center; padding: 12px 10px; font-size: 11px; font-weight: 700; color: #64748b; text-transform: uppercase; width:32%;'>{tr('% Raggiunta vs Media Match', '% Reached vs Match Average')}</th>"
                        "</tr>"
                    )

                    html_table += riga_stat_sess(tr("Durata (min)", "Time (min)"), "VOLUME", "#0284c7", "#e0f2fe", c_min, t_min, m_min, 0, pt_min, pm_min)
                    html_table += riga_stat_sess("Training Load", "VOLUME", "#0284c7", "#e0f2fe", c_tl, t_tl, m_tl, 0, pt_tl, pm_tl)
                    html_table += riga_stat_sess(tr('Azioni Intense >2"', 'Intense Actions >2"'), "VOLUME", "#0284c7", "#e0f2fe", c_az2, t_az2, m_az2, 0, pt_az2, pm_az2)
                    html_table += riga_sunto_sess(tr("Sintesi Volume Generale", "Total General Volume Achievement"), avg_vol_t, avg_vol_m, "#0ea5e9")
                    html_table += "<tr><td colspan='6' style='height: 10px; border:none;'></td></tr>"

                    html_table += riga_stat_sess(tr("Accelerazioni Alta Int.", "High Acc Events"), "HIGH INTENSITY", "#dc2626", "#fee2e2", c_acc, t_acc, m_acc, 0, pt_acc, pm_acc)
                    html_table += riga_stat_sess(tr("Decelerazioni Alta Int.", "High Dec Events"), "HIGH INTENSITY", "#dc2626", "#fee2e2", c_dec, t_dec, m_dec, 0, pt_dec, pm_dec)
                    html_table += riga_stat_sess("Training Load High", "HIGH INTENSITY", "#dc2626", "#fee2e2", c_tlh, t_tlh, m_tlh, 0, pt_tlh, pm_tlh)
                    html_table += riga_sunto_sess(tr("Sintesi Volume Alta Intensità", "Total High Intensity Volume Achievement"), avg_int_t, avg_int_m, "#ef4444")
                    html_table += "<tr><td colspan='6' style='height: 10px; border:none;'></td></tr>"

                    html_table += riga_stat_sess("TL / min", "WORK RATE", "#b45309", "#fef3c7", c_tl_pm, t_tl_pm, m_tl_pm, 1, pt_tl_pm, pm_tl_pm)
                    html_table += riga_stat_sess("High Acc / min", "WORK RATE", "#b45309", "#fef3c7", c_acc_pm, t_acc_pm, m_acc_pm, 1, pt_acc_pm, pm_acc_pm)
                    html_table += riga_stat_sess("High Dec / min", "WORK RATE", "#b45309", "#fef3c7", c_dec_pm, t_dec_pm, m_dec_pm, 1, pt_dec_pm, pm_dec_pm)
                    html_table += riga_stat_sess(tr("Azioni Intense / min", "Intense Actions / min"), "WORK RATE", "#b45309", "#fef3c7", c_az2_pm, t_az2_pm, m_az2_pm, 1, pt_az2_pm, pm_az2_pm)
                    html_table += riga_stat_sess("TL High / min", "WORK RATE", "#b45309", "#fef3c7", c_tlh_pm, t_tlh_pm, m_tlh_pm, 1, pt_tlh_pm, pm_tlh_pm)
                    html_table += riga_sunto_sess(tr("Sintesi Work Rate", "Total Work Rate Achievement"), avg_den_t, avg_den_m, "#f59e0b")

                    html_table += "</table></div>"
                    st.markdown(html_table, unsafe_allow_html=True)

                    render_executive_hexagon_profile(
                        val_cur=dati_sessione,
                        val_ref=medie_tipo,
                        lbl_ref_legend=tr(f"Media {tipologia_corrente} (100%)", f"{tipologia_corrente} Avg (100%)"),
                        lbl_vs=lbl_vs_t,
                        chart_key=f"hex_sess_main_{sessione_selezionata}",
                    )

            # =========================================================================
            # TAB 2: CARICO ENERGETICO (Bands)
            # =========================================================================
            elif active_sess_tab == T_ENERGIA:
                if "Training Load Bands" in report_abilitati:
                    tl_totale = get_val(dati_sessione, 'Training Load', 0.0)
                    val_stand = get_val(dati_sessione, 'TL_Stand', 0.0)
                    val_low = get_val(dati_sessione, 'TL_Low', 0.0)
                    val_med = get_val(dati_sessione, 'TL_Medium', 0.0)
                    val_high = get_val(dati_sessione, 'TL_High', get_val(dati_sessione, 'TL High', 0.0))

                    med_stand = get_val(medie_tipo, 'TL_Stand', 0.0)
                    med_low = get_val(medie_tipo, 'TL_Low', 0.0)
                    med_med = get_val(medie_tipo, 'TL_Medium', 0.0)
                    med_high = get_val(medie_tipo, 'TL_High', 0.0)

                    bands_tl_sess = [
                        ("STAND", "TL Stand", val_stand, med_stand, "#64748b", "#f1f5f9"),
                        ("LOW", "TL Low", val_low, med_low, "#0ea5e9", "#e0f2fe"),
                        ("MEDIUM", "TL Medium", val_med, med_med, "#f59e0b", "#fef3c7"),
                        ("HIGH", "TL High", val_high, med_high, "#ef4444", "#fee2e2"),
                    ]
                    render_executive_bands_section(
                        title_banner=tr("FASCE DI CARICO (TRAINING LOAD BANDS)", "TRAINING LOAD BANDS"),
                        subtitle_ctx=f"Training Load Totale: {tl_totale:.0f}",
                        bands_data=bands_tl_sess,
                        lbl_cur=tr("Sessione", "Session"),
                        lbl_ref=tr("Media Tipologia", "Type Avg"),
                        unit_suffix="",
                        chart_key_prefix=f"sess_tl_bands_{sessione_selezionata}",
                    )

                if "Training Load Time% Bends" in report_abilitati:
                    st.markdown("<div style='height: 18px;'></div>", unsafe_allow_html=True)
                    val_t_stand = get_val(dati_sessione, 'TL_T_Stand', 0.0); med_t_stand = get_val(medie_tipo, 'TL_T_Stand', 0.0)
                    val_t_low = get_val(dati_sessione, 'TL_T_Low', 0.0); med_t_low = get_val(medie_tipo, 'TL_T_Low', 0.0)
                    val_t_med = get_val(dati_sessione, 'TL_T_Medium', 0.0); med_t_med = get_val(medie_tipo, 'TL_T_Medium', 0.0)
                    val_t_high = get_val(dati_sessione, 'TL_T_High', 0.0); med_t_high = get_val(medie_tipo, 'TL_T_High', 0.0)

                    bands_t_sess = [
                        ("STAND %T", "TL Stand %T", val_t_stand, med_t_stand, "#64748b", "#f1f5f9"),
                        ("LOW %T", "TL Low %T", val_t_low, med_t_low, "#0ea5e9", "#e0f2fe"),
                        ("MED %T", "TL Medium %T", val_t_med, med_t_med, "#f59e0b", "#fef3c7"),
                        ("HIGH %T", "TL High %T", val_t_high, med_t_high, "#ef4444", "#fee2e2"),
                    ]
                    render_executive_bands_section(
                        title_banner=tr("DISTRIBUZIONE % TEMPO IN FASCIA (TIME % BANDS)", "TRAINING LOAD TIME % BANDS"),
                        subtitle_ctx=tr("% Tempo sul Totale Sessione", "% Time of Total Session"),
                        bands_data=bands_t_sess,
                        lbl_cur=tr("Sessione", "Session"),
                        lbl_ref=tr("Media Tipologia", "Type Avg"),
                        unit_suffix="%",
                        chart_key_prefix=f"sess_t_bands_{sessione_selezionata}",
                    )

            # =========================================================================
            # TAB 3: DATI MECCANICI, GPS, AEROBIC & ANAEROBIC
            # =========================================================================
            elif active_sess_tab == T_MECC:
                lbl_vs_t3 = tr("vs tipo", "vs type")
                lbl_vs_m3 = tr("vs match", "vs match")
                if "Dati volumetrici IMU" in report_abilitati:
                    val_minuti = get_val(dati_sessione, 'Minuti', 0); med_minuti = get_val(medie_tipo, 'Minuti', 0)
                    val_pl = get_val(dati_sessione, 'Player Load', 0); med_pl = get_val(medie_tipo, 'Player Load', 0)
                    val_tl = get_val(dati_sessione, 'Training Load', 0); med_tl = get_val(medie_tipo, 'Training Load', 0)
                    val_acc = get_val(dati_sessione, 'High Accel IMU', 0); med_acc = get_val(medie_tipo, 'High Accel IMU', 0)
                    val_dec = get_val(dati_sessione, 'High Decel IMU', 0); med_dec = get_val(medie_tipo, 'High Decel IMU', 0)

                    imu_rows_s = [
                        (tr("Durata (min)", "Duration (min)"), "IMU VOLUME", "#0284c7", "#e0f2fe", val_minuti, med_minuti, ""),
                        ("Player Load", "IMU VOLUME", "#0284c7", "#e0f2fe", val_pl, med_pl, ""),
                        ("Training Load", "IMU VOLUME", "#0284c7", "#e0f2fe", val_tl, med_tl, ""),
                        ("High Acceleration IMU", "MECHANICAL", "#dc2626", "#fee2e2", val_acc, med_acc, ""),
                        ("High Deceleration IMU", "MECHANICAL", "#dc2626", "#fee2e2", val_dec, med_dec, ""),
                    ]
                    lbl_imu_s_bn = tr("DATI VOLUMETRICI & MECCANICI IMU — CONFRONTO VS MEDIA TIPOLOGIA", "IMU VOLUMETRIC & MECHANICAL DATA — COMPARISON VS SESSION TYPE AVG")
                    html_imu = (
                        "<div style='background:white; border:1px solid #e2e8f0; border-radius:12px; overflow:hidden; box-shadow:0 2px 6px -1px rgba(15,23,42,0.04); margin-bottom:18px; font-family:\"Inter\", sans-serif;'>"
                        "<div style='background:#0f172a; border-bottom:2px solid #0ea5e9; padding:13px 18px; display:flex; justify-content:space-between; align-items:center;'>"
                        f"<span style='color:white; font-weight:900; font-size:14px; text-transform:uppercase; letter-spacing:0.8px;'>{lbl_imu_s_bn}</span>"
                        f"<span style='background:rgba(255,255,255,0.1); color:#38bdf8; font-size:11px; font-weight:800; padding:4px 10px; border-radius:6px;'>{tipologia_corrente}</span>"
                        "</div>"
                        "<table style='width:100%; border-collapse:collapse;'>"
                        "<tr style='background:#f8fafc; border-bottom:2px solid #e2e8f0;'>"
                        f"<th style='padding:12px 14px; text-align:left; color:#64748b; font-size:11px; font-weight:700; text-transform:uppercase; width:28%;'>{tr('Metrica IMU & Area', 'IMU Metric & Area')}</th>"
                        f"<th style='padding:12px 14px; text-align:center; color:#0f172a; font-size:11px; font-weight:700; text-transform:uppercase; width:16%;'>{tr('Valore Sessione', 'Session Score')}</th>"
                        f"<th style='padding:12px 14px; text-align:center; color:#64748b; font-size:11px; font-weight:700; text-transform:uppercase; width:16%;'>{tr('Media Tipologia', 'Session Type Avg')}</th>"
                        f"<th style='padding:12px 14px; text-align:center; color:#0ea5e9; font-size:11px; font-weight:800; text-transform:uppercase; width:22%;'>{tr('% Raggiunta (Scostamento)', 'Percentage Reached (Delta)')}</th>"
                        f"<th style='padding:12px 14px; text-align:center; color:#64748b; font-size:11px; font-weight:700; text-transform:uppercase; width:18%;'>{tr('Fascia (Tacca = 100%)', 'Zone (Tick = 100%)')}</th>"
                        "</tr>"
                    )
                    for lbl_i, tag_i, fg_i, bg_i, vc_i, vm_i, suf_i in imu_rows_s:
                        has_ri = vm_i > 0
                        pv_i = (vc_i / vm_i * 100.0) if has_ri else 0.0
                        dv_i = pv_i - 100.0 if has_ri else 0.0
                        html_imu += (
                            "<tr style='border-bottom:1px solid #f1f5f9;'>"
                            "<td style='padding:13px 14px;'>"
                            f"<div style='font-weight:700; color:#0f172a; font-size:14px;'>{lbl_i}</div>"
                            f"<span style='display:inline-block; margin-top:3px; background:{bg_i}; color:{fg_i}; font-size:9px; font-weight:800; padding:2px 7px; border-radius:4px;'>{tag_i}</span>"
                            "</td>"
                            f"<td style='padding:13px 14px; text-align:center; font-weight:900; font-size:19px; color:#0f172a;'>{vc_i:.0f}{suf_i}</td>"
                            f"<td style='padding:13px 14px; text-align:center; font-weight:700; font-size:16px; color:#64748b;'>{vm_i:.0f}{suf_i}</td>"
                            f"<td style='padding:13px 14px; text-align:center;'>{render_pct_badge_cell(pv_i, dv_i, has_ri, lbl_vs_t3)}</td>"
                            f"<td style='padding:13px 14px;'>{render_pct_progress_bar(pv_i)}</td>"
                            "</tr>"
                        )
                    html_imu += "</table></div>"
                    st.markdown(html_imu, unsafe_allow_html=True)

                    col_g1, col_g2 = st.columns(2, gap="medium")
                    with col_g1:
                        with st.container(border=True):
                            st.markdown(render_executive_chart_header(tr("Carico Globale (Player Load & Training Load)", "Global Load (Player Load & Training Load)"), accent="#0ea5e9"), unsafe_allow_html=True)
                            fig_load = go.Figure(data=[
                                go.Bar(name=tr('Sessione', 'Session'), x=['Player Load', 'Training Load'], y=[val_pl, val_tl], marker_color='#0ea5e9', text=[f"{val_pl:.0f}", f"{val_tl:.0f}"], textposition='outside', cliponaxis=False),
                                go.Bar(name=tr('Media Tipologia', 'Session Type Avg'), x=['Player Load', 'Training Load'], y=[med_pl, med_tl], marker_color='#cbd5e1', text=[f"{med_pl:.0f}", f"{med_tl:.0f}"], textposition='outside', cliponaxis=False)
                            ])
                            fig_load.update_layout(height=280, barmode='group', showlegend=False, yaxis=dict(range=[0, max(val_pl, val_tl, med_pl, med_tl, 10)*1.25], gridcolor='#f1f5f9'), margin=dict(l=10, r=10, t=15, b=10), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                            st.plotly_chart(fig_load, use_container_width=True, key=f"s_imu_load_{sessione_selezionata}")
                    with col_g2:
                        with st.container(border=True):
                            st.markdown(render_executive_chart_header(tr("Eventi Meccanici IMU (Acc & Dec)", "IMU Mechanical Events (Acc & Dec)"), accent="#10b981"), unsafe_allow_html=True)
                            fig_imu = go.Figure(data=[
                                go.Bar(name=tr('Sessione', 'Session'), x=['High Acc IMU', 'High Dec IMU'], y=[val_acc, val_dec], marker_color='#10b981', text=[f"{val_acc:.0f}", f"{val_dec:.0f}"], textposition='outside', cliponaxis=False),
                                go.Bar(name=tr('Media Tipologia', 'Session Type Avg'), x=['High Acc IMU', 'High Dec IMU'], y=[med_acc, med_dec], marker_color='#cbd5e1', text=[f"{med_acc:.0f}", f"{med_dec:.0f}"], textposition='outside', cliponaxis=False)
                            ])
                            fig_imu.update_layout(height=280, barmode='group', showlegend=False, yaxis=dict(range=[0, max(val_acc, val_dec, med_acc, med_dec, 10)*1.25], gridcolor='#f1f5f9'), margin=dict(l=10, r=10, t=15, b=10), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                            st.plotly_chart(fig_imu, use_container_width=True, key=f"s_imu_mech_{sessione_selezionata}")

                if "Dati GPS" in report_abilitati:
                    st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)
                    if ambiente == "Indoor":
                        st.warning(t['am_indoor_warn'])
                    else:
                        val_dist = get_val(dati_sessione, 'DISTANCE', 0); med_dist = get_val(medie_tipo_gps, 'DISTANCE', 0)
                        val_hml = get_val(dati_sessione, 'HML Distance >25.5W', 0); med_hml = get_val(medie_tipo_gps, 'HML Distance >25.5W', 0)
                        val_vhml = get_val(dati_sessione, 'VHML Distance >50W', 0); med_vhml = get_val(medie_tipo_gps, 'VHML Distance >50W', 0)
                        val_hdec = get_val(dati_sessione, 'High Dec Events <-3.5 m/s2', 0); med_hdec = get_val(medie_tipo_gps, 'High Dec Events <-3.5 m/s2', 0)
                        val_rec = get_val(dati_sessione, 'Recovery Time <5W %', 0); med_rec = get_val(medie_tipo_gps, 'Recovery Time <5W %', 0)
                        val_eq_dist = get_val(dati_sessione, 'Equivalent Distance %', 0); med_eq_dist = get_val(medie_tipo_gps, 'Equivalent Distance %', 0)
                        val_an_idx = get_val(dati_sessione, 'Anaerobic index %', 0); med_an_idx = get_val(medie_tipo_gps, 'Anaerobic index %', 0)

                        gps_rows_s = [
                            ("DISTANCE (m)", "GPS VOLUME", "#0284c7", "#e0f2fe", val_dist, med_dist, " m"),
                            ("HML Distance >25.5W", "GPS METABOLIC", "#b45309", "#fef3c7", val_hml, med_hml, " m"),
                            ("VHML Distance >50W", "GPS HIGH INTENSITY", "#dc2626", "#fee2e2", val_vhml, med_vhml, " m"),
                            ("High Dec Events <-3.5 m/s²", "GPS MECHANICAL", "#dc2626", "#fee2e2", val_hdec, med_hdec, ""),
                            ("Recovery Time <5W %", "METABOLIC INDEX", "#166534", "#dcfce7", val_rec, med_rec, "%"),
                            ("Equivalent Distance %", "METABOLIC INDEX", "#166534", "#dcfce7", val_eq_dist, med_eq_dist, "%"),
                            ("Anaerobic Index %", "METABOLIC INDEX", "#166534", "#dcfce7", val_an_idx, med_an_idx, "%"),
                        ]
                        lbl_gps_s_bn = tr("DATI GPS & SATELLITARI OUTDOOR — CONFRONTO VS MEDIA TIPOLOGIA", "OUTDOOR GPS & SATELLITE DATA — COMPARISON VS SESSION TYPE AVG")
                        html_gps = (
                            "<div style='background:white; border:1px solid #e2e8f0; border-radius:12px; overflow:hidden; box-shadow:0 2px 6px -1px rgba(15,23,42,0.04); margin-bottom:18px; font-family:\"Inter\", sans-serif;'>"
                            "<div style='background:#0f172a; border-bottom:2px solid #f59e0b; padding:13px 18px; display:flex; justify-content:space-between; align-items:center;'>"
                            f"<span style='color:white; font-weight:900; font-size:14px; text-transform:uppercase; letter-spacing:0.8px;'>{lbl_gps_s_bn}</span>"
                            "<span style='background:rgba(255,255,255,0.1); color:#fbbf24; font-size:11px; font-weight:800; padding:4px 10px; border-radius:6px;'>OUTDOOR GPS</span>"
                            "</div>"
                            "<table style='width:100%; border-collapse:collapse;'>"
                            "<tr style='background:#f8fafc; border-bottom:2px solid #e2e8f0;'>"
                            f"<th style='padding:12px 14px; text-align:left; color:#64748b; font-size:11px; font-weight:700; text-transform:uppercase; width:28%;'>{tr('Metrica GPS & Area', 'GPS Metric & Area')}</th>"
                            f"<th style='padding:12px 14px; text-align:center; color:#0f172a; font-size:11px; font-weight:700; text-transform:uppercase; width:16%;'>{tr('Valore Sessione', 'Session Score')}</th>"
                            f"<th style='padding:12px 14px; text-align:center; color:#64748b; font-size:11px; font-weight:700; text-transform:uppercase; width:16%;'>{tr('Media Tipologia', 'Session Type Avg')}</th>"
                            f"<th style='padding:12px 14px; text-align:center; color:#0ea5e9; font-size:11px; font-weight:800; text-transform:uppercase; width:22%;'>{tr('% Raggiunta (Scostamento)', 'Percentage Reached (Delta)')}</th>"
                            f"<th style='padding:12px 14px; text-align:center; color:#64748b; font-size:11px; font-weight:700; text-transform:uppercase; width:18%;'>{tr('Fascia (Tacca = 100%)', 'Zone (Tick = 100%)')}</th>"
                            "</tr>"
                        )
                        for lbl_g, tag_g, fg_g, bg_g, vc_g, vm_g, suf_g in gps_rows_s:
                            has_rg = vm_g > 0
                            pv_g = (vc_g / vm_g * 100.0) if has_rg else 0.0
                            dv_g = pv_g - 100.0 if has_rg else 0.0
                            html_gps += (
                                "<tr style='border-bottom:1px solid #f1f5f9;'>"
                                "<td style='padding:13px 14px;'>"
                                f"<div style='font-weight:700; color:#0f172a; font-size:14px;'>{lbl_g}</div>"
                                f"<span style='display:inline-block; margin-top:3px; background:{bg_g}; color:{fg_g}; font-size:9px; font-weight:800; padding:2px 7px; border-radius:4px;'>{tag_g}</span>"
                                "</td>"
                                f"<td style='padding:13px 14px; text-align:center; font-weight:900; font-size:19px; color:#0f172a;'>{vc_g:.0f}{suf_g}</td>"
                                f"<td style='padding:13px 14px; text-align:center; font-weight:700; font-size:16px; color:#64748b;'>{vm_g:.0f}{suf_g}</td>"
                                f"<td style='padding:13px 14px; text-align:center;'>{render_pct_badge_cell(pv_g, dv_g, has_rg, lbl_vs_t3)}</td>"
                                f"<td style='padding:13px 14px;'>{render_pct_progress_bar(pv_g)}</td>"
                                "</tr>"
                            )
                        html_gps += "</table></div>"
                        st.markdown(html_gps, unsafe_allow_html=True)

                        with st.container(border=True):
                            st.markdown(render_executive_chart_header(tr("Indici Metabolici e Tempi di Recupero GPS (%)", "GPS Metabolic & Recovery Indices (%)"), accent="#f59e0b"), unsafe_allow_html=True)
                            fig_gps_pct = go.Figure(data=[
                                go.Bar(name=tr('Sessione', 'Session'), x=['Recovery <5W %', 'Equivalent Dist %', 'Anaerobic Index %'], y=[val_rec, val_eq_dist, val_an_idx], marker_color='#f59e0b', text=[f"{val_rec:.0f}%", f"{val_eq_dist:.0f}%", f"{val_an_idx:.0f}%"], textposition='outside', cliponaxis=False),
                                go.Bar(name=tr('Media Tipologia', 'Session Type Avg'), x=['Recovery <5W %', 'Equivalent Dist %', 'Anaerobic Index %'], y=[med_rec, med_eq_dist, med_an_idx], marker_color='#cbd5e1', text=[f"{med_rec:.0f}%", f"{med_eq_dist:.0f}%", f"{med_an_idx:.0f}%"], textposition='outside', cliponaxis=False)
                            ])
                            fig_gps_pct.update_layout(height=280, barmode='group', showlegend=False, yaxis=dict(range=[0, max(val_rec, val_eq_dist, val_an_idx, med_rec, med_eq_dist, med_an_idx, 10)*1.25], gridcolor='#f1f5f9'), margin=dict(l=10, r=10, t=15, b=10), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                            st.plotly_chart(fig_gps_pct, use_container_width=True, key=f"s_gps_pct_{sessione_selezionata}")

                if "Aerobic Area - Session Comparison" in report_abilitati:
                    st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)
                    c_high = get_val(dati_sessione, 'TL_T_High'); c_med = get_val(dati_sessione, 'TL_T_Medium'); c_mh = c_high + c_med; c_stand = get_val(dati_sessione, 'TL_T_Stand')
                    t_high = get_val(medie_tipo, 'TL_T_High'); t_med = get_val(medie_tipo, 'TL_T_Medium'); t_mh = t_high + t_med; t_stand = get_val(medie_tipo, 'TL_T_Stand')
                    m_high = get_val(medie_match, 'TL_T_High'); m_med = get_val(medie_match, 'TL_T_Medium'); m_mh = m_high + m_med; m_stand = get_val(medie_match, 'TL_T_Stand')

                    pt_high = calcola_delta(c_high, t_high); pm_high = calcola_delta(c_high, m_high)
                    pt_med = calcola_delta(c_med, t_med); pm_med = calcola_delta(c_med, m_med)
                    pt_mh = calcola_delta(c_mh, t_mh); pm_mh = calcola_delta(c_mh, m_mh)
                    pt_stand = calcola_delta(c_stand, t_stand); pm_stand = calcola_delta(c_stand, m_stand)

                    tot_t = (pt_mh - pt_stand) / 2
                    tot_m = (pm_mh - pm_stand) / 2

                    def riga_metab_exec(title_lbl, sub_lbl, val_str, vt_r, vm_r, pt_v, pm_v, is_highlight=False):
                        bg_r = "background-color: #f8fafc;" if is_highlight else ""
                        col_t = "#0284c7" if is_highlight else "#0f172a"
                        pct_t_v = max(0.0, 100.0 + pt_v)
                        pct_m_v = max(0.0, 100.0 + pm_v)
                        return (
                            f"<tr style='{bg_r} border-bottom: 1px solid #f1f5f9;'>"
                            f"<td style='padding: 13px 12px; font-weight: 700; color: {col_t}; font-size: 14px;'>{title_lbl}<br><span style='font-size:11px; color:#64748b; font-weight:500;'>{sub_lbl}</span></td>"
                            f"<td style='padding: 13px 10px; text-align: center; font-weight: 900; font-size: 18px; color: {col_t};'>{val_str}</td>"
                            f"<td style='padding: 13px 10px; text-align: center;'>{render_pct_badge_cell(pct_t_v, pt_v, vt_r > 0, lbl_vs_t3)}</td>"
                            f"<td style='padding: 13px 10px;'>{render_pct_progress_bar(pct_t_v)}</td>"
                            f"<td style='padding: 13px 10px; text-align: center;'>{render_pct_badge_cell(pct_m_v, pm_v, vm_r > 0, lbl_vs_m3)}</td>"
                            f"<td style='padding: 13px 10px;'>{render_pct_progress_bar(pct_m_v, '#64748b')}</td>"
                            "</tr>"
                        )

                    lbl_aero_bn = tr("AREA AEROBICA — DISTRIBUZIONE TEMPO IN FASCIA METABOLICA", "AEROBIC AREA — METABOLIC BAND TIME DISTRIBUTION")
                    html_aero = (
                        "<div style='background:white; border:1px solid #e2e8f0; border-radius:12px; overflow:hidden; box-shadow:0 2px 6px -1px rgba(15,23,42,0.04); margin-bottom:18px; font-family:\"Inter\", sans-serif;'>"
                        "<div style='background:#0f172a; border-bottom:2px solid #10b981; padding:13px 18px; display:flex; justify-content:space-between; align-items:center;'>"
                        f"<span style='color:white; font-weight:900; font-size:14px; text-transform:uppercase; letter-spacing:0.8px;'>{lbl_aero_bn}</span>"
                        "<span style='background:rgba(255,255,255,0.1); color:#34d399; font-size:11px; font-weight:800; padding:4px 10px; border-radius:6px;'>AEROBIC METABOLISM</span>"
                        "</div>"
                        "<table style='width: 100%; border-collapse: collapse; background-color:white;'>"
                        "<tr style='background-color: #f8fafc; border-bottom: 2px solid #e2e8f0;'>"
                        f"<th style='text-align: left; padding: 12px 12px; font-size: 11px; font-weight:700; color: #64748b; text-transform: uppercase; width:26%;'>{tr('Parametro Aerobico', 'Aerobic Parameter')}</th>"
                        f"<th style='text-align: center; padding: 12px 10px; font-size: 11px; font-weight:700; color: #0f172a; text-transform: uppercase; width:12%;'>{tr('Valore Sessione', 'Session Score')}</th>"
                        f"<th colspan='2' style='text-align: center; padding: 12px 10px; font-size: 11px; font-weight:800; color: #0ea5e9; text-transform: uppercase; width:31%;'>{tr('% Raggiunta vs Media Tipologia', '% Reached vs Session Type Avg')}</th>"
                        f"<th colspan='2' style='text-align: center; padding: 12px 10px; font-size: 11px; font-weight:700; color: #64748b; text-transform: uppercase; width:31%;'>{tr('% Raggiunta vs Media Match', '% Reached vs Match Average')}</th></tr>"
                    )
                    html_aero += riga_metab_exec("% Time TL High", "Time TL >1.5G / Total Time", f"{c_high:.0f}%", t_high, m_high, pt_high, pm_high)
                    html_aero += riga_metab_exec("% Time TL Medium", "Time TL 0.75G - 1.5G / Total Time", f"{c_med:.0f}%", t_med, m_med, pt_med, pm_med)
                    html_aero += riga_metab_exec("% Time TL Med-High (Combined)", "Time TL >0.75G / Total Time", f"{c_mh:.0f}%", t_mh, m_mh, pt_mh, pm_mh, is_highlight=True)
                    html_aero += riga_metab_exec("% Time TL Stand", "Time TL <0.2G / Total Time", f"{c_stand:.0f}%", t_stand, m_stand, pt_stand, pm_stand)
                    pct_aero_t = max(0.0, 100.0 + tot_t)
                    pct_aero_m = max(0.0, 100.0 + tot_m)
                    html_aero += (
                        "<tr style='background-color: #f8fafc; border-top: 1px solid #e2e8f0; border-bottom: 2px solid #e2e8f0;'>"
                        f"<td colspan='2' style='padding: 14px 12px; font-weight: 800; color: #10b981; text-transform: uppercase; font-size: 12px; letter-spacing: 0.6px; border-left: 4px solid #10b981;'>{tr('Sintesi Area Aerobica', 'Total Aerobic Area Comparison')}</td>"
                        f"<td style='padding: 14px 10px; text-align: center;'>{render_pct_badge_cell(pct_aero_t, tot_t, True, lbl_vs_t3)}</td>"
                        f"<td style='padding: 14px 10px;'>{render_pct_progress_bar(pct_aero_t, '#10b981')}</td>"
                        f"<td style='padding: 14px 10px; text-align: center;'>{render_pct_badge_cell(pct_aero_m, tot_m, True, lbl_vs_m3)}</td>"
                        f"<td style='padding: 14px 10px;'>{render_pct_progress_bar(pct_aero_m, '#64748b')}</td>"
                        "</tr></table></div>"
                    )
                    st.markdown(html_aero, unsafe_allow_html=True)

                if "Anaerobic Area - Session Comparison" in report_abilitati:
                    st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)
                    c_tlh_pm = c_tlh / c_min if c_min > 0 else 0; c_mech_pm = (c_acc + c_dec) / c_min if c_min > 0 else 0; c_az2_pm = c_az2 / c_min if c_min > 0 else 0
                    t_min = get_val(medie_tipo, 'Minuti')
                    t_tlh_pm = get_val(medie_tipo, 'TL_High') / t_min if t_min > 0 else 0; t_mech_pm = (get_val(medie_tipo, 'High Accel IMU') + get_val(medie_tipo, 'High Decel IMU')) / t_min if t_min > 0 else 0; t_az2_pm = get_val(medie_tipo, 'Azioni Int. IMU >2') / t_min if t_min > 0 else 0
                    m_min = get_val(medie_match, 'Minuti')
                    m_tlh_pm = get_val(medie_match, 'TL_High') / m_min if m_min > 0 else 0; m_mech_pm = (get_val(medie_match, 'High Accel IMU') + get_val(medie_match, 'High Decel IMU')) / m_min if m_min > 0 else 0; m_az2_pm = get_val(medie_match, 'Azioni Int. IMU >2') / m_min if m_min > 0 else 0

                    pt_tlh_pm = calcola_delta(c_tlh_pm, t_tlh_pm); pm_tlh_pm = calcola_delta(c_tlh_pm, m_tlh_pm)
                    pt_mech_pm = calcola_delta(c_mech_pm, t_mech_pm); pm_mech_pm = calcola_delta(c_mech_pm, m_mech_pm)
                    pt_az2_pm = calcola_delta(c_az2_pm, t_az2_pm); pm_az2_pm = calcola_delta(c_az2_pm, m_az2_pm)

                    tot_ana_t = (pt_tlh_pm + pt_mech_pm + pt_az2_pm) / 3
                    tot_ana_m = (pm_tlh_pm + pm_mech_pm + pm_az2_pm) / 3

                    def riga_ana_exec(title_lbl, sub_lbl, val_str, vt_r, vm_r, pt_v, pm_v):
                        pct_t_v = max(0.0, 100.0 + pt_v)
                        pct_m_v = max(0.0, 100.0 + pm_v)
                        return (
                            "<tr style='border-bottom: 1px solid #f1f5f9;'>"
                            f"<td style='padding: 13px 12px; font-weight: 700; color: #0f172a; font-size: 14px;'>{title_lbl}<br><span style='font-size:11px; color:#64748b; font-weight:500;'>{sub_lbl}</span></td>"
                            f"<td style='padding: 13px 10px; text-align: center; font-weight: 900; font-size: 18px; color: #0f172a;'>{val_str}</td>"
                            f"<td style='padding: 13px 10px; text-align: center;'>{render_pct_badge_cell(pct_t_v, pt_v, vt_r > 0, lbl_vs_t3)}</td>"
                            f"<td style='padding: 13px 10px;'>{render_pct_progress_bar(pct_t_v)}</td>"
                            f"<td style='padding: 13px 10px; text-align: center;'>{render_pct_badge_cell(pct_m_v, pm_v, vm_r > 0, lbl_vs_m3)}</td>"
                            f"<td style='padding: 13px 10px;'>{render_pct_progress_bar(pct_m_v, '#64748b')}</td>"
                            "</tr>"
                        )

                    lbl_ana_bn = tr("AREA ANAEROBICA — DENSITÀ D'ALTA INTENSITÀ & RSA", "ANAEROBIC AREA — HIGH INTENSITY DENSITY & RSA")
                    html_ana = (
                        "<div style='background:white; border:1px solid #e2e8f0; border-radius:12px; overflow:hidden; box-shadow:0 2px 6px -1px rgba(15,23,42,0.04); margin-bottom:18px; font-family:\"Inter\", sans-serif;'>"
                        "<div style='background:#0f172a; border-bottom:2px solid #ef4444; padding:13px 18px; display:flex; justify-content:space-between; align-items:center;'>"
                        f"<span style='color:white; font-weight:900; font-size:14px; text-transform:uppercase; letter-spacing:0.8px;'>{lbl_ana_bn}</span>"
                        "<span style='background:rgba(255,255,255,0.1); color:#f87171; font-size:11px; font-weight:800; padding:4px 10px; border-radius:6px;'>ANAEROBIC POWER</span>"
                        "</div>"
                        "<table style='width: 100%; border-collapse: collapse; background-color:white;'>"
                        "<tr style='background-color: #f8fafc; border-bottom: 2px solid #e2e8f0;'>"
                        f"<th style='text-align: left; padding: 12px 12px; font-size: 11px; font-weight:700; color: #64748b; text-transform: uppercase; width:26%;'>{tr('Parametro Anaerobico', 'Anaerobic Parameter')}</th>"
                        f"<th style='text-align: center; padding: 12px 10px; font-size: 11px; font-weight:700; color: #0f172a; text-transform: uppercase; width:12%;'>{tr('Valore Sessione', 'Session Score')}</th>"
                        f"<th colspan='2' style='text-align: center; padding: 12px 10px; font-size: 11px; font-weight:800; color: #0ea5e9; text-transform: uppercase; width:31%;'>{tr('% Raggiunta vs Media Tipologia', '% Reached vs Session Type Avg')}</th>"
                        f"<th colspan='2' style='text-align: center; padding: 12px 10px; font-size: 11px; font-weight:700; color: #64748b; text-transform: uppercase; width:31%;'>{tr('% Raggiunta vs Media Match', '% Reached vs Match Average')}</th></tr>"
                    )
                    html_ana += riga_ana_exec("TL High / min", "Metabolic Density", f"{c_tlh_pm:.1f}", t_tlh_pm, m_tlh_pm, pt_tlh_pm, pm_tlh_pm)
                    html_ana += riga_ana_exec("Mechanical Actions / min", "(High Acc + High Dec) / Total Time", f"{c_mech_pm:.1f}", t_mech_pm, m_mech_pm, pt_mech_pm, pm_mech_pm)
                    html_ana += riga_ana_exec('Intense Actions >2" / min', "Repeated Sprint Ability (RSA) Index", f"{c_az2_pm:.1f}", t_az2_pm, m_az2_pm, pt_az2_pm, pm_az2_pm)
                    pct_ana_t = max(0.0, 100.0 + tot_ana_t)
                    pct_ana_m = max(0.0, 100.0 + tot_ana_m)
                    html_ana += (
                        "<tr style='background-color: #f8fafc; border-top: 1px solid #e2e8f0; border-bottom: 2px solid #e2e8f0;'>"
                        f"<td colspan='2' style='padding: 14px 12px; font-weight: 800; color: #ef4444; text-transform: uppercase; font-size: 12px; letter-spacing: 0.6px; border-left: 4px solid #ef4444;'>{tr('Sintesi Densità Anaerobica', 'Total Anaerobic Density Comparison')}</td>"
                        f"<td style='padding: 14px 10px; text-align: center;'>{render_pct_badge_cell(pct_ana_t, tot_ana_t, True, lbl_vs_t3)}</td>"
                        f"<td style='padding: 14px 10px;'>{render_pct_progress_bar(pct_ana_t, '#ef4444')}</td>"
                        f"<td style='padding: 14px 10px; text-align: center;'>{render_pct_badge_cell(pct_ana_m, tot_ana_m, True, lbl_vs_m3)}</td>"
                        f"<td style='padding: 14px 10px;'>{render_pct_progress_bar(pct_ana_m, '#64748b')}</td>"
                        "</tr></table></div>"
                    )
                    st.markdown(html_ana, unsafe_allow_html=True)

            # =========================================================================
            # TAB 4: READINESS (BEFORE TOMORROW)
            # =========================================================================
            elif active_sess_tab == T_READINESS:
                if "Before Tomorrow (Acute 2 Days)" in report_abilitati or "Before Tomorrow (Chronic 7 Days)" in report_abilitati:
                    st.markdown(f"<h3 style='color:#0f172a; margin-bottom:6px;'>{tr('Readiness (Before Tomorrow — Carico Acuto / Cronico)', 'Readiness (Before Tomorrow — Acute / Chronic Load)')}</h3>", unsafe_allow_html=True)
                    st.markdown(f"<p style='color:#64748b; font-size:13px; margin-bottom:18px;'>{tr('Valutazione del carico fino alla sessione indagata (2 gg Acuto e 7 gg Cronico) rispetto alla baseline dei 28 giorni precedenti.', 'Evaluation of the load up to the selected session (2d Acute and 7d Chronic) compared to the preceding 28-day baseline.')}</p>", unsafe_allow_html=True)
                    df_ath_all = df_completo[df_completo['Players'] == giocatore_selezionato].copy()
                    df_ath_all['Date_obj'] = pd.to_datetime(df_ath_all['Date'], format="%d/%m/%Y", errors='coerce')
                    target_date = pd.to_datetime(data_sessione_str, format="%d/%m/%Y", errors='coerce')

                    if pd.isna(target_date):
                        st.warning(tr("Impossibile generare Acuto e Cronico: la data della sessione non è valida.", "Unable to generate Acute/Chronic: invalid session date."))
                    else:
                        col_rtm = ['Minuti', 'Training Load', 'TL_High', 'High Decel IMU', 'High Accel IMU', 'Azioni Int. IMU >2']
                        for c_r in col_rtm:
                            if c_r not in df_ath_all.columns:
                                df_ath_all[c_r] = 0
                        df_ath_all[col_rtm] = df_ath_all[col_rtm].apply(pd.to_numeric, errors='coerce').fillna(0)

                        readiness_bt_configs = [
                            (
                                "Before Tomorrow (Acute 2 Days)",
                                2,
                                tr("BEFORE TOMORROW — CARICO ACUTO (2 GIORNI)", "BEFORE TOMORROW — ACUTE LOAD (2 DAYS)"),
                                "#0f172a",
                                tr("Carico 2 Giorni", "2-Day Load"),
                                tr("Media 28 gg (blocchi 2 gg)", "28d Baseline Avg (2d blocks)"),
                                tr("Finestra Acuta (2 gg)", "Acute Window (2d)"),
                                tr("vs media 2 gg", "vs 2d avg"),
                            ),
                            (
                                "Before Tomorrow (Chronic 7 Days)",
                                7,
                                tr("BEFORE TOMORROW — CARICO CRONICO (7 GIORNI)", "BEFORE TOMORROW — CHRONIC LOAD (7 DAYS)"),
                                "#0ea5e9",
                                tr("Carico 7 Giorni", "7-Day Load"),
                                tr("Media 4 Settimane (28 gg / 7 gg)", "4-Week Baseline Avg (28d / 7d)"),
                                tr("Finestra Settimanale (7 gg)", "Weekly Window (7d)"),
                                tr("vs media 7 gg", "vs 7d avg"),
                            ),
                        ]

                        for report_type, days_window, title_bn, accent_col, lbl_ac_col, lbl_ch_col, lbl_ctx_ac, lbl_vs_txt in readiness_bt_configs:
                            if report_type in report_abilitati:
                                window_start = target_date - timedelta(days=days_window - 1)
                                baseline_end = window_start - timedelta(days=1)
                                baseline_start = baseline_end - timedelta(days=27)

                                mask_window = (df_ath_all['Date_obj'] >= window_start) & (df_ath_all['Date_obj'] <= target_date)
                                mask_baseline = (df_ath_all['Date_obj'] >= baseline_start) & (df_ath_all['Date_obj'] <= baseline_end)

                                val_window = df_ath_all[mask_window][col_rtm].sum().fillna(0)
                                df_base = df_ath_all[mask_baseline]

                                blocchi_disponibili = calcola_blocchi_baseline(df_ath_all, baseline_end, days_window)

                                val_avg = (df_base[col_rtm].sum() / blocchi_disponibili).fillna(0) if not df_base.empty else pd.Series(0.0, index=col_rtm)

                                str_win_r = f"{window_start.strftime('%d/%m/%Y')} - {target_date.strftime('%d/%m/%Y')}"
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
                                    chart_key=f"hex_sess_readiness_{days_window}_{sessione_selezionata}",
                                    title_banner=title_bn,
                                    title_accent=accent_col,
                                )
                                st.markdown("<div style='height: 18px;'></div>", unsafe_allow_html=True)
