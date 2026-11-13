# Copyright 2026 Riccardo Di Maio - M0V3 S.r.l. Tutti i diritti riservati.
# Proprietary Sports Science & Clinical Performance Intelligence Architecture.
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import streamlit as st

def get_smtp_config():
    """Recupera la configurazione SMTP e l'URL base dell'app da st.secrets."""
    host = "smtp.gmail.com"
    port = 465
    user = "mov3project26@gmail.com"
    password = ""
    sender_name = "M0V3 Analytics"
    base_url = "https://webapptennisgps.streamlit.app"

    try:
        if "smtp" in st.secrets:
            s_cfg = st.secrets["smtp"]
            host = s_cfg.get("host", host)
            port = int(s_cfg.get("port", port))
            user = s_cfg.get("user", user)
            password = s_cfg.get("password", password)
            sender_name = s_cfg.get("sender_name", sender_name)
        else:
            host = st.secrets.get("SMTP_HOST", host)
            port = int(st.secrets.get("SMTP_PORT", port))
            user = st.secrets.get("SMTP_USER", user)
            password = st.secrets.get("SMTP_PASSWORD", password)
            sender_name = st.secrets.get("SMTP_SENDER_NAME", sender_name)

        if "app" in st.secrets:
            base_url = st.secrets["app"].get("base_url", base_url)
        else:
            base_url = st.secrets.get("APP_BASE_URL", base_url)
    except Exception:
        pass

    return {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "sender_name": sender_name,
        "base_url": base_url.rstrip("/")
    }


def send_smtp_email(to_email, subject, html_content, text_content=None):
    """
    Invia un'email HTML con fallback testuale usando SMTP SSL/TLS.
    Restituisce: (success: bool, message: str)
    """
    cfg = get_smtp_config()

    if not cfg["password"] or cfg["password"].strip() in ("", "INSERISCI_APP_PASSWORD_QUI"):
        return False, "Password SMTP non configurata nei secrets di Streamlit (secrets.toml)."

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{cfg['sender_name']} <{cfg['user']}>"
    msg["To"] = to_email

    if text_content:
        part_text = MIMEText(text_content, "plain", "utf-8")
        msg.attach(part_text)

    part_html = MIMEText(html_content, "html", "utf-8")
    msg.attach(part_html)

    try:
        if cfg["port"] == 465:
            with smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=12) as server:
                server.login(cfg["user"], cfg["password"])
                server.sendmail(cfg["user"], [to_email], msg.as_string())
        else:
            with smtplib.SMTP(cfg["host"], cfg["port"], timeout=12) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(cfg["user"], cfg["password"])
                server.sendmail(cfg["user"], [to_email], msg.as_string())

        return True, "Email inviata con successo!"
    except Exception as e:
        return False, f"Errore durante l'invio dell'email: {str(e)}"


