# Copyright 2026 Riccardo Di Maio - M0V3 S.r.l. Tutti i diritti riservati.
# Proprietary Sports Science & Clinical Performance Intelligence Architecture.
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
    render_page_header,
    render_print_header,
    tr,
)
from utils import (
    supabase,
    supabase_admin,
    COLONNE_GPS,
    COLONNE_DATABASE,
    get_tipologie_sessione,
    converti_durata_in_minuti,
    leggi_csv_gps_robusto,
    applica_mappatura_csv,
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
    slugify_name,
)
from pdf_generator import (
    crea_pdf_m0v3,
    crea_pdf_sessione_m0v3,
    crea_pdf_weekly_m0v3,
    crea_pdf_storico_m0v3,
    crea_pdf_medie_m0v3,
)

def render_caricamento_dati(t):
    render_page_header(t['up_title'], t['home_upload_desc'], "DATA INGESTION")
    utente_target_email = st.session_state['user'].email
    utente_target_id = st.session_state['user'].id
    
    if st.session_state['role'] == 'Super-Admin':
        atleti_disponibili = get_tutti_gli_atleti()
        res_profili = supabase.table('profili').select('*').execute()
        if res_profili.data:
            st.info(t['up_admin_info'])
            lista_email_utenti = [p['email'] for p in res_profili.data]
            utente_delega_email = st.selectbox(t['up_delegate'], [t['up_my_map']] + lista_email_utenti)
            if utente_delega_email != t['up_my_map']:
                utente_target_email = utente_delega_email
                utente_target_id = next((p['id'] for p in res_profili.data if p['email'] == utente_delega_email), st.session_state['user'].id)
    else:
        atleti_disponibili = get_atleti_associati(st.session_state['user'].id)

    if not atleti_disponibili: st.warning(t['up_no_atl']); return
        
    res_mappa = supabase.table('mappatura_csv').select('mapping').eq('profilo_id', utente_target_id).execute()
    mappa_utente = res_mappa.data[0]['mapping'] if res_mappa.data else None
    
    if not mappa_utente: st.warning(t['up_no_map'])

    uploaded_files = st.file_uploader(t['drag_csv'], type=['csv'], accept_multiple_files=True)
    if uploaded_files:
        parsed_files_data = {}
        for idx_f, file in enumerate(uploaded_files):
            f_key = f"{idx_f}_{file.name}"
            base_filename = os.path.splitext(file.name)[0].strip()
            try:
                df_raw = leggi_csv_gps_robusto(file)
                df_mapped, rep_map = applica_mappatura_csv(df_raw, mappa_utente)
                if 'Players' in df_mapped.columns:
                    mask_not_avg = df_mapped['Players'].astype(str).str.strip().str.lower() != 'team average'
                    df_raw = df_raw.loc[mask_not_avg].reset_index(drop=True)
                    df_mapped = df_mapped.loc[mask_not_avg].reset_index(drop=True)
            except Exception as err_read:
                st.error(f"Impossibile leggere {file.name}: {err_read}")
                continue

            if df_mapped.empty:
                st.warning(f"Il file {file.name} non contiene righe valide.")
                continue

            # Data predefinita letta dalla prima riga valida del CSV (o data odierna)
            data_default = pd.Timestamp.today().date()
            if 'Date' in df_mapped.columns and pd.notna(df_mapped['Date'].iloc[0]):
                dt_parsed = pd.to_datetime(str(df_mapped['Date'].iloc[0]), dayfirst=True, errors='coerce')
                if pd.notna(dt_parsed):
                    data_default = dt_parsed.date()

            with st.expander(f"{t['ctx_assign']} {file.name}", expanded=True):
                # 1. Gestione intelligente righe multiple (es. Full Match vs 1st Set / 2nd Set o più giocatori)
                righe_scelte_idx = [0]
                if len(df_mapped) > 1:
                    opzioni_righe = {}
                    default_righe = []
                    for r_i in range(len(df_mapped)):
                        row_m = df_mapped.iloc[r_i]
                        s_val = str(row_m.get('Session', '')).strip()
                        if not s_val or s_val.lower() in ('nan', 'none', '0', '0.0'):
                            s_val = f"Riga {r_i + 1}"
                        p_val = str(row_m.get('Players', '')).strip()
                        p_txt = f" · Atleta CSV: {p_val}" if p_val and p_val.lower() not in ('nan', 'none', '0', '0.0') else ""
                        m_val = float(row_m.get('Minuti', 0.0))
                        tl_val = float(row_m.get('Training Load', 0.0))
                        lbl_r = f"#{r_i + 1} — {s_val}{p_txt} ({m_val:.0f} min | TL: {tl_val:.0f})"
                        opzioni_righe[lbl_r] = r_i
                        if any(k_full in s_val.lower() for k_full in ('full match', 'full session', 'full', 'total', 'totale', 'intera')):
                            default_righe.append(lbl_r)
                    if not default_righe:
                        default_righe = [list(opzioni_righe.keys())[0]]

                    lbl_sel_righe = st.multiselect(
                        tr(
                            f"Questo CSV contiene {len(df_mapped)} righe (es. split/set o più sessioni). Seleziona quali righe importare:",
                            f"This CSV contains {len(df_mapped)} rows (e.g. splits/sets). Select which rows to import:"
                        ),
                        options=list(opzioni_righe.keys()),
                        default=default_righe,
                        key=f"rows_{f_key}"
                    )
                    righe_scelte_idx = [opzioni_righe[k] for k in lbl_sel_righe] if lbl_sel_righe else []

                # Nome sessione predefinito dalla prima riga selezionata (o dal nome del file)
                idx_ref = righe_scelte_idx[0] if righe_scelte_idx else 0
                raw_sess_val = str(df_mapped.iloc[idx_ref].get('Session', '')).strip()
                if not raw_sess_val or raw_sess_val.lower() in ('nan', 'none', '0', '0.0', '<na>'):
                    default_sess_name = base_filename
                else:
                    default_sess_name = raw_sess_val

                col_top_atl, col_top_name, col_top_dt = st.columns([1.2, 1.5, 1])
                with col_top_atl:
                    if st.session_state['role'] == 'Atleta':
                        atleta_scelto = atleti_disponibili[0]
                        st.text_input(t['assign_to'], value=atleta_scelto, disabled=True, key=f"p_{f_key}")
                    else:
                        atleta_scelto = st.selectbox(t['assign_to'], atleti_disponibili, key=f"p_{f_key}")
                with col_top_name:
                    nome_sessione_edit = st.text_input(
                        tr("Nome Identificativo Sessione", "Session Name"),
                        value=default_sess_name,
                        key=f"sname_{f_key}",
                        help=tr("Pre-compilato dal CSV o dal nome file. Puoi personalizzarlo prima di salvare.", "Pre-filled from CSV or filename. You can edit it before saving.")
                    )
                with col_top_dt:
                    data_modificata = st.date_input(tr("Data Sessione", "Session Date"), value=data_default, key=f"d_{f_key}")

                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    campo = st.selectbox(t['surface'], ["Hard", "Clay", "Grass"], key=f"c_{f_key}")
                with col2:
                    ambiente = st.radio(t['environment'], ["Outdoor", "Indoor"], horizontal=True, key=f"a_{f_key}")
                with col3:
                    sparring = st.number_input(t['sparring'], min_value=0, step=1, key=f"s_{f_key}")
                with col4:
                    opz = get_tipologie_sessione(uploader_email=utente_target_email, atleta_nome=atleta_scelto) + [t['add_new']]
                    if st.session_state.get(f"t_{f_key}") not in opz:
                        st.session_state[f"t_{f_key}"] = opz[0]
                    sess = st.selectbox(t['sess_type'], opz, key=f"t_{f_key}")
                    sess_effettiva = st.text_input(t['spec_new'], key=f"n_{f_key}") if sess == t['add_new'] else sess

                # 2. Striscia di anteprima immediata dei 6 parametri principali M0V3
                if righe_scelte_idx:
                    df_sel_preview = df_mapped.iloc[righe_scelte_idx]
                    prev_min = float(df_sel_preview['Minuti'].sum())
                    prev_tl = float(df_sel_preview['Training Load'].sum())
                    prev_tl_h = float(df_sel_preview['TL_High'].sum())
                    prev_acc = float(df_sel_preview['High Accel IMU'].sum())
                    prev_dec = float(df_sel_preview['High Decel IMU'].sum())
                    is_indoor_sel = str(ambiente).strip().lower() == 'indoor'
                    prev_dist = 0.0 if is_indoor_sel else float(df_sel_preview['DISTANCE'].sum())
                    dist_str = f"0 m (Indoor)" if is_indoor_sel else f"{prev_dist:.0f} m"

                    # Controlla se i parametri chiave sono a zero per avvisare l'utente
                    alert_zero = (prev_min <= 0 and prev_tl <= 0)
                    badge_status_bg = "#fef3c7" if alert_zero else "rgba(16,185,129,0.18)"
                    badge_status_fg = "#b45309" if alert_zero else "#34d399"
                    badge_status_txt = (
                        tr("VERIFICA MAPPATURA (VALORI A ZERO)", "CHECK MAPPING (ZERO VALUES)")
                        if alert_zero else
                        tr(f"✓ {len(righe_scelte_idx)} RIGA/E PRONTA/E PER L'IMPORTAZIONE", f"✓ {len(righe_scelte_idx)} ROW(S) READY TO IMPORT")
                    )

                    preview_html = (
                        "<div style='margin-top:10px; background:#0f172a; border-radius:10px; padding:12px 16px; color:white; font-family:\"Inter\", sans-serif;'>"
                        "<div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; flex-wrap:wrap; gap:8px;'>"
                        f"<span style='font-size:11px; font-weight:800; color:#94a3b8; text-transform:uppercase; letter-spacing:0.7px;'>{tr('Anteprima Parametri M0V3 Estratti', 'Extracted M0V3 Parameters Preview')}</span>"
                        f"<span style='background:{badge_status_bg}; color:{badge_status_fg}; font-size:10px; font-weight:800; padding:3px 9px; border-radius:5px;'>{badge_status_txt}</span>"
                        "</div>"
                        "<div style='display:grid; grid-template-columns:repeat(6, 1fr); gap:10px;'>"
                        f"<div style='background:rgba(255,255,255,0.06); padding:8px 10px; border-radius:7px; border-left:3px solid #38bdf8;'><div style='font-size:10px; color:#94a3b8; font-weight:700;'>MINUTI</div><div style='font-size:16px; font-weight:900; color:#f8fafc;'>{prev_min:.1f} min</div></div>"
                        f"<div style='background:rgba(255,255,255,0.06); padding:8px 10px; border-radius:7px; border-left:3px solid #10b981;'><div style='font-size:10px; color:#94a3b8; font-weight:700;'>TRAINING LOAD</div><div style='font-size:16px; font-weight:900; color:#f8fafc;'>{prev_tl:.0f}</div></div>"
                        f"<div style='background:rgba(255,255,255,0.06); padding:8px 10px; border-radius:7px; border-left:3px solid #f59e0b;'><div style='font-size:10px; color:#94a3b8; font-weight:700;'>TL HIGH</div><div style='font-size:16px; font-weight:900; color:#f8fafc;'>{prev_tl_h:.0f}</div></div>"
                        f"<div style='background:rgba(255,255,255,0.06); padding:8px 10px; border-radius:7px; border-left:3px solid #ef4444;'><div style='font-size:10px; color:#94a3b8; font-weight:700;'>HIGH ACCEL IMU</div><div style='font-size:16px; font-weight:900; color:#f8fafc;'>{prev_acc:.0f}</div></div>"
                        f"<div style='background:rgba(255,255,255,0.06); padding:8px 10px; border-radius:7px; border-left:3px solid #ec4899;'><div style='font-size:10px; color:#94a3b8; font-weight:700;'>HIGH DECEL IMU</div><div style='font-size:16px; font-weight:900; color:#f8fafc;'>{prev_dec:.0f}</div></div>"
                        f"<div style='background:rgba(255,255,255,0.06); padding:8px 10px; border-radius:7px; border-left:3px solid #8b5cf6;'><div style='font-size:10px; color:#94a3b8; font-weight:700;'>DISTANZA GPS</div><div style='font-size:16px; font-weight:900; color:#f8fafc;'>{dist_str}</div></div>"
                        "</div></div>"
                    )
                    st.markdown(preview_html, unsafe_allow_html=True)
                else:
                    st.warning(tr("Seleziona almeno una riga da importare per questo file.", "Select at least one row to import for this file."))

                parsed_files_data[f_key] = {
                    "file_name": file.name,
                    "df_mapped": df_mapped,
                    "righe_idx": righe_scelte_idx,
                    "nome_sessione": nome_sessione_edit.strip() if nome_sessione_edit.strip() else default_sess_name,
                    "default_sess_name": default_sess_name,
                    "data_str": data_modificata.strftime('%d/%m/%Y'),
                    "campo": campo,
                    "ambiente": ambiente,
                    "sparring": int(sparring),
                    "tipologia": sess_effettiva.strip() if sess_effettiva and sess_effettiva.strip() else "Non definita",
                    "atleta": atleta_scelto,
                }

        if parsed_files_data and st.button(t['btn_process'], type="primary"):
            dataframes = []
            tot_righe_importate = 0
            for f_key, info in parsed_files_data.items():
                if not info["righe_idx"]:
                    continue
                try:
                    df_sub = info["df_mapped"].iloc[info["righe_idx"]].copy().reset_index(drop=True)
                    nome_base = info["nome_sessione"]
                    if len(df_sub) == 1:
                        df_sub['Session'] = nome_base
                    else:
                        # Se l'utente importa più righe dallo stesso CSV, preserva lo split di ciascuna riga
                        nomi_multi = []
                        for idx_r in range(len(df_sub)):
                            orig_s = str(df_sub.iloc[idx_r].get('Session', '')).strip()
                            if not orig_s or orig_s.lower() in ('nan', 'none', '0', '0.0'):
                                orig_s = f"Split {idx_r + 1}"
                            if nome_base != info["default_sess_name"]:
                                nomi_multi.append(f"{nome_base} - {orig_s}")
                            else:
                                nomi_multi.append(orig_s if orig_s != info["default_sess_name"] else f"{nome_base} (#{idx_r + 1})")
                        df_sub['Session'] = nomi_multi

                    df_sub['Date'] = info['data_str']
                    df_sub['Players'] = info['atleta']
                    df_sub['Tipologia Campo'] = info['campo']
                    df_sub['Ambiente'] = info['ambiente']
                    df_sub['Minuti Sparring'] = info['sparring']
                    df_sub['Tipologia Sessione'] = info['tipologia']
                    df_sub['File_Name'] = info['file_name']
                    df_sub['Uploader_Email'] = utente_target_email
                    df_sub['Dato_Simulato'] = False

                    # Se la sessione è Indoor, azzera automaticamente le metriche satellitari GPS
                    if str(info['ambiente']).strip().lower() == 'indoor':
                        for c_gps in COLONNE_GPS:
                            df_sub[c_gps] = 0.0

                    df_sub = df_sub[COLONNE_DATABASE]
                    dataframes.append(df_sub)
                    tot_righe_importate += len(df_sub)
                except Exception as e:
                    st.error(f"{tr('Errore su', 'Error on')} {info['file_name']}: {e}")

            if dataframes:
                master_df = pd.concat(dataframes, ignore_index=True)
                db_attuale = load_local_database()
                db_aggiornato = pd.concat([db_attuale, master_df], ignore_index=True) if not db_attuale.empty else master_df
                # Deduplicazione sicura: sovrascrive solo se coincidono Data, Sessione, Giocatore E Nome File
                # per evitare che file o split diversi nella stessa data si cancellino a vicenda
                dedup_cols = ['Date', 'Session', 'Players']
                if 'File_Name' in db_aggiornato.columns:
                    dedup_cols.append('File_Name')
                db_aggiornato.drop_duplicates(subset=dedup_cols, keep='last', inplace=True)
                save_local_database(db_aggiornato)
                st.success(
                    tr(
                        f"Elaborazione completata! Importate {tot_righe_importate} sessioni pulite e salvate nel database.",
                        f"Processing complete! Imported {tot_righe_importate} clean sessions into the database."
                    )
                )

