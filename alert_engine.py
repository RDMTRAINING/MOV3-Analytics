# Copyright 2026 Riccardo Di Maio - M0V3 S.r.l. Tutti i diritti riservati.
# Proprietary Sports Science & Clinical Performance Intelligence Architecture.
import os
import json
import uuid
import smtplib
import datetime as dt
from datetime import timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import numpy as np
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SUBSCRIPTIONS_LOCAL_PATH = os.path.join(BASE_DIR, "data_supporto", "alert_subscriptions.json")
DIGEST_LOGS_LOCAL_PATH = os.path.join(BASE_DIR, "data_supporto", "morning_digest_logs.json")


def _get_supabase_admin_client():
    """Restituisce il client Supabase Admin da utils (Streamlit) oppure da variabili d'ambiente (GitHub Actions / CLI)."""
    try:
        from utils import supabase_admin, supabase
        if supabase_admin is not None:
            return supabase_admin
        if supabase is not None:
            return supabase
    except Exception:
        pass
    try:
        from supabase import create_client
        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_KEY", "")
        if url and key:
            return create_client(url, key)
    except Exception:
        pass
    return None


def _get_smtp_credentials():
    """Recupera le credenziali SMTP da variabili d'ambiente (GitHub Actions) o da email_service (Streamlit)."""
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "465"))
    user = os.environ.get("SMTP_USER", "")
    password = os.environ.get("SMTP_PASS") or os.environ.get("SMTP_PASSWORD", "")
    sender_name = os.environ.get("SMTP_SENDER_NAME", "M0V3 Analytics — Proactive Alert Engine")
    base_url = os.environ.get("APP_BASE_URL", "https://webapptennisgps.streamlit.app")

    if not user or not password:
        try:
            from email_service import get_smtp_config
            cfg = get_smtp_config()
            host = cfg.get("host", host)
            port = int(cfg.get("port", port))
            user = user or cfg.get("user", "mov3project26@gmail.com")
            password = password or cfg.get("password", "")
            base_url = cfg.get("base_url", base_url)
        except Exception:
            pass
    return {
        "host": host,
        "port": port,
        "user": user or "mov3project26@gmail.com",
        "password": password,
        "sender_name": sender_name,
        "base_url": base_url.rstrip("/"),
    }


def _send_html_email_raw(to_email, subject, html_body, text_body=""):
    """Invia un'email HTML tramite SMTP SSL/TLS funzionando sia in Streamlit sia in modalità Headless CLI."""
    cfg = _get_smtp_credentials()
    if not cfg["password"] or cfg["password"].strip() in ("", "INSERISCI_APP_PASSWORD_QUI"):
        return False, "Password SMTP non configurata (imposta SMTP_PASS o st.secrets['smtp'])."

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{cfg['sender_name']} <{cfg['user']}>"
    msg["To"] = to_email

    if text_body:
        msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        if int(cfg["port"]) == 465:
            with smtplib.SMTP_SSL(cfg["host"], int(cfg["port"]), timeout=15) as server:
                server.login(cfg["user"], cfg["password"])
                server.sendmail(cfg["user"], [to_email], msg.as_string())
        else:
            with smtplib.SMTP(cfg["host"], int(cfg["port"]), timeout=15) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(cfg["user"], cfg["password"])
                server.sendmail(cfg["user"], [to_email], msg.as_string())
        return True, "INVIATO"
    except Exception as e:
        return False, f"ERRORE SMTP: {str(e)}"


# =========================================================================
# PERSISTENZA ISCRIZIONI ALERT & LOG INVII (SUPABASE + FALLBACK JSON/CLOUD)
# =========================================================================
def load_alert_subscriptions():
    """Carica la lista di destinatari configurati per il Morning Digest."""
    db = _get_supabase_admin_client()
    subs_db = []
    if db is not None:
        try:
            res = db.table("alert_subscriptions").select("*").order("email").execute()
            subs_db = res.data or []
        except Exception:
            subs_db = []

    subs_loc = []
    if os.path.exists(SUBSCRIPTIONS_LOCAL_PATH):
        try:
            with open(SUBSCRIPTIONS_LOCAL_PATH, "r", encoding="utf-8") as f:
                d = json.load(f)
                if isinstance(d, list):
                    subs_loc = d
        except Exception:
            pass

    by_email = {}
    for s in (subs_loc + subs_db):
        if isinstance(s, dict) and s.get("email"):
            em = str(s["email"]).strip().lower()
            by_email[em] = {
                "id": s.get("id") or str(uuid.uuid4()),
                "email": str(s["email"]).strip(),
                "atleti_monitorati": s.get("atleti_monitorati") or "TUTTI",
                "attivo": bool(s.get("attivo", True)),
                "invia_se_tutto_ok": bool(s.get("invia_se_tutto_ok", True)),
                "soglie_custom_json": s.get("soglie_custom_json") or {"acwr_max": 150.0, "ie_decoupling_pct": 20.0, "adapted_cap_pct": 70.0},
            }

    if not by_email:
        # Default seed per Super-Admin
        default_em = "mov3project26@gmail.com"
        by_email[default_em] = {
            "id": str(uuid.uuid4()),
            "email": default_em,
            "atleti_monitorati": "TUTTI",
            "attivo": True,
            "invia_se_tutto_ok": True,
            "soglie_custom_json": {"acwr_max": 150.0, "ie_decoupling_pct": 20.0, "adapted_cap_pct": 70.0},
        }
    return list(by_email.values())


