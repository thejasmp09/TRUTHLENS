"""
Export all reports to JSON file `reports/reports_export.json`.

Run:
    python export_reports.py
"""

import sqlite3
import json
import os
import config


def main():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM reports ORDER BY created_at DESC").fetchall()
    conn.close()

    out = []
    for r in rows:
        d = dict(r)
        # try to parse JSON fields
        for k in ('claims_json', 'verdicts_json', 'agent_results_json'):
            if d.get(k):
                try:
                    d[k] = json.loads(d[k])
                except Exception:
                    pass
        out.append(d)

    os.makedirs('reports', exist_ok=True)
    path = os.path.join('reports', 'reports_export.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=2)

    print('Exported', len(out), 'reports to', path)


if __name__ == '__main__':
    main()
