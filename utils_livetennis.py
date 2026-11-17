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
                    "match_id": f"LT-{m.get('id')}",
                    "date": dt_str,
                    "date_iso": dt_iso,
                    "opponent": opp_name,
                    "opponent_country": str(opp_country or "").upper(),
                    "opponent_rank": opp_rank,
                    "tournament": m.get("tournament") or "ATP Tour",
                    "round": m.get("round") or "-",
                    "surface": surf,
                    "status": "In corso (Live)" if st_filter == "live" else "In programma",
                    "result": "In corso" if st_filter == "live" else "In programma",
                    "score": score_str,
                    "is_live": (st_filter == "live"),
                    "is_completed": False,
                    "source": "LiveTennis",
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
                })
        except Exception:
            pass

    return matches


def _safe_int_val(val, default=0):
    if val is None or val == "":
        return default
    try:
        return int(float(str(val).strip()))
    except (ValueError, TypeError):
        return default


def _format_duration_str(minutes):
    m_int = _safe_int_val(minutes, 0)
    if m_int <= 0:
        return "-"
    h, m = divmod(m_int, 60)
    return f"{h}h {m:02d}m" if h > 0 else f"{m}m"


def _parse_games_sets_from_score(score_str):
    if not score_str:
        return 0, 0
    games_tot = 0
    sets_tot = 0
    for tok in str(score_str).split():
        m_set = re.match(r"^(\d+)-(\d+)", tok)
        if m_set:
            games_tot += int(m_set.group(1)) + int(m_set.group(2))
            sets_tot += 1
    return games_tot, sets_tot


def _extract_surname(name):
    cleaned = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", str(name or ""))
    tokens = [t for t in _normalize_str(cleaned).split() if len(t) >= 2]
    return tokens[-1] if tokens else ""


def _normalize_score_key(score_str):
    return re.sub(r"\s+", " ", str(score_str or "").strip().lower())


def _fetch_espn_exact_dates(athlete_name, days_back=45):
    """
    Interroga il feed pubblico gratuito ESPN Tennis Scoreboard (0 chiamate LiveTennis)
    per ricavare la data esatta di gioco dei match recenti (incluso ieri).
    """
    results = []
    today = datetime.date.today()
    start_d = (today - datetime.timedelta(days=days_back)).strftime("%Y%m%d")
    end_d = (today + datetime.timedelta(days=7)).strftime("%Y%m%d")

    for tour in ["atp", "wta"]:
        url = f"https://site.api.espn.com/apis/site/v2/sports/tennis/{tour}/scoreboard?dates={start_d}-{end_d}"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (MOV3-Analytics)", "Accept": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception:
            continue

        for ev in data.get("events", []):
            t_name = ev.get("name", "")
            for grp in ev.get("groupings", []):
                for comp in grp.get("competitions", []):
                    comps = comp.get("competitors", [])
                    if len(comps) < 2:
                        continue
                    c_names = [
                        (c.get("athlete", {}).get("displayName") or c.get("roster", {}).get("shortDisplayName") or "")
                        for c in comps
                    ]
                    ath_idx = None
                    for idx, cname in enumerate(c_names):
                        if _is_name_match(athlete_name, cname):
                            ath_idx = idx
                            break
                    if ath_idx is None:
                        continue

                    opp_idx = 1 - ath_idx
                    opp_name = c_names[opp_idx]
                    raw_dt = comp.get("date") or comp.get("startDate") or ""
                    date_ddmmyyyy = ""
                    date_iso = ""
                    try:
                        dt_obj = datetime.datetime.fromisoformat(raw_dt.replace("Z", "+00:00"))
                        date_ddmmyyyy = dt_obj.strftime("%d/%m/%Y")
                        date_iso = dt_obj.strftime("%Y-%m-%d")
                    except Exception:
                        pass

                    st_type = comp.get("status", {}).get("type", {})
                    results.append({
                        "date": date_ddmmyyyy,
                        "date_iso": date_iso,
                        "opponent": opp_name,
                        "opponent_surname": _extract_surname(opp_name),
                        "tournament": t_name,
                        "completed": bool(st_type.get("completed"))
                    })
        if results:
            break

    return results


