# Copyright 2026 Riccardo Di Maio - M0V3 S.r.l. Tutti i diritti riservati.
# Proprietary Sports Science & Clinical Performance Intelligence Architecture.
import datetime as dt
from datetime import timedelta
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from config import (
    tr,
    card_kpi,
    render_page_header,
    render_tab_navigation,
    render_action_bar,
    render_scientific_methodology_box,
    slugify_name,
    PLOTLY_CONFIG,
)
from utils import (
    supabase,
    load_athlete_database,
    load_local_database,
    get_tipologie_sessione,
    get_lista_atleti_disponibili,
    get_registro_medico,
    get_piani_microciclo,
    save_piano_microciclo,
    delete_piano_microciclo,
    render_athlete_hero_strip,
    set_notification,
)
from pdf_generator import crea_pdf_pianificazione_whatif


WEEKDAYS_IT = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
WEEKDAYS_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _extract_athlete_work_rates(df_ath, tipologie_list):
    """
    Estrae i ratei reali al minuto (escludendo rigorosamente i dati simulati Dato_Simulato == True)
    per l'atleta attivo e per ciascuna Tipologia di Sessione:
    - tl_per_min
    - tl_high_per_min
    - acc_per_min
    - dec_per_min
    - acc_dec_per_min
    - azioni_per_min
    - avg_match_tl (media storica Training Load di un Match ufficiale per calcolare i Match Equivalenti)
    - avg_daily_tl (media storica Training Load per sessione attiva, usata per il tetto clinico del 70%)
    """
    default_rate = {
        "tl_per_min": 4.2,
        "tl_high_per_min": 1.15,
        "acc_per_min": 0.42,
        "dec_per_min": 0.45,
        "acc_dec_per_min": 0.87,
        "azioni_per_min": 0.55,
        "n_sessions": 0,
        "source": "benchmark",
    }

    if df_ath is None or df_ath.empty:
        rates_map = {tp: dict(default_rate) for tp in tipologie_list}
        return rates_map, dict(default_rate), 420.0, 340.0

    df_real = df_ath.copy()
    if "Dato_Simulato" in df_real.columns:
        df_real = df_real[df_real["Dato_Simulato"] == False].copy()
    if df_real.empty:
        df_real = df_ath.copy()

    for c_num in ("Minuti", "Training Load", "TL_High", "High Accel IMU", "High Decel IMU", "Azioni Int. IMU >2"):
        if c_num not in df_real.columns:
            df_real[c_num] = 0.0
        df_real[c_num] = pd.to_numeric(df_real[c_num], errors="coerce").fillna(0.0)

    df_valid = df_real[(df_real["Minuti"] > 0) & (df_real["Training Load"] > 0)].copy()
    if df_valid.empty:
        rates_map = {tp: dict(default_rate) for tp in tipologie_list}
        return rates_map, dict(default_rate), 420.0, 340.0

    tot_min_g = float(df_valid["Minuti"].sum())
    global_rate = {
        "tl_per_min": round(float(df_valid["Training Load"].sum()) / tot_min_g, 3),
        "tl_high_per_min": round(float(df_valid["TL_High"].sum()) / tot_min_g, 3),
        "acc_per_min": round(float(df_valid["High Accel IMU"].sum()) / tot_min_g, 3),
        "dec_per_min": round(float(df_valid["High Decel IMU"].sum()) / tot_min_g, 3),
        "acc_dec_per_min": round(float((df_valid["High Accel IMU"] + df_valid["High Decel IMU"]).sum()) / tot_min_g, 3),
        "azioni_per_min": round(float(df_valid["Azioni Int. IMU >2"].sum()) / tot_min_g, 3),
        "n_sessions": int(len(df_valid)),
        "source": "global_athlete",
    }

    avg_daily_tl = float(df_valid["Training Load"].mean()) if not df_valid.empty else 340.0
    mask_match = df_valid["Tipologia Sessione"].astype(str).str.lower().str.contains("match|torneo") if "Tipologia Sessione" in df_valid.columns else pd.Series(False, index=df_valid.index)
    df_matches = df_valid[mask_match]
    avg_match_tl = float(df_matches["Training Load"].mean()) if not df_matches.empty else max(avg_daily_tl * 1.25, 380.0)

    rates_map = {}
    for tp in tipologie_list:
        if "Tipologia Sessione" in df_valid.columns:
            sub = df_valid[df_valid["Tipologia Sessione"].astype(str).str.strip().str.lower() == str(tp).strip().lower()]
        else:
            sub = pd.DataFrame()
        if not sub.empty and float(sub["Minuti"].sum()) > 0:
            m_s = float(sub["Minuti"].sum())
            rates_map[tp] = {
                "tl_per_min": round(float(sub["Training Load"].sum()) / m_s, 3),
                "tl_high_per_min": round(float(sub["TL_High"].sum()) / m_s, 3),
                "acc_per_min": round(float(sub["High Accel IMU"].sum()) / m_s, 3),
                "dec_per_min": round(float(sub["High Decel IMU"].sum()) / m_s, 3),
                "acc_dec_per_min": round(float((sub["High Accel IMU"] + sub["High Decel IMU"]).sum()) / m_s, 3),
                "azioni_per_min": round(float(sub["Azioni Int. IMU >2"].sum()) / m_s, 3),
                "n_sessions": int(len(sub)),
                "source": "type_specific",
            }
        else:
            # Modulazione fisiologica di default se la tipologia non ha ancora storico specifico
            mult = 1.0
            tp_low = str(tp).lower()
            if "match" in tp_low or "torneo" in tp_low:
                mult = 1.15
            elif "recupero" in tp_low or "servizio" in tp_low:
                mult = 0.65
            elif "1000" in tp_low or "fisica" in tp_low:
                mult = 1.10
            rates_map[tp] = {
                "tl_per_min": round(global_rate["tl_per_min"] * mult, 3),
                "tl_high_per_min": round(global_rate["tl_high_per_min"] * mult, 3),
                "acc_per_min": round(global_rate["acc_per_min"] * mult, 3),
                "dec_per_min": round(global_rate["dec_per_min"] * mult, 3),
                "acc_dec_per_min": round(global_rate["acc_dec_per_min"] * mult, 3),
                "azioni_per_min": round(global_rate["azioni_per_min"] * mult, 3),
                "n_sessions": 0,
                "source": "fallback_global",
            }

    return rates_map, global_rate, round(avg_match_tl, 1), round(avg_daily_tl, 1)


def _check_athlete_adapted_load_status(atleta_sel):
    """
    Verifica se l'atleta si trova attualmente in status clinico 'CARICO ADATTATO' (status_operativo == 'LIMITATO')
    nel registro medico/fisioterapico.
    """
    today_str = dt.date.today().strftime("%Y-%m-%d")
    try:
        recs = get_registro_medico(nome_giocatore=atleta_sel)
        for r in (recs or []):
            d_in = str(r.get("data_inizio", ""))[:10]
            d_fn = str(r.get("data_fine", ""))[:10]
            st_op = str(r.get("status_operativo", "")).upper()
            if d_in <= today_str <= d_fn and st_op == "LIMITATO":
                return True, r
    except Exception:
        pass
    return False, None


