import os
import re
import time
import json
import datetime
from datetime import timedelta, date
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from supabase import create_client, Client
import postgrest.exceptions
from postgrest._sync.request_builder import SyncQueryRequestBuilder
from config import DB_PATH, DB_PARQUET_PATH, LEGENDA_ACWR, COLONNE_STANDARD, tr, PLOTLY_CONFIG

COLONNE_METADATI = [
    "Tipologia Campo", "Ambiente", "Minuti Sparring",
    "Tipologia Sessione", "File_Name", "Uploader_Email", "Dato_Simulato"
]
COLONNE_DATABASE = COLONNE_STANDARD + COLONNE_METADATI
COLONNE_GPS = [
    "DISTANCE", "HML Distance >25.5W", "VHML Distance >50W",
    "High Dec Events <-3.5 m/s2", "Recovery Time <5W %",
    "Equivalent Distance %", "Anaerobic index %"
]
COLONNE_NUMERICHE_STANDARD = [c for c in COLONNE_STANDARD if c not in ("Date", "Session", "Players", "Minuti")]

def get_user_client():
    """Un client Supabase separato per ogni sessione/utente."""
    if 'sb_client' not in st.session_state:
        st.session_state['sb_client'] = create_client(
            st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"]
        )
    return st.session_state['sb_client']

class _SupabasePerSession:
    """Fa funzionare tutti i 'supabase.table(...)' esistenti con il client della sessione."""
    def __getattr__(self, name):
        return getattr(get_user_client(), name)

@st.cache_resource
def init_admin_connection():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    service_key = st.secrets.get("SUPABASE_SERVICE_KEY", key)
    return create_client(url, service_key)

supabase = None
supabase_admin = None
try:
    supabase = _SupabasePerSession()
    supabase_admin = init_admin_connection()
except Exception as e:
    try:
        st.error(f"Errore DB: {e}")
        st.stop()
    except Exception:
        pass
# =========================================================================
# AUTO-REFRESH DEL JWT EXPIRED PER POSTGREST
# =========================================================================
_orig_postgrest_query_execute = SyncQueryRequestBuilder.execute

def _auto_refresh_postgrest_execute(self, *args, **kwargs):
    try:
        return _orig_postgrest_query_execute(self, *args, **kwargs)
    except Exception as e:
        code = str(getattr(e, 'code', '') or '')
        msg = str(getattr(e, 'message', '') or str(e)).lower()
        if code == 'PGRST303' or 'jwt expired' in msg or 'jwt' in msg:
            # Token scaduto durante una query: tenta il refresh automatico trasparente
            try:
                rt = st.session_state.get('refresh_token')
                if not rt and hasattr(st, 'context') and hasattr(st.context, 'cookies'):
                    rt = st.context.cookies.get('m0v3_rt')

                res = supabase.auth.refresh_session(rt) if rt else None
                if res and hasattr(res, 'session') and res.session:
                    new_token = res.session.access_token
                    st.session_state['refresh_token'] = res.session.refresh_token
                    if hasattr(res, 'user') and res.user:
                        st.session_state['user'] = res.user

                    supabase.postgrest.auth(new_token)
                    if 'sb_client' in st.session_state:
                        st.session_state['sb_client'].postgrest.auth(new_token)

                    # Aggiorna gli header della richiesta corrente prima di rieseguire
                    if hasattr(self, 'request'):
                        req = self.request
                        if hasattr(req, 'headers'):
                            req.headers['Authorization'] = f"Bearer {new_token}"
                            req.headers['authorization'] = f"Bearer {new_token}"
                        if hasattr(req, 'auth'):
                            try:
                                req.auth = lambda r: r.headers.update({"Authorization": f"Bearer {new_token}"})
                            except Exception:
                                pass
                    return _orig_postgrest_query_execute(self, *args, **kwargs)
            except Exception:
                pass

            # Non renderizzare mai st.warning() all'interno di container UI attivi (es. sidebar).
            # Se la sessione è effettivamente compromessa, ensure_valid_session() al main()
            # gestirà il reindirizzamento pulito alla schermata di login.
            if not st.session_state.get('user'):
                st.session_state['refresh_token'] = None
                st.session_state['role'] = None
                st.session_state['view_mode'] = None
        raise e

SyncQueryRequestBuilder.execute = _auto_refresh_postgrest_execute


def ensure_valid_session():
    """
    Mantiene la sessione valida e rinfresca automaticamente il JWT prima che scada (3600s).
    """
    if not st.session_state.get('user'):
        return False
    try:
        now = time.time()
        sess = supabase.auth.get_session()

        rt = st.session_state.get('refresh_token')
        if not rt and sess and hasattr(sess, 'refresh_token') and sess.refresh_token:
            rt = sess.refresh_token
        if not rt and hasattr(st, 'context') and hasattr(st.context, 'cookies'):
            rt = st.context.cookies.get('m0v3_rt')

        # Se la sessione è scaduta o scade a breve (entro 120s), rinfresca preventivamente
        needs_refresh = False
        is_already_expired = False
        if sess and hasattr(sess, 'expires_at') and sess.expires_at:
            if sess.expires_at <= now:
                is_already_expired = True
                needs_refresh = True
            elif sess.expires_at <= (now + 120):
                needs_refresh = True
        elif not sess or not hasattr(sess, 'access_token') or not sess.access_token:
            needs_refresh = True

        if needs_refresh:
            refreshed = False
            if rt:
                try:
                    new_auth = supabase.auth.refresh_session(rt)
                    if new_auth and hasattr(new_auth, 'session') and new_auth.session:
                        sess = new_auth.session
                        st.session_state['refresh_token'] = sess.refresh_token
                        if hasattr(new_auth, 'user') and new_auth.user:
                            st.session_state['user'] = new_auth.user
                        refreshed = True
                except Exception:
                    pass

            if not refreshed and is_already_expired:
                # Token già scaduto e non rinfrescabile
                st.session_state['user'] = None
                st.session_state['refresh_token'] = None
                st.session_state['role'] = None
                st.warning("Sessione scaduta. Effettua nuovamente il login per accedere.")
                st.rerun()
                return False

        if sess and hasattr(sess, 'access_token') and sess.access_token:
            supabase.postgrest.auth(sess.access_token)
            if 'sb_client' in st.session_state:
                st.session_state['sb_client'].postgrest.auth(sess.access_token)
        return True
    except Exception:
        return True


STANDARD_TIPOLOGIE_SESSIONE = [
    "Match",
    "Torneo",
    "Match Doppio",
    "Tecnica",
    "Fisica",
    "Recupero"
]

CANONICAL_COBOLLI_TIPOLOGIE = [
    "Tennis Base",
    "1000 Palle",
    "Tennis Match",
    "500 palle",
    "Servizio",
    "Torneo",
    "Match",
    "Match Doppio",
    "Workout",
    "Calcio"
]

CANONICAL_TIPOLOGIE_SESSIONE = list(CANONICAL_COBOLLI_TIPOLOGIE)

COLORI_TIPOLOGIE_SESSIONE = {
    "Tennis Base": "#0ea5e9",
    "1000 Palle": "#0d9488",
    "Tennis Match": "#6366f1",
    "500 palle": "#8b5cf6",
    "Servizio": "#0891b2",
    "Torneo": "#f59e0b",
    "Match": "#ef4444",
    "Match Doppio": "#ea580c",
    "Workout": "#10b981",
    "Calcio": "#84cc16",
    "Tecnica": "#0ea5e9",
    "Fisica": "#10b981",
    "Recupero": "#8b5cf6",
}

def get_tipologia_badge_style(s_tipo):
    low = str(s_tipo).strip().lower()
    styles = {
        "tennis base": ("#e0f2fe", "#0284c7"),
        "1000 palle": ("#ccfbf1", "#0f766e"),
        "tennis match": ("#ede9fe", "#6d28d9"),
        "500 palle": ("#e0e7ff", "#4338ca"),
        "servizio": ("#cffafe", "#0891b2"),
        "torneo": ("#fef3c7", "#b45309"),
        "match": ("#fee2e2", "#dc2626"),
        "match doppio": ("#ffedd5", "#c2410c"),
        "workout": ("#dcfce7", "#15803d"),
        "calcio": ("#ecfccb", "#4d7c0f"),
        "tecnica": ("#e0f2fe", "#0284c7"),
        "fisica": ("#dcfce7", "#166534"),
        "recupero": ("#f3e8ff", "#7e22ce"),
    }
    return styles.get(low, ("#f1f5f9", "#334155"))

def get_tipologie_sessione(uploader_email=None, atleta_nome=None):
    # Rilevamento contesto atleta (Flavio Cobolli vs altri atleti)
    ath = atleta_nome
    if not ath and 'st' in globals() and hasattr(st, 'session_state'):
        ath = st.session_state.get('selected_athlete')
    
    is_cobolli = False
    if ath:
        # Se l'atleta e' specificato esplicitamente, valutiamo solo il suo nome
        if "cobolli" in str(ath).lower():
            is_cobolli = True
        else:
            is_cobolli = False
    elif uploader_email:
        # Solo come fallback secondario se nessun atleta e' specificato
        try:
            df = load_local_database()
            if not df.empty and 'Uploader_Email' in df.columns and 'Players' in df.columns:
                u_df = df[df['Uploader_Email'] == uploader_email]
                atleti_u = [str(p).lower() for p in u_df['Players'].dropna().unique()]
                if atleti_u and all("cobolli" in p for p in atleti_u):
                    is_cobolli = True
        except Exception:
            pass

    cobolli_only_lower = {
        tp.lower().strip() for tp in CANONICAL_COBOLLI_TIPOLOGIE 
        if tp not in STANDARD_TIPOLOGIE_SESSIONE
    }

    if is_cobolli:
        # Per Flavio Cobolli: le 10 tipologie specifiche + quelle standard
        base_types = list(CANONICAL_COBOLLI_TIPOLOGIE)
        for std in STANDARD_TIPOLOGIE_SESSIONE:
            if std not in base_types:
                base_types.append(std)
    else:
        # Per tutti gli altri atleti: le tipologie standard del tennis
        base_types = list(STANDARD_TIPOLOGIE_SESSIONE)

    df = load_local_database()
    if not df.empty and 'Tipologia Sessione' in df.columns:
        # Raccoglie le tipologie associate all'atleta (o all'uploader)
        if ath and 'Players' in df.columns:
            scoped_df = df[df['Players'] == ath]
            if uploader_email and 'Uploader_Email' in df.columns:
                scoped_df = scoped_df[scoped_df['Uploader_Email'] == uploader_email]
        elif uploader_email and 'Uploader_Email' in df.columns:
            scoped_df = df[df['Uploader_Email'] == uploader_email]
        else:
            scoped_df = df

        custom_types = list(scoped_df['Tipologia Sessione'].dropna().unique())

        for c_type in custom_types:
            c_str = str(c_type).strip()
            # Esclude tassativamente le tipologie specifiche di Cobolli per altri atleti
            if not is_cobolli and c_str.lower() in cobolli_only_lower:
                continue
            if c_str and c_str not in base_types and c_str != "Non definita":
                base_types.append(c_str)
    return base_types

def converti_durata_in_minuti(val, force_seconds=False):
    if pd.isna(val):
        return pd.NA
    val_str = str(val).strip()
    if not val_str or val_str.lower() == 'nan':
        return pd.NA

    val_low = val_str.lower()
    # Gestione suffissi espliciti (es. "5400 s", "5400 sec", "90 min", "1.5 h")
    sec_match = re.match(r'^([0-9]+(?:[.,][0-9]+)?)\s*(?:s|sec|secs|secondi|seconds)$', val_low)
    if sec_match:
        return float(sec_match.group(1).replace(',', '.')) / 60.0
    hr_match = re.match(r'^([0-9]+(?:[.,][0-9]+)?)\s*(?:h|hr|hrs|ora|ore|hours)$', val_low)
    if hr_match:
        return float(hr_match.group(1).replace(',', '.')) * 60.0
    min_match = re.match(r'^([0-9]+(?:[.,][0-9]+)?)\s*(?:m|min|mins|minuti|minutes)$', val_low)
    if min_match:
        return float(min_match.group(1).replace(',', '.'))

    try:
        num = float(val_str.replace(',', '.'))
        # Se la colonna sorgente indica esplicitamente secondi (force_seconds=True)
        # oppure se il valore supera 300 minuti (5 ore), converti da secondi a minuti.
        if force_seconds or num > 300:
            return num / 60.0
        return num
    except ValueError:
        parts = val_str.split(':')
        try:
            if len(parts) == 2:
                p0 = float(parts[0].replace(',', '.'))
                p1 = float(parts[1].replace(',', '.'))
                # Se la prima parte è <= 5 (es. 01:30 = 1h30m, 02:15 = 2h15m, 00:45 = 45m),
                # il formato esportato dal software GPS è HH:MM.
                # Se la prima parte è > 5 (es. 55:30, 89:56), il formato è MM:SS.
                if p0 <= 5 and (p0 > 0 or p1 >= 10):
                    return p0 * 60.0 + p1
                return p0 + p1 / 60.0
            elif len(parts) == 3:
                p0 = float(parts[0].replace(',', '.'))
                p1 = float(parts[1].replace(',', '.'))
                p2 = float(parts[2].replace(',', '.'))
                return p0 * 60.0 + p1 + p2 / 60.0
        except ValueError:
            return pd.NA
        return pd.NA


def to_float_series(series):
    """Converte in modo sicuro una Series in float, gestendo virgole decimali, % e stringhe sporche."""
    if series is None:
        return pd.Series(dtype=float)
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors='coerce').fillna(0.0).astype(float)
    cleaned = (
        series.astype(str)
        .str.strip()
        .str.replace('%', '', regex=False)
        .str.replace(',', '.', regex=False)
    )
    return pd.to_numeric(cleaned, errors='coerce').fillna(0.0).astype(float)


