# MEMORANDUM TECNICO-STORICO INTEGRALE — MOV3 ANALYTICS
**Resoconto Cronologico Completo dall'Inizio dell'Intervento (28 Ottobre 2026) ad Oggi (18 Novembre 2026)**

- **Piattaforma:** MOV3 Analytics Enterprise (`https://github.com/RDMTRAINING/MOV3-Analytics.git`, branch `main`)
- **Arco temporale completo:** **28 Ottobre 2026 (ore 22:11)** – **18 Novembre 2026** (22 giorni solari)
- **Conversazioni coperte:** Tutte le 5 sessioni di lavoro dedicate a MOV3 Analytics *(Fase I di sviluppo locale pre-Git: 28 Ott – 9 Nov; Fase II in produzione cloud GitHub/Streamlit: 9 Nov – 18 Nov, 69 commit da `5bd2bb0` a `3685664`)*
- **Data redazione memorandum:** 18 Novembre 2026

> [!NOTE]
> Nel periodo 5–8 Novembre (e mattino del 9 Novembre) è stata svolta parallelamente la creazione di una seconda piattaforma separata (*FIR Rugby GPS Analytics*). Questo memorandum isola e documenta esclusivamente tutti gli interventi eseguiti su **MOV3 Analytics (Tennis)**.

---

## PARTE 1 — SITUAZIONE INIZIALE ESATTA RILEVATA IL 28 OTTOBRE 2026

Quando il **28 Ottobre 2026 alle 22:11** hai condiviso per la prima volta la cartella `/Users/riccardodimaio/webapp_tennis_gps/`, la webapp — costruita fino a quel momento manualmente con Google Gemini incollando il codice — presentava già una **logica di dominio Sport Science notevole**, ma era strutturalmente un **prototipo monolitico locale** non pronto per la scalabilità né per la messa online commerciale.

### 1.1 Fotografia Tecnica della Cartella Iniziale (28 Ottobre 2026)
| Aspetto | Situazione Trovata al Giorno 1 (28 Ottobre 2026) |
| :--- | :--- |
| **Architettura del Codice** | **Un unico file monolitico `app.py` da 4.547 righe** contenente tutto: configurazioni, CSS, auth Supabase, calcoli, 5 funzioni PDF ReportLab e tutte le viste. Nessuna cartella `views/`, nessun `config.py`, `utils.py` o `pdf_generator.py`. |
| **Database Dati GPS** | Solo **`database_storico.csv`** locale (poche decine di sessioni dimostrative pre-Cobolli, nessun file Parquet, nessuna cache RAM, nessuna sincronizzazione cloud). |
| **Pagine Esistenti** | Home base, Analisi Match GPS, Analisi Sessione, Trend Settimanale base, Storico Match GPS, Medie base, Caricamento CSV, Generatore Dati Simulati (No GPS), Gestione File base, Profilo Personale minimale, Pannello Admin base. |
| **Punti di Forza già Presenti** | Separazione intelligente **Indoor vs Outdoor** (esclusione metriche satellitari indoor mantenendo IMU), prime funzioni **ACWR / Before Tomorrow**, idea del **Generatore No-GPS** con flag `Dato_Simulato`, mappatura dinamica CSV per utente, multi-sessione `_SupabasePerSession` e 5 generatori ReportLab base. |

