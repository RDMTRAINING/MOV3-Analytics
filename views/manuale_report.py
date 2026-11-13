# Copyright 2026 Riccardo Di Maio - M0V3 S.r.l. Tutti i diritti riservati.
# Proprietary Sports Science & Clinical Performance Intelligence Architecture.
import os
import streamlit as st
from config import tr, render_page_header, render_action_bar, CATALOGO_REPORT
from pdf_generator import crea_pdf_manuale_report

# =========================================================================
# DATABASE METODOLOGICO E SCIENTIFICO DI TUTTE LE ANALISI M0V3
# =========================================================================

MANUALE_ANALISI = [
    # ---------------------------------------------------------------------
    # 1. ANALISI MATCH (8 Moduli)
    # ---------------------------------------------------------------------
    {
        "nome": "Distance from the average",
        "nome_it": "Scostamento Percentuale dalle Medie Match",
        "area": "Analisi Match",
        "icona": "bi-distribute-vertical",
        "colore": "#0284c7",
        "cosa_analizza": (
            "Calcola il delta percentuale (+/- %) di ogni parametro fisico, cinematico e metabolico registrato "
            "nella singola partita rispetto alla media storica personale dei match disputati dall'atleta."
        ),
        "a_cosa_serve": (
            "Permette allo staff tecnico di comprendere immediatamente se il match ha richiesto un impegno energetico, "
            "volumetrico o neuromuscolare superiore o inferiore agli standard abituali del giocatore, contestualizzando la fatica."
        ),
        "azioni_consentite": [
            "Filtro selezione Match",
            "Filtro Atleta",
            "Tabella interattiva dei delta con codice colore",
            "Badge di allerta scostamento (>15% sovraccarico)",
            "Esportazione Referto PDF"
        ],
        "bibliografia": [
            "Fernandez-Fernandez, J. et al. (2009). The physiological and metabolic demands of tennis. Sports Medicine, 39(8), 603-626.",
            "Reid, M. et al. (2016). Tracking devices in tennis: application to training and competition. International Journal of Sports Physiology and Performance, 11(5), 675-680."
        ]
    },
    {
        "nome": "Training Load Bands",
        "nome_it": "Bande di Training Load Assolute (AU)",
        "area": "Analisi Match",
        "icona": "bi-bar-chart-steps",
        "colore": "#0284c7",
        "cosa_analizza": (
            "Ripartisce il carico complessivo della partita (Training Load in AU) in 4 bande di intensità metabolica: "
            "Stand (carico di attesa/pausa), Low (bassa intensità), Medium (media intensità) e High (alta intensità)."
        ),
        "a_cosa_serve": (
            "Quantifica la composizione interna del carico di gara, evidenziando quanta parte della fatica accumulata "
            "è riconducibile a fasi di massimo impegno fisiologico rispetto a momenti di transizione o palleggi preparatori."
        ),
        "azioni_consentite": [
            "Istogramma orizzontale a barre comparative (Match vs Media Storica)",
            "Visualizzazione valori numerici in Arbitrary Units (AU)",
            "Ispezione delle soglie di intensità",
            "Esportazione Grafico in PDF"
        ],
        "bibliografia": [
            "Impellizzeri, F. M. et al. (2004). Use of RPE-based training load in sport. Medicine and Science in Sports and Exercise, 36(6), 1042-1047."
        ]
    },
    {
        "nome": "Training Load Time% Bends",
        "nome_it": "Distribuzione Percentuale del Tempo nelle Bande (%)",
        "area": "Analisi Match",
        "icona": "bi-pie-chart-fill",
        "colore": "#0284c7",
        "cosa_analizza": (
            "Calcola la quota percentuale del tempo totale di gara trascorsa all'interno di ciascuna delle 4 fasce "
            "metaboliche (Stand %, Low %, Medium %, High %)."
        ),
        "a_cosa_serve": (
            "Valuta la densità temporale dello sforzo in partita. Un incremento significativo del tempo in fascia High "
            "denota scambi prolungati, minor tempo di recupero tra i punti e un elevato impatto sui sistemi energetici lattacidi."
        ),
        "azioni_consentite": [
            "Grafico a barre sovrapposte al 100% (100% Stacked Bar)",
            "Confronto visivo contestuale (Match vs Media Match)",
            "Dettaglio dei minuti effettivi per ciascuna banda al passaggio del mouse",
            "Esportazione Report PDF"
        ],
        "bibliografia": [
            "Mendez-Villanueva, A. et al. (2007). Match play intensity, metabolic demands and recovery in tennis. British Journal of Sports Medicine, 41(11), 773-776."
        ]
    },
    {
        "nome": "Dati volumetrici IMU",
        "nome_it": "Eventi Meccanici & Volumetria Inerziale IMU (100 Hz)",
        "area": "Analisi Match",
        "icona": "bi-activity",
        "colore": "#0284c7",
        "cosa_analizza": (
            "Elabora i flussi dei sensori inerziali triassiali a 100 Hz: Durata totale (min), Player Load tridimensionale, "
            "Azioni Intense >2\" (cambi di direzione e scatti brevi), Azioni Intense >10\" (scambi prolungati) e Recuperi brevi 1-5 minuti."
        ),
        "a_cosa_serve": (
            "Fornisce la misura oggettiva dello stress meccanico e neuromuscolare a carico di tendini e articolazioni, "
            "indipendentemente dalla copertura satellitare (funziona sia su campi Indoor che Outdoor)."
        ),
        "azioni_consentite": [
            "Tabella strutturata con scostamento percentuale rispetto alla media",
            "Grafici metrici per singola variabile inerziale",
            "Filtro per atleta e match analizzato",
            "Esportazione PDF"
        ],
        "bibliografia": [
            "Boyd, L. J. et al. (2011). The reliability of MinimaxX accelerometers for measuring physical activity in sport. IJSPP, 6(3), 311-326.",
            "Cormack, S. J. et al. (2013). Influence of neuromuscular fatigue on accelerometer-based PlayerLoad. IJSPP, 8(4), 373-380."
        ]
    },
    {
        "nome": "Dati GPS",
        "nome_it": "Parametri Cinematici Satellitari Outdoor",
        "area": "Analisi Match",
        "icona": "bi-geo-alt-fill",
        "colore": "#0284c7",
        "cosa_analizza": (
            "Rileva le grandezze cinematiche di movimento su campi Outdoor: Distanza Totale percorsa (m), Distanza ad alta potenza metabolica "
            "HML >25.5 W/kg (m), Distanza anaerobica estrema VHML >50 W/kg (m) e Velocità di picco (km/h)."
        ),
        "a_cosa_serve": (
            "Mappa la mobilità orizzontale del tennista in campo, evidenziando il volume di corsa ad altissimo impegno energetico "
            "necessario per recuperare palle difensive o condurre attacchi in avanzamento."
        ),
        "azioni_consentite": [
            "Rilevazione automatica ambiente Indoor con blocco e avviso di non applicabilità",
            "Confronto metrico con la media storica dei match Outdoor",
            "Grafici a barre comparative",
            "Download Referto PDF"
        ],
        "bibliografia": [
            "di Prampero, P. E. et al. (2005). Sprint running: a new energetic approach. Journal of Experimental Biology, 208(14), 2809-2816.",
            "Osgnach, C. et al. (2010). Energy cost and metabolic power in elite soccer. MSSE, 42(1), 170-178."
        ]
    },
    {
        "nome": "2 Days Before the Match (Acute)",
        "nome_it": "Carico Acuto Pre-Gara (48 Ore Pre-Match)",
        "area": "Analisi Match",
        "icona": "bi-clock-history",
        "colore": "#0284c7",
        "cosa_analizza": (
            "Somma e analizza il carico di allenamento somministrato nelle 48 ore precedenti la partita (giorni T-1 e T-2)."
        ),
        "a_cosa_serve": (
            "Monitora il tapering pre-gara: serve a garantire che il giocatore arrivi all'incontro in condizioni di freschezza "
            "neuromuscolare e metabolica ottimale, prevenendo la discesa in campo in stato di fatica residua acuta."
        ),
        "azioni_consentite": [
            "Valutazione semaforica automatica (Scarico ottimale vs Carico eccessivo)",
            "Visualizzazione della cronologia dei 2 giorni precedenti",
            "Integrazione nel report match",
            "Stampa PDF"
        ],
        "bibliografia": [
            "Mujika, I. & Padilla, S. (2003). Scientific bases for precompetition tapering: a review. International Journal of Sports Medicine, 24(7), 541-550."
        ]
    },
    {
        "nome": "7 Days Before the Match (Chronic)",
        "nome_it": "Carico Cronico di Avvicinamento (7 Giorni Pre-Match)",
        "area": "Analisi Match",
        "icona": "bi-calendar7",
        "colore": "#0284c7",
        "cosa_analizza": (
            "Esamina il volume di Training Load accumulato nei 7 giorni antecedenti il match rispetto alla media storica mensile."
        ),
        "a_cosa_serve": (
            "Verifica la robustezza della base di allenamento settimanale: previene sia l'undertraining (rischio di cali di resistenza "
            "nei match lunghi) sia il sovraccarico progressivo cumulativo non assorbito."
        ),
        "azioni_consentite": [
            "Grafico a barre progressive dei 7 giorni precedenti il match",
            "Calcolo del carico medio giornaliero di preparazione",
            "Confronto con la media cronica",
            "Esportazione PDF"
        ],
        "bibliografia": [
            "Hulin, B. T. et al. (2014). The acute:chronic workload ratio predicts injury: high chronic-workload may decrease injury risk. BJSM, 50(4), 231-236."
        ]
    },
    {
        "nome": "Infografica Delta Match",
        "nome_it": "Cruscotto Esecutivo Delta Match M0V3",
        "area": "Analisi Match",
        "icona": "bi-card-checklist",
        "colore": "#0284c7",
        "cosa_analizza": (
            "Sintetizza in una schermata esecutiva ad alto impatto visivo tutti i principali indici del match, confrontandoli "
            "con il profilo medio dell'atleta e con il Gold Standard delle partite vinte."
        ),
        "a_cosa_serve": (
            "Fornisce al Direttore Tecnico e all'Head Coach un quadro riassuntivo immediato e leggibile in pochi secondi "
            "per condurre il debriefing post-gara con il giocatore o lo staff."
        ),
        "azioni_consentite": [
            "Card KPI dinamiche con frecce di direzione e variazioni percentuali",
            "Generazione codice formattato per invio rapido WhatsApp allo staff tecnico",
            "Stampa Referto PDF A4 Landscape ad alta risoluzione"
        ],
        "bibliografia": [
            "M0V3 Executive Match System Protocol."
        ]
    },

    # ---------------------------------------------------------------------
    # 2. ANALISI SESSIONE (9 Moduli)
    # ---------------------------------------------------------------------
    {
        "nome": "Distance from the averages (Session)",
        "nome_it": "Scostamento Specifico per Tipologia di Allenamento",
        "area": "Analisi Sessione",
        "icona": "bi-arrows-collapse",
        "colore": "#10b981",
        "cosa_analizza": (
            "Compara la sessione di allenamento con lo storico personale dell'atleta per quella esatta tipologia "
            "(es. Cesto, Tennis 1, Tennis 2, Doppio, Sparring, Atletico)."
        ),
        "a_cosa_serve": (
            "Controlla la fedeltà del carico programmato: evidenzia se una sessione concepita come tecnica o di scarico "
            "ha in realtà richiesto un dispendio fisico superiore alla norma dell'atleta per quella tipologia."
        ),
        "azioni_consentite": [
            "Filtro per Tipologia di Allenamento",
            "Selettore data e ora sessione",
            "Tabella analitica dei delta",
            "Esportazione PDF"
        ],
        "bibliografia": [
            "Foster, C. et al. (2001). A new approach to monitoring exercise training. Journal of Strength and Conditioning Research, 15(1), 109-115."
        ]
    },
    {
        "nome": "Training Load Bands",
        "nome_it": "Bande di Intensità della Singola Seduta",
        "area": "Analisi Sessione",
        "icona": "bi-bar-chart-steps",
        "colore": "#10b981",
        "cosa_analizza": (
            "Ripartizione del carico totale della sessione nelle 4 zone metaboliche (Stand, Low, Medium, High) in AU."
        ),
        "a_cosa_serve": (
            "Consente di verificare se l'obiettivo metabolico della seduta è stato raggiunto (es. prevalenza aerobica vs picchi lattacidi)."
        ),
        "azioni_consentite": [
            "Istogramma comparativo con la media della medesima tipologia",
            "Lettura valori numerici in AU",
            "Download PDF"
        ],
        "bibliografia": [
            "Impellizzeri, F. M. et al. (2004)."
        ]
    },
    {
        "nome": "Training Load Time% Bends",
        "nome_it": "Percentuale di Tempo nelle Bande di Sessione",
        "area": "Analisi Sessione",
        "icona": "bi-pie-chart-fill",
        "colore": "#10b981",
        "cosa_analizza": (
            "La quota percentuale del minutaggio di allenamento trascorsa in ciascun regime di intensità."
        ),
        "a_cosa_serve": (
            "Permette di tarare i tempi di recupero tra drill o cesti: se la percentuale High supera il 25-30%, l'allenamento "
            "assume un carattere prevalentemente anaerobico ad alta deplezione glicogenica."
        ),
        "azioni_consentite": [
            "Grafico a barre al 100% impilato",
            "Dettaglio dei minuti effettivi al mouseover",
            "Esportazione PDF"
        ],
        "bibliografia": [
            "Kovacs, M. S. (2007). Tennis physiology: training the competitive athlete. Sports Medicine, 37(3), 189-198."
        ]
    },
    {
        "nome": "Dati volumetrici IMU",
        "nome_it": "Metriche Biomeccaniche Inerziali di Seduta",
        "area": "Analisi Sessione",
        "icona": "bi-activity",
        "colore": "#10b981",
        "cosa_analizza": (
            "Volume, Player Load, Azioni >2\", Azioni >10\" e Recuperi 1-5m registrati durante l'allenamento."
        ),
        "a_cosa_serve": (
            "Misura l'impatto muscolo-tendineo degli esercizi, monitorando il numero di frenate e ripartenze eseguite dall'atleta."
        ),
        "azioni_consentite": [
            "Tabella comparativa con delta vs media di tipologia",
            "Grafico a barre",
            "Esportazione PDF"
        ],
        "bibliografia": [
            "Cormack, S. J. et al. (2013)."
        ]
    },
    {
        "nome": "Dati GPS",
        "nome_it": "Distanze e Cinematica Outdoor in Allenamento",
        "area": "Analisi Sessione",
        "icona": "bi-geo-alt-fill",
        "colore": "#10b981",
        "cosa_analizza": (
            "Distanza totale (m), HML >25.5 W/kg (m), VHML >50 W/kg (m) e velocità massima registrate durante le sedute all'aperto."
        ),
        "a_cosa_serve": (
            "Verifica se la mobilità e la velocità di esecuzione negli scatti corrispondono ai parametri target stabiliti dal preparatore."
        ),
        "azioni_consentite": [
            "Esclusione automatica sessioni indoor",
            "Grafico a barre metriche",
            "Export PDF"
        ],
        "bibliografia": [
            "di Prampero, P. E. et al. (2005)."
        ]
    },
    {
        "nome": "Aerobic Area - Session Comparison",
        "nome_it": "Profilo Area Aerobica (Stand + Low)",
        "area": "Analisi Sessione",
        "icona": "bi-heart-pulse-fill",
        "colore": "#10b981",
        "cosa_analizza": (
            "Quota di carico e tempo collocata nelle fasce Stand e Low (regime aerobico/estensivo) a confronto con i dati storici."
        ),
        "a_cosa_serve": (
            "Valuta la capacità di recupero dell'atleta e il volume di lavoro sostenibile senza accumulo precoce di acido lattico."
        ),
        "azioni_consentite": [
            "Grafico a barre comparative",
            "Visualizzazione della percentuale aerobica sul totale",
            "Esportazione PDF"
        ],
        "bibliografia": [
            "Banister, E. W. (1991). Modeling elite athletic performance. Physiological Testing of Elite Athletes, 403-424."
        ]
    },
    {
        "nome": "Anaerobic Area - Session Comparison",
        "nome_it": "Profilo Area Anaerobica (Medium + High)",
        "area": "Analisi Sessione",
        "icona": "bi-lightning-charge-fill",
        "colore": "#10b981",
        "cosa_analizza": (
            "Quota di carico e tempo collocata nelle fasce Medium e High (regime glicolitico e anaerobico alattacido/lattacido)."
        ),
        "a_cosa_serve": (
            "Controlla il dosaggio del lavoro ad alta intensità, essenziale per stimolare la rapidità senza indurre affaticamento centrale prolungato."
        ),
        "azioni_consentite": [
            "Grafico comparativo con soglia di allerta",
            "Ispezione dei minuti anaerobici",
            "Esportazione PDF"
        ],
        "bibliografia": [
            "Gastin, P. B. (2001). Energy system interaction and relative contribution during maximal exercise. Sports Medicine, 31(10), 725-741."
        ]
    },
    {
        "nome": "Before Tomorrow (Acute 2 Days)",
        "nome_it": "Effetto Acuto Residuo sulle 48 Ore Successive",
        "area": "Analisi Sessione",
        "icona": "bi-arrow-right-circle-fill",
        "colore": "#10b981",
        "cosa_analizza": (
            "L'impatto cumulativo delle ultime 48 ore rispetto al carico che si prevede di somministrare il giorno successivo."
        ),
        "a_cosa_serve": (
            "Supporta la pianificazione del giorno dopo: evita di inserire una seduta ad alta richiesta neuromuscolare dopo due giorni intensi."
        ),
        "azioni_consentite": [
            "Badge semaforico di idoneità al carico",
            "Raccomandazione sul timing di recupero",
            "Export PDF"
        ],
        "bibliografia": [
            "Mujika, I. (2010). Tapering and Peaking for Optimal Performance. Human Kinetics."
        ]
    },
    {
        "nome": "Before Tomorrow (Chronic 7 Days)",
        "nome_it": "Fondo Cronico dei 7 Giorni Precedenti la Seduta",
        "area": "Analisi Sessione",
        "icona": "bi-calendar-range-fill",
        "colore": "#10b981",
        "cosa_analizza": (
            "Il volume complessivo di lavoro registrato nei 7 giorni precedenti la seduta analizzata."
        ),
        "a_cosa_serve": (
            "Inquadra lo stato di affaticamento o freschezza dell'atleta nel contesto della settimana di allenamento in corso."
        ),
        "azioni_consentite": [
            "Grafico cronico a barre",
            "Calcolo del trend di carico",
            "Esportazione PDF"
        ],
        "bibliografia": [
            "Gabbett, T. J. (2016)."
        ]
    },

    # ---------------------------------------------------------------------
    # 3. TREND SETTIMANALE (7 Moduli)
    # ---------------------------------------------------------------------
    {
        "nome": "Andamento Settimanale (Tutte le Metriche)",
        "nome_it": "Microciclo Settimanale Multimetrica (Lun - Dom)",
        "area": "Trend Settimanale",
        "icona": "bi-calendar-week-fill",
        "colore": "#0ea5e9",
        "cosa_analizza": (
            "La distribuzione quotidiana dal lunedì alla domenica per Volume (Minuti, Training Load), Intensità (TL High, "
            "Accelerazioni e Decelerazioni Meccaniche IMU) e Cinematica GPS Outdoor."
        ),
        "a_cosa_serve": (
            "Verifica la corretta ondulazione del carico nel microciclo, assicurando che le giornate pesanti siano seguite "
            "da adeguate finestre di scarico attivo o riposo passivo."
        ),
        "azioni_consentite": [
            "Selettore settimana storica o in corso",
            "Navigazione per tab (Volumi, Intensità, GPS)",
            "Visualizzazione Totale 7gg, Media Attiva e Picco",
            "Esportazione PDF completa o per singola sottoarea"
        ],
        "bibliografia": [
            "Impellizzeri, F. M. et al. (2019). Internal and external training load: 15 years on. IJSPP, 14(2), 250-253."
        ]
    },
    {
        "nome": "Indici Compositi Settimanali (Volume & Work Rate)",
        "nome_it": "Curve Spline Normalizzate: Volume Index & Work Rate Index",
        "area": "Trend Settimanale",
        "icona": "bi-bezier2",
        "colore": "#0ea5e9",
        "cosa_analizza": (
            "Due indici sintetici proprietari M0V3 calcolati con interpolazione spline a gradiente di colore continuo: "
            "Volume Index (sintesi di durata, TL, azioni >2\" e cambi di direzione) e Work Rate Index (densità intensiva al minuto)."
        ),
        "a_cosa_serve": (
            "Fornisce un'immediata lettura visiva della qualità del lavoro giornaliero: distingue chiaramente le sedute di alto volume "
            "estensivo da quelle ad altissimo ritmo e densità esecutiva."
        ),
        "azioni_consentite": [
            "Grafico spline continuo a 5 colori (da verde brillante a rosso intenso)",
            "Punti discreti con valori da 0 a 10",
            "Banner informativi con scomposizione delle metriche",
            "Download PDF"
        ],
        "bibliografia": [
            "M0V3 Normalization & Composite Index Protocol."
        ]
    },
    {
        "nome": "ACWR Settimanale (Acuto/Cronico)",
        "nome_it": "Rapporto Acuto:Cronico Settimanale (Gabbett Protocol)",
        "area": "Trend Settimanale",
        "icona": "bi-speedometer2",
        "colore": "#0ea5e9",
        "cosa_analizza": (
            "Il rapporto tra il carico acuto dell'ultima settimana (7 giorni) e la media settimanale delle 4 settimane precedenti (28 giorni)."
        ),
        "a_cosa_serve": (
            "Identifica lo **Sweet Spot (0.80 - 1.30)** che riduce al minimo il rischio di infortunio massimizzando la prestazione, "
            "e segnala la **Danger Zone (> 1.50)** con un rischio infortuni moltiplicato da 2 a 4 volte."
        ),
        "azioni_consentite": [
            "Visualizzazione esagonale tachimetrica a colori con quadranti semaforici",
            "Dettaglio numerico del carico acuto e cronico",
            "Confronto percentuale di scostamento",
            "Esportazione PDF"
        ],
        "bibliografia": [
            "Gabbett, T. J. (2016). The training—injury prevention paradox: should athletes be training smarter and harder? BJSM, 50(5), 273-280."
        ]
    },
    {
        "nome": "Last 7 Days Load (Rolling)",
        "nome_it": "Carico Acuto su Finestra Mobile Continua (7 Giorni Rolling)",
        "area": "Trend Settimanale",
        "icona": "bi-arrow-repeat",
        "colore": "#0ea5e9",
        "cosa_analizza": (
            "Calcola il carico acuto sui 7 giorni immediatamente precedenti alla data scelta, confrontato con i 28 giorni precedenti a ritroso."
        ),
        "a_cosa_serve": (
            "Elimina i limiti della scansione rigida Lunedì-Domenica: il corpo umano accumula fatica in modo continuo e non si azzera "
            "alla domenica sera. Fondamentale per i tornei che iniziano a metà settimana."
        ),
        "azioni_consentite": [
            "Selettore data di riferimento",
            "Grafico ACWR Rolling dedicato",
            "Tabella dei 7 giorni mobili con dettaglio per sessione",
            "Esportazione PDF"
        ],
        "bibliografia": [
            "Windt, J. & Gabbett, T. J. (2017). How do training and competition workloads relate to injury? BJSM, 51(5), 428-435."
        ]
    },
    {
        "nome": "Current Week Load (ACWR Progressivo)",
        "nome_it": "Monitoraggio Progressivo del Microciclo in Corso",
        "area": "Trend Settimanale",
        "icona": "bi-hourglass-split",
        "colore": "#0ea5e9",
        "cosa_analizza": (
            "Traccia il carico cumulato dal lunedì fino al giorno corrente della settimana attiva, confrontandolo con la quota attesa."
        ),
        "a_cosa_serve": (
            "Consente una gestione proattiva del microciclo: permette al coach di ricalibrare gli allenamenti residui della settimana "
            "per rimanere nello Sweet Spot ed evitare il superamento delle soglie di allarme nel weekend."
        ),
        "azioni_consentite": [
            "Selettore del giorno di analisi (da Lunedì a Domenica)",
            "Strip orizzontale a tessere cromatiche per ogni giornata",
            "Calcolo predittivo del carico residuo",
            "Stampa PDF"
        ],
        "bibliografia": [
            "Blanch, P. & Gabbett, T. J. (2016). Has the athlete trained enough to return to play safely? BJSM, 50(8), 471-475."
        ]
    },
    {
        "nome": "Benchmark Giornaliero vs Medie",
        "nome_it": "Confronto Giornaliero vs Gold Standard Match & Tipologie",
        "area": "Trend Settimanale",
        "icona": "bi-table",
        "colore": "#0ea5e9",
        "cosa_analizza": (
            "Mette a confronto le sessioni svolte nei singoli giorni della settimana sia con le medie storiche della tipologia, "
            "sia con il **Gold Standard Match** (la prestazione media in partita ufficiale dell'atleta)."
        ),
        "a_cosa_serve": (
            "Permette di capire se gli allenamenti della settimana hanno raggiunto o superato l'intensità e la densità della gara reale, "
            "garantendo una preparazione specifica alle sollecitazioni del match."
        ),
        "azioni_consentite": [
            "Tabella sinottica completa con ripartizione per superfici (Terra, Cemento, Erba)",
            "Barre percentuali vs Match (100% Gold Standard)",
            "Istogramma a barre comparative con soglia match",
            "Esportazione PDF"
        ],
        "bibliografia": [
            "Martin, C. et al. (2014). Activity profile and physiological responses during tennis matches. Journal of Sports Sciences, 32(10), 972-981."
        ]
    },
    {
        "nome": "Referto Descrittivo Settimanale",
        "nome_it": "Referto Medico-Sportivo & Clinico del Microciclo",
        "area": "Trend Settimanale",
        "icona": "bi-file-earmark-medical-fill",
        "colore": "#0ea5e9",
        "cosa_analizza": (
            "Genera automaticamente un referto narrativo professionale suddiviso in tre sezioni cliniche: "
            "1. Volume (TL) & ACWR; 2. Intensità (TL High) & Gestione Neuromuscolare (spaziatura picchi <48h); "
            "3. Variabilità, Monotonia & Training Strain (Foster)."
        ),
        "a_cosa_serve": (
            "Traduce i dati numerici complessi in una valutazione descrittiva pronta all'uso per preparatori, medici e atleti, "
            "evidenziando i fattori di rischio infortuni e le linee guida per la settimana successiva."
        ),
        "azioni_consentite": [
            "Ribbon clinico con stato (Microciclo Concluso o In Corso)",
            "4 Card KPI orizzontali",
            "Box Referto narrativo ad alta leggibilità",
            "Pulsante con codice WhatsApp pre-formattato con grassetto ed emoji pronto per la copia con 1 click",
            "Generazione Referto Medico-Sportivo PDF A4 Landscape"
        ],
        "bibliografia": [
            "Foster, C. (1998). Monitoring training in athletes with reference to overtraining syndrome. MSSE, 30(7), 1164-1168.",
            "Gabbett, T. J. (2016)."
        ]
    },

    # ---------------------------------------------------------------------
    # 4. TREND STAGIONALE (8 Moduli)
    # ---------------------------------------------------------------------
    {
        "nome": "Andamento Ultime 8 Settimane",
        "nome_it": "Monitoraggio Bimesile del Carico di Lavoro",
        "area": "Trend Stagionale",
        "icona": "bi-graph-up",
        "colore": "#8b5cf6",
        "cosa_analizza": (
            "La successione dei carichi settimanali delle ultime 8 settimane consecutive, mostrando l'alternanza tra blocchi intensivi e scarichi."
        ),
        "a_cosa_serve": (
            "Consente di verificare la ciclicità del mesociclo e accertarsi che il tennista stia beneficiando della supercompensazione "
            "senza incorrere in affaticamento cumulativo non smaltito."
        ),
        "azioni_consentite": [
            "Selezione metrica di carico",
            "Grafico con trendline",
            "Esportazione PDF"
        ],
        "bibliografia": [
            "Bompa, T. O. & Buzzichelli, C. (2018). Periodization: Theory and Methodology of Training. Human Kinetics."
        ]
    },
    {
        "nome": "Carico Totale Mensile (12 Mesi)",
        "nome_it": "Distribuzione Volumetrica Annuale Mese per Mese",
        "area": "Trend Stagionale",
        "icona": "bi-bar-chart-fill",
        "colore": "#8b5cf6",
        "cosa_analizza": (
            "Il volume complessivo di lavoro accumulato in ciascun mese solare dell'anno (da gennaio a dicembre)."
        ),
        "a_cosa_serve": (
            "Individua i periodi di picco della stagione agonistica (tornei estivi, preparazione invernale) e quelli di rigenerazione."
        ),
        "azioni_consentite": [
            "Grafico a barre verticali con linea di media annuale",
            "Confronto tra mesi di carico e mesi di scarico",
            "Esportazione PDF"
        ],
        "bibliografia": [
            "Issurin, V. B. (2010). New horizons for the methodology and physiology of training periodization. Sports Medicine, 40(3), 189-206."
        ]
    },
    {
        "nome": "Timeline Settimanale Stagione",
        "nome_it": "Cronologia Completa dei Microcicli dell'Anno",
        "area": "Trend Stagionale",
        "icona": "bi-clock-history",
        "colore": "#8b5cf6",
        "cosa_analizza": (
            "Tutte le settimane della stagione visualizzate cronologicamente con istogrammi di volume e identificazione delle settimane di torneo."
        ),
        "a_cosa_serve": (
            "Fornisce una mappa a lungo termine dell'intera programmazione del tennista, utile per bilanciare le trasferte con i periodi di carico."
        ),
        "azioni_consentite": [
            "Filtro per anno solare",
            "Zoom interattivo",
            "Download PDF"
        ],
        "bibliografia": [
            "Issurin, V. B. (2010)."
        ]
    },
    {
        "nome": "ACWR Stagionale (Intera Stagione)",
        "nome_it": "Evoluzione Annuale Continua dell'Indice Gabbett",
        "area": "Trend Stagionale",
        "icona": "bi-speedometer2",
        "colore": "#8b5cf6",
        "cosa_analizza": (
            "La curva continua dell'Acute:Chronic Workload Ratio tracciata settimana per settimana lungo tutta la stagione."
        ),
        "a_cosa_serve": (
            "Individua retrospettivamente in quali fasi dell'anno l'atleta è entrato nella zona di pericolo (>1.50) o di undertraining (<0.80), "
            "perfezionando la pianificazione dell'anno successivo."
        ),
        "azioni_consentite": [
            "Grafico a linee con fasce colorate Sweet Spot e Danger Zone",
            "Tooltip con carichi acuti e cronici per ogni microciclo",
            "Esportazione PDF"
        ],
        "bibliografia": [
            "Gabbett, T. J. (2016)."
        ]
    },
    {
        "nome": "ACWR Ultime 8 Settimane",
        "nome_it": "Dinamica del Rischio Infortuni su Finestra Bimesile",
        "area": "Trend Stagionale",
        "icona": "bi-activity",
        "colore": "#8b5cf6",
        "cosa_analizza": (
            "Il dettaglio ravvicinato dell'ACWR nelle 8 settimane precedenti rispetto alla settimana di riferimento."
        ),
        "a_cosa_serve": (
            "Fornisce un'indicazione precisa per le decisioni di carico a breve e medio termine in prossimità di competizioni chiave."
        ),
        "azioni_consentite": [
            "Grafico spline con zone di rischio",
            "Indicatori di allerta",
            "Download PDF"
        ],
        "bibliografia": [
            "Gabbett, T. J. (2016)."
        ]
    },
    {
        "nome": "Distribuzione Lavoro",
        "nome_it": "Ripartizione per Superfici e Tipologie di Sessione",
        "area": "Trend Stagionale",
        "icona": "bi-pie-chart",
        "colore": "#8b5cf6",
        "cosa_analizza": (
            "La ripartizione percentuale del tempo di gioco su Terra battuta, Cemento, Erba e altre superfici, e tra le varie sessioni."
        ),
        "a_cosa_serve": (
            "Monitora la transizione biomeccanica tra superfici diverse, momento critico in cui si registra la maggiore incidenza "
            "di infortuni muscolo-tendinei nel circuito tennistico."
        ),
        "azioni_consentite": [
            "Grafici a torta e stacked bars per superficie e sessione",
            "Filtro per anno",
            "Esportazione PDF"
        ],
        "bibliografia": [
            "Girard, O. et al. (2007). Specificities of tennis playing on clay surfaces. Sports Medicine, 37(11), 921-930."
        ]
    },
    {
        "nome": "Monotonia Stagionale",
        "nome_it": "Indice di Monotonia di Foster (Uniformità del Carico)",
        "area": "Trend Stagionale",
        "icona": "bi-soundwave",
        "colore": "#8b5cf6",
        "cosa_analizza": (
            "L'Indice di Monotonia di Foster (Media giornaliera / Deviazione Standard del carico giornaliero) per ogni settimana della stagione."
        ),
        "a_cosa_serve": (
            "Valuta la variabilità quotidiana dello stimolo. Valori superiori a 2.0 per più settimane consecutive indicano un carico "
            "piatto e monotono, uno dei precursori primari della sindrome da sovrallenamento (overtraining syndrome)."
        ),
        "azioni_consentite": [
            "Grafico temporale con soglia di allerta a 2.0",
            "Tooltip con deviazione standard giornaliera",
            "Esportazione PDF"
        ],
        "bibliografia": [
            "Foster, C. (1998). Monitoring training in athletes with reference to overtraining syndrome. MSSE, 30(7), 1164-1168."
        ]
    },
    {
        "nome": "Strain Stagionale",
        "nome_it": "Training Strain di Foster (Stress Moltiplicativo)",
        "area": "Trend Stagionale",
        "icona": "bi-fire",
        "colore": "#8b5cf6",
        "cosa_analizza": (
            "L'indice di Training Strain (Carico Settimanale Totale × Monotonia) tracciato lungo tutto l'arco dell'anno."
        ),
        "a_cosa_serve": (
            "Misura l'effetto moltiplicativo dello stress biologico: un volume alto unito a una monotonia elevata provoca picchi di strain "
            "acuti che deprimono le difese immunitarie e aumentano drasticamente la vulnerabilità a contratture e lesioni."
        ),
        "azioni_consentite": [
            "Grafico spline con baseline e soglia di allarme (+50%)",
            "Evidenziazione dei picchi acuti stagionali",
            "Esportazione PDF"
        ],
        "bibliografia": [
            "Foster, C. (1998).",
            "Putlur, P. et al. (2004). Alteration of immune function in women with high training strain. MSSE, 36(11), 1842-1848."
        ]
    },

    # ---------------------------------------------------------------------
    # 5. STORICO MATCH (6 Moduli)
    # ---------------------------------------------------------------------
    {
        "nome": "Volume Match Timeline",
        "nome_it": "Evoluzione Storica dei Volumi di Gara",
        "area": "Storico Match",
        "icona": "bi-clock",
        "colore": "#f59e0b",
        "cosa_analizza": (
            "La cronologia completa della durata (min) e del Training Load di tutte le partite registrate nel database del giocatore."
        ),
        "a_cosa_serve": (
            "Mappa la capacità di tenuta nei match prolungati, evidenziando se l'atleta incrementa o riduce i volumi di gioco nel corso della carriera."
        ),
        "azioni_consentite": [
            "Filtro temporale e per superficie",
            "Trendline di regressione",
            "Esportazione PDF"
        ],
        "bibliografia": [
            "Fernandez-Fernandez, J. et al. (2009)."
        ]
    },
    {
        "nome": "Intensità Match Timeline",
        "nome_it": "Evoluzione Storica dell'Alta Intensità in Partita",
        "area": "Storico Match",
        "icona": "bi-lightning",
        "colore": "#f59e0b",
        "cosa_analizza": (
            "L'andamento diacronico di TL High e dei cambi di direzione (Azioni >2\") registrati nei singoli match ufficiali."
        ),
        "a_cosa_serve": (
            "Verifica la conservazione della brillantezza esplosiva e della velocità di piedi nelle partite disputate a distanza di mesi o anni."
        ),
        "azioni_consentite": [
            "Grafico combinato barre/linee",
            "Confronto tra match vinti e persi",
            "Esportazione PDF"
        ],
        "bibliografia": [
            "Reid, M. et al. (2016)."
        ]
    },
    {
        "nome": "Work Rate Timeline",
        "nome_it": "Densità Oraria Storica della Prestazione (TL/min)",
        "area": "Storico Match",
        "icona": "bi-speedometer",
        "colore": "#f59e0b",
        "cosa_analizza": (
            "La densità oraria della fatica: Training Load al minuto e TL High al minuto nel corso di tutti i match disputati."
        ),
        "a_cosa_serve": (
            "Misura il ritmo reale della competizione: due partite di pari durata possono richiedere impegni cardiocircolatori radicalmente "
            "diversi a seconda del ritmo imposto dallo scambio e dal tipo di avversario."
        ),
        "azioni_consentite": [
            "Grafico temporale di densità",
            "Tooltip con valori orari",
            "Download PDF"
        ],
        "bibliografia": [
            "Martin, C. et al. (2014)."
        ]
    },
    {
        "nome": "GPS Data Timeline",
        "nome_it": "Distanze e Cinematica Storica nei Match Outdoor",
        "area": "Storico Match",
        "icona": "bi-geo-alt",
        "colore": "#f59e0b",
        "cosa_analizza": (
            "La serie storica delle distanze totali percorse e delle distanze ad alta potenza metabolica (HML e VHML) nei match all'aperto."
        ),
        "a_cosa_serve": (
            "Analizza l'evoluzione dell'efficienza di spostamento e della gittata chilometrica in funzione della superficie di gara."
        ),
        "azioni_consentite": [
            "Filtro per superficie (Terra vs Cemento)",
            "Grafico metrico chilometrico",
            "Esportazione PDF"
        ],
        "bibliografia": [
            "Osgnach, C. et al. (2010)."
        ]
    },
    {
        "nome": "Indici Compositi (Volume & Work Rate)",
        "nome_it": "Classificazione a Quadranti dei Match Disputati",
        "area": "Storico Match",
        "icona": "bi-grid-3x3-gap",
        "colore": "#f59e0b",
        "cosa_analizza": (
            "L'applicazione congiunta del Volume Index e del Work Rate Index M0V3 a tutte le partite disputate dall'atleta."
        ),
        "a_cosa_serve": (
            "Classifica le partite in quattro quadranti tattico-fisici: Alto Volume/Alto Ritmo (maratone veloci), "
            "Alto Volume/Basso Ritmo (scambi lenti), Basso Volume/Alto Ritmo (match rapidi e intensi), Basso Volume/Basso Ritmo."
        ),
        "azioni_consentite": [
            "Grafico a dispersione (Scatter Plot) a 4 quadranti",
            "Tooltip con nome avversario e data",
            "Stampa PDF"
        ],
        "bibliografia": [
            "M0V3 Match Classification Matrix Protocol."
        ]
    },
    {
        "nome": "Record Storici Match",
        "nome_it": "Hall of Fame & Massimali Assoluti (Worst Case Scenario)",
        "area": "Storico Match",
        "icona": "bi-trophy-fill",
        "colore": "#f59e0b",
        "cosa_analizza": (
            "I primati storici registrati dall'atleta in carriera: Match più lungo, Massimo Training Load, Picco di velocità, "
            "Record assoluto di accelerazioni e decelerazioni, Massimo numero di azioni intense."
        ),
        "a_cosa_serve": (
            "Definisce il soffitto prestativo (**Worst Case Scenario**) dell'atleta, parametro fondamentale per programmare "
            "sedute di allenamento capaci di preparare il corpo ai picchi massimi registrabili in competizione."
        ),
        "azioni_consentite": [
            "Card dei primati personali con data, risultato e avversario",
            "Tabella sinottica dei record",
            "Esportazione PDF"
        ],
        "bibliografia": [
            "Gabbett, T. J. et al. (2016). The Worst Case Scenario in competitive sport. IJSPP, 11(6), 720-725."
        ]
    },

    # ---------------------------------------------------------------------
    # 6. MEDIE & CONFRONTI (7 Moduli)
    # ---------------------------------------------------------------------
    {
        "nome": "Analisi Singolo Atleta",
        "nome_it": "Profilo Medie Assolute per Tipologia di Allenamento",
        "area": "Medie",
        "icona": "bi-person-badge",
        "colore": "#0284c7",
        "cosa_analizza": (
            "Le medie storiche consolidate di tutti i parametri fisici, inerziali e metabolici calcolate per ciascuna tipologia "
            "di sessione svolta (Cesto, Sparring, Partita, Tennis 1, Tennis 2, Atletico)."
        ),
        "a_cosa_serve": (
            "Costruisce la carta d'identità motoria del tennista, definendo il carico medio atteso per ogni tipologia di allenamento."
        ),
        "azioni_consentite": [
            "Selettore atleta",
            "Tabella benchmark con conteggio sessioni reali",
            "Generazione Report PDF Profilo Medie Completo"
        ],
        "bibliografia": [
            "Foster, C. et al. (2001)."
        ]
    },
    {
        "nome": "Testa a Testa Medie",
        "nome_it": "Head to Head su Medie Storiche (Base 100%)",
        "area": "Medie",
        "icona": "bi-people-fill",
        "colore": "#0284c7",
        "cosa_analizza": (
            "Il confronto diretto parametro per parametro tra due atleti del roster sulle medie storiche di una specifica tipologia di sessione "
            "(es. Match o Cesto), ponendo l'Atleta 2 al 100% come benchmark di riferimento."
        ),
        "a_cosa_serve": (
            "Evidenzia i gap volumetrici, metabolici e di reattività tra due giocatori, consentendo di tarare i carichi di allenamento "
            "rispetto al giocatore di vertice o al compagno di pari livello, identificando chi esprime più potenza metabolica e volume a parità di esercizio."
        ),
        "azioni_consentite": [
            "Selettore Atleta 1 (analizzato) e Atleta 2 (riferimento 100%)",
            "Selettore Tipologia di sessione",
            "Grafico polare esagonale a radar",
            "Card con indici sintetici di scostamento (Volume, Intensità, Work Rate)",
            "Tabella analitica con delta percentuale per ciascuna metrica",
            "Generazione Report PDF Testa a Testa Medie"
        ],
        "bibliografia": [
            "M0V3 Head to Head Comparative Protocol."
        ]
    },
    {
        "nome": "Testa a Testa Settimana",
        "nome_it": "Head to Head Settimanale del Carico Cumulato",
        "area": "Medie",
        "icona": "bi-calendar2-range-fill",
        "colore": "#0284c7",
        "cosa_analizza": (
            "Il confronto diretto della somma dei carichi settimanali (Lunedì - Domenica) tra due atleti nella medesima settimana."
        ),
        "a_cosa_serve": (
            "Mette a confronto il carico complessivo realmente svolto in un determinato microciclo da due compagni di squadra, "
            "evidenziando discrepanze di volume o intensità nella settimana."
        ),
        "azioni_consentite": [
            "Selettore Settimana (navigabile tra corrente e passate)",
            "Selettore Tipologia di sessione (o Tutte)",
            "Tabella con delta e barre percentuali (100% Atleta 2)",
            "Grafico polare esagonale a radar del microciclo",
            "Generazione Report PDF Testa a Testa Settimana"
        ],
        "bibliografia": [
            "M0V3 Weekly Head to Head Protocol."
        ]
    },
    {
        "nome": "Ranking Roster Atleti",
        "nome_it": "Graduatoria Roster per Volume, Intensità e Podio",
        "area": "Medie",
        "icona": "bi-trophy",
        "colore": "#0284c7",
        "cosa_analizza": (
            "La classifica indipendente dell'intero roster dell'utente loggato su scala Settimanale e Stagionale (anno solare) "
            "per tre pilastri: Training Load (Volume), TL High (Intensità) e Accelerazioni + Decelerazioni (Meccanica). "
            "Include il **Podio Roster Best** (Week Best vs Season Best) calcolato su indici compositi normalizzati."
        ),
        "a_cosa_serve": (
            "Stimola l'emulazione e la motivazione nel team, permettendo al Direttore Tecnico di monitorare chi all'interno del roster "
            "sta sostenendo i carichi più elevati sia nel volume che nell'alta intensità neuromuscolare."
        ),
        "azioni_consentite": [
            "Selettore Stagione (Anno Solare)",
            "Selettore Settimana",
            "Tabella Ranking Settimanale e Tabella Ranking Stagionale con medaglie",
            "Box descrittivo con formule di calcolo esplicite",
            "Podio Roster Best Week vs Season",
            "Generazione Report PDF Ranking Roster Atleti"
        ],
        "bibliografia": [
            "M0V3 Roster Ranking & Normalization Matrix Protocol."
        ]
    },
    {
        "nome": "Distribuzione Lavoro Roster",
        "nome_it": "Ripartizione % del Tempo sulle Tipologie Condivise",
        "area": "Medie",
        "icona": "bi-pie-chart-steps",
        "colore": "#0284c7",
        "cosa_analizza": (
            "La quota percentuale del tempo di allenamento dedicata alle sole tipologie di sessione condivise da tutti gli atleti "
            "del roster (o registrate per il team), analizzata su scala settimanale e stagionale."
        ),
        "a_cosa_serve": (
            "Verifica l'omogeneità metodologica del programma di allenamento del team: evidenzia se determinati atleti "
            "stanno trascurando il lavoro su specifiche tipologie a vantaggio di altre rispetto al gruppo."
        ),
        "azioni_consentite": [
            "Filtro Stagione e Settimana",
            "Tabella percentuale settimanale e stagionale con minuti totali",
            "Grafico a barre sovrapposte al 100% (100% Stacked Bar) con toggle periodo (Stagionale vs Settimanale)",
            "Generazione Report PDF Distribuzione Lavoro Roster"
        ],
        "bibliografia": [
            "M0V3 Workload Distribution Protocol."
        ]
    },
    {
        "nome": "Stress Roster 8 settimane",
        "nome_it": "Longitudinale 8W: ACWR, Monotonia e Strain Individuale",
        "area": "Medie",
        "icona": "bi-activity",
        "colore": "#0284c7",
        "cosa_analizza": (
            "Il monitoraggio longitudinale dell'intero roster nelle 8 settimane precedenti rispetto alla settimana di riferimento per "
            "tre grandezze chiave: **ACWR (Gabbett)**, **Monotonia (Foster)** e **Training Strain (Foster)**, con possibilità di "
            "alternare la base di calcolo tra Volume (TL) e Intensità (TL High)."
        ),
        "a_cosa_serve": (
            "Fornisce al preparatore e al medico la visione sinottica dell'affaticamento cumulativo di tutta la squadra. "
            "Per lo Strain, la soglia di allarme (+50%) è calcolata **in modo rigorosamente individuale** per ogni atleta, "
            "evitando false allerte dovute a medie di squadra fuorvianti."
        ),
        "azioni_consentite": [
            "Selettore Settimana di riferimento",
            "Radio button metrica: ACWR, Monotonia Foster, Training Strain",
            "Radio button base di carico: Volume (TL) vs Intensità (TL High)",
            "Selettore per visualizzare la soglia individuale (+50% allarme) dell'atleta scelto sul grafico Plotly",
            "Grafico spline interattivo con tooltip individualizzati per ogni curva",
            "Matrice comparativa 8 settimane con sparklines SVG vettoriali e trend direzionali (↗, ↘, →)",
            "Generazione Report PDF dinamico conforme a quanto visualizzato a video"
        ],
        "bibliografia": [
            "Gabbett, T. J. (2016). The training—injury prevention paradox: should athletes be training smarter and harder? BJSM, 50(5), 273-280.",
            "Foster, C. (1998). Monitoring training in athletes with reference to overtraining syndrome. MSSE, 30(7), 1164-1168.",
            "Impellizzeri, F. M. et al. (2019). Internal and external training load: 15 years on. IJSPP, 14(2), 250-253."
        ]
    },

    # ---------------------------------------------------------------------
    # 7. STATISTICHE MATCH (7 Moduli)
    # ---------------------------------------------------------------------
    {
        "nome": "Evoluzione Metri per Punto & Costo Vivo (TL High / pt)",
        "nome_it": "Evoluzione Metri per Punto & Costo Vivo (TL High / pt)",
        "area": "Statistiche Match",
        "icona": "bi-speedometer2",
        "colore": "#6366f1",
        "cosa_analizza": (
            "Calcola la quota chilometrica e il dispendio energetico ad alta intensità (Training Load High) normalizzati per ogni singolo punto giocato."
        ),
        "a_cosa_serve": (
            "Quantifica l'efficienza cinetica ed energetica del tennista punto per punto, evidenziando se la tattica adottata comporta uno spreco di metri o se il giocatore chiude i punti con ridotto costo vivo."
        ),
        "azioni_consentite": [
            "Filtro Match e Atleta",
            "Grafico comparativo punto per punto",
            "Benchmark vs media storica di categoria",
            "Esportazione Report PDF"
        ],
        "bibliografia": [
            "Reid, M. et al. (2016). Tracking devices in tennis: application to training and competition. IJSPP, 11(5), 675-680.",
            "Kovacs, M. S. (2007). Tennis physiology: training the competitive athlete. Sports Medicine, 37(3), 189-198."
        ]
    },
    {
        "nome": "Densità Scambi & Azioni Int. IMU >2\" (ogni 10 pt)",
        "nome_it": "Densità Meccanica degli Scambi (Azioni >2\" ogni 10 Punti)",
        "area": "Statistiche Match",
        "icona": "bi-lightning-charge",
        "colore": "#6366f1",
        "cosa_analizza": (
            "Misura la frequenza di eventi inerziali triassiali ad alta intensità (scatti, cambi di direzione >2 secondi) calcolata su blocchi di 10 punti giocati."
        ),
        "a_cosa_serve": (
            "Identifica i momenti di massima densità neuromuscolare della gara e la capacità dell'atleta di sostenere ripetute sollecitazioni eccentriche sotto fatica cumulativa."
        ),
        "azioni_consentite": [
            "Visualizzazione timeline a blocchi di punti",
            "Ispezione soglie inerziali >2s e >3s",
            "Confronto set per set"
        ],
        "bibliografia": [
            "Boyd, L. J. et al. (2011). Accelerometer-based player load in elite sports. IJSPP, 6(3), 311-326."
        ]
    },
    {
        "nome": "Scorporo Servizio vs Risposta (Densità & Impatto Eccentrico)",
        "nome_it": "Scorporo Tattico: Turni di Servizio vs Turni di Risposta",
        "area": "Statistiche Match",
        "icona": "bi-arrow-left-right",
        "colore": "#6366f1",
        "cosa_analizza": (
            "Disaccoppia il volume di corsa, il carico metabolico High e le frenate eccentriche registrate nei game al servizio rispetto a quelli in risposta."
        ),
        "a_cosa_serve": (
            "Identifica in quale fase di gioco si concentra il maggior logorio articolare, orientando la gestione tattica e la programmazione del recupero post-gara."
        ),
        "azioni_consentite": [
            "Confronto affiancato Servizio vs Risposta",
            "Metriche di frenata eccentrica e accelerazione",
            "Esportazione Referto comparativo"
        ],
        "bibliografia": [
            "Fernandez-Fernandez, J. et al. (2009). Physiological demands of tennis. Sports Medicine, 39(8), 603-626."
        ]
    },
    {
        "nome": "Benchmark Prestativo: Vittorie vs Sconfitte",
        "nome_it": "Profilo Fisico Comparativo: Match Vinti vs Match Persi",
        "area": "Statistiche Match",
        "icona": "bi-award-fill",
        "colore": "#6366f1",
        "cosa_analizza": (
            "Confronta i parametri cinematici, volumetrici e di intensità registrati negli incontri vinti rispetto a quelli persi sulla medesima superficie o periodo."
        ),
        "a_cosa_serve": (
            "Definisce i requisiti fisici minimi (work rate, metri/minuto, volume High) associati al successo competitivo per lo specifico atleta."
        ),
        "azioni_consentite": [
            "Filtro Superficie (Terra, Cemento, Erba)",
            "Radar comparativo Vittorie vs Sconfitte",
            "Calcolo scostamento percentuale statistico"
        ],
        "bibliografia": [
            "Hornery, D. J. et al. (2007). Movement patterns and physiological demands in elite tennis. Sports Medicine, 37(6), 475-498."
        ]
    },
    {
        "nome": "Correlazione Metri/Punto vs Rendimento Tecnico",
        "nome_it": "Correlazione Metri/Punto vs Rendimento Tecnico",
        "area": "Statistiche Match",
        "icona": "bi-graph-up",
        "colore": "#6366f1",
        "cosa_analizza": (
            "Incrocia la mobilità orizzontale al metro con i dati tecnici ufficiali di match (percentuale prime palle, punti vinti alla risposta, errori gratuiti)."
        ),
        "a_cosa_serve": (
            "Valuta se un elevato impegno chilometrico sia effettivamente produttivo o se indichi una posizione arretrata e difensiva che disperde energie."
        ),
        "azioni_consentite": [
            "Scatter plot con retta di regressione",
            "Coefficiente di correlazione Pearson/Spearman",
            "Filtro per categoria di avversario"
        ],
        "bibliografia": [
            "Reid, M. et al. (2016). Tracking devices in tennis. IJSPP."
        ]
    },
    {
        "nome": "Impatto dell'Efficienza al Servizio sul Costo Fisico",
        "nome_it": "Efficienza al Servizio e Risparmio di Carico Meccanico",
        "area": "Statistiche Match",
        "icona": "bi-shield-shaded",
        "colore": "#6366f1",
        "cosa_analizza": (
            "Quantifica la riduzione di Training Load, metri percorsi ed eventi inerziali favorita da elevate percentuali di punti rapidi (ace, punti diretti su prima palla)."
        ),
        "a_cosa_serve": (
            "Dimostra allo staff l'effetto protettivo di un servizio incisivo sulla conservazione delle energie muscolari durante tornei plurisettimanali."
        ),
        "azioni_consentite": [
            "Analisi multivariata servizio/carico",
            "Simulazione scenari di efficienza",
            "Esportazione grafico"
        ],
        "bibliografia": [
            "Kovacs, M. S. et al. (2014). Elite tennis serve biomechanics and conditioning. BJSM, 48(Suppl 1), i43-i48."
        ]
    },
    {
        "nome": "Archivio Match Ufficiali & Abbinamento Telemetria GPS",
        "nome_it": "Archivio Gare & Sincronizzazione Telemetria GPS",
        "area": "Statistiche Match",
        "icona": "bi-archive",
        "colore": "#6366f1",
        "cosa_analizza": (
            "Registro storico cronologico dei match ufficiali con integrazione e verifica dell'avvenuto abbinamento con i file GPS/IMU."
        ),
        "a_cosa_serve": (
            "Fornisce un'anagrafica centralizzata delle competizioni, assicurando che nessuna prestazione ufficiale rimanga priva di dati telemetrici correlati."
        ),
        "azioni_consentite": [
            "Ricerca per data, torneo, avversario",
            "Abbinamento rapido sessione GPS a match",
            "Verifica stato sincronizzazione telemetria"
        ],
        "bibliografia": [
            "M0V3 Enterprise Telemetry Synchronization Engine."
        ]
    },

    # ---------------------------------------------------------------------
    # 8. ANALISI WELLNESS-RPE-GPS (3 Moduli)
    # ---------------------------------------------------------------------
    {
        "nome": "Incrocio GPS vs sRPE",
        "nome_it": "Decoupling Ratio: Carico Esterno GPS vs Carico Interno sRPE",
        "area": "Analisi Wellness-RPE-GPS",
        "icona": "bi-heart-pulse-fill",
        "colore": "#ec4899",
        "cosa_analizza": (
            "Confronta il carico meccanico esterno oggettivo (Training Load, Player Load, Distanza GPS) con il carico biologico interno soggettivo (sRPE Foster = RPE CR-10 x Durata min) e calcola l'Indice di Efficienza e il disaccoppiamento biologico (Decoupling I:E Ratio)."
        ),
        "a_cosa_serve": (
            "Rappresenta il gold standard per rilevare tempestivamente stati di sovrallenamento o fatica non funzionale: un aumento del carico interno percepito a parità di output GPS evidenzia che l'atleta richiede un dispendio biologico eccessivo per mantenere le prestazioni, richiedendo scarico precauzionale."
        ),
        "azioni_consentite": [
            "Filtro finestra temporale (7, 14, 28, 60 giorni o tutto lo storico)",
            "Scelta metrica GPS (Indice di Volume, Intensità, TL, Distanza)",
            "Overlay trend Wellness mattutino totale",
            "Esportazione Dossier Clinico-Atletico PDF"
        ],
        "bibliografia": [
            "Foster, C. et al. (2001). A new approach to monitoring exercise training. JSCR, 15(1), 109-115.",
            "Impellizzeri, F. M. et al. (2019). Internal and external training load: 15 years on. IJSPP, 14(2), 250-253.",
            "Halson, S. L. (2014). Monitoring training load to understand fatigue in athletes. Sports Medicine, 44(Suppl 2), S139-S147."
        ]
    },
    {
        "nome": "Trend Risposta Biologica (Wellness)",
        "nome_it": "Monitoraggio Profilo Wellness Mattutino (Protocollo Hooper-Mackinnon)",
        "area": "Analisi Wellness-RPE-GPS",
        "icona": "bi-emoji-smile",
        "colore": "#ec4899",
        "cosa_analizza": (
            "Monitora longitudinalmente i 5 domini neuro-fisiologici del benessere quotidiano raccolti al risveglio: Qualità del Sonno, Fatica Generale, Indolenzimento Muscolare (DOMS), Livello di Stress e Umore Generale (scala validata 1-5 / 1-10)."
        ),
        "a_cosa_serve": (
            "Fornisce una diagnosi preventiva dello stato di prontezza (Readiness) e di recupero prima dell'inizio delle sedute. Un calo marcato dello score o picchi di indolenzimento muscolare consentono di riprogrammare i volumi giornalieri prima della comparsa di lesioni."
        ),
        "azioni_consentite": [
            "Visualizzazione radar a 5 domini",
            "Grafico spline temporale con trendline",
            "Evidenziazione giorni critici con allerta sonno/DOMS",
            "Confronto con media personale stagionale"
        ],
        "bibliografia": [
            "Hooper, S. L. & Mackinnon, L. T. (1995). Monitoring overtraining in athletes. Sports Medicine, 20(5), 321-327.",
            "Meeusen, R. et al. (2013). Prevention, diagnosis, and treatment of the overtraining syndrome. MSSE, 45(1), 186-205."
        ]
    },
    {
        "nome": "Analisi Incrociata",
        "nome_it": "Analisi Incrociata: Carichi Fisici vs Eventi Clinico-Sanitari",
        "area": "Analisi Wellness-RPE-GPS",
        "icona": "bi-clipboard2-pulse",
        "colore": "#ec4899",
        "cosa_analizza": (
            "Sovrappone in una timeline unificata il volume di lavoro fisico (GPS & sRPE) con l'insorgenza di eventi clinici registrati dallo staff medico (infortuni muscolari, tendinopatie, trattamenti fisioterapici, farmaci, stop precauzionali)."
        ),
        "a_cosa_serve": (
            "Permette a preparatori e medici di verificare con evidenze oggettive se determinati picchi di carico (spikes acuti o carichi cronici anomali) abbiano preceduto l'evento lesivo, calibrando le soglie di tolleranza individuali."
        ),
        "azioni_consentite": [
            "Timeline interattiva con marcatori evento clinico",
            "Filtro per distretto anatomico",
            "Correlazione temporale spike acuto vs data evento",
            "Esportazione Report Incrociato PDF"
        ],
        "bibliografia": [
            "Gabbett, T. J. (2016). The training—injury prevention paradox: should athletes be training smarter and harder? BJSM, 50(5), 273-280.",
            "Windt, J. & Gabbett, T. J. (2017). How do training and competition workloads relate to injury? BJSM, 51(5), 428-435."
        ]
    },

    # ---------------------------------------------------------------------
    # 9. MEDICO & EXTRA TENNIS (2 Moduli)
    # ---------------------------------------------------------------------
    {
        "nome": "Inserimento & Gestione Registro",
        "nome_it": "Cartella Clinica, Registro Sanitario & Trattamenti Fisioterapici",
        "area": "Medico & Extra Tennis",
        "icona": "bi-hospital",
        "colore": "#14b8a6",
        "cosa_analizza": (
            "Gestisce l'archivio clinico e fisioterapico completo: tipologia evento (Infortunio, Valutazione, Trattamento Fisioterapico, Prescrizione Farmacologica), distretto anatomico, diagnosi specialistica, farmaci somministrati e note di decorso."
        ),
        "a_cosa_serve": (
            "Garantisce continuità terapeutica e tracciabilità sanitaria GDPR-compliant. Consente allo staff medico di registrare trattamenti sul campo e duplicare protocolli per sedute continuative con un click."
        ),
        "azioni_consentite": [
            "Inserimento rapido nuovo evento o trattamento",
            "Duplicazione guidata trattamento a date successive",
            "Filtro storico per atleta e distretto anatomico",
            "Eliminazione o modifica schede con tracciamento audit"
        ],
        "bibliografia": [
            "Fuller, C. W. et al. (2006). Consensus statement on injury definitions in sport. BJSM, 40(3), 193-201.",
            "Pluim, B. M. et al. (2009). Tennis injuries: occurrence, aetiology, and prevention. BJSM, 40(5), 415-423."
        ]
    },
    {
        "nome": "Allenamenti GYM e Fisico",
        "nome_it": "Registro Sessioni Extra-Tennis (GYM, Palestra & Carichi Gymaware VBT)",
        "area": "Medico & Extra Tennis",
        "icona": "bi-bicycle",
        "colore": "#14b8a6",
        "cosa_analizza": (
            "Registra tutte le sedute atletiche extra-campo (forza massimale, potenza con encoder Velocity-Based Training Gymaware, sedute di mobilità, lavoro cardiovascolare a secco o bicicletta)."
        ),
        "a_cosa_serve": (
            "Impedisce il sottodimensionamento del carico complessivo: quantifica la fatica neuromuscolare e lo stress articolare generato dal lavoro a secco e in palestra, integrandolo nel bilancio sRPE complessivo."
        ),
        "azioni_consentite": [
            "Inserimento data, tipologia seduta, durata, sRPE e RPE sessione",
            "Audit e consultazione dello storico sedute extra-tennis",
            "Integrazione automatica nel database sRPE dell'atleta"
        ],
        "bibliografia": [
            "Suchomel, T. J. et al. (2016). The importance of muscular strength in athletic performance. Sports Medicine, 46(10), 1419-1449.",
            "Weakley, J. et al. (2021). Velocity-based training: From theory to application. Strength & Conditioning Journal, 43(2), 31-49."
        ]
    },

    # ---------------------------------------------------------------------
    # 10. TEST FISICI & NEUROMUSCOLARI (6 Moduli)
    # ---------------------------------------------------------------------
    {
        "nome": "Panoramica Test Atleta",
        "nome_it": "Profilo Funzionale & Batteria Valutativa Atleta",
        "area": "Test Fisici & Neuromuscolari",
        "icona": "bi-person-lines-fill",
        "colore": "#f97316",
        "cosa_analizza": (
            "Quadro sinottico delle valutazioni neuromuscolari, articolari e aerobiche sostenute dall'atleta nelle sessioni di testing (CMJ, Squat Jump, Mobilità, Sprint 5-10-20m, Navetta)."
        ),
        "a_cosa_serve": (
            "Fornisce una fotografia istantanea dei punti di forza e delle carenze condizionali del tennista rispetto ai requisiti biomeccanici del tennis di vertice."
        ),
        "azioni_consentite": [
            "Selettore atleta",
            "Visualizzazione a card interattive per categoria di test",
            "Radar neuromuscolare complessivo"
        ],
        "bibliografia": [
            "Girard, O. & Millet, G. P. (2009). Neuromuscular fatigue in racquet sports. Physical Medicine and Rehabilitation Clinics, 20(1), 161-178."
        ]
    },
    {
        "nome": "Deep-Dive per Test",
        "nome_it": "Analisi Dettagliata & Evoluzione Storica della Singola Prova",
        "area": "Test Fisici & Neuromuscolari",
        "icona": "bi-zoom-in",
        "colore": "#f97316",
        "cosa_analizza": (
            "Evoluzione longitudinale delle metriche specifiche della singola prova nel tempo (es. altezza salto CMJ in cm, potenza di picco W/kg, tempi cronometrici di scatto)."
        ),
        "a_cosa_serve": (
            "Verifica l'efficacia dei cicli di preparazione atletica nel generare gli adattamenti desiderati e rileva cali prestativi improvvisi legati a sovraccarico."
        ),
        "azioni_consentite": [
            "Filtro per test specifico",
            "Grafico di progressione temporale con barre di variabilità",
            "Tabella comparativa sessioni di test"
        ],
        "bibliografia": [
            "Claudino, J. G. et al. (2017). The countermovement jump to monitor neuromuscular status: A meta-analysis. Sports Medicine, 47(7), 1353-1367."
        ]
    },
    {
        "nome": "Executive Summary & Readiness",
        "nome_it": "Sintesi Esecutiva per Staff Tecnico & Indice di Prontezza",
        "area": "Test Fisici & Neuromuscolari",
        "icona": "bi-clipboard-check",
        "colore": "#f97316",
        "cosa_analizza": (
            "Sintesi decisionale che aggrega lo stato neuromuscolare dell'atleta evidenziando indici di asimmetria tra arti (L/R) e prontezza alla gara."
        ),
        "a_cosa_serve": (
            "Offre allo staff tecnico un semaforo decisionale immediato sullo stato di forma del giocatore in vista di tornei impegnativi."
        ),
        "azioni_consentite": [
            "Indicatori semaforici di readiness",
            "Segnalazione asimmetrie bilaterali a rischio (>10%)",
            "Esportazione Executive PDF"
        ],
        "bibliografia": [
            "Bishop, C. et al. (2018). Interlimb asymmetries: Are they detrimental to performance? JSCR, 32(8), 2320-2331."
        ]
    },
    {
        "nome": "Confronti",
        "nome_it": "Comparazioni Inter-Individuali & Benchmark di Squadra",
        "area": "Test Fisici & Neuromuscolari",
        "icona": "bi-people",
        "colore": "#f97316",
        "cosa_analizza": (
            "Confronta i risultati dei test fisici tra atleti dello stesso roster o rispetto a parametri di riferimento per categoria di età."
        ),
        "a_cosa_serve": (
            "Permette di stabilire standard di riferimento interni all'accademia e stimolare l'emulazione virtuosa nel gruppo di allenamento."
        ),
        "azioni_consentite": [
            "Selezione atleti a confronto",
            "Grafici a barre comparative",
            "Graduatorie di rendimento condizionale"
        ],
        "bibliografia": [
            "Fernandez-Fernandez, J. et al. (2014). Physical characteristics of young competitive tennis players. JSCR, 28(2), 485-494."
        ]
    },
    {
        "nome": "Gestione & Inserimento Test",
        "nome_it": "Modulo Immissione Dati & Acquisizione Misure da Campo",
        "area": "Test Fisici & Neuromuscolari",
        "icona": "bi-pencil-square",
        "colore": "#f97316",
        "cosa_analizza": (
            "Interfaccia rapida per registrare le misurazioni rilevate durante i test fisici su campo o in palestra."
        ),
        "a_cosa_serve": (
            "Consente ai preparatori di inserire i valori direttamente a bordo campo da tablet o smartphone, memorizzandoli nel database centrale."
        ),
        "azioni_consentite": [
            "Form dinamica con validazione range fisiologici",
            "Salvataggio e aggiornamento istantaneo",
            "Calcolo automatico indici derivati"
        ],
        "bibliografia": [
            "M0V3 Assessment Workflow Protocol."
        ]
    },
    {
        "nome": "Costruttore Test Custom",
        "nome_it": "Costruttore di Protocolli & Batterie di Test Personalizzate",
        "area": "Test Fisici & Neuromuscolari",
        "icona": "bi-tools",
        "colore": "#f97316",
        "cosa_analizza": (
            "Strumento per creare nuove tipologie di test personalizzate, definendo parametri, unità di misura e soglie di riferimento."
        ),
        "a_cosa_serve": (
            "Offre flessibilità a ogni staff o centro per integrare i propri test metodologici proprietari senza vincoli rigidi."
        ),
        "azioni_consentite": [
            "Creazione test con campi personalizzati",
            "Scelta unità di misura (cm, s, kg, W/kg, ecc.)",
            "Assegnazione ad atleti e categorie"
        ],
        "bibliografia": [
            "M0V3 Custom Assessment Framework."
        ]
    }
]

