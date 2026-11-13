# Copyright 2026 Riccardo Di Maio - M0V3 S.r.l. Tutti i diritti riservati.
# Proprietary Sports Science & Clinical Performance Intelligence Architecture.
import os
import streamlit as st
from config import tr, render_page_header, render_action_bar
from utils import get_catalogo_protocolli
from pdf_generator import crea_pdf_manuale_test, slugify_name

# =========================================================================
# CONFIGURAZIONE STRUTTURA MACRO-AREE E ICONOGRAFIA M0V3
# =========================================================================

AREE_ORDER = [
    "M0V3 & Campo (Velocità, COD, Metabolico)",
    "Pedane di Forza (VALD ForceDecks / Salto & IMTP)",
    "Forza Eccentrica & Ischiocrurali (VALD NordBord)",
    "Dinamometria Isometrica (VALD DynaMo Forza)",
    "Mobilità & Range of Motion (VALD DynaMo ROM)",
    "Antropometria & Custom"
]

AREA_ICONS = {
    "M0V3 & Campo (Velocità, COD, Metabolico)": ("bi-lightning-charge-fill", "#0284c7"),
    "Pedane di Forza (VALD ForceDecks / Salto & IMTP)": ("bi-speedometer2", "#10b981"),
    "Forza Eccentrica & Ischiocrurali (VALD NordBord)": ("bi-shield-check", "#f59e0b"),
    "Dinamometria Isometrica (VALD DynaMo Forza)": ("bi-bullseye", "#8b5cf6"),
    "Mobilità & Range of Motion (VALD DynaMo ROM)": ("bi-compass", "#ec4899"),
    "Antropometria & Custom": ("bi-person-bounding-box", "#64748b")
}


