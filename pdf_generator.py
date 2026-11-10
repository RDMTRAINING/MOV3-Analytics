import os
import re
import base64
import datetime
from io import BytesIO
from datetime import timedelta
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage, PageBreak, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from utils import (
    get_val,
    get_color,
    calcola_delta_percentuale,
    delta_puro,
    calcola_blocchi_baseline,
    acwr_pre_match,
)
from utils_tennis_matches import get_tournament_for_week

LOGO_PATH = "logo.png"

def _clean_text_for_pdf(val):
    """Pulisce tag HTML e caratteri non supportati da ReportLab."""
    if not val:
        return ""
    s = str(val)
    s = re.sub(r'<[^>]+>', ' ', s)
    s = s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    return s.strip()

def colora_delta(tabella, righe, colonne, prima_riga=1):
    """Colora i delta nei PDF come nell'app: blu sopra la media, grigio sotto."""
    cmds = []
    for r in range(prima_riga, len(righe)):
        for c in colonne:
            if c >= len(righe[r]): continue
            testo_cella = str(righe[r][c]).strip()
            if not re.fullmatch(r'[+-]?\d+%', testo_cella): continue
            if testo_cella in ('0%', '+0%', '-0%'): col = '#94a3b8'
            elif testo_cella.startswith('+'): col = '#0369a1'
            else: col = '#64748b'
            cmds.append(('TEXTCOLOR', (c, r), (c, r), colors.HexColor(col)))
    if cmds: tabella.setStyle(TableStyle(cmds))

def colora_acwr(tabella, pct, riga=3):
    """Semaforo readiness (stesse soglie dell'app) sulla riga '% of Average'."""
    cmds = []
    for i, p in enumerate(pct):
        bg, fg = get_color(p)
        cmds.append(('BACKGROUND', (i + 1, riga), (i + 1, riga), colors.HexColor(bg)))
        cmds.append(('TEXTCOLOR', (i + 1, riga), (i + 1, riga), colors.HexColor(fg)))
    tabella.setStyle(TableStyle(cmds))

def build_pdf_con_footer(doc, elements, brand="M0V3 Analytics", is_landscape=True):
    """Costruisce il PDF con data di generazione e numero di pagina in ogni pagina."""
    generato = pd.Timestamp.now(tz='Europe/Rome').strftime('%d/%m/%Y %H:%M')
    larghezza = landscape(A4)[0] if is_landscape else A4[0]
    def _footer(canvas, d):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor('#e2e8f0'))
        canvas.setLineWidth(0.5)
        canvas.line(25, 21, larghezza - 25, 21)
        canvas.setFont('Helvetica', 7.5)
        canvas.setFillColor(colors.HexColor('#64748b'))
        canvas.drawString(25, 11, f"{brand}   |   Report generato il {generato}")
        canvas.drawRightString(larghezza - 25, 11, f"Pagina {d.page}")
        canvas.restoreState()
    doc.build(elements, onFirstPage=_footer, onLaterPages=_footer)
def fig_to_rl_image(fig, width=360, height=210):
    """Converte un grafico Plotly in un'immagine ad alta risoluzione proporzionale per ReportLab."""
    try:
        pixel_w = int(max(width * 2, 800))
        pixel_h = int(pixel_w * (height / width))
        img_bytes = fig.to_image(format="png", width=pixel_w, height=pixel_h, scale=1.5)
        return RLImage(BytesIO(img_bytes), width=width, height=height)
    except Exception:
        return Paragraph("<i>[Grafico non disponibile]</i>", getSampleStyleSheet()['Normal'])
def slugify_name(text):
    return re.sub(r'[^A-Za-z0-9]+', '_', str(text)).strip('_')


def genera_blocco_tabella_paginata(
    righe_dati,
    col_widths,
    headers,
    table_style,
    max_righe_p1=12,
    max_righe_pn=16,
    titolo_continuazione="[SECONDA PARTE — TABELLA CONTINUATA]",
    sec_style=None,
    row_bg_colors=None
):
    """
    Gestisce la paginazione intelligente e anti-taglio delle tabelle ReportLab.
    Se la tabella entra in una pagina (<= max_righe_p1), la restituisce come blocco indivisibile KeepTogether.
    Se la tabella eccede l'altezza utile, la divide in tronconi inserendo un PageBreak esplicito,
    riproponendo obbligatoriamente l'intestazione di colonna preceduta dal banner in evidenza:
    [SECONDA PARTE — TABELLA CONTINUATA] (o TERZA PARTE).
    """
    flowables = []
    tot_righe = len(righe_dati)

    def _apply_row_colors(t_obj, slice_rows, start_orig_idx):
        if not row_bg_colors:
            return
        extra_styles = []
        for i_local in range(len(slice_rows)):
            orig_i = start_orig_idx + i_local
            if orig_i in row_bg_colors:
                c = row_bg_colors[orig_i]
                if isinstance(c, str):
                    c = colors.HexColor(c)
                extra_styles.append(('BACKGROUND', (0, i_local + 1), (-1, i_local + 1), c))
        if extra_styles:
            t_obj.setStyle(TableStyle(extra_styles))

    if tot_righe <= max_righe_p1:
        t_single = Table([headers] + righe_dati, colWidths=col_widths, repeatRows=1)
        t_single.setStyle(table_style)
        _apply_row_colors(t_single, righe_dati, 0)
        flowables.append(KeepTogether([t_single]))
        return flowables

    # Se eccede, effettua chunking controllato con marcatura esplicita
    p1_rows = righe_dati[:max_righe_p1]
    t_p1 = Table([headers] + p1_rows, colWidths=col_widths, repeatRows=1)
    t_p1.setStyle(table_style)
    _apply_row_colors(t_p1, p1_rows, 0)
    flowables.append(KeepTogether([t_p1]))

    rimanenti = righe_dati[max_righe_p1:]
    part_idx = 2
    ordinali = {2: "SECONDA", 3: "TERZA", 4: "QUARTA", 5: "QUINTA", 6: "SESTA", 7: "SETTIMA", 8: "OTTAVA"}
    curr_orig_idx = max_righe_p1

    while rimanenti:
        flowables.append(PageBreak())
        chunk = rimanenti[:max_righe_pn]
        rimanenti = rimanenti[max_righe_pn:]

        ord_str = ordinali.get(part_idx, f"{part_idx}ª")
        lbl_cont = f"[{ord_str} PARTE — TABELLA CONTINUATA]"

        if sec_style:
            p_cont = Paragraph(f"<font color='#0284c7'><b>{lbl_cont}</b></font>", sec_style)
        else:
            p_cont = Paragraph(f"<font color='#0284c7' size='10'><b>{lbl_cont}</b></font>", ParagraphStyle('ContStyle', fontName='Helvetica-Bold', fontSize=10, leading=13))

        t_pn = Table([headers] + chunk, colWidths=col_widths, repeatRows=1)
        t_pn.setStyle(table_style)
        _apply_row_colors(t_pn, chunk, curr_orig_idx)
        flowables.append(KeepTogether([p_cont, Spacer(1, 6), t_pn]))
        curr_orig_idx += len(chunk)
        part_idx += 1

    return flowables


def genera_sezione_metodologia_pdf(modulo_chiave, styles=None, width=792):
    """
    Genera un blocco compatto indivisibile (KeepTogether) con note metodologiche,
    formule matematiche, linee guida e riferimenti bibliografici validati per i referti esportati in PDF.
    """
    from config import SCIENTIFIC_METHODOLOGY_REGISTRY
    meta = SCIENTIFIC_METHODOLOGY_REGISTRY.get(modulo_chiave)
    if not meta:
        return []

    actual_w = width if width is not None else 792

    p_style_hdr = ParagraphStyle(
        'PDF_Biblio_Hdr',
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor('#0284c7')
    )
    p_style_subhdr = ParagraphStyle(
        'PDF_Biblio_SubHdr',
        fontName='Helvetica-Bold',
        fontSize=7.2,
        leading=9.5,
        textColor=colors.HexColor('#0f172a')
    )
    p_style_body = ParagraphStyle(
        'PDF_Biblio_Body',
        fontName='Helvetica',
        fontSize=7.0,
        leading=9.0,
        textColor=colors.HexColor('#334155')
    )
    p_style_formula = ParagraphStyle(
        'PDF_Biblio_Formula',
        fontName='Courier-Bold',
        fontSize=6.8,
        leading=8.8,
        textColor=colors.HexColor('#0369a1')
    )
    p_style_ref = ParagraphStyle(
        'PDF_Biblio_Ref',
        fontName='Helvetica-Oblique',
        fontSize=6.2,
        leading=8.0,
        textColor=colors.HexColor('#64748b')
    )

    flowables = []
    flowables.append(Spacer(1, 4))
    flowables.append(Paragraph(f"<b>NOTE METODOLOGICHE &amp; TRASPARENZA SCIENTIFICA M0V3 — {meta['titolo'].upper()}</b>", p_style_hdr))
    flowables.append(Spacer(1, 3))
    flowables.append(Paragraph(_clean_text_for_pdf(meta['cosa_sto_vedendo']), p_style_body))
    flowables.append(Spacer(1, 3))

    if meta.get('formule'):
        flowables.append(Paragraph("<b>Formulazioni Matematiche &amp; Rapporti Meccanici:</b>", p_style_subhdr))
        for f_txt in meta['formule']:
            clean_f = f_txt.replace(r'\text{', '').replace('}', '').replace(r'\quad', ' ').replace(r'\[', '').replace(r'\]', '')
            clean_f = clean_f.replace(r'\approx', '≈').replace(r'\times', '×').replace(r'\frac', '').replace(r'\sum', 'Σ ')
            clean_f = clean_f.replace('{', '').replace('}', '').replace('_', ' ')
            flowables.append(Paragraph(f"• {_clean_text_for_pdf(clean_f)}", p_style_formula))
        flowables.append(Spacer(1, 3))

    if meta.get('interpretazione'):
        flowables.append(Paragraph("<b>Linee Guida &amp; Soglie Operative di Riferimento:</b>", p_style_subhdr))
        for l_int in meta['interpretazione'].split('\n'):
            if l_int.strip():
                flowables.append(Paragraph(_clean_text_for_pdf(l_int.strip()), p_style_body))
        flowables.append(Spacer(1, 3))

    if meta.get('bibliografia'):
        flowables.append(Paragraph("<b>Riferimenti Bibliografici Validati (Peer-Reviewed Literature):</b>", p_style_subhdr))
        bib_lines = "<br/>• ".join([_clean_text_for_pdf(b) for b in meta['bibliografia']])
        flowables.append(Paragraph(f"• {bib_lines}", p_style_ref))

    t_box = Table([[flowables]], colWidths=[actual_w])
    t_box.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#cbd5e1')),
        ('LINELEFT', (0, 0), (0, -1), 3.5, colors.HexColor('#0284c7')),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    return [KeepTogether([t_box])]
# =========================================================================
# 1. MOTORE PDF: ANALISI MATCH (TUTTE LE SOTTOAREE)
# =========================================================================
def crea_pdf_m0v3(giocatore, data_match, sessione, campo, ambiente, sparring, dati_sessione, medie_storiche, medie_storiche_gps, df_storico=None, sottoarea="Tutte"):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), rightMargin=25, leftMargin=25, topMargin=25, bottomMargin=25)
    elements = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('M0V3Title', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=20, textColor=colors.HexColor('#0f172a'), spaceAfter=4)
    sub_style = ParagraphStyle('M0V3Sub', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=11, textColor=colors.HexColor('#0ea5e9'), spaceAfter=12)
    sec_style = ParagraphStyle('M0V3Sec', keepWithNext=1, parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=13, textColor=colors.HexColor('#0f172a'), spaceBefore=10, spaceAfter=8)

    sub_label = "REPORT COMPLETO" if sottoarea == "Tutte" else sottoarea.replace('_', ' ').upper()
    header_title = [
        Paragraph(f"M0V3 ANALYTICS — MATCH REPORT ({sub_label})", title_style),
        Paragraph(f"ATLETA: {giocatore.upper()}   |   SESSIONE: {sessione}", sub_style)
    ]
    if os.path.exists(LOGO_PATH):
        logo_img = RLImage(LOGO_PATH, width=55, height=55)
        t_head = Table([[header_title, logo_img]], colWidths=[715, 75])
        t_head.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('ALIGN', (1, 0), (1, 0), 'RIGHT'), ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0)]))
        elements.append(t_head)
    else:
        elements.extend(header_title)

    data_meta = [
        ["DATA PARTITA", "SUPERFICIE", "AMBIENTE", "MINUTI SPARRING"],
        [str(data_match), str(campo), str(ambiente), f"{sparring} min"]
    ]
    t_meta = Table(data_meta, colWidths=[198, 198, 198, 198])
    t_meta.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0A192F')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#38bdf8')),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9), ('FONTSIZE', (0, 1), (-1, 1), 11),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7), ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#f8fafc')),
        ('TEXTCOLOR', (0, 1), (-1, 1), colors.HexColor('#0f172a')),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e2e8f0'))
    ]))
    elements.append(t_meta)
    elements.append(Spacer(1, 10))

    def calc_pm(val, mins): return val / mins if mins > 0 else 0

    cur_min = get_val(dati_sessione, 'Minuti')
    cur_tl = get_val(dati_sessione, 'Training Load')
    cur_az2 = get_val(dati_sessione, 'Azioni Int. IMU >2')
    cur_tlh = get_val(dati_sessione, 'TL_High')
    cur_acc = get_val(dati_sessione, 'High Accel IMU')
    cur_dec = get_val(dati_sessione, 'High Decel IMU')

    avg_min = get_val(medie_storiche, 'Minuti')
    avg_tl = get_val(medie_storiche, 'Training Load')
    avg_az2 = get_val(medie_storiche, 'Azioni Int. IMU >2')
    avg_tlh = get_val(medie_storiche, 'TL_High')
    avg_acc = get_val(medie_storiche, 'High Accel IMU')
    avg_dec = get_val(medie_storiche, 'High Decel IMU')

    cur_tl_pm, cur_acc_pm, cur_dec_pm, cur_tlh_pm, cur_az2_pm = calc_pm(cur_tl, cur_min), calc_pm(cur_acc, cur_min), calc_pm(cur_dec, cur_min), calc_pm(cur_tlh, cur_min), calc_pm(cur_az2, cur_min)
    avg_tl_pm, avg_acc_pm, avg_dec_pm, avg_tlh_pm, avg_az2_pm = calc_pm(avg_tl, avg_min), calc_pm(avg_acc, avg_min), calc_pm(avg_dec, avg_min), calc_pm(avg_tlh, avg_min), calc_pm(avg_az2, avg_min)

    p_min, p_tl, p_az2 = calcola_delta_percentuale(cur_min, avg_min), calcola_delta_percentuale(cur_tl, avg_tl), calcola_delta_percentuale(cur_az2, avg_az2)
    p_tlh, p_acc, p_dec = calcola_delta_percentuale(cur_tlh, avg_tlh), calcola_delta_percentuale(cur_acc, avg_acc), calcola_delta_percentuale(cur_dec, avg_dec)
    p_tl_pm, p_acc_pm, p_dec_pm = calcola_delta_percentuale(cur_tl_pm, avg_tl_pm), calcola_delta_percentuale(cur_acc_pm, avg_acc_pm), calcola_delta_percentuale(cur_dec_pm, avg_dec_pm)
    p_tlh_pm, p_az2_pm = calcola_delta_percentuale(cur_tlh_pm, avg_tlh_pm), calcola_delta_percentuale(cur_az2_pm, avg_az2_pm)

    avg_vol = (p_min + p_tl + p_az2) / 3
    avg_int = (p_tlh + p_acc + p_dec) / 3
    avg_den = (p_tl_pm + p_acc_pm + p_dec_pm + p_tlh_pm + p_az2_pm) / 5

    need_break = False

    # --- SOTTOAREA 1: SINTESI & DELTA ---
    if sottoarea in ["Tutte", "Sintesi_Delta"]:
        elements.append(Paragraph("SINTESI & DELTA — DISTANCE FROM THE AVERAGES", sec_style))
        rows_dist = [
            ["PARAMETRO", "SESSION SCORE", "MEDIA STORICA", "DELTA %", "STATUS"],
            ["Time (min)", f"{cur_min:.0f}", f"{avg_min:.0f}", delta_puro(p_min), "SOPRA MEDIA" if p_min >= 0 else "SOTTO MEDIA"],
            ["Training Load", f"{cur_tl:.0f}", f"{avg_tl:.0f}", delta_puro(p_tl), "SOPRA MEDIA" if p_tl >= 0 else "SOTTO MEDIA"],
            ["Intense Actions >2\"", f"{cur_az2:.0f}", f"{avg_az2:.0f}", delta_puro(p_az2), "SOPRA MEDIA" if p_az2 >= 0 else "SOTTO MEDIA"],
            ["TOTAL GENERAL VOLUME ACHIEVEMENT", "", "", delta_puro(avg_vol), "VOLUME GLOBALE"],
            ["TL High", f"{cur_tlh:.0f}", f"{avg_tlh:.0f}", delta_puro(p_tlh), "SOPRA MEDIA" if p_tlh >= 0 else "SOTTO MEDIA"],
            ["High Acc Events", f"{cur_acc:.0f}", f"{avg_acc:.0f}", delta_puro(p_acc), "SOPRA MEDIA" if p_acc >= 0 else "SOTTO MEDIA"],
            ["High Dec Events", f"{cur_dec:.0f}", f"{avg_dec:.0f}", delta_puro(p_dec), "SOPRA MEDIA" if p_dec >= 0 else "SOTTO MEDIA"],
            ["TOTAL HIGH INTENSITY ACHIEVEMENT", "", "", delta_puro(avg_int), "ALTA INTENSITÀ"],
            ["TL / Min", f"{cur_tl_pm:.1f}", f"{avg_tl_pm:.1f}", delta_puro(p_tl_pm), "SOPRA MEDIA" if p_tl_pm >= 0 else "SOTTO MEDIA"],
            ["High Acc / Min", f"{cur_acc_pm:.1f}", f"{avg_acc_pm:.1f}", delta_puro(p_acc_pm), "SOPRA MEDIA" if p_acc_pm >= 0 else "SOTTO MEDIA"],
            ["High Dec / Min", f"{cur_dec_pm:.1f}", f"{avg_dec_pm:.1f}", delta_puro(p_dec_pm), "SOPRA MEDIA" if p_dec_pm >= 0 else "SOTTO MEDIA"],
            ["TL High / Min", f"{cur_tlh_pm:.1f}", f"{avg_tlh_pm:.1f}", delta_puro(p_tlh_pm), "SOPRA MEDIA" if p_tlh_pm >= 0 else "SOTTO MEDIA"],
            ["Intense Actions / Min", f"{cur_az2_pm:.1f}", f"{avg_az2_pm:.1f}", delta_puro(p_az2_pm), "SOPRA MEDIA" if p_az2_pm >= 0 else "SOTTO MEDIA"],
            ["TOTAL DENSITY ACHIEVEMENT", "", "", delta_puro(avg_den), "DENSITÀ (WORK RATE)"]
        ]
        t_dist = Table(rows_dist, colWidths=[240, 130, 130, 130, 162])
        style_dist = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f172a')), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, -1), 8.5),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'), ('ALIGN', (1, 0), (-1, -1), 'CENTER'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4), ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ]
        for idx_row, hex_bg, hex_txt in [(4, '#e0f2fe', '#0284c7'), (8, '#fee2e2', '#dc2626'), (14, '#fef3c7', '#d97706')]:
            style_dist.extend([('BACKGROUND', (0, idx_row), (-1, idx_row), colors.HexColor(hex_bg)), ('TEXTCOLOR', (0, idx_row), (-1, idx_row), colors.HexColor(hex_txt)), ('FONTNAME', (0, idx_row), (-1, idx_row), 'Helvetica-Bold'), ('SPAN', (0, idx_row), (2, idx_row))])
        t_dist.setStyle(TableStyle(style_dist))
        colora_delta(t_dist, rows_dist, [3])
        elements.append(t_dist)
        elements.append(Spacer(1, 8))

        d_dist = delta_puro(calcola_delta_percentuale(get_val(dati_sessione, 'DISTANCE'), get_val(medie_storiche_gps, 'DISTANCE')))
        d_r3_30 = delta_puro(calcola_delta_percentuale(get_val(dati_sessione, 'Recuperi IMU 3-30s'), get_val(medie_storiche, 'Recuperi IMU 3-30s')))
        d_r30_60 = delta_puro(calcola_delta_percentuale(get_val(dati_sessione, 'Recuperi IMU 30-60s'), get_val(medie_storiche, 'Recuperi IMU 30-60s')))
        d_r1_5 = delta_puro(calcola_delta_percentuale(get_val(dati_sessione, 'Recuperi IMU 1-5m'), get_val(medie_storiche, 'Recuperi IMU 1-5m')))

        kpi_grid = [
            ["DISTANCE", "DURATA", "TRAINING LOAD", "TL / MIN", "HIGH ACC", "HIGH DEC", "REC 3\"-30\"", "REC 30\"-60\"", "REC 1'-5'"],
            [d_dist, delta_puro(p_min), delta_puro(p_tl), delta_puro(p_tl_pm), delta_puro(p_acc), delta_puro(p_dec), d_r3_30, d_r30_60, d_r1_5]
        ]
        t_kpi = Table(kpi_grid, colWidths=[88]*9)
        t_kpi.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (5, 0), colors.HexColor('#0f172a')), ('BACKGROUND', (6, 0), (8, 0), colors.HexColor('#047857')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white), ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8), ('FONTSIZE', (0, 1), (-1, 1), 11),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#f8fafc')), ('TEXTCOLOR', (0, 1), (-1, 1), colors.HexColor('#0ea5e9')),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e2e8f0'))
        ]))
        colora_delta(t_kpi, kpi_grid, range(9))
        elements.append(t_kpi)
        need_break = True

    # --- SOTTOAREA 2: CARICO ENERGETICO ---
    if sottoarea in ["Tutte", "Carico_Energetico"]:
        if need_break: elements.append(PageBreak())
        elements.append(Paragraph("CARICO ENERGETICO — TRAINING LOAD BANDS & TIME %", sec_style))

        tl_totale = get_val(dati_sessione, 'Training Load', 1000)
        val_stand, val_low, val_med, val_high = get_val(dati_sessione, 'TL_Stand', tl_totale*0.15), get_val(dati_sessione, 'TL_Low', tl_totale*0.25), get_val(dati_sessione, 'TL_Medium', tl_totale*0.35), get_val(dati_sessione, 'TL_High', tl_totale*0.25)
        med_stand, med_low, med_med, med_high = get_val(medie_storiche, 'TL_Stand', tl_totale*0.12), get_val(medie_storiche, 'TL_Low', tl_totale*0.28), get_val(medie_storiche, 'TL_Medium', tl_totale*0.30), get_val(medie_storiche, 'TL_High', tl_totale*0.30)

        val_t_stand, val_t_low, val_t_med, val_t_high = get_val(dati_sessione, 'TL_T_Stand', 47.0), get_val(dati_sessione, 'TL_T_Low', 34.0), get_val(dati_sessione, 'TL_T_Medium', 13.0), get_val(dati_sessione, 'TL_T_High', 7.0)
        med_t_stand, med_t_low, med_t_med, med_t_high = get_val(medie_storiche, 'TL_T_Stand', 36.0), get_val(medie_storiche, 'TL_T_Low', 45.0), get_val(medie_storiche, 'TL_T_Medium', 13.0), get_val(medie_storiche, 'TL_T_High', 6.0)

        rows_en = [
            ["FASCIA ENERGETICA", "VOLUME SESSIONE", "MEDIA STORICA", "DELTA VOL.", "% TEMPO SESSIONE", "MEDIA % TEMPO", "DELTA % TEMPO"],
            ["TL Stand", f"{val_stand:.0f}", f"{med_stand:.0f}", delta_puro(calcola_delta_percentuale(val_stand, med_stand)), f"{val_t_stand:.0f}%", f"{med_t_stand:.0f}%", delta_puro(calcola_delta_percentuale(val_t_stand, med_t_stand))],
            ["TL Low", f"{val_low:.0f}", f"{med_low:.0f}", delta_puro(calcola_delta_percentuale(val_low, med_low)), f"{val_t_low:.0f}%", f"{med_t_low:.0f}%", delta_puro(calcola_delta_percentuale(val_t_low, med_t_low))],
            ["TL Medium", f"{val_med:.0f}", f"{med_med:.0f}", delta_puro(calcola_delta_percentuale(val_med, med_med)), f"{val_t_med:.0f}%", f"{med_t_med:.0f}%", delta_puro(calcola_delta_percentuale(val_t_med, med_t_med))],
            ["TL High", f"{val_high:.0f}", f"{med_high:.0f}", delta_puro(calcola_delta_percentuale(val_high, med_high)), f"{val_t_high:.0f}%", f"{med_t_high:.0f}%", delta_puro(calcola_delta_percentuale(val_t_high, med_t_high))]
        ]
        t_en = Table(rows_en, colWidths=[140, 108, 108, 108, 112, 108, 108])
        t_en.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0A192F')), ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#38bdf8')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
            ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        colora_delta(t_en, rows_en, [3, 6])
        elements.append(t_en)
        elements.append(Spacer(1, 14))

        fig_b1 = go.Figure(data=[
            go.Bar(name='Sessione', x=['Stand', 'Low', 'Medium', 'High'], y=[val_stand, val_low, val_med, val_high], marker_color=['#94a3b8', '#0ea5e9', '#f59e0b', '#ef4444']),
            go.Bar(name='Media', x=['Stand', 'Low', 'Medium', 'High'], y=[med_stand, med_low, med_med, med_high], marker_color='#cbd5e1')
        ])
        fig_b1.update_layout(title="Training Load Bands (Volume)", barmode='group', paper_bgcolor='white', plot_bgcolor='white', font=dict(color='#0f172a', size=13), margin=dict(l=40, r=20, t=45, b=35))

        fig_b2 = go.Figure(data=[
            go.Bar(name='Sessione %T', x=['Stand', 'Low', 'Medium', 'High'], y=[val_t_stand, val_t_low, val_t_med, val_t_high], marker_color=['#94a3b8', '#0ea5e9', '#f59e0b', '#ef4444']),
            go.Bar(name='Media %T', x=['Stand', 'Low', 'Medium', 'High'], y=[med_t_stand, med_t_low, med_t_med, med_t_high], marker_color='#cbd5e1')
        ])
        fig_b2.update_layout(title="Training Load Time % Bands", barmode='group', paper_bgcolor='white', plot_bgcolor='white', font=dict(color='#0f172a', size=13), margin=dict(l=40, r=20, t=45, b=35))

        t_charts_en = Table([[fig_to_rl_image(fig_b1, 385, 210), fig_to_rl_image(fig_b2, 385, 210)]], colWidths=[396, 396])
        t_charts_en.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e2e8f0'))]))
        elements.append(KeepTogether([t_charts_en]))
        need_break = True

    # --- SOTTOAREA 3: DATI MECCANICI & GPS ---
    if sottoarea in ["Tutte", "Dati_Meccanici_GPS"]:
        if need_break: elements.append(PageBreak())
        elements.append(Paragraph("DATI MECCANICI IMU & SATELLITARI GPS", sec_style))

        val_pl, med_pl = get_val(dati_sessione, 'Player Load'), get_val(medie_storiche, 'Player Load')
        val_dist, med_dist = get_val(dati_sessione, 'DISTANCE'), get_val(medie_storiche_gps, 'DISTANCE')
        val_hml, med_hml = get_val(dati_sessione, 'HML Distance >25.5W'), get_val(medie_storiche_gps, 'HML Distance >25.5W')
        val_vhml, med_vhml = get_val(dati_sessione, 'VHML Distance >50W'), get_val(medie_storiche_gps, 'VHML Distance >50W')
        val_hdec, med_hdec = get_val(dati_sessione, 'High Dec Events <-3.5 m/s2'), get_val(medie_storiche_gps, 'High Dec Events <-3.5 m/s2')
        val_rec, med_rec = get_val(dati_sessione, 'Recovery Time <5W %'), get_val(medie_storiche_gps, 'Recovery Time <5W %')
        val_eq, med_eq = get_val(dati_sessione, 'Equivalent Distance %'), get_val(medie_storiche_gps, 'Equivalent Distance %')
        val_an, med_an = get_val(dati_sessione, 'Anaerobic index %'), get_val(medie_storiche_gps, 'Anaerobic index %')

        rows_mg = [
            ["CATEGORIA", "METRICA", "SESSION SCORE", "MEDIA STORICA", "DELTA %"],
            ["IMU", "Duration (min)", f"{cur_min:.0f}", f"{avg_min:.0f}", delta_puro(p_min)],
            ["IMU", "Player Load", f"{val_pl:.0f}", f"{med_pl:.0f}", delta_puro(calcola_delta_percentuale(val_pl, med_pl))],
            ["IMU", "Training Load", f"{cur_tl:.0f}", f"{avg_tl:.0f}", delta_puro(p_tl)],
            ["IMU", "High Acceleration IMU", f"{cur_acc:.0f}", f"{avg_acc:.0f}", delta_puro(p_acc)],
            ["IMU", "High Deceleration IMU", f"{cur_dec:.0f}", f"{avg_dec:.0f}", delta_puro(p_dec)],
        ]
        if str(ambiente).lower() != "indoor":
            rows_mg.extend([
                ["GPS", "Distance (m)", f"{val_dist:.0f}", f"{med_dist:.0f}", delta_puro(calcola_delta_percentuale(val_dist, med_dist))],
                ["GPS", "HML Distance >25.5W (m)", f"{val_hml:.0f}", f"{med_hml:.0f}", delta_puro(calcola_delta_percentuale(val_hml, med_hml))],
                ["GPS", "VHML Distance >50W (m)", f"{val_vhml:.0f}", f"{med_vhml:.0f}", delta_puro(calcola_delta_percentuale(val_vhml, med_vhml))],
                ["GPS", "High Dec Events <-3.5 m/s²", f"{val_hdec:.0f}", f"{med_hdec:.0f}", delta_puro(calcola_delta_percentuale(val_hdec, med_hdec))],
                ["GPS %", "Recovery Time <5W %", f"{val_rec:.0f}%", f"{med_rec:.0f}%", delta_puro(calcola_delta_percentuale(val_rec, med_rec))],
                ["GPS %", "Equivalent Distance %", f"{val_eq:.0f}%", f"{med_eq:.0f}%", delta_puro(calcola_delta_percentuale(val_eq, med_eq))],
                ["GPS %", "Anaerobic Index %", f"{val_an:.0f}%", f"{med_an:.0f}%", delta_puro(calcola_delta_percentuale(val_an, med_an))],
            ])

        t_mg = Table(rows_mg, colWidths=[90, 260, 145, 145, 152])
        t_mg.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f172a')), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, -1), 8.5),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('ALIGN', (1, 1), (1, -1), 'LEFT'),
            ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1'))
        ]))
        colora_delta(t_mg, rows_mg, [4])
        elements.append(t_mg)
        elements.append(Spacer(1, 10))

        fig_imu_pdf = go.Figure(data=[
            go.Bar(name='Sessione', x=['Acc HI IMU', 'Dec HI IMU'], y=[cur_acc, cur_dec], marker_color='#10b981'),
            go.Bar(name='Media', x=['Acc HI IMU', 'Dec HI IMU'], y=[avg_acc, avg_dec], marker_color='#cbd5e1')
        ])
        fig_imu_pdf.update_layout(title="Eventi Meccanici IMU", barmode='group', paper_bgcolor='white', plot_bgcolor='white', font=dict(color='#0f172a', size=13), margin=dict(l=40, r=20, t=40, b=30))

        fig_gps_pdf = go.Figure(data=[
            go.Bar(name='Sessione', x=['Recovery <5W', 'Equivalent Dist', 'Anaerobic Index'], y=[val_rec, val_eq, val_an], marker_color='#f59e0b'),
            go.Bar(name='Media', x=['Recovery <5W', 'Equivalent Dist', 'Anaerobic Index'], y=[med_rec, med_eq, med_an], marker_color='#cbd5e1')
        ])
        fig_gps_pdf.update_layout(title="Indici GPS e Recupero (%)", barmode='group', paper_bgcolor='white', plot_bgcolor='white', font=dict(color='#0f172a', size=13), margin=dict(l=40, r=20, t=40, b=30))

        t_c_mg = Table([[fig_to_rl_image(fig_imu_pdf, 385, 165), fig_to_rl_image(fig_gps_pdf, 385, 165)]], colWidths=[396, 396])
        t_c_mg.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e2e8f0'))]))
        elements.append(KeepTogether([t_c_mg]))
        need_break = True

    # --- SOTTOAREA 4: READINESS (ACUTO / CRONICO) ---
    if sottoarea in ["Tutte", "Readiness"] and df_storico is not None:
        if need_break: elements.append(PageBreak())
        elements.append(Paragraph("READINESS — ACUTE (2 DAYS) & CHRONIC (7 DAYS) LOAD", sec_style))

        df_ath_all = df_storico[(df_storico['Players'] == giocatore) & (df_storico['Dato_Simulato'] == False)].copy()
        df_ath_all['Date_obj'] = pd.to_datetime(df_ath_all['Date'], format="%d/%m/%Y", errors='coerce')
        target_date = pd.to_datetime(data_match, format="%d/%m/%Y", errors='coerce')

        if pd.notna(target_date):
            col_rtm = ['Minuti', 'Training Load', 'TL_High', 'High Decel IMU', 'High Accel IMU', 'Azioni Int. IMU >2']
            lbl_rtm = ['Time', 'Training Load', 'TL High', 'High Dec', 'High Acc', 'Actions >2"']
            df_ath_all[col_rtm] = df_ath_all[col_rtm].apply(pd.to_numeric, errors='coerce').fillna(0)

            radar_imgs = []
            for days_w, label_w in [(2, "ACUTE LOAD (2 DAYS BEFORE MATCH)"), (7, "CHRONIC LOAD (7 DAYS BEFORE MATCH)")]:
                w_start = target_date - timedelta(days=days_w)
                w_end = target_date - timedelta(days=1)
                b_end = w_start - timedelta(days=1)
                b_start = b_end - timedelta(days=27)

                val_w = df_ath_all[(df_ath_all['Date_obj'] >= w_start) & (df_ath_all['Date_obj'] <= w_end)][col_rtm].sum().fillna(0)
                df_b = df_ath_all[(df_ath_all['Date_obj'] >= b_start) & (df_ath_all['Date_obj'] <= b_end)]
                g_eff = (b_end - df_b['Date_obj'].min()).days + 1 if not df_b.empty else 28
                if g_eff <= 0: g_eff = 28
                blocchi = max(1.0, min(28.0, float(g_eff)) / days_w)
                val_a = (df_b[col_rtm].sum() / blocchi).fillna(0)

                pct = [(val_w[c] / val_a[c] * 100) if val_a[c] > 0 else 0 for c in col_rtm]

                rows_r = [
                    [label_w] + lbl_rtm,
                    ["Carico Finestra"] + [f"{val_w[c]:.0f}" for c in col_rtm],
                    ["Media Baseline (28gg)"] + [f"{val_a[c]:.0f}" for c in col_rtm],
                    ["% of Average (ACWR)"] + [f"{p:.0f}%" for p in pct]
                ]
                t_r = Table(rows_r, colWidths=[162] + [105]*6)
                t_r.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0A192F')), ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#38bdf8')),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, -1), 8.5),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
                    ('BACKGROUND', (0, 3), (-1, 3), colors.HexColor('#f1f5f9')), ('FONTNAME', (0, 3), (-1, 3), 'Helvetica-Bold'),
                    ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ]))
                colora_acwr(t_r, pct)
                elements.append(t_r)
                elements.append(Spacer(1, 6))

                fig_rad = go.Figure()
                fig_rad.add_trace(go.Scatterpolar(r=pct + [pct[0]], theta=lbl_rtm + [lbl_rtm[0]], fill='toself', name=label_w, line_color='#0ea5e9'))
                fig_rad.add_trace(go.Scatterpolar(r=[100]*7, theta=lbl_rtm + [lbl_rtm[0]], mode='lines', line=dict(color='#10b981', dash='dot'), name='100%'))
                fig_rad.update_layout(title=label_w, polar=dict(radialaxis=dict(visible=True, range=[0, max(130, max(pct)+10)])), showlegend=False, paper_bgcolor='white', margin=dict(t=40, b=20, l=40, r=40))
                radar_imgs.append(fig_to_rl_image(fig_rad, 360, 175))

            if len(radar_imgs) == 2:
                t_rad = Table([radar_imgs], colWidths=[396, 396])
                t_rad.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e2e8f0'))]))
                elements.append(KeepTogether([t_rad]))

    # Sezione Note Metodologiche & Bibliografia Validata
    elements.extend(genera_sezione_metodologia_pdf("match_per_point", styles))

    build_pdf_con_footer(doc, elements)
    return buffer.getvalue()


