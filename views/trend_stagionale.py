import os
import datetime
from datetime import timedelta
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config import (
    CATALOGO_REPORT,
    render_page_header,
    render_action_bar,
    render_tab_navigation,
    tr,
)
from utils import (
    supabase,
    load_local_database,
    get_atleti_associati,
    CANONICAL_TIPOLOGIE_SESSIONE,
    get_tipologie_sessione,
    render_executive_chart_header,
    card_kpi,
    acwr_pre_match,
    stato_acwr,
    slugify_name,
    render_athlete_hero_strip,
)
import importlib
import pdf_generator
if not hasattr(pdf_generator, 'crea_pdf_stagionale_m0v3'):
    importlib.reload(pdf_generator)
from pdf_generator import crea_pdf_stagionale_m0v3

def format_minutes_hhmm(minutes_val):
    """Formatta minuti float in HH:MM:00 o HH:MM."""
    if pd.isna(minutes_val) or minutes_val <= 0:
        return "00:00:00"
    tot_sec = int(round(minutes_val * 60))
    hours = tot_sec // 3600
    mins = (tot_sec % 3600) // 60
    secs = tot_sec % 60
    return f"{hours:02d}:{mins:02d}:{secs:02d}"

def format_minutes_hours_mins(minutes_val):
    """Formatta minuti float in formato Ore e Minuti (es. 34h 44m)."""
    if pd.isna(minutes_val) or minutes_val <= 0:
        return "0h 00m"
    tot_m = int(round(minutes_val))
    h = tot_m // 60
    m = tot_m % 60
    return f"{h}h {m:02d}m"

def render_delta_badge(delta_pct, val_curr):
    """Crea il badge colorato con freccia e percentuale di scostamento."""
    if val_curr == 0:
        return (
            "<span style='background:#fee2e2; color:#991b1b; padding:2px 6px; border-radius:4px; font-size:11px; font-weight:800; display:inline-flex; align-items:center; gap:2px;'>"
            "⬇ 100%"
            "</span>"
        )
    
    if delta_pct > 25:
        bg, fg, arrow = "#dcfce7", "#166534", "⬆"
        sign = "+"
    elif 5 <= delta_pct <= 25:
        bg, fg, arrow = "#fef3c7", "#b45309", "↗"
        sign = "+"
    elif -5 < delta_pct < 5:
        bg, fg, arrow = "#f1f5f9", "#475569", "→"
        sign = "±"
    elif -25 <= delta_pct <= -5:
        bg, fg, arrow = "#fef3c7", "#b45309", "↘"
        sign = ""
    else:
        bg, fg, arrow = "#fee2e2", "#991b1b", "⬇"
        sign = ""
        
    return (
        f"<span style='background:{bg}; color:{fg}; padding:2px 6px; border-radius:4px; font-size:11px; font-weight:800; display:inline-flex; align-items:center; gap:2px;'>"
        f"{arrow} {sign}{delta_pct:.0f}%"
        f"</span>"
    )

def get_bar_color_by_delta(delta_pct, val_curr):
    """Restituisce il colore della barra in base allo scostamento dal Season Average."""
    if val_curr == 0:
        return "#cbd5e1"  # Grigio chiaro per settimana/mese a 0 carico
    if delta_pct > 35:
        return "#ef4444"  # Rosso sovraccarico
    if 10 <= delta_pct <= 35:
        return "#f59e0b"  # Ambra/Arancione elevato
    if -15 <= delta_pct < 10:
        return "#10b981"  # Verde ottimale / in media
    if -35 <= delta_pct < -15:
        return "#0ea5e9"  # Azzurro medio-basso
    return "#38bdf8"      # Scarico


# =============================================================================
# RENDERING BLOCCO METRICA - 8 SETTIMANE
# =============================================================================
def render_metric_row_block(
    metric_vertical_title,
    metric_box_title,
    season_avg_val,
    avg_8w_val,
    weeks_data,
    metric_key,
    is_time=False,
    is_pct=False,
    chart_key="chart"
):
    if is_time:
        str_season_avg = format_minutes_hhmm(season_avg_val)
        str_avg_8w = format_minutes_hhmm(avg_8w_val)
    elif is_pct:
        str_season_avg = f"{season_avg_val:.0f}%"
        str_avg_8w = f"{avg_8w_val:.0f}%"
    else:
        str_season_avg = f"{int(round(season_avg_val)):,}".replace(",", ".")
        str_avg_8w = f"{int(round(avg_8w_val)):,}".replace(",", ".")

    weeks_html = ""
    plot_x_labels = []
    plot_y_values = []
    plot_text_labels = []
    plot_colors = []
    plot_hover_texts = []

    for idx, w in enumerate(weeks_data):
        val = w[metric_key]
        
        if season_avg_val > 0:
            delta = ((val - season_avg_val) / season_avg_val) * 100
        else:
            delta = 0.0 if val == 0 else 100.0

        if is_time:
            str_val = format_minutes_hhmm(val)
            chart_text = format_minutes_hhmm(val)[:5] if val > 0 else "0"
        elif is_pct:
            str_val = f"{val:.0f}%"
            chart_text = f"{val:.0f}%" if val > 0 else "0%"
        else:
            str_val = f"{int(round(val)):,}".replace(",", ".")
            chart_text = f"{int(round(val)):,}".replace(",", ".") if val > 0 else "0"

        badge_html = render_delta_badge(delta, val)
        is_current = (idx == len(weeks_data) - 1)
        col_bg = "#f0f9ff" if is_current else "#ffffff"
        border_col = "#38bdf8" if is_current else "#e2e8f0"

        weeks_html += (
            f'<div style="flex:1; min-width:95px; background:{col_bg}; border-left:1px solid {border_col}; padding:8px 6px; text-align:center; display:flex; flex-direction:column; justify-content:center; align-items:center;">'
            f'<div style="font-size:10px; font-weight:800; color:#64748b; text-transform:uppercase; margin-bottom:2px;">{w["col_label"]}</div>'
            f'<div style="font-size:13.5px; font-weight:900; color:#0f172a; margin-bottom:3px; word-break:keep-all;">{str_val}</div>'
            f'<div>{badge_html}</div>'
            f'</div>'
        )

        plot_x_labels.append(w['col_label'])
        plot_y_values.append(val)
        plot_text_labels.append(chart_text)
        plot_colors.append(get_bar_color_by_delta(delta, val))
        
        hover_info = (
            f"<b>{w['col_label']} ({w['date_range']})</b><br>"
            f"{metric_box_title}: <b>{str_val}</b><br>"
            f"Δ vs Media Stagione: <b>{delta:+.1f}%</b><br>"
            f"Sessioni svolte: <b>{w['num_sessions']}</b>"
        )
        plot_hover_texts.append(hover_info)

    block_html = (
        f'<div style="background:#ffffff; border:1px solid #cbd5e1; border-radius:12px; overflow:hidden; box-shadow:0 4px 12px -2px rgba(15,23,42,0.06); margin-bottom:6px; font-family:\'Inter\', sans-serif;">'
        f'<div style="display:flex; flex-direction:row; align-items:stretch; border-bottom:1px solid #e2e8f0; background:#f8fafc;">'
        f'<div style="width:38px; background:#0f172a; color:#f8fafc; display:flex; align-items:center; justify-content:center; padding:6px 0;">'
        f'<span style="writing-mode:vertical-rl; transform:rotate(180deg); font-size:10.5px; font-weight:900; letter-spacing:0.08em; text-transform:uppercase;">{metric_vertical_title}</span>'
        f'</div>'
        f'<div style="width:170px; background:#ffffff; padding:12px 14px; display:flex; align-items:center; justify-content:center; text-align:center; border-right:2px solid #e2e8f0;">'
        f'<div style="font-size:12.5px; font-weight:900; color:#0f172a; text-transform:uppercase; letter-spacing:0.04em;">{metric_box_title}</div>'
        f'</div>'
        f'<div style="width:160px; background:#ffffff; padding:8px 12px; display:flex; flex-direction:column; align-items:center; justify-content:center; text-align:center; border-right:2px solid #e2e8f0;">'
        f'<div style="font-size:10px; font-weight:800; color:#64748b; text-transform:uppercase; letter-spacing:0.04em; margin-bottom:2px;">Season Average</div>'
        f'<div style="font-size:19px; font-weight:900; color:#0f172a; line-height:1.1;">{str_season_avg}</div>'
        f'<div style="font-size:10.5px; font-weight:700; color:#0284c7; margin-top:3px;">(Media 8 sett: {str_avg_8w})</div>'
        f'</div>'
        f'<div style="flex:1; display:flex; flex-direction:row; overflow-x:auto;">'
        f'{weeks_html}'
        f'</div>'
        f'</div>'
        f'</div>'
    )
    st.html(block_html)

    max_y = max(max(plot_y_values) if plot_y_values else 10, season_avg_val, avg_8w_val) * 1.28
    if max_y <= 0:
        max_y = 10.0

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=plot_x_labels,
        y=plot_y_values,
        marker=dict(
            color=plot_colors,
            line=dict(color='#0f172a', width=1.5),
            opacity=0.92
        ),
        text=plot_text_labels,
        textposition='outside',
        textfont=dict(size=11, color='#0f172a', family='Inter, sans-serif'),
        cliponaxis=False,
        hoverinfo='text',
        hovertext=plot_hover_texts,
        width=0.48
    ))

    if season_avg_val > 0:
        fig.add_hline(
            y=season_avg_val,
            line_dash="dash",
            line_color="#475569",
            line_width=1.5,
            annotation_text=f"Season Avg: {str_season_avg}",
            annotation_position="top left",
            annotation_font=dict(size=10, color="#475569", family='Inter, sans-serif')
        )

    if avg_8w_val > 0 and abs(avg_8w_val - season_avg_val) > 0.01:
        fig.add_hline(
            y=avg_8w_val,
            line_dash="dot",
            line_color="#0284c7",
            line_width=1.5,
            annotation_text=f"Media 8 sett: {str_avg_8w}",
            annotation_position="bottom right",
            annotation_font=dict(size=10, color="#0284c7", family='Inter, sans-serif')
        )

    fig.update_layout(
        height=190,
        margin=dict(l=30, r=20, t=18, b=26),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(248,250,252,0.6)',
        xaxis=dict(
            tickfont=dict(size=11, color='#475569', family='Inter, sans-serif'),
            showgrid=False,
            linecolor='#cbd5e1'
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor='#e2e8f0',
            range=[0, max_y],
            tickfont=dict(size=9.5, color='#64748b'),
            zerolinecolor='#cbd5e1'
        ),
        showlegend=False
    )

    st.plotly_chart(fig, use_container_width=True, key=chart_key, config={'displayModeBar': False})
    st.markdown("<div style='margin-bottom: 22px;'></div>", unsafe_allow_html=True)


# =============================================================================
# RENDERING BLOCCO METRICA - 12 MESI (CARICO TOTALE MENSILE)
# =============================================================================
def render_metric_month_row_block(
    metric_vertical_title,
    metric_box_title,
    season_avg_val,
    n_active_months,
    months_data,
    metric_key,
    is_time=False,
    is_pct=False,
    chart_key="chart_m"
):
    """
    Renderizza il blocco metrica per i 12 mesi dell'anno:
    - Season Average mensile (Opzione A: media sui mesi attivi)
    - 12 colonne mensili (GEN-DIC / JAN-DEC) con valore e badge scostamento +-%, '-' per mesi vuoti
    - Grafico a barre su 12 mesi con linea media stagionale
    """
    if is_time:
        str_season_avg = format_minutes_hours_mins(season_avg_val)
    elif is_pct:
        str_season_avg = f"{season_avg_val:.0f}%"
    else:
        str_season_avg = f"{int(round(season_avg_val)):,}".replace(",", ".")

    months_html = ""
    plot_x_labels = []
    plot_y_values = []
    plot_text_labels = []
    plot_colors = []
    plot_hover_texts = []

    for m in months_data:
        m_lbl = m['col_label']
        has_data = m['num_sessions'] > 0
        val = m[metric_key]

        if has_data:
            if season_avg_val > 0:
                delta = ((val - season_avg_val) / season_avg_val) * 100
            else:
                delta = 0.0 if val == 0 else 100.0

            if is_time:
                str_val = format_minutes_hours_mins(val)
                chart_text = format_minutes_hours_mins(val)
            elif is_pct:
                str_val = f"{val:.0f}%"
                chart_text = f"{val:.0f}%"
            else:
                str_val = f"{int(round(val)):,}".replace(",", ".")
                chart_text = f"{int(round(val)):,}".replace(",", ".")

            badge_html = render_delta_badge(delta, val)
            col_bg = "#ffffff"
            border_col = "#e2e8f0"
            p_color = get_bar_color_by_delta(delta, val)
        else:
            str_val = "<span style='color:#94a3b8; font-weight:700;'>-</span>"
            badge_html = "<span style='color:#cbd5e1; font-size:11px; font-weight:700;'>-</span>"
            col_bg = "#f8fafc"
            border_col = "#e2e8f0"
            chart_text = "0"
            p_color = "#cbd5e1"
            delta = 0.0

        months_html += (
            f'<div style="flex:1; min-width:62px; background:{col_bg}; border-left:1px solid {border_col}; padding:8px 4px; text-align:center; display:flex; flex-direction:column; justify-content:center; align-items:center;">'
            f'<div style="font-size:10px; font-weight:800; color:#64748b; text-transform:uppercase; margin-bottom:2px;">{m_lbl}</div>'
            f'<div style="font-size:12px; font-weight:900; color:#0f172a; margin-bottom:3px; word-break:keep-all;">{str_val}</div>'
            f'<div>{badge_html}</div>'
            f'</div>'
        )

        plot_x_labels.append(m_lbl)
        plot_y_values.append(val if has_data else 0.0)
        plot_text_labels.append(chart_text if has_data else "0")
        plot_colors.append(p_color)
        
        if has_data:
            hover_info = (
                f"<b>{m['full_name']}</b><br>"
                f"{metric_box_title}: <b>{str_val}</b><br>"
                f"Δ vs Media Mensile: <b>{delta:+.1f}%</b><br>"
                f"Sessioni: <b>{m['num_sessions']}</b>"
            )
        else:
            hover_info = f"<b>{m['full_name']}</b>: Nessuna sessione registrata"
        plot_hover_texts.append(hover_info)

    sub_avg_lbl = f"(Media su {n_active_months} mesi attivi)"

    block_html = (
        f'<div style="background:#ffffff; border:1px solid #cbd5e1; border-radius:12px; overflow:hidden; box-shadow:0 4px 12px -2px rgba(15,23,42,0.06); margin-bottom:6px; font-family:\'Inter\', sans-serif;">'
        f'<div style="display:flex; flex-direction:row; align-items:stretch; border-bottom:1px solid #e2e8f0; background:#f8fafc;">'
        f'<div style="width:38px; background:#0f172a; color:#f8fafc; display:flex; align-items:center; justify-content:center; padding:6px 0;">'
        f'<span style="writing-mode:vertical-rl; transform:rotate(180deg); font-size:10.5px; font-weight:900; letter-spacing:0.08em; text-transform:uppercase;">{metric_vertical_title}</span>'
        f'</div>'
        f'<div style="width:165px; background:#ffffff; padding:12px 14px; display:flex; align-items:center; justify-content:center; text-align:center; border-right:2px solid #e2e8f0;">'
        f'<div style="font-size:12px; font-weight:900; color:#0f172a; text-transform:uppercase; letter-spacing:0.04em;">{metric_box_title}</div>'
        f'</div>'
        f'<div style="width:160px; background:#ffffff; padding:8px 12px; display:flex; flex-direction:column; align-items:center; justify-content:center; text-align:center; border-right:2px solid #e2e8f0;">'
        f'<div style="font-size:10px; font-weight:800; color:#64748b; text-transform:uppercase; letter-spacing:0.04em; margin-bottom:2px;">Season Average</div>'
        f'<div style="font-size:18px; font-weight:900; color:#0f172a; line-height:1.1;">{str_season_avg}</div>'
        f'<div style="font-size:10px; font-weight:700; color:#0284c7; margin-top:3px;">{sub_avg_lbl}</div>'
        f'</div>'
        f'<div style="flex:1; display:flex; flex-direction:row; overflow-x:auto;">'
        f'{months_html}'
        f'</div>'
        f'</div>'
        f'</div>'
    )
    st.html(block_html)

    max_y = max(max(plot_y_values) if plot_y_values else 10, season_avg_val) * 1.28
    if max_y <= 0:
        max_y = 10.0

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=plot_x_labels,
        y=plot_y_values,
        marker=dict(
            color=plot_colors,
            line=dict(color='#0f172a', width=1.5),
            opacity=0.92
        ),
        text=plot_text_labels,
        textposition='outside',
        textfont=dict(size=10.5, color='#0f172a', family='Inter, sans-serif'),
        cliponaxis=False,
        hoverinfo='text',
        hovertext=plot_hover_texts,
        width=0.52
    ))

    if season_avg_val > 0:
        fig.add_hline(
            y=season_avg_val,
            line_dash="dash",
            line_color="#475569",
            line_width=1.5,
            annotation_text=f"Media Stagionale: {str_season_avg}",
            annotation_position="top left",
            annotation_font=dict(size=10, color="#475569", family='Inter, sans-serif')
        )

    fig.update_layout(
        height=190,
        margin=dict(l=30, r=20, t=18, b=26),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(248,250,252,0.6)',
        xaxis=dict(
            tickfont=dict(size=11, color='#475569', family='Inter, sans-serif'),
            showgrid=False,
            linecolor='#cbd5e1'
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor='#e2e8f0',
            range=[0, max_y],
            tickfont=dict(size=9.5, color='#64748b'),
            zerolinecolor='#cbd5e1'
        ),
        showlegend=False
    )

    st.plotly_chart(fig, use_container_width=True, key=chart_key, config={'displayModeBar': False})
    st.markdown("<div style='margin-bottom: 22px;'></div>", unsafe_allow_html=True)


# =============================================================================
# RENDERING GRAFICO SPLINE AD AREA - TIMELINE STAGIONALE
# =============================================================================
def render_spline_metric_chart(
    title,
    subtitle,
    x_labels,
    y_values,
    text_labels,
    hover_texts,
    line_color,
    fill_color,
    season_avg_val,
    season_avg_str,
    peak_val_str,
    chart_key,
    y_unit=""
):
    """
    Renderizza un grafico ad Area Spline morbida con gradiente Dark Navy,
    marker evidenziati, etichette numeriche, linea tratteggiata di media e statistiche di sintesi.
    """
    header_html = (
        f'<div style="background:#ffffff; border:1px solid #cbd5e1; border-radius:12px 12px 0 0; padding:12px 18px; margin-top:18px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; font-family:\'Inter\', sans-serif;">'
        f'<div>'
        f'<span style="font-size:13.5px; font-weight:900; color:#0f172a; text-transform:uppercase; letter-spacing:0.04em;">{title}</span>'
        f'<span style="font-size:11.5px; font-weight:600; color:#64748b; margin-left:8px;">{subtitle}</span>'
        f'</div>'
        f'<div style="display:flex; gap:10px; align-items:center;">'
        f'<span style="background:#f1f5f9; color:#334155; font-size:11.5px; font-weight:800; padding:4px 10px; border-radius:6px;">Media: <b style="color:#0f172a;">{season_avg_str}</b></span>'
        f'<span style="background:#fef3c7; color:#b45309; font-size:11.5px; font-weight:800; padding:4px 10px; border-radius:6px;">Picco: <b style="color:#92400e;">{peak_val_str}</b></span>'
        f'</div>'
        f'</div>'
    )
    st.html(header_html)

    max_val = max(y_values) if y_values else 10.0
    max_y = max(max_val, season_avg_val) * 1.25
    if max_y <= 0:
        max_y = 10.0

    fig = go.Figure()

    # Area Spline con gradiente
    fig.add_trace(go.Scatter(
        x=x_labels,
        y=y_values,
        mode='lines+markers+text',
        line=dict(color=line_color, width=3, shape='spline', smoothing=0.65),
        marker=dict(size=7, color=line_color, line=dict(color='#ffffff', width=2)),
        fill='tozeroy',
        fillcolor=fill_color,
        text=text_labels,
        textposition='top center',
        textfont=dict(size=10.5, color='#0f172a', family='Inter, sans-serif'),
        cliponaxis=False,
        hoverinfo='text',
        hovertext=hover_texts
    ))

    # Linea tratteggiata Season Average
    if season_avg_val > 0:
        fig.add_hline(
            y=season_avg_val,
            line_dash="dash",
            line_color="#64748b",
            line_width=1.5,
            annotation_text=f"Media Stagione: {season_avg_str}",
            annotation_position="bottom right",
            annotation_font=dict(size=10, color="#64748b", family='Inter, sans-serif')
        )

    fig.update_layout(
        height=240,
        margin=dict(l=35, r=25, t=25, b=30),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(248,250,252,0.6)',
        xaxis=dict(
            tickfont=dict(size=10, color='#475569', family='Inter, sans-serif'),
            showgrid=False,
            linecolor='#cbd5e1'
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor='#f1f5f9',
            range=[0, max_y],
            tickfont=dict(size=9.5, color='#64748b'),
            zerolinecolor='#cbd5e1'
        ),
        showlegend=False
    )

    st.plotly_chart(fig, use_container_width=True, key=chart_key, config={'displayModeBar': False})
    st.markdown("<div style='margin-bottom: 16px;'></div>", unsafe_allow_html=True)