def leggi_csv_gps_robusto(file_obj):
    """Legge un file CSV GPS gestendo automaticamente separatori ';' o ',' e pulendo le intestazioni."""
    if hasattr(file_obj, 'seek'):
        file_obj.seek(0)
    try:
        df = pd.read_csv(file_obj, sep=';')
        if df.shape[1] <= 1:
            if hasattr(file_obj, 'seek'):
                file_obj.seek(0)
            df = pd.read_csv(file_obj, sep=',')
    except Exception:
        if hasattr(file_obj, 'seek'):
            file_obj.seek(0)
        df = pd.read_csv(file_obj, sep=None, engine='python')

    df.columns = [str(c).strip() for c in df.columns]
    # Rimuovi colonne Unnamed completamente vuote e righe interamente vuote
    unnamed_empty = [c for c in df.columns if c.startswith('Unnamed:') and df[c].isna().all()]
    if unnamed_empty:
        df.drop(columns=unnamed_empty, inplace=True)
    df.dropna(how='all', inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def valuta_formula_mappatura(df_raw, formula_str):
    """
    Valuta in sicurezza una formula di mappatura CSV (es. '=[Colonna 1] + [Colonna 2] / 2').
    Converte prima ogni colonna referenziata tra [...] in float (gestendo '.' e ',') e la
    associa a una variabile temporanea pulita (_c0, _c1, ...), così i caratteri speciali
    nei nomi colonna (>, <, %, /, °, →, parentesi) non mandano mai in crash l'interprete.
    Restituisce (Series_risultato, lista_colonne_mancanti, messaggio_errore).
    """
    expr = str(formula_str).strip()
    if expr.startswith('='):
        expr = expr[1:].strip()
    if not expr:
        return pd.Series(0.0, index=df_raw.index), [], "Formula vuota"

    col_map_strip = {str(c).strip(): c for c in df_raw.columns}
    referenced_cols = re.findall(r'\[([^\]]+)\]', expr)
    local_env = {}
    missing_cols = []
    safe_expr = expr

    for idx_c, col_ref in enumerate(referenced_cols):
        var_name = f"_c{idx_c}"
        col_clean = col_ref.strip()
        actual_col = col_ref if col_ref in df_raw.columns else col_map_strip.get(col_clean)
        if actual_col is not None and actual_col in df_raw.columns:
            local_env[var_name] = to_float_series(df_raw[actual_col])
        else:
            missing_cols.append(col_ref)
            local_env[var_name] = pd.Series(0.0, index=df_raw.index)
        safe_expr = safe_expr.replace(f"[{col_ref}]", var_name, 1)

    # Eventuali costanti decimali scritte con la virgola nella formula (es. * 1,5)
    safe_expr = safe_expr.replace(',', '.')

    try:
        res = eval(safe_expr, {"__builtins__": {}, "abs": abs, "round": round, "min": min, "max": max}, local_env)
        if isinstance(res, pd.Series):
            res_series = pd.to_numeric(res, errors='coerce').fillna(0.0).astype(float)
        else:
            res_series = pd.Series(float(res), index=df_raw.index, dtype=float)
        return res_series, missing_cols, None
    except Exception as e:
        return pd.Series(0.0, index=df_raw.index), missing_cols, str(e)


def applica_mappatura_csv(df_raw, mappa_utente=None):
    """
    Applica la mappatura CSV di un utente a un DataFrame grezzo, restituendo
    (df_mappato, report_mappatura) dove df_mappato contiene esclusivamente COLONNE_STANDARD
    pulite e tipizzate, e report_mappatura contiene lo stato di ogni parametro.
    """
    if mappa_utente is None:
        mappa_utente = {}
    df_out = pd.DataFrame(index=df_raw.index)
    col_map_strip = {str(c).strip(): c for c in df_raw.columns}
    report = {}

    for col_std in COLONNE_STANDARD:
        regola = mappa_utente.get(col_std)
        is_text_col = col_std in ("Date", "Session", "Players")

        if regola and str(regola).strip().startswith('='):
            res_s, missing_c, err_msg = valuta_formula_mappatura(df_raw, regola)
            df_out[col_std] = res_s
            if err_msg:
                report[col_std] = {"status": "error", "source": regola, "detail": f"Errore formula: {err_msg}"}
            elif missing_c:
                report[col_std] = {"status": "warning", "source": regola, "detail": f"Colonne assenti nel CSV: {', '.join(missing_c)}"}
            else:
                report[col_std] = {"status": "ok", "source": regola, "detail": "Formula calcolata"}
        elif regola and regola != "Non presente":
            reg_clean = str(regola).strip()
            actual_col = regola if regola in df_raw.columns else col_map_strip.get(reg_clean)
            if actual_col is not None and actual_col in df_raw.columns:
                df_out[col_std] = df_raw[actual_col]
                report[col_std] = {"status": "ok", "source": actual_col, "detail": "Colonna mappata"}
            elif col_std in col_map_strip:
                df_out[col_std] = df_raw[col_map_strip[col_std]]
                report[col_std] = {"status": "fallback", "source": col_map_strip[col_std], "detail": f"'{regola}' assente, usata colonna standard"}
            else:
                df_out[col_std] = pd.NA if is_text_col else 0.0
                report[col_std] = {"status": "missing", "source": regola, "detail": f"Colonna '{regola}' non trovata nel CSV"}
        else:
            if col_std in col_map_strip:
                df_out[col_std] = df_raw[col_map_strip[col_std]]
                report[col_std] = {"status": "auto", "source": col_map_strip[col_std], "detail": "Colonna standard rilevata"}
            else:
                df_out[col_std] = pd.NA if is_text_col else 0.0
                report[col_std] = {"status": "unmapped", "source": "Non presente", "detail": "Non mappato"}

    # Pulizia e tipizzazione colonne standard
    if 'Minuti' in df_out.columns:
        reg_min = str(mappa_utente.get('Minuti', '')).lower()
        is_sec_col = any(k_s in reg_min for k_s in ('sec', '(s)', '_s')) and not reg_min.startswith('=')
        df_out['Minuti'] = df_out['Minuti'].apply(lambda v: converti_durata_in_minuti(v, force_seconds=is_sec_col))
        df_out['Minuti'] = pd.to_numeric(df_out['Minuti'], errors='coerce').fillna(0.0).round(1)

    for c_num in COLONNE_NUMERICHE_STANDARD:
        if c_num in df_out.columns:
            df_out[c_num] = to_float_series(df_out[c_num]).round(2)

    return df_out, report


def pulisci_dataframe_database(df):
    """Mantiene solo le colonne canoniche M0V3 + metadati, garantendo tipi numerici e date pulite."""
    if df is None or df.empty:
        return pd.DataFrame(columns=COLONNE_DATABASE)
    df_c = df.copy()
    for c_std in COLONNE_DATABASE:
        if c_std not in df_c.columns:
            if c_std == 'Dato_Simulato':
                df_c[c_std] = False
            elif c_std in COLONNE_NUMERICHE_STANDARD or c_std in ('Minuti', 'Minuti Sparring'):
                df_c[c_std] = 0.0
            else:
                df_c[c_std] = ""

    if 'Dato_Simulato' in df_c.columns:
        df_c['Dato_Simulato'] = df_c['Dato_Simulato'].apply(
            lambda x: str(x).strip().lower() in ('true', '1', 'yes', 'vero') if not isinstance(x, bool) else x
        )
    if 'Minuti' in df_c.columns:
        df_c['Minuti'] = df_c['Minuti'].apply(converti_durata_in_minuti)
        df_c['Minuti'] = pd.to_numeric(df_c['Minuti'], errors='coerce').fillna(0.0).round(1)
    if 'Minuti Sparring' in df_c.columns:
        df_c['Minuti Sparring'] = to_float_series(df_c['Minuti Sparring']).round(0).astype(int)
    for c_num in COLONNE_NUMERICHE_STANDARD:
        df_c[c_num] = to_float_series(df_c[c_num]).round(2)

    if 'Date' in df_c.columns:
        parsed_d = pd.to_datetime(df_c['Date'], dayfirst=True, errors='coerce')
        df_c['Date'] = parsed_d.dt.strftime('%d/%m/%Y').fillna(df_c['Date'].astype(str))

    return df_c[COLONNE_DATABASE]


def _get_db_mtime_token():
    """Genera un token basato sull'ultimo timestamp di modifica tra CSV e Parquet."""
    m_csv = os.path.getmtime(DB_PATH) if os.path.exists(DB_PATH) else 0.0
    m_parq = os.path.getmtime(DB_PARQUET_PATH) if os.path.exists(DB_PARQUET_PATH) else 0.0
    return max(m_csv, m_parq)


@st.cache_data(ttl=300, show_spinner=False)
def _load_database_cached(_token):
    """
    Caricamento database ad alte prestazioni con cache RAM e accelerazione Parquet:
    - Se esiste il file Parquet aggiornato, lo carica in pochi millisecondi.
    - Se esiste solo il CSV o il CSV è più recente, carica il CSV, lo pulisce e genera il Parquet.
    - Garantisce sempre la presenza della colonna Date_obj pre-calcolata per eliminare ricalcoli nei moduli.
    """
    df = pd.DataFrame()
    p_exists = os.path.exists(DB_PARQUET_PATH)
    c_exists = os.path.exists(DB_PATH)

    # 1. Prova prima il formato Parquet se aggiornato
    if p_exists:
        try:
            m_parq = os.path.getmtime(DB_PARQUET_PATH)
            m_csv = os.path.getmtime(DB_PATH) if c_exists else 0.0
            if m_parq >= m_csv:
                df = pd.read_parquet(DB_PARQUET_PATH)
        except Exception:
            df = pd.DataFrame()

    # 2. Se Parquet non presente o fallito, leggi dal CSV
    if (df is None or df.empty) and c_exists:
        try:
            df_raw = pd.read_csv(DB_PATH, low_memory=False)
            if not df_raw.empty:
                df = pulisci_dataframe_database(df_raw)
                # Salva Parquet per accelerare tutte le letture future
                try:
                    df.to_parquet(DB_PARQUET_PATH, index=False)
                except Exception:
                    pass
        except Exception:
            df = pd.DataFrame()

    if df is None or df.empty:
        return pd.DataFrame(columns=COLONNE_DATABASE + ['Date_obj'])

    # 3. Assicura Date_obj e Date_dt pre-calcolate per tutti i moduli dell'app
    if 'Date_obj' not in df.columns:
        if 'Date' in df.columns:
            df['Date_obj'] = pd.to_datetime(df['Date'], format='%d/%m/%Y', errors='coerce')
        else:
            df['Date_obj'] = pd.NaT

    if 'Date_dt' not in df.columns:
        df['Date_dt'] = pd.to_datetime(df['Date_obj'], errors='coerce').dt.date

    return df


def clear_database_cache():
    """Invalida la cache RAM del database per forzare la rilettura istantanea."""
    try:
        _load_database_cached.clear()
    except Exception:
        pass


def load_local_database():
    """Restituisce una copia protetta del database storico caricato ad alta velocità dalla cache RAM."""
    token = _get_db_mtime_token()
    df_cached = _load_database_cached(token)
    return df_cached.copy() if df_cached is not None else pd.DataFrame(columns=COLONNE_DATABASE + ['Date_obj'])


def save_local_database(df):
    """Salva il database contemporaneamente in Parquet (ultra-rapido) e CSV (interoperabile) e aggiorna la cache."""
    df_clean = pulisci_dataframe_database(df)
    
    # 1. Salvataggio Parquet (ottimizzato e compresso)
    try:
        df_clean.to_parquet(DB_PARQUET_PATH, index=False)
    except Exception:
        pass

    # 2. Salvataggio CSV (compatibilità retroattiva ed export)
    try:
        df_clean.to_csv(DB_PATH, index=False)
    except Exception:
        pass

    # 3. Invalida la cache per riflettere le modifiche all'istante
    clear_database_cache()

def get_val(row, key, default=0):
    val = row.get(key, default)
    if pd.isna(val) or str(val).lower() == 'nan' or val == '': return default
    try: return float(val)
    except: return default

def calcola_delta_percentuale(valore_attuale, valore_medio):
    if pd.isna(valore_medio) or valore_medio == 0 or pd.isna(valore_attuale): return 0.0
    return ((valore_attuale - valore_medio) / valore_medio) * 100

def formatta_delta(delta, size=14):
    """Delta rispetto alla media: colore neutro, la freccia indica la direzione."""
    if pd.isna(delta) or round(delta) == 0:
        return f"<span style='color:#94a3b8; font-weight:700; font-size:{size}px;'>0%</span>"
    if delta > 0:
        return f"<span style='color:#0369a1; font-weight:700; font-size:{size}px;'>▲ +{delta:.0f}%</span>"
    return f"<span style='color:#64748b; font-weight:700; font-size:{size}px;'>▼ {delta:.0f}%</span>"

# --- Readiness: un'unica regola di colore per tutta l'app (stessa soglie della Home) ---
LEGENDA_ACWR = "Verde: 80-125% della media  |  Blu: sotto 80%  |  Rosso: sopra 125%"

def get_color(pct):
    if pd.isna(pct) or pct == 0: return "#f1f5f9", "#94a3b8"
    if pct < 80:   return "#e0f2fe", "#075985"
    if pct <= 125: return "#dcfce7", "#166534"
    return "#fee2e2", "#991b1b"

def get_bar_label(diff):
    if diff > 25: col = "#dc2626"
    elif diff < -20: col = "#0284c7"
    else: col = "#16a34a"
    pct_raggiunta = max(0.0, 100.0 + diff)
    if diff > 0:
        testo = tr("sopra la media", "above average")
    elif diff < 0:
        testo = tr("sotto la media", "below average")
    else:
        testo = tr("in media", "average")
    return f"<span style='color:{col}; font-weight:900;'>{pct_raggiunta:.0f}%</span> <span style='font-size:13px; font-weight:700; color:{col};'>({diff:+.0f}%)</span> <span style='font-size:12px; font-weight:normal; color:#64748b;'>{testo}</span>"

get_color_bt = get_color
get_bar_label_bt = get_bar_label

def calcola_work_rate_acwr(val_win, val_avg):
    """Calcola il Work Rate ACWR (% raggiunta e differenza %) come media delle 5 metriche al minuto."""
    min_w = float(val_win.get('Minuti', 0))
    min_a = float(val_avg.get('Minuti', 0))
    if min_w <= 0 or min_a <= 0:
        return 0.0, 0.0
    metriche_pm = ['Training Load', 'TL_High', 'High Accel IMU', 'High Decel IMU', 'Azioni Int. IMU >2']
    pcts = []
    for m in metriche_pm:
        rw = float(val_win.get(m, 0)) / min_w
        ra = float(val_avg.get(m, 0)) / min_a
        pcts.append((rw / ra * 100.0) if ra > 0 else 0.0)
    pct_wr = sum(pcts) / len(pcts)
    return pct_wr, pct_wr - 100.0


def render_acwr_executive_block(
    val_acute,
    val_chronic,
    str_win_range,
    str_base_range,
    lbl_hdr_acute,
    lbl_hdr_chronic,
    lbl_ctx_acute,
    lbl_vs,
    chart_key,
    title_banner=None,
    title_accent="#0f172a",
):
    """Renderizza il blocco Executive ACWR M0V3:
    1. Tabella unificata a 6 parametri con badge VOLUME/HIGH INTENSITY, % Raggiunta + Delta con segno e barra con tacca 100%
    2. Radar Esagonale geometrico (80%, 100%, 125%, 150%) con legenda HTML dedicata sotto
    3. 3 Scorecard Semantiche (Indice Volume, Indice Alta Intensità, Work Rate)
    4. Expander ispezionabile con il dettaglio dei 5 parametri al minuto del Work Rate
    """
    col_acwr = ['Minuti', 'Training Load', 'TL_High', 'High Decel IMU', 'High Accel IMU', 'Azioni Int. IMU >2']

    def _acwr_zone_meta(pct_v):
        if pct_v <= 0:
            return "#f1f5f9", "#64748b", "#94a3b8", tr("NESSUN DATO", "NO DATA")
        if pct_v < 80:
            return "#e0f2fe", "#0284c7", "#0ea5e9", tr("LOW ZONE (<80%)", "LOW ZONE (<80%)")
        if pct_v <= 125:
            return "#dcfce7", "#166534", "#10b981", tr("OPTIMAL ZONE (80-125%)", "OPTIMAL ZONE (80-125%)")
        if pct_v <= 150:
            return "#fef3c7", "#b45309", "#f59e0b", tr("HIGH ZONE (125-150%)", "HIGH ZONE (125-150%)")
        return "#fee2e2", "#991b1b", "#ef4444", tr("OVERLOAD ZONE (>150%)", "OVERLOAD ZONE (>150%)")

    def _render_acwr_progress(pct_v, bar_col):
        fill_w = min(100.0, max(0.0, (pct_v / 160.0) * 100.0))
        return (
            "<div style='width:100%; height:18px; background:#f8fafc; border:1px solid #e2e8f0; border-radius:6px; position:relative; overflow:hidden;'>"
            f"<div style='position:absolute; left:0; top:2px; bottom:2px; width:{fill_w:.1f}%; background:{bar_col}; border-radius:4px;'></div>"
            "<div style='position:absolute; left:62.5%; top:0; bottom:0; width:2px; background:#0f172a; z-index:3;' title='100% Baseline'></div>"
            "</div>"
        )

    pct_acwr = {}
    diff_acwr = {}
    for c_a in col_acwr:
        v_ch_val = float(val_chronic.get(c_a, 0))
        v_ac_val = float(val_acute.get(c_a, 0))
        if v_ch_val > 0:
            p_v = (v_ac_val / v_ch_val) * 100.0
            pct_acwr[c_a] = p_v
            diff_acwr[c_a] = p_v - 100.0
        else:
            pct_acwr[c_a] = 0.0
            diff_acwr[c_a] = 0.0

    parametri_acwr_rows = [
        ("Minuti", tr("Durata (Time)", "Duration (Time)"), "VOLUME", "#0284c7", "#e0f2fe"),
        ("Training Load", "Training Load", "VOLUME", "#0284c7", "#e0f2fe"),
        ("TL_High", "Training Load High", "HIGH INTENSITY", "#dc2626", "#fee2e2"),
        ("High Decel IMU", tr("Decelerazioni Intense IMU", "High Decelerations Events"), "HIGH INTENSITY", "#dc2626", "#fee2e2"),
        ("High Accel IMU", tr("Accelerazioni Intense IMU", "High Accelerations Events"), "HIGH INTENSITY", "#dc2626", "#fee2e2"),
        ("Azioni Int. IMU >2", tr('Azioni Intense >2"', 'Mid/High Actions >2" Events'), "VOLUME", "#0284c7", "#e0f2fe"),
    ]

    lbl_hdr_param = tr("Parametro & Area", "Parameter & Area")
    lbl_hdr_pct = tr("% Raggiunta (Scostamento)", "Percentage Reached (Delta)")
    lbl_hdr_bar = tr("Fascia ACWR (Tacca = 100%)", "ACWR Zone (Tick = 100%)")
    lbl_ctx_chronic = tr("Baseline Cronica (28 gg prec.)", "Chronic Baseline (Prev. 28d)")

    banner_html = ""
    if title_banner:
        banner_html = (
            f"<div style='background:#0f172a; border-bottom:2px solid {title_accent}; padding:13px 18px; display:flex; justify-content:space-between; align-items:center;'>"
            f"<span style='color:white; font-weight:900; font-size:15px; text-transform:uppercase; letter-spacing:0.8px;'>{title_banner}</span>"
            f"<span style='background:rgba(255,255,255,0.1); color:#38bdf8; font-size:11px; font-weight:800; padding:4px 10px; border-radius:6px;'>{str_win_range}</span>"
            "</div>"
        )

    html_acwr_tbl = (
        "<div style='background:white; border:1px solid #e2e8f0; border-radius:12px; overflow:hidden; box-shadow:0 2px 6px -1px rgba(15,23,42,0.04); margin-bottom:20px; font-family:\"Inter\", sans-serif;'>"
        f"{banner_html}"
        "<div style='background:#f8fafc; border-bottom:1px solid #e2e8f0; padding:10px 16px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;'>"
        f"<div style='font-size:12px; color:#334155;'><b>{lbl_ctx_acute}:</b> <span style='color:#0ea5e9; font-weight:800;'>{str_win_range}</span></div>"
        f"<div style='font-size:12px; color:#64748b;'><b>{lbl_ctx_chronic}:</b> {str_base_range}</div>"
        "</div>"
        "<table style='width:100%; border-collapse:collapse;'>"
        "<tr style='background:#f8fafc; border-bottom:2px solid #e2e8f0;'>"
        f"<th style='text-align:left; padding:12px 14px; font-size:11px; font-weight:700; color:#64748b; text-transform:uppercase; letter-spacing:0.5px; width:28%;'>{lbl_hdr_param}</th>"
        f"<th style='text-align:center; padding:12px 14px; font-size:11px; font-weight:700; color:#0f172a; text-transform:uppercase; letter-spacing:0.5px; width:16%;'>{lbl_hdr_acute}</th>"
        f"<th style='text-align:center; padding:12px 14px; font-size:11px; font-weight:700; color:#64748b; text-transform:uppercase; letter-spacing:0.5px; width:18%;'>{lbl_hdr_chronic}</th>"
        f"<th style='text-align:center; padding:12px 14px; font-size:11px; font-weight:800; color:#0ea5e9; text-transform:uppercase; letter-spacing:0.5px; width:20%;'>{lbl_hdr_pct}</th>"
        f"<th style='text-align:center; padding:12px 14px; font-size:11px; font-weight:700; color:#64748b; text-transform:uppercase; letter-spacing:0.5px; width:18%;'>{lbl_hdr_bar}</th>"
        "</tr>"
    )

    for col_key, label_p, cat_tag, cat_fg, cat_bg in parametri_acwr_rows:
        v_ac = float(val_acute.get(col_key, 0))
        v_ch = float(val_chronic.get(col_key, 0))
        p_ac = pct_acwr[col_key]
        d_ac = diff_acwr[col_key]
        z_bg, z_fg, z_bar, _ = _acwr_zone_meta(p_ac)
        delta_str = f"{d_ac:+.0f}%" if v_ch > 0 else "N/A"
        html_acwr_tbl += (
            "<tr style='border-bottom:1px solid #f1f5f9;'>"
            f"<td style='padding:14px 14px;'>"
            f"<div style='font-weight:700; color:#0f172a; font-size:14px;'>{label_p}</div>"
            f"<span style='display:inline-block; margin-top:3px; background:{cat_bg}; color:{cat_fg}; font-size:9px; font-weight:800; padding:2px 7px; border-radius:4px; letter-spacing:0.5px;'>{cat_tag}</span>"
            "</td>"
            f"<td style='padding:14px 14px; text-align:center; font-weight:900; font-size:20px; color:#0f172a;'>{v_ac:.0f}</td>"
            f"<td style='padding:14px 14px; text-align:center; font-weight:700; font-size:17px; color:#64748b;'>{v_ch:.0f}</td>"
            f"<td style='padding:14px 14px; text-align:center;'>"
            f"<span style='background:{z_bg}; color:{z_fg}; padding:5px 12px; border-radius:8px; font-weight:900; font-size:18px; display:inline-block;'>{p_ac:.0f}%</span>"
            f"<div style='font-size:11px; font-weight:700; color:{z_fg}; margin-top:4px;'>({delta_str} {lbl_vs})</div>"
            "</td>"
            f"<td style='padding:14px 14px;'>{_render_acwr_progress(p_ac, z_bar)}</td>"
            "</tr>"
        )

    html_acwr_tbl += "</table></div>"
    st.markdown(html_acwr_tbl, unsafe_allow_html=True)

    # 2. CALCOLO DEI 3 INDICI SINTETICI (VOLUME, ALTA INTENSITÀ, WORK RATE)
    has_chronic = any(float(val_chronic.get(c, 0)) > 0 for c in col_acwr)
    pct_vol_w = (pct_acwr['Minuti'] + pct_acwr['Training Load'] + pct_acwr['Azioni Int. IMU >2']) / 3.0 if has_chronic else 0.0
    diff_vol_w = pct_vol_w - 100.0 if has_chronic else 0.0

    pct_hi_w = (pct_acwr['TL_High'] + pct_acwr['High Decel IMU'] + pct_acwr['High Accel IMU']) / 3.0 if has_chronic else 0.0
    diff_hi_w = pct_hi_w - 100.0 if has_chronic else 0.0

    pct_wr_w, diff_wr_w = calcola_work_rate_acwr(val_acute, val_chronic)

    # 3. GRAFICO A ESAGONO GEOMETRICO + 3 CARD INDICI A DESTRA
    col_hex_w, col_idx_w = st.columns([1.25, 1], gap="medium")

    with col_hex_w:
        with st.container(border=True):
            lbl_hex_title = tr("Profilo Esagonale ACWR (% Raggiunta per Parametro)", "Hexagonal ACWR Profile (Percentage Reached by Area)")
            st.markdown(f"<div style='font-size:13px; font-weight:800; color:#0f172a; text-transform:uppercase; letter-spacing:0.6px; margin-bottom:4px;'>{lbl_hex_title}</div>", unsafe_allow_html=True)

            hex_cols = ['Minuti', 'Training Load', 'TL_High', 'High Decel IMU', 'High Accel IMU', 'Azioni Int. IMU >2']
            hex_names = [
                tr("Durata", "Time"),
                "Training Load",
                "TL High",
                tr("High Decel", "High Decel"),
                tr("High Accel", "High Accel"),
                tr('Azioni >2"', 'Actions >2"')
            ]
            r_vals = [pct_acwr[k] for k in hex_cols]
            theta_labels = []
            for nm, k in zip(hex_names, hex_cols):
                p_v = pct_acwr[k]
                d_v = diff_acwr[k]
                _, z_fg, _, _ = _acwr_zone_meta(p_v)
                d_txt = f"{d_v:+.0f}%" if float(val_chronic.get(k, 0)) > 0 else "N/A"
                theta_labels.append(f"<b>{nm}</b><br><span style='color:{z_fg}; font-size:12px;'><b>{p_v:.0f}%</b> ({d_txt})</span>")

            r_closed = r_vals + [r_vals[0]]
            theta_closed = theta_labels + [theta_labels[0]]
            max_r_hex = max(160.0, max(r_vals) + 20.0) if r_vals else 160.0

            fig_hex = go.Figure()
            fig_hex.add_trace(go.Scatterpolar(
                r=[80]*7, theta=theta_closed, mode='lines',
                line=dict(color='#38bdf8', width=1.5, dash='dot'),
                name=tr('Low Zone (80%)', 'Low Zone (80%)'), hoverinfo='skip'
            ))
            fig_hex.add_trace(go.Scatterpolar(
                r=[100]*7, theta=theta_closed, mode='lines',
                line=dict(color='#10b981', width=2.5),
                name=tr('Baseline 28 gg (100%)', '28d Baseline (100%)'), hoverinfo='skip'
            ))
            fig_hex.add_trace(go.Scatterpolar(
                r=[125]*7, theta=theta_closed, mode='lines',
                line=dict(color='#f59e0b', width=1.5, dash='dot'),
                name=tr('High Zone (125%)', 'High Zone (125%)'), hoverinfo='skip'
            ))
            fig_hex.add_trace(go.Scatterpolar(
                r=[150]*7, theta=theta_closed, mode='lines',
                line=dict(color='#ef4444', width=1.5, dash='dot'),
                name=tr('Overload Zone (150%)', 'Overload Zone (150%)'), hoverinfo='skip'
            ))
            fig_hex.add_trace(go.Scatterpolar(
                r=r_closed, theta=theta_closed,
                mode='lines+markers',
                fill='toself',
                fillcolor='rgba(15, 23, 42, 0.16)',
                line=dict(color='#0f172a', width=3.5),
                marker=dict(size=8, color='#0f172a', line=dict(color='white', width=1.5)),
                name=tr('% Raggiunta', 'Percentage Reached'),
                hovertemplate="%{theta}<br>ACWR: <b>%{r:.0f}%</b><extra></extra>"
            ))

            fig_hex.update_layout(
                polar=dict(
                    domain=dict(x=[0.16, 0.84], y=[0.08, 0.92]),
                    gridshape='linear',
                    bgcolor='rgba(0,0,0,0)',
                    angularaxis=dict(
                        tickfont=dict(size=12, color='#0f172a', family='Inter, sans-serif'),
                        rotation=90,
                        direction='clockwise',
                        gridcolor='#e2e8f0',
                        linecolor='#cbd5e1'
                    ),
                    radialaxis=dict(
                        visible=True,
                        range=[0, max_r_hex],
                        tickvals=[50, 80, 100, 125, 150],
                        ticktext=['50%', '80%', '100%', '125%', '150%'],
                        tickfont=dict(size=9, color='#94a3b8'),
                        gridcolor='#f1f5f9',
                        angle=90,
                        tickangle=90
                    )
                ),
                showlegend=False,
                height=410,
                margin=dict(l=30, r=30, t=25, b=25),
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)'
            )
            st.plotly_chart(fig_hex, use_container_width=True, key=chart_key)

            leg_low = tr("Low Zone (80%)", "Low Zone (80%)")
            leg_avg = tr("Baseline (100%)", "Baseline (100%)")
            leg_high = tr("High Zone (125%)", "High Zone (125%)")
            leg_over = tr("Overload (150%)", "Overload (150%)")
            leg_val = tr("% Raggiunta", "% Reached")
            st.markdown(
                "<div style='display:flex; flex-wrap:wrap; justify-content:center; align-items:center; gap:14px; padding:8px 10px; background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; margin-top:4px; font-size:11px; font-weight:600; color:#475569;'>"
                f"<div style='display:flex; align-items:center; gap:5px;'><span style='width:18px; border-top:2px dashed #38bdf8; display:inline-block;'></span>{leg_low}</div>"
                f"<div style='display:flex; align-items:center; gap:5px;'><span style='width:18px; border-top:3px solid #10b981; display:inline-block;'></span>{leg_avg}</div>"
                f"<div style='display:flex; align-items:center; gap:5px;'><span style='width:18px; border-top:2px dashed #f59e0b; display:inline-block;'></span>{leg_high}</div>"
                f"<div style='display:flex; align-items:center; gap:5px;'><span style='width:18px; border-top:2px dashed #ef4444; display:inline-block;'></span>{leg_over}</div>"
                f"<div style='display:flex; align-items:center; gap:5px;'><span style='width:10px; height:10px; border-radius:50%; background:#0f172a; display:inline-block;'></span><b style='color:#0f172a;'>{leg_val}</b></div>"
                "</div>",
                unsafe_allow_html=True
            )

    with col_idx_w:
        def _render_acwr_index_card(title_idx, pct_idx, diff_idx, formula_desc):
            z_bg, z_fg, z_bar, z_lbl = _acwr_zone_meta(pct_idx)
            d_str = f"{diff_idx:+.0f}%" if has_chronic else "N/A"
            return (
                f"<div style='background:white; border:1px solid #e2e8f0; border-left:5px solid {z_bar}; border-radius:12px; padding:16px 18px; margin-bottom:14px; box-shadow:0 2px 6px -1px rgba(15,23,42,0.04); font-family:\"Inter\", sans-serif;'>"
                "<div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;'>"
                f"<span style='font-size:12px; font-weight:800; color:#0f172a; text-transform:uppercase; letter-spacing:0.8px;'>{title_idx}</span>"
                f"<span style='background:{z_bg}; color:{z_fg}; font-size:10px; font-weight:800; padding:3px 9px; border-radius:20px; letter-spacing:0.4px;'>{z_lbl}</span>"
                "</div>"
                "<div style='display:flex; align-items:baseline; gap:10px; margin-bottom:10px;'>"
                f"<span style='font-size:34px; font-weight:900; color:{z_fg}; line-height:1;'>{pct_idx:.0f}%</span>"
                f"<span style='font-size:14px; font-weight:800; color:{z_fg}; background:{z_bg}; padding:2px 8px; border-radius:6px;'>{d_str} {lbl_vs}</span>"
                "</div>"
                f"{_render_acwr_progress(pct_idx, z_bar)}"
                f"<div style='font-size:11px; color:#64748b; margin-top:8px; line-height:1.35;'>{formula_desc}</div>"
                "</div>"
            )

        cards_html = (
            _render_acwr_index_card(
                tr("Indice Volume", "Volume Index"),
                pct_vol_w,
                diff_vol_w,
                tr('Media % tra Durata, Training Load e Azioni Intense >2"', 'Average % of Duration, Training Load, and Intense Actions >2"')
            )
            + _render_acwr_index_card(
                tr("Indice Alta Intensità", "High Intensity Index"),
                pct_hi_w,
                diff_hi_w,
                tr("Media % tra Training Load High, Decelerazioni e Accelerazioni IMU", "Average % of Training Load High, High Decel, and High Accel IMU")
            )
            + _render_acwr_index_card(
                "Work Rate",
                pct_wr_w,
                diff_wr_w,
                tr('Media % dei 5 parametri al minuto: TL/m, TL High/m, Acc/m, Dec/m, Azioni >2"/m', 'Average % of the 5 per-minute metrics: TL/m, TL High/m, Acc/m, Dec/m, Actions >2"/m')
            )
        )
        st.markdown(cards_html, unsafe_allow_html=True)

    with st.expander(tr("Dettaglio Calcolo Work Rate (5 Parametri al Minuto)", "Work Rate Calculation Breakdown (5 Per-Minute Metrics)"), expanded=False):
        min_ac_w = float(val_acute.get('Minuti', 0))
        min_ch_w = float(val_chronic.get('Minuti', 0))
        wr_items = [
            ("Training Load", "Training Load / min"),
            ("TL_High", "Training Load High / min"),
            ("High Accel IMU", "High Accelerations IMU / min"),
            ("High Decel IMU", "High Decelerations IMU / min"),
            ("Azioni Int. IMU >2", tr('Azioni Intense >2" / min', 'Intense Actions >2" / min')),
        ]
        lbl_wr_p = tr("Parametro al Minuto", "Per-Minute Parameter")
        lbl_wr_w = lbl_hdr_acute
        lbl_wr_b = lbl_hdr_chronic
        lbl_wr_d = tr("% Raggiunta (Delta)", "Percentage Reached (Delta)")
        html_wr_det = (
            "<table style='width:100%; border-collapse:collapse; font-family:\"Inter\", sans-serif;'>"
            "<tr style='background:#f8fafc; border-bottom:2px solid #e2e8f0;'>"
            f"<th style='text-align:left; padding:10px 12px; font-size:11px; color:#64748b; text-transform:uppercase;'>{lbl_wr_p}</th>"
            f"<th style='text-align:center; padding:10px 12px; font-size:11px; color:#0f172a; text-transform:uppercase;'>{lbl_wr_w}</th>"
            f"<th style='text-align:center; padding:10px 12px; font-size:11px; color:#64748b; text-transform:uppercase;'>{lbl_wr_b}</th>"
            f"<th style='text-align:center; padding:10px 12px; font-size:11px; color:#0ea5e9; text-transform:uppercase;'>{lbl_wr_d}</th>"
            "</tr>"
        )
        for col_m, lbl_m in wr_items:
            r_w = (float(val_acute.get(col_m, 0)) / min_ac_w) if min_ac_w > 0 else 0.0
            r_b = (float(val_chronic.get(col_m, 0)) / min_ch_w) if min_ch_w > 0 else 0.0
            p_m = (r_w / r_b * 100.0) if r_b > 0 else 0.0
            d_m = p_m - 100.0 if r_b > 0 else 0.0
            z_bg_m, z_fg_m, _, _ = _acwr_zone_meta(p_m)
            d_m_str = f"{d_m:+.0f}%" if r_b > 0 else "N/A"
            html_wr_det += (
                "<tr style='border-bottom:1px solid #f1f5f9;'>"
                f"<td style='padding:10px 12px; font-weight:700; color:#334155; font-size:13px;'>{lbl_m}</td>"
                f"<td style='padding:10px 12px; text-align:center; font-weight:800; color:#0f172a; font-size:14px;'>{r_w:.2f}</td>"
                f"<td style='padding:10px 12px; text-align:center; font-weight:600; color:#64748b; font-size:14px;'>{r_b:.2f}</td>"
                f"<td style='padding:10px 12px; text-align:center;'><span style='background:{z_bg_m}; color:{z_fg_m}; padding:3px 9px; border-radius:6px; font-weight:800; font-size:13px;'>{p_m:.0f}% ({d_m_str})</span></td>"
                "</tr>"
            )
        html_wr_det += "</table>"
        st.markdown(html_wr_det, unsafe_allow_html=True)


