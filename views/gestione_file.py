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
    DB_PARQUET_PATH,
    CATALOGO_REPORT,
    COLONNE_STANDARD,
    METRICHE_VOLUME,
    METRICHE_INTENSITA,
    LEGENDA_ACWR,
    render_page_header,
    render_print_header,
    tr,
)
import utils as _utils_mod
from utils import (
    supabase,
    supabase_admin,
    COLONNE_GPS,
    CANONICAL_TIPOLOGIE_SESSIONE,
    get_tipologie_sessione,
    converti_durata_in_minuti,
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
    slugify_name,
    get_atleti_dict,
    get_governance_records,
    soft_delete_rpe_sessione,
    ripristina_rpe_sessione,
    soft_delete_wellness_mattutino,
    ripristina_wellness_mattutino,
    modifica_tracciata_rpe,
    modifica_tracciata_wellness,
    check_native_governance_columns,
)
get_cloud_snapshot_status = getattr(
    _utils_mod,
    "get_cloud_snapshot_status",
    lambda: {"active": True, "max_date": "N/D", "total_rows": 0},
)
from pdf_generator import (
    crea_pdf_m0v3,
    crea_pdf_sessione_m0v3,
    crea_pdf_weekly_m0v3,
    crea_pdf_storico_m0v3,
    crea_pdf_medie_m0v3,
)

def render_gestione_file(t):
    render_page_header(tr("Gestione File e Sessioni Caricate", "Uploaded Files & Sessions Management"), t['home_file_desc'], "DATABASE MANAGEMENT")

    # --- RIGA DIAGNOSTICA CLOUD SNAPSHOT & DOWNLOAD MASTER PARQUET ---
    snap_stat = get_cloud_snapshot_status()
    c_diag1, c_diag2 = st.columns([3.2, 1.8])
    with c_diag1:
        st.markdown(
            f"<div style='background:rgba(16,185,129,0.14); border:1px solid #10b981; border-left:4px solid #10b981; border-radius:10px; padding:10px 14px; margin-bottom:14px; font-family:\"Inter\",sans-serif; font-size:12.5px; color:#34d399; display:flex; align-items:center; gap:8px;'>"
            f"<i class='bi bi-cloud-check-fill' style='color:#10b981; font-size:16px;'></i>"
            f"<span><b>Cloud Snapshot Attivo</b> | Ultima Data GPS Salvata: <b>{snap_stat.get('max_date', 'N/D')}</b> | Totale Righe: <b>{snap_stat.get('total_rows', 0)}</b></span>"
            f"</div>",
            unsafe_allow_html=True
        )
    with c_diag2:
        if st.session_state.get('role') == 'Super-Admin' and os.path.exists(DB_PARQUET_PATH):
            try:
                with open(DB_PARQUET_PATH, "rb") as f_p:
                    p_bytes = f_p.read()
                st.download_button(
                    label="Scarica database_storico.parquet Consolidato",
                    data=p_bytes,
                    file_name="database_storico.parquet",
                    mime="application/octet-stream",
                    key="btn_dl_master_parquet_gestione_file",
                    use_container_width=True
                )
            except Exception:
                pass

    # --- TAB PRINCIPALI: SESSIONI GPS vs DATA GOVERNANCE & AUDIT TRAIL ---
    tab_gps, tab_gov = st.tabs([
        tr("Archivio Sessioni GPS & Database", "GPS Sessions Archive & Database"),
        tr("Data Governance & Audit Trail (RPE / Wellness)", "Data Governance & Audit Trail (RPE / Wellness)")
    ])

    with tab_gps:
        _render_gps_archive_tab(t)

    with tab_gov:
        _render_data_governance_tab(t)