# =========================================================================
# 2. MOTORE PDF: ANALISI SESSIONE (TUTTE LE SOTTOAREE)
# =========================================================================
def crea_pdf_sessione_m0v3(giocatore, data_sess, sessione, tipologia, campo, ambiente, sparring, dati_sessione, medie_tipo, medie_match, medie_tipo_gps=None, df_completo=None, sottoarea="Tutte"):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), rightMargin=25, leftMargin=25, topMargin=25, bottomMargin=25)
    elements = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('M0V3Title', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=20, textColor=colors.HexColor('#0f172a'), spaceAfter=4)
    sub_style = ParagraphStyle('M0V3Sub', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=11, textColor=colors.HexColor('#0ea5e9'), spaceAfter=12)
    sec_style = ParagraphStyle('M0V3Sec', keepWithNext=1, parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=13, textColor=colors.HexColor('#0f172a'), spaceBefore=10, spaceAfter=8)

    sub_label = "REPORT COMPLETO" if sottoarea == "Tutte" else sottoarea.replace('_', ' ').upper()
    header_title = [
        Paragraph(f"M0V3 ANALYTICS — SESSION REPORT ({sub_label})", title_style),
        Paragraph(f"ATLETA: {giocatore.upper()}   |   SESSIONE: {sessione}   |   TIPO: {tipologia.upper()}", sub_style)
    ]
    if os.path.exists(LOGO_PATH):
        logo_img = RLImage(LOGO_PATH, width=55, height=55)
        t_head = Table([[header_title, logo_img]], colWidths=[715, 75])
        t_head.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('ALIGN', (1, 0), (1, 0), 'RIGHT'), ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0)]))
        elements.append(t_head)
    else:
        elements.extend(header_title)

    data_meta = [
        ["DATA SESSIONE", "TIPOLOGIA", "SUPERFICIE", "AMBIENTE", "MINUTI SPARRING"],
        [str(data_sess), str(tipologia), str(campo), str(ambiente), f"{sparring} min"]
    ]
    t_meta = Table(data_meta, colWidths=[158, 158, 158, 158, 158])
    t_meta.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0A192F')), ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#38bdf8')),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, 0), 9), ('FONTSIZE', (0, 1), (-1, 1), 11),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7), ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#f8fafc')), ('TEXTCOLOR', (0, 1), (-1, 1), colors.HexColor('#0f172a')),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e2e8f0'))
    ]))
    elements.append(t_meta)
    elements.append(Spacer(1, 10))

    def calc_pm(val, mins): return val / mins if mins > 0 else 0

    c_min, c_tl, c_az2 = get_val(dati_sessione, 'Minuti'), get_val(dati_sessione, 'Training Load'), get_val(dati_sessione, 'Azioni Int. IMU >2')
    c_tlh, c_acc, c_dec = get_val(dati_sessione, 'TL_High'), get_val(dati_sessione, 'High Accel IMU'), get_val(dati_sessione, 'High Decel IMU')
    c_tl_pm, c_acc_pm, c_dec_pm, c_tlh_pm, c_az2_pm = calc_pm(c_tl, c_min), calc_pm(c_acc, c_min), calc_pm(c_dec, c_min), calc_pm(c_tlh, c_min), calc_pm(c_az2, c_min)

    t_min, t_tl, t_az2 = get_val(medie_tipo, 'Minuti'), get_val(medie_tipo, 'Training Load'), get_val(medie_tipo, 'Azioni Int. IMU >2')
    t_tlh, t_acc, t_dec = get_val(medie_tipo, 'TL_High'), get_val(medie_tipo, 'High Accel IMU'), get_val(medie_tipo, 'High Decel IMU')
    t_tl_pm, t_acc_pm, t_dec_pm, t_tlh_pm, t_az2_pm = calc_pm(t_tl, t_min), calc_pm(t_acc, t_min), calc_pm(t_dec, t_min), calc_pm(t_tlh, t_min), calc_pm(t_az2, t_min)

    m_min, m_tl, m_az2 = get_val(medie_match, 'Minuti'), get_val(medie_match, 'Training Load'), get_val(medie_match, 'Azioni Int. IMU >2')
    m_tlh, m_acc, m_dec = get_val(medie_match, 'TL_High'), get_val(medie_match, 'High Accel IMU'), get_val(medie_match, 'High Decel IMU')
    m_tl_pm, m_acc_pm, m_dec_pm, m_tlh_pm, m_az2_pm = calc_pm(m_tl, m_min), calc_pm(m_acc, m_min), calc_pm(m_dec, m_min), calc_pm(m_tlh, m_min), calc_pm(m_az2, m_min)

    pt_min, pt_tl, pt_az2 = calcola_delta_percentuale(c_min, t_min), calcola_delta_percentuale(c_tl, t_tl), calcola_delta_percentuale(c_az2, t_az2)
    pt_tlh, pt_acc, pt_dec = calcola_delta_percentuale(c_tlh, t_tlh), calcola_delta_percentuale(c_acc, t_acc), calcola_delta_percentuale(c_dec, t_dec)
    pt_tl_pm, pt_acc_pm, pt_dec_pm, pt_tlh_pm, pt_az2_pm = calcola_delta_percentuale(c_tl_pm, t_tl_pm), calcola_delta_percentuale(c_acc_pm, t_acc_pm), calcola_delta_percentuale(c_dec_pm, t_dec_pm), calcola_delta_percentuale(c_tlh_pm, t_tlh_pm), calcola_delta_percentuale(c_az2_pm, t_az2_pm)

    pm_min, pm_tl, pm_az2 = calcola_delta_percentuale(c_min, m_min), calcola_delta_percentuale(c_tl, m_tl), calcola_delta_percentuale(c_az2, m_az2)
    pm_tlh, pm_acc, pm_dec = calcola_delta_percentuale(c_tlh, m_tlh), calcola_delta_percentuale(c_acc, m_acc), calcola_delta_percentuale(c_dec, m_dec)
    pm_tl_pm, pm_acc_pm, pm_dec_pm, pm_tlh_pm, pm_az2_pm = calcola_delta_percentuale(c_tl_pm, m_tl_pm), calcola_delta_percentuale(c_acc_pm, m_acc_pm), calcola_delta_percentuale(c_dec_pm, m_dec_pm), calcola_delta_percentuale(c_tlh_pm, m_tlh_pm), calcola_delta_percentuale(c_az2_pm, m_az2_pm)

    avg_vol_t, avg_vol_m = (pt_min + pt_tl + pt_az2) / 3, (pm_min + pm_tl + pm_az2) / 3
    avg_int_t, avg_int_m = (pt_tlh + pt_acc + pt_dec) / 3, (pm_tlh + pm_acc + pm_dec) / 3
    avg_den_t, avg_den_m = (pt_tl_pm + pt_acc_pm + pt_dec_pm + pt_tlh_pm + pt_az2_pm) / 5, (pm_tl_pm + pm_acc_pm + pm_dec_pm + pm_tlh_pm + pm_az2_pm) / 5

    need_break = False

    # --- SOTTOAREA 1: SINTESI & DELTA ---
    if sottoarea in ["Tutte", "Sintesi_Delta"]:
        elements.append(Paragraph("SINTESI & DELTA — DISTANCE FROM THE AVERAGES (VS TYPE & VS MATCH)", sec_style))
        rows_dist = [
            ["PARAMETRO", "SESSION SCORE", "MEDIA TIPO", "DELTA vs TIPO", "MEDIA MATCH", "DELTA vs MATCH"],
            ["Time (min)", f"{c_min:.0f}", f"{t_min:.0f}", delta_puro(pt_min), f"{m_min:.0f}", delta_puro(pm_min)],
            ["Training Load", f"{c_tl:.0f}", f"{t_tl:.0f}", delta_puro(pt_tl), f"{m_tl:.0f}", delta_puro(pm_tl)],
            ["Intense Actions >2\"", f"{c_az2:.0f}", f"{t_az2:.0f}", delta_puro(pt_az2), f"{m_az2:.0f}", delta_puro(pm_az2)],
            ["TOTAL GENERAL VOLUME ACHIEVEMENT", "", "", delta_puro(avg_vol_t), "", delta_puro(avg_vol_m)],
            ["High Acc Events", f"{c_acc:.0f}", f"{t_acc:.0f}", delta_puro(pt_acc), f"{m_acc:.0f}", delta_puro(pm_acc)],
            ["High Dec Events", f"{c_dec:.0f}", f"{t_dec:.0f}", delta_puro(pt_dec), f"{m_dec:.0f}", delta_puro(pm_dec)],
            ["TL High", f"{c_tlh:.0f}", f"{t_tlh:.0f}", delta_puro(pt_tlh), f"{m_tlh:.0f}", delta_puro(pm_tlh)],
            ["TOTAL HIGH INTENSITY ACHIEVEMENT", "", "", delta_puro(avg_int_t), "", delta_puro(avg_int_m)],
            ["TL / Min", f"{c_tl_pm:.1f}", f"{t_tl_pm:.1f}", delta_puro(pt_tl_pm), f"{m_tl_pm:.1f}", delta_puro(pm_tl_pm)],
            ["High Acc / Min", f"{c_acc_pm:.1f}", f"{t_acc_pm:.1f}", delta_puro(pt_acc_pm), f"{m_acc_pm:.1f}", delta_puro(pm_acc_pm)],
            ["High Dec / Min", f"{c_dec_pm:.1f}", f"{t_dec_pm:.1f}", delta_puro(pt_dec_pm), f"{m_dec_pm:.1f}", delta_puro(pm_dec_pm)],
            ["Intense Actions / Min", f"{c_az2_pm:.1f}", f"{t_az2_pm:.1f}", delta_puro(pt_az2_pm), f"{m_az2_pm:.1f}", delta_puro(pm_az2_pm)],
            ["TL High / Min", f"{c_tlh_pm:.1f}", f"{t_tlh_pm:.1f}", delta_puro(pt_tlh_pm), f"{m_tlh_pm:.1f}", delta_puro(pm_tlh_pm)],
            ["TOTAL DENSITY ACHIEVEMENT", "", "", delta_puro(avg_den_t), "", delta_puro(avg_den_m)]
        ]
        t_dist = Table(rows_dist, colWidths=[212, 115, 115, 115, 115, 120])
        style_dist = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f172a')), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'), ('ALIGN', (1, 0), (-1, -1), 'CENTER'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5), ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ]
        for idx_row, hex_bg, hex_txt in [(4, '#dcfce7', '#166534'), (8, '#fee2e2', '#dc2626'), (14, '#fef3c7', '#d97706')]:
            style_dist.extend([('BACKGROUND', (0, idx_row), (-1, idx_row), colors.HexColor(hex_bg)), ('TEXTCOLOR', (0, idx_row), (-1, idx_row), colors.HexColor(hex_txt)), ('FONTNAME', (0, idx_row), (-1, idx_row), 'Helvetica-Bold'), ('SPAN', (0, idx_row), (2, idx_row))])
        t_dist.setStyle(TableStyle(style_dist))
        colora_delta(t_dist, rows_dist, [3])
        elements.append(t_dist)
        need_break = True

    # --- SOTTOAREA 2: CARICO ENERGETICO ---
    if sottoarea in ["Tutte", "Carico_Energetico"]:
        if need_break: elements.append(PageBreak())
        elements.append(Paragraph("CARICO ENERGETICO — TRAINING LOAD BANDS & TIME %", sec_style))

        tl_totale = get_val(dati_sessione, 'Training Load', 1000)
        val_stand, val_low, val_med, val_high = get_val(dati_sessione, 'TL_Stand', tl_totale*0.15), get_val(dati_sessione, 'TL_Low', tl_totale*0.25), get_val(dati_sessione, 'TL_Medium', tl_totale*0.35), get_val(dati_sessione, 'TL_High', tl_totale*0.25)
        med_stand, med_low, med_med, med_high = get_val(medie_tipo, 'TL_Stand', tl_totale*0.12), get_val(medie_tipo, 'TL_Low', tl_totale*0.28), get_val(medie_tipo, 'TL_Medium', tl_totale*0.30), get_val(medie_tipo, 'TL_High', tl_totale*0.30)

        val_t_stand, val_t_low, val_t_med, val_t_high = get_val(dati_sessione, 'TL_T_Stand', 47.0), get_val(dati_sessione, 'TL_T_Low', 34.0), get_val(dati_sessione, 'TL_T_Medium', 13.0), get_val(dati_sessione, 'TL_T_High', 7.0)
        med_t_stand, med_t_low, med_t_med, med_t_high = get_val(medie_tipo, 'TL_T_Stand', 36.0), get_val(medie_tipo, 'TL_T_Low', 45.0), get_val(medie_tipo, 'TL_T_Medium', 13.0), get_val(medie_tipo, 'TL_T_High', 6.0)

        rows_en = [
            ["FASCIA ENERGETICA", "VOLUME SESSIONE", "MEDIA TIPO", "DELTA VOL.", "% TEMPO SESSIONE", "MEDIA % TIPO", "DELTA % TEMPO"],
            ["TL Stand", f"{val_stand:.0f}", f"{med_stand:.0f}", delta_puro(calcola_delta_percentuale(val_stand, med_stand)), f"{val_t_stand:.0f}%", f"{med_t_stand:.0f}%", delta_puro(calcola_delta_percentuale(val_t_stand, med_t_stand))],
            ["TL Low", f"{val_low:.0f}", f"{med_low:.0f}", delta_puro(calcola_delta_percentuale(val_low, med_low)), f"{val_t_low:.0f}%", f"{med_t_low:.0f}%", delta_puro(calcola_delta_percentuale(val_t_low, med_t_low))],
            ["TL Medium", f"{val_med:.0f}", f"{med_med:.0f}", delta_puro(calcola_delta_percentuale(val_med, med_med)), f"{val_t_med:.0f}%", f"{med_t_med:.0f}%", delta_puro(calcola_delta_percentuale(val_t_med, med_t_med))],
            ["TL High", f"{val_high:.0f}", f"{med_high:.0f}", delta_puro(calcola_delta_percentuale(val_high, med_high)), f"{val_t_high:.0f}%", f"{med_t_high:.0f}%", delta_puro(calcola_delta_percentuale(val_t_high, med_t_high))]
        ]
        t_en = Table(rows_en, colWidths=[140, 108, 108, 108, 112, 108, 108])
        t_en.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0A192F')), ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#38bdf8')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
            ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        colora_delta(t_en, rows_en, [3, 6])
        elements.append(t_en)
        elements.append(Spacer(1, 14))

        fig_b1 = go.Figure(data=[
            go.Bar(name='Sessione', x=['Stand', 'Low', 'Medium', 'High'], y=[val_stand, val_low, val_med, val_high], marker_color=['#94a3b8', '#0ea5e9', '#f59e0b', '#ef4444']),
            go.Bar(name='Media Tipo', x=['Stand', 'Low', 'Medium', 'High'], y=[med_stand, med_low, med_med, med_high], marker_color='#cbd5e1')
        ])
        fig_b1.update_layout(title="Training Load Bands (Volume)", barmode='group', paper_bgcolor='white', plot_bgcolor='white', font=dict(color='#0f172a', size=13), margin=dict(l=40, r=20, t=45, b=35))

        fig_b2 = go.Figure(data=[
            go.Bar(name='Sessione %T', x=['Stand', 'Low', 'Medium', 'High'], y=[val_t_stand, val_t_low, val_t_med, val_t_high], marker_color=['#94a3b8', '#0ea5e9', '#f59e0b', '#ef4444']),
            go.Bar(name='Media Tipo %T', x=['Stand', 'Low', 'Medium', 'High'], y=[med_t_stand, med_t_low, med_t_med, med_t_high], marker_color='#cbd5e1')
        ])
        fig_b2.update_layout(title="Training Load Time % Bands", barmode='group', paper_bgcolor='white', plot_bgcolor='white', font=dict(color='#0f172a', size=13), margin=dict(l=40, r=20, t=45, b=35))

        t_charts_en = Table([[fig_to_rl_image(fig_b1, 385, 210), fig_to_rl_image(fig_b2, 385, 210)]], colWidths=[396, 396])
        t_charts_en.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e2e8f0'))]))
        elements.append(KeepTogether([t_charts_en]))
        need_break = True

    # --- SOTTOAREA 3: DATI MECCANICI, GPS, AEROBIC & ANAEROBIC ---
    if sottoarea in ["Tutte", "Dati_Meccanici_GPS"]:
        if need_break: elements.append(PageBreak())
        elements.append(Paragraph("DATI MECCANICI IMU, GPS & AREE METABOLICHE (AEROBIC / ANAEROBIC)", sec_style))

        c_high_t, c_med_t, c_stand_t = get_val(dati_sessione, 'TL_T_High'), get_val(dati_sessione, 'TL_T_Medium'), get_val(dati_sessione, 'TL_T_Stand')
        t_high_t, t_med_t, t_stand_t = get_val(medie_tipo, 'TL_T_High'), get_val(medie_tipo, 'TL_T_Medium'), get_val(medie_tipo, 'TL_T_Stand')
        m_high_t, m_med_t, m_stand_t = get_val(medie_match, 'TL_T_High'), get_val(medie_match, 'TL_T_Medium'), get_val(medie_match, 'TL_T_Stand')

        c_mh, t_mh, m_mh = c_high_t + c_med_t, t_high_t + t_med_t, m_high_t + m_med_t
        pt_mh, pm_mh = calcola_delta_percentuale(c_mh, t_mh), calcola_delta_percentuale(c_mh, m_mh)
        pt_st, pm_st = calcola_delta_percentuale(c_stand_t, t_stand_t), calcola_delta_percentuale(c_stand_t, m_stand_t)
        tot_aero_t, tot_aero_m = (pt_mh - pt_st) / 2, (pm_mh - pm_st) / 2

        c_mech_pm = (c_acc + c_dec) / c_min if c_min > 0 else 0
        t_mech_pm = (t_acc + t_dec) / t_min if t_min > 0 else 0
        m_mech_pm = (m_acc + m_dec) / m_min if m_min > 0 else 0
        pt_mech_pm, pm_mech_pm = calcola_delta_percentuale(c_mech_pm, t_mech_pm), calcola_delta_percentuale(c_mech_pm, m_mech_pm)
        tot_ana_t, tot_ana_m = (pt_tlh_pm + pt_mech_pm + pt_az2_pm) / 3, (pm_tlh_pm + pm_mech_pm + pm_az2_pm) / 3

        rows_metab = [
            ["AREA METABOLICA", "METRICA CHIAVE", "SCORE", "DELTA vs TIPO", "DELTA vs MATCH"],
            ["AEROBIC", "% Time TL Med-High (>0.75G)", f"{c_mh:.0f}%", delta_puro(pt_mh), delta_puro(pm_mh)],
            ["AEROBIC", "% Time TL Stand (<0.2G)", f"{c_stand_t:.0f}%", delta_puro(pt_st), delta_puro(pm_st)],
            ["TOTAL AEROBIC AREA COMPARISON", "", "", delta_puro(tot_aero_t), delta_puro(tot_aero_m)],
            ["ANAEROBIC", "TL High / min", f"{c_tlh_pm:.1f}", delta_puro(pt_tlh_pm), delta_puro(pm_tlh_pm)],
            ["ANAEROBIC", "Mechanical Actions (Acc+Dec) / min", f"{c_mech_pm:.1f}", delta_puro(pt_mech_pm), delta_puro(pm_mech_pm)],
            ["ANAEROBIC", "Intense Actions >2\" / min", f"{c_az2_pm:.1f}", delta_puro(pt_az2_pm), delta_puro(pm_az2_pm)],
            ["TOTAL ANAEROBIC DENSITY COMPARISON", "", "", delta_puro(tot_ana_t), delta_puro(tot_ana_m)]
        ]
        t_metab = Table(rows_metab, colWidths=[150, 242, 130, 135, 135])
        t_metab.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f172a')), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, -1), 8.5),
            ('ALIGN', (0, 0), (1, -1), 'LEFT'), ('ALIGN', (2, 0), (-1, -1), 'CENTER'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4), ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
            ('BACKGROUND', (0, 3), (-1, 3), colors.HexColor('#dcfce7')), ('TEXTCOLOR', (0, 3), (-1, 3), colors.HexColor('#047857')), ('FONTNAME', (0, 3), (-1, 3), 'Helvetica-Bold'), ('SPAN', (0, 3), (2, 3)),
            ('BACKGROUND', (0, 7), (-1, 7), colors.HexColor('#fee2e2')), ('TEXTCOLOR', (0, 7), (-1, 7), colors.HexColor('#b91c1c')), ('FONTNAME', (0, 7), (-1, 7), 'Helvetica-Bold'), ('SPAN', (0, 7), (2, 7)),
        ]))
        colora_delta(t_metab, rows_metab, [3, 4])
        elements.append(t_metab)
        elements.append(Spacer(1, 10))

        val_pl, med_pl = get_val(dati_sessione, 'Player Load'), get_val(medie_tipo, 'Player Load')
        fig_load_pdf = go.Figure(data=[
            go.Bar(name='Sessione', x=['Player Load', 'Training Load'], y=[val_pl, c_tl], marker_color='#0ea5e9'),
            go.Bar(name='Media Tipo', x=['Player Load', 'Training Load'], y=[med_pl, t_tl], marker_color='#cbd5e1')
        ])
        fig_load_pdf.update_layout(title="Carico Globale IMU", barmode='group', paper_bgcolor='white', plot_bgcolor='white', font=dict(color='#0f172a', size=13), margin=dict(l=40, r=20, t=40, b=30))

        fig_imu_pdf = go.Figure(data=[
            go.Bar(name='Sessione', x=['Acc HI IMU', 'Dec HI IMU'], y=[c_acc, c_dec], marker_color='#10b981'),
            go.Bar(name='Media Tipo', x=['Acc HI IMU', 'Dec HI IMU'], y=[t_acc, t_dec], marker_color='#cbd5e1')
        ])
        fig_imu_pdf.update_layout(title="Eventi Meccanici IMU (Acc / Dec)", barmode='group', paper_bgcolor='white', plot_bgcolor='white', font=dict(color='#0f172a', size=13), margin=dict(l=40, r=20, t=40, b=30))

        t_charts = Table([[fig_to_rl_image(fig_load_pdf, 385, 175), fig_to_rl_image(fig_imu_pdf, 385, 175)]], colWidths=[396, 396])
        t_charts.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e2e8f0'))]))
        elements.append(KeepTogether([t_charts]))
        need_break = True

    # --- SOTTOAREA 4: READINESS (BEFORE TOMORROW) ---
    if sottoarea in ["Tutte", "Readiness"] and df_completo is not None:
        if need_break: elements.append(PageBreak())
        elements.append(Paragraph("BEFORE TOMORROW — ACUTE (2 DAYS) & CHRONIC (7 DAYS) READINESS", sec_style))

        df_ath_all = df_completo[(df_completo['Players'] == giocatore) & (df_completo['Dato_Simulato'] == False)].copy()
        df_ath_all['Date_obj'] = pd.to_datetime(df_ath_all['Date'], format="%d/%m/%Y", errors='coerce')
        target_date = pd.to_datetime(data_sess, format="%d/%m/%Y", errors='coerce')

        if pd.notna(target_date):
            col_rtm = ['Minuti', 'Training Load', 'TL_High', 'High Decel IMU', 'High Accel IMU', 'Azioni Int. IMU >2']
            lbl_rtm = ['Time', 'Training Load', 'TL High', 'High Dec', 'High Acc', 'Actions >2"']
            df_ath_all[col_rtm] = df_ath_all[col_rtm].apply(pd.to_numeric, errors='coerce').fillna(0)

            radar_imgs = []
            for days_w, label_w in [(2, "BEFORE TOMORROW - ACUTE LOAD (2 DAYS)"), (7, "BEFORE TOMORROW - CHRONIC LOAD (7 DAYS)")]:
                w_start = target_date - timedelta(days=days_w - 1)
                b_end = w_start - timedelta(days=1)
                b_start = b_end - timedelta(days=27)

                val_w = df_ath_all[(df_ath_all['Date_obj'] >= w_start) & (df_ath_all['Date_obj'] <= target_date)][col_rtm].sum().fillna(0)
                df_b = df_ath_all[(df_ath_all['Date_obj'] >= b_start) & (df_ath_all['Date_obj'] <= b_end)]
                g_eff = (b_end - df_b['Date_obj'].min()).days + 1 if not df_b.empty else 28
                if g_eff <= 0: g_eff = 28
                blocchi = max(1.0, min(28.0, float(g_eff)) / days_w)
                val_a = (df_b[col_rtm].sum() / blocchi).fillna(0)

                pct = [(val_w[c] / val_a[c] * 100) if val_a[c] > 0 else 0 for c in col_rtm]

                rows_r = [
                    [label_w] + lbl_rtm,
                    ["Carico Finestra"] + [f"{val_w[c]:.0f}" for c in col_rtm],
                    ["Media Baseline (28gg)"] + [f"{val_a[c]:.0f}" for c in col_rtm],
                    ["% of Average (ACWR)"] + [f"{p:.0f}%" for p in pct]
                ]
                t_r = Table(rows_r, colWidths=[162] + [105]*6)
                t_r.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0A192F')), ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#38bdf8')),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, -1), 8.5),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
                    ('BACKGROUND', (0, 3), (-1, 3), colors.HexColor('#f1f5f9')), ('FONTNAME', (0, 3), (-1, 3), 'Helvetica-Bold'),
                    ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ]))
                colora_acwr(t_r, pct)
                elements.append(t_r)
                elements.append(Spacer(1, 6))

                fig_rad = go.Figure()
                fig_rad.add_trace(go.Scatterpolar(r=pct + [pct[0]], theta=lbl_rtm + [lbl_rtm[0]], fill='toself', name=label_w, line_color='#0ea5e9'))
                fig_rad.add_trace(go.Scatterpolar(r=[100]*7, theta=lbl_rtm + [lbl_rtm[0]], mode='lines', line=dict(color='#10b981', dash='dot'), name='100%'))
                fig_rad.update_layout(title=label_w, polar=dict(radialaxis=dict(visible=True, range=[0, max(130, max(pct)+10)])), showlegend=False, paper_bgcolor='white', margin=dict(t=40, b=20, l=40, r=40))
                radar_imgs.append(fig_to_rl_image(fig_rad, 360, 175))

            if len(radar_imgs) == 2:
                t_rad = Table([radar_imgs], colWidths=[396, 396])
                t_rad.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e2e8f0'))]))
                elements.append(KeepTogether([t_rad]))

    # Sezione Note Metodologiche & Bibliografia Validata
    elements.extend(genera_sezione_metodologia_pdf("carico_interno" if tipologia == "S-RPE" else "acwr", styles))

    build_pdf_con_footer(doc, elements)
    return buffer.getvalue()