def acwr_zone_meta(pct_v):
    """Restituisce (bg_hex, fg_hex, bar_hex, zone_label) in base alla % Raggiunta."""
    if pct_v <= 0:
        return "#f1f5f9", "#64748b", "#94a3b8", tr("NESSUN DATO", "NO DATA")
    if pct_v < 80:
        return "#e0f2fe", "#0284c7", "#0ea5e9", tr("LOW ZONE (<80%)", "LOW ZONE (<80%)")
    if pct_v <= 125:
        return "#dcfce7", "#166534", "#10b981", tr("OPTIMAL ZONE (80-125%)", "OPTIMAL ZONE (80-125%)")
    if pct_v <= 150:
        return "#fef3c7", "#b45309", "#f59e0b", tr("HIGH ZONE (125-150%)", "HIGH ZONE (125-150%)")
    return "#fee2e2", "#991b1b", "#ef4444", tr("OVERLOAD ZONE (>150%)", "OVERLOAD ZONE (>150%)")


def render_pct_progress_bar(pct_v, bar_col=None):
    """Barra di progresso 0..160% con tacca nera sul 100% (62.5% della larghezza)."""
    if bar_col is None:
        _, _, bar_col, _ = acwr_zone_meta(pct_v)
    fill_w = min(100.0, max(0.0, (pct_v / 160.0) * 100.0))
    return (
        "<div style='width:100%; height:18px; background:#f8fafc; border:1px solid #e2e8f0; border-radius:6px; position:relative; overflow:hidden;'>"
        f"<div style='position:absolute; left:0; top:2px; bottom:2px; width:{fill_w:.1f}%; background:{bar_col}; border-radius:4px;'></div>"
        "<div style='position:absolute; left:62.5%; top:0; bottom:0; width:2px; background:#0f172a; z-index:3;' title='100% Baseline'></div>"
        "</div>"
    )


def render_pct_badge_cell(pct_v, diff_v, has_ref=True, lbl_vs=""):
    """Formatta il badge principale % Raggiunta + lo scostamento firmato (+Delta%) sotto."""
    z_bg, z_fg, _, _ = acwr_zone_meta(pct_v if has_ref else 0.0)
    if not has_ref:
        return "<span style='background:#f1f5f9; color:#94a3b8; padding:4px 10px; border-radius:8px; font-weight:800; font-size:14px;'>N/A</span>"
    d_str = f"{diff_v:+.0f}%"
    vs_part = f" {lbl_vs}" if lbl_vs else ""
    return (
        f"<span style='background:{z_bg}; color:{z_fg}; padding:4px 11px; border-radius:8px; font-weight:900; font-size:16px; display:inline-block;'>{pct_v:.0f}%</span>"
        f"<div style='font-size:11px; font-weight:700; color:{z_fg}; margin-top:3px;'>({d_str}{vs_part})</div>"
    )


def render_executive_hexagon_profile(val_cur, val_ref, lbl_ref_legend, lbl_vs, chart_key):
    """Renderizza il blocco a 2 colonne (Esagono 6 parametri + 3 Scorecard Volume, Alta Intensità, Work Rate)."""
    hex_cols = ['Minuti', 'Training Load', 'TL_High', 'High Decel IMU', 'High Accel IMU', 'Azioni Int. IMU >2']
    pct_map = {}
    diff_map = {}
    for c_k in hex_cols:
        vc = float(get_val(val_cur, c_k, 0))
        vr = float(get_val(val_ref, c_k, 0))
        if vr > 0:
            pv = (vc / vr) * 100.0
            pct_map[c_k] = pv
            diff_map[c_k] = pv - 100.0
        else:
            pct_map[c_k] = 0.0
            diff_map[c_k] = 0.0

    has_ref = any(float(get_val(val_ref, c_k, 0)) > 0 for c_k in hex_cols)
    pct_vol = (pct_map['Minuti'] + pct_map['Training Load'] + pct_map['Azioni Int. IMU >2']) / 3.0 if has_ref else 0.0
    diff_vol = pct_vol - 100.0 if has_ref else 0.0

    pct_hi = (pct_map['TL_High'] + pct_map['High Decel IMU'] + pct_map['High Accel IMU']) / 3.0 if has_ref else 0.0
    diff_hi = pct_hi - 100.0 if has_ref else 0.0

    dict_cur = {k: float(get_val(val_cur, k, 0)) for k in hex_cols}
    dict_ref = {k: float(get_val(val_ref, k, 0)) for k in hex_cols}
    pct_wr, diff_wr = calcola_work_rate_acwr(dict_cur, dict_ref)

    col_hex_p, col_idx_p = st.columns([1.25, 1], gap="medium")
    with col_hex_p:
        with st.container(border=True):
            lbl_hex_t = tr("Profilo Esagonale (% Raggiunta per Parametro)", "Hexagonal Profile (Percentage Reached by Area)")
            st.markdown(f"<div style='font-size:13px; font-weight:800; color:#0f172a; text-transform:uppercase; letter-spacing:0.6px; margin-bottom:4px;'>{lbl_hex_t}</div>", unsafe_allow_html=True)

            hex_names = [
                tr("Durata", "Time"),
                "Training Load",
                "TL High",
                tr("High Decel", "High Decel"),
                tr("High Accel", "High Accel"),
                tr('Azioni >2"', 'Actions >2"')
            ]
            r_vals = [pct_map[k] for k in hex_cols]
            theta_labels = []
            for nm, k in zip(hex_names, hex_cols):
                pv = pct_map[k]
                dv = diff_map[k]
                _, z_fg, _, _ = acwr_zone_meta(pv)
                d_txt = f"{dv:+.0f}%" if float(get_val(val_ref, k, 0)) > 0 else "N/A"
                theta_labels.append(f"<b>{nm}</b><br><span style='color:{z_fg}; font-size:12px;'><b>{pv:.0f}%</b> ({d_txt})</span>")

            r_closed = r_vals + [r_vals[0]]
            theta_closed = theta_labels + [theta_labels[0]]
            max_r_hex = max(160.0, max(r_vals) + 20.0) if r_vals else 160.0

            fig_hex = go.Figure()
            fig_hex.add_trace(go.Scatterpolar(
                r=[80]*7, theta=theta_closed, mode='lines',
                line=dict(color='#38bdf8', width=1.5, dash='dot'),
                name='Low Zone (80%)', hoverinfo='skip'
            ))
            fig_hex.add_trace(go.Scatterpolar(
                r=[100]*7, theta=theta_closed, mode='lines',
                line=dict(color='#10b981', width=2.5),
                name=lbl_ref_legend, hoverinfo='skip'
            ))
            fig_hex.add_trace(go.Scatterpolar(
                r=[125]*7, theta=theta_closed, mode='lines',
                line=dict(color='#f59e0b', width=1.5, dash='dot'),
                name='High Zone (125%)', hoverinfo='skip'
            ))
            fig_hex.add_trace(go.Scatterpolar(
                r=[150]*7, theta=theta_closed, mode='lines',
                line=dict(color='#ef4444', width=1.5, dash='dot'),
                name='Overload Zone (150%)', hoverinfo='skip'
            ))
            fig_hex.add_trace(go.Scatterpolar(
                r=r_closed, theta=theta_closed,
                mode='lines+markers',
                fill='toself',
                fillcolor='rgba(15, 23, 42, 0.16)',
                line=dict(color='#0f172a', width=3.5),
                marker=dict(size=8, color='#0f172a', line=dict(color='white', width=1.5)),
                name=tr('% Raggiunta', 'Percentage Reached'),
                hovertemplate="%{theta}<br><b>%{r:.0f}%</b><extra></extra>"
            ))
            fig_hex.update_layout(
                polar=dict(
                    domain=dict(x=[0.16, 0.84], y=[0.08, 0.92]),
                    gridshape='linear',
                    bgcolor='rgba(0,0,0,0)',
                    angularaxis=dict(
                        tickfont=dict(size=12, color='#0f172a', family='Inter, sans-serif'),
                        rotation=90,
                        direction='clockwise',
                        gridcolor='#e2e8f0',
                        linecolor='#cbd5e1'
                    ),
                    radialaxis=dict(
                        visible=True,
                        range=[0, max_r_hex],
                        tickvals=[50, 80, 100, 125, 150],
                        ticktext=['50%', '80%', '100%', '125%', '150%'],
                        tickfont=dict(size=9, color='#94a3b8'),
                        gridcolor='#f1f5f9',
                        angle=90,
                        tickangle=90
                    )
                ),
                showlegend=False,
                height=410,
                margin=dict(l=30, r=30, t=25, b=25),
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)'
            )
            st.plotly_chart(fig_hex, use_container_width=True, key=chart_key)

            leg_low = tr("Low Zone (80%)", "Low Zone (80%)")
            leg_high = tr("High Zone (125%)", "High Zone (125%)")
            leg_over = tr("Overload (150%)", "Overload (150%)")
            leg_val = tr("% Raggiunta", "% Reached")
            st.markdown(
                "<div style='display:flex; flex-wrap:wrap; justify-content:center; align-items:center; gap:14px; padding:8px 10px; background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; margin-top:4px; font-size:11px; font-weight:600; color:#475569;'>"
                f"<div style='display:flex; align-items:center; gap:5px;'><span style='width:18px; border-top:2px dashed #38bdf8; display:inline-block;'></span>{leg_low}</div>"
                f"<div style='display:flex; align-items:center; gap:5px;'><span style='width:18px; border-top:3px solid #10b981; display:inline-block;'></span>{lbl_ref_legend}</div>"
                f"<div style='display:flex; align-items:center; gap:5px;'><span style='width:18px; border-top:2px dashed #f59e0b; display:inline-block;'></span>{leg_high}</div>"
                f"<div style='display:flex; align-items:center; gap:5px;'><span style='width:18px; border-top:2px dashed #ef4444; display:inline-block;'></span>{leg_over}</div>"
                f"<div style='display:flex; align-items:center; gap:5px;'><span style='width:10px; height:10px; border-radius:50%; background:#0f172a; display:inline-block;'></span><b style='color:#0f172a;'>{leg_val}</b></div>"
                "</div>",
                unsafe_allow_html=True
            )

    with col_idx_p:
        def _render_idx_card(title_idx, pct_idx, diff_idx, formula_desc):
            z_bg, z_fg, z_bar, z_lbl = acwr_zone_meta(pct_idx)
            d_str = f"{diff_idx:+.0f}%" if has_ref else "N/A"
            return (
                f"<div style='background:white; border:1px solid #e2e8f0; border-left:5px solid {z_bar}; border-radius:12px; padding:16px 18px; margin-bottom:14px; box-shadow:0 2px 6px -1px rgba(15,23,42,0.04); font-family:\"Inter\", sans-serif;'>"
                "<div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;'>"
                f"<span style='font-size:12px; font-weight:800; color:#0f172a; text-transform:uppercase; letter-spacing:0.8px;'>{title_idx}</span>"
                f"<span style='background:{z_bg}; color:{z_fg}; font-size:10px; font-weight:800; padding:3px 9px; border-radius:20px; letter-spacing:0.4px;'>{z_lbl}</span>"
                "</div>"
                "<div style='display:flex; align-items:baseline; gap:10px; margin-bottom:10px;'>"
                f"<span style='font-size:34px; font-weight:900; color:{z_fg}; line-height:1;'>{pct_idx:.0f}%</span>"
                f"<span style='font-size:14px; font-weight:800; color:{z_fg}; background:{z_bg}; padding:2px 8px; border-radius:6px;'>{d_str} {lbl_vs}</span>"
                "</div>"
                f"{render_pct_progress_bar(pct_idx, z_bar)}"
                f"<div style='font-size:11px; color:#64748b; margin-top:8px; line-height:1.35;'>{formula_desc}</div>"
                "</div>"
            )

        cards_html = (
            _render_idx_card(
                tr("Indice Volume", "Volume Index"),
                pct_vol,
                diff_vol,
                tr('Media % tra Durata, Training Load e Azioni Intense >2"', 'Average % of Duration, Training Load, and Intense Actions >2"')
            )
            + _render_idx_card(
                tr("Indice Alta Intensità", "High Intensity Index"),
                pct_hi,
                diff_hi,
                tr("Media % tra Training Load High, Decelerazioni e Accelerazioni IMU", "Average % of Training Load High, High Decel, and High Accel IMU")
            )
            + _render_idx_card(
                "Work Rate",
                pct_wr,
                diff_wr,
                tr('Media % dei 5 parametri al minuto: TL/m, TL High/m, Acc/m, Dec/m, Azioni >2"/m', 'Average % of the 5 per-minute metrics: TL/m, TL High/m, Acc/m, Dec/m, Actions >2"/m')
            )
        )
        st.markdown(cards_html, unsafe_allow_html=True)


