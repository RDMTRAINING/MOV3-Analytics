import base64
import os
import streamlit as st
import plotly.graph_objects as go
import plotly.io as pio

DB_PATH = "database_storico.csv"
DB_PARQUET_PATH = "database_storico.parquet"
LEGENDA_ACWR = "Verde: 80-125% della media  |  Blu: sotto 80%  |  Rosso: sopra 125%"
SUPPORT_EMAIL = "mov3project26@gmail.com"

def setup_plotly_theme():
    pio.templates["m0v3"] = go.layout.Template(layout=dict(
        font=dict(family="Inter, -apple-system, BlinkMacSystemFont, sans-serif", color="#0f172a", size=12),
        title=dict(font=dict(family="Inter, -apple-system, BlinkMacSystemFont, sans-serif", color="#0f172a", size=16)),
        colorway=["#0ea5e9", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6"],
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        hoverlabel=dict(
            bgcolor="#0f172a",
            bordercolor="#334155",
            font=dict(family="Inter, sans-serif", color="#f8fafc", size=12)
        ),
        xaxis=dict(
            gridcolor="#f1f5f9",
            linecolor="#e2e8f0",
            tickfont=dict(family="Inter, sans-serif", color="#64748b", size=11),
            title_font=dict(family="Inter, sans-serif", color="#475569", size=12)
        ),
        yaxis=dict(
            gridcolor="#f1f5f9",
            zerolinecolor="#e2e8f0",
            linecolor="#e2e8f0",
            tickfont=dict(family="Inter, sans-serif", color="#64748b", size=11),
            title_font=dict(family="Inter, sans-serif", color="#475569", size=12)
        ),
        legend=dict(
            font=dict(family="Inter, sans-serif", color="#475569", size=12),
            bgcolor="rgba(255,255,255,0)"
        )
    ))
    pio.templates.default = "m0v3"

LOGO_PATH = "logo.png"
LOGO_CIRCULAR_PATH = "logo_circular.png" if os.path.exists("logo_circular.png") else LOGO_PATH

# =========================================================================
# MOTORE DI TRADUZIONE (MULTILINGUA COMPLETO)
# =========================================================================
LANG = {
    "IT": {
        "nav_title": "### Navigazione", "home": "Home", "analysis": "Analisi", "match_analysis": "Analisi Match",
        "averages": "Medie", "avg_title": "Analisi Medie e Confronti", 
        "weekly_trend": "Trend Settimanale",
        "home_weekly_desc": "Analizza il carico complessivo settimanale suddiviso per giorni dal lunedì alla domenica.",
        "avg_desc": "Confronta il carico medio tra le diverse tipologie di sessione o metti a confronto due atleti.",
        "tab_sing": "Analisi Singolo Atleta", "tab_comp": "Testa a Testa Medie", "tab_comp_week": "Testa a Testa Settimana", "tab_roster_ranking": "Ranking Roster Atleti", "tab_distribuzione_roster": "Distribuzione Lavoro Roster", "tab_stress_roster": "Stress Roster 8 settimane",
        "data_management": "Gestione Dati e CSV", "data_upload": "Caricamento Dati", "data_generator": "Generatore Dati",
        "file_management": "Gestione File Caricati", "admin_panel": "Pannello Admin", "profile": "Profilo Personale",
        "logout": "Logout", "welcome": "Benvenuto in M0V3 Analytics",
        "welcome_sub": "Seleziona una delle aree sottostanti per iniziare a navigare nella piattaforma.",
        "home_match_desc": "Visualizza i grafici e i report delle prestazioni in partita rispetto alle medie storiche.",
        "home_storico_desc": "Analizza l'andamento e la timeline storica delle prestazioni in partita.",
        "home_medie_desc": "Confronta il carico medio tra le diverse sessioni o metti a confronto due atleti.",
        "home_manuale_desc": "Guida enciclopedica e scientifica a tutti i 45 moduli di analisi abilitabili nel sistema M0V3.",
        "home_upload_desc": "Carica nuovi file CSV dai sistemi GPS per alimentare il database storico della piattaforma.",
        "home_gen_desc": "Simula il carico di sessioni senza GPS partendo dallo storico matematico dell'atleta.",
        "home_file_desc": "Controlla lo storico dei caricamenti ed elimina le sessioni inserite per errore o clonate.",
        "home_prof_desc": "Gestisci le impostazioni dell'account, la password e le preferenze sulla Privacy.",
        "home_admin_desc": "Gestisci atleti, profili utente, permessi visivi e mappature CSV per l'intero sistema.",
        "go_to": "Vai a", "user": "Utente", "role": "Ruolo", "select": "Seleziona...",
        "prof_title": "Profilo Personale", "prof_info": "Da qui puoi aggiornare la tua password di accesso alla piattaforma.",
        "new_pwd": "Nuova Password (minimo 6 caratteri)", "conf_pwd": "Conferma Nuova Password", "save_pwd": "Salva Nuova Password",
        "err_pwd_len": "Errore: La password deve contenere almeno 6 caratteri.", "err_pwd_match": "Errore: Le due password non coincidono.",
        "succ_pwd": "Password aggiornata con successo!", "privacy_title": "### Gestione Dati e Privacy (Diritto all'Oblio)",
        "privacy_warn": "ATTENZIONE: Cliccando il pulsante sottostante revocherai il consenso al trattamento dei dati. Il tuo account, le regole di mappatura e i permessi verranno eliminati definitivamente. Questa azione è irreversibile.",
        "privacy_check": "Sono consapevole che l'azione è irreversibile e voglio eliminare definitivamente il mio account.",
        "del_acc_btn": "Elimina Account e Revoca Consenso",
        "admin_title": "Pannello di Controllo Super-Admin", "tab_atl": "Gestione Atleti", "tab_usr": "Profili & Accessi",
        "tab_rep": "Moduli Report", "tab_map": "Mappatura CSV", "tab_sup": "Supporto & Ticket", "add_atl": "### Aggiungi Nuovo Giocatore",
        "atl_name": "Nome Atleta", "atl_surname": "Cognome Atleta", "btn_add_atl": "Crea Atleta", "curr_atl": "### Parco Giocatori Attuale",
        "del_atl": "### Rimuovi Giocatore", "warn_del_atl": "Attenzione: l'eliminazione di un giocatore rimuoverà automaticamente anche i permessi associati.",
        "sel_del_atl": "Seleziona l'atleta da rimuovere", "btn_del_def": "Elimina Definitivamente",
        "add_usr": "### Crea Nuovo Profilo Utente", "email_new": "Email del nuovo utente", "assign_role": "Assegna Ruolo",
        "btn_add_usr": "Crea Utente", "mod_usr": "### Modifica Ruoli, Atleti e Sicurezza", "sel_usr": "Seleziona Utente",
        "usr_role": "Ruolo Utente", "vis_atl": "Giocatori visibili", "btn_save_perm": "Salva Permessi",
        "btn_reset_pwd": "Rigenera Password Provvisoria", "btn_email_reset": "Invia Link Reset via Email",
        "rep_mng": "### Gestione Visibilità Grafici per Utente", "rep_info": "Abilita o disabilita i singoli moduli grafici in base al profilo.",
        "sel_usr_rep": "Seleziona Utente da configurare", "btn_save_rep": "Salva Configurazione Report",
        "map_mng": "### Configurazione Tracciati CSV e Formule", "map_info": "Associa le colonne del CSV o inserisci formule (es. =[Colonna1]+[Colonna2]) per ricavare i parametri M0V3.",
        "sel_usr_map": "Seleziona l'Utente a cui associare il tracciato", "upload_sample": "Carica un CSV di esempio di",
        "map_assoc": "Associa i parametri M0V3 alle colonne del file o usa una formula personalizzata.",
        "req_param": "M0V3 richiede:", "not_present": "Non presente", "custom_formula": "Formula Personalizzata...",
        "btn_save_map": "Salva Mappatura",
        "up_title": "Ingestione Dati GPS", "up_admin_info": "Sei loggato come Super-Admin. Puoi caricare i dati per conto di un altro utente applicando la sua specifica mappatura CSV.",
        "up_delegate": "Carica dati per conto dell'utente (Mappatura CSV da applicare):", "up_my_map": "Usa la mia mappatura Super-Admin (Standard)",
        "up_no_atl": "Non hai atleti associati al profilo per poter caricare i dati. Contatta l'amministratore.",
        "up_no_map": "Non è stata configurata alcuna mappatura CSV per l'account selezionato. Il sistema cercherà le colonne standard.",
        "drag_csv": "Trascina qui i file CSV", "ctx_assign": "Contesto e Assegnazione:", "assign_to": "Assegna al Giocatore",
        "surface": "Campo", "environment": "Ambiente", "sparring": "Sparring (min)", "sess_type": "Tipo Sessione",
        "add_new": "+ Aggiungi nuova...", "spec_new": "Specifica nuova", "btn_process": "Elabora e Salva",
        "gen_title": "Generatore Dati Simulati", "gen_desc": "Usa questo strumento per stimare il carico di una sessione quando il GPS non era disponibile o non ha registrato correttamente. Il sistema userà le medie storiche dell'atleta (escludendo i dati finti) per calcolare i valori.",
        "gen_no_data": "Nessun dato storico disponibile per i tuoi atleti per creare simulazioni.", "sel_player": "Seleziona Giocatore",
        "sess_date": "Data Sessione", "sess_name": "Nome Identificativo Sessione", "duration": "Durata (minuti)",
        "context": "**Contesto:**", "btn_generate": "Genera e Salva nel Database",
        "sim_warn": "Dati generati e salvati. NOTA: L'atleta non aveva precedenti sessioni di questo tipo. Sono state utilizzate le medie generali.",
        "sim_succ": "Dati generati e salvati con successo per",
        "fm_title": "Gestione Dati Caricati", "fm_glob_hist": "### Cronologia Caricamenti Globali", "fm_pers_hist": "### Cronologia Caricamenti Personali",
        "fm_no_sess": "Nessuna sessione trovata.", "fm_del_title": "### Elimina Caricamento o Simulazione",
        "fm_sel_del": "Seleziona file o simulazione da eliminare", "fm_btn_del": "Elimina Definitivamente", "fm_del_succ": "Record eliminato con successo dal database globale!",
        "am_title": "M0V3 Match Analysis", "am_desc": "Seleziona i parametri per analizzare le prestazioni della partita rispetto alle medie storiche.",
        "am_no_db": "Il database è vuoto. Vai su 'Caricamento Dati'.", "am_no_match": "Nessun dato di tipo 'Match' trovato nel database.",
        "am_filters": "Filtri di Ricerca", "am_sel_match": "Seleziona la Partita", "am_glob_team": "Visualizzazione Globale Team",
        "am_no_data_ply": "Nessun dato trovato per questo giocatore in questa specifica partita.", "am_surf": "**Superficie:**",
        "am_env": "**Ambiente:**", "am_spa": "**Sparring:**", "am_sim_alert": "**ATTENZIONE: Questa sessione è stata generata matematicamente dal sistema.**",
        "am_btn_pdf": "Crea PDF", "am_indoor_warn": "Questa sessione è stata registrata **Indoor**. I parametri GPS legati allo spostamento e al segnale satellitare non sono registrati e l'analisi non è disponibile.",
        "am_table_met": "Metrica", "am_table_ss": "Session Score", "am_table_sa": "Session Average", "am_table_pd": "Percentage difference",
        "am_chart_vol": "Carico Globale (Volumi)", "am_chart_imu": "Eventi Meccanici IMU", "am_chart_pct": "Indici e Tempi di Recupero (Densità %)",
        "am_leg_ply": "Atleta (Sessione)", "am_leg_avg": "Media Storica"
    },
    "EN": {
        "nav_title": "### Navigation", "home": "Home", "analysis": "Analysis", "match_analysis": "Match Analysis",
        "averages": "Averages", "avg_title": "Averages & Comparisons",
        "weekly_trend": "Weekly Trend",
        "home_weekly_desc": "Analyze the total weekly load divided by days from Monday to Sunday.",
        "avg_desc": "Compare average loads across session types or set up a head-to-head comparison between athletes.",
        "tab_sing": "Single Athlete Analysis", "tab_comp": "Head-to-Head (Averages)", "tab_comp_week": "Head-to-Head (Weekly)", "tab_roster_ranking": "Athlete Roster Ranking", "tab_distribuzione_roster": "Roster Workload Distribution", "tab_stress_roster": "Roster Stress 8 Weeks",
        "data_management": "Data & CSV Management", "data_upload": "Data Upload", "data_generator": "Data Generator",
        "file_management": "Uploaded Files", "admin_panel": "Admin Panel", "profile": "Personal Profile",
        "logout": "Logout", "welcome": "Welcome to M0V3 Analytics",
        "welcome_sub": "Select one of the areas below to start navigating the platform.",
        "home_match_desc": "View charts and performance reports of matches compared to historical averages.",
        "home_storico_desc": "Analyze the trend and historical timeline of match performances.",
        "home_medie_desc": "Compare average load across sessions or set up a head-to-head.",
        "home_manuale_desc": "Encyclopedic and scientific guide to all 45 analytical modules assignable in the M0V3 system.",
        "home_upload_desc": "Upload new CSV files from GPS systems to feed the platform's historical database.",
        "home_gen_desc": "Simulate session loads without GPS starting from the athlete's mathematical history.",
        "home_file_desc": "Check upload history and delete erroneously inserted or cloned sessions.",
        "home_prof_desc": "Manage account settings, password, and Privacy preferences.",
        "home_admin_desc": "Manage athletes, user profiles, visual permissions, and CSV mappings for the whole system.",
        "go_to": "Go to", "user": "User", "role": "Role", "select": "Select...",
        "prof_title": "Personal Profile", "prof_info": "From here you can update your platform access password.",
        "new_pwd": "New Password (minimum 6 characters)", "conf_pwd": "Confirm New Password", "save_pwd": "Save New Password",
        "err_pwd_len": "Error: Password must contain at least 6 characters.", "err_pwd_match": "Error: The two passwords do not match.",
        "succ_pwd": "Password updated successfully!", "privacy_title": "### Data Management & Privacy (Right to be Forgotten)",
        "privacy_warn": "WARNING: By clicking the button below, you revoke consent to data processing. Your account, mapping rules, and permissions will be permanently deleted. This action is irreversible.",
        "privacy_check": "I am aware that the action is irreversible and I want to permanently delete my account.",
        "del_acc_btn": "Delete Account & Revoke Consent",
        "admin_title": "Super-Admin Control Panel", "tab_atl": "Athlete Management", "tab_usr": "Profiles & Access",
        "tab_rep": "Report Modules", "tab_map": "CSV Mapping", "tab_sup": "Support & Tickets", "add_atl": "### Add New Player",
        "atl_name": "First Name", "atl_surname": "Last Name", "btn_add_atl": "Create Athlete", "curr_atl": "### Current Player Roster",
        "del_atl": "### Remove Player", "warn_del_atl": "Warning: deleting a player will automatically remove associated permissions.",
        "sel_del_atl": "Select player to remove", "btn_del_def": "Permanently Delete",
        "add_usr": "### Create New User Profile", "email_new": "New user email", "assign_role": "Assign Role",
        "btn_add_usr": "Create User", "mod_usr": "### Modify Roles, Athletes & Security", "sel_usr": "Select User",
        "usr_role": "User Role", "vis_atl": "Visible Players", "btn_save_perm": "Save Permissions",
        "btn_reset_pwd": "Regenerate Temporary Password", "btn_email_reset": "Send Reset Link via Email",
        "rep_mng": "### Manage Graph Visibility per User", "rep_info": "Enable or disable individual graphic modules based on profile.",
        "sel_usr_rep": "Select User to configure", "btn_save_rep": "Save Report Configuration",
        "map_mng": "### Custom CSV Tracking & Formulas Configuration", "map_info": "Map a user's CSV columns or insert formulas (e.g. =[Col1]+[Col2]) to calculate M0V3 parameters.",
        "sel_usr_map": "Select User to associate tracking to", "upload_sample": "Upload a sample CSV for",
        "map_assoc": "Associate M0V3 parameters to the uploaded file columns or use a custom formula.",
        "req_param": "M0V3 requires:", "not_present": "Not present", "custom_formula": "Custom Formula...",
        "btn_save_map": "Save Mapping",
        "up_title": "GPS Data Ingestion", "up_admin_info": "You are logged in as Super-Admin. You can upload data on behalf of another user applying their specific CSV mapping.",
        "up_delegate": "Upload data on behalf of user (CSV Mapping to apply):", "up_my_map": "Use my Super-Admin mapping (Standard)",
        "up_no_atl": "You have no athletes associated with your profile to upload data. Contact the administrator.",
        "up_no_map": "No CSV mapping configured for the selected account. The system will look for standard columns.",
        "drag_csv": "Drag CSV files here", "ctx_assign": "Context and Assignment:", "assign_to": "Assign to Player",
        "surface": "Surface", "environment": "Environment", "sparring": "Sparring (min)", "sess_type": "Session Type",
        "add_new": "+ Add new...", "spec_new": "Specify new", "btn_process": "Process and Save",
        "gen_title": "Simulated Data Generator", "gen_desc": "Use this tool to estimate a session load when GPS was unavailable or failed to record. The system will use the athlete's historical averages (excluding fake data) to calculate values.",
        "gen_no_data": "No historical data available for your athletes to create simulations.", "sel_player": "Select Player",
        "sess_date": "Session Date", "sess_name": "Session Identifier Name", "duration": "Duration (minutes)",
        "context": "**Context:**", "btn_generate": "Generate and Save to Database",
        "sim_warn": "Data generated and saved. NOTE: The athlete had no previous sessions of this type. General averages were used.",
        "sim_succ": "Data successfully generated and saved for",
        "fm_title": "Uploaded Data Management", "fm_glob_hist": "### Global Upload History", "fm_pers_hist": "### Personal Upload History",
        "fm_no_sess": "No sessions found.", "fm_del_title": "### Delete Upload or Simulation",
        "fm_sel_del": "Select file or simulation to delete", "fm_btn_del": "Permanently Delete", "fm_del_succ": "Record successfully deleted from global database!",
        "am_title": "M0V3 Match Analysis", "am_desc": "Select parameters to analyze match performance against historical averages.",
        "am_no_db": "Database is empty. Go to 'Data Upload'.", "am_no_match": "No 'Match' type data found in database.",
        "am_filters": "Search Filters", "am_sel_match": "Select Match", "am_glob_team": "Global Team View",
        "am_no_data_ply": "No data found for this player in this specific match.", "am_surf": "**Surface:**",
        "am_env": "**Environment:**", "am_spa": "**Sparring:**", "am_sim_alert": "**WARNING: This session was mathematically generated by the system.**",
        "am_btn_pdf": "Create PDF", "am_indoor_warn": "This session was recorded **Indoor**. GPS parameters related to movement and satellite signal are not recorded and analysis is unavailable.",
        "am_table_met": "Metric", "am_table_ss": "Session Score", "am_table_sa": "Session Average", "am_table_pd": "Percentage difference",
        "am_chart_vol": "Global Load (Volumes)", "am_chart_imu": "Mechanical Events IMU", "am_chart_pct": "Recovery Indices and Times (Density %)",
        "am_leg_ply": "Athlete (Session)", "am_leg_avg": "Historical Average"
    }
}

if 'lang' not in st.session_state: st.session_state['lang'] = 'IT'

def tr(it_text, en_text):
    """Returns it_text when current language is IT, otherwise en_text."""
    return en_text if st.session_state.get('lang', 'IT') == 'EN' else it_text

@st.cache_data
def get_base64_image(image_file):
    if os.path.exists(image_file):
        with open(image_file, "rb") as file:
            return base64.b64encode(file.read()).decode()
    return ""

def add_custom_css(image_file):
    encoded_string = get_base64_image(image_file)
    st.markdown(
    f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap');
    @import url('https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css');
    
    /* Font Globale Unificato Inter per l'intera Web App */
    html, body, [class*="css"], [class*="st-"], 
    h1, h2, h3, h4, h5, h6, p, span, div, label, 
    button, input, select, textarea, table, th, td, 
    [data-testid*="st"], [data-baseweb], [data-baseweb*="tab"], [data-baseweb*="select"] {{
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
    }}

    /* Preserva icone Material e Bootstrap */
    .material-symbols-rounded, [data-testid="stIconMaterial"] {{
        font-family: 'Material Symbols Rounded' !important;
    }}
    i.bi, .bi, [class^="bi-"], [class*=" bi-"] {{
        font-family: 'bootstrap-icons' !important;
    }}

    /* Preserva font monospace per codice tecnico */
    code, pre, kbd, samp, .font-mono, [data-testid="stCodeBlock"] * {{
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace !important;
    }}
    
    /* Nasconde elementi nativi Streamlit (Deploy, Footer, Linea colorata in alto) */
    #MainMenu {{visibility: hidden;}}
    footer {{visibility: hidden;}}
    header[data-testid="stHeader"] {{background: transparent !important;}}
    .stDeployButton {{display:none;}}
    
    /* Sfondo principale grigio ardesia chiarissimo e Sidebar Blu Navy scuro */
    .stApp {{ background-color: #f4f7f9 !important; }}
    [data-testid="stSidebar"] {{ background-color: #0A192F !important; border-right: 1px solid #1e2d4a; }}
    [data-testid="stSidebar"] .stRadio label, [data-testid="stSidebar"] .stRadio div {{ color: #e6f1ff !important; }}

    /* Struttura Sidebar: Header Fisso Sticky in cima + Body Scorrevole fluido */
    [data-testid="stSidebar"] div[data-testid="stVerticalBlockBorderWrapper"] {{
        background-color: transparent !important;
        border: none !important;
        box-shadow: none !important;
        padding: 0 !important;
    }}
    [data-testid="stSidebarContent"] {{
        overflow-y: auto !important;
        overflow-x: hidden !important;
        padding-top: 0 !important;
        padding-bottom: 2.5rem !important;
        height: 100% !important;
        scrollbar-width: thin !important;
        scrollbar-color: rgba(56, 189, 248, 0.3) transparent !important;
    }}
    [data-testid="stSidebarContent"]::-webkit-scrollbar {{
        width: 6px;
    }}
    [data-testid="stSidebarContent"]::-webkit-scrollbar-thumb {{
        background: rgba(56, 189, 248, 0.3);
        border-radius: 4px;
    }}
    [data-testid="stSidebarUserContent"] {{
        padding-top: 0 !important;
        overflow: visible !important;
    }}
    [data-testid="stSidebarUserContent"] > div[data-testid="stVerticalBlock"] {{
        padding-top: 0 !important;
        overflow: visible !important;
    }}
    
    /* 1. HEADER FISSO (Logo MOV3 + Selettore Atleta): Fisso/Sticky in cima */
    div.st-key-sidebar_fixed_header,
    div[class*="st-key-sidebar_fixed_header"],
    div[data-testid="stVerticalBlockBorderWrapper"]:has(div[class*="st-key-sidebar_fixed_header"]),
    [data-testid="stSidebarUserContent"] > div[data-testid="stVerticalBlock"] > div:first-child,
    div[data-testid="stSidebar"] div[data-testid="stVerticalBlock"]:has(> div[class*="st-key-sidebar_fixed_header"]) > div:first-child {{
        position: -webkit-sticky !important;
        position: sticky !important;
        top: 0 !important;
        z-index: 99999 !important;
        background-color: #0A192F !important;
        padding-top: 1.25rem !important;
        padding-bottom: 12px !important;
        margin-bottom: 10px !important;
        border-bottom: 1px solid rgba(255, 255, 255, 0.12) !important;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.45) !important;
        width: 100% !important;
        box-sizing: border-box !important;
    }}
    div.st-key-sidebar_fixed_header img,
    div[class*="st-key-sidebar_fixed_header"] img {{
        width: 145px !important;
        max-width: 85% !important;
        height: auto !important;
        display: block !important;
        margin: 0 auto !important;
    }}
    
    /* Elimina definitivamente qualsiasi sfondo bianco da iframe e custom components nella sidebar */
    [data-testid="stSidebar"] iframe,
    [data-testid="stSidebar"] div[data-testid="stCustomComponentV1"],
    [data-testid="stSidebar"] div[data-testid="stCustomComponentV1"] iframe,
    [data-testid="stSidebar"] .element-container iframe {{
        background-color: transparent !important;
        background: transparent !important;
        color-scheme: dark !important;
    }}
    
    /* Stile Dark per Pulsanti nella Sidebar (Vista Smartphone e Logout) */
    [data-testid="stSidebar"] .stButton > button,
    [data-testid="stSidebar"] .stButton > button[kind="secondary"],
    [data-testid="stSidebar"] div.stButton > button {{
        background-color: rgba(255, 255, 255, 0.05) !important;
        color: #cbd5e1 !important;
        border: 1px solid rgba(255, 255, 255, 0.12) !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        font-size: 13px !important;
        padding: 8px 14px !important;
        transition: all 0.2s ease !important;
    }}
    [data-testid="stSidebar"] .stButton > button:hover,
    [data-testid="stSidebar"] .stButton > button[kind="secondary"]:hover,
    [data-testid="stSidebar"] div.stButton > button:hover {{
        background-color: rgba(14, 165, 233, 0.15) !important;
        color: #38bdf8 !important;
        border-color: rgba(56, 189, 248, 0.4) !important;
    }}
    
    /* Filigrana centrale discreta */
    [data-testid="stAppViewContainer"]::before {{
        content: ""; background-image: url(data:image/png;base64,{encoded_string});
        background-size: 30%; background-position: center; background-repeat: no-repeat;
        background-attachment: fixed; opacity: 0.03; top: 0; left: 0; bottom: 0; right: 0;
        position: fixed; z-index: 0; pointer-events: none; 
    }}
    
    /* Stile Card Moderne (Contenitori con bordo) */
    div[data-testid="stVerticalBlockBorderWrapper"] {{
        background-color: #ffffff !important;
        border-radius: 12px !important;
        border: 1px solid #e2e8f0 !important;
        box-shadow: 0 2px 6px -1px rgba(15, 23, 42, 0.04), 0 1px 3px -1px rgba(15, 23, 42, 0.02) !important;
        padding: 18px !important;
    }}
    
    /* Stile Pulsanti Enterprise M0V3 */
    .stButton > button, .stDownloadButton > button {{
        border-radius: 8px !important;
        font-weight: 700 !important;
        font-size: 13px !important;
        letter-spacing: 0.2px !important;
        transition: all 0.15s ease-in-out !important;
    }}
    .stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"] {{
        background-color: #0ea5e9 !important;
        border-color: #0ea5e9 !important;
        color: #ffffff !important;
        box-shadow: 0 2px 4px rgba(14, 165, 233, 0.2) !important;
    }}
    .stButton > button[kind="primary"]:hover, .stDownloadButton > button[kind="primary"]:hover {{
        background-color: #0284c7 !important;
        border-color: #0284c7 !important;
    }}
    .stButton > button[kind="secondary"] {{
        background-color: #ffffff !important;
        border: 1px solid #cbd5e1 !important;
        color: #0f172a !important;
    }}
    .stButton > button[kind="secondary"]:hover {{
        border-color: #0ea5e9 !important;
        color: #0ea5e9 !important;
        background-color: #f8fafc !important;
    }}

    /* Stile Tabs Moderne */
    button[data-baseweb="tab"] {{
        font-weight: 700 !important;
        font-size: 14px !important;
        color: #64748b !important;
        padding: 10px 20px !important;
        letter-spacing: 0.2px !important;
    }}
    button[data-baseweb="tab"][aria-selected="true"] {{
        color: #0ea5e9 !important;
        border-bottom-color: #0ea5e9 !important;
    }}

    /* Stile Navigazione Tab M0V3 Executive (Persistente e Reattivo) */
    div[data-testid="stSegmentedControl"] {{
        background: #f8fafc !important;
        border: 1px solid #e2e8f0 !important;
        border-radius: 10px !important;
        padding: 4px !important;
        margin-top: 4px !important;
        margin-bottom: 16px !important;
        gap: 6px !important;
        box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04) !important;
    }}
    div[data-testid="stSegmentedControl"] button {{
        border-radius: 7px !important;
        font-family: 'Inter', sans-serif !important;
        font-weight: 700 !important;
        font-size: 13.5px !important;
        color: #475569 !important;
        border: 1px solid transparent !important;
        padding: 8px 16px !important;
        transition: all 0.15s ease-in-out !important;
        background: transparent !important;
    }}
    div[data-testid="stSegmentedControl"] button:hover {{
        color: #0284c7 !important;
        background: rgba(14, 165, 233, 0.08) !important;
        border-color: rgba(14, 165, 233, 0.2) !important;
    }}
    div[data-testid="stSegmentedControl"] button[aria-checked="true"],
    div[data-testid="stSegmentedControl"] button[data-checked="true"] {{
        background: #0ea5e9 !important;
        color: #ffffff !important;
        font-weight: 800 !important;
        box-shadow: 0 2px 8px -1px rgba(14, 165, 233, 0.45) !important;
        border-color: #0284c7 !important;
    }}

    /* Stile Selettori e Tendine MOV3 Executive (Dropdowns, MultiSelect, DateInput) */
    div[data-testid="stSelectbox"] > div > div,
    div[data-testid="stDateInput"] > div > div,
    div[data-testid="stMultiSelect"] > div > div {{
        border-radius: 10px !important;
        border: 1.5px solid #0ea5e9 !important;
        background-color: #ffffff !important;
        font-weight: 700 !important;
        font-size: 14px !important;
        color: #0f172a !important;
        box-shadow: 0 2px 6px rgba(14, 165, 233, 0.08) !important;
        transition: all 0.2s ease-in-out !important;
        min-height: 42px !important;
    }}
    div[data-testid="stSelectbox"] > div > div:hover,
    div[data-testid="stDateInput"] > div > div:hover,
    div[data-testid="stMultiSelect"] > div > div:hover {{
        border-color: #0284c7 !important;
        box-shadow: 0 4px 12px rgba(14, 165, 233, 0.22) !important;
    }}
    div[data-testid="stSelectbox"] label,
    div[data-testid="stDateInput"] label,
    div[data-testid="stMultiSelect"] label {{
        font-weight: 800 !important;
        font-size: 11.5px !important;
        text-transform: uppercase !important;
        letter-spacing: 0.5px !important;
        color: #475569 !important;
    }}

    .report-table table, .report-table th, .report-table td {{ font-size: 14px !important; font-weight: bold !important; font-family: 'Inter', sans-serif !important; }}
    @media screen {{ .print-only {{ display: none !important; }} }}
    @media print {{
        @page {{ size: A4 landscape; margin: 10mm; }}
        .no-print, [data-testid="stSidebar"], header[data-testid="stHeader"], 
        div[data-testid="stSelectbox"], button, div[data-testid="stAlert"] {{ display: none !important; }}
        [data-testid="stAppViewContainer"]::before {{ display: none !important; }}
        .print-only {{ display: block !important; }}
        .page-break {{ break-before: page !important; page-break-before: always !important; margin: 0 !important; padding: 0 !important; }}
        body, .stApp {{ background-color: white !important; color: black !important; zoom: 0.85 !important; }}
        .block-container {{ padding-top: 0rem !important; padding-bottom: 0rem !important; max-width: 100% !important; }}
        div[data-testid="stVerticalBlock"] {{ gap: 0.2rem !important; }}
        div[data-testid="stVerticalBlock"] > div {{ padding-bottom: 0rem !important; padding-top: 0rem !important; }}
        h3 {{ margin-top: 0rem !important; margin-bottom: 25px !important; }}
        .report-table, .report-table * {{ color: black !important; border-color: #ccc !important; }}
        .stPlotlyChart {{ break-inside: avoid !important; page-break-inside: avoid !important; }}
        * {{ -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }}
    }}
    </style>
    """, unsafe_allow_html=True)


def render_page_header(title, subtitle="", badge="M0V3 PERFORMANCE ANALYTICS", icon=None, **kwargs):
    sub_html = f"<p style='margin: 4px 0 0 0; color: #64748b; font-size: 14px; font-weight: 400;'>{subtitle}</p>" if subtitle else ""
    icon_html = f"<i class='bi {icon}' style='margin-right: 8px; color: #0ea5e9;'></i>" if icon else ""
    st.markdown(f"""
    <div id="top-of-page" style="height:0; width:0; margin:0; padding:0;"></div>
    <div class="no-print" style="background: white; padding: 20px 24px; border-radius: 12px; border: 1px solid #e2e8f0; border-left: 5px solid #0ea5e9; margin-bottom: 22px; box-shadow: 0 2px 4px rgba(0,0,0,0.02);">
        <div style="font-size: 11px; text-transform: uppercase; letter-spacing: 1.5px; color: #0ea5e9; font-weight: 700; margin-bottom: 2px;">{badge}</div>
        <h1 style="margin: 0; padding: 0; color: #0f172a; font-size: 24px; font-weight: 900; line-height: 1.2;">{icon_html}{title}</h1>
        {sub_html}
    </div>
    """, unsafe_allow_html=True)


def _build_meta_cells_html(items):
    cells = []
    for idx, item in enumerate(items):
        lbl, val = item[0], item[1]
        is_acc = item[2] if len(item) > 2 else False
        val_color = "#0ea5e9" if is_acc else "#0f172a"
        border_r = "border-right: 1px solid #e2e8f0; padding-right: 18px;" if idx < len(items) - 1 else ""
        cells.append(
            f"<div style='{border_r} display: flex; flex-direction: column; gap: 2px;'>"
            f"<span style='font-size: 10px; font-weight: 700; color: #64748b; text-transform: uppercase; letter-spacing: 0.6px;'>{lbl}</span>"
            f"<span style='font-size: 14px; font-weight: 800; color: {val_color};'>{val}</span>"
            f"</div>"
        )
    return "".join(cells)


def render_meta_bar(items):
    """Renders a clean enterprise metadata bar. items = list of (label, value, is_accent_bool)."""
    inner_html = _build_meta_cells_html(items)
    st.markdown(
        f"<div style='background: white; padding: 10px 18px; border-radius: 8px; border: 1px solid #e2e8f0; display: flex; align-items: center; gap: 18px; box-shadow: 0 1px 2px rgba(0,0,0,0.02); margin-top: 2px; flex-wrap: wrap;'>{inner_html}</div>",
        unsafe_allow_html=True,
    )


def render_tab_navigation(tab_items, key, default=None):
    """
    Controller di navigazione tra analisi con persistenza di stato in Session State:
    - Risolve il reset automatico al primo tab quando si cambia giorno/settimana o filtro.
    - Implementa elemento ID stabile (default=None) per eliminare il problema del doppio clic.
    - Impedisce la deselezione vuota su st.segmented_control (click accidentale sul tab già attivo).
    - Preserva la selezione corretta anche in caso di cambio lingua (IT/EN) mappando per indice.
    - Restituisce la stringa del tab attualmente selezionato.
    """
    if not tab_items:
        return ""

    idx_key = f"_idx_{key}"
    widget_key = f"seg_{key}"

    # 1. Recupero indice persistente in session_state
    if idx_key not in st.session_state:
        init_idx = tab_items.index(default) if (default and default in tab_items) else 0
        st.session_state[idx_key] = init_idx

    cur_idx = st.session_state.get(idx_key, 0)
    if cur_idx >= len(tab_items) or cur_idx < 0:
        cur_idx = 0
        st.session_state[idx_key] = 0

    expected_val = tab_items[cur_idx]

    # 2. Inizializzazione o allineamento (es. cambio lingua IT <-> EN o primo caricamento)
    if widget_key not in st.session_state or st.session_state[widget_key] not in tab_items:
        st.session_state[widget_key] = expected_val

    # 3. segmented_control con default=None per garantire elemento ID stabile al 100%
    selected = st.segmented_control(
        label=key,
        options=tab_items,
        default=None,
        key=widget_key,
        label_visibility="collapsed"
    )

    # 4. Gestione selezione e prevenzione deselezione accidentale (click sul tab attivo)
    if selected and selected in tab_items:
        new_idx = tab_items.index(selected)
        st.session_state[idx_key] = new_idx
        st.session_state[key] = selected
        return selected
    else:
        # Se selected è None (l'utente ha cliccato sul tab già attivo deselezionandolo)
        # ripristiniamo immediatamente la selezione attiva precedente
        fallback_val = tab_items[cur_idx]
        st.session_state[widget_key] = fallback_val
        st.session_state[key] = fallback_val
        return fallback_val


def render_action_bar(meta_items, pdf_options=None, pdf_key=None, generate_fn=None, filename_fn=None):
    """Unified Enterprise Action Bar combining context metadata and optional inline PDF export without layout shift."""
    st.markdown('<div class="no-print">', unsafe_allow_html=True)
    with st.container(border=True):
        if pdf_options and pdf_key and generate_fn and filename_fn:
            col_info, col_sub_pdf, col_print = st.columns([3.3, 1.7, 1.3], vertical_alignment="center")
            with col_info:
                inner_html = _build_meta_cells_html(meta_items)
                st.markdown(
                    f"<div style='display: flex; align-items: center; gap: 18px; flex-wrap: wrap; padding: 2px 4px;'>{inner_html}</div>",
                    unsafe_allow_html=True,
                )
            with col_sub_pdf:
                st.markdown(
                    f"<div style='font-size: 10px; font-weight: 700; color: #64748b; text-transform: uppercase; letter-spacing: 0.6px; margin-bottom: 3px;'>{tr('Sezione Report PDF', 'PDF Report Scope')}</div>",
                    unsafe_allow_html=True,
                )
                scelta_sub = st.selectbox(
                    tr("Sottoarea PDF", "PDF Scope"),
                    list(pdf_options.keys()),
                    key=f"sub_{pdf_key}",
                    label_visibility="collapsed",
                )
                codice_sub = pdf_options[scelta_sub]
            with col_print:
                st.markdown(
                    f"<div style='font-size: 10px; font-weight: 700; color: #64748b; text-transform: uppercase; letter-spacing: 0.6px; margin-bottom: 3px;'>{tr('Esportazione', 'Export Report')}</div>",
                    unsafe_allow_html=True,
                )
                btn_slot = st.empty()
                if btn_slot.button(tr("Genera Report PDF", "Generate PDF Report"), key=f"btn_{pdf_key}", use_container_width=True):
                    with st.spinner(tr("Elaborazione PDF...", "Generating PDF...")):
                        pdf_bytes = generate_fn(codice_sub)
                    btn_slot.download_button(
                        label=tr("Scarica PDF Pronto", "Download PDF Ready"),
                        data=pdf_bytes,
                        file_name=filename_fn(codice_sub),
                        mime="application/pdf",
                        use_container_width=True,
                        type="primary",
                        key=f"dl_{pdf_key}",
                    )
        else:
            inner_html = _build_meta_cells_html(meta_items)
            st.markdown(
                f"<div style='display: flex; align-items: center; gap: 18px; flex-wrap: wrap; padding: 4px 6px;'>{inner_html}</div>",
                unsafe_allow_html=True,
            )
    st.markdown('</div>', unsafe_allow_html=True)


def render_print_header(is_first, giocatore, data_sess, nome_sess, campo, ambiente, sparring):
    if os.path.exists(LOGO_PATH):
        with open(LOGO_PATH, "rb") as f: encoded_logo = base64.b64encode(f.read()).decode()
        img_tag = f'<img src="data:image/png;base64,{encoded_logo}" style="height: 38px;">'
    else: img_tag = "<h3 style='margin:0;'>M0V3 Analytics</h3>"
    pb = "" if is_first else '<div class="page-break"></div>'
    st.markdown(f"""
    {pb}
    <div class="print-only" style="width: 100%; border-bottom: 2px solid #0ea5e9; padding-bottom: 3px; margin-bottom: 10px; margin-top: 0px;">
        <table style="width: 100%; border: none !important; background: transparent !important; margin-bottom: 0;">
            <tr>
                <td style="width: 40%; border: none !important; text-align: left; padding: 0;">{img_tag}</td>
                <td style="width: 60%; text-align: right; border: none !important; padding: 0; color: black !important; font-size: 13px; line-height: 1.2;">
                    <strong>Atleta:</strong> {giocatore} &nbsp;|&nbsp; <strong>Data:</strong> {data_sess}<br>
                    <strong>Sessione:</strong> {nome_sess} &nbsp;|&nbsp; <strong>Ambiente:</strong> {ambiente} &nbsp;|&nbsp; <strong>Sparring:</strong> {sparring} min
                </td>
            </tr>
        </table>
    </div>
    """, unsafe_allow_html=True)

# =========================================================================
# CATALOGO E COLONNE
# =========================================================================
CATALOGO_REPORT = {
    "Analisi Match": [
        "Distance from the average",
        "Training Load Bands",
        "Training Load Time% Bends",
        "Dati volumetrici IMU",
        "Dati GPS",
        "2 Days Before the Match (Acute)",
        "7 Days Before the Match (Chronic)",
        "Infografica Delta Match"
    ],
    "Analisi Sessione": [
        "Distance from the averages (Session)",
        "Training Load Bands",
        "Training Load Time% Bends",
        "Dati volumetrici IMU",
        "Dati GPS",
        "Aerobic Area - Session Comparison",
        "Anaerobic Area - Session Comparison",
        "Before Tomorrow (Acute 2 Days)",
        "Before Tomorrow (Chronic 7 Days)"
    ],
    "Trend Settimanale": [
        "Andamento Settimanale (Tutte le Metriche)",
        "Indici Compositi Settimanali (Volume & Work Rate)",
        "ACWR Settimanale (Acuto/Cronico)",
        "Last 7 Days Load (Rolling)",
        "Current Week Load (ACWR Progressivo)",
        "Benchmark Giornaliero vs Medie",
        "Referto Descrittivo Settimanale"
    ],
    "Trend Stagionale": [
        "Andamento Ultime 8 Settimane",
        "Carico Totale Mensile (12 Mesi)",
        "Timeline Settimanale Stagione",
        "ACWR Stagionale (Intera Stagione)",
        "ACWR Ultime 8 Settimane",
        "Distribuzione Lavoro",
        "Monotonia Stagionale",
        "Strain Stagionale"
    ],
    "Storico Match": [
        "Volume Match Timeline",
        "Intensità Match Timeline",
        "Work Rate Timeline",
        "GPS Data Timeline",
        "Indici Compositi (Volume & Work Rate)",
        "Record Storici Match"
    ],
    "Medie": [
        "Analisi Singolo Atleta",
        "Testa a Testa Medie",
        "Testa a Testa Settimana",
        "Ranking Roster Atleti",
        "Distribuzione Lavoro Roster",
        "Stress Roster 8 settimane"
    ],
    "Test Fisici & Neuromuscolari": [
        "Panoramica Test Atleta",
        "Deep-Dive per Test",
        "Executive Summary & Readiness",
        "Confronti",
        "Gestione & Inserimento Test",
        "Costruttore Test Custom"
    ],
    "Calendario & Area Medica": [
        "Master Calendar & Timeline Giornaliera",
        "Registro Clinico, Trattamenti & Logistica ( Lettura / Scrittura )",
        "Analisi Correlazione Carichi vs Eventi Clinici"
    ]
}

PAGINE_OPERATIVE = [
    {"chiave": "Carico Interno", "nome": "Carico Interno (sRPE & Wellness)", "icona": "heart-pulse"},
    {"chiave": "M0V3 Tennis Test", "nome": "M0V3 Tennis Test (Neuro-Mechanical Profiling)", "icona": "lightning-charge-fill"},
    {"chiave": "Caricamento Dati", "nome": "Caricamento Dati (Ingestion CSV/GPS)", "icona": "cloud-arrow-up"},
    {"chiave": "Generatore Dati (No GPS)", "nome": "Generatore Dati (Simulazione No GPS)", "icona": "sliders"},
    {"chiave": "Gestione File Caricati", "nome": "Gestione File (Archivio Sessioni)", "icona": "folder2-open"},
    {"chiave": "Manuale Report", "nome": "Manuale Report (Documentazione Moduli)", "icona": "journal-bookmark-fill"},
    {"chiave": "Manuale Test", "nome": "Manuale Test (Enciclopedia Protocolli)", "icona": "journal-text"},
]

AREA_TO_PAGINA = {
    "Analisi Match": "Analisi Match",
    "Analisi Sessione": "Analisi Sessione",
    "Trend Settimanale": "Trend Settimanale",
    "Trend Stagionale": "Trend Stagionale",
    "Storico Match": "Storico Match",
    "Medie": "Medie",
    "Test Fisici & Neuromuscolari": "Test & Valutazioni",
    "Calendario & Area Medica": "Calendario & Area Medica"
}

COLONNE_STANDARD = [
    "Date", "Session", "Players", "Minuti", 
    "Training Load", "TL_Stand", "TL_Low", "TL_Medium", "TL_High",
    "TL_T_Stand", "TL_T_Low", "TL_T_Medium", "TL_T_High",
    "Player Load", "High Accel IMU", "High Decel IMU",
    "DISTANCE", "HML Distance >25.5W", "VHML Distance >50W", "High Dec Events <-3.5 m/s2",
    "Recovery Time <5W %", "Equivalent Distance %", "Anaerobic index %",
    "Azioni Int. IMU >2", "Azioni Int. IMU >3", "Azioni Int. IMU >5", "Azioni Int. IMU >7", "Azioni Int. IMU >10",
    "Recuperi IMU 3-30s", "Recuperi IMU 30-60s", "Recuperi IMU 1-5m"
]

METRICHE_VOLUME = [
    "Training Load", "TL_Stand", "TL_Low", "TL_Medium", "TL_High",
    "Player Load", "High Accel IMU", "High Decel IMU", 
    "DISTANCE", "HML Distance >25.5W", "VHML Distance >50W", "High Dec Events <-3.5 m/s2",
    "Azioni Int. IMU >2", "Azioni Int. IMU >3", "Azioni Int. IMU >5", "Azioni Int. IMU >7", "Azioni Int. IMU >10",
    "Recuperi IMU 3-30s", "Recuperi IMU 30-60s", "Recuperi IMU 1-5m"
]

METRICHE_INTENSITA = [
    "TL_T_Stand", "TL_T_Low", "TL_T_Medium", "TL_T_High",
    "Recovery Time <5W %", "Equivalent Distance %", "Anaerobic index %"
]


def card_kpi(titolo, valore_html, sottotitolo="", accento="#0ea5e9", **kwargs):
    """Renderizza una card KPI compatta con bordo laterale colorato."""
    sub = kwargs.get('subtext', sottotitolo)
    acc = kwargs.get('accent', kwargs.get('accento', accento))
    return (
        f"<div style='background:white; padding:18px 16px; border-radius:12px; border:1px solid #e2e8f0; "
        f"border-left:5px solid {acc}; box-shadow:0 2px 4px rgba(0,0,0,0.03);'>"
        f"<div style='font-size:11px; font-weight:700; color:#64748b; text-transform:uppercase; letter-spacing:0.5px;'>{titolo}</div>"
        f"<div style='margin:8px 0 4px 0; line-height:1.1;'>{valore_html}</div>"
        f"<div style='font-size:11px; color:#94a3b8;'>{sub}</div></div>"
    )


def slugify_name(text):
    """Normalizza una stringa per l'uso in ID o nomi di file (minuscolo, senza spazi o caratteri speciali)."""
    import re
    if not text:
        return ""
    s = str(text).lower()
    s = re.sub(r'[\s/\\_]+', '_', s)
    return re.sub(r'[^a-z0-9_]', '', s).strip('_')


# Configurazione standard Plotly per alleggerire rendering DOM e velocizzare i grafici
PLOTLY_CONFIG = {
    'displayModeBar': False,
    'responsive': True,
    'showAxisDragHandles': False,
    'showAxisRangeEntryBoxes': False
}






def render_navigation_cards(page_key: str, cards: list) -> str:
    """
    Rende una griglia elegante di CARD interattive per accedere alle varie analisi di una sezione.
    cards: lista di dizionari o tuple:
      - dict: {"id": str, "title": str, "desc": str, "icon": str}
      - tuple: (id, title, desc, icon)
    Restituisce l'id della card attiva (memorizzato in session_state).
    """
    state_key = f"active_subtab_{page_key}"
    valid_ids = [c["id"] if isinstance(c, dict) else c[0] for c in cards]
    if state_key not in st.session_state or st.session_state[state_key] not in valid_ids:
        st.session_state[state_key] = valid_ids[0]

    norm_cards = []
    for c in cards:
        if isinstance(c, dict):
            norm_cards.append(c)
        else:
            cid = c[0]
            ctitle = c[1]
            cdesc = c[2] if len(c) > 2 else ""
            cicon = c[3] if len(c) > 3 else "bi-grid"
            norm_cards.append({"id": cid, "title": ctitle, "desc": cdesc, "icon": cicon})

    n = len(norm_cards)
    if n <= 3:
        per_row = n
    elif n == 4:
        per_row = 4
    elif n in (5, 6):
        per_row = 3
    elif n in (7, 8):
        per_row = 4
    elif n == 9:
        per_row = 3
    else:
        per_row = 4

    rows = [norm_cards[i:i + per_row] for i in range(0, n, per_row)]

    st.markdown(
        """
        <style>
        .fir-navcard-box {
            border-radius: 12px;
            padding: 10px 12px;
            margin-bottom: 6px;
            min-height: 86px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            transition: all 0.2s ease;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    with st.container():
        for r_idx, row in enumerate(rows):
            cols = st.columns(len(row))
            for c_idx, item in enumerate(row):
                cid = item["id"]
                title = item["title"]
                desc = item.get("desc", "")
                icon = item.get("icon", "bi-graph-up")
                is_active = (st.session_state[state_key] == cid)

                with cols[c_idx]:
                    card_border = "#D4AF37" if is_active else "#CBD5E1"
                    card_bg = "linear-gradient(135deg, #002B49 0%, #004B87 100%)" if is_active else "#FFFFFF"
                    card_shadow = "0 6px 18px rgba(0,43,73,0.22)" if is_active else "0 2px 6px rgba(15,23,42,0.04)"
                    txt_color = "#FFFFFF" if is_active else "#0F172A"
                    desc_color = "#93C5FD" if is_active else "#64748B"
                    badge_bg = "rgba(212,175,55,0.25)" if is_active else "#F1F5F9"
                    badge_border = "#D4AF37" if is_active else "#E2E8F0"
                    badge_txt = "#D4AF37" if is_active else "#0066B2"
                    status_pill = (
                        '<span style="background:#D4AF37; color:#031926; font-size:0.62rem; font-weight:800; padding:2px 8px; border-radius:99px; text-transform:uppercase; letter-spacing:0.04em;">ATTIVA</span>'
                        if is_active
                        else '<span style="background:#F1F5F9; color:#64748B; font-size:0.62rem; font-weight:700; padding:2px 8px; border-radius:99px; text-transform:uppercase;">SELEZIONA</span>'
                    )

                    card_html = f"""
                    <div class="fir-navcard-box" style="background:{card_bg}; border:2px solid {card_border}; box-shadow:{card_shadow};">
                        <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:6px;">
                            <div style="display:flex; align-items:center; gap:8px; min-width:0;">
                                <div style="width:28px; height:28px; border-radius:8px; background:{badge_bg}; border:1px solid {badge_border}; display:flex; align-items:center; justify-content:center; color:{badge_txt}; font-size:0.95rem; flex-shrink:0;">
                                    <i class="bi {icon}"></i>
                                </div>
                                <div style="font-weight:800; font-size:0.83rem; color:{txt_color}; line-height:1.2; word-break:keep-all;" title="{title}">
                                    {title}
                                </div>
                            </div>
                            <div style="flex-shrink:0;">{status_pill}</div>
                        </div>
                        <div style="font-size:0.71rem; color:{desc_color}; margin-top:5px; line-height:1.2; font-weight:500;">
                            {desc}
                        </div>
                    </div>
                    """
                    st.markdown(card_html, unsafe_allow_html=True)
                    btn_label = f"✓ {title}" if is_active else f"Apri {title}"
                    if st.button(
                        btn_label,
                        key=f"cardbtn_{page_key}_{cid}",
                        use_container_width=True,
                        type="primary" if is_active else "secondary",
                    ):
                        st.session_state[state_key] = cid
                        st.session_state["_scroll_top_counter"] = st.session_state.get("_scroll_top_counter", 0) + 1
                        st.rerun()
            if r_idx < len(rows) - 1:
                st.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)

    st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)
    return st.session_state[state_key]


