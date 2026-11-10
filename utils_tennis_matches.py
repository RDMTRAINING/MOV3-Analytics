import os
import re
import json
import datetime
from datetime import timedelta
import pandas as pd
import streamlit as st

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data_supporto")
EXCEL_PATH = os.path.join(DATA_DIR, "STORICO MATCH COBOLLI.xlsx")
CACHE_PARQUET = os.path.join(DATA_DIR, "cobolli_matches.parquet")
CACHE_JSON = os.path.join(DATA_DIR, "cobolli_matches.json")
LINKS_JSON = os.path.join(DATA_DIR, "match_gps_links.json")
CALENDAR_JSON = os.path.join(DATA_DIR, "calendario_tornei.json")


def _parse_time_min(val):
    if val is None:
        return 0, "-"
    if isinstance(val, timedelta):
        tot_min = int(val.total_seconds() // 60)
    elif isinstance(val, datetime.time):
        tot_min = val.hour * 60 + val.minute
    elif isinstance(val, (int, float)):
        tot_min = int(round(val * 24 * 60))
    elif isinstance(val, str):
        parts = val.strip().split(":")
        if len(parts) == 3:
            try:
                tot_min = int(parts[0]) * 60 + int(parts[1])
            except ValueError:
                tot_min = 0
        elif len(parts) == 2:
            try:
                tot_min = int(parts[0])
            except ValueError:
                tot_min = 0
        else:
            tot_min = 0
    else:
        tot_min = 0
    
    h, m = divmod(tot_min, 60)
    fmt = f"{h}h {m:02d}m" if h > 0 else f"{m}m"
    return tot_min, fmt


def _safe_int(val, default=0):
    if val is None or pd.isna(val):
        return default
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return default


def parse_and_cache_cobolli_matches(force=False):
    """
    Legge 'STORICO MATCH COBOLLI.xlsx', normalizza tutte le partite di singolare e doppio,
    calcola durate, esiti (W/L), avversari, e salva una cache super veloce (.parquet e .json).
    """
    if not force and os.path.exists(CACHE_PARQUET) and os.path.exists(EXCEL_PATH):
        if os.path.getmtime(CACHE_PARQUET) >= os.path.getmtime(EXCEL_PATH):
            try:
                df = pd.read_parquet(CACHE_PARQUET)
                return df
            except Exception:
                pass

    if not os.path.exists(EXCEL_PATH):
        return pd.DataFrame()

    import openpyxl
    wb = openpyxl.load_workbook(EXCEL_PATH, data_only=True)
    ws = wb.active

    matches = []
    is_doubles = False

    for r in range(3, ws.max_row + 1):
        c1 = ws.cell(r, 1).value
        if c1 is not None:
            s_c1 = str(c1).strip().upper()
            if s_c1 == "DOPPIO":
                is_doubles = True
                continue
            if s_c1 in ["DATE", "DATA"]:
                continue
        if not c1:
            continue

        d_clean = str(c1).replace("\u2011", "-").replace("\xa0", " ").strip()
        try:
            dt = pd.to_datetime(d_clean, dayfirst=True)
            if pd.isna(dt):
                continue
        except Exception:
            continue

        tourn = str(ws.cell(r, 2).value or "").strip()
        surf_raw = str(ws.cell(r, 3).value or "Hard").strip()
        surf_low = surf_raw.lower()
        if "clay" in surf_low or "terra" in surf_low:
            surf = "Clay"
        elif "grass" in surf_low or "erba" in surf_low:
            surf = "Grass"
        else:
            surf = "Hard"

        rd = str(ws.cell(r, 4).value or "-").strip()
        rk = _safe_int(ws.cell(r, 5).value, None)
        vrk = _safe_int(ws.cell(r, 6).value, None)
        matchup = str(ws.cell(r, 7).value or "").replace("\xa0", " ").strip()
        score = str(ws.cell(r, 8).value or "").strip()

        tot_pts = _safe_int(ws.cell(r, 10).value, 0)
        aces = _safe_int(ws.cell(r, 11).value, 0)
        df = _safe_int(ws.cell(r, 12).value, 0)
        srv_pts = _safe_int(ws.cell(r, 13).value, 0)
        p1_pts = _safe_int(ws.cell(r, 14).value, 0)
        p2_pts = _safe_int(ws.cell(r, 15).value, 0)
        opp_aces = _safe_int(ws.cell(r, 16).value, 0)

        t_val = ws.cell(r, 17).value
        dur_min, dur_str = _parse_time_min(t_val)
        games = _safe_int(ws.cell(r, 18).value, 0)
        sets = _safe_int(ws.cell(r, 19).value, 0)
        anno_raw = ws.cell(r, 20).value
        anno = _safe_int(anno_raw, dt.year) if anno_raw else dt.year

        # Determinazione Risultato e Avversario
        res = "N/D"
        opp = matchup
        if " d. " in matchup:
            w, l = matchup.split(" d. ", 1)
            if "cobolli" in w.lower():
                res = "Vittoria"
                opp = l.strip()
            else:
                res = "Sconfitta"
                opp = w.strip()
        elif "-" in matchup and not is_doubles:
            parts = matchup.split("-", 1)
            if len(parts) == 2:
                p1, p2 = parts[0].strip(), parts[1].strip()
                if "cobolli" in p1.lower():
                    opp = p2
                else:
                    opp = p1
        elif "/" in matchup and is_doubles:
            opp = matchup

        # Se il risultato non è ancora determinato, usiamo il punteggio
        if res == "N/D" and score:
            s_parts = score.split()
            v_won = 0
            v_lost = 0
            for sp in s_parts:
                m_set = re.match(r"(\d+)-(\d+)", sp)
                if m_set:
                    g1, g2 = int(m_set.group(1)), int(m_set.group(2))
                    if g1 > g2:
                        v_won += 1
                    elif g2 > g1:
                        v_lost += 1
            if v_won > v_lost:
                res = "Vittoria"
            elif v_lost > v_won:
                res = "Sconfitta"

        match_id = f"COB-{dt.strftime('%Y%m%d')}-R{r}"

        matches.append({
            "match_id": match_id,
            "date": dt.strftime("%d/%m/%Y"),
            "date_iso": dt.strftime("%Y-%m-%d"),
            "date_obj": dt.date(),
            "year": anno,
            "tournament": tourn,
            "surface": surf,
            "round": rd,
            "type": "Doppio" if is_doubles else "Singolare",
            "rank": rk,
            "opponent_rank": vrk,
            "matchup": matchup,
            "opponent": opp,
            "score": score,
            "result": res,
            "duration_min": dur_min,
            "duration_str": dur_str,
            "total_points": tot_pts,
            "aces": aces,
            "double_faults": df,
            "service_points": srv_pts,
            "first_serve_points": p1_pts,
            "second_serve_points": p2_pts,
            "opponent_aces": opp_aces,
            "games_played": games,
            "sets_played": sets
        })

    df_res = pd.DataFrame(matches)
    if not df_res.empty:
        try:
            # Salvataggio parquet e json per massima velocità
            df_res.to_parquet(CACHE_PARQUET, index=False)
            df_res.to_json(CACHE_JSON, orient="records", date_format="iso", indent=2)
        except Exception:
            pass

        # Genera calendario tornei
        _build_tournament_calendar(df_res)

    return df_res


def _build_tournament_calendar(df_matches):
    if df_matches.empty:
        return
    tourn_summary = df_matches.groupby(["year", "tournament"]).agg(
        start_date=("date_iso", "min"),
        end_date=("date_iso", "max"),
        matches=("date_iso", "count"),
        surfaces=("surface", lambda x: list(x.unique())[0] if len(x.unique()) > 0 else "Hard"),
        types=("type", lambda x: " + ".join(sorted(x.unique())))
    ).reset_index().sort_values("start_date")

    data = tourn_summary.to_dict(orient="records")
    try:
        with open(CALENDAR_JSON, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


@st.cache_data(ttl=3600)
def load_cobolli_matches():
    """
    Ritorna il DataFrame con tutti i match di Flavio Cobolli.
    """
    if os.path.exists(CACHE_PARQUET):
        try:
            df = pd.read_parquet(CACHE_PARQUET)
            df["date_obj"] = pd.to_datetime(df["date"], format="%d/%m/%Y", errors="coerce").dt.date
            return df
        except Exception:
            pass
    return parse_and_cache_cobolli_matches()


def load_match_gps_links():
    if os.path.exists(LINKS_JSON):
        try:
            with open(LINKS_JSON, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_match_gps_link(match_id, session_dict):
    links = load_match_gps_links()
    links[str(match_id)] = session_dict
    os.makedirs(DATA_DIR, exist_ok=True)
    try:
        with open(LINKS_JSON, "w", encoding="utf-8") as f:
            json.dump(links, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def remove_match_gps_link(match_id):
    links = load_match_gps_links()
    if str(match_id) in links:
        del links[str(match_id)]
        try:
            with open(LINKS_JSON, "w", encoding="utf-8") as f:
                json.dump(links, f, ensure_ascii=False, indent=2)
        except Exception:
            pass


def get_tournament_calendar():
    if os.path.exists(CALENDAR_JSON):
        try:
            with open(CALENDAR_JSON, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def get_tournament_for_week(monday_dt):
    """
    Ritorna il torneo giocato nella settimana che inizia col lunedì specificato.
    """
    cal = get_tournament_calendar()
    if not cal:
        return None
    sunday_dt = monday_dt + timedelta(days=6)
    m_str = monday_dt.strftime("%Y-%m-%d")
    s_str = sunday_dt.strftime("%Y-%m-%d")

    for t in cal:
        t_start = t.get("start_date", "")
        t_end = t.get("end_date", "")
        # Se c'è sovrapposizione tra la settimana e il range del torneo
        if (t_start <= s_str) and (t_end >= m_str):
            return t
    return None