def _compute_virtual_ewma_projection(df_ath_hist, df_plan_sim, start_date_plan, avg_daily_tl, avg_match_tl, clinical_cap_active=False):
    """
    Concatena in memoria gli ultimi 35 giorni storici dell'atleta con i 7-14 giorni pianificati futuri
    e calcola:
    - Uncoupled EWMA ACWR (lambda_a = 0.25, lambda_c = 2/29) su Training Load, TL_High e Carico Meccanico (Acc+Dec)
    - Monotonia di Foster (Media 7d / SD 7d) e Training Strain (Carico 7d * Monotonia)
    - Alert Clinico Automatico 70% Carico Adattato
    """
    hist_start = pd.to_datetime(start_date_plan) - pd.Timedelta(days=35)
    hist_end = pd.to_datetime(start_date_plan) - pd.Timedelta(days=1)

    df_h = pd.DataFrame()
    if df_ath_hist is not None and not df_ath_hist.empty:
        df_h = df_ath_hist.copy()
        if "Date_obj" not in df_h.columns:
            df_h["Date_obj"] = pd.to_datetime(df_h["Date"], format="%d/%m/%Y", errors="coerce")
        df_h = df_h.dropna(subset=["Date_obj"])
        df_h = df_h[df_h["Date_obj"] <= hist_end].copy()

    # Aggregazione giornaliera storica dall'inizio della stagione/storico dell'atleta per avere un chronic28 già stabilizzato
    if not df_h.empty:
        for c in ("Training Load", "TL_High", "High Accel IMU", "High Decel IMU", "Minuti"):
            if c not in df_h.columns:
                df_h[c] = 0.0
            df_h[c] = pd.to_numeric(df_h[c], errors="coerce").fillna(0.0)
        df_h["Mech_Load"] = df_h["High Accel IMU"] + df_h["High Decel IMU"]
        daily_hist = df_h.groupby("Date_obj")[["Training Load", "TL_High", "Mech_Load", "Minuti"]].sum()
        min_ever_dt = min(daily_hist.index.min(), hist_start)
    else:
        daily_hist = pd.DataFrame(columns=["Training Load", "TL_High", "Mech_Load", "Minuti"])
        min_ever_dt = hist_start

    plan_max_dt = pd.to_datetime(df_plan_sim["date_obj"]).max()
    full_range = pd.date_range(min_ever_dt, plan_max_dt, freq="D")

    timeline_rows = []
    plan_by_dt = {pd.to_datetime(r["date_obj"]): r for _, r in df_plan_sim.iterrows()}

    for d_cur in full_range:
        is_f = d_cur >= pd.to_datetime(start_date_plan)
        if is_f and d_cur in plan_by_dt:
            pr = plan_by_dt[d_cur]
            tl_v = float(pr["tl_sim"])
            tlh_v = float(pr["tl_high_sim"])
            mech_v = float(pr["acc_dec_sim"])
            min_v = float(pr["durata_min"])
            tipo_v = str(pr["tipologia"])
            srpe_extra_v = float(pr.get("srpe_extra_au", 0.0))
        elif not daily_hist.empty and d_cur in daily_hist.index:
            hr = daily_hist.loc[d_cur]
            tl_v = float(hr["Training Load"])
            tlh_v = float(hr["TL_High"])
            mech_v = float(hr["Mech_Load"])
            min_v = float(hr["Minuti"])
            tipo_v = "Storico"
            srpe_extra_v = 0.0
        else:
            tl_v = 0.0
            tlh_v = 0.0
            mech_v = 0.0
            min_v = 0.0
            tipo_v = "REST / Riposo"
            srpe_extra_v = 0.0

        timeline_rows.append({
            "date_obj": d_cur,
            "date_str": d_cur.strftime("%d/%m/%Y"),
            "date_iso": d_cur.strftime("%Y-%m-%d"),
            "is_forecast": is_f,
            "tipologia": tipo_v,
            "minuti": round(min_v, 1),
            "tl": round(tl_v, 1),
            "tl_high": round(tlh_v, 1),
            "mech_load": round(mech_v, 1),
            "srpe_extra_au": round(srpe_extra_v, 1),
        })

    df_tl = pd.DataFrame(timeline_rows)

    # Calcolo Uncoupled EWMA su TL, TL_High, Mech_Load
    lambda_a = 2.0 / (7.0 + 1.0)
    lambda_c = 2.0 / (28.0 + 1.0)

    for metric_col, acwr_col, ac_col, ch_col in (
        ("tl", "acwr_tl", "ewma_acute_tl", "ewma_chronic_tl"),
        ("tl_high", "acwr_tl_high", "ewma_acute_tlh", "ewma_chronic_tlh"),
        ("mech_load", "acwr_mech", "ewma_acute_mech", "ewma_chronic_mech"),
    ):
        vals = df_tl[metric_col].values
        n = len(vals)
        ac = np.zeros(n)
        ch = np.zeros(n)
        acwr = np.full(n, 100.0)
        for i in range(n):
            v = float(vals[i])
            if i == 0:
                ac[i] = v if v > 0 else (avg_daily_tl * 0.5 if metric_col == "tl" else 10.0)
                ch[i] = ac[i]
                acwr[i] = 100.0
            else:
                ac[i] = v * lambda_a + ac[i - 1] * (1.0 - lambda_a)
                ch[i] = v * lambda_c + ch[i - 1] * (1.0 - lambda_c)
                prev_ch = ch[i - 1]
                if prev_ch > 0:
                    acwr[i] = round((ac[i] / prev_ch) * 100.0, 1)
                else:
                    acwr[i] = 100.0
        df_tl[ac_col] = np.round(ac, 1)
        df_tl[ch_col] = np.round(ch, 1)
        df_tl[acwr_col] = np.round(acwr, 1)

    # Soglia clinica 70% Carico Adattato
    soglia_70 = round(avg_daily_tl * 0.70, 1)
    df_tl["soglia_70_cap"] = soglia_70
    df_tl["violazione_70_cap"] = (df_tl["is_forecast"]) & (clinical_cap_active) & (df_tl["tl"] > soglia_70)
    df_tl["violazione_acwr_150"] = (df_tl["is_forecast"]) & (df_tl["acwr_tl"] > 150.0)

    # Filtra ultimi 21 giorni storici + giorni futuri per i grafici
    plot_start = pd.to_datetime(start_date_plan) - pd.Timedelta(days=21)
    df_plot = df_tl[df_tl["date_obj"] >= plot_start].copy().reset_index(drop=True)
    df_forecast = df_tl[df_tl["is_forecast"] == True].copy().reset_index(drop=True)

    # KPI Predittivi sul periodo futuro pianificato
    peak_acwr_tl = float(df_forecast["acwr_tl"].max()) if not df_forecast.empty else 100.0
    peak_acwr_mech = float(df_forecast["acwr_mech"].max()) if not df_forecast.empty else 100.0
    tot_planned_tl = float(df_forecast["tl"].sum()) if not df_forecast.empty else 0.0
    tot_planned_tlh = float(df_forecast["tl_high"].sum()) if not df_forecast.empty else 0.0
    tot_planned_min = float(df_forecast["minuti"].sum()) if not df_forecast.empty else 0.0

    # Monotonia e Strain di Foster sui primi 7 giorni pianificati (o sull'intero blocco se 7d)
    first_7_loads = df_forecast["tl"].iloc[:7].values if len(df_forecast) >= 7 else df_forecast["tl"].values
    mean_7 = float(np.mean(first_7_loads)) if len(first_7_loads) > 0 else 0.0
    sd_7 = float(np.std(first_7_loads, ddof=0)) if len(first_7_loads) > 1 else 0.0
    monotony_foster = round(mean_7 / sd_7, 2) if sd_7 > 0 else (2.5 if mean_7 > 0 else 0.0)
    strain_foster = round(float(np.sum(first_7_loads)) * monotony_foster, 0)

    # Match Equivalenti (su base settimanale 7gg)
    weekly_tl_equiv = float(np.sum(first_7_loads))
    match_equivalenti = round(weekly_tl_equiv / avg_match_tl, 2) if avg_match_tl > 0 else 0.0

    giorni_fuori_soglia = int(
        ((df_forecast["acwr_tl"] > 150.0) | (df_forecast["violazione_70_cap"] == True)).sum()
    )

    kpis = {
        "peak_acwr_tl": round(peak_acwr_tl, 1),
        "peak_acwr_mech": round(peak_acwr_mech, 1),
        "monotony_foster": monotony_foster,
        "strain_foster": int(strain_foster),
        "tot_planned_tl": round(tot_planned_tl, 0),
        "tot_planned_tlh": round(tot_planned_tlh, 0),
        "tot_planned_min": round(tot_planned_min, 0),
        "weekly_tl_equiv": round(weekly_tl_equiv, 0),
        "match_equivalenti": match_equivalenti,
        "avg_match_tl": avg_match_tl,
        "avg_daily_tl": avg_daily_tl,
        "soglia_70": soglia_70,
        "clinical_cap_active": clinical_cap_active,
        "giorni_fuori_soglia": giorni_fuori_soglia,
        "n_days_viol_acwr": int(df_forecast["violazione_acwr_150"].sum()),
        "n_days_viol_70": int(df_forecast["violazione_70_cap"].sum()),
    }
    return df_plot, df_forecast, kpis


