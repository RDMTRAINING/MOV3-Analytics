# M0V3 ANALYTICS — STATO DELL'ARTE, ARCHITETTURA E SVILUPPI RECENTI
*Documento di allineamento e sincronizzazione per Google Gemini (Gem Specializzata & Advanced Agentic Assistant)*  
*Data aggiornamento: 1 Novembre 2026*  
*Versione WebApp: 2.4 Enterprise*

---

## 1. VISIONE GENERALE DEL PROGETTO
**M0V3 Analytics** è una web application enterprise progettata per preparatori atletici, coach di tennis, fisioterapisti/medici e staff tecnico di alto livello. Il suo scopo è analizzare, monitorare, correlare e programmare i carichi di lavoro (esterni, metabolici, cinematici e meccanici da GPS/IMU), i carichi interni (sRPE Foster), lo stato biologico (Wellness mattutino), le valutazioni neuromuscolari/test fisici e il diario clinico/medico dei tennisti durante allenamenti, tornei e percorsi di Return-To-Play (RTP).

---

## 2. STACK TECNOLOGICO E INFRASTRUTTURA

| Componente | Tecnologia | Ruolo & Dettagli Architetturali |
| :--- | :--- | :--- |
| **Frontend / App** | **Python 3.9 / 3.11 - Streamlit** (>= 1.35.0) | Framework reattivo ad alte prestazioni, layout Glassmorphism custom, contenitori nativi `st.container(border=True)` per eliminare problemi DOM. |
| **Design System & Iconografia** | **Zero Emoji Policy + Bootstrap Icons** | Divieto assoluto di emoji Unicode nelle aree mediche e tecniche; iconografia monocromatica vettoriale tramite `<i class="bi bi-..."></i>` e badge geometrici CSS puri. |
| **Navigazione & Permessi** | `streamlit-option-menu` + RBAC Granulare | Menu laterale dinamico con scomparsa automatica delle aree non autorizzate; matrice permessi per area e sottopagina. |
| **Data Visualization** | **Plotly** (>= 5.18.0) | Grafici interattivi multi-asse, barre raggruppate, bande verticali shaded (`add_vrect`) a tutta altezza e spider radar chart. |
| **Database & Auth** | **Supabase (PostgreSQL 15)** | Autenticazione (JWT con auto-refresh token), Row Level Security (RLS), tabelle relazionali e trigger. |
| **Data Storage GPS** | **Ibrido CSV + Apache Parquet** | File locale `database_storico.parquet` ad alte prestazioni (<10ms accesso) con normalizzazione automatica delle date `Date_obj`. |
| **Reportistica PDF** | **ReportLab** (`pdf_generator.py`) | Motore vettoriale per referti di match, microcicli settimanali, test fisici e master calendar clinico in formato A4 orizzontale. |
| **Mobile Experience** | `views/atleta_mobile.py` | Portale dedicato all'atleta (mobile-first) per la compilazione giornaliera del Wellness mattutino e dei carichi sRPE. |

---

## 3. STRUTTURA DEL REPOSITORY E MODULI AGGIORNATA