# =========================================================================
# 3. MOTORE PDF: TREND SETTIMANALE (TUTTE LE SOTTOAREE)
# =========================================================================
def crea_pdf_weekly_m0v3(giocatore, settimana_label, df_plot, sottoarea="Tutte"):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), rightMargin=25, leftMargin=25, topMargin=25, bottomMargin=25)
    elements = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('M0V3Title', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=20, textColor=colors.HexColor('#0f172a'), spaceAfter=4)
    sub_style = ParagraphStyle('M0V3Sub', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=11, textColor=colors.HexColor('#0ea5e9'), spaceAfter=12)
    sec_style = ParagraphStyle('M0V3Sec', keepWithNext=1, parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=13, textColor=colors.HexColor('#0f172a'), spaceBefore=8, spaceAfter=8)

    sub_label = "REPORT COMPLETO" if sottoarea == "Tutte" else sottoarea.replace('_', ' ').upper()
    header_title = [
        Paragraph(f"M0V3 ANALYTICS — WEEKLY TREND ({sub_label})", title_style),
        Paragraph(f"ATLETA: {giocatore.upper()}   |   SETTIMANA: {settimana_label}", sub_style)
    ]
    if os.path.exists(LOGO_PATH):
        logo_img = RLImage(LOGO_PATH, width=55, height=55)
        t_head = Table([[header_title, logo_img]], colWidths=[715, 75])
        t_head.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('ALIGN', (1, 0), (1, 0), 'RIGHT'), ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0)]))
        elements.append(t_head)
    else:
        elements.extend(header_title)

    elements.append(Paragraph("RIEPILOGO GIORNALIERO E TOTALI SETTIMANALI", sec_style))
    rows_w = [["GIORNO", "DATA", "MINUTI", "TRAINING LOAD", "TL HIGH", "HIGH ACC", "HIGH DEC", "AZIONI >2\"", "DIST. OUT (m)", "HML >25.5W"]]
    for _, r in df_plot.iterrows():
        rows_w.append([
            str(r['DayName']), str(r['ShortDate']),
            f"{r['Minuti']:.0f}", f"{r['Training Load']:.0f}", f"{r['TL_High']:.0f}",
            f"{r['High Accel IMU']:.0f}", f"{r['High Decel IMU']:.0f}", f"{r['Azioni Int. IMU >2']:.0f}",
            f"{r['DISTANCE_out']:.0f}", f"{r['HML_out']:.0f}"
        ])
    rows_w.append([
        "TOTALE SETTIMANA", "",
        f"{df_plot['Minuti'].sum():.0f}", f"{df_plot['Training Load'].sum():.0f}", f"{df_plot['TL_High'].sum():.0f}",
        f"{df_plot['High Accel IMU'].sum():.0f}", f"{df_plot['High Decel IMU'].sum():.0f}", f"{df_plot['Azioni Int. IMU >2'].sum():.0f}",
        f"{df_plot['DISTANCE_out'].sum():.0f}", f"{df_plot['HML_out'].sum():.0f}"
    ])

    t_w = Table(rows_w, colWidths=[92, 60, 75, 95, 75, 75, 75, 80, 85, 80])
    t_w.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0A192F')), ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#38bdf8')),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, -1), 8.5),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e0f2fe')), ('TEXTCOLOR', (0, -1), (-1, -1), colors.HexColor('#0284c7')),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'), ('SPAN', (0, -1), (1, -1)),
    ]))
    elements.append(t_w)
    elements.append(Spacer(1, 10))

    x_lbl = df_plot['DayName'] + " (" + df_plot['ShortDate'] + ")"
    def quick_bar(y_col, color, title):
        f = go.Figure(go.Bar(x=x_lbl, y=df_plot[y_col], marker_color=color, text=[f"{v:.0f}" if v > 0 else "" for v in df_plot[y_col]], textposition='outside'))
        f.update_layout(title=title, paper_bgcolor='white', plot_bgcolor='white', font=dict(color='#0f172a', size=12), margin=dict(l=40, r=20, t=45, b=35), yaxis=dict(rangemode='tozero'))
        return f

    if sottoarea in ["Tutte", "Volumi_Generali"]:
        elements.append(Paragraph("VOLUMI GENERALI DELLA SETTIMANA (DURATA & TRAINING LOAD)", sec_style))
        f_min = quick_bar('Minuti', '#10b981', f"Durata (Tot: {df_plot['Minuti'].sum():.0f} min)")
        f_tl = quick_bar('Training Load', '#0ea5e9', f"Training Load Globale (Tot: {df_plot['Training Load'].sum():.0f})")
        t_c1 = Table([[fig_to_rl_image(f_min, 385, 180), fig_to_rl_image(f_tl, 385, 180)]], colWidths=[396, 396])
        t_c1.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e2e8f0'))]))
        elements.append(t_c1)

    if sottoarea in ["Tutte", "Intensita_Meccanica"]:
        if sottoarea == "Tutte": elements.append(PageBreak())
        elements.append(Paragraph("INTENSITÀ & IMPATTO MECCANICO SETTIMANALE", sec_style))
        f_tlh = quick_bar('TL_High', '#ef4444', f"Training Load High (Tot: {df_plot['TL_High'].sum():.0f})")
        f_mech = go.Figure(data=[
            go.Bar(name='High Acc', x=x_lbl, y=df_plot['High Accel IMU'], marker_color='#10b981'),
            go.Bar(name='High Dec', x=x_lbl, y=df_plot['High Decel IMU'], marker_color='#ef4444')
        ])
        f_mech.update_layout(title="Accelerazioni & Decelerazioni IMU", barmode='group', paper_bgcolor='white', plot_bgcolor='white', font=dict(color='#0f172a', size=12), margin=dict(l=40, r=20, t=45, b=35))
        f_az = quick_bar('Azioni Int. IMU >2', '#8b5cf6', f"Azioni Intense >2\" (Tot: {df_plot['Azioni Int. IMU >2'].sum():.0f})")
        f_az10 = quick_bar('Azioni Int. IMU >10', '#f59e0b', f"Azioni Lunghissime >10\" (Tot: {df_plot['Azioni Int. IMU >10'].sum():.0f})")

        t_c2 = Table([
            [fig_to_rl_image(f_tlh, 385, 180), fig_to_rl_image(f_mech, 385, 180)],
            [fig_to_rl_image(f_az, 385, 180), fig_to_rl_image(f_az10, 385, 180)]
        ], colWidths=[396, 396])
        t_c2.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e2e8f0'))]))
        elements.append(t_c2)

    if sottoarea in ["Tutte", "Dati_GPS_Outdoor"]:
        if sottoarea == "Tutte": elements.append(Spacer(1, 12))
        elements.append(Paragraph("DATI GPS OUTDOOR SETTIMANALI", sec_style))
        f_dist = quick_bar('DISTANCE_out', '#0ea5e9', f"Distanza Totale (Tot: {df_plot['DISTANCE_out'].sum():.0f} m)")
        f_hml = quick_bar('HML_out', '#f59e0b', f"HML >25.5W (Tot: {df_plot['HML_out'].sum():.0f} m)")
        f_vhml = quick_bar('VHML_out', '#ef4444', f"VHML >50W (Tot: {df_plot['VHML_out'].sum():.0f} m)")
        t_c3 = Table([[fig_to_rl_image(f_dist, 255, 165), fig_to_rl_image(f_hml, 255, 165), fig_to_rl_image(f_vhml, 255, 165)]], colWidths=[264, 264, 264])
        t_c3.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e2e8f0'))]))
        elements.append(t_c3)

    if sottoarea in ["Tutte", "Indici_Settimanali"] and 'Vol_Index_W' in df_plot.columns:
        if sottoarea == "Tutte": elements.append(PageBreak())
        elements.append(Paragraph("INDICI COMPOSITI SETTIMANALI (VOLUME & WORK RATE — LIGHTEST DAY = 1)", sec_style))

        def quick_index_pdf(y_col, title_txt):
            vals = df_plot[y_col].tolist()
            txt_v = ["0" if v == 0 else ("1" if abs(v - 1.0) < 0.05 else f"{v:.1f}".replace('.', ',')) for v in vals]
            f = go.Figure()
            for idx_d, v in enumerate(vals):
                if v > 0:
                    f.add_shape(type="line", x0=x_lbl.iloc[idx_d], y0=0, x1=x_lbl.iloc[idx_d], y1=v, line=dict(color="#bae6fd", width=2))
            f.add_trace(go.Scatter(
                x=x_lbl, y=vals, mode='lines+markers+text',
                line=dict(shape='spline', width=5, color='#10b981'),
                marker=dict(size=10, color=vals, colorscale=[[0, '#10b981'], [0.5, '#f59e0b'], [1, '#ef4444']], showscale=False),
                text=txt_v, textposition='top center', textfont=dict(size=12, color='#0f172a', weight='bold')
            ))
            f.update_layout(
                title=f"{title_txt} (Day with score 1 is the lightest of the week)",
                paper_bgcolor='white', plot_bgcolor='white', font=dict(color='#0f172a', size=11),
                margin=dict(l=30, r=30, t=45, b=40),
                yaxis=dict(rangemode='tozero', range=[0, max(max(vals)*1.25, 2.0)], showgrid=True, gridcolor='#f1f5f9')
            )
            return f

        f_vi_pdf = quick_index_pdf('Vol_Index_W', "VOLUME INDEX")
        f_wi_pdf = quick_index_pdf('WR_Index_W', "WORK RATE (DENSITY) INDEX")

        t_idx_pdf = Table([[fig_to_rl_image(f_vi_pdf, 770, 175)], [fig_to_rl_image(f_wi_pdf, 770, 175)]], colWidths=[792])
        t_idx_pdf.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e2e8f0'))]))
        elements.append(KeepTogether([t_idx_pdf]))

    # Sezione Note Metodologiche & Bibliografia Validata
    elements.extend(genera_sezione_metodologia_pdf("acwr", styles))

    build_pdf_con_footer(doc, elements)
    return buffer.getvalue()


# =========================================================================
# 4. MOTORE PDF: STORICO MATCH (TUTTE LE SOTTOAREE)
# =========================================================================
def crea_pdf_storico_m0v3(giocatore, data_inizio_str, df_timeline, sottoarea="Tutte"):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), rightMargin=25, leftMargin=25, topMargin=25, bottomMargin=25)
    elements = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('M0V3Title', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=20, textColor=colors.HexColor('#0f172a'), spaceAfter=4)
    sub_style = ParagraphStyle('M0V3Sub', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=11, textColor=colors.HexColor('#0ea5e9'), spaceAfter=12)
    sec_style = ParagraphStyle('M0V3Sec', keepWithNext=1, parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=13, textColor=colors.HexColor('#0f172a'), spaceBefore=8, spaceAfter=8)

    sub_label = "REPORT COMPLETO" if sottoarea == "Tutte" else sottoarea.replace('_', ' ').upper()
    header_title = [
        Paragraph(f"M0V3 ANALYTICS — MATCH HISTORY ({sub_label})", title_style),
        Paragraph(f"ATLETA: {giocatore.upper()}   |   PERIODO: Dal {data_inizio_str} ad Oggi ({len(df_timeline)} Match)", sub_style)
    ]
    if os.path.exists(LOGO_PATH):
        logo_img = RLImage(LOGO_PATH, width=55, height=55)
        t_head = Table([[header_title, logo_img]], colWidths=[715, 75])
        t_head.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('ALIGN', (1, 0), (1, 0), 'RIGHT'), ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0)]))
        elements.append(t_head)
    else:
        elements.extend(header_title)

    x_labels = df_timeline['Date'].astype(str) + " - " + df_timeline['Session'].astype(str).str[:15]
    def quick_line(df_src, y_col, color, title):
        x_l = df_src['Date'].astype(str) + " - " + df_src['Session'].astype(str).str[:15]
        f = go.Figure(go.Scatter(x=x_l, y=df_src[y_col], mode='lines+markers', line=dict(shape='spline', width=3, color=color), marker=dict(size=7, color=color)))
        f.update_layout(title=title, paper_bgcolor='white', plot_bgcolor='white', font=dict(color='#0f172a', size=11), margin=dict(l=40, r=20, t=40, b=55), xaxis=dict(tickangle=30))
        return f

    need_break = False

    if sottoarea in ["Tutte", "Volumi_Intensita"]:
        elements.append(Paragraph("VOLUMI & INTENSITÀ MATCH TIMELINE", sec_style))
        c1 = fig_to_rl_image(quick_line(df_timeline, 'Minuti', '#10b981', 'Durata (min)'), 255, 175)
        c2 = fig_to_rl_image(quick_line(df_timeline, 'Training Load', '#0ea5e9', 'Training Load'), 255, 175)
        c3 = fig_to_rl_image(quick_line(df_timeline, 'Azioni Int. IMU >2', '#8b5cf6', 'Azioni Intense >2"'), 255, 175)
        c4 = fig_to_rl_image(quick_line(df_timeline, 'TL_High', '#ef4444', 'Training Load High'), 255, 175)
        c5 = fig_to_rl_image(quick_line(df_timeline, 'High Accel IMU', '#10b981', 'High Accelerations IMU'), 255, 175)
        c6 = fig_to_rl_image(quick_line(df_timeline, 'High Decel IMU', '#f59e0b', 'High Decelerations IMU'), 255, 175)
        t_vi = Table([[c1, c2, c3], [c4, c5, c6]], colWidths=[264, 264, 264])
        t_vi.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e2e8f0'))]))
        elements.append(t_vi)
        need_break = True

    if sottoarea in ["Tutte", "Work_Rate_Indici"]:
        if need_break: elements.append(PageBreak())
        elements.append(Paragraph("WORK RATE (DATI AL MINUTO) & INDICI COMPOSITI", sec_style))
        df_timeline['Mech_Tot'] = df_timeline['High Accel IMU'] + df_timeline['High Decel IMU']
        max_m = max(1, df_timeline['Minuti'].max()); max_tl = max(1, df_timeline['Training Load'].max())
        max_az = max(1, df_timeline['Azioni Int. IMU >2'].max()); max_mc = max(1, df_timeline['Mech_Tot'].max())
        max_tlm = max(1, df_timeline['TL/min'].max()); max_tlhm = max(1, df_timeline['TL_High/min'].max()); max_mcm = max(1, df_timeline['Mech/min'].max())
        df_timeline['Vol_Index'] = ((df_timeline['Minuti']/max_m)*100 + (df_timeline['Training Load']/max_tl)*100 + (df_timeline['Azioni Int. IMU >2']/max_az)*100 + (df_timeline['Mech_Tot']/max_mc)*100) / 4
        df_timeline['WR_Index'] = ((df_timeline['TL/min']/max_tlm)*100 + (df_timeline['TL_High/min']/max_tlhm)*100 + (df_timeline['Mech/min']/max_mcm)*100) / 3

        w1 = fig_to_rl_image(quick_line(df_timeline, 'TL/min', '#0ea5e9', 'Training Load / min'), 255, 175)
        w2 = fig_to_rl_image(quick_line(df_timeline, 'TL_High/min', '#ef4444', 'TL High / min'), 255, 175)
        w3 = fig_to_rl_image(quick_line(df_timeline, 'Mech/min', '#f59e0b', 'Azioni Mecc. (Acc+Dec) / min'), 255, 175)
        i1 = fig_to_rl_image(quick_line(df_timeline, 'Vol_Index', '#8b5cf6', 'Indice Composito Volume (Base 100)'), 385, 175)
        i2 = fig_to_rl_image(quick_line(df_timeline, 'WR_Index', '#f59e0b', 'Indice Composito Work Rate (Base 100)'), 385, 175)

        t_wr1 = Table([[w1, w2, w3]], colWidths=[264, 264, 264])
        t_wr1.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e2e8f0'))]))
        t_wr2 = Table([[i1, i2]], colWidths=[396, 396])
        t_wr2.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e2e8f0'))]))
        elements.append(t_wr1)
        elements.append(Spacer(1, 8))
        elements.append(t_wr2)
        need_break = True

    if sottoarea in ["Tutte", "Dati_GPS"]:
        df_gps = df_timeline[df_timeline['Ambiente'].astype(str).str.lower() != 'indoor'].copy()
        if not df_gps.empty:
            if need_break: elements.append(PageBreak())
            elements.append(Paragraph("DATI GPS MATCH TIMELINE (OUTDOOR)", sec_style))
            g1 = fig_to_rl_image(quick_line(df_gps, 'DISTANCE', '#0ea5e9', 'Distanza Totale (m)'), 255, 190)
            g2 = fig_to_rl_image(quick_line(df_gps, 'HML Distance >25.5W', '#f59e0b', 'HML Distance >25.5W (m)'), 255, 190)
            g3 = fig_to_rl_image(quick_line(df_gps, 'VHML Distance >50W', '#ef4444', 'VHML Distance >50W (m)'), 255, 190)
            t_g = Table([[g1, g2, g3]], colWidths=[264, 264, 264])
            t_g.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e2e8f0'))]))
            elements.append(t_g)
            need_break = True

    if sottoarea in ["Tutte", "Record_Storici"]:
        if need_break and sottoarea == "Record_Storici": pass
        elif need_break: elements.append(Spacer(1, 14))
        elements.append(Paragraph("BEST DATA HISTORY (RECORD STORICI NEL PERIODO)", sec_style))
        metriche_record = [
            ("Highest Duration (min)", "Minuti", False), ("Highest Training Load", "Training Load", False),
            ("Highest Training Load High", "TL_High", False), ("Highest Intense Actions >2\"", "Azioni Int. IMU >2", False),
            ("Highest Intense Actions >10\"", "Azioni Int. IMU >10", False), ("Highest Accelerations", "High Accel IMU", False),
            ("Highest Decelerations", "High Decel IMU", False), ("Highest Distance (m)", "DISTANCE", True),
            ("Highest Meters >25.5W", "HML Distance >25.5W", True), ("Highest Meters >50W", "VHML Distance >50W", True)
        ]
        rows_rec = [["PARAMETRO", "RECORD", "% VS MEDIA", "DATA", "SESSIONE"]]
        for etichetta, colonna, is_gps in metriche_record:
            if colonna not in df_timeline.columns: continue
            df_c = df_timeline[df_timeline['Ambiente'].astype(str).str.lower() != 'indoor'].copy() if is_gps else df_timeline.copy()
            df_c[colonna] = pd.to_numeric(df_c[colonna], errors='coerce').fillna(0)
            if df_c.empty or df_c[colonna].sum() == 0: continue
            media_val = df_c[colonna].mean()
            idx_max = df_c[colonna].idxmax()
            val_max = df_c.loc[idx_max, colonna]
            pct_media = (val_max / media_val * 100) if media_val > 0 else 0
            rows_rec.append([etichetta, f"{val_max:.0f}", f"{pct_media:.0f}%", str(df_c.loc[idx_max, 'Date']), str(df_c.loc[idx_max, 'Session'])])

        t_rec_style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0A192F')), ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#38bdf8')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'), ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
            ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ])
        elements.extend(genera_blocco_tabella_paginata(
            rows_rec[1:], [200, 100, 100, 110, 282], rows_rec[0], t_rec_style,
            max_righe_p1=14, max_righe_pn=18, sec_style=sec_style
        ))

    elements.extend(genera_sezione_metodologia_pdf("match_per_point", styles))
    build_pdf_con_footer(doc, elements)
    return buffer.getvalue()


