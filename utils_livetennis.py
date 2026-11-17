# Copyright 2026 Riccardo Di Maio - M0V3 S.r.l. Tutti i diritti riservati.
# Proprietary Sports Science & Clinical Performance Intelligence Architecture.
import os
import re
import json
import datetime
import urllib.request
import urllib.error
import urllib.parse
import unicodedata
import streamlit as st

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data_supporto")
CACHE_FILE = os.path.join(DATA_DIR, "livetennis_cache.json")
USAGE_FILE = os.path.join(DATA_DIR, "livetennis_usage.json")
DEFAULT_API_KEY = "twjp_d83c39866384271a62ce3472ea87f1d1"
BASE_URL = "https://api.livetennisapi.com/api/public/v1"
COBOLLI_ID = 652
MAX_DAILY_CALLS = 100


def get_api_key():
    try:
        if hasattr(st, "secrets") and "LIVE_TENNIS_API_KEY" in st.secrets:
            return st.secrets["LIVE_TENNIS_API_KEY"]
    except Exception:
        pass
    return os.environ.get("LIVE_TENNIS_API_KEY", DEFAULT_API_KEY)


def _sync_snapshot_safe(local_path, remote_name):
    """Sincronizza in background il file con lo snapshot cloud di Supabase Storage."""
    try:
        from utils import upload_binary_snapshot
        upload_binary_snapshot(local_path, remote_name)
    except Exception:
        pass


def _download_snapshot_safe(remote_name):
    """Tenta il download di un file dallo snapshot cloud Supabase."""
    try:
        from utils import download_binary_snapshot
        return download_binary_snapshot(remote_name)
    except Exception:
        return None


