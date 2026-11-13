# Copyright 2026 Riccardo Di Maio - M0V3 S.r.l. Tutti i diritti riservati.
# Proprietary Sports Science & Clinical Performance Intelligence Architecture.
import datetime
from datetime import date, timedelta
import calendar
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from config import (
    tr,
    render_page_header,
    render_action_bar,
    render_tab_navigation,
    card_kpi,
    STIMOLI_GYM,
    STIMOLI_PREP_FISICA,
    DISTRETTI_CATENE_CINETICHE,
    CATENA_TO_DISTRETTI_CLINICI,
    MACRO_FAMIGLIE_BIOMECCANICHE,
    get_stimolo_color,
    get_catena_clinici,
)
from pdf_generator import crea_pdf_calendario_medico, slugify_name
from utils import (
    supabase,
    supabase_admin,
    load_local_database,
    get_atleta_dettagli_per_utente,
    get_athlete_master_calendar,
    get_registro_medico,
    upsert_registro_medico,
    delete_registro_medico,
    render_athlete_hero_strip,
    calcola_e_salva_slot_rpe,
)

# =========================================================================
# COSTANTI & PALETTE CLINICA M0V3 (ZERO EMOJI - BOOTSTRAP ICONS & PURE CSS)
# =========================================================================

STATUS_COLORS = {
    "DISPONIBILE": "#10b981",       # Smeraldo (Full Training)
    "LIMITATO": "#f59e0b",          # Ambra (Modified / RTP)
    "INDISPONIBILE": "#e11d48",     # Rosso Rubino (Out / Stop Medico)
    "RIPOSO_VIAGGIO": "#38bdf8",    # Blu / Ardesia (Off / Viaggio)
    "NESSUN_DATO": "#334155"        # Ardesia neutro
}

STATUS_LABELS = {
    "DISPONIBILE": ("Disponibile (Full Training)", "Available (Full Training)"),
    "LIMITATO": ("Carico Adattato (Modified / RTP)", "Modified Load (RTP)"),
    "INDISPONIBILE": ("Indisponibile (Stop Medico / Out)", "Unavailable (Medical Stop)"),
    "RIPOSO_VIAGGIO": ("Riposo / Viaggio Programmato", "Rest / Scheduled Travel")
}

DISTRETTI_ANATOMICI = [
    "Nessuno / Sistemico",
    "Cervicale",
    "Spalla",
    "Gomito",
    "Polso / Mano",
    "Tronco / Costato",
    "Rachide Lombare / Bacino",
    "Anca / Inguine",
    "Gluteo",
    "Quadricipite (Anteriore Coscia)",
    "Ischiocrurali (Posteriore Coscia)",
    "Adduttori",
    "Ginocchio",
    "Polpaccio / Gastrocnemio",
    "Tendine d'Achille",
    "Caviglia",
    "Piede / Fascia Plantare"
]

SOTTOTIPI_TRATTAMENTO = [
    "Terapia Manuale / Osteopatia",
    "Terapia Fisica (Tecar/Laser/Onde d'urto)",
    "Massaggio Scarico / Decontratturante",
    "Dry Needling / Fibrolisi",
    "Esercizio Terapeutico / Rieducazione",
    "Taping / Bendaggio Funzionale"
]

NATURA_INFORTUNIO = [
    "Muscolare",
    "Tendineo / Entesopatia",
    "Articolare / Legamentoso",
    "Osseo / Cartilagineo",
    "Neurologico / Rachide"
]

MECCANISMI = [
    "Sovraccarico (Overuse)",
    "Traumatico / Acuto in Match",
    "Traumatico / Acuto in Allenamento",
    "Prevenzione / Routine",
    "N/A"
]


def _build_day_tooltip_html(d_key, d_info, st_col, is_en, g_sett):
    """
    Costruisce l'HTML per il Tooltip ricco al passaggio del mouse (Hover) sulla Mini-Card giornaliera.
    Zero Emoji: solo Bootstrap Icons e badge WCAG AAA.
    """
    st_op = d_info.get('status_operativo', 'DISPONIBILE')
    st_lbl_tup = STATUS_LABELS.get(st_op, ('Disponibile', 'Available'))
    st_lbl = st_lbl_tup[1] if is_en else st_lbl_tup[0]

    align_style = "left: 0; transform: none;" if g_sett <= 1 else ("right: 0; left: auto; transform: none;" if g_sett >= 5 else "left: 50%; transform: translateX(-50%);")

    lines = []
    # Header Tooltip
    lines.append(
        f"<div style='display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #334155; padding-bottom:5px; margin-bottom:6px;'>"
        f"<span style='font-weight:800; color:#38bdf8; font-size:11.5px;'>{d_key}</span>"
        f"<span style='color:{st_col}; font-weight:800; font-size:10px; background:rgba(255,255,255,0.08); padding:2px 6px; border-radius:4px;'>{st_lbl}</span>"
        f"</div>"
    )

    has_content = False

    # 1. Tennis & GPS
    has_tennis_srpe = any(sl.get('tipo') == 'Tennis' for sl in d_info.get('srpe_slots', []))
    if d_info.get('gps_presente') or has_tennis_srpe:
        has_content = True
        gps_parts = []
        if d_info.get('gps_presente'):
            tl_v = int(round(d_info.get('training_load_gps', 0)))
            tlh_v = int(round(d_info.get('tl_high', 0)))
            acc_dec = int(round(d_info.get('high_accel_imu', 0) + d_info.get('high_decel_imu', 0)))
            match_str = " [MATCH]" if d_info.get('is_match') else ""
            gps_parts.append(f"TL: <b>{tl_v}</b>{match_str} | TL-High: <b>{tlh_v}</b> | Acc+Dec: <b>{acc_dec}</b>")
        for sl in d_info.get('srpe_slots', []):
            if sl.get('tipo') == 'Tennis':
                gps_parts.append(f"sRPE Tennis: {sl.get('minuti', 0):.0f}m @ RPE {sl.get('rpe', 0):.0f} &rarr; <b>{sl.get('carico', 0):.0f} AU</b>")
        lbl_ten = tr("Tennis & Campo GPS", "Tennis & GPS Court")
        gps_html = "<br>".join(gps_parts)
        lines.append(
            f"<div style='margin-bottom:6px;'>"
            f"<div style='color:#38bdf8; font-weight:800; font-size:10.5px;'><i class='bi bi-broadcast'></i> {lbl_ten}</div>"
            f"<div style='color:#cbd5e1; font-size:10px; margin-left:14px;'>{gps_html}</div>"
            f"</div>"
        )

    # 2. Palestra & Preparazione Fisica (70/30 Split)
    gym_slots = [sl for sl in d_info.get('srpe_slots', []) if sl.get('tipo') in ('Gym', 'Preparazione Fisica')]
    if gym_slots:
        has_content = True
        gym_parts = []
        for sl in gym_slots:
            tipo_sl = sl.get('tipo', 'Gym')
            dur_m = sl.get('minuti', 0)
            dur_atl = sl.get('durata_atleta_min')
            dur_stf = sl.get('durata_staff_min')
            rpe_v = sl.get('rpe', 0)
            carico_tot = sl.get('carico', 0)

            if dur_atl is not None and dur_stf is not None and float(dur_atl) > 0 and float(dur_stf) > 0 and abs(float(dur_atl) - float(dur_stf)) > 0:
                time_info = f"Media {dur_m:.0f}m (Atl {float(dur_atl):.0f}m / Stf {float(dur_stf):.0f}m)"
            else:
                time_info = f"{dur_m:.0f}m"

            s_prim = sl.get('stimolo_primario') or 'Generale'
            d_prim = sl.get('distretto_primario') or ''
            p_prim = sl.get('peso_primario_pct', 100) or 100
            c_prim = sl.get('carico_primario', carico_tot)

            entry_p = f"<b>{tipo_sl}:</b> {time_info} @ RPE {rpe_v:.0f} = <b>{carico_tot:.0f} AU</b>"
            entry_p += f"<br>&bull; <i>{p_prim}% Primario:</i> {s_prim} ({d_prim}) &rarr; <b>{c_prim:.0f} AU</b>"

            s_sec = sl.get('stimolo_secondario')
            if s_sec:
                d_sec = sl.get('distretto_secondario') or ''
                p_sec = 100 - p_prim
                c_sec = sl.get('carico_secondario', 0)
                entry_p += f"<br>&bull; <i>{p_sec}% Complementare:</i> {s_sec} ({d_sec}) &rarr; <b>{c_sec:.0f} AU</b>"

            stress_e = sl.get('stress_eccentrico_atteso', 'Moderato')
            stress_col = "#f87171" if stress_e == 'Elevato' else ("#fbbf24" if stress_e == 'Moderato' else "#34d399")
            entry_p += f"<br>&bull; Stress Eccentrico: <span style='color:{stress_col}; font-weight:700;'>{stress_e}</span>"
            gym_parts.append(entry_p)

        lbl_gym = tr("Palestra & Preparazione Fisica (70/30)", "Gym & Conditioning (70/30)")
        gym_hr_sep = "<hr style='border:none; border-top:1px dashed #334155; margin:4px 0;'>"
        gym_html = gym_hr_sep.join(gym_parts)
        lines.append(
            f"<div style='margin-bottom:6px;'>"
            f"<div style='color:#facc15; font-weight:800; font-size:10.5px;'><i class='bi bi-layers-half'></i> {lbl_gym}</div>"
            f"<div style='color:#cbd5e1; font-size:10px; margin-left:14px;'>{gym_html}</div>"
            f"</div>"
        )

    # 3. Clinica & Fisioterapia
    evs = d_info.get('medico_eventi', [])
    if evs:
        has_content = True
        ev_parts = []
        for ev in evs:
            t_ev = ev.get('tipo_scheda', 'EVENTO')
            distr = ev.get('distretto_anatomico', 'Sistemico')
            vas = ev.get('scala_dolore_vas')
            vas_txt = f" | VAS: <b style='color:#f87171;'>{vas}/10</b>" if vas is not None else ""
            sottotipo = ev.get('sottotipo_evento', '')
            ev_parts.append(f"[{t_ev}] {distr} ({sottotipo}){vas_txt}")
        lbl_med = tr("Clinica & Fisioterapia", "Clinical & Physio")
        ev_html = "<br>".join(ev_parts)
        lines.append(
            f"<div style='margin-bottom:6px;'>"
            f"<div style='color:#34d399; font-weight:800; font-size:10.5px;'><i class='bi bi-bandaid'></i> {lbl_med}</div>"
            f"<div style='color:#cbd5e1; font-size:10px; margin-left:14px;'>{ev_html}</div>"
            f"</div>"
        )

    # 4. Test Fisici
    if d_info.get('test_count', 0) > 0:
        has_content = True
        n_t = d_info.get('test_count')
        lbl_test = tr("Test Fisici", "Physical Tests")
        lines.append(
            f"<div style='margin-bottom:6px;'>"
            f"<div style='color:#60a5fa; font-weight:800; font-size:10.5px;'><i class='bi bi-clipboard2-pulse'></i> {lbl_test}</div>"
            f"<div style='color:#cbd5e1; font-size:10px; margin-left:14px;'>{n_t} {tr('test registrati in archivio', 'tests logged')}</div>"
            f"</div>"
        )

    # 5. Wellness
    if d_info.get('wellness_presente') and d_info.get('wellness_score') is not None:
        has_content = True
        w_sc = d_info.get('wellness_score')
        w_det = d_info.get('wellness_dettagli', {})
        doms_v = w_det.get('doms', 0)
        doms_c = "#f87171" if doms_v >= 7 else ("#fbbf24" if doms_v >= 5 else "#34d399")
        lbl_wel = tr("Wellness Mattutino", "Morning Wellness")
        lines.append(
            f"<div style='margin-bottom:4px;'>"
            f"<div style='color:#c084fc; font-weight:800; font-size:10.5px;'><i class='bi bi-heart-pulse'></i> {lbl_wel}</div>"
            f"<div style='color:#cbd5e1; font-size:10px; margin-left:14px;'>Score: <b>{w_sc:.1f}/10</b> | DOMS: <b style='color:{doms_c};'>{doms_v}/10</b> | Sonno: <b>{w_det.get('sonno_qualita', '-')}</b></div>"
            f"</div>"
        )

    if not has_content:
        lines.append(f"<div style='color:#94a3b8; font-style:italic;'>{tr('Nessuna attività registrata per questo giorno.', 'No activities logged for this day.')}</div>")

    inner_content = "".join(lines)
    return (
        f"<div class='m0v3-tooltip' style='{align_style}'>"
        f"{inner_content}"
        f"</div>"
    )





def _get_atleti_dict(user=None, is_admin=False, is_coach=True):
    dict_atleti = {}
    try:
        db = supabase_admin if is_admin else supabase
        if is_admin:
            res_a = db.table('atleti').select('id, nome, cognome').order('cognome').execute()
            for a in (res_a.data or []):
                full = f"{a.get('nome', '')} {a.get('cognome', '')}".strip()
                dict_atleti[full] = a['id']
        elif is_coach:
            if user:
                res_assoc = db.table('associazioni').select('atleta_id, atleti(id, nome, cognome)').eq('profilo_id', user.id).execute()
                for it in (res_assoc.data or []):
                    atl = it.get('atleti')
                    if atl:
                        full = f"{atl.get('nome', '')} {atl.get('cognome', '')}".strip()
                        dict_atleti[full] = atl['id']
            if not dict_atleti:
                res_a = db.table('atleti').select('id, nome, cognome').order('cognome').execute()
                for a in (res_a.data or []):
                    full = f"{a.get('nome', '')} {a.get('cognome', '')}".strip()
                    dict_atleti[full] = a['id']
        else:
            atl_info = get_atleta_dettagli_per_utente(user.id) if user else None
            if atl_info:
                dict_atleti[atl_info['nome_completo']] = atl_info['id']
    except Exception:
        pass

    if is_admin or is_coach or not dict_atleti:
        df_local = load_local_database()
        if not df_local.empty and 'Players' in df_local.columns:
            norm_map = {k.strip().lower(): k for k in dict_atleti.keys()}
            for p in sorted(df_local['Players'].dropna().unique()):
                p_str = str(p).strip()
                if p_str:
                    p_low = p_str.lower()
                    if p_low in norm_map:
                        dict_atleti[p_str] = dict_atleti[norm_map[p_low]]
                    elif p_str not in dict_atleti:
                        dict_atleti[p_str] = f"mock-{p_str}"

    if not dict_atleti:
        dict_atleti["Atleta Demo"] = "mock-atleta-demo"
    return dict_atleti


