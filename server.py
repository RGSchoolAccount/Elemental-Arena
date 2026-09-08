"""
Elemental Arena - accounts server.

A small Flask + SQLite backend that stores player accounts (username,
password, date joined, games played, wins, losses, XP, level) so the
same account can be logged into from any device that can reach this
server.

RUNNING THIS:
    pip install flask
    python server.py

This starts a server on port 5000, reachable at http://<this-machine's-ip>:5000
from any other device on the same network. For it to be reachable from
devices on a *different* network (e.g. friends playing from their own
homes), you need to either:
  - Deploy this to a hosting service (Render, Railway, PythonAnywhere,
    Fly.io, etc. all have free tiers suitable for this), or
  - Port-forward port 5000 on your router to this machine and give
    people your public IP (not recommended long-term - a real host is
    safer and easier).

Once you have a URL for wherever this ends up running, put it into
SERVER_URL at the top of account_client.py so the game knows where to
find it.
"""

import os
import sqlite3
from datetime import datetime, timezone

from flask import Flask, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash


def _default_data_dir():
    """A stable, per-user location for accounts.db - deliberately NOT
    next to this script. A relative path there resolves against
    whatever the current working directory happens to be when this
    process starts, which changes depending on how the game is
    launched (double-click vs terminal vs a fresh re-download into a
    new folder) - that mismatch is what made accounts appear to
    "vanish" before. This survives all of that."""
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    elif os.uname().sysname == "Darwin":
        base = os.path.join(os.path.expanduser("~"), "Library", "Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")

    data_dir = os.path.join(base, "ElementalArena")
    os.makedirs(data_dir, exist_ok=True)
    return data_dir


DB_PATH = os.path.join(_default_data_dir(), "accounts.db")

app = Flask(__name__)

# XP needed to REACH each level (index 0 = level 1's threshold, i.e. 0).
# Winning games grants XP, losing costs a little - reaching level 20
# takes 1000 XP, equivalent to 100 wins if you never lose along the way.
LEVEL_THRESHOLDS = [
    0, 10, 20, 40, 70, 100, 140, 180, 230, 280,
    340, 400, 460, 520, 600, 670, 750, 830, 910, 1000,
    1100, 1210,
]
MAX_LEVEL = len(LEVEL_THRESHOLDS)

XP_PER_WIN = 10
XP_PER_LOSS = -4

CURRENCY_PER_WIN = 15
CURRENCY_PER_LOSS = 5

ADMIN_USERNAME = "RijoyDaAdmin"
ADMIN_PASSWORD = "Thund*r1ng"
ADMIN_XP = 999999
ADMIN_CURRENCY = 999999


def level_for_xp(xp):
    level = 1

    for index, threshold in enumerate(LEVEL_THRESHOLDS):
        if xp >= threshold:
            level = index + 1

    return min(MAX_LEVEL, level)