def fetch_tennisabstract_matches(athlete_name, limit=12):
    """
    Recupera i match conclusi più recenti da Tennis Abstract (gratuito, 0 chiamate LiveTennis)
    completi di tutte le statistiche necessarie per le analisi incrociate GPS
    (punti totali, durata in minuti, ace, doppi falli, punti al servizio, 1ª e 2ª palla, ace avversario),
    arricchendo la data esatta del match tramite il feed pubblico ESPN.
    """
    norm_tokens = _normalize_str(athlete_name).split()
    if len(norm_tokens) < 2:
        return []

    ta_slug = "".join(tok.capitalize() for tok in norm_tokens)
    url = f"https://www.tennisabstract.com/cgi-bin/player-classic.cgi?p={urllib.parse.quote(ta_slug)}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml"
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
    except Exception:
        return []

    idx = html.find("var matchmx = ")
    if idx < 0:
        return []
    arr_start = html.find("[", idx)
    if arr_start < 0:
        return []

    try:
        rows, _ = json.JSONDecoder().raw_decode(html, arr_start)
    except Exception:
        return []

    if not isinstance(rows, list) or not rows:
        return []

    heads = [
        "date", "tourn", "surf", "level", "wl", "rank", "seed", "entry", "round",
        "score", "max", "opp", "orank", "oseed", "oentry", "ohand", "obday",
        "oht", "ocountry", "oactive", "time", "aces", "dfs", "pts", "firsts", "fwon",
        "swon", "games", "saved", "chances", "oaces", "odfs", "opts", "ofirsts",
        "ofwon", "oswon", "ogames", "osaved", "ochances", "obackhand", "chartlink",
        "pslink", "whserver", "matchid", "wh", "roundnum", "matchnum"
    ]

    # Recupera date esatte da ESPN per i match degli ultimi 45 giorni
    espn_dates = _fetch_espn_exact_dates(athlete_name, days_back=45)
    ath_surname = norm_tokens[-1].capitalize()

    parsed_matches = []
    for r in rows[:limit]:
        if not isinstance(r, list) or len(r) < 12:
            continue
        d = dict(zip(heads, r))
        wl = str(d.get("wl", "")).strip().upper()
        if wl not in ("W", "L"):
            continue

        raw_date = str(d.get("date", "")).strip()
        if len(raw_date) != 8 or not raw_date.isdigit():
            continue

        try:
            ta_dt = datetime.datetime.strptime(raw_date, "%Y%m%d").date()
        except Exception:
            continue

        opp_raw = str(d.get("opp", "")).strip()
        opp_cnt = str(d.get("ocountry", "")).strip().upper()
        opp_disp = f"{opp_raw} [{opp_cnt}]" if opp_cnt else opp_raw
        opp_surname = _extract_surname(opp_raw)

        # Affina la data usando ESPN (data reale del match anziché lunedì del torneo)
        final_dt = ta_dt
        exact_date_matched = False
        for em in espn_dates:
            if not em.get("date_iso") or not em.get("opponent_surname"):
                continue
            if em["opponent_surname"] == opp_surname:
                try:
                    e_dt = datetime.date.fromisoformat(em["date_iso"])
                    if -2 <= (e_dt - ta_dt).days <= 14:
                        final_dt = e_dt
                        exact_date_matched = True
                        break
                except Exception:
                    pass

        date_ddmmyyyy = final_dt.strftime("%d/%m/%Y")
        date_iso = final_dt.strftime("%Y-%m-%d")

        tourn = str(d.get("tourn", "ATP Tour")).strip()
        surf_raw = str(d.get("surf", "Hard")).strip()
        surf_low = surf_raw.lower()
        if "clay" in surf_low:
            surf = "Clay"
        elif "grass" in surf_low:
            surf = "Grass"
        else:
            surf = "Hard"

        rnd = str(d.get("round", "-")).strip() or "-"
        score = str(d.get("score", "-")).strip()
        result_it = "Vittoria" if wl == "W" else "Sconfitta"
        matchup = f"{ath_surname} d. {opp_disp}" if wl == "W" else f"{opp_disp} d. {ath_surname}"

        dur_min = _safe_int_val(d.get("time"), 0)
        aces = _safe_int_val(d.get("aces"), 0)
        dfs = _safe_int_val(d.get("dfs"), 0)
        srv_pts = _safe_int_val(d.get("pts"), 0)
        firsts = _safe_int_val(d.get("firsts"), 0)
        seconds = max(0, srv_pts - firsts) if srv_pts > 0 else 0
        opp_pts = _safe_int_val(d.get("opts"), 0)
        tot_pts = (srv_pts + opp_pts) if (srv_pts > 0 and opp_pts > 0) else 0
        opp_aces = _safe_int_val(d.get("oaces"), 0)

        g_score, s_score = _parse_games_sets_from_score(score)
        g_srv = _safe_int_val(d.get("games"), 0)
        g_opp = _safe_int_val(d.get("ogames"), 0)
        games_played = g_score if g_score > 0 else (g_srv + g_opp)
        sets_played = s_score

        ta_mid = str(d.get("matchid", "")).strip()
        m_id = f"TA-{ta_mid}" if ta_mid else f"TA-{raw_date}-{opp_surname}"

        parsed_matches.append({
            "match_id": m_id,
            "date": date_ddmmyyyy,
            "date_iso": date_iso,
            "exact_date": exact_date_matched,
            "opponent": opp_raw,
            "opponent_display": opp_disp,
            "opponent_country": opp_cnt,
            "opponent_rank": _safe_int_val(d.get("orank"), None),
            "rank": _safe_int_val(d.get("rank"), None),
            "tournament": tourn,
            "round": rnd,
            "surface": surf,
            "matchup": matchup,
            "score": score,
            "result": result_it,
            "status": "Concluso",
            "is_live": False,
            "is_completed": True,
            "source": "Tennis Abstract + ESPN" if exact_date_matched else "Tennis Abstract",
            "duration_min": dur_min,
            "duration_str": _format_duration_str(dur_min),
            "total_points": tot_pts,
            "aces": aces,
            "double_faults": dfs,
            "service_points": srv_pts,
            "first_serve_points": firsts,
            "second_serve_points": seconds,
            "opponent_aces": opp_aces,
            "games_played": games_played,
            "sets_played": sets_played
        })

    return parsed_matches