# =========================================================================
# 5. MOTORE PDF: MEDIE E CONFRONTI
# =========================================================================
def crea_pdf_medie_m0v3(modalita, **kwargs):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), rightMargin=25, leftMargin=25, topMargin=25, bottomMargin=25)
    elements = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('M0V3Title', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=20, textColor=colors.HexColor('#0f172a'), spaceAfter=4)
    sub_style = ParagraphStyle('M0V3Sub', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=11, textColor=colors.HexColor('#0ea5e9'), spaceAfter=15)

    if modalita == "singolo":
        atleta = kwargs.get('atleta', '')
        df_grouped = kwargs.get('df_grouped', pd.DataFrame())
        header_title = [
            Paragraph("M0V3 ANALYTICS — PROFILO MEDIE ATLETA", title_style),
            Paragraph(f"ATLETA: {atleta.upper()}   |   MEDIE STORICHE PER TIPOLOGIA SESSIONE", sub_style)
        ]
        if os.path.exists(LOGO_PATH):
            logo_img = RLImage(LOGO_PATH, width=55, height=55)
            t_head = Table([[header_title, logo_img]], colWidths=[715, 75])
            t_head.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('ALIGN', (1, 0), (1, 0), 'RIGHT')]))
            elements.append(t_head)
        else: elements.extend(header_title)

        cols = ["TIPOLOGIA SESSIONE"] + list(df_grouped.columns)
        rows_data = []
        for idx, r in df_grouped.iterrows():
            rows_data.append([str(idx)] + [f"{val:.1f}" for val in r.values])

        t_m_style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0A192F')), ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#38bdf8')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 7), ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ])
        col_w = [132] + [82]*len(df_grouped.columns)
        elements.extend(genera_blocco_tabella_paginata(rows_data, col_w, cols, t_m_style, max_righe_p1=11, max_righe_pn=15))
    else:
        ath_a, ath_b, sess_sel = kwargs.get('ath_a', ''), kwargs.get('ath_b', ''), kwargs.get('sess_sel', '')
        mean_a, mean_b, col_analisi = kwargs.get('mean_a'), kwargs.get('mean_b'), kwargs.get('col_analisi', [])
        header_title = [
            Paragraph("M0V3 ANALYTICS — HEAD-TO-HEAD COMPARISON", title_style),
            Paragraph(f"{ath_a.upper()}  vs  {ath_b.upper()}   |   SESSIONE: {sess_sel.upper()}", sub_style)
        ]
        if os.path.exists(LOGO_PATH):
            logo_img = RLImage(LOGO_PATH, width=55, height=55)
            t_head = Table([[header_title, logo_img]], colWidths=[715, 75])
            t_head.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('ALIGN', (1, 0), (1, 0), 'RIGHT')]))
            elements.append(t_head)
        else: elements.extend(header_title)

        headers = ["PARAMETRO ANALIZZATO", ath_a.upper(), ath_b.upper(), "DELTA (A vs B)"]
        rows_data = []
        for c in col_analisi:
            va = 0 if pd.isna(mean_a[c]) else mean_a[c]
            vb = 0 if pd.isna(mean_b[c]) else mean_b[c]
            diff_str = f"{((va - vb) / vb * 100):+.0f}%" if vb > 0 else "N/A"
            rows_data.append([c, f"{va:.1f}", f"{vb:.1f}", diff_str])

        t_comp_style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0A192F')), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, -1), 9.5),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'), ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
            ('TOPPADDING', (0, 0), (-1, -1), 7), ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ])
        elements.extend(genera_blocco_tabella_paginata(rows_data, [260, 175, 175, 182], headers, t_comp_style, max_righe_p1=12, max_righe_pn=16))

    build_pdf_con_footer(doc, elements)
    return buffer.getvalue()


# =========================================================================
# 6. MOTORE PDF: TREND STAGIONALE (TIMELINE, ACWR, MONOTONIA, STRAIN)
# =========================================================================
def crea_pdf_stagionale_m0v3(giocatore, stagione, df_season, df_ath=None, sottoarea="Tutte"):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), rightMargin=25, leftMargin=25, topMargin=25, bottomMargin=25)
    elements = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('M0V3Title', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=17, textColor=colors.HexColor('#0f172a'), spaceAfter=3)
    sub_style = ParagraphStyle('M0V3Sub', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=9.5, textColor=colors.HexColor('#0ea5e9'), spaceAfter=8)
    sec_style = ParagraphStyle('M0V3Sec', keepWithNext=1, parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=11, textColor=colors.HexColor('#0f172a'), spaceBefore=6, spaceAfter=4)
    chart_kpi_style = ParagraphStyle('M0V3ChartKPI', keepWithNext=1, parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8, textColor=colors.HexColor('#475569'), spaceBefore=2, spaceAfter=2)

    sub_label = "REPORT STAGIONALE COMPLETO" if sottoarea == "Tutte" else sottoarea.replace('_', ' ').upper()
    header_title = [
        Paragraph("M0V3 ANALYTICS — SEASONAL EXECUTIVE REPORT", title_style),
        Paragraph(f"ATLETA: <b>{giocatore.upper()}</b>   |   STAGIONE: <b>{stagione}</b>   |   MODULO: <b>{sub_label}</b>", sub_style)
    ]
    if os.path.exists(LOGO_PATH):
        logo_img = RLImage(LOGO_PATH, width=50, height=50)
        t_head = Table([[header_title, logo_img]], colWidths=[720, 72])
        t_head.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0)
        ]))
        elements.append(t_head)
    else:
        elements.extend(header_title)

    df_s = df_season.copy() if df_season is not None else pd.DataFrame()
    if df_s.empty:
        elements.append(Paragraph("Nessun dato disponibile per questa stagione.", sec_style))
        build_pdf_con_footer(doc, elements)
        return buffer.getvalue()

    df_s['Date_obj'] = pd.to_datetime(df_s['Date'], format='%d/%m/%Y', errors='coerce')
    df_s['Week_Start'] = df_s['Date_obj'] - pd.to_timedelta(df_s['Date_obj'].dt.dayofweek, unit='d')
    df_s['Week_Start_Date'] = df_s['Week_Start'].dt.date

    # Aggregati di stagione
    tot_sess = len(df_s)
    tot_min = float(df_s['Minuti'].sum()) if 'Minuti' in df_s.columns else 0.0
    tot_tl = float(df_s['Training Load'].sum()) if 'Training Load' in df_s.columns else 0.0
    tot_tlh = float(df_s['TL_High'].sum()) if 'TL_High' in df_s.columns else 0.0
    n_sett_attive = df_s['Week_Start_Date'].nunique()
    avg_tl_week = tot_tl / max(n_sett_attive, 1)

    # Filtro soli Match (esclusivamente "Match" o "Match Doppio")
    is_match_season = df_s['Tipologia Sessione'].astype(str).str.strip().str.lower().isin(['match', 'match doppio'])
    tot_match_min = float(df_s[is_match_season]['Minuti'].sum()) if not df_s.empty else 0.0

    kpi_rows = [
        ["STAGIONE", "SESSIONI TOTALI", "ORE TOTALI", "ORE SOLI MATCH", "TRAINING LOAD TOTALE", "TL HIGH TOTALE", "MEDIA SETTIMANALE TL"],
        [str(stagione), str(tot_sess), f"{tot_min/60.0:.1f} h", f"{tot_match_min/60.0:.1f} h", f"{tot_tl:,.0f}", f"{tot_tlh:,.0f}", f"{avg_tl_week:,.0f} TL"]
    ]
    t_kpi = Table(kpi_rows, colWidths=[90, 105, 95, 120, 130, 115, 137])
    t_kpi.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f172a')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#38bdf8')),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 3.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3.5),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#f8fafc')),
        ('FONTNAME', (0, 1), (-1, 1), 'Helvetica-Bold'),
    ]))
    elements.append(t_kpi)
    elements.append(Spacer(1, 6))

    # Banner Legenda Superfici Tornei (stile identico al portale)
    t_surf_legend = Table([[
        Paragraph("<b>LEGENDA SUPERFICI TORNEI:</b>", ParagraphStyle('Lg0', fontName='Helvetica-Bold', fontSize=7.5, textColor=colors.HexColor('#0f172a'))),
        Paragraph("<font color='#ea580c'>&#9632;</font> <b>Terra Rossa (Clay)</b>", ParagraphStyle('Lg1', fontName='Helvetica', fontSize=7.5, textColor=colors.HexColor('#334155'))),
        Paragraph("<font color='#059669'>&#9632;</font> <b>Erba (Grass)</b>", ParagraphStyle('Lg2', fontName='Helvetica', fontSize=7.5, textColor=colors.HexColor('#334155'))),
        Paragraph("<font color='#0284c7'>&#9632;</font> <b>Cemento (Hard)</b>", ParagraphStyle('Lg3', fontName='Helvetica', fontSize=7.5, textColor=colors.HexColor('#334155'))),
        Paragraph("Tipologie: <b>[S]</b> Singolare  |  <b>[D]</b> Doppio  |  <b>[S+D]</b> Entrambi", ParagraphStyle('Lg4', fontName='Helvetica-Oblique', fontSize=7.5, textColor=colors.HexColor('#64748b')))
    ]], colWidths=[150, 130, 120, 130, 262])
    t_surf_legend.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(t_surf_legend)
    elements.append(Spacer(1, 8))

    min_w_start = df_s['Week_Start_Date'].min()
    max_w_start = df_s['Week_Start_Date'].max()
    curr_mon = min_w_start
    all_mondays = []
    while curr_mon <= max_w_start:
        all_mondays.append(curr_mon)
        curr_mon += timedelta(days=7)

    # Costruzione asse X con tornei e orientamento verticale (-90°)
    is_cobolli = "cobolli" in str(giocatore).lower()
    x_axis_labels = []
    tournaments_highlights = []

    for idx, w_st in enumerate(all_mondays):
        t = get_tournament_for_week(w_st) if is_cobolli else None
        lbl = w_st.strftime('%d/%m')
        if t:
            t_name = str(t.get('tournament', '')).strip()
            t_surf = str(t.get('surfaces', 'Hard')).strip()
            t_type = str(t.get('types', 'Singolare')).strip()
            short_type = 'D' if t_type.lower() == 'doppio' else ('S+D' if '+' in t_type else 'S')
            rich_lbl = f"{lbl} · {t_name} [{short_type}]"
            x_axis_labels.append(rich_lbl)

            if t_surf == 'Clay':
                bg_col, border_col = 'rgba(249, 115, 22, 0.16)', '#ea580c'
            elif t_surf == 'Grass':
                bg_col, border_col = 'rgba(16, 185, 129, 0.16)', '#059669'
            else:
                bg_col, border_col = 'rgba(14, 165, 233, 0.14)', '#0284c7'

            tournaments_highlights.append({
                'idx': idx,
                'label': rich_lbl,
                'bg_col': bg_col,
                'border_col': border_col,
                'name': t_name,
                'surf': t_surf,
                'type': t_type
            })
        else:
            x_axis_labels.append(lbl)

    def apply_pdf_chart_styling(fig, max_y, title_text, y_title="", height=195):
        for h in tournaments_highlights:
            fig.add_shape(
                type="rect",
                xref="x",
                yref="paper",
                x0=h["idx"] - 0.45,
                x1=h["idx"] + 0.45,
                y0=0,
                y1=1,
                fillcolor=h["bg_col"],
                line=dict(color=h["border_col"], width=1.2, dash="dot"),
                layer="below"
            )
        fig.update_layout(
            title=dict(text=title_text, font=dict(family='Helvetica, Arial', size=10.5, color='#0f172a')),
            paper_bgcolor='white',
            plot_bgcolor='rgba(248, 250, 252, 0.6)',
            font=dict(family='Helvetica, Arial', color='#0f172a', size=8.5),
            margin=dict(l=35, r=25, t=30, b=95),
            xaxis=dict(
                tickangle=-90,
                tickfont=dict(size=7.5, color='#334155', family='Helvetica, Arial'),
                linecolor='#cbd5e1',
                showgrid=False
            ),
            yaxis=dict(
                title=dict(text=y_title, font=dict(size=8, color='#64748b')) if y_title else None,
                showgrid=True,
                gridcolor='#f1f5f9',
                zerolinecolor='#cbd5e1',
                range=[0, max_y],
                tickfont=dict(size=8, color='#64748b')
            ),
            showlegend=False
        )

    # -------------------------------------------------------------------------
    # 1. TIMELINE SETTIMANALE STAGIONE
    # -------------------------------------------------------------------------
    if sottoarea in ["Tutte", "Timeline_Settimanale"]:
        elements.append(Paragraph("1. TIMELINE SETTIMANALE STAGIONE (VOLUME & INTENSITÀ)", sec_style))

        # Calcolo dati settimanali
        weekly_data = []
        for w_st in all_mondays:
            w_en = w_st + timedelta(days=6)
            df_w = df_s[df_s['Week_Start_Date'] == w_st]
            w_num = pd.to_datetime(w_st).isocalendar()[1]
            w_lbl = f"{w_st.strftime('%d/%m')}-{w_en.strftime('%d/%m')}"

            if not df_w.empty:
                w_sess = len(df_w)
                # Filtro soli Match (esclusivamente "Match" o "Match Doppio")
                is_m_w = df_w['Tipologia Sessione'].astype(str).str.strip().str.lower().isin(['match', 'match doppio'])
                m_time = float(df_w[is_m_w]['Minuti'].sum()) if not df_w.empty else 0.0
                tot_time = float(df_w['Minuti'].sum())
                tl_tot = float(df_w['Training Load'].sum())
                tl_h = float(df_w['TL_High'].sum())
                pct_h = (tl_h / tl_tot * 100) if tl_tot > 0 else 0.0
            else:
                w_sess, m_time, tot_time, tl_tot, tl_h, pct_h = 0, 0.0, 0.0, 0.0, 0.0, 0.0

            weekly_data.append({
                "w_num": w_num,
                "w_lbl": w_lbl,
                "sess": w_sess,
                "m_time": m_time,
                "tot_time": tot_time,
                "tl": tl_tot,
                "tl_h": tl_h,
                "pct_h": pct_h
            })

        active_w = [w for w in weekly_data if w['sess'] > 0]
        n_act = len(active_w) if active_w else 1
        avg_mtime = sum(w['m_time'] for w in active_w) / n_act
        peak_mtime = max([w['m_time'] for w in weekly_data] or [0.0])
        avg_ttime = sum(w['tot_time'] for w in active_w) / n_act
        peak_ttime = max([w['tot_time'] for w in weekly_data] or [0.0])
        avg_tl_w = sum(w['tl'] for w in active_w) / n_act
        peak_tl_w = max([w['tl'] for w in weekly_data] or [0.0])

        # --- GRAFICO 1: TEMPO DEI SOLI MATCH ---
        y_mtime = [w['m_time'] for w in weekly_data]
        fig_mtime = go.Figure()
        fig_mtime.add_trace(go.Scatter(
            x=x_axis_labels, y=y_mtime, mode='lines+markers',
            line=dict(color='#f97316', width=2.5, shape='spline', smoothing=0.65),
            marker=dict(size=5, color='#f97316', line=dict(color='#ffffff', width=1.5)),
            fill='tozeroy', fillcolor='rgba(249, 115, 22, 0.12)'
        ))
        if avg_mtime > 0:
            fig_mtime.add_hline(y=avg_mtime, line_dash="dash", line_color="#64748b", line_width=1.2,
                                annotation_text=f"Media: {int(avg_mtime//60)}h {int(avg_mtime%60):02d}m",
                                annotation_position="top right", annotation_font_size=8, annotation_font_color="#64748b")
        max_y_m = max(max(y_mtime or [60.0]), avg_mtime) * 1.25
        apply_pdf_chart_styling(
            fig_mtime, max_y_m,
            f"TEMPO DEI SOLI MATCH (MINUTI)  —  Media: {int(avg_mtime//60)}h {int(avg_mtime%60):02d}m  |  Picco: {int(peak_mtime//60)}h {int(peak_mtime%60):02d}m",
            y_title="Minuti Match"
        )
        elements.append(fig_to_rl_image(fig_mtime, 792, 195))
        elements.append(Spacer(1, 8))

        # --- GRAFICO 2: TEMPO TOTALE DI TUTTE LE SESSIONI ---
        y_ttime = [w['tot_time'] for w in weekly_data]
        fig_ttime = go.Figure()
        fig_ttime.add_trace(go.Scatter(
            x=x_axis_labels, y=y_ttime, mode='lines+markers',
            line=dict(color='#0ea5e9', width=2.5, shape='spline', smoothing=0.65),
            marker=dict(size=5, color='#0ea5e9', line=dict(color='#ffffff', width=1.5)),
            fill='tozeroy', fillcolor='rgba(14, 165, 233, 0.12)'
        ))
        if avg_ttime > 0:
            fig_ttime.add_hline(y=avg_ttime, line_dash="dash", line_color="#64748b", line_width=1.2,
                                annotation_text=f"Media: {int(avg_ttime//60)}h {int(avg_ttime%60):02d}m",
                                annotation_position="top right", annotation_font_size=8, annotation_font_color="#64748b")
        max_y_t = max(max(y_ttime or [60.0]), avg_ttime) * 1.25
        apply_pdf_chart_styling(
            fig_ttime, max_y_t,
            f"TEMPO TOTALE DI TUTTE LE SESSIONI (MATCH + ALLENAMENTI)  —  Media: {int(avg_ttime//60)}h {int(avg_ttime%60):02d}m  |  Picco: {int(peak_ttime//60)}h {int(peak_ttime%60):02d}m",
            y_title="Minuti Totali"
        )
        elements.append(fig_to_rl_image(fig_ttime, 792, 195))
        elements.append(Spacer(1, 8))

        # --- GRAFICO 3: TRAINING LOAD ---
        y_tl = [w['tl'] for w in weekly_data]
        fig_tl = go.Figure()
        fig_tl.add_trace(go.Scatter(
            x=x_axis_labels, y=y_tl, mode='lines+markers',
            line=dict(color='#6366f1', width=2.5, shape='spline', smoothing=0.65),
            marker=dict(size=5, color='#6366f1', line=dict(color='#ffffff', width=1.5)),
            fill='tozeroy', fillcolor='rgba(99, 102, 241, 0.12)'
        ))
        if avg_tl_w > 0:
            fig_tl.add_hline(y=avg_tl_w, line_dash="dash", line_color="#64748b", line_width=1.2,
                             annotation_text=f"Media: {avg_tl_w:,.0f} TL",
                             annotation_position="top right", annotation_font_size=8, annotation_font_color="#64748b")
        max_y_tl = max(max(y_tl or [100.0]), avg_tl_w) * 1.25
        apply_pdf_chart_styling(
            fig_tl, max_y_tl,
            f"TRAINING LOAD SETTIMANALE  —  Media: {avg_tl_w:,.0f} TL  |  Picco: {peak_tl_w:,.0f} TL",
            y_title="Training Load"
        )
        elements.append(fig_to_rl_image(fig_tl, 792, 195))

    # -------------------------------------------------------------------------
    # 2. ACWR STAGIONALE
    # -------------------------------------------------------------------------
    if sottoarea in ["Tutte", "ACWR_Stagionale"]:
        if sottoarea == "Tutte":
            elements.append(PageBreak())
        elements.append(Paragraph("2. ACWR STAGIONALE (ACUTE:CHRONIC WORKLOAD RATIO)", sec_style))

        df_full = df_ath if df_ath is not None and not df_ath.empty else df_s
        y_acwr_7d = []
        y_acute_2d = []

        for w_st in all_mondays:
            w_en = w_st + timedelta(days=6)
            w_end_str = w_en.strftime("%d/%m/%Y")
            acwr_7 = acwr_pre_match(df_full, giocatore, w_end_str, giorni=7, col='Training Load', include_target=True, burn_in_mask=True)
            acwr_2 = acwr_pre_match(df_full, giocatore, w_end_str, giorni=2, col='Training Load', include_target=True, burn_in_mask=True)
            y_acwr_7d.append(acwr_7)
            y_acute_2d.append(acwr_2)

        valid_7 = [v for v in y_acwr_7d if v is not None and not pd.isna(v)]
        last_acwr_val = valid_7[-1] if valid_7 else 0.0
        n_sweet = sum(1 for v in valid_7 if 80 <= v <= 125)
        pct_sweet = (n_sweet / len(valid_7) * 100) if valid_7 else 0.0
        n_overload = sum(1 for v in valid_7 if v > 150)

        # Tabella KPI ACWR
        t_acwr_kpi = Table([
            ["ULTIMO ACWR 7G", "TEMPO IN SWEET SPOT (80-125%)", "SETTIMANE SOVRACCARICO (>150%)", "STATO ATTUALE"],
            [f"{last_acwr_val:.1f}%", f"{pct_sweet:.0f}% ({n_sweet}/{len(valid_7)})", str(n_overload),
             "OTTIMALE" if 80 <= last_acwr_val <= 125 else ("ATTENZIONE" if last_acwr_val <= 150 else "ALLARME OVERLOAD")]
        ], colWidths=[180, 220, 200, 192])
        t_acwr_kpi.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f172a')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#38bdf8')),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
            ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#f8fafc')),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        elements.append(t_acwr_kpi)
        elements.append(Spacer(1, 8))

        # Grafico Executive ACWR con 4 zone fisiologiche
        all_acwr_vals = [v for v in (y_acwr_7d + y_acute_2d) if v is not None and not pd.isna(v)]
        max_ac_y = max(max(all_acwr_vals or [150.0]) * 1.15, 180.0)

        fig_acwr = go.Figure()
        # 4 fasce fisiologiche orizzontali
        fig_acwr.add_hrect(y0=0, y1=80, fillcolor="rgba(14, 165, 233, 0.08)", line_width=0,
                           annotation_text="Scarico (<80%)", annotation_position="bottom right", annotation_font_size=7.5, annotation_font_color="#0284c7")
        fig_acwr.add_hrect(y0=80, y1=125, fillcolor="rgba(16, 185, 129, 0.12)", line_width=0,
                           annotation_text="Sweet Spot (80-125%)", annotation_position="bottom right", annotation_font_size=7.5, annotation_font_color="#059669")
        fig_acwr.add_hrect(y0=125, y1=150, fillcolor="rgba(245, 158, 11, 0.10)", line_width=0,
                           annotation_text="Attenzione (125-150%)", annotation_position="bottom right", annotation_font_size=7.5, annotation_font_color="#d97706")
        fig_acwr.add_hrect(y0=150, y1=max_ac_y, fillcolor="rgba(239, 68, 68, 0.12)", line_width=0,
                           annotation_text="Danger Zone (>150%)", annotation_position="bottom right", annotation_font_size=7.5, annotation_font_color="#dc2626")
        fig_acwr.add_hline(y=100, line_dash="dash", line_color="#64748b", line_width=1.2,
                           annotation_text="Baseline 100%", annotation_position="bottom left", annotation_font_size=7.5, annotation_font_color="#475569")

        # Colori marker 7D in base alla zona
        colors_7d = []
        for v in y_acwr_7d:
            if v is None or pd.isna(v): colors_7d.append("#94a3b8")
            elif v < 80: colors_7d.append("#0ea5e9")
            elif v <= 125: colors_7d.append("#10b981")
            elif v <= 150: colors_7d.append("#f59e0b")
            else: colors_7d.append("#ef4444")

        fig_acwr.add_trace(go.Scatter(
            x=x_axis_labels, y=y_acwr_7d, mode='lines+markers', name='ACWR 7 Giorni',
            line=dict(color='#0284c7', width=2.8, shape='spline', smoothing=0.65),
            marker=dict(size=6, color=colors_7d, line=dict(color='#ffffff', width=1.5)),
            connectgaps=True
        ))
        fig_acwr.add_trace(go.Scatter(
            x=x_axis_labels, y=y_acute_2d, mode='lines+markers', name='Acute Readiness 2 Giorni',
            line=dict(color='#f97316', width=2.0, shape='spline', smoothing=0.6),
            marker=dict(symbol='diamond', size=5, color='#f97316', line=dict(color='#ffffff', width=1)),
            connectgaps=True
        ))
        apply_pdf_chart_styling(
            fig_acwr, max_ac_y,
            "ACWR STAGIONALE (RAPPORTO ACUTO 2G : CRONICO 7G) CON FASCE DI RISCHIO FISIOLOGICO",
            y_title="ACWR %", height=220
        )
        elements.append(fig_to_rl_image(fig_acwr, 792, 220))

    # -------------------------------------------------------------------------
    # 3. MONOTONIA STAGIONALE
    # -------------------------------------------------------------------------
    if sottoarea in ["Tutte", "Monotonia_Stagionale"]:
        if sottoarea == "Tutte":
            elements.append(PageBreak())
        elements.append(Paragraph("3. MONOTONIA STAGIONALE (INDICE DI FOSTER: μ / σ)", sec_style))

        y_mono_tlh = []
        y_mono_tl = []

        for w_st in all_mondays:
            df_w = df_s[df_s['Week_Start_Date'] == w_st]
            # Giorni per TL High
            tlh_days = [float(df_w[df_w['Date_obj'].dt.date == (w_st + timedelta(days=d))]['TL_High'].sum()) if not df_w.empty and 'TL_High' in df_w.columns else 0.0 for d in range(7)]
            tl_days = [float(df_w[df_w['Date_obj'].dt.date == (w_st + timedelta(days=d))]['Training Load'].sum()) if not df_w.empty and 'Training Load' in df_w.columns else 0.0 for d in range(7)]

            tot_tlh = sum(tlh_days)
            std_tlh = float(np.std(tlh_days, ddof=1)) if len(tlh_days) > 1 else 0.0
            mean_tlh = tot_tlh / 7.0
            m_tlh = round(mean_tlh / std_tlh, 2) if std_tlh > 0 else (3.5 if tot_tlh > 0 else 0.0)

            tot_tl = sum(tl_days)
            std_tl = float(np.std(tl_days, ddof=1)) if len(tl_days) > 1 else 0.0
            mean_tl = tot_tl / 7.0
            m_tl = round(mean_tl / std_tl, 2) if std_tl > 0 else (3.5 if tot_tl > 0 else 0.0)

            y_mono_tlh.append(m_tlh)
            y_mono_tl.append(m_tl)

        valid_m = [v for v in y_mono_tlh if v > 0]
        last_m = valid_m[-1] if valid_m else 0.0
        avg_m = sum(valid_m) / len(valid_m) if valid_m else 0.0
        n_alarm_m = sum(1 for v in valid_m if v >= 2.0)

        # Tabella KPI Monotonia
        t_mono_kpi = Table([
            ["ULTIMA MONOTONIA (TL HIGH)", "MEDIA STAGIONALE", "SOGLIA ALLARME FOSTER", "SETTIMANE A RISCHIO (≥ 2.0)"],
            [f"{last_m:.2f}", f"{avg_m:.2f}", "2.00", f"{n_alarm_m} su {len(valid_m)} settimane"]
        ], colWidths=[190, 190, 200, 212])
        t_mono_kpi.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f172a')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#38bdf8')),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
            ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#f8fafc')),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        elements.append(t_mono_kpi)
        elements.append(Spacer(1, 8))

        # Grafico Executive Monotonia
        max_y_mo = max(max((y_mono_tlh + y_mono_tl) or [2.5]), 3.5)
        fig_mono = go.Figure()
        # Fascia ottimale verde (<2.0)
        fig_mono.add_shape(
            type="rect", x0=-0.5, x1=len(x_axis_labels) - 0.5, y0=0, y1=2.0,
            fillcolor="rgba(16, 185, 129, 0.08)", line=dict(width=0), layer="below"
        )
        # Linea allarme tratteggiata rossa 2.0
        fig_mono.add_shape(
            type="line", x0=-0.5, x1=len(x_axis_labels) - 0.5, y0=2.0, y1=2.0,
            line=dict(color="#ef4444", width=2, dash="dash"), layer="above"
        )
        fig_mono.add_annotation(
            x=0.01, y=2.0, xref="paper", yref="y", text="SOGLIA ALLARME FOSTER (2.0)",
            showarrow=False, font=dict(color="#b91c1c", size=8), bgcolor="rgba(254, 226, 226, 0.9)"
        )
        colors_mo = ["#ef4444" if v >= 2.0 else "#10b981" for v in y_mono_tlh]
        fig_mono.add_trace(go.Scatter(
            x=x_axis_labels, y=y_mono_tlh, mode='lines+markers', name='Monotonia TL High (Intensità)',
            line=dict(color='#ef4444', width=2.8, shape='spline', smoothing=0.3),
            marker=dict(size=6, color=colors_mo, line=dict(color='#ffffff', width=1.5))
        ))
        fig_mono.add_trace(go.Scatter(
            x=x_axis_labels, y=y_mono_tl, mode='lines+markers', name='Monotonia TL Volume',
            line=dict(color='#0284c7', width=2.0, shape='spline', smoothing=0.3, dash='dot'),
            marker=dict(size=5, color='#0284c7', line=dict(color='#ffffff', width=1))
        ))
        apply_pdf_chart_styling(
            fig_mono, max_y_mo,
            "MONOTONIA STAGIONALE (INDICE DI FOSTER — METRICA PRIMARIA TL HIGH)",
            y_title="Indice Monotonia (μ / σ)", height=220
        )
        elements.append(fig_to_rl_image(fig_mono, 792, 220))

    # -------------------------------------------------------------------------
    # 4. STRAIN STAGIONALE
    # -------------------------------------------------------------------------
    if sottoarea in ["Tutte", "Strain_Stagionale"]:
        if sottoarea == "Tutte":
            elements.append(PageBreak())
        elements.append(Paragraph("4. STRAIN STAGIONALE (STRESS PSICOFISICO: CARICO × MONOTONIA)", sec_style))

        y_strain_tlh = []
        y_strain_tl = []

        for w_st in all_mondays:
            df_w = df_s[df_s['Week_Start_Date'] == w_st]
            tlh_days = [float(df_w[df_w['Date_obj'].dt.date == (w_st + timedelta(days=d))]['TL_High'].sum()) if not df_w.empty and 'TL_High' in df_w.columns else 0.0 for d in range(7)]
            tl_days = [float(df_w[df_w['Date_obj'].dt.date == (w_st + timedelta(days=d))]['Training Load'].sum()) if not df_w.empty and 'Training Load' in df_w.columns else 0.0 for d in range(7)]

            tot_tlh = sum(tlh_days)
            std_tlh = float(np.std(tlh_days, ddof=1)) if len(tlh_days) > 1 else 0.0
            mean_tlh = tot_tlh / 7.0
            m_tlh = round(mean_tlh / std_tlh, 2) if std_tlh > 0 else (3.5 if tot_tlh > 0 else 0.0)
            sn_tlh = round(tot_tlh * m_tlh, 1)

            tot_tl = sum(tl_days)
            std_tl = float(np.std(tl_days, ddof=1)) if len(tl_days) > 1 else 0.0
            mean_tl = tot_tl / 7.0
            m_tl = round(mean_tl / std_tl, 2) if std_tl > 0 else (3.5 if tot_tl > 0 else 0.0)
            sn_tl = round(tot_tl * m_tl, 1)

            y_strain_tlh.append(sn_tlh)
            y_strain_tl.append(sn_tl)

        valid_sn = [v for v in y_strain_tlh if v > 0]
        last_sn = valid_sn[-1] if valid_sn else 0.0
        avg_sn = sum(valid_sn) / len(valid_sn) if valid_sn else 1500.0
        thresh_alarm_sn = avg_sn * 1.5
        peak_sn = max(valid_sn) if valid_sn else 0.0
        n_crit_sn = sum(1 for v in valid_sn if v > thresh_alarm_sn)

        # Tabella KPI Strain
        t_strain_kpi = Table([
            ["ULTIMO STRAIN TL HIGH", "BASELINE MEDIA STAGIONALE", "SOGLIA ALLARME PICCO (+50%)", "PICCO MASSIMO STAGIONALE", "SETTIMANE ALLERTA"],
            [f"{last_sn:,.0f} AU", f"{avg_sn:,.0f} AU", f"{thresh_alarm_sn:,.0f} AU", f"{peak_sn:,.0f} AU", f"{n_crit_sn} settimane"]
        ], colWidths=[150, 160, 170, 160, 152])
        t_strain_kpi.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f172a')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#38bdf8')),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
            ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#f8fafc')),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        elements.append(t_strain_kpi)
        elements.append(Spacer(1, 8))

        # Grafico Executive Strain
        max_y_sn = max(max(y_strain_tlh or [1000.0]), thresh_alarm_sn) * 1.25
        fig_sn = go.Figure()
        fig_sn.add_shape(
            type="rect", x0=-0.5, x1=len(x_axis_labels) - 0.5, y0=0, y1=thresh_alarm_sn,
            fillcolor="rgba(16, 185, 129, 0.07)", line=dict(width=0), layer="below"
        )
        fig_sn.add_shape(
            type="line", x0=-0.5, x1=len(x_axis_labels) - 0.5, y0=avg_sn, y1=avg_sn,
            line=dict(color="#0ea5e9", width=1.5, dash="dot"), layer="above"
        )
        fig_sn.add_shape(
            type="line", x0=-0.5, x1=len(x_axis_labels) - 0.5, y0=thresh_alarm_sn, y1=thresh_alarm_sn,
            line=dict(color="#ef4444", width=2, dash="dash"), layer="above"
        )
        fig_sn.add_annotation(
            x=0.01, y=thresh_alarm_sn, xref="paper", yref="y", text=f"SOGLIA ALLARME PICCO (+50%): {thresh_alarm_sn:,.0f} AU",
            showarrow=False, font=dict(color="#b91c1c", size=8), bgcolor="rgba(254, 226, 226, 0.9)"
        )
        colors_sn = ["#ef4444" if v > thresh_alarm_sn else "#10b981" for v in y_strain_tlh]
        fig_sn.add_trace(go.Scatter(
            x=x_axis_labels, y=y_strain_tlh, mode='lines+markers', name='Strain TL High (Intensità)',
            line=dict(color='#f59e0b', width=2.8, shape='spline', smoothing=0.3),
            marker=dict(size=6, color=colors_sn, line=dict(color='#ffffff', width=1.5))
        ))
        apply_pdf_chart_styling(
            fig_sn, max_y_sn,
            "TRAINING STRAIN STAGIONALE (CARICO TL HIGH × MONOTONIA) CON SOGLIE DI PICCO CRITICO",
            y_title="Strain [AU]", height=220
        )
        elements.append(fig_to_rl_image(fig_sn, 792, 220))

    if sottoarea in ["Tutte", "ACWR_Stagionale"]:
        elements.extend(genera_sezione_metodologia_pdf("acwr", styles))
    if sottoarea in ["Tutte", "Monotonia_Stagionale", "Strain_Stagionale"]:
        elements.extend(genera_sezione_metodologia_pdf("monotonia_strain", styles))

    build_pdf_con_footer(doc, elements)
    return buffer.getvalue()