def invia_email_creazione_account(destinatario, password_provvisoria, ruolo="Atleta"):
    """
    Invia l'email ufficiale di benvenuto M0V3 con le credenziali di accesso
    e la specifica esplicita che l'utente potrà cambiare la password dopo l'accesso.
    """
    cfg = get_smtp_config()
    login_url = cfg["base_url"]

    subject = "Benvenuto in M0V3 Analytics — Le tue credenziali di accesso"

    testo_piano = f"""Benvenuto in M0V3 Analytics!

È stato creato il tuo account sulla piattaforma di monitoraggio delle prestazioni M0V3.

Ecco le tue credenziali di accesso:
• Email: {destinatario}
• Password Provvisoria: {password_provvisoria}
(Potrai cambiare questa password in qualsiasi momento dopo essere entrato nella webapp, recandoti nella sezione "Profilo Personale")

Link per accedere alla Web App:
{login_url}

A presto,
Team M0V3 Analytics
Supporto: {cfg['user']}
"""

    html_email = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Benvenuto in M0V3 Analytics</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f4f7f9; font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #f4f7f9; padding: 35px 15px;">
        <tr>
            <td align="center">
                <table width="600" cellpadding="0" cellspacing="0" style="max-width: 600px; width: 100%; background-color: #ffffff; border-radius: 14px; overflow: hidden; box-shadow: 0 4px 18px rgba(15, 23, 42, 0.08); border: 1px solid #e2e8f0;">
                    
                    <!-- HEADER EXECUTIVE -->
                    <tr>
                        <td style="background-color: #0f172a; border-bottom: 3px solid #0ea5e9; padding: 28px 32px; text-align: left;">
                            <table width="100%" cellpadding="0" cellspacing="0">
                                <tr>
                                    <td>
                                        <div style="font-size: 24px; font-weight: 900; color: #ffffff; letter-spacing: 1px;">M0V3 <span style="color: #0ea5e9; font-weight: 400; font-size: 20px;">ANALYTICS</span></div>
                                        <div style="font-size: 11.5px; font-weight: 700; color: #94a3b8; text-transform: uppercase; letter-spacing: 1.5px; margin-top: 3px;">Performance & Tracking System</div>
                                    </td>
                                    <td align="right">
                                        <span style="background: rgba(14, 165, 233, 0.16); color: #38bdf8; font-size: 11px; font-weight: 800; padding: 5px 12px; border-radius: 6px; border: 1px solid rgba(56, 189, 248, 0.3);">RUOLO: {ruolo.upper()}</span>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- BODY CONTENUTO -->
                    <tr>
                        <td style="padding: 34px 32px;">
                            <h2 style="margin: 0 0 12px 0; color: #0f172a; font-size: 20px; font-weight: 800;">Benvenuto in squadra!</h2>
                            <p style="margin: 0 0 24px 0; color: #475569; font-size: 14.5px; line-height: 1.6;">
                                È stato appena attivato il tuo account per accedere alla piattaforma <b>M0V3 Analytics</b>. Da oggi puoi monitorare le tue metriche di carico (ACWR, Player Load, eventi meccanici IMU e dati GPS).
                            </p>

                            <!-- BOX CREDENZIALI -->
                            <div style="background-color: #f8fafc; border: 1.5px solid #e2e8f0; border-radius: 10px; padding: 22px; margin-bottom: 24px;">
                                <div style="font-size: 11px; font-weight: 800; color: #64748b; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 12px; border-bottom: 1px solid #e2e8f0; padding-bottom: 8px;">
                                    Le tue credenziali di primo accesso
                                </div>
                                <div style="margin-bottom: 10px;">
                                    <span style="font-size: 12px; color: #64748b; font-weight: 700; display: block;">EMAIL ACCOUNT:</span>
                                    <span style="font-size: 15px; color: #0f172a; font-weight: 800;">{destinatario}</span>
                                </div>
                                <div style="margin-bottom: 12px;">
                                    <span style="font-size: 12px; color: #64748b; font-weight: 700; display: block;">PASSWORD PROVVISORIA:</span>
                                    <span style="font-size: 16px; color: #0284c7; font-weight: 900; background: #e0f2fe; padding: 4px 10px; border-radius: 6px; display: inline-block; font-family: monospace; letter-spacing: 1px;">{password_provvisoria}</span>
                                </div>
                                <div style="font-size: 12.5px; color: #b45309; background: #fef3c7; border-left: 3px solid #f59e0b; padding: 10px 12px; border-radius: 4px; line-height: 1.5; margin-top: 10px;">
                                    <b>Nota importante:</b> potrai cambiare la password quando entri nella webapp direttamente all'interno della sezione <b>Profilo Personale</b>.
                                </div>
                            </div>

                            <!-- PULSANTE ACCEDI -->
                            <div style="text-align: center; margin: 30px 0 20px 0;">
                                <a href="{login_url}" target="_blank" style="background-color: #0ea5e9; color: #ffffff; padding: 14px 34px; border-radius: 8px; font-size: 15px; font-weight: 800; text-decoration: none; display: inline-block; box-shadow: 0 4px 12px rgba(14, 165, 233, 0.35);">
                                    Accedi a M0V3 Analytics &rarr;
                                </a>
                            </div>
                            <div style="text-align: center; font-size: 12px; color: #94a3b8;">
                                Oppure copia e incolla questo indirizzo nel tuo browser:<br>
                                <a href="{login_url}" style="color: #0284c7; text-decoration: underline;">{login_url}</a>
                            </div>
                        </td>
                    </tr>

                    <!-- FOOTER -->
                    <tr>
                        <td style="background-color: #f8fafc; border-top: 1px solid #e2e8f0; padding: 20px 32px; text-align: center; color: #94a3b8; font-size: 11.5px; line-height: 1.6;">
                            Questo messaggio è stato generato automaticamente dalla piattaforma <b>M0V3 Analytics</b>.<br>
                            Per richieste di supporto o assistenza scrivi a: <a href="mailto:{cfg['user']}" style="color: #0ea5e9; text-decoration: none; font-weight: 700;">{cfg['user']}</a>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
"""
    return send_smtp_email(destinatario, subject, html_email, testo_piano)


def invia_email_reset_password_admin(destinatario, nuova_password_provvisoria):
    """
    Invia l'email di reset password generata dall'Admin con la nuova password temporanea
    e la specifica esplicita di poterla cambiare subito all'accesso.
    """
    cfg = get_smtp_config()
    login_url = cfg["base_url"]

    subject = "M0V3 Analytics — Nuova Password di Accesso"

    testo_piano = f"""Gentile Utente,

