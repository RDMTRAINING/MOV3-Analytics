# Copyright 2026 Riccardo Di Maio - M0V3 S.r.l. Tutti i diritti riservati.
# Proprietary Sports Science & Clinical Performance Intelligence Architecture.
import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from alert_engine import dispatch_morning_digest, run_proactive_red_flag_scan


def main():
    print("=== M0V3 ANALYTICS V3.0 — HEADLESS MORNING DIGEST ENGINE ===")
    scan = run_proactive_red_flag_scan()
    print(
        f"Data Scansione: {scan['scan_timestamp']} | Atleti: {scan['n_athletes']} | "
        f"Alert Totali: {scan['n_total_alerts']} (Critici: {scan['n_critico']}, Attenzione: {scan['n_attenzione']}, Operativi: {scan['n_operativo']})"
    )
    results = dispatch_morning_digest(force_send_all=False)
    for r in results:
        print(f" -> Destinatario: {r['email']} | Stato: {r['stato']} | Dettaglio: {r['dettaglio']}")
    print("=== ESECUZIONE COMPLETATA ===")


if __name__ == "__main__":
    main()