def _build_real_vs_forecast_figure(df_plot, atleta_sel, clinical_cap_active=False, soglia_70=0.0):
    """
    Costruisce il grafico interattivo Plotly a doppio pannello 'Real vs Forecast':
    - Pannello Superiore: Linea continua storica (ultimi 21 gg) che transita in linea tratteggiata ciano/ambra
      per i 7-14 gg futuri, con bande fisiologiche ACWR (80-130% Sweet Spot verde, >150% Danger Zone rossa).
    - Pannello Inferiore: Barre giornaliere di Training Load e TL High con distinzione visiva tra carichi
      storici consolidati e carichi pianificati simulati (+ linea rossa Tetto 70% se attivo).
    """
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.10,
        row_heights=[0.52, 0.48],
        subplot_titles=(
            tr("Proiezione ACWR Uncoupled EWMA: Storico Reale (Continuo) vs Forecast Pianificato (Tratteggiato)",
               "Uncoupled EWMA ACWR Projection: Historical Real (Solid) vs Planned Forecast (Dashed)"),
            tr("Volumi Giornalieri: Training Load & TL High (Storico Consolidato vs Simulazione Microciclo)",
               "Daily Volumes: Training Load & TL High (Consolidated History vs Microcycle Simulation)")
        )
    )

    df_hist = df_plot[df_plot["is_forecast"] == False]
    df_fore = df_plot[df_plot["is_forecast"] == True]

    # Per congiungere visivamente la linea storica e la linea forecast senza buchi, includiamo l'ultimo punto storico all'inizio del forecast
    if not df_hist.empty and not df_fore.empty:
        df_fore_line = pd.concat([df_hist.iloc[[-1]], df_fore], ignore_index=True)
    else:
        df_fore_line = df_fore

    # Bande fisiologiche ACWR sul pannello 1
    fig.add_hrect(
        y0=80, y1=130,
        fillcolor="rgba(16, 185, 129, 0.12)",
        line_width=0,
        row=1, col=1,
        annotation_text=tr("Sweet Spot (80-130%)", "Sweet Spot (80-130%)"),
        annotation_position="top left",
        annotation_font=dict(size=10, color="#34d399")
    )
    fig.add_hrect(
        y0=150, y1=220,
        fillcolor="rgba(239, 68, 68, 0.10)",
        line_width=0,
        row=1, col=1,
        annotation_text=tr("Danger Zone (>150%)", "Danger Zone (>150%)"),
        annotation_position="top left",
        annotation_font=dict(size=10, color="#f87171")
    )
    fig.add_hline(y=150, line_dash="dot", line_color="#ef4444", line_width=1.5, row=1, col=1)
    fig.add_hline(y=100, line_dash="solid", line_color="rgba(16, 185, 129, 0.45)", line_width=1.2, row=1, col=1)

    # Traccia ACWR Storica (continua)
    if not df_hist.empty:
        fig.add_trace(
            go.Scatter(
                x=df_hist["date_str"],
                y=df_hist["acwr_tl"],
                mode="lines+markers",
                name=tr("ACWR TL Storico", "Historical TL ACWR"),
                line=dict(color="#0ea5e9", width=3),
                marker=dict(size=6, color="#0ea5e9"),
            ),
            row=1, col=1
        )

    # Traccia ACWR Forecast (tratteggiata)
    if not df_fore_line.empty:
        fig.add_trace(
            go.Scatter(
                x=df_fore_line["date_str"],
                y=df_fore_line["acwr_tl"],
                mode="lines+markers",
                name=tr("ACWR TL Previsto (Forecast)", "Forecast TL ACWR"),
                line=dict(color="#38bdf8", width=3.5, dash="dash"),
                marker=dict(size=8, color="#38bdf8", symbol="diamond", line=dict(width=1.5, color="#ffffff")),
            ),
            row=1, col=1
        )
        fig.add_trace(
            go.Scatter(
                x=df_fore_line["date_str"],
                y=df_fore_line["acwr_mech"],
                mode="lines+markers",
                name=tr("ACWR Meccanico Acc+Dec (Forecast)", "Forecast Mechanical Acc+Dec ACWR"),
                line=dict(color="#f59e0b", width=2.2, dash="dot"),
                marker=dict(size=6, color="#fbbf24"),
            ),
            row=1, col=1
        )

    # Pannello 2: Barre Training Load e TL High (Storico vs Pianificato)
    if not df_hist.empty:
        fig.add_trace(
            go.Bar(
                x=df_hist["date_str"],
                y=df_hist["tl"],
                name=tr("Training Load (Storico Reale)", "Training Load (Historical)"),
                marker_color="#0284c7",
            ),
            row=2, col=1
        )
        fig.add_trace(
            go.Bar(
                x=df_hist["date_str"],
                y=df_hist["tl_high"],
                name=tr("TL High (Storico Reale)", "TL High (Historical)"),
                marker_color="#10b981",
            ),
            row=2, col=1
        )

    if not df_fore.empty:
        bar_colors_fore = [
            "#ef4444" if (bool(r.get("violazione_70_cap")) or bool(r.get("violazione_acwr_150"))) else "rgba(56, 189, 248, 0.55)"
            for _, r in df_fore.iterrows()
        ]
        fig.add_trace(
            go.Bar(
                x=df_fore["date_str"],
                y=df_fore["tl"],
                name=tr("Training Load (Pianificato What-If)", "Training Load (Planned What-If)"),
                marker_color=bar_colors_fore,
                marker_line=dict(color="#38bdf8", width=2),
            ),
            row=2, col=1
        )
        fig.add_trace(
            go.Bar(
                x=df_fore["date_str"],
                y=df_fore["tl_high"],
                name=tr("TL High (Pianificato What-If)", "TL High (Planned What-If)"),
                marker_color="rgba(245, 158, 11, 0.65)",
                marker_line=dict(color="#fbbf24", width=1.5),
            ),
            row=2, col=1
        )

    if clinical_cap_active and soglia_70 > 0:
        fig.add_hline(
            y=soglia_70,
            line_dash="dash",
            line_color="#ef4444",
            line_width=2,
            row=2, col=1,
            annotation_text=tr(f"Tetto Clinico 70% ({soglia_70:.0f} TL)", f"70% Clinical Cap ({soglia_70:.0f} TL)"),
            annotation_position="top right",
            annotation_font=dict(size=10.5, color="#f87171")
        )

    max_acwr_y = max(175.0, float(df_plot["acwr_tl"].max()) + 20.0) if not df_plot.empty else 175.0
    fig.update_layout(
        height=580,
        barmode="group",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#cbd5e1", family="Inter"),
        legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="right", x=1, font=dict(size=11, color="#cbd5e1")),
        margin=dict(l=20, r=20, t=55, b=35),
    )
    fig.update_xaxes(type="category", tickangle=-45, tickfont=dict(color="#94a3b8", size=10.5), gridcolor="rgba(56,189,248,0.08)")
    fig.update_yaxes(title_text="ACWR [%]", range=[40, max_acwr_y], gridcolor="rgba(56,189,248,0.12)", tickfont=dict(color="#38bdf8"), row=1, col=1)
    fig.update_yaxes(title_text="Training Load [AU]", gridcolor="rgba(56,189,248,0.12)", tickfont=dict(color="#cbd5e1"), row=2, col=1)
    return fig