# =============================================================================
# GRAFICO EXECUTIVE ACWR CON 4 BANDE DI RISCHIO
# =============================================================================
def get_acwr_zone_details(pct):
    """Restituisce testo zona, colore, sfondo badge e colore bordo per un dato valore ACWR."""
    if pct is None or pd.isna(pct):
        return tr("Dati Insufficienti", "Insufficient Data"), "#94a3b8", "#f1f5f9", "#cbd5e1"
    if pct < 80:
        return tr("Scarico (<80%)", "Low (<80%)"), "#0ea5e9", "#e0f2fe", "#38bdf8"
    elif pct <= 125:
        return tr("Ottimale / Sweet Spot (80-125%)", "Optimal / Sweet Spot (80-125%)"), "#10b981", "#dcfce7", "#34d399"
    elif pct <= 150:
        return tr("Attenzione / Elevato (125-150%)", "Caution / High (125-150%)"), "#f59e0b", "#fef3c7", "#fbbf24"
    else:
        return tr("Danger Zone / Overload (>150%)", "Danger Zone / Overload (>150%)"), "#ef4444", "#fee2e2", "#f87171"


def render_acwr_risk_chart(
    title,
    subtitle,
    x_labels,
    y_acwr_7d,
    y_acute_2d,
    hover_texts_7d,
    hover_texts_2d,
    chart_key="chart_acwr",
    mode_key="mode_acwr",
    is_daily=False
):
    """
    Renderizza il grafico Executive ACWR con:
    - 4 bande fisiologiche di rischio (Scarico, Sweet Spot, Attenzione, Danger Zone)
    - Linea 100% baseline tratteggiata
    - Curve spline sovrapposte o isolate (7D Chronic Rolling vs 2D Acute Readiness)
    - Marker intelligenti con colore legato alla zona di rischio
    """
    c_m1, c_m2 = st.columns([1.6, 1.4])
    with c_m1:
        st.markdown(f"#### <i class='bi bi-activity' style='color:#0ea5e9; margin-right:8px;'></i>{title}", unsafe_allow_html=True)
        st.caption(subtitle)
    with c_m2:
        opzioni_modalita = [
            tr("Confronto Sovrapposto (2d vs 7d)", "Overlaid Comparison (2d vs 7d)"),
            tr("Solo ACWR 7 Giorni (Rolling)", "7-Day ACWR Only (Rolling)"),
            tr("Solo Acute Readiness 2 Giorni", "2-Day Acute Readiness Only")
        ]
        sel_mode = st.radio(
            tr("Modalità Tracciati", "Curve Display Mode"),
            options=opzioni_modalita,
            index=0,
            horizontal=True,
            key=mode_key
        )

    all_nums = [v for v in (y_acwr_7d + y_acute_2d) if v is not None and not pd.isna(v)]
    peak_v = max(all_nums) if all_nums else 150.0
    max_y = max(peak_v * 1.15, 180.0)

    fig = go.Figure()

    # 4 Zone fisiologiche di rischio orizzontali
    fig.add_hrect(
        y0=0, y1=80,
        fillcolor="rgba(14, 165, 233, 0.08)",
        layer="below", line_width=0,
        annotation_text=tr("Scarico (< 80%)", "Low (< 80%)"),
        annotation_position="bottom right",
        annotation_font=dict(size=9.5, color="#0284c7")
    )
    fig.add_hrect(
        y0=80, y1=125,
        fillcolor="rgba(16, 185, 129, 0.12)",
        layer="below", line_width=0,
        annotation_text=tr("Sweet Spot (80% - 125%)", "Sweet Spot (80% - 125%)"),
        annotation_position="bottom right",
        annotation_font=dict(size=9.5, color="#059669")
    )
    fig.add_hrect(
        y0=125, y1=150,
        fillcolor="rgba(245, 158, 11, 0.10)",
        layer="below", line_width=0,
        annotation_text=tr("Attenzione (125% - 150%)", "Caution (125% - 150%)"),
        annotation_position="bottom right",
        annotation_font=dict(size=9.5, color="#d97706")
    )
    fig.add_hrect(
        y0=150, y1=max_y,
        fillcolor="rgba(239, 68, 68, 0.12)",
        layer="below", line_width=0,
        annotation_text=tr("Danger Zone (> 150%)", "Danger Zone (> 150%)"),
        annotation_position="bottom right",
        annotation_font=dict(size=9.5, color="#dc2626")
    )

    # Linea tratteggiata Baseline 100%
    fig.add_hline(
        y=100,
        line_dash="dash",
        line_color="#64748b",
        line_width=1.5,
        annotation_text=tr("Baseline 100% (Carico Neutro)", "Baseline 100% (Neutral)"),
        annotation_position="bottom left",
        annotation_font=dict(size=9.5, color="#475569")
    )

    marker_size = 5 if is_daily else 7

    # Colori dinamici dei marker per 7 Giorni in base alla zona
    marker_colors_7d = []
    for v in y_acwr_7d:
        if v is None or pd.isna(v):
            marker_colors_7d.append("#94a3b8")
        elif v < 80:
            marker_colors_7d.append("#0ea5e9")
        elif v <= 125:
            marker_colors_7d.append("#10b981")
        elif v <= 150:
            marker_colors_7d.append("#f59e0b")
        else:
            marker_colors_7d.append("#ef4444")

    # Aggiunta tracciato 7 Giorni (se sovrapposto o solo 7d)
    if sel_mode in [opzioni_modalita[0], opzioni_modalita[1]]:
        fill_7d = "tozeroy" if sel_mode == opzioni_modalita[1] else None
        fillcolor_7d = "rgba(2, 132, 199, 0.08)" if sel_mode == opzioni_modalita[1] else None
        fig.add_trace(go.Scatter(
            x=x_labels,
            y=y_acwr_7d,
            name=tr("ACWR 7 Giorni (Rolling)", "7-Day ACWR (Rolling)"),
            mode='lines+markers',
            line=dict(color="#0284c7", width=3, shape='spline', smoothing=0.65),
            marker=dict(
                size=marker_size + 1,
                color=marker_colors_7d,
                line=dict(color='#ffffff', width=2)
            ),
            fill=fill_7d,
            fillcolor=fillcolor_7d,
            connectgaps=True,
            hoverinfo='text',
            hovertext=hover_texts_7d
        ))

    # Aggiunta tracciato 2 Giorni (se sovrapposto o solo 2d)
    if sel_mode in [opzioni_modalita[0], opzioni_modalita[2]]:
        fill_2d = "tozeroy" if sel_mode == opzioni_modalita[2] else None
        fillcolor_2d = "rgba(249, 115, 22, 0.08)" if sel_mode == opzioni_modalita[2] else None
        fig.add_trace(go.Scatter(
            x=x_labels,
            y=y_acute_2d,
            name=tr("Acute Readiness 2 Giorni", "2-Day Acute Readiness"),
            mode='lines+markers',
            line=dict(color="#f97316", width=2.5, shape='spline', smoothing=0.6),
            marker=dict(
                symbol='diamond',
                size=marker_size,
                color="#f97316",
                line=dict(color='#ffffff', width=1.5)
            ),
            fill=fill_2d,
            fillcolor=fillcolor_2d,
            connectgaps=True,
            hoverinfo='text',
            hovertext=hover_texts_2d
        ))

    fig.update_layout(
        height=380,
        margin=dict(l=35, r=25, t=30, b=40),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(248,250,252,0.6)',
        xaxis=dict(
            tickfont=dict(size=9.5 if is_daily else 10, color='#475569', family='Inter, sans-serif'),
            showgrid=False,
            linecolor='#cbd5e1',
            nticks=20 if is_daily else None
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor='#f1f5f9',
            range=[0, max_y],
            tickfont=dict(size=9.5, color='#64748b'),
            zerolinecolor='#cbd5e1',
            ticksuffix="%"
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font=dict(size=11, color="#334155")
        )
    )

    st.plotly_chart(fig, use_container_width=True, key=chart_key, config={'displayModeBar': False})
    st.markdown("<div style='margin-bottom: 16px;'></div>", unsafe_allow_html=True)


