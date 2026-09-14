"""
Elemental Arena - the hidden Average/God unlock.

A tiny, self-contained puzzle tracker. Nothing in here touches pygame
or any live game state - main.py calls into this module to check/award
fragments and to persist progress locally (independent of login, same
pattern as story.py's campaign save).

There are three fragments, found in any order, scattered across
completely ordinary screens:

  1. "resonance"  - click the main menu title 7 times within 4 seconds
  2. "extremes"   - have NPC Difficulty at 9 (Nightmare) and Show FPS
                    switched on at the same time, in Settings
  3. "old_rivals" - in the Encyclopedia, view Fire's bio and then
                    Water's bio back to back

Finding all three permanently unlocks the secret character. None of
this is hinted anywhere in the UI on purpose.
"""

import json
import os

SECRET_SAVE_DIR = os.path.dirname(os.path.abspath(__file__))

FRAGMENT_KEYS = ("resonance", "extremes", "old_rivals")

FRAGMENT_MESSAGES = {
    "resonance": "...something stirs...",
    "extremes": "...halfway there...",
    "old_rivals": "...the seal breaks...",
}

UNLOCK_MESSAGE = "A NEW CHALLENGER HAS AWOKEN"

# Hints toward the fragments above, shown once each at specific
# milestones (not part of the puzzle itself - just breadcrumbs so it's
# not pure guesswork). Persisted the same way as fragments so a hint
# already seen doesn't repeat.
CLUE_KEYS = ("clue_story_complete",)

CLUE_TEXT = {
    "clue_story_complete": (
        "The old title above the arena gates flickers sometimes, like "
        "it's waiting for someone to knock. Seven times ought to do "
        "it. Quickly, though."
    ),
}

ALL_PROGRESS_KEYS = FRAGMENT_KEYS + CLUE_KEYS


def _save_path_for(username):
    """Per-account, same reasoning as story.py's save - otherwise the
    secret shows as found/unlocked regardless of who's actually logged
    in, which is exactly the bug this is meant to avoid."""
    safe_name = "".join(c for c in (username or "").lower() if c.isalnum() or c in ("-", "_"))
    safe_name = safe_name or "guest"
    return os.path.join(SECRET_SAVE_DIR, f"secret_progress_{safe_name}.json")


def load_secret_progress(username=None):
    try:
        with open(_save_path_for(username), "r") as save_file:
            data = json.load(save_file)
            return {key: bool(data.get(key, False)) for key in ALL_PROGRESS_KEYS}
    except (OSError, ValueError, TypeError):
        return {key: False for key in ALL_PROGRESS_KEYS}


def save_secret_progress(progress, username=None):
    try:
        with open(_save_path_for(username), "w") as save_file:
            json.dump(progress, save_file)
    except OSError:
        pass


def is_unlocked(progress):
    return all(progress.get(key, False) for key in FRAGMENT_KEYS)