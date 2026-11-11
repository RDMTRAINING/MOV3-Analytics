import datetime as dt
from datetime import datetime, timedelta, date, time
import numpy as np
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from config import tr, render_page_header, render_tab_navigation, render_action_bar, render_scientific_methodology_box
from pdf_generator import crea_pdf_carico_interno, slugify_name
from utils import (
    supabase,
    load_local_database,
    get_atleti_associati,
    get_tutti_gli_atleti,
    card_kpi,
    render_athlete_hero_strip,
)


def render_carico_interno(t):
    """
    Modulo Coach & Super-Admin: Analisi Carico Interno (sRPE) & Wellness:
    - Incrocio Carico Esterno (GPS) vs Carico Interno (sRPE).
    - Ripartizione sRPE per tipologia seduta (Tennis vs Prep. Fisica vs Gym).
    - Monitoraggio trend Wellness mattutino (Sonno, Fatica, Stress, Umore, DOMS).
    - Tabella storica e audit modifiche dell'atleta.
    """
    user = st.session_state.get('user')
    role = st.session_state.get('role', 'Staff')

    render_page_header(
        tr("Carico Interno & Wellness", "Internal Load & Wellness"),
        tr("Monitoraggio del carico soggettivo (sRPE), incrocio con dati GPS e stato biologico dell'atleta.",
           "Subjective load monitoring (sRPE), GPS cross-referencing and athlete biological status."),
        "INTERNAL LOAD & RECOVERY MONITOR"
    )

    # 1. Parco Atleti Visibili
    df_loc = load_local_database()
    nomi_loc = df_loc['Players'].dropna().unique().tolist() if (not df_loc.empty and 'Players' in df_loc.columns) else []

    if role == 'Super-Admin':
        atleti_db = get_tutti_gli_atleti()
        lista_atleti_nomi = sorted(list(set(atleti_db + nomi_loc)))
    else:
        atleti_db = get_atleti_associati(user.id)
        if atleti_db:
            lista_atleti_nomi = sorted(list(set(atleti_db + [n for n in nomi_loc if n in atleti_db])))
        else:
            lista_atleti_nomi = nomi_loc

    if not lista_atleti_nomi:
        lista_atleti_nomi = ["prova uno"]

    # Recupero anagrafica atleti da Supabase per avere gli ID
    dict_nome_to_id = {}
    dict_id_to_nome = {}
    try:
        res_atleti_db = supabase.table('atleti').select('id, nome, cognome').execute()
        if res_atleti_db.data:
            for a in res_atleti_db.data:
                full_n = f"{a.get('nome', '')} {a.get('cognome', '')}".strip()
                dict_nome_to_id[full_n] = a['id']
                if a.get('nome'):
                    dict_nome_to_id[a.get('nome', '').strip()] = a['id']
                dict_id_to_nome[a['id']] = full_n
    except Exception:
        pass

    atleti_selezionabili = lista_atleti_nomi
    glob_ath = st.session_state.get('selected_athlete')
    if glob_ath in atleti_selezionabili:
        atleta_sel = glob_ath
    elif 'sel_atleta_carico_interno' in st.session_state and st.session_state['sel_atleta_carico_interno'] in atleti_selezionabili:
        atleta_sel = st.session_state['sel_atleta_carico_interno']
    else:
        atleta_sel = atleti_selezionabili[0] if atleti_selezionabili else "prova uno"

    # 2. Barra Filtri Superiore
    opz_periodo = [
        tr("Ultimi 7 giorni", "Last 7 days"),
        tr("Ultimi 14 giorni", "Last 14 days"),
        tr("Ultimi 28 giorni (Microciclo completo)", "Last 28 days (Full Microcycle)"),
        tr("Ultimi 60 giorni", "Last 60 days"),
        tr("Tutto lo storico", "All time history")
    ]
    periodo_sel = st.selectbox(
        tr("Finestra Temporale", "Time Window"),
        opz_periodo,
        index=1,
        key="sel_periodo_carico_interno"
    )
    label_periodo_sel = str(periodo_sel)

    # Striscia Compatta Identità Atleta MOV3 con tag periodo
    lbl_per_tag = f"{tr('Finestra', 'Window')}: {periodo_sel}"
    render_athlete_hero_strip(atleta_sel, extra_badges=[lbl_per_tag])

    atleta_id_sel = dict_nome_to_id.get(atleta_sel)
    if not atleta_id_sel:
        parts = atleta_sel.split(' ', 1)
        nome_p = parts[0]
        cognome_p = parts[1] if len(parts) > 1 else ""
        try:
            chk = supabase.table('atleti').select('id').eq('nome', nome_p).execute()
            if chk.data:
                atleta_id_sel = chk.data[0]['id']
                dict_nome_to_id[atleta_sel] = atleta_id_sel
            else:
                ins = supabase.table('atleti').insert({"nome": nome_p, "cognome": cognome_p}).execute()
                if ins.data:
                    atleta_id_sel = ins.data[0]['id']
                    dict_nome_to_id[atleta_sel] = atleta_id_sel
        except Exception:
            pass

    # Calcolo data limite
    oggi = dt.date.today()
    if periodo_sel == opz_periodo[0]:
        data_inizio = oggi - dt.timedelta(days=7)
    elif periodo_sel == opz_periodo[1]:
        data_inizio = oggi - dt.timedelta(days=14)
    elif periodo_sel == opz_periodo[2]:
        data_inizio = oggi - dt.timedelta(days=28)
    elif periodo_sel == opz_periodo[3]:
        data_inizio = oggi - dt.timedelta(days=60)
    else:
        data_inizio = dt.date(2020, 1, 1)

    data_inizio_str = data_inizio.strftime('%Y-%m-%d')

    # 3. Query Dati da Supabase (Wellness & sRPE)
    try:
        res_w = supabase.table('wellness_mattutino').select('*').eq('atleta_id', atleta_id_sel).gte('data', data_inizio_str).order('data').execute()
        list_w = res_w.data or []
    except Exception as e:
        list_w = []

    try:
        res_r = supabase.table('rpe_sessioni').select('*').eq('atleta_id', atleta_id_sel).gte('data', data_inizio_str).order('data').execute()
        list_r = res_r.data or []
    except Exception as e:
        list_r = []

    df_w = pd.DataFrame(list_w)
    df_r = pd.DataFrame(list_r)

    # 4. Caricamento Dati GPS Corrispondenti
    df_all_gps = load_local_database()
    df_gps = pd.DataFrame()
    if not df_all_gps.empty and 'Players' in df_all_gps.columns:
        df_sub = df_all_gps[df_all_gps['Players'].astype(str).str.strip().str.lower() == atleta_sel.strip().lower()].copy()
        if not df_sub.empty and 'Date_obj' in df_sub.columns:
            df_gps = df_sub[df_sub['Date_obj'] >= pd.to_datetime(data_inizio)].copy()
            if not df_gps.empty:
                df_gps['data_iso'] = df_gps['Date_obj'].dt.strftime('%Y-%m-%d')

    # 5. KPI Cards Sintetiche
    tot_srpe = df_r['carico_interno'].sum() if (not df_r.empty and 'carico_interno' in df_r.columns) else 0
    
    # Ricerca robusta colonna Training Load
    col_tl_nome = 'Training Load' if ('Training Load' in df_gps.columns) else ('TL' if 'TL' in df_gps.columns else None)
    tot_tl_gps = df_gps[col_tl_nome].sum() if (not df_gps.empty and col_tl_nome) else 0
    tot_km_gps = (df_gps['DISTANCE'].sum() / 1000.0) if (not df_gps.empty and 'DISTANCE' in df_gps.columns) else 0

    avg_wellness = "N/D"
    if not df_w.empty:
        # Score wellness medio
        s_pos = df_w['sonno_qualita'] + df_w['umore']
        s_neg = (11 - df_w['fatica']) + (11 - df_w['stress']) + (11 - df_w['doms'])
        df_w['score_tot'] = (s_pos + s_neg) / 5.0
        avg_wellness = f"{df_w['score_tot'].mean():.1f}/10"

    eff_val = (tot_tl_gps / tot_srpe) if tot_srpe > 0 else 0.0

    # Action Bar con Export PDF Esecutivo M0V3
    opzioni_pdf = {"carico_interno": tr("Report Carico Interno & Wellness (PDF)", "Internal Load & Wellness Report (PDF)")}
    slug_ath = slugify_name(atleta_sel)
    kpis_ci = {
        'tot_srpe': tot_srpe,
        'tot_tl_gps': tot_tl_gps,
        'eff_ratio': eff_val,
        'avg_wellness': avg_wellness,
        'n_srpe': len(df_r),
        'n_wellness': len(df_w)
    }
    render_action_bar(
        meta_items=[
            (tr("Atleta", "Athlete"), atleta_sel),
            (tr("Periodo", "Period"), label_periodo_sel),
            (tr("Carico sRPE", "sRPE Load"), f"{tot_srpe:,.0f} AU"),
            (tr("Carico GPS", "GPS Load"), f"{tot_tl_gps:,.0f} TL"),
            (tr("Wellness Medio", "Avg Wellness"), avg_wellness)
        ],
        pdf_options=opzioni_pdf,
        pdf_key=f"ci_pdf_{slug_ath}_{slugify_name(label_periodo_sel)}",
        generate_fn=lambda _: crea_pdf_carico_interno(atleta_sel, label_periodo_sel, kpis_ci, df_srpe=df_r, df_wellness=df_w),
        filename_fn=lambda _: f"M0V3_Carico_Interno_{slug_ath}_{label_periodo_sel.replace(' ', '_')}.pdf"
    )

    col_k1, col_k2, col_k3, col_k4 = st.columns(4)
    with col_k1:
        st.markdown(card_kpi(
            tr("Carico Interno (sRPE)", "Internal Load (sRPE)"),
            f"<span style='font-size:24px; font-weight:900; color:#38bdf8;'>{tot_srpe:,.0f} <span style='font-size:13px;'>TL</span></span>",
            f"{len(df_r)} " + tr("sedute registrate", "logged sessions"),
            "#0ea5e9"
        ), unsafe_allow_html=True)
    with col_k2:
        st.markdown(card_kpi(
            tr("Carico Esterno (GPS)", "External Load (GPS)"),
            f"<span style='font-size:24px; font-weight:900; color:#34d399;'>{tot_tl_gps:,.0f} <span style='font-size:13px;'>TL</span></span>",
            f"{tot_km_gps:.1f} " + tr("km complessivi", "total km"),
            "#10b981"
        ), unsafe_allow_html=True)
    with col_k3:
        st.markdown(card_kpi(
            tr("Indice Efficienza (TL/sRPE)", "Efficiency Index (TL/sRPE)"),
            f"<span style='font-size:24px; font-weight:900; color:#f59e0b;'>{ (tot_tl_gps / tot_srpe):.2f}</span>" if tot_srpe > 0 else "<span style='font-size:22px; color:#94a3b8;'>N/D</span>",
            tr("Rapporto Meccanico/Soggettivo", "Mechanical/Subjective Ratio"),
            "#f59e0b"
        ), unsafe_allow_html=True)
    with col_k4:
        st.markdown(card_kpi(
            tr("Score Wellness Medio", "Average Wellness"),
            f"<span style='font-size:24px; font-weight:900; color:#a855f7;'>{avg_wellness}</span>",
            f"{len(df_w)} " + tr("rilevazioni mattutine", "morning check-ins"),
            "#a855f7"
        ), unsafe_allow_html=True)

    st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)

    # Box informativo promemoria atleta per Coach / Desktop
    with st.expander(tr("Strumenti Promemoria Calendario Atleti (Allarme Smartphone)", "Athlete Calendar Notification Tools (Smartphone Alarm)"), expanded=False):
        c_rm1, c_rm2 = st.columns([3, 2])
        with c_rm1:
            st.markdown(
                tr(
                    "I tuoi atleti possono configurare una notifica/sveglia ricorrente quotidiana su iPhone o Android per non dimenticare di compilare il Diario (Wellness alle 08:30 e sRPE alle 20:30). "
                    "Il pulsante è attivo nel loro Diario Smartphone, oppure puoi scaricare qui il file `.ics` da inoltrare loro.",
                    "Your athletes can configure daily recurring alarms on iPhone or Android to remember to complete their Diary (Wellness at 08:30 and sRPE at 20:30). "
                    "The action is available in their Smartphone Diary, or you can download the `.ics` file here to forward to them."
                )
            )
        with c_rm2:
            from views.atleta_mobile import genera_promemoria_ics
            app_url = st.secrets.get('app', {}).get('base_url', 'https://webapptennisgps.streamlit.app') + "?device=mobile"
            ics_bytes = genera_promemoria_ics(dt.time(8, 30), dt.time(20, 30), app_url).encode('utf-8')
            st.download_button(
                label=tr("Scarica File .ics Promemoria (iPhone/Android)", "Download .ics Reminders File (iPhone/Android)"),
                data=ics_bytes,
                file_name="m0v3_promemoria_atleti.ics",
                mime="text/calendar",
                use_container_width=True,
                key="btn_dl_ics_coach"
            )

    # 6. Tab di Dettaglio (con navigazione persistente)
    lbl_ci_1 = tr("Incrocio GPS vs sRPE", "GPS vs sRPE Cross-Match")
    lbl_ci_2 = tr("Trend Risposta Biologica (Wellness)", "Wellness & Biological Trend")
    lbl_ci_3 = tr("Storico Sedute & Audit Modifiche", "Session Log & Audit Trail")
    active_ci_tab = render_tab_navigation([lbl_ci_1, lbl_ci_2, lbl_ci_3], key="nav_carico_interno")

    # -------------------------------------------------------------
    # TAB 1: INCROCIO GPS vs sRPE
    # -------------------------------------------------------------
    if active_ci_tab == lbl_ci_1:
        if df_r.empty and df_gps.empty:
            st.info("Nessuna sessione trovata per il periodo selezionato.")
        else:
            col_sel_metric, col_sel_w = st.columns([2.5, 2.5])
            with col_sel_metric:
                parametro_gps_sel = st.selectbox(
                    tr("Parametro Carico Esterno GPS da incrociare:", "GPS External Load Metric:"),
                    ["Indice di Volume", "Indice di Intensità", "Training Load (GPS)", "Distanza Totale (m)"],
                    index=0,
                    key="sel_parametro_gps_confronto"
                )
            with col_sel_w:
                st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                mostra_wellness_overlay = st.checkbox(
                    tr("Sovrapponi Trend Wellness Totale (1-10)", "Overlay Total Wellness Trend (1-10)"),
                    value=True,
                    key="chk_overlay_wellness"
                )

            # Raggruppamento sRPE per data e tipologia
            df_r_agg = pd.DataFrame()
            if not df_r.empty:
                df_r_agg = df_r.groupby(['data', 'tipologia'])['carico_interno'].sum().unstack(fill_value=0).reset_index()

            # Raggruppamento GPS per data
            df_gps_agg = pd.DataFrame()
            if not df_gps.empty:
                agg_dict = {'DISTANCE': 'sum'}
                for col_opt in [
                    'Player Load', 'Minuti', 'Training Load', 'TL_High', 
                    'High Accel IMU', 'High Decel IMU', 'Azioni Int. IMU >2'
                ]:
                    if col_opt in df_gps.columns:
                        agg_dict[col_opt] = 'sum'
                df_gps_agg = df_gps.groupby('data_iso').agg(agg_dict).reset_index().rename(columns={'data_iso': 'data'})

                # Funzione di ricerca robusta dei parametri
                def _trova_colonna(candidates):
                    for c in candidates:
                        if c in df_gps_agg.columns:
                            return c
                    return None

                col_tl = _trova_colonna(['Training Load', 'TL'])
                col_min = _trova_colonna(['Minuti', 'Duration', 'tot_time'])
                col_az = _trova_colonna(['Azioni Int. IMU >2', 'Azioni Int. IMU >2"', 'Azioni Int. >2', 'Azioni Intense'])

                col_tlh = _trova_colonna(['TL_High', 'Training Load High', 'TL High'])
                col_acc = _trova_colonna(['High Accel IMU', 'High Accel', 'Accelerazioni IMU'])
                col_dec = _trova_colonna(['High Decel IMU', 'High Decel', 'Decelerazioni IMU'])

                # 1. INDICE DI VOLUME: Training Load (40%), Tempo/Minuti (35%), Azioni >2" (25%)
                # Se un parametro non è presente o non mappato, il peso viene ridistribuito sugli altri
                vol_components = [
                    (col_tl, 40.0),
                    (col_min, 35.0),
                    (col_az, 25.0)
                ]
                avail_vol = [(c, w) for c, w in vol_components if c is not None and pd.to_numeric(df_gps_agg[c], errors='coerce').fillna(0).max() > 0]
                if avail_vol:
                    sum_w_vol = sum(w for _, w in avail_vol)
                    vol_series = sum(
                        (pd.to_numeric(df_gps_agg[c], errors='coerce').fillna(0) / pd.to_numeric(df_gps_agg[c], errors='coerce').fillna(0).max()) * (w / sum_w_vol * 100.0)
                        for c, w in avail_vol
                    )
                    df_gps_agg['Indice di Volume'] = vol_series.round(1)
                else:
                    df_gps_agg['Indice di Volume'] = 0.0

                # 2. INDICE DI INTENSITÀ: TL_High (40%), Accelerazioni IMU (30%), Decelerazioni IMU (30%)
                # Se un parametro non è presente o non mappato, il calcolo viene effettuato sugli altri
                int_components = [
                    (col_tlh, 40.0),
                    (col_acc, 30.0),
                    (col_dec, 30.0)
                ]
                avail_int = [(c, w) for c, w in int_components if c is not None and pd.to_numeric(df_gps_agg[c], errors='coerce').fillna(0).max() > 0]
                if avail_int:
                    sum_w_int = sum(w for _, w in avail_int)
                    int_series = sum(
                        (pd.to_numeric(df_gps_agg[c], errors='coerce').fillna(0) / pd.to_numeric(df_gps_agg[c], errors='coerce').fillna(0).max()) * (w / sum_w_int * 100.0)
                        for c, w in avail_int
                    )
                    df_gps_agg['Indice di Intensità'] = int_series.round(1)
                else:
                    df_gps_agg['Indice di Intensità'] = 0.0

                df_gps_agg['Distanza Totale (m)'] = df_gps_agg['DISTANCE'].round(0)
                if col_tl and col_tl in df_gps_agg.columns:
                    df_gps_agg['Training Load (GPS)'] = df_gps_agg[col_tl].round(0)
                elif 'Training Load' in df_gps_agg.columns:
                    df_gps_agg['Training Load (GPS)'] = df_gps_agg['Training Load'].round(0)
                elif 'TL' in df_gps_agg.columns:
                    df_gps_agg['Training Load (GPS)'] = df_gps_agg['TL'].round(0)

            # Unione di tutte le date (sRPE, GPS, e Wellness)
            date_r = df_r_agg['data'].tolist() if not df_r_agg.empty else []
            date_gps = df_gps_agg['data'].tolist() if not df_gps_agg.empty else []
            date_w = df_w['data'].tolist() if not df_w.empty else []
            tutte_date = sorted(list(set(date_r + date_gps + date_w)))

            df_merged = pd.DataFrame({'data': tutte_date})
            if not df_r_agg.empty:
                df_merged = pd.merge(df_merged, df_r_agg, on='data', how='left').fillna(0)
            if not df_gps_agg.empty:
                df_merged = pd.merge(df_merged, df_gps_agg, on='data', how='left').fillna(0)
            if not df_w.empty and 'data' in df_w.columns and 'score_tot' in df_w.columns:
                df_w_sub = df_w[['data', 'score_tot']].rename(columns={'score_tot': 'wellness_totale'})
                df_merged = pd.merge(df_merged, df_w_sub, on='data', how='left')

            # -------------------------------------------------------------
            # CALCOLO INTERNAL:EXTERNAL RATIO PURO (SOLO TENNIS) & DECOUPLING
            # -------------------------------------------------------------
            ie_records = []
            for d_val in tutte_date:
                srpe_ten = 0.0
                if not df_r.empty:
                    r_day = df_r[(df_r['data'] == d_val) & (df_r['tipologia'].astype(str).str.lower().str.contains('tennis'))]
                    if not r_day.empty:
                        srpe_ten = float(r_day['carico_interno'].sum())

                tl_gps = 0.0
                if not df_gps_agg.empty:
                    g_row = df_gps_agg[df_gps_agg['data'] == d_val]
                    if not g_row.empty and 'Training Load (GPS)' in g_row.columns:
                        tl_gps = float(g_row['Training Load (GPS)'].iloc[0])

                if srpe_ten > 0 and tl_gps > 0:
                    r_ie = round(srpe_ten / tl_gps, 2)
                    ie_records.append({'data': d_val, 'srpe_tennis': srpe_ten, 'tl_gps': tl_gps, 'ie_ratio': r_ie})

            df_ie_pure = pd.DataFrame(ie_records)
            mean_ie = float(df_ie_pure['ie_ratio'].mean()) if not df_ie_pure.empty else 0.0
            th_decoupling = mean_ie * 1.20 if mean_ie > 0 else 0.0
            decoupling_dates = []
            if not df_ie_pure.empty and th_decoupling > 0:
                decoupling_dates = df_ie_pure[df_ie_pure['ie_ratio'] > th_decoupling]['data'].tolist()

            # -------------------------------------------------------------
            # CALCOLO LAG EFFECT A 24H (Carico T -> DOMS e Fatica T+1)
            # -------------------------------------------------------------
            lag_stats = {"n_events": 0, "avg_delta_doms": 0.0, "avg_delta_fatica": 0.0}
            if not df_r.empty and not df_w.empty and 'data' in df_w.columns:
                df_rt = df_r.groupby('data')['carico_interno'].sum().reset_index()
                mean_rt = float(df_rt['carico_interno'].mean()) if not df_rt.empty else 0.0
                std_rt = float(df_rt['carico_interno'].std()) if len(df_rt) > 1 else 0.0
                hi_load_th = mean_rt + (0.5 * std_rt) if std_rt > 0 else (mean_rt * 1.15)

                b_doms = float(df_w['doms'].mean()) if 'doms' in df_w.columns and not df_w['doms'].dropna().empty else 3.0
                b_fat = float(df_w['fatica'].mean()) if 'fatica' in df_w.columns and not df_w['fatica'].dropna().empty else 3.0

                diff_doms_list = []
                diff_fat_list = []
                for _, r_row in df_rt.iterrows():
                    if float(r_row['carico_interno']) >= hi_load_th:
                        d_obj_t = pd.to_datetime(r_row['data'], errors='coerce')
                        if pd.notna(d_obj_t):
                            d_next_str = (d_obj_t + timedelta(days=1)).strftime('%Y-%m-%d')
                            w_next_r = df_w[df_w['data'] == d_next_str]
                            if not w_next_r.empty:
                                if 'doms' in w_next_r.columns:
                                    diff_doms_list.append(float(w_next_r['doms'].iloc[0]) - b_doms)
                                if 'fatica' in w_next_r.columns:
                                    diff_fat_list.append(float(w_next_r['fatica'].iloc[0]) - b_fat)

                if diff_doms_list or diff_fat_list:
                    lag_stats["n_events"] = len(diff_doms_list)
                    lag_stats["avg_delta_doms"] = round(float(np.mean(diff_doms_list)), 1) if diff_doms_list else 0.0
                    lag_stats["avg_delta_fatica"] = round(float(np.mean(diff_fat_list)), 1) if diff_fat_list else 0.0

            # 3 KPI Cards Scientifiche: I:E Ratio, Disaccoppiamento e Lag Effect
            c_ie1, c_ie2, c_ie3 = st.columns(3)
            with c_ie1:
                val_ie_str = f"{mean_ie:.2f}" if mean_ie > 0 else "N/D"
                st.markdown(card_kpi(
                    tr("I:E Ratio Medio (Puro Tennis)", "Mean I:E Ratio (Pure Tennis)"),
                    val_ie_str,
                    tr("Rapporto sRPE Tennis / Training Load GPS (escluso Gym)", "sRPE Tennis / GPS TL Ratio (excl. Gym)"),
                    "#0ea5e9"
                ), unsafe_allow_html=True)
            with c_ie2:
                n_dec = len(decoupling_dates)
                col_dec = "#ef4444" if n_dec >= 2 else ("#f59e0b" if n_dec == 1 else "#10b981")
                st.markdown(card_kpi(
                    tr("Disaccoppiamento I:E (>+20%)", "I:E Decoupling (>+20%)"),
                    f"{n_dec} {tr('giorni', 'days')}",
                    tr("Fatica interna alta a parità di lavoro esterno", "High internal fatigue relative to external output"),
                    col_dec
                ), unsafe_allow_html=True)
            with c_ie3:
                txt_lag = f"DOMS {lag_stats['avg_delta_doms']:+.1f} | Fatica {lag_stats['avg_delta_fatica']:+.1f}" if lag_stats['n_events'] > 0 else "In attesa dati"
                st.markdown(card_kpi(
                    tr("Lag Effect 24h (Carico T → T+1)", "24h Lag Effect (Load T → T+1)"),
                    txt_lag,
                    tr(f"Variazione media al risveglio dopo carichi alti ({lag_stats['n_events']} occorrenze)", f"Mean awakening shift after load peaks ({lag_stats['n_events']} events)"),
                    "#8b5cf6"
                ), unsafe_allow_html=True)

            st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

            # Grafico Tri-assiale Plotly (sRPE Barre + GPS Linea + Wellness Linea)
            fig = go.Figure()

            # Barre sovrapposte per tipologia seduta sRPE (Nessun viola per l'RPE)
            color_map = {
                "Tennis": "#0ea5e9",
                "Preparazione Fisica": "#10b981",
                "Gym": "#f97316",
                "Recupero": "#06b6d4",
                "Altro": "#64748b"
            }

            for col_tipo in [c for c in df_merged.columns if c in color_map]:
                fig.add_trace(go.Bar(
                    x=df_merged['data'],
                    y=df_merged[col_tipo],
                    name=f"sRPE: {col_tipo}",
                    marker_color=color_map.get(col_tipo, '#94a3b8'),
                    yaxis="y1"
                ))

            # Linea metrica GPS scelta su asse Y2 (Rosso Rubino ad altissima visibilità ed esclusivo per il GPS)
            col_gps_plot = parametro_gps_sel
            if col_gps_plot in df_merged.columns:
                fig.add_trace(go.Scatter(
                    x=df_merged['data'],
                    y=df_merged[col_gps_plot],
                    name=f"Carico Esterno ({col_gps_plot})",
                    mode="lines+markers",
                    line=dict(color="#e11d48", width=3.5),
                    marker=dict(size=8, color="#e11d48", line=dict(width=2, color="#ffffff")),
                    yaxis="y2"
                ))

            # Marker di Disaccoppiamento I:E (>+20% della media abituale su Tennis)
            if decoupling_dates and col_gps_plot in df_merged.columns:
                df_dec = df_merged[df_merged['data'].isin(decoupling_dates)]
                if not df_dec.empty:
                    fig.add_trace(go.Scatter(
                        x=df_dec['data'],
                        y=df_dec[col_gps_plot],
                        mode="markers",
                        name=tr("Disaccoppiamento I:E (>+20%)", "I:E Decoupling (>+20%)"),
                        marker=dict(symbol="diamond", size=14, color="#f59e0b", line=dict(width=2.5, color="#78350f")),
                        yaxis="y2"
                    ))

            # Linea Wellness Totale opzionale su asse Y3
            if mostra_wellness_overlay and 'wellness_totale' in df_merged.columns:
                fig.add_trace(go.Scatter(
                    x=df_merged['data'],
                    y=df_merged['wellness_totale'],
                    name=tr("Wellness Totale (1-10)", "Total Wellness (1-10)"),
                    mode="lines+markers",
                    line=dict(color="#a855f7", width=2.5, dash="dot"),
                    marker=dict(size=8, color="#c084fc", symbol="diamond"),
                    yaxis="y3"
                ))

            layout_axes = dict(
                barmode='stack',
                title=dict(
                    text=f"Carico Interno (sRPE) vs {parametro_gps_sel}{' + Wellness Totale' if (mostra_wellness_overlay and 'wellness_totale' in df_merged.columns) else ''} — {atleta_sel}",
                    font=dict(size=15, color="#0f172a")
                ),
                height=430,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                xaxis=dict(title=dict(text="Data"), type='category', tickangle=-45),
                yaxis=dict(
                    title=dict(text="Carico Interno (sRPE [TL])", font=dict(color="#0ea5e9")),
                    tickfont=dict(color="#0ea5e9"),
                    showgrid=True,
                    gridcolor="#f1f5f9"
                ),
                yaxis2=dict(
                    title=dict(text=f"Carico Esterno ({parametro_gps_sel})", font=dict(color="#e11d48")),
                    tickfont=dict(color="#e11d48"),
                    overlaying="y",
                    side="right",
                    showgrid=False
                )
            )

            if mostra_wellness_overlay and 'wellness_totale' in df_merged.columns:
                layout_axes['yaxis3'] = dict(
                    title=dict(text="Wellness (1-10)", font=dict(color="#a855f7")),
                    tickfont=dict(color="#a855f7"),
                    overlaying="y",
                    side="right",
                    anchor="free",
                    autoshift=True,
                    range=[0.5, 10.5],
                    dtick=2,
                    showgrid=False
                )

            fig.update_layout(**layout_axes)
            st.plotly_chart(fig, use_container_width=True)

            # Ripartizione Percentuale per Tipologia Seduta
            if not df_r.empty:
                col_p1, col_p2 = st.columns([1, 1])
                with col_p1:
                    df_pie = df_r.groupby('tipologia')['carico_interno'].sum().reset_index()
                    fig_pie = go.Figure(data=[go.Pie(
                        labels=df_pie['tipologia'],
                        values=df_pie['carico_interno'],
                        hole=0.45,
                        marker=dict(colors=[color_map.get(l, '#94a3b8') for l in df_pie['tipologia']])
                    )])
                    fig_pie.update_layout(
                        title=dict(text=tr("Distribuzione Carico Interno per Tipologia", "Internal Load Distribution by Type"), font=dict(size=14)),
                        height=280,
                        margin=dict(l=10, r=10, t=35, b=10)
                    )
                    st.plotly_chart(fig_pie, use_container_width=True)

                with col_p2:
                    st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)
                    st.markdown("#### Insight Metodologico:")
                    st.info(
                        f"L'incrocio simultaneo tra **Carico Esterno GPS** ({parametro_gps_sel}), **Carico Interno** (sRPE) e **Risposta Biologica** (Wellness) evidenzia:\n\n"
                        f"- **sRPE alto + GPS ridotto + Wellness basso**: Fatica cumulativa o stress non assorbito. L'atleta spende molta energia biologica per produrre poco lavoro meccanico.\n"
                        f"- **GPS elevato + sRPE contenuto + Wellness alto**: Stato di grazia e massima assimilazione del carico."
                    )

    # -------------------------------------------------------------
    # TAB 2: WELLNESS & RISPOSTA BIOLOGICA
    # -------------------------------------------------------------
    elif active_ci_tab == lbl_ci_2:
        if df_w.empty:
            st.info("Nessuna rilevazione di wellness mattutino disponibile per il periodo selezionato.")
        else:
            # Selezione interattiva delle metriche da tracciare
            opzioni_metriche = [
                "Score Wellness Globale",
                "Sonno (Qualità)",
                "Fatica Generale",
                "Stress",
                "Umore",
                "DOMS / Dolore Muscolare"
            ]
            metriche_sel = st.multiselect(
                tr("Parametri da visualizzare nel grafico:", "Metrics to display on chart:"),
                options=opzioni_metriche,
                default=opzioni_metriche,
                key="sel_metriche_wellness_chart"
            )

            # Grafico longitudinale dei parametri selezionati
            fig_w = go.Figure()
            if "Score Wellness Globale" in metriche_sel:
                fig_w.add_trace(go.Scatter(
                    x=df_w['data'],
                    y=df_w['score_tot'],
                    name="Score Wellness Globale",
                    mode="lines+markers",
                    line=dict(color="#0ea5e9", width=3.5),
                    marker=dict(size=8, color="#0ea5e9", line=dict(width=2, color="#ffffff"))
                ))
            if "Sonno (Qualità)" in metriche_sel:
                fig_w.add_trace(go.Scatter(x=df_w['data'], y=df_w['sonno_qualita'], name="Sonno (Qualità)", mode="lines+markers", line=dict(color="#38bdf8", width=2)))
            if "Fatica Generale" in metriche_sel:
                fig_w.add_trace(go.Scatter(x=df_w['data'], y=df_w['fatica'], name="Fatica Generale", mode="lines+markers", line=dict(color="#f59e0b", width=2)))
            if "Stress" in metriche_sel:
                fig_w.add_trace(go.Scatter(x=df_w['data'], y=df_w['stress'], name="Stress", mode="lines+markers", line=dict(color="#ef4444", width=2)))
            if "Umore" in metriche_sel:
                fig_w.add_trace(go.Scatter(x=df_w['data'], y=df_w['umore'], name="Umore", mode="lines+markers", line=dict(color="#10b981", width=2)))
            if "DOMS / Dolore Muscolare" in metriche_sel:
                fig_w.add_trace(go.Scatter(x=df_w['data'], y=df_w['doms'], name="DOMS / Dolore Muscolare", mode="lines+markers", line=dict(color="#8b5cf6", width=2)))

            fig_w.update_layout(
                title=dict(text="Trend Parametri Wellness Mattutino (Scala 1-10)", font=dict(size=14)),
                height=360,
                yaxis=dict(range=[0.5, 10.5], dtick=1, gridcolor="#f1f5f9"),
                xaxis=dict(type='category', tickangle=-45),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            st.plotly_chart(fig_w, use_container_width=True)

            # Tabella con semafori colorati
            st.markdown(f"#### {tr('Registro Giornaliero Dettagliato:', 'Detailed Daily Log:')}")
            tabella_w = []
            for _, row in df_w.sort_values('data', ascending=False).iterrows():
                tabella_w.append({
                    tr("Data", "Date"): row['data'],
                    tr("Sonno (1-10)", "Sleep (1-10)"): f"{row['sonno_qualita']} (●)" if row['sonno_qualita']>=7 else f"{row['sonno_qualita']} (▲)" if row['sonno_qualita']>=5 else f"{row['sonno_qualita']} (■)",
                    tr("Fatica (1-10)", "Fatigue (1-10)"): f"{row['fatica']} (●)" if row['fatica']<=4 else f"{row['fatica']} (▲)" if row['fatica']<=6 else f"{row['fatica']} (■)",
                    tr("Stress (1-10)", "Stress (1-10)"): f"{row['stress']} (●)" if row['stress']<=4 else f"{row['stress']} (▲)" if row['stress']<=6 else f"{row['stress']} (■)",
                    tr("Umore (1-10)", "Mood (1-10)"): f"{row['umore']} (●)" if row['umore']>=7 else f"{row['umore']} (▲)" if row['umore']>=5 else f"{row['umore']} (■)",
                    tr("DOMS (1-10)", "DOMS (1-10)"): f"{row['doms']} (●)" if row['doms']<=4 else f"{row['doms']} (▲)" if row['doms']<=6 else f"{row['doms']} (■)",
                    tr("Score Globale", "Overall Score"): f"{row.get('score_tot', 0):.1f}/10",
                    tr("Note", "Notes"): row.get('note') or '-'
                })
            st.dataframe(pd.DataFrame(tabella_w), use_container_width=True)

    # -------------------------------------------------------------
    # TAB 3: AUDIT MODIFICHE & STORICO SEDUTE
    # -------------------------------------------------------------
    elif active_ci_tab == lbl_ci_3:
        if df_r.empty:
            st.info("Nessuna sessione sRPE presente nello storico.")
        else:
            st.markdown("#### Tracciamento Sessioni & Modifiche Effettuate dall'Atleta:")
            tabella_audit = []
            for _, r_item in df_r.sort_values('data', ascending=False).iterrows():
                c_at = r_item.get('created_at', '')
                u_at = r_item.get('updated_at', '')
                # Verifica se modificato a posteriori
                modificato = False
                if c_at and u_at:
                    modificato = (str(u_at)[:19] != str(c_at)[:19])

                tabella_audit.append({
                    "Data Seduta": r_item['data'],
                    "Slot": f"Seduta #{r_item.get('slot', 1)}",
                    "Tipologia": r_item.get('tipologia', 'N/D'),
                    "Durata": f"{r_item.get('durata_minuti', 0)} min",
                    "RPE (0-10)": r_item.get('rpe', 0),
                    "Carico Interno": f"{r_item.get('carico_interno', 0)} TL",
                    "Stato Inserimento": "[MODIFICATO]" if modificato else "[ORIGINALE]",
                    "Ultimo Aggiornamento": str(u_at)[:16].replace('T', ' ') if u_at else '-'
                })
            st.dataframe(pd.DataFrame(tabella_audit), use_container_width=True)

    st.markdown("<div style='margin-top: 30px;'></div>", unsafe_allow_html=True)
    render_scientific_methodology_box("carico_interno")
