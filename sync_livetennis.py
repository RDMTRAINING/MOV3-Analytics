#!/usr/bin/env python3
"""
Sync script per scaricare giornalmente (es. ore 22:00) i dati aggiornati di Flavio Cobolli
da Live Tennis API e aggiornare la cache locale / repository.
"""
import sys
import os
import json
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils_livetennis import fetch_cobolli_live_stats, load_livetennis_cache

def main():
    print(f"[{datetime.datetime.now().isoformat()}] Avvio sincronizzazione Live Tennis API per Flavio Cobolli...")
    stats = fetch_cobolli_live_stats(force_refresh=True)
    print("Dati recuperati con successo:")
    print(f"  Atleta: {stats.get('name')}")
    print(f"  Ranking ATP Live: #{stats.get('ranking')} ({stats.get('ranking_points')} pts)")
    print(f"  Tiebreak Win%: {stats.get('tiebreak_pct')}% ({stats.get('tiebreak_record')})")
    print(f"  Deciding Set Win%: {stats.get('deciding_set_pct')}% ({stats.get('deciding_set_record')})")
    print(f"  Vs Mancini: {stats.get('vs_lefty_pct')}%")
    print("Cache aggiornata su disco.")

if __name__ == "__main__":
    main()