def render_pianificazione_whatif(t=None):
    """
    MODULO 1 V3.0: Simulatore 'What-If' & Pianificazione del Microciclo (Predictive Load Planning).
    Include:
    - Tab 1: Simulatore Microciclo 7/14gg & Proiezione ACWR / Soglia 70%
    - Tab 2: Confronto Piano vs Eseguito (aderenza giornaliera e cumulativa tra piano salvato e GPS reale)
    """
    user = st.session_state.get("user")
    role = st.session_state.get("role", "Staff")

    if role == "Atleta":
        st.warning(tr("Questa sezione di pianificazione predittiva è riservata allo Staff Tecnico, Atletico e Medico.",
                      "This predictive load planning section is restricted to Coaching, Athletic, and Medical Staff."))
        return

    render_page_header(
        tr("Pianificazione & Simulatore What-If", "Load Planning & What-If Simulator"),
        tr("Simulazione predittiva in memoria del microciclo futuro (7 o 14 giorni) con proiezione ACWR Uncoupled EWMA, Monotonia di Foster e controllo automatico del Tetto Clinico 70%.",
           "In-memory predictive simulation of the upcoming microcycle (7 or 14 days) with Uncoupled EWMA ACWR projection, Foster's Monotony, and automated 70% Clinical Cap verification."),
        "PREDICTIVE WORKLOAD ENGINE · WHAT-IF SIMULATOR"
    )

    # 1. Selezione Atleta Attivo
    lista_atleti = get_lista_atleti_disponibili(user, role)
    if not lista_atleti:
        lista_atleti = ["Flavio Cobolli"]
    glob_ath = st.session_state.get("selected_athlete")
    if glob_ath in lista_atleti:
        atleta_sel = glob_ath
    else:
        atleta_sel = lista_atleti[0]
        st.session_state["selected_athlete"] = atleta_sel

    # Caricamento ultra-rapido (<2ms) della partizione Parquet dell'atleta attivo
    df_ath = load_athlete_database(atleta_sel)
    is_adapted_db, med_rec = _check_athlete_adapted_load_status(atleta_sel)

    badge_clinico = (
        tr("STATUS CLINICO: CARICO ADATTATO (TETTO 70%)", "CLINICAL STATUS: ADAPTED LOAD (70% CAP)")
        if is_adapted_db
        else tr("STATUS CLINICO: DISPONIBILE (100%)", "CLINICAL STATUS: AVAILABLE (100%)")
    )
    render_athlete_hero_strip(atleta_sel, df_atleta=df_ath, extra_badges=[badge_clinico])

    # Verifica permessi granulari sottomoduli RBAC
    user_perms = st.session_state.get("user_permessi_moduli")
    can_sim = True
    can_proj = True
    can_comp = True
    if role != "Super-Admin" and user_perms is not None:
        wf_perms = {r for (ar, r) in user_perms if ar == "Pianificazione & Simulatore What-If"}
        if wf_perms:
            can_sim = "Simulatore Microciclo 7/14gg" in wf_perms
            can_proj = "Proiezione ACWR & Soglia 70%" in wf_perms or can_sim
            can_comp = "Confronto Piano vs Eseguito" in wf_perms

    lbl_tab_sim = tr("Simulatore Microciclo 7/14gg & Proiezione ACWR", "7/14d Microcycle Simulator & ACWR Projection")
    lbl_tab_comp = tr("Confronto Piano vs Eseguito", "Plan vs Executed Comparison")
    tabs_wf = []
    if can_sim or can_proj:
        tabs_wf.append(lbl_tab_sim)
    if can_comp:
        tabs_wf.append(lbl_tab_comp)
    if not tabs_wf:
        tabs_wf = [lbl_tab_sim, lbl_tab_comp]

    active_wf_tab = render_tab_navigation(tabs_wf, key="nav_whatif_simulator")

    u_email = getattr(user, "email", "") or (user.get("email", "") if isinstance(user, dict) else "")
    tipologie_atleta = get_tipologie_sessione(uploader_email=None if role == "Super-Admin" else u_email, atleta_nome=atleta_sel)
    rates_map, global_rate, avg_match_tl, avg_daily_tl = _extract_athlete_work_rates(df_ath, tipologie_atleta)

    # =========================================================================
    # TAB 1: SIMULATORE MICROCICLO 7/14GG & PROIEZIONE ACWR
    # =========================================================================
    if active_wf_tab == lbl_tab_sim:
        with st.container(border=True):
            c_cfg1, c_cfg2, c_cfg3, c_cfg4 = st.columns([1.1, 1.1, 1.3, 1.3])
            with c_cfg1:
                orizzonte_sel = st.radio(
                    tr("Orizzonte Previsionale", "Forecast Horizon"),
                    [7, 14],
                    format_func=lambda x: tr(f"{x} Giorni", f"{x} Days"),
                    horizontal=True,
                    key="wf_horizon_days"
                )
            with c_cfg2:
                domani = dt.date.today() + timedelta(days=1)
                start_date_plan = st.date_input(
                    tr("Data Inizio Microciclo (T+1)", "Microcycle Start Date (T+1)"),
                    value=domani,
                    key="wf_start_date"
                )
            with c_cfg3:
                preset_opz = [
                    tr("Microciclo Standard Bilanciato", "Balanced Standard Microcycle"),
                    tr("Blocco Carico Agonistico Intenso", "High Intensity Competitive Block"),
                    tr("Settimana Torneo (Match + Recupero)", "Tournament Week (Match + Recovery)"),
                    tr("Scarico / Tapering & Return-to-Play (≤70%)", "Tapering & Return-to-Play (≤70%)"),
                ]
                preset_sel = st.selectbox(
                    tr("Template Rapido Microciclo", "Quick Microcycle Template"),
                    preset_opz,
                    key="wf_preset_template"
                )
            with c_cfg4:
                st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)
                sim_clinical_cap = st.checkbox(
                    tr("Attiva Vincolo Clinico Carico Adattato (Tetto 70%)", "Enforce Adapted Load Clinical Cap (70% Limit)"),
                    value=bool(is_adapted_db or (preset_sel == preset_opz[3])),
                    key="wf_clinical_cap_toggle"
                )

        if is_adapted_db and med_rec:
            dist_med = med_rec.get("distretto_anatomico", "N/D")
            note_med = med_rec.get("diagnosi_note", "")
            cap_val_str = f"{avg_daily_tl * 0.70:.0f}"
            msg_med = tr(
                f"{atleta_sel} è in stato di CARICO ADATTATO ({dist_med} - {note_med}). Il tetto giornaliero prudenziale è fissato al 70% della media storica ({cap_val_str} TL).",
                f"{atleta_sel} is in ADAPTED LOAD status ({dist_med}). The daily safety cap is set at 70% of historical average ({cap_val_str} TL)."
            )
            st.markdown(
                f"<div style='background:rgba(239,68,68,0.14); border:1px solid #ef4444; border-left:5px solid #ef4444; border-radius:10px; padding:10px 14px; margin-bottom:12px; font-size:12.5px; color:#f8fafc;'>"
                f"<i class='bi bi-exclamation-triangle-fill' style='color:#ef4444; margin-right:6px;'></i>"
                f"<b>{tr('VINCOLO CLINICO ATTIVO DA AREA MEDICA:', 'ACTIVE MEDICAL RESTRICTION:')}</b> {msg_med}"
                f"</div>",
                unsafe_allow_html=True
            )

        # Expander ispezionabile con i Ratei Reali al Minuto estratti per l'atleta
        with st.expander(tr(f" Coefficienti Reali al Minuto Estratti per {atleta_sel} (Esclusi Dati Simulati)", f"Extracted Real Per-Minute Work Rates for {atleta_sel} (Excluding Simulated Data)"), expanded=False):
            rows_rates = []
            for tp, r_info in rates_map.items():
                src_lbl = (
                    tr(f"Storico Specifico ({r_info['n_sessions']} sess.)", f"Type History ({r_info['n_sessions']} sess.)")
                    if r_info["source"] == "type_specific"
                    else tr("Media Globale Atleta (Fallback)", "Athlete Global Mean (Fallback)")
                )
                rows_rates.append({
                    tr("Tipologia Sessione", "Session Type"): tp,
                    "TL / min": f"{r_info['tl_per_min']:.2f}",
                    "TL High / min": f"{r_info['tl_high_per_min']:.2f}",
                    "High Acc + Dec / min": f"{r_info['acc_dec_per_min']:.2f}",
                    'Azioni >2" / min': f"{r_info['azioni_per_min']:.2f}",
                    tr("Stima 90 min (100%)", "90 min Est. (100%)"): f"{r_info['tl_per_min'] * 90.0:.0f} TL",
                    tr("Fonte Calibrazione", "Calibration Source"): src_lbl,
                })
            st.dataframe(pd.DataFrame(rows_rates), use_container_width=True, hide_index=True)

        # Costruzione tabella iniziale del Microciclo Futuro per st.data_editor
        opzioni_tipo_editor = ["REST / Riposo"] + tipologie_atleta
        opzioni_extra_editor = ["Nessuna", "Gym", "Preparazione Fisica", "Recupero Attivo"]
        default_court_type = tipologie_atleta[0] if tipologie_atleta else "Tecnica"
        match_type = next((tp for tp in tipologie_atleta if "match" in tp.lower() or "torneo" in tp.lower()), default_court_type)
        rec_type = next((tp for tp in tipologie_atleta if "recupero" in tp.lower() or "servizio" in tp.lower()), default_court_type)

        state_sched_key = f"wf_sched_df_{slugify_name(atleta_sel)}_{orizzonte_sel}_{start_date_plan.strftime('%Y%m%d')}_{preset_opz.index(preset_sel)}"
        is_en = st.session_state.get("lang", "IT") == "EN"
        w_names = WEEKDAYS_EN if is_en else WEEKDAYS_IT

        if state_sched_key not in st.session_state:
            init_rows = []
            for d_i in range(int(orizzonte_sel)):
                cur_d = start_date_plan + timedelta(days=d_i)
                wd = cur_d.weekday()  # 0=Mon .. 6=Sun
                if preset_sel == preset_opz[1]:  # Blocco Intenso
                    if wd == 6:
                        tp_d, dur_d, mult_d, ex_t, ex_m, ex_r = "REST / Riposo", 0, 100, "Nessuna", 0, 0
                    elif wd in (1, 3, 5):
                        tp_d, dur_d, mult_d, ex_t, ex_m, ex_r = match_type, 110, 110, "Gym", 45, 7
                    else:
                        tp_d, dur_d, mult_d, ex_t, ex_m, ex_r = default_court_type, 95, 105, "Preparazione Fisica", 40, 6
                elif preset_sel == preset_opz[2]:  # Settimana Torneo
                    if wd in (0, 2, 4, 5):
                        tp_d, dur_d, mult_d, ex_t, ex_m, ex_r = match_type, 115, 105, "Recupero Attivo", 30, 3
                    elif wd == 6:
                        tp_d, dur_d, mult_d, ex_t, ex_m, ex_r = "REST / Riposo", 0, 100, "Nessuna", 0, 0
                    else:
                        tp_d, dur_d, mult_d, ex_t, ex_m, ex_r = rec_type, 60, 85, "Recupero Attivo", 25, 3
                elif preset_sel == preset_opz[3]:  # Scarico / Return-to-Play <=70%
                    if wd in (2, 6):
                        tp_d, dur_d, mult_d, ex_t, ex_m, ex_r = "REST / Riposo", 0, 100, "Nessuna", 0, 0
                    else:
                        tp_d, dur_d, mult_d, ex_t, ex_m, ex_r = default_court_type, 55, 80, "Gym", 35, 4
                else:  # Microciclo Standard Bilanciato
                    if wd == 6:
                        tp_d, dur_d, mult_d, ex_t, ex_m, ex_r = "REST / Riposo", 0, 100, "Nessuna", 0, 0
                    elif wd == 5:
                        tp_d, dur_d, mult_d, ex_t, ex_m, ex_r = match_type, 105, 100, "Nessuna", 0, 0
                    elif wd == 2:
                        tp_d, dur_d, mult_d, ex_t, ex_m, ex_r = rec_type, 65, 85, "Gym", 45, 6
                    else:
                        tp_d, dur_d, mult_d, ex_t, ex_m, ex_r = default_court_type, 90, 100, "Preparazione Fisica" if wd in (0, 3) else "Nessuna", 40 if wd in (0, 3) else 0, 6 if wd in (0, 3) else 0

                init_rows.append({
                    "Giorno": f"T+{d_i + 1} · {w_names[wd][:3]} {cur_d.strftime('%d/%m/%Y')}",
                    "Tipologia Sessione": tp_d if tp_d in opzioni_tipo_editor else default_court_type,
                    "Durata Pianificata (min)": int(dur_d),
                    "Moltiplicatore Intensità (%)": int(mult_d),
                    "Extra-Campo (Gym/Prep)": ex_t,
                    "Durata Extra (min)": int(ex_m),
                    "RPE Extra (0-10)": int(ex_r),
                })
            st.session_state[state_sched_key] = pd.DataFrame(init_rows)

        st.markdown(f"### <i class='bi bi-calendar2-week' style='color:#38bdf8;'></i> {tr('Editor Interattivo del Microciclo Futuro', 'Interactive Future Microcycle Editor')}", unsafe_allow_html=True)
        st.caption(tr("Modifica tipologia di seduta, durata in minuti e moltiplicatore d'intensità (50%–130%). I volumi previsti e la curva ACWR si aggiornano istantaneamente in memoria.",
                      "Edit session type, duration in minutes, and intensity multiplier (50%–130%). Predicted volumes and the ACWR curve update instantaneously in memory."))

        edited_df = st.data_editor(
            st.session_state[state_sched_key],
            use_container_width=True,
            hide_index=True,
            num_rows="fixed",
            key=f"editor_{state_sched_key}",
            column_config={
                "Giorno": st.column_config.TextColumn(tr("Giorno & Data", "Day & Date"), disabled=True),
                "Tipologia Sessione": st.column_config.SelectboxColumn(
                    tr("Tipologia Sessione Campo", "Court Session Type"),
                    options=opzioni_tipo_editor,
                    required=True,
                ),
                "Durata Pianificata (min)": st.column_config.NumberColumn(
                    tr("Durata Campo (min)", "Court Duration (min)"),
                    min_value=0, max_value=300, step=5, required=True,
                ),
                "Moltiplicatore Intensità (%)": st.column_config.NumberColumn(
                    tr("Intensità (%)", "Intensity (%)"),
                    min_value=50, max_value=130, step=5, required=True,
                    help=tr("100% = intensità media storica per quella tipologia; >100% = seduta più densa; <100% = seduta blanda/scarico",
                            "100% = historical average intensity for that type; >100% = denser session; <100% = lighter/tapering session")
                ),
                "Extra-Campo (Gym/Prep)": st.column_config.SelectboxColumn(
                    tr("Seduta Extra-Campo", "Off-Court Session"),
                    options=opzioni_extra_editor,
                    required=True,
                ),
                "Durata Extra (min)": st.column_config.NumberColumn(
                    tr("Durata Extra (min)", "Off-Court Min"),
                    min_value=0, max_value=180, step=5, required=True,
                ),
                "RPE Extra (0-10)": st.column_config.NumberColumn(
                    tr("RPE Extra (0-10)", "Off-Court RPE"),
                    min_value=0, max_value=10, step=1, required=True,
                ),
            }
        )

        # Calcolo vettoriale in memoria dei carichi simulati giorno per giorno
        sim_rows = []
        for d_i, (_, r_ed) in enumerate(edited_df.iterrows()):
            cur_d = start_date_plan + timedelta(days=d_i)
            tp_sel = str(r_ed.get("Tipologia Sessione", "REST / Riposo"))
            dur_m = float(r_ed.get("Durata Pianificata (min)", 0) or 0)
            mult_p = float(r_ed.get("Moltiplicatore Intensità (%)", 100) or 100)
            ex_tp = str(r_ed.get("Extra-Campo (Gym/Prep)", "Nessuna"))
            ex_dur = float(r_ed.get("Durata Extra (min)", 0) or 0)
            ex_rpe = float(r_ed.get("RPE Extra (0-10)", 0) or 0)

            if tp_sel == "REST / Riposo" or dur_m <= 0:
                tl_s, tlh_s, acc_s, dec_s, acc_dec_s, az_s = 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
                dur_m = 0.0
            else:
                r_info = rates_map.get(tp_sel, global_rate)
                factor = mult_p / 100.0
                tl_s = round(r_info["tl_per_min"] * dur_m * factor, 1)
                tlh_s = round(r_info["tl_high_per_min"] * dur_m * factor, 1)
                acc_s = round(r_info["acc_per_min"] * dur_m * factor, 1)
                dec_s = round(r_info["dec_per_min"] * dur_m * factor, 1)
                acc_dec_s = round(r_info["acc_dec_per_min"] * dur_m * factor, 1)
                az_s = round(r_info["azioni_per_min"] * dur_m * factor, 1)

            srpe_ex_au = round(ex_dur * ex_rpe, 1) if (ex_tp != "Nessuna" and ex_dur > 0 and ex_rpe > 0) else 0.0
            sim_rows.append({
                "day_idx": d_i + 1,
                "date_obj": cur_d,
                "date_str": cur_d.strftime("%d/%m/%Y"),
                "date_iso": cur_d.strftime("%Y-%m-%d"),
                "giorno_label": str(r_ed.get("Giorno", cur_d.strftime("%d/%m/%Y"))),
                "tipologia": tp_sel,
                "durata_min": dur_m,
                "moltiplicatore_pct": mult_p,
                "tl_sim": tl_s,
                "tl_high_sim": tlh_s,
                "acc_sim": acc_s,
                "dec_sim": dec_s,
                "acc_dec_sim": acc_dec_s,
                "azioni_sim": az_s,
                "extra_tipo": ex_tp,
                "extra_min": ex_dur,
                "extra_rpe": ex_rpe,
                "srpe_extra_au": srpe_ex_au,
            })

        df_plan_sim = pd.DataFrame(sim_rows)
        df_plot, df_forecast, kpis = _compute_virtual_ewma_projection(
            df_ath_hist=df_ath,
            df_plan_sim=df_plan_sim,
            start_date_plan=start_date_plan,
            avg_daily_tl=avg_daily_tl,
            avg_match_tl=avg_match_tl,
            clinical_cap_active=sim_clinical_cap
        )

        # Arricchisce df_plan_sim con ACWR previsto e flag violazioni
        df_plan_sim["acwr_tl"] = df_forecast["acwr_tl"].values
        df_plan_sim["acwr_mech"] = df_forecast["acwr_mech"].values
        df_plan_sim["violazione_70_cap"] = df_forecast["violazione_70_cap"].values
        df_plan_sim["violazione_acwr_150"] = df_forecast["violazione_acwr_150"].values

        fig_forecast = _build_real_vs_forecast_figure(
            df_plot=df_plot,
            atleta_sel=atleta_sel,
            clinical_cap_active=sim_clinical_cap,
            soglia_70=kpis["soglia_70"]
        )

        # Action Bar con Esportazione PDF "Piano di Carico Previsionale"
        slug_ath = slugify_name(atleta_sel)
        opzioni_pdf = {"what_if": tr("Piano di Carico Previsionale What-If (PDF)", "Predictive What-If Load Plan (PDF)")}
        render_action_bar(
            meta_items=[
                (tr("Atleta", "Athlete"), atleta_sel),
                (tr("Orizzonte", "Horizon"), f"{orizzonte_sel} {tr('giorni', 'days')}"),
                (tr("Picco ACWR", "Peak ACWR"), f"{kpis['peak_acwr_tl']:.0f}%"),
                (tr("Monotonia Foster", "Foster Monotony"), f"{kpis['monotony_foster']:.2f}"),
                (tr("Volume Stimato", "Est. Volume"), f"{kpis['tot_planned_tl']:.0f} TL ({kpis['match_equivalenti']:.1f} Match Eq.)")
            ],
            pdf_options=opzioni_pdf,
            pdf_key=f"wf_pdf_{slug_ath}_{orizzonte_sel}",
            generate_fn=lambda _: crea_pdf_pianificazione_whatif(
                giocatore=atleta_sel,
                orizzonte_gg=orizzonte_sel,
                start_date_str=start_date_plan.strftime("%d/%m/%Y"),
                kpis=kpis,
                df_plan=df_plan_sim,
                fig_forecast=fig_forecast
            ),
            filename_fn=lambda _: f"M0V3_Piano_Previsionale_WhatIf_{slug_ath}_{start_date_plan.strftime('%Y%m%d')}.pdf"
        )

        # 4 KPI Cards Predittive
        pk_acwr = kpis["peak_acwr_tl"]
        if 80.0 <= pk_acwr <= 130.0:
            col_pk = "#10b981"
            sub_pk = tr("Sweet Spot Fisiologico (80-130%)", "Physiological Sweet Spot (80-130%)")
        elif pk_acwr <= 150.0:
            col_pk = "#f59e0b"
            sub_pk = tr("Fascia Attenzione / Tapering (<80 o 130-150%)", "Caution / Tapering Zone (<80 or 130-150%)")
        else:
            col_pk = "#ef4444"
            sub_pk = tr("DANGER ZONE (>150% — Rischio Spike Acuto)", "DANGER ZONE (>150% — Acute Spike Risk)")

        mon_v = kpis["monotony_foster"]
        if mon_v < 1.5:
            col_mon = "#10b981"
            lbl_mon_z = tr("Ottimale (<1.5)", "Optimal (<1.5)")
        elif mon_v <= 2.0:
            col_mon = "#f59e0b"
            lbl_mon_z = tr("Attenzione (1.5-2.0)", "Caution (1.5-2.0)")
        else:
            col_mon = "#ef4444"
            lbl_mon_z = tr("Sovraccarico (>2.0)", "Overload (>2.0)")

        n_viol = kpis["giorni_fuori_soglia"]
        col_viol = "#ef4444" if n_viol > 0 else "#10b981"

        ck1, ck2, ck3, ck4 = st.columns(4)
        with ck1:
            st.markdown(card_kpi(
                tr("Picco ACWR Previsto", "Predicted Peak ACWR"),
                f"<span style='color:{col_pk};'>{pk_acwr:.0f}%</span>",
                f"{sub_pk} | Mech: {kpis['peak_acwr_mech']:.0f}%",
                col_pk
            ), unsafe_allow_html=True)
        with ck2:
            st.markdown(card_kpi(
                tr("Monotonia Prevista (Foster)", "Predicted Monotony (Foster)"),
                f"<span style='color:{col_mon};'>{mon_v:.2f}</span>",
                f"{lbl_mon_z} | Strain 7d: {kpis['strain_foster']:,} AU",
                col_mon
            ), unsafe_allow_html=True)
        with ck3:
            st.markdown(card_kpi(
                tr("Volume Stimato & Match Eq.", "Est. Volume & Match Eq."),
                f"{kpis['tot_planned_tl']:,.0f} <span style='font-size:14px; color:#38bdf8;'>TL</span>",
                tr(f"Equivalente a {kpis['match_equivalenti']:.1f} Match Ufficiali ({kpis['tot_planned_min']:.0f} min)",
                   f"Equivalent to {kpis['match_equivalenti']:.1f} Official Matches ({kpis['tot_planned_min']:.0f} min)"),
                "#0ea5e9"
            ), unsafe_allow_html=True)
        with ck4:
            st.markdown(card_kpi(
                tr("Giorni Fuori Soglia", "Days Exceeding Threshold"),
                f"<span style='color:{col_viol};'>{n_viol} {tr('giorni', 'days')}</span>",
                tr(f"ACWR >150%: {kpis['n_days_viol_acwr']} gg | Tetto 70%: {kpis['n_days_viol_70']} gg",
                   f"ACWR >150%: {kpis['n_days_viol_acwr']} d | 70% Cap: {kpis['n_days_viol_70']} d"),
                col_viol
            ), unsafe_allow_html=True)

        st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)

        # Alert rosso automatico se ci sono giorni che violano il Tetto Clinico 70% o ACWR > 150%
        if kpis["n_days_viol_70"] > 0:
            viol_dates_70 = ", ".join(df_plan_sim[df_plan_sim["violazione_70_cap"] == True]["date_str"].tolist())
            soglia_70_str = f"{kpis['soglia_70']:.0f}"
            msg_v70 = tr(
                f"Le giornate pianificate {viol_dates_70} superano il tetto prudenziale di {soglia_70_str} TL. Riduci la durata o il moltiplicatore di intensità.",
                f"Planned days {viol_dates_70} exceed the safety cap of {soglia_70_str} TL. Reduce duration or intensity multiplier."
            )
            st.markdown(
                f"<div style='background:rgba(239,68,68,0.16); border:1px solid #ef4444; border-left:5px solid #ef4444; border-radius:10px; padding:12px 16px; margin-bottom:14px; font-size:13px; color:#ffffff;'>"
                f"<i class='bi bi-shield-exclamation' style='color:#ef4444; margin-right:6px;'></i>"
                f"<b>{tr('ALLERTA CLINICA CARICO ADATTATO (>70% MEDIA STORICA):', 'ADAPTED LOAD CLINICAL ALERT (>70% HISTORICAL MEAN):')}</b> {msg_v70}"
                f"</div>",
                unsafe_allow_html=True
            )

        if can_proj:
            st.plotly_chart(fig_forecast, use_container_width=True, config=PLOTLY_CONFIG)

        # Riepilogo Tabellare Giornaliero dei Volumi Simulati + Semaforo Giornaliero
        st.markdown(f"#### {tr('Prospetto Analitico Giornaliero dei Volumi Previsionali', 'Daily Analytical Breakdown of Predicted Volumes')}")
        preview_rows = []
        for _, r_s in df_plan_sim.iterrows():
            ac_v = float(r_s["acwr_tl"])
            v70 = bool(r_s["violazione_70_cap"])
            if v70 or ac_v > 150.0:
                st_day = tr("[CRITICO] Fuori Soglia", "[CRITICAL] Out of Threshold")
            elif ac_v > 130.0 or ac_v < 80.0:
                st_day = tr("[ATTENZIONE] Transizione", "[CAUTION] Transition")
            else:
                st_day = tr("[OK] Sweet Spot", "[OK] Sweet Spot")
            preview_rows.append({
                tr("Giorno", "Day"): r_s["giorno_label"],
                tr("Sessione Campo", "Court Session"): r_s["tipologia"],
                tr("Durata (min)", "Duration (min)"): int(r_s["durata_min"]),
                tr("Intensità (%)", "Intensity (%)"): f"{int(r_s['moltiplicatore_pct'])}%",
                "TL Stimato": f"{r_s['tl_sim']:.0f}",
                "TL High Stimato": f"{r_s['tl_high_sim']:.0f}",
                "High Acc+Dec IMU": f"{r_s['acc_dec_sim']:.0f}",
                "ACWR Previsto (%)": f"{ac_v:.1f}%",
                tr("Extra-Campo (sRPE)", "Off-Court (sRPE)"): f"{r_s['extra_tipo']} ({r_s['srpe_extra_au']:.0f} AU)" if r_s["srpe_extra_au"] > 0 else "-",
                tr("Stato Previsionale", "Forecast Status"): st_day,
            })
        st.dataframe(pd.DataFrame(preview_rows), use_container_width=True, hide_index=True)

        # Salvataggio Scenario Piano Microciclo (Supabase + JSON/Cloud Snapshot)
        st.divider()
        st.markdown(f"#### <i class='bi bi-bookmark-check' style='color:#38bdf8;'></i> {tr('Salva Scenario Microciclo (Per Confronto Piano vs Eseguito)', 'Save Microcycle Scenario (For Plan vs Executed Comparison)')}", unsafe_allow_html=True)
        cs1, cs2 = st.columns([2.5, 1.2])
        with cs1:
            default_plan_name = f"Microciclo {atleta_sel} ({start_date_plan.strftime('%d/%m/%Y')} - {orizzonte_sel}gg)"
            nome_piano_in = st.text_input(
                tr("Nome Identificativo del Piano Previsionale", "Predictive Plan Identifier Name"),
                value=default_plan_name,
                key="wf_save_plan_name"
            )
        with cs2:
            st.markdown("<div style='height:26px;'></div>", unsafe_allow_html=True)
            if st.button(tr("Salva Piano Microciclo", "Save Microcycle Plan"), type="primary", use_container_width=True, key="btn_wf_save_plan"):
                payload_plan = {
                    "atleta_nome": atleta_sel,
                    "nome_piano": nome_piano_in.strip() or default_plan_name,
                    "data_inizio": start_date_plan.strftime("%Y-%m-%d"),
                    "giorni_orizzonte": int(orizzonte_sel),
                    "schedule_json": df_plan_sim.drop(columns=["date_obj"]).to_dict(orient="records"),
                    "kpi_json": kpis,
                    "creato_da": u_email,
                }
                ok_sp, pid_sp = save_piano_microciclo(payload_plan)
                if ok_sp:
                    set_notification(
                        title=tr("Piano Microciclo Salvato", "Microcycle Plan Saved"),
                        message=tr(f"Il piano '{payload_plan['nome_piano']}' è stato archiviato senza alterare i dati GPS storici. Puoi monitorarne l'aderenza nel tab 'Confronto Piano vs Eseguito'.",
                                   f"Plan '{payload_plan['nome_piano']}' was archived without altering historical GPS data. You can track adherence in the 'Plan vs Executed Comparison' tab."),
                        tipo="toast"
                    )
                    st.rerun()

        st.markdown("<div style='margin-top:24px;'></div>", unsafe_allow_html=True)
        render_scientific_methodology_box("what_if_planning")

    # =========================================================================
    # TAB 2: CONFRONTO PIANO VS ESEGUITO
    # =========================================================================
    elif active_wf_tab == lbl_tab_comp:
        piani_salv = get_piani_microciclo(atleta_nome=atleta_sel)
        if not piani_salv:
            st.info(tr(
                f"Nessun piano di microciclo ancora salvato per {atleta_sel}. Configura una simulazione nel primo tab e clicca su 'Salva Piano Microciclo' per abilitare il monitoraggio Piano vs Eseguito.",
                f"No microcycle plan saved yet for {atleta_sel}. Configure a simulation in the first tab and click 'Save Microcycle Plan' to enable Plan vs Executed tracking."
            ))
            return

        mappa_piani = {
            f"{p.get('nome_piano', 'Piano')} — Inizio: {p.get('data_inizio', '')} ({p.get('giorni_orizzonte', 7)}gg)": p
            for p in piani_salv
        }
        c_ps1, c_ps2 = st.columns([3.2, 1.0])
        with c_ps1:
            sel_p_lbl = st.selectbox(
                tr("Seleziona Piano Microciclo Salvato da Confrontare con i Dati GPS Reali:", "Select Saved Microcycle Plan to Compare with Actual GPS Data:"),
                list(mappa_piani.keys()),
                key="wf_comp_plan_picker"
            )
        piano_attivo = mappa_piani[sel_p_lbl]
        with c_ps2:
            st.markdown("<div style='height:26px;'></div>", unsafe_allow_html=True)
            if st.button(tr("Elimina Piano", "Delete Plan"), type="secondary", use_container_width=True, key="btn_wf_del_plan"):
                delete_piano_microciclo(piano_attivo.get("id"))
                st.rerun()

        sched_list = piano_attivo.get("schedule_json") or []
        if isinstance(sched_list, str):
            import json
            try:
                sched_list = json.loads(sched_list)
            except Exception:
                sched_list = []

        if not sched_list:
            st.warning(tr("Il piano selezionato non contiene giornate valide.", "Selected plan contains no valid days."))
            return

        # Aggregazione dati GPS realmente eseguiti dall'atleta nelle date del piano
        actual_by_date = {}
        if df_ath is not None and not df_ath.empty:
            df_a_tmp = df_ath.copy()
            if "Date_obj" not in df_a_tmp.columns:
                df_a_tmp["Date_obj"] = pd.to_datetime(df_a_tmp["Date"], format="%d/%m/%Y", errors="coerce")
            df_a_tmp["d_str"] = df_a_tmp["Date_obj"].dt.strftime("%d/%m/%Y")
            for d_k, grp in df_a_tmp.groupby("d_str"):
                actual_by_date[str(d_k)] = {
                    "tl_real": float(pd.to_numeric(grp["Training Load"], errors="coerce").fillna(0).sum()),
                    "tl_high_real": float(pd.to_numeric(grp["TL_High"], errors="coerce").fillna(0).sum()) if "TL_High" in grp.columns else 0.0,
                    "min_real": float(pd.to_numeric(grp["Minuti"], errors="coerce").fillna(0).sum()) if "Minuti" in grp.columns else 0.0,
                    "tipi_real": ", ".join([str(x) for x in grp["Tipologia Sessione"].dropna().unique()]) if "Tipologia Sessione" in grp.columns else "Sessione GPS",
                }

        comp_rows = []
        tot_plan_tl = 0.0
        tot_exec_tl = 0.0
        tot_plan_min = 0.0
        tot_exec_min = 0.0
        giorni_eseguiti = 0

        for item in sched_list:
            d_str = str(item.get("date_str", ""))
            tl_p = float(item.get("tl_sim", 0) or 0)
            min_p = float(item.get("durata_min", 0) or 0)
            tp_p = str(item.get("tipologia", ""))

            act = actual_by_date.get(d_str, {})
            tl_r = float(act.get("tl_real", 0.0))
            min_r = float(act.get("min_real", 0.0))
            tp_r = str(act.get("tipi_real", "-")) if tl_r > 0 else ("REST" if tl_p == 0 else tr("Non ancora registrato", "Not logged yet"))

            tot_plan_tl += tl_p
            tot_exec_tl += tl_r
            tot_plan_min += min_p
            tot_exec_min += min_r
            if tl_r > 0 or (tl_p == 0 and d_str in actual_by_date):
                giorni_eseguiti += 1

            delta_tl = tl_r - tl_p
            aderenza_pct = round((tl_r / tl_p) * 100.0, 1) if tl_p > 0 else (100.0 if tl_r == 0 else 0.0)

            comp_rows.append({
                "date_str": d_str,
                "giorno": item.get("giorno_label", d_str),
                "tipo_plan": tp_p,
                "min_plan": round(min_p, 0),
                "tl_plan": round(tl_p, 1),
                "tipo_real": tp_r,
                "min_real": round(min_r, 0),
                "tl_real": round(tl_r, 1),
                "delta_tl": round(delta_tl, 1),
                "aderenza_pct": aderenza_pct,
            })

        df_comp = pd.DataFrame(comp_rows)
        aderenza_globale_tl = round((tot_exec_tl / tot_plan_tl) * 100.0, 1) if tot_plan_tl > 0 else 0.0
        delta_globale_tl = tot_exec_tl - tot_plan_tl
        col_adh = "#10b981" if 85.0 <= aderenza_globale_tl <= 115.0 else ("#f59e0b" if 70.0 <= aderenza_globale_tl <= 130.0 else "#ef4444")

        cc1, cc2, cc3, cc4 = st.columns(4)
        with cc1:
            st.markdown(card_kpi(tr("TL Pianificato Totale", "Total Planned TL"), f"{tot_plan_tl:,.0f} TL", f"{tot_plan_min:.0f} min programmati", "#0ea5e9"), unsafe_allow_html=True)
        with cc2:
            st.markdown(card_kpi(tr("TL Eseguito Reale (GPS)", "Actual Executed TL (GPS)"), f"{tot_exec_tl:,.0f} TL", f"{tot_exec_min:.0f} min registrati", "#10b981"), unsafe_allow_html=True)
        with cc3:
            st.markdown(card_kpi(tr("Aderenza al Piano (%)", "Plan Adherence (%)"), f"<span style='color:{col_adh};'>{aderenza_globale_tl:.1f}%</span>", tr("Target ottimale: 85% - 115%", "Optimal target: 85% - 115%"), col_adh), unsafe_allow_html=True)
        with cc4:
            st.markdown(card_kpi(tr("Scostamento Cumulativo", "Cumulative Delta"), f"{delta_globale_tl:+,.0f} TL", tr(f"Su {len(df_comp)} giornate nel piano", f"Across {len(df_comp)} planned days"), "#f59e0b"), unsafe_allow_html=True)

        st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)

        # Grafico Comparativo Piano vs Eseguito
        fig_c = go.Figure()
        fig_c.add_trace(go.Bar(
            x=df_comp["date_str"],
            y=df_comp["tl_plan"],
            name=tr("Training Load Pianificato (What-If)", "Planned Training Load (What-If)"),
            marker_color="rgba(56, 189, 248, 0.45)",
            marker_line=dict(color="#38bdf8", width=2)
        ))
        fig_c.add_trace(go.Bar(
            x=df_comp["date_str"],
            y=df_comp["tl_real"],
            name=tr("Training Load Eseguito Reale (GPS)", "Actual Executed Training Load (GPS)"),
            marker_color="#10b981"
        ))
        fig_c.update_layout(
            title=dict(text=tr(f"Confronto Giornaliero Piano Previsionale vs Carico Eseguito — {atleta_sel}", f"Daily Planned vs Executed Workload Comparison — {atleta_sel}"), font=dict(size=14, color="#ffffff")),
            barmode="group",
            height=380,
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#cbd5e1", family="Inter"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(color="#cbd5e1")),
            xaxis=dict(type="category", tickfont=dict(color="#94a3b8"), gridcolor="rgba(56,189,248,0.08)"),
            yaxis=dict(title=dict(text="Training Load [AU]", font=dict(color="#38bdf8")), gridcolor="rgba(56,189,248,0.12)", tickfont=dict(color="#cbd5e1"))
        )
        st.plotly_chart(fig_c, use_container_width=True, config=PLOTLY_CONFIG)

        # Tabella Dettaglio Piano vs Eseguito
        tbl_c = []
        for _, rc in df_comp.iterrows():
            tbl_c.append({
                tr("Data", "Date"): rc["giorno"],
                tr("Sessione Pianificata", "Planned Session"): f"{rc['tipo_plan']} ({rc['min_plan']:.0f}m)",
                tr("TL Pianificato", "Planned TL"): f"{rc['tl_plan']:.0f} TL",
                tr("Sessione Eseguita (GPS)", "Executed Session (GPS)"): f"{rc['tipo_real']} ({rc['min_real']:.0f}m)" if rc["tl_real"] > 0 else rc["tipo_real"],
                tr("TL Eseguito", "Executed TL"): f"{rc['tl_real']:.0f} TL",
                tr("Delta TL", "Delta TL"): f"{rc['delta_tl']:+.0f} TL",
                tr("Aderenza %", "Adherence %"): f"{rc['aderenza_pct']:.0f}%",
            })
        st.dataframe(pd.DataFrame(tbl_c), use_container_width=True, hide_index=True)
