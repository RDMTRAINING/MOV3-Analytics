# Copyright 2026 Riccardo Di Maio - M0V3 S.r.l. Tutti i diritti riservati.
# Proprietary Sports Science & Clinical Performance Intelligence Architecture.
"""
M0V3 Analytics - Catalogo Ufficiale Protocolli Seed
Definizione completa di oltre 100 protocolli scientifici suddivisi in 5 macro-aree.
"""

def get_seed_protocols():
    protocols = []

    # =========================================================================
    # GRUPPO 1: M0V3 & CAMPO (Velocità, COD, Metabolico, Resilienza)
    # =========================================================================
    macro_campo = "M0V3 & Campo (Velocità, COD, Metabolico)"

    # 1. M0V3 TENNIS TEST (Flagship)
    protocols.append({
        "codice_univoco": "m0v3_tennis_test",
        "nome_protocollo": "M0V3 Tennis Test",
        "macro_area": macro_campo,
        "categoria": "Specifici Campo & Resilienza",
        "manuale_obiettivi": (
            "Protocollo integrato proprietario M0V3 da campo per valutare la resilienza specifica del tennista, "
            "incrociando il decadimento della prestazione cinematica/metabolica esterna (GPS/IMU) "
            "con l'affaticamento neuromuscolare acuto (CMJ pre/post)."
        ),
        "manuale_esecuzione": (
            "Test intermittente multi-round ad alta intensità sul campo da tennis con rilevazione continua GPS/IMU "
            "e test di salto CMJ a riposo e nelle fasi di recupero/fine test. "
            "Nota: in ambiente Indoor, i parametri legati alla Vmax satellitare (Explosivity Decay Index %) vengono "
            "omessi, affidandosi ai soli sensori inerziali IMU e al CMJ."
        ),
        "manuale_interpretazione": (
            "Interpretazione dei 5 Indici Chiave M0V3:\n\n"
            "• Global Resilience Score (GRS): Integrità sistemica e 'batteria residua'. Fonde in un unico valore (0-100%) "
            "la prestazione di corsa (TPS/Decay) e la risposta interna del salto (CMJ Score). Valori >85% = eccellente resilienza.\n"
            "• Total Performance Score (TPS): Efficienza esterna globale; media tra il mantenimento del volume di azioni "
            "intense (TL High, TL Acc High, TL Dec High) e del picco di intensità (TLmax 30\") rispetto al primo round.\n"
            "• Explosivity Decay Index % (No Indoor): Media delle % di mantenimento dei tre picchi massimali "
            "(Vmax, AccMax, DecMax) rispetto al round iniziale.\n"
            "• CMJ Internal Score: Stato neuromuscolare; % di capacità esplosiva (Jump Height o Peak Power) conservata "
            "nel recupero rispetto al salto basale a riposo.\n"
            "• Physiological Cost Index (PCI): Costo neuro-meccanico; differenza tra il calo del salto e il calo della corsa. "
            "Evidenzia il prezzo reale pagato dal sistema nervoso centrale per mantenere la performance meccanica esterna."
        ),
        "schema_metriche": [
            # 5 Indici Sintetici
            {"key": "grs", "label": "Global Resilience Score (GRS)", "unit": "%", "direction": "HIGHER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": True, "color": "#10b981"},
            {"key": "tps", "label": "Total Performance Score (TPS)", "unit": "%", "direction": "HIGHER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#0ea5e9"},
            {"key": "explosivity_decay_pct", "label": "Explosivity Decay Index % (No Indoor)", "unit": "%", "direction": "HIGHER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#ef4444"},
            {"key": "cmj_internal_score", "label": "CMJ Internal Score", "unit": "%", "direction": "HIGHER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#f59e0b"},
            {"key": "pci", "label": "Physiological Cost Index (PCI)", "unit": "Indice", "direction": "LOWER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#a855f7"},
            # Sotto-metriche grezze opzionali
            {"key": "vmax_picco", "label": "Vmax Picco Test (No Indoor)", "unit": "km/h", "direction": "HIGHER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#38bdf8"},
            {"key": "accmax_picco", "label": "AccMax Picco Test", "unit": "m/s²", "direction": "HIGHER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#38bdf8"},
            {"key": "decmax_picco", "label": "DecMax Picco Test", "unit": "m/s²", "direction": "HIGHER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#38bdf8"},
            {"key": "tl_high", "label": "Training Load High", "unit": "au", "direction": "HIGHER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#38bdf8"},
            {"key": "tl_max_30s", "label": "Training Load Max 30\"", "unit": "au", "direction": "HIGHER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#38bdf8"},
            {"key": "tl_acc_high", "label": "TL Acc High", "unit": "au", "direction": "HIGHER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#38bdf8"},
            {"key": "tl_dec_high", "label": "TL Dec High", "unit": "au", "direction": "HIGHER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#38bdf8"},
            {"key": "cmj_height_post", "label": "CMJ Height (Basale / Post)", "unit": "cm", "direction": "HIGHER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#38bdf8"},
            {"key": "cmj_peak_power_post", "label": "CMJ Peak Power (Basale / Post)", "unit": "W", "direction": "HIGHER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#38bdf8"}
        ]
    })

    # 2. Peso & Composizione Corporea
    protocols.append({
        "codice_univoco": "antropometria_comp_corporea",
        "nome_protocollo": "Peso & Composizione Corporea",
        "macro_area": "Antropometria & Custom",
        "categoria": "Antropometria & Composizione Corporea",
        "manuale_obiettivi": "Monitoraggio dello stato nutrizionale, massa magra (FFM), massa grassa (FM) e idratazione del tennista.",
        "manuale_esecuzione": "Rilevazione al mattino a digiuno tramite bilancia medicale, plicometria o bioimpedenziometria (BIA).",
        "manuale_interpretazione": "Target FFM% per tennisti maschi agonisti: 85-90% (FM 10-15%). Per femmine agoniste: FFM 80-86% (FM 14-20%).",
        "schema_metriche": [
            {"key": "peso", "label": "Peso Corporeo", "unit": "kg", "direction": "NEUTRAL", "laterality": "BILATERAL", "is_primary_kpi": True, "color": "#0ea5e9"},
            {"key": "ffm_pct", "label": "Massa Magra (FFM %)", "unit": "%", "direction": "HIGHER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#10b981"},
            {"key": "ffm_kg", "label": "Massa Magra Assoluta (FFM)", "unit": "kg", "direction": "HIGHER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#10b981"},
            {"key": "fm_pct", "label": "Massa Grassa (FM %)", "unit": "%", "direction": "LOWER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#ef4444"},
            {"key": "sommatoria_pliche", "label": "Sommatoria Pliche", "unit": "mm", "direction": "LOWER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#f59e0b"}
        ]
    })

    # 3. Test di Cooper (12 min)
    protocols.append({
        "codice_univoco": "cooper_12min",
        "nome_protocollo": "Test di Cooper (12 min)",
        "macro_area": macro_campo,
        "categoria": "Capacità & Potenza Metabolica (Endurance & RSA)",
        "manuale_obiettivi": "Valutazione della resistenza aerobica generale e stima del massimo consumo di ossigeno (VO2max).",
        "manuale_esecuzione": "Corsa continua massimale di 12 minuti su pista o campo. Misurare la distanza totale percorsa.",
        "manuale_interpretazione": "Formula VO2max: (Distanza - 504.9) / 44.73. Benchmark agonista >3000m (VO2max >55 ml/kg/min).",
        "schema_metriche": [
            {"key": "distanza", "label": "Distanza Totale", "unit": "m", "direction": "HIGHER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": True, "color": "#0ea5e9"},
            {"key": "vo2max", "label": "VO2max Stimato", "unit": "ml/kg/min", "direction": "HIGHER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#10b981"},
            {"key": "velocita_media", "label": "Velocità Media", "unit": "km/h", "direction": "HIGHER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#38bdf8"},
            {"key": "fc_picco", "label": "FC Picco", "unit": "bpm", "direction": "NEUTRAL", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#ef4444"}
        ]
    })

    # 4. Bronco Test (1.2 km Shuttle)
    protocols.append({
        "codice_univoco": "bronco_test",
        "nome_protocollo": "Bronco Test (1.2 km Shuttle)",
        "macro_area": macro_campo,
        "categoria": "Capacità & Potenza Metabolica (Endurance & RSA)",
        "manuale_obiettivi": "Valutazione della capacità di lavoro aerobico-anaerobico con frequenti cambi di direzione di 180°.",
        "manuale_esecuzione": "Navetta continua 20m, 40m, 60m per 5 serie senza pause (totale 1200m). Cronometrare il tempo totale.",
        "manuale_interpretazione": "Benchmark élite maschile: <4'45\" (285s). Livello alto: <5'00\" (300s). Livello femminile: <5'15\".",
        "schema_metriche": [
            {"key": "tempo_totale", "label": "Tempo Totale", "unit": "s", "direction": "LOWER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": True, "color": "#0ea5e9"},
            {"key": "velocita_media", "label": "Velocità Media", "unit": "m/s", "direction": "HIGHER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#10b981"},
            {"key": "fc_picco", "label": "FC Picco", "unit": "bpm", "direction": "NEUTRAL", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#ef4444"},
            {"key": "rpe_finale", "label": "RPE Finale (0-10)", "unit": "Indice", "direction": "LOWER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#a855f7"}
        ]
    })

    # 5. Yo-Yo Intermittent Recovery Level 1 (IR1)
    protocols.append({
        "codice_univoco": "yoyo_ir1",
        "nome_protocollo": "Yo-Yo Intermittent Recovery 1 (IR1)",
        "macro_area": macro_campo,
        "categoria": "Capacità & Potenza Metabolica (Endurance & RSA)",
        "manuale_obiettivi": "Valutazione della capacità di recupero intermittente ad alta intensità e stima VO2max.",
        "manuale_esecuzione": "Navette di 2x20m a velocità crescente scandita da segnali acustici con 10s di recupero attivo tra le ripetizioni.",
        "manuale_interpretazione": "VO2max = (Distanza * 0.0084) + 36.4. Benchmark tennista agonista: >1800m (Livello 18.1+).",
        "schema_metriche": [
            {"key": "distanza", "label": "Distanza Totale", "unit": "m", "direction": "HIGHER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": True, "color": "#0ea5e9"},
            {"key": "livello", "label": "Livello Raggiunto", "unit": "Livello", "direction": "HIGHER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#38bdf8"},
            {"key": "vo2max", "label": "VO2max Stimato", "unit": "ml/kg/min", "direction": "HIGHER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#10b981"},
            {"key": "fc_picco", "label": "FC Picco", "unit": "bpm", "direction": "NEUTRAL", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#ef4444"}
        ]
    })

    # 6. Yo-Yo Intermittent Recovery Level 2 (IR2)
    protocols.append({
        "codice_univoco": "yoyo_ir2",
        "nome_protocollo": "Yo-Yo Intermittent Recovery 2 (IR2)",
        "macro_area": macro_campo,
        "categoria": "Capacità & Potenza Metabolica (Endurance & RSA)",
        "manuale_obiettivi": "Valutazione della capacità anaerobica lattacida e tolleranza all'acidosi muscolare.",
        "manuale_esecuzione": "Navette di 2x20m con partenza a velocità elevata (13.0 km/h) con 10s di recupero attivo.",
        "manuale_interpretazione": "Benchmark élite: >800m (Livello 20+). Indicatore critico di tolleranza ai punti prolungati.",
        "schema_metriche": [
            {"key": "distanza", "label": "Distanza Totale", "unit": "m", "direction": "HIGHER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": True, "color": "#0ea5e9"},
            {"key": "livello", "label": "Livello Raggiunto", "unit": "Livello", "direction": "HIGHER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#38bdf8"},
            {"key": "fc_picco", "label": "FC Picco", "unit": "bpm", "direction": "NEUTRAL", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#ef4444"},
            {"key": "lattato_picco", "label": "Lattato Picco", "unit": "mmol/L", "direction": "NEUTRAL", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#f59e0b"}
        ]
    })

    # 7. Test di Léger (Beep Test)
    protocols.append({
        "codice_univoco": "leger_beep_test",
        "nome_protocollo": "Test di Léger (Beep Test / VAM)",
        "macro_area": macro_campo,
        "categoria": "Capacità & Potenza Metabolica (Endurance & RSA)",
        "manuale_obiettivi": "Determinazione della Velocità Massima Aerobica (VAM) e del VO2max continuo.",
        "manuale_esecuzione": "Navetta continua sui 20 metri con incrementi di velocità di 0.5 km/h ogni minuto fino all'esaurimento.",
        "manuale_interpretazione": "La VAM raggiunta nell'ultimo palier è il riferimento per i carichi di corsa intermittente.",
        "schema_metriche": [
            {"key": "vam", "label": "VAM - Velocità Massima Aerobica", "unit": "km/h", "direction": "HIGHER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": True, "color": "#0ea5e9"},
            {"key": "livello", "label": "Livello / Palier", "unit": "Livello", "direction": "HIGHER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#38bdf8"},
            {"key": "distanza", "label": "Distanza Totale", "unit": "m", "direction": "HIGHER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#10b981"},
            {"key": "vo2max", "label": "VO2max Stimato", "unit": "ml/kg/min", "direction": "HIGHER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#10b981"}
        ]
    })

    # 8. RSA 8 x 30m
    protocols.append({
        "codice_univoco": "rsa_8x30m",
        "nome_protocollo": "Repeat Sprint Ability (RSA) 8 x 30m",
        "macro_area": macro_campo,
        "categoria": "Capacità & Potenza Metabolica (Endurance & RSA)",
        "manuale_obiettivi": "Valutazione dell'abilità di ripetere sprint lineari con decadimento minimo.",
        "manuale_esecuzione": "8 sprint lineari massimali da 30m con 25s di recupero attivo tra le ripetizioni.",
        "manuale_interpretazione": "Indice di Fatica %: target <5% calo prestativo. Valori >7% indicano deficit di ripristino della fosfocreatina.",
        "schema_metriche": [
            {"key": "tempo_medio", "label": "Tempo Medio", "unit": "s", "direction": "LOWER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": True, "color": "#0ea5e9"},
            {"key": "miglior_sprint", "label": "Miglior Sprint (Best)", "unit": "s", "direction": "LOWER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#10b981"},
            {"key": "tempo_totale", "label": "Tempo Totale", "unit": "s", "direction": "LOWER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#38bdf8"},
            {"key": "decremento_pct", "label": "Decremento / Fatica %", "unit": "%", "direction": "LOWER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#ef4444"},
            {"key": "peggior_sprint", "label": "Peggior Sprint", "unit": "s", "direction": "LOWER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#f59e0b"}
        ]
    })

    # 9. RSA 8 x 15m
    protocols.append({
        "codice_univoco": "rsa_8x15m",
        "nome_protocollo": "Repeat Sprint Ability (RSA) 8 x 15m",
        "macro_area": macro_campo,
        "categoria": "Capacità & Potenza Metabolica (Endurance & RSA)",
        "manuale_obiettivi": "Resilienza all'accelerazione specifica del tennis (distanze brevi di campo).",
        "manuale_esecuzione": "8 sprint da 15m con 20s di recupero attivo. Rilevazione fotocellule o cronometraggio laser.",
        "manuale_interpretazione": "Target fatica <4.5%. Misura l'esplosività ripetuta specifica di scambio lungo.",
        "schema_metriche": [
            {"key": "tempo_medio", "label": "Tempo Medio", "unit": "s", "direction": "LOWER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": True, "color": "#0ea5e9"},
            {"key": "miglior_sprint", "label": "Miglior Sprint (Best)", "unit": "s", "direction": "LOWER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#10b981"},
            {"key": "tempo_totale", "label": "Tempo Totale", "unit": "s", "direction": "LOWER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#38bdf8"},
            {"key": "decremento_pct", "label": "Decremento / Fatica %", "unit": "%", "direction": "LOWER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#ef4444"}
        ]
    })

    # 10. 5-0-5 Agility Test
    protocols.append({
        "codice_univoco": "agility_505",
        "nome_protocollo": "5-0-5 Agility Test",
        "macro_area": macro_campo,
        "categoria": "Agilità & Cambi di Direzione (COD)",
        "manuale_obiettivi": "Capacità di frenata, rotazione di 180° e ri-accelerazione su arto destro vs sinistro.",
        "manuale_esecuzione": "10m di accelerazione, ingresso nella zona fotocellule (5m), tocco linea dei 15m, perno di 180° e ritorno per 5m.",
        "manuale_interpretazione": "COD Deficit = Tempo 5-0-5 - Tempo Sprint 10m. Asimmetria Dx/Sx >10% indica squilibrio frenante a rischio infortunio.",
        "schema_metriche": [
            {"key": "tempo_505", "label": "Tempo 5-0-5", "unit": "s", "direction": "LOWER_IS_BETTER", "laterality": "UNILATERAL", "is_primary_kpi": True, "color": "#0ea5e9"},
            {"key": "cod_deficit", "label": "COD Deficit", "unit": "s", "direction": "LOWER_IS_BETTER", "laterality": "UNILATERAL", "is_primary_kpi": False, "color": "#f59e0b"}
        ]
    })

    # 11. T-Test Agility
    protocols.append({
        "codice_univoco": "t_test_agility",
        "nome_protocollo": "T-Test Agility",
        "macro_area": macro_campo,
        "categoria": "Agilità & Cambi di Direzione (COD)",
        "manuale_obiettivi": "Agilità multidirezionale con corsa avanti, scivolamenti laterali e corsa all'indietro.",
        "manuale_esecuzione": "Percorso a 'T' (9.14m avanti, 4.57m laterale sx, 9.14m laterale dx, 4.57m centro, ritorno indietro).",
        "manuale_interpretazione": "Benchmark élite maschile: <9.5s. Femminile: <10.5s.",
        "schema_metriche": [
            {"key": "tempo_best", "label": "Tempo Best", "unit": "s", "direction": "LOWER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": True, "color": "#0ea5e9"},
            {"key": "tempo_partenza", "label": "Tempo Partenza Dx vs Sx", "unit": "s", "direction": "LOWER_IS_BETTER", "laterality": "UNILATERAL", "is_primary_kpi": False, "color": "#f59e0b"}
        ]
    })

    # 12-16. Sprint Lineari (5m, 10m, 15m, 20m, 30m)
    protocols.append({
        "codice_univoco": "sprint_5m",
        "nome_protocollo": "Sprint 5m (Primo Passo)",
        "macro_area": macro_campo,
        "categoria": "Velocità Lineare & Accelerazione",
        "manuale_obiettivi": "Reattività al primo passo e spinta orizzontale esplosiva iniziale.",
        "manuale_esecuzione": "Partenza da fermo a 30cm dalla prima fotocellula, sprint massimale sui 5 metri.",
        "manuale_interpretazione": "Benchmark élite: <1.05s.",
        "schema_metriche": [
            {"key": "tempo_5m", "label": "Tempo 5m", "unit": "s", "direction": "LOWER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": True, "color": "#0ea5e9"},
            {"key": "velocita_media", "label": "Velocità Media", "unit": "m/s", "direction": "HIGHER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#10b981"}
        ]
    })

    protocols.append({
        "codice_univoco": "sprint_10m",
        "nome_protocollo": "Sprint 10m (Accelerazione Breve)",
        "macro_area": macro_campo,
        "categoria": "Velocità Lineare & Accelerazione",
        "manuale_obiettivi": "Capacità di accelerazione iniziale pura specifica del campo da tennis.",
        "manuale_esecuzione": "Sprint massimale 10m con split cronometrico a 5m e 10m.",
        "manuale_interpretazione": "Benchmark élite: <1.65s (split 0-5m <1.05s).",
        "schema_metriche": [
            {"key": "tempo_10m", "label": "Tempo 10m", "unit": "s", "direction": "LOWER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": True, "color": "#0ea5e9"},
            {"key": "split_0_5m", "label": "Split 0-5m", "unit": "s", "direction": "LOWER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#38bdf8"},
            {"key": "split_5_10m", "label": "Split 5-10m", "unit": "s", "direction": "LOWER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#38bdf8"},
            {"key": "velocita_media", "label": "Velocità Media", "unit": "m/s", "direction": "HIGHER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#10b981"}
        ]
    })

    protocols.append({
        "codice_univoco": "sprint_15m",
        "nome_protocollo": "Sprint 15m",
        "macro_area": macro_campo,
        "categoria": "Velocità Lineare & Accelerazione",
        "manuale_obiettivi": "Valutazione dell'accelerazione completa fino alla velocità di crociera.",
        "manuale_esecuzione": "Sprint 15m con split a 5m e 15m.",
        "manuale_interpretazione": "Benchmark élite: <2.35s.",
        "schema_metriche": [
            {"key": "tempo_15m", "label": "Tempo 15m", "unit": "s", "direction": "LOWER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": True, "color": "#0ea5e9"},
            {"key": "split_0_5m", "label": "Split 0-5m", "unit": "s", "direction": "LOWER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#38bdf8"},
            {"key": "split_5_15m", "label": "Split 5-15m", "unit": "s", "direction": "LOWER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#38bdf8"},
            {"key": "velocita_picco", "label": "Velocità Picco", "unit": "km/h", "direction": "HIGHER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#10b981"}
        ]
    })

    protocols.append({
        "codice_univoco": "sprint_20m",
        "nome_protocollo": "Sprint 20m",
        "macro_area": macro_campo,
        "categoria": "Velocità Lineare & Accelerazione",
        "manuale_obiettivi": "Transizione tra fase di accelerazione e velocità massimale lanciata.",
        "manuale_esecuzione": "Sprint 20m con split 0-10m e 10-20m (Flying).",
        "manuale_interpretazione": "Benchmark élite: <2.95s.",
        "schema_metriche": [
            {"key": "tempo_20m", "label": "Tempo 20m", "unit": "s", "direction": "LOWER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": True, "color": "#0ea5e9"},
            {"key": "split_0_10m", "label": "Split 0-10m", "unit": "s", "direction": "LOWER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#38bdf8"},
            {"key": "split_10_20m", "label": "Split 10-20m (Flying)", "unit": "s", "direction": "LOWER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#38bdf8"},
            {"key": "velocita_picco", "label": "Velocità Picco", "unit": "km/h", "direction": "HIGHER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#10b981"}
        ]
    })

    protocols.append({
        "codice_univoco": "sprint_30m",
        "nome_protocollo": "Sprint 30m (Velocità Massima)",
        "macro_area": macro_campo,
        "categoria": "Velocità Lineare & Accelerazione",
        "manuale_obiettivi": "Velocità massima assoluta (Vmax) e profilo di accelerazione.",
        "manuale_esecuzione": "Sprint 30m con rilevamento split a 10m, 20m e 30m.",
        "manuale_interpretazione": "Benchmark élite: <4.00s (Vmax >30 km/h).",
        "schema_metriche": [
            {"key": "tempo_30m", "label": "Tempo 30m", "unit": "s", "direction": "LOWER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": True, "color": "#0ea5e9"},
            {"key": "split_0_10m", "label": "Split 0-10m", "unit": "s", "direction": "LOWER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#38bdf8"},
            {"key": "split_10_20m", "label": "Split 10-20m", "unit": "s", "direction": "LOWER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#38bdf8"},
            {"key": "split_20_30m", "label": "Split 20-30m", "unit": "s", "direction": "LOWER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#38bdf8"},
            {"key": "vmax", "label": "Velocità Massima (Vmax)", "unit": "km/h", "direction": "HIGHER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#10b981"}
        ]
    })

    # =========================================================================
    # GRUPPO 2: PEDANE DI FORZA (VALD ForceDecks - 16 Protocolli)
    # =========================================================================
    macro_pedane = "Pedane di Forza (VALD ForceDecks / Salto & IMTP)"

    protocols.append({
        "codice_univoco": "vald_fd_cmj",
        "nome_protocollo": "Countermovement Jump (CMJ)",
        "macro_area": macro_pedane,
        "categoria": "Esplosività & Salto (Neuromuscolare)",
        "manuale_obiettivi": "Test neuromuscolare gold standard per altezza di salto, efficienza del ciclo stiramento-accorciamento (SSC) e asimmetria degli impulsi.",
        "manuale_esecuzione": "Salto verticale massimale con contromovimento rapido e mani sui fianchi su pedane VALD ForceDecks.",
        "manuale_interpretazione": "Jump Height >40cm (maschile), Peak Power, Stiffness e asimmetrie bilaterali (target <10%).",
        "schema_metriche": [
            {"key": "jump_height", "label": "Max Jump Height (Imp-Mom)", "unit": "cm", "direction": "HIGHER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": True, "color": "#0ea5e9"},
            {"key": "peak_power", "label": "Max Peak Power", "unit": "W", "direction": "HIGHER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": True, "color": "#10b981"},
            {"key": "stiffness", "label": "Max CMJ Stiffness", "unit": "N/m", "direction": "HIGHER_IS_BETTER", "laterality": "UNILATERAL", "is_primary_kpi": False, "color": "#38bdf8"},
            {"key": "concentric_impulse_100ms", "label": "Max Concentric Impulse-100ms", "unit": "N s", "direction": "HIGHER_IS_BETTER", "laterality": "UNILATERAL", "is_primary_kpi": False, "color": "#38bdf8"},
            {"key": "concentric_peak_force", "label": "Max Concentric Peak Force", "unit": "N", "direction": "HIGHER_IS_BETTER", "laterality": "UNILATERAL", "is_primary_kpi": False, "color": "#38bdf8"},
            {"key": "concentric_rfd_100ms", "label": "Max Concentric RFD - 100ms", "unit": "N/s", "direction": "HIGHER_IS_BETTER", "laterality": "UNILATERAL", "is_primary_kpi": False, "color": "#f59e0b"},
            {"key": "ecc_decel_peak_force", "label": "Max Eccentric Deceleration Peak Force", "unit": "N", "direction": "HIGHER_IS_BETTER", "laterality": "UNILATERAL", "is_primary_kpi": False, "color": "#ef4444"},
            {"key": "eccentric_peak_power", "label": "Max Eccentric Peak Power", "unit": "W", "direction": "HIGHER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#a855f7"}
        ]
    })

    protocols.append({
        "codice_univoco": "vald_fd_sj",
        "nome_protocollo": "Squat Jump (SJ)",
        "macro_area": macro_pedane,
        "categoria": "Esplosività & Salto (Neuromuscolare)",
        "manuale_obiettivi": "Valutazione della forza esplosiva concentrica pura senza sfruttamento dell'energia elastica (senza contromovimento).",
        "manuale_esecuzione": "Salto verticale partendo da posizione isometrica a ginocchia flesse a 90° mantenuta per 2-3 secondi.",
        "manuale_interpretazione": "Jump Height, Peak Velocity, Forza e Potenza concentrica.",
        "schema_metriche": [
            {"key": "jump_height", "label": "Max Jump Height (Imp-Mom)", "unit": "cm", "direction": "HIGHER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": True, "color": "#0ea5e9"},
            {"key": "concentric_mean_force", "label": "Max Concentric Mean Force", "unit": "N", "direction": "HIGHER_IS_BETTER", "laterality": "UNILATERAL", "is_primary_kpi": False, "color": "#38bdf8"},
            {"key": "concentric_peak_velocity", "label": "Max Concentric Peak Velocity", "unit": "m/s", "direction": "HIGHER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#10b981"},
            {"key": "concentric_impulse_100ms", "label": "Max Concentric Impulse-100ms", "unit": "N s", "direction": "HIGHER_IS_BETTER", "laterality": "UNILATERAL", "is_primary_kpi": False, "color": "#38bdf8"},
            {"key": "peak_power", "label": "Max Peak Power", "unit": "W", "direction": "HIGHER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#10b981"},
            {"key": "concentric_rfd_100ms", "label": "Max Concentric RFD - 100ms", "unit": "N/s", "direction": "HIGHER_IS_BETTER", "laterality": "UNILATERAL", "is_primary_kpi": False, "color": "#f59e0b"}
        ]
    })

    protocols.append({
        "codice_univoco": "vald_fd_dj",
        "nome_protocollo": "Drop Jump (DJ)",
        "macro_area": macro_pedane,
        "categoria": "Esplosività & Salto (Neuromuscolare)",
        "manuale_obiettivi": "Reattività elastica veloce (Fast Stretch-Shortening Cycle) e capacità di frenata pliometrica.",
        "manuale_esecuzione": "Caduta da box di 30-40cm e rimbalzo verticale immediato minimizzando il tempo di contatto al suolo (<250ms).",
        "manuale_interpretazione": "RSI = Flight Time / Contact Time. Valori >2.2 indicano eccellente stiffness reattiva.",
        "schema_metriche": [
            {"key": "rsi", "label": "Max RSI (JH (Flight Time)/Contact Time)", "unit": "m/s", "direction": "HIGHER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": True, "color": "#10b981"},
            {"key": "eccentric_duration", "label": "Max Eccentric Duration", "unit": "ms", "direction": "LOWER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#38bdf8"},
            {"key": "concentric_mean_power", "label": "Max Concentric Mean Power", "unit": "W", "direction": "HIGHER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#38bdf8"},
            {"key": "eccentric_mean_force", "label": "Max Eccentric Mean Force", "unit": "N", "direction": "HIGHER_IS_BETTER", "laterality": "UNILATERAL", "is_primary_kpi": False, "color": "#38bdf8"},
            {"key": "peak_power", "label": "Max Peak Power", "unit": "W", "direction": "HIGHER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#0ea5e9"},
            {"key": "coeff_restitution", "label": "Max Coefficient of Restitution", "unit": "", "direction": "HIGHER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#10b981"},
            {"key": "concentric_impulse", "label": "Max Concentric Impulse", "unit": "N s", "direction": "HIGHER_IS_BETTER", "laterality": "UNILATERAL", "is_primary_kpi": False, "color": "#38bdf8"}
        ]
    })

    protocols.append({
        "codice_univoco": "vald_fd_slj",
        "nome_protocollo": "Single Leg Jump (SLJ)",
        "macro_area": macro_pedane,
        "categoria": "Esplosività & Salto (Neuromuscolare)",
        "manuale_obiettivi": "Valutazione dell'esplosività, stiffness e simmetria di salto su arto singolo con ForceDecks.",
        "manuale_esecuzione": "Salto verticale massimale su singolo arto (mani sui fianchi).",
        "manuale_interpretazione": "Confronto Dx vs Sx su altezza di salto, RFD, stiffness e potenza.",
        "schema_metriche": [
            {"key": "jump_height", "label": "Max Jump Height (Imp-Mom)", "unit": "cm", "direction": "HIGHER_IS_BETTER", "laterality": "UNILATERAL", "is_primary_kpi": True, "color": "#0ea5e9"},
            {"key": "concentric_max_rfd", "label": "Max Concentric Maximum RFD", "unit": "N/s", "direction": "HIGHER_IS_BETTER", "laterality": "UNILATERAL", "is_primary_kpi": False, "color": "#10b981"},
            {"key": "stiffness", "label": "Max CMJ Stiffness", "unit": "N/m", "direction": "HIGHER_IS_BETTER", "laterality": "UNILATERAL", "is_primary_kpi": False, "color": "#38bdf8"},
            {"key": "concentric_mean_force", "label": "Max Concentric Mean Force", "unit": "N", "direction": "HIGHER_IS_BETTER", "laterality": "UNILATERAL", "is_primary_kpi": False, "color": "#38bdf8"},
            {"key": "concentric_rfd_100ms", "label": "Max Concentric RFD - 100ms", "unit": "N/s", "direction": "HIGHER_IS_BETTER", "laterality": "UNILATERAL", "is_primary_kpi": False, "color": "#f59e0b"},
            {"key": "velocity_at_peak_power", "label": "Max Velocity at Peak Power", "unit": "m/s", "direction": "HIGHER_IS_BETTER", "laterality": "UNILATERAL", "is_primary_kpi": False, "color": "#38bdf8"},
            {"key": "eccentric_peak_power", "label": "Max Eccentric Peak Power", "unit": "W", "direction": "HIGHER_IS_BETTER", "laterality": "UNILATERAL", "is_primary_kpi": False, "color": "#a855f7"}
        ]
    })

    protocols.append({
        "codice_univoco": "vald_fd_sldj",
        "nome_protocollo": "Single Leg Drop Jump (SLDJ)",
        "macro_area": macro_pedane,
        "categoria": "Esplosività & Salto (Neuromuscolare)",
        "manuale_obiettivi": "Reattività e stiffness pliometrica su singolo arto (fondamentale per atterraggi e ripartenze nel tennis).",
        "manuale_esecuzione": "Caduta monopodalica da box di 15-20cm con salto verticale immediato sul singolo arto.",
        "manuale_interpretazione": "Asimmetria di RSI >12% tra arto di spinta e arto non dominante è un primario campanello d'allarme.",
        "schema_metriche": [
            {"key": "rsi", "label": "RSI", "unit": "ratio", "direction": "HIGHER_IS_BETTER", "laterality": "UNILATERAL", "is_primary_kpi": True, "color": "#10b981"},
            {"key": "jump_height", "label": "Jump Height", "unit": "cm", "direction": "HIGHER_IS_BETTER", "laterality": "UNILATERAL", "is_primary_kpi": False, "color": "#0ea5e9"},
            {"key": "active_stiffness", "label": "Active Stiffness", "unit": "N/m", "direction": "HIGHER_IS_BETTER", "laterality": "UNILATERAL", "is_primary_kpi": False, "color": "#38bdf8"}
        ]
    })

    protocols.append({
        "codice_univoco": "vald_fd_hj",
        "nome_protocollo": "Hop Test (HJ - Bilateral)",
        "macro_area": macro_pedane,
        "categoria": "Esplosività & Salto (Neuromuscolare)",
        "manuale_obiettivi": "Valutazione dei balzi ritmici continui (ankle stiffness e frequenza elastica).",
        "manuale_esecuzione": "Serie di balzi verticali a ginocchia quasi tese sfruttando prevalentemente il complesso caviglia-tendine d'Achille.",
        "manuale_interpretazione": "RSI medio e asimmetria di picco di forza.",
        "schema_metriche": [
            {"key": "rsi", "label": "RSI", "unit": "ratio", "direction": "HIGHER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": True, "color": "#10b981"},
            {"key": "peak_force_asym", "label": "Peak Force Asymmetry", "unit": "%", "direction": "LOWER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#ef4444"}
        ]
    })

    protocols.append({
        "codice_univoco": "vald_fd_slhj",
        "nome_protocollo": "Single Leg Hop Test (SLHJ)",
        "macro_area": macro_pedane,
        "categoria": "Esplosività & Salto (Neuromuscolare)",
        "manuale_obiettivi": "Balzi ritmici monopodalici ripetuti per valutare la stiffness attiva della caviglia destra vs sinistra.",
        "manuale_esecuzione": "Serie di 5-10 balzi continui su un singolo arto mantenendo la reattività costante.",
        "manuale_interpretazione": "Asimmetria di Mean Active Stiffness e Contact Time target <10%.",
        "schema_metriche": [
            {"key": "rsi", "label": "RSI", "unit": "ratio", "direction": "HIGHER_IS_BETTER", "laterality": "UNILATERAL", "is_primary_kpi": True, "color": "#10b981"},
            {"key": "active_stiffness", "label": "Mean Active Stiffness", "unit": "N/m", "direction": "HIGHER_IS_BETTER", "laterality": "UNILATERAL", "is_primary_kpi": False, "color": "#38bdf8"},
            {"key": "mean_impulse", "label": "Mean Impulse", "unit": "Ns", "direction": "HIGHER_IS_BETTER", "laterality": "UNILATERAL", "is_primary_kpi": False, "color": "#38bdf8"},
            {"key": "peak_force_asym", "label": "Peak Force Asymmetry", "unit": "%", "direction": "LOWER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#ef4444"},
            {"key": "contact_time_asym", "label": "Contact Time Asymmetry", "unit": "%", "direction": "LOWER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#ef4444"}
        ]
    })

    protocols.append({
        "codice_univoco": "vald_fd_slhar",
        "nome_protocollo": "Hop and Return (SLHAR)",
        "macro_area": macro_pedane,
        "categoria": "Controllo Motorio & Stabilometria",
        "manuale_obiettivi": "Test funzionale di frenata e rientro orizzontale/verticale specifico per il Return to Play.",
        "manuale_esecuzione": "Balzo avanti atterrando su pedana di forza e rientro immediato con stabilizzazione.",
        "manuale_interpretazione": "Time to Stabilization e simmetria delle forze di picco in atterraggio.",
        "schema_metriche": [
            {"key": "contact_time", "label": "Contact Time", "unit": "s", "direction": "LOWER_IS_BETTER", "laterality": "UNILATERAL", "is_primary_kpi": True, "color": "#0ea5e9"},
            {"key": "time_to_stabilization", "label": "Time to Stabilization", "unit": "s", "direction": "LOWER_IS_BETTER", "laterality": "UNILATERAL", "is_primary_kpi": False, "color": "#10b981"},
            {"key": "concentric_duration", "label": "Concentric Duration", "unit": "ms", "direction": "LOWER_IS_BETTER", "laterality": "UNILATERAL", "is_primary_kpi": False, "color": "#38bdf8"},
            {"key": "eccentric_duration", "label": "Eccentric Duration", "unit": "ms", "direction": "LOWER_IS_BETTER", "laterality": "UNILATERAL", "is_primary_kpi": False, "color": "#38bdf8"},
            {"key": "peak_force_asym", "label": "Peak Take Off / Landing Force Asymmetry", "unit": "%", "direction": "LOWER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#ef4444"}
        ]
    })

    protocols.append({
        "codice_univoco": "vald_fd_imtp",
        "nome_protocollo": "Isometric Mid-Thigh Pull (IMTP)",
        "macro_area": macro_pedane,
        "categoria": "Forza Isometrica & Dinamometria",
        "manuale_obiettivi": "Valutazione della forza massima assoluta isometrica e del Rate of Force Development (RFD).",
        "manuale_esecuzione": "Tirata massimale a bilanciere fisso ad altezza metà coscia (angoli ginocchio ~135°, anca ~140°) per 3-5s.",
        "manuale_interpretazione": "Peak Force / Body Mass >35 N/kg = ottimo. RFD a 100ms correla con la capacità di accelerazione in campo.",
        "schema_metriche": [
            {"key": "peak_vertical_force", "label": "Max Peak Vertical Force", "unit": "N", "direction": "HIGHER_IS_BETTER", "laterality": "UNILATERAL", "is_primary_kpi": True, "color": "#0ea5e9"},
            {"key": "rfd_100ms", "label": "Max RFD - 100ms", "unit": "N/s", "direction": "HIGHER_IS_BETTER", "laterality": "UNILATERAL", "is_primary_kpi": False, "color": "#10b981"},
            {"key": "force_100ms", "label": "Max Force at 100ms", "unit": "N", "direction": "HIGHER_IS_BETTER", "laterality": "UNILATERAL", "is_primary_kpi": False, "color": "#38bdf8"},
            {"key": "absolute_impulse_100ms", "label": "Max Absolute Impulse - 100ms", "unit": "N s", "direction": "HIGHER_IS_BETTER", "laterality": "UNILATERAL", "is_primary_kpi": False, "color": "#38bdf8"},
            {"key": "start_time_to_peak_force", "label": "Max Start Time to Peak Force", "unit": "s", "direction": "LOWER_IS_BETTER", "laterality": "UNILATERAL", "is_primary_kpi": False, "color": "#f59e0b"}
        ]
    })

    protocols.append({
        "codice_univoco": "vald_fd_slisot",
        "nome_protocollo": "Single Limb Isometric Test (SLISOT)",
        "macro_area": macro_pedane,
        "categoria": "Forza Isometrica & Dinamometria",
        "manuale_obiettivi": "Forza isometrica massima e RFD su singolo arto per valutare asimmetrie di picco di forza.",
        "manuale_esecuzione": "Tirata o spinta isometrica monopodalica.",
        "manuale_interpretazione": "Peak Force Relativa Dx vs Sx. Target asimmetria <10%.",
        "schema_metriche": [
            {"key": "peak_force_rel", "label": "Peak Vertical Force / Body Mass", "unit": "N/kg", "direction": "HIGHER_IS_BETTER", "laterality": "UNILATERAL", "is_primary_kpi": True, "color": "#0ea5e9"},
            {"key": "rfd_100_150", "label": "RFD 100-150", "unit": "N/s", "direction": "HIGHER_IS_BETTER", "laterality": "UNILATERAL", "is_primary_kpi": False, "color": "#10b981"},
            {"key": "start_time_80pct", "label": "Start Time to 80% Net Peak Force", "unit": "s", "direction": "LOWER_IS_BETTER", "laterality": "UNILATERAL", "is_primary_kpi": False, "color": "#f59e0b"}
        ]
    })

    protocols.append({
        "codice_univoco": "vald_fd_sqt",
        "nome_protocollo": "Squat Assessment (SQT)",
        "macro_area": macro_pedane,
        "categoria": "Controllo Motorio & Stabilometria",
        "manuale_obiettivi": "Valutazione del controllo di carico e delle asimmetrie durante uno squat controllato.",
        "manuale_esecuzione": "Squat a carico naturale o con sovraccarico eseguito lentamente sulle pedane di forza.",
        "manuale_interpretazione": "Asimmetrie nella fase eccentrica e concentrica indicano compensi di carico.",
        "schema_metriche": [
            {"key": "concentric_impulse_asym", "label": "Concentric Impulse Asymmetry", "unit": "%", "direction": "LOWER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": True, "color": "#ef4444"},
            {"key": "eccentric_impulse_asym", "label": "Eccentric Impulse Asymmetry", "unit": "%", "direction": "LOWER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#ef4444"}
        ]
    })

    protocols.append({
        "codice_univoco": "vald_fd_slsqt",
        "nome_protocollo": "Single Leg Squat Assessment (SLSQT)",
        "macro_area": macro_pedane,
        "categoria": "Controllo Motorio & Stabilometria",
        "manuale_obiettivi": "Profondità di discesa e potenza espressa nello squat monopodalico (Pistol / Single leg squat).",
        "manuale_esecuzione": "Piegamento su un singolo arto mantenendo il controllo pelvico e rialzo.",
        "manuale_interpretazione": "Dislocamento negativo (profondità) e potenza concentrica relativa.",
        "schema_metriche": [
            {"key": "peak_power_rel", "label": "Concentric Peak Power / Body Mass", "unit": "W/kg", "direction": "HIGHER_IS_BETTER", "laterality": "UNILATERAL", "is_primary_kpi": True, "color": "#0ea5e9"},
            {"key": "max_neg_disp", "label": "Maximum Negative Displacement", "unit": "cm", "direction": "HIGHER_IS_BETTER", "laterality": "UNILATERAL", "is_primary_kpi": False, "color": "#10b981"}
        ]
    })

    protocols.append({
        "codice_univoco": "vald_fd_lah",
        "nome_protocollo": "Land and Hold (LAH / SLLAH)",
        "macro_area": macro_pedane,
        "categoria": "Controllo Motorio & Stabilometria",
        "manuale_obiettivi": "Capacità di assorbimento dell'impatto da salto e stabilizzazione rapida del baricentro.",
        "manuale_esecuzione": "Salto da box e atterraggio fermandosi immobili in posizione di squat per 3 secondi.",
        "manuale_interpretazione": "Time to Stabilization target <1.2s. Asimmetrie elevate indicano deficit frenante.",
        "schema_metriche": [
            {"key": "time_to_stabilization", "label": "Time to Stabilization", "unit": "s", "direction": "LOWER_IS_BETTER", "laterality": "UNILATERAL", "is_primary_kpi": True, "color": "#0ea5e9"},
            {"key": "peak_landing_force_asym", "label": "Peak Landing Force Asymmetry", "unit": "%", "direction": "LOWER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#ef4444"}
        ]
    })

    protocols.append({
        "codice_univoco": "vald_fd_ash_iyt",
        "nome_protocollo": "I-Y-T Test (ASH Test - Spalla Isometrica)",
        "macro_area": macro_pedane,
        "categoria": "Forza Isometrica & Dinamometria",
        "manuale_obiettivi": "Test specifico per la spalla del tennista (Athletic Shoulder Test - ASH Test) nelle posizioni I (180°), Y (135°) e T (90°).",
        "manuale_esecuzione": "Atleta prono con braccio esteso sulla pedana di forza o dinamometro; spinta massimale verso l'alto per 3s.",
        "manuale_interpretazione": "Confronto arto dominante vs non dominante. Asimmetria target <10%.",
        "schema_metriche": [
            {"key": "peak_force_i", "label": "Peak Force - Posizione I (180°)", "unit": "N", "direction": "HIGHER_IS_BETTER", "laterality": "UNILATERAL", "is_primary_kpi": True, "color": "#0ea5e9"},
            {"key": "peak_force_y", "label": "Peak Force - Posizione Y (135°)", "unit": "N", "direction": "HIGHER_IS_BETTER", "laterality": "UNILATERAL", "is_primary_kpi": False, "color": "#38bdf8"},
            {"key": "peak_force_t", "label": "Peak Force - Posizione T (90°)", "unit": "N", "direction": "HIGHER_IS_BETTER", "laterality": "UNILATERAL", "is_primary_kpi": False, "color": "#10b981"},
            {"key": "start_time_peak", "label": "Start Time to Peak Force", "unit": "s", "direction": "LOWER_IS_BETTER", "laterality": "UNILATERAL", "is_primary_kpi": False, "color": "#f59e0b"},
            {"key": "impulse_asym", "label": "Impulse Asymmetry", "unit": "%", "direction": "LOWER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#ef4444"},
            {"key": "time_to_peak_asym", "label": "Time to Peak Force Asymmetry", "unit": "%", "direction": "LOWER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#ef4444"}
        ]
    })

    protocols.append({
        "codice_univoco": "vald_fd_pushup",
        "nome_protocollo": "Push Up Test (Pedane)",
        "macro_area": macro_pedane,
        "categoria": "Controllo Motorio & Stabilometria",
        "manuale_obiettivi": "Valutazione dell'asimmetria di carico degli arti superiori durante i piegamenti.",
        "manuale_esecuzione": "Piegamenti sulle braccia con mani posizionate ciascuna su una pedana di forza.",
        "manuale_interpretazione": "Asimmetria di forza di picco e di impulso concentrico ed eccentrico.",
        "schema_metriche": [
            {"key": "peak_force_asym", "label": "Peak Force Asymmetry", "unit": "%", "direction": "LOWER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": True, "color": "#ef4444"},
            {"key": "concentric_impulse_asym", "label": "Concentric Impulse Asymmetry", "unit": "%", "direction": "LOWER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#ef4444"},
            {"key": "eccentric_impulse_asym", "label": "Eccentric Impulse Asymmetry", "unit": "%", "direction": "LOWER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#ef4444"}
        ]
    })

    protocols.append({
        "codice_univoco": "vald_fd_qss_slss",
        "nome_protocollo": "Quiet Stand / Single Leg Stand & Stability (QSS/SLSS)",
        "macro_area": macro_pedane,
        "categoria": "Controllo Motorio & Stabilometria",
        "manuale_obiettivi": "Stabilometria statica monopodalica e oscillazioni del centro di pressione (CoP).",
        "manuale_esecuzione": "Stazione eretta su un solo piede per 20-30s a occhi aperti/chiusi.",
        "manuale_interpretazione": "Range di escursione antero-posteriore e medio-laterale del CoP (minore = più stabile).",
        "schema_metriche": [
            {"key": "cop_range_ap", "label": "CoP Range Anterior-Posterior", "unit": "mm", "direction": "LOWER_IS_BETTER", "laterality": "UNILATERAL", "is_primary_kpi": True, "color": "#0ea5e9"},
            {"key": "cop_range_ml", "label": "CoP Range Medial-Lateral", "unit": "mm", "direction": "LOWER_IS_BETTER", "laterality": "UNILATERAL", "is_primary_kpi": False, "color": "#38bdf8"}
        ]
    })

    protocols.append({
        "codice_univoco": "vald_fd_ststs",
        "nome_protocollo": "Sit to Stand to Sit (STSTS) & Weight Distribution",
        "macro_area": macro_pedane,
        "categoria": "Controllo Motorio & Stabilometria",
        "manuale_obiettivi": "Distribuzione del peso corporeo e tempo di alzata dalla sedia.",
        "manuale_esecuzione": "Transizione controllata da seduto a in piedi su pedane separate.",
        "manuale_interpretazione": "Asimmetria di carico tra gli arti inferiori.",
        "schema_metriche": [
            {"key": "time_to_stand", "label": "Time to Stand", "unit": "s", "direction": "LOWER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": True, "color": "#0ea5e9"},
            {"key": "peak_standing_force", "label": "Peak Standing Force", "unit": "N", "direction": "HIGHER_IS_BETTER", "laterality": "UNILATERAL", "is_primary_kpi": False, "color": "#10b981"},
            {"key": "standing_weight_asym", "label": "Standing Weight Asymmetry", "unit": "%", "direction": "LOWER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#ef4444"}
        ]
    })

    # =========================================================================
    # GRUPPO 3: FORZA ECCENTRICA & ISCHIOCRURALI (VALD NordBord - 5 Protocolli)
    # =========================================================================
    macro_nordbord = "Forza Eccentrica & Ischiocrurali (VALD NordBord)"
    nordbord_protocols = [
        ("nordic_hamstring_eccentric", "Nordic Hamstring (Eccentric)", "Forza eccentrica massimale dei flessori del ginocchio."),
        ("razor_curl", "Razor Curl (Eccentric / Isometric)", "Variante a flessione d'anca per reclutamento mirato ischiocrurali."),
        ("iso_prone_0", "ISO Prone (0°)", "Forza isometrica a ginocchio esteso (0°)."),
        ("iso_prone_30", "ISO 30°", "Forza isometrica a 30° di flessione di ginocchio."),
        ("iso_prone_60", "ISO 60°", "Forza isometrica a 60° di flessione di ginocchio.")
    ]

    for cod, nome, desc in nordbord_protocols:
        protocols.append({
            "codice_univoco": cod,
            "nome_protocollo": nome,
            "macro_area": macro_nordbord,
            "categoria": "Forza Eccentrica & Prevenzione",
            "manuale_obiettivi": desc,
            "manuale_esecuzione": "Esecuzione su dinamometro VALD NordBord con caviglie vincolate.",
            "manuale_interpretazione": "Peak Force >350N per atleti d'élite. Asimmetria Dx/Sx >10-15% è fattore primario di rischio lesionale.",
            "schema_metriche": [
                {"key": "peak_force", "label": "Peak Force", "unit": "N", "direction": "HIGHER_IS_BETTER", "laterality": "UNILATERAL", "is_primary_kpi": True, "color": "#0ea5e9"},
                {"key": "torque", "label": "Torque", "unit": "Nm", "direction": "HIGHER_IS_BETTER", "laterality": "UNILATERAL", "is_primary_kpi": False, "color": "#38bdf8"},
                {"key": "impulse", "label": "Impulse", "unit": "Ns", "direction": "HIGHER_IS_BETTER", "laterality": "UNILATERAL", "is_primary_kpi": False, "color": "#10b981"},
                {"key": "peak_force_asym", "label": "Peak Force Asymmetry", "unit": "%", "direction": "LOWER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#ef4444"},
                {"key": "impulse_asym", "label": "Impulse Asymmetry", "unit": "%", "direction": "LOWER_IS_BETTER", "laterality": "BILATERAL", "is_primary_kpi": False, "color": "#ef4444"}
            ]
        })

    # =========================================================================
    # GRUPPO 4: DINAMOMETRIA ISOMETRICA (VALD DynaMo Forza - 31 Protocolli)
    # =========================================================================
    macro_dynamo_forza = "Dinamometria Isometrica (VALD DynaMo Forza)"

    def _dynamo_forza_metriche(is_unilateral=True):
        lat = "UNILATERAL" if is_unilateral else "BILATERAL"
        return [
            {"key": "max_force", "label": "Max Force", "unit": "N", "direction": "HIGHER_IS_BETTER", "laterality": lat, "is_primary_kpi": True, "color": "#0ea5e9"},
            {"key": "max_impulse", "label": "Max Impulse", "unit": "N⋅s", "direction": "HIGHER_IS_BETTER", "laterality": lat, "is_primary_kpi": False, "color": "#10b981"},
            {"key": "rfd", "label": "Max Rate of Force Development", "unit": "N/s", "direction": "HIGHER_IS_BETTER", "laterality": lat, "is_primary_kpi": False, "color": "#38bdf8"},
            {"key": "time_to_peak_force", "label": "Max Time to Peak Force", "unit": "s", "direction": "LOWER_IS_BETTER", "laterality": lat, "is_primary_kpi": False, "color": "#f59e0b"},
            {"key": "peak_force", "label": "Peak Force (Alias)", "unit": "N", "direction": "HIGHER_IS_BETTER", "laterality": lat, "is_primary_kpi": False, "color": "#0ea5e9"}
        ]

    dynamo_forza_def = [
        ("dynamo_f_grip", "Forza - Grip Strength (Presa Manuale)", True, "Forza isometrica di presa della mano."),
        ("dynamo_f_cerv_fless", "Forza - Cervicale Flessione", False, "Flessione isometrica del rachide cervicale."),
        ("dynamo_f_cerv_est", "Forza - Cervicale Estensione", False, "Estensione isometrica del rachide cervicale."),
        ("dynamo_f_cerv_lat", "Forza - Cervicale Flessione Laterale", True, "Flessione laterale isometrica cervicale Dx vs Sx."),
        ("dynamo_f_spalla_fless", "Forza - Spalla Flessione", True, "Flessione isometrica spalla."),
        ("dynamo_f_spalla_est", "Forza - Spalla Estensione", True, "Estensione isometrica spalla."),
        ("dynamo_f_spalla_abd", "Forza - Spalla Abduzione", True, "Abduzione isometrica spalla."),
        ("dynamo_f_spalla_add", "Forza - Spalla Adduzione", True, "Adduzione isometrica spalla."),
        ("dynamo_f_spalla_ir", "Forza - Spalla Rotazione Interna (IR)", True, "Rotazione interna spalla (intrarotatori: grande pettorale, sottoscapolare)."),
        ("dynamo_f_spalla_er", "Forza - Spalla Rotazione Esterna (ER)", True, "Rotazione esterna spalla (extrarotatori: sottospinato, piccolo rotondo)."),
        ("dynamo_f_spalla_scaption", "Forza - Spalla Scaption", True, "Elevazione sul piano della scapola (30°)."),
        ("dynamo_f_gomito_fless", "Forza - Gomito Flessione", True, "Flessione isometrica gomito."),
        ("dynamo_f_gomito_est", "Forza - Gomito Estensione", True, "Estensione isometrica gomito."),
        ("dynamo_f_polso_fless", "Forza - Polso Flessione", True, "Flessione isometrica polso."),
        ("dynamo_f_polso_est", "Forza - Polso Estensione", True, "Estensione isometrica polso (prevenzione epicondilite)."),
        ("dynamo_f_tronco_fless", "Forza - Tronco Flessione", False, "Flessione isometrica del tronco."),
        ("dynamo_f_tronco_est", "Forza - Tronco Estensione", False, "Estensione isometrica del tronco."),
        ("dynamo_f_tronco_lat", "Forza - Tronco Flessione Laterale", True, "Flessione laterale isometrica del tronco Dx vs Sx."),
        ("dynamo_f_anca_fless", "Forza - Anca Flessione", True, "Flessione isometrica anca (ileopsoas)."),
        ("dynamo_f_anca_est", "Forza - Anca Estensione", True, "Estensione isometrica anca (gluteo)."),
        ("dynamo_f_anca_abd", "Forza - Anca Abduzione", True, "Abduzione isometrica anca (medio gluteo)."),
        ("dynamo_f_anca_add", "Forza - Anca Adduzione", True, "Adduzione isometrica anca (adduttori)."),
        ("dynamo_f_anca_ir", "Forza - Anca Rotazione Interna", True, "Rotazione interna anca."),
        ("dynamo_f_anca_er", "Forza - Anca Rotazione Esterna", True, "Rotazione esterna anca."),
        ("dynamo_f_anca_groin", "Forza - Anca Groin Squeeze", True, "Squeeze isometrico adduttori a 45°/0°."),
        ("dynamo_f_ginocchio_fless", "Forza - Ginocchio Flessione", True, "Flessione isometrica ginocchio (ischiocrurali)."),
        ("dynamo_f_ginocchio_est", "Forza - Ginocchio Estensione", True, "Estensione isometrica ginocchio (quadricipite)."),
        ("dynamo_f_caviglia_dorsi", "Forza - Caviglia Dorsiflessione", True, "Dorsiflessione isometrica caviglia (tibiale anteriore)."),
        ("dynamo_f_caviglia_plantar", "Forza - Caviglia Plantarflessione", True, "Plantarflessione isometrica caviglia (tricipite surale)."),
        ("dynamo_f_caviglia_inv", "Forza - Caviglia Inversione", True, "Inversione isometrica caviglia."),
        ("dynamo_f_caviglia_ev", "Forza - Caviglia Eversione", True, "Eversione isometrica caviglia."),
        ("dynamo_f_spalla_iso_t", "Shoulder ISO T Supine", True, "Forza isometrica spalla in decubito supino a 'T' (DynaMo)."),
        ("dynamo_f_spalla_iso_i", "Shoulder ISO I Supine", True, "Forza isometrica spalla in decubito supino a 'I' (DynaMo)."),
        ("dynamo_f_spalla_ir_standing", "Shoulder IR Standing - Elbow 90°", True, "Rotazione interna spalla in piedi a 90° gomito / 90° abd (DynaMo)."),
        ("dynamo_f_spalla_er_standing", "Shoulder ER Standing - Elbow 90°", True, "Rotazione esterna spalla in piedi a 90° gomito / 90° abd (DynaMo).")
    ]

    for cod, nome, is_unil, desc in dynamo_forza_def:
        protocols.append({
            "codice_univoco": cod,
            "nome_protocollo": nome,
            "macro_area": macro_dynamo_forza,
            "categoria": "Forza Isometrica & Dinamometria",
            "manuale_obiettivi": desc,
            "manuale_esecuzione": "Rilevazione isometrica con dinamometro palmare VALD DynaMo (spinta massimale 3-5 secondi).",
            "manuale_interpretazione": "Valutazione del picco di forza assoluto (N), relativo al peso corporeo (N/kg) e dell'asimmetria Dx vs Sx (target <10%).",
            "schema_metriche": _dynamo_forza_metriche(is_unil)
        })

    # =========================================================================
    # GRUPPO 5: MOBILITÀ & RANGE OF MOTION (VALD DynaMo ROM - 33 Protocolli)
    # =========================================================================
    macro_dynamo_rom = "Mobilità & Range of Motion (VALD DynaMo ROM)"

    def _rom_metriche(unit="°", is_unil=True):
        lat = "UNILATERAL" if is_unil else "BILATERAL"
        return [
            {"key": "max_rom", "label": "Max Range of Motion", "unit": unit, "direction": "HIGHER_IS_BETTER", "laterality": lat, "is_primary_kpi": True, "color": "#0ea5e9"},
            {"key": "max_angle", "label": "Maximum Angle / Excursion (Alias)", "unit": unit, "direction": "HIGHER_IS_BETTER", "laterality": lat, "is_primary_kpi": False, "color": "#38bdf8"}
        ]

    dynamo_rom_def = [
        ("dynamo_rom_cerv_fless", "ROM - Cervicale Flessione", False, "°", "Escursione in flessione cervicale."),
        ("dynamo_rom_cerv_est", "ROM - Cervicale Estensione", False, "°", "Escursione in estensione cervicale."),
        ("dynamo_rom_cerv_lat", "ROM - Cervicale Flessione Laterale", True, "°", "Escursione in flessione laterale cervicale Dx vs Sx."),
        ("dynamo_rom_cerv_rot", "ROM - Cervicale Rotazione", True, "°", "Escursione in rotazione cervicale Dx vs Sx."),
        ("dynamo_rom_spalla_fless", "ROM - Spalla Flessione", True, "°", "Flessione articolare della spalla."),
        ("dynamo_rom_spalla_est", "ROM - Spalla Estensione", True, "°", "Estensione articolare della spalla."),
        ("dynamo_rom_spalla_abd", "ROM - Spalla Abduzione", True, "°", "Abduzione sul piano frontale."),
        ("dynamo_rom_spalla_add", "ROM - Spalla Adduzione", True, "°", "Adduzione orizzontale."),
        ("dynamo_rom_spalla_ir", "ROM - Spalla Rotazione Interna (IR)", True, "°", "Rotazione interna spalla (target deficit <15° rispetto al lato controlaterale: GIRD)."),
        ("dynamo_rom_spalla_er", "ROM - Spalla Rotazione Esterna (ER)", True, "°", "Rotazione esterna spalla."),
        ("dynamo_rom_gomito_fless", "ROM - Gomito Flessione", True, "°", "Flessione articolare del gomito."),
        ("dynamo_rom_gomito_est", "ROM - Gomito Estensione", True, "°", "Estensione articolare del gomito."),
        ("dynamo_rom_gomito_pro", "ROM - Gomito Pronazione", True, "°", "Pronazione dell'avambraccio."),
        ("dynamo_rom_gomito_sup", "ROM - Gomito Supinazione", True, "°", "Supinazione dell'avambraccio."),
        ("dynamo_rom_polso_fless", "ROM - Polso Flessione", True, "°", "Flessione palmare del polso."),
        ("dynamo_rom_polso_est", "ROM - Polso Estensione", True, "°", "Estensione dorsale del polso."),
        ("dynamo_rom_polso_dev_rad", "ROM - Polso Deviazione Radiale", True, "°", "Deviazione radiale del polso."),
        ("dynamo_rom_polso_dev_uln", "ROM - Polso Deviazione Ulnare", True, "°", "Deviazione ulnare del polso."),
        ("dynamo_rom_tronco_fless", "ROM - Tronco Flessione", False, "°", "Flessione del rachide."),
        ("dynamo_rom_tronco_est", "ROM - Tronco Estensione", False, "°", "Estensione del rachide."),
        ("dynamo_rom_tronco_lat", "ROM - Tronco Flessione Laterale", True, "°", "Flessione laterale del tronco Dx vs Sx."),
        ("dynamo_rom_tronco_rot", "ROM - Tronco Rotazione", True, "°", "Rotazione del tronco Dx vs Sx."),
        ("dynamo_rom_anca_fless", "ROM - Anca Flessione", True, "°", "Flessione anca."),
        ("dynamo_rom_anca_est", "ROM - Anca Estensione", True, "°", "Estensione anca."),
        ("dynamo_rom_anca_abd", "ROM - Anca Abduzione", True, "°", "Abduzione anca."),
        ("dynamo_rom_anca_add", "ROM - Anca Adduzione", True, "°", "Adduzione anca."),
        ("dynamo_rom_anca_ir", "ROM - Anca Rotazione Interna", True, "°", "Rotazione interna anca a 90°."),
        ("dynamo_rom_anca_er", "ROM - Anca Rotazione Esterna", True, "°", "Rotazione esterna anca a 90°."),
        ("dynamo_rom_ginocchio_fless", "ROM - Ginocchio Flessione", True, "°", "Flessione ginocchio."),
        ("dynamo_rom_ginocchio_est", "ROM - Ginocchio Estensione", True, "°", "Estensione ginocchio."),
        ("dynamo_rom_caviglia_dorsi", "ROM - Caviglia Dorsiflessione", True, "°", "Dorsiflessione a ginocchio flesso/esteso."),
        ("dynamo_rom_caviglia_plantar", "ROM - Caviglia Plantarflessione", True, "°", "Plantarflessione caviglia."),
        ("dynamo_rom_caviglia_inv", "ROM - Caviglia Inversione", True, "°", "Inversione del retropiede."),
        ("dynamo_rom_caviglia_ev", "ROM - Caviglia Eversione", True, "°", "Eversione del retropiede."),
        ("dynamo_rom_slr", "ROM - Straight Leg Raise (SLR)", True, "°", "Test di flessibilità degli ischiocrurali a gamba tesa."),
        ("dynamo_rom_thomas", "ROM - Thomas Test", True, "°", "Test di retrazione di ileopsoas e retto femorale."),
        ("dynamo_rom_knee_to_wall", "ROM - Knee to Wall (Weight-Bearing Lunge)", True, "cm", "Dorsiflessione caviglia in carico con distanza dal muro."),
        ("dynamo_rom_wrist_sup", "Wrist Supination 90° Elbow Flexion - Wrist Neutral", True, "°", "ROM supinazione polso gomito 90° neutrale."),
        ("dynamo_rom_spalla_er_seated", "Shoulder ER Seated - Elbow 90°", True, "°", "ROM rotazione esterna spalla da seduto gomito 90°."),
        ("dynamo_rom_spalla_ir_seated", "Shoulder IR Seated - Elbow 90°", True, "°", "ROM rotazione interna spalla da seduto gomito 90°."),
        ("dynamo_rom_anca_ir_prone", "Hip IR Prone", True, "°", "ROM rotazione interna anca prona."),
        ("dynamo_rom_anca_er_prone", "Hip ER Prone", True, "°", "ROM rotazione esterna anca prona."),
        ("dynamo_rom_anca_er_seated", "Hip ER Seated", True, "°", "ROM rotazione esterna anca da seduto."),
        ("dynamo_rom_anca_ir_seated", "Hip IR Seated", True, "°", "ROM rotazione interna anca da seduto.")
    ]

    for cod, nome, is_unil, unit, desc in dynamo_rom_def:
        protocols.append({
            "codice_univoco": cod,
            "nome_protocollo": nome,
            "macro_area": macro_dynamo_rom,
            "categoria": "Mobilità, ROM Articolare & Flessibilità",
            "manuale_obiettivi": desc,
            "manuale_esecuzione": "Rilevazione inclinometrica tramite VALD DynaMo ROM o inclinometro digitale.",
            "manuale_interpretazione": "Mobilità articolare in gradi (o cm) e asimmetria bilaterale. Asimmetria target <10%.",
            "schema_metriche": _rom_metriche(unit, is_unil)
        })

    return protocols
