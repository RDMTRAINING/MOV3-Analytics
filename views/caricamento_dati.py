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
    set_notification,
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
    get_atleti_dict,
    upsert_biometria_wearable_batch,
    slugify_name,
)
from pdf_generator import (
    crea_pdf_m0v3,
    crea_pdf_sessione_m0v3,
    crea_pdf_weekly_m0v3,
    crea_pdf_storico_m0v3,
    crea_pdf_medie_m0v3,
)


def _render_wearable_biometrics_importer_tab():
    """
    Modulo 3.2 v3.0 — Batch Importer CSV Wearable (Apple Watch / Sleep++, Oura, Whoop, Garmin):
    Esegue un Upsert Non-Distruttivo sulla tabella `wellness_mattutino` aggiornando esclusivamente
    `hrv_rmssd_ms`, `rhr_bpm`, `sonno_ore_reali` e `biometria_fonte` senza MAI sovrascrivere i 5 slider soggettivi.
    """
    import datetime as dt
    user = st.session_state.get('user')
    role = st.session_state.get('role', 'Staff')
    is_admin = (role in ('Super-Admin', 'Admin'))

    dict_atleti = get_atleti_dict(user=user, is_admin=is_admin, is_coach=True)
    if not dict_atleti:
        st.warning(tr("Nessun atleta associato disponibile per l'importazione biometrica.", "No associated athletes available for biometric import."))
        return

    nomi_atleti = sorted(list(dict_atleti.keys()))
    glob_ath = st.session_state.get('selected_athlete')
    idx_ath = nomi_atleti.index(glob_ath) if glob_ath in nomi_atleti else 0

    st.markdown(
        f"<div style='background:#081120; border:1px solid rgba(56,189,248,0.28); border-left:4px solid #38bdf8; border-radius:12px; padding:14px 18px; margin-bottom:16px;'>"
        f"<div style='font-size:13.5px; font-weight:800; color:#f8fafc; margin-bottom:4px;'><i class='bi bi-smartwatch' style='color:#38bdf8; margin-right:6px;'></i>"
        f"{tr('Ingestione Batch Biometria Passiva da Wearable (HRV rMSSD, RHR & Ore Sonno)', 'Batch Wearable Passive Biometrics Ingestion (HRV rMSSD, RHR & Sleep Hours)')}</div>"
        f"<div style='font-size:12px; color:#94a3b8; line-height:1.5;'>"
        f"{tr('Carica un file CSV esportato da Apple Health / Sleep++, Oura Ring, Whoop, Garmin Connect o il Template Standard M0V3. Il sistema esegue un <b>Upsert Non-Distruttivo</b> su <code>wellness_mattutino</code>: aggiorna esclusivamente i parametri oggettivi preservando al 100% i voti soggettivi già compilati dall’atleta.', 'Upload a CSV exported from Apple Health / Sleep++, Oura Ring, Whoop, Garmin Connect or the M0V3 Standard Template. The engine performs a <b>Non-Destructive Upsert</b> on <code>wellness_mattutino</code>: it updates only objective biometric fields while 100% preserving any subjective ratings already logged by the athlete.')}"
        f"</div></div>",
        unsafe_allow_html=True
    )

    c_cfg1, c_cfg2, c_cfg3 = st.columns([1.4, 1.2, 1.2])
    with c_cfg1:
        sel_atleta_bio = st.selectbox(
            tr("Atleta Destinatario Biometria", "Target Athlete for Biometrics"),
            nomi_atleti,
            index=idx_ath,
            key="bio_csv_target_athlete"
        )
        if sel_atleta_bio != st.session_state.get('selected_athlete'):
            st.session_state['selected_athlete'] = sel_atleta_bio
    with c_cfg2:
        fonti_w = ["Apple Watch / Sleep++", "Whoop", "Oura", "Garmin", "Manuale"]
        sel_fonte_default = st.selectbox(
            tr("Dispositivo / Fonte Wearable Predefinita", "Default Wearable Device / Source"),
            fonti_w,
            key="bio_csv_default_source"
        )
    with c_cfg3:
        st.markdown("<div style='font-size:11px; font-weight:700; color:#94a3b8; margin-bottom:4px;'>" + tr("Template CSV Standard M0V3", "M0V3 Standard CSV Template") + "</div>", unsafe_allow_html=True)
        today_iso = dt.date.today().strftime("%Y-%m-%d")
        yest_iso = (dt.date.today() - dt.timedelta(days=1)).strftime("%Y-%m-%d")
        template_csv = (
            "Date,HRV_rMSSD_ms,RHR_bpm,Sleep_Hours,Source\n"
            f"{yest_iso},74.5,48,7.75,{sel_fonte_default}\n"
            f"{today_iso},78.0,47,8.10,{sel_fonte_default}\n"
        )
        st.download_button(
            label=tr("Scarica Template Biometria CSV", "Download Biometrics CSV Template"),
            data=template_csv.encode("utf-8"),
            file_name="M0V3_Template_Biometria_Wearable.csv",
            mime="text/csv",
            use_container_width=True,
            key="btn_dl_bio_csv_template"
        )

    bio_file = st.file_uploader(
        tr("Trascina qui il file CSV Biometria Wearable (Apple Health, Oura, Whoop, Garmin o Template M0V3)", "Drag & drop Wearable Biometrics CSV file here"),
        type=["csv"],
        accept_multiple_files=False,
        key="uploader_bio_wearable_csv"
    )

    if bio_file is not None:
        try:
            df_bio_raw = leggi_csv_gps_robusto(bio_file)
        except Exception as e_b:
            st.error(f"{tr('Errore nella lettura del CSV:', 'Error reading CSV:')} {e_b}")
            return

        if df_bio_raw is None or df_bio_raw.empty:
            st.warning(tr("Il file CSV caricato è vuoto.", "Uploaded CSV file is empty."))
            return

        cols_raw = list(df_bio_raw.columns)

        def _guess_col(candidates):
            for c in cols_raw:
                c_low = str(c).strip().lower()
                for cand in candidates:
                    if cand == c_low or cand in c_low:
                        return c
            return "Non presente"

        guess_date = _guess_col(["date", "data", "day", "giorno", "timestamp", "summary_date", "calendar_date"])
        guess_hrv = _guess_col(["hrv_rmssd_ms", "rmssd", "hrv", "heart rate variability", "average_hrv"])
        guess_rhr = _guess_col(["rhr_bpm", "rhr", "resting heart rate", "fc riposo", "lowest_heart_rate", "resting_hr"])
        guess_sleep = _guess_col(["sleep_hours", "sonno_ore_reali", "sleep duration", "total_sleep", "ore sonno", "sleep", "asleep"])
        guess_source = _guess_col(["source", "fonte", "biometria_fonte", "device"])

        opts_map = ["Non presente"] + cols_raw
        with st.expander(tr("Mappatura Colonne CSV Wearable (Auto-Rilevata)", "Wearable CSV Column Mapping (Auto-Detected)"), expanded=True):
            cm1, cm2, cm3, cm4, cm5 = st.columns(5)
            with cm1:
                col_date = st.selectbox(tr("Colonna Data *", "Date Column *"), opts_map, index=opts_map.index(guess_date) if guess_date in opts_map else 0, key="map_bio_date")
            with cm2:
                col_hrv = st.selectbox(tr("Colonna HRV rMSSD (ms)", "HRV rMSSD (ms) Col"), opts_map, index=opts_map.index(guess_hrv) if guess_hrv in opts_map else 0, key="map_bio_hrv")
            with cm3:
                col_rhr = st.selectbox(tr("Colonna RHR (bpm)", "RHR (bpm) Col"), opts_map, index=opts_map.index(guess_rhr) if guess_rhr in opts_map else 0, key="map_bio_rhr")
            with cm4:
                col_sleep = st.selectbox(tr("Colonna Ore Sonno", "Sleep Hours Col"), opts_map, index=opts_map.index(guess_sleep) if guess_sleep in opts_map else 0, key="map_bio_sleep")
            with cm5:
                col_src = st.selectbox(tr("Colonna Fonte (Opz.)", "Source Col (Opt.)"), opts_map, index=opts_map.index(guess_source) if guess_source in opts_map else 0, key="map_bio_src")

        if col_date == "Non presente":
            st.warning(tr("Seleziona la colonna contenente la Data per procedere.", "Please select the Date column to proceed."))
            return

        parsed_records = []
        for _, r_b in df_bio_raw.iterrows():
            raw_d = r_b.get(col_date)
            dt_val = pd.to_datetime(raw_d, errors="coerce")
            if pd.isna(dt_val):
                dt_val = pd.to_datetime(str(raw_d), dayfirst=True, errors="coerce")
            if pd.isna(dt_val):
                continue
            d_iso = dt_val.strftime("%Y-%m-%d")

            def _clean_num(col_name, min_v, max_v, is_sleep=False):
                if col_name == "Non presente":
                    return None
                v = r_b.get(col_name)
                if pd.isna(v) or str(v).strip() == "":
                    return None
                try:
                    f_v = float(str(v).replace(",", ".").strip())
                    # Se la durata del sonno nel CSV wearable (es. Oura/Whoop) è espressa in minuti (>24 e <=960) o secondi (>960)
                    if is_sleep:
                        if f_v > 960:
                            f_v = f_v / 3600.0
                        elif f_v > 24:
                            f_v = f_v / 60.0
                    if min_v <= f_v <= max_v:
                        return round(f_v, 2 if is_sleep else 1)
                except Exception:
                    pass
                return None

            hrv_v = _clean_num(col_hrv, 10.0, 250.0, is_sleep=False)
            rhr_v = _clean_num(col_rhr, 30.0, 110.0, is_sleep=False)
            slp_v = _clean_num(col_sleep, 0.5, 16.0, is_sleep=True)
            src_v = str(r_b.get(col_src)).strip() if (col_src != "Non presente" and pd.notna(r_b.get(col_src)) and str(r_b.get(col_src)).strip()) else sel_fonte_default

            if any(x is not None for x in (hrv_v, rhr_v, slp_v)):
                parsed_records.append({
                    "data": d_iso,
                    "hrv_rmssd_ms": hrv_v,
                    "rhr_bpm": rhr_v,
                    "sonno_ore_reali": slp_v,
                    "biometria_fonte": src_v
                })

        if not parsed_records:
            st.warning(tr("Nessuna riga valida estratta dal CSV con i criteri di validazione (HRV 10-250ms, RHR 30-110bpm, Sonno 0.5-16h).", "No valid rows extracted from CSV within physiological ranges (HRV 10-250ms, RHR 30-110bpm, Sleep 0.5-16h)."))
            return

        df_prev_bio = pd.DataFrame(parsed_records).drop_duplicates(subset=["data"], keep="last").sort_values("data", ascending=False)
        st.markdown(f"#### {tr('Anteprima Dati Biometrici Pronti per Upsert Non-Distruttivo', 'Biometric Data Preview Ready for Non-Destructive Upsert')} ({len(df_prev_bio)} {tr('giornate', 'days')})")
        st.dataframe(df_prev_bio, use_container_width=True, hide_index=True)

        if st.button(tr("Importa e Sincronizza Biometria su Wellness Mattutino", "Import & Sync Biometrics onto Morning Wellness"), type="primary", use_container_width=True, key="btn_exec_bio_upsert"):
            target_atl_id = dict_atleti.get(sel_atleta_bio)
            prof_id = getattr(user, "id", None)
            ok_b, n_upd, n_ins, err_b = upsert_biometria_wearable_batch(
                atleta_id=target_atl_id,
                profilo_id=prof_id,
                records_list=df_prev_bio.to_dict(orient="records")
            )
            if ok_b:
                set_notification(
                    title=tr("Biometria Wearable Sincronizzata", "Wearable Biometrics Synchronized"),
                    message=tr(
                        f"Sincronizzate {n_upd + n_ins} giornate biometriche per {sel_atleta_bio} ({n_upd} aggiornate preservando i voti soggettivi, {n_ins} nuove).",
                        f"Synchronized {n_upd + n_ins} biometric days for {sel_atleta_bio} ({n_upd} updated preserving subjective ratings, {n_ins} newly created)."
                    ),
                    tipo="modal",
                    details=[
                        tr(f"Atleta: {sel_atleta_bio}", f"Athlete: {sel_atleta_bio}"),
                        tr(f"Giornate aggiornate (Upsert Non-Distruttivo): {n_upd}", f"Updated days (Non-Destructive Upsert): {n_upd}"),
                        tr(f"Nuove giornate inserite: {n_ins}", f"Newly inserted days: {n_ins}"),
                        tr(f"Fonte Wearable: {sel_fonte_default}", f"Wearable Source: {sel_fonte_default}")
                    ]
                )
                st.rerun()
            else:
                st.error(f"{tr('Errore durante il salvataggio biometrico:', 'Error during biometric save:')} {err_b}")


