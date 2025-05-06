import sqlite3
from datetime import datetime

DB_NAME = './db/gameclub.db'

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()

        c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            join_order INTEGER,
            joined_at TIMESTAMP
        )
        ''')

        c.execute('''
        CREATE TABLE IF NOT EXISTS games (
            game_id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_name TEXT UNIQUE,
            genres TEXT,
            release_date TEXT,
            summary TEXT,
            url TEXT
        )
        ''')


        c.execute('''
        CREATE TABLE IF NOT EXISTS suggestions (
            suggestion_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            game_id INTEGER,
            suggested_at TIMESTAMP,
            picked BOOLEAN DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(user_id),
            FOREIGN KEY (game_id) REFERENCES games(game_id)
        )
        ''')

        c.execute('''
        CREATE TABLE IF NOT EXISTS picks (
            pick_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            suggestion_id INTEGER,
            picked_at TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id),
            FOREIGN KEY (suggestion_id) REFERENCES suggestions(suggestion_id)
        )
        ''')

        conn.commit()

def add_user(username):
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute('SELECT MAX(join_order) FROM users')
        result = c.fetchone()
        next_order = (result[0] or 0) + 1

        c.execute('INSERT OR IGNORE INTO users (username, join_order, joined_at) VALUES (?, ?, ?)',
                  (username, next_order, datetime.now()))
        conn.commit()

def add_game(game_name, genres=None, release_date=None, summary=None, url=None):
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute('''
        INSERT OR IGNORE INTO games (game_name, genres, release_date, summary, url)
        VALUES (?, ?, ?, ?, ?)
        ''', (game_name, genres, release_date, summary, url))
        conn.commit()

def check_game_exists(game_name):
    """Check if a game already exists in the database."""
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute('SELECT game_id FROM games WHERE game_name = ?', (game_name,))
        return c.fetchone() is not None

def add_suggestion(username, game_name, genres=None, release_date=None, summary=None, url=None):
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()

        # Ensure user exists
        c.execute('SELECT user_id FROM users WHERE username = ?', (username,))
        user = c.fetchone()
        if not user:
            # User doesn't exist yet, create them
            c.execute('SELECT MAX(join_order) FROM users')
            result = c.fetchone()
            next_order = (result[0] or 0) + 1

            c.execute('INSERT INTO users (username, join_order, joined_at) VALUES (?, ?, ?)',
                      (username, next_order, datetime.now()))
            conn.commit()

            # Re-fetch new user_id
            c.execute('SELECT user_id FROM users WHERE username = ?', (username,))
            user = c.fetchone()

        user_id = user[0]

        # Ensure game exists
        c.execute('SELECT game_id FROM games WHERE LOWER(game_name) = LOWER(?)', (game_name,))
        game = c.fetchone()
        if not game:
            add_game(game_name, genres, release_date, summary, url)
            c.execute('SELECT game_id FROM games WHERE LOWER(game_name) = LOWER(?)', (game_name,))
            game = c.fetchone()
        game_id = game[0]

        # Check if this user already suggested this game
        c.execute('''
        SELECT 1
        FROM suggestions
        WHERE user_id = ? AND game_id = ? AND picked = 0
        ''', (user_id, game_id))
        existing_suggestion = c.fetchone()

        if existing_suggestion:
            raise ValueError(f"You have already suggested {game_name}.")

        # Insert suggestion
        c.execute('INSERT INTO suggestions (user_id, game_id, suggested_at) VALUES (?, ?, ?)',
                  (user_id, game_id, datetime.now()))
        conn.commit()

    
def get_user_suggestions(username):
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute('''
        SELECT g.game_name, s.picked
        FROM suggestions s
        JOIN users u ON s.user_id = u.user_id
        JOIN games g ON s.game_id = g.game_id
        WHERE u.username = ?
        ''', (username,))
        return c.fetchall()

def remove_suggestion(username, game_name):
    """Remove a user's suggestion for a game, ignoring case."""
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()

        # Get user_id
        c.execute('SELECT user_id FROM users WHERE username = ?', (username,))
        user = c.fetchone()
        if not user:
            raise ValueError(f"User {username} not found.")
        user_id = user[0]

        # Get game_id (case-insensitive match)
        c.execute('SELECT game_id FROM games WHERE LOWER(game_name) = LOWER(?)', (game_name,))
        game = c.fetchone()
        if not game:
            raise ValueError(f"Game {game_name} not found.")
        game_id = game[0]

        # Delete the suggestion (only this user's suggestion)
        c.execute('''
        DELETE FROM suggestions
        WHERE user_id = ? AND game_id = ?
        ''', (user_id, game_id))

        conn.commit()

def list_all_games():
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute('''
        SELECT DISTINCT g.game_name
        FROM games g
        JOIN suggestions s ON g.game_id = s.game_id
        ''')
        return [g[0] for g in c.fetchall()]

def get_all_game_names():
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute('SELECT game_name FROM games')
        return [row[0] for row in c.fetchall()]

def list_user_suggestions(username):
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute('''
        SELECT g.game_name
        FROM suggestions s
        JOIN users u ON s.user_id = u.user_id
        JOIN games g ON s.game_id = g.game_id
        WHERE u.username = ?
        ''', (username,))
        return [s[0] for s in c.fetchall()]
    
def list_user_active_suggestions(username):
    """List all unpicked suggestions made by a user."""
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute('''
        SELECT g.game_name
        FROM suggestions s
        JOIN users u ON s.user_id = u.user_id
        JOIN games g ON s.game_id = g.game_id
        WHERE u.username = ? AND s.picked = 0
        ''', (username,))
        return [row[0] for row in c.fetchall()]

def get_all_suggestions_with_users():
    """Return a list of (username, game_name, url) for all active suggestions."""
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute('''
        SELECT u.username, g.game_name, g.url
        FROM suggestions s
        JOIN users u ON s.user_id = u.user_id
        JOIN games g ON s.game_id = g.game_id
        WHERE s.picked = 0
        ''')
        return c.fetchall()

def get_game_info(game_name):
    """Fetch detailed info for a game by name."""
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute('''
        SELECT game_name, genres, release_date, summary, url
        FROM games
        WHERE LOWER(game_name) = LOWER(?)
        ''', (game_name,))
        return c.fetchone()

def clear_user_order():
    """Clear all users (and their picking order)."""
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute('DELETE FROM users')
        conn.commit()

def get_next_user_to_pick():
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()

        c.execute('SELECT DISTINCT user_id FROM picks')
        picked_users = set(row[0] for row in c.fetchall())

        if picked_users:
            query = '''
            SELECT username
            FROM users
            WHERE user_id NOT IN ({seq})
            ORDER BY join_order ASC
            LIMIT 1
            '''.format(seq=','.join(['?']*len(picked_users)))
            c.execute(query, tuple(picked_users))
        else:
            c.execute('''
            SELECT username
            FROM users
            ORDER BY join_order ASC
            LIMIT 1
            ''')

        row = c.fetchone()
        return row[0] if row else None

def pick_game_for_user(username, game_name):
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()

        c.execute('SELECT user_id FROM users WHERE username = ?', (username,))
        user = c.fetchone()
        if not user:
            raise ValueError(f"User {username} not found.")
        user_id = user[0]

        c.execute('SELECT game_id FROM games WHERE game_name = ?', (game_name,))
        game = c.fetchone()
        if not game:
            raise ValueError(f"Game {game_name} not found.")
        game_id = game[0]

        c.execute('''
        SELECT suggestion_id
        FROM suggestions
        WHERE user_id = ? AND game_id = ? AND picked = 0
        ''', (user_id, game_id))
        suggestion = c.fetchone()
        if not suggestion:
            raise ValueError(f"No active suggestion found for {game_name} by {username}.")
        suggestion_id = suggestion[0]

        c.execute('UPDATE suggestions SET picked = 1 WHERE suggestion_id = ?', (suggestion_id,))
        c.execute('INSERT INTO picks (user_id, suggestion_id, picked_at) VALUES (?, ?, ?)',
                  (user_id, suggestion_id, datetime.now()))
        conn.commit()

def get_user_order():
    """Return the list of usernames in picking order."""
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute('''
        SELECT username
        FROM users
        ORDER BY join_order ASC
        ''')
        return [row[0] for row in c.fetchall()]
