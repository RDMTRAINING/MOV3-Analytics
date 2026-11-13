# Copyright 2026 Riccardo Di Maio - M0V3 S.r.l. Tutti i diritti riservati.
# Proprietary Sports Science & Clinical Performance Intelligence Architecture.
import re
import io
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime

MONTH_MAP = {
    'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6,
    'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12,
    'gennaio': 1, 'febbraio': 2, 'marzo': 3, 'aprile': 4, 'maggio': 5, 'giugno': 6,
    'luglio': 7, 'agosto': 8, 'settembre': 9, 'ottobre': 10, 'novembre': 11, 'dicembre': 12,
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'jun': 6, 'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
}

PROTOCOL_MAP = {
    # ForceDecks
    "drop jump": "vald_fd_dj",
    "countermovement jump": "vald_fd_cmj",
    "cmj": "vald_fd_cmj",
    "squat jump": "vald_fd_sj",
    "single leg jump": "vald_fd_slj",
    "isometric mid-thigh pull": "vald_fd_imtp",
    "imtp": "vald_fd_imtp",
    
    # NordBord
    "nordic": "nordic_hamstring_eccentric",
    "nordic hamstring": "nordic_hamstring_eccentric",
    
    # DynaMo Forza
    "shoulder iso t supine": "dynamo_f_spalla_iso_t",
    "shoulder iso i supine": "dynamo_f_spalla_iso_i",
    "shoulder ir standing - elbow 90°, 90° shoulder abd": "dynamo_f_spalla_ir_standing",
    "shoulder er standing - elbow 90°, 90° shoulder abd": "dynamo_f_spalla_er_standing",
    "shoulder ir standing - elbow 90°": "dynamo_f_spalla_ir_standing",
    "shoulder er standing - elbow 90°": "dynamo_f_spalla_er_standing",
    "hand grip squeeze 90° elbow flexion": "dynamo_f_handgrip",
    "hand grip": "dynamo_f_handgrip",
    
    # DynaMo ROM
    "wrist supination 90° elbow flexion - wrist neutral": "dynamo_rom_wrist_sup",
    "shoulder er seated - elbow 90°": "dynamo_rom_spalla_er_seated",
    "shoulder ir seated - elbow 90°": "dynamo_rom_spalla_ir_seated",
    "hip ir prone": "dynamo_rom_anca_ir_prone",
    "hip er prone": "dynamo_rom_anca_er_prone",
    "hip er seated": "dynamo_rom_anca_er_seated",
    "hip ir seated": "dynamo_rom_anca_ir_seated",
    "ankle dorsiflexion standing": "dynamo_rom_caviglia_dorsiflessione"
}

METRIC_MAP = {
    # Drop jump
    "max rsi": "rsi",
    "max eccentric duration": "eccentric_duration",
    "max concentric mean power": "concentric_mean_power",
    "max eccentric mean force": "eccentric_mean_force",
    "max peak power": "peak_power",
    "max coefficient of restitution": "coeff_restitution",
    "max concentric impulse": "concentric_impulse",
    
    # CMJ & Squat Jump & SLJ
    "max jump height": "jump_height",
    "max cmj stiffness": "stiffness",
    "max concentric impulse-100ms": "concentric_impulse_100ms",
    "max concentric peak force": "concentric_peak_force",
    "max concentric rfd - 100ms": "concentric_rfd_100ms",
    "max eccentric deceleration peak force": "ecc_decel_peak_force",
    "max eccentric peak power": "eccentric_peak_power",
    "max concentric mean force": "concentric_mean_force",
    "max concentric peak velocity": "concentric_peak_velocity",
    "max concentric maximum rfd": "concentric_max_rfd",
    "max velocity at peak power": "velocity_at_peak_power",
    
    # IMTP
    "max peak vertical force": "peak_vertical_force",
    "max rfd - 100ms": "rfd_100ms",
    "max force at 100ms": "force_100ms",
    "max absolute impulse - 100ms": "absolute_impulse_100ms",
    "max start time to peak force": "start_time_to_peak_force",
    
    # DynaMo / NordBord
    "max force": "max_force",
    "max impulse": "max_impulse",
    "max rate of force development": "rfd",
    "max time to peak force": "time_to_peak_force",
    "max rom": "max_rom"
}