def save_alert_subscriptions(subs_list):
    """Salva la configurazione destinatari su JSON locale, Cloud Snapshot e tabella Supabase `alert_subscriptions`."""
    clean_list = []
    for s in (subs_list or []):
        if not isinstance(s, dict) or not str(s.get("email", "")).strip():
            continue
        clean_list.append({
            "id": str(s.get("id") or uuid.uuid4()),
            "email": str(s.get("email")).strip(),
            "atleti_monitorati": str(s.get("atleti_monitorati") or "TUTTI").strip(),
            "attivo": bool(s.get("attivo", True)),
            "invia_se_tutto_ok": bool(s.get("invia_se_tutto_ok", False)),
            "soglie_custom_json": s.get("soglie_custom_json") if isinstance(s.get("soglie_custom_json"), dict) else {"acwr_max": 150.0, "ie_decoupling_pct": 20.0, "adapted_cap_pct": 70.0},
            "updated_at": dt.datetime.utcnow().isoformat(),
        })

    try:
        os.makedirs(os.path.dirname(SUBSCRIPTIONS_LOCAL_PATH), exist_ok=True)
        with open(SUBSCRIPTIONS_LOCAL_PATH, "w", encoding="utf-8") as f:
            json.dump(clean_list, f, ensure_ascii=False, indent=2)
        from utils import upload_binary_snapshot
        upload_binary_snapshot(SUBSCRIPTIONS_LOCAL_PATH, "alert_subscriptions.json")
    except Exception:
        pass

    db = _get_supabase_admin_client()
    if db is not None:
        try:
            db.table("alert_subscriptions").delete().neq("email", "__none__").execute()
            if clean_list:
                db.table("alert_subscriptions").upsert(clean_list, on_conflict="email").execute()
        except Exception:
            pass
    return True


def load_morning_digest_logs(limit=30):
    """Carica il log storico degli ultimi 30 invii del Morning Digest."""
    logs = []
    if os.path.exists(DIGEST_LOGS_LOCAL_PATH):
        try:
            with open(DIGEST_LOGS_LOCAL_PATH, "r", encoding="utf-8") as f:
                d = json.load(f)
                if isinstance(d, list):
                    logs = d
        except Exception:
            pass
    logs.sort(key=lambda x: str(x.get("timestamp", "")), reverse=True)
    return logs[:limit]


def append_morning_digest_log(entry_dict):
    """Aggiunge un record al log storico degli ultimi 30 invii e lo sincronizza nello snapshot Cloud."""
    logs = load_morning_digest_logs(limit=50)
    rec = dict(entry_dict)
    if "id" not in rec:
        rec["id"] = str(uuid.uuid4())
    if "timestamp" not in rec:
        rec["timestamp"] = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logs.insert(0, rec)
    logs = logs[:30]
    try:
        os.makedirs(os.path.dirname(DIGEST_LOGS_LOCAL_PATH), exist_ok=True)
        with open(DIGEST_LOGS_LOCAL_PATH, "w", encoding="utf-8") as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
        from utils import upload_binary_snapshot
        upload_binary_snapshot(DIGEST_LOGS_LOCAL_PATH, "morning_digest_logs.json")
    except Exception:
        pass
    return True


