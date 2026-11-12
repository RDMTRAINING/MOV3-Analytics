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
    PAGINE_OPERATIVE,
    COLONNE_STANDARD,
    METRICHE_VOLUME,
    METRICHE_INTENSITA,
    LEGENDA_ACWR,
    render_page_header,
    render_print_header,
    tr,
    render_tab_navigation,
)
from utils import (
    supabase,
    supabase_admin,
    get_tipologie_sessione,
    converti_durata_in_minuti,
    leggi_csv_gps_robusto,
    applica_mappatura_csv,
    load_local_database,
    save_local_database,
    clear_atleti_cache,
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
from views.supporto import (
    load_all_tickets,
    add_reply,
    update_status,
    get_status_badge,
    get_priority_badge,
    SUPPORT_EMAIL,
)
from email_service import (
    invia_email_creazione_account,
    invia_email_reset_password_admin,
    get_smtp_config,
)

def render_admin(t):
    if st.session_state.get('role') != 'Super-Admin':
        st.error("Accesso negato: questa sezione è riservata ai Super-Admin.")
        st.stop()
    render_page_header(t['admin_title'], t['home_admin_desc'], "SYSTEM ADMINISTRATION")
    tab_list = [t['tab_atl'], t['tab_usr'], t['tab_map'], t['tab_rep'], t.get('tab_sup', 'Supporto & Ticket')]
    active_admin_tab = render_tab_navigation(
        tab_list,
        key="nav_sub_admin_tabs",
        default=t['tab_atl']
    )
    
    if active_admin_tab == t['tab_atl']:
        st.markdown(t['add_atl'])
        col1, col2 = st.columns(2)
        with col1: nuovo_nome = st.text_input(t['atl_name'])
        with col2: nuovo_cognome = st.text_input(t['atl_surname'])
        if st.button(t['btn_add_atl'], type="primary"):
            if nuovo_nome and nuovo_cognome:
                supabase_admin.table('atleti').insert({"nome": nuovo_nome, "cognome": nuovo_cognome}).execute()
                clear_atleti_cache()
                st.success(f"Atleta {nuovo_nome} {nuovo_cognome} OK!")
                st.rerun()

        st.divider()
        st.markdown(t['curr_atl'])
        risposta_atleti = supabase_admin.table('atleti').select('*').execute()
        if risposta_atleti.data:
            df_atleti = pd.DataFrame(risposta_atleti.data)
            st.dataframe(df_atleti[['nome', 'cognome', 'data_nascita']], use_container_width=True)
            
            st.divider()
            st.markdown(t['del_atl'])
            st.warning(t['warn_del_atl'])
            dict_elimina_atleti = {f"{row['nome']} {row['cognome']}": row['id'] for _, row in df_atleti.iterrows()}
            atleta_da_eliminare = st.selectbox(t['sel_del_atl'], [t['select']] + list(dict_elimina_atleti.keys()))
            
            if st.button(t['btn_del_def'], type="primary"):
                if atleta_da_eliminare != t['select']:
                    try:
                        id_da_eliminare = dict_elimina_atleti[atleta_da_eliminare]
                        supabase_admin.table('associazioni').delete().eq('atleta_id', id_da_eliminare).execute()
                        supabase_admin.table('atleti').delete().eq('id', id_da_eliminare).execute()
                        clear_atleti_cache()
                        st.success(f"{atleta_da_eliminare} OK!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")
        else:
            st.info("Nessun atleta / No athletes")

    elif active_admin_tab == t['tab_usr']:
        res_profili = supabase_admin.table('profili').select('*').execute()
        res_atleti = supabase_admin.table('atleti').select('*').execute()
        res_tutte_assoc = supabase_admin.table('associazioni').select('*').execute()
        df_storico_admin = load_local_database()

        list_profili = res_profili.data or []
        list_atleti = res_atleti.data or []
        list_assoc = res_tutte_assoc.data or []

        # Auto-sincronizzazione profili con Supabase Auth per recuperare eventuali account orfani
        try:
            auth_users_resp = supabase_admin.auth.admin.list_users()
            auth_users = auth_users_resp if isinstance(auth_users_resp, list) else getattr(auth_users_resp, 'users', auth_users_resp)
            existing_p_ids = {p['id'] for p in list_profili}
            for u in auth_users:
                if u.id not in existing_p_ids:
                    try:
                        new_p = {"id": u.id, "email": u.email, "ruolo": "Staff", "privacy_accettata": False}
                        supabase_admin.table('profili').insert(new_p).execute()
                        list_profili.append(new_p)
                        existing_p_ids.add(u.id)
                    except Exception:
                        pass
        except Exception:
            pass

        dict_atleti_id_to_name = {a['id']: f"{a['nome']} {a['cognome']}" for a in list_atleti}
        dict_user_assoc = {}
        for a in list_assoc:
            u_id = a.get('profilo_id')
            a_name = dict_atleti_id_to_name.get(a.get('atleta_id'), '')
            if u_id and a_name:
                dict_user_assoc.setdefault(u_id, []).append(a_name)

        tot_profili = len(list_profili)
        tot_staff = sum(1 for p in list_profili if p.get('ruolo') == 'Staff')
        tot_atleti = sum(1 for p in list_profili if p.get('ruolo') == 'Atleta')
        tot_admin = sum(1 for p in list_profili if p.get('ruolo') == 'Super-Admin')
        utenti_senza_privacy = [p['email'] for p in list_profili if not p.get('privacy_accettata')]
        tot_priv_ok = tot_profili - len(utenti_senza_privacy)
        tot_sess_admin = len(df_storico_admin)
        tot_reali_admin = len(df_storico_admin[df_storico_admin['Dato_Simulato'] == False]) if (not df_storico_admin.empty and 'Dato_Simulato' in df_storico_admin.columns) else 0
        tot_sim_admin = tot_sess_admin - tot_reali_admin

        # 1. KPI CARDS EXECUTIVE (MONITORAGGIO GLOBALE ACCOUNT & GDPR)
        col_u1, col_u2, col_u3, col_u4 = st.columns(4)
        with col_u1:
            st.markdown(
                card_kpi(
                    tr("Account Registrati", "Registered Accounts"),
                    f"<span style='font-size:24px; font-weight:900; color:#0f172a;'>{tot_profili}</span>",
                    f"{tot_admin} Admin · {tot_staff} Staff · {tot_atleti} Atleti",
                    "#0ea5e9"
                ),
                unsafe_allow_html=True
            )
        with col_u2:
            pct_priv = int((tot_priv_ok / tot_profili) * 100) if tot_profili > 0 else 0
            st.markdown(
                card_kpi(
                    tr("Conformità GDPR", "GDPR Compliance"),
                    f"<span style='font-size:24px; font-weight:900; color:#0f172a;'>{tot_priv_ok}/{tot_profili}</span>",
                    f"{pct_priv}% {tr('Consensi Privacy Attivi', 'Active Consents')}",
                    "#10b981" if pct_priv == 100 else "#f59e0b"
                ),
                unsafe_allow_html=True
            )
        with col_u3:
            n_non_conf = len(utenti_senza_privacy)
            priv_warn_col = "#10b981" if n_non_conf == 0 else "#ef4444"
            priv_warn_val = tr("✓ 100% Regolari", "✓ 100% Compliant") if n_non_conf == 0 else f"[!] {n_non_conf} Non A Norma"
            priv_warn_sub = tr("Nessun alert privacy", "No privacy alerts") if n_non_conf == 0 else tr("Consenso revocato / mancante", "Consent revoked / missing")
            st.markdown(
                card_kpi(
                    tr("Allarmi Privacy", "Privacy Alerts"),
                    f"<span style='font-size:20px; font-weight:900; color:{priv_warn_col};'>{priv_warn_val}</span>",
                    priv_warn_sub,
                    priv_warn_col
                ),
                unsafe_allow_html=True
            )
        with col_u4:
            st.markdown(
                card_kpi(
                    tr("Sessioni Totali DB", "Total DB Sessions"),
                    f"<span style='font-size:24px; font-weight:900; color:#0f172a;'>{tot_sess_admin}</span>",
                    f"{tot_reali_admin} {tr('Reali', 'Real')} · {tot_sim_admin} {tr('Simulate', 'Simulated')}",
                    "#8b5cf6"
                ),
                unsafe_allow_html=True
            )

        st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)

        # 2. BANNER DI ALERT GDPR SE QUALCUNO NON HA CONCESSO O HA REVOCATO LA PRIVACY
        if utenti_senza_privacy:
            st.warning(
                f"[!] **Attenzione Privacy GDPR:** {len(utenti_senza_privacy)} account su {tot_profili} **hanno revocato o non hanno ancora concesso** la spunta sul trattamento dei dati personali:\n\n"
                + ", ".join([f"`{em}`" for em in utenti_senza_privacy])
            )
        else:
            st.success(f"✓ Tutti i {tot_profili} profili utente hanno il consenso Privacy (GDPR) attivo e conforme.")

        # 3. TABELLA DI RIEPILOGO PROFILI, ACCESSI & STATO PRIVACY
        with st.expander("Registro Dettagliato Profili, Accessi & Stato Privacy (GDPR)", expanded=bool(utenti_senza_privacy)):
            filtro_tab = st.radio(
                "Filtra elenco account:",
                ["Tutti gli Account", "Solo Senza Consenso Privacy ([!])", "Solo con Sessioni nel DB"],
                horizontal=True,
                key="flt_tab_usr"
            )

            tabella_utenti = []
            for p_u in list_profili:
                em_u = p_u['email']
                p_uid = p_u['id']
                r_u = p_u.get('ruolo', 'Atleta')
                priv_ok = bool(p_u.get('privacy_accettata', False))

                df_u_sub = df_storico_admin[df_storico_admin['Uploader_Email'] == em_u] if (not df_storico_admin.empty and 'Uploader_Email' in df_storico_admin.columns) else pd.DataFrame()
                n_sess_u = len(df_u_sub)
                n_real_u = len(df_u_sub[df_u_sub['Dato_Simulato'] == False]) if (not df_u_sub.empty and 'Dato_Simulato' in df_u_sub.columns) else 0
                n_sim_u = n_sess_u - n_real_u

                if r_u == 'Super-Admin':
                    atleti_str = "Tutti (Super-Admin)"
                else:
                    atleti_str = ", ".join(dict_user_assoc.get(p_uid, [])) if dict_user_assoc.get(p_uid) else "Nessuno"

                # Applicazione filtri
                if filtro_tab == "Solo Senza Consenso Privacy ([!])" and priv_ok:
                    continue
                if filtro_tab == "Solo con Sessioni nel DB" and n_sess_u == 0:
                    continue

                tabella_utenti.append({
                    "Email Account": em_u,
                    "Ruolo": r_u,
                    "Stato Privacy GDPR": "✓ Concesso" if priv_ok else "[!] REVOCATO / MANCANTE",
                    "Atleti Assegnati": atleti_str,
                    "Sessioni Totali": n_sess_u,
                    "Reali": n_real_u,
                    "Simulate": n_sim_u
                })

            if tabella_utenti:
                st.dataframe(pd.DataFrame(tabella_utenti), use_container_width=True)
            else:
                st.info("Nessun utente corrisponde al filtro selezionato.")

        st.divider()

        # 4. CREA NUOVO PROFILO UTENTE
        with st.expander("+ Crea Nuovo Profilo Utente", expanded=False):
            st.markdown(t['add_usr'])
            with st.form("form_crea_utente"):
                col_email, col_ruolo_nuovo = st.columns(2)
                with col_email: nueva_email = st.text_input(t['email_new'])
                with col_ruolo_nuovo: nuovo_ruolo = st.selectbox(t['assign_role'], ["Staff (Coach / Preparatore / Fisio)", "Atleta", "Super-Admin"], index=0)
                if st.form_submit_button(t['btn_add_usr'], type="primary") and nueva_email:
                    target_email = nueva_email.strip().lower()
                    db_ruolo = "Staff" if ("staff" in nuovo_ruolo.lower() or "coach" in nuovo_ruolo.lower()) else ("Super-Admin" if "super-admin" in nuovo_ruolo.lower() else "Atleta")
                    pwd_temp = f"M0V3-{secrets.token_urlsafe(6)}!"
                    try:
                        uid = None
                        try:
                            new_user = supabase_admin.auth.admin.create_user({"email": target_email, "password": pwd_temp, "email_confirm": True})
                            uid = new_user.user.id
                        except Exception as e_auth:
                            # Se l'utente esiste già in Auth, recupera il suo UID e reimposta la password provvisoria
                            if "already been registered" in str(e_auth).lower() or "already exists" in str(e_auth).lower():
                                auth_users_resp = supabase_admin.auth.admin.list_users()
                                auth_users = auth_users_resp if isinstance(auth_users_resp, list) else getattr(auth_users_resp, 'users', auth_users_resp)
                                matched_u = next((u for u in auth_users if u.email and u.email.lower() == target_email), None)
                                if matched_u:
                                    uid = matched_u.id
                                    supabase_admin.auth.admin.update_user_by_id(uid, {"password": pwd_temp, "email_confirm": True})
                                else:
                                    raise e_auth
                            else:
                                raise e_auth

                        supabase_admin.table('profili').upsert({
                            "id": uid,
                            "email": target_email,
                            "ruolo": db_ruolo,
                            "privacy_accettata": False
                        }).execute()
                        st.success(f"✓ Utente registrato con successo nel database: {target_email} (Ruolo: {db_ruolo})")

                        # Invio Email con credenziali, link di accesso e nota cambio password
                        ok_mail, msg_mail = invia_email_creazione_account(target_email, pwd_temp, db_ruolo)
                        if ok_mail:
                            st.success(f"Email di benvenuto inviata con successo all'indirizzo {target_email} con credenziali e link di accesso!")
                        else:
                            st.warning(f"[!] Account registrato, ma notifica email non inviata ({msg_mail}). Puoi comunicare manualmente le credenziali:")

                        st.code(
                            f"Email: {target_email}\n"
                            f"Password provvisoria: {pwd_temp}\n\n"
                            f"Nota inviata all'utente: Potrai cambiare questa password provvisoria quando entri nella webapp recandoti nella sezione 'Profilo Personale'.",
                            language="text"
                        )
                    except Exception as e:
                        st.error(f"Errore creazione utente: {e}")

        st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)

        # 5. GESTIONE, PERMESSI, PRIVACY E DATASET DELL'UTENTE SELEZIONATO
        st.markdown(f"### {t['mod_usr']}")

        if list_profili and list_atleti:
            dict_atleti = {f"{a['nome']} {a['cognome']}": a['id'] for a in list_atleti}

            # Helper per etichetta informativa nel selectbox
            def _format_user_option(email_opt):
                if email_opt == t['select']:
                    return t['select']
                p_item = next((p for p in list_profili if p['email'] == email_opt), None)
                if not p_item:
                    return email_opt
                pr_badge = "✓ Priv. OK" if p_item.get('privacy_accettata') else "[!] NO PRIVACY"
                n_s = len(df_storico_admin[df_storico_admin['Uploader_Email'] == email_opt]) if (not df_storico_admin.empty and 'Uploader_Email' in df_storico_admin.columns) else 0
                return f"{email_opt}  ·  [{p_item.get('ruolo', 'Atleta')}]  ·  [{pr_badge}]  ·  ({n_s} sess.)"

            utente_selezionato = st.selectbox(
                t['sel_usr'],
                [t['select']] + [p['email'] for p in list_profili],
                format_func=_format_user_option,
                key="sel_ut"
            )

            if utente_selezionato != t['select']:
                profilo_data = next((p for p in list_profili if p['email'] == utente_selezionato), None)
                p_id = profilo_data['id']
                priv_selezionata = bool(profilo_data.get('privacy_accettata', False))

                # Box informativo stato utente
                with st.container(border=True):
                    c_info1, c_info2 = st.columns([2, 1])
                    with c_info1:
                        st.markdown(f"#### `{utente_selezionato}`")
                        if priv_selezionata:
                            st.markdown("<span style='background:#dcfce7; color:#166534; font-size:13px; font-weight:800; padding:4px 10px; border-radius:6px; display:inline-block;'>✓ Consenso Privacy GDPR: Attivo</span>", unsafe_allow_html=True)
                        else:
                            st.markdown("<span style='background:#fee2e2; color:#991b1b; font-size:13px; font-weight:800; padding:4px 10px; border-radius:6px; display:inline-block;'>[!] Consenso Privacy GDPR: NON RILASCIATO / REVOCATO</span>", unsafe_allow_html=True)

                    with c_info2:
                        st.caption("Azione Rapida Admin:")
                        if not priv_selezionata:
                            if st.button("✓ Registra Consenso (Cartaceo/Verbale)", key=f"btn_force_priv_{p_id}", use_container_width=True):
                                supabase_admin.table('profili').update({"privacy_accettata": True}).eq('id', p_id).execute()
                                st.success(f"Consenso registrato per {utente_selezionato}!")
                                st.rerun()
                        else:
                            if st.button("[!] Revoca Consenso d'Ufficio", key=f"btn_revoke_priv_{p_id}", use_container_width=True):
                                supabase_admin.table('profili').update({"privacy_accettata": False}).eq('id', p_id).execute()
                                st.warning(f"Consenso revocato d'ufficio per {utente_selezionato}!")
                                st.rerun()

                st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)

                # Form modifica ruolo e atleti
                with st.form(f"form_permessi_{p_id}"):
                    col_ruolo, col_atleti = st.columns(2)
                    with col_ruolo:
                        curr_ruolo = profilo_data.get('ruolo', 'Staff')
                        ruoli_scelta = ["Staff (Coach / Preparatore / Fisio)", "Atleta", "Super-Admin"]
                        idx_r = 0
                        if curr_ruolo == 'Atleta':
                            idx_r = 1
                        elif curr_ruolo == 'Super-Admin':
                            idx_r = 2
                        mod_ruolo = st.selectbox(t['usr_role'], ruoli_scelta, index=idx_r)
                    with col_atleti:
                        res_assoc_u = supabase_admin.table('associazioni').select('atleta_id').eq('profilo_id', p_id).execute()
                        nomi_predefiniti = [n for n, id_a in dict_atleti.items() if id_a in [a['atleta_id'] for a in res_assoc_u.data]]
                        atleti_selezionati = st.multiselect(t['vis_atl'], options=list(dict_atleti.keys()), default=nomi_predefiniti)

                    if st.form_submit_button(t['btn_save_perm'], type="primary"):
                        db_mod_ruolo = "Staff" if ("staff" in mod_ruolo.lower() or "coach" in mod_ruolo.lower()) else ("Super-Admin" if "super-admin" in mod_ruolo.lower() else "Atleta")
                        supabase_admin.table('profili').update({"ruolo": db_mod_ruolo}).eq('id', p_id).execute()
                        supabase_admin.table('associazioni').delete().eq('profilo_id', p_id).execute()
                        nuove_assoc = [{"profilo_id": p_id, "atleta_id": dict_atleti[n]} for n in atleti_selezionati]
                        if nuove_assoc:
                            supabase_admin.table('associazioni').insert(nuove_assoc).execute()
                        clear_atleti_cache()
                        st.success(f"Permessi aggiornati per {utente_selezionato}!")
                        st.rerun()

                # Sezione Sicurezza e Reset Password
                st.markdown(f"##### {tr('Sicurezza & Reset Password Utente', 'User Security & Password Reset')}")
                col_sec1, col_sec2 = st.columns(2)
                with col_sec1:
                    if st.button("Genera e Invia Nuova Password via Email", key=f"btn_reset_p_{p_id}", use_container_width=True, type="primary"):
                        pwd_reset = f"M0V3-{secrets.token_urlsafe(6)}!"
                        try:
                            supabase_admin.auth.admin.update_user_by_id(p_id, {"password": pwd_reset})
                            ok_m, msg_m = invia_email_reset_password_admin(utente_selezionato, pwd_reset)
                            if ok_m:
                                st.success(f"✓ Nuova password provvisoria inviata via email a {utente_selezionato}!")
                            else:
                                st.warning(f"[!] Password aggiornata nel database, ma email non inviata ({msg_m}).")
                            st.code(
                                f"Email: {utente_selezionato}\n"
                                f"Nuova password provvisoria: {pwd_reset}\n\n"
                                f"Nota per l'utente: Potrà cambiare la password quando entra nella webapp direttamente in 'Profilo Personale'.",
                                language="text"
                            )
                        except Exception as e:
                            st.error(f"Errore reset password: {e}")
                with col_sec2:
                    if st.button(t['btn_email_reset'], key=f"btn_reset_em_{p_id}", use_container_width=True):
                        try:
                            supabase.auth.reset_password_email(utente_selezionato)
                            st.success(f"✓ Link di ripristino password inviato via email a {utente_selezionato}!")
                        except Exception as e:
                            st.error(f"Errore invio link di reset: {e}")

                # 6. GESTIONE DATASET, CSV & CANCELLAZIONE SESSIONI DELL'UTENTE
                st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)
                df_u_data = df_storico_admin[df_storico_admin['Uploader_Email'] == utente_selezionato].copy() if (not df_storico_admin.empty and 'Uploader_Email' in df_storico_admin.columns) else pd.DataFrame()

                with st.container(border=True):
                    st.markdown(f"#### Gestione Dataset & CSV di `{utente_selezionato}`")
                    tot_u_sess = len(df_u_data)
                    tot_u_real = len(df_u_data[df_u_data['Dato_Simulato'] == False]) if (not df_u_data.empty and 'Dato_Simulato' in df_u_data.columns) else 0
                    tot_u_sim = tot_u_sess - tot_u_real

                    st.caption(f"Attualmente sono registrate **{tot_u_sess} sessioni** a nome di questo utente ({tot_u_real} reali da sensore · {tot_u_sim} simulate).")

                    c_csv_down, c_csv_del = st.columns(2, gap="medium")
                    with c_csv_down:
                        if not df_u_data.empty:
                            csv_usr_bytes = df_u_data.to_csv(index=False).encode('utf-8-sig')
                            nome_file_exp = f"M0V3_Dataset_{slugify_name(utente_selezionato)}.csv"
                            st.download_button(
                                label=f"Scarica Tutti i CSV/Dati dell'Utente ({tot_u_sess} sessioni .csv)",
                                data=csv_usr_bytes,
                                file_name=nome_file_exp,
                                mime="text/csv",
                                type="primary",
                                use_container_width=True,
                                key=f"down_usr_csv_{p_id}"
                            )
                            st.caption("Il file include tutte le sessioni con tutte le 31 colonne M0V3 calcolate (Volume, Intensità, GPS e metadati).")
                        else:
                            st.info("Nessuna sessione registrata a nome di questo utente.")

                    with c_csv_del:
                        if not df_u_data.empty:
                            with st.expander("Cancella Tutti i CSV e Dati di questo Utente", expanded=False):
                                st.warning(f"Attenzione: questa azione rimuoverà definitivamente tutte le **{tot_u_sess} sessioni** di `{utente_selezionato}` dal database.")
                                chk_del_u_data = st.checkbox(
                                    f"Confermo l'eliminazione definitiva di tutti i dati di {utente_selezionato}",
                                    key=f"chk_del_data_{p_id}"
                                )
                                if st.button("Elimina Tutti i Dati e CSV", type="primary", disabled=not chk_del_u_data, key=f"btn_del_data_{p_id}"):
                                    df_nuovo_admin = df_storico_admin[df_storico_admin['Uploader_Email'] != utente_selezionato].copy()
                                    save_local_database(df_nuovo_admin)
                                    st.success(f"Eliminate con successo tutte le {tot_u_sess} sessioni di {utente_selezionato} dal database!")
                                    st.rerun()
                        else:
                            st.caption("Nessun dato da cancellare per questo utente.")

                    # 7. ISPEZIONE ED ELIMINAZIONE SINGOLA SESSIONE
                    if not df_u_data.empty:
                        with st.expander(f"Ispeziona o Rimuovi Singola Sessione di `{utente_selezionato}` ({tot_u_sess} sessioni)", expanded=False):
                            cols_anteprima = [c for c in ['Date', 'Players', 'Session_Type', 'Duration', 'Training_Load', 'High_Intensity_Distance_m', 'File_Name', 'Dato_Simulato'] if c in df_u_data.columns]
                            st.dataframe(df_u_data[cols_anteprima].sort_values(by='Date', ascending=False) if 'Date' in df_u_data.columns else df_u_data[cols_anteprima], use_container_width=True)

                            st.markdown("##### Rimuovi una Sessione Specifica")
                            opzioni_singola = {}
                            df_u_data_sort = df_u_data.copy()
                            if 'Date' in df_u_data_sort.columns:
                                df_u_data_sort['_dt_s'] = pd.to_datetime(df_u_data_sort['Date'], format="%d/%m/%Y", errors='coerce')
                                df_u_data_sort = df_u_data_sort.sort_values(by='_dt_s', ascending=False)
                            for idx_r, row_s in df_u_data_sort.iterrows():
                                d_str = str(row_s.get('Date', 'N/D'))
                                p_str = str(row_s.get('Players', 'N/D'))
                                t_str = str(row_s.get('Session_Type', 'N/D'))
                                dur_str = str(row_s.get('Duration', '0'))
                                fn_str = str(row_s.get('File_Name', 'CSV'))
                                lbl_s = f"{d_str} — {p_str} — {t_str} ({dur_str} min) [File: {fn_str}]"
                                opzioni_singola[lbl_s] = idx_r

                            sel_singola_lbl = st.selectbox("Seleziona la sessione da eliminare:", list(opzioni_singola.keys()), key=f"sel_sing_{p_id}")
                            c_del_s1, c_del_s2 = st.columns([1, 1])
                            with c_del_s1:
                                chk_conf_sing = st.checkbox("Confermo eliminazione singola sessione", key=f"chk_sing_{p_id}")
                            with c_del_s2:
                                if st.button("Elimina Questa Sessione", type="primary", disabled=not chk_conf_sing, key=f"btn_del_sing_{p_id}"):
                                    idx_to_drop = opzioni_singola[sel_singola_lbl]
                                    df_nuovo_sing = df_storico_admin.drop(index=idx_to_drop).copy()
                                    save_local_database(df_nuovo_sing)
                                    st.success(f"Sessione '{sel_singola_lbl}' eliminata con successo!")
                                    st.rerun()

        st.markdown("---")
        st.markdown("### Richieste di Reset Password (M0V3)")
        try:
            res_richieste = supabase_admin.table('richieste_reset').select('*').order('data_richiesta', desc=True).execute()
            if res_richieste.data:
                df_richieste = pd.DataFrame(res_richieste.data)
                st.dataframe(df_richieste[['id', 'email', 'data_richiesta']], use_container_width=True)
                
                if st.button("Svuota Storico Richieste"):
                    supabase_admin.table('richieste_reset').delete().neq('id', 0).execute()
                    st.success("Storico richieste pulito!")
                    st.rerun()
            else:
                st.info("Nessuna richiesta di reset password in sospeso.")
        except Exception as e:
            st.info("Crea la tabella 'richieste_reset' su Supabase per visualizzare qui l'elenco delle richieste.")
                
    elif active_admin_tab == t['tab_map']:
        st.markdown(t['map_mng'])
        st.info(t['map_info'])
        res_profili = supabase_admin.table('profili').select('*').execute()
        if res_profili.data:
            id_to_email = {p['id']: p['email'] for p in res_profili.data}
            utente_mappa = st.selectbox(t['sel_usr_map'], [t['select']] + [p['email'] for p in res_profili.data], key="sel_map")
            if utente_mappa != t['select']:
                profilo_mappa_id = next((p['id'] for p in res_profili.data if p['email'] == utente_mappa), None)
                res_mappa_attuale = supabase_admin.table('mappatura_csv').select('mapping').eq('profilo_id', profilo_mappa_id).execute()
                mappa_esistente = res_mappa_attuale.data[0]['mapping'] if res_mappa_attuale.data and res_mappa_attuale.data[0].get('mapping') else {}

                # 1. Funzione Clona/Copia Mappatura da un altro Utente già configurato
                res_tutte_mappe = supabase_admin.table('mappatura_csv').select('profilo_id, mapping').execute()
                utenti_con_mappa = {}
                if res_tutte_mappe.data:
                    for r_m in res_tutte_mappe.data:
                        pid_m = r_m.get('profilo_id')
                        map_m = r_m.get('mapping') or {}
                        if pid_m and pid_m != profilo_mappa_id and pid_m in id_to_email and map_m:
                            n_attivi = sum(1 for v in map_m.values() if v and v not in ("Non presente", "Not present"))
                            utenti_con_mappa[f"{id_to_email[pid_m]} ({n_attivi}/{len(COLONNE_STANDARD)} parametri)"] = map_m

                with st.expander("Clona / Copia Mappatura da un altro Utente", expanded=not bool(mappa_esistente)):
                    if utenti_con_mappa:
                        col_cl1, col_cl2 = st.columns([2.5, 1])
                        with col_cl1:
                            sorgente_clone = st.selectbox(
                                "Scegli l'account sorgente da cui copiare l'intera mappatura CSV:",
                                list(utenti_con_mappa.keys()),
                                key=f"clone_src_{profilo_mappa_id}"
                            )
                        with col_cl2:
                            st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)
                            if st.button("Clona Mappatura Ora", type="primary", use_container_width=True, key=f"btn_clone_{profilo_mappa_id}"):
                                try:
                                    mappa_clonata = utenti_con_mappa[sorgente_clone]
                                    supabase_admin.table('mappatura_csv').upsert({"profilo_id": profilo_mappa_id, "mapping": mappa_clonata}).execute()
                                    for c_std in COLONNE_STANDARD:
                                        for k_pref in ("sel_", "f_"):
                                            st.session_state.pop(f"{k_pref}{profilo_mappa_id}_{c_std}", None)
                                    st.success(f"Mappatura copiata con successo su {utente_mappa}!")
                                    st.rerun()
                                except Exception as err_cl:
                                    st.error(f"Errore durante la clonazione: {err_cl}")
                    else:
                        st.caption("Nessun altro utente ha ancora una mappatura salvata da cui copiare.")

                # 2. Caricamento opzionale CSV di esempio (per rilevare nuove colonne e testare live i valori)
                csv_esempio = st.file_uploader(
                    f"{t['upload_sample']} {utente_mappa} (opzionale se vuoi solo modificare formule o mappature già salvate)",
                    type=['csv'],
                    key=f"up_sample_{profilo_mappa_id}"
                )

                df_sample_full = pd.DataFrame()
                colonne_csv = []
                if csv_esempio is not None:
                    try:
                        df_sample_full = leggi_csv_gps_robusto(csv_esempio)
                        colonne_csv = df_sample_full.columns.tolist()
                        st.success(f"CSV letto correttamente: {len(colonne_csv)} colonne trovate ({len(df_sample_full)} righe).")
                    except Exception as e:
                        st.error(f"Errore lettura CSV di esempio: {e}")

                # Costruisci la lista di colonne selezionabili unendo quelle del CSV (se caricato) e quelle già salvate nella mappatura
                colonne_salvate = [
                    str(v).strip() for v in mappa_esistente.values()
                    if v and not str(v).strip().startswith("=") and v not in ("Non presente", "Not present")
                ]
                colonne_disponibili = list(dict.fromkeys(colonne_csv + colonne_salvate + COLONNE_STANDARD))

                n_configurati = sum(1 for c in COLONNE_STANDARD if mappa_esistente.get(c) and mappa_esistente.get(c) not in ("Non presente", "Not present"))
                st.markdown(
                    f"#### Configurazione Parametri M0V3 per `{utente_mappa}` "
                    f"({n_configurati}/{len(COLONNE_STANDARD)} parametri attivi)"
                )
                st.caption(t['map_assoc'])

                nuovo_mapping = {}
                col_m_left, col_m_right = st.columns(2, gap="large")
                half_idx = (len(COLONNE_STANDARD) + 1) // 2

                for idx_c, col_std in enumerate(COLONNE_STANDARD):
                    target_col_ui = col_m_left if idx_c < half_idx else col_m_right
                    with target_col_ui:
                        default_fallback = col_std if col_std in colonne_csv else t['not_present']
                        guess_iniziale = mappa_esistente.get(col_std, default_fallback)

                        if str(guess_iniziale).strip().startswith("="):
                            val_testo = str(guess_iniziale).strip()
                            guess_selettore = t['custom_formula']
                        else:
                            if guess_iniziale not in colonne_disponibili and guess_iniziale != t['not_present']:
                                guess_iniziale = t['not_present']
                            guess_selettore = guess_iniziale
                            val_testo = "="

                        opzioni = [t['not_present']] + colonne_disponibili + [t['custom_formula']]
                        idx_default = opzioni.index(guess_selettore) if guess_selettore in opzioni else 0

                        scelta = st.selectbox(
                            f"{t['req_param']} {col_std}",
                            opzioni,
                            index=idx_default,
                            key=f"sel_{profilo_mappa_id}_{col_std}"
                        )
                        if scelta == t['custom_formula']:
                            testo_formula = st.text_input(
                                f"Formula per {col_std} (es. =[Col_1] + [Col_2])",
                                value=val_testo,
                                key=f"f_{profilo_mappa_id}_{col_std}"
                            )
                            nuovo_mapping[col_std] = testo_formula.strip()
                        else:
                            nuovo_mapping[col_std] = scelta

                # 3. Test & Anteprima Live sul CSV di esempio (se caricato)
                if not df_sample_full.empty:
                    st.divider()
                    st.markdown("#### Test & Anteprima Live Mappatura (Riga 1 del CSV caricato)")
                    df_prev_1, rep_prev = applica_mappatura_csv(df_sample_full.head(1), nuovo_mapping)
                    row_prev = df_prev_1.iloc[0]

                    html_prev = (
                        "<div style='background:white; border:1px solid #e2e8f0; border-radius:12px; overflow:hidden; margin-bottom:16px; font-family:\"Inter\", sans-serif;'>"
                        "<table style='width:100%; border-collapse:collapse; font-size:13px;'>"
                        "<tr style='background:#0f172a; color:white;'>"
                        "<th style='padding:10px 14px; text-align:left;'>Parametro M0V3</th>"
                        "<th style='padding:10px 14px; text-align:left;'>Regola / Sorgente</th>"
                        "<th style='padding:10px 14px; text-align:center;'>Valore Calcolato (Riga 1)</th>"
                        "<th style='padding:10px 14px; text-align:center;'>Stato</th>"
                        "</tr>"
                    )
                    for c_std in COLONNE_STANDARD:
                        r_info = rep_prev.get(c_std, {})
                        st_code = r_info.get("status", "unmapped")
                        src_txt = str(r_info.get("source", "Non presente"))
                        det_txt = str(r_info.get("detail", ""))
                        val_c = row_prev.get(c_std)
                        val_str = str(val_c) if pd.notna(val_c) else "N/A"

                        is_num_zero = (c_std not in ("Date", "Session", "Players")) and (pd.isna(val_c) or float(val_c) == 0.0)
                        if st_code == "error" or st_code == "missing":
                            b_bg, b_fg, b_lbl = "#fee2e2", "#991b1b", f"[X] {det_txt}"
                        elif st_code == "warning":
                            b_bg, b_fg, b_lbl = "#fef3c7", "#b45309", f"[!] {det_txt}"
                        elif st_code == "unmapped" or is_num_zero:
                            b_bg, b_fg, b_lbl = "#fef3c7", "#b45309", f"[!] Valore 0 ({det_txt})"
                        else:
                            b_bg, b_fg, b_lbl = "#dcfce7", "#166534", f"✓ Valorizzato ({det_txt})"

                        html_prev += (
                            "<tr style='border-bottom:1px solid #f1f5f9;'>"
                            f"<td style='padding:8px 14px; font-weight:700; color:#0f172a;'>{c_std}</td>"
                            f"<td style='padding:8px 14px; color:#475569; font-family:monospace; font-size:12px;'>{src_txt}</td>"
                            f"<td style='padding:8px 14px; text-align:center; font-weight:800; color:#0f172a;'>{val_str}</td>"
                            f"<td style='padding:8px 14px; text-align:center;'><span style='background:{b_bg}; color:{b_fg}; padding:3px 9px; border-radius:6px; font-size:11px; font-weight:700;'>{b_lbl}</span></td>"
                            "</tr>"
                        )
                    html_prev += "</table></div>"
                    st.markdown(html_prev, unsafe_allow_html=True)

                if st.button(t['btn_save_map'], type="primary", key="save_mapping_btn"):
                    try:
                        supabase_admin.table('mappatura_csv').upsert({"profilo_id": profilo_mappa_id, "mapping": nuovo_mapping}).execute()
                        st.success("Mappatura salvata con successo! / Mapping saved!")
                    except Exception as e:
                        st.error(f"Error: {e}")

    elif active_admin_tab == t['tab_rep']:
        st.markdown(
            f"<div style='background:linear-gradient(135deg, #0f172a 0%, #1e293b 100%); padding:16px 20px; border-radius:12px; margin-bottom:18px; border-left:4px solid #0ea5e9; color:#f8fafc; font-family:\"Inter\",sans-serif;'>"
            f"<div style='font-size:14px; font-weight:800; text-transform:uppercase; letter-spacing:0.05em; color:#38bdf8;'><i class='bi bi-shield-check' style='margin-right:8px;'></i>GESTIONE PERMESSI MODULI & VISIBILITÀ MENU LATERALE</div>"
            f"<div style='font-size:12.5px; color:#cbd5e1; margin-top:4px;'>Configura i moduli analitici, le sottopagine e le voci di navigazione per ciascun utente. <b>Se un'intera area o pagina viene deselezionata, scomparirà automaticamente dalla barra laterale dell'utente.</b></div>"
            f"</div>",
            unsafe_allow_html=True
        )

        res_profili = supabase_admin.table('profili').select('*').order('email').execute()
        if res_profili.data:
            utente_report = st.selectbox(
                tr("Seleziona Utente da Configurare:", "Select User to Configure:"),
                [t['select']] + [p['email'] for p in res_profili.data],
                key="sel_rep_usr"
            )

            if utente_report != t['select']:
                profilo_data_rep = next((p for p in res_profili.data if p['email'] == utente_report), None)
                p_id_rep = profilo_data_rep['id']
                ruolo_rep = profilo_data_rep.get('ruolo', 'Staff')

                if ruolo_rep == 'Super-Admin':
                    st.info("⭐ **Account Super-Admin**: Gli utenti con ruolo Super-Admin hanno accesso illimitato a tutte le aree, pagine e sottomoduli per definizione di sistema.")
                else:
                    # Caricamento permessi salvati da Supabase
                    res_permessi = supabase_admin.table('moduli_report').select('*').eq('profilo_id', p_id_rep).execute()
                    ha_config_salvata = bool(res_permessi.data)
                    permessi_attuali = set((r['area'], r['nome_report']) for r in res_permessi.data) if ha_config_salvata else set()

                    # Gestione stato pulsanti rapidi di selezione
                    state_prefix = f"perm_{p_id_rep}_"

                    c_btn_all1, c_btn_all2, _ = st.columns([1.5, 1.5, 3])
                    with c_btn_all1:
                        if st.button("✓ " + tr("Abilita Tutte le Aree", "Enable All Areas"), key=f"{state_prefix}btn_all_on"):
                            for area, reports in CATALOGO_REPORT.items():
                                st.session_state[f"{state_prefix}area_{area}"] = True
                                for r in reports:
                                    st.session_state[f"{state_prefix}chk_{area}_{r}"] = True
                            for pag in PAGINE_OPERATIVE:
                                st.session_state[f"{state_prefix}op_{pag['chiave']}"] = True
                            st.rerun()

                    with c_btn_all2:
                        if st.button("✗ " + tr("Disabilita Tutte le Aree", "Disable All Areas"), key=f"{state_prefix}btn_all_off"):
                            for area, reports in CATALOGO_REPORT.items():
                                st.session_state[f"{state_prefix}area_{area}"] = False
                                for r in reports:
                                    st.session_state[f"{state_prefix}chk_{area}_{r}"] = False
                            for pag in PAGINE_OPERATIVE:
                                st.session_state[f"{state_prefix}op_{pag['chiave']}"] = False
                            st.rerun()

                    st.markdown("<div style='margin-bottom:14px;'></div>", unsafe_allow_html=True)
                    selezioni_nuove = []

                    # 1. AREE MODULARI CON SOTTOPAGINE E GRAFICI
                    st.markdown(f"#### {tr('Aree Analitiche & Sottopagine Modulari', 'Analytical Areas & Modular Sub-Pages')}")
                    st.caption(tr("Abilita o disabilita intere macro-aree o singoli grafici/tab per questo utente.", "Enable or disable whole macro-areas or individual sub-pages for this user."))

                    # Helper compatibilità backward con vecchi nomi aree/report
                    def _is_module_permitted_in_saved(a_name, rep_name):
                        if (a_name, rep_name) in permessi_attuali:
                            return True
                        if a_name == "Medico & Extra Tennis":
                            for a_alt in ['Calendario & Area Medica', 'Inserimento Sessioni Extra Tennis']:
                                if (a_alt, rep_name) in permessi_attuali:
                                    return True
                                if rep_name == "Inserimento & Gestione Registro" and any(a_alt == ar and "Registro" in rep for (ar, rep) in permessi_attuali):
                                    return True
                                if rep_name == "Allenamenti GYM e Fisico" and any(a_alt == ar and ("GYM" in rep or "Fisico" in rep) for (ar, rep) in permessi_attuali):
                                    return True
                        if a_name == "Analisi Wellness-RPE-GPS":
                            if ('Carico Interno', rep_name) in permessi_attuali or ('Pagine Operative', 'Carico Interno') in permessi_attuali:
                                return True
                            if rep_name == "Analisi Incrociata" and any("Clinici" in rep or "Incrociata" in rep for (_, rep) in permessi_attuali):
                                return True
                        return False

                    for area, reports in CATALOGO_REPORT.items():
                        # Calcolo default se mai configurato prima
                        area_key = f"{state_prefix}area_{area}"
                        moduli_abilitati_area = [r for r in reports if _is_module_permitted_in_saved(area, r)]
                        
                        # Se l'utente non ha mai avuto una config salvata, abilitiamo tutto di default
                        default_area_active = True if not ha_config_salvata else (len(moduli_abilitati_area) > 0)
                        
                        if area_key not in st.session_state:
                            st.session_state[area_key] = default_area_active

                        st.markdown(f"""
                        <div style="background:#ffffff; border:1px solid #e2e8f0; border-left:5px solid #0284c7; border-radius:10px; padding:10px 14px; margin-top:16px; margin-bottom:8px; display:flex; justify-content:space-between; align-items:center;">
                            <span style="font-size:14px; font-weight:800; color:#0f172a; text-transform:uppercase;">
                                <i class="bi bi-folder2-open" style="margin-right:6px; color:#0284c7;"></i>{area}
                            </span>
                            <span style="font-size:11px; font-weight:700; color:#64748b;">
                                {len(reports)} {tr('Sottopagine / Grafici', 'Sub-Pages / Graphs')}
                            </span>
                        </div>
                        """, unsafe_allow_html=True)

                        c_tog, c_sel_all, c_des_all = st.columns([2.5, 1.2, 1.2])
                        with c_tog:
                            area_attiva = st.toggle(
                                f"**{tr('Abilita Area nel Menu:', 'Enable Area in Menu:')} {area}**",
                                key=area_key
                            )
                        with c_sel_all:
                            if st.button(tr("Tutti ✓", "All ✓"), key=f"{state_prefix}all_{area}"):
                                st.session_state[area_key] = True
                                for r in reports:
                                    st.session_state[f"{state_prefix}chk_{area}_{r}"] = True
                                st.rerun()
                        with c_des_all:
                            if st.button(tr("Nessuno ✗", "None ✗"), key=f"{state_prefix}none_{area}"):
                                st.session_state[area_key] = False
                                for r in reports:
                                    st.session_state[f"{state_prefix}chk_{area}_{r}"] = False
                                st.rerun()

                        if area_attiva:
                            cols_rep = st.columns(2)
                            for idx_r, report in enumerate(reports):
                                chk_key = f"{state_prefix}chk_{area}_{report}"
                                default_r = True if not ha_config_salvata else _is_module_permitted_in_saved(area, report)
                                if chk_key not in st.session_state:
                                    st.session_state[chk_key] = default_r

                                with cols_rep[idx_r % 2]:
                                    val_chk = st.checkbox(
                                        report,
                                        key=chk_key
                                    )
                                    if val_chk:
                                        selezioni_nuove.append({"profilo_id": p_id_rep, "area": area, "nome_report": report})
                        else:
                            st.caption(f"*Area {area} disabilitata: la voce scomparirà dal menu laterale dell'utente.*")

                    st.markdown("<hr style='margin:24px 0 16px 0;'>", unsafe_allow_html=True)

                    # 2. PAGINE OPERATIVE & ACCESSO DIRETTO
                    st.markdown(f"#### {tr('Pagine Operative & Accesso Diretto', 'Operational Pages & Direct Access')}")
                    st.caption(tr("Seleziona quali pagine operative e strumenti possono essere visualizzati nella barra laterale dall'utente.", "Select which operational tools and pages can be accessed in the sidebar."))

                    cols_op = st.columns(2)
                    for idx_p, pag in enumerate(PAGINE_OPERATIVE):
                        op_key = f"{state_prefix}op_{pag['chiave']}"
                        default_op = True if not ha_config_salvata else (('Pagine Operative', pag['chiave']) in permessi_attuali)
                        if op_key not in st.session_state:
                            st.session_state[op_key] = default_op

                        with cols_op[idx_p % 2]:
                            st.markdown(f"""
                            <div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:8px; padding:8px 12px; margin-bottom:8px;">
                                <div style="display:flex; align-items:center; gap:8px;">
                                    <i class="bi bi-{pag['icona']}" style="color:#0ea5e9; font-size:16px;"></i>
                                    <span style="font-size:13px; font-weight:700; color:#0f172a;">{pag['nome']}</span>
                                </div>
                            </div>
                            """, unsafe_allow_html=True)
                            val_op = st.checkbox(
                                f"{tr('Consenti accesso a', 'Allow access to')} {pag['chiave']}",
                                key=op_key
                            )
                            if val_op:
                                selezioni_nuove.append({"profilo_id": p_id_rep, "area": "Pagine Operative", "nome_report": pag['chiave']})

                    st.markdown("<div style='margin-top:20px;'></div>", unsafe_allow_html=True)

                    # Pulsante di salvataggio
                    if st.button("" + tr("Salva Permessi & Visibilità Menu Utente", "Save User Permissions & Menu Visibility"), type="primary", use_container_width=True, key=f"btn_save_perm_{p_id_rep}"):
                        try:
                            # Pulizia vecchi permessi
                            supabase_admin.table('moduli_report').delete().eq('profilo_id', p_id_rep).execute()
                            
                            if selezioni_nuove:
                                # Inserimento a blocchi per sicurezza
                                for b_i in range(0, len(selezioni_nuove), 50):
                                    supabase_admin.table('moduli_report').insert(selezioni_nuove[b_i:b_i+50]).execute()
                            
                            st.session_state['refresh_permessi'] = True
                            st.success(f"✓ Permessi e visibilità menu aggiornati con successo per {utente_report}!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Errore durante il salvataggio dei permessi: {e}")

    elif active_admin_tab == t.get('tab_sup', 'Supporto & Ticket'):
        st.markdown(
            f"<div style='background:linear-gradient(135deg, #0f172a 0%, #1e293b 100%); padding:15px 20px; border-radius:12px; margin-bottom:18px; border-left:4px solid #0284c7; color:#f8fafc; font-family:\"Inter\",sans-serif;'>"
            f"<div style='font-size:14px; font-weight:800; text-transform:uppercase; letter-spacing:0.05em; color:#38bdf8;'><i class='bi bi-headset' style='margin-right:8px;'></i>PANNELLO GESTIONE SUPPORTO & SEGNALAZIONI (SUPER-ADMIN)</div>"
            f"<div style='font-size:12.5px; color:#cbd5e1; margin-top:4px;'>Gestisci le richieste di assistenza e rispondi direttamente agli utenti. Le email di riferimento arrivano su <b style='color:#ffffff;'>{SUPPORT_EMAIL}</b>.</div>"
            f"</div>",
            unsafe_allow_html=True
        )

        all_tickets = load_all_tickets()

        # KPI Dashboard Supporto
        n_tot = len(all_tickets)
        n_aperte = sum(1 for tk in all_tickets if tk.get("status") == "Aperta")
        n_in_lav = sum(1 for tk in all_tickets if tk.get("status") == "In Lavorazione")
        n_risolte = sum(1 for tk in all_tickets if tk.get("status") in ["Risolta", "Chiusa"])

        k1, k2, k3, k4 = st.columns(4)
        with k1:
            st.markdown(card_kpi("Totale Segnalazioni", f"<span style='font-size:24px; font-weight:900; color:#0f172a;'>{n_tot}</span>", "Tutti i ticket registrati", "#0ea5e9"), unsafe_allow_html=True)
        with k2:
            st.markdown(card_kpi("In Attesa (Aperte)", f"<span style='font-size:24px; font-weight:900; color:#0284c7;'>{n_aperte}</span>", "Richiedono prima presa in carico", "#0284c7"), unsafe_allow_html=True)
        with k3:
            st.markdown(card_kpi("In Lavorazione", f"<span style='font-size:24px; font-weight:900; color:#f59e0b;'>{n_in_lav}</span>", "Gestione in corso", "#f59e0b"), unsafe_allow_html=True)
        with k4:
            st.markdown(card_kpi("Risolte / Chiuse", f"<span style='font-size:24px; font-weight:900; color:#10b981;'>{n_risolte}</span>", "Completate con successo", "#10b981"), unsafe_allow_html=True)

        st.markdown("<div style='margin-top:16px;'></div>", unsafe_allow_html=True)

        if not all_tickets:
            st.info("Nessuna segnalazione di supporto presente nel sistema al momento.")
        else:
            # Filtri di ricerca
            c_f1, c_f2 = st.columns(2)
            with c_f1:
                filtro_stato = st.selectbox(
                    "Filtra per Stato:",
                    ["Tutte", "Aperta", "In Lavorazione", "Risolta", "Chiusa"],
                    index=0,
                    key="adm_flt_stato"
                )
            with c_f2:
                categorie_presenti = ["Tutte"] + sorted(list({tk.get("category", "") for tk in all_tickets if tk.get("category")}))
                filtro_cat = st.selectbox("Filtra per Categoria:", categorie_presenti, index=0, key="adm_flt_cat")

            filtered_tickets = all_tickets
            if filtro_stato != "Tutte":
                filtered_tickets = [tk for tk in filtered_tickets if tk.get("status") == filtro_stato]
            if filtro_cat != "Tutte":
                filtered_tickets = [tk for tk in filtered_tickets if tk.get("category") == filtro_cat]

            if not filtered_tickets:
                st.info("Nessuna segnalazione corrisponde ai filtri selezionati.")
            else:
                dict_admin_options = {
                    tk["id"]: f"[{tk['status'].upper()}] {tk['id']} — {tk['user_email']} — {tk['subject'][:40]}... ({tk['created_at']})"
                    for tk in filtered_tickets
                }

                sel_admin_ticket_id = st.selectbox(
                    "Seleziona la Segnalazione da gestire:",
                    options=list(dict_admin_options.keys()),
                    format_func=lambda x: dict_admin_options[x],
                    key="sel_admin_ticket"
                )

                sel_tk_adm = next((tk for tk in filtered_tickets if tk["id"] == sel_admin_ticket_id), None)
                if sel_tk_adm:
                    st.markdown("<div style='margin-top:14px;'></div>", unsafe_allow_html=True)
                    
                    b_st = get_status_badge(sel_tk_adm.get("status", "Aperta"))
                    b_pr = get_priority_badge(sel_tk_adm.get("priority", "Normale"))
                    target_user_em = sel_tk_adm.get('user_email', '')

                    card_adm_html = (
                        f"<div style='background:#ffffff; border:1px solid #e2e8f0; border-radius:12px; padding:16px 20px; box-shadow:0 2px 8px -2px rgba(15,23,42,0.06); margin-bottom:14px; font-family:\"Inter\",sans-serif;'>"
                        f"<div style='display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; border-bottom:1px solid #f1f5f9; padding-bottom:10px; margin-bottom:10px;'>"
                        f"<div>"
                        f"<span style='font-size:16px; font-weight:900; color:#0f172a;'>{sel_tk_adm['subject']}</span>"
                        f"<div style='font-size:11.5px; color:#64748b; margin-top:2px;'>ID: <b style='color:#0284c7;'>{sel_tk_adm['id']}</b> · Creato: {sel_tk_adm['created_at']}</div>"
                        f"</div>"
                        f"<div style='display:flex; align-items:center; gap:8px;'>{b_pr} {b_st}</div>"
                        f"</div>"
                        f"<div style='display:flex; gap:18px; flex-wrap:wrap; font-size:12.5px; color:#334155; margin-bottom:6px;'>"
                        f"<span><b>Mittente:</b> <a href='mailto:{target_user_em}' style='color:#0284c7; font-weight:700;'>{target_user_em}</a></span>"
                        f"<span><b>Ruolo:</b> {sel_tk_adm.get('user_role', 'Utente')}</span>"
                        f"<span><b>Categoria:</b> {sel_tk_adm['category']}</span>"
                        f"</div>"
                        f"</div>"
                    )
                    st.html(card_adm_html)

                    # Gestione cambio stato del ticket
                    col_st1, col_st2 = st.columns([2, 2])
                    with col_st1:
                        stati_possibili = ["Aperta", "In Lavorazione", "Risolta", "Chiusa"]
                        curr_st_idx = stati_possibili.index(sel_tk_adm.get("status", "Aperta")) if sel_tk_adm.get("status") in stati_possibili else 0
                        nuovo_stato = st.selectbox(
                            "Aggiorna Stato della Segnalazione:",
                            stati_possibili,
                            index=curr_st_idx,
                            key=f"st_sel_{sel_tk_adm['id']}"
                        )
                        if nuovo_stato != sel_tk_adm.get("status"):
                            update_status(sel_tk_adm['id'], nuovo_stato)
                            st.success(f"Stato aggiornato a: {nuovo_stato}")
                            st.rerun()

                    with col_st2:
                        # Link mailto per scrivere all'utente via email
                        import urllib.parse
                        subj_mail = urllib.parse.quote(f"[M0V3 Support {sel_tk_adm['id']}] {sel_tk_adm['subject']}")
                        body_mail = urllib.parse.quote(f"Gentile utente,\n\nin merito alla tua segnalazione {sel_tk_adm['id']} ('{sel_tk_adm['subject']}')...\n\nCordiali saluti,\nTeam M0V3 Analytics")
                        mailto_user_url = f"mailto:{sel_tk_adm['user_email']}?subject={subj_mail}&body={body_mail}"
                        st.markdown(
                            f"<div style='padding-top:28px;'>"
                            f"<a href='{mailto_user_url}' target='_blank' style='background:#f1f5f9; color:#0f172a; border:1px solid #cbd5e1; padding:8px 14px; border-radius:6px; font-size:12px; font-weight:800; text-decoration:none; display:inline-flex; align-items:center; gap:6px;'><i class='bi bi-envelope-at'></i> Scrivi email a {sel_tk_adm['user_email']}</a>"
                            f"</div>",
                            unsafe_allow_html=True
                        )

                    # Mostra allegato se presente
                    if sel_tk_adm.get("attachment_path") and os.path.exists(sel_tk_adm["attachment_path"]):
                        att_path_adm = sel_tk_adm["attachment_path"]
                        att_name_adm = sel_tk_adm.get("attachment_name", os.path.basename(att_path_adm))
                        st.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)
                        st.caption(f"Allegato caricato dall'utente: **{att_name_adm}**")
                        with open(att_path_adm, "rb") as f_adm:
                            st.download_button(
                                f"Scarica {att_name_adm}",
                                data=f_adm.read(),
                                file_name=att_name_adm,
                                key=f"adm_dl_{sel_tk_adm['id']}"
                            )
                        ext_adm = os.path.splitext(att_name_adm)[1].lower()
                        if ext_adm in [".png", ".jpg", ".jpeg"]:
                            st.image(att_path_adm, caption=att_name_adm, width=420)

                    # Cronologia Messaggi & Chat con l'Utente
                    st.markdown(
                        f"<div style='font-size:13.5px; font-weight:800; color:#0f172a; margin-top:20px; margin-bottom:10px;'><i class='bi bi-chat-left-dots-fill' style='color:#0284c7; margin-right:6px;'></i>Comunicazione Diretta con l'Utente ({sel_tk_adm['user_email']})</div>",
                        unsafe_allow_html=True
                    )

                    messages_adm = sel_tk_adm.get("messages", [])
                    chat_adm_html = "<div style='display:flex; flex-direction:column; gap:12px; margin-bottom:16px;'>"
                    for m in messages_adm:
                        is_adm_msg = (m.get("sender") == "admin")
                        if is_adm_msg:
                            chat_adm_html += (
                                f"<div style='align-self:flex-end; max-width:82%; background:#1e293b; color:#ffffff; padding:12px 16px; border-radius:12px 12px 2px 12px; box-shadow:0 2px 6px rgba(0,0,0,0.06); font-family:\"Inter\",sans-serif;'>"
                                f"<div style='display:flex; justify-content:flex-end; align-items:center; gap:8px; margin-bottom:4px;'>"
                                f"<span style='font-size:11px; color:#94a3b8;'>{m.get('sender_email', 'Super-Admin')} · {m.get('timestamp', '')}</span>"
                                f"<span style='background:#0284c7; color:#ffffff; font-size:9.5px; font-weight:800; padding:2px 6px; border-radius:4px; text-transform:uppercase;'>TU (ADMIN)</span>"
                                f"</div>"
                                f"<div style='font-size:13px; line-height:1.45; white-space:pre-wrap;'>{m.get('text', '')}</div>"
                                f"</div>"
                            )
                        else:
                            chat_adm_html += (
                                f"<div style='align-self:flex-start; max-width:82%; background:#f0f9ff; color:#0f172a; border:1px solid #bae6fd; padding:12px 16px; border-radius:12px 12px 12px 2px; box-shadow:0 2px 6px rgba(2,132,199,0.05); font-family:\"Inter\",sans-serif;'>"
                                f"<div style='display:flex; align-items:center; gap:8px; margin-bottom:4px;'>"
                                f"<span style='background:#e2e8f0; color:#334155; font-size:9.5px; font-weight:800; padding:2px 6px; border-radius:4px;'>UTENTE</span>"
                                f"<span style='font-size:11px; color:#64748b;'>{m.get('sender_email', sel_tk_adm['user_email'])} · {m.get('timestamp', '')}</span>"
                                f"</div>"
                                f"<div style='font-size:13px; line-height:1.45; white-space:pre-wrap;'>{m.get('text', '')}</div>"
                                f"</div>"
                            )
                    chat_adm_html += "</div>"
                    st.html(chat_adm_html)

                    # Form per rispondere all'utente
                    with st.form(f"form_admin_reply_{sel_tk_adm['id']}", clear_on_submit=True):
                        adm_reply_text = st.text_area(
                            f"Invia una risposta diretta all'utente ({sel_tk_adm['user_email']}):",
                            height=95,
                            placeholder="Scrivi qui la risposta o le istruzioni da inviare all'utente..."
                        )
                        c_ab1, c_ab2 = st.columns([3, 1])
                        with c_ab2:
                            btn_send_adm_rep = st.form_submit_button(
                                "Invia Risposta all'Utente",
                                type="primary",
                                use_container_width=True
                            )

                        if btn_send_adm_rep and adm_reply_text:
                            curr_admin_email = st.session_state.get('user', {}).email if hasattr(st.session_state.get('user', None), 'email') else "superadmin@mov3.com"
                            add_reply(sel_tk_adm['id'], "Super-Admin", curr_admin_email, adm_reply_text)
                            st.success("Risposta inviata all'utente con successo!")
                            st.rerun()

