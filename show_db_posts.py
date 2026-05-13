"""
Show recent posts saved in the TruthLens SQLite DB.

Run:
    python show_db_posts.py

This prints recent rows from the `posts` table.
"""

import sqlite3
import config


def main():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        "SELECT id, platform, author, url, fetched_at FROM posts ORDER BY fetched_at DESC LIMIT 50"
    ).fetchall()
    conn.close()

    if not rows:
        print("No posts found in the database.")
        return

    for row in rows:
        print(dict(row))


if __name__ == "__main__":
    main()