def render_executive_bands_section(title_banner, subtitle_ctx, bands_data, lbl_cur, lbl_ref, unit_suffix, chart_key_prefix):
    """Renderizza il blocco Executive per Training Load Bands e Training Load Time % Bands:
    - Banner Header Dark Navy
    - 4 Scorecard Executive con % Raggiunta (+Delta%) e barra con tacca 100%
    - Donut Chart + Bar Chart affiancati con legenda HTML unificata
    bands_data: lista di tuple (label_short, label_full, val_cur, val_ref, accent_hex, badge_bg)
    """
    hdr_html = (
        "<div style='background:#0f172a; border-bottom:2px solid #0ea5e9; border-radius:12px 12px 0 0; padding:13px 18px; display:flex; justify-content:space-between; align-items:center; font-family:\"Inter\", sans-serif;'>"
        f"<span style='color:white; font-weight:900; font-size:14px; text-transform:uppercase; letter-spacing:0.8px;'>{title_banner}</span>"
        f"<span style='background:rgba(255,255,255,0.1); color:#38bdf8; font-size:11px; font-weight:800; padding:4px 10px; border-radius:6px;'>{subtitle_ctx}</span>"
        "</div>"
    )
    cards_grid = "<div style='display:grid; grid-template-columns:repeat(4, 1fr); gap:12px; padding:16px; background:#f8fafc; border:1px solid #e2e8f0; border-top:none; border-radius:0 0 12px 12px; margin-bottom:16px; font-family:\"Inter\", sans-serif;'>"
    for lbl_s, lbl_f, vc, vr, acc_col, b_bg in bands_data:
        pv = (vc / vr * 100.0) if vr > 0 else 0.0
        dv = pv - 100.0 if vr > 0 else 0.0
        z_bg, z_fg, z_bar, _ = acwr_zone_meta(pv)
        d_str = f"{dv:+.0f}%" if vr > 0 else "N/A"
        cards_grid += (
            f"<div style='background:white; border:1px solid #e2e8f0; border-top:4px solid {acc_col}; border-radius:10px; padding:14px; box-shadow:0 1px 3px rgba(15,23,42,0.03);'>"
            "<div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;'>"
            f"<span style='font-size:11px; font-weight:800; color:#0f172a; text-transform:uppercase;'>{lbl_f}</span>"
            f"<span style='background:{b_bg}; color:{acc_col}; font-size:9px; font-weight:800; padding:2px 6px; border-radius:4px;'>{lbl_s}</span>"
            "</div>"
            "<div style='display:flex; align-items:baseline; justify-content:space-between; margin-bottom:8px;'>"
            f"<span style='font-size:26px; font-weight:900; color:#0f172a;'>{vc:.0f}{unit_suffix}</span>"
            f"<span style='font-size:12px; font-weight:700; color:#64748b;'>{lbl_ref}: {vr:.0f}{unit_suffix}</span>"
            "</div>"
            "<div style='display:flex; align-items:center; justify-content:space-between; margin-bottom:8px;'>"
            f"<span style='background:{z_bg}; color:{z_fg}; font-size:13px; font-weight:900; padding:2px 8px; border-radius:6px;'>{pv:.0f}%</span>"
            f"<span style='font-size:11px; font-weight:800; color:{z_fg};'>({d_str})</span>"
            "</div>"
            f"{render_pct_progress_bar(pv, acc_col)}"
            "</div>"
        )
    cards_grid += "</div>"
    st.markdown(hdr_html + cards_grid, unsafe_allow_html=True)

    col_pie, col_bar = st.columns(2, gap="medium")
    labels_short = [b[0] for b in bands_data]
    labels_full = [b[1] for b in bands_data]
    vals_c = [b[2] for b in bands_data]
    vals_r = [b[3] for b in bands_data]
    cols_hex = [b[4] for b in bands_data]

    with col_pie:
        with st.container(border=True):
            lbl_d_title = tr("Ripartizione % per Fascia d'Intensità", "Percentage Breakdown by Intensity Band")
            st.markdown(f"<div style='font-size:12px; font-weight:800; color:#0f172a; text-transform:uppercase; letter-spacing:0.6px; margin-bottom:6px;'>{lbl_d_title}</div>", unsafe_allow_html=True)
            fig_pie = go.Figure(data=[go.Pie(
                labels=labels_full,
                values=vals_c,
                hole=0.48,
                marker=dict(colors=cols_hex, line=dict(color='white', width=2)),
                texttemplate=f"<b>%{{value:.0f}}{unit_suffix}</b><br>(%{{percent}})",
                textfont=dict(size=12, family="Inter, sans-serif"),
                sort=False
            )])
            fig_pie.update_layout(
                height=290, margin=dict(l=15, r=15, t=10, b=10),
                showlegend=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)'
            )
            st.plotly_chart(fig_pie, use_container_width=True, key=f"{chart_key_prefix}_pie")
            leg_items = "".join([
                f"<div style='display:flex; align-items:center; gap:5px;'><span style='width:10px; height:10px; border-radius:3px; background:{c_h}; display:inline-block;'></span>{l_f}</div>"
                for l_f, c_h in zip(labels_full, cols_hex)
            ])
            st.markdown(
                f"<div style='display:flex; flex-wrap:wrap; justify-content:center; gap:14px; padding:7px 10px; background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; font-size:11px; font-weight:700; color:#475569;'>{leg_items}</div>",
                unsafe_allow_html=True
            )

    with col_bar:
        with st.container(border=True):
            lbl_b_title = tr("Confronto Diretto vs Baseline di Riferimento", "Direct Comparison vs Reference Baseline")
            st.markdown(f"<div style='font-size:12px; font-weight:800; color:#0f172a; text-transform:uppercase; letter-spacing:0.6px; margin-bottom:6px;'>{lbl_b_title}</div>", unsafe_allow_html=True)
            fig_b = go.Figure(data=[
                go.Bar(
                    name=lbl_cur, x=labels_short, y=vals_c,
                    marker_color=cols_hex,
                    text=[f"{v:.0f}{unit_suffix}" for v in vals_c],
                    textposition='outside', cliponaxis=False,
                    textfont=dict(size=12, weight='bold', color='#0f172a')
                ),
                go.Bar(
                    name=lbl_ref, x=labels_short, y=vals_r,
                    marker_color='#cbd5e1',
                    text=[f"{v:.0f}{unit_suffix}" for v in vals_r],
                    textposition='outside', cliponaxis=False,
                    textfont=dict(size=11, color='#64748b')
                )
            ])
            max_y_b = max(max(vals_c + vals_r, default=10.0) * 1.25, 10.0)
            fig_b.update_layout(
                height=290, barmode='group',
                margin=dict(l=15, r=15, t=20, b=10),
                showlegend=False,
                yaxis=dict(range=[0, max_y_b], showgrid=True, gridcolor='#f1f5f9', zeroline=False),
                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)'
            )
            st.plotly_chart(fig_b, use_container_width=True, key=f"{chart_key_prefix}_bar")
            st.markdown(
                "<div style='display:flex; justify-content:center; gap:18px; padding:7px 10px; background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; font-size:11px; font-weight:700; color:#475569;'>"
                f"<div style='display:flex; align-items:center; gap:6px;'><span style='width:12px; height:10px; border-radius:3px; background:#0ea5e9; display:inline-block;'></span>{lbl_cur}</div>"
                f"<div style='display:flex; align-items:center; gap:6px;'><span style='width:12px; height:10px; border-radius:3px; background:#cbd5e1; display:inline-block;'></span>{lbl_ref}</div>"
                "</div>",
                unsafe_allow_html=True
            )


def render_executive_chart_header(title, pills=None, accent="#0ea5e9"):
    """Renderizza un banner header Executive sopra un grafico con pill KPI a destra.
    pills: lista di tuple (label, value_str[, pill_color])
    """
    pills_html = ""
    if pills:
        for item in pills:
            if len(item) == 3:
                p_lbl, p_val, p_col = item
            else:
                p_lbl, p_val = item[0], item[1]
                p_col = "#38bdf8"
            pills_html += (
                f"<div style='background:rgba(255,255,255,0.08); border:1px solid rgba(255,255,255,0.14); padding:4px 10px; border-radius:6px; font-size:11px; color:#cbd5e1;'>"
                f"{p_lbl}: <b style='color:{p_col}; font-size:12px;'>{p_val}</b></div>"
            )
    return (
        f"<div style='background:#0f172a; border-bottom:2px solid {accent}; border-radius:10px; padding:11px 16px; margin-bottom:8px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; font-family:\"Inter\", sans-serif;'>"
        f"<span style='color:white; font-weight:800; font-size:13px; text-transform:uppercase; letter-spacing:0.7px;'>{title}</span>"
        f"<div style='display:flex; align-items:center; gap:8px; flex-wrap:wrap;'>{pills_html}</div>"
        "</div>"
    )



def render_delta_bar(pct, color_pos="#0284c7", color_neg="#94a3b8"):
    """Renders a unified bidirectional horizontal progress bar centered at 0%."""
    bar_w = min(abs(pct), 100) / 2
    if pct >= 0:
        bar_div = f"<div style='position:absolute; left:50%; top:2px; bottom:2px; width:{bar_w}%; background-color:{color_pos}; border-radius: 0 4px 4px 0;'></div>"
    else:
        bar_div = f"<div style='position:absolute; right:50%; top:2px; bottom:2px; width:{bar_w}%; background-color:{color_neg}; border-radius: 4px 0 0 4px;'></div>"
    return (
        "<div style='width: 100%; height: 18px; background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 4px; position: relative;'>"
        "<div style='position:absolute; left:50%; top:0; bottom:0; width:1px; background-color:#cbd5e1; z-index:2;'></div>"
        f"{bar_div}</div>"
    )
def riepilogo_match(dati, medie):
    """Scostamento % medio di Volume, Intensità e Densità rispetto alla media storica."""
    def pm(x, mins): return x / mins if mins > 0 else 0
    cm, am = get_val(dati, 'Minuti'), get_val(medie, 'Minuti')
    vol = [calcola_delta_percentuale(get_val(dati, k), get_val(medie, k))
           for k in ('Minuti', 'Training Load', 'Azioni Int. IMU >2')]
    inten = [calcola_delta_percentuale(get_val(dati, k), get_val(medie, k))
             for k in ('TL_High', 'High Accel IMU', 'High Decel IMU')]
    dens = [calcola_delta_percentuale(pm(get_val(dati, k), cm), pm(get_val(medie, k), am))
            for k in ('Training Load', 'High Accel IMU', 'High Decel IMU', 'TL_High', 'Azioni Int. IMU >2')]
    return sum(vol) / 3, sum(inten) / 3, sum(dens) / 5

def calcola_blocchi_baseline(df_ath_all, baseline_end, days_window):
    """
    Calcola il numero di blocchi nella finestra cronica di 28 giorni precedenti:
    - Controlla la prima data assoluta dell'atleta nell'intero database (first_ever_date) per gestire il cold-start.
    - Se l'atleta è presente a sistema da >= 28 giorni prima di baseline_end, restituisce sempre 28.0 / days_window
      (es. 4.0 blocchi per finestra 7 gg, 14.0 blocchi per finestra 2 gg), anche se ci sono settimane di scarico/riposo.
    - Solo se l'atleta è entrato a sistema da meno di 28 giorni prima di baseline_end riduce proporzionalmente i blocchi.
    """
    if df_ath_all is None or df_ath_all.empty or 'Date_obj' not in df_ath_all.columns:
        return max(1.0, 28.0 / float(days_window))
    first_ever_date = df_ath_all['Date_obj'].dropna().min()
    if pd.isna(first_ever_date):
        return max(1.0, 28.0 / float(days_window))
    baseline_end_dt = pd.to_datetime(baseline_end)
    first_ever_dt = pd.to_datetime(first_ever_date)
    giorni_da_esordio = (baseline_end_dt - first_ever_dt).days + 1
    if giorni_da_esordio <= 0:
        return 1.0
    giorni_effettivi = min(28.0, float(giorni_da_esordio))
    return max(1.0, giorni_effettivi / float(days_window))


_EWMA_TIMELINE_CACHE = {}

def get_athlete_ewma_timeline(df, giocatore, col='Training Load', burn_in_mask=True):
    """
    Calcola la serie temporale continua giornaliera con algoritmo UNCOUPLED EWMA
    (Exponentially Weighted Moving Average disaccoppiato — Williams et al., 2017; Impellizzeri et al., 2020).
    - Finestra Acuta: 7 giorni (lambda = 2 / (7 + 1) = 0.25)
    - Finestra Cronica: 28 giorni (lambda = 2 / (28 + 1) = 2 / 29 ~= 0.0689655)
    - Finestra Acute Readiness: 2 giorni (lambda = 2 / (2 + 1) ~= 0.66667)
    - Disaccoppiamento (Uncoupled): acute(t) / chronic(t-1)
    - Burn-in: maschera a np.nan i primi 7 giorni dall'avvio o da stop prolungati (>28 giorni).
    """
    import numpy as np

    if df is None or df.empty or not giocatore:
        return {}

    cache_key = (str(giocatore), str(col), len(df))
    if cache_key in _EWMA_TIMELINE_CACHE:
        return _EWMA_TIMELINE_CACHE[cache_key]

    d = df[df['Players'] == giocatore].copy()
    if d.empty:
        return {}

    d['Date_obj'] = pd.to_datetime(d['Date'], format="%d/%m/%Y", errors='coerce')
    d = d.dropna(subset=['Date_obj'])
    if d.empty:
        return {}

    # Gestione metrica meccanica combinata
    if col in ('Mechanical Load', 'High Accel + Decel', 'Meccanico', 'Carico Meccanico'):
        col_acc = pd.to_numeric(d['High Accel IMU'], errors='coerce').fillna(0) if 'High Accel IMU' in d.columns else 0
        col_dec = pd.to_numeric(d['High Decel IMU'], errors='coerce').fillna(0) if 'High Decel IMU' in d.columns else 0
        d['__calc_col'] = col_acc + col_dec
    else:
        if col not in d.columns:
            return {}
        d['__calc_col'] = pd.to_numeric(d[col], errors='coerce').fillna(0)

    # Aggregazione per giorno
    daily_s = d.groupby('Date_obj')['__calc_col'].sum()
    min_dt = daily_s.index.min()
    max_dt = daily_s.index.max()
    full_idx = pd.date_range(min_dt, max_dt, freq='D')
    daily = daily_s.reindex(full_idx, fill_value=0.0)

    # Identificazione ripartenze dopo stop prolungati (>28 giorni consecutivi di carico zero)
    # Calcolo parametri EWMA
    lambda_7 = 2.0 / (7.0 + 1.0)
    lambda_2 = 2.0 / (2.0 + 1.0)
    lambda_28 = 2.0 / (28.0 + 1.0)

    n_days = len(daily)
    acute7 = np.zeros(n_days)
    acute2 = np.zeros(n_days)
    chronic28 = np.zeros(n_days)
    acwr7 = np.full(n_days, np.nan)
    acwr2 = np.full(n_days, np.nan)

    consecutive_zero = 0
    start_block_idx = 0

    for i in range(n_days):
        load_val = float(daily.iloc[i])
        if load_val == 0.0:
            consecutive_zero += 1
        else:
            if consecutive_zero > 28:
                start_block_idx = i  # Reset baseline al rientro dopo infortunio/stop prolungato
            consecutive_zero = 0

        days_in_block = i - start_block_idx + 1

        if i == 0 or days_in_block == 1:
            acute7[i] = load_val
            acute2[i] = load_val
            chronic28[i] = load_val
        else:
            acute7[i] = load_val * lambda_7 + acute7[i - 1] * (1.0 - lambda_7)
            acute2[i] = load_val * lambda_2 + acute2[i - 1] * (1.0 - lambda_2)
            chronic28[i] = load_val * lambda_28 + chronic28[i - 1] * (1.0 - lambda_28)

            prev_chr = chronic28[i - 1]
            if prev_chr > 0:
                if not burn_in_mask or days_in_block > 7:
                    acwr7[i] = round((acute7[i] / prev_chr) * 100.0, 1)
                    acwr2[i] = round((acute2[i] / prev_chr) * 100.0, 1)

    timeline_map = {}
    for i, dt in enumerate(full_idx):
        dt_key = dt.strftime("%d/%m/%Y")
        timeline_map[dt_key] = {
            "load": float(daily.iloc[i]),
            "acute7": float(acute7[i]),
            "acute2": float(acute2[i]),
            "chronic28": float(chronic28[i]),
            "acwr7": acwr7[i] if not np.isnan(acwr7[i]) else None,
            "acwr2": acwr2[i] if not np.isnan(acwr2[i]) else None,
        }

    _EWMA_TIMELINE_CACHE[cache_key] = timeline_map
    return timeline_map


def acwr_pre_match(df, giocatore, data_match, giorni=2, col='Training Load', include_target=False, burn_in_mask=False):
    """
    Calcola l'ACWR su standard UNCOUPLED EWMA (Williams et al., 2017; Impellizzeri et al., 2020).
    - include_target=False (Match Readiness Pre-Match): valuta la readiness il giorno precedente al match (target - 1 giorno)
    - include_target=True (Session Readiness / Consolidated): include il carico del target
    - giorni=2: restituisce l'Acute Readiness a 2 giorni (EWMA lambda_2 vs Chronic 28d)
    - giorni=7: restituisce l'ACWR classico a 7 giorni (EWMA lambda_7 vs Chronic 28d)
    - Supporta 'Training Load', 'TL_High' e 'Mechanical Load' (High Accel + Decel IMU).
    """
    import numpy as np

    target = pd.to_datetime(data_match, format="%d/%m/%Y", errors='coerce')
    if pd.isna(target):
        return np.nan if burn_in_mask else None

    # Determinazione data esatta di calcolo
    eval_dt = target if include_target else (target - timedelta(days=1))
    eval_key = eval_dt.strftime("%d/%m/%Y")

    timeline = get_athlete_ewma_timeline(df, giocatore, col=col, burn_in_mask=burn_in_mask)
    if not timeline or eval_key not in timeline:
        return np.nan if burn_in_mask else None

    item = timeline[eval_key]
    val = item['acwr2'] if (giorni <= 3) else item['acwr7']
    if val is None:
        return np.nan if burn_in_mask else None
    return float(val)


def stato_acwr(pct):
    """(testo, sfondo, colore testo): stesse soglie della Home e della legenda."""
    if pct < 80: return tr("basso", "low"), "#e0f2fe", "#075985"
    if pct <= 125: return tr("nella norma", "optimal"), "#dcfce7", "#166534"
    return tr("alto", "high"), "#fee2e2", "#991b1b"

def etichetta_scostamento(delta, soglia=10):
    if delta > soglia: return tr("sopra la media", "above average")
    if delta < -soglia: return tr("sotto la media", "below average")
    return tr("in linea con la media", "in line with average")

def frase_riepilogo(vol, inten, den, acwr=None):
    e = etichetta_scostamento
    if st.session_state.get('lang', 'IT') == 'EN':
        frase = (f"Compared to historical average: volume {e(vol)} ({vol:+.0f}%), "
                 f"intensity {e(inten)} ({inten:+.0f}%), work rate {e(den)} ({den:+.0f}%).")
        if acwr is not None:
            frase += f" Pre-session acute load {stato_acwr(acwr)[0]} ({acwr:.0f}% of average)."
        return frase
    frase = (f"Rispetto alla media storica: volume {e(vol)} ({vol:+.0f}%), "
             f"intensità {e(inten)} ({inten:+.0f}%), work rate {e(den)} ({den:+.0f}%).")
    if acwr is not None:
        frase += f" Carico acuto pre-sessione {stato_acwr(acwr)[0]} ({acwr:.0f}% della media)."
    return frase

def card_kpi(titolo, valore_html, sottotitolo="", accento="#0ea5e9", **kwargs):
    sub = kwargs.get('subtext', sottotitolo)
    acc = kwargs.get('accent', kwargs.get('accento', accento))
    return (
        f"<div style='background:white; padding:18px 16px; border-radius:12px; border:1px solid #e2e8f0; "
        f"border-left:5px solid {acc}; box-shadow:0 2px 4px rgba(0,0,0,0.03);'>"
        f"<div style='font-size:11px; font-weight:700; color:#64748b; text-transform:uppercase; letter-spacing:0.5px;'>{titolo}</div>"
        f"<div style='margin:8px 0 4px 0; line-height:1.1;'>{valore_html}</div>"
        f"<div style='font-size:11px; color:#94a3b8;'>{sub}</div></div>"
    )

def delta_puro(delta):
    if pd.isna(delta): return "0%"
    sign = "+" if delta > 0 else ""
    return f"{sign}{delta:.0f}%"

def delta_confronto(va, vb):
    if pd.isna(vb) or vb == 0 or pd.isna(va): return "<span style='color:gray; font-weight:bold; font-size:16px;'>N/A</span>"
    diff = ((va - vb) / vb) * 100
    if diff > 0: return f"<span style='color:#ea4335; font-weight:bold; font-size:16px;'>+{diff:.0f}%</span>"
    elif diff < 0: return f"<span style='color:#34a853; font-weight:bold; font-size:16px;'>{diff:.0f}%</span>"
    return "<span style='color:gray; font-weight:bold; font-size:16px;'>0%</span>"