def render_master_timeline(t, atleta_sel=None, atleta_id_sel=None, key_prefix="cal", show_hero_strip=False):
    """
    Renders the Master Timeline & Integrated Monthly Calendar for the specified athlete.
    """
    user_role = st.session_state.get('role', 'Atleta')
    is_admin = (user_role in ['Super-Admin', 'Admin'])
    is_coach = (user_role in ['Staff', 'Coach', 'Fisio / Medico'] or is_admin)
    user = st.session_state.get('user')

    dict_atleti = _get_atleti_dict(user, is_admin, is_coach)
    atleta_nomi = list(dict_atleti.keys())

    today = datetime.date.today()
    if f'{key_prefix}_current_year' not in st.session_state:
        st.session_state[f'{key_prefix}_current_year'] = today.year
    if f'{key_prefix}_current_month' not in st.session_state:
        st.session_state[f'{key_prefix}_current_month'] = today.month

    if not atleta_sel:
        glob_ath = st.session_state.get('selected_athlete')
        if glob_ath in atleta_nomi:
            atleta_sel = glob_ath
        elif f'{key_prefix}_atleta_sel' in st.session_state and st.session_state[f'{key_prefix}_atleta_sel'] in atleta_nomi:
            atleta_sel = st.session_state[f'{key_prefix}_atleta_sel']
        else:
            atleta_sel = atleta_nomi[0] if atleta_nomi else "prova uno"

    if not atleta_id_sel:
        atleta_id_sel = dict_atleti.get(atleta_sel, f"mock-{atleta_sel}")

    # Navigazione Mese del Calendario
    c_prev, c_label, c_next, c_today = st.columns([1, 2.5, 1, 1.2])
    with c_prev:
        if st.button("< " + tr("Mese Prec.", "Prev"), key=f"{key_prefix}_btn_prev", use_container_width=True):
            m = st.session_state[f'{key_prefix}_current_month'] - 1
            y = st.session_state[f'{key_prefix}_current_year']
            if m < 1:
                m = 12
                y -= 1
            st.session_state[f'{key_prefix}_current_month'] = m
            st.session_state[f'{key_prefix}_current_year'] = y
            st.rerun()
    with c_next:
        if st.button(tr("Mese Succ.", "Next") + " >", key=f"{key_prefix}_btn_next", use_container_width=True):
            m = st.session_state[f'{key_prefix}_current_month'] + 1
            y = st.session_state[f'{key_prefix}_current_year']
            if m > 12:
                m = 1
                y += 1
            st.session_state[f'{key_prefix}_current_month'] = m
            st.session_state[f'{key_prefix}_current_year'] = y
            st.rerun()
    with c_today:
        if st.button(tr("Oggi", "Today"), key=f"{key_prefix}_btn_today", use_container_width=True):
            st.session_state[f'{key_prefix}_current_month'] = today.month
            st.session_state[f'{key_prefix}_current_year'] = today.year
            st.rerun()

    mese_corrente = st.session_state[f'{key_prefix}_current_month']
    anno_corrente = st.session_state[f'{key_prefix}_current_year']
    nomi_mesi_it = ["Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno", "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"]
    nomi_mesi_en = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
    nome_mese_str = tr(nomi_mesi_it[mese_corrente - 1], nomi_mesi_en[mese_corrente - 1])

    with c_label:
        st.markdown(
            f"<div style='text-align:center; padding:7px 0; background:#0f172a; border-radius:8px; border:1px solid #1e293b; color:#38bdf8; font-weight:800; font-size:13.5px; text-transform:uppercase; letter-spacing:0.5px;'>"
            f"<i class='bi bi-calendar3' style='margin-right:6px;'></i>{nome_mese_str} {anno_corrente}"
            f"</div>",
            unsafe_allow_html=True
        )

    # Striscia Compatta Identità Atleta MOV3 con tag mese (solo se richiesta)
    if show_hero_strip:
        lbl_m_tag = f"{tr('Mese Visualizzato', 'Viewing Month')}: {nome_mese_str} {anno_corrente}"
        render_athlete_hero_strip(atleta_sel, extra_badges=[lbl_m_tag])

    # -------------------------------------------------------------------------
    # 3. RECUPERO MASTER TIMELINE MENSILE
    # -------------------------------------------------------------------------
    _, num_giorni_mese = calendar.monthrange(anno_corrente, mese_corrente)
    start_date_mese = datetime.date(anno_corrente, mese_corrente, 1)
    end_date_mese = datetime.date(anno_corrente, mese_corrente, num_giorni_mese)

    master_calendar = get_athlete_master_calendar(atleta_sel, atleta_id_sel, start_date_mese, end_date_mese)

    # Calcolo KPI Mensili
    tot_giorni = len(master_calendar)
    giorni_disponibile = sum(1 for d in master_calendar.values() if d['status_operativo'] == 'DISPONIBILE')
    giorni_limitato = sum(1 for d in master_calendar.values() if d['status_operativo'] == 'LIMITATO')
    giorni_stop = sum(1 for d in master_calendar.values() if d['status_operativo'] == 'INDISPONIBILE')
    giorni_viaggio = sum(1 for d in master_calendar.values() if d['status_operativo'] == 'RIPOSO_VIAGGIO')
    
    tot_trattamenti = sum(1 for d in master_calendar.values() if d['has_trattamento'])
    pct_disp = (giorni_disponibile / tot_giorni * 100) if tot_giorni > 0 else 100.0

    # Action Bar con Export PDF (solo se in pagina dedicata)
    if show_hero_strip:
        slug_atl = slugify_name(atleta_sel)
        kpis_dict = {
            'pct_disp': pct_disp,
            'giorni_disponibile': giorni_disponibile,
            'giorni_limitato': giorni_limitato,
            'giorni_stop': giorni_stop,
            'tot_trattamenti': tot_trattamenti,
            'giorni_viaggio': giorni_viaggio,
            'tot_giorni': tot_giorni
        }
        opzioni_pdf = {"calendario": tr("Master Timeline & Diario Clinico (PDF)", "Master Timeline & Clinical Diary (PDF)")}
        render_action_bar(
            meta_items=[
                (tr("Atleta Selezionato", "Selected Athlete"), atleta_sel),
                (tr("Periodo Mese", "Month Period"), f"{nome_mese_str} {anno_corrente}"),
                (tr("Disponibilità Piena", "Full Availability"), f"{pct_disp:.0f}%"),
                (tr("Trattamenti Fisio", "Physio Treatments"), f"{tot_trattamenti}"),
            ],
            pdf_options=opzioni_pdf,
            pdf_key=f"pdf_cal_med_{slug_atl}_{anno_corrente}_{mese_corrente}",
            generate_fn=lambda _: crea_pdf_calendario_medico(atleta_sel, mese_corrente, anno_corrente, master_calendar, kpis_dict),
            filename_fn=lambda _: f"M0V3_Area_Medica_{slug_atl}_{anno_corrente}_{mese_corrente:02d}.pdf"
        )

    # -------------------------------------------------------------------------
    # 4. BARRA KPI EXECUTIVE MENSILE (5 Card con Bootstrap Icons)
    # -------------------------------------------------------------------------
    c_k1, c_k2, c_k3, c_k4, c_k5 = st.columns(5)
    with c_k1:
        st.markdown(card_kpi(
            tr("Disponibilità Piena", "Full Availability"),
            f"{pct_disp:.0f}%",
            sottotitolo=f"{giorni_disponibile} / {tot_giorni} {tr('giorni', 'days')}",
            accento="#10b981"
        ), unsafe_allow_html=True)
    with c_k2:
        st.markdown(card_kpi(
            tr("Carico Adattato", "Modified Load"),
            f"{giorni_limitato}",
            sottotitolo=tr("Giorni con Limitazione", "Days with Limitation"),
            accento="#f59e0b"
        ), unsafe_allow_html=True)
    with c_k3:
        st.markdown(card_kpi(
            tr("Stop / Infortunio", "Medical Stop"),
            f"{giorni_stop}",
            sottotitolo=tr("Giorni Fuori Gruppo", "Days Out of Group"),
            accento="#e11d48"
        ), unsafe_allow_html=True)
    with c_k4:
        st.markdown(card_kpi(
            tr("Trattamenti Fisio", "Physio Treatments"),
            f"{tot_trattamenti}",
            sottotitolo=tr("Sedute Eseguite", "Sessions Completed"),
            accento="#0ea5e9"
        ), unsafe_allow_html=True)
    with c_k5:
        st.markdown(card_kpi(
            tr("Riposo / Viaggio", "Rest / Travel"),
            f"{giorni_viaggio}",
            sottotitolo=tr("Giorni Logistica", "Logistics Days"),
            accento="#64748b"
        ), unsafe_allow_html=True)

    st.markdown("<div style='margin-bottom:14px;'></div>", unsafe_allow_html=True)

    st.markdown(
        f"<div style='display:flex; align-items:center; gap:8px; margin-bottom:12px;'>"
        f"<i class='bi bi-calendar2-range' style='color:#0ea5e9; font-size:18px;'></i>"
        f"<span style='font-size:16px; font-weight:800; color:#0f172a; text-transform:uppercase; letter-spacing:0.5px;'>"
        f"{tr('Griglia Mensile Integrata', 'Integrated Monthly Grid')} — {nome_mese_str} {anno_corrente}"
        f"</span></div>",
        unsafe_allow_html=True
    )

    # Iniezione Stili CSS per Hover Mini-Card Tooltip M0V3
    st.markdown("""
    <style>
    .m0v3-day-card {
        position: relative;
        background: #ffffff;
        border: 1px solid #cbd5e1;
        border-radius: 8px;
        padding: 6px 6px;
        min-height: 118px;
        margin-bottom: 8px;
        font-family: "Inter", sans-serif;
        transition: transform 0.12s ease, box-shadow 0.12s ease;
    }
    .m0v3-day-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 18px rgba(15, 23, 42, 0.14);
        border-color: #0ea5e9;
        z-index: 1000;
    }
    .m0v3-day-card .m0v3-tooltip {
        visibility: hidden;
        opacity: 0;
        position: absolute;
        bottom: calc(100% + 8px);
        width: 290px;
        background: #0f172a;
        color: #f8fafc;
        border: 1px solid #334155;
        border-radius: 8px;
        padding: 10px 12px;
        font-size: 11px;
        line-height: 1.45;
        box-shadow: 0 14px 28px rgba(0, 0, 0, 0.4);
        z-index: 999999;
        pointer-events: none;
        transition: opacity 0.18s ease, visibility 0.18s ease;
    }
    .m0v3-day-card:hover .m0v3-tooltip {
        visibility: visible;
        opacity: 1;
    }
    </style>
    """, unsafe_allow_html=True)

    # Legenda Status Operativo
    st.markdown(
        f"<div style='display:flex; align-items:center; gap:16px; flex-wrap:wrap; background:#ffffff; border:1px solid #e2e8f0; border-radius:8px; padding:8px 14px; margin-bottom:14px; font-size:11.5px; color:#475569; font-weight:700; font-family:\"Inter\",sans-serif;'>"
        f"<span style='color:#0f172a; text-transform:uppercase; font-size:11px; letter-spacing:0.5px;'>Legenda Status:</span>"
        f"<span style='display:inline-flex; align-items:center; gap:5px;'><span style='width:9px; height:9px; border-radius:50%; background:#10b981;'></span>{tr('Disponibile (Full Training)', 'Available')}</span>"
        f"<span style='display:inline-flex; align-items:center; gap:5px;'><span style='width:9px; height:9px; border-radius:50%; background:#f59e0b;'></span>{tr('Carico Adattato (RTP / Fastidio)', 'Modified')}</span>"
        f"<span style='display:inline-flex; align-items:center; gap:5px;'><span style='width:9px; height:9px; border-radius:50%; background:#e11d48;'></span>{tr('Stop Medico (Infortunio / Out)', 'Out')}</span>"
        f"<span style='display:inline-flex; align-items:center; gap:5px;'><span style='width:9px; height:9px; border-radius:50%; background:#38bdf8;'></span>{tr('Viaggio / Riposo Off', 'Rest/Travel')}</span>"
        f"</div>",
        unsafe_allow_html=True
    )

    # Matrice Calendario (Lun -> Dom)
    primo_giorno_settimana = start_date_mese.weekday()  # 0=Lun, 6=Dom
    giorni_totali_celle = primo_giorno_settimana + num_giorni_mese
    num_settimane = (giorni_totali_celle + 6) // 7

    header_giorni = ["LUN", "MAR", "MER", "GIO", "VEN", "SAB", "DOM"]
    cols_h = st.columns(7)
    for i_h, nome_g in enumerate(header_giorni):
        with cols_h[i_h]:
            st.markdown(
                f"<div style='text-align:center; background:#0f172a; color:#f8fafc; font-size:11px; font-weight:800; padding:6px 0; border-radius:6px; margin-bottom:6px; letter-spacing:0.5px;'>{nome_g}</div>",
                unsafe_allow_html=True
            )

    giorno_cont = 1
    is_en = st.session_state.get('lang', 'IT') == 'EN'

    for sett in range(num_settimane):
        cols_sett = st.columns(7)
        for g_sett in range(7):
            idx_cella = sett * 7 + g_sett
            with cols_sett[g_sett]:
                if idx_cella < primo_giorno_settimana or giorno_cont > num_giorni_mese:
                    # Cella vuota fuori mese
                    st.markdown("<div style='background:rgba(241,245,249,0.5); border:1px dashed #e2e8f0; border-radius:8px; min-height:105px; margin-bottom:6px;'></div>", unsafe_allow_html=True)
                else:
                    d_obj = datetime.date(anno_corrente, mese_corrente, giorno_cont)
                    d_key = d_obj.strftime("%Y-%m-%d")
                    d_info = master_calendar.get(d_key, {})
                    
                    st_col = STATUS_COLORS.get(d_info.get('status_operativo', 'DISPONIBILE'), '#334155')
                    is_today = (d_obj == today)

                    # Micro-Badge Dati
                    badges_list = []
                    if d_info.get('gps_presente'):
                        tl_val = int(round(d_info.get('training_load_gps', 0)))
                        tag_m = " MATCH" if d_info.get('is_match') else ""
                        badges_list.append(
                            f"<div style='background:rgba(14,165,233,0.1); color:#0284c7; border:1px solid rgba(14,165,233,0.3); font-size:9.5px; font-weight:700; padding:1px 4px; border-radius:4px; margin-bottom:2px; display:flex; align-items:center; gap:3px;'>"
                            f"<i class='bi bi-broadcast'></i> TL {tl_val}{tag_m}</div>"
                        )
                    
                    if d_info.get('srpe_presente'):
                        srpe_val = int(round(d_info.get('srpe_carico', 0)))
                        tag_no_gps = " (NO-GPS)" if d_info.get('solo_carico_interno') else ""
                        badges_list.append(
                            f"<div style='background:rgba(249,115,22,0.1); color:#c2410c; border:1px solid rgba(249,115,22,0.3); font-size:9.5px; font-weight:700; padding:1px 4px; border-radius:4px; margin-bottom:2px; display:flex; align-items:center; gap:3px;'>"
                            f"<i class='bi bi-fire'></i> RPE {srpe_val}{tag_no_gps}</div>"
                        )

                    # Micro-badge Palestra & Prep. Fisica
                    gym_slots_cell = [sl for sl in d_info.get('srpe_slots', []) if sl.get('tipo') in ('Gym', 'Preparazione Fisica')]
                    if gym_slots_cell:
                        tot_gym_au_cell = sum(sl.get('carico', 0) for sl in gym_slots_cell)
                        badges_list.append(
                            f"<div style='background:rgba(234,179,8,0.12); color:#a16207; border:1px solid rgba(234,179,8,0.35); font-size:9.5px; font-weight:700; padding:1px 4px; border-radius:4px; margin-bottom:2px; display:flex; align-items:center; gap:3px;'>"
                            f"<i class='bi bi-layers-half'></i> GYM {int(round(tot_gym_au_cell))} AU</div>"
                        )

                    if d_info.get('wellness_presente') and d_info.get('wellness_score') is not None:
                        w_sc = d_info.get('wellness_score')
                        w_doms = d_info.get('wellness_dettagli', {}).get('doms', 0)
                        w_col = "#e11d48" if w_doms >= 7 else ("#f59e0b" if w_doms >= 5 else "#10b981")
                        badges_list.append(
                            f"<div style='background:rgba(168,85,247,0.1); color:{w_col}; border:1px solid rgba(168,85,247,0.3); font-size:9.5px; font-weight:700; padding:1px 4px; border-radius:4px; margin-bottom:2px; display:flex; align-items:center; gap:3px;'>"
                            f"<i class='bi bi-heart-pulse'></i> W: {w_sc:.1f}</div>"
                        )

                    if d_info.get('test_count', 0) > 0:
                        n_t = d_info.get('test_count')
                        badges_list.append(
                            f"<div style='background:rgba(2,132,199,0.1); color:#0369a1; border:1px solid rgba(2,132,199,0.3); font-size:9.5px; font-weight:700; padding:1px 4px; border-radius:4px; margin-bottom:2px; display:flex; align-items:center; gap:3px;'>"
                            f"<i class='bi bi-clipboard2-data'></i> {n_t} Test</div>"
                        )

                    # Eventi Medico / Fisio
                    if d_info.get('has_infortunio'):
                        badges_list.append(
                            f"<div style='background:rgba(225,29,72,0.12); color:#be123c; border:1px solid rgba(225,29,72,0.4); font-size:9px; font-weight:800; padding:1px 4px; border-radius:4px; margin-bottom:2px;'>"
                            f"<i class='bi bi-x-octagon' style='margin-right:2px;'></i>STOP MEDICO</div>"
                        )
                    elif d_info.get('has_sovraccarico') or d_info.get('status_operativo') == 'LIMITATO':
                        badges_list.append(
                            f"<div style='background:rgba(245,158,11,0.12); color:#b45309; border:1px solid rgba(245,158,11,0.4); font-size:9px; font-weight:800; padding:1px 4px; border-radius:4px; margin-bottom:2px;'>"
                            f"<i class='bi bi-exclamation-triangle' style='margin-right:2px;'></i>LIMITATO</div>"
                        )
                    elif d_info.get('has_logistica'):
                        lbl_v = tr("VIAGGIO/OFF", "TRAVEL/OFF")
                        badges_list.append(
                            f"<div style='background:rgba(56,189,248,0.12); color:#0284c7; border:1px solid rgba(56,189,248,0.4); font-size:9px; font-weight:800; padding:1px 4px; border-radius:4px; margin-bottom:2px;'>"
                            f"<i class='bi bi-airplane' style='margin-right:2px;'></i>{lbl_v}</div>"
                        )

                    # Alert violazione limite 70% TL in giorno a Carico Adattato
                    if d_info.get('overload_adattato'):
                        pct_m = d_info.get('pct_su_media_tl', 0)
                        lbl_tl = tr(f"TL >70% MEDIA ({pct_m:.0f}%)", f"TL >70% MEAN ({pct_m:.0f}%)")
                        badges_list.append(
                            f"<div style='background:rgba(225,29,72,0.18); color:#be123c; border:1px solid rgba(225,29,72,0.5); font-size:8.5px; font-weight:800; padding:1px 3px; border-radius:4px; margin-bottom:2px;'>"
                            f"<i class='bi bi-exclamation-octagon-fill' style='margin-right:2px;'></i>{lbl_tl}</div>"
                        )

                    if d_info.get('has_trattamento'):
                        lbl_f = tr("FISIO", "PHYSIO")
                        badges_list.append(
                            f"<div style='background:rgba(16,185,129,0.12); color:#047857; border:1px solid rgba(16,185,129,0.4); font-size:9px; font-weight:800; padding:1px 4px; border-radius:4px; margin-bottom:2px;'>"
                            f"<i class='bi bi-bandaid' style='margin-right:2px;'></i>{lbl_f}</div>"
                        )

                    border_today = "box-shadow: 0 0 0 2px #0ea5e9;" if is_today else ""
                    empty_d_lbl = tr("Riposo / Nessun dato", "Rest / No data")
                    html_badges = "".join(badges_list) if badges_list else f"<div style='color:#94a3b8; font-size:9px; font-style:italic;'>{empty_d_lbl}</div>"

                    # Tooltip ricco al passaggio del mouse
                    tooltip_html = _build_day_tooltip_html(d_key, d_info, st_col, is_en, g_sett)

                    st.markdown(
                        f"<div class='m0v3-day-card' style='border-top:4px solid {st_col}; {border_today}'>"
                        f"<div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;'>"
                        f"<span style='font-size:12px; font-weight:900; color:#0f172a;'>{giorno_cont}</span>"
                        f"<span style='width:7px; height:7px; border-radius:50%; background:{st_col};'></span>"
                        f"</div>"
                        f"{html_badges}"
                        f"{tooltip_html}"
                        f"</div>",
                        unsafe_allow_html=True
                    )
                    giorno_cont += 1

    st.markdown("<hr style='margin:20px 0;'>", unsafe_allow_html=True)

    # ---------------------------------------------------------------------
    # SEZIONE B: DAY INSPECTOR (Ispeziona e Gestisci al Volo)
    # ---------------------------------------------------------------------
    st.markdown(
        f"<div style='display:flex; align-items:center; gap:8px; margin-bottom:12px;'>"
        f"<i class='bi bi-search' style='color:#0ea5e9; font-size:18px;'></i>"
        f"<span style='font-size:16px; font-weight:800; color:#0f172a; text-transform:uppercase; letter-spacing:0.5px;'>"
        f"{tr('Day Inspector — Ispezione Dettagliata Giorno', 'Day Inspector — Daily In-Depth Breakdown')}"
        f"</span></div>",
        unsafe_allow_html=True
    )

    lista_giorni_str = [f"{anno_corrente}-{mese_corrente:02d}-{g:02d}" for g in range(1, num_giorni_mese + 1)]
    def_idx_day = (today.day - 1) if (today.year == anno_corrente and today.month == mese_corrente) else (num_giorni_mese - 1)
    if def_idx_day >= len(lista_giorni_str):
        def_idx_day = 0

    c_insp_sel, _ = st.columns([2.5, 4.5])
    with c_insp_sel:
        if 'cal_inspector_day' in st.session_state and st.session_state['cal_inspector_day'] not in lista_giorni_str:
            st.session_state['cal_inspector_day'] = lista_giorni_str[def_idx_day]
        giorno_insp = st.selectbox(
            tr("Seleziona Giorno da Ispezionare:", "Select Day to Inspect:"),
            lista_giorni_str,
            index=def_idx_day,
            key="cal_inspector_day"
        )

    day_data = master_calendar.get(giorno_insp, {})
    st_day_col = STATUS_COLORS.get(day_data.get('status_operativo', 'DISPONIBILE'), '#334155')
    st_day_lbl = STATUS_LABELS.get(day_data.get('status_operativo', 'DISPONIBILE'), ('Disponibile', 'Available'))

    # Banner Sintesi Giorno
    st.markdown(
        f"<div style='background:#ffffff; border:1px solid #cbd5e1; border-left:6px solid {st_day_col}; border-radius:10px; padding:12px 18px; margin-bottom:14px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; font-family:\"Inter\",sans-serif;'>"
        f"<div>"
        f"<span style='font-size:16px; font-weight:900; color:#0f172a; margin-right:12px;'>DATA: {giorno_insp}</span>"
        f"<span style='background:rgba(15,23,42,0.06); color:#0f172a; font-weight:700; font-size:12px; padding:3px 10px; border-radius:6px;'>"
        f"ATLETA: {atleta_sel}</span>"
        f"</div>"
        f"<div>"
        f"<span style='display:inline-flex; align-items:center; gap:6px; background:#f8fafc; border:1px solid #cbd5e1; padding:4px 12px; border-radius:999px; font-weight:800; font-size:12px; color:{st_day_col};'>"
        f"<span style='width:8px; height:8px; border-radius:50%; background:{st_day_col};'></span>{st_day_lbl[0]}</span>"
        f"</div>"
        f"</div>",
        unsafe_allow_html=True
    )

    col_ins1, col_ins2, col_ins3 = st.columns(3)

    # Colonna 1: Carichi Esterni & Interni
    with col_ins1:
        with st.container(border=True):
            st.markdown(
                f"<div style='font-size:12.5px; font-weight:800; color:#0f172a; text-transform:uppercase; letter-spacing:0.5px; margin-bottom:12px; display:flex; align-items:center; gap:6px;'>"
                f"<i class='bi bi-lightning-charge' style='color:#0ea5e9; font-size:15px;'></i>Carichi di Lavoro (GPS & sRPE)</div>",
                unsafe_allow_html=True
            )
            if day_data.get('gps_presente'):
                st.markdown(
                    f"<div style='font-size:12px; color:#334155; margin-bottom:8px; line-height:1.6;'>"
                    f"<b>GPS Training Load:</b> <span style='color:#0284c7; font-weight:800;'>{day_data.get('training_load_gps', 0):.0f} AU</span><br>"
                    f"<b>Minuti Tracciati:</b> {day_data.get('minuti_gps', 0):.0f} min<br>"
                    f"<b>TL High Intensity:</b> {day_data.get('tl_high_gps', 0):.0f} AU<br>"
                    f"<b>Accelerazioni / Decel:</b> {day_data.get('high_accel_imu', 0):.0f} / {day_data.get('high_decel_imu', 0):.0f}<br>"
                    f"<b>Ambiente:</b> {', '.join(set(day_data.get('gps_ambienti', ['Outdoor'])))}</div>",
                    unsafe_allow_html=True
                )
            else:
                st.markdown(f"<div style='font-size:11.5px; color:#64748b; font-style:italic; margin-bottom:8px;'>{tr('Nessun dato GPS satellitare registrato.', 'No GPS satellite data recorded.')}</div>", unsafe_allow_html=True)

            # Alert Superamento Soglia 70% Training Load in Carico Adattato
            if day_data.get('overload_adattato'):
                tl_val_ov = day_data.get('training_load_gps', 0)
                soglia_ov = day_data.get('soglia_70_adattato', 0)
                pct_ov = day_data.get('pct_su_media_tl', 0)
                att_lbl = tr("Attenzione:", "Warning:")
                msg_ov = tr(
                    f"In questa giornata a Carico Adattato, il Training Load (<b>{tl_val_ov:.0f} AU</b>) ha superato il limite prudenziale del 70% della media storica dell'atleta (Soglia: <b>{soglia_ov:.0f} AU</b> — Raggiunto il <b>{pct_ov:.0f}%</b> della media).",
                    f"On this Adapted Load day, Training Load (<b>{tl_val_ov:.0f} AU</b>) exceeded the 70% threshold of the athlete's historical mean (Threshold: <b>{soglia_ov:.0f} AU</b> — Reached <b>{pct_ov:.0f}%</b> of mean)."
                )
                st.markdown(
                    f"<div style='background:#fef2f2; border:1px solid #fecaca; border-left:4px solid #ef4444; border-radius:6px; padding:8px 10px; margin-top:8px; margin-bottom:8px; font-size:11.5px; color:#991b1b; line-height:1.4;'>"
                    f"<i class='bi bi-exclamation-triangle-fill' style='margin-right:5px; color:#ef4444;'></i>"
                    f"<b>{att_lbl}</b> {msg_ov}"
                    f"</div>",
                    unsafe_allow_html=True
                )

            if day_data.get('srpe_presente'):
                lbl_solo_ci = tr("SOLO CARICO INTERNO (NO GPS)", "INTERNAL LOAD ONLY (NO GPS)")
                tag_no_gps = f"<span style='background:#fee2e2; color:#b91c1c; font-size:10px; font-weight:800; padding:1px 5px; border-radius:4px; margin-left:4px;'>{lbl_solo_ci}</span>" if day_data.get('solo_carico_interno') else ""
                st.markdown(f"<div style='font-size:12px; color:#334155; margin-top:8px; margin-bottom:4px;'><b>{tr('Carico sRPE Totale:', 'Total sRPE Load:')}</b> <span style='color:#c2410c; font-weight:800;'>{day_data.get('srpe_carico', 0):.0f} AU</span> {tag_no_gps}</div>", unsafe_allow_html=True)
                for slot in day_data.get('srpe_slots', []):
                    st.markdown(f"<div style='font-size:11.5px; color:#475569; margin-left:6px; margin-bottom:2px;'>• <b>Slot {slot['slot']}</b> ({slot['tipo']}): {slot['minuti']:.0f}m @ RPE {slot['rpe']:.0f} (<span style='color:#c2410c; font-weight:700;'>{slot['carico']:.0f} AU</span>)</div>", unsafe_allow_html=True)

                # Ponte verso Generatore Dati per stimare carico GPS mancante
                if day_data.get('solo_carico_interno'):
                    btn_bridge_txt = tr("Stima Carico GPS nel Generatore", "Estimate GPS Load in Generator")
                    st.markdown(
                        f"<div style='margin-top:6px; margin-bottom:4px; font-size:11px; color:#64748b;'>"
                        f"<i class='bi bi-sliders' style='color:#0284c7; margin-right:4px;'></i>"
                        f"{tr('Sessione priva di tracciamento GPS. Vuoi stimare i dati cinematici?', 'Session lacks GPS tracking. Estimate kinematic metrics in Generator?')}</div>",
                        unsafe_allow_html=True
                    )
                    if st.button(btn_bridge_txt, key=f"btn_bridge_nogps_{giorno_insp}", type="secondary", use_container_width=True):
                        st.session_state['gen_prefill_atleta'] = atleta_sel
                        st.session_state['gen_prefill_data'] = day_data['date_obj']
                        tennis_min = sum(s['minuti'] for s in day_data.get('srpe_slots', []) if 'tennis' in str(s.get('tipo', '')).lower())
                        st.session_state['gen_prefill_minuti'] = int(tennis_min if tennis_min > 0 else (day_data.get('srpe_minuti') or 60))
                        st.session_state['active_page'] = tr("Generatore Dati", "Data Generator")
                        st.rerun()

            if day_data.get('test_count', 0) > 0:
                lbl_test_sv = tr(f"Test Fisici Svolti ({day_data['test_count']}):", f"Physical Tests Done ({day_data['test_count']}):")
                st.markdown(f"<div style='margin-top:10px; font-size:12px; color:#0369a1;'><b>{lbl_test_sv}</b><br>" + "<br>".join([f"• {t_n}" for t_n in day_data['test_presenti']]) + "</div>", unsafe_allow_html=True)

    # Colonna 2: Stato Biologico & Wellness
    with col_ins2:
        with st.container(border=True):
            st.markdown(
                f"<div style='font-size:12.5px; font-weight:800; color:#0f172a; text-transform:uppercase; letter-spacing:0.5px; margin-bottom:12px; display:flex; align-items:center; gap:6px;'>"
                f"<i class='bi bi-heart-pulse' style='color:#a855f7; font-size:15px;'></i>{tr('Stato Biologico & Wellness', 'Biological State & Wellness')}</div>",
                unsafe_allow_html=True
            )
            if day_data.get('wellness_presente') and day_data.get('wellness_dettagli'):
                w_d = day_data['wellness_dettagli']
                w_sc = day_data.get('wellness_score', 0)
                st.markdown(f"<div style='font-size:13px; font-weight:800; color:#0f172a; margin-bottom:10px;'>Readiness Score: <span style='color:#0284c7;'>{w_sc:.1f} / 10</span></div>", unsafe_allow_html=True)
                
                params = [
                    (tr("Qualità Sonno", "Sleep Quality"), w_d.get('sonno', 0), "#0ea5e9"),
                    (tr("Livello Fatica", "Fatigue Level"), w_d.get('fatica', 0), "#f59e0b" if w_d.get('fatica', 0) >= 6 else "#10b981"),
                    (tr("Indice Stress", "Stress Level"), w_d.get('stress', 0), "#f59e0b" if w_d.get('stress', 0) >= 6 else "#10b981"),
                    (tr("Umore / Motivazione", "Mood / Motivation"), w_d.get('umore', 0), "#0ea5e9"),
                    (tr("DOMS / Dolori Muscolari", "DOMS / Soreness"), w_d.get('doms', 0), "#e11d48" if w_d.get('doms', 0) >= 6 else "#10b981")
                ]
                for p_n, p_v, p_c in params:
                    pct_w = min(max((p_v / 10.0) * 100, 0), 100)
                    st.markdown(
                        f"<div style='font-size:11px; color:#475569; display:flex; justify-content:space-between; margin-bottom:2px;'>"
                        f"<span>{p_n}</span><b>{p_v:.1f}/10</b></div>"
                        f"<div style='background:#f1f5f9; height:6px; border-radius:3px; margin-bottom:7px; overflow:hidden;'>"
                        f"<div style='width:{pct_w}%; background:{p_c}; height:100%; border-radius:3px;'></div></div>",
                        unsafe_allow_html=True
                    )
                if day_data.get('wellness_alerts'):
                    st.markdown("<div style='margin-top:6px; font-size:11px; font-weight:700; color:#b91c1c;'>" + "<br>".join([f"<i class='bi bi-exclamation-triangle'></i> {a}" for a in day_data['wellness_alerts']]) + "</div>", unsafe_allow_html=True)
            else:
                st.markdown(f"<div style='font-size:11.5px; color:#64748b; font-style:italic;'>{tr('Nessun questionario wellness compilato in questa data.', 'No wellness survey completed on this date.')}</div>", unsafe_allow_html=True)

    # Colonna 3: Diario Medico, Fisio & Logistica
    with col_ins3:
        with st.container(border=True):
            st.markdown(
                f"<div style='font-size:12.5px; font-weight:800; color:#0f172a; text-transform:uppercase; letter-spacing:0.5px; margin-bottom:12px; display:flex; align-items:center; gap:6px;'>"
                f"<i class='bi bi-journal-medical' style='color:#e11d48; font-size:15px;'></i>{tr('Diario Clinico & Fisioterapico', 'Clinical & Physio Log')}</div>",
                unsafe_allow_html=True
            )
            eventi_giorno = day_data.get('medico_eventi', [])
            if eventi_giorno:
                for ev in eventi_giorno:
                    t_ev = ev.get('tipo_scheda', 'EVENTO')
                    st_ev = ev.get('status_operativo', 'DISPONIBILE')
                    distr = ev.get('distretto_anatomico', 'Sistemico')
                    vas = ev.get('scala_dolore_vas')
                    vas_str = f" · VAS {vas}/10" if vas is not None else ""
                    ind_staff = ev.get('indicazioni_staff')
                    note_clin = ev.get('note_cliniche_dettaglio')
                    ind_html = f"<div style='color:#0f172a; margin-top:4px; font-weight:600;'><b>{tr('Indicazioni Staff:', 'Staff Directions:')}</b> {ind_staff}</div>" if ind_staff else ""
                    note_html = f"<div style='color:#475569; margin-top:2px;'><b>{tr('Note:', 'Notes:')}</b> {note_clin}</div>" if note_clin else ""
                    st.markdown(
                        f"<div style='background:#f8fafc; border:1px solid #cbd5e1; border-left:4px solid {STATUS_COLORS.get(st_ev, '#334155')}; border-radius:6px; padding:8px 10px; margin-bottom:6px; font-size:11.5px;'>"
                        f"<b>[{t_ev}]</b> {distr}{vas_str}<br>"
                        f"<span style='color:#64748b; font-size:11px;'>{ev.get('sottotipo_evento', '')}</span>"
                        f"{ind_html}"
                        f"{note_html}"
                        f"</div>",
                        unsafe_allow_html=True
                    )
                    if ev.get('tipo_scheda') in ('TRATTAMENTO', 'SOVRACCARICO'):
                        ev_id_s = str(ev.get('id', 'ev'))[:8]
                        with st.popover(tr("Duplica / Ripeti Trattamento", "Duplicate / Repeat")):
                            st.caption(f"{tr('Duplica per', 'Duplicate for')} **{atleta_sel}**:")
                            d_target_insp = st.date_input(tr("Data Ripetizione:", "Target Date:"), value=today, key=f"dup_d_insp_{ev_id_s}_{giorno_insp}")
                            if st.button(tr("Conferma Duplicazione", "Confirm Duplicate"), key=f"btn_dup_insp_{ev_id_s}_{giorno_insp}", type="primary", use_container_width=True):
                                new_pay = dict(ev)
                                new_pay.pop('id', None)
                                new_pay['data_inizio'] = str(d_target_insp)
                                new_pay['data_fine'] = str(d_target_insp)
                                new_pay['atleta_id'] = atleta_id_sel if not str(atleta_id_sel).startswith("mock-") else None
                                new_pay['nome_giocatore'] = atleta_sel
                                if str(atleta_id_sel).startswith("mock-"):
                                    if 'mock_registro_medico' not in st.session_state:
                                         st.session_state['mock_registro_medico'] = []
                                    new_pay['id'] = f"mock-reg-{len(st.session_state['mock_registro_medico']) + 1}"
                                    st.session_state['mock_registro_medico'].insert(0, new_pay)
                                    st.success(f"{tr('Trattamento duplicato per il', 'Treatment duplicated for')} {d_target_insp}!")
                                    st.rerun()
                                else:
                                    succ_d, res_db_d = upsert_registro_medico(new_pay)
                                    if succ_d:
                                        st.success(f"{tr('Trattamento duplicato per il', 'Treatment duplicated for')} {d_target_insp}!")
                                        st.rerun()
                                    else:
                                        st.error(f"{tr('Errore', 'Error')}: {res_db_d}")
            else:
                st.markdown(f"<div style='font-size:11.5px; color:#64748b; font-style:italic;'>{tr('Nessuna segnalazione medica o trattamento registrato per questa data.', 'No medical log or treatment recorded for this date.')}</div>", unsafe_allow_html=True)