def render_manuale_test(t=None):
    """
    Manuale Scientifico dei Protocolli di Test M0V3 Analytics.
    Interfaccia grafica 100% allineata allo standard editoriale di Manuale Report.
    """
    render_page_header(
        tr("Manuale dei Protocolli di Test Scientifici", "Scientific Testing Protocols Manual"),
        tr(
            "Guida metodologica, standardizzazione esecutiva, benchmark fisiologici e interpretazione di tutti i test integrati in M0V3.",
            "Methodological guide, execution standardization, physiological benchmarks and interpretation for all tests integrated into M0V3."
        ),
        badge=tr("DOCUMENTAZIONE METODOLOGICA & SCIENTIFICA", "METHODOLOGICAL & SCIENTIFIC DOCUMENTATION")
    )

    user_id = st.session_state.get('user_id')
    catalogo = get_catalogo_protocolli(user_id)

    if not catalogo:
        st.warning(tr("Nessun protocollo trovato nel catalogo.", "No protocols found in the catalog."))
        return

    n_tot_protocolli = len(catalogo)
    aree_presenti = sorted(list(set(p.get('macro_area') for p in catalogo if p.get('macro_area'))))
    n_aree = len(aree_presenti)
    n_tot_metriche = sum(len(p.get('schema_metriche', [])) for p in catalogo)

    # --- BANNER STATISTICO SINTETICO M0V3 (Identico a Manuale Report) ---
    st.html(
        f"""<div style="background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); border-radius: 12px; padding: 18px 24px; margin-bottom: 22px; box-shadow: 0 4px 14px rgba(0,0,0,0.12); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 16px; font-family: 'Inter', sans-serif;">
            <div>
                <div style="color: #38bdf8; font-size: 11.5px; font-weight: 800; letter-spacing: 1.2px; text-transform: uppercase;">
                    <i class="bi bi-journal-bookmark-fill" style="margin-right:8px;"></i>{tr('M0V3 ANALYTICS — ENCICLOPEDIA DEI PROTOCOLLI', 'M0V3 ANALYTICS — PROTOCOLS ENCYCLOPEDIA')}
                </div>
                <div style="color: #ffffff; font-size: 21px; font-weight: 900; margin-top: 2px;">
                    {tr('Catalogo Completo dei Test Fisici & Neuromuscolari', 'Complete Catalog of Physical & Neuromuscular Tests')}
                </div>
                <div style="color: #94a3b8; font-size: 12.5px; margin-top: 3px;">
                    {tr('Standardizzazione esecutiva, algoritmi di asimmetria e linee guida interpretative validate.', 'Standardized execution, asymmetry algorithms, and validated interpretation guidelines.')}
                </div>
            </div>
            <div style="display: flex; gap: 10px; flex-wrap: wrap;">
                <span style="background: rgba(56, 189, 248, 0.12); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.35); font-size: 11px; font-weight: 800; padding: 6px 14px; border-radius: 20px; letter-spacing: 0.05em;">
                    <i class="bi bi-clipboard2-pulse" style="margin-right:5px;"></i>{n_tot_protocolli} {tr('PROTOCOLLI', 'PROTOCOLS')}
                </span>
                <span style="background: rgba(16, 185, 129, 0.12); color: #10b981; border: 1px solid rgba(16, 185, 129, 0.35); font-size: 11px; font-weight: 800; padding: 6px 14px; border-radius: 20px; letter-spacing: 0.05em;">
                    <i class="bi bi-diagram-3" style="margin-right:5px;"></i>{n_aree} {tr('MACRO-AREE', 'MACRO-AREAS')}
                </span>
                <span style="background: rgba(245, 158, 11, 0.12); color: #f59e0b; border: 1px solid rgba(245, 158, 11, 0.35); font-size: 11px; font-weight: 800; padding: 6px 14px; border-radius: 20px; letter-spacing: 0.05em;">
                    <i class="bi bi-rulers" style="margin-right:5px;"></i>{n_tot_metriche} {tr('METRICHE', 'METRICS')}
                </span>
            </div>
        </div>"""
    )

    # --- BARRA DI RICERCA & FILTRI DINAMICI ---
    c_srch, c_fil = st.columns([1.6, 2.4])
    with c_srch:
        query_search = st.text_input(
            tr("Cerca per nome test, metrica, strumento o red flag:", "Search by test name, metric, tool or red flag:"),
            placeholder=tr("Es. Tennis Test, CMJ, NordBord, Spalla, Asimmetria, ROM...", "E.g. Tennis Test, CMJ, NordBord, Shoulder, Asymmetry, ROM..."),
            key="search_manuale_test_query"
        ).strip().lower()

    with c_fil:
        opzioni_aree = [tr("Tutte le Macro-Aree", "All Macro-Areas")] + [a for a in AREE_ORDER if a in aree_presenti]
        area_sel = st.selectbox(
            tr("Filtra per Macro-Area Strumentale:", "Filter by Instrumental Macro-Area:"),
            opzioni_aree,
            index=0,
            key="filter_manuale_test_area"
        )

    # Filtraggio dinamico dei protocolli
    protocolli_filtrati = []
    for p in catalogo:
        macro = p.get('macro_area', '')
        if area_sel != tr("Tutte le Macro-Aree", "All Macro-Areas") and macro != area_sel:
            continue

        if query_search:
            corpus = " ".join([
                str(p.get('nome_protocollo', '')).lower(),
                str(p.get('codice_univoco', '')).lower(),
                str(p.get('macro_area', '')).lower(),
                str(p.get('categoria', '')).lower(),
                str(p.get('manuale_obiettivi', '')).lower(),
                str(p.get('manuale_esecuzione', '')).lower(),
                str(p.get('manuale_interpretazione', '')).lower(),
                " ".join([f"{m.get('label', '')} {m.get('key', '')}" for m in p.get('schema_metriche', [])]).lower()
            ])
            if query_search not in corpus:
                continue

        protocolli_filtrati.append(p)

    # Feedback conteggio
    n_trovati = len(protocolli_filtrati)
    filtro_str = f" (filtro: '{query_search}')" if query_search else ""
    st.markdown(
        f"<div style='font-size:12px; font-weight:700; color:#64748b; margin-top:4px; margin-bottom:12px;'>"
        f"{tr('Visualizzazione di', 'Showing')} <b style='color:#0284c7;'>{n_trovati}</b> {tr('protocolli di test su', 'testing protocols of')} {n_tot_protocolli}{filtro_str}"
        f"</div>",
        unsafe_allow_html=True
    )

    if not protocolli_filtrati:
        st.info(tr("Nessun protocollo di test trovato corrispondente ai criteri di ricerca.", "No testing protocol found matching the search criteria."))
        return

    # Action bar con pulsante PDF
    opzioni_pdf = {"manuale": tr("Manuale Protocolli (PDF)", "Protocols Manual (PDF)")}
    slug_area = slugify_name(area_sel)
    render_action_bar(
        meta_items=[
            (tr("Macro-Area", "Macro-Area"), area_sel),
            (tr("Protocolli Mappati", "Mapped Protocols"), f"{n_trovati} {tr('di', 'of')} {n_tot_protocolli}"),
            (tr("Filtro Attivo", "Active Filter"), query_search if query_search else tr("Nessuno", "None")),
        ],
        pdf_options=opzioni_pdf,
        pdf_key=f"pdf_man_test_{slug_area}",
        generate_fn=lambda _: crea_pdf_manuale_test(protocolli_filtrati, area_filtro=area_sel),
        filename_fn=lambda _: f"M0V3_Manuale_Test_{slug_area}.pdf"
    )

    # Raggruppamento per Macro-Area
    protocolli_per_area = {}
    for p in protocolli_filtrati:
        ar = p.get('macro_area', 'Altro')
        if ar not in protocolli_per_area:
            protocolli_per_area[ar] = []
        protocolli_per_area[ar].append(p)

    # Rendering per Area
    for ar in AREE_ORDER:
        if ar not in protocolli_per_area:
            continue
        lista_p = protocolli_per_area[ar]
        ico_ar, col_ar = AREA_ICONS.get(ar, ("bi-folder", "#0284c7"))

        # Header Sezione Area (Stile identico a Manuale Report)
        st.html(
            f"""<div style="background:#ffffff; border:1px solid #cbd5e1; border-left:6px solid {col_ar}; border-radius:10px; padding:12px 18px; margin-top:24px; margin-bottom:14px; display:flex; justify-content:space-between; align-items:center; box-shadow:0 2px 6px rgba(15,23,42,0.03); font-family:'Inter',sans-serif;">
                <div style="display:flex; align-items:center; gap:10px;">
                    <span style="font-size:18px; color:{col_ar};"><i class="bi {ico_ar}"></i></span>
                    <span style="font-size:15px; font-weight:900; color:#0f172a; text-transform:uppercase; letter-spacing:0.06em;">{ar.upper()}</span>
                </div>
                <span style="background:#f1f5f9; color:#475569; font-size:11px; font-weight:800; padding:4px 12px; border-radius:999px; border:1px solid #e2e8f0;">
                    {len(lista_p)} {tr('Protocolli', 'Protocols')}
                </span>
            </div>"""
        )

        # Rendering Card per ciascun protocollo
        for idx, proto in enumerate(lista_p):
            nome_display = proto.get('nome_protocollo', 'Senza nome')
            nome_tecnico = proto.get('codice_univoco', '')
            categoria = proto.get('categoria', '')
            is_custom = bool(proto.get('creatore_id'))
            metriche = proto.get('schema_metriche', [])
            obiettivi = proto.get('manuale_obiettivi') or tr("Protocollo standardizzato M0V3 per la misurazione prestativa e funzionale.", "Standardized M0V3 protocol for functional and performance assessment.")
            esecuzione = proto.get('manuale_esecuzione') or tr("Esecuzione guidata secondo linee guida operative M0V3.", "Guided execution according to M0V3 operational guidelines.")
            interpretazione = proto.get('manuale_interpretazione') or tr("Valutare il valore rispetto al Personal Best e ai benchmark del livello agonistico dell'atleta.", "Assess the value against Personal Best and competitive benchmarks.")
            titolo_interp = tr("GUIDA ALL'INTERPRETAZIONE, BENCHMARK & RED FLAGS", "INTERPRETATION GUIDE, BENCHMARKS & RED FLAGS")

            # Pillola categoria / badge di sistema
            badge_custom = f"<span style='background:rgba(245,158,11,0.1); color:#d97706; border:1px solid rgba(245,158,11,0.3); font-size:10px; font-weight:800; padding:3px 8px; border-radius:12px; margin-left:6px;'>CUSTOM COACH</span>" if is_custom else f"<span style='background:rgba(16,185,129,0.1); color:#059669; border:1px solid rgba(16,185,129,0.3); font-size:10px; font-weight:800; padding:3px 8px; border-radius:12px; margin-left:6px;'>OFFICIAL M0V3</span>"

            # Pillole per metriche tracciate (Stile Azioni Consentite)
            pill_list = []
            for m in metriche:
                star_col = str(m.get('color', col_ar))
                ico_m = f"<i class='bi bi-star-fill' style='color:{star_col}; font-size:10px;'></i>" if m.get('is_primary_kpi') else "<i class='bi bi-dot' style='color:#94a3b8; font-size:14px;'></i>"
                lbl_m = m.get('label', m.get('key'))
                un_m = m.get('unit', '-')
                lat_m = m.get('laterality', 'BILATERAL')
                pill_list.append(
                    f"<span style='background:#f8fafc; color:#334155; border:1px solid #cbd5e1; font-size:11px; font-weight:700; padding:4px 10px; border-radius:6px; display:inline-flex; align-items:center; gap:6px; margin:3px 4px 3px 0;'>"
                    f"{ico_m} <b>{lbl_m}</b> "
                    f"<span style='color:#64748b; font-size:10px;'>({un_m})</span> "
                    f"<span style='font-size:9.5px; background:rgba(2,132,199,0.08); color:#0369a1; padding:1px 5px; border-radius:4px;'>{lat_m}</span>"
                    f"</span>"
                )
            metriche_pills_html = "".join(pill_list)

            card_html = f"""<div style="background:#ffffff; border:1.5px solid #e2e8f0; border-radius:12px; padding:18px 22px; margin-bottom:16px; box-shadow:0 3px 10px rgba(15,23,42,0.03); font-family:'Inter',sans-serif; transition:all 0.2s ease;">
                <!-- HEADER CARD -->
                <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:14px; border-bottom:1px solid #f1f5f9; padding-bottom:10px; flex-wrap:wrap; gap:8px;">
                    <div>
                        <div style="font-size:16px; font-weight:900; color:#0f172a; letter-spacing:0.02em;">
                            <span style="color:{col_ar}; margin-right:6px;"># {idx+1}</span> {nome_display}
                            {badge_custom}
                        </div>
                        <div style="font-size:11.5px; font-weight:700; color:#64748b; margin-top:3px;">
                            <i class="bi bi-tag" style="margin-right:4px;"></i>{tr('Codice Univoco / ID Catalogo:', 'Unique Code / Catalog ID:')} <span style="color:#0284c7; font-family:monospace; font-size:12px;">{nome_tecnico}</span>
                        </div>
                    </div>
                    <span style="background:rgba(2,132,199,0.08); color:#0369a1; border:1px solid rgba(2,132,199,0.25); font-size:10px; font-weight:800; padding:4px 10px; border-radius:20px; text-transform:uppercase; letter-spacing:0.05em;">
                        {categoria}
                    </span>
                </div>

                <!-- GRIGLIA CONTENUTI -->
                <div style="display:grid; grid-template-columns: 1fr; gap:12px;">
                    <!-- OBIETTIVO SCIENTIFICO -->
                    <div style="background:#f8fafc; border-left:4px solid #0284c7; border-radius:6px; padding:10px 14px;">
                        <div style="font-size:11px; font-weight:900; color:#0369a1; text-transform:uppercase; letter-spacing:0.06em; margin-bottom:4px;">
                            <i class="bi bi-search" style="margin-right:6px;"></i>{tr('OBIETTIVO FISIOLOGICO & BIOMECCANICO', 'PHYSIOLOGICAL & BIOMECHANICAL OBJECTIVE')}
                        </div>
                        <div style="font-size:13px; color:#1e293b; line-height:1.55; text-align:justify;">
                            {obiettivi}
                        </div>
                    </div>

                    <!-- PROTOCOLLO ESECUZIONE -->
                    <div style="background:#f0fdf4; border-left:4px solid #10b981; border-radius:6px; padding:10px 14px;">
                        <div style="font-size:11px; font-weight:900; color:#15803d; text-transform:uppercase; letter-spacing:0.06em; margin-bottom:4px;">
                            <i class="bi bi-stopwatch" style="margin-right:6px;"></i>{tr('PROTOCOLLO OPERATIVO DI ESECUZIONE', 'OPERATIONAL EXECUTION PROTOCOL')}
                        </div>
                        <div style="font-size:13px; color:#1e293b; line-height:1.55; text-align:justify;">
                            {esecuzione}
                        </div>
                    </div>

                    <!-- INTERPRETAZIONE & BENCHMARK -->
                    <div style="background:#fffbeb; border-left:4px solid #f59e0b; border-radius:6px; padding:10px 14px;">
                        <div style="font-size:11px; font-weight:900; color:#b45309; text-transform:uppercase; letter-spacing:0.06em; margin-bottom:4px;">
                            <i class="bi bi-bar-chart-line-fill" style="margin-right:6px;"></i>{titolo_interp}
                        </div>
                        <div style="font-size:13px; color:#1e293b; line-height:1.55; text-align:justify;">
                            {interpretazione}
                        </div>
                    </div>

                    <!-- METRICHE TRACCIATE -->
                    <div style="background:#faf5ff; border-left:4px solid #8b5cf6; border-radius:6px; padding:10px 14px;">
                        <div style="font-size:11px; font-weight:900; color:#6b21a8; text-transform:uppercase; letter-spacing:0.06em; margin-bottom:6px;">
                            <i class="bi bi-sliders" style="margin-right:6px;"></i>{tr('VARIABILI & METRICHE TRACCIATE DALLO SCHEMA', 'VARIABLES & METRICS TRACKED BY SCHEMA')} ({len(metriche)})
                        </div>
                        <div style="display:flex; flex-wrap:wrap; gap:4px;">
                            {metriche_pills_html}
                        </div>
                    </div>
                </div>

                <!-- FOOTER SCIENTIFICO -->
                <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:8px 12px; margin-top:10px; font-size:11px; color:#64748b;">
                    <i class="bi bi-cpu" style="margin-right:5px; color:#0284c7;"></i><b>M0V3 Algorithmic Core:</b> {tr('Elaborazione computazionale proprietaria su standard ISO/IMU, bio-indicatori di asimmetria e algoritmi di readiness neuromuscolare.', 'Proprietary computational processing based on ISO/IMU standards, asymmetry bio-indicators and neuromuscular readiness algorithms.')}
                </div>
            </div>"""

            st.html(card_html)
