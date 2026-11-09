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
    CANONICAL_TIPOLOGIE_SESSIONE,
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
    slugify_name,
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
    st.markdown(f"### {tr('Filtri Rapidi Database', 'Database Quick Filters')}")
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

    with f_col_a:
        atleti_in_db = sorted([str(p) for p in df_base_perm['Players'].dropna().unique() if str(p).strip()])
        filtro_atleta = st.selectbox(tr("Atleta:", "Athlete:"), [lbl_tutti_atleti] + atleti_in_db, key="gf_flt_ath")
    with f_col_t:
        canonical_rank = {name.lower(): idx for idx, name in enumerate(CANONICAL_TIPOLOGIE_SESSIONE)}
        raw_tipi = [str(tp) for tp in df_base_perm['Tipologia Sessione'].dropna().unique() if str(tp).strip()]
        tipi_in_db = sorted(raw_tipi, key=lambda x: (canonical_rank.get(x.lower(), 99), x))
        filtro_tipo = st.selectbox(tr("Tipologia Sessione:", "Session Type:"), [lbl_tutte_tipologie] + tipi_in_db, key="gf_flt_type")
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

    # Ordinamento cronologico dal più recente al meno recente, preservando l'indice originale di df_storico
    df_vista_sort = df_vista.copy()
    df_vista_sort['_dt_sort'] = pd.to_datetime(df_vista_sort['Date'], format="%d/%m/%Y", errors='coerce')
    df_vista_sort.sort_values(by=['_dt_sort'], ascending=False, inplace=True)

    # Costruzione mappa univoca: Etichetta descrittiva -> Indice univoco di riga in df_storico
    mappa_sessioni_idx = {}
    for idx_row, row_s in df_vista_sort.iterrows():
        dt_s = str(row_s.get('Date', 'N/D'))
        pl_s = str(row_s.get('Players', 'N/D'))
        nm_s = str(row_s.get('Session', 'N/D'))
        tp_s = str(row_s.get('Tipologia Sessione', 'N/D'))
        am_s = str(row_s.get('Ambiente', 'Outdoor'))
        sim_tag = " | SIMULATO" if bool(row_s.get('Dato_Simulato', False)) else ""
        lbl_univoca = f"{dt_s} — {pl_s} — {nm_s} [{tp_s} | {am_s}{sim_tag}] (ID #{idx_row})"
        mappa_sessioni_idx[lbl_univoca] = idx_row

    placeholder_sel = tr("Seleziona una sessione...", "Select a session...")
    lista_etichette_sessioni = [placeholder_sel] + list(mappa_sessioni_idx.keys())

    st.divider()
    st.markdown(f"### {tr('Modifica Informazioni Sessione', 'Edit Session Information')}")
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

        opzioni_atleti_mod = list(dict.fromkeys((atleti_consentiti or []) + atleti_in_db + ([curr_player] if curr_player else [])))
        idx_player = opzioni_atleti_mod.index(curr_player) if curr_player in opzioni_atleti_mod else 0

        opzioni_tipologie_mod = get_tipologie_sessione(None if st.session_state['role'] == 'Super-Admin' else user_email)
        if curr_tipo and curr_tipo not in opzioni_tipologie_mod:
            opzioni_tipologie_mod.append(curr_tipo)
        idx_tipo = opzioni_tipologie_mod.index(curr_tipo) if curr_tipo in opzioni_tipologie_mod else 0

        with st.form("form_modifica_info"):
            c1, c2, c3 = st.columns(3)
            with c1:
                new_player = st.selectbox(tr("Atleta Assegnato", "Assigned Athlete"), opzioni_atleti_mod, index=idx_player)
                new_date = st.date_input(tr("Data Sessione", "Session Date"), value=curr_date_obj)
                new_name = st.text_input(tr("Nome Sessione", "Session Name"), value=curr_name)
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
                tipo_finale = new_tipo_custom.strip() if new_tipo_custom.strip() else new_tipo_sel
                df_storico.loc[idx_target, 'Players'] = new_player
                df_storico.loc[idx_target, 'Date'] = new_date.strftime("%d/%m/%Y")
                df_storico.loc[idx_target, 'Session'] = new_name.strip() if new_name.strip() else curr_name
                df_storico.loc[idx_target, 'Minuti'] = round(float(new_minuti), 1)
                df_storico.loc[idx_target, 'Tipologia Campo'] = new_campo
                df_storico.loc[idx_target, 'Ambiente'] = new_amb
                df_storico.loc[idx_target, 'Tipologia Sessione'] = tipo_finale
                df_storico.loc[idx_target, 'Minuti Sparring'] = int(new_sparring)

                # Se cambiato in Indoor, azzera le colonne GPS satellitari per coerenza fisica
                if str(new_amb).strip().lower() == "indoor":
                    for c_gps in COLONNE_GPS:
                        if c_gps in df_storico.columns:
                            df_storico.loc[idx_target, c_gps] = 0.0

                save_local_database(df_storico)
                st.success(tr("Informazioni della sessione aggiornate con successo!", "Session info successfully updated!"))
                st.rerun()

    st.divider()

    st.markdown(f"### {tr('Elimina Sessione Specifica', 'Delete Specific Session')}")
    etichetta_da_eliminare = st.selectbox(tr("Scegli la sessione specifica da rimuovere dal database:", "Choose specific session to remove from database:"), lista_etichette_sessioni, key="sel_del")

    if st.button(tr("Elimina Sessione Selezionata", "Delete Selected Session"), type="primary") and etichetta_da_eliminare != placeholder_sel:
        idx_del = mappa_sessioni_idx[etichetta_da_eliminare]
        df_pulito = df_storico.drop(index=idx_del).reset_index(drop=True)
        save_local_database(df_pulito)
        st.success(tr(f"Sessione '{etichetta_da_eliminare}' eliminata definitivamente!", f"Session '{etichetta_da_eliminare}' permanently deleted!"))
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
            st.success(tr("Database aggiornato e ripulito con successo!", "Database updated and cleaned successfully!"))
            st.rerun()
