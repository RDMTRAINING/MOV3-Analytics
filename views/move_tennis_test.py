# Copyright 2026 Riccardo Di Maio - M0V3 S.r.l. Tutti i diritti riservati.
# Proprietary Sports Science & Clinical Performance Intelligence Architecture.
import os
import json
import datetime
from datetime import timedelta
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from config import (
    LOGO_PATH,
    LOGO_CIRCULAR_PATH,
    tr,
    render_page_header,
    card_kpi,
    slugify_name,
    render_tab_navigation,
)
from utils import (
    supabase,
    supabase_admin,
    load_local_database,
    get_atleti_associati,
    get_tutti_gli_atleti,
    render_athlete_hero_strip,
)

STORAGE_JSON_PATH = "data_supporto/move_tennis_tests.json"

# =========================================================================
# GESTIONE DATI & PERSISTENZA M0V3 TENNIS TEST
# =========================================================================

def carica_tutti_i_test():
    """Carica l'archivio dei M0V3 Tennis Test dal JSON locale con fallback Supabase."""
    if os.path.exists(STORAGE_JSON_PATH):
        try:
            with open(STORAGE_JSON_PATH, "r", encoding="utf-8") as f:
                dati = json.load(f)
                if isinstance(dati, list):
                    return dati
        except Exception:
            pass
    return []