### 1.2 Bug, Rischi Architetturali e Lacune Riscontrate all'Audit Iniziale (28 Ottobre 2026)
1. **Monolite ingestibile (4.547 righe in `app.py`):** ogni modifica rischiava regressioni a catena ed era lenta/fragile da manutenere.
2. **Persistenza dati GPS solo su CSV locale:** rischio immediato di **data loss** al deploy su cloud (filesystem effimero) e rischio di *race condition* in scrittura simultanea.
3. **Bug critico di deduplicazione CSV (`riga 2258`):** `drop_duplicates(subset=['Date', 'Session', 'Players'])` usava `keep='first'` — ricaricando un CSV corretto per la stessa data/sessione, Pandas scartava il file nuovo e teneva quello vecchio senza avvisare.
4. **Codice duplicato e refusi in `app.py`:** le funzioni `colora_delta`, `colora_acwr` e `build_pdf_con_footer` erano definite **due volte di fila** (righe 648–685 e 696–733); `crea_pdf_m0v3` passava un indice colonna fuori range (`[3, 5]` su tabella a 5 colonne).
5. **Lacune Sicurezza & Privacy:**
   - Password temporanea hardcoded (`"TempPasswordM0V3!"`) in creazione e reset utenti nel Pannello Admin.
   - Nessun guard-check esplicito sul blocco `elif active_page == "Pannello Admin"` (solo menu nascosto).
   - Sezione *Diritto all'Oblio / Elimina Account* sparita dal Profilo Personale e nessun link all'informativa privacy nel consenso iniziale.
   - Nessuna tutela IP (copyright sorgenti, clickwrap legale, watermarking forense PDF, audit trail).
6. **Moduli completamente assenti al 28 Ottobre:**
   - Nessun **Trend Stagionale** (blocchi 8 settimane, 12 mesi, ACWR stagionale, Monotonia, Strain, Distribuzione Lavoro).
   - Nessuna **Mini WebApp Smartphone Atleta** né modulo **Carico Interno (sRPE Foster) & Wellness Mattutino**.
   - Nessun modulo **Test Fisici & Neuromuscolari** (22 protocolli VALD/fotocellule/DSI), nessun **Manuale Test**, nessun **MOVE Tennis Test** (indici a 6 valori).
   - Nessun **Calendario & Area Medica / Fisio** né ruolo `Fisio / Medico`.
   - Nessuna sezione **Supporto / Ticket** né **Manuale Report** né **Confronto Individuale**.
   - Nessun dato reale di **Flavio Cobolli** (né GPS 2025–2026 né archivio match ATP/ITF né API LiveTennis / Tennis Abstract / ESPN).
   - Nessun flusso **Digital Handshake / Kanban K-Sport** per richieste tagli GPS.
   - Grafica ancora vicina allo Streamlit standard con emoji Unicode e senza un Design System Executive unificato.

---

## PARTE 2 — CRONOLOGIA COMPLETA DEGLI INTERVENTI

### FASE I — Rifondazione Architetturale e Sviluppo Moduli Enterprise in Locale (28 Ottobre – 9 Novembre 2026)

#### 28 Ottobre 2026 — Audit Iniziale, Fix Critici, Modularizzazione & Design System Base
- **Audit tecnico completo** del monolite `app.py` (4.547 righe) e correzione immediata dei 4 bug prioritari: deduplicazione CSV con `keep='last'`, rimozione funzioni duplicate, generazione sicura password temporanee con `secrets.token_urlsafe`, guard-check esplicito su Pannello Admin e fix indice colonna PDF.
- **Modularizzazione completa del progetto:** scomposizione di `app.py` (da 4.547 righe a router snello) in `config.py`, `utils.py`, `pdf_generator.py` e cartella `views/` dedicata a ogni pagina, con backup di sicurezza.
- **Upgrade Grafico Commerciale:** sostituzione delle emoji con **icone vettoriali monocromatiche Bootstrap Icons**, nuova barra stilizzata per export PDF, traduzione IT/EN, uniformazione card/tabelle in stile Executive.
- **Nuove Analisi in Trend Settimanale:** creazione vista **7-Day Rolling** e vista **Settimana Calendario (Lun–Dom)** sui 6 parametri chiave, uniformazione della formula *Work Rate (densità)* su tutta la webapp e adozione del nuovo layout ACWR/Readiness anche su *Analisi Match* e *Analisi Sessione*.