# =========================================================================
# MOTORE DI SCANSIONE RED-FLAGS (6 REGOLE SCIENTIFICHE V3.0)
# =========================================================================
def run_proactive_red_flag_scan(target_athletes=None, custom_thresholds=None):
    """
    Esegue la scansione multi-sorgente sulle 6 regole di Red-Flag del Modulo 2.1 v3.0:
    1. WELLNESS_MANCANTE (INFO / WARN)
    2. OVERLOAD_ADATTATO (CRITICO)
    3. DECOUPLING_IE_20 (ATTENZIONE)
    4. ACWR_SPIKE_150 (CRITICO)
    5. HRV_DROP_SWC (ATTENZIONE)
    6. CODA_KSPORT_PENDENTE (OPERATIVO)
    """
    th = custom_thresholds or {}
    acwr_max_th = float(th.get("acwr_max", 150.0) or 150.0)
    ie_dec_pct_th = float(th.get("ie_decoupling_pct", 20.0) or 20.0)
    adapted_cap_pct = float(th.get("adapted_cap_pct", 70.0) or 70.0)

    db = _get_supabase_admin_client()
    today_d = dt.date.today()
    today_iso = today_d.strftime("%Y-%m-%d")
    d_48h_ago = (today_d - timedelta(days=2)).strftime("%Y-%m-%d")
    d_60d_ago = (today_d - timedelta(days=65)).strftime("%Y-%m-%d")

    # 1. Caricamento Database GPS locale/partizionato
    df_gps_all = pd.DataFrame()
    try:
        from utils import load_local_database
        df_gps_all = load_local_database()
    except Exception:
        parq_p = os.path.join(BASE_DIR, "database_storico.parquet")
        if os.path.exists(parq_p):
            try:
                df_gps_all = pd.read_parquet(parq_p)
            except Exception:
                df_gps_all = pd.DataFrame()

    if not df_gps_all.empty and "Date_obj" not in df_gps_all.columns and "Date" in df_gps_all.columns:
        df_gps_all["Date_obj"] = pd.to_datetime(df_gps_all["Date"], format="%d/%m/%Y", errors="coerce")

    # 2. Anagrafica Atleti
    dict_nome_to_id = {}
    nomi_gps = sorted([str(p).strip() for p in df_gps_all["Players"].dropna().unique() if str(p).strip()]) if (not df_gps_all.empty and "Players" in df_gps_all.columns) else []
    if db is not None:
        try:
            res_a = db.table("atleti").select("id, nome, cognome").execute()
            for a in (res_a.data or []):
                fn = f"{a.get('nome', '')} {a.get('cognome', '')}".strip()
                if fn:
                    dict_nome_to_id[fn] = a["id"]
        except Exception:
            pass

    all_athletes = sorted(list(dict.fromkeys(list(dict_nome_to_id.keys()) + nomi_gps)))
    if target_athletes and target_athletes != "TUTTI":
        if isinstance(target_athletes, str):
            wanted = {x.strip().lower() for x in target_athletes.split(",") if x.strip()}
        else:
            wanted = {str(x).strip().lower() for x in target_athletes if str(x).strip()}
        if wanted and "tutti" not in wanted:
            all_athletes = [a for a in all_athletes if a.lower() in wanted]

    # Pre-fetch dati Supabase per evitare N query
    wellness_rows = []
    rpe_rows = []
    medico_rows = []
    if db is not None:
        try:
            wellness_rows = db.table("wellness_mattutino").select("*").gte("data", d_60d_ago).execute().data or []
        except Exception:
            wellness_rows = []
        try:
            rpe_rows = db.table("rpe_sessioni").select("*").gte("data", d_60d_ago).execute().data or []
        except Exception:
            rpe_rows = []
        try:
            medico_rows = db.table("registro_medico_fisio").select("*").lte("data_inizio", today_iso).gte("data_fine", d_48h_ago).execute().data or []
        except Exception:
            medico_rows = []

    from utils import parse_audit_from_row, enrich_wellness_row_biometrics, calcola_analisi_hrv_autonomica, get_athlete_ewma_timeline, get_coda_tagli_gps

    wellness_valid = [enrich_wellness_row_biometrics(w) for w in wellness_rows if parse_audit_from_row(w).get("is_valid", True)]
    rpe_valid = [r for r in rpe_rows if parse_audit_from_row(r).get("is_valid", True)]

    athletes_summary = []
    all_alerts = []

    for ath_name in all_athletes:
        ath_id = dict_nome_to_id.get(ath_name)
        ath_alerts = []

        df_ath_gps = df_gps_all[df_gps_all["Players"].astype(str).str.strip().str.lower() == ath_name.lower()].copy() if (not df_gps_all.empty and "Players" in df_gps_all.columns) else pd.DataFrame()
        w_ath = [w for w in wellness_valid if (ath_id and str(w.get("atleta_id")) == str(ath_id))]
        r_ath = [r for r in rpe_valid if (ath_id and str(r.get("atleta_id")) == str(ath_id))]
        m_ath = [
            m for m in medico_rows
            if (ath_id and str(m.get("atleta_id")) == str(ath_id))
            or (str(m.get("nome_giocatore", "")).strip().lower() == ath_name.lower())
        ]

        # REGOLA 1: WELLNESS_MANCANTE
        w_today = [w for w in w_ath if str(w.get("data", ""))[:10] == today_iso]
        if not w_today:
            al = {
                "atleta": ath_name,
                "codice": "WELLNESS_MANCANTE",
                "severita": "INFO / WARN",
                "badge": "[INFO]",
                "colore": "#0284c7",
                "titolo": "Compilazione Wellness Mattutino Assente",
                "dettaglio": f"L'atleta non ha ancora registrato il check-in mattutino per oggi ({today_d.strftime('%d/%m/%Y')}).",
            }
            ath_alerts.append(al)
            all_alerts.append(al)

        # REGOLA 2: OVERLOAD_ADATTATO (>70% TL storico in status LIMITATO / CARICO ADATTATO)
        is_adapted = any(str(m.get("status_operativo", "")).upper() == "LIMITATO" for m in m_ath)
        avg_tl_hist = 0.0
        latest_tl = 0.0
        latest_gps_date_str = "N/D"
        if not df_ath_gps.empty and "Training Load" in df_ath_gps.columns:
            tl_s = pd.to_numeric(df_ath_gps["Training Load"], errors="coerce").dropna()
            tl_s = tl_s[tl_s > 0]
            if not tl_s.empty:
                avg_tl_hist = float(tl_s.mean())
            df_ath_gps_sorted = df_ath_gps.dropna(subset=["Date_obj"]).sort_values("Date_obj")
            if not df_ath_gps_sorted.empty:
                last_dt = df_ath_gps_sorted.iloc[-1]["Date_obj"]
                latest_gps_date_str = last_dt.strftime("%d/%m/%Y")
                if (today_d - last_dt.date()).days <= 3:
                    latest_tl = float(pd.to_numeric(df_ath_gps_sorted[df_ath_gps_sorted["Date_obj"] == last_dt]["Training Load"], errors="coerce").fillna(0).sum())

        if is_adapted and avg_tl_hist > 0 and latest_tl > (avg_tl_hist * (adapted_cap_pct / 100.0)):
            pct_reached = (latest_tl / avg_tl_hist) * 100.0
            al = {
                "atleta": ath_name,
                "codice": "OVERLOAD_ADATTATO",
                "severita": "CRITICO",
                "badge": "[CRITICO]",
                "colore": "#dc2626",
                "titolo": f"Violazione Tetto Clinico {adapted_cap_pct:.0f}% (Carico Adattato)",
                "dettaglio": f"Sessione del {latest_gps_date_str}: {latest_tl:.0f} TL ({pct_reached:.0f}% della media storica di {avg_tl_hist:.0f} TL).",
            }
            ath_alerts.append(al)
            all_alerts.append(al)

        # REGOLA 3: DECOUPLING_IE_20 (Pure Tennis I:E Ratio > +20% della media individuale)
        if not df_ath_gps.empty and r_ath:
            df_r_ath = pd.DataFrame(r_ath)
            df_r_ten = df_r_ath[df_r_ath["tipologia"].astype(str).str.lower().str.contains("tennis")].copy()
            if not df_r_ten.empty and "carico_interno" in df_r_ten.columns:
                srpe_by_d = df_r_ten.groupby("data")["carico_interno"].sum().to_dict()
                df_g_tmp = df_ath_gps.dropna(subset=["Date_obj"]).copy()
                df_g_tmp["d_iso"] = df_g_tmp["Date_obj"].dt.strftime("%Y-%m-%d")
                tl_by_d = df_g_tmp.groupby("d_iso")["Training Load"].apply(lambda s: pd.to_numeric(s, errors="coerce").fillna(0).sum()).to_dict()
                ie_pairs = []
                for d_k in sorted(set(srpe_by_d.keys()) & set(tl_by_d.keys())):
                    if srpe_by_d[d_k] > 0 and tl_by_d[d_k] > 0:
                        ie_pairs.append((d_k, float(srpe_by_d[d_k]) / float(tl_by_d[d_k])))
                if len(ie_pairs) >= 2:
                    mean_ie = float(np.mean([x[1] for x in ie_pairs]))
                    last_d_ie, last_val_ie = ie_pairs[-1]
                    if mean_ie > 0 and last_val_ie > mean_ie * (1.0 + ie_dec_pct_th / 100.0):
                        diff_ie_pct = ((last_val_ie - mean_ie) / mean_ie) * 100.0
                        al = {
                            "atleta": ath_name,
                            "codice": "DECOUPLING_IE_20",
                            "severita": "ATTENZIONE",
                            "badge": "[ATTENZIONE]",
                            "colore": "#d97706",
                            "titolo": f"Disaccoppiamento I:E Ratio Puro Tennis (+{diff_ie_pct:.0f}%)",
                            "dettaglio": f"Data {last_d_ie}: I:E Ratio pari a {last_val_ie:.2f} vs baseline individuale {mean_ie:.2f} (soglia +{ie_dec_pct_th:.0f}%).",
                        }
                        ath_alerts.append(al)
                        all_alerts.append(al)

        # REGOLA 4: ACWR_SPIKE_150 (ACWR Uncoupled EWMA > 150% o Monotonia 7d > 2.0)
        latest_acwr_tl = None
        latest_acwr_mech = None
        monotony_7d = 0.0
        if not df_ath_gps.empty:
            tl_map = get_athlete_ewma_timeline(df_gps_all, ath_name, col="Training Load", burn_in_mask=False)
            mech_map = get_athlete_ewma_timeline(df_gps_all, ath_name, col="Mechanical Load", burn_in_mask=False)
            if tl_map:
                last_k = list(tl_map.keys())[-1]
                latest_acwr_tl = tl_map[last_k].get("acwr7")
                # Monotonia ultimi 7 giorni della timeline
                last_7_vals = [float(tl_map[k]["load"]) for k in list(tl_map.keys())[-7:]]
                if len(last_7_vals) == 7:
                    m7 = float(np.mean(last_7_vals))
                    sd7 = float(np.std(last_7_vals, ddof=0))
                    if sd7 > 0:
                        monotony_7d = round(m7 / sd7, 2)
            if mech_map:
                last_km = list(mech_map.keys())[-1]
                latest_acwr_mech = mech_map[last_km].get("acwr7")

            if (latest_acwr_tl and latest_acwr_tl > acwr_max_th) or (latest_acwr_mech and latest_acwr_mech > acwr_max_th) or (monotony_7d > 2.0):
                reasons = []
                if latest_acwr_tl and latest_acwr_tl > acwr_max_th:
                    reasons.append(f"ACWR Globale {latest_acwr_tl:.1f}%")
                if latest_acwr_mech and latest_acwr_mech > acwr_max_th:
                    reasons.append(f"ACWR Meccanico {latest_acwr_mech:.1f}%")
                if monotony_7d > 2.0:
                    reasons.append(f"Monotonia Foster {monotony_7d:.2f}")
                al = {
                    "atleta": ath_name,
                    "codice": "ACWR_SPIKE_150",
                    "severita": "CRITICO",
                    "badge": "[CRITICO]",
                    "colore": "#dc2626",
                    "titolo": "Picco ACWR Uncoupled EWMA / Monotonia Fuori Soglia",
                    "dettaglio": f"Rilevato sovraccarico acuto: {' | '.join(reasons)} (Ultima sessione: {latest_gps_date_str}).",
                }
                ath_alerts.append(al)
                all_alerts.append(al)

        # REGOLA 5: HRV_DROP_SWC (Media 7d HRV sotto Baseline 60d - 0.5 SWC per 2+ gg o calo acuto >1 SD con Wellness < 6.0)
        hrv_status_str = "N/D"
        if w_ath:
            df_w_ath = pd.DataFrame(w_ath)
            for c_req in ("sonno_qualita", "umore", "fatica", "stress", "doms"):
                if c_req not in df_w_ath.columns:
                    df_w_ath[c_req] = 5.0
                df_w_ath[c_req] = pd.to_numeric(df_w_ath[c_req], errors="coerce").fillna(5.0)
            df_w_ath["wellness_score"] = ((df_w_ath["sonno_qualita"] + df_w_ath["umore"]) + (11 - df_w_ath["fatica"]) + (11 - df_w_ath["stress"]) + (11 - df_w_ath["doms"])) / 5.0
            bio_eval = calcola_analisi_hrv_autonomica(df_w_ath)
            if bio_eval.get("has_hrv"):
                hrv_status_str = f"{bio_eval.get('latest_hrv_7d', 0):.1f} ms [{bio_eval.get('status_code', 'OK')}]"
                if bio_eval.get("consec_below_swc", 0) >= 2 or bio_eval.get("status_code") == "ROSSO":
                    al = {
                        "atleta": ath_name,
                        "codice": "HRV_DROP_SWC",
                        "severita": "ATTENZIONE",
                        "badge": "[ATTENZIONE]",
                        "colore": "#d97706",
                        "titolo": "Flessione Autonomica HRV Sotto Banda SWC 60d",
                        "dettaglio": f"HRV 7d Rolling ({bio_eval.get('latest_hrv_7d', 0):.1f} ms) sotto il limite SWC ({bio_eval.get('latest_swc_low', 0):.1f} ms) per {bio_eval.get('consec_below_swc', 0)} giorni.",
                    }
                    ath_alerts.append(al)
                    all_alerts.append(al)

        # Determinazione stato semaforico sintetico dell'atleta
        severities = {a["severita"] for a in ath_alerts}
        if "CRITICO" in severities:
            sem_badge = "[CRITICO]"
            sem_color = "#dc2626"
        elif "ATTENZIONE" in severities:
            sem_badge = "[ATTENZIONE]"
            sem_color = "#d97706"
        elif "INFO / WARN" in severities:
            sem_badge = "[INFO]"
            sem_color = "#0284c7"
        else:
            sem_badge = "[OK]"
            sem_color = "#16a34a"

        athletes_summary.append({
            "atleta": ath_name,
            "semaforo_badge": sem_badge,
            "semaforo_colore": sem_color,
            "wellness_oggi": "COMPILATO" if w_today else "ASSENTE",
            "ultima_gps": latest_gps_date_str,
            "acwr_tl": f"{latest_acwr_tl:.1f}%" if latest_acwr_tl is not None else "N/D",
            "monotonia_7d": f"{monotony_7d:.2f}" if monotony_7d > 0 else "N/D",
            "hrv_7d": hrv_status_str,
            "n_alerts": len(ath_alerts),
            "alerts": ath_alerts,
        })

    # REGOLA 6: CODA_KSPORT_PENDENTE (richieste aperte in coda_tagli_gps da oltre 12 ore)
    ksport_pending_over_12h = []
    try:
        df_coda = get_coda_tagli_gps(only_pending=True)
        if df_coda is not None and not df_coda.empty:
            now_dt = dt.datetime.now()
            for _, rc in df_coda.iterrows():
                cr_str = str(rc.get("created_at", ""))
                cr_dt = pd.to_datetime(cr_str, errors="coerce")
                hours_elapsed = ((now_dt - cr_dt.to_pydatetime()).total_seconds() / 3600.0) if pd.notna(cr_dt) else 24.0
                if hours_elapsed >= 12.0:
                    ksport_pending_over_12h.append({
                        "atleta": str(rc.get("atleta", "N/D")),
                        "data_sessione": str(rc.get("data_sessione", "")),
                        "tipologia": str(rc.get("tipologia_sessione", "")),
                        "ore_attesa": round(hours_elapsed, 1),
                    })
    except Exception:
        pass

    if ksport_pending_over_12h:
        al_k = {
            "atleta": "OPERATIVO / K-SPORT",
            "codice": "CODA_KSPORT_PENDENTE",
            "severita": "OPERATIVO",
            "badge": "[OPERATIVO]",
            "colore": "#7c3aed",
            "titolo": f"{len(ksport_pending_over_12h)} Sessioni GPS in Attesa di Taglio K-Sport (>12h)",
            "dettaglio": ", ".join([f"{x['atleta']} ({x['data_sessione']} - {x['ore_attesa']}h)" for x in ksport_pending_over_12h[:5]]),
        }
        all_alerts.append(al_k)

    n_crit = sum(1 for a in all_alerts if a["severita"] == "CRITICO")
    n_att = sum(1 for a in all_alerts if a["severita"] == "ATTENZIONE")
    n_op = sum(1 for a in all_alerts if a["severita"] == "OPERATIVO")
    n_info = sum(1 for a in all_alerts if a["severita"] == "INFO / WARN")

    return {
        "scan_date": today_d.strftime("%d/%m/%Y"),
        "scan_timestamp": dt.datetime.now().strftime("%d/%m/%Y %H:%M"),
        "n_athletes": len(athletes_summary),
        "n_total_alerts": len(all_alerts),
        "n_critico": n_crit,
        "n_attenzione": n_att,
        "n_operativo": n_op,
        "n_info": n_info,
        "is_all_green": (n_crit == 0 and n_att == 0 and n_op == 0),
        "athletes_summary": athletes_summary,
        "alerts": all_alerts,
        "ksport_pending": ksport_pending_over_12h,
    }