# =========================================================================
# TAB 2: INSERIMENTO & GESTIONE REGISTRO CLINICO / FISIO
# =========================================================================



def render_correlazione_clinica(t, atleta_sel=None, atleta_id_sel=None, key_prefix="ci_corr"):
    """
    Renders the Longitudinal Correlation between Training Loads and Clinical/Medical Events (Crossing Analysis).
    """
    user_role = st.session_state.get('role', 'Atleta')
    is_admin = (user_role in ['Super-Admin', 'Admin'])
    is_coach = (user_role in ['Staff', 'Coach', 'Fisio / Medico'] or is_admin)
    user = st.session_state.get('user')

    dict_atleti = _get_atleti_dict(user, is_admin, is_coach)
    atleta_nomi = list(dict_atleti.keys())

    if not atleta_sel:
        glob_ath = st.session_state.get('selected_athlete')
        if glob_ath in atleta_nomi:
            atleta_sel = glob_ath
        else:
            atleta_sel = atleta_nomi[0] if atleta_nomi else "prova uno"

    if not atleta_id_sel:
        atleta_id_sel = dict_atleti.get(atleta_sel, f"mock-{atleta_sel}")

    today = datetime.date.today()
    mese_corrente = today.month
    anno_corrente = today.year
    nomi_mesi_it = ["Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno", "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"]
    nomi_mesi_en = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
    nome_mese_str = tr(nomi_mesi_it[mese_corrente - 1], nomi_mesi_en[mese_corrente - 1])

    _, num_giorni_mese = calendar.monthrange(anno_corrente, mese_corrente)
    start_date_mese = datetime.date(anno_corrente, mese_corrente, 1)
    end_date_mese = datetime.date(anno_corrente, mese_corrente, num_giorni_mese)

    master_calendar = get_athlete_master_calendar(atleta_sel, atleta_id_sel, start_date_mese, end_date_mese)

    st.markdown(
        f"<div style='display:flex; align-items:center; gap:8px; margin-bottom:12px;'>"
        f"<i class='bi bi-graph-up-arrow' style='color:#0ea5e9; font-size:18px;'></i>"
        f"<span style='font-size:16px; font-weight:800; color:#0f172a; text-transform:uppercase; letter-spacing:0.5px;'>"
        f"{tr('Correlazione Longitudinale Carichi vs Eventi Clinici', 'Longitudinal Correlation: Loads vs Clinical Events')}"
        f"</span></div>",
        unsafe_allow_html=True
    )

    c_rng1, c_rng2 = st.columns([2.5, 3.5])
    with c_rng1:
        opz_finestre = [
            f"{tr('Mese Calendario:', 'Calendar Month:')} {nome_mese_str} {anno_corrente}",
            tr("Ultimi 30 Giorni", "Last 30 Days"),
            tr("Ultimi 60 Giorni", "Last 60 Days"),
            tr("Ultimi 90 Giorni", "Last 90 Days")
        ]
        finestra_giorni = st.selectbox(
            tr("Finestra Temporale di Analisi:", "Time Horizon:"),
            opz_finestre,
            index=0,
            key=f"{key_prefix}_window"
        )
    with c_rng2:
        opz_lente = [tr("Tutti i Distretti / Catene (Vista Globale)", "All Districts / Chains (Global View)")] + [c[0] for c in DISTRETTI_CATENE_CINETICHE]
        lente_sel = st.selectbox(
            tr("Lente Clinica (Focus Catena Cinetica):", "Clinical Lens (Kinetic Chain Focus):"),
            opz_lente,
            index=0,
            key=f"{key_prefix}_lente"
        )
    
    if "Mese" in finestra_giorni:
        corr_start = start_date_mese
        corr_end = end_date_mese
        corr_calendar = master_calendar
    else:
        if "30" in finestra_giorni:
            corr_start = today - datetime.timedelta(days=30)
            corr_end = today
        elif "90" in finestra_giorni:
            corr_start = today - datetime.timedelta(days=90)
            corr_end = today
        else:
            corr_start = today - datetime.timedelta(days=60)
            corr_end = today

        # Master Calendar esteso sul range
        corr_calendar = get_athlete_master_calendar(atleta_sel, atleta_id_sel, corr_start, corr_end)

    date_list = sorted(list(corr_calendar.keys()))
    dates_dt = [datetime.datetime.strptime(d, "%Y-%m-%d").date() for d in date_list]
    tl_gps_list = [corr_calendar[d]['training_load_gps'] for d in date_list]
    
    # Carico Tennis sRPE (AU)
    tennis_srpe_list = []
    for d in date_list:
        t_load = sum(sl.get('carico', 0) for sl in corr_calendar[d].get('srpe_slots', []) if sl.get('tipo') == 'Tennis')
        tennis_srpe_list.append(t_load)

    wellness_list = [corr_calendar[d]['wellness_score'] if corr_calendar[d]['wellness_score'] is not None else np.nan for d in date_list]

    # Estrazione dati Palestra & Preparazione Fisica (70/30 Split)
    gym_prim_list = []
    gym_sec_list = []
    gym_tot_list = []
    gym_prim_colors = []
    gym_sec_colors = []
    gym_opacities = []
    gym_labels = []
    gym_customdata = []

    for idx_d, d_str in enumerate(date_list):
        d_val = corr_calendar[d_str]
        gym_slots = [sl for sl in d_val.get('srpe_slots', []) if sl.get('tipo') in ('Gym', 'Preparazione Fisica')]
        if not gym_slots:
            gym_prim_list.append(0.0)
            gym_sec_list.append(0.0)
            gym_tot_list.append(0.0)
            gym_prim_colors.append('#0284c7')
            gym_sec_colors.append('#38bdf8')
            gym_opacities.append(0.85)
            gym_labels.append("")
            gym_customdata.append(["-", "-", "-", "-", "-"])
        else:
            c_p_sum = sum(sl.get('carico_primario', sl.get('carico', 0)) for sl in gym_slots)
            c_s_sum = sum(sl.get('carico_secondario', 0) for sl in gym_slots)
            tot_g = c_p_sum + c_s_sum
            gym_prim_list.append(c_p_sum)
            gym_sec_list.append(c_s_sum)
            gym_tot_list.append(tot_g)

            first_sl = gym_slots[0]
            stim_1 = first_sl.get('stimolo_primario') or 'Forza Massimale / Sub-Massimale'
            dist_1 = first_sl.get('distretto_primario') or 'Total Body / Sistemico Globale'
            stim_2 = first_sl.get('stimolo_secondario') or '-'
            dist_2 = first_sl.get('distretto_secondario') or '-'
            stress_e = first_sl.get('stress_eccentrico_atteso', 'Moderato')

            gym_prim_colors.append(get_stimolo_color(stim_1, is_secondary=False))
            gym_sec_colors.append(get_stimolo_color(stim_2, is_secondary=True) if stim_2 != '-' else '#94a3b8')
            gym_customdata.append([stim_1, dist_1, stim_2, dist_2, stress_e])

            # Lente Clinica: Opacità selettiva
            if lente_sel != opz_lente[0]:
                distretti_target = get_catena_clinici(lente_sel) + [lente_sel]
                matches = any(
                    (sl.get('distretto_primario') == lente_sel or 
                     sl.get('distretto_secondario') == lente_sel or
                     any(dt in str(sl.get('distretto_primario', '')) for dt in distretti_target))
                    for sl in gym_slots
                )
                gym_opacities.append(1.0 if matches else 0.20)
            else:
                gym_opacities.append(0.88)

            # Alert DOMS: controlla giorno corrente o giorno successivo (T+1)
            doms_oggi = d_val.get('wellness_dettagli', {}).get('doms', 0)
            doms_domani = 0
            if idx_d + 1 < len(date_list):
                d_next_str = date_list[idx_d + 1]
                doms_domani = corr_calendar[d_next_str].get('wellness_dettagli', {}).get('doms', 0)

            has_doms_alert = (doms_oggi >= 6 or doms_domani >= 6)
            if tot_g > 0:
                doms_tag = " [! DOMS]" if has_doms_alert else ""
                gym_labels.append(f"{tot_g:.0f} AU{doms_tag}")
            else:
                gym_labels.append("")

    # Range assi Y
    max_load_val = max(max(tl_gps_list + [0]), max(tennis_srpe_list + [0]))
    y1_max = max(max_load_val * 1.25, 1200)

    max_gym_v = max(gym_tot_list + [0])
    y2_max = max(max_gym_v * 1.32, 450)

    # Barra Legenda Integrata M0V3
    st.markdown(
        f"<div style='display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px; background:#f8fafc; border:1px solid #e2e8f0; border-radius:10px; padding:10px 16px; margin-bottom:12px; font-family:\"Inter\",sans-serif; font-size:11.5px;'>"
        f"<div style='display:flex; align-items:center; gap:14px; flex-wrap:wrap;'>"
        f"<span style='font-weight:800; color:#0f172a; text-transform:uppercase; font-size:11px; letter-spacing:0.5px;'><i class='bi bi-activity' style='color:#0ea5e9; margin-right:4px;'></i>{tr('Metriche:', 'Metrics:')}</span>"
        f"<span style='display:inline-flex; align-items:center; gap:5px; font-weight:700; color:#334155;'><span style='width:11px; height:11px; border-radius:3px; background:#0ea5e9;'></span>Training Load GPS</span>"
        f"<span style='display:inline-flex; align-items:center; gap:5px; font-weight:700; color:#334155;'><span style='width:11px; height:11px; border-radius:3px; background:#f97316;'></span>sRPE Tennis (AU)</span>"
        f"<span style='display:inline-flex; align-items:center; gap:5px; font-weight:700; color:#334155;'><span style='width:11px; height:11px; border-radius:3px; background:#0284c7;'></span>Gym (70% Primario)</span>"
        f"<span style='display:inline-flex; align-items:center; gap:5px; font-weight:700; color:#334155;'><span style='width:11px; height:11px; border-radius:3px; background:#38bdf8;'></span>Gym (30% Compl.)</span>"
        f"<span style='display:inline-flex; align-items:center; gap:5px; font-weight:700; color:#334155;'><span style='width:14px; height:3px; border-radius:2px; background:#a855f7;'></span>Wellness Score</span>"
        f"<span style='display:inline-flex; align-items:center; gap:5px; font-weight:700; color:#334155;'><i class='bi bi-plus-lg' style='color:#10b981; font-weight:900;'></i>Seduta Fisio</span>"
        f"</div>"
        f"<div style='display:flex; align-items:center; gap:12px; flex-wrap:wrap;'>"
        f"<span style='font-weight:800; color:#0f172a; text-transform:uppercase; font-size:11px; letter-spacing:0.5px;'>{tr('Bande Cliniche:', 'Clinical Zones:')}</span>"
        f"<span style='display:inline-flex; align-items:center; gap:5px; font-weight:700; color:#475569;'><span style='width:11px; height:11px; border-radius:3px; background:rgba(225,29,72,0.2); border:1px solid #e11d48;'></span>Stop Medico</span>"
        f"<span style='display:inline-flex; align-items:center; gap:5px; font-weight:700; color:#475569;'><span style='width:11px; height:11px; border-radius:3px; background:rgba(245,158,11,0.2); border:1px solid #f59e0b;'></span>Carico Adattato</span>"
        f"<span style='display:inline-flex; align-items:center; gap:5px; font-weight:700; color:#475569;'><span style='width:11px; height:11px; border-radius:3px; background:rgba(56,189,248,0.2); border:1px solid #38bdf8;'></span>Viaggio / Off</span>"
        f"</div>"
        f"</div>",
        unsafe_allow_html=True
    )

    # Inizializzazione Subplots a Doppia Corsia Sincronizzata
    t_lane1 = tr("Corsia Superiore: Carico Esterno GPS, sRPE Tennis & Readiness Clinica", "Upper Lane: GPS External Load, Tennis sRPE & Clinical Readiness")
    t_lane2 = tr("Corsia Inferiore: Carico Extra-Campo (Palestra & Prep. Fisica — 70/30 Split)", "Lower Lane: Extra-Court Load (Gym & Conditioning — 70/30 Split)")
    fig_corr = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        row_heights=[0.60, 0.40],
        vertical_spacing=0.10,
        specs=[[{"secondary_y": True}], [{"secondary_y": False}]],
        subplot_titles=(t_lane1, t_lane2)
    )

    # --- ROW 1: CARICO ESTERNO (GPS) & TENNIS sRPE ---
    fig_corr.add_trace(go.Bar(
        x=dates_dt,
        y=tl_gps_list,
        name="Training Load GPS",
        marker=dict(color="#0ea5e9", opacity=0.88, cornerradius=3),
        offsetgroup=1,
        text=[f"{v:.0f}" if v > 0 else "" for v in tl_gps_list],
        textposition="outside",
        textfont=dict(size=9, color="#0284c7", family="Inter"),
        hovertemplate="<b>%{x|%d %b %Y}</b><br>Training Load GPS: <b>%{y:.0f} AU</b><extra></extra>"
    ), row=1, col=1, secondary_y=False)

    fig_corr.add_trace(go.Bar(
        x=dates_dt,
        y=tennis_srpe_list,
        name="sRPE Tennis (AU)",
        marker=dict(color="#f97316", opacity=0.85, cornerradius=3),
        offsetgroup=2,
        text=[f"{v:.0f}" if v > 0 else "" for v in tennis_srpe_list],
        textposition="outside",
        textfont=dict(size=9, color="#c2410c", family="Inter"),
        hovertemplate="<b>%{x|%d %b %Y}</b><br>sRPE Tennis: <b>%{y:.0f} AU</b><extra></extra>"
    ), row=1, col=1, secondary_y=False)

    fig_corr.add_trace(go.Scatter(
        x=dates_dt,
        y=wellness_list,
        name="Readiness / Wellness Score",
        mode="lines+markers",
        line=dict(color="#a855f7", width=2.8),
        marker=dict(size=6, color="#7e22ce", line=dict(color="#ffffff", width=1.5)),
        hovertemplate="<b>%{x|%d %b %Y}</b><br>Readiness Score: <b>%{y:.1f} / 10</b><extra></extra>"
    ), row=1, col=1, secondary_y=True)

    # Soglia Carico Adattato (70% Media TL)
    soglia_70_val = next((d.get('soglia_70_adattato', 0) for d in corr_calendar.values() if d.get('soglia_70_adattato', 0) > 0), 0.0)
    if soglia_70_val > 0:
        ann_soglia = tr(f"Soglia Carico Adattato (70% Media: {soglia_70_val:.0f} AU)", f"Adapted Load Threshold (70% Mean: {soglia_70_val:.0f} AU)")
        fig_corr.add_hline(
            y=soglia_70_val,
            row=1, col=1,
            line=dict(color="#f59e0b", width=1.5, dash="dash"),
            annotation_text=ann_soglia,
            annotation_position="top left",
            annotation_font=dict(size=9.5, color="#b45309", family="Inter")
        )

    # Overload Warning su Carico Adattato
    overload_d_list = [corr_calendar[d]['date_obj'] for d in date_list if corr_calendar[d].get('overload_adattato')]
    overload_tl_list = [corr_calendar[d]['training_load_gps'] for d in date_list if corr_calendar[d].get('overload_adattato')]
    if overload_d_list:
        fig_corr.add_trace(go.Scatter(
            x=overload_d_list,
            y=[tl + (y1_max * 0.04) for tl in overload_tl_list],
            mode="markers",
            name=tr("Warning Overload (>70% Media)", "Warning Overload (>70% Mean)"),
            marker=dict(symbol="triangle-up", size=12, color="#e11d48", line=dict(color="#991b1b", width=1.4)),
            hovertemplate="<b>WARNING OVERLOAD LIMITATO</b><br>%{x}: %{y:.0f} AU<extra></extra>"
        ), row=1, col=1, secondary_y=False)

    # --- FASCIA CLINICA CENTRALE (Bande di Stato) ---
    periods = []
    curr_p = None
    for d_str in date_list:
        st_op = corr_calendar[d_str].get("status_operativo", "DISPONIBILE")
        d_obj = corr_calendar[d_str]["date_obj"]
        if st_op in ("LIMITATO", "INDISPONIBILE", "RIPOSO_VIAGGIO"):
            if curr_p and curr_p["status"] == st_op and (d_obj - curr_p["end_date"]).days == 1:
                curr_p["end_date"] = d_obj
            else:
                if curr_p:
                    periods.append(curr_p)
                curr_p = {"status": st_op, "start_date": d_obj, "end_date": d_obj}
        else:
            if curr_p:
                periods.append(curr_p)
                curr_p = None
    if curr_p:
        periods.append(curr_p)

    for p in periods:
        dt_x0 = datetime.datetime.combine(p['start_date'], datetime.time(0, 0)) - datetime.timedelta(hours=12)
        dt_x1 = datetime.datetime.combine(p['end_date'], datetime.time(0, 0)) + datetime.timedelta(hours=12)
        if p['status'] == 'INDISPONIBILE':
            f_col = "rgba(225, 29, 72, 0.16)"
            l_col = "rgba(225, 29, 72, 0.55)"
        elif p['status'] == 'LIMITATO':
            f_col = "rgba(245, 158, 11, 0.16)"
            l_col = "rgba(217, 119, 6, 0.55)"
        else:
            f_col = "rgba(56, 189, 248, 0.14)"
            l_col = "rgba(14, 165, 233, 0.55)"
        fig_corr.add_vrect(
            x0=dt_x0, x1=dt_x1, fillcolor=f_col, layer="below",
            line=dict(color=l_col, width=1.2, dash="dot"),
            row="all"
        )

    # Marker Trattamenti Fisioterapici su Row 1
    date_trattamenti = [corr_calendar[d]['date_obj'] for d in date_list if corr_calendar[d]['has_trattamento']]
    if date_trattamenti:
        fig_corr.add_trace(go.Scatter(
            x=date_trattamenti,
            y=[y1_max * 0.02] * len(date_trattamenti),
            mode="markers",
            name=tr("Seduta Fisioterapia", "Physio Session"),
            marker=dict(symbol="cross", size=13, color="#10b981", line=dict(width=2, color="#047857")),
            hovertemplate="<b>%{x|%d %b %Y}</b><br>Seduta Fisioterapica Eseguita<extra></extra>"
        ), row=1, col=1, secondary_y=False)

    # --- ROW 2: CARICO INTERNO EXTRA-CAMPO (PALESTRA & PREP. FISICA 70/30) ---
    # Blocco Primario (70% o 100%)
    fig_corr.add_trace(go.Bar(
        x=dates_dt,
        y=gym_prim_list,
        name=tr("Gym Blocco Primario (70%)", "Gym Primary Block (70%)"),
        marker=dict(color=gym_prim_colors, opacity=gym_opacities, cornerradius=3),
        offsetgroup=3,
        customdata=gym_customdata,
        hovertemplate="<b>%{x|%d %b %Y}</b><br>Blocco Primario: <b>%{y:.0f} AU</b><br>Stimolo: %{customdata[0]}<br>Catena: %{customdata[1]}<br>Stress Eccentrico: %{customdata[4]}<extra></extra>"
    ), row=2, col=1)

    # Blocco Complementare (30%) - Impilato sul Primario tramite base
    fig_corr.add_trace(go.Bar(
        x=dates_dt,
        y=gym_sec_list,
        base=gym_prim_list,
        name=tr("Gym Blocco Complementare (30%)", "Gym Complementary Block (30%)"),
        marker=dict(color=gym_sec_colors, opacity=gym_opacities, cornerradius=3),
        offsetgroup=3,
        customdata=gym_customdata,
        hovertemplate="<b>%{x|%d %b %Y}</b><br>Blocco Complementare: <b>%{y:.0f} AU</b><br>Stimolo: %{customdata[2]}<br>Catena: %{customdata[3]}<extra></extra>"
    ), row=2, col=1)

    # Etichetta Carico Totale AU in cima alla barra impilata + Alert [! DOMS]
    y_text_row2 = [(p + s) + (y2_max * 0.04) if (p + s) > 0 else np.nan for p, s in zip(gym_prim_list, gym_sec_list)]
    fig_corr.add_trace(go.Scatter(
        x=dates_dt,
        y=y_text_row2,
        mode="text",
        text=gym_labels,
        textposition="top center",
        textfont=dict(size=9.5, family="Inter", color="#0f172a"),
        showlegend=False,
        hoverinfo="none"
    ), row=2, col=1)

    # Aggiornamento Layout Complessivo
    fig_corr.update_layout(
        barmode="group",
        bargap=0.32,
        bargroupgap=0.08,
        height=680,
        margin=dict(l=30, r=30, t=50, b=35),
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(family="Inter", color="#0f172a"),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.04,
            xanchor="center",
            x=0.5,
            font=dict(family="Inter", size=10.5, color="#334155")
        ),
        xaxis=dict(
            showgrid=True,
            gridcolor="#f1f5f9",
            tickfont=dict(family="Inter", size=10.5, color="#64748b"),
            tickformat="%d %b"
        ),
        yaxis=dict(
            title=dict(text="Carico Campo & GPS (AU)", font=dict(family="Inter", size=11, color="#0f172a")),
            showgrid=True,
            gridcolor="#f1f5f9",
            range=[0, y1_max],
            side="left",
            tickfont=dict(family="Inter", size=10, color="#64748b")
        ),
        yaxis2=dict(
            title=dict(text="Readiness Score (0-10)", font=dict(family="Inter", size=11, color="#7e22ce")),
            overlaying="y",
            side="right",
            range=[0, 10.5],
            dtick=2,
            showgrid=False,
            tickfont=dict(family="Inter", size=10, color="#7e22ce")
        ),
        yaxis3=dict(
            title=dict(text="Carico Extra-Campo AU (Gym)", font=dict(family="Inter", size=11, color="#0f172a")),
            showgrid=True,
            gridcolor="#f1f5f9",
            range=[0, y2_max],
            side="left",
            tickfont=dict(family="Inter", size=10, color="#64748b")
        )
    )
    st.plotly_chart(fig_corr, use_container_width=True)

    st.caption(
        "Corsia 1: Carico Esterno GPS & sRPE Tennis (AU) con soglia Carico Adattato. "
        "Corsia 2: Palestra & Prep. Fisica profilata (70% Blocco Primario + 30% Complementare) con allerta [! DOMS] per indolenzimento muscolare elevato. "
        "La 'Lente Clinica' modula l'opacità per isolare le catene cinetiche correlate alle problematiche cliniche."
    )

    st.markdown("<hr style='margin:20px 0;'>", unsafe_allow_html=True)

    # ---------------------------------------------------------------------
    # SEZIONE: AUDIT DIAGNOSTICO CONCOMITANZE CRITICHE A 48H
    # ---------------------------------------------------------------------
    st.markdown(
        f"<div style='display:flex; align-items:center; gap:8px; margin-bottom:12px;'>"
        f"<i class='bi bi-shield-check' style='color:#0ea5e9; font-size:18px;'></i>"
        f"<span style='font-size:16px; font-weight:800; color:#0f172a; text-transform:uppercase; letter-spacing:0.5px;'>"
        f"{tr('Audit Diagnostico Concomitanze Critiche a 48h (Clinica vs Carichi Palestra/Prep. Fisica)', '48h Critical Concomitance Diagnostic Audit (Clinical Complaints vs Gym/Fitness Loads)')}"
        f"</span></div>",
        unsafe_allow_html=True
    )

    all_rec_ath = get_registro_medico(atleta_id=atleta_id_sel, nome_giocatore=atleta_sel)
    if str(atleta_id_sel).startswith("mock-"):
        mock_recs = st.session_state.get('mock_registro_medico', [])
        all_rec_ath = [r for r in mock_recs if r.get('nome_giocatore') == atleta_sel] + all_rec_ath

    # Filtra casistiche cliniche nel range temporale
    casi_audit = []
    for r_clin in all_rec_ath:
        try:
            d_c = datetime.datetime.strptime(str(r_clin.get('data_inizio'))[:10], "%Y-%m-%d").date()
            if corr_start <= d_c <= corr_end:
                casi_audit.append(r_clin)
        except Exception:
            pass

    if not casi_audit:
        st.info(tr("Nessun evento clinico o trattamento registrato nel periodo di analisi selezionato.", "No clinical events or treatments logged in the selected time horizon."))
    else:
        righe_audit_tab = []
        for ev in casi_audit:
            d_ev_date = datetime.datetime.strptime(str(ev.get('data_inizio'))[:10], "%Y-%m-%d").date()
            distr_clin = ev.get('distretto_anatomico', 'Sistemico')
            tipo_ev = ev.get('tipo_scheda', 'EVENTO')
            vas_val = ev.get('scala_dolore_vas')
            vas_str = f"VAS {vas_val}/10" if vas_val is not None else "-"

            # Cerca sedute Gym/Prep. Fisica nei giorni T-1 e T-2
            t_minus_1 = (d_ev_date - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
            t_minus_2 = (d_ev_date - datetime.timedelta(days=2)).strftime("%Y-%m-%d")

            gym_prev_slots = []
            for d_prev, timing_lbl in [(t_minus_1, "T-1 (Ieri)"), (t_minus_2, "T-2 (2 gg fa)")]:
                if d_prev in corr_calendar:
                    for sl in corr_calendar[d_prev].get('srpe_slots', []):
                        if sl.get('tipo') in ('Gym', 'Preparazione Fisica'):
                            gym_prev_slots.append((timing_lbl, d_prev, sl))

            if not gym_prev_slots:
                righe_audit_tab.append({
                    tr("Data Evento", "Event Date"): str(d_ev_date),
                    tr("Distretto Clinico", "Clinical District"): distr_clin,
                    tr("Diagnosi / Scheda", "Diagnosis / Type"): f"[{tipo_ev}] {ev.get('sottotipo_evento', '')}",
                    tr("Dolore VAS", "VAS Pain"): vas_str,
                    tr("Seduta Gym Precedente", "Prior Gym Session"): tr("Nessuna Seduta (48h Libere)", "No Session (48h Clean)"),
                    tr("Stimolo & Catena", "Stimulus & Chain"): "-",
                    tr("Carico AU", "Load AU"): "-",
                    tr("Stress Eccentrico", "Eccentric Stress"): "-",
                    tr("Esito Audit", "Audit Outcome"): tr("INDIPENDENTE (Nessun Sovraccarico)", "INDEPENDENT (No Overload)")
                })
            else:
                for timing_lbl, d_prev, sl in gym_prev_slots:
                    stim_1_sl = sl.get('stimolo_primario', 'Generale')
                    dist_1_sl = sl.get('distretto_primario', 'Sistemico')
                    stim_2_sl = sl.get('stimolo_secondario')
                    dist_2_sl = sl.get('distretto_secondario')
                    stress_sl = sl.get('stress_eccentrico_atteso', 'Moderato')
                    au_sl = sl.get('carico', 0)

                    # Verifica corrispondenza anatomica
                    distretti_sl_1 = get_catena_clinici(dist_1_sl)
                    distretti_sl_2 = get_catena_clinici(dist_2_sl) if dist_2_sl else []
                    tutti_distretti_sl = distretti_sl_1 + distretti_sl_2 + [dist_1_sl, dist_2_sl or '']

                    corrisponde = any(
                        distr_clin.lower() in str(dt).lower() or str(dt).lower() in distr_clin.lower()
                        for dt in tutti_distretti_sl if dt and dt != 'Nessuno / Sistemico'
                    )

                    if corrisponde and (stress_sl == 'Elevato' or au_sl >= 300):
                        esito_str = tr("CRITICO (Sollecitazione Diretta 48h)", "CRITICAL (Direct Stress 48h)")
                    elif corrisponde:
                        esito_str = tr("ATTENZIONE (Coinvolgimento Distrettuale)", "WARNING (District Involvement)")
                    elif stress_sl == 'Elevato':
                        esito_str = tr("MONITORARE (Stress Sistemico)", "MONITOR (Systemic Stress)")
                    else:
                        esito_str = tr("CONGRUENTE / PREVENTIVO", "CONGRUENT / PREVENTIVE")

                    stim_str = f"{stim_1_sl} [{dist_1_sl}]"
                    if stim_2_sl:
                        stim_str += f" + {stim_2_sl}"

                    righe_audit_tab.append({
                        tr("Data Evento", "Event Date"): str(d_ev_date),
                        tr("Distretto Clinico", "Clinical District"): distr_clin,
                        tr("Diagnosi / Scheda", "Diagnosis / Type"): f"[{tipo_ev}] {ev.get('sottotipo_evento', '')}",
                        tr("Dolore VAS", "VAS Pain"): vas_str,
                        tr("Seduta Gym Precedente", "Prior Gym Session"): f"{timing_lbl} ({d_prev})",
                        tr("Stimolo & Catena", "Stimulus & Chain"): stim_str,
                        tr("Carico AU", "Load AU"): f"{au_sl:.0f} AU",
                        tr("Stress Eccentrico", "Eccentric Stress"): stress_sl,
                        tr("Esito Audit", "Audit Outcome"): esito_str
                    })

        st.dataframe(pd.DataFrame(righe_audit_tab), use_container_width=True)

    st.markdown("<hr style='margin:20px 0;'>", unsafe_allow_html=True)

    # ---------------------------------------------------------------------
    # Statistiche Incidenza per Distretto Anatomico
    # ---------------------------------------------------------------------
    st.markdown(
        f"<div style='display:flex; align-items:center; gap:8px; margin-bottom:12px;'>"
        f"<i class='bi bi-pie-chart' style='color:#0ea5e9; font-size:18px;'></i>"
        f"<span style='font-size:16px; font-weight:800; color:#0f172a; text-transform:uppercase; letter-spacing:0.5px;'>"
        f"{tr('Incidenza Clinica per Distretto Anatomico', 'Clinical Incidence by Anatomical District')}"
        f"</span></div>",
        unsafe_allow_html=True
    )

    all_rec_ath = get_registro_medico(atleta_id=atleta_id_sel, nome_giocatore=atleta_sel)
    if str(atleta_id_sel).startswith("mock-"):
        mock_recs = st.session_state.get('mock_registro_medico', [])
        all_rec_ath = [r for r in mock_recs if r.get('nome_giocatore') == atleta_sel] + all_rec_ath

    if not all_rec_ath:
        st.info("Nessuna casistica clinica archiviata per calcolare le statistiche di distretto.")
    else:
        conteggi_distretti = {}
        for r in all_rec_ath:
            d_anat = r.get('distretto_anatomico', 'Sistemico')
            if d_anat not in conteggi_distretti:
                conteggi_distretti[d_anat] = {"trattamenti": 0, "sovraccarichi": 0, "infortuni": 0, "giorni_stop": 0}
            t_sch = r.get('tipo_scheda')
            if t_sch == 'TRATTAMENTO': conteggi_distretti[d_anat]["trattamenti"] += 1
            elif t_sch == 'SOVRACCARICO': conteggi_distretti[d_anat]["sovraccarichi"] += 1
            elif t_sch in ('INFORTUNIO', 'MALATTIA'): conteggi_distretti[d_anat]["infortuni"] += 1

            try:
                d1 = datetime.datetime.strptime(str(r.get('data_inizio'))[:10], "%Y-%m-%d").date()
                d2 = datetime.datetime.strptime(str(r.get('data_fine'))[:10], "%Y-%m-%d").date()
                g_durata = (d2 - d1).days + 1
                if r.get('status_operativo') in ('INDISPONIBILE', 'LIMITATO'):
                    conteggi_distretti[d_anat]["giorni_stop"] += g_durata
            except Exception:
                pass

        distretti_sorted = sorted(conteggi_distretti.keys(), key=lambda k: (conteggi_distretti[k]['infortuni'] * 10 + conteggi_distretti[k]['sovraccarichi'] * 3 + conteggi_distretti[k]['trattamenti']), reverse=True)

        c_gr1, c_gr2 = st.columns([3.5, 2.5])
        with c_gr1:
            # Grafico orizzontale a barre impilate
            fig_distr = go.Figure()
            fig_distr.add_trace(go.Bar(
                y=distretti_sorted,
                x=[conteggi_distretti[d]['infortuni'] for d in distretti_sorted],
                name="Infortuni / Stop",
                orientation="h",
                marker=dict(color="#e11d48")
            ))
            fig_distr.add_trace(go.Bar(
                y=distretti_sorted,
                x=[conteggi_distretti[d]['sovraccarichi'] for d in distretti_sorted],
                name="Sovraccarichi / Fastidi",
                orientation="h",
                marker=dict(color="#f59e0b")
            ))
            fig_distr.add_trace(go.Bar(
                y=distretti_sorted,
                x=[conteggi_distretti[d]['trattamenti'] for d in distretti_sorted],
                name="Trattamenti Preventivi",
                orientation="h",
                marker=dict(color="#10b981")
            ))
            fig_distr.update_layout(
                barmode="stack",
                height=max(260, len(distretti_sorted) * 35 + 80),
                margin=dict(l=10, r=20, t=20, b=20),
                plot_bgcolor="white",
                paper_bgcolor="white",
                font=dict(family="Inter", color="#0f172a"),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                xaxis=dict(title="Numero Eventi Registrati", showgrid=True, gridcolor="#f1f5f9"),
                yaxis=dict(showgrid=False)
            )
            st.plotly_chart(fig_distr, use_container_width=True)

        with c_gr2:
            # Tabella riepilogativa
            st.markdown(
                f"<div style='background:#ffffff; border:1px solid #e2e8f0; border-radius:10px; padding:12px; font-family:\"Inter\",sans-serif;'>"
                f"<div style='font-size:12px; font-weight:800; color:#0f172a; margin-bottom:8px; text-transform:uppercase;'>Giorni di Indisponibilità per Distretto</div>",
                unsafe_allow_html=True
            )
            for d in distretti_sorted:
                tot_ev = conteggi_distretti[d]['infortuni'] + conteggi_distretti[d]['sovraccarichi'] + conteggi_distretti[d]['trattamenti']
                g_stop = conteggi_distretti[d]['giorni_stop']
                st.markdown(
                    f"<div style='display:flex; justify-content:space-between; align-items:center; padding:6px 0; border-bottom:1px solid #f1f5f9; font-size:12px;'>"
                    f"<span style='font-weight:700; color:#0f172a;'>{d}</span>"
                    f"<span style='color:#64748b;'>{tot_ev} ev. · <b style='color:#be123c;'>{g_stop} gg stop</b></span>"
                    f"</div>",
                    unsafe_allow_html=True
                )
            st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<hr style='margin:28px 0 20px 0;'>", unsafe_allow_html=True)

    # ---------------------------------------------------------------------
    # SEZIONE: ANALISI LONGITUDINALE & PREVENZIONE TRATTAMENTI FISIOTERAPICI (>90 GIORNI / STORICO)
    # ---------------------------------------------------------------------
    with st.container(border=True):
        st.markdown(
            f"<div style='display:flex; align-items:center; gap:8px; margin-bottom:12px;'>"
            f"<i class='bi bi-bandaid-fill' style='color:#10b981; font-size:18px;'></i>"
            f"<span style='font-size:16px; font-weight:800; color:#0f172a; text-transform:uppercase; letter-spacing:0.5px;'>"
            f"{tr('Analisi Longitudinale & Prevenzione Trattamenti Fisioterapici (>90 Giorni / Storico)', 'Longitudinal Analysis & Physio Prevention (>90 Days / All-Time)')}"
            f"</span></div>",
            unsafe_allow_html=True
        )

        # Selettore Orizzonte Temporale Dedicato
        c_hor1, c_hor2 = st.columns([2.5, 3.5])
        with c_hor1:
            opz_horiz = [
                tr("Ultimi 180 Giorni (6 Mesi)", "Last 180 Days (6 Months)"),
                tr("Ultimi 90 Giorni", "Last 90 Days"),
                tr("Ultimi 365 Giorni (1 Anno)", "Last 365 Days (1 Year)"),
                tr("Tutto lo Storico Atleta", "All-Time Athlete History")
            ]
            sel_horiz = st.selectbox(
                tr("Orizzonte Temporale Trattamenti:", "Physio Time Horizon:"),
                opz_horiz,
                index=0,
                key="cal_fisio_horiz_sel"
            )

        if "90" in sel_horiz:
            d_lim_fisio = today - datetime.timedelta(days=90)
        elif "180" in sel_horiz:
            d_lim_fisio = today - datetime.timedelta(days=180)
        elif "365" in sel_horiz:
            d_lim_fisio = today - datetime.timedelta(days=365)
        else:
            d_lim_fisio = datetime.date(2000, 1, 1)

        # Filtro trattamenti nel periodo
        trattamenti_periodo = []
        for r in all_rec_ath:
            if r.get('tipo_scheda') == 'TRATTAMENTO':
                try:
                    d_r = datetime.datetime.strptime(str(r.get('data_inizio'))[:10], "%Y-%m-%d").date()
                    if d_r >= d_lim_fisio:
                        trattamenti_periodo.append(r)
                except Exception:
                    pass

        tot_sedute_fisio = len(trattamenti_periodo)

        if tot_sedute_fisio == 0:
            st.info(tr("Nessun trattamento fisioterapico registrato nell'orizzonte temporale selezionato.", "No physiotherapy sessions recorded in selected timeframe."))
        else:
            # 4 KPI Preventivi
            distr_counts = {}
            terapie_counts = {}
            for r in trattamenti_periodo:
                d_nat = r.get('distretto_anatomico', 'Sistemico')
                l_nat = r.get('lato', 'N/A')
                lbl_dl = f"{d_nat} ({l_nat})" if l_nat not in ('N/A', '') else d_nat
                distr_counts[lbl_dl] = distr_counts.get(lbl_dl, 0) + 1
                
                t_sub = r.get('sottotipo_evento', 'Altro')
                terapie_counts[t_sub] = terapie_counts.get(t_sub, 0) + 1

            top_distretto = max(distr_counts.items(), key=lambda x: x[1]) if distr_counts else ("-", 0)
            top_terapia = max(terapie_counts.items(), key=lambda x: x[1]) if terapie_counts else ("-", 0)
            n_ricorrenti_3 = sum(1 for c in distr_counts.values() if c >= 3)

            c_pf1, c_pf2, c_pf3, c_pf4 = st.columns(4)
            with c_pf1:
                st.markdown(card_kpi(
                    tr("Sedute Fisioterapia", "Physio Sessions"),
                    f"{tot_sedute_fisio}",
                    sottotitolo=tr("Totale Sedute Periodo", "Total Sessions in Period"),
                    accento="#10b981"
                ), unsafe_allow_html=True)
            with c_pf2:
                st.markdown(card_kpi(
                    tr("Distretto Più Trattato", "Most Treated District"),
                    f"<span style='font-size:15px; font-weight:800; color:#0f172a;'>{top_distretto[0]}</span>",
                    sottotitolo=f"{top_distretto[1]} {tr('sedute eseguite', 'sessions done')}",
                    accento="#0ea5e9"
                ), unsafe_allow_html=True)
            with c_pf3:
                st.markdown(card_kpi(
                    tr("Terapia Prevalente", "Primary Therapy"),
                    f"<span style='font-size:13.5px; font-weight:800; color:#0f172a;'>{top_terapia[0]}</span>",
                    sottotitolo=f"{top_terapia[1]} {tr('applicazioni', 'applications')}",
                    accento="#8b5cf6"
                ), unsafe_allow_html=True)
            with c_pf4:
                col_alert_ric = "#e11d48" if n_ricorrenti_3 >= 2 else ("#f59e0b" if n_ricorrenti_3 == 1 else "#10b981")
                st.markdown(card_kpi(
                    tr("Aree Ricorrenti (≥3 sedute)", "Recurrent Areas (≥3)"),
                    f"{n_ricorrenti_3}",
                    sottotitolo=tr("Distretti con alta richiesta", "Districts with high recurrence"),
                    accento=col_alert_ric
                ), unsafe_allow_html=True)

            st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)

            # -------------------------------------------------------------
            # TABELLA 1: MATRICE DI RICORRENZA PER DISTRETTO ANATOMICO
            # -------------------------------------------------------------
            st.markdown(
                f"<div style='font-size:13px; font-weight:800; color:#0f172a; text-transform:uppercase; letter-spacing:0.5px; margin-bottom:8px; display:flex; align-items:center; gap:6px;'>"
                f"<i class='bi bi-table' style='color:#0ea5e9;'></i>{tr('Matrice di Ricorrenza per Distretto Anatomico (Focus Prevenzione)', 'Recurrence Matrix by Anatomical District')}</div>",
                unsafe_allow_html=True
            )

            # Raggruppamento per Distretto + Lato
            gruppi_distretto = {}
            for r in trattamenti_periodo:
                d_nat = r.get('distretto_anatomico', 'Sistemico')
                l_nat = r.get('lato', 'N/A')
                k_grp = (d_nat, l_nat)
                if k_grp not in gruppi_distretto:
                    gruppi_distretto[k_grp] = []
                gruppi_distretto[k_grp].append(r)

            righe_ricorrenza = []
            for (d_nat, l_nat), recs_grp in gruppi_distretto.items():
                n_tratt = len(recs_grp)
                quota_pct = (n_tratt / tot_sedute_fisio) * 100.0 if tot_sedute_fisio > 0 else 0.0
                
                date_list_grp = []
                for r in recs_grp:
                    try:
                        d_parsed = datetime.datetime.strptime(str(r.get('data_inizio'))[:10], "%Y-%m-%d").date()
                        date_list_grp.append(d_parsed)
                    except Exception:
                        pass
                date_list_grp.sort()

                prima_d = date_list_grp[0].strftime("%d/%m/%Y") if date_list_grp else "-"
                ultima_d = date_list_grp[-1].strftime("%d/%m/%Y") if date_list_grp else "-"

                if len(date_list_grp) >= 2:
                    diffs_gg = [(date_list_grp[idx] - date_list_grp[idx-1]).days for idx in range(1, len(date_list_grp))]
                    avg_interval = f"{float(np.mean(diffs_gg)):.1f} {tr('gg', 'days')}"
                else:
                    avg_interval = "-"

                terapie_usate = list(set(r.get('sottotipo_evento', '') for r in recs_grp if r.get('sottotipo_evento')))
                str_terapie = ", ".join(terapie_usate) if terapie_usate else "-"

                # Conteggio trattamenti negli ultimi 30 giorni per questo distretto
                n_ultimi_30 = sum(1 for d in date_list_grp if (today - d).days <= 30)

                # Classificazione Status Prevenzione
                if n_tratt >= 5 or n_ultimi_30 >= 3:
                    lbl_stat = tr("CRITICO / RICORRENTE", "CRITICAL / RECURRENT")
                    status_badge = f"<span style='background:rgba(225,29,72,0.12); color:#be123c; border:1px solid rgba(225,29,72,0.4); padding:3px 8px; border-radius:6px; font-weight:800; font-size:11px;'><i class='bi bi-exclamation-octagon-fill' style='margin-right:3px;'></i>{lbl_stat}</span>"
                elif n_tratt >= 3:
                    lbl_stat = tr("MONITORARE", "MONITOR")
                    status_badge = f"<span style='background:rgba(245,158,11,0.12); color:#b45309; border:1px solid rgba(245,158,11,0.4); padding:3px 8px; border-radius:6px; font-weight:800; font-size:11px;'><i class='bi bi-exclamation-triangle-fill' style='margin-right:3px;'></i>{lbl_stat}</span>"
                else:
                    lbl_stat = tr("GESTIONE ROUTINE", "ROUTINE MANAGEMENT")
                    status_badge = f"<span style='background:rgba(16,185,129,0.12); color:#047857; border:1px solid rgba(16,185,129,0.4); padding:3px 8px; border-radius:6px; font-weight:800; font-size:11px;'><i class='bi bi-check-circle-fill' style='margin-right:3px;'></i>{lbl_stat}</span>"

                righe_ricorrenza.append({
                    "distretto_lato": f"<b>{d_nat}</b> ({l_nat})",
                    "n_tratt": n_tratt,
                    "quota_pct": quota_pct,
                    "arco_temporale": f"{prima_d} → {ultima_d}",
                    "avg_interval": avg_interval,
                    "terapie": str_terapie,
                    "status_badge": status_badge
                })

            # Ordinamento per N° Trattamenti desc
            righe_ricorrenza.sort(key=lambda x: x['n_tratt'], reverse=True)

            html_ric_body = ""
            for row_r in righe_ricorrenza:
                html_ric_body += (
                    f"<tr style='border-bottom:1px solid #f1f5f9; font-size:12px;'>"
                    f"<td style='padding:9px 12px; color:#0f172a;'>{row_r['distretto_lato']}</td>"
                    f"<td style='padding:9px 12px; text-align:center; font-weight:800; color:#0284c7; font-size:13px;'>{row_r['n_tratt']}</td>"
                    f"<td style='padding:9px 12px; text-align:center; font-weight:700; color:#64748b;'>{row_r['quota_pct']:.1f}%</td>"
                    f"<td style='padding:9px 12px; text-align:center; color:#334155; font-size:11.5px;'>{row_r['arco_temporale']}</td>"
                    f"<td style='padding:9px 12px; text-align:center; font-weight:700; color:#0f172a;'>{row_r['avg_interval']}</td>"
                    f"<td style='padding:9px 12px; color:#475569; font-size:11.5px;'>{row_r['terapie']}</td>"
                    f"<td style='padding:9px 12px; text-align:center;'>{row_r['status_badge']}</td>"
                    f"</tr>"
                )

            th_distr = tr("Distretto Anatomico & Lato", "District & Side")
            th_ntratt = tr("N° Trattamenti", "No. Sessions")
            th_quota = tr("Quota %", "Share %")
            th_dates = tr("Prima → Ultima Data", "First → Last Date")
            th_avg = tr("Intervallo Medio", "Mean Interval")
            th_terapie = tr("Terapie Applicate", "Applied Therapies")
            th_status = tr("Status Prevenzione", "Prevention Status")

            st.markdown(
                f"<div style='background:#ffffff; border:1px solid #e2e8f0; border-radius:10px; overflow-x:auto; margin-bottom:20px;'>"
                f"<table style='width:100%; border-collapse:collapse; font-family:\"Inter\",sans-serif;'>"
                f"<thead><tr style='background:#0f172a; color:#f8fafc; font-size:11px; text-transform:uppercase; letter-spacing:0.5px;'>"
                f"<th style='padding:9px 12px; text-align:left;'>{th_distr}</th>"
                f"<th style='padding:9px 12px; text-align:center;'>{th_ntratt}</th>"
                f"<th style='padding:9px 12px; text-align:center;'>{th_quota}</th>"
                f"<th style='padding:9px 12px; text-align:center;'>{th_dates}</th>"
                f"<th style='padding:9px 12px; text-align:center;'>{th_avg}</th>"
                f"<th style='padding:9px 12px; text-align:left;'>{th_terapie}</th>"
                f"<th style='padding:9px 12px; text-align:center;'>{th_status}</th>"
                f"</tr></thead><tbody>{html_ric_body}</tbody></table></div>",
                unsafe_allow_html=True
            )

            # -------------------------------------------------------------
            # TABELLA 2: REGISTRO STORICO COMPLETO DEI SOLI TRATTAMENTI
            # -------------------------------------------------------------
            st.markdown(
                f"<div style='font-size:13px; font-weight:800; color:#0f172a; text-transform:uppercase; letter-spacing:0.5px; margin-bottom:8px; display:flex; align-items:center; gap:6px;'>"
                f"<i class='bi bi-journal-check' style='color:#10b981;'></i>{tr('Registro Dettagliato Sedute Fisioterapiche', 'Detailed Physiotherapy Sessions Log')}</div>",
                unsafe_allow_html=True
            )

            c_fil_d1, c_fil_d2 = st.columns(2)
            with c_fil_d1:
                distr_presenti_f = sorted(list(set(r.get('distretto_anatomico', 'Sistemico') for r in trattamenti_periodo)))
                fil_distr_f = st.multiselect(
                    tr("Filtra per Distretto Anatomico:", "Filter by District:"),
                    distr_presenti_f,
                    default=[],
                    key=f"{key_prefix}_ms_distr_f"
                )
            with c_fil_d2:
                terapie_presenti_f = sorted(list(set(r.get('sottotipo_evento', 'Altro') for r in trattamenti_periodo if r.get('sottotipo_evento'))))
                fil_terapie_f = st.multiselect(
                    tr("Filtra per Tipologia Trattamento:", "Filter by Therapy:"),
                    terapie_presenti_f,
                    default=[],
                    key=f"{key_prefix}_ms_terapia_f"
                )

            trattamenti_tab2 = []
            for r in trattamenti_periodo:
                if fil_distr_f and r.get('distretto_anatomico') not in fil_distr_f:
                    continue
                if fil_terapie_f and r.get('sottotipo_evento') not in fil_terapie_f:
                    continue
                trattamenti_tab2.append(r)

            # Ordinamento per data decrescente
            trattamenti_tab2.sort(key=lambda x: str(x.get('data_inizio', '')), reverse=True)

            html_det_body = ""
            for r in trattamenti_tab2:
                d_str = str(r.get('data_inizio', ''))[:10]
                distr_s = r.get('distretto_anatomico', '-')
                lato_s = r.get('lato', '-')
                terapia_s = r.get('sottotipo_evento', '-')
                vas_v = f"VAS {r.get('scala_dolore_vas')}" if r.get('scala_dolore_vas') is not None else "-"
                ind_s = r.get('indicazioni_staff', '-') or '-'
                note_s = r.get('note_cliniche_dettaglio', '-') or '-'
                operatore_s = r.get('autore_nome', 'Staff') or 'Staff'

                html_det_body += (
                    f"<tr style='border-bottom:1px solid #f1f5f9; font-size:12px;'>"
                    f"<td style='padding:8px 10px; font-weight:700; color:#0f172a;'>{d_str}</td>"
                    f"<td style='padding:8px 10px; font-weight:700;'>{distr_s}</td>"
                    f"<td style='padding:8px 10px; color:#475569;'>{lato_s}</td>"
                    f"<td style='padding:8px 10px; color:#0284c7; font-weight:700;'>{terapia_s}</td>"
                    f"<td style='padding:8px 10px; text-align:center; font-weight:800; color:#be123c;'>{vas_v}</td>"
                    f"<td style='padding:8px 10px; color:#334155; font-size:11.5px;'>{ind_s}</td>"
                    f"<td style='padding:8px 10px; color:#64748b; font-size:11px;'>{note_s}</td>"
                    f"<td style='padding:8px 10px; color:#475569; font-size:11px;'>{operatore_s}</td>"
                    f"</tr>"
                )

            th_d_data = tr("Data", "Date")
            th_d_distr = tr("Distretto", "District")
            th_d_lato = tr("Lato", "Side")
            th_d_ter = tr("Terapia Applicata", "Applied Therapy")
            th_d_dol = tr("Dolore", "Pain")
            th_d_ind = tr("Indicazioni Staff", "Staff Directions")
            th_d_note = tr("Note Cliniche", "Clinical Notes")
            th_d_op = tr("Operatore", "Provider")

            st.markdown(
                f"<div style='background:#ffffff; border:1px solid #e2e8f0; border-radius:10px; overflow-x:auto; margin-bottom:12px;'>"
                f"<table style='width:100%; border-collapse:collapse; font-family:\"Inter\",sans-serif;'>"
                f"<thead><tr style='background:#0f172a; color:#f8fafc; font-size:10.5px; text-transform:uppercase; letter-spacing:0.5px;'>"
                f"<th style='padding:8px 10px; text-align:left;'>{th_d_data}</th>"
                f"<th style='padding:8px 10px; text-align:left;'>{th_d_distr}</th>"
                f"<th style='padding:8px 10px; text-align:left;'>{th_d_lato}</th>"
                f"<th style='padding:8px 10px; text-align:left;'>{th_d_ter}</th>"
                f"<th style='padding:8px 10px; text-align:center;'>{th_d_dol}</th>"
                f"<th style='padding:8px 10px; text-align:left;'>{th_d_ind}</th>"
                f"<th style='padding:8px 10px; text-align:left;'>{th_d_note}</th>"
                f"<th style='padding:8px 10px; text-align:left;'>{th_d_op}</th>"
                f"</tr></thead><tbody>{html_det_body}</tbody></table></div>",
                unsafe_allow_html=True
            )



