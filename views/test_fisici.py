import datetime
import io
import os
import re
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import streamlit as st

from config import (
    tr,
    render_page_header,
    render_action_bar,
    render_tab_navigation,
)
from pdf_generator import (
    crea_pdf_report_test_fisici,
    slugify_name,
)
from utils import (
    supabase,
    supabase_admin,
    load_local_database,
    get_atleta_dettagli_per_utente,
    card_kpi,
    calcola_asimmetria_dx_sx,
    calcola_baseline_swc,
    valuta_readiness_swc,
    valuta_direzione_delta,
    valuta_readiness_test,
    calcola_formule_derivate_test,
    calcola_indici_clinici_spalla,
    calcola_indici_cross_test,
    get_catalogo_protocolli,
    get_sessioni_test,
    upsert_sessione_test,
    delete_sessione_test,
    update_sessione_test_data,
    update_sessione_test_completa,
    upsert_protocollo_custom,
    delete_protocollo_custom,
    render_athlete_hero_strip,
)


def render_test_fisici(t):
    render_page_header(
        tr("Test Fisici, Neuromuscolari & ROM", "Physical, Neuromuscular & ROM Tests"),
        tr("Valutazione longitudinale, analisi asimmetrie bilaterali e monitoraggio neuromuscolare", 
           "Longitudinal evaluation, bilateral asymmetries and neuromuscular monitoring"),
        "PHYSICAL & NEUROMUSCULAR ASSESSMENT"
    )

    user = st.session_state.get('user')
    user_role = st.session_state.get('role', 'Atleta')
    is_admin = (user_role in ['Super-Admin', 'Admin'])
    is_coach = (user_role in ['Staff', 'Coach', 'Fisio / Medico', 'Preparatore', 'Preparatore Fisico', 'Super-Admin', 'Admin'] or is_admin or user_role != 'Atleta')

    # -------------------------------------------------------------------------
    # 1. RECUPERO ATLETI IN BASE AL RUOLO (RLS)
    # -------------------------------------------------------------------------
    dict_atleti = {}  # {nome_completo: id}
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
            # Atleta loggato: vede solo se stesso
            atl_info = get_atleta_dettagli_per_utente(user.id) if user else None
            if atl_info:
                dict_atleti[atl_info['nome_completo']] = atl_info['id']
    except Exception:
        pass

    # Integra sempre gli atleti del database GPS locale (per garantire sincronia con il selettore globale)
    if is_admin or is_coach or not dict_atleti:
        df_local = load_local_database()
        if not df_local.empty and 'Players' in df_local.columns:
            for p in sorted(df_local['Players'].dropna().unique()):
                p_str = str(p).strip()
                if p_str and p_str not in dict_atleti:
                    dict_atleti[p_str] = f"mock-{p_str}"

    if not dict_atleti:
        dict_atleti["Atleta Demo"] = "mock-atleta-demo"

    # Atleta Attivo (ereditato dal Selettore Globale nella Sidebar)
    atleta_nomi = list(dict_atleti.keys())
    glob_ath = st.session_state.get('selected_athlete')
    if glob_ath in atleta_nomi:
        atleta_sel = glob_ath
    elif 'test_fisici_atleta_sel' in st.session_state and st.session_state['test_fisici_atleta_sel'] in atleta_nomi:
        atleta_sel = st.session_state['test_fisici_atleta_sel']
    else:
        atleta_sel = atleta_nomi[0] if atleta_nomi else "prova uno"
    atleta_id_sel = dict_atleti.get(atleta_sel)

    # -------------------------------------------------------------------------
    # 2. CARICAMENTO PROTOCOLLI E SESSIONI ATLETA
    # -------------------------------------------------------------------------
    catalogo = get_catalogo_protocolli(user.id if user else None)
    protocolli_map = {}
    for p in catalogo:
        if 'id' in p:
            protocolli_map[p['id']] = p
        if 'codice_univoco' in p:
            protocolli_map[p['codice_univoco']] = p
    macro_tutte = sorted(list(set(p.get('macro_area') for p in catalogo if p.get('macro_area'))))
    if not macro_tutte:
        macro_tutte = [
            "Pedane di Forza (VALD ForceDecks / Salto & IMTP)",
            "Dinamometria Isometrica (VALD DynaMo Forza)",
            "Mobilità & Range of Motion (VALD DynaMo ROM)",
            "M0V3 & Campo (Velocità, COD, Metabolico)",
            "Forza Eccentrica & Ischiocrurali (VALD NordBord)",
            "Antropometria & Custom"
        ]
    sessioni_raw = get_sessioni_test(
        atleta_id=atleta_id_sel if not str(atleta_id_sel).startswith("mock-") else None,
        atleta_nome=atleta_sel
    )

    # Filtraggio sessioni per atleta selezionato (anche per matching con nome giocatore)
    sessioni_atleta = []
    for s in sessioni_raw:
        s_ath_id = str(s.get('atleta_id', ''))
        s_name = str(s.get('nome_giocatore', s.get('atleta', ''))).lower().strip()
        target_name = atleta_sel.lower().strip()
        if (
            (atleta_id_sel and not str(atleta_id_sel).startswith("mock-") and s_ath_id == str(atleta_id_sel))
            or (s_name and (s_name == target_name or target_name in s_name or s_name in target_name))
            or not atleta_id_sel
        ):
            p_obj = s.get('catalogo_protocolli') or protocolli_map.get(s.get('protocollo_id')) or protocolli_map.get(s.get('codice_univoco'))
            if p_obj:
                s_copy = dict(s)
                s_copy['protocollo_info'] = p_obj
                sessioni_atleta.append(s_copy)

    # Striscia Compatta Identità Atleta MOV3
    lbl_t_sess = f"{len(sessioni_atleta)} {tr('sessioni test registrate', 'recorded test sessions')}"
    render_athlete_hero_strip(atleta_sel, extra_badges=[lbl_t_sess])

    # -------------------------------------------------------------------------
    # 3. TAB STRUTTURA
    # Action Bar con Export PDF
    opzioni_pdf = {"report_test": tr("Report Test Fisici (PDF)", "Physical Tests Report (PDF)")}
    slug_atl = slugify_name(atleta_sel)
    data_ultimo_test = str(sessioni_atleta[0].get('data', 'N/D')) if sessioni_atleta else tr("Nessuna", "None")
    render_action_bar(
        meta_items=[
            (tr("Atleta Selezionato", "Selected Athlete"), atleta_sel),
            (tr("Sessioni Totali", "Total Sessions"), str(len(sessioni_atleta))),
            (tr("Data Ultimo Test", "Last Test Date"), data_ultimo_test),
        ],
        pdf_options=opzioni_pdf,
        pdf_key=f"pdf_test_fisici_{slug_atl}",
        generate_fn=lambda _: crea_pdf_report_test_fisici(atleta_sel, sessioni_atleta, catalogo=catalogo),
        filename_fn=lambda _: f"M0V3_Test_Fisici_{slug_atl}.pdf"
    )

    # -------------------------------------------------------------------------
    # 3. TAB STRUTTURA DINAMICA BASATA SU PERMESSI
    # -------------------------------------------------------------------------
    tab_defs = [
        ("panoramica", "Panoramica Test Atleta", tr("Panoramica Test Atleta", "Athlete Tests Overview"), False),
        ("deep_dive", "Deep-Dive per Test", tr("Deep-Dive per Test", "Deep-Dive Test Analysis"), False),
        ("executive", "Executive Summary & Readiness", tr("Executive Summary & Readiness", "Executive Summary & Readiness"), False),
        ("confronti", "Confronti", tr("Confronti", "Roster Comparisons"), False),
        ("inserimento", "Gestione & Inserimento Test", tr("Gestione & Inserimento Test", "Test Management & Data Entry"), False),
        ("builder", "Costruttore Test Custom", tr("Costruttore Test Custom", "Custom Test Builder"), True),
    ]

    moduli_utente = st.session_state.get('moduli_report')
    def _is_tab_permitted(cat_name):
        if is_admin or moduli_utente is None:
            return True
        clean_cat = cat_name.lower().strip()
        for m in moduli_utente:
            clean_m = re.sub(r'[\U00010000-\U0010ffff\u2700-\u27bf]', '', str(m)).lower().strip()
            if clean_cat in clean_m or clean_m in clean_cat:
                return True
        return False

    active_tab_defs = []
    for tab_id, cat_name, tab_label, coach_only in tab_defs:
        if coach_only and not is_coach:
            continue
        if _is_tab_permitted(cat_name):
            active_tab_defs.append((tab_id, cat_name, tab_label))

    if not active_tab_defs:
        st.warning(tr("Non hai i permessi per visualizzare le schede di questa sezione.", "You do not have permission to view this section's tabs."))
        return

    active_tf_lbl = render_tab_navigation([t[2] for t in active_tab_defs], key="nav_test_fisici_master")
    active_tf_id = next((t[0] for t in active_tab_defs if t[2] == active_tf_lbl), active_tab_defs[0][0])
    tab_map = {active_tf_id: st.container()}

    def _parse_s_date(d_val):
        if not d_val:
            return pd.Timestamp.min
        dt = pd.to_datetime(d_val, dayfirst=True, errors='coerce')
        if pd.isna(dt):
            dt = pd.to_datetime(d_val, errors='coerce')
        return dt if pd.notna(dt) else pd.Timestamp.min

    # =========================================================================
    # TAB 0: PANORAMICA TEST ATLETA (Macro Card & Trend Sparkline M0V3)
    # =========================================================================
    if "panoramica" in tab_map:
        with tab_map["panoramica"]:
            st.markdown(
                f"<div style='display:flex; align-items:center; justify-content:space-between; margin-bottom:14px;'>"
                f"<div style='display:flex; align-items:center; gap:8px;'>"
                f"<i class='bi bi-grid-1x2-fill' style='color:#0ea5e9; font-size:20px;'></i>"
                f"<span style='font-size:16px; font-weight:800; color:#0f172a; text-transform:uppercase; letter-spacing:0.5px;'>"
                f"{tr('Panoramica Test & Trend Longitudinali — ', 'Tests Overview & Longitudinal Trends — ')}{atleta_sel}"
                f"</span></div>"
                f"</div>",
                unsafe_allow_html=True
            )

            if not sessioni_atleta:
                st.info(tr(
                    f"Nessuna sessione di test registrata nello storico per {atleta_sel}. "
                    f"Puoi inserire nuove misurazioni nella scheda 'Inserimento & Storico Misure'.",
                    f"No recorded test sessions found for {atleta_sel}. "
                    f"You can record new test measurements in the 'Data Entry & History' tab."
                ))
            else:
                test_groups = {}
                for s in sessioni_atleta:
                    p_info = s.get('protocollo_info') or protocolli_map.get(s.get('protocollo_id')) or {}
                    cod = p_info.get('codice_univoco') or s.get('protocollo_id') or p_info.get('nome_protocollo')
                    if not cod:
                        continue
                    if cod not in test_groups:
                        test_groups[cod] = {
                            'codice': cod,
                            'protocollo_info': p_info,
                            'nome': p_info.get('nome_protocollo', str(cod)),
                            'macro_area': p_info.get('macro_area', tr('Generale', 'General')),
                            'strumento': p_info.get('strumento', 'N/D'),
                            'sessions': []
                        }
                    test_groups[cod]['sessions'].append(s)

                elaborated_tests = []
                for cod, t_data in test_groups.items():
                    p_info = t_data['protocollo_info']
                    schema = p_info.get('schema_metriche', []) or []
                    t_sessions = sorted(t_data['sessions'], key=lambda x: _parse_s_date(x.get('data')))
                    
                    chosen_metric = None
                    for m in schema:
                        k = m.get('key')
                        lat = m.get('laterality', 'BILATERAL')
                        has_val = any(
                            (k in s.get('valori', {})) or (lat == 'UNILATERAL' and (f"{k}_dx" in s.get('valori', {}) or f"{k}_sx" in s.get('valori', {})))
                            for s in t_sessions if isinstance(s.get('valori'), dict)
                        )
                        if has_val:
                            chosen_metric = m
                            break
                    if not chosen_metric:
                        if schema:
                            chosen_metric = schema[0]
                        else:
                            chosen_metric = {'key': 'valore', 'label': tr('Valore', 'Value'), 'unit': '', 'direction': 'HIGHER_IS_BETTER', 'laterality': 'BILATERAL'}
                    
                    k = chosen_metric.get('key')
                    m_label = chosen_metric.get('label', k)
                    unit = chosen_metric.get('unit', '')
                    direction = chosen_metric.get('direction', 'HIGHER_IS_BETTER')
                    is_hib = (direction != 'LOWER_IS_BETTER')
                    lat = chosen_metric.get('laterality', 'BILATERAL')
                    
                    points = []
                    for s in t_sessions:
                        d_raw = s.get('data')
                        dt_obj = _parse_s_date(d_raw)
                        d_fmt = dt_obj.strftime('%d/%m/%Y') if dt_obj != pd.Timestamp.min else str(d_raw)
                        v_dict = s.get('valori', {}) or {}
                        
                        val_num = None
                        if lat == 'UNILATERAL':
                            v_dx = v_dict.get(f"{k}_dx")
                            v_sx = v_dict.get(f"{k}_sx")
                            cand = []
                            for vc in (v_dx, v_sx):
                                try:
                                    if vc is not None and not pd.isna(vc):
                                        cand.append(float(vc))
                                except (ValueError, TypeError):
                                    pass
                            if cand:
                                val_num = max(cand) if is_hib else min(cand)
                            elif k in v_dict and v_dict[k] is not None:
                                try:
                                    val_num = float(v_dict[k])
                                except (ValueError, TypeError):
                                    pass
                        else:
                            if k in v_dict and v_dict[k] is not None:
                                try:
                                    val_num = float(v_dict[k])
                                except (ValueError, TypeError):
                                    pass
                        
                        if val_num is not None:
                            points.append({
                                'dt': dt_obj,
                                'date_str': d_fmt,
                                'value': val_num
                            })
                    
                    if not points:
                        continue
                    
                    n_count = len(points)
                    if is_hib:
                        best_item = max(points, key=lambda p: p['value'])
                    else:
                        best_item = min(points, key=lambda p: p['value'])
                    
                    best_val = best_item['value']
                    best_date = best_item['date_str']
                    
                    last_item = points[-1]
                    last_val = last_item['value']
                    last_date = last_item['date_str']
                    
                    if is_hib:
                        pct_max = (last_val / best_val * 100.0) if best_val > 0 else 100.0
                        delta_pct = ((last_val - best_val) / best_val * 100.0) if best_val > 0 else 0.0
                    else:
                        pct_max = (best_val / last_val * 100.0) if last_val > 0 else 100.0
                        delta_pct = ((best_val - last_val) / best_val * 100.0) if best_val > 0 else 0.0
                    
                    elaborated_tests.append({
                        'codice': cod,
                        'nome': t_data['nome'],
                        'macro_area': t_data['macro_area'],
                        'strumento': t_data['strumento'],
                        'metric_key': k,
                        'metric_label': m_label,
                        'unit': unit,
                        'direction': direction,
                        'is_hib': is_hib,
                        'n_count': n_count,
                        'best_val': best_val,
                        'best_date': best_date,
                        'last_val': last_val,
                        'last_date': last_date,
                        'pct_max': pct_max,
                        'delta_pct': delta_pct,
                        'points': points
                    })

                tot_test_types = len(elaborated_tests)
                tot_measurements = sum(t['n_count'] for t in elaborated_tests)
                avg_pct_pb = (sum(t['pct_max'] for t in elaborated_tests) / tot_test_types) if tot_test_types > 0 else 100.0
                recent_test_date = max((t['points'][-1]['dt'] for t in elaborated_tests), default=None)
                recent_test_str = recent_test_date.strftime('%d/%m/%Y') if recent_test_date and recent_test_date != pd.Timestamp.min else tr("N/D", "N/A")
                
                # 4 KPI Cards in alto
                col_k1, col_k2, col_k3, col_k4 = st.columns(4)
                with col_k1:
                    st.markdown(card_kpi(tr("Protocolli Svolti", "Protocols Performed"), f"{tot_test_types}", tr("Test differenti", "Unique test types"), "#0ea5e9"), unsafe_allow_html=True)
                with col_k2:
                    st.markdown(card_kpi(tr("Rilevazioni Storiche", "Total Assessments"), f"{tot_measurements}", tr("Sessioni totali", "Total sessions"), "#10b981"), unsafe_allow_html=True)
                with col_k3:
                    st.markdown(card_kpi(tr("Ultima Sessione Test", "Last Test Session"), recent_test_str, tr("Data più recente", "Most recent date"), "#8b5cf6"), unsafe_allow_html=True)
                with col_k4:
                    col_avg_kpi = "#10b981" if avg_pct_pb >= 95 else ("#f59e0b" if avg_pct_pb >= 90 else "#ef4444")
                    st.markdown(card_kpi(tr("Indice Medio vs PB", "Mean Index vs PB"), f"{avg_pct_pb:.1f}%", tr("Readiness rispetto ai PB", "Readiness relative to PBs"), col_avg_kpi), unsafe_allow_html=True)

                st.markdown("<div style='height: 14px;'></div>", unsafe_allow_html=True)
                col_f1, col_f2, col_f3 = st.columns([1.5, 1.5, 1.2])
                
                all_macros = sorted(list(set(t['macro_area'] for t in elaborated_tests)))
                lbl_all_macro = tr("Tutte le Macro-Aree", "All Macro-Areas")
                with col_f1:
                    sel_macro_filter = st.selectbox(
                        tr("Filtra per Categoria / Strumento", "Filter by Category / Tool"),
                        [lbl_all_macro] + all_macros,
                        key="panoramica_sel_macro"
                    )
                with col_f2:
                    search_query = st.text_input(
                        tr("Cerca Test per Nome", "Search Test by Name"),
                        placeholder=tr("es. CMJ, Sprint, IMTP...", "e.g. CMJ, Sprint, IMTP..."),
                        key="panoramica_search_query"
                    )
                with col_f3:
                    st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)
                    vista_mode = st.radio(
                        tr("Layout", "Layout"),
                        [tr("Macro Card con Grafico", "Macro Cards with Chart"), tr("Tabella M0V3", "M0V3 Table")],
                        horizontal=True,
                        key="panoramica_vista_mode"
                    )

                filtered_tests = elaborated_tests
                if sel_macro_filter != lbl_all_macro:
                    filtered_tests = [t for t in filtered_tests if t['macro_area'] == sel_macro_filter]
                if search_query.strip():
                    q = search_query.strip().lower()
                    filtered_tests = [t for t in filtered_tests if (q in t['nome'].lower() or q in t['metric_label'].lower())]

                if not filtered_tests:
                    st.warning(tr("Nessun test corrisponde ai filtri di ricerca impostati.", "No tests match the current filter criteria."))
                elif vista_mode == tr("Macro Card con Grafico", "Macro Cards with Chart"):
                    for t_idx, t_item in enumerate(filtered_tests):
                        pct_v = t_item['pct_max']
                        d_pct = t_item['delta_pct']
                        
                        # Badge semaforico
                        if pct_v >= 98.0:
                            bg_b, fg_b, border_col = "#dcfce7", "#15803d", "#10b981"
                            txt_b = f"{pct_v:.1f}% PB" if pct_v < 99.9 else "PB 100%"
                        elif pct_v >= 92.0:
                            bg_b, fg_b, border_col = "#e0f2fe", "#0369a1", "#0284c7"
                            txt_b = f"{pct_v:.1f}% PB ({d_pct:+.1f}%)"
                        elif pct_v >= 85.0:
                            bg_b, fg_b, border_col = "#fef3c7", "#b45309", "#f59e0b"
                            txt_b = f"{pct_v:.1f}% PB ({d_pct:+.1f}%)"
                        else:
                            bg_b, fg_b, border_col = "#fee2e2", "#b91c1c", "#ef4444"
                            txt_b = f"{pct_v:.1f}% PB ({d_pct:+.1f}%)"

                        badge_html = f"<span style='background:{bg_b}; color:{fg_b}; font-size:11px; font-weight:800; padding:2px 7px; border-radius:5px;'>{txt_b}</span>"

                        with st.container(border=True):
                            col_info, col_chart = st.columns([1.35, 1.15])
                            with col_info:
                                st.markdown(f"""
                                <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:8px;">
                                    <div>
                                        <div style="font-size:16px; font-weight:800; color:#0f172a; letter-spacing:0.3px;">
                                            <i class="bi bi-clipboard-pulse" style="color:#0ea5e9; margin-right:6px;"></i>{t_item['nome']}
                                        </div>
                                        <div style="margin-top:4px; display:flex; gap:6px; flex-wrap:wrap; align-items:center;">
                                            <span style="background:#e0f2fe; color:#0369a1; font-size:10px; font-weight:800; padding:2px 7px; border-radius:4px; text-transform:uppercase;">{t_item['macro_area']}</span>
                                            <span style="background:#f1f5f9; color:#475569; font-size:10px; font-weight:700; padding:2px 7px; border-radius:4px;"><i class="bi bi-tools"></i> {t_item['strumento']}</span>
                                            <span style="font-size:11px; color:#64748b; font-weight:600;">Metrica: <b>{t_item['metric_label']}</b> ({t_item['unit']})</span>
                                        </div>
                                    </div>
                                    <span style="background:#f8fafc; border:1px solid #cbd5e1; color:#0f172a; font-weight:800; font-size:11px; padding:3px 9px; border-radius:6px; white-space:nowrap;">
                                        <i class="bi bi-arrow-repeat" style="color:#0ea5e9;"></i> {t_item['n_count']} {tr('Rilevazioni', 'Tests')}
                                    </span>
                                </div>
                                <div style="display:grid; grid-template-columns: 1fr 1fr; gap:10px; margin-top:10px;">
                                    <div style="background:#fffbeb; border:1px solid #fef3c7; border-left:4px solid #f59e0b; border-radius:8px; padding:9px 12px;">
                                        <div style="font-size:10px; font-weight:800; color:#b45309; text-transform:uppercase; letter-spacing:0.5px;">
                                            <i class="bi bi-trophy-fill" style="color:#f59e0b; margin-right:4px;"></i>BEST ATLETA (PB)
                                        </div>
                                        <div style="font-size:20px; font-weight:900; color:#0f172a; margin-top:2px;">
                                            {t_item['best_val']:.2f} <span style="font-size:12px; font-weight:700; color:#64748b;">{t_item['unit']}</span>
                                        </div>
                                        <div style="font-size:10.5px; color:#78350f; margin-top:3px; font-weight:600;">
                                            <i class="bi bi-calendar-event"></i> {t_item['best_date']}
                                        </div>
                                    </div>
                                    <div style="background:#f8fafc; border:1px solid #e2e8f0; border-left:4px solid {border_col}; border-radius:8px; padding:9px 12px;">
                                        <div style="display:flex; justify-content:space-between; align-items:center;">
                                            <span style="font-size:10px; font-weight:800; color:#475569; text-transform:uppercase; letter-spacing:0.5px;">
                                                <i class="bi bi-calendar-check-fill" style="color:#0ea5e9; margin-right:4px;"></i>ULTIMO TEST
                                            </span>
                                            {badge_html}
                                        </div>
                                        <div style="font-size:20px; font-weight:900; color:#0f172a; margin-top:2px;">
                                            {t_item['last_val']:.2f} <span style="font-size:12px; font-weight:700; color:#64748b;">{t_item['unit']}</span>
                                        </div>
                                        <div style="font-size:10.5px; color:#64748b; margin-top:3px; font-weight:600;">
                                            <i class="bi bi-calendar"></i> {t_item['last_date']}
                                        </div>
                                    </div>
                                </div>
                                """, unsafe_allow_html=True)
                            
                            with col_chart:
                                pts = t_item['points']
                                x_pts = [p['date_str'] for p in pts]
                                y_pts = [p['value'] for p in pts]
                                
                                fig_sp = go.Figure()
                                fig_sp.add_trace(go.Scatter(
                                    x=x_pts,
                                    y=y_pts,
                                    mode="lines+markers",
                                    line=dict(color="#0ea5e9", width=3, shape="spline"),
                                    marker=dict(size=8, color="#0284c7", line=dict(width=2, color="#ffffff")),
                                    hovertemplate=f"<b>%{{x}}</b><br>{t_item['metric_label']}: <b>%{{y:.2f}} {t_item['unit']}</b><extra></extra>",
                                    name=t_item['metric_label']
                                ))
                                
                                b_val = t_item['best_val']
                                fig_sp.add_hline(
                                    y=b_val,
                                    line_dash="dot",
                                    line_color="#f59e0b",
                                    line_width=1.5,
                                    annotation_text=f"PB: {b_val:.2f}",
                                    annotation_position="top right",
                                    annotation_font=dict(size=9.5, color="#b45309", family="Inter")
                                )
                                
                                y_min_p = min(y_pts + [b_val])
                                y_max_p = max(y_pts + [b_val])
                                diff_y = y_max_p - y_min_p
                                pad_y = diff_y * 0.22 if diff_y > 0 else (abs(y_max_p) * 0.15 or 1.0)
                                
                                fig_sp.update_layout(
                                    height=150,
                                    margin=dict(l=10, r=10, t=16, b=26),
                                    xaxis=dict(showgrid=False, tickfont=dict(size=9.5, color="#64748b"), tickangle=0),
                                    yaxis=dict(showgrid=True, gridcolor="#f1f5f9", range=[y_min_p - pad_y, y_max_p + pad_y], tickfont=dict(size=9.5, color="#64748b")),
                                    plot_bgcolor="rgba(0,0,0,0)",
                                    paper_bgcolor="rgba(0,0,0,0)",
                                    showlegend=False
                                )
                                st.markdown(f"""
                                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:2px;">
                                    <span style="font-size:10.5px; font-weight:800; color:#334155; text-transform:uppercase; letter-spacing:0.5px;">
                                        <i class="bi bi-graph-up" style="color:#0ea5e9; margin-right:4px;"></i>Trend Cronologico
                                    </span>
                                    <span style="font-size:10px; color:#64748b; font-weight:600;">
                                        {x_pts[0]} → {x_pts[-1]}
                                    </span>
                                </div>
                                """, unsafe_allow_html=True)
                                st.plotly_chart(fig_sp, use_container_width=True, key=f"sp_{t_item['codice']}_{t_idx}")
                else:
                    # Tabella Dettagliata M0V3
                    th_p = tr("Test & Metrica", "Test & Metric")
                    th_c = tr("Macro-Area & Tool", "Macro-Area & Tool")
                    th_n = tr("N° Test", "Test Count")
                    th_b = tr("Personal Best (Data)", "Personal Best (Date)")
                    th_l = tr("Ultima Rilevazione (Data)", "Latest Test (Date)")
                    th_pct = tr("% del Massimo", "% of Max")
                    th_d = tr("Delta vs PB", "Delta vs PB")
                    th_st = tr("Stato", "Status")

                    table_rows = []
                    for t_item in filtered_tests:
                        pct_v = t_item['pct_max']
                        d_pct = t_item['delta_pct']
                        if pct_v >= 98.0:
                            bg_b, fg_b, lbl_st = "#dcfce7", "#15803d", tr("Record / Ottimale", "Record / Optimal")
                        elif pct_v >= 92.0:
                            bg_b, fg_b, lbl_st = "#e0f2fe", "#0369a1", tr("In Target", "In Target")
                        elif pct_v >= 85.0:
                            bg_b, fg_b, lbl_st = "#fef3c7", "#b45309", tr("Lieve Calo", "Slight Drop")
                        else:
                            bg_b, fg_b, lbl_st = "#fee2e2", "#b91c1c", tr("Sotto Soglia", "Sub-threshold")

                        badge_st = f"<span style='background:{bg_b}; color:{fg_b}; font-size:11px; font-weight:800; padding:3px 8px; border-radius:5px;'>{lbl_st}</span>"

                        table_rows.append(
                            f"<tr style='border-bottom: 1px solid #f1f5f9;'>"
                            f"<td style='padding:12px 14px;'><div style='font-weight:700; color:#0f172a;'>{t_item['nome']}</div><div style='font-size:11px; color:#64748b;'>{t_item['metric_label']} ({t_item['unit']})</div></td>"
                            f"<td style='padding:12px 14px;'><span style='background:#f1f5f9; color:#475569; font-size:10px; font-weight:700; padding:2px 7px; border-radius:4px;'>{t_item['macro_area']}</span><div style='font-size:10.5px; color:#64748b; margin-top:2px;'>{t_item['strumento']}</div></td>"
                            f"<td style='padding:12px 14px; text-align:center; font-weight:800; color:#0284c7;'>{t_item['n_count']}</td>"
                            f"<td style='padding:12px 14px; text-align:center;'><div style='font-weight:900; color:#0f172a;'>{t_item['best_val']:.2f} {t_item['unit']}</div><div style='font-size:10.5px; color:#78350f;'>{t_item['best_date']}</div></td>"
                            f"<td style='padding:12px 14px; text-align:center;'><div style='font-weight:900; color:#0f172a;'>{t_item['last_val']:.2f} {t_item['unit']}</div><div style='font-size:10.5px; color:#64748b;'>{t_item['last_date']}</div></td>"
                            f"<td style='padding:12px 14px; text-align:center; font-weight:800; color:#0f172a;'>{pct_v:.1f}%</td>"
                            f"<td style='padding:12px 14px; text-align:center; font-weight:800; color:{fg_b};'>{d_pct:+.1f}%</td>"
                            f"<td style='padding:12px 14px; text-align:center;'>{badge_st}</td>"
                            f"</tr>"
                        )

                    html_table_m0v3 = (
                        "<div style='background:white; border-radius:12px; border:1px solid #e2e8f0; overflow:hidden; box-shadow:0 2px 8px -1px rgba(15,23,42,0.05); margin-top:10px; font-family:\"Inter\",sans-serif;'>"
                        "<table style='width:100%; border-collapse:collapse;'>"
                        "<tr style='background-color:#f8fafc; border-bottom:2px solid #e2e8f0;'>"
                        f"<th style='text-align:left; padding:12px 14px; font-size:11px; font-weight:700; color:#64748b; text-transform:uppercase;'>{th_p}</th>"
                        f"<th style='text-align:left; padding:12px 14px; font-size:11px; font-weight:700; color:#64748b; text-transform:uppercase;'>{th_c}</th>"
                        f"<th style='text-align:center; padding:12px 14px; font-size:11px; font-weight:700; color:#64748b; text-transform:uppercase;'>{th_n}</th>"
                        f"<th style='text-align:center; padding:12px 14px; font-size:11px; font-weight:700; color:#64748b; text-transform:uppercase;'>{th_b}</th>"
                        f"<th style='text-align:center; padding:12px 14px; font-size:11px; font-weight:700; color:#64748b; text-transform:uppercase;'>{th_l}</th>"
                        f"<th style='text-align:center; padding:12px 14px; font-size:11px; font-weight:800; color:#0ea5e9; text-transform:uppercase;'>{th_pct}</th>"
                        f"<th style='text-align:center; padding:12px 14px; font-size:11px; font-weight:700; color:#64748b; text-transform:uppercase;'>{th_d}</th>"
                        f"<th style='text-align:center; padding:12px 14px; font-size:11px; font-weight:700; color:#64748b; text-transform:uppercase;'>{th_st}</th>"
                        "</tr>"
                        + "".join(table_rows)
                        + "</table></div>"
                    )
                    st.markdown(html_table_m0v3, unsafe_allow_html=True)

    # =========================================================================
    # TAB 1: ANALISI SPECIFICA TEST PER TEST (Deep-Dive Multi-Parametrico)
    # =========================================================================
    if "deep_dive" in tab_map:
        with tab_map["deep_dive"]:
            st.markdown(f"<div style='display:flex; align-items:center; gap:8px; margin-bottom:12px;'><i class='bi bi-search' style='color:#0ea5e9; font-size:18px;'></i><span style='font-size:16px; font-weight:800; color:#0f172a; text-transform:uppercase; letter-spacing:0.5px;'>{tr('Analisi Dettagliata Protocollo', 'Protocol Deep-Dive Analysis')}</span></div>", unsafe_allow_html=True)
    
            # Identifica SOLO i test effettivamente presenti nello storico dell'atleta
            prot_presenti_dict = {}
            for s in sessioni_atleta:
                p_info = s.get('protocollo_info')
                if p_info:
                    p_name = p_info.get('nome_protocollo')
                    if p_name and p_name not in prot_presenti_dict:
                        prot_presenti_dict[p_name] = p_info

            if not prot_presenti_dict:
                st.info(f"Nessun test presente nello storico di **{atleta_sel}**. Puoi inserire o importare nuovi test dalla scheda 'Inserimento & Gestione Dati'.")
            else:
                opzioni_test = sorted(list(prot_presenti_dict.keys()))
                curr_p1 = st.session_state.get("sel_prot_tab1")
                idx_p1 = opzioni_test.index(curr_p1) if curr_p1 in opzioni_test else 0

                prot_nome_sel = st.selectbox(
                    tr("Seleziona Test / Protocollo da Analizzare:", "Select Test / Protocol to Analyze:"),
                    opzioni_test,
                    index=idx_p1,
                    key="sel_prot_tab1"
                )
                prot_sel = prot_presenti_dict[prot_nome_sel]

                # Guida Rapida Scientifica
                with st.expander(f"{tr('Manuale ed Esecuzione:', 'Manual & Execution:')} {prot_sel['nome_protocollo']}", expanded=False):
                    if prot_sel.get('manuale_obiettivi'):
                        lbl_obj = tr("Obiettivo Fisiologico / Biomeccanico", "Physiological Objective")
                        st.markdown(f"<div style='margin-bottom:6px;'><i class='bi bi-bullseye' style='color:#0ea5e9; margin-right:6px;'></i><b>{lbl_obj}:</b></div>{prot_sel['manuale_obiettivi']}", unsafe_allow_html=True)
                    if prot_sel.get('manuale_esecuzione'):
                        lbl_exec = tr("Protocollo Operativo di Esecuzione", "Standard Protocol")
                        st.markdown(f"<div style='margin-top:8px; margin-bottom:6px;'><i class='bi bi-stopwatch' style='color:#0ea5e9; margin-right:6px;'></i><b>{lbl_exec}:</b></div>{prot_sel['manuale_esecuzione']}", unsafe_allow_html=True)
                    if prot_sel.get('manuale_interpretazione'):
                        lbl_int = tr("Guida all'Interpretazione & Benchmark", "Interpretation & Benchmarks")
                        st.markdown(f"<div style='margin-top:8px; margin-bottom:6px;'><i class='bi bi-bar-chart-line' style='color:#8b5cf6; margin-right:6px;'></i><b>{lbl_int}:</b></div>{prot_sel['manuale_interpretazione']}", unsafe_allow_html=True)
        
                # Sessioni registrate per questo protocollo
                cod_target = prot_sel.get('codice_univoco')
                id_target = prot_sel.get('id')
                sessioni_prot = [
                    s for s in sessioni_atleta 
                    if (s.get('protocollo_id') == id_target) or (s.get('protocollo_info', {}).get('codice_univoco') == cod_target)
                ]
                sessioni_prot.sort(key=lambda x: str(x.get('data')), reverse=False)
    
            if not sessioni_prot:
                st.info(f"Nessuna sessione di **{prot_sel['nome_protocollo']}** registrata per {atleta_sel}. "
                        f"Puoi inserire una nuova misurazione nella scheda 'Inserimento & Gestione Dati'.")
            else:
                schema_metriche = prot_sel.get('schema_metriche', []) or []
                
                # -----------------------------------------------------------------
                # RILEVAMENTO COMPLETO DI TUTTE LE METRICHE (Schema Ufficiale + Valori Caricati)
                # -----------------------------------------------------------------
                metriche_attive = []
                known_keys = set()
                for m in schema_metriche:
                    k = m['key']
                    lat = m.get('laterality', 'BILATERAL')
                    ha_valore = False
                    for s in sessioni_prot:
                        v = s.get('valori', {}) or {}
                        if lat == 'UNILATERAL':
                            if (k in v) or (f"{k}_dx" in v) or (f"{k}_sx" in v) or (f"{k}_asym_pct" in v):
                                ha_valore = True; break
                        else:
                            if (k in v) and v[k] is not None:
                                ha_valore = True; break
                    if ha_valore:
                        metriche_attive.append(dict(m))
                        known_keys.add(k)
    
                # Auto-scoperta dinamica di qualsiasi metrica presente nei valori caricati (es. da file Word o import)
                extra_keys_found = set()
                for s in sessioni_prot:
                    v = s.get('valori', {}) or {}
                    for vk in v.keys():
                        clean_vk = vk
                        for suff in ['_dx', '_sx', '_asym_pct', '_asym_dir', '_mean', '_max']:
                            if clean_vk.endswith(suff):
                                clean_vk = clean_vk[:-len(suff)]
                                break
                        if clean_vk not in known_keys and clean_vk not in extra_keys_found and clean_vk:
                            extra_keys_found.add(clean_vk)

                for ek in sorted(list(extra_keys_found)):
                    # Deduci lateralità
                    is_unil = any(
                        (f"{ek}_dx" in s.get('valori', {})) or (f"{ek}_sx" in s.get('valori', {})) or (f"{ek}_asym_pct" in s.get('valori', {}))
                        for s in sessioni_prot
                    )
                    lat = "UNILATERAL" if is_unil else "BILATERAL"
                    m_label = ek.replace('_', ' ').title()
                    # Includi l'unità di misura dedotta
                    unit_dedotta = ""
                    if "power" in ek.lower(): unit_dedotta = "W"
                    elif "force" in ek.lower(): unit_dedotta = "N"
                    elif "velocity" in ek.lower() or "rsi" in ek.lower(): unit_dedotta = "m/s"
                    elif "impulse" in ek.lower(): unit_dedotta = "N s"
                    elif "rfd" in ek.lower(): unit_dedotta = "N/s"
                    elif "duration" in ek.lower(): unit_dedotta = "ms"
                    elif "time" in ek.lower(): unit_dedotta = "s"
                    elif "height" in ek.lower(): unit_dedotta = "cm"
                    elif "rom" in ek.lower(): unit_dedotta = "°"
                    elif "stiffness" in ek.lower(): unit_dedotta = "N/m"

                    metriche_attive.append({
                        "key": ek,
                        "label": m_label,
                        "unit": unit_dedotta,
                        "direction": "LOWER_IS_BETTER" if ("time" in ek.lower() or "duration" in ek.lower()) else "HIGHER_IS_BETTER",
                        "laterality": lat,
                        "is_primary_kpi": False,
                        "color": "#0ea5e9"
                    })
                    known_keys.add(ek)

                if not metriche_attive:
                    metriche_attive = schema_metriche[:4] if schema_metriche else []
    
                # Snapshot Ultima Seduta: KPI Cards
                ultima_sess = sessioni_prot[-1]
                penultima_sess = sessioni_prot[-2] if len(sessioni_prot) >= 2 else None
                data_ult = ultima_sess.get('data', 'N/D')
                cond_ult = ultima_sess.get('condizione_ambiente', 'Outdoor')
                valori_ult = ultima_sess.get('valori', {}) or {}
    
                st.markdown(f"<div style='display:flex; align-items:center; gap:8px; margin-top:16px; margin-bottom:10px;'><i class='bi bi-clock-history' style='color:#0ea5e9; font-size:17px;'></i><span style='font-size:15px; font-weight:800; color:#0f172a;'>{tr('Snapshot Ultimo Test del', 'Latest Test Snapshot:')} {data_ult} ({cond_ult}) — <span style='color:#0ea5e9;'>{len(metriche_attive)} {tr('Parametri Analizzati', 'Analyzed Parameters')}</span></span></div>", unsafe_allow_html=True)
    
                # Calcolo Personal Best, Media Storica e SWC per ciascuna metrica
                pb_map = {}
                avg_map = {}
                swc_map = {}
                readiness_map = {}
                dir_switch_map = {}

                for m in metriche_attive:
                    k = m['key']
                    lat = m.get('laterality', 'BILATERAL')
                    dir_m = m.get('direction', 'HIGHER_IS_BETTER')
                    
                    vals = []
                    for s in sessioni_prot:
                        v = s.get('valori', {}) or {}
                        if lat == 'UNILATERAL':
                            val_num = v.get(k) or v.get(f"{k}_mean") or v.get(f"{k}_max") or v.get(f"{k}_dx")
                        else:
                            val_num = v.get(k)
                        if val_num is not None:
                            try: vals.append(float(val_num))
                            except: pass

                    val_curr = valori_ult.get(f"{k}_max") if lat == 'UNILATERAL' else valori_ult.get(k)
                    if val_curr is None and lat == 'UNILATERAL':
                        val_curr = valori_ult.get(f"{k}_dx") or valori_ult.get(k)

                    st_lbl, col_read, d_pct, txt_d, pb_v, med_5, swc_v = valuta_readiness_swc(val_curr, vals, dir_m)
                    pb_map[k] = pb_v
                    avg_map[k] = med_5
                    swc_map[k] = swc_v
                    readiness_map[k] = (st_lbl, col_read, d_pct, txt_d)

                    # Rilevamento Inversione Dominanza (Direction-Switch) per test unilaterali
                    if lat == 'UNILATERAL' and len(sessioni_prot) >= 2:
                        p_val = sessioni_prot[-2].get('valori', {}) or {}
                        u_val = sessioni_prot[-1].get('valori', {}) or {}
                        p_dx = p_val.get(f"{k}_dx"); p_sx = p_val.get(f"{k}_sx")
                        u_dx = u_val.get(f"{k}_dx"); u_sx = u_val.get(f"{k}_sx")
                        _, _, _, p_sgn = calcola_asimmetria_dx_sx(p_dx, p_sx, dir_m)
                        _, _, _, u_sgn = calcola_asimmetria_dx_sx(u_dx, u_sx, dir_m)
                        if (p_sgn >= 4.0 and u_sgn <= -4.0) or (p_sgn <= -4.0 and u_sgn >= 4.0):
                            dir_switch_map[k] = (p_sgn, u_sgn)

                # Render KPI Cards (righe ordinate di 4 carte ciascuna)
                num_m = len(metriche_attive)
                for chunk_start in range(0, num_m, 4):
                    chunk_metrics = metriche_attive[chunk_start:chunk_start+4]
                    cols_kpi = st.columns(len(chunk_metrics))
                    for col_k, m in zip(cols_kpi, chunk_metrics):
                        k = m['key']
                        lat = m.get('laterality', 'BILATERAL')
                        dir_m = m.get('direction', 'HIGHER_IS_BETTER')
                        unita = m.get('unit', '')
                        
                        st_lbl, col_read, d_pct, txt_d = readiness_map.get(k, ("N/D", "#94a3b8", 0.0, "N/D"))
                        pb_val = pb_map.get(k)
                        med_val = avg_map.get(k)
                        swc_val = swc_map.get(k)

                        if lat == 'UNILATERAL':
                            dx = valori_ult.get(f"{k}_dx")
                            sx = valori_ult.get(f"{k}_sx")
                            asym = valori_ult.get(f"{k}_asym_pct")
                            asym_dir = valori_ult.get(f"{k}_asym_dir", "")
                            
                            if dx is not None and sx is not None:
                                val_str = f"{tr('Dx', 'R')} {float(dx):.1f} | {tr('Sx', 'L')} {float(sx):.1f}"
                                if asym is not None:
                                    val_str += f"<br><span style='font-size:11.5px; color:#f59e0b; font-weight:700;'>{tr('Asim', 'Asym')}: {float(asym):.1f}% ({asym_dir})</span>"
                            elif asym is not None:
                                val_str = f"{tr('Asimmetria', 'Asymmetry')}: {float(asym):.1f}%"
                            else:
                                val_str = f"{float(valori_ult.get(k, 0)):.1f} {unita}"
                            
                            if k in dir_switch_map:
                                p_s, u_s = dir_switch_map[k]
                                val_str += f"<br><span style='background:#fef3c7; color:#b45309; padding:2px 6px; border-radius:4px; font-weight:800; font-size:10px;'><i class='bi bi-arrow-left-right'></i> {tr('INVERSIONE LATO', 'SIDE INVERSION')} ({p_s:+.1f}% → {u_s:+.1f}%)</span>"
                        else:
                            val_curr = valori_ult.get(k)
                            val_str = f"{float(val_curr):.1f} <span style='font-size:12px;'>{unita}</span>" if val_curr is not None else "N/D"

                        pb_str = f"PB: {pb_val:.1f} {unita}" if pb_val is not None else "PB: N/D"
                        swc_str = f"{tr('Media', 'Mean')}: {med_val:.1f} (±{swc_val:.1f})" if med_val is not None and swc_val is not None else ""

                        sub_txt = (
                            f"{pb_str} · {swc_str}<br>"
                            f"<span style='color:{col_read}; font-weight:700;'>{txt_d}</span> — "
                            f"<span style='color:{col_read}; font-weight:800; font-size:10.5px;'>{st_lbl}</span>"
                        )
                        with col_k:
                            st.markdown(card_kpi(m['label'], val_str, sub_txt, col_read), unsafe_allow_html=True)
    
                st.markdown("<div style='height: 18px;'></div>", unsafe_allow_html=True)

                # -----------------------------------------------------------------
                # TABELLA MATRICE COMPLETA DI TUTTI I PARAMETRI CARICATI (Multi-Data)
                # -----------------------------------------------------------------
                st.markdown(f"<div style='display:flex; align-items:center; gap:8px; margin-top:20px; margin-bottom:10px;'><i class='bi bi-table' style='color:#0ea5e9; font-size:17px;'></i><span style='font-size:15px; font-weight:800; color:#0f172a;'>{tr('Matrice Multi-Parametrica Completa (Tutti i Parametri per Data)', 'Full Multi-Parametric Matrix')}</span></div>", unsafe_allow_html=True)

                date_ordinate = [s.get('data') for s in sessioni_prot]
                th_date_html = "".join([f"<th style='padding:10px 14px; text-align:center;'>{d}</th>" for d in date_ordinate])
                
                rows_param_html = ""
                for m in metriche_attive:
                    k = m['key']
                    lat = m.get('laterality', 'BILATERAL')
                    u = m.get('unit', '')
                    pb_v = pb_map.get(k)

                    tds_date = ""
                    prev_val_num = None
                    for s in sessioni_prot:
                        v_s = s.get('valori', {}) or {}
                        if lat == 'UNILATERAL':
                            dx_s = v_s.get(f"{k}_dx")
                            sx_s = v_s.get(f"{k}_sx")
                            asym_s = v_s.get(f"{k}_asym_pct")
                            asym_d = v_s.get(f"{k}_asym_dir", "")
                            curr_v = v_s.get(k) or v_s.get(f"{k}_mean") or v_s.get(f"{k}_max")
                            
                            if dx_s is not None and sx_s is not None:
                                as_col = "#10b981" if (asym_s is not None and asym_s <= 10) else ("#f59e0b" if (asym_s is not None and asym_s <= 15) else "#ef4444")
                                as_txt = f"<div style='font-size:10.5px; font-weight:700; color:{as_col}; margin-top:2px;'>Asim: {asym_s:.1f}% ({asym_d})</div>" if asym_s is not None else ""
                                cell_content = f"<div style='font-weight:800; color:#0f172a;'>Dx: {float(dx_s):.1f} | Sx: {float(sx_s):.1f}</div>{as_txt}"
                            elif curr_v is not None:
                                cell_content = f"<div style='font-weight:800; color:#0f172a;'>{float(curr_v):.1f} {u}</div>"
                            else:
                                cell_content = "<span style='color:#94a3b8;'>-</span>"
                        else:
                            curr_v = v_s.get(k)
                            if curr_v is not None:
                                delta_str = ""
                                if prev_val_num is not None and prev_val_num > 0:
                                    diff_pct = (float(curr_v) - prev_val_num) / prev_val_num * 100.0
                                    diff_col = "#10b981" if diff_pct >= 0 else "#ef4444"
                                    delta_str = f"<div style='font-size:10.5px; font-weight:700; color:{diff_col};'>{diff_pct:+.1f}%</div>"
                                prev_val_num = float(curr_v)
                                cell_content = f"<div style='font-weight:800; color:#0f172a;'>{float(curr_v):.1f} <span style='font-size:10.5px; color:#64748b;'>{u}</span></div>{delta_str}"
                            else:
                                cell_content = "<span style='color:#94a3b8;'>-</span>"

                        tds_date += f"<td style='padding:10px 14px; text-align:center;'>{cell_content}</td>"

                    pb_td = f"{pb_v:.1f} {u}" if pb_v is not None else "-"
                    rows_param_html += (
                        f"<tr style='border-bottom:1px solid #f1f5f9;'>"
                        f"<td style='padding:10px 14px;'><div style='font-weight:800; color:#0f172a;'>{m['label']}</div><div style='font-size:10.5px; color:#64748b;'>{lat} · {m.get('direction', 'HIGHER_IS_BETTER')}</div></td>"
                        f"<td style='padding:10px 14px; text-align:center; font-weight:600; color:#475569;'>{u if u else '-'}</td>"
                        f"{tds_date}"
                        f"<td style='padding:10px 14px; text-align:center; font-weight:900; color:#0284c7;'>{pb_td}</td>"
                        f"</tr>"
                    )

                html_all_params = (
                    f"<div style='background:white; border-radius:12px; border:1px solid #e2e8f0; overflow-x:auto; margin-bottom:16px; box-shadow:0 1px 3px rgba(0,0,0,0.05); font-family:\"Inter\",sans-serif;'>"
                    f"<table style='width:100%; border-collapse:collapse; font-size:12.5px;'>"
                    f"<thead><tr style='background-color:#0f172a; color:#f8fafc; font-size:11px; text-transform:uppercase; letter-spacing:0.5px;'>"
                    f"<th style='padding:10px 14px; text-align:left;'>{tr('Parametro / Metrica', 'Parameter / Metric')}</th>"
                    f"<th style='padding:10px 14px; text-align:center;'>{tr('Unità', 'Unit')}</th>"
                    f"{th_date_html}"
                    f"<th style='padding:10px 14px; text-align:center; color:#38bdf8;'>Personal Best</th>"
                    f"</tr></thead><tbody>{rows_param_html}</tbody></table></div>"
                )
                st.markdown(html_all_params, unsafe_allow_html=True)
    
                # -----------------------------------------------------------------
                # GRIGLIA GRAFICI SMALL MULTIPLES (Trend Temporale per Metrica)
                # -----------------------------------------------------------------
                st.markdown(f"<div style='display:flex; align-items:center; gap:8px; margin-top:20px; margin-bottom:10px;'><i class='bi bi-graph-up' style='color:#0ea5e9; font-size:17px;'></i><span style='font-size:15px; font-weight:800; color:#0f172a;'>{tr('Trend Longitudinale Metriche', 'Longitudinal Metric Trends')}</span></div>", unsafe_allow_html=True)
                
                # Menù a tendina per selezionare il singolo parametro o tutti
                opzioni_filtro_m = [tr("Tutti i parametri (Griglia Completa)", "All Parameters (Full Grid)")] + [m['label'] for m in metriche_attive]
                sel_filtro_m = st.selectbox(
                    tr("📊 Seleziona Parametro da Visualizzare nel Grafico:", "📊 Select Parameter to Display in Chart:"),
                    opzioni_filtro_m,
                    index=0,
                    key=f"filtro_metrica_deepdive_{prot_nome_sel}"
                )
                
                metriche_da_mostrare = metriche_attive if sel_filtro_m == opzioni_filtro_m[0] else [m for m in metriche_attive if m['label'] == sel_filtro_m]

                dates = [s.get('data') for s in sessioni_prot]
                
                # Mostra grafici in griglia 2x2 (o a larghezza intera se singolo parametro)
                col_step = 1 if len(metriche_da_mostrare) == 1 else 2
                for row_idx in range(0, len(metriche_da_mostrare), col_step):
                    if col_step == 1:
                        target_cols = [st.container()]
                        chunk_m = metriche_da_mostrare[row_idx:row_idx+1]
                    else:
                        c_g1, c_g2 = st.columns(2)
                        target_cols = [c_g1, c_g2]
                        chunk_m = metriche_da_mostrare[row_idx:row_idx+2]

                    for c_chart, m in zip(target_cols, chunk_m):
                        k = m['key']
                        lat = m.get('laterality', 'BILATERAL')
                        fig_m = go.Figure()
    
                        if lat == 'UNILATERAL':
                            dx_vals = [s.get('valori', {}).get(f"{k}_dx") for s in sessioni_prot]
                            sx_vals = [s.get('valori', {}).get(f"{k}_sx") for s in sessioni_prot]
                            
                            signed_asym_vals = []
                            for s in sessioni_prot:
                                v_s = s.get('valori', {}) or {}
                                d_v = v_s.get(f"{k}_dx")
                                s_v = v_s.get(f"{k}_sx")
                                _, _, _, sgn_v = calcola_asimmetria_dx_sx(d_v, s_v, m.get('direction', 'HIGHER_IS_BETTER'))
                                signed_asym_vals.append(sgn_v if (d_v is not None and s_v is not None) else None)

                            # Tracciamento curve Dx e Sx
                            if any(v is not None for v in dx_vals):
                                fig_m.add_trace(go.Scatter(
                                    x=dates, y=dx_vals, name="Arto Destro (Dx)",
                                    mode="lines+markers", line=dict(color="#0ea5e9", width=2.5),
                                    connectgaps=True
                                ))
                            if any(v is not None for v in sx_vals):
                                fig_m.add_trace(go.Scatter(
                                    x=dates, y=sx_vals, name="Arto Sinistro (Sx)",
                                    mode="lines+markers", line=dict(color="#f97316", width=2.5),
                                    connectgaps=True
                                ))
                        else:
                            y_vals = [s.get('valori', {}).get(k) for s in sessioni_prot]
                            fig_m.add_trace(go.Scatter(
                                x=dates, y=y_vals, name=m['label'],
                                mode="lines+markers", line=dict(color=m.get('color', '#0ea5e9'), width=3),
                                marker=dict(size=7),
                                connectgaps=True
                            ))

                        fig_m.update_layout(
                            title=dict(text=f"<b>{m['label']}</b> ({m.get('unit', '')})", font=dict(size=13, color="#0f172a")),
                            height=270,
                            margin=dict(l=10, r=10, t=35, b=10),
                            plot_bgcolor="white",
                            paper_bgcolor="white",
                            xaxis=dict(showgrid=True, gridcolor="#f1f5f9", tickfont=dict(size=10, color="#64748b")),
                            yaxis=dict(showgrid=True, gridcolor="#f1f5f9", tickfont=dict(size=10, color="#64748b")),
                            font=dict(family="Inter", color="#0f172a"),
                            legend=dict(orientation="h", y=1.12, font=dict(size=10))
                        )
                        with c_chart:
                            if lat == 'UNILATERAL' and k in dir_switch_map:
                                p_s, u_s = dir_switch_map[k]
                                alert_lbl = tr("INVERSIONE LATO DOMINANTE (Compenso Dx <-> Sx:", "DOMINANT SIDE INVERSION (R <-> L Compensation:")
                                st.markdown(
                                    f"<div style='background:#fef3c7; color:#b45309; border:1px solid #f59e0b; padding:4px 8px; border-radius:6px; font-weight:800; font-size:10.5px; margin-bottom:6px;'>"
                                    f"<i class='bi bi-arrow-left-right' style='margin-right:4px;'></i>{alert_lbl} {p_s:+.1f}% → {u_s:+.1f}%)</div>",
                                    unsafe_allow_html=True
                                )
                            st.plotly_chart(fig_m, use_container_width=True)

                            # Grafico Dedicato Trend Asimmetria Vettoriale (con 0% al centro)
                            if lat == 'UNILATERAL' and any(v is not None for v in signed_asym_vals):
                                fig_asym_v = go.Figure()
                                asym_trace_lbl = tr("Asimmetria Vettoriale (%)", "Vector Asymmetry (%)")
                                fig_asym_v.add_trace(go.Scatter(
                                    x=dates, y=signed_asym_vals, name=asym_trace_lbl,
                                    mode="lines+markers", line=dict(color="#0284c7", width=2.5),
                                    marker=dict(size=6, color="#0ea5e9", line=dict(color="#ffffff", width=1.5)),
                                    connectgaps=True,
                                    hovertemplate=f"{tr('Data', 'Date')}: %{{x}}<br>{asym_trace_lbl}: <b>%{{y:+.1f}}%</b><extra></extra>"
                                ))
                                max_v_abs = max([abs(v) for v in signed_asym_vals if v is not None] + [16.0])
                                bound_v = max(20.0, max_v_abs * 1.25)
                                fig_asym_v.add_hrect(y0=-10, y1=10, fillcolor="rgba(16,185,129,0.12)", line_width=0, layer="below")
                                fig_asym_v.add_hrect(y0=10, y1=15, fillcolor="rgba(245,158,11,0.14)", line_width=0, layer="below")
                                fig_asym_v.add_hrect(y0=-15, y1=-10, fillcolor="rgba(245,158,11,0.14)", line_width=0, layer="below")
                                fig_asym_v.add_hline(y=15, line=dict(color="#e11d48", width=1.3, dash="dash"))
                                fig_asym_v.add_hline(y=-15, line=dict(color="#e11d48", width=1.3, dash="dash"))
                                fig_asym_v.add_hline(y=0, line=dict(color="#64748b", width=1.2, dash="solid"))
                                asym_chart_title = tr(f"<b>Trend Asimmetria Vettoriale: {m['label']}</b> (← Sx | Dx →)", f"<b>Vector Asymmetry Trend: {m['label']}</b> (← L | R →)")
                                fig_asym_v.update_layout(
                                    title=dict(text=asym_chart_title, font=dict(size=11.5, color="#0f172a")),
                                    height=230,
                                    margin=dict(l=10, r=10, t=35, b=10),
                                    plot_bgcolor="white",
                                    paper_bgcolor="white",
                                    xaxis=dict(showgrid=True, gridcolor="#f1f5f9", tickfont=dict(size=9.5, color="#64748b")),
                                    yaxis=dict(title="← Sx (%) | Dx (%) →", range=[-bound_v, bound_v], showgrid=True, gridcolor="#f1f5f9", tickfont=dict(size=9.5, color="#64748b")),
                                    font=dict(family="Inter", color="#0f172a")
                                )
                                st.plotly_chart(fig_asym_v, use_container_width=True)
    
                # -----------------------------------------------------------------
                # RADAR CHART CONFRONTO DATE (Per M0V3 Tennis Test e test multi-variabile)
                # -----------------------------------------------------------------
                if len(metriche_attive) >= 4 and len(sessioni_prot) >= 2:
                    st.markdown("---")
                    st.markdown(f"<div style='display:flex; align-items:center; gap:8px; margin-top:20px; margin-bottom:10px;'><i class='bi bi-diagram-3' style='color:#8b5cf6; font-size:17px;'></i><span style='font-size:15px; font-weight:800; color:#0f172a;'>{tr('Confronto Spider / Radar Multi-Data', 'Multi-Date Radar Comparison')}</span></div>", unsafe_allow_html=True)
                    col_r1, col_r2 = st.columns(2)
                    date_list = [s.get('data') for s in sessioni_prot]
                    with col_r1:
                        data_a = st.selectbox("Seleziona Data Base (Baseline):", date_list, index=0, key="sel_radar_a")
                    with col_r2:
                        data_b = st.selectbox("Seleziona Data Recente (Confronto):", date_list, index=len(date_list)-1, key="sel_radar_b")
    
                    sess_a = next((s for s in sessioni_prot if s.get('data') == data_a), None)
                    sess_b = next((s for s in sessioni_prot if s.get('data') == data_b), None)
    
                    if sess_a and sess_b:
                        categories = [m['label'] for m in metriche_attive]
                        r_a, r_b = [], []
                        for m in metriche_attive:
                            k = m['key']
                            pb = pb_map.get(k) or 1.0
                            va = float(sess_a.get('valori', {}).get(k) or 0)
                            vb = float(sess_b.get('valori', {}).get(k) or 0)
                            # Normalizzazione 0-100% rispetto al PB
                            ra = min(110.0, (va / pb * 100.0) if pb > 0 else 50.0)
                            rb = min(110.0, (vb / pb * 100.0) if pb > 0 else 50.0)
                            r_a.append(ra); r_b.append(rb)
    
                        # Chiusura loop radar
                        categories_loop = categories + [categories[0]]
                        r_a_loop = r_a + [r_a[0]]
                        r_b_loop = r_b + [r_b[0]]
    
                        fig_radar = go.Figure()
                        fig_radar.add_trace(go.Scatterpolar(
                            r=r_a_loop, theta=categories_loop, fill='toself',
                            name=f"Data A: {data_a}", line=dict(color="#94a3b8")
                        ))
                        fig_radar.add_trace(go.Scatterpolar(
                            r=r_b_loop, theta=categories_loop, fill='toself',
                            name=f"Data B: {data_b}", line=dict(color="#0ea5e9", width=2.5)
                        ))
                        fig_radar.update_layout(
                            polar=dict(
                                radialaxis=dict(visible=True, range=[0, 110], tickfont=dict(size=9, color="#94a3b8")),
                                bgcolor="rgba(255,255,255,0.02)"
                            ),
                            height=380,
                            margin=dict(l=40, r=40, t=30, b=30),
                            paper_bgcolor="rgba(0,0,0,0)"
                        )
                        st.plotly_chart(fig_radar, use_container_width=True)
    
    # =========================================================================
    # TAB 2: EXECUTIVE SUMMARY & QUADRO GLOBALE ATLETA
    # =========================================================================
    if "executive" in tab_map:
        with tab_map["executive"]:
            st.markdown(f"<div style='display:flex; align-items:center; gap:8px; margin-bottom:12px;'><i class='bi bi-speedometer2' style='color:#10b981; font-size:18px;'></i><span style='font-size:16px; font-weight:800; color:#0f172a; text-transform:uppercase; letter-spacing:0.5px;'>{tr('Quadro Generale di Efficienza & Asimmetrie', 'Executive Overview & Asymmetries')}</span></div>", unsafe_allow_html=True)
            
            if not sessioni_atleta:
                st.info(f"Nessun test presente nello storico di {atleta_sel}.")
            else:
                # -------------------------------------------------------------
                # SELETTORE DATA / AMBITO DI ANALISI
                # -------------------------------------------------------------
                all_dates_disponibili = sorted(list(set(str(s.get('data')) for s in sessioni_atleta if s.get('data'))), reverse=True)
                
                lbl_mode_last = tr("Ultima Rilevazione (Test più recenti per tipologia)", "Latest Assessment (Most recent tests)")
                lbl_mode_all = tr("Tutte le Rilevazioni (Storico Completo)", "All Assessments (Complete History)")
                opzioni_filtro_data = [lbl_mode_last, lbl_mode_all] + [f"Data: {d}" for d in all_dates_disponibili]
                
                col_sel_d, _ = st.columns([3, 1])
                with col_sel_d:
                    sel_data_quadro = st.selectbox(
                        tr("Seleziona Sessione / Data di Analisi:", "Select Session / Date of Analysis:"),
                        opzioni_filtro_data,
                        index=0,
                        key="sel_data_quadro_globale"
                    )

                # Definizione delle sessioni per la Matrice e per le Asimmetrie
                if sel_data_quadro == lbl_mode_last:
                    # Ultima rilevazione per ciascun protocollo
                    ultime_dict = {}
                    for s in sorted(sessioni_atleta, key=lambda x: str(x.get('data'))):
                        ultime_dict[s.get('protocollo_id')] = s
                    sessioni_matrice = list(ultime_dict.values())
                    sessioni_asym = sessioni_matrice
                    desc_asym = tr("Asimmetrie relative all'ultima seduta registrata per ciascun test", "Asymmetries from the latest session of each test")
                elif sel_data_quadro == lbl_mode_all:
                    # Tutte le rilevazioni: matrice con tutte le sessioni dello storico
                    sessioni_matrice = sorted(sessioni_atleta, key=lambda x: str(x.get('data')), reverse=True)
                    # Sulle asimmetrie: "il test più recente per ogni tipologia"
                    ultime_asym_dict = {}
                    for s in sorted(sessioni_atleta, key=lambda x: str(x.get('data'))):
                        ultime_asym_dict[s.get('protocollo_id')] = s
                    sessioni_asym = list(ultime_asym_dict.values())
                    desc_asym = tr("Asimmetrie del test più recente per ogni tipologia (Storico Completo)", "Most recent asymmetry for each test type")
                else:
                    target_date = sel_data_quadro.replace("Data: ", "").strip()
                    sessioni_matrice = [s for s in sessioni_atleta if str(s.get('data')) == target_date]
                    sessioni_asym = sessioni_matrice
                    desc_asym = f"{tr('Asimmetrie registrate nella data selezionata', 'Asymmetries recorded on')}: {target_date}"

                # 1. MATRICE SEMAFORICA DEI KPI PRIMARI
                st.markdown(f"<div style='display:flex; align-items:center; gap:8px; margin-top:16px; margin-bottom:10px;'><i class='bi bi-activity' style='color:#0ea5e9; font-size:17px;'></i><span style='font-size:15px; font-weight:800; color:#0f172a;'>{tr('Matrice di Performance & Readiness Atleta', 'Athlete Performance & Readiness Matrix')} ({len(sessioni_matrice)} {tr('sessioni', 'sessions')})</span></div>", unsafe_allow_html=True)
    
                righe_matrice = []
                for s_row in sessioni_matrice:
                    p_info = s_row.get('protocollo_info') or {}
                    p_id = s_row.get('protocollo_id')
                    schema = p_info.get('schema_metriche') or []
                    primary_m = next((m for m in schema if m.get('is_primary_kpi')), schema[0] if schema else None)
                    
                    if primary_m:
                        k = primary_m['key']
                        unita = primary_m.get('unit', '')
                        dir_m = primary_m.get('direction', 'HIGHER_IS_BETTER')
                        v_dict = s_row.get('valori', {}) or {}
                        
                        if primary_m.get('laterality') == 'UNILATERAL':
                            val_num = v_dict.get(k) or v_dict.get(f"{k}_max") or v_dict.get(f"{k}_dx")
                        else:
                            val_num = v_dict.get(k)
                        
                        if val_num is not None:
                            try:
                                val_f = float(val_num)
                                # Calcolo PB, Media Storica (ultime 5) e SWC
                                tutti_val = []
                                for sess in sessioni_atleta:
                                    if sess.get('protocollo_id') == p_id:
                                        v_tmp = sess.get('valori', {}).get(k) or sess.get('valori', {}).get(f"{k}_max") or sess.get('valori', {}).get(f"{k}_dx")
                                        if v_tmp is not None:
                                            try: tutti_val.append(float(v_tmp))
                                            except: pass
                                
                                stato_lbl, col_read, delta_m, txt_m, pb_v, med_5, swc_v = valuta_readiness_swc(val_f, tutti_val, dir_m)
                                pb_str = f"{pb_v:.1f} {unita}" if pb_v is not None else "-"
                                med_swc_str = f"{med_5:.1f} (±{swc_v:.1f}) {unita}" if (med_5 is not None and swc_v is not None) else "-"

                                righe_matrice.append({
                                    tr("Data Test", "Test Date"): s_row.get('data'),
                                    tr("Categoria", "Category"): p_info.get('categoria', 'Altro'),
                                    tr("Test", "Test"): p_info.get('nome_protocollo', 'N/D'),
                                    tr("KPI", "KPI"): primary_m['label'],
                                    tr("Risultato", "Result"): f"{val_f:.1f} {unita}",
                                    "Personal Best": pb_str,
                                    tr("Media Abituale (±SWC)", "Usual Mean (±SWC)"): med_swc_str,
                                    tr("vs Media", "vs Mean"): txt_m,
                                    tr("Stato Readiness", "Readiness State"): stato_lbl
                                })
                            except Exception:
                                pass

                if righe_matrice:
                    df_matrice = pd.DataFrame(righe_matrice)
                    st.dataframe(df_matrice, use_container_width=True, hide_index=True)
                else:
                    st.info(tr("Nessuna misurazione valida presente per i criteri selezionati.", "No valid measurements found for selected criteria."))

                st.markdown("<div style='height: 18px;'></div>", unsafe_allow_html=True)

                # 2. CRUSCOTTO GLOBALE ASIMMETRIE (Diverging Bar Chart Sx <-> Dx)
                st.markdown(f"<div style='display:flex; align-items:center; gap:8px; margin-top:24px; margin-bottom:10px;'><i class='bi bi-arrow-left-right' style='color:#f59e0b; font-size:17px;'></i><span style='font-size:15px; font-weight:800; color:#0f172a;'>{tr('Cruscotto Asimmetrie Bilaterali (Focus Return-to-Play)', 'Bilateral Asymmetries Dashboard')}</span></div>", unsafe_allow_html=True)
                st.caption(f"{desc_asym} — (0-10% Normale | 10-15% Attenzione | >15% Rischio Elevato)")

                asimmetrie_rilevate = []
                for s_as in sessioni_asym:
                    p_info = s_as.get('protocollo_info') or {}
                    schema = p_info.get('schema_metriche') or []
                    v_dict = s_as.get('valori', {}) or {}
                    d_as = s_as.get('data', 'N/D')
                    
                    for m in schema:
                        if m.get('laterality') == 'UNILATERAL':
                            k = m['key']
                            asym_val = v_dict.get(f"{k}_asym_pct")
                            asym_dir = v_dict.get(f"{k}_asym_dir")
                            dx = v_dict.get(f"{k}_dx")
                            sx = v_dict.get(f"{k}_sx")
                            
                            # Se non c'era l'asym salvato, calcolalo al volo con segno vettoriale
                            if asym_val is None and dx is not None and sx is not None:
                                asym_val, asym_dir, _, signed_asym = calcola_asimmetria_dx_sx(dx, sx, m.get('direction', 'HIGHER_IS_BETTER'))
                            
                            if asym_val is not None:
                                try:
                                    a_float = float(asym_val)
                                    dir_sgn = 1.0 if asym_dir == "Dx" else (-1.0 if asym_dir == "Sx" else 0.0)
                                    lbl_chart = f"{p_info.get('nome_protocollo')}: {m['label']}"
                                    if sel_data_quadro == lbl_mode_all:
                                        lbl_chart += f" ({d_as})"
                                    asimmetrie_rilevate.append({
                                        "etichetta": lbl_chart,
                                        "data": d_as,
                                        "asym_pct": a_float,
                                        "asym_signed": a_float * dir_sgn,
                                        "dominanza": asym_dir or "="
                                    })
                                except: pass
    
                if asimmetrie_rilevate:
                    df_asym = pd.DataFrame(asimmetrie_rilevate).sort_values('asym_pct', ascending=True)
                    
                    # Assegnazione colore in base alla soglia
                    colori_barre = []
                    for val in df_asym['asym_pct']:
                        if val <= 10.0: colori_barre.append("#10b981") # Verde
                        elif val <= 15.0: colori_barre.append("#f59e0b") # Giallo
                        else: colori_barre.append("#ef4444") # Rosso Allarme
    
                    fig_div = go.Figure()
                    fig_div.add_trace(go.Bar(
                        y=df_asym['etichetta'],
                        x=df_asym['asym_signed'],
                        orientation='h',
                        marker_color=colori_barre,
                        text=[f"{row['asym_pct']:.1f}% ({row['dominanza']})" for _, row in df_asym.iterrows()],
                        textposition='outside'
                    ))
                    
                    max_bound = max(25.0, max(df_asym['asym_pct']) * 1.25)
                    fig_div.update_layout(
                        title=dict(text="<b>Asimmetria Bilaterale (Sx ← 0% → Dx)</b>", font=dict(size=13, color="#f8fafc")),
                        xaxis=dict(
                            title="← Dominanza Sinistra (%) | Dominanza Destra (%) →",
                            range=[-max_bound, max_bound],
                            zeroline=True, zerolinewidth=2, zerolinecolor="#ffffff",
                            showgrid=True, gridcolor="rgba(255,255,255,0.06)"
                        ),
                        height=max(280, len(df_asym) * 35),
                        margin=dict(l=10, r=20, t=35, b=20),
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(255,255,255,0.02)"
                    )
                    st.plotly_chart(fig_div, use_container_width=True)
                else:
                    st.caption("Nessun test unilaterale registrato con dati Destro/Sinistro.")
    
                # 3. INDICI BIOMECCANICI DERIVATI CROSS-TEST (Stessa Data)
                st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
                cross_ind = calcola_indici_cross_test(sessioni_atleta)
                eur_data = cross_ind.get('eur')
                dsi_data = cross_ind.get('dsi')
                cod_data = cross_ind.get('cod_deficit')
                spalla_ratios = cross_ind.get('spalla') or {}

                ha_cross = (eur_data is not None) or (dsi_data is not None) or (cod_data is not None) or (spalla_ratios.get('trom_dx') is not None)
                if ha_cross:
                    st.markdown(
                        f"<div style='display:flex; align-items:center; gap:8px; margin-top:24px; margin-bottom:12px;'>"
                        f"<i class='bi bi-diagram-3-fill' style='color:#0284c7; font-size:18px;'></i>"
                        f"<span style='font-size:15px; font-weight:800; color:#0f172a; text-transform:uppercase; letter-spacing:0.5px;'>"
                        f"{tr('Indici Biomeccanici Derivati & Cross-Test (Stessa Data)', 'Derived Biomechanical & Cross-Test Indices (Same Date)')}"
                        f"</span></div>",
                        unsafe_allow_html=True
                    )

                    c_cr1, c_cr2, c_cr3 = st.columns(3)

                    # Card 1: Elastic Index / EUR (CMJ vs SJ)
                    with c_cr1:
                        if eur_data:
                            eur_val_str = f"+{eur_data['diff_cm']:.1f} cm ({eur_data['diff_pct']:+.1f}%)"
                            if eur_data.get('is_battery_fallback') and eur_data.get('data_cmj') and eur_data.get('data_sj'):
                                sub_d = f"CMJ ({eur_data['data_cmj']}) · SJ ({eur_data['data_sj']})"
                            else:
                                d_raw = str(eur_data.get('data', ''))
                                try:
                                    dt_p = pd.to_datetime(d_raw, errors='coerce')
                                    sub_d = f"Data: {dt_p.strftime('%d/%m/%Y')}" if pd.notnull(dt_p) else f"Data: {d_raw}"
                                except Exception:
                                    sub_d = f"Data: {d_raw}"
                            eur_sub = (
                                f"Ratio EUR: <b>{eur_data['eur_ratio']:.2f}</b> · {sub_d}<br>"
                                f"<span style='color:{eur_data['colore']}; font-weight:800;'>{eur_data['valutazione']}</span>"
                            )
                            st.markdown(card_kpi(
                                tr("Elastic Index / EUR (CMJ vs SJ)", "Elastic Index / EUR (CMJ vs SJ)"),
                                eur_val_str,
                                eur_sub,
                                eur_data['colore']
                            ), unsafe_allow_html=True)
                        else:
                            st.markdown(card_kpi(
                                tr("Elastic Index / EUR (CMJ vs SJ)", "Elastic Index / EUR (CMJ vs SJ)"),
                                "N/D",
                                tr("Registrare CMJ e SJ per calcolare l'indice elastico", "Record CMJ and SJ to compute elastic index"),
                                "#94a3b8"
                            ), unsafe_allow_html=True)

                    # Card 2: Dynamic Strength Index (DSI)
                    with c_cr2:
                        if dsi_data:
                            dsi_val_str = f"DSI {dsi_data['dsi_ratio']:.2f}"
                            if dsi_data.get('is_battery_fallback') and dsi_data.get('data_jump') and dsi_data.get('data_imtp'):
                                sub_d2 = f"{dsi_data['jump_type']} ({dsi_data['data_jump']}) · IMTP ({dsi_data['data_imtp']})"
                            else:
                                d_raw2 = str(dsi_data.get('data', ''))
                                try:
                                    dt_p2 = pd.to_datetime(d_raw2, errors='coerce')
                                    sub_d2 = f"Data: {dt_p2.strftime('%d/%m/%Y')}" if pd.notnull(dt_p2) else f"Data: {d_raw2}"
                                except Exception:
                                    sub_d2 = f"Data: {d_raw2}"
                            dsi_sub = (
                                f"{dsi_data['jump_type']} PF: {dsi_data['pf_jump']:.0f}N · IMTP PF: {dsi_data['pf_imtp']:.0f}N<br>"
                                f"<span style='color:{dsi_data['colore']}; font-weight:800;'>{dsi_data['valutazione']}</span><br>"
                                f"<span style='font-size:10.5px; color:#64748b;'>{sub_d2} · {dsi_data.get('raccomandazione', '')}</span>"
                            )
                            st.markdown(card_kpi(
                                tr("Dynamic Strength Index (DSI)", "Dynamic Strength Index (DSI)"),
                                dsi_val_str,
                                dsi_sub,
                                dsi_data['colore']
                            ), unsafe_allow_html=True)
                        else:
                            st.markdown(card_kpi(
                                tr("Dynamic Strength Index (DSI)", "Dynamic Strength Index (DSI)"),
                                "N/D",
                                tr("Registrare Salto (CMJ/SJ) e IMTP per calcolare DSI (Target 0.60-0.80)", "Record Jump and IMTP to compute DSI (Target 0.60-0.80)"),
                                "#94a3b8"
                            ), unsafe_allow_html=True)

                    # Card 3: COD Deficit (5-0-5 vs Sprint 10m)
                    with c_cr3:
                        if cod_data:
                            cod_dx_s = f"{cod_data['cod_def_dx']:+.2f}s" if cod_data['cod_def_dx'] is not None else "-"
                            cod_sx_s = f"{cod_data['cod_def_sx']:+.2f}s" if cod_data['cod_def_sx'] is not None else "-"
                            cod_val_str = f"Dx: {cod_dx_s} | Sx: {cod_sx_s}"
                            if cod_data.get('is_battery_fallback') and cod_data.get('data_505') and cod_data.get('data_10m'):
                                sub_d3 = f"5-0-5 ({cod_data['data_505']}) · 10m ({cod_data['data_10m']})"
                            else:
                                d_raw3 = str(cod_data.get('data', ''))
                                try:
                                    dt_p3 = pd.to_datetime(d_raw3, errors='coerce')
                                    sub_d3 = f"Data: {dt_p3.strftime('%d/%m/%Y')}" if pd.notnull(dt_p3) else f"Data: {d_raw3}"
                                except Exception:
                                    sub_d3 = f"Data: {d_raw3}"
                            cod_sub = (
                                f"Sprint 10m: {cod_data['t10m']:.2f}s · Asim: {cod_data['asym_cod']:.1f}% · {sub_d3}<br>"
                                f"<span style='color:{cod_data['colore']}; font-weight:800;'>{cod_data['valutazione']}</span>"
                            )
                            st.markdown(card_kpi(
                                tr("COD Deficit (5-0-5 vs Sprint 10m)", "COD Deficit (5-0-5 vs Sprint 10m)"),
                                cod_val_str,
                                cod_sub,
                                cod_data['colore']
                            ), unsafe_allow_html=True)
                        else:
                            st.markdown(card_kpi(
                                tr("COD Deficit (5-0-5 vs Sprint 10m)", "COD Deficit (5-0-5 vs Sprint 10m)"),
                                "N/D",
                                tr("Registrare 5-0-5 Agility e Sprint 10m nella stessa data per calcolare il deficit", "Record 5-0-5 Agility and 10m Sprint on same date to compute deficit"),
                                "#94a3b8"
                            ), unsafe_allow_html=True)

                    # Sezione Indici Spalla (se presenti)
                    if spalla_ratios.get('trom_dx') is not None or spalla_ratios.get('er_ir_ratio_dx') is not None:
                        c_sp1, c_sp2, c_sp3 = st.columns(3)
                        with c_sp1:
                            t_dx = spalla_ratios.get('trom_dx')
                            t_sx = spalla_ratios.get('trom_sx')
                            diff_trom = spalla_ratios.get('trom_diff', 0)
                            t_str = f"Dx: {t_dx}° | Sx: {t_sx}°" if (t_dx and t_sx) else f"{t_dx or t_sx}°"
                            st.markdown(card_kpi(
                                "TROM (Total ROM: IR + ER)",
                                t_str,
                                f"Diff: {diff_trom:.1f}° {'Simmetrico' if diff_trom<=5 else 'GIRD Warning'}",
                                "#0ea5e9"
                            ), unsafe_allow_html=True)
                        with c_sp2:
                            ratio_dx = spalla_ratios.get('er_ir_ratio_dx')
                            r_dx_str = f"{ratio_dx:.1f}%" if ratio_dx else "N/D"
                            is_target = (ratio_dx >= 65.0 and ratio_dx <= 75.0) if ratio_dx else False
                            st.markdown(card_kpi(
                                "Ratio Forza ER / IR (Arto Dx)",
                                r_dx_str,
                                f"Target fisiologico: 65-75% {'Ottimale' if is_target else 'Attenzione'}",
                                "#10b981" if is_target else "#f59e0b"
                            ), unsafe_allow_html=True)
                        with c_sp3:
                            ratio_sx = spalla_ratios.get('er_ir_ratio_sx')
                            r_sx_str = f"{ratio_sx:.1f}%" if ratio_sx else "N/D"
                            is_target_sx = (ratio_sx >= 65.0 and ratio_sx <= 75.0) if ratio_sx else False
                            st.markdown(card_kpi(
                                "Ratio Forza ER / IR (Arto Sx)",
                                r_sx_str,
                                f"Target fisiologico: 65-75% {'Ottimale' if is_target_sx else 'Attenzione'}",
                                "#10b981" if is_target_sx else "#f59e0b"
                            ), unsafe_allow_html=True)
    
    # =========================================================================
    # TAB 3: CONFRONTI ROSTER ATLETI (Comparative Benchmarking)
    # =========================================================================
    if "confronti" in tab_map:
        with tab_map["confronti"]:
            def _render_tab_confronti_body():
                        st.markdown(
                            f"<div style='display:flex; align-items:center; gap:10px; margin-bottom:14px;'>"
                            f"<i class='bi bi-people' style='font-size:22px; color:#0ea5e9;'></i>"
                            f"<div>"
                            f"<div style='font-size:16px; font-weight:800; color:#0f172a; text-transform:uppercase; letter-spacing:0.5px;'>{tr('Confronto Prestazioni & Screening Roster', 'Roster Performance & Screening Comparison')}</div>"
                            f"<div style='font-size:12px; color:#64748b;'>{tr('Benchmarking comparativo tra gli atleti del roster sul protocollo di test selezionato', 'Comparative benchmarking among roster athletes on selected test protocol')}</div>"
                            f"</div>"
                            f"</div>",
                            unsafe_allow_html=True
                        )

                        all_sessions_db = get_sessioni_test()
                        roster_nomi = list(dict_atleti.keys())
                        n_roster = len(roster_nomi)

                        macro_tutte = sorted(list(set(p.get('macro_area') for p in catalogo if p.get('macro_area'))))
                        col_cf1, col_cf2, col_cf3 = st.columns([2.2, 2.8, 2])

                        with col_cf1:
                            macro_conf_sel = st.selectbox(
                                tr("Filtra Macro-Area:", "Filter Macro-Area:"),
                                [tr("Tutte le Macro-Aree", "All Macro-Areas")] + macro_tutte,
                                key="conf_macro_sel"
                            )

                        protocolli_conf = catalogo
                        if macro_conf_sel != tr("Tutte le Macro-Aree", "All Macro-Areas"):
                            protocolli_conf = [p for p in catalogo if p.get('macro_area') == macro_conf_sel]

                        if not protocolli_conf:
                            st.info(tr("Nessun protocollo di test disponibile per la macro-area selezionata.", "No testing protocol available for selected macro-area."))
                            return

                        prot_nomi = [p['nome_protocollo'] for p in protocolli_conf]
                        with col_cf2:
                            test_conf_nome = st.selectbox(
                                tr("Seleziona Protocollo da Confrontare:", "Select Test to Compare:"),
                                prot_nomi,
                                index=0,
                                key="conf_test_sel"
                            )
                        prot_scelto = next((p for p in protocolli_conf if p['nome_protocollo'] == test_conf_nome), protocolli_conf[0])
                        schema_scelto = prot_scelto.get('schema_metriche', [])

                        with col_cf3:
                            criterio_tempo = st.selectbox(
                                tr("Criterio Temporale:", "Time Benchmark:"),
                                [tr("Ultimo Test Disponibile", "Latest Test Available"), tr("Personal Best (Miglior Valore)", "Personal Best (All-Time)")],
                                key="conf_criterio_tempo"
                            )
                        is_pb_mode = (criterio_tempo == tr("Personal Best (Miglior Valore)", "Personal Best (All-Time)"))

                        if not schema_scelto:
                            st.warning(tr("Lo schema metriche di questo protocollo non è configurato.", "Protocol metric schema not configured."))
                            return

                        metriche_opzioni = []
                        for m in schema_scelto:
                            lbl = m.get('label', m.get('key'))
                            u = m.get('unit', '')
                            disp = f"{lbl} ({u})" if u else lbl
                            metriche_opzioni.append((m.get('key'), disp, m))

                        idx_def_met = 0
                        for i_m, (_, _, m_obj) in enumerate(metriche_opzioni):
                            if m_obj.get('is_primary_kpi'):
                                idx_def_met = i_m
                                break

                        col_m_sel, col_lat_sel = st.columns([3, 2])
                        with col_m_sel:
                            scelta_met_disp = st.selectbox(
                                tr("Metrica da Confrontare:", "Metric to Compare:"),
                                [item[1] for item in metriche_opzioni],
                                index=idx_def_met,
                                key="conf_met_sel"
                            )
                        met_scelta_info = next(item for item in metriche_opzioni if item[1] == scelta_met_disp)
                        met_key = met_scelta_info[0]
                        met_obj = met_scelta_info[2]
                        is_higher_better = (met_obj.get('direction', 'HIGHER_IS_BETTER') != 'LOWER_IS_BETTER')
                        met_unit = met_obj.get('unit', '')
                        met_lat = met_obj.get('laterality', 'BILATERAL')

                        opz_lat = "mean"
                        if met_lat == "UNILATERAL":
                            with col_lat_sel:
                                scelta_lat = st.selectbox(
                                    tr("Parametro Bilaterale:", "Bilateral Parameter:"),
                                    [
                                        tr("Valore Medio (Dx/Sx)", "Mean Value (R/L)"),
                                        tr("Valore Massimo (Best)", "Max Value (Best)"),
                                        tr("Lato Destro (Dx)", "Right Side (R)"),
                                        tr("Lato Sinistro (Sx)", "Left Side (L)"),
                                        tr("Indice Asimmetria (%)", "Asymmetry Index (%)"),
                                    ],
                                    key="conf_lat_param"
                                )
                                if "Massimo" in scelta_lat or "Max" in scelta_lat:
                                    opz_lat = "max"
                                elif "Destro" in scelta_lat or "Right" in scelta_lat:
                                    opz_lat = "dx"
                                elif "Sinistro" in scelta_lat or "Left" in scelta_lat:
                                    opz_lat = "sx"
                                elif "Asimmetria" in scelta_lat or "Asymmetry" in scelta_lat:
                                    opz_lat = "asym"

                        prot_id = prot_scelto.get('id')
                        prot_code = prot_scelto.get('codice_univoco')

                        dati_confronto = []
                        atleti_senza_dati = []

                        for nome_atl, id_atl in dict_atleti.items():
                            sess_atl = []
                            for s in all_sessions_db:
                                s_p_id = s.get('protocollo_id')
                                s_p_obj = s.get('catalogo_protocolli') or {}
                                p_match = (
                                    (str(s_p_id) == str(prot_id)) or
                                    (s_p_obj.get('codice_univoco') == prot_code) or
                                    (s_p_obj.get('nome_protocollo') == prot_scelto['nome_protocollo'])
                                )
                                if not p_match:
                                    continue

                                atl_match = (
                                    (str(s.get('atleta_id')) == str(id_atl)) or
                                    (str(s.get('nome_giocatore', '')).strip().lower() == nome_atl.strip().lower())
                                )
                                if atl_match:
                                    sess_atl.append(s)

                            if not sess_atl:
                                atleti_senza_dati.append(nome_atl)
                                continue

                            def estrai_valore(s_item):
                                vals = s_item.get('valori', {})
                                if met_lat == "UNILATERAL":
                                    if opz_lat == "dx":
                                        return vals.get(f"{met_key}_dx")
                                    elif opz_lat == "sx":
                                        return vals.get(f"{met_key}_sx")
                                    elif opz_lat == "max":
                                        return vals.get(f"{met_key}_max", max(vals.get(f"{met_key}_dx", 0) or 0, vals.get(f"{met_key}_sx", 0) or 0) or None)
                                    elif opz_lat == "asym":
                                        return vals.get(f"{met_key}_asym_pct")
                                    else:
                                        return vals.get(f"{met_key}_mean", vals.get(f"{met_key}"))
                                else:
                                    return vals.get(met_key)

                            if is_pb_mode:
                                best_s = None
                                best_val = None
                                for s_i in sess_atl:
                                    v = estrai_valore(s_i)
                                    if v is not None and not pd.isna(v):
                                        try:
                                            v_num = float(v)
                                            if best_val is None:
                                                best_val = v_num
                                                best_s = s_i
                                            else:
                                                if is_higher_better and v_num > best_val:
                                                    best_val = v_num
                                                    best_s = s_i
                                                elif not is_higher_better and v_num < best_val:
                                                    best_val = v_num
                                                    best_s = s_i
                                        except Exception:
                                            pass
                                scelta_s = best_s or sess_atl[0]
                            else:
                                sess_atl.sort(key=lambda x: str(x.get('data', '')), reverse=True)
                                scelta_s = sess_atl[0]

                            val_fin = estrai_valore(scelta_s)
                            if val_fin is not None and not pd.isna(val_fin):
                                vals_s = scelta_s.get('valori', {})
                                dati_confronto.append({
                                    'atleta': nome_atl,
                                    'valore': float(val_fin),
                                    'data': scelta_s.get('data', '-'),
                                    'ambiente': scelta_s.get('condizione_ambiente', 'Outdoor'),
                                    'strumento': scelta_s.get('strumentazione', '-'),
                                    'valori_completi': vals_s,
                                    'val_dx': vals_s.get(f"{met_key}_dx"),
                                    'val_sx': vals_s.get(f"{met_key}_sx"),
                                    'asym_pct': vals_s.get(f"{met_key}_asym_pct"),
                                    'asym_dir': vals_s.get(f"{met_key}_asym_dir", "-")
                                })
                            else:
                                atleti_senza_dati.append(nome_atl)

                        # Rendering Risultati
                        if not dati_confronto:
                            st.markdown(
                                f"<div style='background:#f8fafc; border:1px solid #cbd5e1; border-radius:12px; padding:24px; text-align:center; margin-top:16px;'>"
                                f"<i class='bi bi-info-circle' style='font-size:24px; color:#0ea5e9;'></i>"
                                f"<div style='font-size:15px; font-weight:700; color:#0f172a; margin-top:8px;'>Nessun dato registrato per il test '{prot_scelto['nome_protocollo']}'</div>"
                                f"<div style='font-size:12.5px; color:#64748b; margin-top:4px;'>Gli atleti del tuo roster non hanno ancora misurazioni salvate per questo protocollo. Puoi registrarle nella scheda 'Inserimento & Storico Misure'.</div>"
                                f"</div>",
                                unsafe_allow_html=True
                            )
                            return

                        # Ordinamento
                        sort_reverse = is_higher_better if opz_lat != "asym" else False
                        dati_confronto.sort(key=lambda x: x['valore'], reverse=sort_reverse)

                        valori_arr = [d['valore'] for d in dati_confronto]
                        n_testati = len(dati_confronto)
                        cov_pct = (n_testati / n_roster) * 100 if n_roster > 0 else 0
                        top_ath = dati_confronto[0]['atleta']
                        top_val = dati_confronto[0]['valore']
                        mean_val = float(np.mean(valori_arr))
                        min_val = float(np.min(valori_arr))
                        max_val = float(np.max(valori_arr))

                        # KPI Roster
                        unit_str = f" {met_unit}" if met_unit and opz_lat != "asym" else (" %" if opz_lat == "asym" else "")
                        c_kp1, c_kp2, c_kp3, c_kp4 = st.columns(4)
                        with c_kp1:
                            st.markdown(card_kpi(tr("Copertura Roster", "Roster Coverage"), f"{n_testati}/{n_roster}", sottotitolo=f"{cov_pct:.0f}% {tr('degli atleti', 'of athletes')}", accento="#0ea5e9"), unsafe_allow_html=True)
                        with c_kp2:
                            st.markdown(card_kpi(tr("Top Performer", "Top Performer"), f"{top_val:.1f}{unit_str}", sottotitolo=f"{top_ath}", accento="#10b981"), unsafe_allow_html=True)
                        with c_kp3:
                            st.markdown(card_kpi(tr("Media Roster", "Team Average"), f"{mean_val:.1f}{unit_str}", sottotitolo=tr("Benchmark di Squadra", "Team Benchmark"), accento="#0284c7"), unsafe_allow_html=True)
                        with c_kp4:
                            st.markdown(card_kpi(tr("Range Prestazionale", "Performance Range"), f"{max_val - min_val:.1f}{unit_str}", sottotitolo=f"Min {min_val:.1f} | Max {max_val:.1f}", accento="#8b5cf6"), unsafe_allow_html=True)

                        st.markdown("<div style='margin-bottom:14px;'></div>", unsafe_allow_html=True)

                        # Grafico a Barre Orizzontali Plotly
                        # Inverti l'ordine per visualizzazione orizzontale dal primo in alto all'ultimo in basso
                        dati_plot = list(reversed(dati_confronto))
                        nomi_plot = [d['atleta'] for d in dati_plot]
                        vals_plot = [d['valore'] for d in dati_plot]

                        bar_colors = []
                        for d in dati_plot:
                            if d['atleta'] == top_ath:
                                bar_colors.append('#0ea5e9')  # Top performer
                            elif d['valore'] >= mean_val:
                                bar_colors.append('#10b981')  # Sopra media
                            else:
                                bar_colors.append('#94a3b8')  # Sotto media

                        fig_bar = go.Figure()
                        fig_bar.add_trace(go.Bar(
                            y=nomi_plot,
                            x=vals_plot,
                            orientation='h',
                            marker=dict(color=bar_colors, cornerradius=4),
                            text=[f"{v:.1f}{unit_str}" for v in vals_plot],
                            textposition='outside',
                            textfont=dict(color='#0f172a', size=11, family='Inter'),
                            hovertemplate="<b>%{y}</b><br>Valore: %{x:.2f}" + unit_str + "<extra></extra>"
                        ))

                        # Linea Media
                        fig_bar.add_vline(
                            x=mean_val,
                            line_dash="dash",
                            line_color="#ef4444",
                            line_width=2,
                            annotation_text=f"{tr('Media Roster', 'Mean')}: {mean_val:.1f}{unit_str}",
                            annotation_position="top right",
                            annotation_font=dict(size=10, color="#ef4444")
                        )

                        max_x_axis = max(vals_plot) * 1.15 if vals_plot else 10
                        fig_bar.update_layout(
                            title=f"<b>{tr('Ranking Roster', 'Roster Ranking')}: {scelta_met_disp}</b> ({criterio_tempo})",
                            title_font=dict(size=13, color='#0f172a', family='Inter'),
                            xaxis=dict(range=[0, max_x_axis], showgrid=True, gridcolor='#f1f5f9', title=f"{scelta_met_disp}"),
                            yaxis=dict(showgrid=False, tickfont=dict(color='#0f172a', size=12, family='Inter')),
                            height=max(280, len(dati_plot) * 45 + 100),
                            margin=dict(l=10, r=40, t=50, b=30),
                            plot_bgcolor='white',
                            paper_bgcolor='white'
                        )
                        st.plotly_chart(fig_bar, use_container_width=True)

                        # Leaderboard Table
                        st.markdown(
                            f"<div style='display:flex; align-items:center; gap:8px; margin-top:20px; margin-bottom:10px;'>"
                            f"<i class='bi bi-trophy' style='color:#0ea5e9; font-size:16px;'></i>"
                            f"<span style='font-size:15px; font-weight:800; color:#0f172a;'>{tr('Tabella Comparativa & Dettaglio Misure Roster', 'Comparative Table & Roster Breakdown')}</span>"
                            f"</div>",
                            unsafe_allow_html=True
                        )

                        rows_html = ""
                        for rank_idx, d in enumerate(dati_confronto, start=1):
                            delta_mean = d['valore'] - mean_val
                            delta_pct = (delta_mean / mean_val * 100) if mean_val != 0 else 0

                            if delta_pct >= 0:
                                col_d = "#10b981"
                                sign_d = "+"
                            else:
                                col_d = "#64748b"
                                sign_d = ""

                            # Podio badge
                            if rank_idx == 1:
                                rank_badge = "<span style='background:rgba(14,165,233,0.12); color:#0284c7; padding:2px 8px; border-radius:6px; font-weight:800; font-size:11px;'><i class='bi bi-trophy-fill' style='margin-right:4px;'></i>1°</span>"
                            elif rank_idx == 2:
                                rank_badge = "<span style='background:#f1f5f9; color:#475569; padding:2px 8px; border-radius:6px; font-weight:800; font-size:11px;'>2°</span>"
                            elif rank_idx == 3:
                                rank_badge = "<span style='background:#f1f5f9; color:#475569; padding:2px 8px; border-radius:6px; font-weight:800; font-size:11px;'>3°</span>"
                            else:
                                rank_badge = f"<span style='color:#64748b; font-weight:700; font-size:11px;'>#{rank_idx}</span>"

                            # Dettaglio Unilaterale se presente
                            unilat_txt = "-"
                            if d.get('val_dx') is not None and d.get('val_sx') is not None:
                                as_pct = d.get('asym_pct', 0) or 0
                                as_col = "#10b981" if as_pct <= 10 else ("#f59e0b" if as_pct <= 15 else "#ef4444")
                                unilat_txt = (
                                    f"Dx: <b>{d['val_dx']:.1f}</b> | Sx: <b>{d['val_sx']:.1f}</b> "
                                    f"<span style='background:rgba(255,255,255,0.8); color:{as_col}; font-weight:700; margin-left:4px;'>({as_pct:.1f}% {d.get('asym_dir', '-')})</span>"
                                )

                            amb_s = d.get('ambiente', 'Outdoor') or 'Outdoor'
                            strum_s = d.get('strumento')
                            setup_lbl = f"{amb_s} ({strum_s})" if (strum_s and str(strum_s).strip().lower() not in ('none', '-', '', 'null')) else amb_s

                            rows_html += (
                                f'<tr style="border-bottom:1px solid #f1f5f9; font-size:12.5px;">'
                                f'<td style="padding:10px 12px; text-align:center;">{rank_badge}</td>'
                                f'<td style="padding:10px 12px; font-weight:700; color:#0f172a;">{d["atleta"]}</td>'
                                f'<td style="padding:10px 12px; text-align:right; font-weight:800; color:#0284c7; font-size:13.5px;">{d["valore"]:.1f}{unit_str}</td>'
                                f'<td style="padding:10px 12px; text-align:center;"><span style="color:{col_d}; font-weight:700; font-size:12px;">{sign_d}{delta_pct:.1f}%</span></td>'
                                f'<td style="padding:10px 12px; text-align:center; color:#334155;">{unilat_txt}</td>'
                                f'<td style="padding:10px 12px; text-align:center; color:#64748b; font-size:11.5px;">{d["data"]}</td>'
                                f'<td style="padding:10px 12px; text-align:center; color:#64748b; font-size:11.5px;">{setup_lbl}</td>'
                                f'</tr>'
                            )

                        table_html = (
                            f"<div style='background:#ffffff; border:1px solid #e2e8f0; border-radius:12px; overflow-x:auto; margin-bottom:18px;'>"
                            f"<table style='width:100%; border-collapse:collapse; font-family:\"Inter\",sans-serif;'>"
                            f"<thead><tr style='background:#0f172a; color:#f8fafc; font-size:11px; text-transform:uppercase; letter-spacing:0.5px;'>"
                            f"<th style='padding:10px 12px; text-align:center;'>Pos</th>"
                            f"<th style='padding:10px 12px; text-align:left;'>Atleta</th>"
                            f"<th style='padding:10px 12px; text-align:right;'>Valore ({scelta_met_disp})</th>"
                            f"<th style='padding:10px 12px; text-align:center;'>vs Media Roster</th>"
                            f"<th style='padding:10px 12px; text-align:center;'>Dettaglio Bilaterale (Dx / Sx)</th>"
                            f"<th style='padding:10px 12px; text-align:center;'>Data Test</th>"
                            f"<th style='padding:10px 12px; text-align:center;'>Setup & Strumento</th>"
                            f"</tr></thead><tbody>{rows_html}</tbody></table></div>"
                        )
                        st.markdown(table_html, unsafe_allow_html=True)

                        # Matrice Multi-Parametrica del Test
                        if len(schema_scelto) > 1:
                            with st.expander(f"{tr('Matrice Multi-Parametrica Completa:', 'Full Multi-Parametric Matrix:')} {prot_scelto['nome_protocollo']}"):
                                cols_mat = [m.get('label', m.get('key')) for m in schema_scelto]
                                header_th = "".join([f"<th style='padding:8px 10px; text-align:center;'>{c}</th>" for c in cols_mat])

                                rows_mat = ""
                                for d in dati_confronto:
                                    v_comp = d.get('valori_completi', {})
                                    tds = ""
                                    for m_obj in schema_scelto:
                                        k_m = m_obj.get('key')
                                        u_m = m_obj.get('unit', '')
                                        val_k = v_comp.get(k_m)
                                        if val_k is None and m_obj.get('laterality') == 'UNILATERAL':
                                            val_k = v_comp.get(f"{k_m}_mean")

                                        val_str = f"{float(val_k):.1f} {u_m}" if val_k is not None and not pd.isna(val_k) else "-"
                                        tds += f"<td style='padding:8px 10px; text-align:center; font-size:12px;'>{val_str}</td>"

                                    rows_mat += f'<tr style="border-bottom:1px solid #f1f5f9;"><td style="padding:8px 10px; font-weight:700; color:#0f172a; font-size:12px;">{d["atleta"]}</td>{tds}</tr>'

                                mat_html = (
                                    f"<div style='background:#ffffff; border:1px solid #e2e8f0; border-radius:10px; overflow-x:auto;'>"
                                    f"<table style='width:100%; border-collapse:collapse; font-family:\"Inter\",sans-serif;'>"
                                    f"<thead><tr style='background:#1e293b; color:#f8fafc; font-size:10.5px; text-transform:uppercase;'>"
                                    f"<th style='padding:8px 10px; text-align:left;'>Atleta</th>{header_th}"
                                    f"</tr></thead><tbody>{rows_mat}</tbody></table></div>"
                                )
                                st.markdown(mat_html, unsafe_allow_html=True)

                        # Atleti Non Testati
                        if atleti_senza_dati:
                            st.markdown(
                                f"<div style='background:#f8fafc; border:1px dashed #cbd5e1; border-radius:10px; padding:12px 16px; margin-top:14px;'>"
                                f"<div style='font-size:12.5px; font-weight:700; color:#475569;'><i class='bi bi-person-x' style='margin-right:6px;'></i>{tr('Atleti del Roster in Attesa di Test', 'Roster Athletes Pending Test')} ({len(atleti_senza_dati)})</div>"
                                f"<div style='font-size:11.5px; color:#64748b; margin-top:4px;'>"
                                + ", ".join([f"<span style='background:#e2e8f0; color:#334155; padding:2px 6px; border-radius:4px; font-weight:600;'>{a}</span>" for a in atleti_senza_dati])
                                + f"</div></div>",
                                unsafe_allow_html=True
                            )

            _render_tab_confronti_body()

    # =========================================================================
    # TAB 5: GESTIONE & INSERIMENTO TEST (Coach, Staff & Atleta)
    # =========================================================================
    if "inserimento" in tab_map:
        with tab_map["inserimento"]:
            lbl_sub_gest = tr("Tabella Gestione Test Caricati (Modifica & Elimina)", "Uploaded Tests Management (Edit & Delete)")
            lbl_sub_import = tr("Caricamento Diretto da File Word (.docx)", "Direct Word Document Ingestion (.docx)")
            lbl_sub_ins = tr("Inserimento Nuova Misurazione Manuale", "Manual Test Measurement Entry")
            active_sub_ins = render_tab_navigation([lbl_sub_gest, lbl_sub_import, lbl_sub_ins], key="nav_test_fisici_gestione")

            # -------------------------------------------------------------
            # SUB-TAB 1: TABELLA GESTIONE TEST CARICATI (MODIFICA & ELIMINA)
            # -------------------------------------------------------------
            if active_sub_ins == lbl_sub_gest:
                st.markdown(
                    f"<div style='display:flex; align-items:center; gap:8px; margin-bottom:12px;'>"
                    f"<i class='bi bi-table' style='color:#0ea5e9; font-size:18px;'></i>"
                    f"<span style='font-size:16px; font-weight:800; color:#0f172a; text-transform:uppercase; letter-spacing:0.5px;'>"
                    f"{tr('Tabella Gestione Test Caricati', 'Uploaded Tests Management Table')} — {atleta_sel}"
                    f"</span></div>",
                    unsafe_allow_html=True
                )

                if not sessioni_atleta:
                    st.info(tr("Nessuna sessione di test registrata per questo atleta.", "No test sessions recorded for this athlete."))
                else:
                    # Filtri rapidi per la tabella
                    col_ft1, col_ft2, col_ft3 = st.columns([2, 2, 1.5])
                    with col_ft1:
                        date_univoche = sorted(list(set(str(s.get('data')) for s in sessioni_atleta if s.get('data'))), reverse=True)
                        sel_f_data = st.selectbox(tr("Filtra per Data:", "Filter by Date:"), [tr("Tutte le date", "All dates")] + date_univoche, key="flt_gest_data")
                    with col_ft2:
                        test_univoci = sorted(list(set(s.get('protocollo_info', {}).get('nome_protocollo', 'N/D') for s in sessioni_atleta)))
                        sel_f_test = st.selectbox(tr("Filtra per Protocollo:", "Filter by Protocol:"), [tr("Tutti i protocolli", "All protocols")] + test_univoci, key="flt_gest_test")
                    with col_ft3:
                        st.markdown(f"<div style='margin-top:28px; font-weight:800; color:#0ea5e9; font-size:13px;'>{len(sessioni_atleta)} test totali</div>", unsafe_allow_html=True)

                    sess_filtrate = sessioni_atleta
                    if sel_f_data != tr("Tutte le date", "All dates"):
                        sess_filtrate = [s for s in sess_filtrate if str(s.get('data')) == sel_f_data]
                    if sel_f_test != tr("Tutti i protocolli", "All protocols"):
                        sess_filtrate = [s for s in sess_filtrate if s.get('protocollo_info', {}).get('nome_protocollo') == sel_f_test]

                    righe_gest = []
                    for s in sorted(sess_filtrate, key=lambda x: str(x.get('data') or ''), reverse=True):
                        p_info = s.get('protocollo_info') or {}
                        sid = s.get('id') or ''
                        vals = s.get('valori', {}) or {}
                        
                        val_items = []
                        for vk, vv in vals.items():
                            if vk.endswith('_mean') or vk.endswith('_max') or vk.endswith('_dir'):
                                continue
                            clean_k = vk.replace('_', ' ').title()
                            val_items.append(f"{clean_k}: {vv}")
                        val_summary_str = " · ".join(val_items) if val_items else "-"

                        righe_gest.append({
                            "ID": sid,
                            "Data": s.get('data'),
                            "Test": p_info.get('nome_protocollo', 'N/D'),
                            "Macro-Area": p_info.get('macro_area', 'N/D'),
                            "Ambiente": s.get('condizione_ambiente', 'Outdoor'),
                            "Strumento": s.get('strumentazione') or '-',
                            "Valori Rilevati": val_summary_str,
                            "Note": s.get('note') or '-'
                        })
                    
                    df_gest = pd.DataFrame(righe_gest)
                    if not df_gest.empty:
                        st.dataframe(df_gest.drop(columns=['ID']), use_container_width=True)
                    else:
                        st.warning(tr("Nessun test corrisponde ai filtri selezionati.", "No tests match the selected filters."))

                    if is_coach and not df_gest.empty:
                        # Azioni rapide di gruppo
                        with st.expander(tr("Opzioni di Cancellazione di Gruppo (per Data o Completa)", "Batch Delete Options (by Date or Full)"), expanded=False):
                            col_bd1, col_bd2 = st.columns(2)
                            with col_bd1:
                                if sel_f_data != tr("Tutte le date", "All dates"):
                                    if st.button(f"🗑️ Elimina tutti i test del {sel_f_data} ({len(sess_filtrate)} test)", type="secondary", key="btn_del_batch_date"):
                                        c_del = 0
                                        for s_d in sess_filtrate:
                                            if s_d.get('id') and delete_sessione_test(s_d['id']):
                                                c_del += 1
                                        st.cache_data.clear()
                                        st.success(f"✓ Eliminati {c_del} test per la data {sel_f_data}!")
                                        st.rerun()
                                else:
                                    st.caption(tr("Seleziona una data specifica nel filtro sopra per eliminare tutti i test di quel giorno in un clic.", "Select a specific date above to batch delete that day's tests."))
                            with col_bd2:
                                if st.button(f"⚠️ Resetta e Cancella TUTTI i Test di {atleta_sel}", type="secondary", key="btn_del_all_ath_tests"):
                                    c_all = 0
                                    for s_a in sessioni_atleta:
                                        if s_a.get('id') and delete_sessione_test(s_a['id']):
                                            c_all += 1
                                    st.cache_data.clear()
                                    st.success(f"✓ Resettati ed eliminati {c_all} test per {atleta_sel}!")
                                    st.rerun()

                    if is_coach:
                        st.markdown("---")
                        st.markdown(
                            f"<div style='display:flex; align-items:center; gap:8px; margin-top:14px; margin-bottom:12px;'>"
                            f"<i class='bi bi-pencil-square' style='color:#0284c7; font-size:17px;'></i>"
                            f"<span style='font-size:15px; font-weight:800; color:#0f172a; text-transform:uppercase; letter-spacing:0.5px;'>"
                            f"{tr('Modifica o Elimina Test Selezionato', 'Edit or Delete Selected Test')}"
                            f"</span></div>",
                            unsafe_allow_html=True
                        )

                        dict_sess_map = {}
                        sessioni_atleta_sort = sorted(
                            sessioni_atleta,
                            key=lambda s: str(s.get('data') or ''),
                            reverse=True
                        )
                        for s in sessioni_atleta_sort:
                            p_i = s.get('protocollo_info') or {}
                            sid_str = str(s.get('id'))[:8] if s.get('id') else 'N/A'
                            lbl_sess = f"{s.get('data')} — {p_i.get('nome_protocollo', 'Test')} (#{sid_str})"
                            dict_sess_map[lbl_sess] = s

                        col_sel_mod, _ = st.columns([3, 1])
                        with col_sel_mod:
                            sess_to_mod_lbl = st.selectbox(
                                tr("Seleziona il test da modificare o eliminare:", "Select test to edit or delete:"),
                                list(dict_sess_map.keys()),
                                key="gest_test_session_sel"
                            )

                        target_sess_mod = dict_sess_map.get(sess_to_mod_lbl)
                        if target_sess_mod:
                            p_info_mod = target_sess_mod.get('protocollo_info') or {}
                            vals_curr_mod = target_sess_mod.get('valori', {}) or {}
                            schema_metrics_mod = p_info_mod.get('schema_metriche') or []

                            with st.container(border=True):
                                st.markdown(f"**Modifica Sessione: {p_info_mod.get('nome_protocollo', 'Test')} ({target_sess_mod.get('data')})**")
                                
                                c_m_d1, c_m_d2, c_m_d3 = st.columns(3)
                                with c_m_d1:
                                    dt_val_curr = pd.to_datetime(target_sess_mod.get('data'), errors='coerce')
                                    def_d = dt_val_curr.date() if pd.notnull(dt_val_curr) else datetime.date.today()
                                    mod_data_inp = st.date_input(tr("Data Esecuzione:", "Date:"), def_d, key=f"mod_d_{target_sess_mod.get('id')}")
                                with c_m_d2:
                                    amb_opts = ["Outdoor", "Indoor", "Palestra/Lab"]
                                    curr_amb = target_sess_mod.get('condizione_ambiente', 'Outdoor')
                                    idx_amb = amb_opts.index(curr_amb) if curr_amb in amb_opts else 0
                                    mod_amb_inp = st.selectbox(tr("Ambiente:", "Environment:"), amb_opts, index=idx_amb, key=f"mod_amb_{target_sess_mod.get('id')}")
                                with c_m_d3:
                                    mod_strum_inp = st.text_input(tr("Strumentazione:", "Equipment:"), value=target_sess_mod.get('strumentazione') or "", key=f"mod_strum_{target_sess_mod.get('id')}")

                                mod_note_inp = st.text_area(tr("Note e osservazioni:", "Notes:"), value=target_sess_mod.get('note') or "", height=60, key=f"mod_note_{target_sess_mod.get('id')}")

                                st.markdown(f"###### Metriche & Valori Rilevati — **{p_info_mod.get('nome_protocollo')}**")
                                
                                nuovi_valori_mod = {}
                                for m in schema_metrics_mod:
                                    k_m = m['key']
                                    lbl_m = m['label']
                                    unita_m = m.get('unit', '')
                                    lat_m = m.get('laterality', 'BILATERAL')

                                    if lat_m == 'UNILATERAL':
                                        st.markdown(f"**{lbl_m}** ({unita_m}) — *Unilaterale Dx/Sx:*")
                                        c_mdx, c_msx, c_masym = st.columns(3)
                                        with c_mdx:
                                            v_dx_cur = vals_curr_mod.get(f"{k_m}_dx")
                                            new_v_dx = st.number_input(f"{lbl_m} - Dx", value=float(v_dx_cur) if v_dx_cur is not None else None, key=f"mod_inp_{k_m}_dx_{target_sess_mod.get('id')}")
                                        with c_msx:
                                            v_sx_cur = vals_curr_mod.get(f"{k_m}_sx")
                                            new_v_sx = st.number_input(f"{lbl_m} - Sx", value=float(v_sx_cur) if v_sx_cur is not None else None, key=f"mod_inp_{k_m}_sx_{target_sess_mod.get('id')}")
                                        with c_masym:
                                            v_asym_cur = vals_curr_mod.get(f"{k_m}_asym_pct")
                                            calc_asym_mod, calc_dir_mod, _, _ = calcola_asimmetria_dx_sx(new_v_dx, new_v_sx)
                                            val_asym_def = float(v_asym_cur) if v_asym_cur is not None else calc_asym_mod
                                            new_v_asym = st.number_input(f"Asimmetria %", value=val_asym_def, key=f"mod_inp_{k_m}_asym_{target_sess_mod.get('id')}")

                                        if new_v_dx is not None: nuovi_valori_mod[f"{k_m}_dx"] = float(new_v_dx)
                                        if new_v_sx is not None: nuovi_valori_mod[f"{k_m}_sx"] = float(new_v_sx)
                                        if new_v_asym is not None:
                                            nuovi_valori_mod[f"{k_m}_asym_pct"] = float(new_v_asym)
                                            nuovi_valori_mod[f"{k_m}_asym_dir"] = calc_dir_mod if (new_v_dx and new_v_sx) else ("Dx" if new_v_asym > 0 else "Sx")
                                        if new_v_dx is not None and new_v_sx is not None:
                                            nuovi_valori_mod[f"{k_m}_mean"] = round((float(new_v_dx) + float(new_v_sx)) / 2.0, 2)
                                            nuovi_valori_mod[f"{k_m}_max"] = max(float(new_v_dx), float(new_v_sx))
                                    else:
                                        v_b_cur = vals_curr_mod.get(k_m)
                                        new_v_b = st.number_input(f"{lbl_m} ({unita_m})", value=float(v_b_cur) if v_b_cur is not None else None, key=f"mod_inp_{k_m}_{target_sess_mod.get('id')}")
                                        if new_v_b is not None:
                                            nuovi_valori_mod[k_m] = float(new_v_b)

                                # Conserva eventuali campi extra precedentemente inseriti
                                for ek, ev in vals_curr_mod.items():
                                    if ek not in nuovi_valori_mod and not any(ek.startswith(m['key']) for m in schema_metrics_mod):
                                        nuovi_valori_mod[ek] = ev

                                st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
                                c_act_save, c_act_del = st.columns([2.5, 1.2])
                                with c_act_save:
                                    if st.button(tr("Salva Modifiche Test", "Save Test Changes"), type="primary", use_container_width=True, key=f"btn_save_mod_{target_sess_mod.get('id')}"):
                                        if not nuovi_valori_mod:
                                            st.warning(tr("Compila almeno un valore prima di salvare.", "Fill in at least one value."))
                                        else:
                                            valori_finali_mod = calcola_formule_derivate_test(p_info_mod.get('codice_univoco'), nuovi_valori_mod)
                                            payload_update = {
                                                "data": mod_data_inp.strftime('%Y-%m-%d'),
                                                "condizione_ambiente": mod_amb_inp,
                                                "strumentazione": mod_strum_inp.strip() or None,
                                                "note": mod_note_inp.strip() or None,
                                                "valori": valori_finali_mod
                                            }
                                            ok_upd, res_upd = update_sessione_test_completa(target_sess_mod['id'], payload_update)
                                            if ok_upd:
                                                st.success(tr("Test aggiornato con successo!", "Test updated successfully!"))
                                                st.rerun()
                                            else:
                                                st.error(f"Errore durante l'aggiornamento: {res_upd}")
                                
                                with c_act_del:
                                    if st.button(tr("Elimina Test", "Delete Test"), type="secondary", use_container_width=True, key=f"btn_del_mod_{target_sess_mod.get('id')}"):
                                        if delete_sessione_test(target_sess_mod['id']):
                                            st.success(tr("Test eliminato con successo!", "Test deleted successfully!"))
                                            st.rerun()
                                        else:
                                            st.error(tr("Errore durante l'eliminazione.", "Error deleting test."))
                    else:
                        st.info(tr(
                            "La modifica e la cancellazione delle misurazioni sono riservate allo staff tecnico e medico.",
                            "Editing and deleting measurements are restricted to technical and medical staff."
                        ))

            # -------------------------------------------------------------
            # SUB-TAB 2: CARICAMENTO DIRETTO DA FILE WORD (.DOCX)
            # -------------------------------------------------------------
            elif active_sub_ins == lbl_sub_import:
                st.markdown(
                    f"<div style='display:flex; align-items:center; gap:8px; margin-bottom:12px;'>"
                    f"<i class='bi bi-file-earmark-word-fill' style='color:#2563eb; font-size:22px;'></i>"
                    f"<span style='font-size:16px; font-weight:800; color:#0f172a; text-transform:uppercase; letter-spacing:0.5px;'>"
                    f"{tr('Caricamento Diretto Risultati Test da File Word (.docx)', 'Direct Test Results Upload from Word File (.docx)')}"
                    f"</span></div>",
                    unsafe_allow_html=True
                )
                st.info(
                    tr(
                        "Carica il report Word (.docx) contenente i test VALD (ForceDecks, DynaMo, NordBord). Il sistema riconosce automaticamente tutte le date, i protocolli e le metriche bilaterali/asimmetrie.",
                        "Upload the Word (.docx) report containing VALD tests (ForceDecks, DynaMo, NordBord). The system automatically parses all dates, protocols, and bilateral/asymmetry metrics."
                    )
                )

                c_upl1, c_upl2 = st.columns([1.5, 2.5])
                with c_upl1:
                    atleta_dest = st.selectbox(
                        tr("Assegna Test all'Atleta:", "Assign Tests to Athlete:"),
                        atleta_nomi,
                        index=atleta_nomi.index(atleta_sel) if atleta_sel in atleta_nomi else 0,
                        key="word_import_atleta"
                    )
                    atleta_dest_id = dict_atleti.get(atleta_dest)
                    ambiente_dest = st.selectbox(
                        tr("Ambiente Predefinito:", "Default Environment:"),
                        ["Palestra/Lab", "Indoor", "Outdoor"],
                        key="word_import_ambiente"
                    )
                with c_upl2:
                    uploaded_docx = st.file_uploader(
                        tr("Seleziona o Trascina il File Word (.docx):", "Select or Drag Word File (.docx):"),
                        type=["docx"],
                        key="upl_docx_tests"
                    )

                docx_bytes = None
                if uploaded_docx:
                    docx_bytes = uploaded_docx.read()
                elif os.path.exists("data_supporto/Test Cobolli.docx") and "cobolli" in atleta_dest.lower():
                    if st.button("📄 Carica File Presente in Cartella: 'data_supporto/Test Cobolli.docx'", key="btn_load_local_docx"):
                        with open("data_supporto/Test Cobolli.docx", "rb") as f_local:
                            docx_bytes = f_local.read()

                if docx_bytes:
                    from parsers.test_docx_parser import parse_test_docx
                    parsed_tests = parse_test_docx(docx_bytes)
                    if not parsed_tests:
                        st.error(tr("Nessun test riconosciuto nel file caricato.", "No tests recognized in uploaded file."))
                    else:
                        dates_found = sorted(list(set(t['data'] for t in parsed_tests)))
                        st.success(f"✓ Rilevate **{len(parsed_tests)} sessioni di test** distribuite su **{len(dates_found)} date**: {', '.join(dates_found)}")
                        
                        # Tabella di anteprima
                        preview_rows = []
                        for t_item in parsed_tests:
                            p_code = t_item['codice_univoco']
                            p_info = protocolli_map.get(p_code, {})
                            v_dict = t_item['valori']
                            v_summary = " · ".join([f"{k.replace('_', ' ').title()}: {v}" for k, v in list(v_dict.items())[:3]])
                            if len(v_dict) > 3:
                                v_summary += f" (+{len(v_dict)-3} metriche)"
                            preview_rows.append({
                                "Data": t_item['data'],
                                "Dispositivo": t_item['device'],
                                "Test": p_info.get('nome_protocollo', t_item['protocollo_nome']),
                                "Codice": p_code,
                                "Metriche Rilevate": v_summary
                            })
                        
                        st.dataframe(pd.DataFrame(preview_rows), use_container_width=True)
                        
                        if st.button("💾 Conferma & Salva Tutte le Sessioni nel Database", type="primary", key="btn_confirm_import_docx"):
                            with st.spinner("Salvataggio in corso..."):
                                imported_count = 0
                                for t_item in parsed_tests:
                                    p_code = t_item['codice_univoco']
                                    p_info = protocolli_map.get(p_code, {})
                                    proto_id = p_info.get('id', p_code)
                                    
                                    payload = {
                                        "atleta_id": atleta_dest_id,
                                        "nome_giocatore": atleta_dest,
                                        "atleta": atleta_dest,
                                        "protocollo_id": proto_id,
                                        "codice_univoco": p_code,
                                        "data": t_item['data'],
                                        "condizione_ambiente": ambiente_dest,
                                        "strumentazione": f"{t_item['device']} Vald",
                                        "valori": t_item['valori'],
                                        "note": f"Importato da file Word: {t_item['protocollo_nome']}"
                                    }
                                    upsert_sessione_test(payload)
                                    imported_count += 1
                                    
                                st.cache_data.clear()
                                st.success(f"🎉 **{imported_count} test salvati con successo per {atleta_dest}!**")
                                st.rerun()

            # -------------------------------------------------------------
            # SUB-TAB 3: INSERIMENTO NUOVA MISURAZIONE TEST
            # -------------------------------------------------------------
            elif active_sub_ins == lbl_sub_ins:
                if is_coach:
                    st.markdown(f"<div style='display:flex; align-items:center; gap:8px; margin-bottom:12px;'><i class='bi bi-pencil-square' style='color:#0ea5e9; font-size:18px;'></i><span style='font-size:16px; font-weight:800; color:#0f172a; text-transform:uppercase; letter-spacing:0.5px;'>{tr('Inserimento Nuova Misurazione Test', 'New Test Data Entry')}</span></div>", unsafe_allow_html=True)
                    
                    def _on_macro_ins_change():
                        if "form_ins_prot" in st.session_state:
                            del st.session_state["form_ins_prot"]

                    c_in1, c_in2, c_in3 = st.columns(3)
                    with c_in1:
                        atleta_ins = atleta_sel
                        st.text_input(
                            tr("Atleta Attivo:", "Active Athlete:"),
                            value=atleta_sel,
                            disabled=True,
                            key="form_ins_atleta_readonly"
                        )
                    with c_in2:
                        data_ins = st.date_input(tr("Data Esecuzione:", "Execution Date:"), datetime.date.today(), key="form_ins_data")
                    with c_in3:
                        condizione_ins = st.selectbox(
                            tr("Ambiente / Condizione:", "Environment:"),
                            ["Outdoor", "Indoor", "Palestra/Lab"],
                            key="form_ins_ambiente"
                        )

                    c_m1, c_m2 = st.columns(2)
                    with c_m1:
                        macro_ins = st.selectbox(
                            tr("Macro-Area Test:", "Macro-Area:"),
                            macro_tutte,
                            key="form_ins_macro",
                            on_change=_on_macro_ins_change
                        )
                    
                    prot_disponibili = [p for p in catalogo if p.get('macro_area') == macro_ins]
                    map_prot_ins = {p['nome_protocollo']: p for p in prot_disponibili}
                    opzioni_prot_ins = list(map_prot_ins.keys()) if map_prot_ins else ["Nessun protocollo"]

                    curr_ins_p = st.session_state.get("form_ins_prot")
                    idx_ins_p = opzioni_prot_ins.index(curr_ins_p) if curr_ins_p in opzioni_prot_ins else 0

                    with c_m2:
                        nome_p_ins = st.selectbox(
                            tr("Protocollo Test:", "Protocol:"),
                            opzioni_prot_ins,
                            index=idx_ins_p,
                            key="form_ins_prot"
                        )

                    target_prot = map_prot_ins.get(nome_p_ins)
                    valori_input = {}

                    st.markdown("---")
                    if target_prot:
                        st.markdown(f"##### Variabili di Misurazione — **{target_prot['nome_protocollo']}**")
                        st.caption("ℹ️ *Sparse Data: compila solo i dati rilevati; lascia vuoti i campi non misurati.*")

                        is_m0v3_flagship = (target_prot.get('codice_univoco') == 'm0v3_tennis_test')
                        schema = target_prot.get('schema_metriche') or []

                        for m in schema:
                            k = m['key']
                            lbl = m['label']
                            unita = m.get('unit', '')
                            lat = m.get('laterality', 'BILATERAL')

                            # Gestione Indoor su M0V3 Tennis Test
                            is_decay_field = ("decay" in k.lower() or "vmax" in k.lower())
                            if is_m0v3_flagship and condizione_ins == "Indoor" and is_decay_field:
                                st.caption(f"**{lbl}**: *Non richiesto in ambiente Indoor (omesso dal calcolo)*")
                                continue

                            if lat == 'UNILATERAL':
                                st.markdown(f"**{lbl}** ({unita}) — *Unilaterale Dx/Sx:*")
                                c_dx, c_sx, c_asym = st.columns(3)
                                with c_dx:
                                    v_dx = st.number_input(f"{lbl} - Destro (Dx)", value=None, placeholder="Valore Dx", key=f"inp_{k}_dx")
                                with c_sx:
                                    v_sx = st.number_input(f"{lbl} - Sinistro (Sx)", value=None, placeholder="Valore Sx", key=f"inp_{k}_sx")
                                with c_asym:
                                    calc_asym, calc_dir, _, _ = calcola_asimmetria_dx_sx(v_dx, v_sx)
                                    v_asym_manual = st.number_input(f"Asimmetria % (Opzionale)", value=calc_asym, placeholder="es. 10.5", key=f"inp_{k}_asym")

                                if v_dx is not None: valori_input[f"{k}_dx"] = float(v_dx)
                                if v_sx is not None: valori_input[f"{k}_sx"] = float(v_sx)
                                if v_asym_manual is not None:
                                    valori_input[f"{k}_asym_pct"] = float(v_asym_manual)
                                    valori_input[f"{k}_asym_dir"] = calc_dir if (v_dx and v_sx) else ("Dx" if v_asym_manual>0 else "Sx")
                                if v_dx is not None and v_sx is not None:
                                    valori_input[f"{k}_mean"] = round((float(v_dx) + float(v_sx)) / 2.0, 2)
                                    valori_input[f"{k}_max"] = max(float(v_dx), float(v_sx))
                            else:
                                val_b = st.number_input(f"{lbl} ({unita})", value=None, placeholder="Opzionale", key=f"inp_{k}")
                                if val_b is not None:
                                    valori_input[k] = float(val_b)

                        c_extra1, c_extra2 = st.columns([1.5, 2.5])
                        with c_extra1:
                            strumento_ins = st.text_input(tr("Strumentazione Utilizzata (opzionale):", "Equipment:"), placeholder="es. VALD ForceDecks, Microgate", key="inp_strum")
                        with c_extra2:
                            note_ins = st.text_area(tr("Note e osservazioni cliniche / prestative:", "Notes:"), key="inp_note", height=68)
                    else:
                        st.info(tr("Nessun protocollo di test selezionato per questa macro-area.", "No test protocol selected for this macro-area."))

                    btn_salva = st.button(tr("Salva Sessione Test", "Save Test Session"), type="primary", use_container_width=True, key="btn_salva_test_action")

                    if btn_salva:
                        if not target_prot:
                            st.error("Seleziona un protocollo valido.")
                        elif not valori_input:
                            st.warning("Compila almeno un parametro del test prima di salvare.")
                        else:
                            valori_finali = calcola_formule_derivate_test(target_prot.get('codice_univoco'), valori_input)
                            
                            payload = {
                                "atleta_id": dict_atleti[atleta_ins],
                                "nome_giocatore": atleta_ins,
                                "protocollo_id": target_prot['id'] if 'id' in target_prot else '00000000-0000-0000-0000-000000000000',
                                "data": data_ins.strftime('%Y-%m-%d'),
                                "condizione_ambiente": condizione_ins,
                                "strumentazione": strumento_ins or None,
                                "valori": valori_finali,
                                "note": note_ins or None,
                                "inserito_da": user.id if user else None
                            }
                            ok, res = upsert_sessione_test(payload)
                            if ok:
                                st.success(f"Test {target_prot['nome_protocollo']} salvato con successo per {atleta_ins}!")
                                st.rerun()
                            else:
                                if "PGRST205" in str(res) or "Could not find the table" in str(res):
                                    st.error(
                                        "**Tabella non trovata su Supabase**: La tabella `sessioni_test` non è ancora presente nel database.\n\n"
                                        "Per attivarla in 30 secondi:\n"
                                        "1. Apri la console di **Supabase** -> **SQL Editor**.\n"
                                        "2. Incolla ed esegui il contenuto del file `setup_test_fisici.sql` presente nella root del progetto.\n"
                                        "3. Torna qui e premi di nuovo Salva!"
                                    )
                                else:
                                    st.error(f"Errore durante il salvataggio: {res}")
                else:
                    st.info(tr(
                        "L'inserimento di nuove misurazioni è riservato allo staff tecnico e medico.",
                        "New measurement entry is restricted to coaching and medical staff."
                    ))

    # =========================================================================
    # TAB 6: COSTRUTTORE PROTOCOLLI CUSTOM (Custom Test Builder)
    # =========================================================================
    if "builder" in tab_map:
        with tab_map["builder"]:
            if not is_coach:
                st.info(tr(
                    "Il costruttore di protocolli personalizzati è riservato allo staff tecnico e agli amministratori.",
                    "Custom test builder is reserved for coaching staff and administrators."
                ))
            else:
                st.markdown(f"<div style='display:flex; align-items:center; gap:8px; margin-bottom:12px;'><i class='bi bi-tools' style='color:#0ea5e9; font-size:18px;'></i><span style='font-size:16px; font-weight:800; color:#0f172a; text-transform:uppercase; letter-spacing:0.5px;'>{tr('Costruttore Protocolli Personalizzati', 'Custom Test Builder')}</span></div>", unsafe_allow_html=True)
                st.caption(tr(
                    "Crea un protocollo di test personalizzato per la tua accademia o struttura atletica. Sarà immediatamente integrato nel sistema e nei report.",
                    "Create a custom test protocol for your academy. It will be immediately available in tests and reports."
                ))

                # Form Builder Reattivo
                c_cust1, c_cust2 = st.columns(2)
                with c_cust1:
                    cust_nome = st.text_input("Nome del Protocollo:", placeholder="es. Test Navetta 4x10m con Racchetta", key="cust_nome")
                    cust_macro = st.selectbox(
                        "Macro-Area di Riferimento:",
                        macro_tutte + ["Antropometria & Custom"],
                        key="cust_macro"
                    )
                with c_cust2:
                    categorie_10 = [
                        "Specifici Campo & Resilienza", "Velocità Lineare & Accelerazione", "Agilità & Cambi di Direzione (COD)",
                        "Capacità & Potenza Metabolica (Endurance & RSA)", "Esplosività & Salto (Neuromuscolare)",
                        "Forza Isometrica & Dinamometria", "Forza Eccentrica & Prevenzione",
                        "Mobilità, ROM Articolare & Flessibilità", "Controllo Motorio & Stabilometria",
                        "Antropometria & Composizione Corporea"
                    ]
                    cust_cat = st.selectbox("Categoria Fisiologica:", categorie_10, key="cust_cat")
                    cust_num_var = st.slider("Numero di Variabili / Metriche da creare:", min_value=1, max_value=8, value=3, key="cust_num_var")

                st.markdown("---")
                st.markdown("##### Definizione Variabili e Metriche del Test")

                unita_opzioni = ["s", "ms", "cm", "m", "mm", "°", "N", "N/kg", "Nm", "W", "W/kg", "kg", "%BW", "km/h", "m/s", "bpm", "mmol/L", "ml/kg/min", "%", "ratio", "Indice", "Livello"]
                metriche_custom = []

                for v_idx in range(cust_num_var):
                    c_v1, c_v2, c_v3, c_v4 = st.columns([2.5, 1.2, 1.8, 1.5])
                    with c_v1:
                        v_label = st.text_input(f"Nome Metrica #{v_idx+1}", value=f"Variabile {v_idx+1}", key=f"cust_lbl_{v_idx}")
                    with c_v2:
                        v_unit = st.selectbox(f"Unità #{v_idx+1}", unita_opzioni, index=0, key=f"cust_unit_{v_idx}")
                    with c_v3:
                        v_dir = st.selectbox(
                            f"Direzione #{v_idx+1}",
                            ["HIGHER_IS_BETTER (Più alto è meglio)", "LOWER_IS_BETTER (Più basso è meglio)", "NEUTRAL (Neutro)"],
                            key=f"cust_dir_{v_idx}"
                        )
                        dir_code = "HIGHER_IS_BETTER" if "HIGHER" in v_dir else ("LOWER_IS_BETTER" if "LOWER" in v_dir else "NEUTRAL")
                    with c_v4:
                        v_lat = st.selectbox(f"Lateralità #{v_idx+1}", ["BILATERAL (Bilaterale)", "UNILATERAL (Dx/Sx)"], key=f"cust_lat_{v_idx}")
                        lat_code = "UNILATERAL" if "UNILATERAL" in v_lat else "BILATERAL"

                    k_clean = v_label.lower().replace(' ', '_').replace('/', '_').replace('-', '_')
                    metriche_custom.append({
                        "key": f"m_{k_clean}_{v_idx}",
                        "label": v_label,
                        "unit": v_unit,
                        "direction": dir_code,
                        "laterality": lat_code,
                        "is_primary_kpi": (v_idx == 0),
                        "color": "#0ea5e9"
                    })

                st.markdown("---")
                st.markdown("##### Documentazione Scientifica & Istruzioni Manuale (Opzionali)")
                cust_obj = st.text_area("Obiettivo Fisiologico / Biomeccanico:", key="cust_obj")
                cust_exec = st.text_area("Protocollo Operativo di Esecuzione:", key="cust_exec")
                cust_interp = st.text_area("Guida all'Interpretazione dei Risultati:", key="cust_interp")

                btn_crea_custom = st.button(tr("Salva Protocollo Personalizzato", "Save Custom Protocol"), type="primary", use_container_width=True, key="btn_save_custom_proto_action")

                if btn_crea_custom:
                    if not cust_nome.strip():
                        st.error("Inserisci il nome del protocollo.")
                    else:
                        cod_cust = f"custom_{user.id[:6]}_{cust_nome.lower().replace(' ', '_')}"
                        payload_cust = {
                            "codice_univoco": cod_cust,
                            "creatore_id": user.id if user else None,
                            "nome_protocollo": cust_nome.strip(),
                            "macro_area": cust_macro,
                            "categoria": cust_cat,
                            "schema_metriche": metriche_custom,
                            "manuale_obiettivi": cust_obj.strip() or None,
                            "manuale_esecuzione": cust_exec.strip() or None,
                            "manuale_interpretazione": cust_interp.strip() or None
                        }
                        ok, res = upsert_protocollo_custom(payload_cust)
                        if ok:
                            st.success(f"Protocollo '{cust_nome}' creato e integrato nel catalogo!")
                            st.rerun()
                        else:
                            st.error(f"Errore durante la creazione del protocollo: {res}")
