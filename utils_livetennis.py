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


def _parse_player_payload(data):
    """Estrae e normalizza le metriche prestazionali dal payload LiveTennis."""
    stats = data.get("stats") or {}
    ratings = stats.get("ratings") or {}
    comp = ratings.get("computed") or {}

    # Tiebreak
    tb = comp.get("tiebreaks") or {}
    tb_pct = float(tb.get("pct", 0.0) or 0.0)
    tb_won = tb.get("won", 0)
    tb_lost = tb.get("lost", 0)

    # Deciding sets
    ds = comp.get("deciding_sets") or {}
    ds_pct = float(ds.get("pct", 0.0) or 0.0)
    ds_won = ds.get("won", 0)
    ds_lost = ds.get("lost", 0)

    # Vs Lefty
    vl = comp.get("vs_lefty") or {}
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

        if new_stats:
            found_count += 1
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
                "changes": {},
                "has_existing_data": bool(old_stats),
                "error": error_msg or "Giocatore non trovato su LiveTennis"
            })

    calls_made_end = get_daily_api_usage().get("calls_count", 0)

    return {
        "timestamp": datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        "total_athletes": len(clean_athletes),
        "found_count": found_count,
        "not_found_count": not_found_count,
        "calls_made": max(0, calls_made_end - calls_made_start),
        "athletes": preview_items
    }


def commit_sync_results(preview_data):
    """
    Salva nel database / cache locale e cloud ESCLUSIVAMENTE gli atleti trovati.
    Quelli non trovati rimangono inalterati con i dati vecchi già presenti.

    Returns:
        tuple (bool success, int updated_count)
    """
    if not preview_data or "athletes" not in preview_data:
        return False, 0

    cache = load_livetennis_cache()
    today_str = datetime.date.today().isoformat()
    now_ts = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    updated_count = 0

    for item in preview_data.get("athletes", []):
        if item.get("status") == "TROVATO" and item.get("new_stats"):
            slug = item["slug"]
            cache[slug] = {
                "fetch_date": today_str,
                "fetch_timestamp": now_ts,
                "raw": item.get("new_raw", {}),
                "stats": item.get("new_stats", {})
            }
            updated_count += 1

    save_livetennis_cache(cache)
    return True, updated_count