def _render_gps_archive_tab(t):
    """Gestione delle sessioni GPS consolidate in database_storico.parquet."""
    df_storico = load_local_database()
    if df_storico.empty:
        st.info(tr("Nessun dato presente nel database.", "No data found in the database."))
        return

    user_email = st.session_state['user'].email
    if st.session_state['role'] == 'Super-Admin':
        atleti_consentiti = get_tutti_gli_atleti()
        df_base_perm = df_storico.copy()
    else:
        atleti_consentiti = get_atleti_associati(st.session_state['user'].id)
        mask_perm = df_storico['Players'].isin(atleti_consentiti) | (df_storico['Uploader_Email'] == user_email)
        df_base_perm = df_storico[mask_perm].copy()

    if df_base_perm.empty:
        st.warning(tr("Nessuna sessione disponibile per il tuo profilo o per gli atleti associati.", "No sessions available for your profile or associated athletes."))
        return

    # --- BARRA FILTRI RAPIDI ---
    st.markdown(f"### {tr('Filtri Rapidi Database GPS', 'GPS Database Quick Filters')}")
    lbl_tutti_utenti = tr("Tutti gli utenti", "All users")
    lbl_tutti_atleti = tr("Tutti gli atleti", "All athletes")
    lbl_tutte_tipologie = tr("Tutte le tipologie", "All types")

    if st.session_state['role'] == 'Super-Admin':
        f_col_u, f_col_a, f_col_t, f_col_o = st.columns(4)
        with f_col_u:
            utenti_presenti = sorted([str(u) for u in df_base_perm['Uploader_Email'].dropna().unique() if str(u).strip()])
            filtro_utente = st.selectbox(tr("Account Uploader:", "Uploader Account:"), [lbl_tutti_utenti] + utenti_presenti, key="gf_flt_user")
    else:
        filtro_utente = lbl_tutti_utenti
        f_col_a, f_col_t, f_col_o = st.columns(3)

    df_scoped_ath = df_base_perm.copy()
    if filtro_utente != lbl_tutti_utenti:
        df_scoped_ath = df_scoped_ath[df_scoped_ath['Uploader_Email'] == filtro_utente]

    with f_col_a:
        atleti_in_db = sorted([str(p) for p in df_scoped_ath['Players'].dropna().unique() if str(p).strip()])
        opts_atleti = [lbl_tutti_atleti] + atleti_in_db
        if st.session_state.get('gf_flt_ath') not in opts_atleti:
            st.session_state['gf_flt_ath'] = lbl_tutti_atleti
        filtro_atleta = st.selectbox(tr("Atleta:", "Athlete:"), opts_atleti, key="gf_flt_ath")

    df_scoped_tipi = df_scoped_ath.copy()
    if filtro_atleta != lbl_tutti_atleti:
        df_scoped_tipi = df_scoped_tipi[df_scoped_tipi['Players'] == filtro_atleta]

    with f_col_t:
        canonical_rank = {name.lower(): idx for idx, name in enumerate(CANONICAL_TIPOLOGIE_SESSIONE)}
        raw_tipi = [str(tp) for tp in df_scoped_tipi['Tipologia Sessione'].dropna().unique() if str(tp).strip()]
        tipi_in_db = sorted(raw_tipi, key=lambda x: (canonical_rank.get(x.lower(), 99), x))
        opts_tipi = [lbl_tutte_tipologie] + tipi_in_db
        if st.session_state.get('gf_flt_type') not in opts_tipi:
            st.session_state['gf_flt_type'] = lbl_tutte_tipologie
        filtro_tipo = st.selectbox(tr("Tipologia Sessione:", "Session Type:"), opts_tipi, key="gf_flt_type")
    with f_col_o:
        opt_orig = [
            tr("Tutte (Reali + Simulate)", "All (Real + Simulated)"),
            tr("Solo Reali (Sensore)", "Real Sensor Only"),
            tr("Solo Simulate", "Simulated Only")
        ]
        filtro_origine = st.selectbox(tr("Origine Dato:", "Data Source:"), opt_orig, key="gf_flt_orig")

    df_vista = df_base_perm.copy()
    if filtro_utente != lbl_tutti_utenti:
        df_vista = df_vista[df_vista['Uploader_Email'] == filtro_utente]
    if filtro_atleta != lbl_tutti_atleti:
        df_vista = df_vista[df_vista['Players'] == filtro_atleta]
    if filtro_tipo != lbl_tutte_tipologie:
        df_vista = df_vista[df_vista['Tipologia Sessione'] == filtro_tipo]
    if filtro_origine == opt_orig[1]:
        df_vista = df_vista[df_vista['Dato_Simulato'] == False]
    elif filtro_origine == opt_orig[2]:
        df_vista = df_vista[df_vista['Dato_Simulato'] == True]

    if df_vista.empty:
        st.warning(tr("Nessuna sessione trovata con i filtri selezionati.", "No sessions found with selected filters."))
        return

    df_vista_sort = df_vista.copy()
    df_vista_sort['_dt_sort'] = pd.to_datetime(df_vista_sort['Date'], format="%d/%m/%Y", errors='coerce')
    df_vista_sort.sort_values(by=['_dt_sort'], ascending=False, inplace=True)

    mappa_sessioni_idx = {}
    for idx_row, row_s in df_vista_sort.iterrows():
        dt_s = str(row_s.get('Date', 'N/D'))
        pl_s = str(row_s.get('Players', 'N/D'))
        nm_s = str(row_s.get('Session', 'N/D'))
        tp_s = str(row_s.get('Tipologia Sessione', 'N/D'))
        am_s = str(row_s.get('Ambiente', 'Outdoor'))
        sim_tag = " | SIMULATO" if bool(row_s.get('Dato_Simulato', False)) else " | REALE"
        lbl_univoca = f"{dt_s} — {pl_s} — {nm_s} [{tp_s} | {am_s}{sim_tag}] (ID #{idx_row})"
        mappa_sessioni_idx[lbl_univoca] = idx_row

    placeholder_sel = tr("Seleziona una sessione...", "Select a session...")
    lista_etichette_sessioni = [placeholder_sel] + list(mappa_sessioni_idx.keys())

    st.divider()
    st.markdown(f"### {tr('Modifica Informazioni Sessione GPS', 'Edit GPS Session Information')}")
    st.info(tr("Seleziona una sessione specifica per modificarne Atleta, Data, Nome, Durata, Superficie, Ambiente, Sparring o Tipologia senza dover ricaricare il file CSV.", "Select a specific session to edit Athlete, Date, Name, Duration, Surface, Environment, Sparring or Type without re-uploading the CSV file."))

    etichetta_da_modificare = st.selectbox(tr("Scegli la sessione da modificare:", "Choose session to edit:"), lista_etichette_sessioni, key="sel_mod")

    if etichetta_da_modificare != placeholder_sel:
        idx_target = mappa_sessioni_idx[etichetta_da_modificare]
        riga_attuale = df_storico.loc[idx_target]

        curr_date_str = str(riga_attuale.get('Date', ''))
        curr_date_pd = pd.to_datetime(curr_date_str, format="%d/%m/%Y", errors='coerce')
        curr_date_obj = curr_date_pd.date() if pd.notna(curr_date_pd) else pd.Timestamp.today().date()

        curr_player = str(riga_attuale.get('Players', ''))
        curr_name = str(riga_attuale.get('Session', ''))
        curr_minuti = float(riga_attuale.get('Minuti', 60.0)) if pd.notna(riga_attuale.get('Minuti')) else 60.0
        curr_campo = str(riga_attuale.get('Tipologia Campo', 'Hard')) if pd.notna(riga_attuale.get('Tipologia Campo')) else 'Hard'
        curr_amb = str(riga_attuale.get('Ambiente', 'Outdoor')) if pd.notna(riga_attuale.get('Ambiente')) else 'Outdoor'
        curr_tipo = str(riga_attuale.get('Tipologia Sessione', 'Match')) if pd.notna(riga_attuale.get('Tipologia Sessione')) else 'Match'
        curr_sparring = int(float(riga_attuale.get('Minuti Sparring', 0))) if pd.notna(riga_attuale.get('Minuti Sparring')) else 0
        curr_simulato = bool(riga_attuale.get('Dato_Simulato', False))

        opzioni_atleti_mod = list(dict.fromkeys((atleti_consentiti or []) + atleti_in_db + ([curr_player] if curr_player else [])))
        idx_player = opzioni_atleti_mod.index(curr_player) if curr_player in opzioni_atleti_mod else 0

        opzioni_tipologie_mod = get_tipologie_sessione(None if st.session_state['role'] == 'Super-Admin' else user_email, atleta_nome=curr_player)
        if curr_tipo and curr_tipo not in opzioni_tipologie_mod:
            opzioni_tipologie_mod.append(curr_tipo)
        idx_tipo = opzioni_tipologie_mod.index(curr_tipo) if curr_tipo in opzioni_tipologie_mod else 0

        with st.form("form_modifica_info"):
            c1, c2, c3 = st.columns(3)
            with c1:
                new_player = st.selectbox(tr("Atleta Assegnato", "Assigned Athlete"), opzioni_atleti_mod, index=idx_player)
                new_date = st.date_input(tr("Data Sessione", "Session Date"), value=curr_date_obj)
                new_name = st.text_input(tr("Nome Sessione", "Session Name"), value=curr_name)
                opt_reale = tr("Reale (Sensore GPS)", "Real (GPS Sensor)")
                opt_sim = tr("Simulato (Senza GPS)", "Simulated (No GPS)")
                new_origine_sel = st.radio(
                    tr("Stato Origine Dato", "Data Origin Status"),
                    [opt_reale, opt_sim],
                    index=1 if curr_simulato else 0,
                    horizontal=True
                )
            with c2:
                opzioni_campo = ["Hard", "Clay", "Grass"]
                if curr_campo not in opzioni_campo:
                    opzioni_campo.append(curr_campo)
                idx_campo = opzioni_campo.index(curr_campo)
                new_campo = st.selectbox(tr("Superficie", "Surface"), opzioni_campo, index=idx_campo)
                new_amb = st.radio(tr("Ambiente", "Environment"), ["Outdoor", "Indoor"], index=0 if str(curr_amb).strip().lower() != "indoor" else 1, horizontal=True)
                new_minuti = st.number_input(tr("Durata (Minuti)", "Duration (Minutes)"), min_value=1.0, value=max(1.0, float(curr_minuti)), step=1.0)
            with c3:
                new_tipo_sel = st.selectbox(tr("Tipologia Sessione", "Session Type"), opzioni_tipologie_mod, index=idx_tipo)
                new_tipo_custom = st.text_input(tr("Oppure Nuova Tipologia Personalizzata (opzionale)", "Or Custom Session Type (optional)"), value="", placeholder=tr("Lascia vuoto per usare il menu sopra", "Leave empty to use dropdown"))
                new_sparring = st.number_input(tr("Minuti Sparring", "Sparring Minutes"), min_value=0, step=1, value=int(curr_sparring))

            if st.form_submit_button(tr("Salva Nuove Info", "Save New Info"), type="primary"):
                is_sim_final = (new_origine_sel == opt_sim)
                tipo_finale = new_tipo_custom.strip() if new_tipo_custom.strip() else new_tipo_sel

                nome_pulito = new_name.strip() if new_name.strip() else curr_name
                if not is_sim_final and nome_pulito.endswith('*'):
                    nome_pulito = nome_pulito.rstrip('*').strip()

                df_storico.loc[idx_target, 'Players'] = new_player
                df_storico.loc[idx_target, 'Date'] = new_date.strftime("%d/%m/%Y")
                df_storico.loc[idx_target, 'Session'] = nome_pulito
                df_storico.loc[idx_target, 'Minuti'] = round(float(new_minuti), 1)
                df_storico.loc[idx_target, 'Tipologia Campo'] = new_campo
                df_storico.loc[idx_target, 'Ambiente'] = new_amb
                df_storico.loc[idx_target, 'Tipologia Sessione'] = tipo_finale
                df_storico.loc[idx_target, 'Minuti Sparring'] = int(new_sparring)
                df_storico.loc[idx_target, 'Dato_Simulato'] = bool(is_sim_final)

                if not is_sim_final:
                    curr_fn = str(df_storico.loc[idx_target, 'File_Name']).strip()
                    if curr_fn in ('Generato_dal_Sistema_M0V3', '', 'nan', 'None'):
                        df_storico.loc[idx_target, 'File_Name'] = f"Sessione_{new_player}_{new_date.strftime('%Y%m%d')}.csv"

                if str(new_amb).strip().lower() == "indoor":
                    for c_gps in COLONNE_GPS:
                        if c_gps in df_storico.columns:
                            df_storico.loc[idx_target, c_gps] = 0.0

                save_local_database(df_storico)
                set_notification(
                    title=tr("Informazioni Sessione Aggiornate", "Session Info Updated"),
                    message=tr("Le informazioni della sessione sono state salvate con successo.", "Session info was successfully saved."),
                    tipo="toast"
                )
                st.rerun()

    st.divider()

    st.markdown(f"### {tr('Elimina Sessione Specifica', 'Delete Specific Session')}")
    etichetta_da_eliminare = st.selectbox(tr("Scegli la sessione specifica da rimuovere dal database:", "Choose specific session to remove from database:"), lista_etichette_sessioni, key="sel_del")

    if st.button(tr("Elimina Sessione Selezionata", "Delete Selected Session"), type="primary") and etichetta_da_eliminare != placeholder_sel:
        idx_del = mappa_sessioni_idx[etichetta_da_eliminare]
        df_pulito = df_storico.drop(index=idx_del).reset_index(drop=True)
        save_local_database(df_pulito)
        set_notification(
            title=tr("Sessione Eliminata Definitivamente", "Session Permanently Deleted"),
            message=tr(f"La sessione '{etichetta_da_eliminare}' è stata rimossa dal database.", f"Session '{etichetta_da_eliminare}' was permanently removed from database."),
            tipo="modal",
            details=[
                tr(f"Sessione: {etichetta_da_eliminare}", f"Session: {etichetta_da_eliminare}"),
                tr("Database aggiornato e ricalcolato", "Database updated and recalculated")
            ]
        )
        st.rerun()

    st.divider()

    with st.expander(f"{tr('Modifica Rapida Dati Avanzata — Tabella Database', 'Advanced Data Quick Edit — Database Table')} ({len(df_vista)} {tr('sessioni filtrate', 'filtered sessions')})"):
        st.info(tr("Puoi modificare, aggiungere o rimuovere singole righe tra quelle filtrate qui sopra. Le colonne anagrafiche principali sono posizionate a sinistra.", "You can edit, add or remove individual rows among those filtered above. Main identity columns are on the left."))

        colonne_tutte = df_vista.columns.tolist()
        colonne_prioritarie = ['Date', 'Players', 'Session', 'Tipologia Sessione', 'Ambiente', 'Tipologia Campo', 'Minuti', 'Training Load', 'Dato_Simulato', 'Uploader_Email', 'File_Name']
        colonne_ordinate = [c for c in colonne_prioritarie if c in colonne_tutte] + [c for c in colonne_tutte if c not in colonne_prioritarie]

        df_ordinato = df_vista_sort.drop(columns=['_dt_sort'])[colonne_ordinate]

        df_modificato = st.data_editor(df_ordinato, use_container_width=True, num_rows="dynamic", key="data_editor_gestione")
        if st.button(tr("Salva Modifiche Tabella", "Save Table Changes"), type="primary"):
            df_storico_restante = df_storico.drop(index=df_vista.index)
            df_nuovo_completo = pd.concat([df_storico_restante, df_modificato], ignore_index=True)
            save_local_database(df_nuovo_completo)
            set_notification(
                title=tr("Database Aggiornato", "Database Updated"),
                message=tr("Le modifiche alla tabella database sono state salvate con successo.", "Database table modifications were saved successfully."),
                tipo="modal",
                details=[
                    tr(f"Totale sessioni nel database: {len(df_nuovo_completo)}", f"Total sessions in database: {len(df_nuovo_completo)}"),
                    tr("Snapshot e cache sincronizzati", "Snapshot and cache synchronized")
                ]
            )
            st.rerun()