def build_morning_digest_html(scan_result, lang="IT"):
    """
    Genera il Template Email HTML Executive "M0V3 Morning Digest" (Modulo 2.1 v3.0):
    - Sfondo chiaro stampabile, header Dark Navy (#081120)
    - Tabella semaforica per atleta e lista red-flags
    - RIGOROSAMENTE ZERO EMOJI (solo badge testuali [CRITICO], [ATTENZIONE], [OPERATIVO], [INFO], [OK]).
    """
    cfg = _get_smtp_credentials()
    app_url = cfg["base_url"]
    is_en = str(lang).upper() == "EN"

    title_hdr = "M0V3 ANALYTICS ENTERPRISE — PROACTIVE MORNING DIGEST" if is_en else "M0V3 ANALYTICS ENTERPRISE — MORNING DIGEST PROATTIVO"
    sub_hdr = f"Report Automatico Readiness, ACWR, Biometria HRV & Compliance | {scan_result['scan_timestamp']}"

    rows_ath_html = ""
    for ath in scan_result.get("athletes_summary", []):
        b_col = ath["semaforo_colore"]
        rows_ath_html += (
            f"<tr style='border-bottom:1px solid #e2e8f0;'>"
            f"<td style='padding:10px 12px; font-weight:800; color:#0f172a;'>{ath['atleta']}</td>"
            f"<td style='padding:10px 12px; text-align:center;'><span style='background:{b_col}; color:#ffffff; font-weight:800; font-size:11px; padding:3px 8px; border-radius:4px;'>{ath['semaforo_badge']}</span></td>"
            f"<td style='padding:10px 12px; text-align:center; font-weight:700; color:{'#16a34a' if ath['wellness_oggi']=='COMPILATO' else '#d97706'};'>{ath['wellness_oggi']}</td>"
            f"<td style='padding:10px 12px; text-align:center; color:#334155;'>{ath['ultima_gps']}</td>"
            f"<td style='padding:10px 12px; text-align:center; font-weight:800; color:#0f172a;'>{ath['acwr_tl']}</td>"
            f"<td style='padding:10px 12px; text-align:center; color:#334155;'>{ath['monotonia_7d']}</td>"
            f"<td style='padding:10px 12px; text-align:center; color:#0284c7; font-weight:700;'>{ath['hrv_7d']}</td>"
            f"</tr>"
        )

    alerts_html = ""
    if scan_result.get("alerts"):
        for al in scan_result["alerts"]:
            c_al = al["colore"]
            alerts_html += (
                f"<div style='background:#ffffff; border:1px solid #cbd5e1; border-left:5px solid {c_al}; border-radius:6px; padding:10px 14px; margin-bottom:8px;'>"
                f"<div style='font-size:12px; font-weight:800; color:#0f172a;'>"
                f"<span style='color:{c_al}; margin-right:6px;'>{al['badge']}</span> {al['atleta']} — {al['titolo']} <span style='font-size:10px; color:#64748b;'>({al['codice']})</span>"
                f"</div>"
                f"<div style='font-size:12px; color:#334155; margin-top:3px;'>{al['dettaglio']}</div>"
                f"</div>"
            )
    else:
        alerts_html = (
            "<div style='background:#f0fdf4; border:1px solid #86efac; border-left:5px solid #16a34a; border-radius:6px; padding:12px 16px; color:#166534; font-weight:700; font-size:13px;'>"
            "[OK] ALL GREEN REPORT — Nessuna anomalia critica o disaccoppiamento rilevato per il roster monitorato."
            "</div>"
        )

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0; padding:20px; background-color:#f1f5f9; font-family:'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color:#0f172a;">
    <div style="max-width:760px; margin:0 auto; background:#ffffff; border:1px solid #cbd5e1; border-radius:12px; overflow:hidden; box-shadow:0 4px 16px rgba(15,23,42,0.08);">
        <div style="background:#081120; color:#f8fafc; padding:20px 24px; border-bottom:3px solid #0ea5e9;">
            <div style="font-size:11px; font-weight:800; color:#38bdf8; letter-spacing:1px; text-transform:uppercase;">M0V3 ANALYTICS V3.0 · CLINICAL & PERFORMANCE INTELLIGENCE</div>
            <div style="font-size:18px; font-weight:900; color:#ffffff; margin-top:4px;">{title_hdr}</div>
            <div style="font-size:12px; color:#94a3b8; margin-top:4px;">{sub_hdr}</div>
        </div>

        <div style="padding:20px 24px;">
            <table style="width:100%; border-collapse:collapse; margin-bottom:18px; background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px;">
                <tr>
                    <td style="padding:10px; text-align:center; border-right:1px solid #e2e8f0;">
                        <div style="font-size:10px; font-weight:800; color:#64748b; text-transform:uppercase;">ATLETI MONITORATI</div>
                        <div style="font-size:18px; font-weight:900; color:#0f172a;">{scan_result['n_athletes']}</div>
                    </td>
                    <td style="padding:10px; text-align:center; border-right:1px solid #e2e8f0;">
                        <div style="font-size:10px; font-weight:800; color:#dc2626; text-transform:uppercase;">[CRITICO]</div>
                        <div style="font-size:18px; font-weight:900; color:#dc2626;">{scan_result['n_critico']}</div>
                    </td>
                    <td style="padding:10px; text-align:center; border-right:1px solid #e2e8f0;">
                        <div style="font-size:10px; font-weight:800; color:#d97706; text-transform:uppercase;">[ATTENZIONE]</div>
                        <div style="font-size:18px; font-weight:900; color:#d97706;">{scan_result['n_attenzione']}</div>
                    </td>
                    <td style="padding:10px; text-align:center; border-right:1px solid #e2e8f0;">
                        <div style="font-size:10px; font-weight:800; color:#7c3aed; text-transform:uppercase;">[OPERATIVO]</div>
                        <div style="font-size:18px; font-weight:900; color:#7c3aed;">{scan_result['n_operativo']}</div>
                    </td>
                    <td style="padding:10px; text-align:center;">
                        <div style="font-size:10px; font-weight:800; color:#0284c7; text-transform:uppercase;">[INFO / WELLNESS]</div>
                        <div style="font-size:18px; font-weight:900; color:#0284c7;">{scan_result['n_info']}</div>
                    </td>
                </tr>
            </table>

            <div style="font-size:13px; font-weight:900; color:#0f172a; text-transform:uppercase; letter-spacing:0.5px; margin-bottom:8px;">
                1. QUADRO SINOTTICO SEMAFORICO ROSTER ATLETI
            </div>
            <table style="width:100%; border-collapse:collapse; font-size:12px; border:1px solid #cbd5e1; margin-bottom:20px;">
                <thead>
                    <tr style="background:#0f172a; color:#ffffff; font-size:10.5px; text-transform:uppercase;">
                        <th style="padding:9px 12px; text-align:left;">ATLETA</th>
                        <th style="padding:9px 12px; text-align:center;">STATO</th>
                        <th style="padding:9px 12px; text-align:center;">WELLNESS OGGI</th>
                        <th style="padding:9px 12px; text-align:center;">ULTIMA GPS</th>
                        <th style="padding:9px 12px; text-align:center;">ACWR EWMA</th>
                        <th style="padding:9px 12px; text-align:center;">MONOTONIA</th>
                        <th style="padding:9px 12px; text-align:center;">HRV 7D (SWC)</th>
                    </tr>
                </thead>
                <tbody>
                    {rows_ath_html}
                </tbody>
            </table>

            <div style="font-size:13px; font-weight:900; color:#0f172a; text-transform:uppercase; letter-spacing:0.5px; margin-bottom:8px;">
                2. DETTAGLIO ANOMALIE & RED-FLAGS RILEVATE ({scan_result['n_total_alerts']})
            </div>
            {alerts_html}

            <div style="text-align:center; margin-top:22px; margin-bottom:10px;">
                <a href="{app_url}" style="background:#0284c7; color:#ffffff; text-decoration:none; font-weight:800; font-size:13px; padding:10px 22px; border-radius:6px; display:inline-block;">
                    APRI DASHBOARD M0V3 ANALYTICS ENTERPRISE
                </a>
            </div>
        </div>

        <div style="background:#f8fafc; border-top:1px solid #e2e8f0; padding:12px 24px; text-align:center; font-size:11px; color:#64748b;">
            &copy; 2026 — Generato tramite tecnologia proprietaria Riccardo Di Maio &amp; M0V3 S.r.l. - Tutti i diritti riservati
        </div>
    </div>