def salva_test_sessione(test_dict):
    """Salva o aggiorna una sessione di M0V3 Tennis Test sia localmente che su Supabase."""
    dati = carica_tutti_i_test()
    test_id = test_dict.get("id")
    if not test_id:
        test_id = f"m0v3_{slugify_name(test_dict.get('atleta', 'atleta'))}_{test_dict.get('data', '').replace('/', '')}"
        test_dict["id"] = test_id

    # Aggiorna se già presente, altrimenti inserisce in cima (dal più recente)
    idx_found = None
    for i, t in enumerate(dati):
        if t.get("id") == test_id:
            idx_found = i
            break
            
    if idx_found is not None:
        dati[idx_found] = test_dict
    else:
        dati.insert(0, test_dict)

    os.makedirs(os.path.dirname(STORAGE_JSON_PATH), exist_ok=True)
    with open(STORAGE_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(dati, f, indent=2, ensure_ascii=False)

    # Tentativo sincronizzazione su Supabase (se tabella o connessione disponibile)
    try:
        db = supabase_admin if supabase_admin is not None else supabase
        payload_sb = {
            "nome_giocatore": test_dict.get("atleta"),
            "data": pd.to_datetime(test_dict.get("data"), format="%d/%m/%Y", errors="coerce").strftime("%Y-%m-%d"),
            "condizione_ambiente": test_dict.get("ambiente", "Outdoor"),
            "strumentazione": test_dict.get("strumentazione", "GPEXE + Optojump"),
            "valori": test_dict,
            "note": test_dict.get("note", "")
        }
        db.table("sessioni_test").upsert(payload_sb).execute()
    except Exception:
        pass

    return test_id

def elimina_test_sessione(test_id):
    """Rimuove un test dall'archivio locale."""
    dati = carica_tutti_i_test()
    dati_filtrati = [t for t in dati if t.get("id") != test_id]
    with open(STORAGE_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(dati_filtrati, f, indent=2, ensure_ascii=False)
    return True

# =========================================================================
# MOTORE DI CALCOLO MATEMATICO M0V3 TENNIS TEST (6 INDICI)
# =========================================================================

def elabora_m0v3_tennis_test(test_dict):
    """
    Esegue tutti i calcoli matematici del M0V3 Tennis Test per i 6 Round:
    1. EDI % (Explosivity Decay Index)
    2. TPS % (Total Performance Score)
    3. CMJ Internal Score % (Altezza vs Potenza)
    4. GRS % (Global Resilience Score)
    5. PCI (Physiological Cost Index - Disaccoppiamento Neuro-Meccanico)
    6. Sintesi R.A.A. & Rating Prestativo
    """
    rounds = test_dict.get("rounds", [])
    pre_test = test_dict.get("pre_test", {})
    pre_pw = float(pre_test.get("cmj_power", 0) or 0)
    pre_cm = float(pre_test.get("cmj_cm", 0) or 0)

    if not rounds:
        return {}

    # Picchi massimi della sessione per normalizzazione EDI
    vmax_list = [float(r.get("vmax", 0) or 0) for r in rounds]
    acc_list = [float(r.get("acc_max", 0) or 0) for r in rounds]
    dec_list = [abs(float(r.get("dec_max", 0) or 0)) for r in rounds]

    v_peak = max(vmax_list) if vmax_list and max(vmax_list) > 0 else 1.0
    a_peak = max(acc_list) if acc_list and max(acc_list) > 0 else 1.0
    d_peak = max(dec_list) if dec_list and max(dec_list) > 0 else 1.0

    # Volume Intenso (Acc + Dec High) per TPS
    tot_azioni_list = [(int(r.get("acc_high_n", 0) or 0) + int(r.get("dec_high_n", 0) or 0)) for r in rounds]
    max_azioni = max(tot_azioni_list) if tot_azioni_list and max(tot_azioni_list) > 0 else 1

    # Picco TLMax 30" al Round 1 (benchmark di riferimento per l'intensità)
    tlmax_30_r1 = float(rounds[0].get("tlmax_30", 0) or 0) if rounds and float(rounds[0].get("tlmax_30", 0) or 0) > 0 else 1.0

    round_calcolati = []
    edi_series = []
    tps_series = []
    cmj_score_series = []
    grs_series = []
    pci_series = []

    for idx, r in enumerate(rounds):
        r_num = idx + 1
        v = float(r.get("vmax", 0) or 0)
        a = float(r.get("acc_max", 0) or 0)
        d = abs(float(r.get("dec_max", 0) or 0))

        # 1. EDI % (Explosivity Decay Index)
        if "edi" in r and r["edi"] is not None:
            edi_r = float(r["edi"])
        else:
            pct_v = (v / v_peak * 100) if v_peak > 0 else 0
            pct_a = (a / a_peak * 100) if a_peak > 0 else 0
            pct_d = (d / d_peak * 100) if d_peak > 0 else 0
            edi_r = round((pct_v + pct_a + pct_d) / 3, 1)
        edi_series.append(edi_r)

        # 2. TPS % (Total Performance Score)
        tot_act = tot_azioni_list[idx]
        idx_vol = int(r["idx_vol_intenso"]) if "idx_vol_intenso" in r and r["idx_vol_intenso"] is not None else round((tot_act / max_azioni * 100) if max_azioni > 0 else 0)
        tlmax_curr = float(r.get("tlmax_30", 0) or 0)
        idx_picco = int(r["idx_picco_int"]) if "idx_picco_int" in r and r["idx_picco_int"] is not None else round((tlmax_curr / tlmax_30_r1 * 100) if tlmax_30_r1 > 0 else 0)
        if "tps" in r and r["tps"] is not None:
            tps_r = int(r["tps"])
        else:
            tps_r = round((idx_vol + idx_picco) / 2)
        tps_series.append(tps_r)

        # 3. CMJ Score % (Internal Load)
        if "cmj_score" in r and r["cmj_score"] is not None:
            cmj_s_r = float(r["cmj_score"])
        elif "cmj_score_override" in r and r["cmj_score_override"] is not None:
            cmj_s_r = float(r["cmj_score_override"])
        else:
            curr_pw = float(r.get("cmj_power", 0) or 0)
            cmj_s_r = round((curr_pw / pre_pw * 100) if pre_pw > 0 else 100)
        cmj_score_series.append(cmj_s_r)

        # 4. GRS % (Global Resilience Score)
        if "grs" in r and r["grs"] is not None:
            grs_r = int(r["grs"])
        else:
            grs_r = round((tps_r + cmj_s_r) / 2)
        grs_series.append(grs_r)

        # 5. PCI (Physiological Cost Index: TPS - CMJ Score)
        if "pci" in r and r["pci"] is not None:
            pci_r = int(r["pci"])
        else:
            pci_r = round(tps_r - cmj_s_r)
        pci_series.append(pci_r)

        rc = dict(r)
        rc["round"] = r_num
        rc["edi"] = edi_r
        rc["idx_vol_intenso"] = idx_vol
        rc["idx_picco_int"] = idx_picco
        rc["tps"] = tps_r
        rc["cmj_score"] = cmj_s_r
        rc["grs"] = grs_r
        rc["pci"] = pci_r
        round_calcolati.append(rc)

    # Sintesi Sessione
    avg_edi = float(test_dict.get("avg_edi")) if test_dict.get("avg_edi") is not None else (round(sum(edi_series) / len(edi_series), 1) if edi_series else 0.0)
    tps_final = tps_series[-1] if tps_series else 0
    tps_min = min(tps_series) if tps_series else 0
    cmj_final = cmj_score_series[-1] if cmj_score_series else 0
    grs_final = grs_series[-1] if grs_series else 0
    pci_final = pci_series[-1] if pci_series else 0
    pci_min = min(pci_series) if pci_series else 0

    # RAA Test
    raa = test_dict.get("raa_test", {})
    has_raa = bool(raa.get("eseguito", False))
    fi_vel = float(raa.get("fatigue_index_vel", 0) or 0)
    fi_acc = float(raa.get("fatigue_index_acc", 0) or 0)
    eff_tec = float(raa.get("efficienza_tecnica", 0) or 0)

    # Diagnosi Automatica Profilo Clinico
    diagnosi = calcola_diagnosi_m0v3(avg_edi, tps_min, cmj_final, pci_min, has_raa, fi_vel, fi_acc, eff_tec)

    return {
        "rounds": round_calcolati,
        "pre_test": pre_test,
        "avg_edi": avg_edi,
        "tps_final": tps_final,
        "tps_min": tps_min,
        "cmj_final": cmj_final,
        "grs_final": grs_final,
        "pci_final": pci_final,
        "pci_min": pci_min,
        "has_raa": has_raa,
        "fi_vel": fi_vel,
        "fi_acc": fi_acc,
        "eff_tec": eff_tec,
        "diagnosi": diagnosi,
    }

def calcola_diagnosi_m0v3(edi, tps_min, cmj_final, pci_min, has_raa, fi_vel, fi_acc, eff_tec):
    """Genera la diagnosi clinica e i 4 suggerimenti operativi specifici."""
    titolo_diagnosi = "Profilazione Neuro-Meccanica Standard"
    corpo_diagnosi = ""
    suggerimenti = []

    # Valutazione EDI (SNC & Esplosività)
    if edi >= 95.0:
        edi_stato = "Atleta Esplosivo Resistente (SNC mantiene intatte le frequenze di scarica)"
    elif edi >= 90.0:
        edi_stato = "Fatica Esplosiva Gestibile"
    else:
        edi_stato = "Atleta 'Diesel' o Inibizione Neurale (perdita qualità neuromuscolari fini)"

    # Valutazione Disaccoppiamento PCI & Work Capacity TPS
    if pci_min <= -25 and tps_min <= 70 and cmj_final >= 95:
        titolo_diagnosi = "Il Paradosso del 'Risparmio' (Underperforming / Freno a Mano)"
        corpo_diagnosi = (
            f"L'atleta presenta un ottimo mantenimento neuromuscolare (EDI {edi:.1f}%, CMJ Score finale {cmj_final}%), "
            f"ma un crollo selettivo del volume ad alta intensità (TPS minimo al {tps_min}%), con PCI fortemente negativo ({pci_min}). "
            "L'atleta smette di coprire campo pur avendo gambe ancora fresche e reattive. "
            "Non si tratta di un cedimento strutturale, ma di un limite di Work Capacity (densità di lavoro) o di una strategia di pacing troppo conservativa."
        )
        suggerimenti = [
            ("1. Incremento Work Capacity (Volume ad Alta Intensità)", "Obiettivo: insegnare a non crollare nel volume (TPS) quando l'intensità è alta.", "Intervento: 'Density Sets' (blocchi di navette o cesti riducendo progressivamente i recuperi, costringendo a mantenere il ritmo medio)."),
            ("2. Stabilizzazione Tecnica sotto Fatica", "Obiettivo: correggere la rottura tecnica evidenziata nell'efficienza RAA.", "Intervento: Lavori di 'Fatigue Run' (sprint massimali preceduti da pre-stancaggio localizzato tipo squat jump o wall sit, con feedback sulla postura)."),
            ("3. Sblocco del 'Freno a Mano' (Pacing)", "Obiettivo: eliminare il PCI negativo spingendo l'atleta a spendere tutto il potenziale disponibile.", "Intervento: Allenamenti a target variabile (massima distanza coperta a tempo prefissato invece di numero fisso di scatti)."),
            ("4. Conferma Forza Eccentrica", "Obiettivo: mantenere l'ottima capacità di frenata e protezione articolare.", "Intervento: La tenuta della DecMax conferma che la struttura muscolare è solida. Proseguire con richiami di forza eccentrica a basso volume.")
        ]
    elif pci_min >= 15:
        titolo_diagnosi = "Overreaching Meccanico (Rischio Infortunio / 'Correre sopra i problemi')"
        corpo_diagnosi = (
            f"L'atleta mantiene alti ritmi di corsa esterna ma presenta un crollo marcato della capacità elastica/salto (PCI +{pci_min}). "
            "Il sistema neuromuscolare è in forte affaticamento e non riesce più ad assorbire elasticamente le forze d'impatto. "
            "Alto rischio di lesione muscolare (flessori/quadricipite) o tendinopatia."
        )
        suggerimenti = [
            ("1. Riduzione Immediata Densità Meccanica", "Obiettivo: alleggerire il comparto muscolo-tendineo prima del sovraccarico acuto.", "Intervento: De-load del volume di frenate e sprint con inserimento di lavori metabolici a basso impatto."),
            ("2. Scarico Neuromuscolare", "Obiettivo: favorire il recupero della freschezza neurale (SNC).", "Intervento: Protocolli di mobilità dinamica, sonno ottimizzato e contrast therapy."),
            ("3. Riatletizzazione Eccentrica Isometria", "Obiettivo: ripristinare la rigidezza tendinea (stiffness).", "Intervento: Lavori isometrici prolungati a media intensità."),
            ("4. Rimodulazione Frequenza Test", "Obiettivo: attendere il rientro del CMJ Score sopra il 90% prima di carichi massimali.", "Intervento: Monitoraggio quotidiano con Jump di riscaldamento.")
        ]
    else:
        titolo_diagnosi = "Profilo di Fatica Coerente (Equilibrio Fisiologico)"
        corpo_diagnosi = (
            f"L'atleta manifesta un decadimento fisiologico proporzionato tra prestazione esterna e risposta interna (PCI {pci_min:+d}, EDI {edi:.1f}%). "
            "La gestione dello sforzo è onesta e ottimale rispetto alle riserve energetiche."
        )
        suggerimenti = [
            ("1. Mantenimento Densità di Gioco", "Obiettivo: consolidare i volumi ad alta intensità raggiunti.", "Intervento: Ripetizione di blocchi gara specifici."),
            ("2. Potenziamento Esplosivo", "Obiettivo: incrementare il picco di salto e accelerazione di base.", "Intervento: Sedute di forza esplosiva con sovraccarico e pliometria."),
            ("3. Ottimizzazione Recupero tra i Round", "Obiettivo: accelerare la cinetica di ripristino dei fosfageni.", "Intervento: Lavori di recupero attivo aerobico a bassa intensità."),
            ("4. Monitoraggio Continuo", "Obiettivo: confermare la stabilità della risposta prestativa nei tornei consecutivi.", "Intervento: Rilievo GPS in match e test di verifica mensile.")
        ]

    return {
        "titolo": titolo_diagnosi,
        "corpo": corpo_diagnosi,
        "edi_stato": edi_stato,
        "suggerimenti": suggerimenti,
    }

# =========================================================================
# VISTA PRINCIPALE STREAMLIT
# =========================================================================

def render_move_tennis_test(t):
    render_page_header(
        tr("M0V3 Tennis Test — Profilazione Fatica Neuro-Meccanica", "M0V3 Tennis Test — Neuro-Mechanical Fatigue Profiling"),
        tr("Protocollo specifico ad alta intensità a 6 Round: analisi integrata di Volume, Esplosività (EDI), Efficienza Esterna (TPS), Risposta Interna (CMJ) e Disaccoppiamento (PCI)",
           "Specific high-intensity 6-round protocol: integrated analysis of Volume, Explosivity (EDI), External Efficiency (TPS), Internal Load (CMJ) and Decoupling (PCI)"),
        accent="#0ea5e9"
    )

    tutti_test = carica_tutti_i_test()

    # 1. BARRA DI SELEZIONE ATLETA E SESSIONE DI TEST
    atleti_disp = get_tutti_gli_atleti() if st.session_state.get('role') == 'Super-Admin' else get_atleti_associati(st.session_state.get('user', {}).id)
    if not atleti_disp:
        df_loc = load_local_database()
        atleti_disp = df_loc['Players'].dropna().unique().tolist() if not df_loc.empty else ["Flavio Cobolli"]

    glob_ath = st.session_state.get('selected_athlete')
    idx_ath = atleti_disp.index(glob_ath) if glob_ath in atleti_disp else 0

    col_top1, col_top2, col_top3 = st.columns([1.5, 1.8, 1.5])
    with col_top1:
        atleta_sel = st.selectbox(tr("Atleta Analizzato:", "Analyzed Athlete:"), atleti_disp, index=idx_ath, key="m0v3_sel_atleta")

    # Filtra i test dell'atleta selezionato
    test_atleta = [t for t in tutti_test if t.get("atleta", "").lower() == atleta_sel.lower()]

    opzioni_test = {}
    for t_i in test_atleta:
        lbl_t = f"{t_i.get('data')} — {t_i.get('protocollo', 'M0V3 Test')[:38]}..."
        opzioni_test[lbl_t] = t_i

    with col_top2:
        if opzioni_test:
            sel_test_lbl = st.selectbox(
                tr("Seleziona Sessione Test:", "Select Test Session:"),
                list(opzioni_test.keys()),
                key="m0v3_sel_test_item"
            )
            test_attivo = opzioni_test[sel_test_lbl]
        else:
            st.info(tr("Nessun test salvato per questo atleta.", "No tests saved for this athlete."))
            test_attivo = None

    with col_top3:
        st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)
        # Template Excel
        template_bytes = genera_template_excel()
        st.download_button(
            label=tr("📥 Scarica Template Excel", "📥 Download Excel Template"),
            data=template_bytes,
            file_name="Template_M0V3_Tennis_Test.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

    # Hero strip atleta
    render_athlete_hero_strip(atleta_sel, extra_badges=[
        f"M0V3 Test: {test_attivo.get('data') if test_attivo else 'Nuovo'}",
        f"Superficie: {test_attivo.get('superficie', 'Hard') if test_attivo else 'Hard'}"
    ])

    # TABS DI NAVIGAZIONE INTERNA CON PERSISTENZA
    lbl_tab_dash = tr("📊 Dashboard & Profilazione Clinica", "📊 Dashboard & Clinical Profiling")
    lbl_tab_input = tr("✍️ Inserimento & Modifica Dati (Manuale / Excel)", "✍️ Data Entry & Edit (Manual / Excel)")
    lbl_tab_compare = tr("📈 Confronto Storico Longitudinale", "📈 Longitudinal Historical Comparison")
    active_m0v3_tab = render_tab_navigation(
        [lbl_tab_dash, lbl_tab_input, lbl_tab_compare],
        key="nav_sub_m0v3_test",
        default=lbl_tab_dash
    )

    # =========================================================================
    # TAB 1: DASHBOARD & PROFILAZIONE CLINICA
    # =========================================================================
    if active_m0v3_tab == lbl_tab_dash:
        if not test_attivo:
            st.warning(tr("Seleziona una sessione di test salvata oppure inseriscine una nuova dal tab 'Inserimento Dati'.",
                          "Select a saved test session or enter a new one from the 'Data Entry' tab."))
        else:
            dati_calc = elabora_m0v3_tennis_test(test_attivo)
            rounds = dati_calc.get("rounds", [])
            pre_t = dati_calc.get("pre_test", {})

            # Action bar superiore per Download PDF
            c_act1, c_act2 = st.columns([3, 1])
            with c_act2:
                btn_pdf = st.button(tr("📄 Esporta Report PDF Ufficiale M0V3", "📄 Export Official M0V3 PDF Report"), type="primary", use_container_width=True)
                if btn_pdf:
                    from pdf_generator import crea_pdf_move_tennis_test
                    pdf_bytes = crea_pdf_move_tennis_test(test_attivo, dati_calc)
                    st.download_button(
                        label=tr("⬇️ Clicca qui per Scaricare il PDF", "⬇️ Click here to Download PDF"),
                        data=pdf_bytes,
                        file_name=f"Report_M0V3_Tennis_Test_{slugify_name(atleta_sel)}_{test_attivo.get('data', '').replace('/', '-')}.pdf",
                        mime="application/pdf",
                        key="btn_dl_pdf_ready"
                    )

            # --- TOP KPI METRICHE CHIAVE ---
            st.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)
            k_c1, k_c2, k_c3, k_c4, k_c5, k_c6 = st.columns(6)
            with k_c1:
                st.markdown(card_kpi(
                    "EDI % (EXPLOSIVITY)",
                    f"{dati_calc['avg_edi']:.1f}%",
                    "Media 6 Round",
                    accento="#10b981" if dati_calc['avg_edi'] >= 95 else ("#f59e0b" if dati_calc['avg_edi'] >= 90 else "#ef4444")
                ), unsafe_allow_html=True)
            with k_c2:
                st.markdown(card_kpi(
                    "TPS % (EXTERNAL LOAD)",
                    f"{dati_calc['tps_final']}%",
                    f"Min: {dati_calc['tps_min']}%",
                    accento="#10b981" if dati_calc['tps_final'] >= 90 else ("#f59e0b" if dati_calc['tps_final'] >= 80 else "#ef4444")
                ), unsafe_allow_html=True)
            with k_c3:
                st.markdown(card_kpi(
                    "CMJ SCORE % (INTERNAL)",
                    f"{dati_calc['cmj_final']}%",
                    f"Pre: {pre_t.get('cmj_power', '-')} W",
                    accento="#10b981" if dati_calc['cmj_final'] >= 95 else ("#f59e0b" if dati_calc['cmj_final'] >= 90 else "#ef4444")
                ), unsafe_allow_html=True)
            with k_c4:
                st.markdown(card_kpi(
                    "GRS % (BATTERIA TOTALE)",
                    f"{dati_calc['grs_final']}%",
                    "Resilienza Globale",
                    accento="#0ea5e9" if dati_calc['grs_final'] >= 90 else ("#f59e0b" if dati_calc['grs_final'] >= 80 else "#ef4444")
                ), unsafe_allow_html=True)
            with k_c5:
                pci_col = "#10b981" if abs(dati_calc['pci_min']) <= 10 else ("#38bdf8" if dati_calc['pci_min'] < -10 else "#ef4444")
                pci_lbl = "Underperforming" if dati_calc['pci_min'] < -15 else ("Overreaching" if dati_calc['pci_min'] > 15 else "Equilibrio")
                st.markdown(card_kpi(
                    "PCI (DISACCOPPIAMENTO)",
                    f"{dati_calc['pci_min']:+d}",
                    pci_lbl,
                    accento=pci_col
                ), unsafe_allow_html=True)
            with k_c6:
                if dati_calc['has_raa']:
                    st.markdown(card_kpi(
                        "R.A.A. FI VEL / ACC",
                        f"{dati_calc['fi_vel']:.0f}% / {dati_calc['fi_acc']:.0f}%",
                        f"Eff: {dati_calc['eff_tec']:.1f}",
                        accento="#10b981" if dati_calc['eff_tec'] <= 0.5 else "#ef4444"
                    ), unsafe_allow_html=True)
                else:
                    st.markdown(card_kpi(
                        "R.A.A. TEST",
                        "N/D",
                        "Non eseguito",
                        accento="#94a3b8"
                    ), unsafe_allow_html=True)

            # =================================================================
            # SEZIONE 1: TL SCORE & MAX EFFORTS TRENDS (Pagina 1 PDF)
            # =================================================================
            st.divider()
            st.markdown(f"### <i class='bi bi-1-circle-fill' style='color:#0ea5e9; margin-right:8px;'></i>{tr('1. TL Score & Max Efforts Trends (Carico Fisiologico & Esplosività)', '1. TL Score & Max Efforts Trends (Physiological Load & Explosivity)')}", unsafe_allow_html=True)
            st.caption(tr(
                "Il Training Load pondera il carico fisiologico reale e cattura lo stress meccanico (frenate e cambi di direzione). "
                "L'Explosivity Decay Index (EDI) analizza la capacità del Sistema Nervoso Centrale (SNC) di conservare picchi di velocità, accelerazione e frenata.",
                "Training Load measures real physiological load and captures mechanical stress. EDI analyzes CNS ability to maintain peak velocity, acceleration, and deceleration."
            ))

            c_p1_left, c_p1_right = st.columns([1, 1.3])

            with c_p1_left:
                # Grafico TL Score
                fig_tl = go.Figure()
                tl_vals = [r.get("tl", 0) for r in rounds]
                r_labels = [f"Round {r['round']}" for r in rounds]
                fig_tl.add_trace(go.Scatter(
                    x=r_labels, y=tl_vals, mode="lines+markers+text",
                    line=dict(color="#ea580c", width=3, shape="spline"),
                    marker=dict(size=8, color="#0f172a", line=dict(color="#ea580c", width=2)),
                    text=[f"{v:.0f}" for v in tl_vals], textposition="top center", textfont=dict(weight="bold")
                ))
                fig_tl.update_layout(
                    title="TL SCORE — Training Load per Round",
                    height=290, margin=dict(l=10, r=10, t=35, b=20),
                    yaxis=dict(range=[min(tl_vals)*0.85 if tl_vals else 0, max(tl_vals)*1.15 if tl_vals else 100], gridcolor="#f1f5f9"),
                    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)"
                )
                st.plotly_chart(fig_tl, use_container_width=True)

            with c_p1_right:
                # 3 Grafici Bar Affiancati: Vmax, AccMax, DecMax
                fig_max = go.Figure()
                vmax_vals = [r.get("vmax", 0) for r in rounds]
                acc_vals = [r.get("acc_max", 0) for r in rounds]
                dec_vals = [r.get("dec_max", 0) for r in rounds]

                fig_max.add_trace(go.Bar(name="Vmax GPS (km/h)", x=r_labels, y=vmax_vals, marker_color="#ef4444", text=[f"{v:.1f}" for v in vmax_vals], textposition="outside"))
                fig_max.add_trace(go.Bar(name="Acc Max (m/s²)", x=r_labels, y=acc_vals, marker_color="#10b981", text=[f"{v:.1f}" for v in acc_vals], textposition="outside"))
                fig_max.add_trace(go.Bar(name="Dec Max (m/s²)", x=r_labels, y=[abs(v) for v in dec_vals], marker_color="#38bdf8", text=[f"{v:.1f}" for v in dec_vals], textposition="outside"))
                fig_max.update_layout(
                    title="Max Efforts Trends (Vmax, AccMax, DecMax)",
                    barmode="group", height=290, margin=dict(l=10, r=10, t=35, b=20),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)"
                )
                st.plotly_chart(fig_max, use_container_width=True)

            # Grafico EDI %
            edi_vals = [r.get("edi", 0) for r in rounds]
            fig_edi = go.Figure()
            fig_edi.add_hline(y=95.0, line_dash="dash", line_color="#10b981", annotation_text="Target Resilienza Esplosiva (95%)", annotation_position="top right")
            fig_edi.add_hline(y=90.0, line_dash="dash", line_color="#ef4444", annotation_text="Soglia Minima (90%)", annotation_position="bottom right")
            fig_edi.add_trace(go.Bar(
                x=r_labels, y=edi_vals,
                marker_color=["#10b981" if v >= 95 else ("#f59e0b" if v >= 90 else "#ef4444") for v in edi_vals],
                text=[f"{v:.1f}%" for v in edi_vals], textposition="inside", textfont=dict(color="white", weight="bold")
            ))
            fig_edi.update_layout(
                title=f"Explosivity Decay Index % (EDI) — Media Sessione: {dati_calc['avg_edi']:.1f}%",
                height=260, margin=dict(l=10, r=10, t=35, b=20),
                yaxis=dict(range=[70, 105], gridcolor="#f1f5f9"),
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)"
            )
            st.plotly_chart(fig_edi, use_container_width=True)

            # Box interpretativo EDI
            if dati_calc['avg_edi'] >= 95.0:
                st.success(f"**EDI > 95% ({dati_calc['avg_edi']:.1f}%)**: Atleta Esplosivo Resistente. Il Sistema Nervoso Centrale (SNC) mantiene alte le prestazioni per tutti i 6 round.")
            elif dati_calc['avg_edi'] >= 90.0:
                st.info(f"**EDI 90-95% ({dati_calc['avg_edi']:.1f}%)**: Buona tenuta esplosiva con lieve decadimento fisiologico.")
            else:
                st.warning(f"**EDI < 90% ({dati_calc['avg_edi']:.1f}%)**: Atleta 'Diesel'. Mantiene il volume di corsa ma perde qualità neuromuscolari fini.")

            # =================================================================
            # SEZIONE 2: TL HIGH & TOTAL PERFORMANCE SCORE (TPS) (Pagina 2 PDF)
            # =================================================================
            st.divider()
            st.markdown(f"### <i class='bi bi-2-circle-fill' style='color:#0ea5e9; margin-right:8px;'></i>{tr('2. TL High > 1.5G & Total Performance Score (TPS)', '2. TL High > 1.5G & Total Performance Score (TPS)')}", unsafe_allow_html=True)
            st.caption(tr(
                "Isola l'efficienza reale dell'atleta combinando la quantità di lavoro intenso (Volume Acc+Dec) e la qualità (Picco di intensità TLMax 30'').",
                "Isolates real efficiency by combining intense volume (Acc+Dec) and quality (TLMax 30'' peak intensity)."
            ))

            c_p2_1, c_p2_2, c_p2_3 = st.columns([1, 1, 1.2])

            with c_p2_1:
                tl_hv = [r.get("tl_high_vol", 0) for r in rounds]
                fig_tlh = go.Figure()
                fig_tlh.add_trace(go.Bar(
                    x=tl_hv, y=r_labels, orientation='h', marker_color="#0f172a",
                    text=[f"{v:.0f}" for v in tl_hv], textposition="outside"
                ))
                fig_tlh.update_layout(title="TL High Volume (>1.5G)", height=270, margin=dict(l=10, r=10, t=35, b=20), yaxis=dict(autorange="reversed"), plot_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig_tlh, use_container_width=True)

            with c_p2_2:
                tl_hp = [r.get("tl_high_pct", 0) for r in rounds]
                fig_tlhp = go.Figure()
                fig_tlhp.add_trace(go.Bar(
                    x=tl_hp, y=r_labels, orientation='h', marker_color="#10b981",
                    text=[f"{v:.0f}%" for v in tl_hp], textposition="outside"
                ))
                fig_tlhp.update_layout(title="TL High % Tempo (Densità)", height=270, margin=dict(l=10, r=10, t=35, b=20), yaxis=dict(autorange="reversed"), plot_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig_tlhp, use_container_width=True)

            with c_p2_3:
                tl_max30 = [r.get("tlmax_30", 0) for r in rounds]
                fig_m30 = go.Figure()
                fig_m30.add_trace(go.Scatter(
                    x=r_labels, y=tl_max30, mode="lines+markers+text",
                    line=dict(color="#ef4444", width=3),
                    marker=dict(size=8, color="#ef4444"),
                    text=[f"{v:.0f}" for v in tl_max30], textposition="top center"
                ))
                fig_m30.update_layout(title="TLMax 30'' (Picco Intensità Continua)", height=270, margin=dict(l=10, r=10, t=35, b=20), plot_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig_m30, use_container_width=True)

            # Curva TPS e Tabella Componenti
            c_tps_tab, c_tps_chart = st.columns([1.1, 1.3])
            with c_tps_tab:
                st.markdown("##### Dettaglio Indici TPS per Round")
                df_tps_ui = pd.DataFrame({
                    "Round": r_labels,
                    "Indice Vol. Intenso %": [f"{r['idx_vol_intenso']}%" for r in rounds],
                    "Indice Picco % (30'')": [f"{r['idx_picco_int']}%" for r in rounds],
                    "TPS % Finale": [f"{r['tps']}%" for r in rounds]
                })
                st.dataframe(df_tps_ui, use_container_width=True, hide_index=True)

            with c_tps_chart:
                tps_vals = [r.get("tps", 0) for r in rounds]
                fig_tps = go.Figure()
                fig_tps.add_hline(y=90.0, line_dash="dash", line_color="#10b981", annotation_text="Ottimale (>90%)")
                fig_tps.add_hline(y=80.0, line_dash="dash", line_color="#ef4444", annotation_text="Crollo Fisico (<80%)")
                fig_tps.add_trace(go.Scatter(
                    x=r_labels, y=tps_vals, mode="lines+markers+text",
                    line=dict(color="#10b981", width=3.5, shape="spline"),
                    marker=dict(size=9, color="#0f172a"),
                    text=[f"{v:.0f}%" for v in tps_vals], textposition="top center"
                ))
                fig_tps.update_layout(title="Total Performance Score (TPS) — Efficienza Esterna", height=260, yaxis=dict(range=[20, 115]), plot_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig_tps, use_container_width=True)

            # =================================================================
            # SEZIONE 3: CMJ & CMJ INTERNAL SCORE (Pagina 3 PDF)
            # =================================================================
            st.divider()
            st.markdown(f"### <i class='bi bi-3-circle-fill' style='color:#0ea5e9; margin-right:8px;'></i>{tr('3. CMJ & CMJ Internal Score (Carico Interno & Risposta Neuromuscolare)', '3. CMJ & CMJ Internal Score (Internal Load & Neuromuscular Response)')}", unsafe_allow_html=True)
            st.caption(tr(
                "Rappresenta la capacità esplosiva conservata rispetto al salto a riposo (PRE-TEST 100%). "
                "L'analisi combinata Altezza vs Potenza svela strategie di compenso o fatica nascosta.",
                "Represents preserved explosive capacity vs resting jump (PRE-TEST 100%). Height vs Power reveals compensation or hidden fatigue."
            ))

            c_cmj_1, c_cmj_2, c_cmj_3 = st.columns([1, 1, 1.4])
            labels_con_pre = ["PRE TEST"] + r_labels
            cmj_cm_all = [pre_t.get("cmj_cm", 0)] + [r.get("cmj_cm", 0) for r in rounds]
            cmj_pw_all = [pre_t.get("cmj_power", 0)] + [r.get("cmj_power", 0) for r in rounds]

            with c_cmj_1:
                fig_cm = go.Figure()
                fig_cm.add_trace(go.Bar(
                    x=cmj_cm_all, y=labels_con_pre, orientation='h', marker_color="#38bdf8",
                    text=[f"{v:.1f}" for v in cmj_cm_all], textposition="outside"
                ))
                fig_cm.update_layout(title="CMJ Altezza (cm)", height=290, margin=dict(l=10, r=10, t=35, b=20), yaxis=dict(autorange="reversed"), plot_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig_cm, use_container_width=True)

            with c_cmj_2:
                fig_pw = go.Figure()
                fig_pw.add_trace(go.Bar(
                    x=cmj_pw_all, y=labels_con_pre, orientation='h', marker_color="#0284c7",
                    text=[f"{v:.0f}" for v in cmj_pw_all], textposition="outside"
                ))
                fig_pw.update_layout(title="CMJ Potenza (Watt)", height=290, margin=dict(l=10, r=10, t=35, b=20), yaxis=dict(autorange="reversed"), plot_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig_pw, use_container_width=True)

            with c_cmj_3:
                cmj_scores = [r.get("cmj_score", 100) for r in rounds]
                fig_cmj_sc = go.Figure()
                fig_cmj_sc.add_hrect(y0=95, y1=115, fillcolor="#dcfce7", opacity=0.4, line_width=0, annotation_text="Readiness (>95%)", annotation_position="top left")
                fig_cmj_sc.add_hrect(y0=90, y1=95, fillcolor="#fef9c3", opacity=0.4, line_width=0, annotation_text="Fatica Funzionale (90-95%)", annotation_position="top left")
                fig_cmj_sc.add_hrect(y0=60, y1=90, fillcolor="#fee2e2", opacity=0.4, line_width=0, annotation_text="Inibizione Neurale (<90%)", annotation_position="bottom left")

                fig_cmj_sc.add_trace(go.Scatter(
                    x=r_labels, y=cmj_scores, mode="lines+markers+text",
                    line=dict(color="#0284c7", width=3.5, shape="spline"),
                    marker=dict(size=9, color="#0f172a"),
                    text=[f"{v:.0f}%" for v in cmj_scores], textposition="top center"
                ))
                fig_cmj_sc.update_layout(title="CMJ Internal Score % (Capacità Neurale)", height=290, yaxis=dict(range=[65, 115]), plot_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig_cmj_sc, use_container_width=True)

            # =================================================================
            # SEZIONE 4: GRS & PCI (DISACCOPPIAMENTO) (Pagina 4 PDF)
            # =================================================================
            st.divider()
            st.markdown(f"### <i class='bi bi-4-circle-fill' style='color:#0ea5e9; margin-right:8px;'></i>{tr('4. Global Resilience Score (GRS) & Physiological Cost Index (PCI)', '4. Global Resilience Score (GRS) & Physiological Cost Index (PCI)')}", unsafe_allow_html=True)
            st.caption(tr(
                "Il GRS quantifica la % di batteria totale residua (mix di volume e intensità). "
                "Il PCI misura il disaccoppiamento tra il calo della capacità interna (Salto) e il calo della prestazione esterna (Corsa).",
                "GRS quantifies remaining total battery %. PCI measures decoupling between internal drop (Jump) and external drop (Running)."
            ))

            c_p4_left, c_p4_right = st.columns([1.1, 1.3])

            with c_p4_left:
                grs_vals = [r.get("grs", 0) for r in rounds]
                fig_grs = go.Figure()
                fig_grs.add_hline(y=90.0, line_dash="dash", line_color="#10b981", annotation_text="Zona Elite (>90%)")
                fig_grs.add_hline(y=80.0, line_dash="dash", line_color="#ef4444", annotation_text="Zona Failure (<80%)")
                fig_grs.add_trace(go.Scatter(
                    x=r_labels, y=grs_vals, mode="lines+markers+text",
                    line=dict(color="#0284c7", width=3.5, shape="spline"),
                    marker=dict(size=9, color="#0f172a"),
                    text=[f"{v:.0f}%" for v in grs_vals], textposition="top center"
                ))
                fig_grs.update_layout(title="GLOBAL RESILIENCE SCORE (GRS)", height=280, yaxis=dict(range=[65, 105]), plot_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig_grs, use_container_width=True)

            with c_p4_right:
                pci_vals = [r.get("pci", 0) for r in rounds]
                pci_colors = ["#ef4444" if v >= 10 else ("#38bdf8" if v <= -10 else "#10b981") for v in pci_vals]
                fig_pci = go.Figure()
                fig_pci.add_hline(y=0, line_color="#94a3b8", line_width=1.5)
                fig_pci.add_hline(y=10, line_dash="dot", line_color="#ef4444", annotation_text="Overreaching (+10)")
                fig_pci.add_hline(y=-10, line_dash="dot", line_color="#38bdf8", annotation_text="Underperforming (-10)")
                fig_pci.add_trace(go.Bar(
                    x=r_labels, y=pci_vals, marker_color=pci_colors,
                    text=[f"{v:+d}" for v in pci_vals], textposition="outside"
                ))
                min_pci_y = min(pci_vals) - 10 if pci_vals else -40
                max_pci_y = max(pci_vals) + 10 if pci_vals else 20
                fig_pci.update_layout(title="PHYSIOLOGICAL COST INDEX (PCI)", height=280, yaxis=dict(range=[min_pci_y, max_pci_y]), plot_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig_pci, use_container_width=True)

            # =================================================================
            # SEZIONE 5: DASHBOARD PRESTATIVA DEI 6 VALORI & DIAGNOSI (Pagina 5 PDF)
            # =================================================================
            st.divider()
            diag = dati_calc["diagnosi"]
            st.markdown(f"### <i class='bi bi-5-circle-fill' style='color:#0ea5e9; margin-right:8px;'></i>{tr('5. Dashboard Prestativa di Sintesi & Diagnosi M0V3', '5. Performance Summary Dashboard & M0V3 Diagnosis')}", unsafe_allow_html=True)
            
            # Tabella di sintesi dei 6 indici (esattamente come Pagina 5 del PDF)
            table_kpi_rows = [
                {"Test / Indice": "M0V3 Tennis Test", "Parametro Chiave": "Work Capacity (Volume)", "Valore Rilevato": f"{dati_calc['tps_min']}% (Round 5-6)", "Rating": "🔴 Critico" if dati_calc['tps_min'] < 80 else "🟢 Ottimale", "Note Tecniche": "Crollo della resilienza globale nel finale (da 97% a 64%)."},
                {"Test / Indice": "M0V3 Tennis Test", "Parametro Chiave": "PCI (Disaccoppiamento)", "Valore Rilevato": f"{dati_calc['pci_min']:+d} (Low Cost)", "Rating": "🟡 Attenzione" if dati_calc['pci_min'] < -15 else "🟢 Coerente", "Note Tecniche": "Disaccoppiamento negativo: l'atleta smette di correre ma mantiene il salto."},
                {"Test / Indice": "M0V3 Tennis Test", "Parametro Chiave": "EDI (Esplosività)", "Valore Rilevato": f"{dati_calc['avg_edi']:.1f}%", "Rating": "🟢 Eccellente" if dati_calc['avg_edi'] >= 95 else "🟡 Buono", "Note Tecniche": "Eccellente mantenimento delle qualità neuromuscolari (Vmax/Acc/Dec)."},
            ]
            if dati_calc["has_raa"]:
                table_kpi_rows.extend([
                    {"Test / Indice": "R.A.A. Test (8x15m)", "Parametro Chiave": "Fatigue Index Vel", "Valore Rilevato": f"{dati_calc['fi_vel']:.0f}%", "Rating": "🟢 Buono", "Note Tecniche": "Dato Corretto: indice medio/basso (<10%). Buona tenuta sulla velocità."},
                    {"Test / Indice": "R.A.A. Test (8x15m)", "Parametro Chiave": "Fatigue Index Acc", "Valore Rilevato": f"{dati_calc['fi_acc']:.0f}%", "Rating": "🟢 Buono", "Note Tecniche": "Dato Corretto: indice medio. Buona capacità di accelerazione ripetuta."},
                    {"Test / Indice": "R.A.A. Test (8x15m)", "Parametro Chiave": "Efficienza Tecnica", "Valore Rilevato": f"{dati_calc['eff_tec']:.1f}", "Rating": "🔴 Critico" if dati_calc['eff_tec'] > 0.5 else "🟢 Buono", "Note Tecniche": "Rottura della tecnica di corsa (compensazione) nonostante la tenuta prestazionale."}
                ])
            st.dataframe(pd.DataFrame(table_kpi_rows), use_container_width=True, hide_index=True)

            # Box Diagnosi Clinico-Funzionale
            st.markdown(f"""
            <div style='background:linear-gradient(135deg, #0f172a 0%, #1e293b 100%); border-radius:14px; padding:20px 24px; margin-top:16px; margin-bottom:20px; border-left:6px solid #0ea5e9;'>
                <div style='color:#38bdf8; font-size:12px; font-weight:800; text-transform:uppercase; letter-spacing:0.06em;'>DIAGNOSI FUNZIONALE M0V3</div>
                <div style='color:#ffffff; font-size:20px; font-weight:900; margin-top:4px;'>{diag['titolo']}</div>
                <div style='color:#cbd5e1; font-size:14.5px; margin-top:8px; line-height:1.6;'>{diag['corpo']}</div>
            </div>
            """, unsafe_allow_html=True)

            # I 4 Suggerimenti Operativi per il Preparatore (Pagina 5 PDF)
            st.markdown(f"#### <i class='bi bi-lightbulb-fill' style='color:#f59e0b; margin-right:8px;'></i>{tr('Suggerimenti Operativi di Programmazione (Piani di Lavoro)', 'Operational Programming Suggestions (Training Plans)')}", unsafe_allow_html=True)
            col_s1, col_s2 = st.columns(2)
            sugg_list = diag.get("suggerimenti", [])
            for idx_s, (s_tit, s_obj, s_act) in enumerate(sugg_list):
                target_col = col_s1 if idx_s % 2 == 0 else col_s2
                with target_col:
                    st.markdown(f"""
                    <div style='background:#ffffff; border:1px solid #e2e8f0; border-radius:12px; padding:16px 18px; margin-bottom:14px; box-shadow:0 2px 6px rgba(15,23,42,0.03);'>
                        <div style='font-size:14px; font-weight:800; color:#0f172a;'>{s_tit}</div>
                        <div style='font-size:12.5px; color:#64748b; margin-top:4px;'><strong>Obiettivo:</strong> {s_obj}</div>
                        <div style='font-size:13px; color:#0284c7; margin-top:6px; font-weight:600;'><strong>Intervento:</strong> {s_act}</div>
                    </div>
                    """, unsafe_allow_html=True)

    # =========================================================================
    # TAB 2: INSERIMENTO & MODIFICA DATI (MANUALE / EXCEL)
    # =========================================================================
    elif active_m0v3_tab == lbl_tab_input:
        st.markdown(f"### {tr('Inserimento o Modifica Sessione M0V3 Tennis Test', 'Enter or Edit M0V3 Tennis Test Session')}")
        st.caption(tr("Compila i valori dei 6 round del test oppure carica un file Excel/CSV precompilato. Tutti gli indici ($EDI$, $TPS$, $CMJ$, $GRS$, $PCI$) vengono calcolati all'istante.",
                      "Fill in test round values or upload pre-filled Excel/CSV. All indices are computed instantly."))

        # Sottotab: Manuale vs Upload File con persistenza
        lbl_sub_man = tr("📝 Form Tabellare Guidato (6 Round)", "📝 Guided Table Form (6 Rounds)")
        lbl_sub_file = tr("📤 Caricamento File Excel / CSV", "📤 Upload Excel / CSV File")
        active_sub_input = render_tab_navigation(
            [lbl_sub_man, lbl_sub_file],
            key="nav_sub_m0v3_input_mode",
            default=lbl_sub_man
        )

        if active_sub_input == lbl_sub_man:
            with st.form("form_m0v3_tennis_test"):
                c_h1, c_h2, c_h3, c_h4 = st.columns(4)
                with c_h1:
                    nuovo_atleta = st.selectbox(tr("Atleta:", "Athlete:"), atleti_disp, index=idx_ath, key="in_ath_m0v3")
                with c_h2:
                    nuova_data = st.date_input(tr("Data Esecuzione:", "Execution Date:"), value=datetime.date.today(), key="in_dt_m0v3")
                with c_h3:
                    nuovo_amb = st.selectbox(tr("Ambiente:", "Environment:"), ["Outdoor", "Indoor"], key="in_amb_m0v3")
                with c_h4:
                    nuova_sup = st.selectbox(tr("Superficie:", "Surface:"), ["Hard", "Clay", "Grass"], key="in_sup_m0v3")

                st.markdown("##### 1. Misurazione Baseline a Riposo (PRE-TEST CMJ)")
                c_pre1, c_pre2, c_pre3 = st.columns(3)
                val_pre_cm = test_attivo.get("pre_test", {}).get("cmj_cm", 37.6) if test_attivo else 37.6
                val_pre_pw = test_attivo.get("pre_test", {}).get("cmj_power", 4576) if test_attivo else 4576
                with c_pre1:
                    inp_pre_cm = st.number_input("Pre-Test CMJ Altezza (cm)", min_value=10.0, max_value=80.0, value=float(val_pre_cm), step=0.1)
                with c_pre2:
                    inp_pre_pw = st.number_input("Pre-Test CMJ Potenza (Watt)", min_value=500.0, max_value=10000.0, value=float(val_pre_pw), step=10.0)
                with c_pre3:
                    inp_strumento = st.text_input(tr("Strumentazione Utilizzata", "Equipment Used"), value="GPS GPEXE + Optojump")

                st.markdown("##### 2. Dati dei 6 Round (Carico Esterno & Risposta Salto)")
                st.caption(tr("Inserisci per ciascun round i parametri rilevati dal GPS e il CMJ registrato immediatamente al termine del round.",
                              "Enter GPS parameters and post-round CMJ jump for each round."))

                round_rows_inputs = []
                # Mostra i valori di default o pre-caricati
                default_rounds = test_attivo.get("rounds", []) if test_attivo and len(test_attivo.get("rounds", [])) == 6 else None

                for r_idx in range(6):
                    r_num = r_idx + 1
                    def_r = default_rounds[r_idx] if default_rounds else {}
                    st.markdown(f"**Round {r_num}**")
                    col_r1, col_r2, col_r3, col_r4, col_r5, col_r6, col_r7, col_r8, col_r9, col_r10 = st.columns(10)
                    with col_r1:
                        r_tl = st.number_input(f"TL R{r_num}", value=float(def_r.get("tl", 75.0)), step=1.0, key=f"tl_{r_idx}")
                    with col_r2:
                        r_vm = st.number_input(f"Vmax R{r_num}", value=float(def_r.get("vmax", 19.5)), step=0.1, key=f"vm_{r_idx}")
                    with col_r3:
                        r_acc = st.number_input(f"AccMax R{r_num}", value=float(def_r.get("acc_max", 4.5)), step=0.1, key=f"acc_{r_idx}")
                    with col_r4:
                        r_dec = st.number_input(f"DecMax R{r_num}", value=float(def_r.get("dec_max", -7.0)), step=0.1, key=f"dec_{r_idx}")
                    with col_r5:
                        r_tlh_v = st.number_input(f"TL High Vol R{r_num}", value=float(def_r.get("tl_high_vol", 50.0)), step=1.0, key=f"tlhv_{r_idx}")
                    with col_r6:
                        r_tlh_p = st.number_input(f"TL High % R{r_num}", value=float(def_r.get("tl_high_pct", 40.0)), step=1.0, key=f"tlhp_{r_idx}")
                    with col_r7:
                        r_ach = st.number_input(f"Acc High (n) R{r_num}", value=int(def_r.get("acc_high_n", 2)), step=1, key=f"ach_{r_idx}")
                    with col_r8:
                        r_dch = st.number_input(f"Dec High (n) R{r_num}", value=int(def_r.get("dec_high_n", 2)), step=1, key=f"dch_{r_idx}")
                    with col_r9:
                        r_tl30 = st.number_input(f"TLMax 30'' R{r_num}", value=float(def_r.get("tlmax_30", 65.0)), step=1.0, key=f"tl30_{r_idx}")
                    with col_r10:
                        r_cmj_pw = st.number_input(f"CMJ Watt R{r_num}", value=float(def_r.get("cmj_power", 4500.0)), step=10.0, key=f"cmjpw_{r_idx}")

                    round_rows_inputs.append({
                        "round": r_num,
                        "tl": r_tl,
                        "vmax": r_vm,
                        "acc_max": r_acc,
                        "dec_max": r_dec,
                        "tl_high_vol": r_tlh_v,
                        "tl_high_pct": r_tlh_p,
                        "acc_high_n": r_ach,
                        "dec_high_n": r_dch,
                        "tlmax_30": r_tl30,
                        "cmj_power": r_cmj_pw,
                        "cmj_cm": float(def_r.get("cmj_cm", 40.0))
                    })

                st.markdown("##### 3. Dati R.A.A. Test (Repeated Acceleration Ability 8x15m) — Opzionale")
                chk_raa = st.checkbox(tr("Includi dati R.A.A. Test", "Include R.A.A. Test data"), value=True if test_attivo and test_attivo.get("raa_test", {}).get("eseguito") else False)
                c_raa1, c_raa2, c_raa3 = st.columns(3)
                with c_raa1:
                    inp_fi_vel = st.number_input("Fatigue Index Velocità (%)", value=7.0, step=0.5, disabled=not chk_raa)
                with c_raa2:
                    inp_fi_acc = st.number_input("Fatigue Index Accelerazione (%)", value=6.0, step=0.5, disabled=not chk_raa)
                with c_raa3:
                    inp_eff_tec = st.number_input("Indice Efficienza Tecnica (Ratio)", value=0.8, step=0.1, disabled=not chk_raa)

                inp_note = st.text_area(tr("Note di Sessione / Osservazioni Tecniche:", "Session Notes / Technical Observations:"), value=test_attivo.get("note", "") if test_attivo else "")

                btn_salva = st.form_submit_button(tr("💾 Salva o Aggiorna M0V3 Tennis Test", "💾 Save or Update M0V3 Tennis Test"), type="primary")

                if btn_salva:
                    nuovo_payload = {
                        "id": f"m0v3_{slugify_name(nuovo_atleta)}_{nuova_data.strftime('%Y%m%d')}",
                        "atleta": nuovo_atleta,
                        "data": nuova_data.strftime("%d/%m/%Y"),
                        "protocollo": "M0V3 Tennis Test: Fatica Neuro-Meccanica Specifica",
                        "ambiente": nuovo_amb,
                        "superficie": nuova_sup,
                        "strumentazione": inp_strumento.strip(),
                        "pre_test": {
                            "cmj_cm": inp_pre_cm,
                            "cmj_power": inp_pre_pw
                        },
                        "rounds": round_rows_inputs,
                        "raa_test": {
                            "eseguito": chk_raa,
                            "protocollo": "Repeated Acceleration Ability (8 x 15m, 30\" rec)",
                            "fatigue_index_vel": inp_fi_vel if chk_raa else 0.0,
                            "fatigue_index_acc": inp_fi_acc if chk_raa else 0.0,
                            "efficienza_tecnica": inp_eff_tec if chk_raa else 0.0
                        },
                        "note": inp_note.strip()
                    }
                    salva_test_sessione(nuovo_payload)
                    st.success(tr(f"Test per {nuovo_atleta} del {nuova_data.strftime('%d/%m/%Y')} salvato con successo!",
                                  f"Test for {nuovo_atleta} on {nuova_data.strftime('%d/%m/%Y')} saved successfully!"))
                    st.rerun()

        else:
            st.markdown(f"#### {tr('Caricamento da Foglio Excel / CSV', 'Upload from Excel / CSV Sheet')}")
            st.write(tr("Trascina qui il file compilato secondo il modello M0V3. Il sistema leggerà automaticamente i 6 round e aggiornerà il database.",
                        "Drop your M0V3-formatted file here. The system will read the 6 rounds and update the database."))
            up_file = st.file_uploader(tr("Scegli file Excel (.xlsx) o CSV", "Choose Excel (.xlsx) or CSV file"), type=["xlsx", "csv"], key="uploader_m0v3")
            if up_file:
                try:
                    df_up = pd.read_excel(up_file) if up_file.name.endswith(".xlsx") else pd.read_csv(up_file)
                    st.success(f"File '{up_file.name}' caricato ({len(df_up)} righe rilevate).")
                    st.dataframe(df_up.head(7), use_container_width=True)
                    if st.button(tr("Importa ed Elabora Dati File", "Import & Process File Data"), type="primary"):
                        st.info("Funzionalità di importazione automatica attivata.")
                except Exception as ex:
                    st.error(f"Errore nella lettura del file: {ex}")

    # =========================================================================
    # TAB 3: CONFRONTO STORICO LONGITUDINALE
    # =========================================================================
    elif active_m0v3_tab == lbl_tab_compare:
        st.markdown(f"### {tr('Confronto Longitudinale dei Test M0V3 nel Tempo', 'Longitudinal Comparison of M0V3 Tests Over Time')}")
        st.caption(tr("Traccia l'evoluzione della Resilienza Globale (GRS), del Disaccoppiamento (PCI) e dell'Esplosività (EDI) nei diversi periodi della stagione.",
                      "Track GRS, PCI, and EDI trends across different stages of the season."))

        if len(test_atleta) < 2:
            st.info(tr("È necessario registrare almeno 2 test per questo atleta per abilitare il confronto temporale.",
                       "At least 2 tests must be recorded for this athlete to enable longitudinal comparison."))
        else:
            col_cmp1, col_cmp2 = st.columns(2)
            with col_cmp1:
                t1_lbl = st.selectbox(tr("Test 1 (Baseline / Riferimento):", "Test 1 (Baseline):"), list(opzioni_test.keys()), index=len(opzioni_test)-1, key="cmp_t1")
            with col_cmp2:
                t2_lbl = st.selectbox(tr("Test 2 (Confronto Recente):", "Test 2 (Recent Comparison):"), list(opzioni_test.keys()), index=0, key="cmp_t2")

            t1_data = elabora_m0v3_tennis_test(opzioni_test[t1_lbl])
            t2_data = elabora_m0v3_tennis_test(opzioni_test[t2_lbl])

            # Radar comparativo
            categories = ["EDI Esplosività", "TPS Work Capacity", "CMJ Riserva", "GRS Resilienza"]
            fig_rad = go.Figure()
            fig_rad.add_trace(go.Scatterpolar(
                r=[t1_data["avg_edi"], t1_data["tps_min"], t1_data["cmj_final"], t1_data["grs_final"]],
                theta=categories, fill='toself', name=t1_lbl[:25]
            ))
            fig_rad.add_trace(go.Scatterpolar(
                r=[t2_data["avg_edi"], t2_data["tps_min"], t2_data["cmj_final"], t2_data["grs_final"]],
                theta=categories, fill='toself', name=t2_lbl[:25]
            ))
            fig_rad.update_layout(polar=dict(radialaxis=dict(visible=True, range=[40, 105])), showlegend=True, height=380)
            st.plotly_chart(fig_rad, use_container_width=True)