def render_allenamenti_gym_fisico(t, atleta_sel=None, atleta_id_sel=None, key_prefix="et_gym"):
    """
    Renders Staff Entry & Validation for Gym / Athletic Preparation (70/30 Model) and Session Audit Trail.
    """
    user_role = st.session_state.get('role', 'Atleta')
    is_admin = (user_role in ['Super-Admin', 'Admin'])
    is_coach = (user_role in ['Staff', 'Coach', 'Fisio / Medico'] or is_admin)
    user = st.session_state.get('user')

    dict_atleti = _get_atleti_dict(user, is_admin, is_coach)
    atleta_nomi = list(dict_atleti.keys())

    if not atleta_sel:
        glob_ath = st.session_state.get('selected_athlete')
        if glob_ath in atleta_nomi:
            atleta_sel = glob_ath
        else:
            atleta_sel = atleta_nomi[0] if atleta_nomi else "prova uno"

    if not atleta_id_sel:
        atleta_id_sel = dict_atleti.get(atleta_sel, f"mock-{atleta_sel}")

    df_r = pd.DataFrame()
    if atleta_id_sel and not str(atleta_id_sel).startswith("mock-"):
        try:
            res_r = supabase.table('rpe_sessioni').select('*').eq('atleta_id', atleta_id_sel).order('data', desc=True).limit(60).execute()
            df_r = pd.DataFrame(res_r.data or [])
        except Exception:
            df_r = pd.DataFrame()

    is_en_lang = st.session_state.get('lang', 'IT') == 'EN'

    # Modulo Inserimento / Validazione Staff (Palestra & Prep. Fisica / RPE)
    with st.expander(tr("Registrazione & Validazione Seduta Staff (Palestra, Prep. Fisica & Tennis)", "Staff Session Entry & Validation (Gym, Fitness & Tennis)"), expanded=False):
        info_staff_sub = tr("Inserisci o valida la durata e il profilo biomeccanico per riconciliarli con quanto dichiarato dall'atleta.", "Enter or validate duration and biomechanical profile to reconcile with athlete inputs.")
        st.markdown(
            f"<div style='font-size:12px; color:#64748b; margin-bottom:12px; font-weight:600;'>"
            f"{info_staff_sub}"
            f"</div>",
            unsafe_allow_html=True
        )
        c_f1, c_f2, c_f3 = st.columns([1.5, 1.2, 1.8])
        with c_f1:
            data_staff_input = st.date_input(
                tr("Data Seduta", "Session Date"),
                value=datetime.date.today(),
                key=f"{key_prefix}_staff_date"
            )
        with c_f2:
            slot_staff_input = st.selectbox(
                tr("Slot Seduta", "Session Slot"),
                [1, 2],
                format_func=lambda s: f"Slot #{s}",
                key=f"{key_prefix}_staff_slot"
            )
        with c_f3:
            tipo_staff_opts = ["Palestra (Gym)", "Preparazione Fisica", "Tennis", "Recupero", "Altro"]
            tipo_staff_sel = st.selectbox(
                tr("Tipologia Seduta", "Session Type"),
                tipo_staff_opts,
                key=f"{key_prefix}_staff_tipo"
            )
            tipo_db_staff = "Gym" if "Palestra" in tipo_staff_sel else tipo_staff_sel

        c_fd1, c_fd2 = st.columns([2, 2])
        with c_fd1:
            dur_staff_min_input = st.number_input(
                tr("Durata Staff (minuti)", "Staff Duration (minutes)"),
                min_value=5,
                max_value=360,
                value=60,
                step=5,
                key=f"{key_prefix}_staff_dur_min"
            )
        with c_fd2:
            rpe_staff_input = st.slider(
                tr("RPE Staff Stimato (0-10)", "Staff Estimated RPE (0-10)"),
                0, 10, 5,
                key=f"{key_prefix}_staff_rpe"
            )

        # Profilazione Biomeccanica 70/30 per Palestra e Prep. Fisica
        s_stim1, s_dist1, s_peso, s_stim2, s_dist2, s_stress = None, None, 100, None, None, 'Moderato'
        if tipo_db_staff in ("Gym", "Preparazione Fisica"):
            st.markdown(
                f"<div style='background:rgba(14,165,233,0.06); border:1px solid rgba(14,165,233,0.25); border-radius:8px; padding:10px 12px; margin:8px 0 12px 0;'>"
                f"<div style='font-size:11.5px; font-weight:800; color:#0284c7; text-transform:uppercase; letter-spacing:0.5px; margin-bottom:6px;'>"
                f"<i class='bi bi-layers-half'></i> {tr('Profilazione Biomeccanica (Modello 70/30 Staff)', 'Biomechanical Profile (70/30 Staff Model)')}"
                f"</div>",
                unsafe_allow_html=True
            )
            l_stim_st = STIMOLI_GYM if tipo_db_staff == "Gym" else STIMOLI_PREP_FISICA
            st_lbls_st = [s[1] if is_en_lang else s[0] for s in l_stim_st]
            cat_lbls_st = [c[1] if is_en_lang else c[0] for c in DISTRETTI_CATENE_CINETICHE]

            c_sb1, c_sb2 = st.columns(2)
            with c_sb1:
                stim1_st_sel = st.selectbox(tr("Stimolo Preponderante (70%)", "Primary Stimulus (70%)"), st_lbls_st, key=f"{key_prefix}_stim1_st")
            with c_sb2:
                dist1_st_sel = st.selectbox(tr("Catena Cinetica Primaria", "Primary Kinetic Chain"), cat_lbls_st, key=f"{key_prefix}_dist1_st")
            s_stim1 = l_stim_st[st_lbls_st.index(stim1_st_sel)][0]
            s_dist1 = DISTRETTI_CATENE_CINETICHE[cat_lbls_st.index(dist1_st_sel)][0]

            chk_st_sec = st.checkbox(
                tr("Aggiungi Blocco Complementare (30% split)", "Add Complementary Block (30% split)"),
                value=False,
                key=f"{key_prefix}_chk_st_sec"
            )
            if chk_st_sec:
                s_peso = 70
                c_sbc1, c_sbc2 = st.columns(2)
                with c_sbc1:
                    stim2_st_sel = st.selectbox(tr("Stimolo Complementare (30%)", "Complementary Stimulus (30%)"), st_lbls_st, key=f"{key_prefix}_stim2_st")
                with c_sbc2:
                    dist2_st_sel = st.selectbox(tr("Catena Complementare", "Complementary Chain"), cat_lbls_st, key=f"{key_prefix}_dist2_st")
                s_stim2 = l_stim_st[st_lbls_st.index(stim2_st_sel)][0]
                s_dist2 = DISTRETTI_CATENE_CINETICHE[cat_lbls_st.index(dist2_st_sel)][0]

            opz_str_st = [("Basso", "Low"), ("Moderato", "Moderate"), ("Elevato", "High")]
            str_lbls_st = [s[1] if is_en_lang else s[0] for s in opz_str_st]
            str_sel_st = st.selectbox(tr("Stress Eccentrico / Frenate", "Expected Eccentric Stress"), str_lbls_st, index=1, key=f"{key_prefix}_str_st")
            s_stress = opz_str_st[str_lbls_st.index(str_sel_st)][0]
            st.markdown("</div>", unsafe_allow_html=True)

        note_staff_input = st.text_input(tr("Note Tecniche Seduta (opzionale)", "Staff Technical Notes (optional)"), key=f"{key_prefix}_staff_note")

        if st.button(tr("Salva / Valida Seduta Staff", "Save / Validate Staff Session"), type="primary", key=f"{key_prefix}_btn_save_staff"):
            staff_payload = {
                "atleta_id": atleta_id_sel,
                "profilo_id": user.id if user else None,
                "data": str(data_staff_input),
                "slot": slot_staff_input,
                "tipologia": tipo_db_staff,
                "durata_staff_min": float(dur_staff_min_input),
                "rpe_staff": float(rpe_staff_input),
                "stimolo_primario": s_stim1,
                "distretto_primario": s_dist1,
                "peso_primario_pct": s_peso,
                "stimolo_secondario": s_stim2,
                "distretto_secondario": s_dist2,
                "stress_eccentrico_atteso": s_stress,
                "note": note_staff_input.strip() if note_staff_input else None
            }
            ok_st, res_st = calcola_e_salva_slot_rpe(staff_payload, autore='staff')
            if ok_st:
                st.success(tr("Seduta validata e salvata con successo dallo Staff!", "Session successfully validated and saved by Staff!"))
                st.rerun()
            else:
                st.error(f"{tr('Errore nel salvataggio:', 'Error saving:')} {res_st}")

    st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)

    if df_r.empty:
        st.info("Nessuna sessione sRPE presente nello storico.")
    else:
        st.markdown(f"#### {tr('Tracciamento Sessioni, Riconciliazione & Audit Modifiche:', 'Session Tracking, Reconciliation & Audit Trail:')}")
        tabella_audit = []
        for _, r_item in df_r.sort_values('data', ascending=False).iterrows():
            c_at = r_item.get('created_at', '')
            u_at = r_item.get('updated_at', '')
            modificato = False
            if c_at and u_at:
                modificato = (str(u_at)[:19] != str(c_at)[:19])

            dur_atl = r_item.get('durata_atleta_min')
            dur_stf = r_item.get('durata_staff_min')
            dur_eff = r_item.get('durata_minuti', 0)

            # Dettaglio riconciliazione
            if dur_atl is not None and dur_stf is not None and float(dur_atl) > 0 and float(dur_stf) > 0:
                dur_str = f"{dur_eff}m (Atl: {float(dur_atl):.0f}m | Stf: {float(dur_stf):.0f}m)"
            elif dur_atl is not None and float(dur_atl) > 0:
                dur_str = f"{dur_eff}m (Atleta)"
            elif dur_stf is not None and float(dur_stf) > 0:
                dur_str = f"{dur_eff}m (Staff)"
            else:
                dur_str = f"{dur_eff}m"

            # Profilo 70/30
            stim_prim = r_item.get('stimolo_primario')
            dist_prim = r_item.get('distretto_primario')
            stim_sec = r_item.get('stimolo_secondario')
            peso_pct = r_item.get('peso_primario_pct', 100) or 100

            if stim_prim and stim_sec:
                profilo_str = f"{stim_prim} ({peso_pct}%) + {stim_sec} ({100-peso_pct}%)"
            elif stim_prim:
                profilo_str = f"{stim_prim} ({dist_prim or 'Globale'})"
            else:
                profilo_str = "-"

            rpe_v = r_item.get('rpe', 0)
            rpe_stf_v = r_item.get('rpe_staff')
            rpe_display = f"{rpe_v} (Stf: {float(rpe_stf_v):.0f})" if rpe_stf_v is not None and float(rpe_stf_v) != float(rpe_v) else str(rpe_v)

            tabella_audit.append({
                tr("Data", "Date"): r_item['data'],
                tr("Slot", "Slot"): f"#{r_item.get('slot', 1)}",
                tr("Tipologia", "Type"): r_item.get('tipologia', 'N/D'),
                tr("Durata Consolidata", "Duration"): dur_str,
                tr("RPE", "RPE"): rpe_display,
                tr("Carico AU", "Load AU"): f"{r_item.get('carico_interno', 0)} AU",
                tr("Profilo 70/30", "70/30 Profile"): profilo_str,
                tr("Stress Eccentrico", "Eccentric Stress"): r_item.get('stress_eccentrico_atteso', 'Moderato') or 'Moderato',
                tr("Stato", "Status"): "[MODIFICATO]" if modificato else "[ORIGINALE]",
                tr("Ultimo Aggiornamento", "Last Update"): str(u_at)[:16].replace('T', ' ') if u_at else '-'
            })
        st.dataframe(pd.DataFrame(tabella_audit), use_container_width=True)