@st.cache_data(ttl=120, show_spinner=False)
def get_atleti_associati(user_id):
    try:
        res = supabase.table('associazioni').select('atleti(nome, cognome)').eq('profilo_id', user_id).execute()
        if not res.data:
            res = supabase_admin.table('associazioni').select('atleti(nome, cognome)').eq('profilo_id', user_id).execute()
        if res.data:
            return [f"{item['atleti']['nome']} {item['atleti']['cognome']}" for item in res.data if item.get('atleti')]
        return []
    except Exception:
        try:
            res = supabase_admin.table('associazioni').select('atleti(nome, cognome)').eq('profilo_id', user_id).execute()
            if res.data:
                return [f"{item['atleti']['nome']} {item['atleti']['cognome']}" for item in res.data if item.get('atleti')]
        except Exception:
            pass
        return []

@st.cache_data(ttl=120, show_spinner=False)
def get_tutti_gli_atleti():
    try:
        res = supabase.table('atleti').select('nome, cognome').execute()
        if not res.data:
            res = supabase_admin.table('atleti').select('nome, cognome').execute()
        if res.data:
            return [f"{a['nome']} {a['cognome']}" for a in res.data]
        return []
    except Exception:
        try:
            res = supabase_admin.table('atleti').select('nome, cognome').execute()
            if res.data:
                return [f"{a['nome']} {a['cognome']}" for a in res.data]
        except Exception:
            pass
        return []

def clear_atleti_cache():
    """Invalida la cache RAM degli elenchi atleti ed associazioni Supabase."""
    try:
        get_atleti_associati.clear()
    except Exception:
        pass
    try:
        get_tutti_gli_atleti.clear()
    except Exception:
        pass


def get_lista_atleti_disponibili(user=None, role=None):
    """
    Restituisce l'elenco ordinato e univoco di atleti disponibili per l'utente e il ruolo corrente.
    - Ruolo 'Atleta': restituisce solo il proprio nome associato.
    - Ruoli Staff / Coach / Fisio / Preparatore (tutti i ruoli non Super-Admin):
      restituisce ESCLUSIVAMENTE gli atleti a loro associati su Supabase.
      Non mostra il roster totale per preservare privacy e correttezza della selezione.
    - Ruolo 'Super-Admin': unione di tutti gli atleti da Supabase e dal DB locale GPS.
    """
    # 1. Se Atleta, prendi solo l'atleta collegato all'account
    if role == 'Atleta' and user:
        try:
            atl_info = get_atleta_dettagli_per_utente(user.id)
            if atl_info and atl_info.get('nome_completo'):
                return [atl_info['nome_completo']]
        except Exception:
            pass
        if hasattr(user, 'email') and user.email:
            return [user.email.split('@')[0]]
        return ["Atleta"]

    # 2. Per ruoli NON Super-Admin (Coach, Preparatore, Fisio, Staff, ecc.):
    # Mostra RIGOROSAMENTE E SOLTANTO gli atleti a loro esplicitamente associati
    is_super_admin = (str(role).strip().lower() in ('super-admin', 'superadmin') or role is None)

    if not is_super_admin and user:
        nomi = []
        try:
            assoc = get_atleti_associati(user.id)
            if assoc:
                nomi.extend(assoc)
        except Exception:
            pass

        # Verifica eventuale associazione diretta
        if not nomi:
            try:
                single_info = get_atleta_dettagli_per_utente(user.id)
                if single_info and single_info.get('nome_completo'):
                    nomi.append(single_info['nome_completo'])
            except Exception:
                pass

        nomi_unici = sorted(list(dict.fromkeys([n for n in nomi if n and str(n).strip()])))
        if nomi_unici:
            return nomi_unici
        else:
            # Nessun atleta associato a questo utente: non mostrare il roster totale altrui!
            return ["Nessun atleta associato"]

    # 3. Solo per Super-Admin: carica l'intero roster da Supabase + database locale GPS
    nomi = []
    try:
        tutti_sb = get_tutti_gli_atleti()
        if tutti_sb:
            nomi.extend(tutti_sb)
    except Exception:
        pass

    try:
        df_loc = load_local_database()
        if not df_loc.empty and 'Players' in df_loc.columns:
            loc_players = [str(p).strip() for p in df_loc['Players'].dropna().unique() if str(p).strip()]
            nomi.extend(loc_players)
    except Exception:
        pass

    nomi_unici = sorted(list(dict.fromkeys([n for n in nomi if n and str(n).strip()])))
    if not nomi_unici:
        nomi_unici = ["Flavio Cobolli"]
    return nomi_unici



def slugify_name(text):
    return re.sub(r'[^A-Za-z0-9]+', '_', str(text)).strip('_')


# =========================================================================
# HELPER PER CARICO INTERNO & WELLNESS ATLETA
# =========================================================================

def get_atleta_dettagli_per_utente(profilo_id):
    """Restituisce l'atleta (id, nome, cognome) associato a un account utente."""
    try:
        res = supabase.table('associazioni').select('atleta_id, atleti(id, nome, cognome)').eq('profilo_id', profilo_id).execute()
        if res.data and len(res.data) > 0:
            item = res.data[0]
            if item.get('atleti'):
                return {
                    "id": item['atleti']['id'],
                    "nome": item['atleti']['nome'],
                    "cognome": item['atleti']['cognome'],
                    "nome_completo": f"{item['atleti']['nome']} {item['atleti']['cognome']}"
                }
            elif item.get('atleta_id'):
                atl_res = supabase.table('atleti').select('*').eq('id', item['atleta_id']).execute()
                if atl_res.data:
                    atl = atl_res.data[0]
                    return {
                        "id": atl['id'],
                        "nome": atl['nome'],
                        "cognome": atl['cognome'],
                        "nome_completo": f"{atl['nome']} {atl['cognome']}"
                    }
        return None
    except Exception as e:
        return None


@st.cache_data(ttl=60, show_spinner=False)
def get_wellness_mattutino(atleta_id, data_str):
    """Carica la rilevazione di wellness mattutino per un atleta in una determinata data."""
    try:
        res = supabase.table('wellness_mattutino').select('*').eq('atleta_id', atleta_id).eq('data', data_str).execute()
        return res.data[0] if (res.data and len(res.data) > 0) else None
    except Exception:
        return None


def upsert_wellness_mattutino(payload):
    """Inserisce o aggiorna il wellness mattutino (grazie al vincolo UNIQUE atleta_id, data)."""
    try:
        res = supabase.table('wellness_mattutino').upsert(payload, on_conflict='atleta_id, data').execute()
        try:
            get_wellness_mattutino.clear()
            get_athlete_master_calendar.clear()
        except Exception:
            pass
        return True, res.data
    except Exception as e:
        return False, str(e)


@st.cache_data(ttl=60, show_spinner=False)
def get_rpe_sessioni(atleta_id, data_str):
    """Recupera le sessioni sRPE registrate da un atleta per una determinata data."""
    try:
        res = supabase.table('rpe_sessioni').select('*').eq('atleta_id', atleta_id).eq('data', data_str).order('slot').execute()
        return res.data or []
    except Exception:
        return []


def upsert_rpe_sessione(payload):
    """Inserisce o aggiorna uno slot di sessione sRPE."""
    try:
        res = supabase.table('rpe_sessioni').upsert(payload, on_conflict='atleta_id, data, slot').execute()
        try:
            get_rpe_sessioni.clear()
            get_athlete_master_calendar.clear()
        except Exception:
            pass
        return True, res.data
    except Exception as e:
        return False, str(e)


def delete_rpe_sessione(session_id):
    """Elimina uno slot di sessione sRPE."""
    try:
        supabase.table('rpe_sessioni').delete().eq('id', session_id).execute()
        try:
            get_rpe_sessioni.clear()
            get_athlete_master_calendar.clear()
        except Exception:
            pass
        return True
    except Exception:
        return False


def check_stato_giornaliero_atleta(atleta_id, data_str):
    """Restituisce lo stato sintetico di compilazione per il giorno indicato."""
    w = get_wellness_mattutino(atleta_id, data_str)
    r = get_rpe_sessioni(atleta_id, data_str)
    
    wellness_fatto = w is not None
    wellness_score = None
    if wellness_fatto:
        # Score medio su 10 (con inversione dei parametri negativi Fatica, Stress, DOMS)
        # Positivi: Sonno (1-10), Umore (1-10)
        # Negativi invertiti: 11 - Fatica, 11 - Stress, 11 - DOMS
        score_pos = w['sonno_qualita'] + w['umore']
        score_neg_inv = (11 - w['fatica']) + (11 - w['stress']) + (11 - w['doms'])
        wellness_score = round((score_pos + score_neg_inv) / 5.0, 1)

    rpe_fatto = len(r) > 0
    tot_carico_interno = sum(s.get('carico_interno', 0) or (s.get('durata_minuti', 0) * s.get('rpe', 0)) for s in r)
    tot_minuti = sum(s.get('durata_minuti', 0) for s in r)

    return {
        "wellness_compilato": wellness_fatto,
        "wellness_dati": w,
        "wellness_score": wellness_score,
        "rpe_compilato": rpe_fatto,
        "rpe_sessioni": r,
        "rpe_tot_carico": tot_carico_interno,
        "rpe_tot_minuti": tot_minuti
    }


# =========================================================================
# MODULO: TEST FISICI & NEUROMUSCOLARI (M0V3 Enterprise)
# =========================================================================

def calcola_asimmetria_dx_sx(val_dx, val_sx, direction="HIGHER_IS_BETTER"):
    """
    Calcola l'asimmetria percentuale standardizzata e l'asimmetria vettoriale con segno:
    - Asimmetria Assoluta % = (|Dx - Sx| / max(Dx, Sx)) * 100
    - Asimmetria Vettoriale % (signed_asym_pct):
        HIGHER_IS_BETTER: ((Dx - Sx) / max(Dx, Sx)) * 100 (+ = dominanza Dx, - = dominanza Sx)
        LOWER_IS_BETTER (es. sprint 5-0-5): ((Sx - Dx) / max(Dx, Sx)) * 100 (+ = Dx più veloce, - = Sx più veloce)
    Restituisce: (asym_pct, direction_str, formatted_label, signed_asym_pct)
    """
    try:
        if val_dx is None or val_sx is None or pd.isna(val_dx) or pd.isna(val_sx):
            return None, None, "N/D", 0.0
        dx = float(val_dx)
        sx = float(val_sx)
        m = max(abs(dx), abs(sx))
        if m == 0:
            return 0.0, "=", "0.0% (=)", 0.0
        
        asym = round((abs(dx - sx) / m) * 100.0, 2)

        # Calcolo vettoriale con segno e dominanza
        if direction == "LOWER_IS_BETTER":
            # Per metriche a tempo, un valore inferiore indica performance migliore
            signed_asym = round(((sx - dx) / m) * 100.0, 2)
            dir_str = "Dx" if dx < sx else ("Sx" if sx < dx else "=")
        else:
            signed_asym = round(((dx - sx) / m) * 100.0, 2)
            dir_str = "Dx" if dx > sx else ("Sx" if sx > dx else "=")

        label = f"{asym:.1f}% ({dir_str})"
        return asym, dir_str, label, signed_asym
    except Exception:
        return None, None, "N/D", 0.0


def calcola_baseline_swc(valori_storici, direction="HIGHER_IS_BETTER"):
    """
    Calcola Personal Best, Media Storica e Smallest Worthwhile Change (SWC):
    - Media_Storica (mu) e Deviazione_Standard (sigma) sulle ultime 5 sessioni (o tutte se <5).
    - SWC = 0.2 * sigma (se sigma == 0 o 1 sola sessione, buffer di default del 2.5% della media).
    Restituisce: (pb, media_5, std_5, swc)
    """
    import numpy as np
    vals_clean = []
    for v in (valori_storici or []):
        if v is not None and not pd.isna(v):
            try:
                vals_clean.append(float(v))
            except Exception:
                pass
    
    if not vals_clean:
        return None, None, None, None

    is_lower = (direction == "LOWER_IS_BETTER")
    pb = min(vals_clean) if is_lower else max(vals_clean)

    subset = vals_clean[-5:]
    media_5 = float(np.mean(subset))
    
    if len(subset) > 1:
        std_5 = float(np.std(subset, ddof=1))
    else:
        std_5 = 0.0

    if std_5 == 0.0 or pd.isna(std_5):
        swc = abs(media_5) * 0.025 if media_5 != 0 else 0.1
    else:
        swc = 0.2 * std_5

    return pb, media_5, std_5, swc


def valuta_readiness_swc(val_current, valori_storici, direction="HIGHER_IS_BETTER"):
    """
    Semaforo di Readiness scientifico M0V3 basato su Baseline Storica + SWC (Zero Emoji):
    - SOPRA MEDIA / OTTIMALE (#10b981 Smeraldo): Migliore di mu + SWC (o entro il 3% dal PB)
    - STABILE / IN TARGET (#38bdf8 Blu M0V3): All'interno della fascia [mu - SWC, mu + SWC]
    - LIEVE CALO / ATTENZIONE (#f59e0b Ambra): Peggiore di mu - SWC fino a mu - 2*SWC (o calo 5-10% se 2 test)
    - SOTTO SOGLIA / CRITICO (#e11d48 Rosso Rubino): Peggiore di mu - 2*SWC (o calo >10% rispetto alla media)
    
    Restituisce: (stato_lbl, colore_hex, delta_media_pct, txt_delta_media, pb, media_5, swc)
    """
    pb, media, std, swc = calcola_baseline_swc(valori_storici, direction)
    if val_current is None or media is None or pd.isna(val_current):
        return "N/D", "#94a3b8", 0.0, "N/D", pb, media, swc

    try:
        curr = float(val_current)
        delta_pct = round(((curr - media) / abs(media)) * 100.0, 1) if media != 0 else 0.0
        n_sess = len([v for v in (valori_storici or []) if v is not None and not pd.isna(v)])
        
        is_higher = (direction == "HIGHER_IS_BETTER")
        is_lower = (direction == "LOWER_IS_BETTER")

        sign_sym = "+" if delta_pct > 0 else ""
        txt_delta = f"{sign_sym}{delta_pct:.1f}% " + tr("vs Media", "vs Mean")

        lbl_sopra = tr("SOPRA MEDIA / OTTIMALE", "ABOVE MEAN / OPTIMAL")
        lbl_stabile = tr("STABILE / IN TARGET", "STABLE / ON TARGET")
        lbl_calo = tr("LIEVE CALO / ATTENZIONE", "SLIGHT DROP / CAUTION")
        lbl_sotto = tr("SOTTO SOGLIA / CRITICO", "BELOW THRESHOLD / CRITICAL")
        lbl_var = tr("VARIAZIONE / ATTENZIONE", "VARIATION / CAUTION")
        lbl_var_sig = tr("VARIAZIONE SIGNIFICATIVA", "SIGNIFICANT VARIATION")

        if is_higher:
            # Prestazione migliore verso l'alto
            vicino_pb = (pb is not None and pb > 0 and curr >= (pb * 0.97))
            if curr > (media + swc) or vicino_pb:
                return lbl_sopra, "#10b981", delta_pct, txt_delta, pb, media, swc
            elif (media - swc) <= curr <= (media + swc):
                return lbl_stabile, "#38bdf8", delta_pct, txt_delta, pb, media, swc
            elif (media - 2 * swc) <= curr < (media - swc) or (n_sess == 2 and -10.0 <= delta_pct <= -5.0):
                return lbl_calo, "#f59e0b", delta_pct, txt_delta, pb, media, swc
            else:
                return lbl_sotto, "#e11d48", delta_pct, txt_delta, pb, media, swc

        elif is_lower:
            # Prestazione migliore verso il basso (tempi)
            vicino_pb = (pb is not None and pb > 0 and curr <= (pb * 1.03))
            if curr < (media - swc) or vicino_pb:
                return lbl_sopra, "#10b981", delta_pct, txt_delta, pb, media, swc
            elif (media - swc) <= curr <= (media + swc):
                return lbl_stabile, "#38bdf8", delta_pct, txt_delta, pb, media, swc
            elif (media + swc) < curr <= (media + 2 * swc) or (n_sess == 2 and 5.0 <= delta_pct <= 10.0):
                return lbl_calo, "#f59e0b", delta_pct, txt_delta, pb, media, swc
            else:
                return lbl_sotto, "#e11d48", delta_pct, txt_delta, pb, media, swc

        else:
            # Neutrale / Antropometria
            if abs(curr - media) <= swc:
                return lbl_stabile, "#38bdf8", delta_pct, txt_delta, pb, media, swc
            elif abs(curr - media) <= (2 * swc):
                return lbl_var, "#f59e0b", delta_pct, txt_delta, pb, media, swc
            else:
                return lbl_var_sig, "#e11d48", delta_pct, txt_delta, pb, media, swc

    except Exception:
        return "N/D", "#94a3b8", 0.0, "N/D", pb, media, swc


def valuta_direzione_delta(val_current, val_baseline, direction):
    """
    Calcola il delta percentuale e assegna colore semantico in base alla direzione di miglioramento:
    - HIGHER_IS_BETTER: aumento è verde (#10b981), calo è rosso (#ef4444)
    - LOWER_IS_BETTER: calo è verde (#10b981), aumento è rosso (#ef4444)
    - NEUTRAL: colore informativo blu (#0ea5e9)
    """
    if val_current is None or val_baseline is None or pd.isna(val_current) or pd.isna(val_baseline):
        return None, "#94a3b8", "N/D", ""
    try:
        curr = float(val_current)
        base = float(val_baseline)
        if base == 0:
            return None, "#94a3b8", "N/D", ""
        delta_pct = round(((curr - base) / abs(base)) * 100.0, 1)

        if delta_pct == 0:
            return 0.0, "#94a3b8", "= 0.0%", "="

        is_higher_better = (direction == "HIGHER_IS_BETTER")
        is_lower_better = (direction == "LOWER_IS_BETTER")

        if is_higher_better:
            is_positive = (delta_pct > 0)
        elif is_lower_better:
            is_positive = (delta_pct < 0)
        else:
            return delta_pct, "#0ea5e9", f"{'+' if delta_pct > 0 else ''}{delta_pct:.1f}%", ("▲" if delta_pct > 0 else "▼")

        color = "#10b981" if is_positive else "#ef4444"
        arrow = "▲" if delta_pct > 0 else "▼"
        text = f"{arrow} {'+' if delta_pct > 0 else ''}{delta_pct:.1f}%"
        return delta_pct, color, text, arrow
    except Exception:
        return None, "#94a3b8", "N/D", ""


def valuta_readiness_test(val_current, personal_best, direction):
    """
    Valuta lo stato di forma (Readiness) rispetto al Personal Best storico:
    OTTIMALE / IN FORMA: >=95% del proprio PB
    STABILE / NELLA MEDIA: tra 88% e 94.9% del PB
    SOTTO SOGLIA / AFFATICATO: <88% del proprio PB
    """
    if val_current is None or personal_best is None:
        return "N/D", "#94a3b8", "white"
    try:
        curr = float(val_current)
        pb = float(personal_best)
        if pb == 0:
            return "N/D", "#94a3b8", "white"

        if direction == "HIGHER_IS_BETTER":
            ratio_pct = (curr / pb) * 100.0
        elif direction == "LOWER_IS_BETTER":
            ratio_pct = (pb / curr) * 100.0
        else:
            # Neutrale: valuta vicinanza assoluta
            diff_pct = abs((curr - pb) / pb) * 100.0
            ratio_pct = max(0.0, 100.0 - diff_pct)

        if ratio_pct >= 95.0:
            return "OTTIMALE", "#10b981", "#ffffff"
        elif ratio_pct >= 88.0:
            return "NELLA MEDIA", "#f59e0b", "#ffffff"
        else:
            return "SOTTO SOGLIA", "#ef4444", "#ffffff"
    except Exception:
        return "N/D", "#94a3b8", "white"