def crea_pdf_referto_settimanale(giocatore, settimana_label, testo_volume, testo_intensita, testo_monotonia, kpis=None):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), rightMargin=25, leftMargin=25, topMargin=25, bottomMargin=25)
    elements = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('M0V3Title', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=18, textColor=colors.HexColor('#0f172a'), spaceAfter=4)
    sub_style = ParagraphStyle('M0V3Sub', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=10.5, textColor=colors.HexColor('#0ea5e9'), spaceAfter=12)
    sec_style = ParagraphStyle('M0V3Sec', parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=11, textColor=colors.HexColor('#0f172a'), spaceBefore=8, spaceAfter=4)
    body_style = ParagraphStyle('M0V3Body', parent=styles['Normal'], fontName='Helvetica', fontSize=9, textColor=colors.HexColor('#1e293b'), leading=13)

    header_title = [
        Paragraph("M0V3 ANALYTICS — REFERTO MEDICO-SPORTIVO & CARICHI", title_style),
        Paragraph(f"ATLETA: {giocatore.upper()}   |   SETTIMANA: {settimana_label}", sub_style)
    ]
    if os.path.exists(LOGO_PATH):
        logo_img = RLImage(LOGO_PATH, width=50, height=50)
        t_head = Table([[header_title, logo_img]], colWidths=[720, 70])
        t_head.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('ALIGN', (1, 0), (1, 0), 'RIGHT')]))
        elements.append(t_head)
    else: elements.extend(header_title)

    # Box Referto Narrativo
    card_rows = [
        [Paragraph("<b>VOLUME (TL) & ACWR</b>", ParagraphStyle('H_vol', fontName='Helvetica-Bold', fontSize=9.5, textColor=colors.HexColor('#0369a1')))],
        [Paragraph(testo_volume.replace('<br>', '<br/>'), body_style)],
        [Paragraph("<b>INTENSITÀ (TL HIGH) & GESTIONE NEUROMUSCOLARE</b>", ParagraphStyle('H_int', fontName='Helvetica-Bold', fontSize=9.5, textColor=colors.HexColor('#b91c1c')))],
        [Paragraph(testo_intensita.replace('<br>', '<br/>'), body_style)],
        [Paragraph("<b>VARIABILITÀ, MONOTONIA & TRAINING STRAIN (FOSTER)</b>", ParagraphStyle('H_mon', fontName='Helvetica-Bold', fontSize=9.5, textColor=colors.HexColor('#b45309')))],
        [Paragraph(testo_monotonia.replace('<br>', '<br/>'), body_style)],
    ]
    t_card = Table(card_rows, colWidths=[790])
    t_card.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
        ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 10), ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#cbd5e1')),
        ('LINEBELOW', (0, 1), (-1, 1), 0.5, colors.HexColor('#e2e8f0')),
        ('LINEBELOW', (0, 3), (-1, 3), 0.5, colors.HexColor('#e2e8f0')),
    ]))
    elements.append(t_card)

    if kpis:
        elements.append(Spacer(1, 8))
        elements.append(Paragraph("PARAMETRI FISICI & INDICI METRICI DEL MICROCICLO", sec_style))
        kpi_rows = [
            ["DURATA (MIN)", "TRAINING LOAD", "TL HIGH", "HIGH ACCEL", "HIGH DECEL", "ACWR SETT.", "MONOTONIA", "TRAINING STRAIN"],
            [
                f"{kpis.get('minuti', 0):.0f}",
                f"{kpis.get('tl', 0):.0f}",
                f"{kpis.get('tlh', 0):.0f}",
                f"{kpis.get('acc', 0):.0f}",
                f"{kpis.get('dec', 0):.0f}",
                f"{kpis.get('acwr', 0):.2f}",
                f"{kpis.get('mono', 0):.2f}",
                f"{int(round(kpis.get('strain', 0))):,}".replace(",", ".")
            ]
        ]
        t_kpi = Table(kpi_rows, colWidths=[98]*8)
        t_kpi.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f172a')), ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#38bdf8')),
            ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#f0fdf4')), ('TEXTCOLOR', (0, 1), (-1, 1), colors.HexColor('#0f172a')),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ]))
        elements.append(t_kpi)

    build_pdf_con_footer(doc, elements)
    return buffer.getvalue()