# Raggruppamento per area
AREE_ORDER = [
    "Analisi Match",
    "Analisi Sessione",
    "Trend Settimanale",
    "Trend Stagionale",
    "Storico Match",
    "Statistiche Match",
    "Medie",
    "Analisi Wellness-RPE-GPS",
    "Medico & Extra Tennis",
    "Test Fisici & Neuromuscolari"
]

AREA_ICONS = {
    "Analisi Match": ("bi-trophy-fill", "#0284c7"),
    "Analisi Sessione": ("bi-activity", "#10b981"),
    "Trend Settimanale": ("bi-calendar-week-fill", "#0ea5e9"),
    "Trend Stagionale": ("bi-calendar-range-fill", "#8b5cf6"),
    "Storico Match": ("bi-graph-up-arrow", "#f59e0b"),
    "Statistiche Match": ("bi-card-checklist", "#6366f1"),
    "Medie": ("bi-bar-chart-steps", "#0284c7"),
    "Analisi Wellness-RPE-GPS": ("bi-heart-pulse-fill", "#ec4899"),
    "Medico & Extra Tennis": ("bi-calendar-plus-fill", "#14b8a6"),
    "Test Fisici & Neuromuscolari": ("bi-clipboard2-pulse-fill", "#f97316")
}


# =========================================================================
# VISTA PRINCIPALE: MANUALE REPORT
# =========================================================================