def calcola_formule_derivate_test(codice_protocollo, valori_dict):
    """
    Calcola automaticamente metriche derivate note (se i campi grezzi sono valorizzati):
    - Antropometria: FFM (kg) da Peso e FFM %
    - Cooper: VO2max da Distanza
    - Yo-Yo IR1: VO2max da Distanza
    - RSA: Decrement % da Tempo Medio e Best Sprint
    """
    v = dict(valori_dict or {})
    cod = str(codice_protocollo or '').lower()

    try:
        # 1. Antropometria: FFM kg = Peso * (FFM% / 100)
        if cod == 'antropometria_comp_corporea':
            peso = v.get('peso') if v.get('peso') is not None else v.get('weight')
            ffm_pct = v.get('ffm_pct') if v.get('ffm_pct') is not None else v.get('ffm')
            if peso is not None and ffm_pct is not None and 'ffm_kg' not in v:
                v['ffm_kg'] = round(float(peso) * (float(ffm_pct) / 100.0), 2)

        # 2. Cooper 12 min: VO2max = (Distanza - 504.9) / 44.73
        elif cod == 'cooper_12min':
            dist = v.get('distanza') if v.get('distanza') is not None else v.get('distance')
            if dist is not None and 'vo2max' not in v:
                v['vo2max'] = round((float(dist) - 504.9) / 44.73, 1)

        # 3. Yo-Yo IR1: VO2max = (Distanza * 0.0084) + 36.4
        elif cod == 'yoyo_ir1':
            dist = v.get('distanza') if v.get('distanza') is not None else v.get('distance')
            if dist is not None and 'vo2max' not in v:
                v['vo2max'] = round((float(dist) * 0.0084) + 36.4, 1)

        # 4. RSA (8x30m / 8x15m): Decremento % = (((Tempo Medio * 8) / (Best * 8)) - 1) * 100
        elif 'rsa' in cod:
            t_med = v.get('tempo_medio') if v.get('tempo_medio') is not None else v.get('mean_time')
            t_best = v.get('miglior_sprint') if v.get('miglior_sprint') is not None else v.get('best_sprint')
            if t_med is not None and t_best is not None and float(t_best) > 0 and 'decremento_pct' not in v:
                v['decremento_pct'] = round((((float(t_med) * 8.0) / (float(t_best) * 8.0)) - 1.0) * 100.0, 2)
    except Exception:
        pass

    return v


def calcola_indici_clinici_spalla(sessioni_per_data):
    """
    Calcola indici clinici spalla cross-test:
    1. TROM (Total Range of Motion) = ROM IR + ROM ER (per Dx e Sx)
    2. Strength ER/IR ratio (%) = (Forza ER / Forza IR) * 100 (target: 65% - 75%)
    """
    res = {
        "trom_dx": None, "trom_sx": None, "trom_diff": None,
        "er_ir_ratio_dx": None, "er_ir_ratio_sx": None,
        "data": None
    }
    rom_ir_dx, rom_ir_sx = None, None
    rom_er_dx, rom_er_sx = None, None
    forza_ir_dx, forza_ir_sx = None, None
    forza_er_dx, forza_er_sx = None, None
    date_spalla = []

    for s in sessioni_per_data:
        cod = str(s.get('codice_univoco', '')).lower()
        nome = str(s.get('protocollo_info', {}).get('nome_protocollo', '')).lower()
        val = s.get('valori', {}) or {}
        d_cur = s.get('data')
        if d_cur: date_spalla.append(str(d_cur)[:10])

        if 'rom' in cod and ('ir' in cod or 'intrarot' in nome):
            rom_ir_dx = val.get('max_angle_dx') or val.get('rom_dx') or val.get('max_rom_dx')
            rom_ir_sx = val.get('max_angle_sx') or val.get('rom_sx') or val.get('max_rom_sx')
        elif 'rom' in cod and ('er' in cod or 'extrarot' in nome):
            rom_er_dx = val.get('max_angle_dx') or val.get('rom_dx') or val.get('max_rom_dx')
            rom_er_sx = val.get('max_angle_sx') or val.get('rom_sx') or val.get('max_rom_sx')
        elif ('dynamo_f_spalla_ir' in cod) or ('shoulder ir' in nome):
            forza_ir_dx = val.get('max_force_dx') or val.get('peak_force_dx') or val.get('force_dx')
            forza_ir_sx = val.get('max_force_sx') or val.get('peak_force_sx') or val.get('force_sx')
        elif ('dynamo_f_spalla_er' in cod) or ('shoulder er' in nome):
            forza_er_dx = val.get('max_force_dx') or val.get('peak_force_dx') or val.get('force_dx')
            forza_er_sx = val.get('max_force_sx') or val.get('peak_force_sx') or val.get('force_sx')

    if date_spalla:
        res["data"] = date_spalla[-1]

    if rom_ir_dx is not None and rom_er_dx is not None:
        res["trom_dx"] = round(float(rom_ir_dx) + float(rom_er_dx), 1)
    if rom_ir_sx is not None and rom_er_sx is not None:
        res["trom_sx"] = round(float(rom_ir_sx) + float(rom_er_sx), 1)
    if res["trom_dx"] is not None and res["trom_sx"] is not None:
        res["trom_diff"] = round(abs(res["trom_dx"] - res["trom_sx"]), 1)

    if forza_er_dx is not None and forza_ir_dx is not None and float(forza_ir_dx) > 0:
        res["er_ir_ratio_dx"] = round((float(forza_er_dx) / float(forza_ir_dx)) * 100.0, 1)
    if forza_er_sx is not None and forza_ir_sx is not None and float(forza_ir_sx) > 0:
        res["er_ir_ratio_sx"] = round((float(forza_er_sx) / float(forza_ir_sx)) * 100.0, 1)

    return res


def calcola_indici_cross_test(sessioni_atleta):
    """
    Calcola automaticamente gli indici biomeccanici e fisiologici derivati cross-test
    tra prove registrate per lo stesso atleta nella medesima data:
    1. Elastic Index / Eccentric Utilization Ratio (EUR: CMJ vs SJ):
       - Differenziale elastico assoluto in cm (CMJ - SJ)
       - Differenziale percentuale ((CMJ - SJ) / SJ) * 100
       - EUR Ratio (CMJ / SJ, target fisiologico 1.10 - 1.15)
    2. Dynamic Strength Index (DSI = Peak Force Salto / Peak Force IMTP):
       - Rapporto tra picco di forza dinamico (salto) e picco di forza isometrico massimale (IMTP)
       - Target ottimale: 0.60 - 0.80 (<0.60: Ballistic Deficit | >0.80: Max Strength Deficit)
    3. Change of Direction Deficit (COD Deficit: 5-0-5 Agility vs Sprint 10m):
       - Tempo 5-0-5 - Tempo Sprint 10m per arto Dx e Sx
    4. Indici Spalla (DynaMo):
       - Total ROM (TROM) e Ratio di forza rotatori ER/IR
    """
    import numpy as np

    risultato = {
        "eur": None,
        "dsi": None,
        "cod_deficit": None,
        "spalla": None,
        "storico_eur": [],
        "storico_dsi": [],
        "storico_cod": []
    }

    if not sessioni_atleta:
        return risultato

    # Raggruppamento delle sessioni per data
    by_date = {}
    for s in sessioni_atleta:
        d_raw = s.get('data')
        if not d_raw:
            continue
        d_str = str(d_raw)[:10]
        if d_str not in by_date:
            by_date[d_str] = []
        by_date[d_str].append(s)

    date_ordinate = sorted(by_date.keys())

    for d_str in date_ordinate:
        recs_giorno = by_date[d_str]

        # Mappatura dei test del giorno
        sess_cmj = None
        sess_sj = None
        sess_imtp = None
        sess_505 = None
        sess_10m = None

        for s in recs_giorno:
            p_info = s.get('protocollo_info') or {}
            cod = str(s.get('codice_univoco') or p_info.get('codice_univoco') or '').lower()
            nome = str(s.get('nome_test') or p_info.get('nome_protocollo') or '').lower()

            if cod == 'vald_fd_cmj' or 'cmj' in cod or 'countermovement' in nome:
                sess_cmj = s
            elif cod == 'vald_fd_sj' or 'sj' in cod or 'squat jump' in nome:
                sess_sj = s
            elif cod == 'vald_fd_imtp' or 'imtp' in cod or 'isometric mid-thigh' in nome:
                sess_imtp = s
            elif cod == 'agility_505' or '505' in cod or '5-0-5' in nome:
                sess_505 = s
            elif cod == 'sprint_10m' or '10m' in cod or 'sprint 10' in nome:
                sess_10m = s

        # -------------------------------------------------------------
        # 1. ELASTIC INDEX / EUR (CMJ vs SJ)
        # -------------------------------------------------------------
        if sess_cmj and sess_sj:
            v_cmj = sess_cmj.get('valori', {}) or {}
            v_sj = sess_sj.get('valori', {}) or {}
            h_cmj = v_cmj.get('jump_height') or v_cmj.get('altezza_salto') or v_cmj.get('altezza')
            h_sj = v_sj.get('jump_height') or v_sj.get('altezza_salto') or v_sj.get('altezza')
            if h_cmj is not None and h_sj is not None:
                try:
                    f_cmj = float(h_cmj)
                    f_sj = float(h_sj)
                    if f_sj > 0:
                        diff_cm = round(f_cmj - f_sj, 1)
                        diff_pct = round(((f_cmj - f_sj) / f_sj) * 100.0, 1)
                        eur_r = round(f_cmj / f_sj, 2)

                        if diff_pct >= 10.0 and diff_pct <= 20.0:
                            valut = tr("Ottimale (+10-20% SSC)", "Optimal (+10-20% SSC)")
                            col_eur = "#10b981"
                        elif diff_pct > 20.0:
                            valut = tr("Iper-Reattivo / Deficit Forza Concentrica", "Hyper-Reactive / Concentric Deficit")
                            col_eur = "#38bdf8"
                        elif diff_pct >= 5.0:
                            valut = tr("Moderato (+5-10% SSC)", "Moderate (+5-10% SSC)")
                            col_eur = "#f59e0b"
                        else:
                            valut = tr("Deficit Elastico (<5% SSC)", "Elastic Deficit (<5% SSC)")
                            col_eur = "#e11d48"

                        item_eur = {
                            "data": d_str,
                            "cmj_h": f_cmj,
                            "sj_h": f_sj,
                            "diff_cm": diff_cm,
                            "diff_pct": diff_pct,
                            "eur_ratio": eur_r,
                            "valutazione": valut,
                            "colore": col_eur
                        }
                        risultato["eur"] = item_eur
                        risultato["storico_eur"].append(item_eur)
                except Exception:
                    pass

        # -------------------------------------------------------------
        # 2. DYNAMIC STRENGTH INDEX (DSI = Jump PF / IMTP PF)
        # -------------------------------------------------------------
        if (sess_cmj or sess_sj) and sess_imtp:
            v_imtp = sess_imtp.get('valori', {}) or {}
            pf_imtp = v_imtp.get('peak_vertical_force') or v_imtp.get('peak_force')

            # Ricerca picco di forza del salto da CMJ o SJ
            pf_jump = None
            j_type = "CMJ"
            sess_jump = sess_cmj or sess_sj
            if sess_jump:
                v_j = sess_jump.get('valori', {}) or {}
                j_cod = str(sess_jump.get('codice_univoco') or sess_jump.get('protocollo_info', {}).get('codice_univoco') or '').lower()
                j_type = "SJ" if "sj" in j_cod else "CMJ"

                # 1. Picco di forza diretto (ForceDecks)
                pf_raw = v_j.get('peak_takeoff_force') or v_j.get('peak_force')
                if pf_raw is not None:
                    try:
                        pf_jump = float(pf_raw)
                    except Exception:
                        pass

                # 2. Se mancante, stima biomeccanica validata da Jump Height (cm) + Massa
                if (pf_jump is None or pf_jump <= 0):
                    jh = v_j.get('jump_height') or v_j.get('altezza_salto') or v_j.get('altezza')
                    if jh is not None:
                        try:
                            m_est = 75.0
                            pf_rel = v_imtp.get('peak_force_rel')
                            if pf_imtp and pf_rel:
                                try:
                                    calc_m = float(pf_imtp) / float(pf_rel)
                                    if 40.0 <= calc_m <= 130.0:
                                        m_est = calc_m
                                except Exception:
                                    pass
                            pf_jump = round(m_est * 9.81 * (1.25 + 0.024 * float(jh)), 1)
                        except Exception:
                            pass

            if pf_jump is not None and pf_imtp is not None:
                try:
                    f_jump = float(pf_jump)
                    f_imtp = float(pf_imtp)
                    if f_imtp > 0:
                        dsi_val = round(f_jump / f_imtp, 2)
                        if dsi_val < 0.60:
                            valut_dsi = tr("Deficit Balistico / Velocità (<0.60)", "Ballistic / Velocity Deficit (<0.60)")
                            col_dsi = "#38bdf8"
                            rec_dsi = tr("Focus su forza rapida, salti e potenza balistica", "Focus on ballistic power & fast SSC")
                        elif dsi_val <= 0.80:
                            valut_dsi = tr("Target Ottimale (0.60 - 0.80)", "Optimal Target (0.60 - 0.80)")
                            col_dsi = "#10b981"
                            rec_dsi = tr("Profilo forza-velocità ben bilanciato", "Well balanced force-velocity profile")
                        else:
                            valut_dsi = tr("Deficit Forza Massima (>0.80)", "Max Strength Deficit (>0.80)")
                            col_dsi = "#f59e0b"
                            rec_dsi = tr("Focus su forza massimale e reclutamento neurale", "Focus on maximal strength training")

                        item_dsi = {
                            "data": d_str,
                            "pf_jump": f_jump,
                            "pf_imtp": f_imtp,
                            "dsi_ratio": dsi_val,
                            "jump_type": j_type,
                            "valutazione": valut_dsi,
                            "raccomandazione": rec_dsi,
                            "colore": col_dsi
                        }
                        risultato["dsi"] = item_dsi
                        risultato["storico_dsi"].append(item_dsi)
                except Exception:
                    pass

        # -------------------------------------------------------------
        # 3. COD DEFICIT (5-0-5 Agility vs Sprint 10m)
        # -------------------------------------------------------------
        if sess_505 and sess_10m:
            v_505 = sess_505.get('valori', {}) or {}
            v_10m = sess_10m.get('valori', {}) or {}
            t10 = v_10m.get('tempo_10m') or v_10m.get('tempo_best')
            t505_dx = v_505.get('tempo_505_dx') or v_505.get('tempo_dx')
            t505_sx = v_505.get('tempo_505_sx') or v_505.get('tempo_sx')

            if t10 is not None and (t505_dx is not None or t505_sx is not None):
                try:
                    f_10 = float(t10)
                    f_dx = float(t505_dx) if t505_dx is not None else None
                    f_sx = float(t505_sx) if t505_sx is not None else None

                    def_dx = round(f_dx - f_10, 2) if f_dx is not None else None
                    def_sx = round(f_sx - f_10, 2) if f_sx is not None else None

                    asym_cod = 0.0
                    if def_dx is not None and def_sx is not None and max(def_dx, def_sx) > 0:
                        asym_cod = round((abs(def_dx - def_sx) / max(def_dx, def_sx)) * 100.0, 1)

                    if asym_cod > 10.0:
                        valut_cod = tr(f"Asimmetria Marcata COD ({asym_cod:.1f}%)", f"Marked COD Asymmetry ({asym_cod:.1f}%)")
                        col_cod = "#e11d48"
                    elif asym_cod > 5.0:
                        valut_cod = tr(f"Asimmetria Lieve COD ({asym_cod:.1f}%)", f"Mild COD Asymmetry ({asym_cod:.1f}%)")
                        col_cod = "#f59e0b"
                    else:
                        valut_cod = tr("Simmetrico (≤5% Asimmetria)", "Symmetrical (≤5% Asymmetry)")
                        col_cod = "#10b981"

                    item_cod = {
                        "data": d_str,
                        "t10m": f_10,
                        "t505_dx": f_dx,
                        "t505_sx": f_sx,
                        "cod_def_dx": def_dx,
                        "cod_def_sx": def_sx,
                        "asym_cod": asym_cod,
                        "valutazione": valut_cod,
                        "colore": col_cod
                    }
                    risultato["cod_deficit"] = item_cod
                    risultato["storico_cod"].append(item_cod)
                except Exception:
                    pass

    # -------------------------------------------------------------
    # FALLBACK INTELLIGENTE BATTERIA RECENTE (CROSS-TEST MULTI-DATA)
    # -------------------------------------------------------------
    # 1. Fallback EUR (CMJ vs SJ)
    if risultato["eur"] is None:
        all_cmj = []
        all_sj = []
        for s in sessioni_atleta:
            p_info = s.get('protocollo_info') or {}
            cod = str(s.get('codice_univoco') or p_info.get('codice_univoco') or '').lower()
            nome = str(s.get('nome_test') or p_info.get('nome_protocollo') or '').lower()
            val = s.get('valori', {}) or {}
            h = val.get('jump_height') or val.get('altezza_salto') or val.get('altezza')
            d_raw = s.get('data')
            if h is not None and d_raw:
                try:
                    h_f = float(h)
                    dt = pd.to_datetime(d_raw, errors='coerce')
                    if pd.notnull(dt) and h_f > 0:
                        if cod == 'vald_fd_cmj' or 'cmj' in cod or 'countermovement' in nome:
                            all_cmj.append((dt, str(d_raw)[:10], h_f, s))
                        elif cod == 'vald_fd_sj' or 'sj' in cod or 'squat jump' in nome:
                            all_sj.append((dt, str(d_raw)[:10], h_f, s))
                except Exception:
                    pass
        if all_cmj and all_sj:
            all_cmj.sort(key=lambda x: x[0], reverse=True)
            all_sj.sort(key=lambda x: x[0], reverse=True)
            best_pair = None
            min_diff = None
            for c in all_cmj:
                for j in all_sj:
                    diff_days = abs((c[0] - j[0]).days)
                    if min_diff is None or diff_days < min_diff:
                        min_diff = diff_days
                        best_pair = (c, j, diff_days)
            if best_pair:
                c_sel, j_sel, d_diff = best_pair
                f_cmj = c_sel[2]
                f_sj = j_sel[2]
                diff_cm = round(f_cmj - f_sj, 1)
                diff_pct = round(((f_cmj - f_sj) / f_sj) * 100.0, 1)
                eur_r = round(f_cmj / f_sj, 2)

                if diff_pct >= 10.0 and diff_pct <= 20.0:
                    valut = tr("Ottimale (+10-20% SSC)", "Optimal (+10-20% SSC)")
                    col_eur = "#10b981"
                elif diff_pct > 20.0:
                    valut = tr("Iper-Reattivo / Deficit Forza Concentrica", "Hyper-Reactive / Concentric Deficit")
                    col_eur = "#38bdf8"
                elif diff_pct >= 5.0:
                    valut = tr("Moderato (+5-10% SSC)", "Moderate (+5-10% SSC)")
                    col_eur = "#f59e0b"
                else:
                    valut = tr("Deficit Elastico (<5% SSC)", "Elastic Deficit (<5% SSC)")
                    col_eur = "#e11d48"

                d_c_fmt = pd.to_datetime(c_sel[1]).strftime('%d/%m/%Y')
                d_s_fmt = pd.to_datetime(j_sel[1]).strftime('%d/%m/%Y')

                risultato["eur"] = {
                    "data": f"{d_c_fmt} vs {d_s_fmt}",
                    "data_cmj": d_c_fmt,
                    "data_sj": d_s_fmt,
                    "cmj_h": f_cmj,
                    "sj_h": f_sj,
                    "diff_cm": diff_cm,
                    "diff_pct": diff_pct,
                    "eur_ratio": eur_r,
                    "valutazione": valut,
                    "colore": col_eur,
                    "is_battery_fallback": True,
                    "diff_days": d_diff
                }

    # 2. Fallback DSI (Jump vs IMTP)
    if risultato["dsi"] is None:
        all_jumps = []
        all_imtp = []
        for s in sessioni_atleta:
            p_info = s.get('protocollo_info') or {}
            cod = str(s.get('codice_univoco') or p_info.get('codice_univoco') or '').lower()
            nome = str(s.get('nome_test') or p_info.get('nome_protocollo') or '').lower()
            val = s.get('valori', {}) or {}
            d_raw = s.get('data')
            if not d_raw:
                continue
            dt = pd.to_datetime(d_raw, errors='coerce')
            if pd.isnull(dt):
                continue

            pf_imtp = val.get('peak_vertical_force') or val.get('peak_force')
            if (cod == 'vald_fd_imtp' or 'imtp' in cod or 'isometric mid-thigh' in nome) and pf_imtp:
                try:
                    f_i = float(pf_imtp)
                    if f_i > 0:
                        all_imtp.append((dt, str(d_raw)[:10], f_i, s))
                except Exception:
                    pass

            pf_j = val.get('peak_takeoff_force') or val.get('peak_force')
            jh = val.get('jump_height') or val.get('altezza_salto') or val.get('altezza')
            f_j_calc = None
            if pf_j is not None:
                try:
                    f_j_calc = float(pf_j)
                except Exception:
                    pass
            elif jh is not None:
                try:
                    m_est = 75.0
                    f_j_calc = round(m_est * 9.81 * (1.25 + 0.024 * float(jh)), 1)
                except Exception:
                    pass

            if f_j_calc and f_j_calc > 0:
                if cod == 'vald_fd_cmj' or 'cmj' in cod:
                    all_jumps.append((dt, str(d_raw)[:10], f_j_calc, "CMJ", s))
                elif cod == 'vald_fd_sj' or 'sj' in cod:
                    all_jumps.append((dt, str(d_raw)[:10], f_j_calc, "SJ", s))

        if all_jumps and all_imtp:
            all_jumps.sort(key=lambda x: x[0], reverse=True)
            all_imtp.sort(key=lambda x: x[0], reverse=True)
            best_pair = None
            min_diff = None
            for j in all_jumps:
                for i in all_imtp:
                    diff_days = abs((j[0] - i[0]).days)
                    if min_diff is None or diff_days < min_diff:
                        min_diff = diff_days
                        best_pair = (j, i, diff_days)
            if best_pair:
                j_sel, i_sel, d_diff = best_pair
                f_jump = j_sel[2]
                f_imtp = i_sel[2]
                j_type = j_sel[3]
                dsi_val = round(f_jump / f_imtp, 2)
                if dsi_val < 0.60:
                    valut_dsi = tr("Deficit Balistico / Velocità (<0.60)", "Ballistic / Velocity Deficit (<0.60)")
                    col_dsi = "#38bdf8"
                    rec_dsi = tr("Focus su forza rapida, salti e potenza balistica", "Focus on ballistic power & fast SSC")
                elif dsi_val <= 0.80:
                    valut_dsi = tr("Target Ottimale (0.60 - 0.80)", "Optimal Target (0.60 - 0.80)")
                    col_dsi = "#10b981"
                    rec_dsi = tr("Profilo forza-velocità ben bilanciato", "Well balanced force-velocity profile")
                else:
                    valut_dsi = tr("Deficit Forza Massima (>0.80)", "Max Strength Deficit (>0.80)")
                    col_dsi = "#f59e0b"
                    rec_dsi = tr("Focus su forza massimale e reclutamento neurale", "Focus on maximal strength training")

                d_j_fmt = pd.to_datetime(j_sel[1]).strftime('%d/%m/%Y')
                d_i_fmt = pd.to_datetime(i_sel[1]).strftime('%d/%m/%Y')

                risultato["dsi"] = {
                    "data": f"{d_j_fmt} vs {d_i_fmt}",
                    "data_jump": d_j_fmt,
                    "data_imtp": d_i_fmt,
                    "pf_jump": f_jump,
                    "pf_imtp": f_imtp,
                    "dsi_ratio": dsi_val,
                    "jump_type": j_type,
                    "valutazione": valut_dsi,
                    "raccomandazione": rec_dsi,
                    "colore": col_dsi,
                    "is_battery_fallback": True,
                    "diff_days": d_diff
                }

    # 3. Fallback COD Deficit (5-0-5 vs Sprint 10m)
    if risultato["cod_deficit"] is None:
        all_505 = []
        all_10m = []
        for s in sessioni_atleta:
            p_info = s.get('protocollo_info') or {}
            cod = str(s.get('codice_univoco') or p_info.get('codice_univoco') or '').lower()
            nome = str(s.get('nome_test') or p_info.get('nome_protocollo') or '').lower()
            val = s.get('valori', {}) or {}
            d_raw = s.get('data')
            if not d_raw:
                continue
            dt = pd.to_datetime(d_raw, errors='coerce')
            if pd.isnull(dt):
                continue

            if cod == 'agility_505' or '505' in cod or '5-0-5' in nome:
                t_dx = val.get('tempo_505_dx') or val.get('tempo_dx')
                t_sx = val.get('tempo_505_sx') or val.get('tempo_sx')
                if t_dx is not None or t_sx is not None:
                    all_505.append((dt, str(d_raw)[:10], t_dx, t_sx, s))
            elif cod == 'sprint_10m' or '10m' in cod or 'sprint 10' in nome:
                t10 = val.get('tempo_10m') or val.get('tempo_best')
                if t10 is not None:
                    try:
                        all_10m.append((dt, str(d_raw)[:10], float(t10), s))
                    except Exception:
                        pass

        if all_505 and all_10m:
            all_505.sort(key=lambda x: x[0], reverse=True)
            all_10m.sort(key=lambda x: x[0], reverse=True)
            best_pair = None
            min_diff = None
            for a5 in all_505:
                for a10 in all_10m:
                    diff_days = abs((a5[0] - a10[0]).days)
                    if min_diff is None or diff_days < min_diff:
                        min_diff = diff_days
                        best_pair = (a5, a10, diff_days)
            if best_pair:
                a5_sel, a10_sel, d_diff = best_pair
                f_10 = a10_sel[2]
                f_dx = float(a5_sel[2]) if a5_sel[2] is not None else None
                f_sx = float(a5_sel[3]) if a5_sel[3] is not None else None
                def_dx = round(f_dx - f_10, 2) if f_dx is not None else None
                def_sx = round(f_sx - f_10, 2) if f_sx is not None else None
                asym_cod = 0.0
                if def_dx is not None and def_sx is not None and max(def_dx, def_sx) > 0:
                    asym_cod = round((abs(def_dx - def_sx) / max(def_dx, def_sx)) * 100.0, 1)

                if asym_cod > 10.0:
                    valut_cod = tr(f"Asimmetria Marcata COD ({asym_cod:.1f}%)", f"Marked COD Asymmetry ({asym_cod:.1f}%)")
                    col_cod = "#e11d48"
                elif asym_cod > 5.0:
                    valut_cod = tr(f"Asimmetria Lieve COD ({asym_cod:.1f}%)", f"Mild COD Asymmetry ({asym_cod:.1f}%)")
                    col_cod = "#f59e0b"
                else:
                    valut_cod = tr("Simmetrico (≤5% Asimmetria)", "Symmetrical (≤5% Asymmetry)")
                    col_cod = "#10b981"

                d_5_fmt = pd.to_datetime(a5_sel[1]).strftime('%d/%m/%Y')
                d_10_fmt = pd.to_datetime(a10_sel[1]).strftime('%d/%m/%Y')

                risultato["cod_deficit"] = {
                    "data": f"{d_5_fmt} vs {d_10_fmt}",
                    "data_505": d_5_fmt,
                    "data_10m": d_10_fmt,
                    "t10m": f_10,
                    "t505_dx": f_dx,
                    "t505_sx": f_sx,
                    "cod_def_dx": def_dx,
                    "cod_def_sx": def_sx,
                    "asym_cod": asym_cod,
                    "valutazione": valut_cod,
                    "colore": col_cod,
                    "is_battery_fallback": True,
                    "diff_days": d_diff
                }

    # Calcolo indici spalla più recenti
    risultato["spalla"] = calcola_indici_clinici_spalla(sessioni_atleta)

    return risultato


