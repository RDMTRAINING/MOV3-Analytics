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
    tr,
    render_page_header,
    render_print_header,
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
    slugify_name,
)
from pdf_generator import (
    crea_pdf_m0v3,
    crea_pdf_sessione_m0v3,
    crea_pdf_weekly_m0v3,
    crea_pdf_storico_m0v3,
    crea_pdf_medie_m0v3,
)

def render_profilo(t):
    render_page_header(
        tr("Profilo Personale & Gestione Account", "Personal Profile & Account Management"),
        tr("Gestisci le tue credenziali di accesso, verifica i consensi Privacy (GDPR) ed esporta i tuoi dati storici.", "Manage your credentials, verify Privacy (GDPR) consents, and export your historical dataset."),
        "ACCOUNT & PRIVACY HUB"
    )

    user = st.session_state.get('user')
    if not user:
        st.warning("Nessun utente autenticato.")
        return

    uid = user.id
    email_utente = user.email
    ruolo_utente = st.session_state.get('role', 'Atleta')
    privacy_attiva = st.session_state.get('privacy_accettata', False)

    # Dati DB e statistiche personali
    df_storico = load_local_database()
    df_user = df_storico[df_storico['Uploader_Email'] == email_utente].copy() if not df_storico.empty and 'Uploader_Email' in df_storico.columns else pd.DataFrame()
    tot_sess_user = len(df_user)
    tot_reali = len(df_user[df_user['Dato_Simulato'] == False]) if not df_user.empty and 'Dato_Simulato' in df_user.columns else 0
    tot_sim = tot_sess_user - tot_reali

    # Atleti associati
    if ruolo_utente == 'Super-Admin':
        atleti_list = get_tutti_gli_atleti()
        lbl_atleti_sub = tr(f"Accesso Super-Admin ({len(atleti_list)} atleti complessivi)", f"Super-Admin Full Access ({len(atleti_list)} total athletes)")
    else:
        atleti_list = get_atleti_associati(uid)
        lbl_atleti_sub = tr(f"{len(atleti_list)} atleti assegnati al profilo", f"{len(atleti_list)} athletes linked to profile")

    # Stato Privacy badge
    terms_acc_date = st.session_state.get('terms_accepted_at', '')
    if not terms_acc_date:
        try:
            p_res = supabase.table('profili').select('*').eq('id', uid).execute()
            if p_res.data:
                terms_acc_date = p_res.data[0].get('terms_accepted_at', '')
        except Exception:
            pass

    if privacy_attiva or st.session_state.get('has_accepted_terms'):
        priv_badge_bg, priv_badge_fg = "#dcfce7", "#166534"
        date_str = f" il {terms_acc_date}" if terms_acc_date else ""
        priv_badge_txt = f"Termini IP & GDPR Accettati{date_str}"
    else:
        priv_badge_bg, priv_badge_fg = "#fee2e2", "#991b1b"
        priv_badge_txt = tr("[!] In attesa di primo accesso", "[!] Pending First Login")

    # 1. CARD ANAGRAFICA & STATO PROFILO (STILE EXECUTIVE)
    col_k1, col_k2, col_k3, col_k4 = st.columns(4)
    with col_k1:
        st.markdown(
            card_kpi(
                tr("Email Account", "Account Email"),
                f"<div style='font-size:15px; font-weight:800; color:#0f172a; word-break:break-all;'>{email_utente}</div>",
                f"ID: {uid[:8]}...{uid[-4:]}",
                "#0ea5e9"
            ),
            unsafe_allow_html=True
        )
    with col_k2:
        st.markdown(
            card_kpi(
                tr("Ruolo di Sistema", "System Role"),
                f"<span style='font-size:22px; font-weight:900; color:#0f172a;'>{ruolo_utente}</span>",
                lbl_atleti_sub,
                "#10b981"
            ),
            unsafe_allow_html=True
        )
    with col_k3:
        st.markdown(
            card_kpi(
                tr("Conformità GDPR", "GDPR Compliance"),
                f"<span style='background:{priv_badge_bg}; color:{priv_badge_fg}; font-size:12px; font-weight:800; padding:4px 8px; border-radius:6px; display:inline-block;'>{priv_badge_txt}</span>",
                tr("Informativa Trattamento Dati Personali", "Personal Data Protection Policy"),
                "#16a34a" if privacy_attiva else "#dc2626"
            ),
            unsafe_allow_html=True
        )
    with col_k4:
        st.markdown(
            card_kpi(
                tr("Sessioni Caricate", "Uploaded Sessions"),
                f"<span style='font-size:24px; font-weight:900; color:#0f172a;'>{tot_sess_user}</span>",
                f"{tot_reali} {tr('Reali', 'Real')} · {tot_sim} {tr('Simulate', 'Simulated')}",
                "#8b5cf6"
            ),
            unsafe_allow_html=True
        )

    st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)

    # 2. SEZIONE ATLETI ASSEGNATI
    with st.container(border=True):
        st.markdown(f"#### <i class='bi bi-people-fill'></i> {tr('Atleti Associati al Tuo Profilo', 'Athletes Linked to Your Profile')}", unsafe_allow_html=True)
        if atleti_list:
            pills_html = " ".join([
                f"<span style='background:#f1f5f9; color:#0f172a; border:1px solid #cbd5e1; padding:5px 12px; border-radius:20px; font-size:12px; font-weight:700; display:inline-block; margin:3px 4px;'>{ath}</span>"
                for ath in atleti_list
            ])
            st.markdown(f"<div style='margin-top:6px;'>{pills_html}</div>", unsafe_allow_html=True)
        else:
            st.info(tr("Nessun atleta attualmente collegato. Contatta l'amministratore di sistema per richiedere l'assegnazione.", "No athletes currently linked. Contact system admin to request assignment."))

    st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)

    col_left, col_right = st.columns(2, gap="large")

    # 3. COLONNA SINISTRA: SICUREZZA & CAMBIO PASSWORD
    with col_left:
        with st.container(border=True):
            st.markdown(f"### <i class='bi bi-shield-lock'></i> {t['prof_title']}", unsafe_allow_html=True)
            st.caption(t['prof_info'])

            with st.form("cambio_password_form"):
                nuova_pw = st.text_input(t['new_pwd'], type="password", help=tr("Minimo 6 caratteri.", "Minimum 6 characters."))
                conferma_pw = st.text_input(t['conf_pwd'], type="password")
                
                submit_pw = st.form_submit_button(t['save_pwd'], type="primary", use_container_width=True)
                if submit_pw:
                    if len(nuova_pw) < 6:
                        st.error(t['err_pwd_len'])
                    elif nuova_pw != conferma_pw:
                        st.error(t['err_pwd_match'])
                    else:
                        try:
                            supabase.auth.update_user({"password": nuova_pw})
                            st.success(t['succ_pwd'])
                        except Exception as e:
                            st.error(f"Errore durante l'aggiornamento password: {e}")

    # 4. COLONNA DESTRA: PORTABILITÀ DEI DATI (GDPR ART. 20)
    with col_right:
        with st.container(border=True):
            st.markdown(f"### <i class='bi bi-box-arrow-up-right'></i> {tr('Portabilità dei Dati (GDPR Art. 20)', 'Data Portability (GDPR Art. 20)')}", unsafe_allow_html=True)
            st.caption(tr(
                "Ai sensi del GDPR, hai il diritto di esportare in qualsiasi momento l'intero archivio delle tue sessioni con tutti i parametri M0V3 calcolati.",
                "Under GDPR, you have the right to export your complete session dataset with all computed M0V3 parameters at any time."
            ))

            if not df_user.empty:
                csv_bytes = df_user.to_csv(index=False).encode('utf-8-sig')
                filename_export = f"M0V3_Dataset_{slugify_name(email_utente)}.csv"
                st.download_button(
                    label=tr(f"Scarica il Mio Archivio Dati ({tot_sess_user} sessioni .csv)", f"Download My Dataset ({tot_sess_user} sessions .csv)"),
                    data=csv_bytes,
                    file_name=filename_export,
                    mime="text/csv",
                    type="primary",
                    use_container_width=True,
                    key="btn_download_personal_dataset"
                )
            else:
                st.info(tr("Nessun dato registrato a tuo nome nel database storico.", "No recorded data under your account in the historical database."))

    st.markdown("<div style='margin-top: 20px;'></div>", unsafe_allow_html=True)

    # 5. SEZIONE INFORMATIVA PRIVACY & GESTIONE CONSENSO
    with st.container(border=True):
        st.markdown(f"### <i class='bi bi-file-earmark-lock'></i> {tr('Informativa Privacy & Gestione Consenso (GDPR)', 'Privacy Policy & Consent Management (GDPR)')}", unsafe_allow_html=True)
        c_doc1, c_doc2 = st.columns([1.5, 1])
        with c_doc1:
            st.markdown(tr(
                "M0V3 tratta i dati biometrici e prestazionali nel pieno rispetto del Regolamento UE 2016/679 (GDPR). Puoi consultare l'informativa o revocare il consenso al trattamento.",
                "M0V3 processes performance and tracking data in strict compliance with EU Regulation 2016/679 (GDPR). You can review the policy or revoke your processing consent."
            ))
        with c_doc2:
            doc_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "Atto_Privacy_IP_MOV3_v2.pdf")
            pdf_bytes = None
            if os.path.exists(doc_path):
                try:
                    with open(doc_path, "rb") as f_pdf:
                        pdf_bytes = f_pdf.read()
                except Exception:
                    pdf_bytes = None
            if not pdf_bytes:
                try:
                    import pdf_generator
                    pdf_bytes = pdf_generator.genera_pdf_informativa_privacy_mov3(user_email=email_utente, data_ora=terms_acc_date)
                except Exception:
                    pdf_bytes = None

            if pdf_bytes:
                st.download_button(
                    label=tr("Scarica Informativa Privacy & IP (PDF)", "Download Privacy & IP Policy (PDF)"),
                    data=pdf_bytes,
                    file_name="Atto_Privacy_IP_MOV3_v2.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                    key="btn_download_policy_profile_pdf"
                )
            else:
                privacy_doc_path = "INFORMATIVA SUL TRATTAMENTO DEI DATI PERSONALI.docx"
                if os.path.exists(privacy_doc_path):
                    with open(privacy_doc_path, "rb") as f_doc:
                        st.download_button(
                            label=tr("Scarica Informativa Privacy (.docx)", "Download Privacy Policy (.docx)"),
                            data=f_doc.read(),
                            file_name="Informativa_Privacy_M0V3.docx",
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            use_container_width=True,
                            key="btn_download_policy_profile"
                        )

        st.divider()

        # Switch revoca consenso
        col_rev1, col_rev2 = st.columns([2, 1])
        with col_rev1:
            st.markdown(f"**{tr('Stato Attuale del Consenso:', 'Current Consent Status:')}**")
            if privacy_attiva or st.session_state.get('has_accepted_terms'):
                st.markdown(f"<span style='color:#166534; font-weight:700;'>{tr('Termini IP & GDPR accettati e attivi', 'IP & GDPR Terms active and accepted')}{f' ({terms_acc_date})' if terms_acc_date else ''}.</span>", unsafe_allow_html=True)
            else:
                st.markdown(f"<span style='color:#dc2626; font-weight:700;'>{tr('Consenso revocato o in attesa di primo accesso.', 'Consent revoked or pending first login.')}</span>", unsafe_allow_html=True)
        with col_rev2:
            if privacy_attiva or st.session_state.get('has_accepted_terms'):
                if st.button(tr("Revoca Consenso Privacy", "Revoke Privacy Consent"), type="secondary", use_container_width=True):
                    try:
                        upd_rev = {
                            "privacy_accettata": False,
                            "has_accepted_terms": False,
                            "terms_accepted_at": None
                        }
                        try:
                            supabase.table('profili').update(upd_rev).eq('id', uid).execute()
                        except Exception:
                            supabase.table('profili').update({"privacy_accettata": False}).eq('id', uid).execute()
                        st.session_state['privacy_accettata'] = False
                        st.session_state['has_accepted_terms'] = False
                        st.session_state['terms_accepted_at'] = ''
                        st.warning(tr("Consenso revocato. Verrai reindirizzato alla schermata di accettazione.", "Consent revoked. You will be redirected to the acceptance screen."))
                        st.rerun()
                    except Exception as e:
                        st.error(f"Errore revoca consenso: {e}")

    st.markdown("<div style='margin-top: 20px;'></div>", unsafe_allow_html=True)

    # 6. SEZIONE ELIMINAZIONE ACCOUNT E DIRITTO ALL'OBLIO (GDPR ART. 17)
    with st.expander(f"{t['privacy_title']} (Diritto all'Oblio / GDPR Art. 17)", expanded=False):
        st.error(t['privacy_warn'])
        st.markdown(tr(
            "La richiesta di eliminazione comporta la rimozione irreversibile di: credenziali di autenticazione, profilo utente, associazioni con atleti, moduli report abilitati e regole di tracciato CSV.",
            "Deletion irrevocably removes: authentication credentials, profile data, athlete associations, report modules, and CSV mapping rules."
        ))
        conferma_oblio = st.checkbox(t['privacy_check'], key="chk_oblio")
        if st.button(t['del_acc_btn'], type="primary", disabled=not conferma_oblio):
            try:
                supabase_admin.table('associazioni').delete().eq('profilo_id', uid).execute()
                supabase_admin.table('moduli_report').delete().eq('profilo_id', uid).execute()
                supabase_admin.table('mappatura_csv').delete().eq('profilo_id', uid).execute()
                supabase_admin.table('profili').delete().eq('id', uid).execute()
                supabase_admin.auth.admin.delete_user(uid)
                supabase.auth.sign_out()
                st.session_state['user'] = None
                st.session_state['role'] = None
                st.session_state['privacy_accettata'] = False
                st.success("Account eliminato con successo. Arrivederci.")
                st.rerun()
            except Exception as e:
                st.error(f"Errore durante l'eliminazione dell'account: {e}")