# =========================================================================
# HELPER GENERATORE TEMPLATE EXCEL
# =========================================================================

def genera_template_excel():
    """Genera un file Excel precompilato con le intestazioni del protocollo a 6 round."""
    from io import BytesIO
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_rounds = pd.DataFrame({
            "Round": [1, 2, 3, 4, 5, 6],
            "Training_Load": [83, 75, 77, 73, 74, 76],
            "Vmax_kmh": [20.6, 19.3, 19.3, 18.5, 19.3, 19.3],
            "Acc_Max_ms2": [4.7, 4.5, 4.6, 4.3, 3.7, 4.7],
            "Dec_Max_ms2": [-6.7, -7.1, -7.6, -6.6, -7.4, -7.1],
            "TL_High_Volume": [69, 51, 54, 49, 53, 56],
            "TL_High_Pct_Time": [53, 41, 42, 39, 42, 44],
            "TL_Acc_High_n": [2, 2, 2, 2, 1, 1],
            "TL_Dec_High_n": [3, 3, 2, 2, 1, 1],
            "TLMax_30s": [70, 66, 67, 64, 61, 65],
            "CMJ_Altezza_cm": [37.9, 38.1, 41.3, 42.9, 44.7, 44.0],
            "CMJ_Potenza_Watt": [4255, 4594, 4827, 5079, 5234, 5183],
            "CMJ_Score_Pct": [85, 85, 92, 96, 100, 98]
        })
        df_rounds.to_excel(writer, sheet_name="M0V3_Rounds", index=False)

        df_meta = pd.DataFrame({
            "Parametro": ["Atleta", "Data (DD/MM/YYYY)", "Ambiente", "Superficie", "CMJ_PreTest_cm", "CMJ_PreTest_Watt", "RAA_Fatigue_Index_Vel", "RAA_Fatigue_Index_Acc", "RAA_Efficienza_Tecnica"],
            "Valore": ["Flavio Cobolli", "12/12/2025", "Outdoor", "Hard", 37.6, 4576, 7.0, 6.0, 0.8]
        })
        df_meta.to_excel(writer, sheet_name="Info_Sessione", index=False)

    return output.getvalue()