def _render_data_governance_tab(t):
    """
    Modulo 'Data Governance & Audit Trail' (GDPR Art. 9):
    Integrità del dato sulle metriche soggettive dell'atleta (RPE e Wellness).
    Zero Hard-Delete (nessun DELETE SQL), Soft-Delete (Invalidazione is_valid=False)
    e Modifica Tracciata con archiviazione del dato originale.
    """
    # Box Introduttivo di Governance & GDPR Art. 9
    gov_intro_desc = tr(
        "Conformemente al principio di integrità del dato e validità scientifica, le metriche soggettive dell'atleta (RPE e Wellness) non possono essere eliminate fisicamente dal database (Zero DELETE SQL policy). Lo staff tecnico applica l'Invalidazione (Soft-Delete) che esclude istantaneamente il record dai calcoli analitici (ACWR, Readiness e Trend di Carico) preservando la tracciabilità storica. Ogni rettifica manuale dello staff archivia il valore originale dell'atleta esponendo un apposito segnale visivo di Audit.",
        "In compliance with data integrity and scientific validity principles, subjective athlete metrics (RPE and Wellness) cannot be physically deleted from the database (Zero DELETE SQL policy). Technical staff can apply Invalidation (Soft-Delete) which instantly excludes the record from analytical load calculations (ACWR, Readiness and Load Trends) while preserving historical auditability. Every manual adjustment by staff archives the athlete's original input and displays a dedicated Audit visual signal."
    )
    st.markdown(
        f"<div style='background:#081120; border:1px solid #1e293b; border-radius:14px; box-shadow:0 4px 16px rgba(0,0,0,0.4); padding:16px 20px; margin-bottom:18px;'>"
        f"<div style='display:flex; align-items:center; gap:10px; margin-bottom:8px;'>"
        f"<i class='bi bi-shield-check' style='color:#38bdf8; font-size:22px;'></i>"
        f"<span style='font-size:15px; font-weight:800; color:#f8fafc; text-transform:uppercase; letter-spacing:0.5px;'>{tr('Data Governance & Audit Trail — Integrità del Dato (GDPR Art. 9)', 'Data Governance & Audit Trail — Data Integrity (GDPR Art. 9)')}</span>"
        f"</div>"
        f"<div style='font-size:12px; color:#94a3b8; line-height:1.55;'>"
        f"{gov_intro_desc}"
        f"</div></div>",
        unsafe_allow_html=True
    )

    if not check_native_governance_columns():
        lbl_exp = tr("Stato Database: Schema Supabase DDL (Opzionale / Consigliato)", "Database Status: Supabase DDL Schema (Optional / Recommended)")
        with st.expander(lbl_exp, expanded=False):
            info_sql = tr(
                "<b>Data Governance Attiva in Modalità Ibrida Resiliente:</b><br>Le modifiche tracciate, l'Audit Trail dei valori originali dell'atleta e il Soft-Delete sono già attivi e persistiti in tempo reale. Per abilitare le colonne PostgreSQL native (is_valid, modificato_da_staff, rpe_originale) ed ottimizzare gli indici del database, copia ed esegui questa query nel <b>SQL Editor di Supabase</b>:",
                "<b>Data Governance Active in Resilient Hybrid Mode:</b><br>Tracked edits, original athlete Audit Trail, and Soft-Deletes are already active and persisted in real-time. To enable native PostgreSQL columns (is_valid, modificato_da_staff, rpe_originale) and optimize database indexes, copy and run this query in the <b>Supabase SQL Editor</b>:"
            )
            st.markdown(f"<div style='font-size:12.5px; color:#334155; line-height:1.55; margin-bottom:10px;'>{info_sql}</div>", unsafe_allow_html=True)
            sql_ddl = """-- M0V3 Analytics: Data Governance & Audit Trail Schema (GDPR Art. 9)
ALTER TABLE rpe_sessioni ADD COLUMN IF NOT EXISTS is_valid BOOLEAN DEFAULT TRUE;
ALTER TABLE rpe_sessioni ADD COLUMN IF NOT EXISTS modificato_da_staff BOOLEAN DEFAULT FALSE;
ALTER TABLE rpe_sessioni ADD COLUMN IF NOT EXISTS rpe_originale NUMERIC;
ALTER TABLE rpe_sessioni ADD COLUMN IF NOT EXISTS durata_originale_min NUMERIC;
UPDATE rpe_sessioni SET is_valid = TRUE WHERE is_valid IS NULL;
UPDATE rpe_sessioni SET modificato_da_staff = FALSE WHERE modificato_da_staff IS NULL;

ALTER TABLE wellness_mattutino ADD COLUMN IF NOT EXISTS is_valid BOOLEAN DEFAULT TRUE;
ALTER TABLE wellness_mattutino ADD COLUMN IF NOT EXISTS modificato_da_staff BOOLEAN DEFAULT FALSE;
ALTER TABLE wellness_mattutino ADD COLUMN IF NOT EXISTS wellness_originale_json JSONB;
UPDATE wellness_mattutino SET is_valid = TRUE WHERE is_valid IS NULL;
UPDATE wellness_mattutino SET modificato_da_staff = FALSE WHERE modificato_da_staff IS NULL;

CREATE INDEX IF NOT EXISTS idx_rpe_is_valid ON rpe_sessioni(atleta_id, is_valid, data DESC);
CREATE INDEX IF NOT EXISTS idx_wellness_is_valid ON wellness_mattutino(atleta_id, is_valid, data DESC);"""
            st.code(sql_ddl, language="sql")

    user_role = st.session_state.get('role', 'Super-Admin')
    is_admin = (user_role in ['Super-Admin', 'Admin'])
    is_coach = (user_role in ['Staff', 'Coach', 'Fisio / Medico'] or is_admin)
    user = st.session_state.get('user')

    dict_atleti = get_atleti_dict(user=user, is_admin=is_admin, is_coach=is_coach)
    nomi_atleti = sorted(list(dict_atleti.keys()))

    # --- BARRA DEI FILTRI GOVERNANCE ---
    st.markdown(f"### {tr('Filtri di Governance & Selezione Dati', 'Governance Filters & Data Selection')}")
    c_f1, c_f2, c_f3, c_f4 = st.columns(4)

    lbl_all_ath = tr("Tutti gli Atleti", "All Athletes")
    opts_ath = [lbl_all_ath] + nomi_atleti
    with c_f1:
        sel_ath = st.selectbox(tr("Atleta:", "Athlete:"), opts_ath, key="gov_sel_ath")
    atleta_id_filtro = dict_atleti.get(sel_ath) if sel_ath != lbl_all_ath else None

    with c_f2:
        opz_metrica = [
            tr("Tutte le Metriche (sRPE + Wellness)", "All Metrics (sRPE + Wellness)"),
            tr("Solo sRPE (Carico Sedute)", "sRPE Only (Session Load)"),
            tr("Solo Wellness (Rilevazioni Mattutine)", "Wellness Only (Morning Entries)")
        ]
        sel_metrica = st.selectbox(tr("Tipo Metrica:", "Metric Type:"), opz_metrica, key="gov_sel_metr")

    with c_f3:
        opz_validita = [
            tr("Tutti i Record (Validi + Invalidati)", "All Records (Valid + Invalidated)"),
            tr("Solo Validi (Attivi nei Calcoli)", "Valid Only (Active in Calculations)"),
            tr("Solo Invalidati (Soft-Deleted)", "Invalidated Only (Soft-Deleted)")
        ]
        sel_validita = st.selectbox(tr("Stato Validità:", "Validity Status:"), opz_validita, key="gov_sel_val")

    with c_f4:
        opz_giorni = [
            tr("Ultimi 30 giorni", "Last 30 days"),
            tr("Ultimi 60 giorni", "Last 60 days"),
            tr("Ultimi 90 giorni", "Last 90 days"),
            tr("Ultimi 180 giorni", "Last 180 days"),
            tr("Tutto lo Storico", "All History")
        ]
        sel_giorni = st.selectbox(tr("Finestra Temporale:", "Time Window:"), opz_giorni, index=2, key="gov_sel_days")

    days_map = {
        opz_giorni[0]: 30,
        opz_giorni[1]: 60,
        opz_giorni[2]: 90,
        opz_giorni[3]: 180,
        opz_giorni[4]: 0
    }
    days_val = days_map.get(sel_giorni, 90)

    # Recupero record via funzione centralizzata
    raw_records = get_governance_records(atleta_id=atleta_id_filtro, limit_days=days_val)

    # Filtraggio per metrica
    if sel_metrica == opz_metrica[1]:
        filtered_records = [r for r in raw_records if r['metrica'] == 'sRPE']
    elif sel_metrica == opz_metrica[2]:
        filtered_records = [r for r in raw_records if r['metrica'] == 'Wellness']
    else:
        filtered_records = list(raw_records)

    # Filtraggio per validità
    if sel_validita == opz_validita[1]:
        filtered_records = [r for r in filtered_records if r['is_valid'] is True]
    elif sel_validita == opz_validita[2]:
        filtered_records = [r for r in filtered_records if r['is_valid'] is False]

    # --- BARRA KPI SINTETICI DI GOVERNANCE ---
    tot_rec = len(filtered_records)
    tot_val = sum(1 for r in filtered_records if r['is_valid'] is True)
    tot_inval = sum(1 for r in filtered_records if r['is_valid'] is False)
    tot_mod = sum(1 for r in filtered_records if r['modificato_da_staff'] is True)

    c_k1, c_k2, c_k3, c_k4 = st.columns(4)
    with c_k1:
        st.markdown(card_kpi(tr("Record Monitorati", "Monitored Records"), f"{tot_rec}", sottotitolo=tr("Nel perimetro selezionato", "In selected perimeter"), accento="#0ea5e9"), unsafe_allow_html=True)
    with c_k2:
        st.markdown(card_kpi(tr("Record Validi (Attivi)", "Valid Records (Active)"), f"{tot_val}", sottotitolo=tr("Partecipano ad ACWR e carichi", "Active in ACWR & loads"), accento="#10b981"), unsafe_allow_html=True)
    with c_k3:
        st.markdown(card_kpi(tr("Invalidati (Soft-Delete)", "Invalidated (Soft-Delete)"), f"{tot_inval}", sottotitolo=tr("Esclusi da grafici e medie", "Excluded from charts & means"), accento="#e11d48"), unsafe_allow_html=True)
    with c_k4:
        st.markdown(card_kpi(tr("Modificati dallo Staff", "Staff Corrected"), f"{tot_mod}", sottotitolo=tr("Con tracciamento audit attivo", "Active audit trail"), accento="#f59e0b"), unsafe_allow_html=True)

    st.markdown("<div style='margin-bottom:14px;'></div>", unsafe_allow_html=True)

    if not filtered_records:
        st.info(tr("Nessuna registrazione trovata per i filtri selezionati.", "No records found matching selected filters."))
        return

    # --- SEZIONE A: TABELLA INTERATTIVA DI CONTROLLO & AUDIT ---
    st.markdown(f"### {tr('A. Tabella di Controllo & Registro Audit Trail', 'A. Control Table & Audit Trail Registry')}")
    st.caption(tr("I record invalidati hanno sfondo grigio ed opacità ridotta. Il badge 'Modificato' segnala le rettifiche apportate dallo staff con tooltip sul valore originale.", "Invalidated records appear with gray background and reduced opacity. The 'Modified' badge signals staff adjustments with hover tooltip on athlete original values."))

    html_rows = []
    rows_for_df = []

    for r in filtered_records:
        is_v = r['is_valid']
        is_m = r['modificato_da_staff']

        # Descrizioni di valore e di audit
        if r['metrica'] == 'sRPE':
            val_html = f"<b>RPE {r['rpe']}</b> &bull; {r['durata_minuti']}m ({r['tipologia']}) &rarr; <b>{r['carico_interno']} AU</b>"
            val_raw = f"RPE {r['rpe']} | {r['durata_minuti']}m ({r['tipologia']}) -> {r['carico_interno']} AU"
            if is_m:
                rpe_o = r.get('rpe_originale')
                dur_o = r.get('durata_originale_min')
                orig_desc = f"RPE {rpe_o}" + (f", {dur_o:.0f} min" if dur_o is not None else "")
                audit_hover = f"Valore originale Atleta: {orig_desc}"
                badge_audit = (
                    f"<span title='{audit_hover}' style='background:rgba(245,158,11,0.18); color:#fbbf24; padding:3px 7px; border-radius:4px; font-weight:800; font-size:10.5px; border:1px solid #f59e0b; cursor:help; display:inline-flex; align-items:center; gap:4px;'>"
                    f"<i class='bi bi-pencil-square text-warning'></i> Modificato"
                    f"</span>"
                )
                audit_txt = f"Modificato (Orig: {orig_desc})"
            else:
                badge_audit = (
                    f"<span style='color:#94a3b8; font-size:11px; font-weight:600; display:inline-flex; align-items:center; gap:4px;'>"
                    f"<i class='bi bi-person-check' style='color:#34d399;'></i> Originale Atleta"
                    f"</span>"
                )
                audit_txt = "Originale Atleta"
        else:
            w_sc = r.get('wellness_score', 0)
            val_html = f"<b>Score {w_sc:.1f}</b> (Sonno {r.get('sonno')}, Fatica {r.get('fatica')}, DOMS {r.get('doms')}, Stress {r.get('stress')}, Umore {r.get('umore')})"
            val_raw = f"Score {w_sc:.1f} (Sonno {r.get('sonno')}, Fatica {r.get('fatica')}, DOMS {r.get('doms')}, Stress {r.get('stress')}, Umore {r.get('umore')})"
            if is_m:
                wel_o = r.get('wellness_originale_json') or {}
                if isinstance(wel_o, dict):
                    orig_desc = f"Sonno:{wel_o.get('sonno')}, Fatica:{wel_o.get('fatica')}, DOMS:{wel_o.get('doms')}, Stress:{wel_o.get('stress')}, Umore:{wel_o.get('umore')}"
                else:
                    orig_desc = str(wel_o)
                audit_hover = f"Valore originale Atleta: {orig_desc}"
                badge_audit = (
                    f"<span title='{audit_hover}' style='background:rgba(245,158,11,0.18); color:#fbbf24; padding:3px 7px; border-radius:4px; font-weight:800; font-size:10.5px; border:1px solid #f59e0b; cursor:help; display:inline-flex; align-items:center; gap:4px;'>"
                    f"<i class='bi bi-pencil-square text-warning'></i> Modificato"
                    f"</span>"
                )
                audit_txt = f"Modificato (Orig: {orig_desc})"
            else:
                badge_audit = (
                    f"<span style='color:#94a3b8; font-size:11px; font-weight:600; display:inline-flex; align-items:center; gap:4px;'>"
                    f"<i class='bi bi-person-check' style='color:#34d399;'></i> Originale Atleta"
                    f"</span>"
                )
                audit_txt = "Originale Atleta"

        # Badge validità
        if is_v:
            badge_stato = (
                f"<span style='background:rgba(16,185,129,0.18); color:#34d399; padding:3px 7px; border-radius:4px; font-weight:800; font-size:10.5px; border:1px solid #10b981; display:inline-flex; align-items:center; gap:4px;'>"
                f"<i class='bi bi-shield-check'></i> Valido"
                f"</span>"
            )
            stato_txt = "Valido"
            row_style = "background:#081120; color:#f8fafc; border-bottom:1px solid #1e293b;"
        else:
            badge_stato = (
                f"<span style='background:rgba(239,68,68,0.18); color:#f87171; padding:3px 7px; border-radius:4px; font-weight:800; font-size:10.5px; border:1px solid #ef4444; display:inline-flex; align-items:center; gap:4px;'>"
                f"<i class='bi bi-eye-slash-fill'></i> Invalidato"
                f"</span>"
            )
            stato_txt = "INVALIDATO"
            row_style = "background:#0d1e38; color:#64748b; border-bottom:1px solid #1e293b; opacity:0.65; text-decoration:line-through;"

        html_rows.append(
            f"<tr style='{row_style} font-size:12px; font-family:\"Inter\",sans-serif;'>"
            f"<td style='padding:8px 10px; font-weight:700;'>{r['data']}</td>"
            f"<td style='padding:8px 10px; font-weight:700;'>{r['atleta_nome']}</td>"
            f"<td style='padding:8px 10px; font-weight:600;'>{r['metrica']}</td>"
            f"<td style='padding:8px 10px;'>{val_html}</td>"
            f"<td style='padding:8px 10px; text-align:center;'>{badge_audit}</td>"
            f"<td style='padding:8px 10px; text-align:center;'>{badge_stato}</td>"
            f"<td style='padding:8px 10px; font-size:11px; color:#64748b;'>{r.get('note', '') or '-'}</td>"
            f"</tr>"
        )

        rows_for_df.append({
            "ID": r['id'][:8],
            "Data": r['data'],
            "Atleta": r['atleta_nome'],
            "Metrica": r['metrica'],
            "Valore": val_raw,
            "Audit": audit_txt,
            "Stato": stato_txt,
            "Valido": bool(is_v),
            "Modificato": bool(is_m),
            "Note": r.get('note', '') or "-"
        })

    # Render Tabella HTML High-Contrast con Bootstrap Badges
    th_data = tr("Data", "Date")
    th_atl = tr("Atleta", "Athlete")
    th_met = tr("Metrica", "Metric")
    th_val = tr("Valore Corrente", "Current Value")
    th_aud = tr("Audit Trail", "Audit Trail")
    th_sta = tr("Stato Validità", "Validity Status")
    th_not = tr("Note", "Notes")

    st.markdown(
        f"<div style='background:#081120; border:1px solid #1e293b; border-radius:14px; box-shadow:0 4px 16px rgba(0,0,0,0.4); overflow:hidden; margin-bottom:16px;'>"
        f"<table style='width:100%; border-collapse:collapse;'>"
        f"<thead><tr style='background:#0d1e38; color:#38bdf8; font-size:11px; text-transform:uppercase; letter-spacing:0.5px; border-bottom:2px solid #1e293b; font-family:\"Inter\",sans-serif;'>"
        f"<th style='padding:10px 12px; text-align:left;'>{th_data}</th>"
        f"<th style='padding:10px 12px; text-align:left;'>{th_atl}</th>"
        f"<th style='padding:10px 12px; text-align:left;'>{th_met}</th>"
        f"<th style='padding:10px 12px; text-align:left;'>{th_val}</th>"
        f"<th style='padding:10px 12px; text-align:center;'>{th_aud}</th>"
        f"<th style='padding:10px 12px; text-align:center;'>{th_sta}</th>"
        f"<th style='padding:10px 12px; text-align:left;'>{th_not}</th>"
        f"</tr></thead><tbody>{''.join(html_rows)}</tbody></table></div>",
        unsafe_allow_html=True
    )

    # Vista st.data_editor per ispezione interattiva e ordinamento
    with st.expander(tr("Visualizza Vista Dati Avanzata (st.data_editor)", "View Advanced Data View (st.data_editor)"), expanded=False):
        df_editor = pd.DataFrame(rows_for_df)
        st.data_editor(
            df_editor,
            use_container_width=True,
            disabled=True,
            key="gov_data_editor_table",
            column_config={
                "Valido": st.column_config.CheckboxColumn(tr("Valido", "Valid"), help=tr("Partecipa ai calcoli analitici", "Participates in analytical calculations")),
                "Modificato": st.column_config.CheckboxColumn(tr("Modificato da Staff", "Modified by Staff"), help=tr("Dato rettificato manualmente dallo staff", "Data manually adjusted by staff")),
            }
        )

    st.divider()

    # --- SEZIONE B & C: CENTRO OPERATIVO DI MODIFICA TRACCIATA & SOFT-DELETE ---
    st.markdown(f"### {tr('B & C. Modifica Tracciata & Invalida Registrazione (Soft-Delete)', 'B & C. Tracked Edit & Record Invalidation (Soft-Delete)')}")
    st.info(tr("Seleziona una specifica registrazione per modificarne il valore in modo tracciato (conservando il voto originale dell'atleta nell'Audit Trail) oppure per Invalidarla/Ripristinarla senza eseguire eliminazioni fisiche.", "Select a specific record to edit its value with tracking (preserving athlete original input in the Audit Trail) or to Invalidate/Restore it without executing physical deletions."))

    mappa_scelte = {}
    for r in filtered_records:
        tag_v = "VALIDO" if r['is_valid'] else "INVALIDATO"
        tag_m = "MODIFICATO" if r['modificato_da_staff'] else "ORIGINALE"
        if r['metrica'] == 'sRPE':
            desc_s = f"RPE {r['rpe']} ({r['durata_minuti']}m - {r['tipologia']})"
        else:
            desc_s = f"Wellness Score {r.get('wellness_score', 0):.1f}"
        lbl_k = f"[{tag_v} | {tag_m}] {r['data']} — {r['atleta_nome']} — {r['metrica']}: {desc_s} (ID #{r['id'][:8]})"
        mappa_scelte[lbl_k] = r

    chiavi_scelte = list(mappa_scelte.keys())
    placeholder_sel_gov = tr("Seleziona una registrazione...", "Select a record...")
    sel_rec_label = st.selectbox(
        tr("Scegli la registrazione da gestire:", "Choose record to manage:"),
        [placeholder_sel_gov] + chiavi_scelte,
        key="gov_rec_picker"
    )

    if sel_rec_label != placeholder_sel_gov:
        rec = mappa_scelte[sel_rec_label]
        is_rpe = (rec['tabella'] == 'rpe_sessioni')

        # Scheda Dettagliata Record Selezionato
        st.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)
        col_sch1, col_sch2 = st.columns([1.8, 1.2])

        with col_sch1:
            # Badge di Stato
            if rec['is_valid']:
                badge_v_big = "<span style='background:rgba(16,185,129,0.18); color:#34d399; padding:4px 10px; border-radius:6px; font-weight:800; font-size:12px; border:1px solid #10b981;'><i class='bi bi-shield-check'></i> Record Valido (Incluso nei Calcoli di Carico)</span>"
            else:
                badge_v_big = "<span style='background:rgba(239,68,68,0.18); color:#f87171; padding:4px 10px; border-radius:6px; font-weight:800; font-size:12px; border:1px solid #ef4444;'><i class='bi bi-eye-slash-fill'></i> Record INVALIDATO (Escluso da Medie e Grafici)</span>"

            if rec['modificato_da_staff']:
                orig_show = f"RPE {rec.get('rpe_originale')}" if is_rpe else f"{rec.get('wellness_originale_json')}"
                badge_m_big = f"<span style='background:rgba(245,158,11,0.18); color:#fbbf24; padding:4px 10px; border-radius:6px; font-weight:800; font-size:12px; border:1px solid #f59e0b;'><i class='bi bi-pencil-square text-warning'></i> Modificato dallo Staff</span> &bull; <b style='color:#ffffff;'>Valore Originale Atleta: {orig_show}</b>"
            else:
                badge_m_big = "<span style='background:rgba(16,185,129,0.18); color:#34d399; padding:4px 10px; border-radius:6px; font-weight:800; font-size:12px; border:1px solid #10b981;'><i class='bi bi-person-check'></i> Dato Originale Inserito dall'Atleta</span>"

            st.markdown(
                f"<div style='background:#081120; border:1px solid #1e293b; border-radius:14px; box-shadow:0 4px 16px rgba(0,0,0,0.4); padding:16px 20px; margin-bottom:14px;'>"
                f"<div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; flex-wrap:wrap; gap:8px;'>"
                f"<span style='font-size:14px; font-weight:800; color:#f8fafc;'><i class='bi bi-person-badge' style='color:#38bdf8; margin-right:6px;'></i>{rec['atleta_nome']} — {rec['data']}</span>"
                f"<span style='font-size:11px; color:#94a3b8; font-family:monospace;'>ID: {rec['id']}</span>"
                f"</div>"
                f"<div style='display:flex; align-items:center; gap:10px; flex-wrap:wrap; margin-bottom:8px;'>"
                f"{badge_v_big} {badge_m_big}"
                f"</div></div>",
                unsafe_allow_html=True
            )

        with col_sch2:
            privacy_note_desc = tr(
                "Nessuna operazione rimuove righe fisiche dal database Supabase. Le modifiche generano un'impronta di Audit permanente. Le invalidazioni aggiornano il flag logico is_valid.",
                "No operation physically removes rows from Supabase database. Modifications generate a permanent Audit footprint. Invalidations update the logical is_valid flag."
            )
            st.markdown(
                f"<div style='background:#081120; border:1px solid #1e293b; border-radius:14px; box-shadow:0 4px 16px rgba(0,0,0,0.4); padding:14px 16px; margin-bottom:14px; font-size:11.5px; color:#94a3b8;'>"
                f"<b style='color:#38bdf8;'>{tr('Integrità Scientifica & Privacy:', 'Scientific Integrity & Privacy:')}</b><br>"
                f"{privacy_note_desc}"
                f"</div>",
                unsafe_allow_html=True
            )

        # Sezione Due Colonne: Modifica Tracciata (SX) vs Azione Soft-Delete / Ripristino (DX)
        c_mod, c_del = st.columns([1.6, 1.4])

        with c_mod:
            st.markdown(f"#### <i class='bi bi-pencil-square'></i> {tr('Motore di Modifica Tracciata', 'Tracked Modification Engine')}", unsafe_allow_html=True)
            if is_rpe:
                with st.form("form_modifica_rpe_gov"):
                    st.caption(tr("Rettifica il carico dichiarato dall'atleta. Se è la prima modifica, il voto originale viene archiviato nell'Audit Trail.", "Adjust load declared by athlete. On first edit, original input is archived in Audit Trail."))
                    curr_rpe_val = int(rec.get('rpe', 5))
                    curr_dur_val = int(rec.get('durata_minuti', 60))
                    curr_tipo_val = rec.get('tipologia', 'Tennis')

                    col_r1, col_r2 = st.columns(2)
                    with col_r1:
                        new_rpe_in = st.number_input(tr("Nuovo Voto RPE (0-10)", "New RPE Vote (0-10)"), min_value=0, max_value=10, value=curr_rpe_val, step=1)
                        opz_tipi = ['Tennis', 'Preparazione Fisica', 'Gym', 'Recupero', 'Altro']
                        idx_tp = opz_tipi.index(curr_tipo_val) if curr_tipo_val in opz_tipi else 0
                        new_tipo_in = st.selectbox(tr("Tipologia Sessione", "Session Type"), opz_tipi, index=idx_tp)
                    with col_r2:
                        new_dur_in = st.number_input(tr("Durata (Minuti)", "Duration (Minutes)"), min_value=1, value=curr_dur_val, step=5)
                        prev_carico = int(new_rpe_in * new_dur_in)
                        st.metric(tr("Carico Ricalcolato", "Recalculated Load"), f"{prev_carico} AU")

                    new_note_in = st.text_input(tr("Motivazione Rettifica Staff / Note", "Staff Adjustment Reason / Notes"), value=rec.get('note', '') or "")

                    btn_salva_rpe = st.form_submit_button(tr("Salva Modifica Tracciata", "Save Tracked Edit"), type="primary", use_container_width=True)
                    if btn_salva_rpe:
                        ok_up, res_up = modifica_tracciata_rpe(
                            session_id=rec['id'],
                            nuovo_rpe=new_rpe_in,
                            nuova_durata_min=new_dur_in,
                            nuova_tipologia=new_tipo_in,
                            nuove_note=new_note_in
                        )
                        if ok_up:
                            orig_str_not = f"RPE {rec['rpe_originale'] or rec['rpe']}"
                            set_notification(
                                title=tr("Modifica Tracciata Salvata", "Tracked Edit Saved"),
                                message=tr(f"Sessione sRPE per {rec['atleta_nome']} aggiornata a RPE {new_rpe_in} e durata {new_dur_in} min. Valore originale archiviato.",
                                           f"sRPE session for {rec['atleta_nome']} updated to RPE {new_rpe_in} and duration {new_dur_in} min. Original value archived."),
                                tipo="modal",
                                details=[
                                    tr(f"Atleta: {rec['atleta_nome']}", f"Athlete: {rec['atleta_nome']}"),
                                    tr(f"Data: {rec['data']}", f"Date: {rec['data']}"),
                                    tr(f"Valore Primario Atleta: {orig_str_not}", f"Primary Athlete Value: {orig_str_not}"),
                                    tr(f"Nuovo Valore Rettificato Staff: RPE {new_rpe_in} ({new_dur_in} min) &rarr; {prev_carico} AU", f"New Staff Adjusted Value: RPE {new_rpe_in} ({new_dur_in} min) -> {prev_carico} AU"),
                                    tr("Flag 'modificato_da_staff' attivato nell'Audit Trail", "Flag 'modificato_da_staff' set in Audit Trail")
                                ]
                            )
                            st.rerun()
                        else:
                            st.error(f"Errore durante l'aggiornamento: {res_up}")
            else:
                # Wellness Mattutino Form
                with st.form("form_modifica_wel_gov"):
                    st.caption(tr("Rettifica i 5 parametri del Wellness. I valori originali dell'atleta vengono archiviati nel campo JSON di Audit.", "Adjust the 5 Wellness parameters. Original values are archived in the Audit JSON field."))
                    raw_w = rec.get('raw_record', {})
                    c_w1, c_w2, c_w3 = st.columns(3)
                    with c_w1:
                        w_sonno = st.number_input(tr("Qualità Sonno (1-10)", "Sleep Quality (1-10)"), min_value=1, max_value=10, value=int(rec.get('sonno', 5)), step=1)
                        w_fatica = st.number_input(tr("Fatica (1-10)", "Fatigue (1-10)"), min_value=1, max_value=10, value=int(rec.get('fatica', 5)), step=1)
                    with c_w2:
                        w_doms = st.number_input(tr("DOMS / Dolore (1-10)", "DOMS / Soreness (1-10)"), min_value=1, max_value=10, value=int(rec.get('doms', 5)), step=1)
                        w_stress = st.number_input(tr("Stress (1-10)", "Stress (1-10)"), min_value=1, max_value=10, value=int(rec.get('stress', 5)), step=1)
                    with c_w3:
                        w_umore = st.number_input(tr("Umore (1-10)", "Mood (1-10)"), min_value=1, max_value=10, value=int(rec.get('umore', 5)), step=1)
                        calc_new_score = round(((w_sonno + w_umore) + (11 - w_fatica) + (11 - w_stress) + (11 - w_doms)) / 5.0, 1)
                        st.metric(tr("Readiness Score", "Readiness Score"), f"{calc_new_score} / 10")

                    w_note_in = st.text_input(tr("Motivazione Rettifica Staff / Note", "Staff Adjustment Reason / Notes"), value=rec.get('note', '') or "")

                    btn_salva_wel = st.form_submit_button(tr("Salva Modifica Tracciata", "Save Tracked Edit"), type="primary", use_container_width=True)
                    if btn_salva_wel:
                        ok_up_w, res_up_w = modifica_tracciata_wellness(
                            record_id=rec['id'],
                            nuovi_valori_dict={
                                "sonno": w_sonno,
                                "sonno_qualita": w_sonno,
                                "fatica": w_fatica,
                                "doms": w_doms,
                                "stress": w_stress,
                                "umore": w_umore
                            },
                            nuove_note=w_note_in
                        )
                        if ok_up_w:
                            set_notification(
                                title=tr("Modifica Tracciata Salvata", "Tracked Edit Saved"),
                                message=tr(f"Rilevazione Wellness per {rec['atleta_nome']} aggiornata con nuovo score {calc_new_score}. Parametri originali archiviati.",
                                           f"Wellness entry for {rec['atleta_nome']} updated with new score {calc_new_score}. Original parameters archived."),
                                tipo="modal",
                                details=[
                                    tr(f"Atleta: {rec['atleta_nome']}", f"Athlete: {rec['atleta_nome']}"),
                                    tr(f"Data: {rec['data']}", f"Date: {rec['data']}"),
                                    tr(f"Nuovo Readiness Score: {calc_new_score} / 10", f"New Readiness Score: {calc_new_score} / 10"),
                                    tr("Valori originali archiviati nel campo JSON di Audit", "Original values archived in Audit JSON field")
                                ]
                            )
                            st.rerun()
                        else:
                            st.error(f"Errore durante l'aggiornamento: {res_up_w}")

        with c_del:
            st.markdown(f"#### <i class='bi bi-shield-slash'></i> {tr('Azione di Validità (Soft-Delete)', 'Validity Action (Soft-Delete)')}", unsafe_allow_html=True)
            st.markdown(
                f"<div style='background:#081120; border:1px solid #1e293b; border-radius:10px; padding:12px 14px; margin-bottom:14px; font-size:12px; line-height:1.5; color:#94a3b8;'>"
                f"<b style='color:#38bdf8;'>{tr('Regola di Validità Analitica:', 'Analytical Validity Rule:')}</b><br>"
                f"{tr('Se una compilazione è viziata o inattendibile, non cancellarla fisicamente: invalida la registrazione. Il record non parteciperà più alle medie settimanali, ai calcoli ACWR e alla Readiness, ma rimarrà conservato per trasparenza medico-legale.', 'If an entry is flawed or unreliable, do not physically delete it: invalidate the registration. The record will no longer participate in weekly averages, ACWR calculations and Readiness, but will remain preserved for medico-legal transparency.')}"
                f"</div>",
                unsafe_allow_html=True
            )

            if rec['is_valid']:
                st.warning(tr("La registrazione è attualmente ATTIVA e partecipa a tutti i calcoli di carico e grafici.", "This record is currently ACTIVE and participates in all load calculations and charts."))
                lbl_inval_btn = tr("Invalida Registrazione (Soft-Delete)", "Invalidate Record (Soft-Delete)")
                if st.button(lbl_inval_btn, type="primary", key="btn_invalida_rec", use_container_width=True):
                    if is_rpe:
                        ok_inv, err_inv = soft_delete_rpe_sessione(rec['id'], is_valid=False)
                    else:
                        ok_inv, err_inv = soft_delete_wellness_mattutino(rec['id'], is_valid=False)

                    if ok_inv:
                        set_notification(
                            title=tr("Registrazione Invalidata con Successo", "Record Successfully Invalidated"),
                            message=tr(f"La registrazione di {rec['metrica']} del {rec['data']} per {rec['atleta_nome']} è stata invalidata. È ora esclusa da tutti i calcoli e grafici.",
                                       f"{rec['metrica']} record of {rec['data']} for {rec['atleta_nome']} was invalidated. It is now excluded from all calculations and charts."),
                            tipo="modal",
                            details=[
                                tr(f"Atleta: {rec['atleta_nome']}", f"Athlete: {rec['atleta_nome']}"),
                                tr(f"Data: {rec['data']}", f"Date: {rec['data']}"),
                                tr(f"Metrica: {rec['metrica']}", f"Metric: {rec['metrica']}"),
                                tr("Stato impostato su: INVALIDATO (is_valid = FALSE)", "Status set to: INVALIDATED (is_valid = FALSE)"),
                                tr("Zero Hard-Delete: nessuna cancellazione fisica eseguita sul database", "Zero Hard-Delete: no physical row deleted from database")
                            ]
                        )
                        st.rerun()
                    else:
                        st.error(f"Errore durante l'invalidazione: {err_inv}")
            else:
                st.error(tr("Questa registrazione è attualmente INVALIDATA ed esclusa da tutti i calcoli analitici e grafici.", "This record is currently INVALIDATED and excluded from all analytical calculations and charts."))
                lbl_rip_btn = tr("Rendi Valido (Ripristina)", "Make Valid (Restore)")
                if st.button(lbl_rip_btn, type="primary", key="btn_ripristina_rec", use_container_width=True):
                    if is_rpe:
                        ok_rip, err_rip = ripristina_rpe_sessione(rec['id'])
                    else:
                        ok_rip, err_rip = ripristina_wellness_mattutino(rec['id'])

                    if ok_rip:
                        set_notification(
                            title=tr("Registrazione Ripristinata", "Record Restored"),
                            message=tr(f"La registrazione di {rec['metrica']} per {rec['atleta_nome']} è stata riattivata con successo.",
                                       f"{rec['metrica']} record for {rec['atleta_nome']} was successfully restored."),
                            tipo="toast"
                        )
                        st.rerun()
                    else:
                        st.error(f"Errore durante il ripristino: {err_rip}")