#### 29 Ottobre 2026 — Audit Matematico, Nascita Trend Stagionale, Supporto, Roster Analytics & Manuale Report
- **Audit matematico integrale** di tutti i moduli e PDF: separazione rigorosa tra medie storiche/benchmark (solo `Dato_Simulato == False`) e calcoli di carico/ACWR (reali + simulati).
- **Consolidamento Gestione CSV & Database:** valutatore sicuro delle formule di mappatura, identificazione univoca di ogni sessione per modifica/eliminazione sicura e pulizia automatica DB.
- **Fix Login, Profilo & Accessi:** correzione campi login per autofill browser, ripristino controlli privacy/Diritto all'Oblio in *Profilo Personale* e monitoraggio stato spunta privacy in *Profili & Accessi*.
- **Creazione Modulo "Trend Stagionale" (`views/trend_stagionale.py`):**
  - Analisi blocchi 8 settimane + *Season Average*;
  - Carico totale mensile sui 12 mesi (formato ore/minuti);
  - Andamento settimanale lungo l'intera stagione;
  - **ACWR settimanale** consolidato (Lun–Dom);
  - **Monotonia** e **Strain Training** (con selettore Volume TL vs Intensità TL High e guida scientifica);
  - **Distribuzione Lavoro** per superficie e tipologia sessione.