def render_calendario_medico(t):
    """
    Pagina principale: Inserimento Sessioni Extra Tennis
    Tab 1: Inserimento & Gestione Registro (Clinico / Fisio / Infortuni)
    Tab 2: Allenamenti GYM e Fisico (Validazione Sedute Staff 70/30 & Audit Modifiche)
    """
    user_role = st.session_state.get('role', 'Atleta')
    if user_role == 'Atleta':
        st.error(tr("Accesso non consentito all'Area Medica ed Extra-Tennis.", "Access not authorized to Medical & Extra-Tennis Area."))
        return

    is_admin = (user_role in ['Super-Admin', 'Admin'])
    is_coach = (user_role in ['Staff', 'Coach', 'Fisio / Medico'] or is_admin)
    user = st.session_state.get('user')

    # Header Istituzionale M0V3
    render_page_header(
        tr("Medico & Extra Tennis", "Medical & Extra-Tennis"),
        tr("Registro clinico/fisioterapico, infortuni e inserimento sedute GYM / Preparazione Fisica", 
           "Clinical/physio registry, injury tracking, and GYM / Athletic preparation entries"),
        "MEDICAL & EXTRA-TENNIS SESSIONS"
    )

    dict_atleti = _get_atleti_dict(user, is_admin, is_coach)
    atleta_nomi = list(dict_atleti.keys())

    glob_ath = st.session_state.get('selected_athlete')
    if glob_ath in atleta_nomi:
        default_idx = atleta_nomi.index(glob_ath)
    else:
        default_idx = 0

    c_sel, c_info = st.columns([2.5, 3.5])
    with c_sel:
        atleta_sel = st.selectbox(
            tr("Atleta Selezionato:", "Selected Athlete:"),
            atleta_nomi,
            index=default_idx,
            key="et_atleta_sel_page"
        )
    atleta_id_sel = dict_atleti.get(atleta_sel)

    # Hero strip compatta
    render_athlete_hero_strip(atleta_sel)

    # Tab Navigazione con controllo permessi utente
    lbl_et_1 = tr("Inserimento & Gestione Registro", "Data Entry & Registry")
    lbl_et_2 = tr("Allenamenti GYM e Fisico", "GYM & Fitness Sessions")

    user_perms = st.session_state.get('user_permessi_moduli')
    tabs_disponibili_et = []
    if st.session_state.get('role') == 'Super-Admin' or user_perms is None:
        tabs_disponibili_et = [lbl_et_1, lbl_et_2]
    else:
        et_perms = {r for (ar, r) in user_perms if ar in ['Medico & Extra Tennis', 'Calendario & Area Medica', 'Inserimento Sessioni Extra Tennis']}
        if not et_perms:
            tabs_disponibili_et = [lbl_et_1, lbl_et_2]
        else:
            if "Inserimento & Gestione Registro" in et_perms or any("Registro" in r for r in et_perms):
                tabs_disponibili_et.append(lbl_et_1)
            if "Allenamenti GYM e Fisico" in et_perms or any("GYM" in r or "Fisico" in r for r in et_perms):
                tabs_disponibili_et.append(lbl_et_2)
            if not tabs_disponibili_et:
                tabs_disponibili_et = [lbl_et_1, lbl_et_2]

    active_et_tab = render_tab_navigation(tabs_disponibili_et, key="nav_extra_tennis")

    today = datetime.date.today()
    mese_corrente = today.month
    anno_corrente = today.year
    nomi_mesi_it = ["Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno", "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"]
    nomi_mesi_en = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
    nome_mese_str = tr(nomi_mesi_it[mese_corrente - 1], nomi_mesi_en[mese_corrente - 1])

    # =========================================================================
    # TAB 1: INSERIMENTO & GESTIONE REGISTRO
    # =========================================================================
    if active_et_tab == lbl_et_1:
        st.markdown(
            f"<div style='display:flex; align-items:center; gap:8px; margin-bottom:12px;'>"
            f"<i class='bi bi-pencil-square' style='color:#0ea5e9; font-size:18px;'></i>"
            f"<span style='font-size:16px; font-weight:800; color:#0f172a; text-transform:uppercase; letter-spacing:0.5px;'>"
            f"{tr('Inserimento Voce nel Registro Clinico & Logistico', 'New Clinical & Logistics Entry')}"
            f"</span></div>",
            unsafe_allow_html=True
        )

        modalita_scheda = st.radio(
            tr("Tipologia Scheda da Compilare:", "Entry Category:"),
            [
                tr("Trattamento Fisioterapico / Prevenzione", "Physiotherapy Treatment / Prevention"),
                tr("Segnalazione Fastidio / Sovraccarico (Carico Adattato)", "Discomfort / Overload (Modified Load)"),
                tr("Infortunio / Stop Medico / Malattia", "Injury / Medical Stop / Illness"),
                tr("Logistica: Viaggio / Riposo Programmato", "Logistics: Travel / Scheduled Rest")
            ],
            horizontal=True,
            key="cal_tipo_scheda_sel"
        )

        with st.form("form_registro_medico"):
            st.markdown(f"##### Compilazione per **{atleta_sel}**")
            
            if "Trattamento" in modalita_scheda:
                c_f1, c_f2 = st.columns([1.5, 1.5])
                with c_f1:
                    f_data_inizio = st.date_input(tr("Data Trattamento:", "Treatment Date:"), value=today, key="reg_data_inizio_tratt")
                    f_data_fine = f_data_inizio
                with c_f2:
                    st_opts = ["DISPONIBILE", "LIMITATO", "INDISPONIBILE", "RIPOSO_VIAGGIO"]
                    f_status = st.selectbox(
                        tr("Status Operativo Atleta:", "Athlete Availability Status:"),
                        st_opts,
                        index=0,  # DISPONIBILE di default
                        key="reg_status_operativo_tratt"
                    )
            elif "Sovraccarico" in modalita_scheda:
                c_f1, c_f2, c_f3 = st.columns([1.3, 1.3, 1.4])
                with c_f1:
                    f_data_inizio = st.date_input(tr("Data Segnalazione:", "Report Date:"), value=today, key="reg_data_inizio_sovr")
                with c_f2:
                    st_opts = ["DISPONIBILE", "LIMITATO", "INDISPONIBILE"]
                    f_status = st.selectbox(
                        tr("Status Operativo Atleta:", "Athlete Availability Status:"),
                        st_opts,
                        index=0,  # DISPONIBILE di default quando il giocatore non si ferma
                        key="reg_status_operativo_sovr"
                    )
                with c_f3:
                    richiede_rientro = st.checkbox(
                        tr("Imposta Data Rientro", "Set Return Date"),
                        value=False,
                        help=tr("Spunta solo se l'atleta richiede un periodo di stop o recupero programmato con data di rientro",
                                "Check only if the athlete requires an extended stop/modified period with an expected return date"),
                        key="reg_chk_rientro_sovraccarico"
                    )
                    if richiede_rientro:
                        f_data_fine = st.date_input(tr("Data Rientro Prevista:", "Return Date:"), value=today, key="reg_data_fine_sovr")
                    else:
                        f_data_fine = f_data_inizio
            elif "Infortunio" in modalita_scheda:
                c_f1, c_f2, c_f3 = st.columns(3)
                with c_f1:
                    f_data_inizio = st.date_input(tr("Data Inizio Stop:", "Injury Start Date:"), value=today, key="reg_data_inizio_inf")
                with c_f2:
                    f_data_fine = st.date_input(tr("Data Rientro (o Fine Stop):", "Return Date (or End of Stop):"), value=today, key="reg_data_fine_inf")
                with c_f3:
                    st_opts = ["INDISPONIBILE", "LIMITATO", "DISPONIBILE"]
                    f_status = st.selectbox(
                        tr("Status Operativo Atleta:", "Athlete Availability Status:"),
                        st_opts,
                        index=0,  # INDISPONIBILE di default
                        key="reg_status_operativo_inf"
                    )
            else:  # Logistica
                c_f1, c_f2, c_f3 = st.columns(3)
                with c_f1:
                    f_data_inizio = st.date_input(tr("Data Inizio:", "Start Date:"), value=today, key="reg_data_inizio_log")
                with c_f2:
                    f_data_fine = st.date_input(tr("Data Fine:", "End Date:"), value=today, key="reg_data_fine_log")
                with c_f3:
                    st_opts = ["RIPOSO_VIAGGIO", "DISPONIBILE"]
                    f_status = st.selectbox(
                        tr("Status Operativo:", "Status:"),
                        st_opts,
                        index=0,
                        key="reg_status_operativo_log"
                    )

            # Campi specifici per modalità
            f_sottotipo = ""
            f_distretto = "Nessuno / Sistemico"
            f_lato = "N/A"
            f_meccanismo = "N/A"
            f_vas = 0
            f_tipo_scheda = "TRATTAMENTO"

            if "Trattamento" in modalita_scheda:
                f_tipo_scheda = "TRATTAMENTO"
                c_t1, c_t2, c_t3 = st.columns(3)
                with c_t1:
                    f_sottotipo = st.selectbox(tr("Tipo Trattamento Eseguito:", "Treatment Type:"), SOTTOTIPI_TRATTAMENTO, key="reg_sottotipo_t")
                with c_t2:
                    f_distretto = st.selectbox(tr("Distretto Anatomico:", "Anatomical District:"), DISTRETTI_ANATOMICI, key="reg_distretto_t")
                with c_t3:
                    f_lato = st.selectbox(tr("Lato Corporeo:", "Body Side:"), ["Destro", "Sinistro", "Bilaterale", "Centrale / Rachide", "N/A"], key="reg_lato_t")
                
                c_vas1, _ = st.columns([1.5, 3.5])
                with c_vas1:
                    f_vas = st.slider(tr("Scala Dolore Riferita (VAS 0-10):", "Pain Scale (VAS 0-10):"), 0, 10, 0, key="reg_vas_t")

            elif "Sovraccarico" in modalita_scheda:
                f_tipo_scheda = "SOVRACCARICO"
                c_s1, c_s2, c_s3 = st.columns(3)
                with c_s1:
                    f_sottotipo = st.selectbox(tr("Natura Sovraccarico:", "Nature of Overload:"), NATURA_INFORTUNIO, key="reg_sottotipo_s")
                with c_s2:
                    f_distretto = st.selectbox(tr("Distretto Anatomico:", "Anatomical District:"), DISTRETTI_ANATOMICI, key="reg_distretto_s")
                with c_s3:
                    f_lato = st.selectbox(tr("Lato Corporeo:", "Body Side:"), ["Destro", "Sinistro", "Bilaterale", "Centrale / Rachide", "N/A"], key="reg_lato_s")
                
                c_vas1, c_m1 = st.columns([1.5, 2.5])
                with c_vas1:
                    f_vas = st.slider(tr("Scala Dolore VAS (0-10):", "Pain VAS (0-10):"), 0, 10, 4, key="reg_vas_s")
                with c_m1:
                    f_meccanismo = st.selectbox(tr("Meccanismo Insorgenza:", "Onset Mechanism:"), MECCANISMI, key="reg_mecc_s")

            elif "Infortunio" in modalita_scheda:
                c_i1, c_i2, c_i3 = st.columns(3)
                with c_i1:
                    f_tipo_scheda = st.selectbox(tr("Classificazione Evento:", "Event Classification:"), ["INFORTUNIO", "MALATTIA"], key="reg_tipo_i")
                with c_i2:
                    f_sottotipo = st.selectbox(tr("Natura Lesione / Malattia:", "Nature of Injury:"), NATURA_INFORTUNIO, key="reg_sottotipo_i")
                with c_i3:
                    f_distretto = st.selectbox(tr("Distretto Anatomico:", "Anatomical District:"), DISTRETTI_ANATOMICI, key="reg_distretto_i")

                c_l1, c_m2, c_v2 = st.columns(3)
                with c_l1:
                    f_lato = st.selectbox(tr("Lato Corporeo:", "Body Side:"), ["Destro", "Sinistro", "Bilaterale", "Centrale / Rachide", "N/A"], key="reg_lato_i")
                with c_m2:
                    f_meccanismo = st.selectbox(tr("Meccanismo:", "Mechanism:"), MECCANISMI, key="reg_mecc_i")
                with c_v2:
                    f_vas = st.slider(tr("Scala Dolore VAS (0-10):", "Pain VAS (0-10):"), 0, 10, 6, key="reg_vas_i")

            else:
                f_tipo_scheda = "LOGISTICA"
                c_l1, c_l2 = st.columns(2)
                with c_l1:
                    f_sottotipo = st.selectbox(tr("Evento Logistico:", "Logistics Event:"), ["Giorno Off / Riposo Programmato", "Viaggio / Trasferta Torneo"], key="reg_sottotipo_l")
                with c_l2:
                    f_distretto = "Nessuno / Sistemico"

            # Indicazioni per lo Staff (campo evidenziato fondamentale per il coach)
            f_indicazioni = st.text_area(
                tr("Indicazioni Operative per Coach & Preparatore (RTP / Modifiche Carico):", 
                   "Operational Instructions for Coach & Fitness Staff (RTP / Modifications):"),
                placeholder=tr("Es. Ridurre volume servizio del 40%, evitare cambi di direzione massimali su arto Dx, focus mobilità anca pre-sessione...", 
                               "E.g. Reduce serve volume by 40%, avoid maximal COD on right limb, focus on hip mobility pre-session..."),
                key="reg_indicazioni"
            )

            # Note Cliniche di Dettaglio
            f_note_cliniche = st.text_area(
                tr("Note Cliniche, Test Obiettivi, Esami Strumentali & Dettaglio Seduta:", 
                   "Clinical Notes, Physical Tests, Imaging & Session Details:"),
                placeholder=tr("Es. Ecografia muscolare negativa per lesioni di grado elevato. Test isometrico forza con lieve deficit...", 
                               "E.g. Ultrasound negative for high-grade tears. Isometric force test shows mild deficit..."),
                key="reg_note_cliniche"
            )

            btn_submit_reg = st.form_submit_button(tr("Salva Voce nel Registro Clinico", "Save Entry in Clinical Log"), type="primary", use_container_width=True)

        if btn_submit_reg:
            if f_data_fine < f_data_inizio:
                st.error(tr("La data di fine non può essere precedente alla data di inizio.", "End date cannot be earlier than start date."))
            else:
                payload = {
                    "atleta_id": atleta_id_sel if not str(atleta_id_sel).startswith("mock-") else None,
                    "nome_giocatore": atleta_sel,
                    "data_inizio": str(f_data_inizio),
                    "data_fine": str(f_data_fine),
                    "tipo_scheda": f_tipo_scheda,
                    "status_operativo": f_status,
                    "sottotipo_evento": f_sottotipo,
                    "distretto_anatomico": f_distretto,
                    "lato": f_lato,
                    "meccanismo": f_meccanismo,
                    "scala_dolore_vas": f_vas,
                    "indicazioni_staff": f_indicazioni.strip(),
                    "note_cliniche_dettaglio": f_note_cliniche.strip(),
                    "autore_id": user.id if user else None,
                    "autore_nome": getattr(user, 'email', 'Staff')
                }
                
                # Se id atleta è mock (modalità demo locale), simuliamo il salvataggio in session_state
                if str(atleta_id_sel).startswith("mock-"):
                    if 'mock_registro_medico' not in st.session_state:
                        st.session_state['mock_registro_medico'] = []
                    payload['id'] = f"mock-reg-{len(st.session_state['mock_registro_medico']) + 1}"
                    st.session_state['mock_registro_medico'].insert(0, payload)
                    st.success(f"Voce registrata con successo nel diario clinico di {atleta_sel} (Modalità Demo)!")
                    st.rerun()
                else:
                    success, res_db = upsert_registro_medico(payload)
                    if success:
                        st.success(f"Voce registrata con successo nel diario clinico di {atleta_sel}!")
                        st.rerun()
                    else:
                        st.error(f"Errore durante il salvataggio su database: {res_db}")

        st.markdown("<hr style='margin:24px 0 16px 0;'>", unsafe_allow_html=True)

        # ---------------------------------------------------------------------
        # SEZIONE B: TABELLA STORICO REGISTRO CLINICO & ELIMINAZIONE
        # ---------------------------------------------------------------------
        st.markdown(
            f"<div style='display:flex; align-items:center; gap:8px; margin-bottom:12px;'>"
            f"<i class='bi bi-archive' style='color:#64748b; font-size:18px;'></i>"
            f"<span style='font-size:16px; font-weight:800; color:#0f172a; text-transform:uppercase; letter-spacing:0.5px;'>"
            f"{tr('Archivio Storico Registrazioni Cliniche & Logistiche', 'Clinical & Logistics Historical Registry')}"
            f"</span></div>",
            unsafe_allow_html=True
        )

        # Recupero record reali da Supabase o mock
        db_records = get_registro_medico(atleta_id=atleta_id_sel, nome_giocatore=atleta_sel)
        if str(atleta_id_sel).startswith("mock-"):
            mock_recs = st.session_state.get('mock_registro_medico', [])
            db_records = [r for r in mock_recs if r.get('nome_giocatore') == atleta_sel] + db_records

        if not db_records:
            st.info(f"Nessun evento clinico o logistico archiviato per {atleta_sel}.")
        else:
            c_flt1, c_flt2 = st.columns(2)
            with c_flt1:
                filtro_tipo = st.selectbox(
                    tr("Filtra per Tipologia:", "Filter by Type:"),
                    ["Tutte le Tipologie", "TRATTAMENTO", "SOVRACCARICO", "INFORTUNIO", "MALATTIA", "LOGISTICA"],
                    key="cal_flt_tipo_tbl"
                )
            with c_flt2:
                distretti_presenti = sorted(list(set(r.get('distretto_anatomico', 'Sistemico') for r in db_records)))
                filtro_distretto = st.selectbox(
                    tr("Filtra per Distretto:", "Filter by District:"),
                    ["Tutti i Distretti"] + distretti_presenti,
                    key="cal_flt_distr_tbl"
                )

            recs_filtrati = []
            for r in db_records:
                if filtro_tipo != "Tutte le Tipologie" and r.get('tipo_scheda') != filtro_tipo:
                    continue
                if filtro_distretto != "Tutti i Distretti" and r.get('distretto_anatomico') != filtro_distretto:
                    continue
                recs_filtrati.append(r)

            st.caption(f"{len(recs_filtrati)} registrazioni trovate.")

            # Tabella storico
            rows_reg_html = ""
            for r_item in recs_filtrati:
                r_id = r_item.get('id')
                r_st = r_item.get('status_operativo', 'DISPONIBILE')
                st_color = STATUS_COLORS.get(r_st, '#334155')
                d_range = f"{r_item.get('data_inizio')}" if r_item.get('data_inizio') == r_item.get('data_fine') else f"{r_item.get('data_inizio')} -> {r_item.get('data_fine')}"
                vas_val = f"VAS {r_item.get('scala_dolore_vas')}" if r_item.get('scala_dolore_vas') is not None else "-"
                
                rows_reg_html += (
                    f"<tr style='border-bottom:1px solid #f1f5f9; font-size:12px;'>"
                    f"<td style='padding:8px 10px; font-weight:700; color:#0f172a;'>{d_range}</td>"
                    f"<td style='padding:8px 10px;'><span style='background:#f8fafc; border:1px solid #cbd5e1; border-left:3px solid {st_color}; padding:2px 8px; border-radius:4px; font-weight:800; font-size:11px;'>{r_item.get('tipo_scheda')}</span></td>"
                    f"<td style='padding:8px 10px; font-weight:700;'>{r_item.get('distretto_anatomico', '-')} ({r_item.get('lato', '-')})</td>"
                    f"<td style='padding:8px 10px; color:#64748b;'>{r_item.get('sottotipo_evento', '-')}</td>"
                    f"<td style='padding:8px 10px; text-align:center; font-weight:700; color:#be123c;'>{vas_val}</td>"
                    f"<td style='padding:8px 10px; color:#334155; font-size:11.5px;'>{r_item.get('indicazioni_staff', '-') or '-'}</td>"
                    f"</tr>"
                )

            st.markdown(
                f"<div style='background:#ffffff; border:1px solid #e2e8f0; border-radius:10px; overflow-x:auto; margin-bottom:16px;'>"
                f"<table style='width:100%; border-collapse:collapse; font-family:\"Inter\",sans-serif;'>"
                f"<thead><tr style='background:#0f172a; color:#f8fafc; font-size:10.5px; text-transform:uppercase; letter-spacing:0.5px;'>"
                f"<th style='padding:8px 10px; text-align:left;'>Periodo</th>"
                f"<th style='padding:8px 10px; text-align:left;'>Categoria</th>"
                f"<th style='padding:8px 10px; text-align:left;'>Distretto (Lato)</th>"
                f"<th style='padding:8px 10px; text-align:left;'>Dettaglio Evento</th>"
                f"<th style='padding:8px 10px; text-align:center;'>Dolore</th>"
                f"<th style='padding:8px 10px; text-align:left;'>Indicazioni Staff</th>"
                f"</tr></thead><tbody>{rows_reg_html}</tbody></table></div>",
                unsafe_allow_html=True
            )

            # Opzione di duplicazione rapida trattamento (One-Click Follow-Up)
            trattamenti_esistenti = [r for r in db_records if r.get('tipo_scheda') in ('TRATTAMENTO', 'SOVRACCARICO')]
            if trattamenti_esistenti:
                with st.expander(tr("Duplica / Ripeti Trattamento Fisioterapico (One-Click Follow-Up)", "Duplicate / Repeat Treatment (One-Click Follow-Up)")):
                    dict_dup_opts = {f"[{r.get('data_inizio')}] {r.get('tipo_scheda')}: {r.get('sottotipo_evento', '-')} - {r.get('distretto_anatomico', '-')} ({r.get('lato', '-')}) (ID: {str(r.get('id'))[:8]})": r for r in trattamenti_esistenti}
                    del_dup_keys = list(dict_dup_opts.keys())
                    if 'cal_sel_dup_rec' in st.session_state and st.session_state['cal_sel_dup_rec'] not in del_dup_keys:
                        st.session_state.pop('cal_sel_dup_rec', None)
                    sel_dup_label = st.selectbox(tr("Seleziona Voce da Duplicare:", "Select Entry to Duplicate:"), del_dup_keys, key="cal_sel_dup_rec")
                    target_rec = dict_dup_opts.get(sel_dup_label)
                    
                    c_dp1, c_dp2 = st.columns([1.5, 2.5])
                    with c_dp1:
                        data_ripetizione = st.date_input(tr("Nuova Data Esecuzione:", "New Execution Date:"), value=today, key="cal_data_ripetizione")
                    with c_dp2:
                        st.markdown("<div style='height:26px;'></div>", unsafe_allow_html=True)
                        btn_do_dup = st.button(tr("Duplica in Data Selezionata", "Duplicate on Selected Date"), type="primary", key="btn_exec_dup_t")

                    if btn_do_dup and target_rec:
                        new_pay = dict(target_rec)
                        new_pay.pop('id', None)
                        new_pay['data_inizio'] = str(data_ripetizione)
                        new_pay['data_fine'] = str(data_ripetizione)
                        new_pay['atleta_id'] = atleta_id_sel if not str(atleta_id_sel).startswith("mock-") else None
                        new_pay['nome_giocatore'] = atleta_sel
                        if str(atleta_id_sel).startswith("mock-"):
                            if 'mock_registro_medico' not in st.session_state:
                                st.session_state['mock_registro_medico'] = []
                            new_pay['id'] = f"mock-reg-{len(st.session_state['mock_registro_medico']) + 1}"
                            st.session_state['mock_registro_medico'].insert(0, new_pay)
                            st.success(f"Trattamento duplicato con successo per il {data_ripetizione}!")
                            st.rerun()
                        else:
                            succ_d, res_db_d = upsert_registro_medico(new_pay)
                            if succ_d:
                                st.success(f"Trattamento duplicato con successo per il {data_ripetizione}!")
                                st.rerun()
                            else:
                                st.error(f"Errore duplicazione: {res_db_d}")

            # Opzione di eliminazione record
            with st.expander(tr("Gestione / Eliminazione Registrazione", "Manage / Delete Entry")):
                dict_select_del = {f"[{r.get('data_inizio')}] {r.get('tipo_scheda')} - {r.get('distretto_anatomico')} (ID: {str(r.get('id'))[:8]})": r.get('id') for r in recs_filtrati}
                del_opts = list(dict_select_del.keys())
                if 'cal_sel_del_rec' in st.session_state and st.session_state['cal_sel_del_rec'] not in del_opts:
                    st.session_state.pop('cal_sel_del_rec', None)
                rec_del_label = st.selectbox(tr("Seleziona Voce da Eliminare:", "Select Entry to Delete:"), del_opts, key="cal_sel_del_rec")
                id_to_del = dict_select_del.get(rec_del_label)
                
                if st.button(tr("Elimina Definitivamente Registrazione", "Permanently Delete Entry"), type="secondary", key="btn_del_reg_submit"):
                    if str(id_to_del).startswith("mock-"):
                        if 'mock_registro_medico' in st.session_state:
                            st.session_state['mock_registro_medico'] = [r for r in st.session_state['mock_registro_medico'] if r.get('id') != id_to_del]
                        st.success("Registrazione demo eliminata con successo!")
                        st.rerun()
                    else:
                        succ = delete_registro_medico(id_to_del)
                        if succ:
                            st.success("Registrazione eliminata dal database!")
                            st.rerun()
                        else:
                            st.error("Errore durante l'eliminazione del record.")


    # =========================================================================
    # TAB 2: ALLENAMENTI GYM E FISICO
    # =========================================================================
    elif active_et_tab == lbl_et_2:
        render_allenamenti_gym_fisico(t, atleta_sel=atleta_sel, atleta_id_sel=atleta_id_sel, key_prefix="et_gym")