def _get_all_database_matches_raw(athlete_name):
    """Restituisce tutti i match attualmente presenti nel database locale per deduplicazione affidabile."""
    rows = []
    if "cobolli" in str(athlete_name).lower():
        try:
            parquet_path = os.path.join(DATA_DIR, "cobolli_matches.parquet")
            if os.path.exists(parquet_path):
                import pandas as pd
                df_m = pd.read_parquet(parquet_path)
                if not df_m.empty:
                    return df_m.to_dict(orient="records")
        except Exception:
            pass
        try:
            json_path = os.path.join(DATA_DIR, "cobolli_matches.json")
            if os.path.exists(json_path):
                with open(json_path, "r", encoding="utf-8") as f:
                    data_m = json.load(f)
                if isinstance(data_m, list):
                    return data_m
        except Exception:
            pass
    return rows


def _is_match_already_in_db(candidate, db_rows):
    """Verifica se il match candidato è già presente nello storico (per ID, data+avversario o score+avversario±14gg)."""
    cand_id = str(candidate.get("match_id", "")).strip()
    cand_date_str = str(candidate.get("date", ""))[:10]
    cand_iso = str(candidate.get("date_iso", ""))[:10]
    cand_opp_surn = _extract_surname(candidate.get("opponent_display") or candidate.get("opponent", ""))
    cand_score = _normalize_score_key(candidate.get("score", ""))

    cand_dt = None
    try:
        if cand_iso:
            cand_dt = datetime.date.fromisoformat(cand_iso)
    except Exception:
        pass

    for row in db_rows:
        r_id = str(row.get("match_id", "")).strip()
        if cand_id and r_id and cand_id == r_id:
            return True

        r_opp_surn = _extract_surname(row.get("opponent", ""))
        if not cand_opp_surn or not r_opp_surn or cand_opp_surn != r_opp_surn:
            continue

        r_date_str = str(row.get("date", ""))[:10]
        if cand_date_str and r_date_str and cand_date_str == r_date_str:
            return True

        r_iso = str(row.get("date_iso", ""))[:10]
        r_score = _normalize_score_key(row.get("score", ""))
        if cand_dt and r_iso:
            try:
                r_dt = datetime.date.fromisoformat(r_iso)
                delta = abs((cand_dt - r_dt).days)
                if delta <= 14 and cand_score and r_score and cand_score == r_score:
                    return True
                if delta <= 3:
                    return True
            except Exception:
                pass

    return False


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
    Integra i nuovi match selezionati (completi di statistiche Tennis Abstract:
    punti totali, durata, servizio, 1ª/2ª palla, ace, doppi falli, game/set)
    nel file cobolli_matches.parquet e cobolli_matches.json, aggiorna lo snapshot cloud
    e svuota la cache di load_cobolli_matches per renderli subito visibili nelle analisi incrociate.
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

    db_rows = df_old.to_dict(orient="records") if not df_old.empty else []
    added_count = 0
    new_rows = []

    for m in matches:
        if _is_match_already_in_db(m, db_rows):
            continue

        raw_mid = str(m.get("match_id") or "").strip()
        m_id = raw_mid if raw_mid.startswith(("TA-", "LT-", "COB-")) else f"LT-{raw_mid}"
        m_date = str(m.get("date", ""))[:10]
        m_opp = str(m.get("opponent_display") or m.get("opponent") or "N/D")
        if m.get("opponent_country") and "[" not in m_opp:
            m_opp = f"{m_opp} [{m['opponent_country']}]"

        year_val = datetime.date.today().year
        try:
            year_val = int(m_date.split("/")[-1])
        except Exception:
            pass

        dur_min = _safe_int_val(m.get("duration_min"), 0)
        dur_str = m.get("duration_str") or _format_duration_str(dur_min)
        tot_pts = _safe_int_val(m.get("total_points"), 0)
        aces = _safe_int_val(m.get("aces"), 0)
        dfs = _safe_int_val(m.get("double_faults"), 0)
        srv_pts = _safe_int_val(m.get("service_points"), 0)
        p1_pts = _safe_int_val(m.get("first_serve_points"), 0)
        p2_pts = _safe_int_val(m.get("second_serve_points"), 0)
        opp_aces = _safe_int_val(m.get("opponent_aces"), 0)
        games_p = _safe_int_val(m.get("games_played"), 0)
        sets_p = _safe_int_val(m.get("sets_played"), 0)

        res_val = m.get("result") or m.get("status") or "In programma"
        matchup_val = m.get("matchup") or (
            f"Cobolli d. {m_opp}" if res_val == "Vittoria"
            else (f"{m_opp} d. Cobolli" if res_val == "Sconfitta" else f"Cobolli vs {m_opp}")
        )

        dt_parsed = pd.to_datetime(m_date, format="%d/%m/%Y", errors="coerce") if m_date else pd.NaT
        date_obj_val = dt_parsed.date() if pd.notna(dt_parsed) else datetime.date.today()

        row = {
            "match_id": m_id,
            "date": m_date,
            "date_iso": m.get("date_iso") or (dt_parsed.strftime("%Y-%m-%d") if pd.notna(dt_parsed) else datetime.date.today().isoformat()),
            "date_obj": date_obj_val,
            "year": year_val,
            "tournament": m.get("tournament", "ATP Tour"),
            "surface": m.get("surface", "Hard"),
            "round": m.get("round", "-"),
            "type": "Singolare",
            "rank": m.get("rank"),
            "opponent_rank": m.get("opponent_rank"),
            "matchup": matchup_val,
            "opponent": m_opp,
            "score": m.get("score", "In programma"),
            "result": res_val,
            "duration_min": dur_min,
            "duration_str": dur_str,
            "total_points": tot_pts,
            "aces": aces,
            "double_faults": dfs,
            "service_points": srv_pts,
            "first_serve_points": p1_pts,
            "second_serve_points": p2_pts,
            "opponent_aces": opp_aces,
            "games_played": games_p,
            "sets_played": sets_p
        }
        new_rows.append(row)
        db_rows.append(row)
        added_count += 1

    if new_rows:
        df_new = pd.DataFrame(new_rows)
        df_merged = pd.concat([df_old, df_new], ignore_index=True)
        # Allinea il tipo di date_obj per compatibilità PyArrow/Parquet
        if "date_obj" in df_merged.columns:
            df_merged["date_obj"] = pd.to_datetime(df_merged["date"], format="%d/%m/%Y", errors="coerce").dt.date
        try:
            df_merged.to_parquet(parquet_path, index=False)
            _sync_snapshot_safe(parquet_path, "cobolli_matches.parquet")
            df_merged.to_json(json_path, orient="records", date_format="iso", indent=2)
            _sync_snapshot_safe(json_path, "cobolli_matches.json")
        except Exception:
            pass

        # Aggiorna calendario tornei e invalida cache Streamlit di load_cobolli_matches
        try:
            from utils_tennis_matches import _build_tournament_calendar, load_cobolli_matches
            _build_tournament_calendar(df_merged)
            load_cobolli_matches.clear()
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

        all_db_rows = _get_all_database_matches_raw(full_name)
        recent_db_matches = get_recent_database_matches(full_name, limit=5)

        # 1. Match CONCLUSI con statistiche complete (punti, durata, servizio, ace) da Tennis Abstract + data esatta ESPN (0 chiamate LiveTennis)
        completed_new_matches = []
        if found_player_id or new_stats:
            try:
                ta_matches = fetch_tennisabstract_matches(full_name, limit=12)
                for tm in ta_matches:
                    already = _is_match_already_in_db(tm, all_db_rows)
                    tm["already_in_db"] = already
                    if not already:
                        completed_new_matches.append(tm)
            except Exception:
                pass

        # 2. Match LIVE / IN PROGRAMMA da LiveTennis API
        lt_live_upcoming = []
        if found_player_id:
            try:
                lt_live_upcoming = fetch_player_matches(found_player_id, player_name=full_name)
                for lm in lt_live_upcoming:
                    lm["already_in_db"] = _is_match_already_in_db(lm, all_db_rows)
            except Exception:
                lt_live_upcoming = []

        # Ordine in anteprima: prima i NUOVI match conclusi (pronti per le analisi incrociate), poi live/upcoming
        matches_to_load = completed_new_matches + lt_live_upcoming

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
        "schema_version": 3,
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