- **Nuova Analisi Descrittiva Settimanale & Tabella Giornaliera vs Media Match:** inclusa generazione automatica del referto copiabile per WhatsApp (con rimozione del *Before Tomorrow* non coerente).
- **Creazione Sezione "Supporto & Ticket" (`views/supporto.py`):** invio segnalazioni verso `mov3project26@gmail.com` e archivio ticket locale.
- **Espansione "Medie e Confronti" (`views/medie.py`):** rinomina *Testa a Testa Medie*, aggiunta *Ranking Roster Atleti*, *Distribuzione Lavoro Roster* e *Stress Roster 8 Settimane* (ACWR, Monotonia e Strain con soglie d'allarme tarate sul singolo atleta).
- **Creazione "Manuale Report" (`views/manuale_report.py`):** catalogo interattivo completo di tutte le analisi prodotte con export PDF impaginato senza spezzare titolo e descrizione.

#### 30 Ottobre 2026 — Coerenza Matematica, Design System Ufficiale & Email Onboarding
- Check globale di coerenza tra tutte le pagine: integrazione di `calcola_blocchi_baseline` nel loop 8 settimane di *Medie*, normalizzazione a 100 e fix `ImportError` di `crea_pdf_stagionale_m0v3`.
- **Uniformazione Tipografica & Design System M0V3:** allineamento font stack unico e palette colori istituzionale su tutte le pagine e i grafici Plotly.
- **Sistema Email Onboarding & Reset Password (`email_service.py`):** predisposizione invio credenziali e reset password agli utenti.

#### 31 Ottobre 2026 — Accelerazione Parquet, Login Cockpit, Modulo Carico Interno & Mini WebApp Smartphone
- **Ottimizzazione Performance:** introduzione dello storage binario **Apache Parquet** (`database_storico.parquet`, lettura <10ms) affiancato al CSV, caching RAM e risoluzione del bug di refresh/cambio scheda al variare di data o settimana.
- Fix proprietà Plotly deprecata `YAxis.titlefont` in `trend_stagionale.py`.
- **Restyling Pagina Login:** sfondo dark con *Geometric Tennis Grid*, logo rotondo trasparente centrato e plancia telemetrica a 3 colonne.
- **Implementazione Modulo "Carico Interno (sRPE) & Wellness Mattutino":**
  - Schema SQL Supabase `setup_carico_interno.sql` (`wellness_mattutino` e `rpe_sessioni` con RLS);
  - Vista staff `views/carico_interno.py` (sRPE Foster, confronto Carico Interno vs Esterno GPS, distribuzione per tipologia);
  - **Nuova Mini WebApp Smartphone Atleta (`views/atleta_mobile.py`):** interfaccia mobile-first per compilazione rapida giornaliera di Wellness e sRPE + scheda *Le Mie Prestazioni* (ultima sessione GPS) con routing differenziato smartphone/desktop.

#### 1 Novembre 2026 — Auto-Refresh JWT, Modulo Test Fisici (22 Protocolli) & Modulo Calendario Medico
- **Hardening Supabase Auth:** implementato auto-refresh trasparente dei token JWT scaduti (`PGRST303 JWT expired`) e protezione anti-loop al logout.
- **Promemoria Wellness/RPE su Smartphone:** aggiunta generazione rapida di promemoria tramite calendario nativo a costo zero.
- **Implementazione Modulo "Test Fisici & Valutazione Neuromuscolare":**
  - Schema SQL `setup_test_fisici.sql` + `protocolli_seed.py` con **22 protocolli internazionali** su 6 macro-aree (VALD ForceDecks, ForceFrame/Handgrip, Fotocellule Sprint/Agilità, Resistenza Tennis, Mobilità, Antropometria);
  - Vista completa `views/test_fisici.py` a 5 schede (*Deep-Dive*, *Executive Summary & Readiness PB*, *Confronti Roster*, *Inserimento & Storico*, *Costruttore Test Custom*) + `views/manuale_test.py` con export PDF.
- **Implementazione Modulo "Calendario & Area Medica" (`views/calendario_medico.py`):**
  - Schema SQL `setup_calendario_medico.sql` (`registro_medico_fisio`) e motore di fusione giornaliera `get_athlete_master_calendar` in `utils.py` (GPS + sRPE + Wellness + Test + Diario Clinico);
  - Introduzione ruolo **`Fisio / Medico`** e blocco di sicurezza assoluto per il ruolo `Atleta`;
  - Applicazione rigorosa della **Zero Emoji Policy** (solo Bootstrap Icons) e gestione trattamenti/fastidi puntuali senza data di rientro obbligatoria;
  - Ottimizzazione indici compositi B-Tree su Supabase e stesura documento `STATO_SISTEMA_MOV3_ANALYTICS.md`.

#### 2 Novembre 2026 — Bilinguismo Globale IT/EN, Redesign Home Focus Atleta & Dossier Operativo
- **Audit e riassetto completo bilinguismo IT/EN** su tutta la webapp inclusa la Mini WebApp smartphone.
- **Riorganizzazione Home Executive:** aggiunta delle 2 card cliniche (stato atleta + ultimo trattamento), barra *Focus Atleta* con selettore integrato e uniformazione di tutti i selettori atleta nelle varie viste.
- Aggiunta selezione **periodo personalizzato** in *Medie e Confronti* (Ranking Roster e Distribuzione Lavoro).
- **Upgrade Scientifico Multi-Modulo**, nuova vista tabellare con elenco completo di tutti i test svolti dall'atleta e redazione di `DOSSIER_OPERATIVO_MOV3_ANALYTICS.md`.

#### 3–4 Novembre 2026 — Selettore Atleta Globale in Sidebar, PDF Test Completi + DSI & Audit Stabile
- Audit statico AST, scope variabili, query Supabase e velocizzazione caricamenti.
- **Potenziamento Export PDF Test Fisici:** inclusione di tutte le sottopagine analitiche, calcolo e visualizzazione del **Dynamic Strength Index (DSI)** incrociando CMJ/SJ e IMTP nella stessa data, e tabella di modifica/gestione dei test caricati.
- **Selettore Atleta Globale unificato nella Sidebar** (sopra il selettore lingua) sincronizzato con tutte le viste mono-atleta + auto-scroll automatico in cima alla pagina ad ogni cambio vista.
- Fix leggibilità/contrasto su Mini WebApp smartphone e correzione bug `datetime`/`today` in *Generatore Dati Simulati*.

#### 8 Novembre 2026 (sera) — Dati Reali Flavio Cobolli (Marzo 2025 – Nov 2026), MOVE Tennis Test & Parser DOCX
- **Ingestione Storico Reale Flavio Cobolli:** importazione completa del file `data_supporto/dati_cobolli.xlsx` (da Marzo 2025 fino all'8 Novembre 2026 — **440 sessioni GPS reali**), rimozione vecchi dati sporchi e normalizzazione superfici rigorosa su **`Hard / Clay / Grass`** (rimozione `green`).
- **Creazione Modulo "MOVE Tennis Test" (`views/move_tennis_test.py`):** modellazione dedicata agli indici composti a 6 valori da `move tennis test.pdf` con caricamento dei test reali di Flavio Cobolli in `data_supporto/move_tennis_tests.json`.
- **Creazione Parser Test DOCX (`parsers/test_docx_parser.py`):** importazione strutturata di `data_supporto/Test Cobolli.docx` in `sessioni_test.json` con persistenza della selezione parametri per test e verifica completa dei permessi granulari Admin su ogni area/modulo.

#### 9 Novembre 2026 — Raffinamento Deep-Dive Test, Go-Live Cloud GitHub/Streamlit & Avvio LiveTennis API
- Miglioramento selettore *Deep-Dive Test* (mostra esclusivamente i test realmente presenti per l'atleta selezionato).
- **Go-Live Produzione su Streamlit Cloud (`5bd2bb0`, ore 16:29):**
  - Creazione repository ufficiale `https://github.com/RDMTRAINING/MOV3-Analytics.git` e primo commit strutturato (**MOV3 Analytics Enterprise v2.4**, 47 file, 33.128 righe);
  - Configurazione deployment pubblico/privato su `share.streamlit.io` e salvaguardia account.
- **Avvio integrazione LiveTennis API (ore 23:02):** validazione API key (piano 100 chiamate/giorno), progettazione card ATP live per Flavio Cobolli in Home e progettazione della nuova pagina *Statistiche Match*.

---

### FASE II — Produzione Cloud, Analisi Incrociate ATP-GPS, Governance, Dark Cockpit & Motore Ibrido Match (10 Novembre – 18 Novembre 2026)

#### 10 Novembre 2026 — Archivio Match ATP, Statistiche Match Tennis ↔ GPS e Qualità Dati (11 commit)
- **`e840ff0` (10:13):** Ingestione `STORICO MATCH COBOLLI.xlsx` tramite `utils_tennis_matches.py` (`cobolli_matches.parquet` + `.json`, **486 match punto-per-punto**, `calendario_tornei.json`); creazione `views/statistiche_match.py`, primi client `utils_livetennis.py`/`sync_livetennis.py`, bande colorate superfici + etichette tornei verticali `-90°` in `trend_stagionale.py` e nuovo `crea_pdf_stagionale_m0v3` in `pdf_generator.py`.
- **`27f3ef0` (10:58):** Hardening sessione e null-check difensivi su `user_obj` in `app.py`.
- **`805b479` (11:18) & `d38fa4e` (11:22):** Motore completo di correlazione **Tennis ↔ GPS** in `statistiche_match.py` (`m/pt`, `TL/pt`, `PL/pt`, `Acc+Dec High/pt`, benchmark Vittorie vs Sconfitte, superfici, ranking tier, efficienza servizio) con sostituzione `statsmodels` → **NumPy `np.polyfit`**.
- **`5fe8f0c` (12:57):** Politica rigorosa **solo match singoli e dati 100% reali** (esclusione simulati) + nuovo grafico cronologico a barre *Metri/Punto* con rolling 3 match.
- **`f82fbe2` (14:22) & `adc176f` (15:08):** Audit filtri match in `analisi_sessione.py` e `atleta_mobile.py`; confronto coerente Doppio vs media Doppi e Singolo vs media Singoli in `analisi_match.py`; redazione `AGGIORNAMENTO_SISTEMA_GEMINI.md`.
- **`21cb9c7` (15:21), `4e0c4ae` (15:23), `74b991e` (15:33), `468f4de` (15:36):** Isolamento rigoroso tipologie sessione per atleta (separazione catalogo Cobolli dagli altri atleti) e toggle Reale/Simulato in `gestione_file.py` e `caricamento_dati.py`.

#### 11 Novembre 2026 — Statistiche Match PDF, Pulizia Database & Fix Clinici (6 commit)
- **`0580095` (00:37):** Upgrade `statistiche_match.py` (work rate/volume, superfici su Training Load, ranking tier, spiegazioni scientifiche visibili) + nuovo export PDF completo in `pdf_generator.py` (+1.928 righe su 14 file).
- **`4a1d371` (00:48) & `9b34bf7` (07:32):** Ancoraggio percorsi a `BASE_DIR`, miglioramento deduplicazione upload, rimozione sessioni spurie e ripristino database pulito (440 Cobolli + 21 `prova uno`).
- **`408f1fc` (09:59):** Spostamento Hero Card *Focus Atleta* in cima alla Home sotto *Executive Locker Room*.
- **`b46a152` (22:12), `1f4d559` (22:17), `545eab3` (22:42):** Fix `label_periodo_sel` in `carico_interno.py`, gestione difensiva `None` in `test_fisici.py` e allineamento a mezzanotte dei bordi bande cliniche in `calendario_medico.py`.

#### 12 Novembre 2026 — Palestra 70/30, 62 Moduli Report & Fix Loop Mobile (10 commit)
- **`5316ea8` (18:15):** Modulo **Palestra 70/30**, riconciliazione durata atleta-staff, hover mini-card calendario e grafico a doppia corsia AU con audit 48h (+1.281 righe su 7 file).
- **`e3f3dda` (18:30), `fe06e94` (18:37), `8c74ce0` (18:41):** Risoluzione ricorsione infinita in monkey-patching `SyncQueryRequestBuilder.execute` su hot-reload tramite `_unwrapped_execute` persistente.
- **`917d2cc` (21:09), `5b1d5d4` (21:15), `7d2c7b5` (21:56), `6f65248` (22:02):** Riorganizzazione layout Home, rinomina *Medico & Extra Tennis* e *Analisi Wellness-RPE-GPS*, decoupling isolato su Tab 1 e fix `UnboundLocalError` in `admin.py`.
- **`353ba23` (22:11):** Aggiornamento `CATALOGO_REPORT` e **Manuale Report espanso a 62 moduli** con permessi modulari granulari.
- **`a982eb3` (23:40):** Eliminazione loop infinito di reload su smartphone dovuto a redirect dispositivo e token auth stantii.

#### 13 Novembre 2026 — Proprietà Intellettuale, Privacy GDPR & Watermark PDF (4 commit)
- **`7b12d2e` (14:54):** Intestazioni copyright M0V3 su tutti i 39 file sorgenti, clickwrap GDPR/IP obbligatorio al login (`assets/Atto_Privacy_IP_MOV3_v2.pdf`), footer con logo M0V3 e watermark di audit sui PDF esportati.
- **`9b7ef64` (15:05):** Safeguard hot-reload per `render_m0v3_footer`.
- **`ad62d97` (15:09):** Redazione dossier normativo `DOSSIER_PRIVACY_IP_MOV3_GEMINI.md`.
- **`4f3d617` (15:13):** Copia sessioni GPS 2026 Cobolli su profilo demo `prova uno` per test realistici.

#### 14 Novembre 2026 — Parità Grafica Totale dei Report PDF (2 commit)
- **`1f42c7e` (20:11) & `9e2866c` (20:42):** Riscrittura profonda di `pdf_generator.py` (+866 righe nette) per replicare esattamente grafici Plotly, tabelle executive, spider radar e impaginazione del portale web su tutti gli export PDF (*Settimanale*, *Match*, *Sessione*, *Medie* e *Carico Interno*).

#### 15 Novembre 2026 — Cloud Snapshot Zero-Latency, Confronto Individuale, Notifiche Ibride & Data Governance (14 commit)
- **`89c757c` (13:51) & `4dce11c` (13:54):** Implementazione **Cloud Binary Snapshot Zero-Latency su Supabase Storage** (Local Mirroring all'avvio + upload automatico su ogni modifica) che elimina definitivamente il data loss su Streamlit Cloud; ripristino sessioni GPS 9–14 Novembre e affinamento correlazione AU 70/30.
- **`0506996` (14:04), `367b03c` (14:18), `f6a924a` (14:26), `2113e77` (14:32):** Iterazioni visual sullo sfondo telemetrico (`assets/mov3_cyber_bg.jpg`) e incorniciatura card grafici.
- **`8bc94a9` (15:36):** Nuova sottopagina **Confronto Individuale** in `views/medie.py` (+678 righe) con export PDF dedicato e documentazione nel Manuale Report.
- **`e107f37` (17:15) & `f14d15e` (18:24):** Distinzione cromatica infortunio aperto (rosso), riposo/viaggio (grigio) e carico modificato (giallo) + algoritmo **anti-collisione a livelli sfalsati** per badge fisio e fastidi in `calendario_medico.py`.
- **`778fd7c` (18:04), `97c916e` (18:08), `440bf97` (18:11):** **Sistema Notifiche Ibrido Intelligente** (Modal Dialog per azioni critiche + Emerald Toast HUD per conferme rapide) esteso a 13 file.
- **`138fe8d` (22:57):** Bordi navy raffinati e angoli arrotondati anti-bleed su tutte le card e grafici.
- **`c55e2b3` (23:14) & `66c0e92` (23:44):** Modulo **Data Governance & Audit Trail GDPR Art. 9** (`setup_data_governance.sql`, soft-delete reversibile, tracciamento modifiche a doppio livello, console governance in `gestione_file.py` e fix colonna generata `carico_interno`).

#### 16 Novembre 2026 — Zero-Emoji, Email Automatica Ticket & Redesign Dark Cockpit (6 commit)
- **`1abc525` (09:17):** Fix definitivo upsert su colonna generata `carico_interno`, pulizia emoji residue (*Zero-Emoji Policy*) e upgrade notifiche test.
- **`8d8a413` (09:49):** Notifica email automatica verso `mov3project26@gmail.com` ad ogni ticket aperto in `supporto.py`.
- **`7bdd561` (14:46), `38bd7b7` (14:52), `ba12794` (14:58):** Nuova schermata **Login Dark Mode Minimal Executive** con blueprint campo da tennis neon, logo 145px e leggibilità box recupero password/lingua.
- **`95deb92` (16:55):** Estensione completa del design system **Dark Cockpit** a 18 file applicativi con riallineamento contrasti e navigazione.

#### 17–18 Novembre 2026 — Contrasto Globale, Digital Handshake K-Sport & Motore Ibrido Match ATP (13 commit)
- **`3acc8bc` (12:30):** Audit contrasto globale su 16 file e `.streamlit/config.toml` (eliminazione definitiva testi bianco-su-bianco e card illeggibili).
- **`9f186f3` (13:24), `d3b906b` (13:49), `66eebfa` (13:59), `ac0fefe` (14:20):** Implementazione completa **Digital Handshake & Coda Tagli GPS K-Sport** (`setup_coda_tagli_gps.sql`, dashboard Kanban To-Do List in Admin, integrazione in Sidebar, Home, Caricamento Dati, Carico Interno e Mobile Atleta, selettore tipologie per utente con voce custom).
- **`9ae938c` (16:59) & `b610dbe` (17:37):** Rimozione overlay `Press Enter to apply` (`InputInstructions`) e rafforzamento styling alert warning.
- **`c18d871` (17:13) & `04c34ca` (17:28):** Sync master database sessioni 15–16 Novembre con TTL snapshot e sync cloud cache LiveTennis Cobolli.
- **`731f285` (18:32):** Pulsante di chiamata istantanea **LiveTennis API** nel Pannello Admin per tutta la lista atleti (atleti non trovati invariati), **anteprima obbligatoria prima del salvataggio** e **contatore giornaliero delle chiamate API (`X/100`)** persistito localmente e su Supabase, con validatore rigoroso del nome (`_is_name_match`).
- **`28149db` (21:53) & `5c8a14b` (21:57):** Ridisegno anteprima centrata su **Data del Match + Avversario + Torneo** + ultime 5 partite già nel DB come riferimento + checkbox di selezione per match; fix parsing metriche annidate `overall` (`79.6%` TB, `62.7%` Set Decisivi) e fix rendering HTML grezzo (`_clean_html`).
- **`3685664` (22:16):** **Integrazione Gratuita Tennis Abstract + ESPN** (a **0 chiamate** sulla quota LiveTennis) per superare il blocco `403` del piano Free sui match conclusi:
  - Estrazione automatica dei match già giocati (incluso il match del giorno prima: *16/11/2026 vs Daniil Medvedev — Nitto ATP Finals, 7-6(4) 6-3, 125 pts, 85 min, 71 srv, 47 1ª, 24 2ª, 6 Ace, 0 DF, 9 Ace avv.*) con **tutte le 26 colonne identiche allo storico Excel** per le analisi incrociate GPS;
  - Data esatta del match risolta automaticamente da ESPN;
  - Deduplicazione sull'intero storico (486 match), checkbox intelligenti (spunta automatica solo sui nuovi match conclusi, deselezionati quelli futuri a `0 pts`) e invalidazione istantanea cache `load_cobolli_matches.clear()`.

---

## PARTE 3 — BILANCIO COMPLESSIVO: 28 OTTOBRE 2026 vs 18 NOVEMBRE 2026

| Dimensione | Stato Iniziale (28 Ottobre 2026) | Stato Attuale (18 Novembre 2026) |
| :--- | :--- | :--- |
| **Architettura Codice** | 1 file monolitico `app.py` (4.547 righe) | **32 file `.py` modulari (44.129 righe Python puro)** |
| **Ambiente & Deploy** | Solo locale su Mac (nessun Git) | **Produzione Cloud GitHub + Streamlit Cloud (69 commit su `main`)** |
| **Storage & Affidabilità Dati** | Solo `database_storico.csv` locale (~21 sessioni demo) | **701 sessioni GPS** su **Parquet + CSV + Cloud Binary Snapshot Supabase Zero-Latency** |
| **Moduli Sport Science** | Analisi GPS base (Match, Sessione, Settimana, Medie) | **Suite completa:** + Trend Stagionale (Monotonia/Strain), Carico Interno 70/30 & Wellness, Mini WebApp Smartphone, Test Fisici (22 protocolli + DSI), MOVE Tennis Test (6 indici), Calendario Medico/Fisio, Confronto Individuale, **62+ Moduli nel Manuale Report** |
| **Dati Match ATP & Analisi Incrociate** | Completamente assenti | **486 match storici** + **Statistiche Match Tennis ↔ GPS** + **Sync Automatico Ibrido (LiveTennis 100/gg + Tennis Abstract + ESPN a 0 chiamate)** con anteprima e selezione match |
| **Operatività Staff/Atleta** | Nessuna | **Digital Handshake Kanban K-Sport**, Promemoria Smartphone, Ticket Supporto con email automatica |
| **Reportistica PDF** | 5 export ReportLab base con bug colonne | **Motore PDF ad alta risoluzione** in parità grafica con il portale web + watermark forense IP |
| **Sicurezza, Privacy & IP** | Password hardcoded, no GDPR/IP, no audit | **Copyright, Clickwrap GDPR, Audit Trail doppio livello, Soft-Delete (GDPR Art. 9), Auto-refresh JWT, RBAC granulare** |
| **Design System & UX** | Streamlit standard con emoji | **Dark Cockpit Executive** ad alto contrasto, Zero-Emoji / Bootstrap Icons, Selettore Atleta Globale, **Notifiche Ibride (Modal + HUD)** |

> [!TIP]
> **Copia permanente salvata sul tuo Mac:** [MEMORANDUM_INTERVENTI_MOV3_ANALYTICS.md](file:///Users/riccardodimaio/webapp_tennis_gps/MEMORANDUM_INTERVENTI_MOV3_ANALYTICS.md)