# -------------------------------------------------------------------------
# PERSISTENZA PROTOCOLLI E SESSIONI TEST SU SUPABASE
# -------------------------------------------------------------------------

@st.cache_data(ttl=60, show_spinner=False)
def get_catalogo_protocolli(user_id=None):
    """
    Carica l'elenco dei protocolli da Supabase (ufficiali + custom dell'utente).
    Se la tabella è vuota, esegue il seed iniziale trasparente.
    """
    from protocolli_seed import get_seed_protocols
    seed_list = get_seed_protocols()
    seed_map = {p['codice_univoco']: p for p in seed_list}

    try:
        # Proviamo con supabase_admin per immunità da RLS/JWT su catalogo globale
        db = supabase_admin if supabase_admin is not None else supabase
        res = db.table('catalogo_protocolli').select('*').order('nome_protocollo').execute()
        rows = res.data or []

        if not rows:
            # La tabella esiste ma è vuota: avvia il seed
            seed_default_protocols()
            res2 = db.table('catalogo_protocolli').select('*').order('nome_protocollo').execute()
            rows = res2.data or []

        # Se ci sono record su DB, li filtriamo:
        # Visibili se creatore_id è None (ufficiali) OPPURE se creatore_id == user_id
        if rows:
            risultati = []
            for r in rows:
                c_id = r.get('creatore_id')
                if not c_id or (user_id and str(c_id) == str(user_id)):
                    risultati.append(r)
            return risultati
    except Exception:
        pass

    # Fallback protetto in RAM se il DB non è ancora configurato
    return seed_list


def seed_default_protocols():
    """Inserisce i ~100 protocolli seed ufficiali su Supabase se non già presenti."""
    from protocolli_seed import get_seed_protocols
    seed_list = get_seed_protocols()
    try:
        db = supabase_admin if supabase_admin is not None else supabase
        # Controlla quali codici sono già presenti
        res = db.table('catalogo_protocolli').select('codice_univoco').execute()
        esistenti = set(r['codice_univoco'] for r in (res.data or []))

        da_inserire = [p for p in seed_list if p['codice_univoco'] not in esistenti]
        if da_inserire:
            # Batch da 25 per evitare timeout
            for i in range(0, len(da_inserire), 25):
                batch = da_inserire[i:i+25]
                db.table('catalogo_protocolli').insert(batch).execute()
        return True, len(da_inserire)
    except Exception as e:
        return False, str(e)


SESSIONI_TEST_LOCAL_PATH = "data_supporto/sessioni_test.json"

def _carica_sessioni_test_locali():
    if os.path.exists(SESSIONI_TEST_LOCAL_PATH):
        try:
            with open(SESSIONI_TEST_LOCAL_PATH, "r", encoding="utf-8") as f:
                d = json.load(f)
                if isinstance(d, list):
                    return d
        except Exception:
            pass
    return []

def _salva_sessioni_test_locali(sessioni):
    os.makedirs(os.path.dirname(SESSIONI_TEST_LOCAL_PATH), exist_ok=True)
    with open(SESSIONI_TEST_LOCAL_PATH, "w", encoding="utf-8") as f:
        json.dump(sessioni, f, ensure_ascii=False, indent=2)

@st.cache_data(ttl=60, show_spinner=False)
def get_sessioni_test(atleta_id=None, protocollo_id=None, atleta_nome=None):
    """
    Recupera le sessioni di test registrate, con join o arricchimento del protocollo.
    Supporta sincronizzazione bidirezionale tra Supabase e file locale JSON di persistenza.
    """
    sessioni_db = []
    try:
        db = supabase_admin if supabase_admin is not None else supabase
        query = db.table('sessioni_test').select('*, catalogo_protocolli(nome_protocollo, codice_univoco, macro_area, categoria, schema_metriche)')
        if atleta_id and not str(atleta_id).startswith("mock-"):
            query = query.eq('atleta_id', atleta_id)
        if protocollo_id:
            query = query.eq('protocollo_id', protocollo_id)
        res = query.order('data', desc=True).execute()
        sessioni_db = res.data or []
    except Exception:
        sessioni_db = []

    # Merge con archivio locale JSON
    locali = _carica_sessioni_test_locali()
    
    # Prepara seed map per protocolli
    try:
        from protocolli_seed import get_seed_protocols
        seed_map = {}
        for p in get_seed_protocols():
            if 'id' in p:
                seed_map[p['id']] = p
            if 'codice_univoco' in p:
                seed_map[p['codice_univoco']] = p
    except Exception:
        seed_map = {}

    db_ids = set(str(s.get('id')) for s in sessioni_db if s.get('id'))
    merged = list(sessioni_db)
    for loc in locali:
        if str(loc.get('id')) not in db_ids:
            if not loc.get('catalogo_protocolli'):
                pid = loc.get('protocollo_id') or loc.get('codice_univoco')
                if pid in seed_map:
                    loc['catalogo_protocolli'] = seed_map[pid]
            merged.append(loc)

    # Filtraggio opzionale per atleta_id, atleta_nome o protocollo_id
    risultato = []
    name_tgt = str(atleta_nome).lower().strip() if atleta_nome else ""
    for s in merged:
        s_ath_id = str(s.get('atleta_id', ''))
        s_name = str(s.get('nome_giocatore', s.get('atleta', ''))).lower().strip()

        if atleta_id or name_tgt:
            matches_ath = False
            if atleta_id:
                aid_str = str(atleta_id).strip()
                if not aid_str.startswith("mock-") and s_ath_id == aid_str:
                    matches_ath = True
                elif s_name and (s_name == aid_str.lower() or aid_str.lower() in s_name):
                    matches_ath = True
            if name_tgt:
                if s_name and (s_name == name_tgt or name_tgt in s_name or s_name in name_tgt):
                    matches_ath = True
            if not matches_ath:
                continue

        if protocollo_id:
            s_pid = s.get('protocollo_id') or s.get('codice_univoco') or (s.get('catalogo_protocolli') or {}).get('codice_univoco')
            if str(s_pid) != str(protocollo_id):
                continue
        risultato.append(s)

    # Ordina cronologicamente desc
    risultato.sort(key=lambda x: str(x.get('data', '')), reverse=True)
    return risultato


def upsert_sessione_test(payload):
    """
    Inserisce o aggiorna una sessione di test garantendo la regola Sparse Data:
    I campi non compilati vengono omessi o puliti per non registrare zeri fittizi.
    Salva sia su Supabase che nel JSON locale di persistenza.
    """
    clean_payload = dict(payload)
    if 'valori' in clean_payload and isinstance(clean_payload['valori'], dict):
        clean_payload['valori'] = {
            k: v for k, v in clean_payload['valori'].items() 
            if v is not None and str(v).strip() != '' and not (isinstance(v, float) and pd.isna(v))
        }

    # Salva sempre nel JSON locale
    locali = _carica_sessioni_test_locali()
    sess_id = clean_payload.get('id')
    trovato = False
    if sess_id:
        for idx, item in enumerate(locali):
            if str(item.get('id')) == str(sess_id):
                locali[idx] = clean_payload
                trovato = True
                break
    if not trovato:
        if not sess_id:
            import uuid
            sess_id = str(uuid.uuid4())
            clean_payload['id'] = sess_id
        locali.append(clean_payload)
    _salva_sessioni_test_locali(locali)

    try:
        db = supabase_admin if supabase_admin is not None else supabase
        res = db.table('sessioni_test').upsert(clean_payload).execute()
        try:
            get_sessioni_test.clear()
            get_athlete_master_calendar.clear()
        except Exception:
            pass
        return True, res.data
    except Exception as e:
        try:
            get_sessioni_test.clear()
            get_athlete_master_calendar.clear()
        except Exception:
            pass
        return True, [clean_payload]


def delete_sessione_test(sessione_id):
    """Elimina una sessione di test dal database e dal JSON locale."""
    locali = _carica_sessioni_test_locali()
    locali = [s for s in locali if str(s.get('id')) != str(sessione_id)]
    _salva_sessioni_test_locali(locali)

    try:
        db = supabase_admin if supabase_admin is not None else supabase
        db.table('sessioni_test').delete().eq('id', sessione_id).execute()
    except Exception:
        pass
    try:
        get_sessioni_test.clear()
        get_athlete_master_calendar.clear()
    except Exception:
        pass
    return True


def update_sessione_test_data(sessione_id, nuova_data):
    """Aggiorna la data di esecuzione di una sessione di test su Supabase."""
    try:
        db = supabase_admin if supabase_admin is not None else supabase
        d_str = str(nuova_data)[:10]
        res = db.table('sessioni_test').update({'data': d_str}).eq('id', sessione_id).execute()
        try:
            get_sessioni_test.clear()
            get_athlete_master_calendar.clear()
        except Exception:
            pass
        return True, res.data
    except Exception as e:
        return False, str(e)


def update_sessione_test_completa(sessione_id, payload):
    """Aggiorna completamente una sessione di test registrata su Supabase (data, parametri, valori, note, ecc.)."""
    try:
        db = supabase_admin if supabase_admin is not None else supabase
        res = db.table('sessioni_test').update(payload).eq('id', sessione_id).execute()
        try:
            get_sessioni_test.clear()
            get_athlete_master_calendar.clear()
        except Exception:
            pass
        return True, res.data
    except Exception as e:
        return False, str(e)


def upsert_protocollo_custom(payload):
    """Salva un protocollo personalizzato creato da un Coach."""
    try:
        db = supabase_admin if supabase_admin is not None else supabase
        res = db.table('catalogo_protocolli').upsert(payload).execute()
        get_catalogo_protocolli.clear()
        return True, res.data
    except Exception as e:
        return False, str(e)


def delete_protocollo_custom(protocollo_id, user_id=None):
    """Elimina un protocollo custom creato dal Coach."""
    try:
        db = supabase_admin if supabase_admin is not None else supabase
        q = db.table('catalogo_protocolli').delete().eq('id', protocollo_id)
        if user_id:
            q = q.eq('creatore_id', user_id)
        q.execute()
        get_catalogo_protocolli.clear()
        return True
    except Exception:
        return False


# =========================================================================
# MOTORE CALENDARIO & AREA MEDICA (Registro Medico, Fisio & Logistica)
# =========================================================================

@st.cache_data(ttl=60, show_spinner=False)
def get_registro_medico(atleta_id=None, nome_giocatore=None, start_date=None, end_date=None):
    """
    Recupera i record dal registro medico/fisioterapico/logistico con filtri opzionali.
    """
    try:
        db = supabase_admin if supabase_admin is not None else supabase
        q = db.table('registro_medico_fisio').select('*')
        if atleta_id and not str(atleta_id).startswith("mock-"):
            q = q.eq('atleta_id', atleta_id)
        elif nome_giocatore:
            q = q.ilike('nome_giocatore', f"%{nome_giocatore}%")
        
        if start_date:
            q = q.lte('data_inizio', str(end_date) if end_date else str(start_date))
        if end_date:
            q = q.gte('data_fine', str(start_date) if start_date else str(end_date))
            
        res = q.order('data_inizio', desc=True).execute()
        return res.data or []
    except Exception:
        return []


def upsert_registro_medico(payload):
    """
    Inserisce o aggiorna una voce nel registro medico/fisioterapico.
    """
    try:
        db = supabase_admin if supabase_admin is not None else supabase
        res = db.table('registro_medico_fisio').upsert(payload).execute()
        try:
            get_registro_medico.clear()
            get_athlete_master_calendar.clear()
        except Exception:
            pass
        return True, res.data
    except Exception as e:
        return False, str(e)


def delete_registro_medico(record_id):
    """
    Elimina un record dal registro medico/fisioterapico.
    """
    try:
        db = supabase_admin if supabase_admin is not None else supabase
        db.table('registro_medico_fisio').delete().eq('id', record_id).execute()
        try:
            get_registro_medico.clear()
            get_athlete_master_calendar.clear()
        except Exception:
            pass
        return True
    except Exception:
        return False


