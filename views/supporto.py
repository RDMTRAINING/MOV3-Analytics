import os
import json
import secrets
from datetime import datetime
import urllib.parse
import streamlit as st

from config import (
    SUPPORT_EMAIL,
    tr,
    render_page_header,
)
from utils import card_kpi

TICKETS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data_supporto")
TICKETS_FILE = os.path.join(TICKETS_DIR, "tickets.json")
ATTACHMENTS_DIR = os.path.join(TICKETS_DIR, "allegati")

def _ensure_storage():
    os.makedirs(TICKETS_DIR, exist_ok=True)
    os.makedirs(ATTACHMENTS_DIR, exist_ok=True)
    if not os.path.exists(TICKETS_FILE):
        with open(TICKETS_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)

def load_all_tickets():
    _ensure_storage()
    try:
        with open(TICKETS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        st.error(f"Errore caricamento ticket: {e}")
        return []

def save_all_tickets(tickets):
    _ensure_storage()
    try:
        with open(TICKETS_FILE, "w", encoding="utf-8") as f:
            json.dump(tickets, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        st.error(f"Errore salvataggio ticket: {e}")
        return False

def create_ticket(user_email, user_role, subject, category, priority, description, uploaded_file=None):
    tickets = load_all_tickets()
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
    now_id = datetime.now().strftime("%Y%m%d")
    ticket_id = f"TK-{now_id}-{secrets.token_hex(2).upper()}"
    
    attachment_name = None
    attachment_path = None
    if uploaded_file is not None:
        safe_name = f"{ticket_id}_{uploaded_file.name}"
        save_path = os.path.join(ATTACHMENTS_DIR, safe_name)
        with open(save_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        attachment_name = uploaded_file.name
        attachment_path = save_path

    new_ticket = {
        "id": ticket_id,
        "created_at": now_str,
        "user_email": user_email,
        "user_role": user_role,
        "subject": subject.strip(),
        "category": category,
        "priority": priority,
        "status": "Aperta",
        "description": description.strip(),
        "attachment_name": attachment_name,
        "attachment_path": attachment_path,
        "messages": [
            {
                "id": f"msg-{secrets.token_hex(3)}",
                "sender": "user",
                "sender_email": user_email,
                "sender_role": user_role,
                "timestamp": now_str,
                "text": description.strip()
            }
        ]
    }
    
    tickets.insert(0, new_ticket)
    save_all_tickets(tickets)
    return new_ticket

def add_reply(ticket_id, sender_role, sender_email, text):
    tickets = load_all_tickets()
    for t in tickets:
        if t["id"] == ticket_id:
            now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
            t["messages"].append({
                "id": f"msg-{secrets.token_hex(3)}",
                "sender": "admin" if sender_role == "Super-Admin" else "user",
                "sender_email": sender_email,
                "sender_role": sender_role,
                "timestamp": now_str,
                "text": text.strip()
            })
            if sender_role == "Super-Admin" and t["status"] == "Aperta":
                t["status"] = "In Lavorazione"
            save_all_tickets(tickets)
            return True
    return False

def update_status(ticket_id, new_status):
    tickets = load_all_tickets()
    for t in tickets:
        if t["id"] == ticket_id:
            t["status"] = new_status
            save_all_tickets(tickets)
            return True
    return False

def build_mailto_url(ticket_id, subject, user_email, description):
    body = (
        f"SEGNALAZIONE MOV3 ANALYTICS\n"
        f"ID Ticket: {ticket_id}\n"
        f"Utente: {user_email}\n"
        f"Oggetto: {subject}\n\n"
        f"Descrizione del problema o richiesta:\n"
        f"{description}\n\n"
        f"--- Inviato tramite M0V3 Analytics Support Help Desk ---"
    )
    subject_enc = urllib.parse.quote(f"[M0V3 Support {ticket_id}] {subject}")
    body_enc = urllib.parse.quote(body)
    return f"mailto:{SUPPORT_EMAIL}?subject={subject_enc}&body={body_enc}"


def get_status_badge(status):
    if status == "Aperta":
        return f"<span style='background:#e0f2fe; color:#0369a1; padding:3px 10px; border-radius:6px; font-size:11.5px; font-weight:800; border:1px solid #bae6fd;'>{tr('Aperta', 'Open')}</span>"
    elif status == "In Lavorazione":
        return f"<span style='background:#fef3c7; color:#b45309; padding:3px 10px; border-radius:6px; font-size:11.5px; font-weight:800; border:1px solid #fde68a;'>{tr('In Lavorazione', 'In Progress')}</span>"
    elif status == "Risolta":
        return f"<span style='background:#dcfce7; color:#15803d; padding:3px 10px; border-radius:6px; font-size:11.5px; font-weight:800; border:1px solid #bbf7d0;'>{tr('Risolta', 'Resolved')}</span>"
    else:
        return f"<span style='background:#f1f5f9; color:#475569; padding:3px 10px; border-radius:6px; font-size:11.5px; font-weight:800; border:1px solid #e2e8f0;'>{tr('Chiusa', 'Closed')}</span>"

def get_priority_badge(prio):
    if prio == "Urgente":
        return f"<span style='background:#fee2e2; color:#b91c1c; padding:2px 8px; border-radius:4px; font-size:11px; font-weight:800;'>{tr('URGENTE', 'URGENT')}</span>"
    elif prio == "Alta":
        return f"<span style='background:#ffedd5; color:#c2410c; padding:2px 8px; border-radius:4px; font-size:11px; font-weight:800;'>{tr('ALTA', 'HIGH')}</span>"
    elif prio == "Bassa":
        return f"<span style='background:#f1f5f9; color:#64748b; padding:2px 8px; border-radius:4px; font-size:11px; font-weight:700;'>{tr('BASSA', 'LOW')}</span>"
    else:
        return f"<span style='background:#f0fdf4; color:#166534; padding:2px 8px; border-radius:4px; font-size:11px; font-weight:700;'>{tr('NORMALE', 'NORMAL')}</span>"


def render_supporto(t):
    render_page_header(
        tr("Supporto & Assistenza", "Support & Help Desk"),
        tr("Invia segnalazioni tecniche, richiedi assistenza o comunica direttamente con il team Super-Admin.", "Submit technical reports, request assistance or communicate directly with the Super-Admin team."),
        "HELP DESK"
    )

    curr_user = st.session_state.get('user')
    curr_email = curr_user.email if (curr_user and hasattr(curr_user, 'email')) else "utente@mov3.com"
    curr_role = st.session_state.get('role', 'Utente')

    tab_nuova, tab_miei = st.tabs([
        tr("Invia Nuova Segnalazione", "Submit New Ticket"),
        tr("Le Mie Segnalazioni & Chat", "My Tickets & Direct Chat")
    ])

    # -------------------------------------------------------------------------
    # TAB 1: FORM NUOVA SEGNALAZIONE
    # -------------------------------------------------------------------------
    with tab_nuova:
        st.markdown(
            f"<div style='background:linear-gradient(135deg, #0f172a 0%, #1e293b 100%); padding:16px 20px; border-radius:12px; margin-bottom:20px; border-left:4px solid #0284c7; color:#f8fafc; font-family:\"Inter\",sans-serif;'>"
            f"<div style='font-size:14px; font-weight:800; text-transform:uppercase; letter-spacing:0.05em; color:#38bdf8;'><i class='bi bi-headset' style='margin-right:8px;'></i>{tr('Centro Assistenza e Segnalazioni M0V3', 'M0V3 Support Center')}</div>"
            f"<div style='font-size:12.5px; color:#cbd5e1; margin-top:4px;'>{tr('Compila il form sottostante per inviare un ticket. Le segnalazioni vengono recapitate direttamente a', 'Fill out the form below to submit a ticket. Reports are delivered directly to')} <b style='color:#ffffff;'>{SUPPORT_EMAIL}</b> {tr('e prese in carico dal Super-Admin.', 'and handled by Super-Admin.')}</div>"
            f"</div>",
            unsafe_allow_html=True
        )

        with st.form("form_nuovo_ticket", clear_on_submit=True):
            col_c1, col_c2 = st.columns(2)
            with col_c1:
                categoria = st.selectbox(
                    tr("Categoria della Segnalazione", "Ticket Category"),
                    [
                        tr("Bug / Errore Sistema", "Bug / System Error"),
                        tr("Problema Caricamento / GPS", "Upload / GPS Issue"),
                        tr("Suggerimento / Nuova Funzione", "Feature Request / Suggestion"),
                        tr("Assistenza Account / Accesso", "Account / Access Assistance"),
                        tr("Altro", "Other")
                    ]
                )
            with col_c2:
                priorita = st.selectbox(
                    tr("Priorità", "Priority"),
                    [
                        tr("Normale", "Normal"),
                        tr("Alta", "High"),
                        tr("Urgente", "Urgent"),
                        tr("Bassa", "Low")
                    ]
                )

            oggetto = st.text_input(
                tr("Oggetto della Segnalazione *", "Subject *"),
                placeholder=tr("Es. Errore nel calcolo ACWR o richiesta nuovo campo...", "E.g. Error in ACWR calculation or request new field...")
            )

            descrizione = st.text_area(
                tr("Descrizione Dettagliata *", "Detailed Description *"),
                height=140,
                placeholder=tr("Descrivi dettagliatamente cosa è successo, i passaggi per riprodurre il problema o la tua richiesta...", "Describe in detail what happened, steps to reproduce or your request...")
            )

            allegato = st.file_uploader(
                tr("Allegato / Screenshot opzionale (PNG, JPG, CSV, PDF, LOG)", "Optional Attachment / Screenshot (PNG, JPG, CSV, PDF, LOG)"),
                type=["png", "jpg", "jpeg", "csv", "txt", "pdf", "log"],
                help=tr("Aggiungi uno screenshot per facilitare l'analisi del problema.", "Attach a screenshot to help analyze the issue.")
            )

            st.caption(f"✓ {tr('Verranno inviati automaticamente:', 'Will be sent automatically:')} **{curr_email}** ({curr_role}) · {datetime.now().strftime('%d/%m/%Y %H:%M')}")

            btn_invia = st.form_submit_button(
                tr("Invia Segnalazione al Team", "Submit Ticket to Team"),
                type="primary",
                use_container_width=True
            )

            if btn_invia:
                if not oggetto or not descrizione:
                    st.error(tr("Compila i campi obbligatori (Oggetto e Descrizione).", "Please fill in all required fields (Subject and Description)."))
                else:
                    new_t = create_ticket(
                        user_email=curr_email,
                        user_role=curr_role,
                        subject=oggetto,
                        category=categoria,
                        priority=priorita,
                        description=descrizione,
                        uploaded_file=allegato
                    )
                    st.success(f"✓ {tr('Segnalazione inviata con successo!', 'Ticket successfully submitted!')} ID: **{new_t['id']}**")
                    
                    # Callout con link rapido mailto
                    mailto_link = build_mailto_url(new_t['id'], new_t['subject'], curr_email, new_t['description'])
                    st.markdown(
                        f"<div style='background:#f0f9ff; border:1px solid #bae6fd; border-radius:8px; padding:12px 16px; margin-top:10px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;'>"
                        f"<span style='color:#0369a1; font-size:12.5px; font-weight:600;'><i class='bi bi-info-circle-fill' style='color:#0284c7; margin-right:6px;'></i>{tr('Il ticket è registrato nel sistema. Puoi anche inviare una notifica email diretta con 1 click:', 'The ticket is registered. You can also send a direct email notification with 1 click:')}</span>"
                        f"<a href='{mailto_link}' target='_blank' style='background:#0284c7; color:#ffffff; padding:6px 14px; border-radius:6px; font-size:12px; font-weight:800; text-decoration:none; display:inline-flex; align-items:center; gap:6px;'><i class='bi bi-envelope-fill'></i> Notifica Email a {SUPPORT_EMAIL}</a>"
                        f"</div>",
                        unsafe_allow_html=True
                    )

    # -------------------------------------------------------------------------
    # TAB 2: STORICO TICKET & CHAT DIRETTA CON ADMIN
    # -------------------------------------------------------------------------
    with tab_miei:
        all_tickets = load_all_tickets()
        # Filtra i ticket dell'utente corrente (se Super-Admin vede tutti, altrimenti solo i propri)
        if curr_role == "Super-Admin":
            miei_tickets = all_tickets
        else:
            miei_tickets = [tk for tk in all_tickets if tk.get("user_email", "").lower() == curr_email.lower()]

        if not miei_tickets:
            st.info(tr("Nessuna segnalazione aperta registrata a tuo nome. Per inviarne una, usa la scheda 'Invia Nuova Segnalazione'.", "No open tickets found under your account. To submit one, use the 'Submit New Ticket' tab."))
        else:
            st.markdown(
                f"<div style='font-size:13px; font-weight:700; color:#475569; margin-bottom:12px;'>"
                f"{tr('Hai', 'You have')} <b style='color:#0284c7;'>{len(miei_tickets)}</b> {tr('segnalazioni attive. Seleziona un ticket per visualizzare la conversazione diretta con il Super-Admin.', 'active tickets. Select a ticket to view the direct chat with the Super-Admin.')}"
                f"</div>",
                unsafe_allow_html=True
            )

            dict_options = {
                tk["id"]: f"[{tk['status'].upper()}] {tk['id']} — {tk['subject'][:45]}... ({tk['created_at']})"
                for tk in miei_tickets
            }
            sel_ticket_id = st.selectbox(
                tr("Seleziona Segnalazione da consultare:", "Select Ticket to view:"),
                options=list(dict_options.keys()),
                format_func=lambda x: dict_options[x],
                key="sel_user_ticket"
            )

            sel_tk = next((tk for tk in miei_tickets if tk["id"] == sel_ticket_id), None)
            if sel_tk:
                st.markdown("<div style='margin-top:14px;'></div>", unsafe_allow_html=True)
                
                # Card riassuntiva del ticket
                badge_st = get_status_badge(sel_tk.get("status", "Aperta"))
                badge_pr = get_priority_badge(sel_tk.get("priority", "Normale"))
                
                card_tk_html = (
                    f"<div style='background:#ffffff; border:1px solid #e2e8f0; border-radius:12px; padding:16px 20px; box-shadow:0 2px 8px -2px rgba(15,23,42,0.06); margin-bottom:16px; font-family:\"Inter\",sans-serif;'>"
                    f"<div style='display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; border-bottom:1px solid #f1f5f9; padding-bottom:10px; margin-bottom:10px;'>"
                    f"<div>"
                    f"<span style='font-size:16px; font-weight:900; color:#0f172a;'>{sel_tk['subject']}</span>"
                    f"<div style='font-size:11.5px; color:#64748b; margin-top:2px;'>ID: <b style='color:#0284c7;'>{sel_tk['id']}</b> · Inviato il: {sel_tk['created_at']}</div>"
                    f"</div>"
                    f"<div style='display:flex; align-items:center; gap:8px;'>{badge_pr} {badge_st}</div>"
                    f"</div>"
                    f"<div style='display:flex; gap:16px; flex-wrap:wrap; font-size:12px; color:#475569; margin-bottom:10px;'>"
                    f"<span><b>{tr('Categoria:', 'Category:')}</b> {sel_tk['category']}</span>"
                    f"<span><b>{tr('Destinatario Mail:', 'Recipient Email:')}</b> <a href='mailto:{SUPPORT_EMAIL}' style='color:#0284c7; text-decoration:none;'>{SUPPORT_EMAIL}</a></span>"
                    f"</div>"
                    f"</div>"
                )
                st.html(card_tk_html)

                # Mostra allegato se presente
                if sel_tk.get("attachment_path") and os.path.exists(sel_tk["attachment_path"]):
                    att_path = sel_tk["attachment_path"]
                    att_name = sel_tk.get("attachment_name", os.path.basename(att_path))
                    col_att1, col_att2 = st.columns([3, 1])
                    with col_att1:
                        st.caption(f"{tr('Allegato disponibile:', 'Attachment available:')} **{att_name}**")
                    with col_att2:
                        with open(att_path, "rb") as f:
                            st.download_button(
                                f"Scarica {att_name}",
                                data=f.read(),
                                file_name=att_name,
                                key=f"dl_att_{sel_tk['id']}",
                                use_container_width=True
                            )
                    # Se è un'immagine, mostra anteprima
                    ext = os.path.splitext(att_name)[1].lower()
                    if ext in [".png", ".jpg", ".jpeg"]:
                        st.image(att_path, caption=att_name, width=420)

                # -------------------------------------------------------------
                # CHAT DIRETTA: MESSAGGI SCAMBIATI
                # -------------------------------------------------------------
                st.markdown(
                    f"<div style='font-size:13.5px; font-weight:800; color:#0f172a; margin-top:16px; margin-bottom:10px;'><i class='bi bi-chat-left-text-fill' style='color:#0284c7; margin-right:6px;'></i>{tr('Conversazione Diretta con il Supporto Super-Admin', 'Direct Conversation with Super-Admin Support')}</div>",
                    unsafe_allow_html=True
                )

                messages = sel_tk.get("messages", [])
                chat_html = "<div style='display:flex; flex-direction:column; gap:12px; margin-bottom:16px;'>"
                for msg in messages:
                    is_admin = (msg.get("sender") == "admin")
                    if is_admin:
                        # Messaggio Admin (allineato a sinistra, stile scuro/blu executive)
                        chat_html += (
                            f"<div style='align-self:flex-start; max-width:82%; background:#1e293b; color:#ffffff; padding:12px 16px; border-radius:12px 12px 12px 2px; box-shadow:0 2px 6px rgba(0,0,0,0.06); font-family:\"Inter\",sans-serif;'>"
                            f"<div style='display:flex; align-items:center; gap:8px; margin-bottom:4px;'>"
                            f"<span style='background:#0284c7; color:#ffffff; font-size:9.5px; font-weight:800; padding:2px 6px; border-radius:4px; text-transform:uppercase;'>SUPER-ADMIN</span>"
                            f"<span style='font-size:11px; color:#94a3b8;'>{msg.get('sender_email', 'Support')} · {msg.get('timestamp', '')}</span>"
                            f"</div>"
                            f"<div style='font-size:13px; line-height:1.45; white-space:pre-wrap;'>{msg.get('text', '')}</div>"
                            f"</div>"
                        )
                    else:
                        # Messaggio Utente (allineato a destra, stile azzurro chiaro)
                        chat_html += (
                            f"<div style='align-self:flex-end; max-width:82%; background:#f0f9ff; color:#0f172a; border:1px solid #bae6fd; padding:12px 16px; border-radius:12px 12px 2px 12px; box-shadow:0 2px 6px rgba(2,132,199,0.05); font-family:\"Inter\",sans-serif;'>"
                            f"<div style='display:flex; justify-content:flex-end; align-items:center; gap:8px; margin-bottom:4px;'>"
                            f"<span style='font-size:11px; color:#64748b;'>{msg.get('sender_email', curr_email)} · {msg.get('timestamp', '')}</span>"
                            f"<span style='background:#e2e8f0; color:#334155; font-size:9.5px; font-weight:800; padding:2px 6px; border-radius:4px;'>TU</span>"
                            f"</div>"
                            f"<div style='font-size:13px; line-height:1.45; white-space:pre-wrap;'>{msg.get('text', '')}</div>"
                            f"</div>"
                        )
                chat_html += "</div>"
                st.html(chat_html)

                # Box per inviare una replica
                with st.form(f"form_reply_{sel_tk['id']}", clear_on_submit=True):
                    rep_input = st.text_area(
                        tr("Scrivi una risposta o aggiornamento:", "Write a reply or update:"),
                        height=85,
                        placeholder=tr("Aggiungi ulteriori dettagli o rispondi all'assistenza...", "Add more details or reply to support...")
                    )
                    c_b1, c_b2 = st.columns([3, 1])
                    with c_b2:
                        btn_send_rep = st.form_submit_button(
                            tr("Invia Risposta", "Send Reply"),
                            type="primary",
                            use_container_width=True
                        )

                    if btn_send_rep and rep_input:
                        add_reply(sel_tk['id'], curr_role, curr_email, rep_input)
                        st.success(tr("Risposta inviata!", "Reply sent!"))
                        st.rerun()
