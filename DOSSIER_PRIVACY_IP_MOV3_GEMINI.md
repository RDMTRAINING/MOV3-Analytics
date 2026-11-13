# DOSSIER TECNICO & NORMATIVO: TUTELA IP, GDPR E ULTIMI AGGIORNAMENTI
**Piattaforme:** M0V3 Analytics Enterprise & FIR Rugby GPS Analysis Platform  
**Autore & Titolare IP:** Riccardo Di Maio — M0V3 S.r.l.  
**Destinatario:** Gemini Developer Context / Executive Report  
**Data di Rilascio:** 13 Novembre 2026 | Versione Normativa: `M0V3_IP_GDPR_v2.0` / `FIR_IP_GDPR_v2.0`

---

## 1. VISIONE D'INSIEME & OBIETTIVO DEL PROGETTO
Il sistema gestisce l'analisi prestazionale, telemetrica (GPS/IMU 10-18 Hz), neuromuscolare, cinetica e clinico-fisioterapica di atleti d'élite (Tennis Professionistico ATP/WTA e Nazionale Maggiore Federazione Italiana Rugby).

A causa della natura critica dei dati trattati (**dati biometrici, sanitari e cartelle cliniche protette dall'Art. 9 del Regolamento UE 2016/679 - GDPR**) e dell'elevato valore scientifico degli algoritmi proprietari sviluppati da **Riccardo Di Maio**, è stata implementata un'infrastruttura completa di:
1. **Tutela della Proprietà Intellettuale (IP)** a livello di sorgenti, interfaccia grafica Streamlit e reportistica PDF.
2. **Clickwrap Agreement bloccante al primo accesso**, vincolante sia per lo Staff (Tecnici, Medici, Fisioterapisti, Preparatori) sia per gli Atleti.
3. **Audit Trail e Tracciabilità Anti-Diffusione** su ogni esportazione documentale.

---

## 2. MODULO 1: TUTELA DELLA PROPRIETÀ INTELLETTUALE (IP) & BRANDING

### 2.1 Copyright Headers nei Codici Sorgente
Tutti i file Python (`.py`) del repository, sia nella cartella radice sia nelle directory `views/` e `parsers/`, includono in testa il commento ufficiale di riserva dei diritti:
```python
# Copyright 2026 Riccardo Di Maio - M0V3 S.r.l. Tutti i diritti riservati.
# Proprietary Sports Science & Clinical Performance Intelligence Architecture.
```

### 2.2 Footer Istituzionale Streamlit UI
Implementata la funzione modulare `render_m0v3_footer(is_sidebar=False)` disponibile sia in `utils.py` sia in `config.py` per garantire massima resilienza contro il caching dei moduli:
* **Allineamento Logo + Testo:** Caricamento automatico del logo circolare ufficiale `logo_mov3.png` in Base64 (con ricerca a cascata in `assets/`, directory principale e `data_supporto/`), affiancato da un fallback vettoriale SVG nativo.
* **Stringa Legale Ufficiale:**
  > `"© 2026 — Generato tramite tecnologia proprietaria Riccardo Di Maio & M0V3 S.r.l. - Tutti i diritti riservati"`
* **Punti di Iniezione:**
  - Nel footer fisso della barra laterale (`st.sidebar`) di navigazione in `app.py`.
  - A fondo pagina di ogni vista principale Desktop in `app.py`.
  - A fondo pagina della Mini-WebApp Mobile Smartphone in `views/atleta_mobile.py`.

### 2.3 Piè di Pagina nei Report PDF Esportabili (ReportLab)
In `pdf_generator.py`, la funzione `build_pdf_con_footer()` è stata estesa per applicare la nuova impaginazione di sicurezza su ogni singolo report generato (Match, Sessioni, Medie, Test Fisici, Calendario Medico, Trend):
* **Header Istituzionale:** Palette Dark Navy (`#0F172A`), Ciano M0V3 (`#0284C7`) e Smeraldo (`#10B981`).
* **Footer Sinistro:** Logo M0V3 ridimensionato (altezza 12–14pt) con stringa:
  > `"Generato tramite tecnologia proprietaria Riccardo Di Maio - M0V3 S.r.l. - Tutti i diritti riservati"`
* **Footer Destro (Audit Watermark Anti-Diffusione):**
  > `"Documento Riservato (Art. 9 GDPR) — Esportato da: {user_email} il {data_ora}   |   Pagina {d.page}"`
  *(Garantisce l'immediata individuazione del responsabile in caso di divulgazione non autorizzata o screenshot).*

---

## 3. MODULO 2: PRIVACY, GDPR (ART. 9) & CLICKWRAP AGREEMENT

### 3.1 Flusso di Routing & Login Interceptor (`app.py`)
Subito dopo l'autenticazione dell'utente e prima di mostrare qualsiasi dashboard analitica o il menu laterale, l'applicazione intercetta lo stato del profilo verificando `has_accepted_terms` (con fallback su `privacy_accettata`):
* **Se `True`:** Sblocco immediato dell'interfaccia (Desktop per Staff o Mobile per Atleta).
* **Se `False`:** Blocco totale della navigazione e rendering **esclusivo** della schermata di accettazione con il logo istituzionale e il testo integrale dei 3 articoli operativi.

### 3.2 I Tre Pilastri Contrattuali del Disciplinare
1. **Proprietà Intellettuale e Licenza d'Uso Limitata:**  
   Protezione esplicita di architetture DB, logiche di calcolo del micro/macrociclo, algoritmi proprietari (*Readiness SWC, Pure I:E Ratio, Metriche Per-Point, ACWR Uncoupled EWMA, ripartizione carichi 70/30 e matrici di correlazione clinica*) e layout visuali. Divieto assoluto di reverse engineering, copia, screenshot a fini divulgativi o cessione a terzi.
2. **Trattamento dei Dati Sensibili, Biometrici e Sanitari (Art. 9 GDPR):**  
   Vincolo al segreto professionale per lo Staff Tecnico/Medico e autorizzazione al conferimento dei parametri di benessere e sRPE da parte dell'atleta a fini di prevenzione infortuni e monitoraggio del recupero.
3. **Sicurezza Credenziali e Tracciabilità:**  
   Responsabilità nominale dell'account e marcatura forense dei report esportati con email e timestamp.

### 3.3 Download Documentale & Sblocco
* **Pulsante di Download:** `st.download_button` per scaricare il PDF ufficiale `Atto_Privacy_IP_MOV3_v2.pdf`. In assenza del file statico su disco, la funzione `genera_pdf_informativa_privacy_mov3()` in `pdf_generator.py` lo rigenera in tempo reale in memoria.
* **Checkbox Vincolante:**
  > *"Dichiaro di aver letto, compreso e accettato i Termini d'Uso, i vincoli di Proprietà Intellettuale (Tecnologia Riccardo Di Maio — M0V3 S.r.l.) e le direttive GDPR sulla Privacy dei dati biometrici e sanitari."*
* **Pulsante di Sblocco:** Disabilitato finché la casella non è spuntata. Al clic, salva su Supabase:
  - `has_accepted_terms = True`
  - `privacy_accettata = True`
  - `terms_accepted_at = "<TIMESTAMP ISO>"`
  - `terms_version = "M0V3_IP_GDPR_v2.0"`
  ed esegue `st.rerun()`.

### 3.4 Gestione in Profilo Personale & Pannello Admin
* **`views/profilo.py`:**
  - Badge verde: `"Termini IP & GDPR Accettati il {terms_accepted_at}"`.
  - Pulsante per scaricare in qualsiasi momento copia ufficiale del PDF sottoscritto.
  - Possibilità per l'utente di revocare il consenso (con reindirizzamento al blocco contrattuale).
* **`views/admin.py`:**
  - Colonna `"Stato Privacy & IP"` nella tabella riassuntiva di tutti gli utenti (`✓ Accettati (data/ora)` oppure `In attesa di primo accesso`).
  - Pulsante per Super-Admin: `[!] Resetta Termini (Richiedi Nuovo Accesso)` per forzare la ri-sottoscrizione nominale in caso di rilascio di una nuova versione normativa.

---

## 4. REGISTRO DELLE ULTIME MODIFICHE & RISOLUZIONI TECNICHE

### 4.1 Correzione Piè di Pagina FIR Rugby (`rugby_fir_app`)
* **Problema:** Un estratto PDF scaricato continuava a mostrare in scuro la vecchia dicitura `"Generato tramite tecnologia proprietaria RDM - Tutti i diritti riservati"`.
* **Causa:** Il PDF statico di nomina (`Atto_Nomina_Privacy_FIR_RDM_v2.pdf`) conteneva la vecchia impaginazione compilata in una sessione precedente.
* **Soluzione:** Rigenerato il documento con piè di pagina ultra-chiaro (`#CBD5E1`) e dicitura esatta `"MOV3 S.r.l. - Tutti i diritti riservati"`.
* **Deploy:** Pushed su GitHub `FIR---GPS-Nazionale-Maggiore` (commit `f7df071`).

### 4.2 Risoluzione `ImportError` su Streamlit Cloud (`MOV3-Analytics`)
* **Problema:** All'avvio su Streamlit Cloud, l'import `from utils import (..., render_m0v3_footer)` generava un `ImportError` bloccante a riga 22.
* **Causa:** L'interprete Python di Streamlit riutilizzava il modulo `utils` già presente in `sys.modules` prima del reload, non trovando il nuovo simbolo `render_m0v3_footer`. Inoltre, in alcune versioni di PostgREST su cloud, il path `postgrest._sync.request_builder` poteva variare.
* **Soluzioni Applicate:**
  1. Definita la funzione `render_m0v3_footer()` sia in `config.py` sia in `utils.py`.
  2. Aggiunto in `app.py` un controllo con `importlib.reload(utils)` e fallback `except ImportError: from config import render_m0v3_footer`.
  3. Protetta l'importazione di `SyncQueryRequestBuilder` con blocchi `try/except` a cascata per totale indipendenza dalla versione di PostgREST.
  4. Inserito `[client] showErrorDetails = true` in `.streamlit/config.toml` per visualizzare i dettagli non censurati dei log di sistema.
* **Deploy:** Pushed su GitHub `MOV3-Analytics` (commit `9b7ef64`).

---

## 5. STATO ATTUALE DEI REPOSITORY

| Repository | Branch | Ultimo Commit | Stato Deploy |
|---|---|---|---|
| **`FIR---GPS-Nazionale-Maggiore`** | `main` | `f7df071` | Sincronizzato & Live |
| **`MOV3-Analytics`** | `main` | `9b7ef64` | Sincronizzato & Live |

Tutti i requisiti normativi GDPR e di tutela della proprietà intellettuale sono pienamente operativi e verificati.
