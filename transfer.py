import sqlite3
from datetime import datetime

# Paths
OLD_DB_PATH = "gameclubold.db"  # your old one
NEW_DB_PATH = "gameclub.db"    # your new one

# Connect to old db
old_conn = sqlite3.connect(OLD_DB_PATH)
old_c = old_conn.cursor()

# Connect to new db
new_conn = sqlite3.connect(NEW_DB_PATH)
new_c = new_conn.cursor()

try:
    # Fetch all old picks
    old_c.execute("SELECT user, game_name, genres, release_date, summary, url FROM game_picks")
    games = old_c.fetchall()
    print(f"Found {len(games)} games to migrate...")

    for user, game_name, genres, release_date, summary, url in games:
        # Insert user if not exists
        new_c.execute('SELECT user_id FROM users WHERE username = ?', (user,))
        user_row = new_c.fetchone()
        if not user_row:
            new_c.execute('SELECT MAX(join_order) FROM users')
            max_order = new_c.fetchone()[0]
            next_order = (max_order or 0) + 1
            new_c.execute('INSERT INTO users (username, join_order, joined_at) VALUES (?, ?, ?)',
                          (user, next_order, datetime.now()))
            new_conn.commit()

        # Insert game if not exists
        new_c.execute('SELECT game_id FROM games WHERE LOWER(game_name) = LOWER(?)', (game_name,))
        game_row = new_c.fetchone()
        if not game_row:
            new_c.execute('''
            INSERT INTO games (game_name, genres, release_date, summary, url)
            VALUES (?, ?, ?, ?, ?)
            ''', (game_name, genres or None, release_date or None, summary or None, url or None))
            new_conn.commit()

        # Insert suggestion
        new_c.execute('SELECT user_id FROM users WHERE username = ?', (user,))
        user_id = new_c.fetchone()[0]
        new_c.execute('SELECT game_id FROM games WHERE LOWER(game_name) = LOWER(?)', (game_name,))
        game_id = new_c.fetchone()[0]

        # Insert suggestion if not already there
        new_c.execute('''
        SELECT 1 FROM suggestions WHERE user_id = ? AND game_id = ? AND picked = 0
        ''', (user_id, game_id))
        if not new_c.fetchone():
            new_c.execute('''
            INSERT INTO suggestions (user_id, game_id, suggested_at)
            VALUES (?, ?, ?)
            ''', (user_id, game_id, datetime.now()))
            new_conn.commit()

    print("✅ Migration complete.")

except Exception as e:
    print(f"❌ Error during migration: {e}")

finally:
    old_conn.close()
    new_conn.close()