@st.cache_data(ttl=60, show_spinner=False)
def get_athlete_master_calendar(nome_giocatore, atleta_id, start_date, end_date):
    """
    Fonde ad alte prestazioni le 5 sorgenti dati dell'atleta nel range temporale selezionato:
    1. GPS / IMU (database_storico.parquet)
    2. Carico Interno sRPE (rpe_sessioni)
    3. Wellness Mattutino (wellness_mattutino)
    4. Test Fisici & Neuromuscolari (sessioni_test)
    5. Registro Medico, Fisio & Logistica (registro_medico_fisio)
    
    Restituisce un dizionario indicizzato per data (YYYY-MM-DD).
    """
    import datetime
    
    # 1. Normalizzazione date di inizio e fine
    if isinstance(start_date, str):
        d_start = datetime.datetime.strptime(start_date[:10], "%Y-%m-%d").date()
    elif isinstance(start_date, datetime.datetime):
        d_start = start_date.date()
    else:
        d_start = start_date

    if isinstance(end_date, str):
        d_end = datetime.datetime.strptime(end_date[:10], "%Y-%m-%d").date()
    elif isinstance(end_date, datetime.datetime):
        d_end = end_date.date()
    else:
        d_end = end_date

    calendar_data = {}
    curr_d = d_start
    while curr_d <= d_end:
        d_str = curr_d.strftime("%Y-%m-%d")
        calendar_data[d_str] = {
            "data": d_str,
            "date_obj": curr_d,
            "day_num": curr_d.day,
            "weekday": curr_d.weekday(),  # 0=Lun, 6=Dom
            "status_operativo": "DISPONIBILE",
            # Sorgente 1: GPS / IMU
            "gps_presente": False,
            "is_match": False,
            "gps_tipi": [],
            "gps_ambienti": [],
            "minuti_gps": 0.0,
            "training_load_gps": 0.0,
            "tl_high_gps": 0.0,
            "high_accel_imu": 0.0,
            "high_decel_imu": 0.0,
            "azioni_int_imu": 0.0,
            # Sorgente 2: sRPE
            "srpe_presente": False,
            "srpe_minuti": 0.0,
            "srpe_carico": 0.0,
            "srpe_slots": [],
            "solo_carico_interno": False,
            # Sorgente 3: Wellness
            "wellness_presente": False,
            "wellness_score": None,
            "wellness_dettagli": {},
            "wellness_alerts": [],
            # Sorgente 4: Test Fisici
            "test_presenti": [],
            "test_count": 0,
            # Sorgente 5: Medico / Fisio / Logistica
            "medico_eventi": [],
            "has_infortunio": False,
            "has_sovraccarico": False,
            "has_trattamento": False,
            "has_logistica": False,
            "overload_adattato": False,
            "pct_su_media_tl": 0.0,
            "tl_media_storica": 0.0,
            "soglia_70_adattato": 0.0,
        }
        curr_d += datetime.timedelta(days=1)

    # -------------------------------------------------------------------------
    # Sorgente 1: GPS / IMU da database_storico.parquet
    # -------------------------------------------------------------------------
    tl_media_storica = 0.0
    soglia_70 = 0.0
    try:
        df_local = load_local_database()
        if not df_local.empty and 'Players' in df_local.columns and nome_giocatore:
            target_norm = str(nome_giocatore).strip().lower()
            df_ath = df_local[df_local['Players'].astype(str).str.strip().str.lower() == target_norm].copy()
            if not df_ath.empty:
                if 'Training Load' in df_ath.columns:
                    tl_active = pd.to_numeric(df_ath['Training Load'], errors='coerce').dropna()
                    tl_active = tl_active[tl_active > 0]
                    if not tl_active.empty:
                        tl_media_storica = float(tl_active.mean())
                        soglia_70 = tl_media_storica * 0.70
                if 'Date_dt' in df_ath.columns:
                    dates_col = df_ath['Date_dt']
                elif 'Date_obj' in df_ath.columns:
                    dates_col = pd.to_datetime(df_ath['Date_obj'], errors='coerce').dt.date
                elif 'Date' in df_ath.columns:
                    dates_col = pd.to_datetime(df_ath['Date'], errors='coerce', dayfirst=True).dt.date
                else:
                    dates_col = pd.Series([None] * len(df_ath), index=df_ath.index)

                df_ath['Date_clean'] = dates_col
                df_ath_range = df_ath[(df_ath['Date_clean'] >= d_start) & (df_ath['Date_clean'] <= d_end)]
                for _, row in df_ath_range.iterrows():
                    d_row = row['Date_clean']
                    if not d_row or pd.isna(d_row):
                        continue
                    d_str = d_row.strftime("%Y-%m-%d") if hasattr(d_row, 'strftime') else str(d_row)[:10]
                    if d_str in calendar_data:
                        d_dict = calendar_data[d_str]
                        d_dict["gps_presente"] = True
                        s_name = str(row.get('Session', ''))
                        if 'match' in s_name.lower():
                            d_dict["is_match"] = True
                        d_dict["gps_tipi"].append(s_name)
                        d_dict["gps_ambienti"].append(str(row.get('Ambiente', 'Outdoor')))
                        d_dict["minuti_gps"] += float(row.get('Minuti', 0) or 0)
                        d_dict["training_load_gps"] += float(row.get('Training Load', 0) or 0)
                        d_dict["tl_high_gps"] += float(row.get('TL_High', 0) or 0)
                        d_dict["high_accel_imu"] += float(row.get('High Accel IMU', 0) or 0)
                        d_dict["high_decel_imu"] += float(row.get('High Decel IMU', 0) or 0)
                        d_dict["azioni_int_imu"] += float(row.get('Azioni Int. IMU >2', 0) or 0)
    except Exception:
        pass

    db = supabase_admin if supabase_admin is not None else supabase

    # -------------------------------------------------------------------------
    # Sorgente 2: Carico Interno sRPE (tabella rpe_sessioni)
    # -------------------------------------------------------------------------
    try:
        if atleta_id and not str(atleta_id).startswith("mock-"):
            res_rpe = db.table('rpe_sessioni').select('*').eq('atleta_id', atleta_id).gte('data', str(d_start)).lte('data', str(d_end)).execute()
            for r in (res_rpe.data or []):
                d_str = str(r.get('data', ''))[:10]
                if d_str in calendar_data:
                    d_dict = calendar_data[d_str]
                    d_dict["srpe_presente"] = True

                    # 1. Schema con colonne singole (tabella reale: slot, tipologia, durata_minuti, rpe, carico_interno)
                    if 'durata_minuti' in r or 'carico_interno' in r or 'rpe' in r:
                        minuti = float(r.get('durata_minuti', 0) or 0)
                        rpe_v = float(r.get('rpe', 0) or 0)
                        carico = float(r.get('carico_interno', 0) or (minuti * rpe_v))
                        tipo = r.get('tipologia') or r.get('tipo') or "Attività"
                        slot_n = int(r.get('slot', len(d_dict["srpe_slots"]) + 1) or 1)
                        d_dict["srpe_slots"].append({
                            "slot": slot_n,
                            "tipo": tipo,
                            "minuti": minuti,
                            "rpe": rpe_v,
                            "carico": carico
                        })
                        d_dict["srpe_minuti"] += minuti
                        d_dict["srpe_carico"] += carico

                    # 2. Schema alternativo con colonne piatte (slot1_..., slot2_...)
                    if r.get('slot1_tipo') or r.get('slot1_durata_minuti'):
                        s1_t = r.get('slot1_tipo')
                        s1_m = float(r.get('slot1_durata_minuti', 0) or 0)
                        s1_r = float(r.get('slot1_rpe', 0) or 0)
                        s1_c = float(r.get('slot1_carico', 0) or (s1_m * s1_r))
                        d_dict["srpe_slots"].append({"slot": 1, "tipo": s1_t or "Attività", "minuti": s1_m, "rpe": s1_r, "carico": s1_c})
                        d_dict["srpe_minuti"] += s1_m
                        d_dict["srpe_carico"] += s1_c

                    if r.get('slot2_tipo') or r.get('slot2_durata_minuti'):
                        s2_t = r.get('slot2_tipo')
                        s2_m = float(r.get('slot2_durata_minuti', 0) or 0)
                        s2_r = float(r.get('slot2_rpe', 0) or 0)
                        s2_c = float(r.get('slot2_carico', 0) or (s2_m * s2_r))
                        d_dict["srpe_slots"].append({"slot": 2, "tipo": s2_t or "Attività", "minuti": s2_m, "rpe": s2_r, "carico": s2_c})
                        d_dict["srpe_minuti"] += s2_m
                        d_dict["srpe_carico"] += s2_c

                    if d_dict["training_load_gps"] == 0 and d_dict["srpe_carico"] > 0:
                        d_dict["solo_carico_interno"] = True
    except Exception:
        pass

    # -------------------------------------------------------------------------
    # Sorgente 3: Wellness Mattutino (tabella wellness_mattutino)
    # -------------------------------------------------------------------------
    try:
        if atleta_id and not str(atleta_id).startswith("mock-"):
            res_wel = db.table('wellness_mattutino').select('*').eq('atleta_id', atleta_id).gte('data', str(d_start)).lte('data', str(d_end)).execute()
            for w in (res_wel.data or []):
                d_str = str(w.get('data', ''))[:10]
                if d_str in calendar_data:
                    d_dict = calendar_data[d_str]
                    d_dict["wellness_presente"] = True
                    sonno = float(w.get('sonno_qualita', 0) or w.get('sonno', 0) or 0)
                    fatica = float(w.get('fatica', 0) or 0)
                    stress = float(w.get('stress', 0) or 0)
                    umore = float(w.get('umore', 0) or 0)
                    doms = float(w.get('dolore_muscolare', 0) or w.get('doms', 0) or 0)
                    d_dict["wellness_dettagli"] = {
                        "sonno": sonno, "fatica": fatica, "stress": stress, "umore": umore, "doms": doms
                    }
                    score_db = w.get('wellness_score')
                    if score_db is not None:
                        d_dict["wellness_score"] = float(score_db)
                    else:
                        vals = [sonno, fatica, stress, umore, doms]
                        vals_v = [v for v in vals if v > 0]
                        d_dict["wellness_score"] = round(sum(vals_v) / len(vals_v), 1) if vals_v else 0

                    alerts = []
                    if doms >= 7: alerts.append(f"DOMS Elevati ({doms:.0f})")
                    if fatica >= 7: alerts.append(f"Fatica Elevata ({fatica:.0f})")
                    if stress >= 7: alerts.append(f"Stress Alto ({stress:.0f})")
                    d_dict["wellness_alerts"] = alerts
    except Exception:
        pass

    # -------------------------------------------------------------------------
    # Sorgente 4: Test Fisici (tabella sessioni_test)
    # -------------------------------------------------------------------------
    try:
        if atleta_id and not str(atleta_id).startswith("mock-"):
            res_t = db.table('sessioni_test').select('*, catalogo_protocolli(nome_protocollo)').eq('atleta_id', atleta_id).gte('data', str(d_start)).lte('data', str(d_end)).execute()
            for t_item in (res_t.data or []):
                d_str = str(t_item.get('data', ''))[:10]
                if d_str in calendar_data:
                    d_dict = calendar_data[d_str]
                    p_obj = t_item.get('catalogo_protocolli') or {}
                    p_name = p_obj.get('nome_protocollo') or t_item.get('nome_test', 'Test')
                    d_dict["test_presenti"].append(p_name)
                    d_dict["test_count"] += 1
    except Exception:
        pass

    # -------------------------------------------------------------------------
    # Sorgente 5: Registro Medico, Fisio & Logistica (tabella registro_medico_fisio)
    # -------------------------------------------------------------------------
    try:
        q_m = db.table('registro_medico_fisio').select('*')
        if atleta_id and not str(atleta_id).startswith("mock-"):
            q_m = q_m.eq('atleta_id', atleta_id)
        elif nome_giocatore:
            q_m = q_m.ilike('nome_giocatore', f"%{nome_giocatore}%")

        res_m = q_m.lte('data_inizio', str(d_end)).gte('data_fine', str(d_start)).execute()
        
        PRIORITY_STATUS = {
            "INDISPONIBILE": 4,
            "LIMITATO": 3,
            "RIPOSO_VIAGGIO": 2,
            "DISPONIBILE": 1
        }

        for rec in (res_m.data or []):
            rec_st = datetime.datetime.strptime(str(rec['data_inizio'])[:10], "%Y-%m-%d").date()
            rec_end = datetime.datetime.strptime(str(rec['data_fine'])[:10], "%Y-%m-%d").date()
            eff_st = max(rec_st, d_start)
            eff_end = min(rec_end, d_end)

            c_rec_d = eff_st
            while c_rec_d <= eff_end:
                d_str = c_rec_d.strftime("%Y-%m-%d")
                if d_str in calendar_data:
                    d_dict = calendar_data[d_str]
                    d_dict["medico_eventi"].append(rec)
                    t_sch = rec.get('tipo_scheda', '')
                    if t_sch in ('INFORTUNIO', 'MALATTIA'):
                        d_dict["has_infortunio"] = True
                    elif t_sch == 'SOVRACCARICO':
                        d_dict["has_sovraccarico"] = True
                    elif t_sch == 'TRATTAMENTO':
                        d_dict["has_trattamento"] = True
                    elif t_sch == 'LOGISTICA':
                        d_dict["has_logistica"] = True

                    st_op = rec.get('status_operativo', 'DISPONIBILE')
                    curr_p = PRIORITY_STATUS.get(d_dict["status_operativo"], 1)
                    new_p = PRIORITY_STATUS.get(st_op, 1)
                    if new_p > curr_p:
                        d_dict["status_operativo"] = st_op

                c_rec_d += datetime.timedelta(days=1)
    except Exception:
        pass

    # -------------------------------------------------------------------------
    # Controllo Soglia 70% Training Load nei giorni a Carico Adattato ('LIMITATO')
    # -------------------------------------------------------------------------
    for d_k, d_dict in calendar_data.items():
        d_dict["tl_media_storica"] = round(tl_media_storica, 1)
        d_dict["soglia_70_adattato"] = round(soglia_70, 1)
        if d_dict.get("status_operativo") == "LIMITATO" and soglia_70 > 0:
            tl_val = float(d_dict.get("training_load_gps", 0) or 0)
            if tl_val > soglia_70:
                d_dict["overload_adattato"] = True
                d_dict["pct_su_media_tl"] = round((tl_val / tl_media_storica) * 100.0, 1) if tl_media_storica > 0 else 0.0

    return calendar_data


def get_athlete_initials(name):
    """Calcola le 2 lettere iniziali dell'atleta per l'avatar monogramma."""
    parts = [p for p in str(name).strip().split() if p]
    if len(parts) >= 2:
        return f"{parts[0][0]}{parts[1][0]}".upper()
    elif len(parts) == 1 and len(parts[0]) > 0:
        return parts[0][:2].upper()
    return "AT"


def render_athlete_hero_strip(ath_name, df_atleta=None, extra_badges=None, extra_info=None):
    """
    Renders an executive compact athlete strip (Opzione A, ~65px) in MOV3 style.
    Features:
    - Glowing avatar monogram with athlete initials
    - Athlete name in prominent bold uppercase (font-size 21px, font-weight 900)
    - M0V3 ATLETA ATTIVO badge
    - Optional smart tags for secondary dropdowns (season, date, session type)
    - Total sessions / last activity info
    """
    if not ath_name:
        return

    initials = get_athlete_initials(ath_name)
    badges_html = []

    # Tag principale Atleta Attivo
    lbl_attivo = tr("M0V3 ATLETA ATTIVO", "M0V3 ACTIVE ATHLETE")
    badges_html.append(
        f"<span style='background:rgba(14,165,233,0.12); color:#0284c7; font-size:11px; font-weight:800; padding:3px 9px; border-radius:6px; border:1px solid rgba(14,165,233,0.25); text-transform:uppercase; display:inline-flex; align-items:center; gap:4px;'>"
        f"<i class='bi bi-person-fill'></i>{lbl_attivo}</span>"
    )

    # Info da df_atleta se fornito
    if df_atleta is not None and not df_atleta.empty:
        n_sess = len(df_atleta)
        lbl_sess_w = tr("sessioni", "sessions")
        badges_html.append(
            f"<span style='background:#f8fafc; color:#475569; font-size:11.5px; font-weight:700; padding:3px 9px; border-radius:6px; border:1px solid #cbd5e1; display:inline-flex; align-items:center; gap:4px;'>"
            f"<i class='bi bi-database' style='color:#0ea5e9;'></i><b>{n_sess}</b> {lbl_sess_w}</span>"
        )
        if 'Date_obj' in df_atleta.columns:
            df_sorted = df_atleta.dropna(subset=['Date_obj']).sort_values('Date_obj', ascending=False)
            if not df_sorted.empty:
                dt_last = df_sorted.iloc[0]['Date_obj']
                diff_d = (datetime.date.today() - dt_last.date()).days
                if diff_d == 0:
                    d_txt = tr("Oggi", "Today")
                elif diff_d == 1:
                    d_txt = tr("Ieri", "Yesterday")
                elif diff_d > 1:
                    d_txt = f"{diff_d} {tr('gg fa', 'd ago')}"
                else:
                    d_txt = dt_last.strftime("%d/%m/%Y")
                lbl_ult = tr("Ultima:", "Latest:")
                dt_formatted = dt_last.strftime("%d/%m/%Y")
                badges_html.append(
                    f"<span style='background:#f8fafc; color:#475569; font-size:11.5px; font-weight:700; padding:3px 9px; border-radius:6px; border:1px solid #cbd5e1; display:inline-flex; align-items:center; gap:4px;'>"
                    f"<i class='bi bi-calendar3' style='color:#0ea5e9;'></i>{lbl_ult} <b>{dt_formatted}</b> ({d_txt})</span>"
                )

    # Badges extra per i filtri secondari affiancati (Stagione, Settimana, Match, ecc.)
    if extra_badges:
        for b in extra_badges:
            if b:
                badges_html.append(
                    f"<span style='background:rgba(56,189,248,0.08); color:#0369a1; font-size:11.5px; font-weight:800; padding:3px 10px; border-radius:6px; border:1px solid rgba(56,189,248,0.3); display:inline-flex; align-items:center; gap:4px;'>"
                    f"<i class='bi bi-funnel-fill' style='color:#0ea5e9;'></i>{b}</span>"
                )

    all_badges_str = "".join(badges_html)

    strip_html = (
        f"<div class='no-print' style='background:white; border:1px solid #e2e8f0; border-left:5px solid #0ea5e9; border-radius:12px; "
        f"padding:10px 16px; margin-top:8px; margin-bottom:18px; box-shadow:0 2px 6px -1px rgba(15,23,42,0.05); font-family:\"Inter\", sans-serif; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px;'>"
        f"<div style='display:flex; align-items:center; gap:14px;'>"
        f"<div style='width:46px; height:46px; border-radius:10px; background:linear-gradient(135deg, #0f172a 0%, #1e293b 100%); "
        f"border:2px solid #0ea5e9; display:flex; align-items:center; justify-content:center; color:#38bdf8; font-size:19px; "
        f"font-weight:900; box-shadow:0 3px 10px rgba(14,165,233,0.25); flex-shrink:0; letter-spacing:0.5px;'>{initials}</div>"
        f"<div>"
        f"<div style='font-size:21px; font-weight:900; color:#0f172a; letter-spacing:-0.4px; line-height:1.15; text-transform:uppercase;'>{ath_name}</div>"
        f"</div>"
        f"</div>"
        f"<div style='display:flex; align-items:center; gap:8px; flex-wrap:wrap;'>"
        f"{all_badges_str}"
        f"</div>"
        f"</div>"
    )
    st.markdown(strip_html, unsafe_allow_html=True)


def render_dual_athlete_strip(ath1, ath2, session_type=None, week=None, extra_badges=None):
    """
    Renders an executive dual-athlete comparison strip (Testa a Testa).
    - Ath1 (Focus): Cyan accent #0ea5e9
    - Ath2 (Benchmark): Amber/orange accent #f59e0b
    - Central VS divider
    - Session type and week context tags
    """
    init1 = get_athlete_initials(ath1)
    init2 = get_athlete_initials(ath2)

    tags = []
    if session_type:
        lbl_tip = tr('Tipologia:', 'Type:')
        tags.append(
            f"<span style='background:#f8fafc; color:#334155; font-size:11.5px; font-weight:800; padding:3px 9px; border-radius:6px; border:1px solid #cbd5e1; display:inline-flex; align-items:center; gap:4px;'>"
            f"<i class='bi bi-tag-fill' style='color:#0ea5e9;'></i>{lbl_tip} <b>{session_type}</b></span>"
        )
    if week:
        lbl_sett = tr('Settimana:', 'Week:')
        tags.append(
            f"<span style='background:#f8fafc; color:#334155; font-size:11.5px; font-weight:800; padding:3px 9px; border-radius:6px; border:1px solid #cbd5e1; display:inline-flex; align-items:center; gap:4px;'>"
            f"<i class='bi bi-calendar-week' style='color:#0ea5e9;'></i>{lbl_sett} <b>{week}</b></span>"
        )
    if extra_badges:
        for b in extra_badges:
            if b:
                tags.append(
                    f"<span style='background:rgba(56,189,248,0.08); color:#0369a1; font-size:11.5px; font-weight:800; padding:3px 10px; border-radius:6px; border:1px solid rgba(56,189,248,0.3); display:inline-flex; align-items:center; gap:4px;'>"
                    f"<i class='bi bi-funnel-fill' style='color:#0ea5e9;'></i>{b}</span>"
                )
    tags_html = "".join(tags)

    lbl_focus = tr("SOGGETTO ANALIZZATO", "ANALYZED SUBJECT")
    lbl_bench = tr("RIFERIMENTO BENCHMARK 100%", "100% BENCHMARK")

    dual_html = (
        f"<div class='no-print' style='background:white; border:1px solid #e2e8f0; border-radius:12px; padding:12px 18px; margin-top:8px; margin-bottom:18px; "
        f"box-shadow:0 2px 6px -1px rgba(15,23,42,0.05); font-family:\"Inter\", sans-serif; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:14px;'>"
        f"<div style='display:flex; align-items:center; gap:14px; flex-wrap:wrap;'>"
        f"<div style='display:flex; align-items:center; gap:10px;'>"
        f"<div style='width:44px; height:44px; border-radius:10px; background:linear-gradient(135deg, #0f172a 0%, #1e293b 100%); "
        f"border:2px solid #0ea5e9; display:flex; align-items:center; justify-content:center; color:#38bdf8; font-size:18px; "
        f"font-weight:900; box-shadow:0 3px 8px rgba(14,165,233,0.25); flex-shrink:0;'>{init1}</div>"
        f"<div>"
        f"<div style='font-size:18px; font-weight:900; color:#0f172a; text-transform:uppercase;'>{ath1}</div>"
        f"<span style='background:rgba(14,165,233,0.12); color:#0284c7; font-size:10px; font-weight:800; padding:2px 7px; border-radius:4px;'>{lbl_focus}</span>"
        f"</div>"
        f"</div>"
        f"<div style='background:#f1f5f9; color:#64748b; font-size:12px; font-weight:900; padding:4px 10px; border-radius:999px; border:1px solid #cbd5e1;'>VS</div>"
        f"<div style='display:flex; align-items:center; gap:10px;'>"
        f"<div style='width:44px; height:44px; border-radius:10px; background:linear-gradient(135deg, #1c1917 0%, #292524 100%); "
        f"border:2px solid #f59e0b; display:flex; align-items:center; justify-content:center; color:#fbbf24; font-size:18px; "
        f"font-weight:900; box-shadow:0 3px 8px rgba(245,158,11,0.25); flex-shrink:0;'>{init2}</div>"
        f"<div>"
        f"<div style='font-size:18px; font-weight:900; color:#0f172a; text-transform:uppercase;'>{ath2}</div>"
        f"<span style='background:rgba(245,158,11,0.12); color:#b45309; font-size:10px; font-weight:800; padding:2px 7px; border-radius:4px;'>{lbl_bench}</span>"
        f"</div>"
        f"</div>"
        f"</div>"
        f"<div style='display:flex; align-items:center; gap:8px; flex-wrap:wrap;'>"
        f"{tags_html}"
        f"</div>"
        f"</div>"
    )
    st.markdown(dual_html, unsafe_allow_html=True)