def get_daily_api_usage():
    """
    Restituisce le statistiche di utilizzo giornaliero delle chiamate API LiveTennis.
    Quota gratuita: 100 chiamate/giorno con reset a mezzanotte (data ISO).
    """
    today_str = datetime.date.today().isoformat()
    usage = {
        "date": today_str,
        "calls_count": 0,
        "calls_limit": MAX_DAILY_CALLS,
        "remaining": MAX_DAILY_CALLS,
        "history": [],
        "last_call": None
    }

    if not os.path.exists(USAGE_FILE):
        # Tenta download snapshot
        b_data = _download_snapshot_safe("livetennis_usage.json")
        if b_data:
            try:
                os.makedirs(DATA_DIR, exist_ok=True)
                with open(USAGE_FILE, "wb") as f:
                    f.write(b_data)
            except Exception:
                pass

    if os.path.exists(USAGE_FILE):
        try:
            with open(USAGE_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            if saved.get("date") == today_str:
                usage["calls_count"] = int(saved.get("calls_count", 0))
                usage["remaining"] = max(0, MAX_DAILY_CALLS - usage["calls_count"])
                usage["history"] = saved.get("history", [])
                usage["last_call"] = saved.get("last_call")
            else:
                # Giorno cambiato: reset contatore, preserva storico recente
                prev_hist = saved.get("history", [])[-30:] if isinstance(saved.get("history"), list) else []
                usage["history"] = prev_hist
                save_daily_api_usage(usage)
        except Exception:
            pass

    return usage


def save_daily_api_usage(usage_data):
    """Salva il contatore chiamate su disco e sincronizza con lo snapshot cloud."""
    os.makedirs(DATA_DIR, exist_ok=True)
    try:
        with open(USAGE_FILE, "w", encoding="utf-8") as f:
            json.dump(usage_data, f, ensure_ascii=False, indent=2)
        _sync_snapshot_safe(USAGE_FILE, "livetennis_usage.json")
    except Exception:
        pass


def record_api_call(endpoint, status_code, player_name="", note=""):
    """
    Registra una singola chiamata API effettuata, incrementando il contatore giornaliero.
    """
    today_str = datetime.date.today().isoformat()
    usage = get_daily_api_usage()

    if usage.get("date") != today_str:
        usage["date"] = today_str
        usage["calls_count"] = 0

    usage["calls_count"] = int(usage.get("calls_count", 0)) + 1
    usage["remaining"] = max(0, MAX_DAILY_CALLS - usage["calls_count"])

    now_iso = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    entry = {
        "timestamp": now_iso,
        "endpoint": endpoint,
        "status": status_code,
        "player": player_name,
        "note": note
    }
    history = usage.get("history", [])
    history.append(entry)
    usage["history"] = history[-50:]  # mantieni ultime 50 chiamate
    usage["last_call"] = entry

    save_daily_api_usage(usage)
    return usage


def load_livetennis_cache():
    """Carica la cache locale con fallback su snapshot cloud."""
    if not os.path.exists(CACHE_FILE):
        b_data = _download_snapshot_safe("livetennis_cache.json")
        if b_data:
            try:
                os.makedirs(DATA_DIR, exist_ok=True)
                with open(CACHE_FILE, "wb") as f:
                    f.write(b_data)
            except Exception:
                pass

    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_livetennis_cache(cache_data):
    """Salva la cache locale e sincronizza lo snapshot cloud."""
    os.makedirs(DATA_DIR, exist_ok=True)
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
        _sync_snapshot_safe(CACHE_FILE, "livetennis_cache.json")
    except Exception:
        pass


def _api_request(endpoint, player_name=""):
    """
    Esegue una richiesta HTTP a LiveTennis API verificando la quota giornaliera.
    """
    usage = get_daily_api_usage()
    if usage["remaining"] <= 0:
        raise RuntimeError("Quota limite di 100 chiamate giornaliere LiveTennis raggiunta. Riprova domani.")

    api_key = get_api_key()
    url = f"{BASE_URL}{endpoint}" if endpoint.startswith("/") else f"{BASE_URL}/{endpoint}"
    headers = {
        "X-API-Key": api_key,
        "Accept": "application/json",
        "User-Agent": "MOV3-Analytics/1.0"
    }

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            status = resp.status
            record_api_call(endpoint, status, player_name=player_name)
            if status == 200:
                return json.loads(resp.read().decode("utf-8"))
            raise RuntimeError(f"LiveTennis API status code: {status}")
    except urllib.error.HTTPError as e:
        record_api_call(endpoint, e.code, player_name=player_name, note=f"HTTP Error {e.code}")
        raise
    except Exception as e:
        record_api_call(endpoint, 0, player_name=player_name, note=str(e))
        raise


def _normalize_str(text):
    if not text:
        return ""
    norm = unicodedata.normalize('NFKD', str(text)).encode('ASCII', 'ignore').decode('utf-8')
    return norm.strip().lower()


def _slugify(name):
    norm = _normalize_str(name)
    return re.sub(r'[^a-z0-9]+', '_', norm).strip('_')


def _is_name_match(athlete_query, candidate_name):
    """
    Verifica se il nome del candidato corrisponde realmente all'atleta cercato.
    Richiede che il cognome corrisponda e che il nome sia coerente (se presente).
    """
    q_norm = _normalize_str(athlete_query)
    c_norm = _normalize_str(candidate_name)
    if not q_norm or not c_norm:
        return False
    if q_norm == c_norm:
        return True
    q_tokens = set(q_norm.split())
    c_tokens = set(c_norm.split())
    if len(q_tokens) >= 2:
        if q_tokens.issubset(c_tokens) or c_tokens.issubset(q_tokens):
            return True
        q_parts = q_norm.split()
        if q_parts[-1] in c_tokens and any(p in c_tokens for p in q_parts[:-1]):
            return True
        return False
    return q_norm in c_tokens


def search_livetennis_player(query):
    """
    Cerca un giocatore su LiveTennis API tramite nome/cognome.
    Filtra i doppi (is_doubles_team) e seleziona il miglior match singolare.
    """
    q_clean = query.strip()
    if not q_clean:
        return None

    endpoint = f"/players?search={urllib.parse.quote(q_clean)}"
    data = _api_request(endpoint, player_name=q_clean)
    items = data.get("data", []) if isinstance(data, dict) else []

    # Filtra team di doppio
    singles = [x for x in items if not x.get("is_doubles_team") and "/" not in str(x.get("name", ""))]
    if not singles and items:
        singles = [x for x in items if not x.get("is_doubles_team")]

    if not singles:
        return None

    # Ricerca corrispondenza rigorosa
    for p in singles:
        cand_name = p.get("name", "")
        if _is_name_match(q_clean, cand_name):
            return p

    return None


def fetch_player_details(player_id, player_name=""):
    """
    Scarica il profilo completo e le statistiche dettagliate di un giocatore da LiveTennis API.
    """
    endpoint = f"/players/{player_id}"
    raw_data = _api_request(endpoint, player_name=player_name)
    parsed = _parse_player_payload(raw_data)
    return parsed, raw_data


def fetch_player_matches(player_id, player_name=""):
    """
    Recupera i match (live e upcoming) per il giocatore specificato da LiveTennis API.
    Restituisce un elenco formattato con data precisa, avversario (con chi ha giocato),
    torneo, superficie e stato del match.
    """
    matches = []
    # Interroga sia i match in corso (live) che quelli programmati (upcoming)
    for st_filter in ["live", "upcoming"]:
        endpoint = f"/matches?status={st_filter}&player={player_id}"
        try:
            raw = _api_request(endpoint, player_name=player_name)
            data_items = raw.get("data", []) if isinstance(raw, dict) else []
            for m in data_items:
                p1 = m.get("players", {}).get("p1", {}) or {}
                p2 = m.get("players", {}).get("p2", {}) or {}

                p1_id = p1.get("id")
                p2_id = p2.get("id")
                p1_name = p1.get("name", "")
                p2_name = p2.get("name", "")

                # Identifica chi è l'atleta e chi è l'avversario ("CON CHI HA GIOCATO")
                if p1_id == player_id or (player_name and _normalize_str(player_name) in _normalize_str(p1_name)):
                    opp_name = p2_name or "N/D"
                    opp_country = p2.get("country", "")
                    opp_rank = p2.get("ranking")
                else:
                    opp_name = p1_name or "N/D"
                    opp_country = p1.get("country", "")
                    opp_rank = p1.get("ranking")

                raw_dt = m.get("scheduled_time") or m.get("created_at") or ""
                dt_str = raw_dt
                dt_iso = ""
                try:
                    dt_obj = datetime.datetime.fromisoformat(raw_dt.replace("Z", "+00:00"))
                    dt_str = dt_obj.strftime("%d/%m/%Y %H:%M")
                    dt_iso = dt_obj.strftime("%Y-%m-%d")
                except Exception:
                    pass

                score_obj = m.get("score")
                score_str = "In programma" if st_filter == "upcoming" else "In corso (Live)"
                if isinstance(score_obj, dict):
                    sets = score_obj.get("sets")
                    if sets:
                        score_str = f"Set: {sets}"

                surf = m.get("surface") or "Hard"
                if m.get("indoor"):
                    surf += " (Indoor)"

                matches.append({
                    "match_id": m.get("id"),
                    "date": dt_str,
                    "date_iso": dt_iso,
                    "opponent": opp_name,
                    "opponent_country": str(opp_country or "").upper(),
                    "opponent_rank": opp_rank,
                    "tournament": m.get("tournament") or "ATP Tour",
                    "round": m.get("round") or "-",
                    "surface": surf,
                    "status": "In corso (Live)" if st_filter == "live" else "In programma",
                    "score": score_str,
                    "is_live": (st_filter == "live")
                })
        except Exception:
            pass

    return matches


def get_recent_database_matches(athlete_name, limit=5):
    """
    Recupera gli ultimi match ufficiali già registrati nel database per l'atleta,
    permettendo all'utente di verificare lo stato attuale e riconoscere i nuovi match.
    """
    matches = []
    # 1. Se Cobolli, legge cobolli_matches.parquet (o fallback JSON senza dipendenza pandas)
    if "cobolli" in str(athlete_name).lower():
        try:
            parquet_path = os.path.join(DATA_DIR, "cobolli_matches.parquet")
            if os.path.exists(parquet_path):
                import pandas as pd
                df_m = pd.read_parquet(parquet_path)
                if not df_m.empty and "date_iso" in df_m.columns:
                    df_sorted = df_m.sort_values(by="date_iso", ascending=False).head(limit)
                    for _, row in df_sorted.iterrows():
                        matches.append({
                            "date": str(row.get("date", "")),
                            "date_iso": str(row.get("date_iso", "")),
                            "opponent": str(row.get("opponent", "N/D")),
                            "tournament": str(row.get("tournament", "N/D")),
                            "round": str(row.get("round", "-")),
                            "score": str(row.get("score", "-")),
                            "result": str(row.get("result", "-")),
                            "surface": str(row.get("surface", "-"))
                        })
                    return matches
        except Exception:
            pass

        try:
            json_path = os.path.join(DATA_DIR, "cobolli_matches.json")
            if os.path.exists(json_path):
                with open(json_path, "r", encoding="utf-8") as f:
                    data_m = json.load(f)
                if isinstance(data_m, list) and data_m:
                    sorted_m = sorted(data_m, key=lambda x: str(x.get("date_iso", "")), reverse=True)[:limit]
                    for row in sorted_m:
                        matches.append({
                            "date": str(row.get("date", "")),
                            "date_iso": str(row.get("date_iso", "")),
                            "opponent": str(row.get("opponent", "N/D")),
                            "tournament": str(row.get("tournament", "N/D")),
                            "round": str(row.get("round", "-")),
                            "score": str(row.get("score", "-")),
                            "result": str(row.get("result", "-")),
                            "surface": str(row.get("surface", "-"))
                        })
                    return matches
        except Exception:
            pass

    # 2. Fallback su database_storico
    try:
        from utils import load_local_database
        df_db = load_local_database()
        if df_db is not None and not df_db.empty and "Players" in df_db.columns and "Tipologia Sessione" in df_db.columns:
            df_ath = df_db[(df_db["Players"].astype(str).str.lower().str.contains(athlete_name.lower(), na=False)) &
                           (df_db["Tipologia Sessione"].astype(str).str.lower().isin(["match", "match doppio"]))].copy()
            if not df_ath.empty:
                df_ath = df_ath.sort_values(by="Date", ascending=False).head(limit)
                for _, row in df_ath.iterrows():
                    matches.append({
                        "date": str(row.get("Date", ""))[:10],
                        "opponent": str(row.get("Session", "Match")),
                        "tournament": str(row.get("Tipologia Campo", "Campo")),
                        "round": "-",
                        "score": f"{row.get('Minuti', 0)} min",
                        "result": "Disputato",
                        "surface": str(row.get("Tipologia Campo", "-"))
                    })
    except Exception:
        pass

    return matches


def sync_matches_to_parquet(matches, athlete_name="Flavio Cobolli"):
    """
    Integra i nuovi match trovati via LiveTennis nel file cobolli_matches.parquet
    ed esegue l'upload dello snapshot cloud.
    """
    if not matches or "cobolli" not in athlete_name.lower():
        return 0

    parquet_path = os.path.join(DATA_DIR, "cobolli_matches.parquet")
    json_path = os.path.join(DATA_DIR, "cobolli_matches.json")
    if not os.path.exists(parquet_path):
        return 0

    import pandas as pd
    try:
        df_old = pd.read_parquet(parquet_path)
    except Exception:
        return 0

    added_count = 0
    new_rows = []
    existing_match_ids = set(df_old["match_id"].dropna().astype(str).tolist()) if "match_id" in df_old.columns else set()
    existing_keys = set(zip(df_old["date"].astype(str), df_old["opponent"].astype(str))) if "date" in df_old.columns and "opponent" in df_old.columns else set()

    for m in matches:
        m_id = f"LT-{m.get('match_id')}"
        m_date = str(m.get("date", ""))[:10]
        m_opp = str(m.get("opponent", "N/D"))

        if m_id in existing_match_ids or (m_date, m_opp) in existing_keys:
            continue

        year_val = 2026
        try:
            year_val = int(m_date.split("/")[-1])
        except Exception:
            pass

        row = {
            "match_id": m_id,
            "date": m_date,
            "date_iso": m.get("date_iso") or datetime.date.today().isoformat(),
            "date_obj": pd.to_datetime(m_date, format="%d/%m/%Y", errors="coerce") if m_date else pd.Timestamp.today().normalize(),
            "year": year_val,
            "tournament": m.get("tournament", "ATP Tour"),
            "surface": m.get("surface", "Hard"),
            "round": m.get("round", "-"),
            "type": "Singolare",
            "rank": None,
            "opponent_rank": m.get("opponent_rank"),
            "matchup": f"Cobolli vs {m_opp}",
            "opponent": m_opp,
            "score": m.get("score", "In programma"),
            "result": m.get("status", "In programma"),
            "duration_min": 0,
            "duration_str": "-",
            "total_points": 0,
            "aces": 0,
            "double_faults": 0,
            "service_points": 0,
            "first_serve_points": 0,
            "second_serve_points": 0,
            "opponent_aces": 0,
            "games_played": 0,
            "sets_played": 0
        }
        new_rows.append(row)
        added_count += 1
        existing_match_ids.add(m_id)
        existing_keys.add((m_date, m_opp))

    if new_rows:
        df_new = pd.DataFrame(new_rows)
        df_merged = pd.concat([df_old, df_new], ignore_index=True)
        try:
            df_merged.to_parquet(parquet_path, index=False)
            _sync_snapshot_safe(parquet_path, "cobolli_matches.parquet")
            if os.path.exists(json_path):
                df_merged.to_json(json_path, orient="records", date_format="iso", indent=2)
                _sync_snapshot_safe(json_path, "cobolli_matches.json")
        except Exception:
            pass

    return added_count


def _parse_player_payload(data):
    """Estrae e normalizza le metriche prestazionali dal payload LiveTennis."""
    if isinstance(data, dict) and isinstance(data.get("data"), dict) and "stats" not in data:
        data = data["data"]
    stats = data.get("stats") or {}
    ratings = stats.get("ratings") or {}
    comp = ratings.get("computed") or {}

    # Tiebreak (supporta sia formato piatto che annidato sotto "overall")
    tb_raw = comp.get("tiebreaks") or {}
    tb = tb_raw.get("overall") if isinstance(tb_raw.get("overall"), dict) else tb_raw
    tb_pct = float(tb.get("pct", 0.0) or 0.0)
    tb_won = tb.get("w", tb.get("won", 0)) or 0
    tb_lost = tb.get("l", tb.get("lost", 0)) or 0

    # Deciding sets
    ds_raw = comp.get("deciding_sets") or {}
    ds = ds_raw.get("overall") if isinstance(ds_raw.get("overall"), dict) else ds_raw
    ds_pct = float(ds.get("pct", 0.0) or 0.0)
    ds_won = ds.get("w", ds.get("won", 0)) or 0
    ds_lost = ds.get("l", ds.get("lost", 0)) or 0

    # Vs Lefty
    vl_raw = comp.get("vs_lefty") or {}
    vl = vl_raw.get("overall") if isinstance(vl_raw.get("overall"), dict) else vl_raw
    vl_pct = float(vl.get("pct", 0.0) or 0.0)

    hand_val = data.get("hand")
    if hand_val == "R":
        hand_str = "Destrorso (Right-handed)"
    elif hand_val == "L":
        hand_str = "Mancino (Left-handed)"
    else:
        hand_str = str(hand_val or "N/D")

    backhand_val = data.get("backhand")
    if backhand_val == 2:
        backhand_str = "A due mani (Two-handed)"
    elif backhand_val == 1:
        backhand_str = "A una mano (One-handed)"
    else:
        backhand_str = str(backhand_val or "N/D")

    return {
        "id": data.get("id"),
        "name": data.get("name", "N/D"),
        "ranking": data.get("ranking"),
        "ranking_points": data.get("ranking_points"),
        "ranking_movement": data.get("ranking_movement", "same"),
        "ranking_status": data.get("ranking_status", "ranked"),
        "tiebreak_pct": tb_pct,
        "tiebreak_record": f"{tb_won}W - {tb_lost}L",
        "deciding_set_pct": ds_pct,
        "deciding_set_record": f"{ds_won}W - {ds_lost}L",
        "vs_lefty_pct": vl_pct,
        "country": (data.get("country") or "N/D").upper(),
        "hand": hand_str,
        "backhand": backhand_str,
        "birthday": data.get("birthday"),
        "last_sync": datetime.datetime.now().strftime("%H:%M"),
        "sync_date": datetime.date.today().strftime("%d/%m/%Y"),
        "is_live": True
    }


def get_athlete_live_stats(athlete_name):
    """
    Recupera le statistiche LiveTennis salvate nella cache per un dato atleta.
    """
    if not athlete_name:
        return None
    cache = load_livetennis_cache()
    slug = _slugify(athlete_name)

    if slug in cache and "stats" in cache[slug]:
        return cache[slug]["stats"]

    # Ricerca per confronto normalizzato dei nomi
    norm_ath = _normalize_str(athlete_name)
    for k, v in cache.items():
        if isinstance(v, dict):
            c_name = _normalize_str(v.get("stats", {}).get("name", ""))
            if c_name and (c_name == norm_ath or norm_ath in c_name or c_name in norm_ath):
                return v.get("stats")

    # Fallback specifico Cobolli
    if "cobolli" in norm_ath and "flavio_cobolli" in cache and "stats" in cache["flavio_cobolli"]:
        return cache["flavio_cobolli"]["stats"]

    return None


def fetch_cobolli_live_stats(force_refresh=False):
    """
    Recupera le statistiche Live ATP di Flavio Cobolli con logica di caching giornaliero.
    Effettua al massimo 1 chiamata al giorno per preservare la quota API.
    """
    today_str = datetime.date.today().isoformat()
    cache = load_livetennis_cache()
    cobolli_cache = cache.get("flavio_cobolli", {})

    last_date = cobolli_cache.get("fetch_date")
    if not force_refresh and last_date == today_str and "stats" in cobolli_cache:
        return cobolli_cache["stats"]

    try:
        parsed, raw_data = fetch_player_details(COBOLLI_ID, player_name="Flavio Cobolli")
        cache["flavio_cobolli"] = {
            "fetch_date": today_str,
            "fetch_timestamp": datetime.datetime.now().strftime("%d/%m/%Y %H:%M"),
            "raw": raw_data,
            "stats": parsed
        }
        save_livetennis_cache(cache)
        return parsed
    except Exception:
        if "stats" in cobolli_cache:
            st_data = dict(cobolli_cache["stats"])
            st_data["is_offline_cache"] = True
            st_data["cache_warning"] = f"Dati offline (ultimo aggiornamento: {cobolli_cache.get('fetch_timestamp', 'N/D')})"
            return st_data

    return _default_cobolli_stats()


def _default_cobolli_stats():
    return {
        "id": COBOLLI_ID,
        "name": "Flavio Cobolli",
        "ranking": 6,
        "ranking_points": 3690,
        "ranking_movement": "same",
        "ranking_status": "ranked",
        "tiebreak_pct": 80.0,
        "tiebreak_record": "120W - 30L",
        "deciding_set_pct": 61.9,
        "deciding_set_record": "91W - 56L",
        "vs_lefty_pct": 60.3,
        "country": "ITA",
        "hand": "Destrorso (Right-handed)",
        "backhand": "A due mani (Two-handed)",
        "last_sync": "22:00",
        "sync_date": datetime.date.today().strftime("%d/%m/%Y"),
        "is_live": False
    }


def preview_sync_all_athletes(athletes_input):
    """
    Esegue la chiamata istantanea a LiveTennis per tutti i giocatori in lista atleti
    e genera un'anteprima dettagliata (chi e cosa sta per essere caricato).
    NON modifica la cache né il database fino a successiva conferma dell'utente.

    Args:
        athletes_input: lista di stringhe di nomi o lista di dizionari con 'nome' e 'cognome'
    Returns:
        dict con il resoconto completo dell'anteprima
    """
    # Normalizza la lista di atleti
    clean_athletes = []
    seen = set()
    for item in athletes_input:
        if isinstance(item, dict):
            nome = str(item.get("nome", "")).strip()
            cognome = str(item.get("cognome", "")).strip()
            full_name = f"{nome} {cognome}".strip()
            ath_id = item.get("id")
        else:
            full_name = str(item).strip()
            ath_id = None

        if full_name and full_name.lower() not in seen:
            seen.add(full_name.lower())
            clean_athletes.append({"full_name": full_name, "id": ath_id})

    cache = load_livetennis_cache()
    preview_items = []
    found_count = 0
    not_found_count = 0
    calls_made_start = get_daily_api_usage().get("calls_count", 0)

    for ath in clean_athletes:
        full_name = ath["full_name"]
        slug = _slugify(full_name)
        cached_entry = cache.get(slug, {})
        old_stats = cached_entry.get("stats")

        # Cerca ID LiveTennis se già noto
        known_id = None
        if "cobolli" in full_name.lower():
            known_id = COBOLLI_ID
        elif cached_entry.get("raw", {}).get("id"):
            known_id = cached_entry["raw"]["id"]
        elif old_stats and old_stats.get("id"):
            known_id = old_stats["id"]

        new_stats = None
        new_raw = None
        found_player_id = None
        error_msg = None

        try:
            # 1. Se ID già noto, chiamata diretta al profilo (/players/{id})
            if known_id:
                new_stats, new_raw = fetch_player_details(known_id, player_name=full_name)
                found_player_id = known_id
            else:
                # 2. Altrimenti, ricerca per nome/cognome (/players?search=...)
                matched_player = search_livetennis_player(full_name)
                if not matched_player:
                    # Tenta con solo cognome se composto da più parti, ma convalida sempre il match
                    parts = full_name.split()
                    if len(parts) > 1 and len(parts[-1]) >= 3:
                        cand = search_livetennis_player(parts[-1])
                        if cand and _is_name_match(full_name, cand.get("name", "")):
                            matched_player = cand

                if matched_player and matched_player.get("id"):
                    found_player_id = matched_player["id"]
                    new_stats, new_raw = fetch_player_details(found_player_id, player_name=full_name)

        except Exception as e:
            error_msg = str(e)

        matches_to_load = []
        if found_player_id:
            try:
                matches_to_load = fetch_player_matches(found_player_id, player_name=full_name)
            except Exception:
                matches_to_load = []

        recent_db_matches = get_recent_database_matches(full_name, limit=5)

        # Marca ogni match API indicando se è già presente nel database (confronto su data + avversario)
        existing_db_keys = set()
        for dbm in recent_db_matches:
            db_d = str(dbm.get("date", ""))[:10]
            db_opp = _normalize_str(dbm.get("opponent", ""))
            existing_db_keys.add((db_d, db_opp))

        for m in matches_to_load:
            m_d = str(m.get("date", ""))[:10]
            m_opp = _normalize_str(m.get("opponent", ""))
            is_dup = False
            for (db_d, db_opp) in existing_db_keys:
                if db_d == m_d and m_opp and (m_opp in db_opp or db_opp in m_opp):
                    is_dup = True
                    break
            m["already_in_db"] = is_dup

        if new_stats:
            found_count += 1
            # Protegge le metriche storiche se l'API restituisce 0.0 ma in cache erano già presenti
            if old_stats:
                if new_stats.get("tiebreak_pct", 0.0) == 0.0 and new_stats.get("tiebreak_record") == "0W - 0L" and old_stats.get("tiebreak_pct", 0.0) > 0:
                    new_stats["tiebreak_pct"] = old_stats["tiebreak_pct"]
                    new_stats["tiebreak_record"] = old_stats.get("tiebreak_record", "0W - 0L")
                if new_stats.get("deciding_set_pct", 0.0) == 0.0 and new_stats.get("deciding_set_record") == "0W - 0L" and old_stats.get("deciding_set_pct", 0.0) > 0:
                    new_stats["deciding_set_pct"] = old_stats["deciding_set_pct"]
                    new_stats["deciding_set_record"] = old_stats.get("deciding_set_record", "0W - 0L")
                if new_stats.get("vs_lefty_pct", 0.0) == 0.0 and old_stats.get("vs_lefty_pct", 0.0) > 0:
                    new_stats["vs_lefty_pct"] = old_stats["vs_lefty_pct"]
            # Calcola differenze rispetto ai dati precedenti
            changes = {}
            if old_stats:
                old_rank = old_stats.get("ranking")
                new_rank = new_stats.get("ranking")
                if old_rank != new_rank:
                    changes["ranking"] = {"old": old_rank, "new": new_rank}

                old_pts = old_stats.get("ranking_points")
                new_pts = new_stats.get("ranking_points")
                if old_pts != new_pts:
                    changes["points"] = {"old": old_pts, "new": new_pts}

                old_tb = old_stats.get("tiebreak_pct")
                new_tb = new_stats.get("tiebreak_pct")
                if old_tb != new_tb:
                    changes["tiebreak_pct"] = {"old": old_tb, "new": new_tb}

            preview_items.append({
                "athlete_name": full_name,
                "slug": slug,
                "status": "TROVATO",
                "player_id": found_player_id,
                "old_stats": old_stats,
                "new_stats": new_stats,
                "new_raw": new_raw,
                "matches_to_load": matches_to_load,
                "recent_db_matches": recent_db_matches,
                "changes": changes,
                "has_existing_data": bool(old_stats),
                "error": None
            })
        else:
            not_found_count += 1
            preview_items.append({
                "athlete_name": full_name,
                "slug": slug,
                "status": "NON_TROVATO",
                "player_id": None,
                "old_stats": old_stats,
                "new_stats": None,
                "new_raw": None,
                "matches_to_load": [],
                "recent_db_matches": recent_db_matches,
                "changes": {},
                "has_existing_data": bool(old_stats),
                "error": error_msg or "Giocatore non trovato su LiveTennis"
            })

    calls_made_end = get_daily_api_usage().get("calls_count", 0)

    return {
        "schema_version": 2,
        "timestamp": datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        "total_athletes": len(clean_athletes),
        "found_count": found_count,
        "not_found_count": not_found_count,
        "calls_made": max(0, calls_made_end - calls_made_start),
        "athletes": preview_items
    }


def commit_sync_results(preview_data, selected_matches_by_slug=None):
    """
    Salva nel database / cache locale e cloud ESCLUSIVAMENTE gli atleti trovati
    (e solo i match selezionati dall'utente in anteprima, se specificato).
    Quelli non trovati rimangono inalterati con i dati vecchi già presenti.

    Returns:
        tuple (bool success, int updated_count, int added_matches_count)
    """
    if not preview_data or "athletes" not in preview_data:
        return False, 0, 0

    cache = load_livetennis_cache()
    today_str = datetime.date.today().isoformat()
    now_ts = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    updated_count = 0
    added_matches_total = 0

    for item in preview_data.get("athletes", []):
        if item.get("status") == "TROVATO" and item.get("new_stats"):
            slug = item["slug"]
            if selected_matches_by_slug is not None and slug in selected_matches_by_slug:
                matches_to_save = selected_matches_by_slug[slug]
            else:
                matches_to_save = item.get("matches_to_load", [])

            cache[slug] = {
                "fetch_date": today_str,
                "fetch_timestamp": now_ts,
                "raw": item.get("new_raw", {}),
                "stats": item.get("new_stats", {}),
                "matches": matches_to_save
            }
            updated_count += 1

            # Sincronizza i nuovi match selezionati se presenti nel file parquet dello storico
            if matches_to_save:
                added_n = sync_matches_to_parquet(matches_to_save, athlete_name=item["athlete_name"])
                added_matches_total += added_n

    save_livetennis_cache(cache)
    return True, updated_count, added_matches_total
