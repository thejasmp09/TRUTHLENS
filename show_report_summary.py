"""
Print a summary of the latest report, including agent results if available.

Run:
    python show_report_summary.py
"""

import sqlite3
import json
import config


def main():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM reports ORDER BY created_at DESC LIMIT 1").fetchone()
    conn.close()

    if not row:
        print("No reports found.")
        return

    print(f"Report #{row['id']} — {row['overall_verdict']} (confidence: {row['confidence']})")
    print("---- AUTOPSY (first 800 chars) ----")
    print((row['autopsy_md'] or '')[:800])
    print("\n---- AGENT RESULTS (if available) ----")
    # sqlite3.Row behaves like a mapping but doesn't have .get()
    try:
        ar = row['agent_results_json']
    except Exception:
        try:
            ar = row.get('agent_results_json')
        except Exception:
            ar = None
    if ar:
        try:
            parsed = json.loads(ar)
            print(json.dumps(parsed, indent=2)[:3000])
        except Exception:
            print(ar[:3000])
    else:
        print("No agent_results saved for this report.")


if __name__ == '__main__':
    main()