def render_manuale_report(t):
    n_tot_moduli = len(MANUALE_ANALISI)
    n_aree = len(AREE_ORDER)
    n_biblio = sum(len(m.get('bibliografia', [])) for m in MANUALE_ANALISI)

    render_page_header(
        tr("Manuale Report & Moduli Analitici", "Reports & Analytical Modules Manual"),
        f"{tr('Guida tecnica, metodologica e scientifica a tutti i', 'Technical, methodological, and scientific guide to all')} {n_tot_moduli} {tr('moduli di analisi abilitabili e assegnabili nel sistema M0V3 Analytics.', 'analysis modules assignable in the M0V3 Analytics system.')}",
        tr("DOCUMENTAZIONE METODOLOGICA & SCIENTIFICA", "METHODOLOGICAL & SCIENTIFIC DOCUMENTATION")
    )

    # --- BANNER STATISTICO SINTETICO M0V3 ---

    st.html(
        f"""<div style="background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); border-radius: 12px; padding: 18px 24px; margin-bottom: 22px; box-shadow: 0 4px 14px rgba(0,0,0,0.12); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 16px; font-family: 'Inter', sans-serif;">
            <div>
                <div style="color: #38bdf8; font-size: 11.5px; font-weight: 800; letter-spacing: 1.2px; text-transform: uppercase;">
                    <i class="bi bi-journal-bookmark-fill" style="margin-right:8px;"></i>{tr('M0V3 ANALYTICS — ENCICLOPEDIA DEI REPORT', 'M0V3 ANALYTICS — REPORTS ENCYCLOPEDIA')}
                </div>
                <div style="color: #ffffff; font-size: 21px; font-weight: 900; margin-top: 2px;">
                    {tr('Catalogo Completo dei Moduli Operativi', 'Complete Catalog of Operational Modules')}
                </div>
                <div style="color: #94a3b8; font-size: 12px; margin-top: 4px;">
                    {tr('Tutte le analisi presenti nel Pannello Admin pronte per essere assegnate ai clienti, club e accademie.', 'All analyses present in the Admin Panel ready to be assigned to clients, clubs, and academies.')}
                </div>
            </div>
            <div style="display: flex; gap: 14px; align-items: center; flex-wrap: wrap;">
                <div style="background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.12); padding: 8px 16px; border-radius: 10px; text-align: center;">
                    <div style="color: #38bdf8; font-size: 18px; font-weight: 900;">{n_tot_moduli}</div>
                    <div style="color: #94a3b8; font-size: 10.5px; font-weight: 700; text-transform: uppercase;">{tr('Moduli Totali', 'Total Modules')}</div>
                </div>
                <div style="background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.12); padding: 8px 16px; border-radius: 10px; text-align: center;">
                    <div style="color: #34d399; font-size: 18px; font-weight: 900;">{n_aree}</div>
                    <div style="color: #94a3b8; font-size: 10.5px; font-weight: 700; text-transform: uppercase;">{tr('Aree Funzionali', 'Functional Areas')}</div>
                </div>
                <div style="background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.12); padding: 8px 16px; border-radius: 10px; text-align: center;">
                    <div style="color: #fbbf24; font-size: 18px; font-weight: 900;">{n_biblio}+</div>
                    <div style="color: #94a3b8; font-size: 10.5px; font-weight: 700; text-transform: uppercase;">{tr('Studi Accademici', 'Academic Studies')}</div>
                </div>
            </div>
        </div>"""
    )

    # --- BARRA DI RICERCA & FILTRI DINAMICI ---
    c_srch, c_fil = st.columns([1.6, 2.4])
    with c_srch:
        query_search = st.text_input(
            "" + tr("Cerca per nome, metrica, formula o autore scientifico:", "Search by name, metric, formula, or author:"),
            placeholder=tr("Es. Gabbett, ACWR, Monotonia, Strain, GPS, Podio...", "E.g. Gabbett, ACWR, Monotony, Strain, GPS, Podium..."),
            key="search_manuale_query"
        ).strip().lower()

    with c_fil:
        opzioni_aree = [tr("Tutte le Aree", "All Areas")] + AREE_ORDER
        area_sel = st.selectbox(
            "" + tr("Filtra per Area Funzionale:", "Filter by Functional Area:"),
            opzioni_aree,
            index=0,
            key="filter_manuale_area"
        )

    # Filtraggio dinamico dei dati
    moduli_filtrati = []
    for m in MANUALE_ANALISI:
        # Filtro area
        if area_sel != opzioni_aree[0] and m['area'] != area_sel:
            continue
        # Filtro testo ricerca
        if query_search:
            corpus = " ".join([
                m['nome'].lower(),
                m.get('nome_it', '').lower(),
                m['area'].lower(),
                m['cosa_analizza'].lower(),
                m['a_cosa_serve'].lower(),
                " ".join(m.get('azioni_consentite', [])).lower(),
                " ".join(m.get('bibliografia', [])).lower()
            ])
            if query_search not in corpus:
                continue
        moduli_filtrati.append(m)

    # Feedback conteggio
    n_trovati = len(moduli_filtrati)
    filtro_str = f" (filtro: '{query_search}')" if query_search else ""
    st.markdown(
        f"<div style='font-size:12px; font-weight:700; color:#64748b; margin-top:4px; margin-bottom:12px;'>"
        f"{tr('Visualizzazione di', 'Showing')} <b style='color:#0284c7;'>{n_trovati}</b> {tr('moduli analitici su', 'analytical modules of')} {n_tot_moduli}{filtro_str}"
        f"</div>",
        unsafe_allow_html=True
    )

    if not moduli_filtrati:
        st.info(tr("Nessuna analisi trovata corrispondente ai criteri di ricerca.", "No analysis found matching the search criteria."))
        return

    opzioni_pdf_man = {
        tr("Manuale Report Completo (Tutti i Moduli Filtrati)", "Complete Reports Manual (All Filtered Modules)"): "manuale_pdf"
    }
    render_action_bar(
        meta_items=[
            (tr("Area Selezionata", "Selected Area"), area_sel),
            (tr("Moduli Documentati", "Documented Modules"), f"{n_trovati} {tr('di', 'of')} {n_tot_moduli}"),
            (tr("Filtro Attivo", "Active Filter"), query_search if query_search else tr("Nessuno", "None")),
        ],
        pdf_options=opzioni_pdf_man,
        pdf_key=f"pdf_action_manuale_{area_sel}_{query_search}",
        generate_fn=lambda _: crea_pdf_manuale_report(moduli_filtrati, area_filtro=area_sel),
        filename_fn=lambda _: f"M0V3_Manuale_Report_{area_sel.replace(' ', '_')}.pdf"
    )

    # Raggruppamento dei moduli filtrati per Area
    moduli_per_area = {}
    for m in moduli_filtrati:
        ar = m['area']
        if ar not in moduli_per_area:
            moduli_per_area[ar] = []
        moduli_per_area[ar].append(m)

    # Rendering per Area
    for ar in AREE_ORDER:
        if ar not in moduli_per_area:
            continue
        lista_m = moduli_per_area[ar]
        ico_ar, col_ar = AREA_ICONS.get(ar, ("bi-folder", "#0284c7"))

        # Header Sezione Area
        st.html(
            f"""<div style="background:#ffffff; border:1px solid #cbd5e1; border-left:6px solid {col_ar}; border-radius:10px; padding:12px 18px; margin-top:24px; margin-bottom:14px; display:flex; justify-content:space-between; align-items:center; box-shadow:0 2px 6px rgba(15,23,42,0.03); font-family:'Inter',sans-serif;">
                <div style="display:flex; align-items:center; gap:10px;">
                    <span style="font-size:18px; color:{col_ar};"><i class="bi {ico_ar}"></i></span>
                    <span style="font-size:15px; font-weight:900; color:#0f172a; text-transform:uppercase; letter-spacing:0.06em;">{ar.upper()}</span>
                </div>
                <span style="background:#f1f5f9; color:#475569; font-size:11px; font-weight:800; padding:4px 12px; border-radius:999px; border:1px solid #e2e8f0;">
                    {len(lista_m)} {tr('Moduli', 'Modules')}
                </span>
            </div>"""
        )

        # Rendering Card per ciascun modulo
        for idx, mod in enumerate(lista_m):
            nome_display = mod.get('nome_it', mod['nome'])
            nome_tecnico = mod['nome']

            # Pillole per azioni consentite
            azioni_pills_html = "".join([
                f"<span style='background:#f8fafc; color:#334155; border:1px solid #cbd5e1; font-size:10.5px; font-weight:700; padding:3px 9px; border-radius:6px; display:inline-flex; align-items:center; gap:4px; margin:2px 3px 2px 0;'>"
                f"<i class='bi bi-check2-circle' style='color:{col_ar};'></i>{az}"
                f"</span>"
                for az in mod.get('azioni_consentite', [])
            ])

            # Riferimenti bibliografici formattati
            biblio_items = mod.get('bibliografia', [])
            if biblio_items:
                biblio_html_list = "".join([
                    f"<div style='margin-bottom:5px; font-size:11.5px; line-height:1.5; color:#1e293b;'>"
                    f"<span style='color:#b45309; font-weight:800; margin-right:4px;'>•</span><i>{b}</i>"
                    f"</div>"
                    for b in biblio_items
                ])
                biblio_block = f"""
                <div style="background:#fffbeb; border:1px solid #fef3c7; border-left:4px solid #f59e0b; border-radius:8px; padding:10px 14px; margin-top:12px;">
                    <div style="font-size:10.5px; font-weight:900; color:#92400e; text-transform:uppercase; letter-spacing:0.06em; margin-bottom:6px;">
                        <i class="bi bi-book-half" style="margin-right:6px;"></i>{tr('Riferimenti Bibliografici & Validazione Scientifica', 'Bibliographic References & Scientific Validation')}
                    </div>
                    {biblio_html_list}
                </div>
                """
            else:
                biblio_block = f"""
                <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:8px 12px; margin-top:10px; font-size:11px; color:#64748b;">
                    <i class="bi bi-cpu" style="margin-right:5px; color:#0284c7;"></i><b>M0V3 Algorithmic Core:</b> {tr('Elaborazione computazionale proprietaria su standard ISO/IMU.', 'Proprietary computational processing based on ISO/IMU standards.')}
                </div>
                """

            card_html = f"""<div style="background:#ffffff; border:1.5px solid #e2e8f0; border-radius:12px; padding:18px 22px; margin-bottom:16px; box-shadow:0 3px 10px rgba(15,23,42,0.03); font-family:'Inter',sans-serif; transition:all 0.2s ease;">
                <!-- HEADER CARD -->
                <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:14px; border-bottom:1px solid #f1f5f9; padding-bottom:10px; flex-wrap:wrap; gap:8px;">
                    <div>
                        <div style="font-size:16px; font-weight:900; color:#0f172a; letter-spacing:0.02em;">
                            <span style="color:{col_ar}; margin-right:6px;"># {idx+1}</span> {nome_display}
                        </div>
                        <div style="font-size:11.5px; font-weight:700; color:#64748b; margin-top:2px;">
                            <i class="bi bi-tag" style="margin-right:4px;"></i>{tr('Nome Modulo nel Catalogo Admin:', 'Admin Catalog Module Name:')} <span style="color:#0284c7; font-family:monospace; font-size:12px;">{nome_tecnico}</span>
                        </div>
                    </div>
                    <span style="background:rgba(2,132,199,0.08); color:#0369a1; border:1px solid rgba(2,132,199,0.25); font-size:10px; font-weight:800; padding:4px 10px; border-radius:20px; text-transform:uppercase; letter-spacing:0.05em;">
                        {ar}
                    </span>
                </div>

                <!-- GRIGLIA CONTENUTI -->
                <div style="display:grid; grid-template-columns: 1fr; gap:12px;">
                    <!-- COSA ANALIZZA -->
                    <div style="background:#f8fafc; border-left:4px solid #0284c7; border-radius:6px; padding:10px 14px;">
                        <div style="font-size:11px; font-weight:900; color:#0369a1; text-transform:uppercase; letter-spacing:0.06em; margin-bottom:4px;">
                            <i class="bi bi-search" style="margin-right:6px;"></i>{tr('COSA ANALIZZA', 'WHAT IT ANALYZES')}
                        </div>
                        <div style="font-size:13px; color:#1e293b; line-height:1.55; text-align:justify;">
                            {mod['cosa_analizza']}
                        </div>
                    </div>

                    <!-- A COSA SERVE -->
                    <div style="background:#f0fdf4; border-left:4px solid #10b981; border-radius:6px; padding:10px 14px;">
                        <div style="font-size:11px; font-weight:900; color:#15803d; text-transform:uppercase; letter-spacing:0.06em; margin-bottom:4px;">
                            <i class="bi bi-bullseye" style="margin-right:6px;"></i>{tr('A COSA SERVE (VALORE PER IL COACH)', 'WHAT IT IS FOR (COACH VALUE)')}
                        </div>
                        <div style="font-size:13px; color:#1e293b; line-height:1.55; text-align:justify;">
                            {mod['a_cosa_serve']}
                        </div>
                    </div>

                    <!-- AZIONI CONSENTITE -->
                    <div style="background:#faf5ff; border-left:4px solid #8b5cf6; border-radius:6px; padding:10px 14px;">
                        <div style="font-size:11px; font-weight:900; color:#6b21a8; text-transform:uppercase; letter-spacing:0.06em; margin-bottom:6px;">
                            <i class="bi bi-sliders" style="margin-right:6px;"></i>{tr('AZIONI CONSENTITE SULLA PIATTAFORMA', 'PERMITTED PLATFORM ACTIONS')}
                        </div>
                        <div style="display:flex; flex-wrap:wrap; gap:4px;">
                            {azioni_pills_html}
                        </div>
                    </div>
                </div>

                <!-- BIBLIOGRAFIA -->
                {biblio_block}
            </div>"""

            st.html(card_html)