def parse_date_string(date_str):
    """Estrae e normalizza la data in formato YYYY-MM-DD."""
    cleaned = re.sub(r'^date:\s*', '', date_str, flags=re.IGNORECASE).strip()
    
    # 1. Prova YYYY-MM-DD o DD/MM/YYYY
    for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"]:
        try:
            return datetime.strptime(cleaned, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
            
    # 2. Formato testuale es: "26 March 2025" o "4 December 2025" o "26 Marzo 2025"
    m = re.match(r'^(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})', cleaned)
    if m:
        day = int(m.group(1))
        month_name = m.group(2).lower()
        year = int(m.group(3))
        month = MONTH_MAP.get(month_name)
        if month:
            return f"{year:04d}-{month:02d}-{day:02d}"
            
    return cleaned


def _clean_num(val_str):
    """Pulisce stringhe numeriche rimuovendo virgole delle migliaia e %."""
    if not val_str:
        return None
    s = val_str.replace(',', '').replace('%', '').strip()
    try:
        return float(s)
    except ValueError:
        return None


def parse_metric_line(line):
    """
    Analizza una riga metrica e restituisce (metric_key, dict_valori).
    Supporta metriche sia bilaterali (Left/Right/Asym) che scalari.
    """
    if ':' not in line:
        return None, {}
        
    parts = line.split(':', 1)
    label_part = parts[0].strip()
    val_part = parts[1].strip()
    
    # Normalizza nome metrica
    clean_label = re.sub(r'\(.*?\)', '', label_part)
    clean_label = re.sub(r'- Asym', '', clean_label, flags=re.IGNORECASE).strip().lower()
    
    metric_key = None
    for k, v in METRIC_MAP.items():
        if k in clean_label:
            metric_key = v
            break
            
    if not metric_key:
        metric_key = re.sub(r'[^a-z0-9_]', '_', clean_label).strip('_')
        
    # Verifica presenza Left / Right / Asymmetry
    is_bilateral = bool(re.search(r'\b(left|right|asymmetry)\b', val_part, flags=re.IGNORECASE))
    
    valori = {}
    if is_bilateral:
        # Left
        m_left = re.search(r'Left\s+([-\d.,]+)', val_part, flags=re.IGNORECASE)
        if m_left:
            val_sx = _clean_num(m_left.group(1))
            if val_sx is not None:
                valori[f"{metric_key}_sx"] = val_sx
                
        # Right
        m_right = re.search(r'Right\s+([-\d.,]+)', val_part, flags=re.IGNORECASE)
        if m_right:
            val_dx = _clean_num(m_right.group(1))
            if val_dx is not None:
                valori[f"{metric_key}_dx"] = val_dx
                
        # Asymmetry
        m_asym = re.search(r'Asymmetry\s+([-\d.,]+)%\s*(Left|Right|Sx|Dx)?', val_part, flags=re.IGNORECASE)
        if m_asym:
            val_asym = _clean_num(m_asym.group(1))
            if val_asym is not None:
                valori[f"{metric_key}_asym_pct"] = val_asym
            dir_asym = m_asym.group(2)
            if dir_asym:
                d_clean = "Sx" if dir_asym.lower() in ["left", "sx"] else "Dx"
                valori[f"{metric_key}_asym_dir"] = d_clean
    else:
        # Valore scalare singolo (es. "1.82" o "10,950")
        m_num = re.search(r'^([-\d.,]+)', val_part)
        if m_num:
            val_single = _clean_num(m_num.group(1))
            if val_single is not None:
                valori[metric_key] = val_single
                
    return metric_key, valori


def parse_test_docx(file_bytes_or_path):
    """
    Estrae tutti i test fisici dal file Word (.docx) suddivisi per data e protocollo.
    Restituisce: list di dict { 'data', 'device', 'protocollo_nome', 'codice_univoco', 'valori', 'raw_lines' }
    """
    if isinstance(file_bytes_or_path, (bytes, bytearray)):
        docx_file = io.BytesIO(file_bytes_or_path)
    else:
        docx_file = file_bytes_or_path

    with zipfile.ZipFile(docx_file) as z:
        xml_content = z.read('word/document.xml')
        
    tree = ET.fromstring(xml_content)
    namespaces = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    
    raw_paragraphs = []
    for p in tree.iterfind('.//w:p', namespaces):
        text = ''.join([elem.text for elem in p.iterfind('.//w:t', namespaces) if elem.text]).strip()
        if text:
            raw_paragraphs.append(text)

    sessions = []
    current_date = None
    current_device = None
    current_test_name = None
    current_test_code = None
    current_values = {}
    current_lines = []

    def _flush_test():
        nonlocal current_test_name, current_test_code, current_values, current_lines
        if current_date and current_test_code and current_values:
            sessions.append({
                "data": current_date,
                "device": current_device or "VALD",
                "protocollo_nome": current_test_name,
                "codice_univoco": current_test_code,
                "valori": dict(current_values),
                "raw_lines": list(current_lines)
            })
        current_test_name = None
        current_test_code = None
        current_values = {}
        current_lines = []

    for line in raw_paragraphs:
        # 1. Riconoscimento Data
        if line.lower().startswith('date:'):
            _flush_test()
            current_date = parse_date_string(line)
            current_device = None
            continue
            
        # 2. Riconoscimento Dispositivo
        if line.strip().lower() in ['forcedecks', 'dynamo', 'nordbord']:
            _flush_test()
            current_device = line.strip()
            continue

        # 3. Salta marcatori orari intermedi tipo "3:20 PM"
        if re.match(r'^\d{1,2}:\d{2}\s*(am|pm)$', line.strip(), flags=re.IGNORECASE):
            continue

        # 4. Riconoscimento Protocollo / Test
        line_clean = line.strip().lower()
        matched_code = PROTOCOL_MAP.get(line_clean)
        
        # Prova matching parziale se non esatto
        if not matched_code:
            for proto_txt, code in PROTOCOL_MAP.items():
                if proto_txt in line_clean or line_clean in proto_txt:
                    # Assicurati che non sia una riga di metrica
                    if ':' not in line:
                        matched_code = code
                        break

        if matched_code and ':' not in line:
            _flush_test()
            current_test_name = line.strip()
            current_test_code = matched_code
            continue

        # 5. Riconoscimento Metrica
        if ':' in line and current_test_code:
            current_lines.append(line)
            m_key, m_vals = parse_metric_line(line)
            if m_vals:
                current_values.update(m_vals)

    # Flush finale dell'ultimo test
    _flush_test()
    return sessions
