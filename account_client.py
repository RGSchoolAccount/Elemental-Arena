"""
Elemental Arena - account client.

Talks to server.py over plain HTTP using only the Python standard
library (urllib), so the game itself needs no extra installs beyond
pygame.

IMPORTANT: change SERVER_URL below to point at wherever you end up
running server.py (see the instructions at the top of that file).
Left as localhost, this only works when the server is running on the
same machine as the game.
"""

import json
import urllib.error
import urllib.request

SERVER_URL = "http://127.0.0.1:5000"
TIMEOUT_SECONDS = 5


def _post(path, payload):
    url = f"{SERVER_URL}{path}"
    data = json.dumps(payload).encode("utf-8")
    request_obj = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )

    try:
        with urllib.request.urlopen(request_obj, timeout=TIMEOUT_SECONDS) as response:
            return True, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        try:
            body = json.loads(error.read().decode("utf-8"))
            message = body.get("error", "Something went wrong.")
        except Exception:
            message = "Something went wrong."
        return False, message
    except urllib.error.URLError:
        return False, "Can't reach the account server. Check your connection/SERVER_URL."
    except Exception:
        return False, "Something went wrong."


def _get(path, timeout=TIMEOUT_SECONDS):
    url = f"{SERVER_URL}{path}"

    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return True, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        try:
            body = json.loads(error.read().decode("utf-8"))
            message = body.get("error", "Something went wrong.")
        except Exception:
            message = "Something went wrong."
        return False, message
    except urllib.error.URLError:
        return False, "Can't reach the account server. Check your connection/SERVER_URL."
    except Exception:
        return False, "Something went wrong."


def ping(timeout=0.6):
    """Quick check for whether the account server is reachable at all."""
    success, _ = _get("/health", timeout=timeout)
    return success


def register(username, password):
    """Returns (success, account_dict_or_error_message)."""
    return _post("/register", {"username": username, "password": password})


def login(username, password):
    """Returns (success, account_dict_or_error_message)."""
    return _post("/login", {"username": username, "password": password})


def get_stats(username):
    """Returns (success, account_dict_or_error_message)."""
    return _get(f"/stats/{username}")


def record_result(username, won):
    """Returns (success, account_dict_or_error_message)."""
    return _post("/record_result", {"username": username, "won": won})


def delete_account(username, password):
    """Permanently deletes the account. Returns (success, dict_or_error_message).

    Requires the password again as a confirmation/authentication step, same
    as login - this isn't something a stolen session should be able to do.
    """
    return _post("/delete_account", {"username": username, "password": password})


def admin_list_accounts(admin_username, admin_password):
    """Returns (success, list_of_account_dicts_or_error_message). Only
    works for an account with is_admin set - everyone else gets a 403."""
    success, result = _post("/admin/accounts", {
        "admin_username": admin_username, "admin_password": admin_password,
    })

    if success:
        return True, result.get("accounts", [])

    return False, result


def admin_delete_account(admin_username, admin_password, target_username):
    """Returns (success, dict_or_error_message). Admin-only; refuses to
    delete another admin account."""
    return _post("/admin/delete_account", {
        "admin_username": admin_username, "admin_password": admin_password,
        "target_username": target_username,
    })