from flask import Flask, render_template
import sqlite3
import os
from datetime import datetime

app = Flask(__name__, template_folder="templates", static_folder="static")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "../db/gameclub.db")


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@app.route("/")
def home():
    conn = get_db_connection()
    game = conn.execute("""
        SELECT ag.user, ag.game_name, ag.genres, ag.release_date, ag.summary, ag.url
        FROM current_game cg
        JOIN archived_games ag ON cg.game_id = ag.id
        LIMIT 1
    """).fetchone()
    conn.close()

    if game and game["release_date"].isdigit():
        formatted_date = datetime.utcfromtimestamp(int(game["release_date"])).strftime("%B %d, %Y")
        game = dict(game)
        game["release_date"] = formatted_date

    return render_template("home.html", game=game)



@app.route("/games")
def games():
    conn = get_db_connection()
    rows = conn.execute("""
        SELECT user, game_name, genres, release_date, summary, url
        FROM game_picks
        ORDER BY id DESC
    """).fetchall()
    conn.close()

    formatted_rows = []
    for row in rows:
        row = dict(row)
        if row["release_date"] and row["release_date"].isdigit():
            row["release_date"] = datetime.utcfromtimestamp(int(row["release_date"])).strftime("%B %d, %Y")
        formatted_rows.append(row)

    return render_template("games.html", rows=formatted_rows)