```
webapp_tennis_gps/
├── app.py                       # Entry point: routing, sidebar dinamica, dispatch ruoli, session state
├── config.py                    # Costanti, catalogo permessi (CATALOGO_REPORT), dizionario IT/EN, card KPI, slugify
├── utils.py                     # Motore DB (Parquet + Supabase), JWT auto-refresh, get_athlete_master_calendar, CRUD
├── pdf_generator.py             # Generazione referti PDF vettoriali ReportLab (Match, Test, Manuali, Master Calendar)
├── email_service.py             # Servizio invio email e reset credenziali
├── database_storico.parquet     # Database locale GPS compresso ad alta velocità
├── database_storico.csv         # Database di backup compatibile
├── requirements.txt             # Dipendenze Python dell'ambiente
├── setup_carico_interno.sql     # DDL Supabase: tabelle rpe_sessioni e wellness_mattutino con RLS
├── setup_test_fisici.sql        # DDL Supabase: tabelle catalogo_protocolli e sessioni_test con RLS
├── setup_calendario_medico.sql  # DDL Supabase: tabella registro_medico_fisio con RLS e indici
├── protocolli_seed.py           # Script di popolazione iniziale catalogo 22 test fisici internazionali
└── views/                       # Moduli applicativi
    ├── home.py                  # Executive Dashboard: metriche chiave, stato giocatori, scorciatoie
    ├── atleta_mobile.py         # Portale Atleta Mobile: compilazione Wellness e RPE, storico personale
    ├── calendario_medico.py     # NUOVO: Master Timeline clinico-atletica, diario trattamenti, correlazione
    ├── test_fisici.py           # NUOVO: Deep-Dive, Readiness PB, Confronti Roster, Inserimento e Builder
    ├── manuale_test.py          # NUOVO: Manuale scientifico interattivo dei protocolli di valutazione
    ├── analisi_match.py         # Analisi specifica singola partita con confronto storico
    ├── analisi_sessione.py      # Analisi singola sessione allenamento (Tecnica, Fisica, ecc.)
    ├── trend_settimanale.py     # Microciclo (Lun-Dom): distribuzione giornaliera, ACWR, fatica
    ├── trend_stagionale.py      # Macrociclo/Stagione: carichi acuti vs cronici, picchi
    ├── storico_match.py         # Timeline e andamento longitudinale dei match disputati
    ├── medie.py                 # Analisi comparativa medie, Head-to-Head (H2H), stress roster
    ├── manuale_report.py        # Manuale scientifico interattivo dei 45 moduli di reportistica GPS
    ├── caricamento_dati.py      # Ingestione CSV con motore di mappatura automatica/custom
    ├── generatore_dati.py       # Simulatore di sessioni senza GPS partendo dal profilo dell'atleta
    ├── gestione_file.py         # Controllo storico file caricati ed eliminazione controllata
    ├── profilo.py               # Profilo utente, cambio password e cancellazione account GDPR
    ├── admin.py                 # Pannello Super-Admin: gestione utenti, ruoli, atleti e permessi
    └── supporto.py              # Invio e gestione ticket di assistenza tecnica
```

---

## 4. I NUOVI GRANDI MODULI ENTERPRISE IMPLEMENTATI

### A. Modulo "Carico Interno & Wellness" (`setup_carico_interno.sql` + `views/atleta_mobile.py`)
1. **Tabelle Supabase**:
   - `wellness_mattutino`: traccia qualità sonno, fatica, stress, umore, dolore muscolare/DOMS (scala 1-10) e calcola il Readiness Score giornaliero.
   - `rpe_sessioni`: traccia ogni seduta per slot (Slot 1, Slot 2), tipologia (Tennis, Palestra, Prep. Fisica), durata in minuti, RPE Borg (1-10) e calcola automaticamente il `carico_interno = durata_minuti * rpe`.
2. **Interfaccia Mobile per l'Atleta**:
   - Accessibile direttamente da smartphone per i tennisti con ruolo `Atleta`.
   - Card KPI personal best, indicatori semaforici di recupero e compilazione istantanea.

---

### B. Modulo "Test Fisici & Valutazione Neuromuscolare" (`views/test_fisici.py` + `views/manuale_test.py`)
1. **Architettura Database & Protocolli**:
   - Catalogo di 22 test standard internazionali pre-caricati suddivisi in 6 macro-aree:
     * *Pedane di Forza (VALD ForceDecks)*: CMJ, SJ, Drop Jump, IMTP.
     * *Dinamometria & Forza Isometria (VALD ForceFrame / Handgrip)*: Test adduttori/abduttori, rotatori spalla, handgrip.
     * *Velocità, Sprint & Agilità (Fotocellule)*: Sprint 5m/10m/20m, 5-0-5 Agility Test, T-Test.
     * *Resistenza Specifica Tennis & Vo2Max*: Yo-Yo Intermittent Recovery Test, 30-15 IFT, Test Conconi.
     * *Mobilità Articolare & Flessibilità*: Sit & Reach, Weight-Bearing Lunge Test (WBLT).
     * *Antropometria & Composizione Corporea*: Pliche corporee, circonferenze muscolari, rapporto vita/fianchi.
2. **Funzionalità e Tab di Analisi**:
   - **Tab 1 — Deep-Dive per Test**: Analisi protocollo, manuale rapido a scomparsa, snapshot ultimo test con asimmetrie Dx/Sx, delta percentuali calcolati rispettando la direzionalità scientifica (*Higher is better* vs *Lower is better*) e trend temporale multi-metrica.
   - **Tab 2 — Executive Summary & Readiness**: Valutazione dello stato di forma dell'atleta rispetto al proprio Personal Best storico (verde: >=95% PB, giallo: 88-94.9%, rosso: <88%), matrice delle asimmetrie bilaterali e spider radar delle qualità atletiche.
   - **Tab 3 — Confronti Roster**: Ranking orizzontale a barre Plotly dell'intera squadra per qualsiasi test e parametro, linea di media del roster, range prestazionale e copertura atleti testati.
   - **Tab 4 — Inserimento & Storico Misure**: Form reattivo per inserire nuove sedute di test con calcolo automatico asimmetrie e tabella storico modificabile/eliminabile.
   - **Tab 5 — Costruttore Test Custom**: Tool per il coach per creare protocolli personalizzati (nome, macro-area, metriche custom, direzionalità e benchmark).