def crea_pdf_manuale_report(moduli, area_filtro="Tutte le Aree"):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), rightMargin=25, leftMargin=25, topMargin=25, bottomMargin=25)
    elements = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('ManTitle', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=18, textColor=colors.HexColor('#0f172a'), spaceAfter=3)
    sub_style = ParagraphStyle('ManSub', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=10, textColor=colors.HexColor('#0ea5e9'), spaceAfter=10)
    
    sec_h_style = ParagraphStyle('ManModH', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=9, textColor=colors.HexColor('#38bdf8'))
    lbl_style = ParagraphStyle('ManLbl', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8, textColor=colors.HexColor('#0f172a'))
    body_style = ParagraphStyle('ManBody', parent=styles['Normal'], fontName='Helvetica', fontSize=7.5, textColor=colors.HexColor('#1e293b'), leading=10.5)
    bib_style = ParagraphStyle('ManBib', parent=styles['Normal'], fontName='Helvetica-Oblique', fontSize=7, textColor=colors.HexColor('#92400e'), leading=9.5)

    header_title = [
        Paragraph("M0V3 ANALYTICS — MANUALE DEI REPORT & MODULI ANALITICI", title_style),
        Paragraph(f"AREA: {area_filtro.upper()}   |   DOCUMENTAZIONE METODOLOGICA & SCIENTIFICA ({len(moduli)} MODULI)", sub_style)
    ]
    if os.path.exists(LOGO_PATH):
        logo_img = RLImage(LOGO_PATH, width=45, height=45)
        t_head = Table([[header_title, logo_img]], colWidths=[725, 65])
        t_head.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('ALIGN', (1, 0), (1, 0), 'RIGHT')]))
        elements.append(t_head)
    else:
        elements.extend(header_title)

    for idx, mod in enumerate(moduli, start=1):
        nome_display = mod.get('nome_it', mod['nome'])
        nome_tecnico = mod['nome']
        area = mod['area']
        
        # Righe del modulo
        cosa_txt = mod.get('cosa_analizza', '')
        serve_txt = mod.get('a_cosa_serve', '')
        azioni_txt = " • ".join(mod.get('azioni_consentite', []))
        biblio_list = mod.get('bibliografia', [])
        biblio_txt = "<br/>".join([f"• <i>{b}</i>" for b in biblio_list]) if biblio_list else "M0V3 Algorithmic Core — Validazione computazionale su standard ISO/IMU."

        mod_rows = [
            [
                Paragraph(f"<b>#{idx} — {nome_display.upper()}</b> <font color='#94a3b8' size='7.5'>[Area: {area.upper()} | Catalogo: {nome_tecnico}]</font>", sec_h_style),
                ""
            ],
            [
                Paragraph("<b>COSA ANALIZZA:</b>", lbl_style),
                Paragraph(cosa_txt, body_style)
            ],
            [
                Paragraph("<b>A COSA SERVE:</b>", lbl_style),
                Paragraph(serve_txt, body_style)
            ],
            [
                Paragraph("<b>AZIONI CONSENTITE:</b>", lbl_style),
                Paragraph(azioni_txt, body_style)
            ],
            [
                Paragraph("<b>FONTI SCIENTIFICHE:</b>", lbl_style),
                Paragraph(biblio_txt, bib_style)
            ]
        ]

        t_mod = Table(mod_rows, colWidths=[130, 660])
        t_mod.setStyle(TableStyle([
            ('SPAN', (0, 0), (1, 0)),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f172a')),
            ('BACKGROUND', (0, 1), (0, -1), colors.HexColor('#f8fafc')),
            ('BACKGROUND', (1, 1), (1, -1), colors.white),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('BOX', (0, 0), (-1, -1), 0.75, colors.HexColor('#cbd5e1')),
            ('GRID', (0, 1), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        elements.append(t_mod)
        elements.append(Spacer(1, 6))

    build_pdf_con_footer(doc, elements)
    return buffer.getvalue()


# =========================================================================
# GENERATORE PDF: MANUALE PROTOCOLLI DI TEST
# =========================================================================

def crea_pdf_manuale_test(protocolli, area_filtro="Tutte le Macro-Aree"):
    """Genera il compendio PDF completo dei protocolli scientifici di test M0V3."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), rightMargin=25, leftMargin=25, topMargin=25, bottomMargin=25)
    elements = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('ManTestTitle', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=17, textColor=colors.HexColor('#0f172a'), spaceAfter=2)
    sub_style = ParagraphStyle('ManTestSub', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=9.5, textColor=colors.HexColor('#0ea5e9'), spaceAfter=8)
    
    sec_h_style = ParagraphStyle('ManTestModH', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8.5, textColor=colors.HexColor('#38bdf8'), leading=10)
    lbl_style = ParagraphStyle('ManTestLbl', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=7.5, textColor=colors.HexColor('#0f172a'), leading=9)
    body_style = ParagraphStyle('ManTestBody', parent=styles['Normal'], fontName='Helvetica', fontSize=7.5, textColor=colors.HexColor('#1e293b'), leading=9.5)
    metric_style = ParagraphStyle('ManTestMet', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=7, textColor=colors.HexColor('#0369a1'), leading=8.5)

    header_title = [
        Paragraph("M0V3 ANALYTICS — MANUALE DEI PROTOCOLLI DI TEST SCIENTIFICI", title_style),
        Paragraph(f"MACRO-AREA: {area_filtro.upper()}   |   STANDARDIZZAZIONE & BENCHMARK ({len(protocolli)} PROTOCOLLI)", sub_style)
    ]
    if os.path.exists(LOGO_PATH):
        logo_img = RLImage(LOGO_PATH, width=45, height=45)
        t_head = Table([[header_title, logo_img]], colWidths=[725, 65])
        t_head.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('ALIGN', (1, 0), (1, 0), 'RIGHT')]))
        elements.append(t_head)
    else:
        elements.extend(header_title)

    for idx, proto in enumerate(protocolli, start=1):
        nome_display = _clean_text_for_pdf(proto.get('nome_protocollo', 'Senza nome'))
        nome_tecnico = _clean_text_for_pdf(proto.get('codice_univoco', ''))
        macro = _clean_text_for_pdf(proto.get('macro_area', ''))
        cat = _clean_text_for_pdf(proto.get('categoria', ''))
        
        obiettivi_txt = _clean_text_for_pdf(proto.get('manuale_obiettivi') or "Standardizzazione M0V3 per la valutazione fisiologica e neuromuscolare.")
        esecuzione_txt = _clean_text_for_pdf(proto.get('manuale_esecuzione') or "Protocollo operativo standardizzato secondo linee guida M0V3.")
        interpretazione_txt = _clean_text_for_pdf(proto.get('manuale_interpretazione') or "Valutare rispetto al benchmark di categoria e al Personal Best dell'atleta.")
        
        schema_metriche = proto.get('schema_metriche', [])
        metriche_parts = []
        for m in schema_metriche:
            u_str = f" ({m.get('unit')})" if m.get('unit') else ""
            lat_str = f" [{m.get('laterality', 'BILATERAL')}]"
            kpi_str = " [PRIMARY]" if m.get('is_primary_kpi') else ""
            metriche_parts.append(f"{m.get('label', m.get('key'))}{u_str}{lat_str}{kpi_str}")
        metriche_txt = _clean_text_for_pdf(" • ".join(metriche_parts)) if metriche_parts else "Nessuna metrica specifica definita."

        proto_rows = [
            [
                Paragraph(f"<b>#{idx} — {nome_display.upper()}</b> <font color='#94a3b8' size='7.5'>[Macro: {macro.upper()} | Cat: {cat} | ID: {nome_tecnico}]</font>", sec_h_style),
                ""
            ],
            [
                Paragraph("<b>OBIETTIVO SCIENTIFICO:</b>", lbl_style),
                Paragraph(obiettivi_txt, body_style)
            ],
            [
                Paragraph("<b>PROTOCOLLO ESECUZIONE:</b>", lbl_style),
                Paragraph(esecuzione_txt, body_style)
            ],
            [
                Paragraph("<b>INTERPRETAZIONE & BENCHMARK:</b>", lbl_style),
                Paragraph(interpretazione_txt, body_style)
            ],
            [
                Paragraph("<b>VARIABILI TRACCIATE:</b>", lbl_style),
                Paragraph(metriche_txt, metric_style)
            ]
        ]

        t_mod = Table(proto_rows, colWidths=[135, 655])
        t_mod.setStyle(TableStyle([
            ('SPAN', (0, 0), (1, 0)),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f172a')),
            ('BACKGROUND', (0, 1), (0, -1), colors.HexColor('#f8fafc')),
            ('BACKGROUND', (1, 1), (1, -1), colors.white),
            ('TOPPADDING', (0, 0), (-1, -1), 2.5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('BOX', (0, 0), (-1, -1), 0.75, colors.HexColor('#cbd5e1')),
            ('GRID', (0, 1), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        elements.append(KeepTogether([t_mod, Spacer(1, 6)]))

    build_pdf_con_footer(doc, elements)
    return buffer.getvalue()


# =========================================================================
# GENERATORE PDF: REFERTO VALUTAZIONE TEST FISICI ATLETA (MULTI-SUBPAGE)
# =========================================================================

def crea_pdf_report_test_fisici(atleta_nome, sessioni, area_filtro="Tutte le Macro-Aree", catalogo=None):
    """
    Genera il Dossier Scientifico Completo di Valutazione Test Fisici & Readiness dell'atleta.
    Include tutte le sottopagine analitiche:
    1. Panoramica Test & Personal Best (PB, ultima misurazione, delta % e trend)
    2. Indici Biomeccanici Derivati Cross-Test (EUR, DSI, COD Deficit, Ratios Spalla)
    3. Executive Summary & Readiness (Rolling Baseline 5 Sessioni ± SWC 0.2*sigma)
    4. Cruscotto Asimmetrie Bilaterali Dx vs Sx (Vettoriale con segno, soglie 10-15%, alert direction-switch)
    5. Registro Cronologico Dettagliato delle Sessioni (Log analitico completo)
    (Esclude le schede operative di puro inserimento dati e costruttore)
    """
    from utils import (
        valuta_readiness_swc,
        calcola_asimmetria_dx_sx,
        calcola_indici_cross_test,
        get_catalogo_protocolli,
    )

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), rightMargin=25, leftMargin=25, topMargin=25, bottomMargin=25)
    elements = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('RepTestTitle', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=15, textColor=colors.HexColor('#0f172a'), spaceAfter=2)
    sub_style = ParagraphStyle('RepTestSub', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8.5, textColor=colors.HexColor('#0ea5e9'), spaceAfter=6)
    sec_title_style = ParagraphStyle('RepTestSecTitle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=9.5, textColor=colors.HexColor('#0f172a'), spaceBefore=6, spaceAfter=4)
    sec_desc_style = ParagraphStyle('RepTestSecDesc', parent=styles['Normal'], fontName='Helvetica', fontSize=7, textColor=colors.HexColor('#64748b'), spaceAfter=4)

    th_style = ParagraphStyle('RepTestTH', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=7.5, textColor=colors.white, alignment=1)
    td_style = ParagraphStyle('RepTestTD', parent=styles['Normal'], fontName='Helvetica', fontSize=7, textColor=colors.HexColor('#0f172a'), leading=8.5)
    td_bold = ParagraphStyle('RepTestTDBold', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=7, textColor=colors.HexColor('#0f172a'), leading=8.5)
    td_center = ParagraphStyle('RepTestTDCenter', parent=styles['Normal'], fontName='Helvetica', fontSize=7, textColor=colors.HexColor('#0f172a'), leading=8.5, alignment=1)
    td_center_bold = ParagraphStyle('RepTestTDCenterBold', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=7, textColor=colors.HexColor('#0f172a'), leading=8.5, alignment=1)

    kpi_title_st = ParagraphStyle('RepTestKPITitle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=7.5, textColor=colors.HexColor('#64748b'), alignment=1)
    kpi_val_st = ParagraphStyle('RepTestKPIVal', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=12, textColor=colors.HexColor('#0f172a'), alignment=1)

    def _parse_s_date(d_val):
        if not d_val:
            return pd.Timestamp.min
        dt = pd.to_datetime(d_val, errors='coerce')
        if pd.isna(dt):
            dt = pd.to_datetime(d_val, dayfirst=True, errors='coerce')
        return dt if pd.notna(dt) else pd.Timestamp.min

    if not catalogo:
        try:
            catalogo = get_catalogo_protocolli()
        except Exception:
            catalogo = []
    protocolli_map = {p['id'] if 'id' in p else p['codice_univoco']: p for p in (catalogo or [])}

    # Header Documento
    header_title = [
        Paragraph("M0V3 ANALYTICS — DOSSIER SCIENTIFICO VALUTAZIONE TEST FISICI & READINESS", title_style),
        Paragraph(f"ATLETA: {atleta_nome.upper()}   |   FILTRO AREA: {area_filtro.upper()}   |   DATA REFERTO: {datetime.date.today().strftime('%d/%m/%Y')}", sub_style)
    ]
    if os.path.exists(LOGO_PATH):
        logo_img = RLImage(LOGO_PATH, width=45, height=45)
        t_head = Table([[header_title, logo_img]], colWidths=[725, 65])
        t_head.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('ALIGN', (1, 0), (1, 0), 'RIGHT')]))
        elements.append(t_head)
    else:
        elements.extend(header_title)

    elements.append(Spacer(1, 4))

    # Elaborazione Test Storici dell'Atleta
    test_groups = {}
    for s in sessioni:
        p_info = s.get('protocollo_info') or protocolli_map.get(s.get('protocollo_id')) or {}
        cod = p_info.get('codice_univoco') or s.get('protocollo_id') or p_info.get('nome_protocollo')
        if not cod: continue
        if cod not in test_groups:
            test_groups[cod] = {
                'codice': cod,
                'protocollo_info': p_info,
                'nome': p_info.get('nome_protocollo', str(cod)),
                'macro_area': p_info.get('macro_area', 'Generale'),
                'strumento': p_info.get('strumento') or s.get('strumentazione') or 'N/D',
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
            chosen_metric = schema[0] if schema else {'key': 'valore', 'label': 'Valore', 'unit': '', 'direction': 'HIGHER_IS_BETTER', 'laterality': 'BILATERAL'}

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
                cand = []
                for vc in (v_dict.get(f"{k}_dx"), v_dict.get(f"{k}_sx")):
                    try:
                        if vc is not None and not pd.isna(vc): cand.append(float(vc))
                    except: pass
                if cand:
                    val_num = max(cand) if is_hib else min(cand)
                elif k in v_dict and v_dict[k] is not None:
                    try: val_num = float(v_dict[k])
                    except: pass
            else:
                if k in v_dict and v_dict[k] is not None:
                    try: val_num = float(v_dict[k])
                    except: pass

            if val_num is not None:
                points.append({'dt': dt_obj, 'date_str': d_fmt, 'value': val_num})

        if not points: continue

        n_count = len(points)
        best_item = max(points, key=lambda p: p['value']) if is_hib else min(points, key=lambda p: p['value'])
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
    recent_dt = max((t['points'][-1]['dt'] for t in elaborated_tests), default=None)
    recent_date_str = recent_dt.strftime('%d/%m/%Y') if recent_dt and recent_dt != pd.Timestamp.min else "N/D"

    # KPI Strip Row
    kpi_cells = [
        [
            Paragraph("TEST PROTOCOLLI SINTESI", kpi_title_st),
            Paragraph("RILEVAZIONI TOTALI", kpi_title_st),
            Paragraph("EFFICIENZA VS PB", kpi_title_st),
            Paragraph("DATA ULTIMO RILEVAMENTO", kpi_title_st)
        ],
        [
            Paragraph(f"<font color='#0284c7'><b>{tot_test_types}</b> Test</font>", kpi_val_st),
            Paragraph(f"<font color='#0f172a'><b>{tot_measurements}</b> Misure</font>", kpi_val_st),
            Paragraph(f"<font color='{'#10b981' if avg_pct_pb>=95 else '#f59e0b'}'><b>{avg_pct_pb:.1f}%</b></font>", kpi_val_st),
            Paragraph(f"<font color='#475569'>{recent_date_str}</font>", kpi_val_st),
        ]
    ]
    t_kpi = Table(kpi_cells, colWidths=[198, 198, 198, 198])
    t_kpi.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
        ('BOX', (0, 0), (-1, -1), 0.75, colors.HexColor('#cbd5e1')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(t_kpi)
    elements.append(Spacer(1, 5))

    # -------------------------------------------------------------
    # SEZIONE 1: PANORAMICA TEST & PERSONAL BEST
    # -------------------------------------------------------------
    elements.append(Paragraph("<b>1. PANORAMICA TEST & RECORD PERSONALI (PB vs ULTIMA MISURAZIONE)</b>", sec_title_style))
    th_pan = [
        Paragraph("<b>TEST / PROTOCOLLO</b>", th_style),
        Paragraph("<b>MACRO-AREA</b>", th_style),
        Paragraph("<b>N° MISURE</b>", th_style),
        Paragraph("<b>PERSONAL BEST</b>", th_style),
        Paragraph("<b>ULTIMA MISURA</b>", th_style),
        Paragraph("<b>% vs PB (DELTA)</b>", th_style),
        Paragraph("<b>TREND / STATO</b>", th_style),
    ]
    rows_pan = [th_pan]

    if elaborated_tests:
        for t in elaborated_tests:
            unit_s = f" {t['unit']}" if t['unit'] else ""
            pb_txt = f"<b>{t['best_val']:.1f}{unit_s}</b><br/><font color='#0284c7' size='6.5'><b>Data: {t['best_date']}</b></font>"
            last_txt = f"<b>{t['last_val']:.1f}{unit_s}</b><br/><font color='#0284c7' size='6.5'><b>Data: {t['last_date']}</b></font>"
            d_sgn = "+" if t['delta_pct'] > 0 else ""
            pct_txt = f"<b>{t['pct_max']:.1f}%</b> ({d_sgn}{t['delta_pct']:.1f}%)"

            if t['pct_max'] >= 98.0:
                tr_color = "#10b981"
                tr_label = "Ottimale / PB"
            elif t['pct_max'] >= 92.0:
                tr_color = "#0284c7"
                tr_label = "In Target"
            elif t['pct_max'] >= 85.0:
                tr_color = "#f59e0b"
                tr_label = "Attenzione"
            else:
                tr_color = "#ef4444"
                tr_label = "Sotto Soglia"

            tr_txt = f"<font color='{tr_color}'><b>{tr_label}</b></font>"

            rows_pan.append([
                Paragraph(f"<b>{_clean_text_for_pdf(t['nome'])}</b><br/><font color='#64748b' size='6'>{_clean_text_for_pdf(t['metric_label'])} · {_clean_text_for_pdf(t['strumento'])}</font>", td_style),
                Paragraph(_clean_text_for_pdf(t['macro_area']), td_style),
                Paragraph(str(t['n_count']), td_center_bold),
                Paragraph(pb_txt, td_center),
                Paragraph(last_txt, td_center),
                Paragraph(pct_txt, td_center_bold),
                Paragraph(tr_txt, td_center_bold),
            ])
    else:
        cat_preview = catalogo[:6] if catalogo else []
        for p in cat_preview:
            rows_pan.append([
                Paragraph(f"<b>{_clean_text_for_pdf(p.get('nome_protocollo', 'Test'))}</b><br/><font color='#64748b' size='6'>{_clean_text_for_pdf(p.get('strumento', 'Strumentazione M0V3'))}</font>", td_style),
                Paragraph(_clean_text_for_pdf(p.get('macro_area', 'Generale')), td_style),
                Paragraph("0", td_center),
                Paragraph("<font color='#94a3b8'>N/D</font>", td_center),
                Paragraph("<font color='#94a3b8'>In Attesa</font>", td_center),
                Paragraph("<font color='#94a3b8'>Baseline da Creare</font>", td_center),
                Paragraph("<font color='#64748b'>In Attesa</font>", td_center),
            ])

    t_pan = Table(rows_pan, colWidths=[185, 95, 55, 125, 125, 107, 100])
    t_pan.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f172a')),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3),
        ('BOX', (0, 0), (-1, -1), 0.75, colors.HexColor('#cbd5e1')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    for r_i in range(1, len(rows_pan)):
        bg_c = '#ffffff' if r_i % 2 != 0 else '#f8fafc'
        t_pan.setStyle(TableStyle([('BACKGROUND', (0, r_i), (-1, r_i), colors.HexColor(bg_c))]))
    elements.append(t_pan)
    elements.append(Spacer(1, 5))

    # -------------------------------------------------------------
    # SEZIONE 2: INDICI BIOMECCANICI DERIVATI CROSS-TEST
    # -------------------------------------------------------------
    elements.append(Paragraph("<b>2. INDICI BIOMECCANICI DERIVATI & CROSS-TEST (STESSA DATA)</b>", sec_title_style))
    elements.append(Paragraph("Calcolo automatico tra prove differenti eseguite nella stessa sessione: Elastic Index / EUR, Dynamic Strength Index, COD Deficit, Ratios Spalla.", sec_desc_style))

    cross_ind = calcola_indici_cross_test(sessioni)
    eur_data = cross_ind.get('eur')
    dsi_data = cross_ind.get('dsi')
    cod_data = cross_ind.get('cod_deficit')
    spalla_ratios = cross_ind.get('spalla') or {}

    # Card 1: EUR
    if eur_data:
        c1_val = f"+{eur_data['diff_cm']:.1f} cm ({eur_data['diff_pct']:+.1f}%)"
        if eur_data.get('is_battery_fallback') and eur_data.get('data_cmj') and eur_data.get('data_sj'):
            sub_d = f"CMJ ({eur_data['data_cmj']}) · SJ ({eur_data['data_sj']})"
        else:
            d_raw = str(eur_data.get('data', ''))
            try:
                dt_p = pd.to_datetime(d_raw, errors='coerce')
                sub_d = f"Data: {dt_p.strftime('%d/%m/%Y')}" if pd.notnull(dt_p) else f"Data: {d_raw}"
            except Exception:
                sub_d = f"Data: {d_raw}"
        c1_sub = f"Ratio EUR: <b>{eur_data['eur_ratio']:.2f}</b> · {sub_d}<br/><font color='{eur_data['colore']}'><b>{_clean_text_for_pdf(eur_data['valutazione'])}</b></font>"
    else:
        c1_val = "Target 1.10 - 1.15"
        c1_sub = "<b>Elastic Index / EUR</b><br/><font color='#64748b'>Eseguire CMJ e SJ nella stessa sessione per calcolare il contributo elastico SSC.</font>"

    # Card 2: DSI
    if dsi_data:
        c2_val = f"DSI {dsi_data['dsi_ratio']:.2f}"
        if dsi_data.get('is_battery_fallback') and dsi_data.get('data_jump') and dsi_data.get('data_imtp'):
            sub_d2 = f"{dsi_data['jump_type']} ({dsi_data['data_jump']}) · IMTP ({dsi_data['data_imtp']})"
        else:
            d_raw2 = str(dsi_data.get('data', ''))
            try:
                dt_p2 = pd.to_datetime(d_raw2, errors='coerce')
                sub_d2 = f"Data: {dt_p2.strftime('%d/%m/%Y')}" if pd.notnull(dt_p2) else f"Data: {d_raw2}"
            except Exception:
                sub_d2 = f"Data: {d_raw2}"
        c2_sub = f"{dsi_data['jump_type']} PF: {dsi_data['pf_jump']:.0f}N · IMTP: {dsi_data['pf_imtp']:.0f}N<br/><font color='{dsi_data['colore']}'><b>{_clean_text_for_pdf(dsi_data['valutazione'])}</b></font>"
    else:
        c2_val = "Target 0.60 - 0.80"
        c2_sub = "<b>Dynamic Strength Index (DSI)</b><br/><font color='#64748b'>Rapporto Salto/IMTP: individua deficit balistico vs deficit forza massimale.</font>"

    # Card 3: COD Deficit
    if cod_data:
        c3_dx = f"{cod_data['cod_def_dx']:+.2f}s" if cod_data.get('cod_def_dx') is not None else "-"
        c3_sx = f"{cod_data['cod_def_sx']:+.2f}s" if cod_data.get('cod_def_sx') is not None else "-"
        c3_val = f"Dx: {c3_dx} | Sx: {c3_sx}"
        if cod_data.get('is_battery_fallback') and cod_data.get('data_505') and cod_data.get('data_10m'):
            sub_d3 = f"5-0-5 ({cod_data['data_505']}) · 10m ({cod_data['data_10m']})"
        else:
            d_raw3 = str(cod_data.get('data', ''))
            try:
                dt_p3 = pd.to_datetime(d_raw3, errors='coerce')
                sub_d3 = f"Data: {dt_p3.strftime('%d/%m/%Y')}" if pd.notnull(dt_p3) else f"Data: {d_raw3}"
            except Exception:
                sub_d3 = f"Data: {d_raw3}"
        c3_sub = f"Sprint 10m: {cod_data['t10m']:.2f}s · Asim: {cod_data['asym_cod']:.1f}%<br/><font color='{cod_data['colore']}'><b>{_clean_text_for_pdf(cod_data['valutazione'])}</b></font>"
    else:
        c3_val = "Asimmetria ≤ 5%"
        c3_sub = "<b>COD Deficit (5-0-5 vs 10m)</b><br/><font color='#64748b'>Tempo 5-0-5 meno Sprint 10m: isola la pura capacità di frenata e ripartenza.</font>"

    # Card 4: Spalla Ratios
    sp_d_raw = spalla_ratios.get('data')
    sp_d_fmt = ""
    if sp_d_raw:
        try: sp_d_fmt = f"Data: {pd.to_datetime(sp_d_raw).strftime('%d/%m/%Y')}"
        except: sp_d_fmt = f"Data: {sp_d_raw}"

    if spalla_ratios.get('trom_dx') is not None or spalla_ratios.get('er_ir_ratio_dx') is not None:
        t_dx = spalla_ratios.get('trom_dx')
        t_sx = spalla_ratios.get('trom_sx')
        r_dx = spalla_ratios.get('er_ir_ratio_dx')
        c4_val = f"TROM {t_dx or t_sx or '-'}° | ER/IR {r_dx or '-'}%"
        trom_d = spalla_ratios.get('trom_diff')
        sub_sp_info = f"Diff TROM: {trom_d:.1f}°" if trom_d is not None else "TROM Bilaterale"
        if sp_d_fmt: sub_sp_info += f" · {sp_d_fmt}"
        c4_sub = f"{sub_sp_info}<br/><font color='#0ea5e9'><b>Target fisiologico ER/IR: 65-75%</b></font>"
    else:
        c4_val = "Target ER/IR 65-75%"
        sub_sp_info = f" · {sp_d_fmt}" if sp_d_fmt else ""
        c4_sub = f"<b>DynaMo Ratios Spalla{sub_sp_info}</b><br/><font color='#64748b'>TROM (IR+ER) e Ratio di forza rotatori: prevenzione GIRD e sovraccarico cuffia.</font>"

    t_cross = Table([
        [
            Paragraph("<b>ELASTIC INDEX / EUR (CMJ vs SJ)</b>", kpi_title_st),
            Paragraph("<b>DYNAMIC STRENGTH INDEX (DSI)</b>", kpi_title_st),
            Paragraph("<b>COD DEFICIT (5-0-5 vs 10m)</b>", kpi_title_st),
            Paragraph("<b>INDICI SPALLA (TROM & ER/IR)</b>", kpi_title_st),
        ],
        [
            Paragraph(f"<font color='#0284c7'><b>{c1_val}</b></font><br/>{c1_sub}", td_style),
            Paragraph(f"<font color='#0284c7'><b>{c2_val}</b></font><br/>{c2_sub}", td_style),
            Paragraph(f"<font color='#0284c7'><b>{c3_val}</b></font><br/>{c3_sub}", td_style),
            Paragraph(f"<font color='#0284c7'><b>{c4_val}</b></font><br/>{c4_sub}", td_style),
        ]
    ], colWidths=[198, 198, 198, 198])
    t_cross.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#ffffff')),
        ('BOX', (0, 0), (-1, -1), 0.75, colors.HexColor('#cbd5e1')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    elements.append(t_cross)

    # PAGE BREAK PER LA SECONDA PAGINA
    elements.append(PageBreak())

    # Header Pagina 2
    header_title_p2 = [
        Paragraph("M0V3 ANALYTICS — READINESS, ASIMMETRIE CLINICHE & STORICO MISURE", title_style),
        Paragraph(f"ATLETA: {atleta_nome.upper()}   |   DATA REFERTO: {datetime.date.today().strftime('%d/%m/%Y')}", sub_style)
    ]
    if os.path.exists(LOGO_PATH):
        t_head_p2 = Table([[header_title_p2, RLImage(LOGO_PATH, width=38, height=38)]], colWidths=[735, 57])
        t_head_p2.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('ALIGN', (1, 0), (1, 0), 'RIGHT')]))
        elements.append(t_head_p2)
    else:
        elements.extend(header_title_p2)
    elements.append(Spacer(1, 4))

    # -------------------------------------------------------------
    # SEZIONE 3: EXECUTIVE SUMMARY & READINESS (ROLLING BASELINE ± SWC)
    # -------------------------------------------------------------
    elements.append(Paragraph("<b>3. EXECUTIVE SUMMARY & READINESS (ROLLING BASELINE 5 SESSIONI ± SWC)</b>", sec_title_style))
    elements.append(Paragraph("Valutazione dello stato di forma dell'atleta confrontando l'ultimo valore registrato con la media storica recente (µ ultime 5 sessioni) e la Smallest Worthwhile Change (SWC = 0.2 × sigma).", sec_desc_style))

    ultime_per_prot = {}
    for s in sorted(sessioni, key=lambda x: str(x.get('data'))):
        p_id = s.get('protocollo_id')
        ultime_per_prot[p_id] = s

    righe_readiness = []
    for p_id, s_ult in ultime_per_prot.items():
        p_info = s_ult.get('protocollo_info') or protocolli_map.get(p_id) or {}
        schema = p_info.get('schema_metriche') or []
        primary_m = next((m for m in schema if m.get('is_primary_kpi')), schema[0] if schema else None)
        if not primary_m: continue
        k = primary_m['key']
        unita = primary_m.get('unit', '')
        dir_m = primary_m.get('direction', 'HIGHER_IS_BETTER')
        v_dict = s_ult.get('valori', {}) or {}

        if primary_m.get('laterality') == 'UNILATERAL':
            val_num = v_dict.get(k) or v_dict.get(f"{k}_max") or v_dict.get(f"{k}_dx")
        else:
            val_num = v_dict.get(k)
        if val_num is None: continue

        try:
            val_f = float(val_num)
            tutti_val = []
            pb_date_str = "-"
            best_tuple = None
            is_hib = (dir_m != 'LOWER_IS_BETTER')
            for sess in sessioni:
                if sess.get('protocollo_id') == p_id:
                    v_tmp = sess.get('valori', {}).get(k) or sess.get('valori', {}).get(f"{k}_max") or sess.get('valori', {}).get(f"{k}_dx")
                    if v_tmp is not None:
                        try:
                            vf = float(v_tmp)
                            tutti_val.append(vf)
                            dt_s = str(sess.get('data', ''))
                            if best_tuple is None or (vf > best_tuple[0] if is_hib else vf < best_tuple[0]):
                                best_tuple = (vf, dt_s)
                        except: pass
            if best_tuple and best_tuple[1]:
                try: pb_date_str = pd.to_datetime(best_tuple[1]).strftime('%d/%m/%Y')
                except: pb_date_str = str(best_tuple[1])

            stato_lbl, col_read, delta_m, txt_m, pb_v, med_5, swc_v = valuta_readiness_swc(val_f, tutti_val, dir_m)
            pb_str = f"{pb_v:.1f} {unita}" if pb_v is not None else "-"
            med_swc_str = f"{med_5:.1f} (±{swc_v:.1f}) {unita}" if (med_5 is not None and swc_v is not None) else "-"

            d_ult_raw = str(s_ult.get('data', ''))
            try: d_ult_fmt = pd.to_datetime(d_ult_raw).strftime('%d/%m/%Y')
            except: d_ult_fmt = d_ult_raw

            righe_readiness.append({
                'categoria': p_info.get('macro_area') or p_info.get('categoria') or 'Test',
                'nome': p_info.get('nome_protocollo', 'Test'),
                'kpi': primary_m.get('label', k),
                'risultato': f"{val_f:.1f} {unita}",
                'data_test': d_ult_fmt,
                'pb': pb_str,
                'data_pb': pb_date_str,
                'media_swc': med_swc_str,
                'delta_vs_media': txt_m,
                'stato_lbl': stato_lbl,
                'col_read': col_read
            })
        except: pass

    th_read = [
        Paragraph("<b>CATEGORIA</b>", th_style),
        Paragraph("<b>PROTOCOLLO TEST</b>", th_style),
        Paragraph("<b>RISULTATO ATTUALE</b>", th_style),
        Paragraph("<b>PERSONAL BEST</b>", th_style),
        Paragraph("<b>MEDIA RECENTE (±SWC)</b>", th_style),
        Paragraph("<b>vs MEDIA RECENTE</b>", th_style),
        Paragraph("<b>STATO READINESS</b>", th_style),
    ]
    rows_read = [th_read]

    if righe_readiness:
        for r in righe_readiness:
            st_badge = f"<font color='{r['col_read']}'><b>{r['stato_lbl']}</b></font>"
            rows_read.append([
                Paragraph(_clean_text_for_pdf(r['categoria']), td_style),
                Paragraph(f"<b>{_clean_text_for_pdf(r['nome'])}</b><br/><font color='#64748b' size='6'>{_clean_text_for_pdf(r['kpi'])}</font>", td_style),
                Paragraph(f"<b>{r['risultato']}</b><br/><font color='#0284c7' size='6.5'><b>Data: {r['data_test']}</b></font>", td_center_bold),
                Paragraph(f"<b>{r['pb']}</b><br/><font color='#64748b' size='6'>PB: {r['data_pb']}</font>", td_center),
                Paragraph(r['media_swc'], td_center),
                Paragraph(r['delta_vs_media'], td_center_bold),
                Paragraph(st_badge, td_center_bold),
            ])
    else:
        rows_read.append([
            Paragraph("Benchmark Fisiologico", td_style),
            Paragraph("Countermovement Jump & Sprint", td_style),
            Paragraph("In Attesa", td_center),
            Paragraph("N/D", td_center),
            Paragraph("Banda SWC (±0.2·σ)", td_center),
            Paragraph("Baseline da Definire", td_center),
            Paragraph("<font color='#64748b'><b>IN ATTESA DI DATI</b></font>", td_center_bold),
        ])

    t_read = Table(rows_read, colWidths=[100, 160, 105, 105, 125, 95, 102])
    t_read.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f172a')),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3),
        ('BOX', (0, 0), (-1, -1), 0.75, colors.HexColor('#cbd5e1')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    for r_i in range(1, len(rows_read)):
        bg_c = '#ffffff' if r_i % 2 != 0 else '#f8fafc'
        t_read.setStyle(TableStyle([('BACKGROUND', (0, r_i), (-1, r_i), colors.HexColor(bg_c))]))
    elements.append(t_read)
    elements.append(Spacer(1, 5))

    # -------------------------------------------------------------
    # SEZIONE 4: CRUSCOTTO ASIMMETRIE BILATERALI DX vs SX
    # -------------------------------------------------------------
    elements.append(Paragraph("<b>4. CRUSCOTTO ASIMMETRIE BILATERALI DX vs SX (PREVENZIONE INFORTUNI & RTP)</b>", sec_title_style))
    elements.append(Paragraph("Formula vettoriale con segno: (+) Dominanza Destra | (-) Dominanza Sinistra. Soglie cliniche: Fisiologico (≤10%) | Attenzione (10-15%) | Rischio Elevato (>15%).", sec_desc_style))

    asimmetrie_rilevate = []
    for p_id, s_ult in ultime_per_prot.items():
        p_info = s_ult.get('protocollo_info') or protocolli_map.get(p_id) or {}
        schema = p_info.get('schema_metriche') or []
        v_dict = s_ult.get('valori', {}) or {}
        d_as_raw = str(s_ult.get('data', ''))
        try: d_as_fmt = pd.to_datetime(d_as_raw).strftime('%d/%m/%Y')
        except: d_as_fmt = d_as_raw

        for m in schema:
            if m.get('laterality') == 'UNILATERAL':
                k = m['key']
                dx = v_dict.get(f"{k}_dx")
                sx = v_dict.get(f"{k}_sx")
                asym_val = v_dict.get(f"{k}_asym_pct")
                asym_dir = v_dict.get(f"{k}_asym_dir")

                if (asym_val is None or asym_dir is None) and dx is not None and sx is not None:
                    asym_val, asym_dir, _, signed_a = calcola_asimmetria_dx_sx(dx, sx, m.get('direction', 'HIGHER_IS_BETTER'))

                if asym_val is not None:
                    try:
                        a_float = float(asym_val)
                        dx_f = float(dx) if dx is not None else None
                        sx_f = float(sx) if sx is not None else None
                        sign_str = "+" if asym_dir == "Dx" else ("-" if asym_dir == "Sx" else "=")

                        if a_float <= 10.0:
                            fascia = "Fisiologico (≤10%)"
                            col_fascia = "#10b981"
                        elif a_float <= 15.0:
                            fascia = "Attenzione (10-15%)"
                            col_fascia = "#f59e0b"
                        else:
                            fascia = "Rischio Elevato (>15%)"
                            col_fascia = "#ef4444"

                        asimmetrie_rilevate.append({
                            'test': f"{p_info.get('nome_protocollo')}: {m.get('label', k)}",
                            'data': d_as_fmt,
                            'dx': f"{dx_f:.1f} {m.get('unit', '')}" if dx_f is not None else "-",
                            'sx': f"{sx_f:.1f} {m.get('unit', '')}" if sx_f is not None else "-",
                            'asym_signed': f"{sign_str}{a_float:.1f}%",
                            'dominanza': asym_dir or "=",
                            'fascia': fascia,
                            'col_fascia': col_fascia
                        })
                    except: pass

    th_asym = [
        Paragraph("<b>TEST / METRICA UNILATERALE</b>", th_style),
        Paragraph("<b>DATA TEST</b>", th_style),
        Paragraph("<b>VALORE DESTRO (Dx)</b>", th_style),
        Paragraph("<b>VALORE SINISTRO (Sx)</b>", th_style),
        Paragraph("<b>ASIMMETRIA VETTORIALE</b>", th_style),
        Paragraph("<b>DOMINANZA PRESTATIVA</b>", th_style),
        Paragraph("<b>FASCIA CLINICA / ALERT</b>", th_style),
    ]
    rows_asym = [th_asym]

    if asimmetrie_rilevate:
        for a in asimmetrie_rilevate:
            f_badge = f"<font color='{a['col_fascia']}'><b>{a['fascia']}</b></font>"
            rows_asym.append([
                Paragraph(f"<b>{_clean_text_for_pdf(a['test'])}</b>", td_style),
                Paragraph(f"<font color='#0284c7' size='6.5'><b>{a['data']}</b></font>", td_center),
                Paragraph(a['dx'], td_center),
                Paragraph(a['sx'], td_center),
                Paragraph(f"<b>{a['asym_signed']}</b>", td_center_bold),
                Paragraph(a['dominanza'], td_center_bold),
                Paragraph(f_badge, td_center_bold),
            ])
    else:
        rows_asym.append([
            Paragraph("Protocolli Dinamometrici & Salto Monopodalico", td_style),
            Paragraph("-", td_center),
            Paragraph("In Attesa", td_center),
            Paragraph("In Attesa", td_center),
            Paragraph("0.0%", td_center),
            Paragraph("Simmetrico", td_center),
            Paragraph("<font color='#10b981'><b>Fascia Fisiologica Attesa (≤10%)</b></font>", td_center_bold),
        ])

    t_asym = Table(rows_asym, colWidths=[180, 65, 80, 80, 95, 75, 117])
    t_asym.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f172a')),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3),
        ('BOX', (0, 0), (-1, -1), 0.75, colors.HexColor('#cbd5e1')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    for r_i in range(1, len(rows_asym)):
        bg_c = '#ffffff' if r_i % 2 != 0 else '#f8fafc'
        t_asym.setStyle(TableStyle([('BACKGROUND', (0, r_i), (-1, r_i), colors.HexColor(bg_c))]))
    elements.append(t_asym)
    elements.append(Spacer(1, 5))

    # -------------------------------------------------------------
    # SEZIONE 5: REGISTRO CRONOLOGICO DELLE MISURAZIONI (SESSION LOG)
    # -------------------------------------------------------------
    if len(sessioni) > 4:
        elements.append(PageBreak())
        header_title_p3 = [
            Paragraph("M0V3 ANALYTICS — REGISTRO CRONOLOGICO DELLE MISURAZIONI", title_style),
            Paragraph(f"ATLETA: {atleta_nome.upper()}   |   DATA REFERTO: {datetime.date.today().strftime('%d/%m/%Y')}", sub_style)
        ]
        if os.path.exists(LOGO_PATH):
            t_head_p3 = Table([[header_title_p3, RLImage(LOGO_PATH, width=38, height=38)]], colWidths=[735, 57])
            t_head_p3.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('ALIGN', (1, 0), (1, 0), 'RIGHT')]))
            elements.append(t_head_p3)
        else:
            elements.extend(header_title_p3)
        elements.append(Spacer(1, 4))

    elements.append(Paragraph("<b>5. REGISTRO CRONOLOGICO DETTAGLIATO DELLE MISURAZIONI (LOG COMPLETO)</b>", sec_title_style))
    elements.append(Paragraph("Archivio storico di tutte le rilevazioni registrate per l'atleta con parametri operativi, valori chiave e asimmetrie.", sec_desc_style))

    table_data = [[
        Paragraph("<b>DATA</b>", th_style),
        Paragraph("<b>TEST PROTOCOLLO</b>", th_style),
        Paragraph("<b>MACRO-AREA</b>", th_style),
        Paragraph("<b>AMBIENTE</b>", th_style),
        Paragraph("<b>STRUMENTO</b>", th_style),
        Paragraph("<b>VALORI CHIAVE RILEVATI</b>", th_style),
        Paragraph("<b>ASIMMETRIA %</b>", th_style)
    ]]

    if sessioni:
        sess_sorted = sorted(sessioni, key=lambda s: str(s.get('data')), reverse=True)
        for s in sess_sorted:
            p_info = s.get('protocollo_info') or protocolli_map.get(s.get('protocollo_id')) or {}
            nome_t = _clean_text_for_pdf(p_info.get('nome_protocollo', 'Test'))
            macro_t = _clean_text_for_pdf(p_info.get('macro_area', '-'))
            amb_t = _clean_text_for_pdf(s.get('condizione_ambiente', 'Outdoor'))
            strum_t = _clean_text_for_pdf(s.get('strumentazione') or p_info.get('strumento') or '-')
            data_t = _clean_text_for_pdf(str(s.get('data', '')))

            valori = s.get('valori', {}) or {}
            val_str_list = []
            asym_str_list = []

            for k, v in valori.items():
                if k.endswith('_asym_pct'):
                    base = k.replace('_asym_pct', '')
                    d_val = valori.get(f"{base}_asym_dir", "")
                    dir_label = f" ({d_val})" if d_val else ""
                    asym_str_list.append(f"{base}: <b>{v}%</b>{dir_label}")
                elif not k.endswith('_dir') and not k.endswith('_mean') and not k.endswith('_max'):
                    val_str_list.append(f"{k}: <b>{v}</b>")

            val_display = _clean_text_for_pdf(" • ".join(val_str_list[:4]))
            asym_display = _clean_text_for_pdf(" • ".join(asym_str_list[:2])) if asym_str_list else "-"

            table_data.append([
                Paragraph(data_t, td_bold),
                Paragraph(nome_t, td_bold),
                Paragraph(macro_t, td_style),
                Paragraph(amb_t, td_style),
                Paragraph(strum_t, td_style),
                Paragraph(val_display, td_style),
                Paragraph(asym_display, td_style)
            ])
    else:
        table_data.append([
            Paragraph("In Attesa", td_center),
            Paragraph("Nessuna sessione registrata nello storico per l'atleta", td_style),
            Paragraph("-", td_center),
            Paragraph("-", td_center),
            Paragraph("-", td_center),
            Paragraph("Le nuove misurazioni inserite confluiranno automaticamente in questo registro.", td_style),
            Paragraph("-", td_center)
        ])

    t_sess_style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f172a')),
        ('TOPPADDING', (0, 0), (-1, -1), 2.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3),
        ('BOX', (0, 0), (-1, -1), 0.75, colors.HexColor('#cbd5e1')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ])
    row_bgs = {idx: ('#ffffff' if idx % 2 == 0 else '#f8fafc') for idx in range(len(table_data) - 1)}
    elements.extend(genera_blocco_tabella_paginata(
        table_data[1:], [65, 140, 115, 60, 85, 230, 97], table_data[0], t_sess_style,
        max_righe_p1=11, max_righe_pn=15, row_bg_colors=row_bgs
    ))

    # Sezione Note Metodologiche & Bibliografia Validata
    elements.extend(genera_sezione_metodologia_pdf("test_fisici", styles))

    build_pdf_con_footer(doc, elements)
    return buffer.getvalue()



# =========================================================================
# GENERATORE PDF: MASTER CALENDAR & AREA MEDICA
# =========================================================================

def crea_pdf_calendario_medico(atleta_nome, month, year, master_calendar, kpis):
    """Genera il referto clinico/prestativo mensile in formato PDF per Calendario & Area Medica."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), rightMargin=25, leftMargin=25, topMargin=25, bottomMargin=25)
    elements = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('RepMedTitle', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=16, textColor=colors.HexColor('#0f172a'), spaceAfter=2)
    sub_style = ParagraphStyle('RepMedSub', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=9, textColor=colors.HexColor('#0ea5e9'), spaceAfter=8)

    th_style = ParagraphStyle('RepMedTH', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=7.5, textColor=colors.white, alignment=1)
    td_style = ParagraphStyle('RepMedTD', parent=styles['Normal'], fontName='Helvetica', fontSize=7, textColor=colors.HexColor('#0f172a'), leading=8.5)
    td_bold = ParagraphStyle('RepMedTDBold', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=7, textColor=colors.HexColor('#0f172a'), leading=8.5)
    kpi_title_st = ParagraphStyle('RepMedKPITitle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=7.5, textColor=colors.HexColor('#64748b'), alignment=1)
    kpi_val_st = ParagraphStyle('RepMedKPIVal', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=12, textColor=colors.HexColor('#0f172a'), alignment=1)

    nome_mese_str = datetime.date(year, month, 1).strftime('%B %Y')
    header_title = [
        Paragraph("M0V3 ANALYTICS — MASTER TIMELINE CLINICA & DISPONIBILITA ATLETICA", title_style),
        Paragraph(f"ATLETA: {atleta_nome.upper()}   |   PERIODO: {nome_mese_str.upper()}   |   DATA REFERTO: {datetime.date.today().strftime('%d/%m/%Y')}", sub_style)
    ]
    if os.path.exists(LOGO_PATH):
        logo_img = RLImage(LOGO_PATH, width=45, height=45)
        t_head = Table([[header_title, logo_img]], colWidths=[725, 65])
        t_head.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('ALIGN', (1, 0), (1, 0), 'RIGHT')]))
        elements.append(t_head)
    else:
        elements.extend(header_title)

    elements.append(Spacer(1, 6))

    # KPI Summary Row
    kpi_cells = [
        [Paragraph("DISPONIBILITA PIENA", kpi_title_st), Paragraph("CARICO ADATTATO", kpi_title_st), Paragraph("STOP MEDICO", kpi_title_st), Paragraph("TRATTAMENTI FISIO", kpi_title_st), Paragraph("RIPOSO / TRASFERTA", kpi_title_st)],
        [
            Paragraph(f"<font color='#10b981'>{kpis.get('pct_disp', 100):.0f}%</font>", kpi_val_st),
            Paragraph(f"<font color='#f59e0b'>{kpis.get('giorni_limitato', 0)} gg</font>", kpi_val_st),
            Paragraph(f"<font color='#e11d48'>{kpis.get('giorni_stop', 0)} gg</font>", kpi_val_st),
            Paragraph(f"<font color='#0284c7'>{kpis.get('tot_trattamenti', 0)} sedute</font>", kpi_val_st),
            Paragraph(f"<font color='#64748b'>{kpis.get('giorni_viaggio', 0)} gg</font>", kpi_val_st),
        ]
    ]
    t_kpi = Table(kpi_cells, colWidths=[158, 158, 158, 158, 158])
    t_kpi.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
        ('BOX', (0, 0), (-1, -1), 0.75, colors.HexColor('#cbd5e1')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(t_kpi)
    elements.append(Spacer(1, 8))

    # Daily Timeline Table
    table_headers = [
        Paragraph("DATA", th_style),
        Paragraph("STATUS", th_style),
        Paragraph("CARICO GPS / IMU", th_style),
        Paragraph("CARICO sRPE", th_style),
        Paragraph("WELLNESS MATTUTINO", th_style),
        Paragraph("TEST FISICI", th_style),
        Paragraph("DIARIO CLINICO, TRATTAMENTI & INDICAZIONI", th_style),
    ]

    table_data = [table_headers]
    status_bg_colors = {
        'DISPONIBILE': '#ecfdf5',
        'LIMITATO': '#fffbeb',
        'INDISPONIBILE': '#fff1f2',
        'RIPOSO_VIAGGIO': '#f0f9ff'
    }

    dates_sorted = sorted(master_calendar.keys())
    for d_str in dates_sorted:
        d_val = master_calendar[d_str]
        st_op = d_val.get('status_operativo', 'DISPONIBILE')

        # GPS summary
        if d_val.get('gps_presente'):
            tl_g = int(round(d_val.get('training_load_gps', 0)))
            match_txt = " [MATCH]" if d_val.get('is_match') else ""
            gps_txt = f"TL: <b>{tl_g}</b>{match_txt}"
        else:
            gps_txt = "-"

        # sRPE summary
        if d_val.get('srpe_presente'):
            srpe_g = int(round(d_val.get('srpe_carico', 0)))
            no_gps_tag = " (NO-GPS)" if d_val.get('solo_carico_interno') else ""
            srpe_txt = f"Carico: <b>{srpe_g}</b>{no_gps_tag}"
        else:
            srpe_txt = "-"

        # Wellness summary
        if d_val.get('wellness_presente') and d_val.get('wellness_score') is not None:
            w_score = d_val.get('wellness_score', 0)
            doms = d_val.get('wellness_dettagli', {}).get('doms', 0)
            well_txt = f"Score: <b>{w_score:.1f}</b> | DOMS: <b>{doms}</b>"
        else:
            well_txt = "-"

        # Test summary
        test_cnt = d_val.get('test_count', 0)
        test_txt = f"{test_cnt} test eseguiti" if test_cnt > 0 else "-"

        # Clinical diary summary
        evs = d_val.get('medico_eventi', [])
        if evs:
            med_lines = []
            for ev in evs:
                t_ev = _clean_text_for_pdf(ev.get('tipo_scheda', 'EVENTO'))
                distr = _clean_text_for_pdf(ev.get('distretto_anatomico', 'Sistemico'))
                vas = ev.get('scala_dolore_vas')
                vas_str = f" [VAS {vas}]" if vas is not None else ""
                staff_ind = _clean_text_for_pdf(ev.get('indicazioni_staff', ''))
                line_str = f"• <b>[{t_ev}]</b> {distr}{vas_str}"
                if staff_ind:
                    line_str += f" | {staff_ind}"
                med_lines.append(line_str)
            med_txt = "<br/>".join(med_lines[:3])
        else:
            med_txt = "-"

        table_data.append([
            Paragraph(d_str, td_bold),
            Paragraph(st_op, td_bold),
            Paragraph(gps_txt, td_style),
            Paragraph(srpe_txt, td_style),
            Paragraph(well_txt, td_style),
            Paragraph(test_txt, td_style),
            Paragraph(med_txt, td_style)
        ])

    t_style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f172a')),
        ('TOPPADDING', (0, 0), (-1, -1), 2.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3),
        ('BOX', (0, 0), (-1, -1), 0.75, colors.HexColor('#cbd5e1')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ])
    # Highlight non-disponibile rows via row_bg_colors
    row_bgs = {}
    for r_idx, d_str in enumerate(dates_sorted):
        st_op = master_calendar[d_str].get('status_operativo', 'DISPONIBILE')
        if st_op in status_bg_colors:
            row_bgs[r_idx] = status_bg_colors[st_op]

    elements.extend(genera_blocco_tabella_paginata(
        table_data[1:], [65, 80, 85, 85, 95, 75, 305], table_data[0], t_style,
        max_righe_p1=11, max_righe_pn=15, row_bg_colors=row_bgs
    ))

    # Sezione Note Metodologiche & Bibliografia Validata
    elements.extend(genera_sezione_metodologia_pdf("acwr", styles))

    build_pdf_con_footer(doc, elements)
    return buffer.getvalue()


def crea_pdf_move_tennis_test(test_dict, dati_calc):
    """
    Genera il referto ufficiale M0V3 Tennis Test (Neuro-Mechanical Fatigue Profiling) in formato A4 Portrait.
    Include metriche dei 6 round, indici compositi (EDI, TPS, CMJ, GRS, PCI), R.A.A. e diagnosi clinica con 4 direttive operative.
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=25,
        leftMargin=25,
        topMargin=25,
        bottomMargin=25
    )
    elements = []
    styles = getSampleStyleSheet()

    # Stili tipografici
    title_st = ParagraphStyle('M0V3Title', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=15, textColor=colors.HexColor('#0f172a'), spaceAfter=2)
    sub_st = ParagraphStyle('M0V3Sub', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8.5, textColor=colors.HexColor('#0284c7'), spaceAfter=8)
    sec_title = ParagraphStyle('M0V3SecTitle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=10, textColor=colors.HexColor('#0f172a'), spaceBefore=8, spaceAfter=4)

    th_st = ParagraphStyle('M0V3TH', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=6.5, textColor=colors.white, alignment=1)
    td_st = ParagraphStyle('M0V3TD', parent=styles['Normal'], fontName='Helvetica', fontSize=6.5, textColor=colors.HexColor('#0f172a'), alignment=1)
    td_bold = ParagraphStyle('M0V3TDBold', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=6.5, textColor=colors.HexColor('#0f172a'), alignment=1)

    kpi_title_st = ParagraphStyle('M0V3KPITitle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=6.5, textColor=colors.HexColor('#64748b'), alignment=1)
    kpi_val_st = ParagraphStyle('M0V3KPIVal', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=11, textColor=colors.HexColor('#0f172a'), alignment=1)

    diag_title_st = ParagraphStyle('M0V3DiagTitle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=10, textColor=colors.HexColor('#0369a1'), spaceAfter=3)
    diag_body_st = ParagraphStyle('M0V3DiagBody', parent=styles['Normal'], fontName='Helvetica', fontSize=7.5, textColor=colors.HexColor('#334155'), leading=10.5)

    sug_h_st = ParagraphStyle('M0V3SugH', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=7.5, textColor=colors.HexColor('#0f172a'))
    sug_t_st = ParagraphStyle('M0V3SugT', parent=styles['Normal'], fontName='Helvetica', fontSize=6.5, textColor=colors.HexColor('#475569'), leading=9)

    atleta = _clean_text_for_pdf(test_dict.get('atleta', 'Flavio Cobolli'))
    data_test = _clean_text_for_pdf(test_dict.get('data', ''))
    ambiente = _clean_text_for_pdf(test_dict.get('ambiente', 'Outdoor'))
    superficie = _clean_text_for_pdf(test_dict.get('superficie', 'Hard'))

    # Header con logo e metadati
    header_left = [
        Paragraph("M0V3 TENNIS TEST — NEURO-MECHANICAL FATIGUE PROFILING", title_st),
        Paragraph(f"ATLETA: {atleta.upper()}   |   DATA: {data_test}   |   AMBIENTE: {ambiente.upper()}   |   SUPERFICIE: {superficie.upper()}", sub_st)
    ]
    if os.path.exists(LOGO_PATH):
        logo_img = RLImage(LOGO_PATH, width=42, height=42)
        t_header = Table([[header_left, logo_img]], colWidths=[475, 70])
        t_header.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT')
        ]))
        elements.append(t_header)
    else:
        elements.extend(header_left)

    elements.append(Spacer(1, 4))

    # --- KPI CARDS (6 metriche chiave) ---
    avg_edi = dati_calc.get("avg_edi", 0.0)
    tps_min = dati_calc.get("tps_min", 0)
    cmj_final = dati_calc.get("cmj_final", 0)
    grs_final = dati_calc.get("grs_final", 0)
    pci_min = dati_calc.get("pci_min", 0)
    has_raa = dati_calc.get("has_raa", False)
    eff_tec = dati_calc.get("eff_tec", 0.0)
    fi_vel = dati_calc.get("fi_vel", 0.0)
    fi_acc = dati_calc.get("fi_acc", 0.0)

    pci_color = '#0284c7' if abs(pci_min) <= 10 else ('#ef4444' if pci_min > 0 else '#f59e0b')
    raa_lbl = f"{eff_tec:.1f} (FI {fi_vel:.0f}%)" if has_raa else "N/D"

    kpi_matrix = [
        [
            Paragraph("EDI (EXPLOSIVITY)", kpi_title_st),
            Paragraph("TPS (WORK CAPACITY)", kpi_title_st),
            Paragraph("CMJ SCORE (POTENZA)", kpi_title_st),
            Paragraph("GRS (RESILIENZA)", kpi_title_st),
            Paragraph("PCI (DECOUPLING)", kpi_title_st),
            Paragraph("R.A.A. EFFICIENZA", kpi_title_st),
        ],
        [
            Paragraph(f"<font color='#0284c7'><b>{avg_edi:.1f}%</b></font>", kpi_val_st),
            Paragraph(f"<font color='#f59e0b'><b>{tps_min}%</b></font>", kpi_val_st),
            Paragraph(f"<font color='#10b981'><b>{cmj_final}%</b></font>", kpi_val_st),
            Paragraph(f"<font color='#8b5cf6'><b>{grs_final}%</b></font>", kpi_val_st),
            Paragraph(f"<font color='{pci_color}'><b>{pci_min:+d}</b></font>", kpi_val_st),
            Paragraph(f"<font color='#0284c7'><b>{raa_lbl}</b></font>", kpi_val_st),
        ]
    ]
    t_kpi = Table(kpi_matrix, colWidths=[90, 91, 91, 91, 91, 91])
    t_kpi.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
        ('BOX', (0, 0), (-1, -1), 0.75, colors.HexColor('#cbd5e1')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(t_kpi)

    elements.append(Spacer(1, 6))

    # --- TABELLA 6 ROUND ---
    elements.append(Paragraph("DATI ANALITICI DEI 6 ROUND (METRICHE ACCELEROMETRICHE, GPS & JUMP)", sec_title))

    tab_h = [
        Paragraph("RND", th_st),
        Paragraph("TL", th_st),
        Paragraph("VMAX<br/>km/h", th_st),
        Paragraph("ACC<br/>m/s²", th_st),
        Paragraph("DEC<br/>m/s²", th_st),
        Paragraph("TL HIGH<br/>Vol / %", th_st),
        Paragraph("ACC/DEC<br/>HIGH n", th_st),
        Paragraph("TLMAX<br/>30\"", th_st),
        Paragraph("CMJ<br/>cm", th_st),
        Paragraph("CMJ<br/>Watt", th_st),
        Paragraph("EDI<br/>%", th_st),
        Paragraph("TPS<br/>%", th_st),
        Paragraph("CMJ<br/>Score %", th_st),
        Paragraph("PCI<br/>Decoup.", th_st),
    ]
    tab_rows = [tab_h]

    for rc in dati_calc.get("rounds", []):
        r_num = rc.get("round", 1)
        tl_val = rc.get("training_load", 0)
        v_val = rc.get("vmax", 0.0)
        a_val = rc.get("acc_max", 0.0)
        d_val = rc.get("dec_max", 0.0)
        tl_h_vol = rc.get("tl_high_vol", 0)
        tl_h_pct = rc.get("tl_high_pct", 0)
        acc_h = rc.get("acc_high_n", 0)
        dec_h = rc.get("dec_high_n", 0)
        tlm = rc.get("tlmax_30", 0)
        cmj_cm = rc.get("cmj_cm", 0.0)
        cmj_w = rc.get("cmj_power", 0)
        edi_r = rc.get("edi", 0.0)
        tps_r = rc.get("tps", 0)
        cmj_s = rc.get("cmj_score", 0)
        pci_r = rc.get("pci", 0)

        pci_str = f"{pci_r:+d}"
        tab_rows.append([
            Paragraph(f"<b>R{r_num}</b>", td_bold),
            Paragraph(str(tl_val), td_st),
            Paragraph(f"{v_val:.1f}", td_st),
            Paragraph(f"{a_val:.1f}", td_st),
            Paragraph(f"{d_val:.1f}", td_st),
            Paragraph(f"{tl_h_vol} ({tl_h_pct}%)", td_st),
            Paragraph(f"{acc_h} / {dec_h}", td_st),
            Paragraph(str(tlm), td_st),
            Paragraph(f"{cmj_cm:.1f}", td_st),
            Paragraph(str(cmj_w), td_st),
            Paragraph(f"<b>{edi_r:.0f}%</b>", td_bold),
            Paragraph(f"<b>{tps_r}%</b>", td_bold),
            Paragraph(f"<b>{cmj_s}%</b>", td_bold),
            Paragraph(f"<b>{pci_str}</b>", td_bold),
        ])

    t_rounds = Table(tab_rows, colWidths=[28, 30, 42, 40, 40, 52, 46, 36, 38, 45, 38, 36, 40, 34])
    t_rounds.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f172a')),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 1.5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 1.5),
        ('BOX', (0, 0), (-1, -1), 0.75, colors.HexColor('#cbd5e1')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(t_rounds)

    elements.append(Spacer(1, 6))

    # --- SEZIONE DIAGNOSI CLINICA AUTOMATICA (PAGE 5 PDF) ---
    diag = dati_calc.get("diagnosi", {})
    titolo_diag = _clean_text_for_pdf(diag.get("titolo", "Profilazione Neuro-Meccanica"))
    corpo_diag = _clean_text_for_pdf(diag.get("corpo", ""))

    diag_cells = [
        [Paragraph(f"CLINICAL PROFILING: {titolo_diag.upper()}", diag_title_st)],
        [Paragraph(corpo_diag, diag_body_st)]
    ]
    t_diag = Table(diag_cells, colWidths=[545])
    t_diag.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f0f9ff')),
        ('BOX', (0, 0), (-1, -1), 1.0, colors.HexColor('#0284c7')),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(t_diag)

    elements.append(Spacer(1, 6))

    # --- 4 DIRETTIVE OPERATIVE ---
    elements.append(Paragraph("DIRETTIVE OPERATIVE & PROGRAMMAZIONE SFORZI (ACTION PLAN)", sec_title))

    suggerimenti = diag.get("suggerimenti", [])
    sug_rows = []
    for sug in suggerimenti:
        s_title = _clean_text_for_pdf(sug[0])
        s_obj = _clean_text_for_pdf(sug[1])
        s_act = _clean_text_for_pdf(sug[2])

        content = [
            Paragraph(f"<b>{s_title}</b>", sug_h_st),
            Paragraph(f"<b>{s_obj}</b>", sug_t_st),
            Paragraph(s_act, sug_t_st)
        ]
        sug_rows.append([content])

    if sug_rows:
        t_sug = Table(sug_rows, colWidths=[545])
        t_sug.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
            ('BOX', (0, 0), (-1, -1), 0.75, colors.HexColor('#cbd5e1')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
            ('TOPPADDING', (0, 0), (-1, -1), 3.5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3.5),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(t_sug)

    # Sezione Note Metodologiche & Bibliografia Validata
    elements.extend(genera_sezione_metodologia_pdf("test_fisici", styles))

    build_pdf_con_footer(doc, elements, is_landscape=False)
    return buffer.getvalue()


def crea_pdf_carico_interno(atleta_nome, periodo_label, kpis, df_srpe=None, df_wellness=None):
    """
    Genera il Referto Esecutivo PDF M0V3 per Carico Interno (sRPE) e Wellness.
    Include KPI di sintesi, indice di efficienza meccanico/soggettiva e tabelle giornaliere.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=24,
        rightMargin=24,
        topMargin=24,
        bottomMargin=28
    )
    elements = []
    styles = getSampleStyleSheet()

    title_st = ParagraphStyle('CiTitle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=14, textColor=colors.HexColor('#0f172a'), leading=17)
    sub_st = ParagraphStyle('CiSub', parent=styles['Normal'], fontName='Helvetica', fontSize=8, textColor=colors.HexColor('#64748b'), leading=10)
    sec_title = ParagraphStyle('CiSec', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=9, textColor=colors.HexColor('#0284c7'), leading=11, spaceBefore=6, spaceAfter=4)
    th_st = ParagraphStyle('CiTH', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=7, textColor=colors.HexColor('#ffffff'), alignment=1)
    td_st = ParagraphStyle('CiTD', parent=styles['Normal'], fontName='Helvetica', fontSize=7, textColor=colors.HexColor('#0f172a'), alignment=1)
    td_bold = ParagraphStyle('CiTDBold', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=7, textColor=colors.HexColor('#0f172a'), alignment=1)
    kpi_lbl = ParagraphStyle('CiKPILbl', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=7, textColor=colors.HexColor('#64748b'), alignment=1)
    kpi_val = ParagraphStyle('CiKPIVal', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=11, textColor=colors.HexColor('#0f172a'), alignment=1)

    # 1. Header Istituzionale
    header_title = [
        Paragraph("M0V3 ANALYTICS — MONITORAGGIO CARICO INTERNO & WELLNESS", title_st),
        Paragraph(f"ATLETA: {atleta_nome.upper()}   |   PERIODO: {_clean_text_for_pdf(periodo_label).upper()}   |   DATA REFERTO: {datetime.date.today().strftime('%d/%m/%Y')}", sub_st)
    ]
    if os.path.exists(LOGO_PATH):
        logo_img = RLImage(LOGO_PATH, width=42, height=42)
        t_head = Table([[header_title, logo_img]], colWidths=[485, 60])
        t_head.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('ALIGN', (1, 0), (1, 0), 'RIGHT')]))
        elements.append(t_head)
    else:
        elements.extend(header_title)

    elements.append(Spacer(1, 8))

    # 2. KPI Summary Bar
    tot_srpe = kpis.get('tot_srpe', 0)
    tot_tl = kpis.get('tot_tl_gps', 0)
    eff_ratio = kpis.get('eff_ratio', 0)
    avg_well = kpis.get('avg_wellness', 0)

    eff_str = f"{eff_ratio:.2f}" if eff_ratio > 0 else "N/D"

    kpi_cells = [
        [Paragraph("CARICO SOGGETTIVO sRPE", kpi_lbl), Paragraph("CARICO ESTERNO (GPS)", kpi_lbl), Paragraph("INDICE EFFICIENZA (TL/sRPE)", kpi_lbl), Paragraph("WELLNESS MEDIO", kpi_lbl)],
        [
            Paragraph(f"<font color='#0284c7'>{tot_srpe:,.0f} AU</font>", kpi_val),
            Paragraph(f"<font color='#10b981'>{tot_tl:,.0f} TL</font>", kpi_val),
            Paragraph(f"<font color='#f59e0b'>{eff_str}</font>", kpi_val),
            Paragraph(f"<font color='#8b5cf6'>{avg_well} / 10</font>", kpi_val)
        ]
    ]
    t_kpi = Table(kpi_cells, colWidths=[136, 136, 136, 137])
    t_kpi.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
        ('BOX', (0, 0), (-1, -1), 0.75, colors.HexColor('#cbd5e1')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(t_kpi)

    elements.append(Spacer(1, 8))

    # 3. Tabella sRPE Sessioni
    elements.append(Paragraph("REGISTRO SESSIONI & CARICO SOGGETTIVO sRPE (SESSION RPE)", sec_title))
    if df_srpe is not None and not df_srpe.empty:
        srpe_headers = [
            Paragraph("DATA", th_st),
            Paragraph("SESSIONE", th_st),
            Paragraph("TIPOLOGIA", th_st),
            Paragraph("DURATA (MIN)", th_st),
            Paragraph("RPE (1-10)", th_st),
            Paragraph("CARICO sRPE", th_st),
        ]
        srpe_rows = [srpe_headers]
        for _, r in df_srpe.iterrows():
            d_s = str(r.get('data', ''))
            nm_s = str(r.get('nome_sessione', ''))
            tp_s = str(r.get('tipologia', 'Allenamento'))
            dur_s = f"{float(r.get('durata_minuti', 0)):.0f}"
            rpe_s = f"{r.get('rpe', '-')}"
            load_s = f"{float(r.get('carico_srpe', 0)):.0f}"
            srpe_rows.append([
                Paragraph(d_s, td_st),
                Paragraph(nm_s, td_st),
                Paragraph(tp_s, td_st),
                Paragraph(dur_s, td_st),
                Paragraph(rpe_s, td_bold),
                Paragraph(load_s, td_bold),
            ])
        t_srpe = Table(srpe_rows, colWidths=[75, 150, 110, 70, 65, 75])
        t_srpe.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0284c7')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        elements.append(t_srpe)
    else:
        elements.append(Paragraph("<i>Nessuna sessione sRPE registrata nel periodo selezionato.</i>", td_st))

    elements.append(Spacer(1, 8))

    # 4. Tabella Wellness Mattutino
    elements.append(Paragraph("QUESTIONARIO WELLNESS MATTUTINO (FATICA, SONNO, DOMS, STRESS, UMORE)", sec_title))
    if df_wellness is not None and not df_wellness.empty:
        well_headers = [
            Paragraph("DATA", th_st),
            Paragraph("SONNO", th_st),
            Paragraph("FATICA", th_st),
            Paragraph("DOMS", th_st),
            Paragraph("STRESS", th_st),
            Paragraph("UMORE", th_st),
            Paragraph("TOTALE", th_st),
        ]
        well_rows = [well_headers]
        for _, rw in df_wellness.iterrows():
            d_w = str(rw.get('data', ''))
            s_sl = f"{rw.get('sonno', '-')}"
            s_fat = f"{rw.get('fatica', '-')}"
            s_dom = f"{rw.get('dolori_muscolari', rw.get('doms', '-'))}"
            s_str = f"{rw.get('stress', '-')}"
            s_um = f"{rw.get('umore', '-')}"
            s_tot = f"{rw.get('score_totale', rw.get('totale', '-'))}"
            well_rows.append([
                Paragraph(d_w, td_st),
                Paragraph(s_sl, td_st),
                Paragraph(s_fat, td_st),
                Paragraph(s_dom, td_st),
                Paragraph(s_str, td_st),
                Paragraph(s_um, td_st),
                Paragraph(s_tot, td_bold),
            ])
        t_well = Table(well_rows, colWidths=[85, 75, 75, 75, 75, 75, 85])
        t_well.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#8b5cf6')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        elements.append(t_well)
    else:
        elements.append(Paragraph("<i>Nessuna rilevazione Wellness mattutina nel periodo selezionato.</i>", td_st))

    # Sezione Note Metodologiche & Bibliografia Validata
    elements.extend(genera_sezione_metodologia_pdf("carico_interno", styles, width=545))

    build_pdf_con_footer(doc, elements, is_landscape=False)
    return buffer.getvalue()


# =========================================================================
# 11. MOTORE PDF: REPORT STATISTICHE MATCH SINGOLI & TELEMETRIA FISICA
# =========================================================================
def crea_pdf_statistiche_match(atleta_nome, df_corr, df_f, df_matches=None, kpis=None):
    """
    Genera il Referto Esecutivo PDF Ufficiale M0V3 per Statistiche Match Singoli e Telemetria Fisica GPS/IMU.
    Riproduce fedelmente tutti i grafici, tabelle e spiegazioni scientifiche del portale
    senza tagli a meta' tra le pagine, con layout orizzontale (A4 Landscape) strutturato in 4 pagine tematiche.
    """
    import io
    import numpy as np
    import pandas as pd
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=25,
        rightMargin=25,
        topMargin=20,
        bottomMargin=24
    )
    elements = []
    styles = getSampleStyleSheet()

    page_w = 792

    title_st = ParagraphStyle('SmTitle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=13, textColor=colors.HexColor('#0f172a'), leading=16)
    sub_st = ParagraphStyle('SmSub', parent=styles['Normal'], fontName='Helvetica', fontSize=7.5, textColor=colors.HexColor('#64748b'), leading=10)
    sec_title = ParagraphStyle('SmSec', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=9.5, textColor=colors.HexColor('#0284c7'), leading=12, spaceBefore=4, spaceAfter=4)
    th_st = ParagraphStyle('SmTH', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=7.2, textColor=colors.HexColor('#ffffff'), alignment=1)
    th_left = ParagraphStyle('SmTHL', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=7.2, textColor=colors.HexColor('#ffffff'), alignment=0)
    td_st = ParagraphStyle('SmTD', parent=styles['Normal'], fontName='Helvetica', fontSize=7.0, textColor=colors.HexColor('#0f172a'), alignment=1)
    td_left = ParagraphStyle('SmTDL', parent=styles['Normal'], fontName='Helvetica', fontSize=7.0, textColor=colors.HexColor('#0f172a'), alignment=0)
    td_bold = ParagraphStyle('SmTDBold', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=7.0, textColor=colors.HexColor('#0f172a'), alignment=1)
    kpi_lbl = ParagraphStyle('SmKPILbl', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=6.8, textColor=colors.HexColor('#64748b'), alignment=1)
    kpi_val = ParagraphStyle('SmKPIVal', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=10.5, textColor=colors.HexColor('#0f172a'), alignment=1)

    tot_m = len(df_f) if df_f is not None else len(df_corr)
    vittorie = len(df_f[df_f["result"] == "Vittoria"]) if df_f is not None and not df_f.empty else len(df_corr[df_corr['result'] == 'Vittoria'])
    sconfitte = len(df_f[df_f["result"] == "Sconfitta"]) if df_f is not None and not df_f.empty else len(df_corr[df_corr['result'] == 'Sconfitta'])
    win_rate = (vittorie / tot_m * 100) if tot_m > 0 else 0.0

    tot_dur_min = df_f["duration_min"].sum() if df_f is not None and not df_f.empty else df_corr['min'].sum()
    avg_dur_min = (tot_dur_min / tot_m) if tot_m > 0 else 0
    h_avg, m_avg = divmod(int(avg_dur_min), 60)
    dur_avg_str = f"{h_avg}h {m_avg:02d}m" if h_avg > 0 else f"{m_avg}m"

    tot_aces = int(df_f["aces"].sum()) if df_f is not None and 'aces' in df_f.columns else (int(df_corr['aces'].sum()) if 'aces' in df_corr.columns else 0)
    avg_aces = (tot_aces / tot_m) if tot_m > 0 else 0.0
    linked_gps_count = len(df_corr)
    pct_gps_linked = (linked_gps_count / tot_m * 100) if tot_m > 0 else 0.0

    # =========================================================================
    # PAGINA 1: TESTATA + KPI DI SINTESI + SEZIONE 1 (COSTO FISICO DEL PUNTO)
    # =========================================================================
    p1_elements = []

    # 1. Header Istituzionale
    header_title = [
        Paragraph("M0V3 ANALYTICS — REPORT STATISTICHE MATCH SINGOLI & TELEMETRIA FISICA", title_st),
        Paragraph(f"ATLETA: {atleta_nome.upper()}   |   DATABASE: {tot_m} MATCH SINGOLI ({linked_gps_count} TELEMETRIE GPS REALI ABBINATE)   |   DATA REFERTO: {datetime.date.today().strftime('%d/%m/%Y')}", sub_st)
    ]
    if os.path.exists(LOGO_PATH):
        logo_img = RLImage(LOGO_PATH, width=38, height=38)
        t_head = Table([[header_title, logo_img]], colWidths=[730, 62])
        t_head.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('ALIGN', (1, 0), (1, 0), 'RIGHT')]))
        p1_elements.append(t_head)
    else:
        p1_elements.extend(header_title)

    p1_elements.append(Spacer(1, 4))

    # 2. KPI Summary Bar (4 blocchi)
    kpi_cells = [
        [Paragraph("WIN RATE MATCH SINGOLI", kpi_lbl), Paragraph("DURATA MEDIA PARTITA", kpi_lbl), Paragraph("ACE TOTALI & MEDIA", kpi_lbl), Paragraph("TELEMETRIA FISICA REALE", kpi_lbl)],
        [
            Paragraph(f"<font color='#16a34a'>{win_rate:.1f}%</font> ({vittorie}W - {sconfitte}L)", kpi_val),
            Paragraph(f"<font color='#0284c7'>{dur_avg_str}</font>", kpi_val),
            Paragraph(f"<font color='#f59e0b'>{tot_aces}</font> ({avg_aces:.1f} / match)", kpi_val),
            Paragraph(f"<font color='#8b5cf6'>{linked_gps_count} / {tot_m}</font> ({pct_gps_linked:.0f}% reali)", kpi_val)
        ]
    ]
    t_kpi = Table(kpi_cells, colWidths=[198, 198, 198, 198])
    t_kpi.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
        ('BOX', (0, 0), (-1, -1), 0.75, colors.HexColor('#cbd5e1')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    p1_elements.append(t_kpi)
    p1_elements.append(Spacer(1, 6))

    # 3. Sezione 1: Costo Fisico del Punto nei Match Singoli (senza metri/punto)
    p1_elements.append(Paragraph("1. COSTO FISICO DEL PUNTO NEI MATCH SINGOLI (WORK RATE & INTENSITÀ METABOLICA)", sec_title))

    tl_high_min_avg = df_corr['tl_high_per_min'].mean() if 'tl_high_per_min' in df_corr.columns else 0.0
    tl_high_pt_avg = df_corr['tl_high_per_point'].mean() if 'tl_high_per_point' in df_corr.columns else 0.0
    acc_dec_pt_avg = df_corr['acc_dec_per_point'].mean() if 'acc_dec_per_point' in df_corr.columns else 0.0
    imu_actions_avg = df_corr['imu_actions_per_10pt'].mean() if 'imu_actions_per_10pt' in df_corr.columns else 0.0

    kpi_pt_cells = [
        [Paragraph("TL HIGH AL MINUTO", kpi_lbl), Paragraph("COSTO FISICO VIVO (TL HIGH / PT)", kpi_lbl), Paragraph("ACC + DEC IMU PER PUNTO", kpi_lbl), Paragraph("DENSITÀ SCAMBI IMU >2\"", kpi_lbl)],
        [
            Paragraph(f"<font color='#0284c7'>{tl_high_min_avg:.1f} AU/min</font>", kpi_val),
            Paragraph(f"<font color='#ef4444'>{tl_high_pt_avg:.2f} AU/pt</font>", kpi_val),
            Paragraph(f"<font color='#ea580c'>{acc_dec_pt_avg:.2f} ev/pt</font>", kpi_val),
            Paragraph(f"<font color='#8b5cf6'>{imu_actions_avg:.1f} / 10pt</font>", kpi_val)
        ]
    ]
    t_pt_kpi = Table(kpi_pt_cells, colWidths=[198, 198, 198, 198])
    t_pt_kpi.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#ffffff')),
        ('BOX', (0, 0), (-1, -1), 0.75, colors.HexColor('#cbd5e1')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#f1f5f9')),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    p1_elements.append(t_pt_kpi)
    p1_elements.append(Spacer(1, 5))

    # Grafico 1: Cronologico Costo Vivo TL High / pt per ciascun match singolo
    bar_labels = []
    bar_colors = []
    for _, r in df_corr.iterrows():
        r_dt = str(r.get('date', '')).strip()
        opp_str = str(r.get('opponent', 'Opp')).strip()
        bar_labels.append(f"{r_dt} vs {opp_str[:10]}")
        bar_colors.append('#10b981' if r.get('result') == 'Vittoria' else '#ef4444')

    fig_pt = go.Figure()
    fig_pt.add_trace(go.Bar(
        x=bar_labels,
        y=df_corr['tl_high_per_point'],
        marker=dict(color=bar_colors),
        name="Costo Vivo TL High / pt"
    ))
    # Rolling trend (3 matches)
    roll_trend = df_corr['tl_high_per_point'].rolling(window=3, min_periods=1).mean()
    fig_pt.add_trace(go.Scatter(
        x=bar_labels,
        y=roll_trend,
        mode='lines',
        line=dict(color='#0284c7', width=2),
        name="Media Mobile (3 Match)"
    ))
    fig_pt.add_hline(
        y=tl_high_pt_avg,
        line_dash="dash",
        line_color="#64748b",
        annotation_text=f"Media: {tl_high_pt_avg:.2f} AU/pt",
        annotation_position="top left",
        annotation_font=dict(size=9, color="#475569")
    )
    fig_pt.update_layout(
        title=dict(text="<b>Costo Fisico Vivo (TL High / pt) per ciascun Match Singolo Ufficiale (Cronologico)</b>", font=dict(size=10.5, family="Inter")),
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
        height=260,
        margin=dict(l=35, r=15, t=30, b=55),
        xaxis=dict(showgrid=False, tickangle=-45, tickfont=dict(size=7.5)),
        yaxis=dict(showgrid=True, gridcolor="#f1f5f9", title="AU/pt", tickfont=dict(size=8)),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=8))
    )
    img_chart1 = fig_to_rl_image(fig_pt, width=785, height=215)
    p1_elements.append(img_chart1)

    elements.append(KeepTogether(p1_elements))
    elements.append(PageBreak())

    # =========================================================================
    # PAGINA 2: BENCHMARK PRESTATIVO (3 WORK RATE + 4 VOLUME) + EFFICIENZA SERVIZIO
    # =========================================================================
    p2_elements = []
    p2_elements.append(Paragraph("2. BENCHMARK PRESTATIVO: VITTORIE VS SCONFITTE (MATCH SINGOLI)", sec_title))

    m_win = df_corr[df_corr['result'] == 'Vittoria']
    m_loss = df_corr[df_corr['result'] == 'Sconfitta']

    if not m_win.empty and not m_loss.empty:
        # 3 Work Rate
        w_tlh_min = m_win['tl_high_per_min'].mean() if 'tl_high_per_min' in m_win.columns else 0.0
        l_tlh_min = m_loss['tl_high_per_min'].mean() if 'tl_high_per_min' in m_loss.columns else 0.0
        delta_tlh_min = ((w_tlh_min - l_tlh_min) / l_tlh_min * 100) if l_tlh_min > 0 else 0.0

        w_tlh_pt = m_win['tl_high_per_point'].mean() if 'tl_high_per_point' in m_win.columns else 0.0
        l_tlh_pt = m_loss['tl_high_per_point'].mean() if 'tl_high_per_point' in m_loss.columns else 0.0
        delta_tlh_pt = ((w_tlh_pt - l_tlh_pt) / l_tlh_pt * 100) if l_tlh_pt > 0 else 0.0

        w_accdec_pt = m_win['acc_dec_per_point'].mean() if 'acc_dec_per_point' in m_win.columns else 0.0
        l_accdec_pt = m_loss['acc_dec_per_point'].mean() if 'acc_dec_per_point' in m_loss.columns else 0.0
        delta_accdec_pt = ((w_accdec_pt - l_accdec_pt) / l_accdec_pt * 100) if l_accdec_pt > 0 else 0.0

        # 4 Volume
        w_pts = m_win['total_points'].mean() if 'total_points' in m_win.columns else 0.0
        l_pts = m_loss['total_points'].mean() if 'total_points' in m_loss.columns else 0.0
        delta_pts = ((w_pts - l_pts) / l_pts * 100) if l_pts > 0 else 0.0

        w_tl = m_win['tl'].mean() if 'tl' in m_win.columns else 0.0
        l_tl = m_loss['tl'].mean() if 'tl' in m_loss.columns else 0.0
        delta_tl = ((w_tl - l_tl) / l_tl * 100) if l_tl > 0 else 0.0

        w_act_imu = m_win['actions_imu_2s'].mean() if 'actions_imu_2s' in m_win.columns else 0.0
        l_act_imu = m_loss['actions_imu_2s'].mean() if 'actions_imu_2s' in m_loss.columns else 0.0
        delta_act_imu = ((w_act_imu - l_act_imu) / l_act_imu * 100) if l_act_imu > 0 else 0.0

        w_tl_high = m_win['tl_high'].mean() if 'tl_high' in m_win.columns else 0.0
        l_tl_high = m_loss['tl_high'].mean() if 'tl_high' in m_loss.columns else 0.0
        delta_tl_high = ((w_tl_high - l_tl_high) / l_tl_high * 100) if l_tl_high > 0 else 0.0

        # Tabella Fedele a 7 metriche
        bench_hdr = [
            Paragraph("METRICA FISICA REALE", th_left),
            Paragraph(f"VITTORIE ({len(m_win)})", th_st),
            Paragraph(f"SCONFITTE ({len(m_loss)})", th_st),
            Paragraph("DELTA %", th_st)
        ]
        cat_wr_hdr = [Paragraph("<b>⚡ 3 VALORI DI WORK RATE (INTENSITÀ REALE)</b>", ParagraphStyle('WRH', parent=th_left, fontName='Helvetica-Bold', fontSize=6.8, textColor=colors.HexColor('#0369a1'))), "", "", ""]
        cat_vol_hdr = [Paragraph("<b>📊 4 VALORI DI VOLUME (CARICO TOTALE MATCH)</b>", ParagraphStyle('VOLH', parent=th_left, fontName='Helvetica-Bold', fontSize=6.8, textColor=colors.HexColor('#7c3aed'))), "", "", ""]

        def _fmt_delta(d_val):
            c_hex = '#16a34a' if d_val > 0 else ('#dc2626' if d_val < 0 else '#64748b')
            return Paragraph(f"<font color='{c_hex}'><b>{d_val:+.1f}%</b></font>", td_st)

        bench_table_rows = [
            bench_hdr,
            cat_wr_hdr,
            [Paragraph("Training Load High al Minuto", td_left), Paragraph(f"{w_tlh_min:.1f} AU/min", td_bold), Paragraph(f"{l_tlh_min:.1f} AU/min", td_st), _fmt_delta(delta_tlh_min)],
            [Paragraph("Training Load High per Punto", td_left), Paragraph(f"{w_tlh_pt:.2f} AU/pt", td_bold), Paragraph(f"{l_tlh_pt:.2f} AU/pt", td_st), _fmt_delta(delta_tlh_pt)],
            [Paragraph("Acc + Dec IMU per Punto", td_left), Paragraph(f"{w_accdec_pt:.2f} ev/pt", td_bold), Paragraph(f"{l_accdec_pt:.2f} ev/pt", td_st), _fmt_delta(delta_accdec_pt)],
            cat_vol_hdr,
            [Paragraph("Punti Totali nel Match", td_left), Paragraph(f"{w_pts:.0f} pts", td_bold), Paragraph(f"{l_pts:.0f} pts", td_st), _fmt_delta(delta_pts)],
            [Paragraph("Training Load nel Match", td_left), Paragraph(f"{w_tl:.0f} TL", td_bold), Paragraph(f"{l_tl:.0f} TL", td_st), _fmt_delta(delta_tl)],
            [Paragraph("Azioni Intense >2\" nel Match", td_left), Paragraph(f"{w_act_imu:.0f} az", td_bold), Paragraph(f"{l_act_imu:.0f} az", td_st), _fmt_delta(delta_act_imu)],
            [Paragraph("Training Load High nel Match", td_left), Paragraph(f"{w_tl_high:.0f} TL", td_bold), Paragraph(f"{l_tl_high:.0f} TL", td_st), _fmt_delta(delta_tl_high)]
        ]
        t_bench = Table(bench_table_rows, colWidths=[185, 75, 75, 65])
        t_bench.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f172a')),
            ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#e0f2fe')),
            ('SPAN', (0, 1), (-1, 1)),
            ('BACKGROUND', (0, 5), (-1, 5), colors.HexColor('#f3e8ff')),
            ('SPAN', (0, 5), (-1, 5)),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
            ('ROWBACKGROUNDS', (0, 2), (-1, 4), [colors.white, colors.HexColor('#f8fafc')]),
            ('ROWBACKGROUNDS', (0, 6), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))

        # Subplots Chart Fedele: Work Rate (Row 1) & Volume (Row 2)
        fig_bench_pdf = make_subplots(
            rows=2, cols=1,
            shared_xaxes=False,
            vertical_spacing=0.28,
            subplot_titles=[
                "<b>Work Rate: Intensita' Reale (AU/min, AU/pt, ev/pt)</b>",
                "<b>Volume: Carico Totale nel Match (pts, TL, azioni, TL High)</b>"
            ]
        )
        cat_wr = ['TL High / min', 'TL High / pt', 'Acc+Dec / pt']
        v_win_wr = [w_tlh_min, w_tlh_pt, w_accdec_pt]
        v_loss_wr = [l_tlh_min, l_tlh_pt, l_accdec_pt]

        fig_bench_pdf.add_trace(go.Bar(name='Vittorie', x=cat_wr, y=v_win_wr, marker_color='#16a34a', text=[f"{v:.2f}" for v in v_win_wr], textposition='auto'), row=1, col=1)
        fig_bench_pdf.add_trace(go.Bar(name='Sconfitte', x=cat_wr, y=v_loss_wr, marker_color='#dc2626', text=[f"{v:.2f}" for v in v_loss_wr], textposition='auto'), row=1, col=1)

        cat_vol = ['Punti Tot', 'Training Load', 'Azioni IMU >2"', 'TL High Match']
        v_win_vol = [w_pts, w_tl, w_act_imu, w_tl_high]
        v_loss_vol = [l_pts, l_tl, l_act_imu, l_tl_high]

        fig_bench_pdf.add_trace(go.Bar(name='Vittorie', x=cat_vol, y=v_win_vol, marker_color='#16a34a', text=[f"{v:.0f}" for v in v_win_vol], textposition='auto', showlegend=False), row=2, col=1)
        fig_bench_pdf.add_trace(go.Bar(name='Sconfitte', x=cat_vol, y=v_loss_vol, marker_color='#dc2626', text=[f"{v:.0f}" for v in v_loss_vol], textposition='auto', showlegend=False), row=2, col=1)

        fig_bench_pdf.update_layout(
            barmode='group',
            plot_bgcolor="#ffffff",
            paper_bgcolor="#ffffff",
            height=280,
            margin=dict(l=25, r=15, t=35, b=25),
            legend=dict(orientation="h", yanchor="bottom", y=1.04, xanchor="right", x=1, font=dict(size=7.5))
        )
        for i in [1, 2]:
            fig_bench_pdf.update_xaxes(tickfont=dict(size=7.5), row=i, col=1)
            fig_bench_pdf.update_yaxes(showgrid=True, gridcolor="#f1f5f9", tickfont=dict(size=7.5), row=i, col=1)

        img_bench = fig_to_rl_image(fig_bench_pdf, width=375, height=230)

        # Affianca tabella e grafico
        t_row_bench = Table([[t_bench, img_bench]], colWidths=[405, 380])
        t_row_bench.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP')]))
        p2_elements.append(t_row_bench)
        p2_elements.append(Spacer(1, 5))

        # Box Evidenza Prestativa
        evid_txt = (
            f"<b>Evidenza Prestativa Reale:</b> Nelle partite vinte Flavio esprime un Training Load High al Minuto di "
            f"<b>{w_tlh_min:.1f} AU/min</b> ({delta_tlh_min:+.1f}% rispetto alle sconfitte) e un Training Load High per Punto di "
            f"<b>{w_tlh_pt:.2f} AU/pt</b> ({delta_tlh_pt:+.1f}%), sostenendo un Training Load complessivo superiore del <b>{delta_tl:+.1f}%</b>."
        )
        t_evid = Table([[Paragraph(evid_txt, ParagraphStyle('EvidSt', parent=styles['Normal'], fontName='Helvetica', fontSize=7.2, leading=9.5, textColor=colors.HexColor('#1e293b')))]], colWidths=[785])
        t_evid.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f0fdf4')),
            ('BOX', (0, 0), (-1, -1), 0.75, colors.HexColor('#86efac')),
            ('LINELEFT', (0, 0), (0, -1), 3.5, colors.HexColor('#16a34a')),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 7),
            ('RIGHTPADDING', (0, 0), (-1, -1), 7),
        ]))
        p2_elements.append(t_evid)
        p2_elements.append(Spacer(1, 5))

    # Sezione 5: Efficienza del Servizio vs Risparmio Fisico
    p2_elements.append(Paragraph("5. EFFICIENZA DEL SERVIZIO VS RISPARMIO FISICO (MATCH SINGOLI)", sec_title))
    hi_ace = df_corr[df_corr['aces'] >= 6] if 'aces' in df_corr.columns else pd.DataFrame()
    lo_ace = df_corr[df_corr['aces'] < 6] if 'aces' in df_corr.columns else pd.DataFrame()
    tlh_hi = hi_ace['tl_high_per_point'].mean() if not hi_ace.empty else 0.0
    tlh_lo = lo_ace['tl_high_per_point'].mean() if not lo_ace.empty else 0.0
    wr_hi = (hi_ace['result'] == 'Vittoria').mean() * 100.0 if not hi_ace.empty else 0.0
    wr_lo = (lo_ace['result'] == 'Vittoria').mean() * 100.0 if not lo_ace.empty else 0.0

    srv_txt = (
        f"<b>Impatto Ace &amp; Battuta:</b> Nelle partite con <b>&ge;6 Ace</b> il Costo Fisico Vivo per Punto e' di <b>{tlh_hi:.2f} AU/pt</b> (Win Rate: {wr_hi:.1f}%), "
        f"mentre con <b>&lt;6 Ace</b> sale a <b>{tlh_lo:.2f} AU/pt</b> (Win Rate: {wr_lo:.1f}%). Il servizio dominante consente di abbreviare gli scambi e preservare "
        f"l'integrita' muscolare eccentrica per le fasi cruciali del torneo."
    )
    t_srv = Table([[Paragraph(srv_txt, ParagraphStyle('SrvSt', parent=styles['Normal'], fontName='Helvetica', fontSize=7.0, leading=9.0, textColor=colors.HexColor('#334155')))]], colWidths=[785])
    t_srv.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('LINELEFT', (0, 0), (0, -1), 3.0, colors.HexColor('#f59e0b')),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))
    p2_elements.append(t_srv)

    elements.append(KeepTogether(p2_elements))
    elements.append(PageBreak())

    # =========================================================================
    # PAGINA 3: IMPATTO DELLA SUPERFICIE & DIFFICOLTA' AVVERSARIO (RANKING TIER)
    # =========================================================================
    p3_elements = []

    # Sezione 3: Impatto della Superficie basato su Training Load
    p3_elements.append(Paragraph("3. IMPATTO DELLA SUPERFICIE: TERRA VS CEMENTO VS ERBA (ANALISI BASATA SU TRAINING LOAD)", sec_title))

    surf_agg = df_corr.groupby('surface').agg(
        n_match=('match_id', 'count'),
        tl_avg=('tl', 'mean'),
        tl_high_avg=('tl_high', 'mean'),
        tl_high_pct=('pct_tl_high', 'mean'),
        tl_high_min=('tl_high_per_min', 'mean'),
        tl_high_pt=('tl_high_per_point', 'mean'),
        dec_avg=('dec', 'mean'),
        dur_avg=('duration_min', 'mean')
    ).reset_index()

    surf_rows = [
        [
            Paragraph("SUPERFICIE", th_left),
            Paragraph("MATCH", th_st),
            Paragraph("TRAINING LOAD MEDIO", th_st),
            Paragraph("TL HIGH MEDIO", th_st),
            Paragraph("TL HIGH / MIN", th_st),
            Paragraph("TL HIGH / PT", th_st),
            Paragraph("FRENATE HIGH IMU", th_st),
            Paragraph("DURATA MEDIA", th_st)
        ]
    ]
    for _, sr in surf_agg.iterrows():
        s_name = str(sr['surface'])
        surf_rows.append([
            Paragraph(f"<b>{s_name.upper()}</b>", td_left),
            Paragraph(f"{int(sr['n_match'])}", td_st),
            Paragraph(f"{sr['tl_avg']:.0f} TL", td_bold),
            Paragraph(f"{sr['tl_high_avg']:.0f} TL ({sr['tl_high_pct']:.1f}%)", td_st),
            Paragraph(f"{sr['tl_high_min']:.1f} AU/min", td_st),
            Paragraph(f"{sr['tl_high_pt']:.2f} AU/pt", td_st),
            Paragraph(f"{sr['dec_avg']:.0f} / match", td_st),
            Paragraph(f"{sr['dur_avg']:.0f} min", td_st),
        ])
    t_surf = Table(surf_rows, colWidths=[95, 55, 115, 120, 95, 95, 110, 97])
    t_surf.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#ea580c')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    p3_elements.append(t_surf)
    p3_elements.append(Spacer(1, 6))

    # Sezione 4: Difficolta' Avversario (Ranking Tier) & Top 5 Match Logoramento
    p3_elements.append(Paragraph("4. DIFFICOLTÀ AVVERSARIO (RANKING TIER) & TOP 5 MATCH A MASSIMO LOGORAMENTO", sec_title))

    def _assign_rank_tier_pdf(r):
        if pd.isna(r) or r <= 0: return "Oltre 100"
        if r <= 10: return "Top 10"
        if r <= 20: return "Top 20"
        if r <= 50: return "Top 50"
        if r <= 100: return "Top 100"
        return "Oltre 100"

    df_corr['rank_tier'] = df_corr['opponent_rank'].apply(_assign_rank_tier_pdf)
    tier_order = ['Top 10', 'Top 20', 'Top 50', 'Top 100', 'Oltre 100']
    tier_data = []
    for t_name in tier_order:
        df_t = df_corr[df_corr['rank_tier'] == t_name]
        n_t = len(df_t)
        if n_t > 0:
            w_rate = (df_t['result'] == 'Vittoria').mean() * 100.0
            tl_m = df_t['tl'].mean()
            tlh_m = df_t['tl_high'].mean()
            tier_data.append({'tier': t_name, 'count': n_t, 'win_rate': w_rate, 'tl_mean': tl_m, 'tlh_mean': tlh_m})

    # Grafico a Barre Ranking Tier Esplicativo
    if tier_data:
        df_td = pd.DataFrame(tier_data)
        fig_tier_pdf = go.Figure()
        fig_tier_pdf.add_trace(go.Bar(
            x=df_td['tier'],
            y=df_td['tl_mean'],
            marker=dict(color=['#8b5cf6', '#3b82f6', '#0ea5e9', '#10b981', '#64748b'][:len(df_td)]),
            text=[f"<b>{tl:.0f} TL</b><br><span style='font-size:8px;'>Win: {wr:.0f}% ({cnt}m)</span>" for tl, wr, cnt in zip(df_td['tl_mean'], df_td['win_rate'], df_td['count'])],
            textposition='auto',
            name="Training Load Medio"
        ))
        fig_tier_pdf.update_layout(
            title=dict(text="<b>Training Load Medio Reale per Fascia di Ranking Avversario (Tier)</b>", font=dict(size=10, family="Inter")),
            plot_bgcolor="#ffffff",
            paper_bgcolor="#ffffff",
            height=200,
            margin=dict(l=30, r=15, t=30, b=25),
            xaxis=dict(showgrid=False, tickfont=dict(size=8)),
            yaxis=dict(showgrid=True, gridcolor="#f1f5f9", title="TL", tickfont=dict(size=7.5))
        )
        img_tier = fig_to_rl_image(fig_tier_pdf, width=380, height=185)
    else:
        img_tier = Paragraph("<i>Dati di Ranking Tier non disponibili</i>", td_st)

    # Tabella Top 5 Match a Massimo Logoramento Meccanico
    top5_df = df_corr.sort_values(by='tl', ascending=False).head(5)
    top5_rows = [
        [
            Paragraph("TORNEO &amp; AVVERSARIO", th_left),
            Paragraph("SUP", th_st),
            Paragraph("PUNTI", th_st),
            Paragraph("TL HIGH", th_st),
            Paragraph("TL TOT", th_st),
            Paragraph("ESITO", th_st)
        ]
    ]
    for _, s_r in top5_df.iterrows():
        res_col = '#16a34a' if s_r['result'] == 'Vittoria' else '#dc2626'
        opp_lbl = f"{s_r['tournament']} · vs {s_r['opponent']}"
        top5_rows.append([
            Paragraph(f"<b>{opp_lbl[:30]}</b>", td_left),
            Paragraph(f"{str(s_r['surface'])[:4]}", td_st),
            Paragraph(f"{int(s_r['total_points'])}", td_st),
            Paragraph(f"{s_r['tl_high']:.0f} AU", td_st),
            Paragraph(f"<b>{s_r['tl']:.0f} TL</b>", td_bold),
            Paragraph(f"<font color='{res_col}'><b>{s_r['result'][:3].upper()}</b></font>", td_st)
        ])
    t_top5 = Table(top5_rows, colWidths=[150, 40, 45, 55, 55, 45])
    t_top5.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#8b5cf6')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))

    t_rk_row = Table([[img_tier, t_top5]], colWidths=[395, 390])
    t_rk_row.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP')]))
    p3_elements.append(t_rk_row)

    elements.append(KeepTogether(p3_elements))
    elements.append(PageBreak())

    # =========================================================================
    # PAGINA 4: TRASPARENZA SCIENTIFICA, FORMULE & BIBLIOGRAFIA INTERNAZIONALE
    # =========================================================================
    p4_elements = []
    p4_elements.append(Paragraph("METODOLOGIA VALIDATA &amp; TRASPARENZA SCIENTIFICA M0V3 ANALYTICS", sec_title))
    p4_elements.extend(genera_sezione_metodologia_pdf("match_per_point", styles, width=785))

    elements.append(KeepTogether(p4_elements))

    build_pdf_con_footer(doc, elements, brand="M0V3 Analytics — Match Intelligence", is_landscape=True)
    return buffer.getvalue()