L'amministratore di M0V3 Analytics ha reimpostato la tua password di accesso.

Ecco le tue nuove credenziali:
• Email: {destinatario}
• Nuova Password Provvisoria: {nuova_password_provvisoria}
(Potrai cambiare questa password quando entri nella webapp direttamente nella sezione "Profilo Personale")

Accedi alla Web App:
{login_url}

Team M0V3 Analytics
Supporto: {cfg['user']}
"""

    html_email = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Nuova Password M0V3 Analytics</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f4f7f9; font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #f4f7f9; padding: 35px 15px;">
        <tr>
            <td align="center">
                <table width="600" cellpadding="0" cellspacing="0" style="max-width: 600px; width: 100%; background-color: #ffffff; border-radius: 14px; overflow: hidden; box-shadow: 0 4px 18px rgba(15, 23, 42, 0.08); border: 1px solid #e2e8f0;">
                    
                    <!-- HEADER -->
                    <tr>
                        <td style="background-color: #0f172a; border-bottom: 3px solid #f59e0b; padding: 26px 32px; text-align: left;">
                            <div style="font-size: 24px; font-weight: 900; color: #ffffff; letter-spacing: 1px;">M0V3 <span style="color: #0ea5e9; font-weight: 400; font-size: 20px;">ANALYTICS</span></div>
                            <div style="font-size: 11.5px; font-weight: 700; color: #94a3b8; text-transform: uppercase; letter-spacing: 1.5px; margin-top: 3px;">Aggiornamento Credenziali di Accesso</div>
                        </td>
                    </tr>

                    <!-- BODY -->
                    <tr>
                        <td style="padding: 34px 32px;">
                            <h2 style="margin: 0 0 12px 0; color: #0f172a; font-size: 19px; font-weight: 800;">Password Reimpostata dall'Amministratore</h2>
                            <p style="margin: 0 0 22px 0; color: #475569; font-size: 14.5px; line-height: 1.6;">
                                È stata generata una nuova password per il tuo account su richiesta dell'amministratore. Utilizza le credenziali seguenti per rientrare nella piattaforma:
                            </p>

                            <!-- BOX CREDENZIALI -->
                            <div style="background-color: #f8fafc; border: 1.5px solid #e2e8f0; border-radius: 10px; padding: 22px; margin-bottom: 24px;">
                                <div style="margin-bottom: 10px;">
                                    <span style="font-size: 12px; color: #64748b; font-weight: 700; display: block;">EMAIL ACCOUNT:</span>
                                    <span style="font-size: 15px; color: #0f172a; font-weight: 800;">{destinatario}</span>
                                </div>
                                <div style="margin-bottom: 12px;">
                                    <span style="font-size: 12px; color: #64748b; font-weight: 700; display: block;">NUOVA PASSWORD PROVVISORIA:</span>
                                    <span style="font-size: 16px; color: #0284c7; font-weight: 900; background: #e0f2fe; padding: 4px 10px; border-radius: 6px; display: inline-block; font-family: monospace; letter-spacing: 1px;">{nuova_password_provvisoria}</span>
                                </div>
                                <div style="font-size: 12.5px; color: #b45309; background: #fef3c7; border-left: 3px solid #f59e0b; padding: 10px 12px; border-radius: 4px; line-height: 1.5; margin-top: 10px;">
                                    <b>Nota importante:</b> potrai cambiare la password quando entri nella webapp direttamente all'interno della sezione <b>Profilo Personale</b>.
                                </div>
                            </div>

                            <!-- PULSANTE ACCEDI -->
                            <div style="text-align: center; margin: 30px 0 20px 0;">
                                <a href="{login_url}" target="_blank" style="background-color: #0ea5e9; color: #ffffff; padding: 14px 34px; border-radius: 8px; font-size: 15px; font-weight: 800; text-decoration: none; display: inline-block; box-shadow: 0 4px 12px rgba(14, 165, 233, 0.35);">
                                    Accedi a M0V3 Analytics &rarr;
                                </a>
                            </div>
                        </td>
                    </tr>

                    <!-- FOOTER -->
                    <tr>
                        <td style="background-color: #f8fafc; border-top: 1px solid #e2e8f0; padding: 20px 32px; text-align: center; color: #94a3b8; font-size: 11.5px; line-height: 1.6;">
                            Se non sei stato tu o l'amministratore a richiedere questa operazione, contatta subito l'assistenza: <a href="mailto:{cfg['user']}" style="color: #0ea5e9; text-decoration: none; font-weight: 700;">{cfg['user']}</a>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
"""
    return send_smtp_email(destinatario, subject, html_email, testo_piano)