</body>
</html>"""
    return html


def dispatch_morning_digest(force_send_all=False):
    """
    Esegue la scansione per tutti i destinatari attivi in `alert_subscriptions`
    e invia il Morning Digest via SMTP, registrando l'esito nel log storico degli ultimi 30 invii.
    """
    subs = load_alert_subscriptions()
    active_subs = [s for s in subs if s.get("attivo", True)]
    results = []

    for sub in active_subs:
        email_to = str(sub.get("email", "")).strip()
        if not email_to:
            continue
        ath_scope = sub.get("atleti_monitorati", "TUTTI")
        soglie = sub.get("soglie_custom_json") if isinstance(sub.get("soglie_custom_json"), dict) else {}
        invia_ok = bool(sub.get("invia_se_tutto_ok", False)) or force_send_all

        scan = run_proactive_red_flag_scan(target_athletes=ath_scope, custom_thresholds=soglie)
        has_actionable_alerts = scan["n_total_alerts"] > 0

        if not has_actionable_alerts and not invia_ok:
            log_entry = {
                "timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "email": email_to,
                "atleti": ath_scope,
                "n_alerts": 0,
                "stato": "SKIPPED (ALL GREEN)",
                "dettaglio": "Nessuna red-flag rilevata e invia_se_tutto_ok=False.",
            }
            append_morning_digest_log(log_entry)
            results.append(log_entry)
            continue

        subj_tag = f"[{scan['n_critico']} CRITICI | {scan['n_attenzione']} ATTENZIONE]" if (scan["n_critico"] > 0 or scan["n_attenzione"] > 0) else "[REPORT GIORNALIERO]"
        subject = f"M0V3 Morning Digest {subj_tag} — {scan['scan_date']}"
        html_body = build_morning_digest_html(scan, lang="IT")
        ok_send, msg_send = _send_html_email_raw(email_to, subject, html_body)

        log_entry = {
            "timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "email": email_to,
            "atleti": ath_scope,
            "n_alerts": scan["n_total_alerts"],
            "stato": "INVIATO" if ok_send else "ERRORE",
            "dettaglio": msg_send,
        }
        append_morning_digest_log(log_entry)
        results.append(log_entry)

    return results
