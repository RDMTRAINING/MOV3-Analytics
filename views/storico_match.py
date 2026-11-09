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
    render_print_header,
    render_page_header,
    render_meta_bar,
    render_action_bar,
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
    riepilogo_match,
    acwr_pre_match,
    stato_acwr,
    etichetta_scostamento,
    render_athlete_hero_strip,
    frase_riepilogo,
    card_kpi,
    delta_puro,
    delta_confronto,
    get_atleti_associati,
    get_tutti_gli_atleti,
    slugify_name,
    acwr_zone_meta,
    render_pct_progress_bar,
    render_pct_badge_cell,
    render_executive_chart_header,
)
from pdf_generator import (
    crea_pdf_m0v3,
    crea_pdf_sessione_m0v3,
    crea_pdf_weekly_m0v3,
    crea_pdf_storico_m0v3,
    crea_pdf_medie_m0v3,
)

def render_storico_match(t):
    render_page_header(
        tr("Storico Match", "Match History"),
        tr("Analizza l'andamento e la timeline storica delle prestazioni in partita.", "Analyze historical match performance trends and timeline."),
        "HISTORICAL TIMELINE"
    )

    df_storico = load_local_database()
    if df_storico.empty: st.warning(t['am_no_db']); return

    if st.session_state['role'] != 'Super-Admin':
        atleti_consentiti = get_atleti_associati(st.session_state['user'].id)
        if not atleti_consentiti: st.warning(t['up_no_atl']); return
        df_storico = df_storico[df_storico['Players'].isin(atleti_consentiti)]

    # Prendiamo solo i Match (escludendo le simulazioni se vogliamo solo dati reali)
    df_match = df_storico[(df_storico['Tipologia Sessione'].astype(str).str.lower() == 'match') & (df_storico['Dato_Simulato'] == False)].copy()
    if df_match.empty: st.warning(t['am_no_match']); return

    giocatori_disponibili = df_match['Players'].dropna().unique().tolist()
    glob_ath = st.session_state.get('selected_athlete')
    if glob_ath in giocatori_disponibili:
        giocatore_selezionato = glob_ath
    elif 'storico_match_sel_player' in st.session_state and st.session_state['storico_match_sel_player'] in giocatori_disponibili:
        giocatore_selezionato = st.session_state['storico_match_sel_player']
    else:
        giocatore_selezionato = giocatori_disponibili[0]
    st.session_state['storico_match_sel_player'] = giocatore_selezionato

    st.markdown(f'<h3 class="no-print" style="margin-top:0px;">{tr("Filtri Timeline Storica", "Historical Timeline Filters")}</h3>', unsafe_allow_html=True)
    col_f1, col_f2, col_f3 = st.columns([1.2, 1.2, 1.4])
    with col_f1:
        data_inizio_timeline = st.date_input(tr("Mostra i Match a partire dal:", "Show Matches starting from:"), value=pd.Timestamp.today().date() - timedelta(days=90))
    
    df_match = df_match[df_match['Players'] == giocatore_selezionato]

    superfici_disponibili_hist = sorted([
        str(s).strip() for s in df_match['Tipologia Campo'].dropna().unique()
        if str(s).strip() and str(s).lower() not in ['nan', '0', 'n/d']
    ])
    lbl_all_sup_h = tr("Tutte le Superfici", "All Surfaces")
    opzioni_sup_h = [lbl_all_sup_h] + superfici_disponibili_hist
    with col_f2:
        filtro_superficie_hist = st.selectbox(
            tr("Filtro Superficie", "Surface Filter"),
            opzioni_sup_h,
            index=0,
            key="widget_surface_hist"
        )

    with col_f3:
        st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)
        norm_60_active = st.toggle(
            tr("Densità 60m (Normalizza / 60 min)", "60m Density (Norm / 60 min)"),
            value=False,
            key="toggle_norm_60_hist",
            help=tr("Normalizza i volumi match a 60 minuti di gioco per confrontare match di durata diversa", "Normalizes match volumes to 60 minutes of playing time")
        )

    # Striscia Compatta Identità Atleta MOV3 con tag timeline
    dt_tl_fmt = data_inizio_timeline.strftime('%d/%m/%Y') if hasattr(data_inizio_timeline, 'strftime') else str(data_inizio_timeline)
    lbl_tl_tag = f"{tr('Timeline dal', 'Timeline from')}: {dt_tl_fmt}"
    extra_badges_h = [lbl_tl_tag]
    if filtro_superficie_hist != lbl_all_sup_h:
        extra_badges_h.append(f"{tr('Superficie', 'Surface')}: {filtro_superficie_hist}")
    if norm_60_active:
        extra_badges_h.append(f"<i class='bi bi-clock-history'></i> {tr('Densità 60m', '60m Density')}")
    render_athlete_hero_strip(giocatore_selezionato, df_atleta=df_match, extra_badges=extra_badges_h)

    if st.session_state['role'] == 'Super-Admin': report_abilitati = CATALOGO_REPORT.get("Storico Match", [])
    else:
        try:
            res_rep = supabase.table('moduli_report').select('nome_report').eq('profilo_id', st.session_state['user'].id).eq('area', 'Storico Match').execute()
            report_abilitati = [r['nome_report'] for r in res_rep.data] if res_rep.data else []
        except: report_abilitati = []

    if any(rep in report_abilitati for rep in ["Volume Match Timeline", "Intensità Match Timeline", "Work Rate Timeline", "GPS Data Timeline", "Indici Compositi (Volume & Work Rate)", "Record Storici Match"]):
        
        df_match['Date_obj'] = pd.to_datetime(df_match['Date'], dayfirst=True, errors='coerce')
        df_match_sorted = df_match.dropna(subset=['Date_obj']).sort_values('Date_obj').copy()
        df_timeline = df_match_sorted[df_match_sorted['Date_obj'].dt.date >= data_inizio_timeline].copy()

        if filtro_superficie_hist != lbl_all_sup_h:
            df_timeline = df_timeline[df_timeline['Tipologia Campo'].astype(str).str.strip().str.lower() == filtro_superficie_hist.strip().lower()].copy()

        if df_timeline.empty:
            msg_empty = tr(
                f"Nessun match trovato per {giocatore_selezionato} a partire dal {data_inizio_timeline.strftime('%d/%m/%Y')} con i filtri selezionati.",
                f"No matches found for {giocatore_selezionato} starting from {data_inizio_timeline.strftime('%d/%m/%Y')} with selected filters."
            )
            st.warning(msg_empty)
        else:
            opzioni_sub_hist = {
                tr("Tutte le Sottoaree (Completo)", "All Sub-areas (Full)"): "Tutte",
                tr("1. Volumi & Intensità", "1. Volumes & Intensity"): "Volumi_Intensita",
                tr("2. Work Rate & Indici", "2. Work Rate & Indices"): "Work_Rate_Indici",
                tr("3. Dati GPS Outdoor", "3. Outdoor GPS Data"): "Dati_GPS",
                tr("4. Record Storici", "4. Historical Records"): "Record_Storici"
            }
            def _gen_pdf_hist(codice_sub_h):
                col_tl_pdf = ['Minuti', 'Training Load', 'Azioni Int. IMU >2', 'Azioni Int. IMU >10', 'TL_High', 'High Accel IMU', 'High Decel IMU', 'DISTANCE', 'HML Distance >25.5W', 'VHML Distance >50W']
                df_tl_pdf = df_timeline.copy()
                df_tl_pdf[col_tl_pdf] = df_tl_pdf[col_tl_pdf].apply(pd.to_numeric, errors='coerce').fillna(0)
                df_tl_pdf['TL/min'] = df_tl_pdf.apply(lambda row: row['Training Load']/row['Minuti'] if row['Minuti'] > 0 else 0, axis=1)
                df_tl_pdf['TL/min'] = df_tl_pdf.apply(lambda row: row['Training Load']/row['Minuti'] if row['Minuti'] > 0 else 0, axis=1)
                df_tl_pdf['TL_High/min'] = df_tl_pdf.apply(lambda row: row['TL_High']/row['Minuti'] if row['Minuti'] > 0 else 0, axis=1)
                df_tl_pdf['Acc/min'] = df_tl_pdf.apply(lambda row: row['High Accel IMU']/row['Minuti'] if row['Minuti'] > 0 else 0, axis=1)
                df_tl_pdf['Dec/min'] = df_tl_pdf.apply(lambda row: row['High Decel IMU']/row['Minuti'] if row['Minuti'] > 0 else 0, axis=1)
                df_tl_pdf['Az2/min'] = df_tl_pdf.apply(lambda row: row['Azioni Int. IMU >2']/row['Minuti'] if row['Minuti'] > 0 else 0, axis=1)
                df_tl_pdf['Mech/min'] = df_tl_pdf.apply(lambda row: (row['High Accel IMU'] + row['High Decel IMU'])/row['Minuti'] if row['Minuti'] > 0 else 0, axis=1)
                return crea_pdf_storico_m0v3(
                    giocatore_selezionato, data_inizio_timeline.strftime('%d/%m/%Y'), df_tl_pdf, sottoarea=codice_sub_h
                )

            render_action_bar(
                meta_items=[
                    (tr("Atleta", "Athlete"), giocatore_selezionato),
                    (tr("Periodo", "Period"), tr(f"Dal {data_inizio_timeline.strftime('%d/%m/%Y')} ad oggi", f"From {data_inizio_timeline.strftime('%d/%m/%Y')} to today"))
                ],
                pdf_options=opzioni_sub_hist,
                pdf_key="hist",
                generate_fn=_gen_pdf_hist,
                filename_fn=lambda codice_sub_h: f"M0V3_StoricoMatch_{codice_sub_h}_{slugify_name(giocatore_selezionato)}.pdf"
            )
            

            is_first_report = True
            render_print_header(is_first_report, giocatore_selezionato, f"Dal {data_inizio_timeline.strftime('%d/%m/%Y')} ad Oggi", "Timeline Storica Match", "Vari", "Vari", 0)
            
            col_timeline = ['Minuti', 'Training Load', 'Azioni Int. IMU >2', 'Azioni Int. IMU >10', 'TL_High', 'High Accel IMU', 'High Decel IMU', 'DISTANCE', 'HML Distance >25.5W', 'VHML Distance >50W']
            df_timeline[col_timeline] = df_timeline[col_timeline].apply(pd.to_numeric, errors='coerce').fillna(0)

            df_timeline['TL/min'] = df_timeline.apply(lambda row: row['Training Load']/row['Minuti'] if row['Minuti'] > 0 else 0, axis=1)
            df_timeline['TL_High/min'] = df_timeline.apply(lambda row: row['TL_High']/row['Minuti'] if row['Minuti'] > 0 else 0, axis=1)
            df_timeline['Acc/min'] = df_timeline.apply(lambda row: row['High Accel IMU']/row['Minuti'] if row['Minuti'] > 0 else 0, axis=1)
            df_timeline['Dec/min'] = df_timeline.apply(lambda row: row['High Decel IMU']/row['Minuti'] if row['Minuti'] > 0 else 0, axis=1)
            df_timeline['Az2/min'] = df_timeline.apply(lambda row: row['Azioni Int. IMU >2']/row['Minuti'] if row['Minuti'] > 0 else 0, axis=1)
            df_timeline['Mech/min'] = df_timeline.apply(lambda row: (row['High Accel IMU'] + row['High Decel IMU'])/row['Minuti'] if row['Minuti'] > 0 else 0, axis=1)

            if norm_60_active:
                df_timeline['Training Load'] = df_timeline.apply(lambda r: (r['Training Load'] / r['Minuti'] * 60) if r['Minuti'] > 0 else 0, axis=1)
                df_timeline['TL_High'] = df_timeline.apply(lambda r: (r['TL_High'] / r['Minuti'] * 60) if r['Minuti'] > 0 else 0, axis=1)
                df_timeline['High Accel IMU'] = df_timeline.apply(lambda r: (r['High Accel IMU'] / r['Minuti'] * 60) if r['Minuti'] > 0 else 0, axis=1)
                df_timeline['High Decel IMU'] = df_timeline.apply(lambda r: (r['High Decel IMU'] / r['Minuti'] * 60) if r['Minuti'] > 0 else 0, axis=1)
                df_timeline['Azioni Int. IMU >2'] = df_timeline.apply(lambda r: (r['Azioni Int. IMU >2'] / r['Minuti'] * 60) if r['Minuti'] > 0 else 0, axis=1)
                df_timeline['Azioni Int. IMU >10'] = df_timeline.apply(lambda r: (r['Azioni Int. IMU >10'] / r['Minuti'] * 60) if r['Minuti'] > 0 else 0, axis=1)
                df_timeline['DISTANCE'] = df_timeline.apply(lambda r: (r['DISTANCE'] / r['Minuti'] * 60) if r['Minuti'] > 0 else 0, axis=1)
                df_timeline['HML Distance >25.5W'] = df_timeline.apply(lambda r: (r['HML Distance >25.5W'] / r['Minuti'] * 60) if r['Minuti'] > 0 else 0, axis=1)
                df_timeline['VHML Distance >50W'] = df_timeline.apply(lambda r: (r['VHML Distance >50W'] / r['Minuti'] * 60) if r['Minuti'] > 0 else 0, axis=1)

            def render_exec_spline_chart(df, y_col, color, title, chart_key, decimals=0, unit="", avg_override=None):
                vals = pd.to_numeric(df[y_col], errors='coerce').fillna(0)
                max_val = float(vals.max()) if not vals.empty else 0.0
                avg_val = float(avg_override) if avg_override is not None else (float(vals.mean()) if not vals.empty else 0.0)
                last_val = float(vals.iloc[-1]) if not vals.empty else 0.0
                y_max = max(max_val, avg_val) * 1.28 if max(max_val, avg_val) > 0 else 10.0

                u_sfx = f" {unit}" if unit else ""
                fmt_fn = (lambda v: f"{v:.0f}{u_sfx}") if decimals == 0 else (lambda v: f"{v:.{decimals}f}{u_sfx}")

                x_labels = df['Date'].astype(str) + " - " + df['Session'].astype(str)
                text_vals = vals.round(0).astype(int).astype(str) if decimals == 0 else vals.map(lambda x: f"{x:.{decimals}f}")

                fig = go.Figure()
                if avg_val > 0:
                    avg_lbl_txt = tr("Media Periodo", "Period Avg")
                    fig.add_hline(
                        y=avg_val,
                        line_dash="dash",
                        line_color="#64748b",
                        line_width=1.5,
                        annotation_text=f"{avg_lbl_txt}: {fmt_fn(avg_val)}",
                        annotation_position="top right",
                        annotation_font=dict(size=10, color="#475569", family="Inter")
                    )
                fig.add_trace(go.Scatter(
                    x=x_labels, y=vals, mode='lines+markers+text',
                    line=dict(shape='spline', width=3.5, color=color),
                    marker=dict(size=9, color='white', line=dict(width=3, color=color)),
                    text=text_vals, textposition='top center', textfont=dict(size=12, color='#0f172a', weight='bold'),
                    name=title, cliponaxis=False
                ))
                fig.update_layout(
                    height=370, margin=dict(l=10, r=10, t=20, b=45),
                    xaxis=dict(showgrid=False, tickangle=35, tickfont=dict(size=11, color='#64748b')),
                    yaxis=dict(showgrid=True, gridcolor='#f1f5f9', range=[0, y_max], zeroline=False, tickfont=dict(color='#64748b')),
                    plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                    showlegend=False
                )

                lbl_p_avg = tr("Media Periodo", "Period Avg")
                lbl_p_max = tr("Picco Record", "Peak Record")
                lbl_p_last = tr("Ultimo Match", "Latest Match")
                lbl_p_cnt = tr("Match Analizzati", "Matches")
                with st.container(border=True):
                    st.markdown(render_executive_chart_header(
                        title,
                        pills=[
                            (lbl_p_cnt, f"{len(df)}", "#94a3b8"),
                            (lbl_p_avg, fmt_fn(avg_val), "#38bdf8"),
                            (lbl_p_max, fmt_fn(max_val), "#f59e0b"),
                            (lbl_p_last, fmt_fn(last_val), "#10b981"),
                        ],
                        accent=color
                    ), unsafe_allow_html=True)
                    st.plotly_chart(fig, use_container_width=True, key=chart_key)

            # --- TABS DI NAVIGAZIONE STORICO ---
            lbl_sm_vol = tr("Volumi & Intensità", "Volumes & Intensity")
            lbl_sm_wr = tr("Work Rate & Indici", "Work Rate & Indices")
            lbl_sm_gps = tr("Dati GPS", "GPS Data")
            lbl_sm_rec = tr("Record Storici", "Historical Records")
            active_sm_tab = render_tab_navigation([lbl_sm_vol, lbl_sm_wr, lbl_sm_gps, lbl_sm_rec], key="nav_storico_match")

            if active_sm_tab == lbl_sm_vol:
                if "Volume Match Timeline" in report_abilitati:
                    lbl_vol_sec = tr("Volume Match — Timeline Storica (Normalizzata a 60 Minuti)", "Match Volume — Historical Timeline (Normalized to 60 Min)") if norm_60_active else tr("Volume Match — Timeline Storica", "Match Volume — Historical Timeline")
                    st.markdown(f"<h3 style='color:#0f172a;'>{lbl_vol_sec}</h3>", unsafe_allow_html=True)
                    render_exec_spline_chart(df_timeline, 'Minuti', '#10b981', tr('Tempo (Durata in min)', 'Duration (min)'), "vol_1", decimals=0, unit="min")
                    lbl_tl_plot = "Training Load (/60 min)" if norm_60_active else "Training Load"
                    lbl_az2_plot = tr('Azioni Intense >2" (/60 min)', 'Intense Actions >2" (/60 min)') if norm_60_active else tr('Azioni Intense >2"', 'Intense Actions >2"')
                    render_exec_spline_chart(df_timeline, 'Training Load', '#0ea5e9', lbl_tl_plot, "vol_2", decimals=0, unit="AU")
                    render_exec_spline_chart(df_timeline, 'Azioni Int. IMU >2', '#8b5cf6', lbl_az2_plot, "vol_3", decimals=0)

                if "Intensità Match Timeline" in report_abilitati:
                    lbl_int_sec = tr("Intensità Match — Timeline Storica (Normalizzata a 60 Minuti)", "Match Intensity — Historical Timeline (Normalized to 60 Min)") if norm_60_active else tr("Intensità Match — Timeline Storica", "Match Intensity — Historical Timeline")
                    st.markdown(f"<h3 style='color:#0f172a; margin-top:20px;'>{lbl_int_sec}</h3>", unsafe_allow_html=True)
                    lbl_tlh_plot = "Training Load High (/60 min)" if norm_60_active else "Training Load High"
                    lbl_acc_plot = "High Accelerations IMU (/60 min)" if norm_60_active else "High Accelerations IMU"
                    lbl_dec_plot = "High Decelerations IMU (/60 min)" if norm_60_active else "High Decelerations IMU"
                    render_exec_spline_chart(df_timeline, 'TL_High', '#ef4444', lbl_tlh_plot, "int_1", decimals=0, unit="AU")
                    render_exec_spline_chart(df_timeline, 'High Accel IMU', '#10b981', lbl_acc_plot, "int_2", decimals=0)
                    render_exec_spline_chart(df_timeline, 'High Decel IMU', '#f59e0b', lbl_dec_plot, "int_3", decimals=0)

            elif active_sm_tab == lbl_sm_wr:
                if "Work Rate Timeline" in report_abilitati:
                    lbl_wr_sec = tr("Work Rate (5 Parametri Ufficiali al Minuto) — Timeline Storica", "Work Rate (5 Official Per-Minute Parameters) — Historical Timeline")
                    st.markdown(f"<h3 style='color:#0f172a;'>{lbl_wr_sec}</h3>", unsafe_allow_html=True)
                    sum_min_tl = float(df_timeline['Minuti'].sum())
                    avg_tl_pm_h = (float(df_timeline['Training Load'].sum()) / sum_min_tl) if sum_min_tl > 0 else 0.0
                    avg_tlh_pm_h = (float(df_timeline['TL_High'].sum()) / sum_min_tl) if sum_min_tl > 0 else 0.0
                    avg_acc_pm_h = (float(df_timeline['High Accel IMU'].sum()) / sum_min_tl) if sum_min_tl > 0 else 0.0
                    avg_dec_pm_h = (float(df_timeline['High Decel IMU'].sum()) / sum_min_tl) if sum_min_tl > 0 else 0.0
                    avg_az2_pm_h = (float(df_timeline['Azioni Int. IMU >2'].sum()) / sum_min_tl) if sum_min_tl > 0 else 0.0

                    render_exec_spline_chart(df_timeline, 'TL/min', '#0ea5e9', 'Training Load / min', "wr_1", decimals=1, unit="AU/m", avg_override=avg_tl_pm_h)
                    render_exec_spline_chart(df_timeline, 'TL_High/min', '#ef4444', 'Training Load High / min', "wr_2", decimals=2, unit="AU/m", avg_override=avg_tlh_pm_h)
                    render_exec_spline_chart(df_timeline, 'Acc/min', '#10b981', 'High Accelerations IMU / min', "wr_3", decimals=2, unit="act/m", avg_override=avg_acc_pm_h)
                    render_exec_spline_chart(df_timeline, 'Dec/min', '#f59e0b', 'High Decelerations IMU / min', "wr_4", decimals=2, unit="act/m", avg_override=avg_dec_pm_h)
                    render_exec_spline_chart(df_timeline, 'Az2/min', '#8b5cf6', tr('Azioni Intense >2" / min', 'Intense Actions >2" / min'), "wr_5", decimals=2, unit="act/m", avg_override=avg_az2_pm_h)

                if "Indici Compositi (Volume & Work Rate)" in report_abilitati:
                    lbl_idx_sec = tr("Indici Compositi (Base 100)", "Composite Indices (Base 100)")
                    st.markdown(f"<h3 style='color:#0f172a; margin-top:20px;'>{lbl_idx_sec}</h3>", unsafe_allow_html=True)

                    try:
                        res_pesi = supabase.table('impostazioni_pesi').select('pesi').eq('profilo_id', st.session_state['user'].id).execute()
                        pesi = res_pesi.data[0]['pesi'] if res_pesi.data else {}
                    except: pesi = {}

                    w_min = float(pesi.get('w_min', 1.0)); w_tl = float(pesi.get('w_tl', 1.0)); w_az2 = float(pesi.get('w_az2', 1.0)); w_mech = float(pesi.get('w_mech', 1.0))
                    w_tlmin = float(pesi.get('w_tlmin', 1.0)); w_tlhmin = float(pesi.get('w_tlhmin', 1.0))
                    w_accmin = float(pesi.get('w_accmin', pesi.get('w_mechmin', 1.0)))
                    w_decmin = float(pesi.get('w_decmin', pesi.get('w_mechmin', 1.0)))
                    w_az2min = float(pesi.get('w_az2min', 1.0))

                    with st.expander(tr("Configurazione Pesi Indici (Salvataggio su Profilo)", "Index Weights Configuration (Saved to Profile)"), expanded=False):
                        st.info(tr("Imposta un valore da 0 a 10 per l'importanza di ogni metrica. Il sistema bilancerà automaticamente il totale al 100%.", "Set a value from 0 to 10 for each metric's weight. The system will automatically normalize the total to 100%."))
                        with st.form("form_pesi"):
                            c_v, c_w = st.columns(2)
                            with c_v:
                                st.markdown(f"**{tr('Composizione Indice Volume', 'Volume Index Composition')}**")
                                nw_min = st.slider(tr("Importanza Tempo (Minuti)", "Duration Weight (Minutes)"), 0.0, 10.0, w_min, 0.5)
                                nw_tl = st.slider(tr("Importanza Training Load", "Training Load Weight"), 0.0, 10.0, w_tl, 0.5)
                                nw_az2 = st.slider(tr("Importanza Azioni >2s", "Actions >2s Weight"), 0.0, 10.0, w_az2, 0.5)
                                nw_mech = st.slider(tr("Importanza Azioni Meccaniche (Acc+Dec)", "Mechanical Actions Weight (Acc+Dec)"), 0.0, 10.0, w_mech, 0.5)
                            with c_w:
                                st.markdown(f"**{tr('Composizione Indice Work Rate', 'Work Rate Index Composition')}**")
                                nw_tlmin = st.slider(tr("Importanza TL / min", "TL / min Weight"), 0.0, 10.0, w_tlmin, 0.5)
                                nw_tlhmin = st.slider(tr("Importanza TL High / min", "TL High / min Weight"), 0.0, 10.0, w_tlhmin, 0.5)
                                nw_accmin = st.slider(tr("Importanza High Acc / min", "High Acc / min Weight"), 0.0, 10.0, w_accmin, 0.5)
                                nw_decmin = st.slider(tr("Importanza High Dec / min", "High Dec / min Weight"), 0.0, 10.0, w_decmin, 0.5)
                                nw_az2min = st.slider(tr("Importanza Azioni >2s / min", "Actions >2s / min Weight"), 0.0, 10.0, w_az2min, 0.5)
                                
                            if st.form_submit_button(tr("Salva Impostazioni Pesi", "Save Weight Settings"), type="primary"):
                                nuovi_pesi = {'w_min': nw_min, 'w_tl': nw_tl, 'w_az2': nw_az2, 'w_mech': nw_mech, 'w_tlmin': nw_tlmin, 'w_tlhmin': nw_tlhmin, 'w_accmin': nw_accmin, 'w_decmin': nw_decmin, 'w_az2min': nw_az2min}
                                try:
                                    supabase.table('impostazioni_pesi').upsert({"profilo_id": st.session_state['user'].id, "pesi": nuovi_pesi}).execute()
                                    st.success(tr("Pesi aggiornati con successo!", "Weights updated successfully!"))
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"DB Error: {e}")

                    df_ath = df_match.copy()
                    df_ath[col_timeline] = df_ath[col_timeline].apply(pd.to_numeric, errors='coerce').fillna(0)
                    df_ath['Mech_Tot'] = df_ath['High Accel IMU'] + df_ath['High Decel IMU']
                    df_ath['TL/min'] = df_ath.apply(lambda r: r['Training Load']/r['Minuti'] if r['Minuti']>0 else 0, axis=1)
                    df_ath['TL_High/min'] = df_ath.apply(lambda r: r['TL_High']/r['Minuti'] if r['Minuti']>0 else 0, axis=1)
                    df_ath['Acc/min'] = df_ath.apply(lambda r: r['High Accel IMU']/r['Minuti'] if r['Minuti']>0 else 0, axis=1)
                    df_ath['Dec/min'] = df_ath.apply(lambda r: r['High Decel IMU']/r['Minuti'] if r['Minuti']>0 else 0, axis=1)
                    df_ath['Az2/min'] = df_ath.apply(lambda r: r['Azioni Int. IMU >2']/r['Minuti'] if r['Minuti']>0 else 0, axis=1)

                    max_minuti = df_ath['Minuti'].max() if df_ath['Minuti'].max() > 0 else 1
                    max_tl = df_ath['Training Load'].max() if df_ath['Training Load'].max() > 0 else 1
                    max_az = df_ath['Azioni Int. IMU >2'].max() if df_ath['Azioni Int. IMU >2'].max() > 0 else 1
                    max_mech = df_ath['Mech_Tot'].max() if df_ath['Mech_Tot'].max() > 0 else 1
                    max_tlmin = df_ath['TL/min'].max() if df_ath['TL/min'].max() > 0 else 1
                    max_tlhmin = df_ath['TL_High/min'].max() if df_ath['TL_High/min'].max() > 0 else 1
                    max_accmin = df_ath['Acc/min'].max() if df_ath['Acc/min'].max() > 0 else 1
                    max_decmin = df_ath['Dec/min'].max() if df_ath['Dec/min'].max() > 0 else 1
                    max_az2min = df_ath['Az2/min'].max() if df_ath['Az2/min'].max() > 0 else 1

                    tot_w_vol = w_min + w_tl + w_az2 + w_mech if (w_min + w_tl + w_az2 + w_mech) > 0 else 1
                    tot_w_wr = (w_tlmin + w_tlhmin + w_accmin + w_decmin + w_az2min) if (w_tlmin + w_tlhmin + w_accmin + w_decmin + w_az2min) > 0 else 1

                    df_timeline['Mech_Tot'] = df_timeline['High Accel IMU'] + df_timeline['High Decel IMU']
                    df_timeline['Acc/min'] = df_timeline.apply(lambda r: r['High Accel IMU']/r['Minuti'] if r['Minuti']>0 else 0, axis=1)
                    df_timeline['Dec/min'] = df_timeline.apply(lambda r: r['High Decel IMU']/r['Minuti'] if r['Minuti']>0 else 0, axis=1)
                    df_timeline['Az2/min'] = df_timeline.apply(lambda r: r['Azioni Int. IMU >2']/r['Minuti'] if r['Minuti']>0 else 0, axis=1)
                    
                    df_timeline['Vol_Index'] = (((df_timeline['Minuti']/max_minuti)*100 * w_min) + ((df_timeline['Training Load']/max_tl)*100 * w_tl) + ((df_timeline['Azioni Int. IMU >2']/max_az)*100 * w_az2) + ((df_timeline['Mech_Tot']/max_mech)*100 * w_mech)) / tot_w_vol
                    df_timeline['WR_Index'] = (((df_timeline['TL/min']/max_tlmin)*100 * w_tlmin) + ((df_timeline['TL_High/min']/max_tlhmin)*100 * w_tlhmin) + ((df_timeline['Acc/min']/max_accmin)*100 * w_accmin) + ((df_timeline['Dec/min']/max_decmin)*100 * w_decmin) + ((df_timeline['Az2/min']/max_az2min)*100 * w_az2min)) / tot_w_wr

                    render_exec_spline_chart(df_timeline, 'Vol_Index', '#8b5cf6', tr('Indice Composito: Volume Match (Base 100)', 'Composite Index: Match Volume (Base 100)'), "idx_1", decimals=1, unit="pts")
                    render_exec_spline_chart(df_timeline, 'WR_Index', '#f59e0b', tr('Indice Composito: Work Rate Match (Base 100)', 'Composite Index: Match Work Rate (Base 100)'), "idx_2", decimals=1, unit="pts")

            elif active_sm_tab == lbl_sm_gps:
                if "GPS Data Timeline" in report_abilitati:
                    lbl_gps_sec = tr("Dati GPS Match (Solo Outdoor) — Timeline Storica (Normalizzata a 60 Minuti)", "Match GPS Data (Outdoor Only) — Historical Timeline (Normalized to 60 Min)") if norm_60_active else tr("Dati GPS Match (Solo Outdoor) — Timeline Storica", "Match GPS Data (Outdoor Only) — Historical Timeline")
                    st.markdown(f"<h3 style='color:#0f172a;'>{lbl_gps_sec}</h3>", unsafe_allow_html=True)
                    
                    df_gps = df_timeline[df_timeline['Ambiente'].astype(str).str.lower() != 'indoor'].copy()
                    
                    if df_gps.empty:
                        st.info(tr("Nessun dato GPS disponibile nel periodo selezionato (tutte le sessioni sono Indoor o mancano dati storici).", "No GPS data available in the selected period (all sessions are Indoor or historical data is missing)."))
                    else:
                        lbl_dist = tr("Distanza Totale (/60 min)", "Total Distance (/60 min)") if norm_60_active else tr("Distanza Totale (m)", "Total Distance (m)")
                        lbl_hml = "HML Distance >25.5W (/60 min)" if norm_60_active else "HML Distance >25.5W (m)"
                        lbl_vhml = "VHML Distance >50W (/60 min)" if norm_60_active else "VHML Distance >50W (m)"
                        render_exec_spline_chart(df_gps, 'DISTANCE', '#0ea5e9', lbl_dist, "gps_1", decimals=0, unit="m")
                        render_exec_spline_chart(df_gps, 'HML Distance >25.5W', '#f59e0b', lbl_hml, "gps_2", decimals=0, unit="m")
                        render_exec_spline_chart(df_gps, 'VHML Distance >50W', '#ef4444', lbl_vhml, "gps_3", decimals=0, unit="m")

            elif active_sm_tab == lbl_sm_rec:
                if "Record Storici Match" in report_abilitati:
                    metriche_record = [
                        (tr("Durata Massima (min)", "Highest Duration (min)"), "Minuti", False, 0, "VOLUME", "#f59e0b"),
                        ("Highest Training Load", "Training Load", False, 0, "VOLUME", "#f59e0b"),
                        ("Highest Training Load High", "TL_High", False, 0, "HIGH INTENSITY", "#ef4444"),
                        (tr('Azioni Intense >2" (Picco)', 'Highest Intense Actions >2"'), "Azioni Int. IMU >2", False, 0, "VOLUME", "#f59e0b"),
                        (tr('Azioni Intense >10" (Picco)', 'Highest Intense Actions >10"'), "Azioni Int. IMU >10", False, 0, "VOLUME", "#f59e0b"),
                        ("Highest Accelerations IMU", "High Accel IMU", False, 0, "HIGH INTENSITY", "#ef4444"),
                        ("Highest Decelerations IMU", "High Decel IMU", False, 0, "HIGH INTENSITY", "#ef4444"),
                        (tr("Distanza Massima GPS (m)", "Highest Distance GPS (m)"), "DISTANCE", True, 0, "GPS OUTDOOR", "#0ea5e9"),
                        ("Highest HML >25.5W (m)", "HML Distance >25.5W", True, 0, "GPS OUTDOOR", "#0ea5e9"),
                        ("Highest VHML >50W (m)", "VHML Distance >50W", True, 0, "GPS OUTDOOR", "#0ea5e9")
                    ]

                    lbl_rec_banner = tr("BEST DATA HISTORY — RECORD STORICI MATCH NEL PERIODO", "BEST DATA HISTORY — MATCH HISTORICAL RECORDS IN PERIOD")
                    lbl_rec_sub = tr(f"Atleta: {giocatore_selezionato} • Dal {data_inizio_timeline.strftime('%d/%m/%Y')}", f"Athlete: {giocatore_selezionato} • From {data_inizio_timeline.strftime('%d/%m/%Y')}")
                    th_r_p = tr("Parametro", "Parameter")
                    th_r_max = tr("Record", "Record")
                    th_r_avg = tr("Media Periodo", "Period Avg")
                    th_r_pct = tr("% vs Media (Scostamento)", "% vs Avg (Delta)")
                    th_r_bar = tr("Confronto vs Media (100%)", "Comparison vs Avg (100%)")
                    th_r_dt = tr("Data & Sessione Record", "Record Date & Session")
                    lbl_vs_per = tr("vs media", "vs avg")

                    html_table = (
                        "<div style='background:#ffffff; border-radius:14px; border:1px solid #e2e8f0; box-shadow:0 4px 12px -2px rgba(15,23,42,0.05); overflow:hidden; margin-top:10px; margin-bottom:20px; font-family:\"Inter\",sans-serif;'>"
                        "<div style='background:linear-gradient(135deg, #0f172a 0%, #1e293b 100%); padding:14px 20px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;'>"
                        "<div style='display:flex; align-items:center; gap:10px;'>"
                        "<span style='width:8px; height:8px; border-radius:50%; background:#f59e0b; display:inline-block;'></span>"
                        f"<span style='color:#ffffff; font-size:13px; font-weight:800; text-transform:uppercase; letter-spacing:0.06em;'>{lbl_rec_banner}</span>"
                        "</div>"
                        f"<span style='color:#94a3b8; font-size:11px; font-weight:600;'>{lbl_rec_sub}</span>"
                        "</div>"
                        "<table style='width:100%; border-collapse:collapse;'>"
                        "<thead><tr style='background:#f8fafc; border-bottom:2px solid #e2e8f0;'>"
                        f"<th style='text-align:left; padding:12px 18px; color:#475569; font-size:10.5px; font-weight:800; text-transform:uppercase; letter-spacing:0.06em; width:24%;'>{th_r_p}</th>"
                        f"<th style='text-align:center; padding:12px 10px; color:#0f172a; font-size:10.5px; font-weight:800; text-transform:uppercase; letter-spacing:0.06em; width:12%;'>{th_r_max}</th>"
                        f"<th style='text-align:center; padding:12px 10px; color:#64748b; font-size:10.5px; font-weight:800; text-transform:uppercase; letter-spacing:0.06em; width:12%;'>{th_r_avg}</th>"
                        f"<th style='text-align:center; padding:12px 10px; color:#475569; font-size:10.5px; font-weight:800; text-transform:uppercase; letter-spacing:0.06em; width:18%;'>{th_r_pct}</th>"
                        f"<th style='text-align:left; padding:12px 14px; color:#475569; font-size:10.5px; font-weight:800; text-transform:uppercase; letter-spacing:0.06em; width:16%;'>{th_r_bar}</th>"
                        f"<th style='text-align:right; padding:12px 18px; color:#475569; font-size:10.5px; font-weight:800; text-transform:uppercase; letter-spacing:0.06em; width:18%;'>{th_r_dt}</th>"
                        "</tr></thead><tbody>"
                    )

                    nessun_dato_gps = True
                    row_idx_r = 0

                    for etichetta, colonna, is_gps, dec, cat_tag, cat_col in metriche_record:
                        if colonna not in df_timeline.columns: continue
                            
                        df_calc = df_timeline[df_timeline['Ambiente'].astype(str).str.lower() != 'indoor'].copy() if is_gps else df_timeline.copy()
                        df_calc[colonna] = pd.to_numeric(df_calc[colonna], errors='coerce').fillna(0)
                        
                        if df_calc.empty or df_calc[colonna].sum() == 0: continue
                        if is_gps: nessun_dato_gps = False

                        media_val = float(df_calc[colonna].mean())
                        idx_max = df_calc[colonna].idxmax()
                        val_max = float(df_calc.loc[idx_max, colonna])
                        data_max = str(df_calc.loc[idx_max, 'Date'])
                        sess_max = str(df_calc.loc[idx_max, 'Session'])

                        pct_media = (val_max / media_val * 100.0) if media_val > 0 else 100.0
                        diff_media = pct_media - 100.0
                        val_str = f"{val_max:.0f}" if dec == 0 else f"{val_max:.{dec}f}"
                        avg_str = f"{media_val:.0f}" if dec == 0 else f"{media_val:.{dec}f}"
                        bg_color = "#ffffff" if row_idx_r % 2 == 0 else "#f8fafc"
                        row_idx_r += 1

                        badge_html = render_pct_badge_cell(pct_media, diff_media, True, lbl_vs_per)
                        pbar_html = render_pct_progress_bar(pct_media)

                        riga_html = (
                            f"<tr style='background:{bg_color}; border-bottom:1px solid #f1f5f9;'>"
                            f"<td style='padding:12px 18px;'>"
                            f"<div style='font-weight:700; color:#0f172a; font-size:13.5px;'>{etichetta}</div>"
                            f"<span style='display:inline-block; margin-top:2px; font-size:9px; font-weight:800; color:{cat_col}; background:{cat_col}14; padding:1px 6px; border-radius:4px; letter-spacing:0.05em;'>{cat_tag}</span>"
                            f"</td>"
                            f"<td style='padding:12px 10px; text-align:center; font-size:19px; font-weight:900; color:#0f172a;'>{val_str}</td>"
                            f"<td style='padding:12px 10px; text-align:center; font-size:15px; font-weight:700; color:#64748b;'>{avg_str}</td>"
                            f"<td style='padding:12px 10px; text-align:center;'>{badge_html}</td>"
                            f"<td style='padding:12px 14px;'>{pbar_html}</td>"
                            f"<td style='padding:12px 18px; text-align:right;'>"
                            f"<div style='display:inline-block; background:#f1f5f9; border:1px solid #e2e8f0; border-radius:6px; padding:4px 8px; text-align:right;'>"
                            f"<div style='font-size:11.5px; font-weight:800; color:#0f172a;'>{data_max}</div>"
                            f"<div style='font-size:10px; font-weight:700; color:#475569; text-transform:uppercase;'>{sess_max}</div>"
                            f"</div>"
                            f"</td>"
                            "</tr>"
                        )
                        html_table += riga_html

                    html_table += "</tbody></table></div>"
                    st.markdown(html_table, unsafe_allow_html=True)
                    
                    if nessun_dato_gps:
                        st.info(tr("I record GPS (Distanza, HML, VHML) non sono mostrati perché nel periodo selezionato non ci sono match Outdoor.", "GPS records (Distance, HML, VHML) are not shown because there are no Outdoor matches in the selected period."))
                st.markdown('<hr class="no-print">', unsafe_allow_html=True)

