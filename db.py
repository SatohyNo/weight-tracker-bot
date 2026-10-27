"""SQLite storage: one profile and a weight log per Telegram user."""
import os, sqlite3
from datetime import date

PATH = os.environ.get("WEIGHT_BOT_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "weights.db"))

con = sqlite3.connect(PATH)
con.executescript("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    goal    TEXT NOT NULL DEFAULT 'maintain',
    kcal    INTEGER
);
CREATE TABLE IF NOT EXISTS weights (
    user_id INTEGER NOT NULL,
    day     TEXT NOT NULL,   -- YYYY-MM-DD, one weight per day
    kg      REAL NOT NULL,
    PRIMARY KEY (user_id, day)
);
""")


def user(uid):
    """(goal, kcal); creates the profile on first contact."""
    con.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (uid,))
    con.commit()
    return con.execute("SELECT goal, kcal FROM users WHERE user_id = ?", (uid,)).fetchone()


def set_goal(uid, goal):
    user(uid)
    con.execute("UPDATE users SET goal = ? WHERE user_id = ?", (goal, uid))
    con.commit()


def set_kcal(uid, kcal):
    user(uid)
    con.execute("UPDATE users SET kcal = ? WHERE user_id = ?", (kcal, uid))
    con.commit()


def add(uid, entries):
    """Insert or overwrite weights; returns how many dates already existed."""
    days = [d.isoformat() for d, _ in entries]
    q = f"SELECT COUNT(*) FROM weights WHERE user_id = ? AND day IN ({','.join('?' * len(days))})"
    existed = con.execute(q, (uid, *days)).fetchone()[0]
    con.executemany("INSERT OR REPLACE INTO weights VALUES (?, ?, ?)",
                    [(uid, d.isoformat(), kg) for d, kg in entries])
    con.commit()
    return existed


def entries(uid):
    rows = con.execute("SELECT day, kg FROM weights WHERE user_id = ? ORDER BY day", (uid,))
    return [(date.fromisoformat(d), kg) for d, kg in rows]


def delete(uid, day):
    n = con.execute("DELETE FROM weights WHERE user_id = ? AND day = ?", (uid, day.isoformat())).rowcount
    con.commit()
    return n


def clear(uid):
    con.execute("DELETE FROM weights WHERE user_id = ?", (uid,))
    con.commit()