def get_db():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    connection = get_db()
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS accounts (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            date_joined TEXT NOT NULL,
            games_played INTEGER NOT NULL DEFAULT 0,
            wins INTEGER NOT NULL DEFAULT 0,
            losses INTEGER NOT NULL DEFAULT 0,
            xp INTEGER NOT NULL DEFAULT 0,
            level INTEGER NOT NULL DEFAULT 1,
            currency INTEGER NOT NULL DEFAULT 0
        )
        """
    )

    # Migration for databases created before xp/level/currency existed.
    existing_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(accounts)")
    }

    if "xp" not in existing_columns:
        connection.execute("ALTER TABLE accounts ADD COLUMN xp INTEGER NOT NULL DEFAULT 0")

    if "level" not in existing_columns:
        connection.execute("ALTER TABLE accounts ADD COLUMN level INTEGER NOT NULL DEFAULT 1")

    if "currency" not in existing_columns:
        connection.execute("ALTER TABLE accounts ADD COLUMN currency INTEGER NOT NULL DEFAULT 0")

    if "is_admin" not in existing_columns:
        connection.execute("ALTER TABLE accounts ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0")

    connection.commit()

    # Seed (or refresh) the admin account every startup, so its
    # credentials/privileges/stats are always right even if the DB
    # already existed from before this feature was added.
    admin_row = connection.execute(
        "SELECT username FROM accounts WHERE LOWER(username) = LOWER(?)", (ADMIN_USERNAME,)
    ).fetchone()
    admin_hash = generate_password_hash(ADMIN_PASSWORD)

    if admin_row is None:
        connection.execute(
            """
            INSERT INTO accounts
                (username, password_hash, date_joined, xp, level, currency, is_admin)
            VALUES (?, ?, ?, ?, ?, ?, 1)
            """,
            (
                ADMIN_USERNAME, admin_hash, datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                ADMIN_XP, MAX_LEVEL, ADMIN_CURRENCY,
            ),
        )
    else:
        connection.execute(
            """
            UPDATE accounts
            SET password_hash = ?, xp = ?, level = ?, currency = ?, is_admin = 1
            WHERE username = ?
            """,
            (admin_hash, ADMIN_XP, MAX_LEVEL, ADMIN_CURRENCY, admin_row["username"]),
        )

    connection.commit()
    connection.close()


def account_to_dict(row):
    return {
        "username": row["username"],
        "date_joined": row["date_joined"],
        "games_played": row["games_played"],
        "wins": row["wins"],
        "losses": row["losses"],
        "xp": row["xp"],
        "level": row["level"],
        "currency": row["currency"],
        "is_admin": bool(row["is_admin"]),
    }


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    if not (3 <= len(username) <= 20):
        return jsonify({"error": "Username must be 3-20 characters."}), 400

    if len(password) < 4:
        return jsonify({"error": "Password must be at least 4 characters."}), 400

    connection = get_db()
    existing = connection.execute(
        "SELECT username FROM accounts WHERE LOWER(username) = LOWER(?)", (username,)
    ).fetchone()

    if existing is not None:
        connection.close()
        return jsonify({"error": "That username is already taken."}), 409

    password_hash = generate_password_hash(password)
    date_joined = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    connection.execute(
        "INSERT INTO accounts (username, password_hash, date_joined) VALUES (?, ?, ?)",
        (username, password_hash, date_joined),
    )
    connection.commit()

    row = connection.execute(
        "SELECT * FROM accounts WHERE username = ?", (username,)
    ).fetchone()
    connection.close()

    return jsonify(account_to_dict(row)), 201


@app.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    connection = get_db()
    row = connection.execute(
        "SELECT * FROM accounts WHERE LOWER(username) = LOWER(?)", (username,)
    ).fetchone()
    connection.close()

    if row is None or not check_password_hash(row["password_hash"], password):
        return jsonify({"error": "Incorrect username or password."}), 401

    return jsonify(account_to_dict(row)), 200


@app.route("/stats/<username>", methods=["GET"])
def get_stats(username):
    connection = get_db()
    row = connection.execute(
        "SELECT * FROM accounts WHERE LOWER(username) = LOWER(?)", (username,)
    ).fetchone()
    connection.close()

    if row is None:
        return jsonify({"error": "No such account."}), 404

    return jsonify(account_to_dict(row)), 200


@app.route("/record_result", methods=["POST"])
def record_result():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    won = bool(data.get("won"))

    connection = get_db()
    row = connection.execute(
        "SELECT * FROM accounts WHERE LOWER(username) = LOWER(?)", (username,)
    ).fetchone()

    if row is None:
        connection.close()
        return jsonify({"error": "No such account."}), 404

    # Use the canonical stored username (not whatever case the caller sent)
    # for the UPDATE, since the primary key comparison below is exact-match.
    username = row["username"]

    if row["is_admin"]:
        new_xp, new_level, new_currency = ADMIN_XP, MAX_LEVEL, ADMIN_CURRENCY
    else:
        xp_delta = XP_PER_WIN if won else XP_PER_LOSS
        new_xp = max(0, row["xp"] + xp_delta)
        new_level = level_for_xp(new_xp)
        currency_delta = CURRENCY_PER_WIN if won else CURRENCY_PER_LOSS
        new_currency = row["currency"] + currency_delta

    if won:
        connection.execute(
            """
            UPDATE accounts
            SET games_played = games_played + 1, wins = wins + 1,
                xp = ?, level = ?, currency = ?
            WHERE username = ?
            """,
            (new_xp, new_level, new_currency, username),
        )
    else:
        connection.execute(
            """
            UPDATE accounts
            SET games_played = games_played + 1, losses = losses + 1,
                xp = ?, level = ?, currency = ?
            WHERE username = ?
            """,
            (new_xp, new_level, new_currency, username),
        )

    connection.commit()

    row = connection.execute(
        "SELECT * FROM accounts WHERE username = ?", (username,)
    ).fetchone()
    connection.close()

    return jsonify(account_to_dict(row)), 200


@app.route("/delete_account", methods=["POST"])
def delete_account():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    connection = get_db()
    row = connection.execute(
        "SELECT * FROM accounts WHERE LOWER(username) = LOWER(?)", (username,)
    ).fetchone()

    if row is None or not check_password_hash(row["password_hash"], password):
        connection.close()
        return jsonify({"error": "Incorrect username or password."}), 401

    connection.execute(
        "DELETE FROM accounts WHERE username = ?", (row["username"],)
    )
    connection.commit()
    connection.close()

    return jsonify({"deleted": True}), 200


def _require_admin(data):
    """Returns the verified admin row, or None if the credentials in
    `data` don't belong to an admin account."""
    admin_username = (data.get("admin_username") or "").strip()
    admin_password = data.get("admin_password") or ""

    connection = get_db()
    admin_row = connection.execute(
        "SELECT * FROM accounts WHERE LOWER(username) = LOWER(?)", (admin_username,)
    ).fetchone()
    connection.close()

    if admin_row is None or not admin_row["is_admin"]:
        return None

    if not check_password_hash(admin_row["password_hash"], admin_password):
        return None

    return admin_row


@app.route("/admin/accounts", methods=["POST"])
def admin_list_accounts():
    # POST (not GET) so credentials travel in the body, not a URL/query
    # string that might end up logged somewhere.
    data = request.get_json(silent=True) or {}

    if _require_admin(data) is None:
        return jsonify({"error": "Not authorized."}), 403

    connection = get_db()
    rows = connection.execute("SELECT * FROM accounts ORDER BY username COLLATE NOCASE").fetchall()
    connection.close()

    return jsonify({"accounts": [account_to_dict(row) for row in rows]}), 200


@app.route("/admin/delete_account", methods=["POST"])
def admin_delete_account():
    data = request.get_json(silent=True) or {}

    if _require_admin(data) is None:
        return jsonify({"error": "Not authorized."}), 403

    target_username = (data.get("target_username") or "").strip()

    connection = get_db()
    target_row = connection.execute(
        "SELECT username, is_admin FROM accounts WHERE LOWER(username) = LOWER(?)", (target_username,)
    ).fetchone()

    if target_row is None:
        connection.close()
        return jsonify({"error": "No such account."}), 404

    if target_row["is_admin"]:
        connection.close()
        return jsonify({"error": "Can't delete an admin account."}), 400

    connection.execute("DELETE FROM accounts WHERE username = ?", (target_row["username"],))
    connection.commit()
    connection.close()

    return jsonify({"deleted": True}), 200


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000)