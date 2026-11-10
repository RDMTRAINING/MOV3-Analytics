import os
import re
import secrets
import datetime as dt
from datetime import datetime, timedelta, date
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
    render_page_header,
    render_print_header,
    tr,
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
    frase_riepilogo,
    card_kpi,
    delta_puro,
    delta_confronto,
    get_atleti_associati,
    get_tutti_gli_atleti,
    render_athlete_hero_strip,
    slugify_name,
)
from pdf_generator import (
    crea_pdf_m0v3,
    crea_pdf_sessione_m0v3,
    crea_pdf_weekly_m0v3,
    crea_pdf_storico_m0v3,
    crea_pdf_medie_m0v3,
)

def render_generatore_dati(t):
    render_page_header(t['gen_title'], t['gen_desc'], "SIMULATION ENGINE")
    df_storico = load_local_database()
    
    if st.session_state['role'] == 'Super-Admin':
        st.info(tr("Essendo Super-Admin, seleziona per quale account (Coach) stai generando i dati.", "As Super-Admin, select which account (Coach) you are generating data for."))
        res_profili = supabase.table('profili').select('email', 'id').execute()
        if res_profili.data:
            dict_utenti = {p['email']: p['id'] for p in res_profili.data}
            utente_target_email = st.selectbox(tr("Account Proprietario (Coach):", "Owner Account (Coach):"), list(dict_utenti.keys()))
            utente_target_id = dict_utenti[utente_target_email]
        else:
            st.error(tr("Nessun utente trovato nel database.", "No users found in database."))
            return
    else:
        utente_target_email = st.session_state['user'].email
        utente_target_id = st.session_state['user'].id

    atleti_disponibili = get_atleti_associati(utente_target_id)
    
    if not atleti_disponibili: 
        st.warning(tr("Nessun atleta associato a questo account.", "No athletes linked to this account."))
        return

    df_storico_atleti = df_storico[(df_storico['Players'].isin(atleti_disponibili)) & (df_storico['Dato_Simulato'] == False)] if not df_storico.empty else pd.DataFrame()
    if df_storico_atleti.empty: 
        st.warning(tr("Nessun dato storico reale disponibile per gli atleti associati a questo account. Carica prima un file CSV per stabilire le medie.", "No real historical data available for athletes linked to this account. Upload a CSV file first to establish averages."))
        return

    # Pre-popolamento proveniente da ponte Day Inspector (Sessioni NO-GPS)
    pre_ath = st.session_state.pop('gen_prefill_atleta', None)
    pre_date = st.session_state.pop('gen_prefill_data', None)
    pre_min = st.session_state.pop('gen_prefill_minuti', None)

    glob_ath = st.session_state.get('selected_athlete')
    if pre_ath and pre_ath in atleti_disponibili:
        atleta = pre_ath
        st.session_state['selected_athlete'] = pre_ath
    elif glob_ath and glob_ath in atleti_disponibili:
        atleta = glob_ath
    else:
        atleta = atleti_disponibili[0]

    val_date = pre_date if pre_date else date.today()
    val_min = int(pre_min) if (pre_min and pre_min > 0) else 60

    render_athlete_hero_strip(atleta, extra_badges=[tr("Simulatore Sessioni NO-GPS", "NO-GPS Session Simulator")])

    with st.form("form_simulazione"):
        col1, col2 = st.columns(2)
        with col1:
            data_sessione = st.date_input(t['sess_date'], value=val_date)
            st.text_input(t['sess_name'], key="gen_nome_input", placeholder=f"Lascia vuoto per: Sim_{data_sessione.strftime('%d-%m-%Y')}")
            
        with col2:
            opzioni_sess = get_tipologie_sessione(utente_target_email, atleta_nome=atleta) + [t['add_new']]
            tipo_sess = st.selectbox(t['sess_type'], opzioni_sess)
            tipo_sess_effettiva = st.text_input(t['spec_new']) if tipo_sess == t['add_new'] else tipo_sess
            minuti_sessione = st.number_input(t['duration'], min_value=1, value=val_min)
        
        st.markdown(t['context'])
        col_c1, col_c2, col_c3 = st.columns(3)
        with col_c1: campo = st.selectbox(t['surface'], ["Hard", "Clay", "Grass"])
        with col_c2: ambiente = st.radio(t['environment'], ["Outdoor", "Indoor"], horizontal=True)
        with col_c3: sparring = st.number_input(t['sparring'], min_value=0, step=1)
        submit_simulazione = st.form_submit_button(t['btn_generate'], type="primary")

    if submit_simulazione:
        valore_nome = st.session_state.gen_nome_input
        nome_sessione_finale = valore_nome if valore_nome.strip() else f"Sim_{data_sessione.strftime('%d-%m-%Y')}"

        df_reale_atleta = df_storico[(df_storico['Players'] == atleta) & (df_storico['Dato_Simulato'] == False)].copy()
        if df_reale_atleta.empty: 
            st.error(f"Errore: Nessun dato storico reale trovato per {atleta}.")
            return

        colonne_imu_vol = [
            "Training Load", "TL_Stand", "TL_Low", "TL_Medium", "TL_High",
            "Player Load", "High Accel IMU", "High Decel IMU",
            "Azioni Int. IMU >2", "Azioni Int. IMU >3", "Azioni Int. IMU >5", "Azioni Int. IMU >7", "Azioni Int. IMU >10",
            "Recuperi IMU 3-30s", "Recuperi IMU 30-60s", "Recuperi IMU 1-5m"
        ]
        colonne_imu_pct = ["TL_T_Stand", "TL_T_Low", "TL_T_Medium", "TL_T_High"]
        colonne_gps_vol = ["DISTANCE", "HML Distance >25.5W", "VHML Distance >50W", "High Dec Events <-3.5 m/s2"]
        colonne_gps_pct = ["Recovery Time <5W %", "Equivalent Distance %", "Anaerobic index %"]
        colonne_conteggi_interi = {
            "High Accel IMU", "High Decel IMU", "High Dec Events <-3.5 m/s2",
            "Azioni Int. IMU >2", "Azioni Int. IMU >3", "Azioni Int. IMU >5", "Azioni Int. IMU >7", "Azioni Int. IMU >10",
            "Recuperi IMU 3-30s", "Recuperi IMU 30-60s", "Recuperi IMU 1-5m"
        }

        tutte_col_num = ["Minuti"] + colonne_imu_vol + colonne_imu_pct + colonne_gps_vol + colonne_gps_pct
        for c_n in tutte_col_num:
            if c_n not in df_reale_atleta.columns:
                df_reale_atleta[c_n] = 0.0
            df_reale_atleta[c_n] = pd.to_numeric(df_reale_atleta[c_n], errors='coerce').fillna(0.0)
        
        storico_tipo = df_reale_atleta['Tipologia Sessione'].astype(str).str.strip().str.lower()
        target_tipo = tipo_sess_effettiva.strip().lower()
        df_tipologia = df_reale_atleta[storico_tipo == target_tipo]
        
        usato_media_generale = False
        if df_tipologia.empty: 
            usato_media_generale = True
            df_base_calcolo = df_reale_atleta 
        else: 
            df_base_calcolo = df_tipologia

        somma_minuti_imu = float(df_base_calcolo['Minuti'].sum())
        if somma_minuti_imu <= 0:
            somma_minuti_imu = float(len(df_base_calcolo) * 60.0)

        nuova_riga = {
            "Date": data_sessione.strftime('%d/%m/%Y'), 
            "Session": nome_sessione_finale, 
            "Players": atleta, 
            "Minuti": float(minuti_sessione),
            "Tipologia Campo": campo, 
            "Ambiente": ambiente, 
            "Minuti Sparring": int(sparring), 
            "Tipologia Sessione": tipo_sess_effettiva,
            "File_Name": "Generato_dal_Sistema_M0V3", 
            "Uploader_Email": utente_target_email,
            "Dato_Simulato": True
        }

        # 1. Calcolo Metriche Volumetriche IMU/Cardio (Tasso medio al minuto: Somma Parametro / Somma Minuti)
        for col in colonne_imu_vol:
            tasso_min = float(df_base_calcolo[col].sum()) / somma_minuti_imu
            val_sim = tasso_min * float(minuti_sessione)
            nuova_riga[col] = int(round(val_sim)) if col in colonne_conteggi_interi else round(val_sim, 1)

        # Allineamento fasce volumetriche TL (TL_Stand + TL_Low + TL_Medium + TL_High == Training Load)
        tl_tot_sim = float(nuova_riga.get("Training Load", 0.0))
        somma_fasce_tl = sum(float(nuova_riga.get(k, 0.0)) for k in ["TL_Stand", "TL_Low", "TL_Medium", "TL_High"])
        if tl_tot_sim > 0 and somma_fasce_tl > 0:
            fattore_tl = tl_tot_sim / somma_fasce_tl
            for k_tl in ["TL_Stand", "TL_Low", "TL_Medium", "TL_High"]:
                nuova_riga[k_tl] = round(float(nuova_riga[k_tl]) * fattore_tl, 1)
            residuo_tl = round(tl_tot_sim - sum(float(nuova_riga[k_tl]) for k_tl in ["TL_Stand", "TL_Low", "TL_Medium", "TL_High"]), 1)
            if residuo_tl != 0:
                max_k_tl = max(["TL_Stand", "TL_Low", "TL_Medium", "TL_High"], key=lambda k: float(nuova_riga[k]))
                nuova_riga[max_k_tl] = round(float(nuova_riga[max_k_tl]) + residuo_tl, 1)

        # 2. Calcolo Percentuali Tempo IMU (TL_T_Stand, TL_T_Low, TL_T_Medium, TL_T_High) normalizzate al 100%
        medie_t_pct = {k: float(df_base_calcolo[k].mean()) for k in colonne_imu_pct}
        somma_t_pct = sum(medie_t_pct.values())
        if somma_t_pct > 0:
            for k in colonne_imu_pct:
                nuova_riga[k] = round((medie_t_pct[k] / somma_t_pct) * 100.0, 1)
            residuo_pct = round(100.0 - sum(float(nuova_riga[k]) for k in colonne_imu_pct), 1)
            if residuo_pct != 0:
                max_k_pct = max(colonne_imu_pct, key=lambda k: float(nuova_riga[k]))
                nuova_riga[max_k_pct] = round(float(nuova_riga[max_k_pct]) + residuo_pct, 1)
        else:
            for k in colonne_imu_pct:
                nuova_riga[k] = 0.0

        # 3. Calcolo Metriche GPS (Azzerate se Indoor; calcolate solo su storico Outdoor se Outdoor)
        if str(ambiente).strip().lower() == "indoor":
            for col in colonne_gps_vol:
                nuova_riga[col] = 0 if col in colonne_conteggi_interi else 0.0
            for col in colonne_gps_pct:
                nuova_riga[col] = 0.0
        else:
            mask_out_tipo = (df_base_calcolo['Ambiente'].astype(str).str.strip().str.lower() != 'indoor') & (df_base_calcolo['DISTANCE'] > 0)
            df_base_gps = df_base_calcolo[mask_out_tipo]
            if df_base_gps.empty:
                mask_out_all = (df_reale_atleta['Ambiente'].astype(str).str.strip().str.lower() != 'indoor') & (df_reale_atleta['DISTANCE'] > 0)
                df_base_gps = df_reale_atleta[mask_out_all]

            if df_base_gps.empty:
                for col in colonne_gps_vol:
                    nuova_riga[col] = 0 if col in colonne_conteggi_interi else 0.0
                for col in colonne_gps_pct:
                    nuova_riga[col] = 0.0
            else:
                somma_minuti_gps = float(df_base_gps['Minuti'].sum())
                if somma_minuti_gps <= 0:
                    somma_minuti_gps = float(len(df_base_gps) * 60.0)
                for col in colonne_gps_vol:
                    tasso_gps_min = float(df_base_gps[col].sum()) / somma_minuti_gps
                    val_gps_sim = tasso_gps_min * float(minuti_sessione)
                    nuova_riga[col] = int(round(val_gps_sim)) if col in colonne_conteggi_interi else round(val_gps_sim, 1)
                for col in colonne_gps_pct:
                    nuova_riga[col] = round(float(df_base_gps[col].mean()), 1)

        df_nuova_riga = pd.DataFrame([nuova_riga])
        db_aggiornato = pd.concat([df_storico, df_nuova_riga], ignore_index=True)
        db_aggiornato.drop_duplicates(subset=['Date', 'Session', 'Players'], keep='last', inplace=True)
        save_local_database(db_aggiornato)
        
        if usato_media_generale: 
            st.warning(tr(
                f"Generata simulazione per {atleta}. NOTA: Non essendoci uno storico per la tipologia '{tipo_sess_effettiva}', è stata usata la media generale.",
                f"Generated simulation for {atleta}. NOTE: As no history existed for '{tipo_sess_effettiva}', general averages were used."
            ))
        else: 
            st.success(f"{t['sim_succ']} {atleta}.")