def render_caricamento_dati(t):
    render_page_header(t['up_title'], t['home_upload_desc'], "DATA INGESTION")

    # Verifica permesso RBAC per il tab di Import Biometria Wearable (CSV)
    role_curr = st.session_state.get('role', 'Staff')
    perm_set = st.session_state.get('user_permessi_moduli')
    can_import_bio = (
        role_curr == 'Super-Admin'
        or perm_set is None
        or ('Pagine Operative', 'Import Biometria Wearable (CSV)') in perm_set
        or ('Pagine Operative', 'Caricamento Dati') in perm_set
    )

    if can_import_bio:
        tab_gps_csv, tab_bio_csv = st.tabs([
            tr("Ingestione Telemetria GPS (CSV)", "GPS Telemetry Ingestion (CSV)"),
            tr("Import Biometria Wearable (CSV Apple/Oura/Whoop/Garmin)", "Wearable Biometrics Import (CSV Apple/Oura/Whoop/Garmin)")
        ])
        with tab_bio_csv:
            _render_wearable_biometrics_importer_tab()
        ctx_container = tab_gps_csv
    else:
        ctx_container = st.container()

    with ctx_container:
        _render_gps_csv_ingestion_body(t)


def _render_gps_csv_ingestion_body(t):
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

    from utils import render_pulsante_segnalazione_gps, is_servizio_tagli_gps_abilitato
    if is_servizio_tagli_gps_abilitato():
        c_up_box1, c_up_box2 = st.columns([2.5, 1.5])
        with c_up_box1:
            st.markdown(
                f"<div style='font-size:12px; color:#94a3b8; padding-top:6px;'>"
                f"<i class='bi bi-info-circle' style='color:#38bdf8;'></i> {tr('Hai scaricato sessioni da K-Sport che devono ancora essere tagliate da Riccardo?', 'Have you downloaded sessions from K-Sport that still need to be trimmed by Riccardo?')}"
                f"</div>",
                unsafe_allow_html=True
            )
        with c_up_box2:
            render_pulsante_segnalazione_gps(
                key="btn_caricamento_segnala_gps",
                default_atleta=st.session_state.get('selected_athlete'),
                lista_atleti=atleti_disponibili,
                use_container_width=True
            )
        st.markdown("<div style='margin-bottom: 8px;'></div>", unsafe_allow_html=True)

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
                        glob_ath = st.session_state.get('selected_athlete')
                        idx_up_ath = atleti_disponibili.index(glob_ath) if glob_ath in atleti_disponibili else 0
                        atleta_scelto = st.selectbox(t['assign_to'], atleti_disponibili, index=idx_up_ath, key=f"p_{f_key}")
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
                        tr(f"{len(righe_scelte_idx)} RIGA/E PRONTA/E PER L'IMPORTAZIONE", f"{len(righe_scelte_idx)} ROW(S) READY TO IMPORT")
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
                set_notification(
                    title=tr("Importazione CSV Completata con Successo", "CSV Import Completed Successfully"),
                    message=tr(
                        f"Importate {tot_righe_importate} sessioni pulite e integrate nel database di M0V3 Analytics.",
                        f"Successfully imported and integrated {tot_righe_importate} clean sessions into the M0V3 Analytics database."
                    ),
                    tipo="modal",
                    details=[
                        tr(f"File elaborati: {len(dataframes)}", f"Processed files: {len(dataframes)}"),
                        tr(f"Nuove sessioni/righe salvate: {tot_righe_importate}", f"New saved sessions/rows: {tot_righe_importate}"),
                        tr("Database storico sincronizzato e ricalcolato", "Historical database synchronized and recalculated")
                    ]
                )
                st.rerun()