# =============================================================================
# VISTA PRINCIPALE TREND STAGIONALE
# =============================================================================
def render_trend_stagionale(t):
    render_page_header(
        tr("Trend Stagionale", "Seasonal Trend"),
        tr("Analisi longitudinale del carico su 8 settimane e monitoraggio dell'intera stagione sportiva.", "Longitudinal workload analysis across 8 weeks and full sports season monitoring."),
        "SEASONAL WORKLOAD"
    )

    df_storico = load_local_database()
    if df_storico.empty:
        st.warning(t['am_no_db'])
        return

    # Filtro atleti consentiti per ruolo
    if st.session_state['role'] != 'Super-Admin':
        atleti_consentiti = get_atleti_associati(st.session_state['user'].id)
        if not atleti_consentiti:
            st.warning(t['up_no_atl'])
            return
        df_storico = df_storico[df_storico['Players'].isin(atleti_consentiti)]

    giocatori_disponibili = sorted(df_storico['Players'].dropna().unique().tolist())
    if not giocatori_disponibili:
        st.warning(tr("Nessun dato disponibile.", "No data available."))
        return

    # Verifica permessi per moduli Trend Stagionale
    if st.session_state.get('role') == 'Super-Admin':
        report_abilitati = CATALOGO_REPORT.get("Trend Stagionale", [])
    else:
        try:
            res_rep = supabase.table('moduli_report').select('nome_report').eq('profilo_id', st.session_state['user'].id).eq('area', 'Trend Stagionale').execute()
            report_abilitati = [r['nome_report'] for r in res_rep.data] if (res_rep and res_rep.data) else []
        except:
            report_abilitati = []
        # Se non è ancora stato configurato nulla su Supabase per la nuova area Trend Stagionale, abilita di default tutti i moduli
        if not report_abilitati:
            report_abilitati = CATALOGO_REPORT.get("Trend Stagionale", [])

    # 1. ATLETA ATTIVO & SELETTORE STAGIONE (ANNO)
    glob_ath = st.session_state.get('selected_athlete')
    if glob_ath in giocatori_disponibili:
        giocatore_selezionato = glob_ath
    elif 'am_sel_player' in st.session_state and st.session_state['am_sel_player'] in giocatori_disponibili:
        giocatore_selezionato = st.session_state['am_sel_player']
    else:
        giocatore_selezionato = giocatori_disponibili[0]
    st.session_state['am_sel_player'] = giocatore_selezionato

    df_ath = df_storico[df_storico['Players'] == giocatore_selezionato].copy()
    df_ath['Date_obj'] = pd.to_datetime(df_ath['Date'], format='%d/%m/%Y', errors='coerce')
    df_ath = df_ath.dropna(subset=['Date_obj']).copy()

    if df_ath.empty:
        st.warning(tr("Nessuna sessione con data valida per questo atleta.", "No valid date sessions for this athlete."))
        return

    stagioni_disponibili = sorted(df_ath['Date_obj'].dt.year.unique().astype(int).tolist(), reverse=True)
    if not stagioni_disponibili:
        st.warning("Nessun dato temporale per questo atleta.")
        return

    stagione_sel = st.selectbox(
        tr("Stagione (Anno)", "Season (Year)"),
        stagioni_disponibili,
        index=0,
        key="widget_stagionale_year"
    )

    # Striscia Compatta Identità Atleta MOV3 con tag Stagione
    lbl_stag_tag = f"{tr('Stagione', 'Season')}: {stagione_sel}"
    render_athlete_hero_strip(giocatore_selezionato, df_atleta=df_ath, extra_badges=[lbl_stag_tag])

    # Filtraggio dati per la stagione selezionata
    df_season = df_ath[df_ath['Date_obj'].dt.year == stagione_sel].copy()
    if df_season.empty:
        st.info(f"Nessuna sessione registrata per {giocatore_selezionato} nella stagione {stagione_sel}.")
        return

    # 2. KPI EXECUTIVE DI SINTESI STAGIONE
    tot_sess_stagione = len(df_season)
    tot_min_stagione = df_season['Minuti'].sum()
    tot_tl_stagione = df_season['Training Load'].sum()
    tot_reali_stagione = len(df_season[df_season['Dato_Simulato'] == False]) if 'Dato_Simulato' in df_season.columns else tot_sess_stagione

    df_season['Week_Start'] = df_season['Date_obj'] - pd.to_timedelta(df_season['Date_obj'].dt.dayofweek, unit='d')
    df_season['Week_End'] = df_season['Week_Start'] + pd.to_timedelta(6, unit='d')
    df_season['Week_Start_Date'] = df_season['Week_Start'].dt.date
    n_settimane_attive_stagione = df_season['Week_Start_Date'].nunique()

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(
            card_kpi(
                tr("Stagione Sportiva", "Sports Season"),
                f"<span style='font-size:24px; font-weight:900; color:#0f172a;'>{stagione_sel}</span>",
                f"{giocatore_selezionato}",
                "#0ea5e9"
            ),
            unsafe_allow_html=True
        )
    with k2:
        st.markdown(
            card_kpi(
                tr("Sessioni Svolte", "Completed Sessions"),
                f"<span style='font-size:24px; font-weight:900; color:#0f172a;'>{tot_sess_stagione}</span>",
                f"{tot_reali_stagione} {tr('Reali', 'Real')} · {n_settimane_attive_stagione} {tr('Settimane attive', 'Active weeks')}",
                "#10b981"
            ),
            unsafe_allow_html=True
        )
    with k3:
        ore_tot = tot_min_stagione / 60.0
        st.markdown(
            card_kpi(
                tr("Volume Orario Stagione", "Total Season Hours"),
                f"<span style='font-size:24px; font-weight:900; color:#0f172a;'>{ore_tot:.1f} h</span>",
                f"{tot_min_stagione:,.0f} {tr('minuti complessivi', 'total minutes')}",
                "#8b5cf6"
            ),
            unsafe_allow_html=True
        )
    with k4:
        media_sett_tl = tot_tl_stagione / max(n_settimane_attive_stagione, 1)
        st.markdown(
            card_kpi(
                tr("Training Load Totale", "Total Season Load"),
                f"<span style='font-size:24px; font-weight:900; color:#0f172a;'>{tot_tl_stagione:,.0f}</span>",
                f"{tr('Media settimanale', 'Weekly avg')}: {media_sett_tl:,.0f} TL",
                "#f59e0b"
            ),
            unsafe_allow_html=True
        )

    st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)

    opzioni_pdf_stagione = {
        tr("Report Stagionale Completo", "Complete Seasonal Report"): "Tutte",
        tr("Timeline Settimanale Stagione", "Full Season Weekly Timeline"): "Timeline_Settimanale",
        tr("ACWR Stagionale (Intera Stagione)", "Seasonal ACWR (Full Season)"): "ACWR_Stagionale",
        tr("Monotonia Stagionale (Foster)", "Seasonal Monotony (Foster)"): "Monotonia_Stagionale",
        tr("Strain Stagionale (Foster)", "Seasonal Strain (Foster)"): "Strain_Stagionale",
    }
    render_action_bar(
        meta_items=[
            (tr("Atleta", "Athlete"), giocatore_selezionato),
            (tr("Stagione", "Season"), str(stagione_sel)),
            (tr("Sessioni", "Sessions"), str(tot_sess_stagione)),
            (tr("Carico Totale", "Total Load"), f"{tot_tl_stagione:,.0f} TL"),
        ],
        pdf_options=opzioni_pdf_stagione,
        pdf_key=f"pdf_season_{slugify_name(giocatore_selezionato)}_{stagione_sel}",
        generate_fn=lambda sottoarea: crea_pdf_stagionale_m0v3(
            giocatore_selezionato, stagione_sel, df_season, df_ath=df_ath, sottoarea=sottoarea
        ),
        filename_fn=lambda sottoarea: f"M0V3_Stagionale_{sottoarea}_{slugify_name(giocatore_selezionato)}_{stagione_sel}.pdf"
    )

    st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)

    # 3. TAB NAVIGAZIONE MODULI (PERSISTENTI & REATTIVI M0V3)
    T_8W = tr("Andamento Ultime 8 Settimane", "Last 8 Weeks Trend")
    T_12M = tr("Carico Totale Mensile (12 Mesi)", "Total Monthly Load (12 Months)")
    T_TIMELINE = tr("Timeline Settimanale Stagione", "Full Season Weekly Timeline")
    T_ACWR_S = tr("ACWR Stagionale (Intera Stagione)", "Seasonal ACWR (Full Season)")
    T_ACWR_8W = tr("ACWR Ultime 8 Settimane", "ACWR Last 8 Weeks (Daily)")
    T_DIST = tr("Distribuzione Lavoro", "Workload Distribution")
    T_MONO = tr("Monotonia Stagionale", "Seasonal Monotony")
    T_STRAIN = tr("Strain Stagionale", "Seasonal Strain")

    stagione_tabs = [T_8W, T_12M, T_TIMELINE, T_ACWR_S, T_ACWR_8W, T_DIST, T_MONO, T_STRAIN]
    active_tab = render_tab_navigation(stagione_tabs, key="nav_trend_stagionale")

    # -------------------------------------------------------------------------
    # TAB 1: ANDAMENTO ULTIME 8 SETTIMANE
    # -------------------------------------------------------------------------
    if active_tab == T_8W:
        if "Andamento Ultime 8 Settimane" not in report_abilitati:
            st.info(tr("Il modulo 'Andamento Ultime 8 Settimane' non è abilitato per questo account. Contatta l'amministratore.", "The 'Last 8 Weeks Trend' module is not enabled for this account. Contact admin."))
        else:
            oggi = datetime.date.today()
            curr_mon = oggi - timedelta(days=oggi.weekday())
            
            all_w_set = set(df_season['Week_Start_Date'].unique()) if 'Week_Start_Date' in df_season.columns else set()
            if not df_season.empty and 'Week_Start_Date' in df_season.columns:
                min_mon = min(df_season['Week_Start_Date'])
            else:
                d_init = datetime.date(stagione_sel, 1, 1)
                min_mon = d_init - timedelta(days=d_init.weekday())
            
            if stagione_sel >= oggi.year:
                max_mon = curr_mon
            else:
                d_end = datetime.date(stagione_sel, 12, 31)
                max_mon = d_end - timedelta(days=d_end.weekday())
            
            cur_iter = min_mon
            while cur_iter <= max_mon:
                all_w_set.add(cur_iter)
                cur_iter += timedelta(days=7)
            
            settimane_univoche = sorted(list(all_w_set), reverse=True)
            dict_settimane_label = {}
            for w_start in settimane_univoche:
                w_end = w_start + timedelta(days=6)
                w_num = pd.to_datetime(w_start).isocalendar()[1]
                prefix = f"[{tr('Settimana Corrente', 'Current Week')}] " if w_start == curr_mon else ""
                dict_settimane_label[w_start] = f"{prefix}Settimana {w_num:02d} ({w_start.strftime('%d/%m/%Y')} - {w_end.strftime('%d/%m/%Y')})"

            c_w1, c_w2 = st.columns([2, 1])
            with c_w1:
                st.markdown(f"#### <i class='bi bi-graph-up' style='color:#0ea5e9; margin-right:8px;'></i>{tr('Andamento Ultime 8 Settimane vs Media Stagionale', 'Last 8 Weeks Trend vs Season Average')}", unsafe_allow_html=True)
                st.caption(tr(
                    "Confronto longitudinale dei carichi settimanali totali (Lunedì-Domenica) rispetto alla media stagionale. Include la media del blocco 8 settimane e la percentuale di scostamento.",
                    "Longitudinal comparison of total weekly workloads (Monday-Sunday) against season average. Includes 8-week block average and percentage deviation."
                ))
            with c_w2:
                settimana_finale_sel = st.selectbox(
                    tr("Settimana Finale del Blocco", "Final Week of Block"),
                    options=settimane_univoche,
                    format_func=lambda w: dict_settimane_label.get(w, str(w)),
                    key="widget_stagionale_end_week_tab"
                )

            # Raggruppamento per settimana dell'intera stagione
            df_weekly_season = df_season.groupby('Week_Start_Date').agg({
                'Minuti': 'sum',
                'Training Load': 'sum',
                'TL_High': 'sum',
                'High Accel IMU': 'sum',
                'High Decel IMU': 'sum',
                'Azioni Int. IMU >2': 'sum',
                'Date': 'count'
            }).reset_index().rename(columns={'Date': 'Num_Sessions'})

            season_avg_time = df_weekly_season['Minuti'].mean()
            season_avg_tl = df_weekly_season['Training Load'].mean()
            season_avg_tl_high = df_weekly_season['TL_High'].mean()
            season_avg_tl_high_pct = (season_avg_tl_high / season_avg_tl * 100) if season_avg_tl > 0 else 0.0
            season_avg_acc_dec = (df_weekly_season['High Accel IMU'] + df_weekly_season['High Decel IMU']).mean()
            season_avg_intense_actions = df_weekly_season['Azioni Int. IMU >2'].mean()

            # Costruzione 8 settimane a ritroso
            lista_8_lunedi = [settimana_finale_sel - timedelta(weeks=7 - i) for i in range(8)]
            dict_weekly_lookup = df_weekly_season.set_index('Week_Start_Date').to_dict('index')

            weeks_8_data = []
            labels_colonne_8w = ["WEEK -7", "WEEK -6", "WEEK -5", "WEEK -4", "WEEK -3", "WEEK -2", "WEEK -1", "CURRENT WEEK"]

            for idx, w_start in enumerate(lista_8_lunedi):
                w_end = w_start + timedelta(days=6)
                col_lbl = labels_colonne_8w[idx]
                range_str = f"{w_start.strftime('%d/%m')} - {w_end.strftime('%d/%m')}"

                if w_start in dict_weekly_lookup:
                    row_w = dict_weekly_lookup[w_start]
                    w_time = float(row_w.get('Minuti', 0.0))
                    w_tl = float(row_w.get('Training Load', 0.0))
                    w_tl_high = float(row_w.get('TL_High', 0.0))
                    w_tl_high_pct = (w_tl_high / w_tl * 100) if w_tl > 0 else 0.0
                    w_acc_dec = float(row_w.get('High Accel IMU', 0.0)) + float(row_w.get('High Decel IMU', 0.0))
                    w_intense = float(row_w.get('Azioni Int. IMU >2', 0.0))
                    w_sessions = int(row_w.get('Num_Sessions', 0))
                else:
                    w_time = 0.0
                    w_tl = 0.0
                    w_tl_high = 0.0
                    w_tl_high_pct = 0.0
                    w_acc_dec = 0.0
                    w_intense = 0.0
                    w_sessions = 0

                weeks_8_data.append({
                    "col_label": col_lbl,
                    "date_range": range_str,
                    "week_start": w_start,
                    "week_end": w_end,
                    "time": w_time,
                    "training_load": w_tl,
                    "tl_high": w_tl_high,
                    "tl_high_pct": w_tl_high_pct,
                    "acc_dec": w_acc_dec,
                    "intense_actions": w_intense,
                    "num_sessions": w_sessions,
                })

            avg8_time = sum(w['time'] for w in weeks_8_data) / 8.0
            avg8_tl = sum(w['training_load'] for w in weeks_8_data) / 8.0
            sum8_tl_high = sum(w['tl_high'] for w in weeks_8_data)
            avg8_tl_high_pct = (sum8_tl_high / (avg8_tl * 8.0) * 100) if avg8_tl > 0 else 0.0
            avg8_acc_dec = sum(w['acc_dec'] for w in weeks_8_data) / 8.0
            avg8_intense = sum(w['intense_actions'] for w in weeks_8_data) / 8.0

            # Rendering delle 5 metriche 8W
            render_metric_row_block(
                metric_vertical_title=tr("TIME", "TIME"),
                metric_box_title=tr("TIME (min)", "TIME (min)"),
                season_avg_val=season_avg_time,
                avg_8w_val=avg8_time,
                weeks_data=weeks_8_data,
                metric_key="time",
                is_time=True,
                chart_key="chart_time_8w"
            )

            render_metric_row_block(
                metric_vertical_title=tr("TRAINING LOAD", "TRAINING LOAD"),
                metric_box_title=tr("TRAINING LOAD", "TRAINING LOAD"),
                season_avg_val=season_avg_tl,
                avg_8w_val=avg8_tl,
                weeks_data=weeks_8_data,
                metric_key="training_load",
                chart_key="chart_tl_8w"
            )

            render_metric_row_block(
                metric_vertical_title=tr("TL HIGH %", "TL HIGH %"),
                metric_box_title=tr("TL HIGH % ON TOTAL TL", "TL HIGH % ON TOTAL TL"),
                season_avg_val=season_avg_tl_high_pct,
                avg_8w_val=avg8_tl_high_pct,
                weeks_data=weeks_8_data,
                metric_key="tl_high_pct",
                is_pct=True,
                chart_key="chart_tl_high_pct_8w"
            )

            render_metric_row_block(
                metric_vertical_title=tr("ACC + DEC", "ACC + DEC"),
                metric_box_title=tr("HIGH DEC + HIGH ACC", "HIGH DEC + HIGH ACC"),
                season_avg_val=season_avg_acc_dec,
                avg_8w_val=avg8_acc_dec,
                weeks_data=weeks_8_data,
                metric_key="acc_dec",
                chart_key="chart_acc_dec_8w"
            )

            render_metric_row_block(
                metric_vertical_title=tr("INTENSE ACTIONS", "INTENSE ACTIONS"),
                metric_box_title=tr("INTENSE ACTIONS >2\"", "INTENSE ACTIONS >2\""),
                season_avg_val=season_avg_intense_actions,
                avg_8w_val=avg8_intense,
                weeks_data=weeks_8_data,
                metric_key="intense_actions",
                chart_key="chart_intense_8w"
            )

    # -------------------------------------------------------------------------
    # TAB 2: CARICO TOTALE MENSILE (12 MESI)
    # -------------------------------------------------------------------------
    elif active_tab == T_12M:
        if "Carico Totale Mensile (12 Mesi)" not in report_abilitati:
            st.info(tr("Il modulo 'Carico Totale Mensile (12 Mesi)' non è abilitato per questo account. Contatta l'amministratore.", "The 'Total Monthly Load (12 Months)' module is not enabled for this account. Contact admin."))
        else:
            st.markdown(f"#### <i class='bi bi-calendar-range' style='color:#0ea5e9; margin-right:8px;'></i>{tr('Carico Totale Mensile (12 Mesi)', 'Total Monthly Load (12 Months)')} — {stagione_sel}", unsafe_allow_html=True)
            st.caption(tr(
                "Distribuzione mensile dell'intero anno solare (Gennaio - Dicembre). I valori sono confrontati con la media mensile della stagione (Season Average calcolata sui mesi attivi).",
                "Monthly distribution across the calendar year (January - December). Values are compared against the monthly season average calculated over active months."
            ))

            mesi_nomi = [
                (1, tr("GEN", "JAN"), tr("Gennaio", "January")),
                (2, tr("FEB", "FEB"), tr("Febbraio", "February")),
                (3, tr("MAR", "MAR"), tr("Marzo", "March")),
                (4, tr("APR", "APR"), tr("Aprile", "April")),
                (5, tr("MAG", "MAY"), tr("Maggio", "May")),
                (6, tr("GIU", "JUN"), tr("Giugno", "June")),
                (7, tr("LUG", "JUL"), tr("Luglio", "July")),
                (8, tr("AGO", "AUG"), tr("Agosto", "August")),
                (9, tr("SET", "SEP"), tr("Settembre", "September")),
                (10, tr("OTT", "OCT"), tr("Ottobre", "October")),
                (11, tr("NOV", "NOV"), tr("Novembre", "November")),
                (12, tr("DIC", "DEC"), tr("Dicembre", "December")),
            ]

            months_12_data = []
            for m_num, m_short, m_full in mesi_nomi:
                df_m = df_season[df_season['Date_obj'].dt.month == m_num]
                n_sess_m = len(df_m)

                if n_sess_m > 0:
                    t_m = float(df_m['Minuti'].sum())
                    tl_m = float(df_m['Training Load'].sum())
                    tl_high_m = float(df_m['TL_High'].sum())
                    tl_high_pct_m = (tl_high_m / tl_m * 100) if tl_m > 0 else 0.0
                    acc_dec_m = float(df_m['High Accel IMU'].sum() + df_m['High Decel IMU'].sum())
                    intense_m = float(df_m['Azioni Int. IMU >2'].sum())
                else:
                    t_m = 0.0
                    tl_m = 0.0
                    tl_high_m = 0.0
                    tl_high_pct_m = 0.0
                    acc_dec_m = 0.0
                    intense_m = 0.0

                months_12_data.append({
                    "month_num": m_num,
                    "col_label": m_short,
                    "full_name": m_full,
                    "time": t_m,
                    "training_load": tl_m,
                    "tl_high": tl_high_m,
                    "tl_high_pct": tl_high_pct_m,
                    "acc_dec": acc_dec_m,
                    "intense_actions": intense_m,
                    "num_sessions": n_sess_m
                })

            # Calcolo Season Average Mensile (Opzione A: media sui mesi con sessioni attive)
            active_months = [m for m in months_12_data if m['num_sessions'] > 0]
            n_act_m = len(active_months) if active_months else 1

            season_avg_time_m = sum(m['time'] for m in active_months) / n_act_m if active_months else 0.0
            season_avg_tl_m = sum(m['training_load'] for m in active_months) / n_act_m if active_months else 0.0
            sum_tl_high_m = sum(m['tl_high'] for m in active_months)
            tot_tl_m = sum(m['training_load'] for m in active_months)
            season_avg_tl_high_pct_m = (sum_tl_high_m / tot_tl_m * 100) if tot_tl_m > 0 else 0.0
            season_avg_acc_dec_m = sum(m['acc_dec'] for m in active_months) / n_act_m if active_months else 0.0
            season_avg_intense_m = sum(m['intense_actions'] for m in active_months) / n_act_m if active_months else 0.0

            # RIGA 1: TIME (h:m)
            render_metric_month_row_block(
                metric_vertical_title=tr("TIME", "TIME"),
                metric_box_title=tr("TIME (h:m)", "TIME (h:m)"),
                season_avg_val=season_avg_time_m,
                n_active_months=len(active_months),
                months_data=months_12_data,
                metric_key="time",
                is_time=True,
                chart_key="chart_m_time"
            )

            # RIGA 2: TRAINING LOAD
            render_metric_month_row_block(
                metric_vertical_title=tr("TRAINING LOAD", "TRAINING LOAD"),
                metric_box_title=tr("TRAINING LOAD", "TRAINING LOAD"),
                season_avg_val=season_avg_tl_m,
                n_active_months=len(active_months),
                months_data=months_12_data,
                metric_key="training_load",
                chart_key="chart_m_tl"
            )

            # RIGA 3: TL HIGH % ON TOTAL TL
            render_metric_month_row_block(
                metric_vertical_title=tr("TL HIGH %", "TL HIGH %"),
                metric_box_title=tr("TL HIGH % ON TOTAL TL", "TL HIGH % ON TOTAL TL"),
                season_avg_val=season_avg_tl_high_pct_m,
                n_active_months=len(active_months),
                months_data=months_12_data,
                metric_key="tl_high_pct",
                is_pct=True,
                chart_key="chart_m_tl_high"
            )

            # RIGA 4: HIGH DEC + HIGH ACC
            render_metric_month_row_block(
                metric_vertical_title=tr("ACC + DEC", "ACC + DEC"),
                metric_box_title=tr("HIGH DEC + HIGH ACC", "HIGH DEC + HIGH ACC"),
                season_avg_val=season_avg_acc_dec_m,
                n_active_months=len(active_months),
                months_data=months_12_data,
                metric_key="acc_dec",
                chart_key="chart_m_acc_dec"
            )

            # RIGA 5: INTENSE ACTIONS >2"
            render_metric_month_row_block(
                metric_vertical_title=tr("INTENSE ACTIONS", "INTENSE ACTIONS"),
                metric_box_title=tr("INTENSE ACTIONS >2\"", "INTENSE ACTIONS >2\""),
                season_avg_val=season_avg_intense_m,
                n_active_months=len(active_months),
                months_data=months_12_data,
                metric_key="intense_actions",
                chart_key="chart_m_intense"
            )

    # -------------------------------------------------------------------------
    # TAB 3: TIMELINE SETTIMANALE STAGIONE (ANDAMENTO SETTIMANA PER SETTIMANA)
    # -------------------------------------------------------------------------
    elif active_tab == T_TIMELINE:
        if "Timeline Settimanale Stagione" not in report_abilitati:
            st.info(tr("Il modulo 'Timeline Settimanale Stagione' non è abilitato per questo account. Contatta l'amministratore.", "The 'Full Season Weekly Timeline' module is not enabled for this account. Contact admin."))
        else:
            st.markdown(f"#### <i class='bi bi-activity' style='color:#0ea5e9; margin-right:8px;'></i>{tr('Timeline Settimanale Stagione (Volume & Intensità)', 'Full Season Weekly Timeline (Volume & Intensity)')} — {stagione_sel}", unsafe_allow_html=True)
            st.caption(tr(
                "Monitoraggio longitudinale continuo settimana per settimana dall'inizio all'ultima settimana disputata. Include tempo match, tempo totale, training load, % carico ad alta intensità e indici compositi.",
                "Continuous longitudinal week-by-week monitoring from season start to the last completed week. Includes match time, total time, training load, % high load and composite indices."
            ))

            # 1. Costruzione timeline continua (Lunedì consecutivi fino all'ultima settimana)
            min_w_start = df_season['Week_Start_Date'].min()
            max_w_start = df_season['Week_Start_Date'].max()

            curr_monday = min_w_start
            all_season_mondays = []
            while curr_monday <= max_w_start:
                all_season_mondays.append(curr_monday)
                curr_monday += timedelta(days=7)

            # Raggruppamento dati stagionali
            weekly_timeline_raw = []
            for w_start in all_season_mondays:
                w_end = w_start + timedelta(days=6)
                w_num = pd.to_datetime(w_start).isocalendar()[1]
                w_lbl = f"{w_start.strftime('%d/%m')}"
                w_full_lbl = f"Sett. {w_num:02d} ({w_start.strftime('%d/%m')} - {w_end.strftime('%d/%m')})"

                df_w = df_season[df_season['Week_Start_Date'] == w_start]
                n_sess_w = len(df_w)

                if n_sess_w > 0:
                    # Filtro soli Match
                    is_match = (
                        df_w['Tipologia Sessione'].astype(str).str.strip().str.lower() == 'match'
                    ) | (
                        df_w['Session'].astype(str).str.lower().str.contains('match|torneo|partita')
                    )
                    df_m_w = df_w[is_match]

                    t_match = float(df_m_w['Minuti'].sum()) if not df_m_w.empty else 0.0
                    t_tot = float(df_w['Minuti'].sum())
                    tl_tot = float(df_w['Training Load'].sum())
                    tl_high = float(df_w['TL_High'].sum())
                    pct_high = (tl_high / tl_tot * 100) if tl_tot > 0 else 0.0
                    high_acc = float(df_w['High Accel IMU'].sum())
                    high_dec = float(df_w['High Decel IMU'].sum())
                    intense_az2 = float(df_w['Azioni Int. IMU >2'].sum())
                    tot_mech = high_acc + high_dec
                else:
                    t_match = 0.0
                    t_tot = 0.0
                    tl_tot = 0.0
                    tl_high = 0.0
                    pct_high = 0.0
                    high_acc = 0.0
                    high_dec = 0.0
                    intense_az2 = 0.0
                    tot_mech = 0.0

                weekly_timeline_raw.append({
                    "week_start": w_start,
                    "col_label": w_lbl,
                    "full_label": w_full_lbl,
                    "num_sessions": n_sess_w,
                    "match_time": t_match,
                    "tot_time": t_tot,
                    "training_load": tl_tot,
                    "tl_high": tl_high,
                    "pct_tl_high": pct_high,
                    "acc_dec": tot_mech,
                    "intense_actions": intense_az2
                })

            # 2. Calcolo Indici Compositi (Volume & Work Rate)
            max_t = max([w['tot_time'] for w in weekly_timeline_raw] or [1.0]) or 1.0
            max_tl = max([w['training_load'] for w in weekly_timeline_raw] or [1.0]) or 1.0
            max_az = max([w['intense_actions'] for w in weekly_timeline_raw] or [1.0]) or 1.0

            # Calcolo densità per Work Rate
            for w in weekly_timeline_raw:
                if w['tot_time'] > 0:
                    w['tl_min'] = w['training_load'] / w['tot_time']
                    w['tlh_min'] = w['tl_high'] / w['tot_time']
                    w['az_min'] = w['intense_actions'] / w['tot_time']
                    w['mech_min'] = w['acc_dec'] / w['tot_time']
                else:
                    w['tl_min'] = 0.0
                    w['tlh_min'] = 0.0
                    w['az_min'] = 0.0
                    w['mech_min'] = 0.0

            max_tl_min = max([w['tl_min'] for w in weekly_timeline_raw] or [1.0]) or 1.0
            max_tlh_min = max([w['tlh_min'] for w in weekly_timeline_raw] or [1.0]) or 1.0
            max_az_min = max([w['az_min'] for w in weekly_timeline_raw] or [1.0]) or 1.0
            max_mech_min = max([w['mech_min'] for w in weekly_timeline_raw] or [1.0]) or 1.0

            for w in weekly_timeline_raw:
                # Indice di Volume (0 - 100): 35% Tempo, 40% TL, 25% Azioni Int.
                if w['tot_time'] > 0:
                    v_raw = ((w['tot_time'] / max_t) * 35.0) + ((w['training_load'] / max_tl) * 40.0) + ((w['intense_actions'] / max_az) * 25.0)
                    w['vol_index'] = round(v_raw, 1)
                else:
                    w['vol_index'] = 0.0

                # Indice di Work Rate (0 - 100): intensità al minuto
                if w['tot_time'] > 0:
                    wr_raw = ((w['tl_min'] / max_tl_min) * 40.0) + ((w['tlh_min'] / max_tlh_min) * 30.0) + ((w['az_min'] / max_az_min) * 15.0) + ((w['mech_min'] / max_mech_min) * 15.0)
                    w['wr_index'] = round(wr_raw, 1)
                else:
                    w['wr_index'] = 0.0

            # 3. Medie Stagionali (sulle settimane attive con sessioni)
            active_weeks = [w for w in weekly_timeline_raw if w['num_sessions'] > 0]
            n_act_w = len(active_weeks) if active_weeks else 1

            avg_match_time = sum(w['match_time'] for w in active_weeks) / n_act_w if active_weeks else 0.0
            avg_tot_time = sum(w['tot_time'] for w in active_weeks) / n_act_w if active_weeks else 0.0
            avg_tl = sum(w['training_load'] for w in active_weeks) / n_act_w if active_weeks else 0.0
            tot_tl_sum = sum(w['training_load'] for w in active_weeks)
            tot_tlh_sum = sum(w['tl_high'] for w in active_weeks)
            avg_pct_tl_high = (tot_tlh_sum / tot_tl_sum * 100) if tot_tl_sum > 0 else 0.0
            avg_wr = sum(w['wr_index'] for w in active_weeks) / n_act_w if active_weeks else 0.0
            avg_vol = sum(w['vol_index'] for w in active_weeks) / n_act_w if active_weeks else 0.0

            x_labels = [w['col_label'] for w in weekly_timeline_raw]

            # 4. RENDERING DEI 6 GRAFICI AD AREA SPLINE

            # --- GRAFICO 1: TEMPO DEI SOLI MATCH ---
            y_mtime = [w['match_time'] for w in weekly_timeline_raw]
            txt_mtime = [format_minutes_hours_mins(v) if v > 0 else "0" for v in y_mtime]
            hov_mtime = [f"<b>{w['full_label']}</b><br>Tempo Match: <b>{format_minutes_hours_mins(w['match_time'])}</b>" for w in weekly_timeline_raw]
            peak_mtime_val = max(y_mtime) if y_mtime else 0.0

            render_spline_metric_chart(
                title=tr("Tempo dei Soli Match", "Match Time (Matches Only)"),
                subtitle=tr("Minuti totali disputati in soli Match", "Total minutes played in Match sessions only"),
                x_labels=x_labels,
                y_values=y_mtime,
                text_labels=txt_mtime,
                hover_texts=hov_mtime,
                line_color="#f97316",
                fill_color="rgba(249, 115, 22, 0.12)",
                season_avg_val=avg_match_time,
                season_avg_str=format_minutes_hours_mins(avg_match_time),
                peak_val_str=format_minutes_hours_mins(peak_mtime_val),
                chart_key="spline_match_time"
            )

            # --- GRAFICO 2: TEMPO TOTALE DI TUTTE LE SESSIONI ---
            y_ttime = [w['tot_time'] for w in weekly_timeline_raw]
            txt_ttime = [format_minutes_hours_mins(v) if v > 0 else "0" for v in y_ttime]
            hov_ttime = [f"<b>{w['full_label']}</b><br>Tempo Totale: <b>{format_minutes_hours_mins(w['tot_time'])}</b> ({w['num_sessions']} sess.)" for w in weekly_timeline_raw]
            peak_ttime_val = max(y_ttime) if y_ttime else 0.0

            render_spline_metric_chart(
                title=tr("Tempo Totale di Tutte le Sessioni", "Total Weekly Time (All Sessions)"),
                subtitle=tr("Minuti totali settimanali (Match + Allenamenti)", "Total weekly minutes (Matches + Training)"),
                x_labels=x_labels,
                y_values=y_ttime,
                text_labels=txt_ttime,
                hover_texts=hov_ttime,
                line_color="#0ea5e9",
                fill_color="rgba(14, 165, 233, 0.12)",
                season_avg_val=avg_tot_time,
                season_avg_str=format_minutes_hours_mins(avg_tot_time),
                peak_val_str=format_minutes_hours_mins(peak_ttime_val),
                chart_key="spline_tot_time"
            )

            # --- GRAFICO 3: TRAINING LOAD ---
            y_tl = [w['training_load'] for w in weekly_timeline_raw]
            txt_tl = [f"{int(round(v)):,}".replace(",", ".") if v > 0 else "0" for v in y_tl]
            hov_tl = [f"<b>{w['full_label']}</b><br>Training Load: <b>{int(round(w['training_load'])):,}</b>" for w in weekly_timeline_raw]
            peak_tl_val = max(y_tl) if y_tl else 0.0

            render_spline_metric_chart(
                title=tr("Training Load", "Training Load"),
                subtitle=tr("Carico totale accumulato nella settimana", "Total weekly training load accumulated"),
                x_labels=x_labels,
                y_values=y_tl,
                text_labels=txt_tl,
                hover_texts=hov_tl,
                line_color="#6366f1",
                fill_color="rgba(99, 102, 241, 0.12)",
                season_avg_val=avg_tl,
                season_avg_str=f"{int(round(avg_tl)):,}".replace(",", "."),
                peak_val_str=f"{int(round(peak_tl_val)):,}".replace(",", "."),
                chart_key="spline_tl"
            )

            # --- GRAFICO 4: % TRAINING LOAD HIGH SUL TOTALE ---
            y_pct_high = [w['pct_tl_high'] for w in weekly_timeline_raw]
            txt_pct_high = [f"{v:.0f}%" if v > 0 else "0%" for v in y_pct_high]
            hov_pct_high = [f"<b>{w['full_label']}</b><br>% TL High: <b>{w['pct_tl_high']:.1f}%</b> ({w['tl_high']:.0f} TL High)" for w in weekly_timeline_raw]
            peak_pct_high_val = max(y_pct_high) if y_pct_high else 0.0

            render_spline_metric_chart(
                title=tr("% Training Load High", "% High Intensity Training Load"),
                subtitle=tr("Percentuale di carico ad alta intensità su carico totale", "% High load on total training load"),
                x_labels=x_labels,
                y_values=y_pct_high,
                text_labels=txt_pct_high,
                hover_texts=hov_pct_high,
                line_color="#ef4444",
                fill_color="rgba(239, 68, 68, 0.12)",
                season_avg_val=avg_pct_tl_high,
                season_avg_str=f"{avg_pct_tl_high:.0f}%",
                peak_val_str=f"{peak_pct_high_val:.0f}%",
                chart_key="spline_pct_high"
            )

            # --- GRAFICO 5: INDICE DI WORK RATE GENERALE ---
            y_wr = [w['wr_index'] for w in weekly_timeline_raw]
            txt_wr = [f"{v:.1f}" if v > 0 else "0" for v in y_wr]
            hov_wr = [f"<b>{w['full_label']}</b><br>Indice Work Rate: <b>{w['wr_index']:.1f}</b>" for w in weekly_timeline_raw]
            peak_wr_val = max(y_wr) if y_wr else 0.0

            render_spline_metric_chart(
                title=tr("Indice di Work Rate Generale", "General Work Rate Index"),
                subtitle=tr("Intensità media al minuto normalizzata su scala 0-100", "Normalized average work rate intensity per minute (0-100)"),
                x_labels=x_labels,
                y_values=y_wr,
                text_labels=txt_wr,
                hover_texts=hov_wr,
                line_color="#10b981",
                fill_color="rgba(16, 185, 129, 0.12)",
                season_avg_val=avg_wr,
                season_avg_str=f"{avg_wr:.1f}",
                peak_val_str=f"{peak_wr_val:.1f}",
                chart_key="spline_wr"
            )

            # --- GRAFICO 6: INDICE DI VOLUME (TEMPO + TL + AZIONI >2") ---
            y_vol = [w['vol_index'] for w in weekly_timeline_raw]
            txt_vol = [f"{v:.1f}" if v > 0 else "0" for v in y_vol]
            hov_vol = [f"<b>{w['full_label']}</b><br>Indice Volume: <b>{w['vol_index']:.1f}</b>" for w in weekly_timeline_raw]
            peak_vol_val = max(y_vol) if y_vol else 0.0

            render_spline_metric_chart(
                title=tr("Indice di Volume (Tempo + TL + Azioni >2\")", "Volume Index (Time + TL + Actions >2\")"),
                subtitle=tr("Indice composito ponderato di volume su scala 0-100", "Weighted composite volume index on a 0-100 scale"),
                x_labels=x_labels,
                y_values=y_vol,
                text_labels=txt_vol,
                hover_texts=hov_vol,
                line_color="#8b5cf6",
                fill_color="rgba(139, 92, 246, 0.12)",
                season_avg_val=avg_vol,
                season_avg_str=f"{avg_vol:.1f}",
                peak_val_str=f"{peak_vol_val:.1f}",
                chart_key="spline_vol"
            )

    # -------------------------------------------------------------------------
    # TAB 4: ACWR STAGIONALE (INTERA STAGIONE)
    # -------------------------------------------------------------------------
    elif active_tab == T_ACWR_S:
        if "ACWR Stagionale (Intera Stagione)" not in report_abilitati:
            st.info(tr("Il modulo 'ACWR Stagionale (Intera Stagione)' non è abilitato per questo account. Contatta l'amministratore.", "The 'Seasonal ACWR (Full Season)' module is not enabled for this account. Contact admin."))
        else:
            st.markdown(f"#### <i class='bi bi-activity' style='color:#0ea5e9; margin-right:8px;'></i>{tr('ACWR Stagionale (Intera Stagione)', 'Seasonal ACWR (Full Season)')} — {stagione_sel}", unsafe_allow_html=True)
            st.caption(tr(
                "Progressione dell'Acute:Chronic Workload Ratio consolidato settimana per settimana (Lunedì-Domenica) per l'intera stagione agonistica. Confronta la reattività acuta a 2 giorni con il carico cronico a 7 giorni rispetto alla baseline di 28 giorni precedenti.",
                "Week-by-week consolidated Acute:Chronic Workload Ratio (Monday-Sunday) progression across the sports season. Compares 2-day acute readiness with 7-day rolling chronic load against the preceding 28-day baseline."
            ))

            opt_acwr_curves = [
                tr("ACWR Globale (Training Load)", "Global ACWR (Training Load)"),
                tr("ACWR Meccanico (High Accel + Decel)", "Mechanical ACWR (High Accel + Decel)"),
                tr("ACWR Alta Intensità (TL High)", "High Intensity ACWR (TL High)")
            ]
            sel_curve_lbl = render_tab_navigation(opt_acwr_curves, key="sel_acwr_season_curve")
            
            if "Meccanico" in sel_curve_lbl or "Mechanical" in sel_curve_lbl:
                col_acwr_calc = 'Mechanical Load'
            elif "Alta Intensità" in sel_curve_lbl or "High Intensity" in sel_curve_lbl:
                col_acwr_calc = 'TL_High'
            else:
                col_acwr_calc = 'Training Load'

            min_w_start = df_season['Week_Start_Date'].min()
            max_w_start = df_season['Week_Start_Date'].max()

            curr_monday = min_w_start
            all_season_mondays = []
            while curr_monday <= max_w_start:
                all_season_mondays.append(curr_monday)
                curr_monday += timedelta(days=7)

            season_acwr_data = []
            for w_start in all_season_mondays:
                w_end = w_start + timedelta(days=6)
                w_num = pd.to_datetime(w_start).isocalendar()[1]
                w_lbl = f"{w_start.strftime('%d/%m')}"
                w_full_lbl = f"Sett. {w_num:02d} ({w_start.strftime('%d/%m')} - {w_end.strftime('%d/%m')})"
                w_end_str = w_end.strftime("%d/%m/%Y")

                acwr_7d = acwr_pre_match(df_storico, giocatore_selezionato, w_end_str, giorni=7, col=col_acwr_calc, include_target=True, burn_in_mask=True)
                acute_2d = acwr_pre_match(df_storico, giocatore_selezionato, w_end_str, giorni=2, col=col_acwr_calc, include_target=True, burn_in_mask=True)

                df_w = df_season[df_season['Week_Start_Date'] == w_start]
                tl_w = float(df_w['Training Load'].sum()) if not df_w.empty else 0.0
                n_sess = len(df_w)

                season_acwr_data.append({
                    "w_start": w_start,
                    "w_end": w_end,
                    "w_lbl": w_lbl,
                    "full_label": w_full_lbl,
                    "acwr_7d": acwr_7d,
                    "acute_2d": acute_2d,
                    "training_load": tl_w,
                    "num_sessions": n_sess
                })

            valid_7d = [p['acwr_7d'] for p in season_acwr_data if p['acwr_7d'] is not None and not pd.isna(p['acwr_7d'])]
            valid_2d = [p['acute_2d'] for p in season_acwr_data if p['acute_2d'] is not None and not pd.isna(p['acute_2d'])]

            last_7d = valid_7d[-1] if valid_7d else None
            last_2d = valid_2d[-1] if valid_2d else None

            n_valid = len(valid_7d)
            n_sweet = sum(1 for v in valid_7d if 80 <= v <= 125)
            pct_sweet = (n_sweet / n_valid * 100) if n_valid > 0 else 0.0
            n_overload = sum(1 for v in valid_7d if v > 150)

            # 4 KPI Cards
            ak1, ak2, ak3, ak4 = st.columns(4)
            with ak1:
                z_txt, z_col, z_bg, z_border = get_acwr_zone_details(last_7d)
                val_str = f"{last_7d:.1f}%" if last_7d is not None else "N/D"
                st.markdown(
                    card_kpi(
                        tr("Ultimo ACWR 7 Giorni", "Latest 7-Day ACWR"),
                        f"<span style='font-size:24px; font-weight:900; color:{z_col};'>{val_str}</span>",
                        f"<span style='background:{z_bg}; color:{z_col}; font-weight:700; padding:2px 8px; border-radius:4px; font-size:11px;'>{z_txt}</span>",
                        z_col
                    ),
                    unsafe_allow_html=True
                )
            with ak2:
                z2_txt, z2_col, z2_bg, z2_border = get_acwr_zone_details(last_2d)
                val2_str = f"{last_2d:.1f}%" if last_2d is not None else "N/D"
                st.markdown(
                    card_kpi(
                        tr("Acute Readiness 2 Giorni", "2-Day Acute Readiness"),
                        f"<span style='font-size:24px; font-weight:900; color:{z2_col};'>{val2_str}</span>",
                        f"<span style='background:{z2_bg}; color:{z2_col}; font-weight:700; padding:2px 8px; border-radius:4px; font-size:11px;'>{z2_txt}</span>",
                        "#f97316"
                    ),
                    unsafe_allow_html=True
                )
            with ak3:
                st.markdown(
                    card_kpi(
                        tr("Tempo in Sweet Spot", "Time in Sweet Spot"),
                        f"<span style='font-size:24px; font-weight:900; color:#10b981;'>{pct_sweet:.0f}%</span>",
                        f"{n_sweet} {tr('su', 'of')} {n_valid} {tr('settimane (80-125%)', 'weeks (80-125%)')}",
                        "#10b981"
                    ),
                    unsafe_allow_html=True
                )
            with ak4:
                st.markdown(
                    card_kpi(
                        tr("Picchi Sovraccarico", "Overload Peaks"),
                        f"<span style='font-size:24px; font-weight:900; color:{'#ef4444' if n_overload > 0 else '#10b981'};'>{n_overload}</span>",
                        f"{tr('Settimane con ACWR >150%', 'Weeks with ACWR >150%')}",
                        "#ef4444" if n_overload > 0 else "#10b981"
                    ),
                    unsafe_allow_html=True
                )

            st.markdown("<div style='margin-top: 14px;'></div>", unsafe_allow_html=True)

            x_lbls_season = [p['w_lbl'] for p in season_acwr_data]
            y_7d_season = [p['acwr_7d'] for p in season_acwr_data]
            y_2d_season = [p['acute_2d'] for p in season_acwr_data]

            hov_7d_season = []
            hov_2d_season = []
            for p in season_acwr_data:
                z_info = get_acwr_zone_details(p['acwr_7d'])[0]
                val_7_str = f"{p['acwr_7d']:.1f}%" if p['acwr_7d'] is not None else "N/D"
                hov_7d_season.append(
                    f"<b>{p['full_label']}</b><br>"
                    f"ACWR 7 Giorni: <b>{val_7_str}</b><br>"
                    f"Stato: <b>{z_info}</b><br>"
                    f"Carico Settimanale: <b>{int(round(p['training_load'])):,} TL</b> ({p['num_sessions']} sess.)"
                )
                val_2_str = f"{p['acute_2d']:.1f}%" if p['acute_2d'] is not None else "N/D"
                z2_info = get_acwr_zone_details(p['acute_2d'])[0]
                hov_2d_season.append(
                    f"<b>{p['full_label']}</b><br>"
                    f"Acute Readiness 2 Giorni: <b>{val_2_str}</b><br>"
                    f"Stato: <b>{z2_info}</b>"
                )

            render_acwr_risk_chart(
                title=f"{tr('ACWR Stagionale', 'Seasonal ACWR')} ({sel_curve_lbl}) — {stagione_sel}",
                subtitle=tr("Monitoraggio longitudinale dell'equilibrio di carico per ogni settimana dell'anno.", "Longitudinal workload balance monitoring for every week of the year."),
                x_labels=x_lbls_season,
                y_acwr_7d=y_7d_season,
                y_acute_2d=y_2d_season,
                hover_texts_7d=hov_7d_season,
                hover_texts_2d=hov_2d_season,
                chart_key="acwr_season_chart",
                mode_key="acwr_season_mode",
                is_daily=False
            )

            with st.expander(tr("Tabella Dettagliata ACWR Stagionale", "Detailed Seasonal ACWR Table")):
                tab_rows = []
                for p in season_acwr_data:
                    tab_rows.append({
                        tr("Settimana", "Week"): p['full_label'],
                        tr("ACWR 7 Giorni", "7-Day ACWR"): f"{p['acwr_7d']:.1f}%" if p['acwr_7d'] is not None else "-",
                        tr("Acute Readiness 2 Giorni", "2-Day Acute"): f"{p['acute_2d']:.1f}%" if p['acute_2d'] is not None else "-",
                        tr("Stato Zona", "Zone Status"): get_acwr_zone_details(p['acwr_7d'])[0],
                        tr("Carico Settimanale", "Weekly Load"): f"{int(round(p['training_load'])):,} TL" if p['training_load'] > 0 else "-",
                        tr("Sessioni", "Sessions"): p['num_sessions']
                    })
                st.dataframe(pd.DataFrame(tab_rows), use_container_width=True, hide_index=True)

    # -------------------------------------------------------------------------
    # TAB 5: ACWR ULTIME 8 SETTIMANE (PROGRESSIONE GIORNALIERA)
    # -------------------------------------------------------------------------
    elif active_tab == T_ACWR_8W:
        if "ACWR Ultime 8 Settimane" not in report_abilitati:
            st.info(tr("Il modulo 'ACWR Ultime 8 Settimane' non è abilitato per questo account. Contatta l'amministratore.", "The 'ACWR Last 8 Weeks (Daily)' module is not enabled for this account. Contact admin."))
        else:
            st.markdown(f"#### <i class='bi bi-activity' style='color:#0ea5e9; margin-right:8px;'></i>{tr('ACWR Ultime 8 Settimane (Progressione Giornaliera)', 'ACWR Last 8 Weeks (Daily Progression)')}", unsafe_allow_html=True)
            st.caption(tr(
                "Curva giornaliera continua ad alta risoluzione (ultimi 56 giorni). Evidenzia l'insorgenza rapida di fatica acuta o picchi di carico nei giorni chiave di allenamento e match.",
                "High-resolution continuous daily curve (last 56 days). Highlights rapid onset of acute fatigue or load spikes on key training and match days."
            ))

            opt_acwr_curves_8w = [
                tr("ACWR Globale (Training Load)", "Global ACWR (Training Load)"),
                tr("ACWR Meccanico (High Accel + Decel)", "Mechanical ACWR (High Accel + Decel)"),
                tr("ACWR Alta Intensità (TL High)", "High Intensity ACWR (TL High)")
            ]
            sel_curve_lbl_8w = render_tab_navigation(opt_acwr_curves_8w, key="sel_acwr_8w_curve")
            
            if "Meccanico" in sel_curve_lbl_8w or "Mechanical" in sel_curve_lbl_8w:
                col_acwr_calc_8w = 'Mechanical Load'
            elif "Alta Intensità" in sel_curve_lbl_8w or "High Intensity" in sel_curve_lbl_8w:
                col_acwr_calc_8w = 'TL_High'
            else:
                col_acwr_calc_8w = 'Training Load'

            max_dt_8w = df_season['Date_obj'].max().date()
            start_dt_8w = max_dt_8w - timedelta(days=55)

            daily_acwr_data = []
            curr_d = start_dt_8w
            while curr_d <= max_dt_8w:
                d_str = curr_d.strftime("%d/%m/%Y")
                d_lbl = curr_d.strftime("%d/%m")
                full_d_lbl = curr_d.strftime("%d/%m/%Y")

                acwr_7d = acwr_pre_match(df_storico, giocatore_selezionato, d_str, giorni=7, col=col_acwr_calc_8w, include_target=True, burn_in_mask=True)
                acute_2d = acwr_pre_match(df_storico, giocatore_selezionato, d_str, giorni=2, col=col_acwr_calc_8w, include_target=True, burn_in_mask=True)

                df_day = df_season[df_season['Date_obj'].dt.date == curr_d]
                tl_day = float(df_day['Training Load'].sum()) if not df_day.empty else 0.0
                n_sess_day = len(df_day)

                daily_acwr_data.append({
                    "date": curr_d,
                    "d_lbl": d_lbl,
                    "full_label": full_d_lbl,
                    "acwr_7d": acwr_7d,
                    "acute_2d": acute_2d,
                    "training_load": tl_day,
                    "num_sessions": n_sess_day
                })
                curr_d += timedelta(days=1)

            valid_7d_daily = [p['acwr_7d'] for p in daily_acwr_data if p['acwr_7d'] is not None and not pd.isna(p['acwr_7d'])]
            valid_2d_daily = [p['acute_2d'] for p in daily_acwr_data if p['acute_2d'] is not None and not pd.isna(p['acute_2d'])]

            last_7d_d = valid_7d_daily[-1] if valid_7d_daily else None
            last_2d_d = valid_2d_daily[-1] if valid_2d_daily else None

            n_valid_d = len(valid_7d_daily)
            n_sweet_d = sum(1 for v in valid_7d_daily if 80 <= v <= 125)
            pct_sweet_d = (n_sweet_d / n_valid_d * 100) if n_valid_d > 0 else 0.0
            n_overload_d = sum(1 for v in valid_7d_daily if v > 150)

            # 4 KPI Cards
            dk1, dk2, dk3, dk4 = st.columns(4)
            with dk1:
                z_txt, z_col, z_bg, z_border = get_acwr_zone_details(last_7d_d)
                val_str = f"{last_7d_d:.1f}%" if last_7d_d is not None else "N/D"
                st.markdown(
                    card_kpi(
                        tr("Ultimo ACWR Giornaliero", "Latest Daily ACWR"),
                        f"<span style='font-size:24px; font-weight:900; color:{z_col};'>{val_str}</span>",
                        f"<span style='background:{z_bg}; color:{z_col}; font-weight:700; padding:2px 8px; border-radius:4px; font-size:11px;'>{z_txt}</span>",
                        z_col
                    ),
                    unsafe_allow_html=True
                )
            with dk2:
                z2_txt, z2_col, z2_bg, z2_border = get_acwr_zone_details(last_2d_d)
                val2_str = f"{last_2d_d:.1f}%" if last_2d_d is not None else "N/D"
                st.markdown(
                    card_kpi(
                        tr("Acute Readiness (2 Giorni)", "Acute Readiness (2 Days)"),
                        f"<span style='font-size:24px; font-weight:900; color:{z2_col};'>{val2_str}</span>",
                        f"<span style='background:{z2_bg}; color:{z2_col}; font-weight:700; padding:2px 8px; border-radius:4px; font-size:11px;'>{z2_txt}</span>",
                        "#f97316"
                    ),
                    unsafe_allow_html=True
                )
            with dk3:
                st.markdown(
                    card_kpi(
                        tr("Tempo in Sweet Spot", "Time in Sweet Spot"),
                        f"<span style='font-size:24px; font-weight:900; color:#10b981;'>{pct_sweet_d:.0f}%</span>",
                        f"{n_sweet_d} {tr('su', 'of')} {n_valid_d} {tr('giorni nel range (80-125%)', 'days in range (80-125%)')}",
                        "#10b981"
                    ),
                    unsafe_allow_html=True
                )
            with dk4:
                st.markdown(
                    card_kpi(
                        tr("Picchi Sovraccarico", "Overload Peaks"),
                        f"<span style='font-size:24px; font-weight:900; color:{'#ef4444' if n_overload_d > 0 else '#10b981'};'>{n_overload_d}</span>",
                        f"{tr('Giorni con ACWR >150% (56 gg)', 'Days with ACWR >150% (56 d)')}",
                        "#ef4444" if n_overload_d > 0 else "#10b981"
                    ),
                    unsafe_allow_html=True
                )

            st.markdown("<div style='margin-top: 14px;'></div>", unsafe_allow_html=True)

            x_lbls_daily = [p['d_lbl'] for p in daily_acwr_data]
            y_7d_daily = [p['acwr_7d'] for p in daily_acwr_data]
            y_2d_daily = [p['acute_2d'] for p in daily_acwr_data]

            hov_7d_daily = []
            hov_2d_daily = []
            for p in daily_acwr_data:
                z_info = get_acwr_zone_details(p['acwr_7d'])[0]
                val_7_str = f"{p['acwr_7d']:.1f}%" if p['acwr_7d'] is not None else "N/D"
                hov_7d_daily.append(
                    f"<b>{p['full_label']}</b><br>"
                    f"ACWR 7 Giorni: <b>{val_7_str}</b><br>"
                    f"Stato: <b>{z_info}</b><br>"
                    f"Carico Giornaliero: <b>{int(round(p['training_load'])):,} TL</b> ({p['num_sessions']} sess.)"
                )
                val_2_str = f"{p['acute_2d']:.1f}%" if p['acute_2d'] is not None else "N/D"
                z2_info = get_acwr_zone_details(p['acute_2d'])[0]
                hov_2d_daily.append(
                    f"<b>{p['full_label']}</b><br>"
                    f"Acute Readiness 2 Giorni: <b>{val_2_str}</b><br>"
                    f"Stato: <b>{z2_info}</b>"
                )

            render_acwr_risk_chart(
                title=f"{tr('ACWR Ultime 8 Settimane', 'Last 8 Weeks ACWR')} ({sel_curve_lbl_8w})",
                subtitle=tr("Evoluzione giorno per giorno negli ultimi 56 giorni con rilevazione immediata dei picchi acuti.", "Day-by-day evolution across the last 56 days with immediate acute spike detection."),
                x_labels=x_lbls_daily,
                y_acwr_7d=y_7d_daily,
                y_acute_2d=y_2d_daily,
                hover_texts_7d=hov_7d_daily,
                hover_texts_2d=hov_2d_daily,
                chart_key="acwr_8w_chart",
                mode_key="acwr_8w_mode",
                is_daily=True
            )

            with st.expander(tr("Tabella Dettagliata ACWR Giornaliero (56 Giorni)", "Detailed Daily ACWR Table (56 Days)")):
                tab_daily_rows = []
                for p in reversed(daily_acwr_data):
                    tab_daily_rows.append({
                        tr("Data", "Date"): p['full_label'],
                        tr("ACWR 7 Giorni", "7-Day ACWR"): f"{p['acwr_7d']:.1f}%" if p['acwr_7d'] is not None else "-",
                        tr("Acute Readiness 2 Giorni", "2-Day Acute"): f"{p['acute_2d']:.1f}%" if p['acute_2d'] is not None else "-",
                        tr("Stato Zona", "Zone Status"): get_acwr_zone_details(p['acwr_7d'])[0],
                        tr("Carico Giornaliero", "Daily Load"): f"{int(round(p['training_load'])):,} TL" if p['training_load'] > 0 else "-",
                        tr("Sessioni", "Sessions"): p['num_sessions']
                    })
                st.dataframe(pd.DataFrame(tab_daily_rows), use_container_width=True, hide_index=True)

    # -------------------------------------------------------------------------
    # TAB 6: DISTRIBUZIONE LAVORO (METADATA: SUPERFICI, TIPOLOGIE, SPARRING, MATCH)
    # -------------------------------------------------------------------------
    elif active_tab == T_DIST:
        if "Distribuzione Lavoro" not in report_abilitati:
            st.info(tr("Il modulo 'Distribuzione Lavoro' non è abilitato per questo account. Contatta l'amministratore.", "The 'Workload Distribution' module is not enabled for this account. Contact admin."))
        else:
            df_dist = df_season.copy()

            # Superfici canoniche e dinamiche
            raw_surfaces = df_dist['Tipologia Campo'].dropna().astype(str).str.strip().unique()
            extra_surfaces = [
                s.capitalize() for s in raw_surfaces
                if s and s.lower() not in ["hard", "clay", "grass", "-", "n/d", "none", "nan"]
            ]
            surfaces_cols = ["Hard", "Clay", "Grass"] + sorted(list(set(extra_surfaces)))

            # Tipologie di sessione dinamiche (campionate dai dati dell'atleta e config utente)
            user_email_dist = None if st.session_state.get('role') == 'Super-Admin' else st.session_state.get('user', {}).email if hasattr(st.session_state.get('user', None), 'email') else None
            all_known_types = get_tipologie_sessione(user_email_dist)
            raw_present_types = [
                str(x).strip() for x in df_dist['Tipologia Sessione'].dropna().unique()
                if str(x).strip() and str(x).strip() not in ["-", "N/D", "None", "nan"]
            ]

            canonical_order = list(CANONICAL_TIPOLOGIE_SESSIONE)
            tipologie_cols = []
            for ct in canonical_order:
                matching_t = next((p for p in raw_present_types if p.lower() == ct.lower()), None)
                if matching_t and matching_t not in tipologie_cols:
                    tipologie_cols.append(matching_t)

            for pt in sorted(raw_present_types):
                if not any(tc.lower() == pt.lower() for tc in tipologie_cols):
                    tipologie_cols.append(pt)

            if not tipologie_cols:
                tipologie_cols = [t for t in CANONICAL_TIPOLOGIE_SESSIONE if t in all_known_types] or list(CANONICAL_TIPOLOGIE_SESSIONE)

            # Mesi dell'anno (1 - 12)
            mesi_def = [
                ("Gen", "Jan", 1),
                ("Feb", "Feb", 2),
                ("Mar", "Mar", 3),
                ("Apr", "Apr", 4),
                ("Mag", "May", 5),
                ("Giu", "Jun", 6),
                ("Lug", "Jul", 7),
                ("Ago", "Aug", 8),
                ("Set", "Sep", 9),
                ("Ott", "Oct", 10),
                ("Nov", "Nov", 11),
                ("Dic", "Dec", 12)
            ]

            # Aggregati stagione
            tot_season_min = float(df_dist['Minuti'].sum())
            tot_season_sparring_min = float(df_dist['Minuti Sparring'].fillna(0).sum()) if 'Minuti Sparring' in df_dist.columns else 0.0
            tot_season_matches = len(df_dist[df_dist['Tipologia Sessione'].astype(str).str.strip().str.lower() == 'match'])

            surface_season_min = {
                s: float(df_dist[df_dist['Tipologia Campo'].astype(str).str.strip().str.lower() == s.lower()]['Minuti'].sum())
                for s in surfaces_cols
            }
            tipo_season_min = {
                t: float(df_dist[df_dist['Tipologia Sessione'].astype(str).str.strip().str.lower() == t.lower()]['Minuti'].sum())
                for t in tipologie_cols
            }

            # KPI di sintesi in cima
            top_surf = max(surface_season_min.items(), key=lambda x: x[1]) if surface_season_min else ("-", 0.0)
            top_surf_pct = (top_surf[1] / tot_season_min * 100) if tot_season_min > 0 else 0.0
            top_tipo = max(tipo_season_min.items(), key=lambda x: x[1]) if tipo_season_min else ("-", 0.0)
            top_tipo_pct = (top_tipo[1] / tot_season_min * 100) if tot_season_min > 0 else 0.0

            h_sp_tot = int(tot_season_sparring_min // 60)
            m_sp_tot = int(tot_season_sparring_min % 60)
            str_sp_tot = f"{h_sp_tot}h {m_sp_tot:02d}m"

            kd1, kd2, kd3, kd4 = st.columns(4)
            with kd1:
                st.markdown(
                    card_kpi(
                        tr("Superficie Principale", "Primary Surface"),
                        f"<span style='font-size:22px; font-weight:900; color:#0f172a;'>{top_surf[0].upper()}</span>",
                        f"{top_surf_pct:.1f}% del tempo totale ({int(top_surf[1]//60)}h {int(top_surf[1]%60):02d}m)",
                        "#f59e0b"
                    ),
                    unsafe_allow_html=True
                )
            with kd2:
                st.markdown(
                    card_kpi(
                        tr("Tipologia Più Frequente", "Most Frequent Session"),
                        f"<span style='font-size:22px; font-weight:900; color:#0f172a;'>{top_tipo[0].upper()}</span>",
                        f"{top_tipo_pct:.1f}% del lavoro totale ({int(top_tipo[1]//60)}h {int(top_tipo[1]%60):02d}m)",
                        "#0284c7"
                    ),
                    unsafe_allow_html=True
                )
            with kd3:
                st.markdown(
                    card_kpi(
                        tr("Tempo Sparring Totale", "Total Sparring Time"),
                        f"<span style='font-size:22px; font-weight:900; color:#0f172a;'>{str_sp_tot}</span>",
                        f"{int(round(tot_season_sparring_min))} minuti cumulati nell'anno",
                        "#8b5cf6"
                    ),
                    unsafe_allow_html=True
                )
            with kd4:
                st.markdown(
                    card_kpi(
                        tr("Match Ufficiali Giocati", "Official Matches Played"),
                        f"<span style='font-size:22px; font-weight:900; color:#ef4444;'>{tot_season_matches}</span>",
                        f"Stagione agonistica {stagione_sel}",
                        "#ef4444"
                    ),
                    unsafe_allow_html=True
                )

            st.markdown("<div style='margin-top: 18px;'></div>", unsafe_allow_html=True)

            # Costruzione Righe Tabella Mensile (12 Mesi)
            rows_dist_html = ""

            for m_it, m_en, m_num in mesi_def:
                df_m = df_dist[df_dist['Date_obj'].dt.month == m_num]
                tot_m_min = float(df_m['Minuti'].sum())
                is_active = (tot_m_min > 0)
                m_label = tr(m_it, m_en)

                # Cella Mese con separatore verticale marcato
                m_bg = "#f8fafc" if m_num % 2 == 0 else "#ffffff"
                m_cell_html = (
                    f"<td style='padding:10px 8px; text-align:center; font-weight:900; font-size:14px; "
                    f"color:{'#0f172a' if is_active else '#94a3b8'}; background:{m_bg}; "
                    f"border-right:2.5px solid #cbd5e1; white-space:nowrap;'>{m_label}</td>"
                )

                # Celle Superfici (con separatore di fine area a destra)
                cells_surf_html = ""
                for idx_s, s in enumerate(surfaces_cols):
                    is_last_s = (idx_s == len(surfaces_cols) - 1)
                    sep_s = "border-right:3px solid #0284c7;" if is_last_s else "border-right:1px solid #f1f5f9;"
                    s_min_m = float(df_m[df_m['Tipologia Campo'].astype(str).str.strip().str.lower() == s.lower()]['Minuti'].sum())
                    pct_s = (s_min_m / tot_m_min * 100) if tot_m_min > 0 else 0.0

                    if pct_s > 0:
                        b_col = "#cbd5e1"
                        fill_h = min(max(pct_s, 6.0), 100.0)
                        fill_div = f"<div style='width:100%; height:{fill_h:.0f}%; background:linear-gradient(180deg, #f59e0b 0%, #fbbf24 100%); opacity:0.85;'></div>"
                        txt_col = "#0f172a"
                        cell_bg = "#fefdfa"
                    else:
                        b_col = "#e2e8f0"
                        fill_div = ""
                        txt_col = "#94a3b8"
                        cell_bg = "#fcfdfd" if m_num % 2 == 0 else "#ffffff"

                    cells_surf_html += (
                        f"<td style='padding:6px 4px; text-align:center; background:{cell_bg}; {sep_s}'>"
                        f"<div style='font-size:9.5px; font-weight:700; color:#92400e; margin-bottom:2px;'>{s}</div>"
                        f"<div style='width:46px; height:36px; border:1px solid {b_col}; border-radius:4px; background:#f8fafc; position:relative; overflow:hidden; display:flex; flex-direction:column; justify-content:flex-end; margin:0 auto;'>"
                        f"{fill_div}"
                        f"<span style='position:absolute; width:100%; height:100%; top:0; left:0; display:flex; align-items:center; justify-content:center; font-size:11px; font-weight:800; color:{txt_col};'>{pct_s:.0f}%</span>"
                        f"</div>"
                        f"</td>"
                    )

                # Celle Tipologie (con separatore di fine area a destra)
                cells_tipo_html = ""
                for idx_t, t in enumerate(tipologie_cols):
                    is_last_t = (idx_t == len(tipologie_cols) - 1)
                    sep_t = "border-right:3px solid #0284c7;" if is_last_t else "border-right:1px solid #f1f5f9;"
                    t_min_m = float(df_m[df_m['Tipologia Sessione'].astype(str).str.strip().str.lower() == t.lower()]['Minuti'].sum())
                    pct_t = (t_min_m / tot_m_min * 100) if tot_m_min > 0 else 0.0

                    if pct_t > 0:
                        b_col = "#93c5fd"
                        fill_h = min(max(pct_t, 6.0), 100.0)
                        fill_div = f"<div style='width:100%; height:{fill_h:.0f}%; background:linear-gradient(180deg, #0284c7 0%, #38bdf8 100%); opacity:0.85;'></div>"
                        txt_col = "#0f172a"
                        cell_bg = "#f8fbff"
                    else:
                        b_col = "#e2e8f0"
                        fill_div = ""
                        txt_col = "#94a3b8"
                        cell_bg = "#fcfdfd" if m_num % 2 == 0 else "#ffffff"

                    cells_tipo_html += (
                        f"<td style='padding:6px 4px; text-align:center; background:{cell_bg}; {sep_t}'>"
                        f"<div style='font-size:9.5px; font-weight:700; color:#0369a1; margin-bottom:2px;'>{t}</div>"
                        f"<div style='width:46px; height:36px; border:1px solid {b_col}; border-radius:4px; background:#f8fafc; position:relative; overflow:hidden; display:flex; flex-direction:column; justify-content:flex-end; margin:0 auto;'>"
                        f"{fill_div}"
                        f"<span style='position:absolute; width:100%; height:100%; top:0; left:0; display:flex; align-items:center; justify-content:center; font-size:11px; font-weight:800; color:{txt_col};'>{pct_t:.0f}%</span>"
                        f"</div>"
                        f"</td>"
                    )

                # Cella T Sparring (separata verticalmente a destra)
                m_sp_m = float(df_m['Minuti Sparring'].fillna(0).sum()) if 'Minuti Sparring' in df_m.columns else 0.0
                if m_sp_m > 0:
                    h_m = int(m_sp_m // 60)
                    rem_m = int(m_sp_m % 60)
                    sp_str = f"{h_m}h {rem_m:02d}m"
                    cell_sp_html = (
                        f"<td style='padding:8px 8px; text-align:center; background:#faf8ff; border-right:2.5px solid #cbd5e1; white-space:nowrap;'>"
                        f"<div style='font-size:14px; font-weight:900; color:#0f172a;'>{sp_str}</div>"
                        f"<div style='font-size:10px; font-weight:700; color:#64748b;'>{int(round(m_sp_m))} min</div>"
                        f"</td>"
                    )
                else:
                    cell_sp_html = (
                        f"<td style='padding:8px 8px; text-align:center; background:#faf8ff; border-right:2.5px solid #cbd5e1; white-space:nowrap;'>"
                        f"<div style='font-size:13.5px; font-weight:800; color:#cbd5e1;'>0</div>"
                        f"<div style='font-size:9.5px; color:#e2e8f0;'>0 min</div>"
                        f"</td>"
                    )

                # Cella N Match
                n_match_m = len(df_m[df_m['Tipologia Sessione'].astype(str).str.strip().str.lower() == 'match'])
                if n_match_m > 0:
                    cell_match_html = f"<td style='padding:8px 8px; text-align:center; background:#fffafa; font-size:16px; font-weight:900; color:#ef4444;'>{n_match_m}</td>"
                else:
                    cell_match_html = f"<td style='padding:8px 8px; text-align:center; background:#fffafa; font-size:13.5px; font-weight:800; color:#cbd5e1;'>0</td>"

                rows_dist_html += (
                    f"<tr style='border-bottom:1px solid #f1f5f9;'>"
                    f"{m_cell_html}"
                    f"{cells_surf_html}"
                    f"{cells_tipo_html}"
                    f"{cell_sp_html}"
                    f"{cell_match_html}"
                    f"</tr>"
                )

            # Riga Totale Stagione (in basso)
            cells_tot_surf = ""
            for idx_s, s in enumerate(surfaces_cols):
                is_last_s = (idx_s == len(surfaces_cols) - 1)
                sep_s = "border-right:3px solid #0284c7;" if is_last_s else "border-right:1px solid #bae6fd;"
                s_tot_m = surface_season_min.get(s, 0.0)
                pct_s_tot = (s_tot_m / tot_season_min * 100) if tot_season_min > 0 else 0.0
                fill_h = min(max(pct_s_tot, 6.0), 100.0) if pct_s_tot > 0 else 0.0
                fill_div = f"<div style='width:100%; height:{fill_h:.0f}%; background:linear-gradient(180deg, #f59e0b 0%, #fbbf24 100%); opacity:0.95;'></div>" if pct_s_tot > 0 else ""
                cells_tot_surf += (
                    f"<td style='padding:8px 4px; text-align:center; background:#fef9ee; {sep_s}'>"
                    f"<div style='font-size:9.5px; font-weight:800; color:#92400e; margin-bottom:2px;'>{s}</div>"
                    f"<div style='width:46px; height:36px; border:1px solid #fde68a; border-radius:4px; background:#ffffff; position:relative; overflow:hidden; display:flex; flex-direction:column; justify-content:flex-end; margin:0 auto;'>"
                    f"{fill_div}"
                    f"<span style='position:absolute; width:100%; height:100%; top:0; left:0; display:flex; align-items:center; justify-content:center; font-size:11.5px; font-weight:900; color:#0f172a;'>{pct_s_tot:.0f}%</span>"
                    f"</div>"
                    f"</td>"
                )

            cells_tot_tipo = ""
            for idx_t, t in enumerate(tipologie_cols):
                is_last_t = (idx_t == len(tipologie_cols) - 1)
                sep_t = "border-right:3px solid #0284c7;" if is_last_t else "border-right:1px solid #bae6fd;"
                t_tot_m = tipo_season_min.get(t, 0.0)
                pct_t_tot = (t_tot_m / tot_season_min * 100) if tot_season_min > 0 else 0.0
                fill_h = min(max(pct_t_tot, 6.0), 100.0) if pct_t_tot > 0 else 0.0
                fill_div = f"<div style='width:100%; height:{fill_h:.0f}%; background:linear-gradient(180deg, #0284c7 0%, #38bdf8 100%); opacity:0.95;'></div>" if pct_t_tot > 0 else ""
                cells_tot_tipo += (
                    f"<td style='padding:8px 4px; text-align:center; background:#f0f9ff; {sep_t}'>"
                    f"<div style='font-size:9.5px; font-weight:800; color:#0369a1; margin-bottom:2px;'>{t}</div>"
                    f"<div style='width:46px; height:36px; border:1px solid #bae6fd; border-radius:4px; background:#ffffff; position:relative; overflow:hidden; display:flex; flex-direction:column; justify-content:flex-end; margin:0 auto;'>"
                    f"{fill_div}"
                    f"<span style='position:absolute; width:100%; height:100%; top:0; left:0; display:flex; align-items:center; justify-content:center; font-size:11.5px; font-weight:900; color:#0f172a;'>{pct_t_tot:.0f}%</span>"
                    f"</div>"
                    f"</td>"
                )

            rows_dist_html += (
                f"<tr style='border-top:2.5px solid #0284c7; font-family:\"Inter\",sans-serif;'>"
                f"<td style='padding:12px 8px; text-align:center; font-weight:900; color:#0284c7; font-size:12px; text-transform:uppercase; border-right:2.5px solid #cbd5e1; background:#f0f9ff; white-space:nowrap;'>TOTALE<br>ANNO</td>"
                f"{cells_tot_surf}"
                f"{cells_tot_tipo}"
                f"<td style='padding:10px 8px; text-align:center; border-right:2.5px solid #cbd5e1; background:#faf8ff; white-space:nowrap;'>"
                f"<div style='font-size:15px; font-weight:900; color:#6b21a8;'>{str_sp_tot}</div>"
                f"<div style='font-size:10px; font-weight:800; color:#7e22ce;'>{int(round(tot_season_sparring_min))} min</div>"
                f"</td>"
                f"<td style='padding:10px 8px; text-align:center; font-size:18px; font-weight:900; color:#ef4444; background:#fffafa;'>{tot_season_matches}</td>"
                f"</tr>"
            )

            # Sotto-intestazioni di colonna (Row 2 thead)
            subheaders_surf_html = ""
            for idx_s, s in enumerate(surfaces_cols):
                is_last_s = (idx_s == len(surfaces_cols) - 1)
                b_s = "border-right:3px solid #0284c7;" if is_last_s else "border-right:1px solid #fde68a;"
                subheaders_surf_html += f"<th style='text-align:center; padding:7px 4px; background:#fef3c7; color:#92400e; font-size:11px; font-weight:900; text-transform:uppercase; {b_s}'>{s}</th>"

            subheaders_tipo_html = ""
            for idx_t, t in enumerate(tipologie_cols):
                is_last_t = (idx_t == len(tipologie_cols) - 1)
                b_t = "border-right:3px solid #0284c7;" if is_last_t else "border-right:1px solid #bae6fd;"
                subheaders_tipo_html += f"<th style='text-align:center; padding:7px 4px; background:#e0f2fe; color:#0369a1; font-size:11px; font-weight:900; text-transform:uppercase; {b_t}'>{t}</th>"

            # Header colgroup & layout width
            min_tbl_w = max(960, 70 + len(surfaces_cols)*54 + len(tipologie_cols)*54 + 115 + 85)

            table_dist_html = (
                f"<div style='background:#ffffff; border-radius:14px; border:1px solid #e2e8f0; box-shadow:0 4px 14px -2px rgba(15,23,42,0.06); overflow:hidden; margin-bottom:24px; font-family:\"Inter\",sans-serif;'>"
                f"<div style='background:linear-gradient(135deg, #0f172a 0%, #1e293b 100%); padding:13px 20px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;'>"
                f"<span style='color:#ffffff; font-size:13.5px; font-weight:800; text-transform:uppercase; letter-spacing:0.06em;'><i class='bi bi-calendar3' style='color:#38bdf8; margin-right:8px;'></i>{tr('TIMELINE STAGIONE — DISTRIBUZIONE DEL LAVORO', 'SEASON TIMELINE — WORKLOAD DISTRIBUTION')}</span>"
                f"<span style='color:#38bdf8; font-size:12px; font-weight:700;'>{giocatore_selezionato} · {stagione_sel}</span>"
                f"</div>"
                f"<div style='overflow-x:auto; width:100%; -webkit-overflow-scrolling:touch;'>"
                f"<table style='width:100%; border-collapse:collapse; min-width:{min_tbl_w}px;'>"
                f"<thead>"
                f"<tr>"
                f"<th rowspan='2' style='text-align:center; padding:12px 10px; vertical-align:middle; background:#0f172a; color:#ffffff; font-size:12px; font-weight:900; text-transform:uppercase; border-right:2.5px solid #475569; width:65px;'>Mese</th>"
                f"<th colspan='{len(surfaces_cols)}' style='text-align:center; padding:9px 6px; background:#1e293b; color:#fbbf24; font-size:11.5px; font-weight:900; text-transform:uppercase; letter-spacing:0.05em; border-right:3px solid #0284c7;'><i class='bi bi-layers-fill' style='margin-right:6px;'></i>{tr('Superfici di Gioco', 'Court Surfaces')}</th>"
                f"<th colspan='{len(tipologie_cols)}' style='text-align:center; padding:9px 6px; background:#1e293b; color:#38bdf8; font-size:11.5px; font-weight:900; text-transform:uppercase; letter-spacing:0.05em; border-right:3px solid #0284c7;'><i class='bi bi-pie-chart-fill' style='margin-right:6px;'></i>{tr('Distribuzione del Lavoro (Tipologie)', 'Workload Distribution (Types)')}</th>"
                f"<th rowspan='2' style='text-align:center; padding:12px 10px; vertical-align:middle; background:#0f172a; color:#ffffff; font-size:12px; font-weight:900; text-transform:uppercase; border-right:2.5px solid #475569; width:110px;'><i class='bi bi-stopwatch' style='color:#a855f7; margin-right:4px;'></i>T Sparring</th>"
                f"<th rowspan='2' style='text-align:center; padding:12px 10px; vertical-align:middle; background:#0f172a; color:#ffffff; font-size:12px; font-weight:900; text-transform:uppercase; width:85px;'><i class='bi bi-trophy-fill' style='color:#ef4444; margin-right:4px;'></i>N Match</th>"
                f"</tr>"
                f"<tr>"
                f"{subheaders_surf_html}"
                f"{subheaders_tipo_html}"
                f"</tr>"
                f"</thead>"
                f"<tbody>{rows_dist_html}</tbody>"
                f"</table></div></div>"
            )
            st.html(table_dist_html)

            # -----------------------------------------------------------------
            # GRAFICI A CIAMBELLA / TORTA DI RIEPILOGO STAGIONALE
            # -----------------------------------------------------------------
            st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
            col_pie1, col_pie2 = st.columns(2)

            with col_pie1:
                with st.container(border=True):
                    st.markdown(
                        render_executive_chart_header(
                            tr("Riepilogo Stagionale Superfici", "Season Surfaces Summary"),
                            pills=[
                                (tr("Superfici Attive", "Active Surfaces"), f"{sum(1 for v in surface_season_min.values() if v > 0)}", "#f59e0b"),
                                (tr("Tempo Totale", "Total Time"), f"{tot_season_min/60:.1f}h", "#38bdf8")
                            ],
                            accent="#f59e0b"
                        ),
                        unsafe_allow_html=True
                    )

                    surf_pie_labels = []
                    surf_pie_values = []
                    surf_pie_texts = []
                    surf_pie_colors = []
                    
                    # Palette Superfici garantita senza duplicati
                    surf_palette_canonical = {
                        "hard": "#0ea5e9",   # Azzurro intenso (Cemento)
                        "clay": "#ea580c",   # Arancio terracotta (Terra)
                        "grass": "#16a34a",  # Verde prato (Erba)
                        "indoor": "#8b5cf6"  # Viola
                    }
                    extra_surf_palette = ["#f59e0b", "#ec4899", "#06b6d4", "#64748b", "#84cc16"]
                    used_surf_colors = set()

                    for s in surfaces_cols:
                        s_min = surface_season_min.get(s, 0.0)
                        if s_min > 0:
                            surf_pie_labels.append(s)
                            surf_pie_values.append(s_min)
                            surf_pie_texts.append(f"{int(s_min//60)}h {int(s_min%60):02d}m")
                            
                            c = surf_palette_canonical.get(s.lower())
                            if not c or c in used_surf_colors:
                                # Trova il primo colore libero dalla palette extra
                                c = next((col for col in extra_surf_palette if col not in used_surf_colors), None)
                                if not c:
                                    c = f"hsl({(len(used_surf_colors)*67) % 360}, 75%, 50%)"
                            
                            used_surf_colors.add(c)
                            surf_pie_colors.append(c)

                    if surf_pie_values:
                        fig_surf = go.Figure(data=[go.Pie(
                            labels=surf_pie_labels,
                            values=surf_pie_values,
                            customdata=surf_pie_texts,
                            hole=0.58,
                            marker=dict(colors=surf_pie_colors, line=dict(color='#ffffff', width=2)),
                            textinfo='label+percent',
                            textposition='outside',
                            hovertemplate="<b>%{label}</b><br>Tempo: %{customdata}<br>Percentuale: %{percent:.1%}<extra></extra>"
                        )])
                        fig_surf.update_layout(
                            margin=dict(l=20, r=20, t=25, b=25),
                            height=340,
                            showlegend=True,
                            legend=dict(orientation="h", yanchor="bottom", y=-0.15, xanchor="center", x=0.5),
                            annotations=[dict(
                                text=f"<b>{tot_season_min/60:.0f}h</b><br><span style='font-size:10px; color:#64748b;'>{tr('TEMPO TOTALE', 'TOTAL TIME')}</span>",
                                x=0.5, y=0.5, font_size=17, showarrow=False
                            )]
                        )
                        st.plotly_chart(fig_surf, use_container_width=True)
                    else:
                        st.info(tr("Nessun dato di superficie disponibile per questa stagione.", "No surface data available for this season."))

            with col_pie2:
                with st.container(border=True):
                    st.markdown(
                        render_executive_chart_header(
                            tr("Riepilogo Stagionale Tipologie", "Season Session Types Summary"),
                            pills=[
                                (tr("Tipologie Attive", "Active Types"), f"{sum(1 for v in tipo_season_min.values() if v > 0)}", "#0284c7"),
                                (tr("N° Sessioni", "Sessions Count"), f"{tot_sess_stagione}", "#ef4444")
                            ],
                            accent="#0284c7"
                        ),
                        unsafe_allow_html=True
                    )

                    tipo_pie_labels = []
                    tipo_pie_values = []
                    tipo_pie_texts = []
                    tipo_pie_colors = []

                    # Palette canonica tipologie (Allineata alle 10 tipologie ufficiali M0V3)
                    tipo_palette_canonical = {
                        "match": "#ef4444",         # Rosso Match
                        "match doppio": "#ea580c",  # Arancio Doppio
                        "torneo": "#f59e0b",        # Ambra Torneo
                        "tennis base": "#0ea5e9",   # Sky Blue Tennis Base
                        "1000 palle": "#0d9488",    # Teal 1000 Palle
                        "tennis match": "#6366f1",  # Indaco Tennis Match
                        "500 palle": "#8b5cf6",     # Viola 500 Palle
                        "servizio": "#0891b2",      # Cyan Servizio
                        "workout": "#10b981",       # Verde Smeraldo Workout
                        "calcio": "#84cc16",        # Lime Calcio
                    }
                    # Colori unici e differenziati per qualsiasi altra tipologia personalizzata
                    distinct_fallback_hues = [
                        "#f59e0b",  # Ambra / Giallo caldo (es. PROVA)
                        "#ec4899",  # Magenta / Fucsia
                        "#84cc16",  # Lime acceso
                        "#0284c7",  # Sky Blue
                        "#d97706",  # Ocra
                        "#e11d48",  # Cremisi
                        "#64748b",  # Slate
                        "#a21caf"   # Fucsia scuro
                    ]
                    used_tipo_colors = set()

                    for t in tipologie_cols:
                        t_min = tipo_season_min.get(t, 0.0)
                        if t_min > 0:
                            tipo_pie_labels.append(t)
                            tipo_pie_values.append(t_min)
                            tipo_pie_texts.append(f"{int(t_min//60)}h {int(t_min%60):02d}m")
                            
                            c = tipo_palette_canonical.get(t.lower())
                            if not c or c in used_tipo_colors:
                                c = next((col for col in distinct_fallback_hues if col not in used_tipo_colors), None)
                                if not c:
                                    c = f"hsl({(len(used_tipo_colors)*59 + 25) % 360}, 80%, 48%)"
                            
                            used_tipo_colors.add(c)
                            tipo_pie_colors.append(c)

                    if tipo_pie_values:
                        fig_tipo = go.Figure(data=[go.Pie(
                            labels=tipo_pie_labels,
                            values=tipo_pie_values,
                            customdata=tipo_pie_texts,
                            hole=0.58,
                            marker=dict(colors=tipo_pie_colors, line=dict(color='#ffffff', width=2)),
                            textinfo='label+percent',
                            textposition='outside',
                            hovertemplate="<b>%{label}</b><br>Tempo: %{customdata}<br>Percentuale: %{percent:.1%}<extra></extra>"
                        )])
                        fig_tipo.update_layout(
                            margin=dict(l=20, r=20, t=25, b=25),
                            height=340,
                            showlegend=True,
                            legend=dict(orientation="h", yanchor="bottom", y=-0.15, xanchor="center", x=0.5),
                            annotations=[dict(
                                text=f"<b>{tot_sess_stagione}</b><br><span style='font-size:10px; color:#64748b;'>{tr('SESSIONI', 'SESSIONS')}</span>",
                                x=0.5, y=0.5, font_size=17, showarrow=False
                            )]
                        )
                        st.plotly_chart(fig_tipo, use_container_width=True)
                    else:
                        st.info(tr("Nessun dato di tipologia sessione disponibile per questa stagione.", "No session type data available for this season."))

    # -------------------------------------------------------------------------
    # TAB 7: MONOTONIA STAGIONALE (INDICE DI FOSTER — TL HIGH & VOLUME)
    # -------------------------------------------------------------------------
    elif active_tab == T_MONO:
        if "Monotonia Stagionale" not in report_abilitati:
            st.info(tr("Il modulo 'Monotonia Stagionale' non è abilitato per questo account. Contatta l'amministratore.", "The 'Seasonal Monotony' module is not enabled for this account. Contact admin."))
        else:
            st.markdown(f"#### <i class='bi bi-speedometer2' style='color:#ef4444; margin-right:8px;'></i>{tr('Monotonia Stagionale (Indice di Foster)', 'Seasonal Monotony (Foster Index)')} — {stagione_sel}", unsafe_allow_html=True)
            st.caption(tr(
                "Misura la variabilità del carico di allenamento su finestre fisse di 7 giorni (Lunedì-Domenica), includendo i giorni di riposo (valore 0). Metrica primaria su Training Load High (Intensità). Valori < 2.0 indicano un microciclo ottimale e bilanciato; valori > 2.0 segnalano un carico monotono con alto rischio di sovrallenamento e infortunio.",
                "Measures training load variability over fixed 7-day windows (Monday-Sunday), including rest days (value 0). Primary metric on Training Load High (Intensity). Values < 2.0 indicate an optimal balanced microcycle; values > 2.0 flag a flat monotone load with high overtraining and injury risk."
            ))

            min_w_start = df_season['Week_Start_Date'].min()
            max_w_start = df_season['Week_Start_Date'].max()

            curr_monday = min_w_start
            all_season_mondays = []
            while curr_monday <= max_w_start:
                all_season_mondays.append(curr_monday)
                curr_monday += timedelta(days=7)

            col_tlh = 'TL_High' if 'TL_High' in df_season.columns else ('Training Load High' if 'Training Load High' in df_season.columns else None)

            mono_season_data = []
            for w_start in all_season_mondays:
                w_end = w_start + timedelta(days=6)
                w_num = pd.to_datetime(w_start).isocalendar()[1]
                w_lbl = f"{w_start.strftime('%d/%m')}"
                w_full_lbl = f"Sett. {w_num:02d} ({w_start.strftime('%d/%m')} - {w_end.strftime('%d/%m')})"

                tlh_days = []
                tl_days = []
                n_sessions_w = 0

                for d_idx in range(7):
                    d_target = w_start + timedelta(days=d_idx)
                    df_d = df_season[df_season['Date_obj'].dt.date == d_target]
                    if not df_d.empty:
                        val_tlh = float(df_d[col_tlh].sum()) if col_tlh and col_tlh in df_d.columns else 0.0
                        val_tl = float(df_d['Training Load'].sum()) if 'Training Load' in df_d.columns else 0.0
                        n_sessions_w += len(df_d)
                    else:
                        val_tlh = 0.0
                        val_tl = 0.0
                    tlh_days.append(val_tlh)
                    tl_days.append(val_tl)

                # Calcolo Monotonia TL High (Intensità)
                tot_tlh_w = sum(tlh_days)
                mean_tlh_w = tot_tlh_w / 7.0
                std_tlh_w = float(np.std(tlh_days, ddof=1)) if len(tlh_days) > 1 else 0.0

                if tot_tlh_w <= 0:
                    mono_tlh = 0.0
                elif std_tlh_w <= 0:
                    mono_tlh = 3.5
                else:
                    mono_tlh = round(mean_tlh_w / std_tlh_w, 2)

                # Calcolo Monotonia Training Load Totale (Volume)
                tot_tl_w = sum(tl_days)
                mean_tl_w = tot_tl_w / 7.0
                std_tl_w = float(np.std(tl_days, ddof=1)) if len(tl_days) > 1 else 0.0

                if tot_tl_w <= 0:
                    mono_tl = 0.0
                elif std_tl_w <= 0:
                    mono_tl = 3.5
                else:
                    mono_tl = round(mean_tl_w / std_tl_w, 2)

                mono_season_data.append({
                    "w_start": w_start,
                    "w_end": w_end,
                    "w_lbl": w_lbl,
                    "full_label": w_full_lbl,
                    "mono_tlh": mono_tlh,
                    "mono_tl": mono_tl,
                    "tot_tlh": tot_tlh_w,
                    "tot_tl": tot_tl_w,
                    "mean_tlh": mean_tlh_w,
                    "std_tlh": std_tlh_w,
                    "mean_tl": mean_tl_w,
                    "std_tl": std_tl_w,
                    "num_sessions": n_sessions_w
                })

            # Metriche KPI Executive
            active_weeks = [p for p in mono_season_data if p['tot_tlh'] > 0 or p['tot_tl'] > 0]
            valid_mono = [p['mono_tlh'] for p in active_weeks]
            last_mono = valid_mono[-1] if valid_mono else 0.0
            avg_mono = (sum(valid_mono) / len(valid_mono)) if valid_mono else 0.0
            n_ottimale = sum(1 for v in valid_mono if v < 2.0)
            pct_ottimale = (n_ottimale / len(valid_mono) * 100) if valid_mono else 100.0
            n_allarme = sum(1 for v in valid_mono if v >= 2.0)

            last_is_alarm = (last_mono >= 2.0)
            last_badge_col = "#ef4444" if last_is_alarm else "#10b981"
            last_badge_bg = "#fee2e2" if last_is_alarm else "#dcfce7"
            last_badge_txt = tr("Allarme (> 2.0)", "Alarm (> 2.0)") if last_is_alarm else tr("Bilanciato (< 2.0)", "Balanced (< 2.0)")

            mk1, mk2, mk3, mk4 = st.columns(4)
            with mk1:
                st.markdown(
                    card_kpi(
                        tr("Ultima Monotonia (TL High)", "Latest Monotony (TL High)"),
                        f"<span style='font-size:24px; font-weight:900; color:{last_badge_col};'>{last_mono:.2f}</span>",
                        f"<span style='background:{last_badge_bg}; color:{last_badge_col}; font-weight:700; padding:2px 8px; border-radius:4px; font-size:11px;'>{last_badge_txt}</span>",
                        last_badge_col
                    ),
                    unsafe_allow_html=True
                )
            with mk2:
                st.markdown(
                    card_kpi(
                        tr("Media Stagione (TL High)", "Season Mean (TL High)"),
                        f"<span style='font-size:24px; font-weight:900; color:#0f172a;'>{avg_mono:.2f}</span>",
                        f"{tr('Su', 'Across')} {len(valid_mono)} {tr('settimane con carico', 'active weeks')}",
                        "#0ea5e9"
                    ),
                    unsafe_allow_html=True
                )
            with mk3:
                st.markdown(
                    card_kpi(
                        tr("Microcicli Bilanciati (< 2.0)", "Balanced Microcycles (< 2.0)"),
                        f"<span style='font-size:24px; font-weight:900; color:#10b981;'>{pct_ottimale:.0f}%</span>",
                        f"{n_ottimale} {tr('su', 'of')} {len(valid_mono)} {tr('settimane in range ottimale', 'weeks in optimal range')}",
                        "#10b981"
                    ),
                    unsafe_allow_html=True
                )
            with mk4:
                st.markdown(
                    card_kpi(
                        tr("Settimane Allarme (> 2.0)", "Alarm Weeks (> 2.0)"),
                        f"<span style='font-size:24px; font-weight:900; color:{'#ef4444' if n_allarme > 0 else '#10b981'};'>{n_allarme}</span>",
                        tr("Rischio sovraccarico / piatto", "Overuse / flat load risk"),
                        "#ef4444" if n_allarme > 0 else "#10b981"
                    ),
                    unsafe_allow_html=True
                )

            st.markdown("<div style='margin-top: 18px;'></div>", unsafe_allow_html=True)

            # Selettore Modalità di Visualizzazione Grafico (Opzione A)
            c_sel_m, _ = st.columns([3, 1])
            with c_sel_m:
                mode_labels = [
                    tr("Training Load High (Intensità) — Consigliato", "Training Load High (Intensity) — Recommended"),
                    tr("Training Load Totale (Volume)", "Total Training Load (Volume)"),
                    tr("Sovrapposizione (Entrambi)", "Overlay (Both)")
                ]
                sel_mono_mode = st.radio(
                    tr("Seleziona Metrica Monotonia da visualizzare:", "Select Monotony Metric to display:"),
                    options=mode_labels,
                    index=0,
                    horizontal=True,
                    key="radio_mono_mode"
                )

            # Costruzione Grafico Plotly Executive a Soglie (Foster)
            x_labels = [p['w_lbl'] for p in mono_season_data]
            y_tlh = [p['mono_tlh'] for p in mono_season_data]
            y_tl = [p['mono_tl'] for p in mono_season_data]

            hover_tlh = []
            hover_tl = []
            for p in mono_season_data:
                st_tlh = tr("[ALLARME] (> 2.0)", "[ALARM] (> 2.0)") if p['mono_tlh'] >= 2.0 else tr("[OTTIMALE] (< 2.0)", "[OPTIMAL] (< 2.0)")
                st_tl = tr("[ALLARME] (> 2.0)", "[ALARM] (> 2.0)") if p['mono_tl'] >= 2.0 else tr("[OTTIMALE] (< 2.0)", "[OPTIMAL] (< 2.0)")

                hover_tlh.append(
                    f"<b>{p['full_label']}</b><br>"
                    f"Monotonia TL High: <b>{p['mono_tlh']:.2f}</b><br>"
                    f"Stato: <b>{st_tlh}</b><br>"
                    f"TL High Settimanale: <b>{int(round(p['tot_tlh'])):,} AU</b> ({p['num_sessions']} sess.)<br>"
                    f"Media Giornaliera (μ): <b>{p['mean_tlh']:.1f}</b> · Dev.Std (σ): <b>{p['std_tlh']:.1f}</b>"
                )
                hover_tl.append(
                    f"<b>{p['full_label']}</b><br>"
                    f"Monotonia TL Volume: <b>{p['mono_tl']:.2f}</b><br>"
                    f"Stato: <b>{st_tl}</b><br>"
                    f"Training Load Settimanale: <b>{int(round(p['tot_tl'])):,} TL</b> ({p['num_sessions']} sess.)<br>"
                    f"Media Giornaliera (μ): <b>{p['mean_tl']:.1f}</b> · Dev.Std (σ): <b>{p['std_tl']:.1f}</b>"
                )

            fig_mono = go.Figure()

            # Fascia Ottimale Verde (< 2.0)
            max_y_val = max(max(y_tlh + y_tl + [2.5]), 3.5)
            fig_mono.add_shape(
                type="rect",
                x0=-0.5,
                x1=len(x_labels) - 0.5,
                y0=0,
                y1=2.0,
                fillcolor="rgba(16, 185, 129, 0.08)",
                line=dict(width=0),
                layer="below"
            )

            # Linea tratteggiata di soglia allarme a 2.0
            fig_mono.add_shape(
                type="line",
                x0=-0.5,
                x1=len(x_labels) - 0.5,
                y0=2.0,
                y1=2.0,
                line=dict(color="#ef4444", width=2, dash="dash"),
                layer="above"
            )

            fig_mono.add_annotation(
                x=0.01,
                y=2.0,
                xref="paper",
                yref="y",
                text="<b>SOGLIA ALLARME FOSTER (2.0)</b>",
                showarrow=False,
                font=dict(color="#b91c1c", size=10),
                bgcolor="rgba(254, 226, 226, 0.9)",
                bordercolor="#ef4444",
                borderwidth=1,
                borderpad=3,
                xanchor="left",
                yanchor="bottom"
            )

            fig_mono.add_annotation(
                x=0.01,
                y=0.15,
                xref="paper",
                yref="y",
                text="<b>ZONA OTTIMALE / MICROCICLO BILANCIATO (&lt; 2.0)</b>",
                showarrow=False,
                font=dict(color="#15803d", size=10),
                bgcolor="rgba(220, 252, 231, 0.8)",
                bordercolor="#10b981",
                borderwidth=1,
                borderpad=3,
                xanchor="left",
                yanchor="bottom"
            )

            # Aggiunta Tracce in base alla modalità selezionata
            show_tlh = (sel_mono_mode == mode_labels[0] or sel_mono_mode == mode_labels[2])
            show_tl = (sel_mono_mode == mode_labels[1] or sel_mono_mode == mode_labels[2])

            if show_tlh:
                marker_colors_tlh = ["#ef4444" if v >= 2.0 else "#10b981" for v in y_tlh]
                marker_sizes_tlh = [11 if v >= 2.0 else 8 for v in y_tlh]

                fig_mono.add_trace(go.Scatter(
                    x=x_labels,
                    y=y_tlh,
                    mode="lines+markers",
                    name=tr("Monotonia TL High (Intensità)", "TL High Monotony (Intensity)"),
                    line=dict(color="#ef4444", width=3, shape="spline", smoothing=0.3),
                    marker=dict(color=marker_colors_tlh, size=marker_sizes_tlh, line=dict(color="#ffffff", width=2)),
                    hoverinfo="text",
                    hovertext=hover_tlh
                ))

            if show_tl:
                marker_colors_tl = ["#ef4444" if v >= 2.0 else "#0284c7" for v in y_tl]
                marker_sizes_tl = [11 if v >= 2.0 else 8 for v in y_tl]

                fig_mono.add_trace(go.Scatter(
                    x=x_labels,
                    y=y_tl,
                    mode="lines+markers",
                    name=tr("Monotonia Training Load (Volume)", "Training Load Monotony (Volume)"),
                    line=dict(color="#0284c7", width=2.5, shape="spline", smoothing=0.3, dash="dot" if show_tlh else "solid"),
                    marker=dict(color=marker_colors_tl, size=marker_sizes_tl, line=dict(color="#ffffff", width=2)),
                    hoverinfo="text",
                    hovertext=hover_tl
                ))

            fig_mono.update_layout(
                margin=dict(l=40, r=40, t=25, b=40),
                height=420,
                xaxis=dict(
                    title=tr("Settimana di Calendario (Data Lunedì)", "Calendar Week (Monday Date)"),
                    tickangle=-45,
                    gridcolor="#f1f5f9",
                    linecolor="#cbd5e1",
                    tickfont=dict(size=11, color="#475569")
                ),
                yaxis=dict(
                    title=tr("Indice di Monotonia (μ / σ)", "Monotony Index (μ / σ)"),
                    range=[0, max_y_val],
                    gridcolor="#f1f5f9",
                    linecolor="#cbd5e1",
                    tickfont=dict(size=11, color="#475569")
                ),
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1.0
                ),
                hoverlabel=dict(bgcolor="#0f172a", font_color="#ffffff", font_size=12)
            )

            with st.container(border=True):
                pills_mono = [
                    (tr("Ultima Settimana", "Last Week"), f"{last_mono:.2f}", last_badge_col),
                    (tr("Soglia Allarme", "Alarm Threshold"), "2.00", "#ef4444")
                ]
                st.markdown(
                    render_executive_chart_header(
                        tr("Andamento Stagionale Indice di Monotonia — Foster", "Seasonal Monotony Trend — Foster"),
                        pills=pills_mono,
                        accent="#ef4444"
                    ),
                    unsafe_allow_html=True
                )
                st.plotly_chart(fig_mono, use_container_width=True)

            # Tabella Dettagliata Settimana per Settimana
            with st.expander(tr("Tabella Dettagliata Monotonia Stagionale", "Detailed Seasonal Monotony Table")):
                tab_mono_rows = []
                for p in reversed(mono_season_data):
                    st_tlh_str = "[ALLARME] (> 2.0)" if p['mono_tlh'] >= 2.0 else ("[OTTIMALE]" if p['mono_tlh'] > 0 else "-")
                    st_tl_str = "[ALLARME] (> 2.0)" if p['mono_tl'] >= 2.0 else ("[OTTIMALE]" if p['mono_tl'] > 0 else "-")
                    tab_mono_rows.append({
                        tr("Settimana", "Week"): p['full_label'],
                        tr("Monotonia TL High", "TL High Monotony"): f"{p['mono_tlh']:.2f}" if p['mono_tlh'] > 0 else "-",
                        tr("Stato TL High", "TL High Status"): st_tlh_str,
                        tr("TL High Totale", "Total TL High"): f"{int(round(p['tot_tlh'])):,} AU" if p['tot_tlh'] > 0 else "-",
                        tr("Monotonia Volume TL", "TL Volume Monotony"): f"{p['mono_tl']:.2f}" if p['mono_tl'] > 0 else "-",
                        tr("Stato Volume", "Volume Status"): st_tl_str,
                        tr("Training Load Totale", "Total Training Load"): f"{int(round(p['tot_tl'])):,} TL" if p['tot_tl'] > 0 else "-",
                        tr("Sessioni", "Sessions"): p['num_sessions']
                    })
                st.dataframe(pd.DataFrame(tab_mono_rows), use_container_width=True, hide_index=True)

            # Box Formativo / Informativo Foster (fedele al mockup)
            lbl_foster_title = tr("COS'E' L'INDICE MONOTONIA - Foster, C.", "WHAT IS THE MONOTONY INDEX - Foster, C.")
            lbl_foster_desc = tr("Misura la <b>variabilità del carico settimanale</b>, valutando l'alternanza tra sforzo e recupero.", "Measures <b>weekly workload variability</b>, assessing alternation between effort and recovery.")
            lbl_foster_ott = tr("Ottimale (&lt; 2.0):", "Optimal (&lt; 2.0):")
            lbl_foster_ott_desc = tr("Microciclo bilanciato, con veri picchi di intensità seguiti da un adeguato scarico.", "Balanced microcycle, with true intensity peaks followed by adequate recovery.")
            lbl_foster_all = tr("Allarme (&gt; 2.0):", "Alarm (&gt; 2.0):")
            lbl_foster_all_desc = tr("Settimana troppo \"piatta\" e senza vero riposo; alto rischio di infortuni da sovrallenamento.", "Week too \"flat\" and without true rest; high risk of overtraining injuries.")

            box_foster_html = (
                f"<div style='background:#f0f9ff; border:1px solid #bae6fd; border-radius:12px; padding:16px 20px; margin-top:20px; font-family:\"Inter\",sans-serif;'>"
                f"<div style='background:#0284c7; color:#ffffff; font-size:12.5px; font-weight:900; padding:4px 12px; border-radius:6px; display:inline-block; text-transform:uppercase; letter-spacing:0.05em; margin-bottom:10px;'>"
                f"{lbl_foster_title}"
                f"</div>"
                f"<div style='font-size:13px; color:#1e293b; line-height:1.6;'>"
                f"{lbl_foster_desc}<br>"
                f"• <b style='color:#15803d;'>{lbl_foster_ott}</b> {lbl_foster_ott_desc}<br>"
                f"• <b style='color:#b91c1c;'>{lbl_foster_all}</b> {lbl_foster_all_desc}"
                f"</div>"
                f"</div>"
            )
            st.html(box_foster_html)

    # -------------------------------------------------------------------------
    # TAB 8: STRAIN STAGIONALE (INDICE DI TENSIONE/STRESS — FOSTER)
    # -------------------------------------------------------------------------
    elif active_tab == T_STRAIN:
        if "Strain Stagionale" not in report_abilitati:
            st.info(tr("Il modulo 'Strain Stagionale' non è abilitato per questo account. Contatta l'amministratore.", "The 'Seasonal Strain' module is not enabled for this account. Contact admin."))
        else:
            st.markdown(f"#### <i class='bi bi-lightning-charge-fill' style='color:#f59e0b; margin-right:8px;'></i>{tr('Strain Stagionale (Indice di Tensione / Stress — Foster)', 'Seasonal Strain (Stress / Strain Index — Foster)')} — {stagione_sel}", unsafe_allow_html=True)
            st.caption(tr(
                "Quantifica lo stress psicofisico e biologico complessivo moltiplicando il carico settimanale per l'indice di monotonia (Strain = Carico Settimanale × Monotonia). Metrica primaria su Training Load High (Intensità). Quando carico e monotonia sono contemporaneamente elevati, lo Strain cresce in modo esponenziale segnalando picchi critici di affaticamento.",
                "Quantifies overall weekly psychophysical and biological stress by multiplying weekly load by monotony (Strain = Weekly Load × Monotony). Primary metric on Training Load High (Intensity). When both load and monotony are high, Strain spikes exponentially signaling critical fatigue peaks."
            ))

            min_w_start = df_season['Week_Start_Date'].min()
            max_w_start = df_season['Week_Start_Date'].max()

            curr_monday = min_w_start
            all_season_mondays = []
            while curr_monday <= max_w_start:
                all_season_mondays.append(curr_monday)
                curr_monday += timedelta(days=7)

            col_tlh = 'TL_High' if 'TL_High' in df_season.columns else ('Training Load High' if 'Training Load High' in df_season.columns else None)

            strain_season_data = []
            for w_start in all_season_mondays:
                w_end = w_start + timedelta(days=6)
                w_num = pd.to_datetime(w_start).isocalendar()[1]
                w_lbl = f"{w_start.strftime('%d/%m')}"
                w_full_lbl = f"Sett. {w_num:02d} ({w_start.strftime('%d/%m')} - {w_end.strftime('%d/%m')})"

                tlh_days = []
                tl_days = []
                n_sessions_w = 0

                for d_idx in range(7):
                    d_target = w_start + timedelta(days=d_idx)
                    df_d = df_season[df_season['Date_obj'].dt.date == d_target]
                    if not df_d.empty:
                        val_tlh = float(df_d[col_tlh].sum()) if col_tlh and col_tlh in df_d.columns else 0.0
                        val_tl = float(df_d['Training Load'].sum()) if 'Training Load' in df_d.columns else 0.0
                        n_sessions_w += len(df_d)
                    else:
                        val_tlh = 0.0
                        val_tl = 0.0
                    tlh_days.append(val_tlh)
                    tl_days.append(val_tl)

                # Monotonia & Strain TL High
                tot_tlh_w = sum(tlh_days)
                mean_tlh_w = tot_tlh_w / 7.0
                std_tlh_w = float(np.std(tlh_days, ddof=1)) if len(tlh_days) > 1 else 0.0

                if tot_tlh_w <= 0:
                    mono_tlh = 0.0
                    strain_tlh = 0.0
                elif std_tlh_w <= 0:
                    mono_tlh = 3.5
                    strain_tlh = round(tot_tlh_w * mono_tlh, 1)
                else:
                    mono_tlh = round(mean_tlh_w / std_tlh_w, 2)
                    strain_tlh = round(tot_tlh_w * mono_tlh, 1)

                # Monotonia & Strain Training Load Totale (Volume)
                tot_tl_w = sum(tl_days)
                mean_tl_w = tot_tl_w / 7.0
                std_tl_w = float(np.std(tl_days, ddof=1)) if len(tl_days) > 1 else 0.0

                if tot_tl_w <= 0:
                    mono_tl = 0.0
                    strain_tl = 0.0
                elif std_tl_w <= 0:
                    mono_tl = 3.5
                    strain_tl = round(tot_tl_w * mono_tl, 1)
                else:
                    mono_tl = round(mean_tl_w / std_tl_w, 2)
                    strain_tl = round(tot_tl_w * mono_tl, 1)

                strain_season_data.append({
                    "w_start": w_start,
                    "w_end": w_end,
                    "w_lbl": w_lbl,
                    "full_label": w_full_lbl,
                    "strain_tlh": strain_tlh,
                    "strain_tl": strain_tl,
                    "mono_tlh": mono_tlh,
                    "mono_tl": mono_tl,
                    "tot_tlh": tot_tlh_w,
                    "tot_tl": tot_tl_w,
                    "mean_tlh": mean_tlh_w,
                    "std_tlh": std_tlh_w,
                    "mean_tl": mean_tl_w,
                    "std_tl": std_tl_w,
                    "num_sessions": n_sessions_w
                })

            # Metriche KPI Executive
            active_strain_weeks = [p for p in strain_season_data if p['strain_tlh'] > 0 or p['strain_tl'] > 0]
            valid_strain_tlh = [p['strain_tlh'] for p in active_strain_weeks]
            last_strain = valid_strain_tlh[-1] if valid_strain_tlh else 0.0
            avg_strain = (sum(valid_strain_tlh) / len(valid_strain_tlh)) if valid_strain_tlh else 0.0
            max_strain = max(valid_strain_tlh) if valid_strain_tlh else 0.0
            peak_item = next((p for p in strain_season_data if p['strain_tlh'] == max_strain), None) if max_strain > 0 else None
            peak_week_lbl = peak_item['full_label'] if peak_item else "-"

            threshold_strain_alarm = avg_strain * 1.50 if avg_strain > 0 else 1000.0
            n_high_strain = sum(1 for v in valid_strain_tlh if v > threshold_strain_alarm)

            last_is_high = (last_strain > threshold_strain_alarm and last_strain > 0)
            last_badge_col = "#ef4444" if last_is_high else "#10b981"
            last_badge_bg = "#fee2e2" if last_is_high else "#dcfce7"
            last_badge_txt = tr("Tensione Elevata", "High Strain") if last_is_high else tr("Sotto Controllo", "Controlled")

            sk1, sk2, sk3, sk4 = st.columns(4)
            with sk1:
                st.markdown(
                    card_kpi(
                        tr("Ultimo Strain (TL High)", "Latest Strain (TL High)"),
                        f"<span style='font-size:24px; font-weight:900; color:{last_badge_col};'>{last_strain:,.0f} AU</span>",
                        f"<span style='background:{last_badge_bg}; color:{last_badge_col}; font-weight:700; padding:2px 8px; border-radius:4px; font-size:11px;'>{last_badge_txt}</span>",
                        last_badge_col
                    ),
                    unsafe_allow_html=True
                )
            with sk2:
                st.markdown(
                    card_kpi(
                        tr("Media Stagionale (TL High)", "Season Mean (TL High)"),
                        f"<span style='font-size:24px; font-weight:900; color:#0f172a;'>{avg_strain:,.0f} AU</span>",
                        f"{tr('Baseline di riferimento annuale', 'Annual reference baseline')}",
                        "#0ea5e9"
                    ),
                    unsafe_allow_html=True
                )
            with sk3:
                st.markdown(
                    card_kpi(
                        tr("Picco Massimo Stagionale", "Season Peak Strain"),
                        f"<span style='font-size:24px; font-weight:900; color:#ef4444;'>{max_strain:,.0f} AU</span>",
                        f"{peak_week_lbl}",
                        "#ef4444"
                    ),
                    unsafe_allow_html=True
                )
            with sk4:
                st.markdown(
                    card_kpi(
                        tr("Picchi Critici (> +50%)", "Critical Peaks (> +50%)"),
                        f"<span style='font-size:24px; font-weight:900; color:{'#ef4444' if n_high_strain > 0 else '#10b981'};'>{n_high_strain}</span>",
                        f"{tr('Settimane sopra soglia allerta', 'Weeks above alert threshold')} ({threshold_strain_alarm:,.0f} AU)",
                        "#ef4444" if n_high_strain > 0 else "#10b981"
                    ),
                    unsafe_allow_html=True
                )

            st.markdown("<div style='margin-top: 18px;'></div>", unsafe_allow_html=True)

            # Selettore Modalità Grafico Strain
            c_sel_str, _ = st.columns([3, 1])
            with c_sel_str:
                strain_mode_labels = [
                    tr("Strain TL High (Intensità) — Consigliato", "TL High Strain (Intensity) — Recommended"),
                    tr("Strain Training Load (Volume)", "Training Load Strain (Volume)"),
                    tr("Sovrapposizione (Entrambi)", "Overlay (Both)")
                ]
                sel_strain_mode = st.radio(
                    tr("Seleziona Metrica Strain da visualizzare:", "Select Strain Metric to display:"),
                    options=strain_mode_labels,
                    index=0,
                    horizontal=True,
                    key="radio_strain_mode"
                )

            # Calcolo metriche Volume per quando viene selezionato Volume o Sovrapposizione
            valid_strain_tl = [p['strain_tl'] for p in active_strain_weeks]
            last_strain_tl = valid_strain_tl[-1] if valid_strain_tl else 0.0
            avg_strain_tl = (sum(valid_strain_tl) / len(valid_strain_tl)) if valid_strain_tl else 0.0
            threshold_strain_tl_alarm = avg_strain_tl * 1.50 if avg_strain_tl > 0 else 5000.0

            # Costruzione Grafico Plotly Executive a Soglie per lo Strain
            x_labels_s = [p['w_lbl'] for p in strain_season_data]
            y_strain_tlh = [p['strain_tlh'] for p in strain_season_data]
            y_strain_tl = [p['strain_tl'] for p in strain_season_data]

            hover_strain_tlh = []
            hover_strain_tl = []
            for p in strain_season_data:
                is_alert_tlh = (p['strain_tlh'] > threshold_strain_alarm and p['strain_tlh'] > 0)
                st_tlh_str = tr("[ALLARME PICCO STRAIN]", "[ALARM STRAIN PEAK]") if is_alert_tlh else tr("[RANGE TOLLERABILE]", "[TOLERABLE RANGE]")

                hover_strain_tlh.append(
                    f"<b>{p['full_label']}</b><br>"
                    f"Strain TL High: <b>{p['strain_tlh']:,.0f} AU</b><br>"
                    f"Stato: <b>{st_tlh_str}</b><br>"
                    f"Carico TL High: <b>{int(round(p['tot_tlh'])):,} AU</b> · Monotonia: <b>{p['mono_tlh']:.2f}</b><br>"
                    f"Formula: {int(round(p['tot_tlh'])):,} AU × {p['mono_tlh']:.2f} ({p['num_sessions']} sess.)"
                )
                hover_strain_tl.append(
                    f"<b>{p['full_label']}</b><br>"
                    f"Strain Training Load: <b>{p['strain_tl']:,.0f} AU</b><br>"
                    f"Carico TL: <b>{int(round(p['tot_tl'])):,} TL</b> · Monotonia: <b>{p['mono_tl']:.2f}</b><br>"
                    f"Formula: {int(round(p['tot_tl'])):,} TL × {p['mono_tl']:.2f} ({p['num_sessions']} sess.)"
                )

            fig_strain = go.Figure()

            is_overlay_mode = (sel_strain_mode == strain_mode_labels[2])
            is_volume_only = (sel_strain_mode == strain_mode_labels[1])
            is_tlh_only = (sel_strain_mode == strain_mode_labels[0])

            # Calcolo dinamico dei range dell'asse Y per evitare l'appiattimento verso il basso
            max_tlh_active = max(y_strain_tlh + [threshold_strain_alarm * 1.15]) if y_strain_tlh else 500.0
            range_y_tlh = [0, max(max_tlh_active * 1.18, 500.0)]

            max_tl_active = max(y_strain_tl + [threshold_strain_tl_alarm * 1.15]) if y_strain_tl else 5000.0
            range_y_tl = [0, max(max_tl_active * 1.18, 5000.0)]

            if is_tlh_only:
                # Modalità Primaria TL High (scala ottimale su TL High)
                fig_strain.add_shape(
                    type="rect",
                    x0=-0.5,
                    x1=len(x_labels_s) - 0.5,
                    y0=0,
                    y1=threshold_strain_alarm,
                    fillcolor="rgba(16, 185, 129, 0.07)",
                    line=dict(width=0),
                    layer="below"
                )
                fig_strain.add_shape(
                    type="line",
                    x0=-0.5,
                    x1=len(x_labels_s) - 0.5,
                    y0=avg_strain,
                    y1=avg_strain,
                    line=dict(color="#0ea5e9", width=1.8, dash="dot"),
                    layer="above"
                )
                fig_strain.add_shape(
                    type="line",
                    x0=-0.5,
                    x1=len(x_labels_s) - 0.5,
                    y0=threshold_strain_alarm,
                    y1=threshold_strain_alarm,
                    line=dict(color="#ef4444", width=2, dash="dash"),
                    layer="above"
                )
                fig_strain.add_annotation(
                    x=0.01,
                    y=threshold_strain_alarm,
                    xref="paper",
                    yref="y",
                    text=f"<b>SOGLIA ALLARME PICCO (+50%): {threshold_strain_alarm:,.0f} AU</b>",
                    showarrow=False,
                    font=dict(color="#b91c1c", size=10),
                    bgcolor="rgba(254, 226, 226, 0.9)",
                    bordercolor="#ef4444",
                    borderwidth=1,
                    borderpad=3,
                    xanchor="left",
                    yanchor="bottom"
                )
                fig_strain.add_annotation(
                    x=0.01,
                    y=avg_strain,
                    xref="paper",
                    yref="y",
                    text=f"<b>MEDIA STAGIONALE (BASELINE): {avg_strain:,.0f} AU</b>",
                    showarrow=False,
                    font=dict(color="#0369a1", size=10),
                    bgcolor="rgba(224, 242, 254, 0.9)",
                    bordercolor="#0284c7",
                    borderwidth=1,
                    borderpad=3,
                    xanchor="left",
                    yanchor="top"
                )

                marker_colors_stlh = ["#ef4444" if (v > threshold_strain_alarm and v > 0) else ("#f59e0b" if v > avg_strain else "#10b981") for v in y_strain_tlh]
                marker_sizes_stlh = [11 if (v > threshold_strain_alarm and v > 0) else 8 for v in y_strain_tlh]

                fig_strain.add_trace(go.Scatter(
                    x=x_labels_s,
                    y=y_strain_tlh,
                    mode="lines+markers",
                    name=tr("Strain TL High (Intensità)", "TL High Strain (Intensity)"),
                    line=dict(color="#f59e0b", width=3, shape="spline", smoothing=0.3),
                    marker=dict(color=marker_colors_stlh, size=marker_sizes_stlh, line=dict(color="#ffffff", width=2)),
                    hoverinfo="text",
                    hovertext=hover_strain_tlh
                ))

                fig_strain.update_layout(
                    yaxis=dict(
                        title=tr("Strain TL High (Carico High × Monotonia) [AU]", "TL High Strain [AU]"),
                        range=range_y_tlh,
                        gridcolor="#f1f5f9",
                        linecolor="#cbd5e1",
                        tickfont=dict(size=11, color="#475569")
                    )
                )

            elif is_volume_only:
                # Modalità Training Load Totale (scala ottimale su Volume TL)
                fig_strain.add_shape(
                    type="rect",
                    x0=-0.5,
                    x1=len(x_labels_s) - 0.5,
                    y0=0,
                    y1=threshold_strain_tl_alarm,
                    fillcolor="rgba(16, 185, 129, 0.07)",
                    line=dict(width=0),
                    layer="below"
                )
                fig_strain.add_shape(
                    type="line",
                    x0=-0.5,
                    x1=len(x_labels_s) - 0.5,
                    y0=avg_strain_tl,
                    y1=avg_strain_tl,
                    line=dict(color="#0ea5e9", width=1.8, dash="dot"),
                    layer="above"
                )
                fig_strain.add_shape(
                    type="line",
                    x0=-0.5,
                    x1=len(x_labels_s) - 0.5,
                    y0=threshold_strain_tl_alarm,
                    y1=threshold_strain_tl_alarm,
                    line=dict(color="#ef4444", width=2, dash="dash"),
                    layer="above"
                )
                fig_strain.add_annotation(
                    x=0.01,
                    y=threshold_strain_tl_alarm,
                    xref="paper",
                    yref="y",
                    text=f"<b>SOGLIA ALLARME VOLUME (+50%): {threshold_strain_tl_alarm:,.0f} AU</b>",
                    showarrow=False,
                    font=dict(color="#b91c1c", size=10),
                    bgcolor="rgba(254, 226, 226, 0.9)",
                    bordercolor="#ef4444",
                    borderwidth=1,
                    borderpad=3,
                    xanchor="left",
                    yanchor="bottom"
                )
                fig_strain.add_annotation(
                    x=0.01,
                    y=avg_strain_tl,
                    xref="paper",
                    yref="y",
                    text=f"<b>MEDIA VOLUME (BASELINE): {avg_strain_tl:,.0f} AU</b>",
                    showarrow=False,
                    font=dict(color="#0369a1", size=10),
                    bgcolor="rgba(224, 242, 254, 0.9)",
                    bordercolor="#0284c7",
                    borderwidth=1,
                    borderpad=3,
                    xanchor="left",
                    yanchor="top"
                )

                marker_colors_stl = ["#ef4444" if (v > threshold_strain_tl_alarm and v > 0) else "#0284c7" for v in y_strain_tl]
                marker_sizes_stl = [11 if (v > threshold_strain_tl_alarm and v > 0) else 8 for v in y_strain_tl]

                fig_strain.add_trace(go.Scatter(
                    x=x_labels_s,
                    y=y_strain_tl,
                    mode="lines+markers",
                    name=tr("Strain Training Load (Volume)", "Training Load Strain (Volume)"),
                    line=dict(color="#0284c7", width=3, shape="spline", smoothing=0.3),
                    marker=dict(color=marker_colors_stl, size=marker_sizes_stl, line=dict(color="#ffffff", width=2)),
                    hoverinfo="text",
                    hovertext=hover_strain_tl
                ))

                fig_strain.update_layout(
                    yaxis=dict(
                        title=tr("Strain Volume (Carico Totale × Monotonia) [AU]", "Volume Strain [AU]"),
                        range=range_y_tl,
                        gridcolor="#f1f5f9",
                        linecolor="#cbd5e1",
                        tickfont=dict(size=11, color="#475569")
                    )
                )

            else:
                # Modalità Sovrapposizione: Doppio Asse Y indipendente (nessun appiattimento!)
                marker_colors_stlh = ["#ef4444" if (v > threshold_strain_alarm and v > 0) else ("#f59e0b" if v > avg_strain else "#10b981") for v in y_strain_tlh]
                marker_sizes_stlh = [11 if (v > threshold_strain_alarm and v > 0) else 8 for v in y_strain_tlh]

                marker_colors_stl = ["#ef4444" if (v > threshold_strain_tl_alarm and v > 0) else "#0284c7" for v in y_strain_tl]
                marker_sizes_stl = [11 if (v > threshold_strain_tl_alarm and v > 0) else 8 for v in y_strain_tl]

                fig_strain.add_trace(go.Scatter(
                    x=x_labels_s,
                    y=y_strain_tlh,
                    mode="lines+markers",
                    name=tr("Strain TL High (Intensità)", "TL High Strain (Intensity)"),
                    line=dict(color="#f59e0b", width=3, shape="spline", smoothing=0.3),
                    marker=dict(color=marker_colors_stlh, size=marker_sizes_stlh, line=dict(color="#ffffff", width=2)),
                    hoverinfo="text",
                    hovertext=hover_strain_tlh,
                    yaxis="y1"
                ))

                fig_strain.add_trace(go.Scatter(
                    x=x_labels_s,
                    y=y_strain_tl,
                    mode="lines+markers",
                    name=tr("Strain Training Load (Volume)", "Training Load Strain (Volume)"),
                    line=dict(color="#0284c7", width=2.5, shape="spline", smoothing=0.3, dash="dot"),
                    marker=dict(color=marker_colors_stl, size=marker_sizes_stl, line=dict(color="#ffffff", width=2)),
                    hoverinfo="text",
                    hovertext=hover_strain_tl,
                    yaxis="y2"
                ))

                fig_strain.update_layout(
                    yaxis=dict(
                        title=dict(text=tr("Strain TL High [AU]", "TL High Strain [AU]"), font=dict(color="#f59e0b")),
                        range=range_y_tlh,
                        tickfont=dict(size=11, color="#f59e0b"),
                        gridcolor="#f1f5f9",
                        linecolor="#cbd5e1"
                    ),
                    yaxis2=dict(
                        title=dict(text=tr("Strain Volume [AU]", "Volume Strain [AU]"), font=dict(color="#0284c7")),
                        range=range_y_tl,
                        tickfont=dict(size=11, color="#0284c7"),
                        overlaying="y",
                        side="right",
                        gridcolor="rgba(0,0,0,0)",
                        linecolor="#bae6fd"
                    )
                )

            fig_strain.update_layout(
                margin=dict(l=40, r=40, t=25, b=40),
                height=430,
                xaxis=dict(
                    title=tr("Settimana di Calendario (Data Lunedì)", "Calendar Week (Monday Date)"),
                    tickangle=-45,
                    gridcolor="#f1f5f9",
                    linecolor="#cbd5e1",
                    tickfont=dict(size=11, color="#475569")
                ),
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1.0
                ),
                hoverlabel=dict(bgcolor="#0f172a", font_color="#ffffff", font_size=12)
            )

            with st.container(border=True):
                if is_volume_only:
                    pills_strain = [
                        (tr("Ultima Settimana", "Last Week"), f"{last_strain_tl:,.0f} AU", "#0284c7"),
                        (tr("Media Stagionale (Volume)", "Season Mean (Volume)"), f"{avg_strain_tl:,.0f} AU", "#0ea5e9"),
                        (tr("Soglia Allarme (Volume)", "Alarm Threshold (Volume)"), f"{threshold_strain_tl_alarm:,.0f} AU", "#ef4444")
                    ]
                    acc_col = "#0284c7"
                elif is_overlay_mode:
                    pills_strain = [
                        (tr("Media TL High", "Mean TL High"), f"{avg_strain:,.0f} AU", "#f59e0b"),
                        (tr("Media TL Volume", "Mean TL Volume"), f"{avg_strain_tl:,.0f} AU", "#0284c7")
                    ]
                    acc_col = "#6366f1"
                else:
                    pills_strain = [
                        (tr("Ultima Settimana", "Last Week"), f"{last_strain:,.0f} AU", last_badge_col),
                        (tr("Media Stagionale (TL High)", "Season Mean (TL High)"), f"{avg_strain:,.0f} AU", "#0ea5e9"),
                        (tr("Soglia Allarme", "Alarm Threshold"), f"{threshold_strain_alarm:,.0f} AU", "#ef4444")
                    ]
                    acc_col = "#f59e0b"

                st.markdown(
                    render_executive_chart_header(
                        tr("Andamento Stagionale Indice di Strain — Foster", "Seasonal Strain Trend — Foster"),
                        pills=pills_strain,
                        accent=acc_col
                    ),
                    unsafe_allow_html=True
                )
                st.plotly_chart(fig_strain, use_container_width=True)

            # Tabella Dettagliata Settimana per Settimana
            with st.expander(tr("Tabella Dettagliata Strain Stagionale", "Detailed Seasonal Strain Table")):
                tab_strain_rows = []
                for p in reversed(strain_season_data):
                    is_h_tlh = (p['strain_tlh'] > threshold_strain_alarm and p['strain_tlh'] > 0)
                    st_str_tlh = "[Picco Allarme]" if is_h_tlh else ("[Regolare]" if p['strain_tlh'] > 0 else "-")

                    is_h_tl = (p['strain_tl'] > threshold_strain_alarm and p['strain_tl'] > 0)
                    st_str_tl = "[Picco Allarme]" if is_h_tl else ("[Regolare]" if p['strain_tl'] > 0 else "-")

                    tab_strain_rows.append({
                        tr("Settimana", "Week"): p['full_label'],
                        tr("Strain TL High", "TL High Strain"): f"{p['strain_tlh']:,.0f} AU" if p['strain_tlh'] > 0 else "-",
                        tr("Stato TL High", "TL High Status"): st_str_tlh,
                        tr("TL High Settimanale", "Weekly TL High"): f"{int(round(p['tot_tlh'])):,} AU" if p['tot_tlh'] > 0 else "-",
                        tr("Monotonia TL High", "TL High Monotony"): f"{p['mono_tlh']:.2f}" if p['mono_tlh'] > 0 else "-",
                        tr("Strain Volume TL", "TL Volume Strain"): f"{p['strain_tl']:,.0f} AU" if p['strain_tl'] > 0 else "-",
                        tr("Stato Volume", "Volume Status"): st_str_tl,
                        tr("Training Load Totale", "Total Training Load"): f"{int(round(p['tot_tl'])):,} TL" if p['tot_tl'] > 0 else "-",
                        tr("Sessioni", "Sessions"): p['num_sessions']
                    })
                st.dataframe(pd.DataFrame(tab_strain_rows), use_container_width=True, hide_index=True)

            # Box Formativo / Informativo Foster per lo Strain
            lbl_strain_title = tr("COS'E' L'INDICE DI STRAIN (TENSIONE / STRESS) - Foster, C.", "WHAT IS THE STRAIN INDEX (STRESS / STRAIN) - Foster, C.")
            lbl_strain_desc = tr("Rappresenta l'indice complessivo di <b>stress biologico e psicofisico cumulato</b> dall'atleta durante la settimana.", "Represents the overall index of <b>cumulative biological and psychophysical stress</b> experienced by the athlete during the week.")
            lbl_strain_formula = tr("Formula di Calcolo:", "Calculation Formula:")
            lbl_strain_formula_txt = tr("Strain = Carico Settimanale Totale × Indice di Monotonia", "Strain = Total Weekly Load × Monotony Index")
            lbl_strain_molt = tr("Effetto Moltiplicativo:", "Multiplicative Effect:")
            lbl_strain_molt_desc = tr("Quando sia il carico settimanale sia la monotonia sono elevati (es. settimana dura senza adeguato scarico), lo Strain sale in modo esponenziale.", "When both weekly load and monotony are high (e.g. hard week without adequate rest), Strain spikes exponentially.")
            lbl_strain_rischio = tr("Rischio Infortuni & Overtraining:", "Injury & Overtraining Risk:")
            lbl_strain_rischio_desc = tr("Picchi anomali di Strain superiori al 50% rispetto alla media stagionale sono il principale predittore scientifico di lesioni muscolari, calo delle difese immunitarie e sovrallenamento.", "Abnormal Strain spikes exceeding 50% above the season average are the primary scientific predictor of muscle injuries, immune suppression, and overtraining.")

            box_strain_html = (
                f"<div style='background:#fefbf6; border:1px solid #fde68a; border-radius:12px; padding:16px 20px; margin-top:20px; font-family:\"Inter\",sans-serif;'>"
                f"<div style='background:#f59e0b; color:#ffffff; font-size:12.5px; font-weight:900; padding:4px 12px; border-radius:6px; display:inline-block; text-transform:uppercase; letter-spacing:0.05em; margin-bottom:10px;'>"
                f"{lbl_strain_title}"
                f"</div>"
                f"<div style='font-size:13px; color:#1e293b; line-height:1.6;'>"
                f"{lbl_strain_desc}<br>"
                f"• <b>{lbl_strain_formula}</b> <code style='background:#fffbeb; color:#b45309; padding:2px 6px; border-radius:4px; font-weight:700;'>{lbl_strain_formula_txt}</code><br>"
                f"• <b style='color:#b45309;'>{lbl_strain_molt}</b> {lbl_strain_molt_desc}<br>"
                f"• <b style='color:#b91c1c;'>{lbl_strain_rischio}</b> {lbl_strain_rischio_desc}"
                f"</div>"
                f"</div>"
            )
            st.html(box_strain_html)