3. **Manuale Didattico (`views/manuale_test.py`)**:
   - Manuale completo con filtri di ricerca, spiegazione biomeccanica, setup strumentale, istruzioni operative per l'atleta e linee guida d'interpretazione.
   - Esportazione referti in PDF integrata con `render_action_bar`.

---

### C. Modulo "Calendario & Area Medica" (`views/calendario_medico.py`)
1. **Zero Emoji Policy & Design System Monocromatico**:
   - Divieto assoluto di emoji Unicode: nessun pallino o simbolo emoji.
   - Utilizzo esclusivo di Bootstrap Icons vettoriali (`<i class="bi bi-..."></i>`) per tutte le intestazioni, i badge e i grafici.
   - Stati operativi codificati con palette istituzionale M0V3:
     * `DISPONIBILE` (Full Training): Smeraldo `#10b981`
     * `LIMITATO` (Modified / RTP): Ambra `#f59e0b`
     * `INDISPONIBILE` (Stop Medico / Out): Rosso Rubino `#e11d48`
     * `RIPOSO_VIAGGIO` (Giorno Off / Trasferta): Blu/Ardesia `#38bdf8` / `#64748b`
2. **Controllo Accessi & Ruoli**:
   - Nuovo ruolo **`Fisio / Medico`**: Comportamento analogo al Coach (vede solo gli atleti associati, accede ai moduli abilitati dall'Admin).
   - **Esclusione Assoluta Ruolo 'Atleta'**: L'atleta non vede la voce nel menu e viene bloccato con messaggio di sicurezza se tenta l'accesso diretto.
3. **Motore di Fusione Dati (`get_athlete_master_calendar` in `utils.py`)**:
   Fonde in un unico dizionario giornaliero:
   - Carico Esterno GPS (Parquet): Training Load, Minuti, TL High, High Accel/Decel, tag `[MATCH]`.
   - Carico Interno sRPE (`rpe_sessioni`): Minuti, RPE per slot, carico totale, flag automatico `solo_carico_interno` (*NO-GPS*).
   - Wellness Mattutino (`wellness_mattutino`): Score normalizzato, sonno, fatica, stress, umore, DOMS ed eventuali alert critici.
   - Test Fisici (`sessioni_test`): Conteggio e nomi dei test eseguiti.
   - Registro Medico/Fisio (`registro_medico_fisio`): Eventi clinici e gerarchia di status (`INDISPONIBILE` > `LIMITATO` > `RIPOSO_VIAGGIO` > `DISPONIBILE`).
4. **Le 3 Schede del Modulo**:
   - **Tab 1 — Calendario & Master Timeline**: Navigazione mese (`< Prec. | Mese | Succ. >` + `Oggi`), 5 KPI executive mensili, griglia mensile Lun-Dom con bordo superiore colorato per status e micro-badge (GPS TL, sRPE NO-GPS, Wellness, Test, Stop/Limit/Fisio/Viaggio). Day Inspector a 3 colonne native (`with st.container(border=True)`) per Carichi, Wellness e Diario Clinico.
   - **Tab 2 — Inserimento & Gestione Registro**: Form a 4 modalità (Trattamento, Sovraccarico, Infortunio, Logistica). Per trattamenti e fastidi senza stop del giocatore, viene richiesta **solo la data di segnalazione/trattamento** (nessuna data di rientro forzata, con checkbox facoltativo solo per periodi prolungati).
   - **Tab 3 — Correlazione Carichi & Clinica**: Grafico multi-layer Plotly sincronizzato con il mese selezionato o orizzonti 30/60/90 giorni:
     * Asse Y1: Barre Training Load GPS (blu) e Barre sRPE (arancione) raggruppate.
     * Asse Y2: Linea Readiness/Wellness (viola).
     * Bande verticali shaded a tutta altezza (`add_vrect`) che evidenziano i periodi di Carico Adattato (ambra), Stop Medico (rosso) e Viaggio/Off (azzurro) con etichette di testo in alto.
     * Marcatori a croce verde sull'asse X per le sedute di fisioterapia eseguite.
     * Tabella e grafico a barre orizzontali di incidenza per distretto anatomico.
   - Esportazione PDF: Funzione [`crea_pdf_calendario_medico`](file:///Users/riccardodimaio/webapp_tennis_gps/pdf_generator.py#L1752) per generare il referto clinico mensile in A4 landscape.

---

## 5. MATRICE PERMESSI DINAMICA E GESTIONE ADMIN

- In [config.py](file:///Users/riccardodimaio/webapp_tennis_gps/config.py), `CATALOGO_REPORT` e `AREA_TO_PAGINA` mappano tutte le aree e sottopagine:
  - *Home / Executive Dashboard*
  - *Test & Valutazioni* (Deep-Dive, Executive, Confronti, Inserimento, Costruttore)
  - *Manuale Protocolli Test*
  - *Calendario & Area Medica* (Master Calendar, Registro Clinico, Correlazione)
  - *Analisi Match*, *Analisi Sessione*, *Trend Settimanale*, *Trend Stagionale*, *Storico Match*, *Analisi Medie*
- In [app.py](file:///Users/riccardodimaio/webapp_tennis_gps/app.py), la funzione `_is_menu_page_visible`:
  - Se un Super-Admin deseleziona un'intera area (es. Analisi Match) per un utente, la voce **scompare completamente dal menu laterale**.
  - Se l'utente tenta di accedere a una pagina per cui non ha permessi, compare un warning informativo senza crash.

---

## 6. BUG CRITICI RISOLTI E BEST PRACTICES CONSOLIDATE

1. **Risoluzione Mismatch Tipi Date Pandas vs Datetime**:
   - *Problema*: `TypeError: Invalid comparison between dtype=datetime64[ns] and date` durante il filtraggio del dataframe Parquet in `get_athlete_master_calendar`.
   - *Soluzione*: Normalizzazione esplicita tramite `pd.to_datetime(df_ath['Date_obj'], errors='coerce').dt.date`.
2. **Risoluzione Mappatura Colonne `rpe_sessioni`**:
   - *Problema*: Il codice cercava colonne piatte `slot1_durata_minuti`, mentre la tabella Supabase salva i record su singola riga con `slot`, `tipologia`, `durata_minuti`, `rpe`, `carico_interno`. Il carico risultava 0 AU.
   - *Soluzione*: Parsing dello schema normalizzato con estrazione diretta di `carico_interno` e `durata_minuti * rpe`.
3. **Risoluzione Larghezza Zero delle Bande Verticali Plotly (`add_vrect`)**:
   - *Problema*: Aggiungere/sottrarre un `timedelta(hours=12)` a un oggetto `datetime.date` restituisce la stessa identica data (troncata a 0 giorni), facendo coincidere `x0 == x1` e rendendo la banda larga 0 pixel (invisibile).
   - *Soluzione*: Conversione a `datetime.datetime.combine(d, time(...))` con buffer temporale a 24 ore e raggruppamento dei giorni consecutivi in periodi continui.
4. **Eliminazione Riquadri Bianchi Vuoti nel Day Inspector**:
   - *Problema*: Aprire un `<div style='min-height:260px;'>` in un `st.markdown()` e chiuderlo in un altro portava il browser ad auto-chiudere il div subito, creando un rettangolo bianco vuoto di 260px e lasciando i dati fuori dal riquadro.
   - *Soluzione*: Adozione dei contenitori nativi Streamlit `with st.container(border=True):`.
5. **Compatibilità Python 3.9 (Divieto Backslash in f-string)**:
   - *Problema*: In Python 3.9 le espressioni f-string `{...}` non supportano backslash (`\"`, `\n`).
   - *Soluzione*: Pre-calcolo delle stringhe HTML o spezzamento delle variabili prima dell'interpolazione f-string.
6. **Esportazione Sicura di Utility Comuni**:
   - Funzione `slugify_name` esportata sia in `pdf_generator.py`, sia in `utils.py`, sia in `config.py` per prevenire qualsiasi `ImportError`.
   - Firma `card_kpi(titolo, valore_html, sottotitolo="", accento="#0ea5e9", **kwargs)` flessibile per accettare indifferentemente `subtext`/`sottotitolo` e `accent`/`accento`.
