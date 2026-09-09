import array
import atexit
import ctypes
import json
import math
import os
import random
import subprocess
import sys
import time

# --- AUTO-INSTALLER FOR PYGAME ---
try:
    import pygame
except ImportError:
    print("Pygame not found. Attempting to install automatically...")
    # --- AUTO-INSTALLER FOR PYGAME ---
    try:
        import pygame
    except ImportError:
        print("Pygame not found. Attempting to install automatically...")
        try:
            # Installs pygame-ce (fully compatible with Python 3.14)
            subprocess.check_call([sys.executable, "-m", "pip", "install", "pygame-ce"])
            # CRITICAL FIX: The package name is 'pygame-ce', but you still import 'pygame'
            import pygame 
            print("Pygame successfully installed!")
        except Exception as e:
            print(f"Auto-installation failed: {e}")
            print("Please install it manually using: pip install pygame-ce")
            sys.exit(1)
# ---------------------------------

# ---------------------------------

from pygame.math import Vector2

from elements import ELEMENTS, AVERAGE_GOD_DATA
from fighters import Fighter, AVERAGE_ASCENSION_TIME
from trails import Trail
import account_client as account
import story
import secret

pygame.init()

AVERAGE_GOD_ELEMENTS = frozenset(AVERAGE_GOD_DATA)

try:
    pygame.joystick.init()
    pygame.controller.init()
    CONTROLLER_API_AVAILABLE = True
except (AttributeError, pygame.error):
    # Some pygame builds (rare) are compiled without controller/joystick
    # support. Controller input mode simply won't do anything in that
    # case - keyboard & mouse always still works.
    CONTROLLER_API_AVAILABLE = False


# --- Windows accessibility shortcuts -------------------------------------
# Several elements (Ice, Animalia) require holding Shift continuously,
# which is exactly the pattern that triggers Windows' Sticky Keys /
# Filter Keys accessibility prompts. We disable them for this session
# only (never touching the user's permanent settings) and restore
# whatever they had on exit.

SPI_GETSTICKYKEYS = 0x3A
SPI_SETSTICKYKEYS = 0x3B
SPI_GETTOGGLEKEYS = 0x34
SPI_SETTOGGLEKEYS = 0x35
SPI_GETFILTERKEYS = 0x32
SPI_SETFILTERKEYS = 0x33

SKF_STICKYKEYSON = 0x00000001
SKF_HOTKEYACTIVE = 0x00000004
SKF_CONFIRMHOTKEY = 0x00000008


class _StickyKeys(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwFlags", ctypes.c_uint)]


class _ToggleKeys(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwFlags", ctypes.c_uint)]


class _FilterKeys(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_uint),
        ("dwFlags", ctypes.c_uint),
        ("iWaitMSec", ctypes.c_uint),
        ("iDelayMSec", ctypes.c_uint),
        ("iRepeatMSec", ctypes.c_uint),
        ("iBounceMSec", ctypes.c_uint),
    ]


_original_sticky = _StickyKeys()
_original_toggle = _ToggleKeys()
_original_filter = _FilterKeys()
_accessibility_shortcuts_disabled = False


def disable_sticky_keys():
    global _accessibility_shortcuts_disabled

    if sys.platform != "win32":
        return

    try:
        user32 = ctypes.windll.user32

        _original_sticky.cbSize = ctypes.sizeof(_StickyKeys)
        user32.SystemParametersInfoW(SPI_GETSTICKYKEYS, ctypes.sizeof(_StickyKeys), ctypes.byref(_original_sticky), 0)

        _original_toggle.cbSize = ctypes.sizeof(_ToggleKeys)
        user32.SystemParametersInfoW(SPI_GETTOGGLEKEYS, ctypes.sizeof(_ToggleKeys), ctypes.byref(_original_toggle), 0)

        _original_filter.cbSize = ctypes.sizeof(_FilterKeys)
        user32.SystemParametersInfoW(SPI_GETFILTERKEYS, ctypes.sizeof(_FilterKeys), ctypes.byref(_original_filter), 0)

        new_sticky = _StickyKeys(
            cbSize=ctypes.sizeof(_StickyKeys),
            dwFlags=_original_sticky.dwFlags & ~(SKF_STICKYKEYSON | SKF_HOTKEYACTIVE | SKF_CONFIRMHOTKEY),
        )
        user32.SystemParametersInfoW(SPI_SETSTICKYKEYS, ctypes.sizeof(_StickyKeys), ctypes.byref(new_sticky), 0)

        new_toggle = _ToggleKeys(
            cbSize=ctypes.sizeof(_ToggleKeys),
            dwFlags=_original_toggle.dwFlags & ~SKF_HOTKEYACTIVE,
        )
        user32.SystemParametersInfoW(SPI_SETTOGGLEKEYS, ctypes.sizeof(_ToggleKeys), ctypes.byref(new_toggle), 0)

        new_filter = _FilterKeys(
            cbSize=ctypes.sizeof(_FilterKeys),
            dwFlags=_original_filter.dwFlags & ~SKF_HOTKEYACTIVE,
            iWaitMSec=_original_filter.iWaitMSec,
            iDelayMSec=_original_filter.iDelayMSec,
            iRepeatMSec=_original_filter.iRepeatMSec,
            iBounceMSec=_original_filter.iBounceMSec,
        )
        user32.SystemParametersInfoW(SPI_SETFILTERKEYS, ctypes.sizeof(_FilterKeys), ctypes.byref(new_filter), 0)

        _accessibility_shortcuts_disabled = True
    except Exception:
        pass


def restore_sticky_keys():
    if sys.platform != "win32" or not _accessibility_shortcuts_disabled:
        return

    try:
        user32 = ctypes.windll.user32
        user32.SystemParametersInfoW(SPI_SETSTICKYKEYS, ctypes.sizeof(_StickyKeys), ctypes.byref(_original_sticky), 0)
        user32.SystemParametersInfoW(SPI_SETTOGGLEKEYS, ctypes.sizeof(_ToggleKeys), ctypes.byref(_original_toggle), 0)
        user32.SystemParametersInfoW(SPI_SETFILTERKEYS, ctypes.sizeof(_FilterKeys), ctypes.byref(_original_filter), 0)
    except Exception:
        pass


disable_sticky_keys()
atexit.register(restore_sticky_keys)

# --- Account server auto-start -------------------------------------------
# If nothing is answering at account.SERVER_URL yet, assume it's meant to
# run locally alongside the game and start it ourselves, so there's no
# need to manually open a second window. If SERVER_URL points somewhere
# remote (a real hosted server), this quietly does nothing since the
# ping will succeed and we never even try to launch it.

_account_server_process = None


def _start_local_account_server():
    global _account_server_process

    if account.ping():
        return  # something's already answering - nothing to do

    server_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server.py")

    if not os.path.exists(server_path):
        return

    try:
        creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        _account_server_process = subprocess.Popen(
            [sys.executable, server_path],
            cwd=os.path.dirname(server_path),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags,
        )
    except Exception:
        _account_server_process = None
        return

    # Give it a moment to come up before the player might try to log in.
    for _ in range(20):
        if account.ping():
            break
        time.sleep(0.15)


def _stop_local_account_server():
    if _account_server_process is not None and _account_server_process.poll() is None:
        _account_server_process.terminate()


_start_local_account_server()
atexit.register(_stop_local_account_server)

WIDTH, HEIGHT = 1100, 700
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Elemental Arena")
clock = pygame.time.Clock()

font = pygame.font.SysFont("arial", 19)
small_font = pygame.font.SysFont("arial", 16)
big_font = pygame.font.SysFont("arial", 38, bold=True)

# --- Music --------------------------------------------------------------
# Small ambient loops, synthesized from scratch as raw sine-wave PCM data
# (no external audio files, so nothing to license or ship).

AUDIO_ENABLED = True

try:
    pygame.mixer.init(frequency=44100, size=-16, channels=2)
except pygame.error:
    AUDIO_ENABLED = False


def _generate_music_loop(notes, tempo, sample_rate=44100, volume=5200):
    """notes: list of (frequency_hz_or_None_for_rest, duration_in_beats)."""
    beat_seconds = 60 / tempo
    samples = array.array("h")
    fade_samples = max(1, int(sample_rate * 0.015))

    for frequency, beats in notes:
        note_samples = int(sample_rate * beats * beat_seconds)

        for i in range(note_samples):
            if frequency is None:
                value = 0
            else:
                fade = min(1.0, i / fade_samples, (note_samples - i) / fade_samples)
                value = int(volume * fade * math.sin(2 * math.pi * frequency * i / sample_rate))

            samples.append(value)
            samples.append(value)

    return samples.tobytes()


MENU_MUSIC_TRACKS = [
    (
        "Calm Waters",
        [
            (261.63, 1.2), (329.63, 1.2), (392.00, 1.2), (329.63, 1.2),
            (293.66, 1.2), (349.23, 1.2), (440.00, 1.6), (349.23, 1.2),
            (261.63, 1.2), (311.13, 1.2), (392.00, 1.2), (311.13, 1.2),
        ],
        70,
    ),
    (
        "Twilight Walk",
        [
            (220.00, 1.4), (261.63, 1.0), (293.66, 1.0), (329.63, 1.4),
            (293.66, 1.0), (261.63, 1.0), (246.94, 1.4), (220.00, 1.0),
            (196.00, 1.0), (220.00, 1.4), (246.94, 1.0), (261.63, 1.0),
        ],
        62,
    ),
    (
        "Golden Hall",
        [
            (349.23, 1.0), (392.00, 1.0), (440.00, 1.0), (392.00, 1.0),
            (349.23, 1.0), (329.63, 1.0), (293.66, 1.6), (0, 0.4),
            (349.23, 1.0), (440.00, 1.0), (392.00, 1.0), (329.63, 1.6),
        ],
        76,
    ),
]

GAME_MUSIC_TRACKS = [
    (
        "Charge",
        [
            (220.00, 0.45), (0, 0.05), (220.00, 0.45), (0, 0.05),
            (261.63, 0.45), (0, 0.05), (293.66, 0.45), (0, 0.05),
            (329.63, 0.45), (0, 0.05), (293.66, 0.45), (0, 0.05),
            (261.63, 0.45), (0, 0.05), (246.94, 0.45), (0, 0.05),
            (220.00, 0.45), (0, 0.05), (196.00, 0.45), (0, 0.05),
            (220.00, 0.45), (0, 0.05), (261.63, 0.45), (0, 0.05),
        ],
        132,
    ),
    (
        "Skirmish",
        [
            (196.00, 0.35), (233.08, 0.35), (196.00, 0.35), (233.08, 0.35),
            (261.63, 0.35), (293.66, 0.35), (261.63, 0.35), (233.08, 0.35),
            (196.00, 0.35), (174.61, 0.35), (196.00, 0.35), (233.08, 0.35),
            (261.63, 0.7), (0, 0.1),
        ],
        150,
    ),
    (
        "Overdrive",
        [
            (293.66, 0.3), (329.63, 0.3), (349.23, 0.3), (392.00, 0.3),
            (349.23, 0.3), (329.63, 0.3), (293.66, 0.3), (261.63, 0.3),
            (293.66, 0.3), (349.23, 0.3), (392.00, 0.3), (440.00, 0.6),
            (0, 0.1),
        ],
        170,
    ),
]

menu_music_sounds = []
game_music_sounds = []
current_music_state = (None, None)

if AUDIO_ENABLED:
    try:
        for _name, _notes, _tempo in MENU_MUSIC_TRACKS:
            sound = pygame.mixer.Sound(buffer=_generate_music_loop(_notes, tempo=_tempo))
            sound.set_volume(0.35)
            menu_music_sounds.append(sound)

        for _name, _notes, _tempo in GAME_MUSIC_TRACKS:
            sound = pygame.mixer.Sound(buffer=_generate_music_loop(_notes, tempo=_tempo))
            sound.set_volume(0.3)
            game_music_sounds.append(sound)
    except pygame.error:
        AUDIO_ENABLED = False


music_enabled = True
TUTORIAL_BOT_BEHAVIORS = ["idle", "attack", "move"]
tutorial_bot_behavior = "idle"
npc_difficulty = 5  # 1 (Rookie) - 9 (Nightmare); shared across every game mode

INPUT_MODES = ["keyboard_mouse", "controller"]
INPUT_MODE_LABELS = {
    "keyboard_mouse": "KEYBOARD & MOUSE",
    "controller": "CONTROLLER",
}
input_mode = "keyboard_mouse"

active_controller = None
controller_backend = None  # "mapped" (pygame.controller) or "raw" (pygame.joystick fallback)

# Deadzone/sensitivity tuning for an Xbox-style pad. pygame.controller
# reports stick axes as ints in [-32768, 32767] and triggers as
# [0, 32767] - CONTROLLER_AXIS_MAX normalizes those to [-1, 1] / [0, 1].
# Raw pygame.joystick axes are already floats in [-1, 1], so they skip
# this normalization - see controller_axis() below.
CONTROLLER_AXIS_MAX = 32767
CONTROLLER_DEADZONE = 0.22
CONTROLLER_TRIGGER_THRESHOLD = 0.4
CONTROLLER_CURSOR_SPEED = 900  # px/sec for the virtual menu cursor

# Our own backend-agnostic "roles" - the rest of the code asks for e.g.
# ROLE_A rather than a raw button index, so it works the same whether the
# pad ended up on the mapped or the raw backend.
ROLE_LEFTX, ROLE_LEFTY = "leftx", "lefty"
ROLE_RIGHTX, ROLE_RIGHTY = "rightx", "righty"
ROLE_A, ROLE_B, ROLE_X = "a", "b", "x"
ROLE_START, ROLE_LEFTSHOULDER = "start", "leftshoulder"

if CONTROLLER_API_AVAILABLE:
    MAPPED_AXIS = {
        ROLE_LEFTX: pygame.CONTROLLER_AXIS_LEFTX, ROLE_LEFTY: pygame.CONTROLLER_AXIS_LEFTY,
        ROLE_RIGHTX: pygame.CONTROLLER_AXIS_RIGHTX, ROLE_RIGHTY: pygame.CONTROLLER_AXIS_RIGHTY,
    }
    MAPPED_BUTTON = {
        ROLE_A: pygame.CONTROLLER_BUTTON_A, ROLE_B: pygame.CONTROLLER_BUTTON_B,
        ROLE_X: pygame.CONTROLLER_BUTTON_X, ROLE_START: pygame.CONTROLLER_BUTTON_START,
        ROLE_LEFTSHOULDER: pygame.CONTROLLER_BUTTON_LEFTSHOULDER,
    }
else:
    MAPPED_AXIS = {}
    MAPPED_BUTTON = {}

# Standard Windows XInput layout - this is what a genuine Xbox pad (wired
# or wireless) reports through raw pygame.joystick even when SDL's
# GameControllerDB has no mapping entry for its exact product ID. This is
# the fallback that actually makes an "unrecognized" Xbox controller work.
RAW_AXIS = {ROLE_LEFTX: 0, ROLE_LEFTY: 1, ROLE_RIGHTX: 3, ROLE_RIGHTY: 4}
RAW_BUTTON = {ROLE_A: 0, ROLE_B: 1, ROLE_X: 2, ROLE_LEFTSHOULDER: 4, ROLE_START: 7}

MAPPED_BUTTON_REVERSE = {v: k for k, v in MAPPED_BUTTON.items()}
RAW_BUTTON_REVERSE = {v: k for k, v in RAW_BUTTON.items()}


def joystick_connected():
    return active_controller is not None


def refresh_active_joystick():
    """(Re)acquires the first connected pad, if any. Tries the mapped
    SDL GameController API first (correct names for anything SDL
    recognizes), and falls back to the raw joystick API - assuming a
    standard Xbox/XInput layout - for pads that are physically connected
    and working but that SDL doesn't have a mapping for. Safe to call
    repeatedly, e.g. on every hotplug event."""
    global active_controller, controller_backend

    if active_controller is not None:
        try:
            active_controller.get_init()
            return  # still connected and already initialized
        except pygame.error:
            active_controller = None
            controller_backend = None

    if CONTROLLER_API_AVAILABLE and pygame.controller.get_count() > 0:
        candidate = pygame.controller.Controller(0)
        candidate.init()
        active_controller = candidate
        controller_backend = "mapped"
        return

    if pygame.joystick.get_count() > 0:
        candidate = pygame.joystick.Joystick(0)
        candidate.init()
        active_controller = candidate
        controller_backend = "raw"


def controller_axis(role, invert=False):
    if active_controller is None:
        return 0.0

    try:
        if controller_backend == "mapped":
            axis_id = MAPPED_AXIS.get(role)

            if axis_id is None:
                return 0.0

            raw = active_controller.get_axis(axis_id) / CONTROLLER_AXIS_MAX
        else:
            axis_id = RAW_AXIS.get(role)

            if axis_id is None or axis_id >= active_controller.get_numaxes():
                return 0.0

            raw = active_controller.get_axis(axis_id)  # already -1.0..1.0
    except pygame.error:
        return 0.0

    if invert:
        raw = -raw

    if abs(raw) < CONTROLLER_DEADZONE:
        return 0.0

    # Rescale so movement starts at 0 right past the deadzone instead of
    # jumping straight to ~0.22, and still reaches a clean 1.0 at the edge.
    sign = 1 if raw > 0 else -1
    return sign * (abs(raw) - CONTROLLER_DEADZONE) / (1 - CONTROLLER_DEADZONE)


def controller_button(role):
    if active_controller is None:
        return False

    try:
        if controller_backend == "mapped":
            button_id = MAPPED_BUTTON.get(role)
        else:
            button_id = RAW_BUTTON.get(role)

        if button_id is None:
            return False

        if controller_backend == "raw" and button_id >= active_controller.get_numbuttons():
            return False

        return bool(active_controller.get_button(button_id))
    except pygame.error:
        return False



# Mirrors server.py's leveling curve, used here only to show "XP to next
# level" locally without an extra round trip.
LEVEL_THRESHOLDS = [
    0, 10, 20, 40, 70, 100, 140, 180, 230, 280,
    340, 400, 460, 520, 600, 670, 750, 830, 910, 1000,
    1100, 1210,
]

CHARACTER_UNLOCK_LEVEL = {
    "fire": 1,
    "ice": 2,
    "nature": 4,
    "earth": 6,
    "shadow": 8,
    "lightning": 10,
    "metal": 12,
    "rage": 14,
    "animalia": 16,
    "music": 18,
    "wind": 20,
    "water": 22,
}


def is_character_unlocked(element):
    if account_stats is not None and account_stats.get("is_admin"):
        return True  # admin has everything unlocked, always

    if account_username is None or account_stats is None:
        return True  # not logged in - no persistent progress to gate against

    return account_stats.get("level", 1) >= CHARACTER_UNLOCK_LEVEL.get(element, 1)


# --- Story Mode -------------------------------------------------------
#
# Narrative content, mission order, and save/load of campaign progress
# now live in story.py - referenced below as story.STORY_MISSIONS,
# story.STORY_INTRO_BEATS, etc. This file only keeps the glue that needs
# live game state (starting a duel, advancing game_state, and so on).

def start_story_cutscene(beats, next_state, mission_element=None):
    global story_cutscene_beats, story_cutscene_index, story_cutscene_reveal
    global story_cutscene_next_state, story_cutscene_mission_element, game_state

    story_cutscene_beats = beats
    story_cutscene_index = 0
    story_cutscene_reveal = 0.0
    story_cutscene_next_state = next_state
    story_cutscene_mission_element = mission_element
    game_state = "story_cutscene"


def begin_story_mission(element):
    """Kicks off the pre-fight cutscene for `element` - concatenating the
    kidnapping intro in front of it if this is the very first mission."""
    beats = story.STORY_MISSION_BEATS[element]["pre"]

    if element == story.STORY_MISSIONS[0]:
        beats = story.STORY_INTRO_BEATS + beats

    start_story_cutscene(beats, next_state="start_mission", mission_element=element)


def advance_story_cutscene():
    """Called when the player confirms past the last beat of whatever
    cutscene is currently playing. Resolves into either the next mission's
    duel, the next cutscene in a chain, or back to the story hub."""
    global story_active, story_current_mission, game_state, selected_element

    next_state = story_cutscene_next_state
    mission_element = story_cutscene_mission_element

    if next_state == "start_mission":
        selected_element = "fire"
        story_active = True
        story_current_mission = mission_element
        start_match(story_element=mission_element)
        game_state = "game"

    elif next_state == "story_finale":
        start_story_cutscene(story.STORY_FINALE_BEATS, next_state="story_hub")

    else:
        game_state = next_state

        if next_state == "story_hub" and story_progress >= len(story.STORY_MISSIONS):
            award_clue("clue_story_complete")


def resolve_story_match_result(won):
    """Called once, right when a story-mode duel ends, to advance (or not)
    the campaign and queue up the right follow-up cutscene."""
    global story_active, story_progress, story_current_mission, game_state

    element = story_current_mission
    story_active = False
    story_current_mission = None

    if not won:
        game_state = "story_hub"
        return

    mission_index = story.STORY_MISSIONS.index(element)
    story_progress = max(story_progress, mission_index + 1)
    story.save_story_progress(story_progress, account_username)

    is_final_mission = mission_index == len(story.STORY_MISSIONS) - 1
    next_state = "story_finale" if is_final_mission else "story_hub"
    start_story_cutscene(story.STORY_MISSION_BEATS[element]["post"], next_state=next_state)


selected_menu_track = 0
selected_game_track = 0


def update_music(desired_mode):
    global current_music_state

    if not AUDIO_ENABLED:
        return

    track_index = selected_menu_track if desired_mode == "menu" else selected_game_track
    desired_state = (desired_mode, track_index)

    if not music_enabled:
        if current_music_state != (None, None):
            pygame.mixer.stop()
            current_music_state = (None, None)
        return

    if desired_state == current_music_state:
        return

    pygame.mixer.stop()

    sounds = menu_music_sounds if desired_mode == "menu" else game_music_sounds

    if sounds:
        sounds[track_index].play(loops=-1)

    current_music_state = desired_state


def set_music_enabled(enabled):
    global music_enabled, current_music_state

    music_enabled = enabled

    if not enabled:
        pygame.mixer.stop()
        current_music_state = (None, None)


def cycle_menu_track():
    global selected_menu_track

    if not menu_music_sounds:
        return

    selected_menu_track = (selected_menu_track + 1) % len(menu_music_sounds)


def cycle_game_track():
    global selected_game_track

    if not game_music_sounds:
        return

    selected_game_track = (selected_game_track + 1) % len(game_music_sounds)


# --- Sound effects --------------------------------------------------------
# Short synthesized one-shot sounds (not looping music) for hits and
# ultimate casts, built the same way as the music tracks above.

def _generate_tone(frequency, duration, sample_rate=44100, volume=9000, sweep_to=None):
    samples = array.array("h")
    fade_samples = max(1, int(sample_rate * 0.01))
    total_samples = int(sample_rate * duration)

    for i in range(total_samples):
        progress = i / total_samples
        freq = frequency if sweep_to is None else frequency + (sweep_to - frequency) * progress
        fade = min(1.0, i / fade_samples, (total_samples - i) / fade_samples)
        value = int(volume * fade * math.sin(2 * math.pi * freq * i / sample_rate))
        samples.append(value)
        samples.append(value)

    return samples.tobytes()


hit_sound = None
ultimate_sound = None
level_up_sound = None

if AUDIO_ENABLED:
    try:
        hit_sound = pygame.mixer.Sound(buffer=_generate_tone(180, 0.08, volume=7000, sweep_to=90))
        ultimate_sound = pygame.mixer.Sound(buffer=_generate_tone(220, 0.5, volume=8500, sweep_to=440))
        level_up_sound = pygame.mixer.Sound(buffer=_generate_tone(392, 0.35, volume=8000, sweep_to=784))
        hit_sound.set_volume(0.25)
        ultimate_sound.set_volume(0.4)
        level_up_sound.set_volume(0.4)
    except pygame.error:
        pass


def play_sound(sound):
    if AUDIO_ENABLED and music_enabled and sound is not None:
        sound.play()


# --- World / camera setup -----------------------------------------------
# The arena is now bigger than the window, so the game view scrolls with
# the player (camera) and a minimap shows the whole map.

WORLD_WIDTH, WORLD_HEIGHT = 3000, 2000
ARENA = pygame.Rect(90, 90, WORLD_WIDTH - 180, WORLD_HEIGHT - 180)
ZONE_CENTER = Vector2(WORLD_WIDTH / 2, WORLD_HEIGHT / 2)

HUD_HEIGHT = 96
VIEW_RECT = pygame.Rect(0, HUD_HEIGHT, WIDTH, HEIGHT - HUD_HEIGHT)

MINIMAP_RECT = pygame.Rect(WIDTH - 220, 10, 210, 78)
_MINIMAP_SX = MINIMAP_RECT.width / WORLD_WIDTH
_MINIMAP_SY = MINIMAP_RECT.height / WORLD_HEIGHT

camera = Vector2(0, 0)

STEALTH_REVEAL_RANGE = 190

# --- Terrain zones -------------------------------------------------------
# Circular patches of terrain that change how each element plays there.
# Several full map layouts are defined below (see MAPS); TERRAIN_ZONES and
# SHADOW_POCKETS are populated by load_map() for whichever one is active.

TERRAIN_ZONES = []
SHADOW_POCKETS = []


def _random_point_in_circle(radius, margin=0.85):
    while True:
        x = random.uniform(-radius, radius)
        y = random.uniform(-radius, radius)
        if x * x + y * y <= (radius * margin) ** 2:
            return x, y


def _generate_zone_decor(zone):
    radius = zone["radius"]
    decor = {}

    if zone["type"] == "lava":
        decor["bubbles"] = []
        for _ in range(12):
            x, y = _random_point_in_circle(radius, 0.7)
            decor["bubbles"].append({
                "x": x, "y": y,
                "phase": random.uniform(0, 6.28),
                "speed": random.uniform(0.7, 1.4),
                "max_r": random.uniform(6, 15),
            })
        decor["embers"] = []
        for _ in range(10):
            x, y = _random_point_in_circle(radius, 0.9)
            decor["embers"].append({
                "x": x, "y": y,
                "speed": random.uniform(16, 32),
                "size": random.uniform(1.5, 3),
            })

    elif zone["type"] == "water":
        decor["ripples"] = [{"phase": random.uniform(0, 2.4)} for _ in range(3)]
        decor["sparkles"] = []
        for _ in range(18):
            x, y = _random_point_in_circle(radius, 0.9)
            decor["sparkles"].append({"x": x, "y": y, "phase": random.uniform(0, 6.28)})

    elif zone["type"] == "ice":
        decor["snow"] = []
        for _ in range(28):
            x, y = _random_point_in_circle(radius, 0.95)
            decor["snow"].append({
                "x": x, "y": y,
                "speed": random.uniform(16, 34),
                "drift_phase": random.uniform(0, 6.28),
                "size": random.uniform(1.5, 3.2),
            })
        decor["crystals"] = []
        for _ in range(6):
            x, y = _random_point_in_circle(radius, 0.7)
            decor["crystals"].append({"x": x, "y": y, "phase": random.uniform(0, 6.28)})

    elif zone["type"] == "grass":
        decor["blades"] = []
        for _ in range(45):
            x, y = _random_point_in_circle(radius, 0.95)
            decor["blades"].append({
                "x": x, "y": y,
                "phase": random.uniform(0, 6.28),
                "height": random.uniform(8, 17),
                "shade": random.uniform(0.8, 1.15),
            })
        decor["flowers"] = []
        for _ in range(9):
            x, y = _random_point_in_circle(radius, 0.85)
            color = random.choice([(255, 220, 120), (255, 160, 200), (225, 225, 255)])
            decor["flowers"].append({"x": x, "y": y, "color": color})

    elif zone["type"] == "stone":
        decor["rocks"] = []
        for _ in range(14):
            x, y = _random_point_in_circle(radius, 0.75)
            size = random.uniform(10, 24)
            points = []
            for corner in range(7):
                angle = math.radians(corner * (360 / 7) + random.uniform(-10, 10))
                point_r = size * random.uniform(0.75, 1.15)
                points.append((math.cos(angle) * point_r, math.sin(angle) * point_r))
            shade = random.uniform(0.75, 1.2)
            decor["rocks"].append({"x": x, "y": y, "points": points, "shade": shade})

    return decor


TERRAIN_COLORS = {
    "lava": (150, 45, 25),
    "stone": (95, 95, 105),
    "grass": (45, 100, 55),
    "ice": (110, 190, 230),
    "water": (35, 90, 150),
}

TERRAIN_BORDER_COLORS = {
    "lava": (255, 140, 60),
    "stone": (170, 170, 185),
    "grass": (140, 220, 130),
    "ice": (200, 240, 255),
    "water": (110, 190, 235),
}

# --- Maps -----------------------------------------------------------------
# Each map is a distinct arrangement of terrain zones and shadow pockets.
# World/arena size stays the same across maps - only what's placed on the
# floor changes.

MAPS = [
    {
        "name": "Elemental Crossroads",
        "zones": [
            {"type": "lava", "pos": Vector2(ARENA.left + 560, ARENA.top + 560), "radius": 240},
            {"type": "stone", "pos": Vector2(ARENA.right - 560, ARENA.top + 560), "radius": 250},
            {"type": "grass", "pos": Vector2(ARENA.left + 560, ARENA.bottom - 560), "radius": 260},
            {"type": "ice", "pos": Vector2(ARENA.right - 560, ARENA.bottom - 560), "radius": 240},
            {"type": "water", "pos": Vector2(ZONE_CENTER.x, ZONE_CENTER.y), "radius": 230},
        ],
        "shadow_pockets": [
            {"pos": Vector2(ARENA.left + 420, ARENA.centery - 220), "radius": 110},
            {"pos": Vector2(ARENA.right - 420, ARENA.centery - 220), "radius": 110},
            {"pos": Vector2(ZONE_CENTER.x - 540, ZONE_CENTER.y + 320), "radius": 120},
            {"pos": Vector2(ZONE_CENTER.x + 540, ZONE_CENTER.y + 320), "radius": 120},
            {"pos": Vector2(ARENA.left + 900, ARENA.top + 380), "radius": 100},
            {"pos": Vector2(ARENA.right - 900, ARENA.bottom - 380), "radius": 100},
        ],
    },
    {
        "name": "Volcanic Ring",
        "zones": [
            {"type": "lava", "pos": Vector2(ARENA.left + 480, ZONE_CENTER.y), "radius": 260},
            {"type": "lava", "pos": Vector2(ARENA.right - 480, ZONE_CENTER.y), "radius": 260},
            {"type": "stone", "pos": Vector2(ZONE_CENTER.x, ARENA.top + 420), "radius": 220},
            {"type": "stone", "pos": Vector2(ZONE_CENTER.x, ARENA.bottom - 420), "radius": 220},
        ],
        "shadow_pockets": [
            {"pos": Vector2(ZONE_CENTER.x, ZONE_CENTER.y), "radius": 130},
            {"pos": Vector2(ARENA.left + 300, ARENA.top + 300), "radius": 100},
            {"pos": Vector2(ARENA.right - 300, ARENA.bottom - 300), "radius": 100},
        ],
    },
    {
        "name": "Frozen Wastes",
        "zones": [
            {"type": "ice", "pos": Vector2(ARENA.left + 500, ARENA.top + 500), "radius": 260},
            {"type": "ice", "pos": Vector2(ARENA.right - 500, ARENA.bottom - 500), "radius": 260},
            {"type": "water", "pos": Vector2(ZONE_CENTER.x, ZONE_CENTER.y), "radius": 200},
            {"type": "stone", "pos": Vector2(ARENA.right - 500, ARENA.top + 500), "radius": 200},
        ],
        "shadow_pockets": [
            {"pos": Vector2(ARENA.left + 500, ARENA.bottom - 500), "radius": 110},
            {"pos": Vector2(ARENA.right - 900, ARENA.top + 320), "radius": 100},
            {"pos": Vector2(ARENA.left + 900, ARENA.bottom - 320), "radius": 100},
        ],
    },
    {
        "name": "Overgrown Ruins",
        "zones": [
            {"type": "grass", "pos": Vector2(ARENA.left + 450, ZONE_CENTER.y), "radius": 250},
            {"type": "grass", "pos": Vector2(ARENA.right - 450, ZONE_CENTER.y), "radius": 250},
            {"type": "stone", "pos": Vector2(ZONE_CENTER.x, ARENA.top + 380), "radius": 200},
            {"type": "stone", "pos": Vector2(ZONE_CENTER.x, ARENA.bottom - 380), "radius": 200},
        ],
        "shadow_pockets": [
            {"pos": Vector2(ZONE_CENTER.x, ZONE_CENTER.y), "radius": 110},
            {"pos": Vector2(ARENA.left + 300, ARENA.top + 260), "radius": 90},
            {"pos": Vector2(ARENA.right - 300, ARENA.top + 260), "radius": 90},
            {"pos": Vector2(ARENA.left + 300, ARENA.bottom - 260), "radius": 90},
            {"pos": Vector2(ARENA.right - 300, ARENA.bottom - 260), "radius": 90},
        ],
    },
    {
        "name": "Twin Isles",
        "zones": [
            {"type": "water", "pos": Vector2(ARENA.left + 520, ZONE_CENTER.y), "radius": 270},
            {"type": "water", "pos": Vector2(ARENA.right - 520, ZONE_CENTER.y), "radius": 270},
            {"type": "grass", "pos": Vector2(ZONE_CENTER.x, ARENA.top + 400), "radius": 200},
            {"type": "ice", "pos": Vector2(ZONE_CENTER.x, ARENA.bottom - 400), "radius": 200},
        ],
        "shadow_pockets": [
            {"pos": Vector2(ZONE_CENTER.x, ARENA.top + 260), "radius": 90},
            {"pos": Vector2(ZONE_CENTER.x, ARENA.bottom - 260), "radius": 90},
            {"pos": Vector2(ARENA.left + 900, ZONE_CENTER.y), "radius": 100},
            {"pos": Vector2(ARENA.right - 900, ZONE_CENTER.y), "radius": 100},
        ],
    },
]

MAP_RANDOM_INDEX = -1  # sentinel meaning "pick a random map at match start"
selected_map_index = 0

# Which arena each story-mode opponent fights on, so duels look like the
# character rather than always defaulting to the same generic arena.
# Falls back to the mixed "Elemental Crossroads" (0) for anyone without a
# strong thematic match among the existing maps.
STORY_MISSION_MAP_INDEX = {
    "ice": 2,        # Frozen Wastes
    "nature": 3,      # Overgrown Ruins
    "earth": 1,       # Volcanic Ring (stone-heavy)
    "shadow": 0,      # Elemental Crossroads
    "lightning": 0,   # Elemental Crossroads
    "metal": 1,       # Volcanic Ring (foundry-ish)
    "rage": 1,        # Volcanic Ring
    "animalia": 3,    # Overgrown Ruins
    "music": 0,       # Elemental Crossroads
    "wind": 0,        # Elemental Crossroads
    "water": 4,       # Twin Isles
}


def load_map(index):
    global TERRAIN_ZONES, SHADOW_POCKETS

    map_def = MAPS[index]

    TERRAIN_ZONES = []
    for zone in map_def["zones"]:
        loaded_zone = dict(zone)
        loaded_zone["decor"] = _generate_zone_decor(loaded_zone)
        TERRAIN_ZONES.append(loaded_zone)

    SHADOW_POCKETS = [dict(pocket) for pocket in map_def["shadow_pockets"]]


load_map(0)


def setup_domination_points():
    global domination_points

    mid_y = ARENA.centery
    domination_points = [
        {
            "name": "A", "pos": Vector2(ARENA.left + ARENA.width * 0.22, mid_y),
            "radius": DOMINATION_POINT_RADIUS, "progress": 0.0, "owner": None,
        },
        {
            "name": "B", "pos": Vector2(ARENA.centerx, mid_y),
            "radius": DOMINATION_POINT_RADIUS, "progress": 0.0, "owner": None,
        },
        {
            "name": "C", "pos": Vector2(ARENA.left + ARENA.width * 0.78, mid_y),
            "radius": DOMINATION_POINT_RADIUS, "progress": 0.0, "owner": None,
        },
    ]

selected_element = "fire"
opponent_count = 1
practice_mode = False
combat_input_locked = True

account_username = None
account_stats = None

story_active = False
story_current_mission = None
story_progress = story.load_story_progress(account_username)
story_cutscene_beats = []
story_cutscene_index = 0
story_cutscene_reveal = 0.0
story_cutscene_next_state = "menu"
story_cutscene_mission_element = None

secret_progress = secret.load_secret_progress(account_username)
secret_unlocked = secret.is_unlocked(secret_progress)
secret_toast_text = ""
secret_toast_timer = 0
secret_menu_click_times = []  # timestamps (seconds) of recent title clicks
secret_last_encyclopedia_views = []  # most recent elements viewed, in order
average_god_flipped = False  # which face the character-select card is showing

account_error = ""
account_field_username = ""
account_field_password = ""
account_active_field = "username"
account_show_password = False
account_delete_password = ""
account_delete_show_password = False
match_result_recorded = False

admin_password_field = ""
admin_password_show = False
admin_panel_error = ""
admin_panel_scroll = 0
admin_accounts = []
admin_confirm_delete_username = None  # set while confirming a specific delete

tutorial_active = False
tutorial_step = 0
tutorial_moved = False
tutorial_short_used = False
tutorial_long_used = False
tutorial_special_used = False
tutorial_ultimate_used = False
tutorial_advance_pressed = False

player = None
bots = []
projectiles = []
trails = []
effects = []
lightning_arcs = []
damage_numbers = []
kill_feed = []
screen_shake_timer = 0
screen_shake_magnitude = 0
show_fps = False

blizzard = None
earthquake = None
vine_leech = None
vine_whip = None
burrow = None
eternal_night = None
thunderstorm = None
hover = None
iron_maiden = None
bloodlust = None
adrenaline = None
bear_ride = None
monster = None
water_beam_visual = None
tsunami = None
fire_zone = None
symphony = None
cyclone = None

entering_tutorial = False
tutorial_element = "fire"
current_tutorial_steps = []

storm_radius = 1700
storm_wait = 16

CHAIN_LIGHTNING_RANGE = 220
CHAIN_LIGHTNING_CHANCE = 0.35
LIGHTNING_HOMING_RADIUS = 260
REFLECT_CHANCE = 0.05
COMPANION_STRIKE_CHANCE = 0.3
BEAR_SLASH_RANGE = 60
MONSTER_MOVE_SPEED = 260
MONSTER_ATTACK_RANGE = 60
MONSTER_MAX_HP = 220
MONSTER_NATURAL_DECAY_PER_SEC = MONSTER_MAX_HP / 30
THUNDERSTORM_RADIUS = 260
ICICLE_RING_COUNT = 16
ICICLE_RING_SPEED = 480
ICICLE_RING_DAMAGE = 14
ICICLE_RING_STUN = 3.0
FIGHTER_COLLISION_RADIUS = 18

STAMINA_COST_SHORT = 14
STAMINA_COST_LONG = 12
STAMINA_COST_SPECIAL = 22
STAMINA_COST_ULTIMATE = 35
STAMINA_DRAIN_CHANNEL_PER_SEC = 20
WATER_BEAM_RANGE = 480
WATER_BEAM_WIDTH = 30
WATER_BEAM_DPS = 24
UNDERTOW_CHANCE = 0.25

game_state = "menu"
game_over = False
winner_text = ""

# --- Domination (5v5) --------------------------------------------------
DOMINATION_TEAM_SIZE = 5
DOMINATION_SCORE_TARGET = 200
DOMINATION_TIME_LIMIT = 360  # 6 minutes
DOMINATION_POINT_RADIUS = 130
DOMINATION_CAPTURE_RATE = 16  # per stacked fighter, up to 3, per second
DOMINATION_DECAY_RATE = 4     # neutral drift back toward 0 when empty
DOMINATION_RESPAWN_GRACE = 1.5

domination_active = False
domination_points = []
domination_score = {"blue": 0, "red": 0}
domination_timer = 0
domination_tick_timer = 0

MENU_TITLE_RECT = pygame.Rect(0, 0, 420, 56)
MENU_TITLE_RECT.center = (WIDTH // 2, 120)

menu_buttons = {
    "play": pygame.Rect(400, 180, 300, 46),
    "characters": pygame.Rect(400, 234, 300, 46),
    "shop": pygame.Rect(400, 288, 300, 46),
    "settings": pygame.Rect(400, 342, 300, 46),
    "quit": pygame.Rect(400, 396, 300, 46),
}

MENU_BUTTON_LABELS = {
    "play": "PLAY",
    "characters": "CHARACTERS",
    "shop": "SHOP",
    "settings": "SETTINGS",
    "quit": "QUIT",
}

GAME_MODE_BUTTONS = {
    "quick_match": pygame.Rect(400, 195, 300, 50),
    "domination": pygame.Rect(400, 260, 300, 50),
    "story_mode": pygame.Rect(400, 325, 300, 50),
    "how_to_play": pygame.Rect(400, 390, 300, 50),
}

GAME_MODE_BUTTON_LABELS = {
    "quick_match": "QUICK MATCH",
    "domination": "DOMINATION (5v5)",
    "story_mode": "STORY MODE",
    "how_to_play": "HOW TO PLAY",
}

# Set when entering character select from the Domination button, so map
# select knows to skip straight into a 5v5 match instead of the normal
# opponent-count screen.
pending_domination = False

# Which screen "BACK" returns to from character select - it's entered from
# a couple of different places (Game Modes' Quick Match, and Practice
# Arena under How To Play), so we remember where we came from.
character_select_return_state = "game_modes"

ACCOUNT_CORNER_BUTTON = pygame.Rect(WIDTH - 190, 20, 170, 42)

HUB_BUTTONS = {
    "controls": pygame.Rect(400, 220, 300, 60),
    "tutorials": pygame.Rect(400, 300, 300, 60),
    "practice": pygame.Rect(400, 380, 300, 60),
}

HUB_BUTTON_LABELS = {
    "controls": "CONTROLS & TIPS",
    "tutorials": "CHARACTER TUTORIALS",
    "practice": "PRACTICE ARENA",
}

tutorial_select_buttons = {}

_TUT_COLS = 2
_TUT_BTN_W = 260
_TUT_BTN_H = 56
_TUT_GAP_X = 20
_TUT_GAP_Y = 14
_TUT_ROW_WIDTH = _TUT_COLS * _TUT_BTN_W + (_TUT_COLS - 1) * _TUT_GAP_X
_TUT_START_X = (WIDTH - _TUT_ROW_WIDTH) / 2
_TUT_START_Y = 150

for _index, _element in enumerate(e for e in ELEMENTS if e not in AVERAGE_GOD_ELEMENTS):
    _tut_col = _index % _TUT_COLS
    _tut_row = _index // _TUT_COLS

    tutorial_select_buttons[_element] = pygame.Rect(
        _TUT_START_X + _tut_col * (_TUT_BTN_W + _TUT_GAP_X),
        _TUT_START_Y + _tut_row * (_TUT_BTN_H + _TUT_GAP_Y),
        _TUT_BTN_W,
        _TUT_BTN_H,
    )

back_button = pygame.Rect(30, 25, 120, 42)

encyclopedia_selected = "fire"

encyclopedia_list_buttons = {}

_ENCY_COLS = 2
_ENCY_BTN_W = 105
_ENCY_BTN_H = 56
_ENCY_GAP_X = 10
_ENCY_GAP_Y = 10

for _index, _element in enumerate(e for e in ELEMENTS if e not in AVERAGE_GOD_ELEMENTS):
    _ency_col = _index % _ENCY_COLS
    _ency_row = _index // _ENCY_COLS

    encyclopedia_list_buttons[_element] = pygame.Rect(
        40 + _ency_col * (_ENCY_BTN_W + _ENCY_GAP_X),
        135 + _ency_row * (_ENCY_BTN_H + _ENCY_GAP_Y),
        _ENCY_BTN_W,
        _ENCY_BTN_H,
    )

element_buttons = {}

_GRID_COLS = 3
_GRID_MARGIN_X = 40
_GRID_GAP = 20
_GRID_TOP = 0
_GRID_ROW_H = 145
_GRID_ROW_GAP = 20
_GRID_BTN_W = (WIDTH - 2 * _GRID_MARGIN_X - (_GRID_COLS - 1) * _GRID_GAP) / _GRID_COLS

for _index, _element in enumerate(e for e in ELEMENTS if e not in AVERAGE_GOD_ELEMENTS):
    _col = _index % _GRID_COLS
    _row = _index // _GRID_COLS

    element_buttons[_element] = pygame.Rect(
        _GRID_MARGIN_X + _col * (_GRID_BTN_W + _GRID_GAP),
        _GRID_TOP + _row * (_GRID_ROW_H + _GRID_ROW_GAP),
        _GRID_BTN_W,
        _GRID_ROW_H,
    )

# The secret Average/God slot - one extra tile right after the normal
# roster, at whatever grid position comes next.
_AG_INDEX = len(element_buttons)
_AG_COL = _AG_INDEX % _GRID_COLS
_AG_ROW = _AG_INDEX // _GRID_COLS
AVERAGE_GOD_BUTTON = pygame.Rect(
    _GRID_MARGIN_X + _AG_COL * (_GRID_BTN_W + _GRID_GAP),
    _GRID_TOP + _AG_ROW * (_GRID_ROW_H + _GRID_ROW_GAP),
    _GRID_BTN_W,
    _GRID_ROW_H,
)
AVERAGE_GOD_FLIP_BUTTON = pygame.Rect(0, 0, 26, 26)  # positioned relative to the card each draw

CHAR_SELECT_TOP = 210
CHAR_SELECT_BOTTOM = HEIGHT - 20

character_select_scroll = 0


def character_select_max_scroll():
    total_slots = len(ELEMENTS) - len(AVERAGE_GOD_ELEMENTS) + 1  # the pair renders as one card
    rows = -(-total_slots // _GRID_COLS)  # ceil division
    content_height = rows * (_GRID_ROW_H + _GRID_ROW_GAP) - _GRID_ROW_GAP
    viewport_height = CHAR_SELECT_BOTTOM - CHAR_SELECT_TOP
    return max(0, content_height - viewport_height)


def character_select_screen_rect(base_rect):
    return pygame.Rect(
        base_rect.x,
        base_rect.y + CHAR_SELECT_TOP - character_select_scroll,
        base_rect.width,
        base_rect.height,
    )

MAX_OPPONENTS = 8

count_buttons = {}

_COUNT_COLS = 4
_COUNT_BTN_W = 150
_COUNT_BTN_H = 72
_COUNT_GAP_X = 20
_COUNT_GAP_Y = 18
_COUNT_ROW_WIDTH = _COUNT_COLS * _COUNT_BTN_W + (_COUNT_COLS - 1) * _COUNT_GAP_X
_COUNT_START_X = (WIDTH - _COUNT_ROW_WIDTH) / 2
_COUNT_START_Y = 310

for _count in range(1, MAX_OPPONENTS + 1):
    _idx = _count - 1
    _col = _idx % _COUNT_COLS
    _row = _idx // _COUNT_COLS

    count_buttons[_count] = pygame.Rect(
        _COUNT_START_X + _col * (_COUNT_BTN_W + _COUNT_GAP_X),
        _COUNT_START_Y + _row * (_COUNT_BTN_H + _COUNT_GAP_Y),
        _COUNT_BTN_W,
        _COUNT_BTN_H,
    )


def is_average_god_unlocked():
    if account_stats is not None and account_stats.get("is_admin"):
        return True

    return secret_unlocked


def switch_account_progress(username):
    """Reloads story/secret progress scoped to `username` (None for
    guest). Call this any time account_username actually changes -
    login, logout, or registering a new account - so progress never
    bleeds between accounts or shows guest progress while logged in."""
    global story_progress, secret_progress, secret_unlocked

    story_progress = story.load_story_progress(username)
    secret_progress = secret.load_secret_progress(username)
    secret_unlocked = secret.is_unlocked(secret_progress)


def award_secret_fragment(key):
    global secret_progress, secret_unlocked, secret_toast_text, secret_toast_timer

    if secret_progress.get(key):
        return  # already found

    secret_progress[key] = True
    secret.save_secret_progress(secret_progress, account_username)

    if secret.is_unlocked(secret_progress):
        secret_unlocked = True
        secret_toast_text = secret.UNLOCK_MESSAGE
    else:
        secret_toast_text = secret.FRAGMENT_MESSAGES[key]

    secret_toast_timer = 3.5


def award_clue(key):
    global secret_progress, secret_toast_text, secret_toast_timer

    if secret_progress.get(key) or secret_unlocked:
        return  # already shown, or no longer needed

    secret_progress[key] = True
    secret.save_secret_progress(secret_progress, account_username)
    secret_toast_text = secret.CLUE_TEXT[key]
    secret_toast_timer = 6.0  # clues get more reading time than fragment pings


def draw_secret_toast():
    if secret_toast_timer <= 0:
        return

    fade = min(1.0, secret_toast_timer / 1.0) if secret_toast_timer < 1.0 else 1.0
    lines = wrap_text(secret_toast_text, 640, font)

    if len(lines) == 1 and len(secret_toast_text) < 40:
        toast_surface = big_font.render(secret_toast_text, True, (255, 210, 120))
        toast_surface.set_alpha(int(255 * fade))
        screen.blit(toast_surface, toast_surface.get_rect(center=(WIDTH // 2, 110)))
        return

    box_height = 30 + len(lines) * 24
    box = pygame.Rect(0, 0, 680, box_height)
    box.center = (WIDTH // 2, 120)
    box_surface = pygame.Surface((box.width, box.height), pygame.SRCALPHA)
    box_surface.fill((10, 10, 16, int(200 * fade)))
    screen.blit(box_surface, box.topleft)

    line_y = box.top + 15

    for line in lines:
        line_surface = font.render(line, True, (255, 210, 120))
        line_surface.set_alpha(int(255 * fade))
        screen.blit(line_surface, line_surface.get_rect(center=(WIDTH // 2, line_y + 10)))
        line_y += 24


def draw_text(text, x, y, color="white", text_font=font):
    screen.blit(text_font.render(text, True, color), (x, y))


def draw_fitted_text(text, center, max_width, color="white", text_font=font):
    """Renders `text` centered at `center`, shrinking to a smaller font
    and finally truncating with an ellipsis if it would otherwise
    overflow max_width - used for settings buttons whose label includes
    variable content (track names, etc.) that can run long."""
    for candidate_font in (text_font, small_font):
        if candidate_font.size(text)[0] <= max_width:
            surface = candidate_font.render(text, True, color)
            screen.blit(surface, surface.get_rect(center=center))
            return

    trimmed = text

    while trimmed and small_font.size(trimmed + "...")[0] > max_width:
        trimmed = trimmed[:-1]

    surface = small_font.render(trimmed + "...", True, color)
    screen.blit(surface, surface.get_rect(center=center))


def wrap_text(text, max_width, text_font=font):
    words = text.split(" ")
    lines = []
    current_line = ""

    for word in words:
        candidate = f"{current_line} {word}".strip()

        if text_font.size(candidate)[0] <= max_width:
            current_line = candidate
        else:
            if current_line:
                lines.append(current_line)
            current_line = word

    if current_line:
        lines.append(current_line)

    return lines


def living_fighters():
    return [fighter for fighter in [player] + bots if fighter.alive]


def add_effect(position, color, radius, life):
    effects.append({
        "pos": Vector2(position),
        "color": color,
        "radius": radius,
        "life": life,
        "max_life": life,
    })


def spawn_damage_number(position, amount, color=(255, 235, 235)):
    damage_numbers.append({
        "pos": Vector2(position) + Vector2(random.uniform(-8, 8), -10),
        "text": str(int(round(amount))),
        "color": color,
        "life": 0.7,
        "max_life": 0.7,
    })


def spawn_kill_feed(text):
    kill_feed.append({"text": text, "life": 4.0})

    if len(kill_feed) > 5:
        kill_feed.pop(0)


def trigger_screen_shake(duration, magnitude):
    global screen_shake_timer, screen_shake_magnitude
    screen_shake_timer = duration
    screen_shake_magnitude = magnitude


def draw_health_bar(screen_pos, fighter):
    x = screen_pos.x - 25
    y = screen_pos.y - 35

    pygame.draw.rect(screen, (80, 25, 30), (x, y, 50, 7))

    pygame.draw.rect(
        screen,
        (80, 220, 100),
        (x, y, 50 * max(0, fighter.hp) / fighter.max_hp, 7),
    )


def draw_hud_status_icons(x, y):
    """Proper icon badges for the player's own active status effects,
    living in the HUD bar next to health/stamina/ultimate - replaces
    the small glyphs that used to float above the player's own head."""
    statuses = []

    if player.burn_timer > 0:
        statuses.append(("burn", (255, 140, 40), player.burn_timer))
    if player.slow_timer > 0:
        statuses.append(("slow", (150, 220, 255), player.slow_timer))
    if player.root_timer > 0:
        statuses.append(("root", (150, 110, 60), player.root_timer))
    if player.stun_timer > 0:
        statuses.append(("stun", (255, 235, 90), player.stun_timer))
    if player.fear_timer > 0:
        statuses.append(("fear", (170, 110, 210), player.fear_timer))
    if player.magnet_timer > 0:
        statuses.append(("magnet", (255, 100, 180), player.magnet_timer))
    if player.soak_timer > 0:
        statuses.append(("soak", (110, 180, 240), player.soak_timer))

    badge_size = 26
    gap = 4

    for index, (kind, color, remaining) in enumerate(statuses):
        badge = pygame.Rect(x + index * (badge_size + gap), y, badge_size, badge_size)
        draw_status_badge(badge, kind, color, remaining)


def draw_status_badge(badge, kind, color, remaining):
    pygame.draw.rect(screen, (25, 26, 34), badge, border_radius=7)
    pygame.draw.rect(screen, color, badge, 2, border_radius=7)

    center = Vector2(badge.centerx, badge.centery - 2)
    s = badge.width  # scale reference

    if kind == "burn":
        # A proper layered flame - outer lick + inner core.
        outer = [
            center + Vector2(0, -s * 0.32),
            center + Vector2(s * 0.20, -s * 0.02),
            center + Vector2(s * 0.14, s * 0.20),
            center + Vector2(0, s * 0.30),
            center + Vector2(-s * 0.14, s * 0.20),
            center + Vector2(-s * 0.20, -s * 0.02),
        ]
        pygame.draw.polygon(screen, color, [(p.x, p.y) for p in outer])
        inner_center = center + Vector2(0, s * 0.08)
        pygame.draw.circle(screen, (255, 235, 180), (int(inner_center.x), int(inner_center.y)), max(2, int(s * 0.09)))

    elif kind == "slow":
        # A real six-spoke snowflake with tick marks on each arm.
        for angle in (0, 60, 120):
            spoke = Vector2(0, -s * 0.28).rotate(angle)
            start = center - spoke
            end = center + spoke
            pygame.draw.line(screen, color, (start.x, start.y), (end.x, end.y), 2)

            for t in (0.5, -0.5):
                tick_center = center + spoke * t
                tick = spoke.rotate(90).normalize() * s * 0.09
                pygame.draw.line(
                    screen, color,
                    (tick_center.x - tick.x, tick_center.y - tick.y),
                    (tick_center.x + tick.x, tick_center.y + tick.y), 2,
                )

    elif kind == "root":
        # Entangling vine - a looped, thorny curve rather than a plain box.
        loop_rect = pygame.Rect(0, 0, s * 0.5, s * 0.5)
        loop_rect.center = (center.x, center.y)
        pygame.draw.arc(screen, color, loop_rect, 0.6, 5.4, 3)
        for angle in (40, 160, 260):
            thorn_dir = Vector2(1, 0).rotate(angle) * s * 0.14
            base = center + Vector2(1, 0).rotate(angle) * s * 0.2
            pygame.draw.line(screen, color, (base.x, base.y), (base.x + thorn_dir.x, base.y + thorn_dir.y), 2)

    elif kind == "stun":
        # A clean lightning bolt.
        bolt = [
            center + Vector2(-s * 0.05, -s * 0.32),
            center + Vector2(s * 0.14, -s * 0.02),
            center + Vector2(-s * 0.02, -s * 0.02),
            center + Vector2(s * 0.08, s * 0.32),
            center + Vector2(-s * 0.16, s * 0.02),
            center + Vector2(-s * 0.02, s * 0.02),
        ]
        pygame.draw.polygon(screen, color, [(p.x, p.y) for p in bolt])

    elif kind == "fear":
        # A wavering downward chevron, like a spooked step-back.
        pygame.draw.lines(
            screen, color, False,
            [
                (center.x - s * 0.2, center.y - s * 0.18),
                (center.x, center.y + s * 0.05),
                (center.x + s * 0.2, center.y - s * 0.18),
            ], 3,
        )
        pygame.draw.circle(screen, color, (int(center.x), int(center.y + s * 0.22)), max(2, int(s * 0.05)))

    elif kind == "magnet":
        # A horseshoe magnet with two poles, not just a dot-in-circle.
        magnet_rect = pygame.Rect(0, 0, s * 0.4, s * 0.4)
        magnet_rect.center = (center.x, center.y - s * 0.02)
        pygame.draw.arc(screen, color, magnet_rect, 0.3, math.pi - 0.3, 4)
        leg_y = center.y - s * 0.02 + s * 0.2
        pygame.draw.line(screen, color, (center.x - s * 0.2, center.y - s * 0.02), (center.x - s * 0.2, leg_y), 4)
        pygame.draw.line(screen, color, (center.x + s * 0.2, center.y - s * 0.02), (center.x + s * 0.2, leg_y), 4)
        pygame.draw.rect(screen, (255, 210, 90), (center.x - s * 0.24, leg_y - 3, s * 0.16, 4))
        pygame.draw.rect(screen, (200, 210, 220), (center.x + s * 0.08, leg_y - 3, s * 0.16, 4))

    elif kind == "soak":
        # A droplet with a highlight and a small ripple beneath it.
        drop = [
            center + Vector2(0, -s * 0.28),
            center + Vector2(s * 0.18, s * 0.12),
            center + Vector2(0, s * 0.26),
            center + Vector2(-s * 0.18, s * 0.12),
        ]
        pygame.draw.polygon(screen, color, [(p.x, p.y) for p in drop])
        pygame.draw.circle(screen, (200, 230, 255), (int(center.x - s * 0.05), int(center.y - s * 0.02)), max(2, int(s * 0.05)))

    # Duration remaining, small and unobtrusive in the corner.
    duration_text = small_font.render(f"{remaining:.1f}", True, "white")
    screen.blit(duration_text, (badge.right - duration_text.get_width() - 2, badge.bottom - 13))


def draw_status_icons(screen_pos, fighter):
    """Small glyphs above a fighter's health bar showing which status
    effects are currently active on them - a glance, not a label."""
    icons = []

    if fighter.burn_timer > 0:
        icons.append(("flame", (255, 140, 40)))
    if fighter.slow_timer > 0:
        icons.append(("snow", (150, 220, 255)))
    if fighter.root_timer > 0:
        icons.append(("root", (150, 110, 60)))
    if fighter.stun_timer > 0:
        icons.append(("stun", (255, 235, 90)))
    if fighter.fear_timer > 0:
        icons.append(("fear", (170, 110, 210)))
    if fighter.magnet_timer > 0:
        icons.append(("magnet", (255, 100, 180)))
    if fighter.soak_timer > 0:
        icons.append(("drop", (110, 180, 240)))

    if not icons:
        return

    icon_size = 12
    gap = 3
    total_width = len(icons) * icon_size + (len(icons) - 1) * gap
    start_x = screen_pos.x - total_width / 2
    icon_y = screen_pos.y - 50

    for index, (kind, color) in enumerate(icons):
        center = Vector2(start_x + index * (icon_size + gap) + icon_size / 2, icon_y)

        if kind == "flame":
            points = [
                center + Vector2(0, -6),
                center + Vector2(4, 4),
                center + Vector2(0, 1),
                center + Vector2(-4, 4),
            ]
            pygame.draw.polygon(screen, color, [(p.x, p.y) for p in points])

        elif kind == "snow":
            for angle in (0, 60, 120):
                a = Vector2(0, -5).rotate(angle)
                start_point = center - a
                end_point = center + a
                pygame.draw.line(screen, color, (start_point.x, start_point.y), (end_point.x, end_point.y), 2)

        elif kind == "root":
            pygame.draw.rect(screen, color, (center.x - 5, center.y - 5, 10, 10), border_radius=2)

        elif kind == "stun":
            points = [
                center + Vector2(-2, -6), center + Vector2(2, -1),
                center + Vector2(-1, -1), center + Vector2(3, 6),
                center + Vector2(-3, 1), center + Vector2(0, 1),
            ]
            pygame.draw.polygon(screen, color, [(p.x, p.y) for p in points])

        elif kind == "fear":
            pygame.draw.polygon(
                screen, color,
                [(center.x, center.y + 6), (center.x - 5, center.y - 5), (center.x + 5, center.y - 5)],
            )

        elif kind == "magnet":
            pygame.draw.circle(screen, color, center, 5, 2)
            pygame.draw.circle(screen, color, center, 2)

        elif kind == "drop":
            points = [
                center + Vector2(0, -6),
                center + Vector2(5, 4),
                center + Vector2(-5, 4),
            ]
            pygame.draw.polygon(screen, color, [(p.x, p.y) for p in points])
            pygame.draw.circle(screen, color, (center.x, center.y + 3), 4)


def world_to_screen(pos):
    return Vector2(
        pos[0] - camera.x + VIEW_RECT.left,
        pos[1] - camera.y + VIEW_RECT.top,
    )


def world_to_minimap(pos):
    return (
        MINIMAP_RECT.left + pos[0] * _MINIMAP_SX,
        MINIMAP_RECT.top + pos[1] * _MINIMAP_SY,
    )


def get_world_mouse():
    screen_mouse = pygame.mouse.get_pos()
    return Vector2(
        screen_mouse[0] - VIEW_RECT.left + camera.x,
        screen_mouse[1] - VIEW_RECT.top + camera.y,
    )


def update_camera():
    target_x = player.pos.x - VIEW_RECT.width / 2
    target_y = player.pos.y - VIEW_RECT.height / 2

    camera.x = max(0, min(WORLD_WIDTH - VIEW_RECT.width, target_x))
    camera.y = max(0, min(WORLD_HEIGHT - VIEW_RECT.height, target_y))

    if screen_shake_timer > 0:
        camera.x += random.uniform(-screen_shake_magnitude, screen_shake_magnitude)
        camera.y += random.uniform(-screen_shake_magnitude, screen_shake_magnitude)


def terrain_zone_at(position):
    for zone in TERRAIN_ZONES:
        if position.distance_to(zone["pos"]) < zone["radius"]:
            return zone

    return None


def terrain_speed_multiplier(fighter):
    zone = terrain_zone_at(fighter.pos)

    if zone is None:
        return 1

    if zone["type"] == "ice":
        return 1.35 if fighter.element == "ice" else 0.7

    if zone["type"] == "stone" and fighter.element != "earth":
        return 0.85

    return 1


def in_shadow_pocket(fighter):
    """Shadow fighters standing inside a shadow pocket cannot attack, charge
    ult, or be hit by incoming attacks. Other elements are unaffected."""
    if fighter is None or fighter.element != "shadow":
        return False

    for pocket in SHADOW_POCKETS:
        if fighter.pos.distance_to(pocket["pos"]) < pocket["radius"]:
            return True

    return False


def domination_spawn_point(team):
    """Blue spawns on the left edge of the arena, red on the right -
    matches capture point A/B/C running left-to-right across the middle."""
    y = ARENA.centery + random.uniform(-120, 120)

    if team == "blue":
        return Vector2(ARENA.left + 90, y)

    return Vector2(ARENA.right - 90, y)


def respawn_fighter(fighter):
    """Domination has no permanent elimination - death is an instant
    respawn back at your team's edge of the map, full health, with a
    brief window of invulnerability so you can't be re-killed the
    instant you reappear."""
    fighter.hp = fighter.max_hp
    fighter.stamina = fighter.MAX_STAMINA
    fighter.pos = domination_spawn_point(fighter.team)
    fighter.respawn_grace_timer = DOMINATION_RESPAWN_GRACE

    fighter.burn_timer = 0
    fighter.slow_timer = 0
    fighter.root_timer = 0
    fighter.magnet_timer = 0
    fighter.stun_timer = 0
    fighter.fear_timer = 0
    fighter.soak_timer = 0
    fighter.melee_swing_timer = 0

    for cooldown_name in fighter.cooldowns:
        fighter.cooldowns[cooldown_name] = max(fighter.cooldowns[cooldown_name], 0.5)

    add_effect(fighter.pos, ELEMENTS[fighter.element]["light_color"], 55, 0.4)


def update_domination(dt):
    global domination_timer, domination_tick_timer, game_over, winner_text

    for fighter in [player] + bots:
        if not fighter.alive:
            respawn_fighter(fighter)

    domination_timer += dt

    for point in domination_points:
        blue_count = 0
        red_count = 0

        for fighter in living_fighters():
            if fighter.pos.distance_to(point["pos"]) <= point["radius"]:
                if fighter.team == "blue":
                    blue_count += 1
                elif fighter.team == "red":
                    red_count += 1

        if blue_count > 0 and red_count == 0:
            rate = DOMINATION_CAPTURE_RATE * min(blue_count, 3)
            point["progress"] = min(100, point["progress"] + rate * dt)
        elif red_count > 0 and blue_count == 0:
            rate = DOMINATION_CAPTURE_RATE * min(red_count, 3)
            point["progress"] = max(-100, point["progress"] - rate * dt)
        elif blue_count == 0 and red_count == 0:
            if point["progress"] > 0:
                point["progress"] = max(0, point["progress"] - DOMINATION_DECAY_RATE * dt)
            elif point["progress"] < 0:
                point["progress"] = min(0, point["progress"] + DOMINATION_DECAY_RATE * dt)
        # else: contested (both teams present) - progress holds steady

        if point["progress"] >= 100:
            point["owner"] = "blue"
        elif point["progress"] <= -100:
            point["owner"] = "red"
        else:
            point["owner"] = None

    domination_tick_timer += dt

    if domination_tick_timer >= 1.0:
        domination_tick_timer -= 1.0

        for point in domination_points:
            if point["owner"] is not None:
                domination_score[point["owner"]] += 1

    time_up = domination_timer >= DOMINATION_TIME_LIMIT
    blue_score, red_score = domination_score["blue"], domination_score["red"]

    if blue_score >= DOMINATION_SCORE_TARGET or (time_up and blue_score > red_score):
        game_over = True
        winner_text = "VICTORY! BLUE TEAM WINS"
    elif red_score >= DOMINATION_SCORE_TARGET or (time_up and red_score > blue_score):
        game_over = True
        winner_text = "DEFEAT - RED TEAM WINS"
    elif time_up:
        game_over = True
        winner_text = "TIME'S UP - TIE GAME"


def apply_terrain_effects(dt):
    for fighter in living_fighters():
        if in_shadow_pocket(fighter):
            continue

        zone = terrain_zone_at(fighter.pos)
        zone_type = zone["type"] if zone else None

        if fighter.element == "earth":
            fighter.damage_reduction = 0.15 if zone_type == "stone" else 0

        if zone_type == "lava":
            if fighter.element == "fire":
                fighter.hp = min(fighter.max_hp, fighter.hp + 6 * dt)
                fighter.ult = min(100, fighter.ult + 8 * dt)
            else:
                fighter.damage(14 * dt)
                fighter.burn(0.6)

        elif zone_type == "grass":
            heal = 8 * dt if fighter.element == "nature" else 2 * dt
            fighter.hp = min(fighter.max_hp, fighter.hp + heal)

        elif zone_type == "stone":
            if fighter.element != "earth":
                fighter.slow(0.3)


def resolve_fighter_collisions():
    """Fighters now physically collide instead of passing through each
    other. Each pair of living fighters that overlap gets pushed apart
    along the line between them, split evenly between the two."""
    fighters = living_fighters()

    for i in range(len(fighters)):
        for j in range(i + 1, len(fighters)):
            fighter_a = fighters[i]
            fighter_b = fighters[j]

            # A hidden shadow fighter can't be interacted with at all,
            # so let others walk straight through them.
            if in_shadow_pocket(fighter_a) or in_shadow_pocket(fighter_b):
                continue

            delta = fighter_a.pos - fighter_b.pos
            distance = delta.length()
            min_distance = FIGHTER_COLLISION_RADIUS * 2

            if 0 < distance < min_distance:
                overlap = min_distance - distance
                push = delta.normalize() * (overlap / 2)

                fighter_a.pos += push
                fighter_b.pos -= push

                fighter_a.keep_in_arena(ARENA)
                fighter_b.keep_in_arena(ARENA)

            elif distance == 0:
                # Exactly stacked (rare) - nudge apart in a fixed direction
                # so they don't stay glued together forever.
                nudge = Vector2(1, 0) * (min_distance / 2)
                fighter_a.pos += nudge
                fighter_b.pos -= nudge
                fighter_a.keep_in_arena(ARENA)
                fighter_b.keep_in_arena(ARENA)


def start_match(practice=False, story_element=None, domination=False):
    global player, bots, projectiles, trails, effects, lightning_arcs
    global damage_numbers, kill_feed, screen_shake_timer
    global blizzard, earthquake, vine_leech, vine_whip, burrow, eternal_night, thunderstorm
    global hover, iron_maiden, bloodlust, adrenaline, bear_ride, monster
    global water_beam_visual, tsunami, fire_zone, symphony, cyclone
    global storm_radius, storm_wait, game_over, winner_text, practice_mode
    global combat_input_locked
    global match_result_recorded
    global ultimate_lock_timer, ultimate_lock_owner
    global domination_active, domination_timer, domination_tick_timer, domination_score

    if practice:
        load_map(0)
    elif story_element is not None:
        load_map(STORY_MISSION_MAP_INDEX.get(story_element, 0))
    elif selected_map_index == MAP_RANDOM_INDEX:
        load_map(random.randrange(len(MAPS)))
    else:
        load_map(selected_map_index)

    domination_active = domination

    if domination:
        setup_domination_points()
        domination_timer = 0
        domination_tick_timer = 0
        domination_score = {"blue": 0, "red": 0}

    combat_input_locked = True
    match_result_recorded = False
    ultimate_lock_timer = 0
    ultimate_lock_owner = None
    practice_mode = practice

    if domination:
        player = Fighter(
            selected_element,
            domination_spawn_point("blue"),
            "YOU",
            300,
            starting_ult=40,
            team="blue",
        )

        if selected_element == "earth":
            player.max_hp = 135
            player.hp = 135
        elif selected_element == "average":
            player.max_hp = 78
            player.hp = 78

        available_elements = [
            element for element in ELEMENTS
            if element != selected_element and element not in AVERAGE_GOD_ELEMENTS
        ]
        random.shuffle(available_elements)
        ally_elements = (available_elements * 2)[:DOMINATION_TEAM_SIZE - 1]

        enemy_pool = [element for element in ELEMENTS if element not in AVERAGE_GOD_ELEMENTS]
        random.shuffle(enemy_pool)
        enemy_elements = (enemy_pool * 2)[:DOMINATION_TEAM_SIZE]

        bots = []

        for number, element in enumerate(ally_elements):
            ally = Fighter(
                element, domination_spawn_point("blue"),
                f"{ELEMENTS[element]['name']} (Ally)", 155, team="blue",
            )

            if element == "earth":
                ally.max_hp = 135
                ally.hp = 135

            ally.cooldowns["long"] = 0.5 + number * 0.2
            bots.append(ally)

        for number, element in enumerate(enemy_elements):
            enemy = Fighter(
                element, domination_spawn_point("red"),
                f"{ELEMENTS[element]['name']} BOT {number + 1}", 155, team="red",
            )

            if element == "earth":
                enemy.max_hp = 135
                enemy.hp = 135

            enemy.cooldowns["long"] = 0.5 + number * 0.2
            bots.append(enemy)

    elif story_element is not None:
        player = Fighter(
            "fire",
            (ZONE_CENTER.x - 260, ZONE_CENTER.y),
            "YOU",
            300,
            starting_ult=40,
        )

        bot = Fighter(
            story_element,
            (ZONE_CENTER.x + 260, ZONE_CENTER.y),
            ELEMENTS[story_element]["name"],
            155,
        )

        if story_element == "earth":
            bot.max_hp = 135
            bot.hp = 135

        bots = [bot]

    else:
        player = Fighter(
            selected_element,
            (ZONE_CENTER.x - (450 if practice else 0), ZONE_CENTER.y),
            "YOU",
            300,
            starting_ult=100 if practice else 40,
        )

        if selected_element == "earth":
            player.max_hp = 135
            player.hp = 135

        if practice:
            dummy_speed = 0 if tutorial_bot_behavior == "idle" else 150

            dummy = Fighter(
                "earth",
                (ZONE_CENTER.x + 450, ZONE_CENTER.y),
                "TRAINING DUMMY",
                dummy_speed,
            )
            dummy.max_hp = 100000
            dummy.hp = 100000
            dummy.wander_timer = 0
            bots = [dummy]
        else:
            spawn_positions = [
                (ARENA.left + 220, ARENA.top + 220),
                (ARENA.right - 220, ARENA.top + 220),
                (ARENA.left + 220, ARENA.bottom - 220),
                (ARENA.right - 220, ARENA.bottom - 220),
                (ARENA.centerx, ARENA.top + 220),
                (ARENA.centerx, ARENA.bottom - 220),
                (ARENA.left + 220, ARENA.centery),
                (ARENA.right - 220, ARENA.centery),
            ]

            available_elements = [
                element for element in ELEMENTS
                if element != selected_element and element not in AVERAGE_GOD_ELEMENTS
            ]
            random.shuffle(available_elements)

            bots = []

            for number in range(opponent_count):
                element = available_elements[number % len(available_elements)]

                bot = Fighter(
                    element,
                    spawn_positions[number],
                    f"{ELEMENTS[element]['name']} BOT {number + 1}",
                    155,
                )

                if element == "earth":
                    bot.max_hp = 135
                    bot.hp = 135

                bot.cooldowns["long"] = 0.8 + number * 0.3
                bots.append(bot)

    projectiles = []
    trails = []
    effects = []
    lightning_arcs = []
    damage_numbers = []
    kill_feed = []
    screen_shake_timer = 0

    blizzard = None
    earthquake = None
    vine_leech = None
    vine_whip = None
    burrow = None
    eternal_night = None
    thunderstorm = None
    hover = None
    iron_maiden = None
    bloodlust = None
    adrenaline = None
    bear_ride = None
    monster = None
    water_beam_visual = None
    tsunami = None
    fire_zone = None
    symphony = None
    cyclone = None

    storm_radius = 6000 if (practice or story_element is not None or domination) else 1700
    storm_wait = 999999 if (practice or story_element is not None or domination) else 16

    game_over = False
    winner_text = ""

    update_camera()


ELEMENT_TUTORIAL_TEXT = {
    "fire": {
        "short": (
            "Left Click to swing Blade of Flame - a short melee hit that "
            "also sets your target on fire (Too Hot To Handle), ticking "
            "extra damage over time."
        ),
        "long": "Right Click throws Fireballs - fast projectiles that ignite anything they touch.",
        "special": (
            "Shift for Rocket Shoes - a quick fire dash that leaves a "
            "burning trail behind you. Enemies who step in it take burn "
            "damage, so dash through a crowd if you can."
        ),
        "ultimate": (
            "Supernova detonates a massive fire blast centered on you - "
            "the closer enemies are, the more it hurts - and leaves the "
            "ground burning for several seconds afterward, so don't "
            "linger in your own blast site."
        ),
        "tip": "Your burn trail lingers on the ground - use it to zone enemies away, not just to escape.",
        "terrain": (
            "Step into the lava zone (orange-bordered pool) - it heals "
            "you and charges your ultimate fast, while it burns anyone "
            "else who wanders in."
        ),
    },
    "ice": {
        "short": "Left Click for Frosted Knife - a quick jab that slows your target.",
        "long": "Right Click throws Icicles, which slow on impact too.",
        "special": (
            "Hold Shift to skate - unlike most specials this has no time "
            "limit, so you glide for as long as you hold it, leaving an "
            "ice trail that speeds YOU up if you cross back over it."
        ),
        "ultimate": (
            "Blizzard bursts an instant ring of icicles outward that "
            "stuns anyone it hits for 3 seconds, then leaves a moving "
            "storm around you - anyone who lingers in it gets slowed, "
            "then frozen solid and hit hard if they don't leave in time."
        ),
        "tip": (
            "Loop your skate trail around an enemy - they get slowed by "
            "your attacks while you stay fast crossing your own ice."
        ),
        "terrain": "The ice patch on the map boosts your movement further, and turns brutally slippery for everyone else.",
    },
    "nature": {
        "short": "Left Click for Flower Power - a melee bloom that briefly roots the target in place.",
        "long": "Right Click fires a 3-shot Thorn Volley spread instead of a single shot, good for area denial.",
        "special": "Shift is Vine Whip - yank yourself toward wherever your mouse is pointing, great for closing distance or escaping.",
        "ultimate": (
            "Leeching Vines drains health from every enemy in range "
            "continuously and heals you for the same amount - the "
            "longer you keep multiple enemies in range, the more it's worth."
        ),
        "tip": "Natural Respiration heals you passively even outside your ultimate, so you can afford to play patiently.",
        "terrain": "Stand in the grass zone to heal even faster than your passive already gives you.",
    },
    "earth": {
        "short": "Left Click for Rock Barrage - a heavy melee hit that roots the target.",
        "long": "Right Click launches Earth Shift boulders.",
        "special": "Shift to Burrow - a short underground dash that's hard to interrupt.",
        "ultimate": (
            "Earth Waves Goodbye ripples out from you repeatedly for its "
            "duration, damaging, rooting, and knocking back everyone "
            "nearby - stand in a cluster of enemies for full value."
        ),
        "tip": "Homeland gives you +35% max health passively, so you can tank hits other elements can't. Use that cushion to stay aggressive.",
        "terrain": "The stone zone adds extra damage reduction on top of your passive, while it just slows everyone else down.",
    },
    "shadow": {
        "short": "Left Click for Warp - you blink right up to the target as you strike, so it works even at awkward angles.",
        "long": "Right Click fires Vortex, which pulls whoever it hits toward you.",
        "special": "Shift for a pure teleport dash - One With Shadows.",
        "ultimate": (
            "Eternal Night darkens the arena, slows every enemy, and "
            "gives you damage reduction for its duration - use it to "
            "turn a losing fight around."
        ),
        "tip": (
            "The map has dark shadow pockets - stand in one and you "
            "become completely untargetable (can't be hit, but also "
            "can't attack or heal) until you leave. Great for resetting "
            "a fight or escaping lethal damage."
        ),
        "terrain": "You don't need a specific terrain zone - your shadow pockets work wherever they're placed, check the minimap for their locations.",
    },
    "lightning": {
        "short": "Left Click for Static Kung Fu, a melee zap with a chance to arc to a second nearby enemy (Deadly Network).",
        "long": "Right Click fires a homing Lightning Bolt that curves harder toward anyone already Magnetized.",
        "special": "Shift is Charged Displacement - a short, cheap teleport-dash you can chain quickly since its cooldown is very short.",
        "ultimate": (
            "Thunderstorm strikes any opponent within a radius around "
            "you (shown as a yellow ring) automatically at a steady "
            "interval - it can't miss inside that ring, so pull enemies "
            "close before using it."
        ),
        "tip": "Any hit applies Magnetized, which makes your next Lightning Bolt curve much harder onto that target - chain your short and long attacks together.",
        "terrain": "No zone favors you specifically, but your mobility means you can reach any zone first and deny it to others.",
    },
    "metal": {
        "short": "Left Click for Man Of Steel - a melee hit that also drops a spike hazard where your target stood.",
        "long": "Right Click fires Shrapnel Blast, a 5-pellet shotgun spread instead of one shot.",
        "special": "Shift activates Hoverboard, a big steerable speed boost.",
        "ultimate": (
            "Iron Maiden Cage locks onto the nearest enemy, roots them, "
            "and slowly crushes them - damage ramps up sharply the "
            "longer they're trapped, so use it early in a fight."
        ),
        "tip": "Reflective Body gives a quiet passive chance to bounce incoming long-range attacks back at whoever fired them - it just happens, no input needed.",
        "terrain": "No zone favors you specifically, but your shotgun spread rewards closing distance rather than staying at max range.",
    },
    "rage": {
        "short": "Left Click swings your Axe.",
        "long": "Right Click throws a pair of Throwing Knives.",
        "special": "Shift triggers Adrenaline Rush for a temporary +50% speed burst.",
        "ultimate": (
            "Bloodlust burns 75% of your CURRENT health for a massive "
            "damage multiplier - the lower your health already is, the "
            "less you're risking, so it's strongest as a desperate "
            "comeback tool, not an opener."
        ),
        "tip": "An Eye For An Eye scales your damage up automatically the lower your health drops - don't be afraid to fight at low HP, you hit much harder there.",
        "terrain": "No zone favors you directly - lean on your damage scaling instead of positioning.",
    },
    "animalia": {
        "short": "Left Click for Simple Yet Effective, a spear jab that fears the target (reduces their damage briefly).",
        "long": "Right Click fires Hunter's Bow And Arrow.",
        "special": "Hold Shift for Natural Taxi - ride a bear for as long as you hold it, auto-slashing anyone who gets close.",
        "ultimate": (
            "Ancient Monster summons a T-Rex that hunts enemies on its "
            "own - it acts independently, so you're free to keep "
            "fighting elsewhere while it works. It has a real health "
            "bar: it can be killed if focused down, but otherwise "
            "slowly weakens with old age until it dies on its own."
        ),
        "tip": "Unspoken Bond gives your companion a chance to land a bonus hit whenever you do - keep the pressure on to see it trigger more.",
        "terrain": "No zone favors you directly - your bear ride's mobility lets you fight from wherever suits you.",
    },
    "water": {
        "short": "Left Click for Tidal Strike - a melee hit that also Waterlogs the target, slowing how fast their attacks recover.",
        "long": (
            "Hold Right Click for Water Beam - unlike everyone else's "
            "long-range attack, this is a continuous channel with no "
            "cooldown, not a single shot. Keep it aimed at a target to "
            "keep damaging them."
        ),
        "special": "Shift triggers Riptide Dash, a quick burst dash.",
        "ultimate": (
            "Twin Tsunami sends two walls of water sweeping in from "
            "either side of the arena, damaging and shoving anyone they "
            "hit to a new spot - good for repositioning a fight or "
            "separating enemies."
        ),
        "tip": "Undertow gives you a passive chance to slow anyone who hits you in melee - it's automatic, just let them attack you.",
        "terrain": "Stand in the water zone at the map's center - it slows down projectiles passing through it, buying you time defensively.",
    },
    "music": {
        "short": "Left Click for Discordant Beat - a melee hit that throws the target off rhythm, slowing them down.",
        "long": "Right Click for Sound Wave - a ranged shot that also slows whoever it hits.",
        "special": "Shift triggers Sonic Boom, a quick dash that leaves a ringing trail behind you.",
        "ultimate": (
            "Symphony of Chaos is different from other ultimates - hold "
            "both attack buttons to channel a cone-shaped shriek toward "
            "your aim, damaging, stunning, and healing you a little with "
            "every tick. It drains your ultimate bar as you hold it "
            "instead of spending it all at once, so you can use it with "
            "any amount of charge, not just at 100%."
        ),
        "tip": "Perfect Pitch means every hit you land slows the target's next moves - stack it up to control a fight.",
        "terrain": "Terrain doesn't treat Music specially - use positioning and your slows to control the fight instead.",
    },
    "wind": {
        "short": "Left Click for Gale Palm - a melee hit that also shoves the target back and slows them.",
        "long": "Right Click for Slipstream Blast - a fast, long-range shot that slows whoever it hits.",
        "special": "Shift triggers Tailwind Dash, a long burst dash that also gusts nearby enemies away from you.",
        "ultimate": (
            "Cyclone opens a vortex centered on you that pulls every "
            "opponent in range steadily toward its eye, damaging them "
            "the whole way in."
        ),
        "tip": "Featherweight means you're simply faster than everyone else in the arena, all the time - use the extra speed to control range.",
        "terrain": "Terrain doesn't treat Wind specially - your natural speed already does most of the work getting around it.",
    },
}


def build_tutorial_steps(element):
    """Builds a tutorial script hand-written for this specific element -
    its actual moves, its actual strategy, not a generic template."""
    data = ELEMENTS[element]
    text = ELEMENT_TUTORIAL_TEXT[element]

    return [
        {
            "text": "Use WASD to move around the arena.",
            "check": lambda: tutorial_moved,
        },
        {
            "text": text["short"],
            "check": lambda: tutorial_short_used,
        },
        {
            "text": text["long"],
            "check": lambda: tutorial_long_used,
        },
        {
            "text": text["special"],
            "check": lambda: tutorial_special_used,
        },
        {
            "text": (
                f"Land hits to fill your ultimate bar (top HUD), then "
                f"press Left + Right Click together to unleash it: "
                f"{text['ultimate']}"
            ),
            "check": lambda: tutorial_ultimate_used,
        },
        {
            "text": f"{data['passive_name']} - {text['tip']} Press SPACE to continue.",
            "check": lambda: tutorial_advance_pressed,
        },
        {
            "text": f"{text['terrain']} Press SPACE to continue.",
            "check": lambda: tutorial_advance_pressed,
        },
        {
            "text": (
                "The minimap (top-right) shows the whole arena, "
                "terrain, and every fighter. Press SPACE to continue."
            ),
            "check": lambda: tutorial_advance_pressed,
        },
        {
            "text": (
                "In a real match, a storm zone shrinks over time and "
                "damages anyone caught outside it (disabled here). "
                "Press SPACE to continue."
            ),
            "check": lambda: tutorial_advance_pressed,
        },
        {
            "text": "You're ready! Press Esc any time to return to the menu.",
            "check": None,
        },
    ]


def start_tutorial(element="fire"):
    global selected_element, tutorial_element, current_tutorial_steps
    global tutorial_active, tutorial_step
    global tutorial_moved, tutorial_short_used, tutorial_long_used
    global tutorial_special_used, tutorial_ultimate_used, tutorial_advance_pressed

    selected_element = element
    tutorial_element = element
    start_match(practice=True)

    current_tutorial_steps = build_tutorial_steps(element)

    tutorial_active = True
    tutorial_step = 0
    tutorial_moved = False
    tutorial_short_used = False
    tutorial_long_used = False
    tutorial_special_used = False
    tutorial_ultimate_used = False
    tutorial_advance_pressed = False


def nearest_target(fighter):
    choices = []

    for other in opponents_of(fighter):
        if eternal_night is not None and other is eternal_night["owner"]:
            if fighter.pos.distance_to(other.pos) > STEALTH_REVEAL_RANGE:
                continue

        if in_shadow_pocket(other):
            # Hidden shadow fighters can't be targeted or tracked by
            # anyone else, whether it's the player or a bot.
            continue

        choices.append(other)

    if not choices:
        return None

    return min(
        choices,
        key=lambda other: fighter.pos.distance_to(other.pos),
    )


def owner_damage_multiplier(fighter):
    """Rage's An Eye For An Eye (more damage the lower your health),
    Bloodlust's temporary +200% buff, and Animalia's Fear effect (less
    damage while feared) all scale a fighter's outgoing damage, so they
    all live here in one shared hook."""
    multiplier = 1

    if fighter.element == "rage":
        missing_fraction = 1 - max(0, fighter.hp) / fighter.max_hp
        multiplier *= 1 + missing_fraction

        if bloodlust is not None and bloodlust["owner"] is fighter:
            multiplier *= 3

    if fighter.fear_timer > 0:
        multiplier *= 0.85

    return multiplier


def spawn_icicle_ring(fighter):
    """Ice's ultimate buff: an instant burst of icicles fired in a full
    circle around the caster, each stunning whatever it hits."""
    for index in range(ICICLE_RING_COUNT):
        angle = (360 / ICICLE_RING_COUNT) * index
        direction = Vector2(1, 0).rotate(angle)

        projectiles.append({
            "pos": fighter.pos.copy(),
            "velocity": direction * ICICLE_RING_SPEED,
            "owner": fighter,
            "element": "ice",
            "damage": ICICLE_RING_DAMAGE,
            "color": (150, 220, 255),
            "radius": 8,
            "life": 1.0,
            "stun_ring": True,
        })


def shoot_projectile(owner, direction, life=2.6):
    if direction.length() == 0:
        return

    if in_shadow_pocket(owner):
        return

    if not owner.has_stamina(STAMINA_COST_LONG):
        return

    owner.spend_stamina(STAMINA_COST_LONG)

    stats = {
        "fire": ((255, 150, 25), 13, 570, 9),
        "ice": ((100, 220, 255), 11, 460, 8),
        "nature": ((100, 210, 75), 9, 520, 7),
        "earth": ((160, 120, 75), 15, 380, 12),
        "shadow": ((150, 100, 200), 12, 500, 8),
        "lightning": ((255, 240, 120), 11, 650, 7),
        "metal": ((195, 200, 210), 8, 480, 6),
        "rage": ((200, 200, 210), 10, 600, 6),
        "animalia": ((150, 110, 60), 14, 600, 6),
        "water": ((90, 170, 230), 10, 520, 7),
        "music": ((220, 100, 210), 10, 540, 8),
        "wind": ((200, 235, 225), 9, 700, 7),
        "average": ((160, 160, 160), 8, 420, 7),
        "god": ((255, 215, 130), 24, 500, 14),
    }

    color, damage, speed, radius = stats[owner.element]
    damage *= owner_damage_multiplier(owner)

    projectiles.append({
        "pos": owner.pos.copy(),
        "velocity": direction.normalize() * speed,
        "owner": owner,
        "element": owner.element,
        "damage": damage,
        "color": color,
        "radius": radius,
        "life": life,
    })


def apply_element_effect(target, element):
    if element == "fire":
        target.burn(2.5)

    elif element == "ice":
        target.slow(2.5)

    elif element == "nature":
        target.root(0.35)

    elif element == "earth":
        target.root(0.45)

    elif element == "shadow":
        target.slow(1.2)

    elif element == "lightning":
        target.magnetize(1.5)

    elif element == "metal":
        target.ult = max(0, target.ult - 8)
        target.slow(0.4)

    elif element == "rage":
        target.slow(0.3)

    elif element == "animalia":
        target.fear(2.5)

    elif element == "water":
        target.soak(1.5)

    elif element == "music":
        target.slow(1.2)

    elif element == "wind":
        target.slow(0.9)

    elif element == "god":
        target.stun(0.3)


def try_chain_lightning(source, primary_target, base_damage):
    """Lightning's Deadly Network passive: a chance for a hit to arc
    from the primary target to another nearby living enemy."""
    if random.random() > CHAIN_LIGHTNING_CHANCE:
        return

    candidates = [
        fighter for fighter in opponents_of(source)
        if fighter is not primary_target
        and fighter.pos.distance_to(primary_target.pos) < CHAIN_LIGHTNING_RANGE
    ]

    if not candidates:
        return

    chained = min(
        candidates,
        key=lambda fighter: fighter.pos.distance_to(primary_target.pos),
    )

    chained.damage(base_damage * 0.5)
    chained.magnetize(1.5)

    lightning_arcs.append({
        "a": primary_target.pos.copy(),
        "b": chained.pos.copy(),
        "life": 0.18,
        "max_life": 0.18,
    })


def try_companion_strike(target, base_damage):
    """Animalia's Unspoken Bond passive: the animal companion sometimes
    joins in with a bonus hit on whatever its owner just struck."""
    if random.random() > COMPANION_STRIKE_CHANCE:
        return

    target.damage(base_damage * 0.4)
    add_effect(target.pos, (205, 175, 95), 35, 0.2)


def player_short_attack(aim_direction=None):
    direction = aim_direction if aim_direction is not None else (get_world_mouse() - player.pos)
    perform_short_attack(player, direction)


def perform_short_attack(attacker, aim_direction):
    """Melee attack for ANY fighter - the player (via player_short_attack
    above) or a bot (via bot AI). Targeting respects team via
    opponents_of(), so allies never hit each other in Domination."""
    global monster

    if in_shadow_pocket(attacker):
        return

    if not attacker.has_stamina(STAMINA_COST_SHORT):
        return

    direction = aim_direction

    if direction is None or direction.length() == 0:
        return

    attacker.spend_stamina(STAMINA_COST_SHORT)
    attacker.trigger_melee_swing(direction)

    targets = []
    short_range = 150 if attacker.element == "shadow" else 92

    for fighter in opponents_of(attacker):
        if in_shadow_pocket(fighter):
            continue

        distance = fighter.pos.distance_to(attacker.pos)

        if distance < short_range:
            direction_to_enemy = (fighter.pos - attacker.pos).normalize()

            if direction.normalize().dot(direction_to_enemy) > 0.1:
                targets.append(fighter)

    if not targets:
        if monster is not None and monster["owner"] is not attacker:
            monster_distance = monster["pos"].distance_to(attacker.pos)

            if monster_distance < short_range:
                direction_to_monster = (monster["pos"] - attacker.pos).normalize()

                if direction.normalize().dot(direction_to_monster) > 0.1:
                    melee_damage = 20 * owner_damage_multiplier(attacker)
                    monster["hp"] -= melee_damage
                    spawn_damage_number(monster["pos"], melee_damage, (255, 180, 150))
                    add_effect(monster["pos"], (200, 60, 40), 40, 0.2)
                    attacker.ult = min(100, attacker.ult + 20)

                    if monster["hp"] <= 0:
                        monster = None

        return

    target = min(
        targets,
        key=lambda fighter: fighter.pos.distance_to(attacker.pos),
    )

    dmg_mult = owner_damage_multiplier(attacker)
    hp_before_hit = target.hp

    if attacker.element == "fire":
        target.damage(18 * dmg_mult)
        target.burn(3)

    elif attacker.element == "ice":
        target.damage(15 * dmg_mult)
        target.slow(2.5)

    elif attacker.element == "nature":
        target.damage(16 * dmg_mult)
        target.root(0.6)

    elif attacker.element == "earth":
        target.damage(23 * dmg_mult)
        target.root(0.35)

    elif attacker.element == "shadow":
        blink_direction = target.pos - attacker.pos

        if blink_direction.length() > 0:
            attacker.pos = target.pos - blink_direction.normalize() * 40
            attacker.keep_in_arena(ARENA)

        target.damage(21 * dmg_mult)
        target.slow(1.0)

    elif attacker.element == "lightning":
        target.damage(17 * dmg_mult)
        target.magnetize(1.5)
        try_chain_lightning(attacker, target, 17 * dmg_mult)

    elif attacker.element == "metal":
        target.damage(19 * dmg_mult)
        target.slow(0.3)
        trails.append(Trail(target.pos, "metal", team=attacker.team))

    elif attacker.element == "rage":
        target.damage(24 * dmg_mult)
        target.slow(0.3)

    elif attacker.element == "animalia":
        target.damage(20 * dmg_mult)
        target.fear(2.5)
        try_companion_strike(target, 20 * dmg_mult)

    elif attacker.element == "water":
        target.damage(21 * dmg_mult)
        target.soak(1.5)

    elif attacker.element == "music":
        target.damage(19 * dmg_mult)
        target.slow(1.4)

    elif attacker.element == "wind":
        target.damage(17 * dmg_mult)
        target.slow(0.5)

        gust_direction = target.pos - attacker.pos

        if gust_direction.length() > 0:
            target.pos += gust_direction.normalize() * 70
            target.keep_in_arena(ARENA)

    elif attacker.element == "average":
        # Just a punch. An ordinary, unremarkable punch.
        target.damage(11 * dmg_mult)

    elif attacker.element == "god":
        # 1000 Punch Combo - reduced to "a lot" for balance reasons,
        # with real force behind it.
        target.damage(30 * dmg_mult)

        knockback_direction = target.pos - attacker.pos

        if knockback_direction.length() > 0:
            target.pos += knockback_direction.normalize() * 90
            target.keep_in_arena(ARENA)

    if target.element == "water" and random.random() < UNDERTOW_CHANCE:
        # Undertow: Water's passive - being struck up close has a chance
        # to slow the attacker right back.
        attacker.slow(1.0)

    attacker.ult = min(100, attacker.ult + 20)

    add_effect(
        target.pos,
        ELEMENTS[attacker.element]["light_color"],
        45,
        0.2,
    )

    actual_dealt = max(0, hp_before_hit - target.hp)

    if actual_dealt > 0:
        spawn_damage_number(target.pos, actual_dealt)
        attacker.register_hit(actual_dealt)
        play_sound(hit_sound)

        if not target.alive:
            attacker.register_kill()
            spawn_kill_feed(f"{attacker.name} eliminated {target.name}")


def opponents_of(fighter):
    if fighter.team is not None:
        return [
            other for other in living_fighters()
            if other is not fighter and other.team != fighter.team
        ]

    return [other for other in living_fighters() if other is not fighter]


def allies_of(fighter):
    """Only meaningful in team modes (Domination) - empty everywhere else."""
    if fighter.team is None:
        return []

    return [
        other for other in living_fighters()
        if other is not fighter and other.team == fighter.team
    ]


ULTIMATE_LOCK_DURATION = {
    "fire": 1.5,
    "ice": 6,
    "nature": 3.5,
    "earth": 3.5,
    "shadow": 5,
    "lightning": 5,
    "metal": 4,
    "rage": 6,
    "animalia": 30,
    "water": 3.2,
}

ultimate_lock_timer = 0
ultimate_lock_owner = None


def trigger_ultimate(fighter):
    global blizzard, earthquake, vine_leech, eternal_night, thunderstorm, iron_maiden
    global bloodlust, monster, tsunami, fire_zone, symphony, cyclone
    global ultimate_lock_timer, ultimate_lock_owner

    fighter.ult = 0
    fighter.spend_stamina(STAMINA_COST_ULTIMATE)

    play_sound(ultimate_sound)
    trigger_screen_shake(0.35, 10)

    ultimate_lock_timer = ULTIMATE_LOCK_DURATION.get(fighter.element, 4)
    ultimate_lock_owner = fighter

    if fighter.element == "fire":
        add_effect(fighter.pos, (255, 190, 50), 280, 0.6)

        for other in opponents_of(fighter):
            if other.pos.distance_to(fighter.pos) < 280:
                distance = other.pos.distance_to(fighter.pos)
                other.damage(max(20, 60 - distance / 8))
                other.burn(4)

        # Supernova leaves the ground burning for a while afterward -
        # reuses the lava terrain zone's bubble/ember decoration so it
        # looks the part without new art.
        fire_zone = {
            "owner": fighter,
            "pos": fighter.pos.copy(),
            "life": 6,
            "max_life": 6,
            "radius": 190,
            "decor": _generate_zone_decor({"type": "lava", "radius": 190}),
        }

    elif fighter.element == "ice":
        blizzard = {
            "owner": fighter,
            "life": 6,
            "radius": 155,
            "exposure": {},
            "decor": _generate_zone_decor({"type": "ice", "radius": 155}),
        }

        # Buff: an instant ring of icicles bursts outward on cast,
        # stunning anyone it hits for 3 seconds on top of the usual
        # lingering blizzard zone.
        spawn_icicle_ring(fighter)
        add_effect(fighter.pos, (200, 240, 255), 220, 0.3)

    elif fighter.element == "nature":
        vine_leech = {
            "owner": fighter,
            "life": 3.5,
            "range": 370,
        }

    elif fighter.element == "earth":
        earthquake = {
            "owner": fighter,
            "life": 3.5,
            "radius": 360,
            "pulse_timer": 0,
        }

    elif fighter.element == "shadow":
        # Eternal Night: the arena darkens and the caster becomes very
        # hard for others to see - see nearest_target()/update_bot_ai()
        # for the detection-range and aim-inaccuracy side of this.
        eternal_night = {"owner": fighter, "life": 5}
        fighter.damage_reduction = 0.25

        for other in opponents_of(fighter):
            other.slow(1.5)

    elif fighter.element == "lightning":
        # Thunderstorm: bolts "aimbot" onto wherever each opponent
        # currently stands, at a steady interval, for the duration -
        # but nerfed to only reach opponents within range of the caster
        # (shown as a yellow ring), rather than the whole arena.
        thunderstorm = {
            "owner": fighter,
            "life": 5,
            "strike_timer": 0,
            "radius": THUNDERSTORM_RADIUS,
        }

    elif fighter.element == "metal":
        # Iron Maiden Cage: traps the nearest living opponent and slowly
        # crushes them - the cage tightens and the damage ramps up as
        # it does, see update_specials() for the tick logic.
        candidates = [
            other for other in opponents_of(fighter)
            if not in_shadow_pocket(other)
        ]

        if candidates:
            target = min(
                candidates,
                key=lambda other: other.pos.distance_to(fighter.pos),
            )

            iron_maiden = {
                "owner": fighter,
                "target": target,
                "life": 4,
                "max_life": 4,
                "start_radius": 150,
                "min_radius": 22,
                "radius": 150,
            }

    elif fighter.element == "rage":
        # Bloodlust: sacrifice 75% of current health for a huge
        # temporary attack boost. Never drops below 1 hp outright.
        fighter.hp = max(1, fighter.hp * 0.25)
        bloodlust = {"owner": fighter, "life": 6}
        add_effect(fighter.pos, (255, 60, 60), 90, 0.4)

    elif fighter.element == "animalia":
        # Ancient Monster: summons a T-Rex that hunts down opponents on
        # its own - see update_monster() for its AI. It has a real
        # health bar now: it takes damage from attacks and also slowly
        # loses health on its own until it dies of old age.
        spawn_offset = Vector2(70, 0)

        if fighter is player and get_world_mouse() != player.pos:
            spawn_direction = get_world_mouse() - player.pos

            if spawn_direction.length() > 0:
                spawn_offset = spawn_direction.normalize() * 70

        monster = {
            "owner": fighter,
            "pos": fighter.pos + spawn_offset,
            "hp": MONSTER_MAX_HP,
            "max_hp": MONSTER_MAX_HP,
            "attack_cooldown": 0,
        }

    elif fighter.element == "water":
        # Twin Tsunami: two walls of water sweep in from the left and
        # right edges of the arena toward the center, damaging and
        # shoving aside anyone caught in them - see update_specials().
        tsunami = {
            "owner": fighter,
            "life": 3.2,
            "max_life": 3.2,
            "left_x": float(ARENA.left),
            "right_x": float(ARENA.right),
            "hit_cooldowns": {},
        }

    elif fighter.element == "wind":
        # Cyclone: a vortex centered on the caster that reels every
        # opponent in range steadily toward its eye, ticking damage the
        # whole way in - see update_specials().
        cyclone = {
            "owner": fighter,
            "life": 4,
            "radius": 340,
        }
        add_effect(fighter.pos, (200, 235, 225), 200, 0.4)


MUSIC_ULT_DRAIN_PER_SEC = 25  # a full 100 stock channels for 4 seconds
MUSIC_ULT_CONE_HALF_ANGLE = 32
MUSIC_ULT_RANGE = 320
MUSIC_ULT_TICK_INTERVAL = 0.2


def update_music_channel(fighter, aim_direction, dt):
    """Symphony of Chaos works differently from every other ultimate -
    instead of firing all at once at 100%, it channels for as long as
    you hold it and there's stock left, draining the ult bar over time
    rather than spending it all up front. A cone-shaped shriek extends
    from the caster toward aim_direction, ticking damage and a short
    stun on anyone caught in it."""
    global symphony, ultimate_lock_timer, ultimate_lock_owner

    if fighter.ult <= 0 or aim_direction.length() == 0 or in_shadow_pocket(fighter):
        stop_music_channel(fighter)
        return

    if symphony is not None and symphony["owner"] is not fighter:
        # Only one Symphony can be active in the arena at a time.
        return

    fighter.ult = max(0, fighter.ult - MUSIC_ULT_DRAIN_PER_SEC * dt)

    if symphony is None:
        symphony = {
            "owner": fighter,
            "direction": aim_direction.normalize(),
            "tick_timer": 0,
        }
        add_effect(fighter.pos, (220, 100, 210), 70, 0.2)
    else:
        symphony["direction"] = aim_direction.normalize()

    symphony["tick_timer"] -= dt

    if symphony["tick_timer"] <= 0:
        symphony["tick_timer"] = MUSIC_ULT_TICK_INTERVAL

        for target in opponents_of(fighter):
            if in_shadow_pocket(target):
                continue

            to_target = target.pos - fighter.pos
            target_distance = to_target.length()

            if target_distance == 0 or target_distance > MUSIC_ULT_RANGE:
                continue

            facing_dot = to_target.normalize().dot(symphony["direction"])
            angle = math.degrees(math.acos(max(-1, min(1, facing_dot))))

            if angle <= MUSIC_ULT_CONE_HALF_ANGLE:
                target.damage(4)
                target.stun(0.3)
                fighter.hp = min(fighter.max_hp, fighter.hp + 1)
                add_effect(target.pos, (220, 100, 210), 30, 0.15)

    ultimate_lock_owner = fighter
    ultimate_lock_timer = 0.3

    if fighter.ult <= 0:
        stop_music_channel(fighter)


def stop_music_channel(fighter):
    global symphony

    if symphony is not None and symphony["owner"] is fighter:
        symphony = None


def update_dummy_wander(bot, dt):
    """Used by the training dummy in 'Move Around' mode - wanders the
    arena aimlessly, never attacks."""
    bot.wander_timer -= dt

    if bot.wander_timer <= 0:
        bot.wander_timer = random.uniform(0.8, 1.8)
        bot.wander_direction = Vector2(1, 0).rotate(random.uniform(0, 360))

    bot.move(bot.wander_direction, dt, ARENA, 0.6 * terrain_speed_multiplier(bot))


def update_bot_ai(bot, dt):
    target = nearest_target(bot)

    if target is None:
        # Nothing visible (e.g. the player vanished into Eternal Night) -
        # wander around aimlessly instead of freezing in place.
        bot.wander_timer -= dt

        if bot.wander_timer <= 0:
            bot.wander_timer = random.uniform(0.6, 1.4)
            bot.wander_direction = Vector2(1, 0).rotate(random.uniform(0, 360))

        bot.move(bot.wander_direction, dt, ARENA, 0.5 * terrain_speed_multiplier(bot))
        return

    direction = target.pos - bot.pos
    distance = direction.length()
    multiplier = terrain_speed_multiplier(bot)
    stealthed_target = eternal_night is not None and target is eternal_night["owner"]

    if direction.length() > 0:
        bot.facing_direction = direction

    # 0.0 at difficulty 1 (Rookie) up to 1.0 at difficulty 9 (Nightmare).
    # This single shared setting is what all game modes read - there's no
    # separate per-mode difficulty concept.
    skill = (npc_difficulty - 1) / 8

    approach_range = 135 - skill * 25
    retreat_range = 55 - skill * 20

    if distance > approach_range:
        bot.move(direction, dt, ARENA, multiplier)

    elif distance < retreat_range:
        bot.move(-direction, dt, ARENA, multiplier)

    melee_range = 150 if bot.element == "shadow" else 92

    if (
        distance < melee_range
        and bot.cooldowns["short"] <= 0
        and bot.has_stamina(STAMINA_COST_SHORT)
        and random.random() < 0.35 + skill * 0.5
    ):
        # In melee range, higher-difficulty bots throw a punch instead of
        # only ever kiting and shooting - same perform_short_attack() the
        # player uses, so it's the exact same damage/effects/weapon swing.
        perform_short_attack(bot, direction)
        bot.cooldowns["short"] = 0.5 - skill * 0.15

    attack_interval = 1.6 - skill * 1.05

    if bot.cooldowns["long"] <= 0 and distance > 0:
        aim = direction
        aim_jitter = 26 - skill * 26

        if aim_jitter > 0:
            aim = aim.rotate(random.uniform(-aim_jitter, aim_jitter))

        if stealthed_target:
            aim = aim.rotate(random.uniform(-45, 45))

        shoot_projectile(bot, aim)
        bot.cooldowns["long"] = attack_interval

    if (
        bot.cooldowns["special"] <= 0
        and bot.has_stamina(STAMINA_COST_SPECIAL)
        and random.random() < 0.015 + skill * 0.02
    ):
        # Bots don't replicate every element's exact special mechanic
        # (glide/burrow/hover toggles are single-owner state machines
        # built around the player) - instead they get a generic dash,
        # closing distance on a target that's too far, or repositioning
        # away from one that's dangerously close.
        dash_direction = direction if distance > approach_range else -direction

        if dash_direction.length() > 0:
            bot.last_move_direction = dash_direction.normalize()
            bot.spend_stamina(STAMINA_COST_SPECIAL)
            bot.dash(150, ARENA)
            add_effect(bot.pos, ELEMENTS[bot.element]["light_color"], 40, 0.25)
            bot.cooldowns["special"] = 2.2 - skill * 0.8

    if bot.element == "music":
        # Symphony of Chaos channels rather than firing all at once, so
        # Music bots use it whenever they have any stock and a target in
        # range, draining as they go, instead of waiting for 100%. Once
        # started, keep going (don't re-roll every single frame) until
        # it naturally runs out or the target gets away.
        already_channeling = symphony is not None and symphony["owner"] is bot
        should_channel = bot.ult > 0 and distance < 340 and (
            already_channeling or random.random() < 0.02 + skill * 0.03
        )

        if should_channel:
            update_music_channel(bot, direction, dt)
        else:
            stop_music_channel(bot)
    elif (
        bot.ult >= 100
        and bot.cooldowns["ultimate"] <= 0
        and ultimate_lock_timer <= 0
        and bot.has_stamina(STAMINA_COST_ULTIMATE)
    ):
        # Weaker bots don't necessarily fire their ultimate the instant
        # it's ready - they get a fresh roll on this about once a second
        # (see the cooldown reset below either way).
        if random.random() < 0.5 + skill * 0.5:
            trigger_ultimate(bot)

        bot.cooldowns["ultimate"] = 1.0


def update_projectiles(dt):
    global monster

    for projectile in projectiles[:]:
        if projectile["element"] == "lightning":
            homing_target = None
            best_distance = LIGHTNING_HOMING_RADIUS

            for candidate in opponents_of(projectile["owner"]):
                distance = projectile["pos"].distance_to(candidate.pos)

                if distance < best_distance:
                    best_distance = distance
                    homing_target = candidate

            if homing_target is not None:
                desired_direction = homing_target.pos - projectile["pos"]

                if desired_direction.length() > 0:
                    speed = projectile["velocity"].length()
                    desired_velocity = desired_direction.normalize() * speed
                    turn_rate = 6 if homing_target.magnet_timer > 0 else 3
                    projectile["velocity"] = projectile["velocity"].lerp(
                        desired_velocity, min(1, turn_rate * dt)
                    )

        water_zone = terrain_zone_at(projectile["pos"])
        speed_scale = 0.6 if water_zone and water_zone["type"] == "water" else 1

        projectile["pos"] += projectile["velocity"] * speed_scale * dt
        projectile["life"] -= dt

        for target in opponents_of(projectile["owner"]):
            if projectile["pos"].distance_to(target.pos) < projectile["radius"] + 18:
                if target.element == "metal" and random.random() < REFLECT_CHANCE:
                    projectile["velocity"] = -projectile["velocity"]
                    projectile["owner"] = target
                    add_effect(target.pos, (225, 228, 235), 40, 0.2)
                    break

                if in_shadow_pocket(target):
                    # Hidden shadow: projectiles pass through harmlessly.
                    projectiles.remove(projectile)
                    break

                hp_before_hit = target.hp
                target.damage(projectile["damage"])
                apply_element_effect(target, projectile["element"])

                if projectile["element"] == "shadow":
                    pull_direction = projectile["owner"].pos - target.pos

                    if pull_direction.length() > 0:
                        target.pos += pull_direction.normalize() * 60
                        target.keep_in_arena(ARENA)

                if projectile["element"] == "lightning":
                    try_chain_lightning(
                        projectile["owner"], target, projectile["damage"]
                    )

                if projectile["element"] == "animalia":
                    try_companion_strike(target, projectile["damage"])

                if projectile.get("stun_ring"):
                    target.stun(ICICLE_RING_STUN)

                projectile["owner"].ult = min(100, projectile["owner"].ult + 16)

                actual_dealt = max(0, hp_before_hit - target.hp)

                if actual_dealt > 0:
                    spawn_damage_number(target.pos, actual_dealt)
                    projectile["owner"].register_hit(actual_dealt)

                    if projectile["owner"] is player:
                        play_sound(hit_sound)

                    if not target.alive:
                        projectile["owner"].register_kill()
                        spawn_kill_feed(f"{projectile['owner'].name} eliminated {target.name}")

                projectiles.remove(projectile)
                break

        if projectile in projectiles and monster is not None and projectile["owner"] is not monster["owner"]:
            if projectile["pos"].distance_to(monster["pos"]) < projectile["radius"] + 34:
                monster["hp"] -= projectile["damage"]
                spawn_damage_number(monster["pos"], projectile["damage"], (255, 180, 150))
                add_effect(monster["pos"], (200, 60, 40), 40, 0.2)
                projectiles.remove(projectile)

                if monster["hp"] <= 0:
                    monster = None

        if projectile in projectiles:
            if (
                projectile["life"] <= 0
                or not ARENA.collidepoint(projectile["pos"])
            ):
                projectiles.remove(projectile)


def update_trails(dt):
    for trail in trails[:]:
        trail.update(dt)

        if trail.element == "fire":
            for target in bots:
                if target.team is not None and target.team == trail.team:
                    continue

                if target.alive and trail.contains(target.pos):
                    if trail.damage_cooldown <= 0:
                        target.damage(5)
                        target.burn(1)
                        trail.damage_cooldown = 0.6

        elif trail.element == "metal":
            for target in bots:
                if target.team is not None and target.team == trail.team:
                    continue

                if target.alive and trail.contains(target.pos):
                    if trail.damage_cooldown <= 0:
                        target.damage(4)
                        trail.damage_cooldown = 0.5

        elif trail.element == "electric":
            for target in bots:
                if target.team is not None and target.team == trail.team:
                    continue

                if target.alive and trail.contains(target.pos):
                    if trail.damage_cooldown <= 0:
                        target.stun(1.0)
                        trail.damage_cooldown = 1.0

        if not trail.alive:
            trails.remove(trail)


def player_on_ice_trail():
    return (
        player.element == "ice"
        and any(
            trail.element == "ice" and trail.contains(player.pos)
            for trail in trails
        )
    )


def update_specials(dt):
    global blizzard, earthquake, vine_leech, vine_whip, burrow, eternal_night, thunderstorm
    global hover, iron_maiden, bloodlust, adrenaline, bear_ride, tsunami, fire_zone
    global symphony, cyclone

    if vine_whip is not None:
        vine_whip["life"] -= dt
        direction = vine_whip["target"] - player.pos

        if direction.length() > 12:
            player.move(direction, dt, ARENA, 3.2)

        if vine_whip["life"] <= 0:
            vine_whip = None

    if burrow is not None:
        burrow["life"] -= dt
        burrow["trail_timer"] -= dt

        player.move(player.last_move_direction, dt, ARENA, 2.5)

        if burrow["trail_timer"] <= 0:
            burrow["trail_timer"] = 0.06
            add_effect(player.pos, (135, 95, 55), 30, 0.3)

        if burrow["life"] <= 0:
            burrow = None

    if blizzard is not None:
        blizzard["life"] -= dt
        owner = blizzard["owner"]

        for target in opponents_of(owner):
            if in_shadow_pocket(target):
                continue

            key = id(target)

            if target.pos.distance_to(owner.pos) < blizzard["radius"]:
                target.slow(0.4)
                blizzard["exposure"][key] = (
                    blizzard["exposure"].get(key, 0) + dt
                )

                if blizzard["exposure"][key] >= 2.2:
                    target.damage(12)
                    target.slow(1.7)
                    blizzard["exposure"][key] = 1.1

        if blizzard["life"] <= 0:
            blizzard = None

    if vine_leech is not None:
        vine_leech["life"] -= dt
        owner = vine_leech["owner"]

        for target in opponents_of(owner):
            if in_shadow_pocket(target):
                continue

            if target.pos.distance_to(owner.pos) < vine_leech["range"]:
                target.damage(10 * dt)
                target.root(0.25)
                owner.hp = min(owner.max_hp, owner.hp + 10 * dt)

        if vine_leech["life"] <= 0:
            vine_leech = None

    if earthquake is not None:
        earthquake["life"] -= dt
        earthquake["pulse_timer"] -= dt
        owner = earthquake["owner"]

        if earthquake["pulse_timer"] <= 0:
            earthquake["pulse_timer"] = 0.65

            for target in opponents_of(owner):
                if in_shadow_pocket(target):
                    continue

                if target.pos.distance_to(owner.pos) < earthquake["radius"]:
                    target.damage(11)
                    target.root(0.45)

                    direction = target.pos - owner.pos

                    if direction.length() > 0:
                        target.pos += direction.normalize() * 55
                        target.keep_in_arena(ARENA)

                    add_effect(target.pos, (195, 145, 85), 70, 0.25)

        if earthquake["life"] <= 0:
            earthquake = None

    if eternal_night is not None:
        eternal_night["life"] -= dt

        if eternal_night["life"] <= 0:
            owner = eternal_night["owner"]
            eternal_night = None

            if owner.element == "shadow":
                owner.damage_reduction = 0

    if thunderstorm is not None:
        thunderstorm["life"] -= dt
        thunderstorm["strike_timer"] -= dt
        owner = thunderstorm["owner"]

        if thunderstorm["strike_timer"] <= 0:
            thunderstorm["strike_timer"] = 0.7

            for target in opponents_of(owner):
                if in_shadow_pocket(target):
                    continue

                if target.pos.distance_to(owner.pos) > thunderstorm["radius"]:
                    continue

                target.damage(16)
                target.magnetize(1.5)
                add_effect(target.pos, (255, 255, 140), 45, 0.25)
                lightning_arcs.append({
                    "a": Vector2(target.pos.x, target.pos.y - 380),
                    "b": target.pos.copy(),
                    "life": 0.15,
                    "max_life": 0.15,
                })

        if thunderstorm["life"] <= 0:
            thunderstorm = None

    for arc in lightning_arcs[:]:
        arc["life"] -= dt

        if arc["life"] <= 0:
            lightning_arcs.remove(arc)

    if hover is not None:
        hover["life"] -= dt
        hover["trail_timer"] -= dt

        if hover["trail_timer"] <= 0:
            hover["trail_timer"] = 0.08
            add_effect(player.pos, (200, 205, 215), 22, 0.2)

        if hover["life"] <= 0:
            hover = None

    if iron_maiden is not None:
        iron_maiden["life"] -= dt
        target = iron_maiden["target"]

        if target.alive and not in_shadow_pocket(target):
            target.root(0.3)

            progress = 1 - max(0, iron_maiden["life"]) / iron_maiden["max_life"]
            span = iron_maiden["start_radius"] - iron_maiden["min_radius"]
            iron_maiden["radius"] = iron_maiden["start_radius"] - progress * span

            tightness = progress
            target.damage((6 + tightness * 26) * dt)

        if iron_maiden["life"] <= 0 or not target.alive:
            iron_maiden = None

    if bloodlust is not None:
        bloodlust["life"] -= dt

        if bloodlust["life"] <= 0:
            bloodlust = None

    if adrenaline is not None:
        adrenaline["life"] -= dt

        if adrenaline["life"] <= 0:
            adrenaline = None

    if bear_ride is not None:
        if bear_ride["life"] is not None:
            bear_ride["life"] -= dt
        bear_ride["slash_cooldown"] = max(0, bear_ride["slash_cooldown"] - dt)
        bear_ride["trail_timer"] -= dt

        if bear_ride["trail_timer"] <= 0:
            bear_ride["trail_timer"] = 0.12
            add_effect(player.pos, (140, 100, 60), 28, 0.2)

        if bear_ride["slash_cooldown"] <= 0:
            for target in opponents_of(player):
                if (
                    not in_shadow_pocket(target)
                    and target.pos.distance_to(player.pos) < BEAR_SLASH_RANGE
                ):
                    target.damage(10 * owner_damage_multiplier(player))
                    add_effect(target.pos, (200, 130, 70), 38, 0.25)
                    bear_ride["slash_cooldown"] = 0.35

        if bear_ride["life"] is not None and bear_ride["life"] <= 0:
            bear_ride = None

    if tsunami is not None:
        tsunami["life"] -= dt
        progress = 1 - max(0, tsunami["life"]) / tsunami["max_life"]
        half_width = ARENA.width / 2

        tsunami["left_x"] = ARENA.left + progress * half_width
        tsunami["right_x"] = ARENA.right - progress * half_width

        for cooldown_key in list(tsunami["hit_cooldowns"]):
            tsunami["hit_cooldowns"][cooldown_key] = max(
                0, tsunami["hit_cooldowns"][cooldown_key] - dt
            )

        for target in opponents_of(tsunami["owner"]):
            if in_shadow_pocket(target):
                continue

            key = id(target)
            already_cooling = tsunami["hit_cooldowns"].get(key, 0) > 0

            hit_left = abs(target.pos.x - tsunami["left_x"]) < 45
            hit_right = abs(target.pos.x - tsunami["right_x"]) < 45

            if (hit_left or hit_right) and not already_cooling:
                target.damage(28)
                tsunami["hit_cooldowns"][key] = tsunami["max_life"]

                push_direction = 1 if hit_left else -1
                target.pos.x += push_direction * 150
                target.keep_in_arena(ARENA)

                add_effect(target.pos, (110, 190, 235), 65, 0.3)

        if tsunami["life"] <= 0:
            tsunami = None

    if fire_zone is not None:
        fire_zone["life"] -= dt

        for fighter in opponents_of(fire_zone["owner"]):
            if in_shadow_pocket(fighter):
                continue

            if fighter.pos.distance_to(fire_zone["pos"]) <= fire_zone["radius"]:
                fighter.damage(9 * dt)
                fighter.burn(0.6)

        if fire_zone["life"] <= 0:
            fire_zone = None

    if symphony is not None and not symphony["owner"].alive:
        symphony = None

    if cyclone is not None:
        cyclone["life"] -= dt
        owner = cyclone["owner"]

        for target in opponents_of(owner):
            if in_shadow_pocket(target):
                continue

            pull_direction = owner.pos - target.pos
            distance = pull_direction.length()

            if 0 < distance < cyclone["radius"]:
                target.damage(7 * dt)

                if distance > 40:
                    target.pos += pull_direction.normalize() * 90 * dt
                    target.keep_in_arena(ARENA)

        if cyclone["life"] <= 0:
            cyclone = None


def update_monster(dt):
    global monster

    if monster is None:
        return

    monster["hp"] -= MONSTER_NATURAL_DECAY_PER_SEC * dt
    monster["attack_cooldown"] = max(0, monster["attack_cooldown"] - dt)

    target = None
    best_distance = None

    for candidate in opponents_of(monster["owner"]):
        if in_shadow_pocket(candidate):
            continue

        distance = candidate.pos.distance_to(monster["pos"])

        if best_distance is None or distance < best_distance:
            best_distance = distance
            target = candidate

    if target is not None:
        direction = target.pos - monster["pos"]

        if direction.length() > MONSTER_ATTACK_RANGE:
            if direction.length() > 0:
                monster["pos"] += direction.normalize() * MONSTER_MOVE_SPEED * dt
        elif monster["attack_cooldown"] <= 0:
            target.damage(16)
            target.root(0.2)
            monster["attack_cooldown"] = 0.5
            add_effect(target.pos, (200, 60, 40), 50, 0.2)

    monster["pos"].x = max(ARENA.left + 40, min(ARENA.right - 40, monster["pos"].x))
    monster["pos"].y = max(ARENA.top + 40, min(ARENA.bottom - 40, monster["pos"].y))

    if monster["hp"] <= 0:
        monster = None


def update_storm(dt):
    global storm_wait, storm_radius

    if storm_wait > 0:
        storm_wait -= dt
        return

    storm_radius = max(300, storm_radius - 11 * dt)

    for fighter in living_fighters():
        if fighter.pos.distance_to(ZONE_CENTER) > storm_radius:
            fighter.damage(8 * dt)


def update_effects(dt):
    for effect in effects[:]:
        effect["life"] -= dt

        if effect["life"] <= 0:
            effects.remove(effect)


def update_damage_numbers(dt):
    for number in damage_numbers[:]:
        number["life"] -= dt
        number["pos"].y -= 28 * dt

        if number["life"] <= 0:
            damage_numbers.remove(number)


def update_kill_feed(dt):
    for entry in kill_feed[:]:
        entry["life"] -= dt

        if entry["life"] <= 0:
            kill_feed.remove(entry)


def update_screen_shake(dt):
    global screen_shake_timer

    if screen_shake_timer > 0:
        screen_shake_timer = max(0, screen_shake_timer - dt)


def draw_menu():
    title = big_font.render("ELEMENTAL ARENA", True, (255, 190, 60))
    screen.blit(title, title.get_rect(center=(WIDTH // 2, 120)))

    mouse = pygame.mouse.get_pos()

    for key, button in menu_buttons.items():
        color = (220, 110, 45) if button.collidepoint(mouse) else (90, 80, 85)
        pygame.draw.rect(screen, color, button, border_radius=12)

        text = font.render(MENU_BUTTON_LABELS[key], True, "white")
        screen.blit(text, text.get_rect(center=button.center))

    account_color = (220, 110, 45) if ACCOUNT_CORNER_BUTTON.collidepoint(mouse) else (70, 75, 90)
    pygame.draw.rect(screen, account_color, ACCOUNT_CORNER_BUTTON, border_radius=10)

    account_label = account_username if account_username is not None else "ACCOUNT"
    account_text = font.render(account_label, True, "white")
    screen.blit(account_text, account_text.get_rect(center=ACCOUNT_CORNER_BUTTON.center))


STORY_HUB_CONTINUE_BUTTON = pygame.Rect(400, 590, 300, 55)


STORY_HUB_LIST_TOP = 160
STORY_HUB_ROW_HEIGHT = 34


def story_hub_row_rect(index):
    row_y = STORY_HUB_LIST_TOP + index * STORY_HUB_ROW_HEIGHT
    return pygame.Rect(WIDTH // 2 - 270, row_y - 2, 540, STORY_HUB_ROW_HEIGHT - 4)


def draw_story_hub():
    title = big_font.render("STORY MODE", True, (255, 190, 60))
    screen.blit(title, title.get_rect(center=(WIDTH // 2, 90)))

    subtitle = small_font.render(
        f"Fire's son, {story.STORY_SON_NAME}, has been taken. Fight your way to Water.",
        True, (190, 190, 205),
    )
    screen.blit(subtitle, subtitle.get_rect(center=(WIDTH // 2, 128)))

    mouse = pygame.mouse.get_pos()

    for index, element in enumerate(story.STORY_MISSIONS):
        row_y = STORY_HUB_LIST_TOP + index * STORY_HUB_ROW_HEIGHT
        row_rect = story_hub_row_rect(index)
        unlocked = index <= story_progress

        if index < story_progress:
            status = "DEFEATED - click to replay"
            color = (110, 200, 130)
        elif index == story_progress:
            status = "NEXT"
            color = (255, 210, 120)
        else:
            status = "LOCKED"
            color = (110, 110, 120)

        if unlocked and row_rect.collidepoint(mouse):
            pygame.draw.rect(screen, (50, 48, 55), row_rect, border_radius=6)

        info = ELEMENTS[element]
        row_text = f"{index + 1}. {info['name']}" + (" (FINAL BOSS)" if element == "water" else "")
        row_surface = font.render(row_text, True, color)
        screen.blit(row_surface, (WIDTH // 2 - 260, row_y))

        status_surface = small_font.render(status, True, color)
        screen.blit(status_surface, (WIDTH // 2 + 90, row_y + 2))

    story_complete = story_progress >= len(story.STORY_MISSIONS)

    if story_complete:
        button_label = "REPLAY FROM START"
    elif story_progress == 0:
        button_label = "BEGIN STORY"
    else:
        button_label = "CONTINUE STORY"

    button_color = (220, 110, 45) if STORY_HUB_CONTINUE_BUTTON.collidepoint(mouse) else (90, 80, 85)
    pygame.draw.rect(screen, button_color, STORY_HUB_CONTINUE_BUTTON, border_radius=12)
    button_text = font.render(button_label, True, "white")
    screen.blit(button_text, button_text.get_rect(center=STORY_HUB_CONTINUE_BUTTON.center))

    pygame.draw.rect(screen, (75, 75, 90), back_button, border_radius=8)
    draw_text("BACK", 63, 36)


# --- Story cutscene rendering -------------------------------------------
#
# This is the one place in the game that isn't drawn with the same flat
# combat shapes - portraits get simple layered, animated features (a
# blinking, talking face instead of a plain circle) and each scene gets
# its own animated backdrop, so cutscenes read as a clear step up in
# presentation from the arena.

STORY_SCENE_COLORS = {
    "home": (40, 28, 22),
    "capture": (18, 16, 28),
    "coast": (14, 26, 40),
    "ice_ridge": (18, 30, 42),
    "greenhouse": (16, 34, 22),
    "mine": (24, 20, 16),
    "shadow_district": (12, 12, 18),
    "storm_towers": (22, 24, 34),
    "factory": (26, 18, 14),
    "fairground": (30, 16, 12),
    "treeline": (14, 22, 16),
    "street": (16, 18, 26),
    "airfield": (24, 28, 30),
    None: (22, 22, 30),
}


def draw_story_portrait(center, radius, element, talking, seed):
    t = pygame.time.get_ticks() / 1000

    if element is None:
        base_color = (200, 195, 190)
        light_color = (235, 232, 228)
    elif element == story.STORY_SON_NAME.lower():
        base_color = (255, 150, 60)
        light_color = (255, 195, 130)
    else:
        info = ELEMENTS[element]
        base_color = info["color"]
        light_color = info["light_color"]

    bob = math.sin(t * 1.6 + seed) * 4
    portrait_center = (center[0], center[1] + bob)

    # Body/head silhouette.
    pygame.draw.circle(screen, base_color, portrait_center, radius)
    pygame.draw.circle(screen, light_color, portrait_center, radius, 3)

    # Blinking eyes - closed for a few frames every couple of seconds.
    blink_phase = (t * 0.6 + seed) % 3.0
    eyes_closed = blink_phase > 2.85
    eye_offset_x = radius * 0.34
    eye_offset_y = -radius * 0.12
    eye_y = portrait_center[1] + eye_offset_y

    for side in (-1, 1):
        eye_x = portrait_center[0] + side * eye_offset_x

        if eyes_closed:
            pygame.draw.line(screen, (20, 18, 22), (eye_x - 6, eye_y), (eye_x + 6, eye_y), 3)
        else:
            pygame.draw.circle(screen, (20, 18, 22), (eye_x, eye_y), max(3, int(radius * 0.09)))

    # Mouth - flaps open/closed on a fast cycle only while this speaker
    # is the one currently talking.
    mouth_y = portrait_center[1] + radius * 0.32
    mouth_width = radius * 0.5

    if talking:
        mouth_open = (math.sin(t * 14 + seed) + 1) / 2
    else:
        mouth_open = 0.12

    mouth_height = max(2, int(radius * 0.22 * mouth_open))
    mouth_rect = pygame.Rect(0, 0, mouth_width, mouth_height)
    mouth_rect.center = (portrait_center[0], mouth_y)
    pygame.draw.ellipse(screen, (30, 22, 26), mouth_rect)


def draw_story_scene_background(scene):
    color = STORY_SCENE_COLORS.get(scene, STORY_SCENE_COLORS[None])
    screen.fill(color)

    t = pygame.time.get_ticks() / 1000
    rng = random.Random(1234)  # fixed seed so particles don't jitter/re-shuffle every frame

    if scene == "home":
        # Drifting embers.
        for index in range(26):
            base_x = rng.uniform(0, WIDTH)
            base_y = rng.uniform(0, HEIGHT)
            ember_y = (base_y + t * 22) % HEIGHT
            flicker = (math.sin(t * 3 + index) + 1) / 2
            size = 2 + int(flicker * 2)
            glow = (255, int(120 + flicker * 90), 40)
            pygame.draw.circle(screen, glow, (int(base_x), int(ember_y)), size)

    elif scene == "capture":
        # Cold, jagged shadow bars sweeping slowly across the scene.
        for index in range(9):
            bar_x = (index * 140 + t * 30) % (WIDTH + 140) - 70
            pygame.draw.polygon(
                screen, (10, 8, 16),
                [(bar_x, 0), (bar_x + 40, 0), (bar_x + 10, HEIGHT), (bar_x - 30, HEIGHT)],
            )

    elif scene == "coast":
        # Rolling wave lines near the bottom of the screen.
        for row in range(5):
            wave_y = HEIGHT - 40 - row * 26
            points = []

            for x in range(0, WIDTH + 20, 20):
                offset = math.sin(x * 0.02 + t * 1.4 + row) * 6
                points.append((x, wave_y + offset))

            if len(points) > 1:
                pygame.draw.lines(screen, (40 + row * 8, 90 + row * 10, 140 + row * 12), False, points, 2)

    elif scene == "ice_ridge":
        # Falling snow over jagged icy silhouettes along the bottom.
        for index in range(40):
            base_x = rng.uniform(0, WIDTH)
            fall_speed = 18 + (index % 5) * 6
            snow_y = (rng.uniform(0, HEIGHT) + t * fall_speed) % HEIGHT
            drift_x = (base_x + math.sin(t * 0.6 + index) * 12) % WIDTH
            pygame.draw.circle(screen, (220, 240, 255), (int(drift_x), int(snow_y)), 2)

        for peak in range(6):
            peak_x = peak * (WIDTH / 5)
            height = 60 + (peak % 3) * 30
            pygame.draw.polygon(
                screen, (60, 90, 110),
                [(peak_x - 70, HEIGHT), (peak_x, HEIGHT - height), (peak_x + 70, HEIGHT)],
            )

    elif scene == "greenhouse":
        # Creeping vines up both edges, dappled light drifting through glass.
        for side in (-1, 1):
            vine_x = WIDTH / 2 + side * (WIDTH / 2 - 40)
            points = []

            for step in range(12):
                y = step * (HEIGHT / 11)
                sway = math.sin(t * 0.8 + step * 0.5 + side) * 18
                points.append((vine_x + sway, y))

            if len(points) > 1:
                pygame.draw.lines(screen, (60, 130, 60), False, points, 5)

        for index in range(14):
            light_x = rng.uniform(80, WIDTH - 80)
            light_y = rng.uniform(0, HEIGHT)
            flicker = (math.sin(t * 1.2 + index) + 1) / 2
            glow = (int(140 + flicker * 60), int(200 + flicker * 40), 120)
            pygame.draw.circle(screen, glow, (int(light_x), int(light_y)), 3)

    elif scene == "mine":
        # A swinging lantern glow and drifting dust motes in the dark.
        swing = math.sin(t * 1.1) * 60
        lantern_pos = (WIDTH / 2 + swing, 90)
        glow_surface = pygame.Surface((260, 260), pygame.SRCALPHA)
        pygame.draw.circle(glow_surface, (200, 160, 90, 60), (130, 130), 130)
        screen.blit(glow_surface, (lantern_pos[0] - 130, lantern_pos[1] - 130))
        pygame.draw.circle(screen, (255, 220, 150), lantern_pos, 6)

        for index in range(20):
            dust_x = rng.uniform(0, WIDTH)
            dust_y = (rng.uniform(0, HEIGHT) + t * 8) % HEIGHT
            pygame.draw.circle(screen, (140, 120, 100), (int(dust_x), int(dust_y)), 1)

    elif scene == "shadow_district":
        # A dead streetlamp flickering, with the same jagged shadow bars.
        for index in range(9):
            bar_x = (index * 140 + t * 25) % (WIDTH + 140) - 70
            pygame.draw.polygon(
                screen, (8, 6, 12),
                [(bar_x, 0), (bar_x + 40, 0), (bar_x + 10, HEIGHT), (bar_x - 30, HEIGHT)],
            )

        flicker_on = (math.sin(t * 9) + math.sin(t * 3.3)) > 0.6

        if flicker_on:
            glow_surface = pygame.Surface((200, HEIGHT), pygame.SRCALPHA)
            pygame.draw.polygon(glow_surface, (200, 190, 140, 30), [(100, 0), (0, HEIGHT), (200, HEIGHT)])
            screen.blit(glow_surface, (WIDTH / 2 - 100, 0))

    elif scene == "storm_towers":
        # Lightning flashes and a distant zigzag bolt.
        flash = max(0, math.sin(t * 5.3)) ** 6

        if flash > 0.3:
            flash_surface = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            flash_surface.fill((220, 225, 255, int(flash * 90)))
            screen.blit(flash_surface, (0, 0))

        bolt_phase = (t * 1.3) % 4

        if bolt_phase < 0.2:
            bolt_x = WIDTH * 0.3 + math.sin(t * 50) * 20
            points = [(bolt_x, 0)]
            for step in range(6):
                points.append((bolt_x + rng.uniform(-30, 30), (step + 1) * (HEIGHT / 6)))
            pygame.draw.lines(screen, (255, 250, 200), False, points, 2)

    elif scene == "factory":
        # Falling sparks over dead machinery silhouettes.
        for index in range(18):
            spark_x = rng.uniform(0, WIDTH)
            spark_y = (rng.uniform(0, HEIGHT) + t * 40) % HEIGHT
            flicker = (math.sin(t * 5 + index) + 1) / 2
            glow = (255, int(120 + flicker * 100), 40)
            pygame.draw.circle(screen, glow, (int(spark_x), int(spark_y)), 2)

        for machine in range(4):
            machine_x = machine * (WIDTH / 3.5) + 40
            pygame.draw.rect(screen, (35, 30, 32), (machine_x, HEIGHT - 90, 70, 90))

    elif scene == "fairground":
        # A tall bonfire flicker plus a scatter of string lights.
        flame_base = (WIDTH / 2, HEIGHT - 20)

        for index in range(16):
            flicker = (math.sin(t * 6 + index) + 1) / 2
            height = 60 + flicker * 50
            sway = math.sin(t * 3 + index * 0.7) * 14
            glow = (255, int(120 + flicker * 100), 30)
            pygame.draw.circle(
                screen, glow,
                (int(flame_base[0] + sway * (index / 16)), int(flame_base[1] - height)),
                4,
            )

        for index in range(10):
            light_x = (index / 9) * WIDTH
            light_y = 50 + math.sin(t * 2 + index) * 6
            twinkle = (math.sin(t * 4 + index * 2) + 1) / 2
            color = (int(255 * twinkle), int(200 * twinkle), 90)
            pygame.draw.circle(screen, color, (int(light_x), int(light_y)), 3)

    elif scene == "treeline":
        # Swaying dark tree silhouettes with a scatter of watching eyes.
        for tree in range(7):
            tree_x = tree * (WIDTH / 6)
            sway = math.sin(t * 0.7 + tree) * 10
            pygame.draw.polygon(
                screen, (10, 30, 16),
                [(tree_x - 50 + sway, HEIGHT), (tree_x + sway, HEIGHT - 140), (tree_x + 50 + sway, HEIGHT)],
            )

        for index in range(6):
            eye_x = rng.uniform(60, WIDTH - 60)
            eye_y = rng.uniform(HEIGHT * 0.4, HEIGHT * 0.75)
            blink = (math.sin(t * 2 + index * 3) + 1) / 2

            if blink > 0.4:
                pygame.draw.circle(screen, (255, 210, 90), (int(eye_x), int(eye_y)), 2)

    elif scene == "street":
        # A streetlamp cone of light with drifting musical notes.
        lamp_x = WIDTH / 2
        cone_surface = pygame.Surface((300, HEIGHT), pygame.SRCALPHA)
        pygame.draw.polygon(cone_surface, (200, 190, 140, 35), [(150, 0), (40, HEIGHT), (260, HEIGHT)])
        screen.blit(cone_surface, (lamp_x - 150, 0))

        for index in range(8):
            note_x = (lamp_x + math.sin(t * 0.9 + index * 2) * 160) % WIDTH
            note_y = (HEIGHT - (t * 30 + index * 90) % HEIGHT)
            pygame.draw.circle(screen, (230, 130, 220), (int(note_x), int(note_y)), 3)
            pygame.draw.line(screen, (230, 130, 220), (note_x + 3, note_y), (note_x + 3, note_y - 10), 2)

    elif scene == "airfield":
        # Horizontal wind streaks tearing across the runway.
        for index in range(14):
            streak_y = rng.uniform(0, HEIGHT)
            speed = 200 + (index % 4) * 60
            streak_x = (rng.uniform(0, WIDTH) + t * speed) % (WIDTH + 120) - 60
            length = 40 + (index % 3) * 20
            pygame.draw.line(
                screen, (210, 235, 225),
                (streak_x, streak_y), (streak_x + length, streak_y), 2,
            )


def draw_story_title_card(beat):
    screen.fill((14, 12, 18))

    t = pygame.time.get_ticks() / 1000

    for index in range(30):
        rng = random.Random(index)
        base_x = rng.uniform(0, WIDTH)
        base_y = rng.uniform(0, HEIGHT)
        drift_y = (base_y + t * 10) % HEIGHT
        flicker = (math.sin(t * 2 + index) + 1) / 2
        shade = int(30 + flicker * 40)
        pygame.draw.circle(screen, (shade, shade, shade + 10), (int(base_x), int(drift_y)), 1)

    fade_in = min(1.0, (pygame.time.get_ticks() % 100000) / 400)  # quick fade on first appearance

    title_surface = big_font.render(beat["title"], True, (255, 190, 60))
    title_surface.set_alpha(int(255 * fade_in))
    screen.blit(title_surface, title_surface.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 20)))

    subtitle_surface = font.render(beat.get("subtitle", ""), True, (220, 220, 230))
    subtitle_surface.set_alpha(int(255 * fade_in))
    screen.blit(subtitle_surface, subtitle_surface.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 24)))

    blink = (pygame.time.get_ticks() // 500) % 2 == 0

    if blink:
        prompt = small_font.render("▸ click / space to continue", True, (170, 170, 185))
        screen.blit(prompt, prompt.get_rect(center=(WIDTH // 2, HEIGHT - 60)))


def draw_story_cutscene():
    if not story_cutscene_beats:
        return

    index = min(story_cutscene_index, len(story_cutscene_beats) - 1)
    beat = story_cutscene_beats[index]

    if "title" in beat:
        draw_story_title_card(beat)
        return

    # The scene backdrop carries forward from the most recent beat that
    # set one, so consecutive lines in the same location don't need to
    # repeat it.
    scene = None
    for earlier_beat in story_cutscene_beats[:index + 1]:
        if "scene" in earlier_beat:
            scene = earlier_beat["scene"]

    draw_story_scene_background(scene)

    left_element = "fire"
    speaker = beat.get("speaker")

    # Who's actually "on screen" on the right depends on who has spoken
    # so far, not just which mission this is - otherwise the mission's
    # opponent portrait shows up during narration/setup beats before
    # they've actually appeared (e.g. Ice's face during Ash's kidnapping).
    right_element = None

    for earlier_beat in story_cutscene_beats[: story_cutscene_index + 1]:
        earlier_speaker = earlier_beat.get("speaker")

        if earlier_speaker not in (None, "fire", left_element):
            right_element = earlier_speaker

    if right_element is not None:
        draw_story_portrait((WIDTH * 0.76, HEIGHT * 0.42), 90, right_element, speaker == right_element, seed=1.7)

    draw_story_portrait((WIDTH * 0.24, HEIGHT * 0.42), 90, "fire", speaker == "fire", seed=0.0)

    # Dialogue box.
    box = pygame.Rect(70, HEIGHT - 190, WIDTH - 140, 150)
    box_surface = pygame.Surface((box.width, box.height), pygame.SRCALPHA)
    box_surface.fill((12, 12, 18, 225))
    screen.blit(box_surface, box.topleft)
    pygame.draw.rect(screen, (90, 90, 110), box, 2, border_radius=10)

    if speaker == "fire":
        name_label, name_color = "FIRE", (255, 150, 60)
    elif speaker is None:
        name_label, name_color = None, None
    elif speaker == story.STORY_SON_NAME.lower():
        name_label, name_color = story.STORY_SON_NAME.upper(), (255, 195, 130)
    else:
        name_label, name_color = ELEMENTS[speaker]["name"], ELEMENTS[speaker]["light_color"]

    text_top = box.top + 16

    if name_label:
        name_surface = font.render(name_label, True, name_color)
        screen.blit(name_surface, (box.left + 20, text_top))
        text_top += 28

    full_text = beat["text"]
    reveal_count = int(story_cutscene_reveal)
    visible_text = full_text[:reveal_count]
    lines = wrap_text(visible_text, box.width - 40)

    line_y = text_top
    for line in lines[:4]:
        line_surface = font.render(line, True, (230, 230, 235))
        screen.blit(line_surface, (box.left + 20, line_y))
        line_y += 24

    if reveal_count >= len(full_text):
        blink = (pygame.time.get_ticks() // 500) % 2 == 0

        if blink:
            prompt = small_font.render("▸ click / space to continue", True, (200, 200, 215))
            screen.blit(prompt, (box.right - prompt.get_width() - 18, box.bottom - 26))


def draw_game_modes():
    title = big_font.render("GAME MODES", True, (255, 190, 60))
    screen.blit(title, title.get_rect(center=(WIDTH // 2, 120)))

    mouse = pygame.mouse.get_pos()

    for key, button in GAME_MODE_BUTTONS.items():
        color = (220, 110, 45) if button.collidepoint(mouse) else (90, 80, 85)
        pygame.draw.rect(screen, color, button, border_radius=12)

        text = font.render(GAME_MODE_BUTTON_LABELS[key], True, "white")
        screen.blit(text, text.get_rect(center=button.center))

    pygame.draw.rect(screen, (75, 75, 90), back_button, border_radius=8)
    draw_text("BACK", 63, 36)


def draw_encyclopedia():
    title = big_font.render("CHARACTER ENCYCLOPEDIA", True, "white")
    screen.blit(title, title.get_rect(center=(WIDTH // 2, 65)))

    mouse = pygame.mouse.get_pos()

    for element, button in encyclopedia_list_buttons.items():
        data = ELEMENTS[element]
        is_selected = element == encyclopedia_selected

        if is_selected:
            color = data["color"]
        elif button.collidepoint(mouse):
            color = tuple(min(255, channel + 30) for channel in data["color"])
        else:
            color = tuple(channel // 3 for channel in data["color"])

        pygame.draw.rect(screen, color, button, border_radius=10)

        if is_selected:
            pygame.draw.rect(screen, "white", button, 3, border_radius=10)

        label = font.render(data["name"], True, "white")
        screen.blit(label, label.get_rect(center=button.center))

    data = ELEMENTS[encyclopedia_selected]
    panel = pygame.Rect(300, 130, 760, 500)
    pygame.draw.rect(screen, (30, 33, 44), panel, border_radius=14)
    pygame.draw.rect(screen, data["color"], panel, 3, border_radius=14)

    name_label = big_font.render(data["name"], True, data["light_color"])
    screen.blit(name_label, (panel.x + 30, panel.y + 20))

    stat_rows = [
        ("Difficulty", data["difficulty"]),
        ("Short Range", data["short_name"]),
        ("Long Range", data["long_name"]),
        ("Ultimate", data["ultimate_name"]),
        ("Movement", data["movement_name"]),
        ("Passive", data["passive_name"]),
    ]

    stat_y = panel.y + 80

    for label, value in stat_rows:
        draw_text(f"{label}:", panel.x + 30, stat_y, (170, 175, 190))
        draw_text(value, panel.x + 190, stat_y, "white")
        stat_y += 28

    stat_y += 6
    passive_lines = wrap_text(data["passive_desc"], panel.width - 60)

    for line in passive_lines:
        draw_text(line, panel.x + 30, stat_y, (190, 210, 230))
        stat_y += 24

    stat_y += 20
    draw_text("Backstory", panel.x + 30, stat_y, (255, 210, 120))
    stat_y += 30

    bio_lines = wrap_text(data["bio"], panel.width - 60)

    for line in bio_lines:
        draw_text(line, panel.x + 30, stat_y, (215, 215, 225))
        stat_y += 24

    pygame.draw.rect(screen, (75, 75, 90), back_button, border_radius=8)
    draw_text("BACK", 63, 36)


def draw_how_to_play_hub():
    title = big_font.render("HOW TO PLAY", True, "white")
    screen.blit(title, title.get_rect(center=(WIDTH // 2, 170)))

    mouse = pygame.mouse.get_pos()

    for key, button in HUB_BUTTONS.items():
        color = (220, 110, 45) if button.collidepoint(mouse) else (90, 80, 85)
        pygame.draw.rect(screen, color, button, border_radius=12)

        text = font.render(HUB_BUTTON_LABELS[key], True, "white")
        screen.blit(text, text.get_rect(center=button.center))

    pygame.draw.rect(screen, (75, 75, 90), back_button, border_radius=8)
    draw_text("BACK", 63, 36)


SETTINGS_BUTTON_WIDTH = 380
SETTINGS_X = (WIDTH - SETTINGS_BUTTON_WIDTH) // 2  # 360, keeps every row's edges aligned

music_toggle_button = pygame.Rect(SETTINGS_X, 172, SETTINGS_BUTTON_WIDTH, 46)
menu_track_button = pygame.Rect(SETTINGS_X, 234, SETTINGS_BUTTON_WIDTH, 46)
game_track_button = pygame.Rect(SETTINGS_X, 296, SETTINGS_BUTTON_WIDTH, 46)
dummy_behavior_button = pygame.Rect(SETTINGS_X, 358, SETTINGS_BUTTON_WIDTH, 46)
fps_toggle_button = pygame.Rect(SETTINGS_X, 420, SETTINGS_BUTTON_WIDTH, 46)
input_mode_button = pygame.Rect(SETTINGS_X, 482, SETTINGS_BUTTON_WIDTH, 46)

DIFFICULTY_LABEL_Y = 548
DIFFICULTY_MINUS_BUTTON = pygame.Rect(SETTINGS_X, 574, 60, 46)
DIFFICULTY_PLUS_BUTTON = pygame.Rect(SETTINGS_X + SETTINGS_BUTTON_WIDTH - 60, 574, 60, 46)
DIFFICULTY_LABEL_RECT = pygame.Rect(SETTINGS_X + 70, 574, SETTINGS_BUTTON_WIDTH - 140, 46)

NPC_DIFFICULTY_NAMES = {
    1: "Rookie",
    2: "Easy",
    3: "Casual",
    4: "Normal",
    5: "Skilled",
    6: "Tough",
    7: "Expert",
    8: "Elite",
    9: "Nightmare",
}

DUMMY_BEHAVIOR_LABELS = {
    "idle": "Idle",
    "attack": "Attack",
    "move": "Move Around",
}


def draw_shop_stall():
    """A simple decorative market stall - poles, a striped awning, and a
    counter - drawn entirely from shapes, no image assets."""
    stall_center_x = WIDTH // 2
    counter_top = 480
    counter_bottom = 560
    counter_width = 420

    # Support poles
    for offset in (-190, 190):
        pole_x = stall_center_x + offset
        pygame.draw.rect(screen, (110, 75, 45), (pole_x - 8, 260, 16, counter_top - 260))

    # Striped awning (a fan of triangles under a canopy bar)
    awning_top = 230
    awning_left = stall_center_x - 220
    awning_right = stall_center_x + 220
    pygame.draw.rect(screen, (120, 40, 40), (awning_left, awning_top, awning_right - awning_left, 18))

    stripe_count = 9
    stripe_width = (awning_right - awning_left) / stripe_count

    for index in range(stripe_count):
        stripe_x = awning_left + index * stripe_width
        color = (200, 60, 60) if index % 2 == 0 else (235, 225, 200)
        points = [
            (stripe_x, awning_top + 18),
            (stripe_x + stripe_width, awning_top + 18),
            (stripe_x + stripe_width * 0.6, awning_top + 55),
            (stripe_x + stripe_width * 0.4, awning_top + 55),
        ]
        pygame.draw.polygon(screen, color, points)

    # Counter
    pygame.draw.rect(
        screen, (150, 105, 65),
        (stall_center_x - counter_width // 2, counter_top, counter_width, counter_bottom - counter_top),
        border_radius=6,
    )
    pygame.draw.rect(
        screen, (110, 75, 45),
        (stall_center_x - counter_width // 2, counter_top, counter_width, counter_bottom - counter_top),
        3, border_radius=6,
    )

    for plank_x in range(stall_center_x - counter_width // 2 + 30, stall_center_x + counter_width // 2, 40):
        pygame.draw.line(screen, (110, 75, 45), (plank_x, counter_top + 6), (plank_x, counter_bottom - 6), 2)

    # Empty display shelf on the counter (nothing on it - all sold out)
    pygame.draw.rect(
        screen, (60, 65, 78),
        (stall_center_x - counter_width // 2 + 20, counter_top - 14, counter_width - 40, 14),
        border_radius=3,
    )


def draw_shop():
    title = big_font.render("SHOP", True, "white")
    screen.blit(title, title.get_rect(center=(WIDTH // 2, 90)))

    if account_username is None:
        draw_shop_stall()

        draw_text(
            "Log in to earn currency from matches and visit the shop.",
            WIDTH // 2 - 260, 150, (200, 200, 210),
        )

        mouse = pygame.mouse.get_pos()
        color = (220, 110, 45) if ACCOUNT_LOGIN_BUTTON.collidepoint(mouse) else (90, 80, 85)
        pygame.draw.rect(screen, color, ACCOUNT_LOGIN_BUTTON, border_radius=12)
        text = font.render("GO TO ACCOUNT", True, "white")
        screen.blit(text, text.get_rect(center=ACCOUNT_LOGIN_BUTTON.center))
    else:
        currency = (account_stats or {}).get("currency", 0)
        draw_text(f"Your coins: {currency}", WIDTH // 2 - 90, 150, (255, 210, 120), big_font)

        draw_shop_stall()

        sold_out_font = pygame.font.SysFont("arial", 64, bold=True)
        sold_out_text = sold_out_font.render("ALL SOLD OUT", True, (255, 235, 235))
        rotated = pygame.transform.rotate(sold_out_text, 12)
        screen.blit(rotated, rotated.get_rect(center=(WIDTH // 2, 400)))

    pygame.draw.rect(screen, (75, 75, 90), back_button, border_radius=8)
    draw_text("BACK", 63, 36)


def draw_settings():
    title = big_font.render("SETTINGS", True, "white")
    screen.blit(title, title.get_rect(center=(WIDTH // 2, 120)))

    mouse = pygame.mouse.get_pos()
    label_max_width = SETTINGS_BUTTON_WIDTH - 24

    if not AUDIO_ENABLED:
        label = "MUSIC UNAVAILABLE"
        color = (70, 70, 78)
    elif music_enabled:
        label = "MUSIC: ON"
        color = (90, 170, 100) if music_toggle_button.collidepoint(mouse) else (70, 130, 80)
    else:
        label = "MUSIC: OFF"
        color = (170, 90, 90) if music_toggle_button.collidepoint(mouse) else (110, 70, 70)

    pygame.draw.rect(screen, color, music_toggle_button, border_radius=12)
    draw_fitted_text(label, music_toggle_button.center, label_max_width)

    if AUDIO_ENABLED and menu_music_sounds:
        menu_track_name = MENU_MUSIC_TRACKS[selected_menu_track][0]
        menu_color = (90, 85, 100) if menu_track_button.collidepoint(mouse) else (70, 65, 80)
        pygame.draw.rect(screen, menu_color, menu_track_button, border_radius=12)
        draw_fitted_text(f"MENU MUSIC: {menu_track_name}", menu_track_button.center, label_max_width)

    if AUDIO_ENABLED and game_music_sounds:
        game_track_name = GAME_MUSIC_TRACKS[selected_game_track][0]
        game_color = (90, 85, 100) if game_track_button.collidepoint(mouse) else (70, 65, 80)
        pygame.draw.rect(screen, game_color, game_track_button, border_radius=12)
        draw_fitted_text(f"GAME MUSIC: {game_track_name}", game_track_button.center, label_max_width)

    dummy_color = (90, 90, 105) if dummy_behavior_button.collidepoint(mouse) else (72, 72, 86)
    pygame.draw.rect(screen, dummy_color, dummy_behavior_button, border_radius=12)
    dummy_label = DUMMY_BEHAVIOR_LABELS[tutorial_bot_behavior]
    draw_fitted_text(f"TUTORIAL BOT: {dummy_label}", dummy_behavior_button.center, label_max_width)

    fps_color = (90, 170, 100) if show_fps else (72, 72, 86)
    if fps_toggle_button.collidepoint(mouse):
        fps_color = tuple(min(255, channel + 20) for channel in fps_color)
    pygame.draw.rect(screen, fps_color, fps_toggle_button, border_radius=12)
    draw_fitted_text(f"SHOW FPS: {'ON' if show_fps else 'OFF'}", fps_toggle_button.center, label_max_width)

    controller_missing = input_mode == "controller" and not joystick_connected()
    input_color = (170, 130, 60) if controller_missing else (90, 85, 100)
    if input_mode_button.collidepoint(mouse):
        input_color = tuple(min(255, channel + 20) for channel in input_color)
    pygame.draw.rect(screen, input_color, input_mode_button, border_radius=12)
    input_label = f"INPUT: {INPUT_MODE_LABELS[input_mode]}"

    if controller_missing:
        input_label += " (not detected)"
    elif input_mode == "controller" and controller_backend == "raw":
        input_label += " (unmapped, using Xbox layout)"
    elif input_mode == "controller" and controller_backend == "mapped":
        input_label += " (connected)"

    draw_fitted_text(input_label, input_mode_button.center, label_max_width)

    draw_text("NPC DIFFICULTY (applies everywhere):", SETTINGS_X, DIFFICULTY_LABEL_Y, (170, 175, 190), small_font)

    minus_color = (95, 95, 110) if DIFFICULTY_MINUS_BUTTON.collidepoint(mouse) else (75, 75, 90)
    pygame.draw.rect(screen, minus_color, DIFFICULTY_MINUS_BUTTON, border_radius=10)
    draw_fitted_text("-", DIFFICULTY_MINUS_BUTTON.center, DIFFICULTY_MINUS_BUTTON.width - 10)

    pygame.draw.rect(screen, (45, 48, 58), DIFFICULTY_LABEL_RECT, border_radius=10)
    difficulty_label = f"{npc_difficulty} - {NPC_DIFFICULTY_NAMES[npc_difficulty]}"
    draw_fitted_text(difficulty_label, DIFFICULTY_LABEL_RECT.center, DIFFICULTY_LABEL_RECT.width - 16)

    plus_color = (95, 95, 110) if DIFFICULTY_PLUS_BUTTON.collidepoint(mouse) else (75, 75, 90)
    pygame.draw.rect(screen, plus_color, DIFFICULTY_PLUS_BUTTON, border_radius=10)
    draw_fitted_text("+", DIFFICULTY_PLUS_BUTTON.center, DIFFICULTY_PLUS_BUTTON.width - 10)

    pygame.draw.rect(screen, (75, 75, 90), back_button, border_radius=8)
    draw_text("BACK", 63, 36)


ACCOUNT_LOGIN_BUTTON = pygame.Rect(400, 300, 300, 55)
ACCOUNT_REGISTER_BUTTON = pygame.Rect(400, 375, 300, 55)
ACCOUNT_LOGOUT_BUTTON = pygame.Rect(400, 500, 300, 50)
ACCOUNT_DELETE_BUTTON = pygame.Rect(400, 560, 300, 50)
ACCOUNT_ADMIN_PANEL_BUTTON = pygame.Rect(400, 620, 300, 50)

ADMIN_PASSWORD_FIELD = pygame.Rect(350, 300, 330, 46)
ADMIN_PASSWORD_SHOW_BUTTON = pygame.Rect(690, 300, 60, 46)
ADMIN_PASSWORD_CONFIRM_BUTTON = pygame.Rect(350, 380, 195, 50)
ADMIN_PASSWORD_CANCEL_BUTTON = pygame.Rect(555, 380, 195, 50)

ADMIN_PANEL_LIST_TOP = 170
ADMIN_PANEL_ROW_HEIGHT = 40
ADMIN_PANEL_DELETE_BUTTON_WIDTH = 90

ACCOUNT_USERNAME_FIELD = pygame.Rect(350, 260, 400, 46)
ACCOUNT_PASSWORD_FIELD = pygame.Rect(350, 320, 330, 46)
ACCOUNT_SHOW_PASSWORD_BUTTON = pygame.Rect(690, 320, 60, 46)
ACCOUNT_SUBMIT_BUTTON = pygame.Rect(400, 390, 300, 50)

ACCOUNT_DELETE_PASSWORD_FIELD = pygame.Rect(350, 300, 330, 46)
ACCOUNT_DELETE_SHOW_PASSWORD_BUTTON = pygame.Rect(690, 300, 60, 46)
ACCOUNT_DELETE_CONFIRM_BUTTON = pygame.Rect(350, 380, 195, 50)
ACCOUNT_DELETE_CANCEL_BUTTON = pygame.Rect(555, 380, 195, 50)


def draw_account_hub():
    title = big_font.render("ACCOUNT", True, "white")
    screen.blit(title, title.get_rect(center=(WIDTH // 2, 120)))

    mouse = pygame.mouse.get_pos()

    if account_username is None:
        for button, label in [
            (ACCOUNT_LOGIN_BUTTON, "LOG IN"),
            (ACCOUNT_REGISTER_BUTTON, "CREATE ACCOUNT"),
        ]:
            color = (220, 110, 45) if button.collidepoint(mouse) else (90, 80, 85)
            pygame.draw.rect(screen, color, button, border_radius=12)
            text = font.render(label, True, "white")
            screen.blit(text, text.get_rect(center=button.center))

        draw_text(
            "Not logged in. Your stats sync across any device once you log in.",
            WIDTH // 2 - 260, 230, (190, 190, 200),
        )
    else:
        draw_text(f"Logged in as: {account_username}", WIDTH // 2 - 130, 190, (255, 210, 120), big_font)

        stats = account_stats or {}
        level = stats.get("level", 1)
        xp = stats.get("xp", 0)

        rows = [
            ("Level", str(level)),
            ("Coins", str(stats.get("currency", 0))),
            ("Date joined", stats.get("date_joined", "-")),
            ("Games played", str(stats.get("games_played", 0))),
            ("Wins", str(stats.get("wins", 0))),
            ("Losses", str(stats.get("losses", 0))),
        ]

        row_y = 250

        for label, value in rows:
            draw_text(f"{label}:", WIDTH // 2 - 150, row_y, (170, 175, 190))
            draw_text(value, WIDTH // 2 + 30, row_y, "white")
            row_y += 32

        if level < len(LEVEL_THRESHOLDS):
            next_threshold = LEVEL_THRESHOLDS[level]
            draw_text(
                f"XP: {xp} / {next_threshold} to level {level + 1}",
                WIDTH // 2 - 150, row_y, (150, 190, 255),
            )
        else:
            draw_text(f"XP: {xp} - MAX LEVEL", WIDTH // 2 - 150, row_y, (150, 190, 255))

        row_y += 40

        color = (170, 90, 90) if ACCOUNT_LOGOUT_BUTTON.collidepoint(mouse) else (110, 70, 70)
        pygame.draw.rect(screen, color, ACCOUNT_LOGOUT_BUTTON, border_radius=12)
        text = font.render("LOG OUT", True, "white")
        screen.blit(text, text.get_rect(center=ACCOUNT_LOGOUT_BUTTON.center))

        delete_color = (190, 60, 55) if ACCOUNT_DELETE_BUTTON.collidepoint(mouse) else (95, 45, 45)
        pygame.draw.rect(screen, delete_color, ACCOUNT_DELETE_BUTTON, border_radius=12)
        delete_text = font.render("DELETE ACCOUNT", True, "white")
        screen.blit(delete_text, delete_text.get_rect(center=ACCOUNT_DELETE_BUTTON.center))

        if stats.get("is_admin"):
            admin_color = (150, 90, 220) if ACCOUNT_ADMIN_PANEL_BUTTON.collidepoint(mouse) else (85, 60, 120)
            pygame.draw.rect(screen, admin_color, ACCOUNT_ADMIN_PANEL_BUTTON, border_radius=12)
            admin_text = font.render("ADMIN PANEL", True, "white")
            screen.blit(admin_text, admin_text.get_rect(center=ACCOUNT_ADMIN_PANEL_BUTTON.center))

    if account_error:
        draw_text(account_error, WIDTH // 2 - 260, 630, (255, 130, 120))

    pygame.draw.rect(screen, (75, 75, 90), back_button, border_radius=8)
    draw_text("BACK", 63, 36)


def draw_account_text_field(rect, value, is_masked, is_active):
    border_color = (255, 210, 120) if is_active else (110, 110, 125)
    pygame.draw.rect(screen, (35, 38, 48), rect, border_radius=8)
    pygame.draw.rect(screen, border_color, rect, 2, border_radius=8)

    shown = "*" * len(value) if is_masked else value

    if is_active and pygame.time.get_ticks() % 1000 < 500:
        shown += "|"

    draw_text(shown, rect.x + 12, rect.y + 12, "white")


def draw_account_form(title_text):
    title = big_font.render(title_text, True, "white")
    screen.blit(title, title.get_rect(center=(WIDTH // 2, 170)))

    draw_text("Username", ACCOUNT_USERNAME_FIELD.x, ACCOUNT_USERNAME_FIELD.y - 24, (170, 175, 190))
    draw_account_text_field(
        ACCOUNT_USERNAME_FIELD, account_field_username, False, account_active_field == "username"
    )

    draw_text("Password", ACCOUNT_PASSWORD_FIELD.x, ACCOUNT_PASSWORD_FIELD.y - 24, (170, 175, 190))
    draw_account_text_field(
        ACCOUNT_PASSWORD_FIELD,
        account_field_password,
        not account_show_password,
        account_active_field == "password",
    )

    mouse = pygame.mouse.get_pos()

    show_color = (90, 130, 90) if account_show_password else (80, 80, 92)
    if ACCOUNT_SHOW_PASSWORD_BUTTON.collidepoint(mouse):
        show_color = tuple(min(255, channel + 25) for channel in show_color)

    pygame.draw.rect(screen, show_color, ACCOUNT_SHOW_PASSWORD_BUTTON, border_radius=8)
    show_label = font.render("HIDE" if account_show_password else "SHOW", True, "white")
    screen.blit(show_label, show_label.get_rect(center=ACCOUNT_SHOW_PASSWORD_BUTTON.center))

    color = (220, 110, 45) if ACCOUNT_SUBMIT_BUTTON.collidepoint(mouse) else (90, 80, 85)
    pygame.draw.rect(screen, color, ACCOUNT_SUBMIT_BUTTON, border_radius=12)
    label = "LOG IN" if title_text == "LOG IN" else "CREATE ACCOUNT"
    text = font.render(label, True, "white")
    screen.blit(text, text.get_rect(center=ACCOUNT_SUBMIT_BUTTON.center))

    draw_text("Click a field to type, Tab to switch, Enter to submit", 350, 445, (150, 155, 168))

    if account_error:
        draw_text(account_error, 350, 480, (255, 130, 120))

    pygame.draw.rect(screen, (75, 75, 90), back_button, border_radius=8)
    draw_text("BACK", 63, 36)


def draw_account_login():
    draw_account_form("LOG IN")


def draw_account_register():
    draw_account_form("CREATE ACCOUNT")


def draw_account_delete_confirm():
    title = big_font.render("DELETE ACCOUNT", True, (255, 140, 130))
    screen.blit(title, title.get_rect(center=(WIDTH // 2, 170)))

    draw_text(
        f"This permanently deletes '{account_username}' and all of its stats.",
        350, 220, (220, 190, 190),
    )
    draw_text("This can't be undone. Enter your password to confirm.", 350, 244, (220, 190, 190))

    draw_text("Password", ACCOUNT_DELETE_PASSWORD_FIELD.x, ACCOUNT_DELETE_PASSWORD_FIELD.y - 24, (170, 175, 190))
    draw_account_text_field(
        ACCOUNT_DELETE_PASSWORD_FIELD,
        account_delete_password,
        not account_delete_show_password,
        True,
    )

    mouse = pygame.mouse.get_pos()

    show_color = (90, 130, 90) if account_delete_show_password else (80, 80, 92)
    if ACCOUNT_DELETE_SHOW_PASSWORD_BUTTON.collidepoint(mouse):
        show_color = tuple(min(255, channel + 25) for channel in show_color)

    pygame.draw.rect(screen, show_color, ACCOUNT_DELETE_SHOW_PASSWORD_BUTTON, border_radius=8)
    show_label = font.render("HIDE" if account_delete_show_password else "SHOW", True, "white")
    screen.blit(show_label, show_label.get_rect(center=ACCOUNT_DELETE_SHOW_PASSWORD_BUTTON.center))

    confirm_color = (190, 60, 55) if ACCOUNT_DELETE_CONFIRM_BUTTON.collidepoint(mouse) else (110, 55, 55)
    pygame.draw.rect(screen, confirm_color, ACCOUNT_DELETE_CONFIRM_BUTTON, border_radius=12)
    confirm_text = font.render("CONFIRM DELETE", True, "white")
    screen.blit(confirm_text, confirm_text.get_rect(center=ACCOUNT_DELETE_CONFIRM_BUTTON.center))

    cancel_color = (95, 95, 110) if ACCOUNT_DELETE_CANCEL_BUTTON.collidepoint(mouse) else (75, 75, 90)
    pygame.draw.rect(screen, cancel_color, ACCOUNT_DELETE_CANCEL_BUTTON, border_radius=12)
    cancel_text = font.render("CANCEL", True, "white")
    screen.blit(cancel_text, cancel_text.get_rect(center=ACCOUNT_DELETE_CANCEL_BUTTON.center))

    if account_error:
        draw_text(account_error, 350, 450, (255, 130, 120))


def draw_admin_password_confirm():
    title = big_font.render("ADMIN PANEL", True, (200, 150, 255))
    screen.blit(title, title.get_rect(center=(WIDTH // 2, 170)))

    draw_text("Re-enter your password to view and manage accounts.", 350, 220, (210, 200, 220))

    draw_text("Password", ADMIN_PASSWORD_FIELD.x, ADMIN_PASSWORD_FIELD.y - 24, (170, 175, 190))
    draw_account_text_field(ADMIN_PASSWORD_FIELD, admin_password_field, not admin_password_show, True)

    mouse = pygame.mouse.get_pos()

    show_color = (90, 130, 90) if admin_password_show else (80, 80, 92)
    if ADMIN_PASSWORD_SHOW_BUTTON.collidepoint(mouse):
        show_color = tuple(min(255, channel + 25) for channel in show_color)

    pygame.draw.rect(screen, show_color, ADMIN_PASSWORD_SHOW_BUTTON, border_radius=8)
    show_label = font.render("HIDE" if admin_password_show else "SHOW", True, "white")
    screen.blit(show_label, show_label.get_rect(center=ADMIN_PASSWORD_SHOW_BUTTON.center))

    confirm_color = (150, 90, 220) if ADMIN_PASSWORD_CONFIRM_BUTTON.collidepoint(mouse) else (85, 60, 120)
    pygame.draw.rect(screen, confirm_color, ADMIN_PASSWORD_CONFIRM_BUTTON, border_radius=12)
    confirm_text = font.render("CONFIRM", True, "white")
    screen.blit(confirm_text, confirm_text.get_rect(center=ADMIN_PASSWORD_CONFIRM_BUTTON.center))

    cancel_color = (95, 95, 110) if ADMIN_PASSWORD_CANCEL_BUTTON.collidepoint(mouse) else (75, 75, 90)
    pygame.draw.rect(screen, cancel_color, ADMIN_PASSWORD_CANCEL_BUTTON, border_radius=12)
    cancel_text = font.render("CANCEL", True, "white")
    screen.blit(cancel_text, cancel_text.get_rect(center=ADMIN_PASSWORD_CANCEL_BUTTON.center))

    if admin_panel_error:
        draw_text(admin_panel_error, 350, 450, (255, 130, 120))

    pygame.draw.rect(screen, (75, 75, 90), back_button, border_radius=8)
    draw_text("BACK", 63, 36)


def admin_panel_row_rects(index):
    row_y = ADMIN_PANEL_LIST_TOP + index * ADMIN_PANEL_ROW_HEIGHT - admin_panel_scroll
    row_rect = pygame.Rect(70, row_y, WIDTH - 140, ADMIN_PANEL_ROW_HEIGHT - 6)
    delete_button = pygame.Rect(
        row_rect.right - ADMIN_PANEL_DELETE_BUTTON_WIDTH, row_rect.y,
        ADMIN_PANEL_DELETE_BUTTON_WIDTH, row_rect.height,
    )
    return row_rect, delete_button


def draw_admin_panel():
    title = big_font.render("ADMIN PANEL", True, (200, 150, 255))
    screen.blit(title, title.get_rect(center=(WIDTH // 2, 90)))

    draw_text(f"{len(admin_accounts)} account(s)", 70, 130, (170, 175, 190))

    mouse = pygame.mouse.get_pos()
    viewport = pygame.Rect(60, ADMIN_PANEL_LIST_TOP - 6, WIDTH - 120, HEIGHT - ADMIN_PANEL_LIST_TOP - 60)
    screen.set_clip(viewport)

    for index, entry in enumerate(admin_accounts):
        row_rect, delete_button = admin_panel_row_rects(index)

        if row_rect.bottom < viewport.top or row_rect.top > viewport.bottom:
            continue

        pygame.draw.rect(screen, (35, 35, 44), row_rect, border_radius=6)

        label = f"{entry['username']}  -  Lv{entry.get('level', 1)}  -  {entry.get('currency', 0)} coins"

        if entry.get("is_admin"):
            label += "  [ADMIN]"

        draw_text(label, row_rect.x + 12, row_rect.y + 9, (230, 230, 235), small_font)

        if admin_confirm_delete_username == entry["username"]:
            confirm_label = font.render("CONFIRM?", True, "white")
            screen.blit(confirm_label, confirm_label.get_rect(center=delete_button.center))
            pygame.draw.rect(screen, (210, 60, 55), delete_button, border_radius=6)
        elif not entry.get("is_admin"):
            delete_color = (170, 70, 65) if delete_button.collidepoint(mouse) else (110, 55, 55)
            pygame.draw.rect(screen, delete_color, delete_button, border_radius=6)
            delete_label = small_font.render("DELETE", True, "white")
            screen.blit(delete_label, delete_label.get_rect(center=delete_button.center))

    screen.set_clip(None)

    if admin_panel_error:
        draw_text(admin_panel_error, 70, HEIGHT - 46, (255, 130, 120))

    pygame.draw.rect(screen, (75, 75, 90), back_button, border_radius=8)
    draw_text("BACK", 63, 36)


def admin_panel_max_scroll():
    content_height = len(admin_accounts) * ADMIN_PANEL_ROW_HEIGHT
    viewport_height = HEIGHT - ADMIN_PANEL_LIST_TOP - 60
    return max(0, content_height - viewport_height)

    pygame.draw.rect(screen, (75, 75, 90), back_button, border_radius=8)
    draw_text("BACK", 63, 36)


def draw_tutorial_select():
    title = big_font.render("PICK A CHARACTER TO LEARN", True, "white")
    screen.blit(title, title.get_rect(center=(WIDTH // 2, 100)))

    mouse = pygame.mouse.get_pos()

    for element, button in tutorial_select_buttons.items():
        data = ELEMENTS[element]

        color = data["color"] if button.collidepoint(mouse) else tuple(
            channel // 2 for channel in data["color"]
        )

        pygame.draw.rect(screen, color, button, border_radius=10)

        label = font.render(data["name"], True, "white")
        screen.blit(label, label.get_rect(center=button.center))

    pygame.draw.rect(screen, (75, 75, 90), back_button, border_radius=8)
    draw_text("BACK", 63, 36)


HOW_TO_PLAY_SECTIONS = [
    ("Movement", ["WASD - move around the arena"]),
    (
        "Combat",
        [
            "Left Click - short-range attack",
            "Right Click - long-range attack",
            "Left + Right Click together - ultimate (needs a full bar)",
        ],
    ),
    (
        "Stamina",
        [
            "Every attack, special, and ultimate costs stamina (bar under",
            "the ultimate bar) - it regenerates on its own over time, so",
            "pace yourself instead of spamming everything at once",
        ],
    ),
    (
        "Special",
        [
            "Shift - element-specific movement special",
            "(dash, teleport, burrow, whip, hover, or blizzard-skate)",
        ],
    ),
    (
        "Other",
        [
            "R - restart the match",
            "Esc - return to the main menu",
        ],
    ),
    (
        "Arena tips",
        [
            "The storm shrinks over time - staying outside it deals damage",
            "Terrain patches (lava/stone/grass/ice) help or hurt depending",
            "on your element - check the Characters page for passives",
            "Use the minimap (top-right) to track opponents and terrain",
            "New here? Check CHARACTER TUTORIALS in this How To Play menu",
        ],
    ),
]

HOW_TO_PLAY_TOP = 150
HOW_TO_PLAY_BOTTOM = HEIGHT - 50

how_to_play_scroll = 0


def how_to_play_layout():
    """Returns (entries, total_height). Each entry is
    (y_offset, kind, text) relative to the top of the content."""
    entries = []
    y = 0

    for heading, lines in HOW_TO_PLAY_SECTIONS:
        entries.append((y, "heading", heading))
        y += 40

        for line in lines:
            entries.append((y, "line", line))
            y += 26

        y += 14

    return entries, y


def how_to_play_max_scroll():
    _, total_height = how_to_play_layout()
    viewport_height = HOW_TO_PLAY_BOTTOM - HOW_TO_PLAY_TOP
    return max(0, total_height - viewport_height)


def draw_how_to_play():
    title = big_font.render("HOW TO PLAY", True, "white")
    screen.blit(title, title.get_rect(center=(WIDTH // 2, 100)))

    entries, total_height = how_to_play_layout()
    viewport = pygame.Rect(
        0, HOW_TO_PLAY_TOP, WIDTH, HOW_TO_PLAY_BOTTOM - HOW_TO_PLAY_TOP
    )

    screen.set_clip(viewport)

    for offset, kind, text in entries:
        y = HOW_TO_PLAY_TOP + offset - how_to_play_scroll

        if y < HOW_TO_PLAY_TOP - 40 or y > HOW_TO_PLAY_BOTTOM:
            continue

        if kind == "heading":
            draw_text(text, 90, y, (255, 190, 60), big_font)
        else:
            draw_text(text, 110, y)

    screen.set_clip(None)

    if total_height > viewport.height:
        track = pygame.Rect(WIDTH - 34, viewport.top, 10, viewport.height)
        pygame.draw.rect(screen, (50, 50, 62), track, border_radius=5)

        max_scroll = how_to_play_max_scroll()
        thumb_height = max(30, viewport.height * viewport.height / total_height)
        scroll_fraction = how_to_play_scroll / max_scroll if max_scroll else 0
        thumb_y = track.top + scroll_fraction * (viewport.height - thumb_height)

        pygame.draw.rect(
            screen,
            (200, 200, 212),
            (track.left, thumb_y, track.width, thumb_height),
            border_radius=5,
        )

    pygame.draw.rect(screen, (75, 75, 90), back_button, border_radius=8)
    draw_text("BACK", 63, 36)


def draw_average_god_card(mouse):
    button = character_select_screen_rect(AVERAGE_GOD_BUTTON)

    if button.bottom < CHAR_SELECT_TOP or button.top > CHAR_SELECT_BOTTOM:
        return

    if not is_average_god_unlocked():
        color = (34, 34, 40)
        pygame.draw.rect(screen, color, button, border_radius=18)
        pygame.draw.rect(screen, (55, 55, 64), button, 2, border_radius=18)

        mark = big_font.render("?", True, (90, 90, 100))
        screen.blit(mark, mark.get_rect(center=(button.centerx, button.y + 68)))
        draw_text("???", button.x + 20, button.y + 96, (90, 90, 100))
        draw_text("???", button.x + 20, button.y + 118, (90, 90, 100))
        return

    shown_element = "god" if average_god_flipped else "average"
    data = ELEMENTS[shown_element]

    color = data["color"] if button.collidepoint(mouse) else tuple(channel // 2 for channel in data["color"])
    pygame.draw.rect(screen, color, button, border_radius=18)

    name_label = big_font.render(data["name"], True, "white")
    screen.blit(name_label, name_label.get_rect(center=(button.centerx, button.y + 68)))
    draw_text(data["short_name"], button.x + 20, button.y + 96)
    draw_text(data["long_name"], button.x + 20, button.y + 118)

    flip_button = pygame.Rect(0, 0, 26, 26)
    flip_button.topright = (button.right - 10, button.top + 10)
    flip_color = (255, 255, 255) if flip_button.collidepoint(mouse) else (220, 220, 220)
    pygame.draw.rect(screen, (0, 0, 0, 0), flip_button)  # keep hit area, no fill
    pygame.draw.circle(screen, flip_color, flip_button.center, 12, 2)
    arrow_a = (flip_button.centerx - 4, flip_button.centery - 3)
    arrow_b = (flip_button.centerx + 4, flip_button.centery - 3)
    arrow_c = (flip_button.centerx, flip_button.centery + 4)
    pygame.draw.polygon(screen, flip_color, (arrow_a, arrow_b, arrow_c))


def draw_character_select():
    title = big_font.render("CHOOSE YOUR ELEMENT", True, "white")
    screen.blit(title, title.get_rect(center=(WIDTH // 2, 135)))

    mouse = pygame.mouse.get_pos()
    viewport = pygame.Rect(
        0, CHAR_SELECT_TOP, WIDTH, CHAR_SELECT_BOTTOM - CHAR_SELECT_TOP
    )

    screen.set_clip(viewport)

    for element, base_button in element_buttons.items():
        button = character_select_screen_rect(base_button)

        if button.bottom < viewport.top or button.top > viewport.bottom:
            continue

        data = ELEMENTS[element]
        unlocked = is_character_unlocked(element)

        if not unlocked:
            color = (48, 48, 54)
        else:
            color = data["color"] if button.collidepoint(mouse) else tuple(
                channel // 2 for channel in data["color"]
            )

        pygame.draw.rect(screen, color, button, border_radius=18)

        name_color = "white" if unlocked else (120, 120, 128)
        name_label = big_font.render(data["name"], True, name_color)
        screen.blit(name_label, name_label.get_rect(center=(button.centerx, button.y + 68)))

        if unlocked:
            draw_text(data["short_name"], button.x + 20, button.y + 96)
            draw_text(data["long_name"], button.x + 20, button.y + 118)
        else:
            required_level = CHARACTER_UNLOCK_LEVEL.get(element, 1)
            draw_text(f"LOCKED - reach level {required_level}", button.x + 20, button.y + 96, (170, 170, 178))

    draw_average_god_card(mouse)

    screen.set_clip(None)

    total_slots = len(ELEMENTS) - len(AVERAGE_GOD_ELEMENTS) + 1
    total_height = -(-total_slots // _GRID_COLS) * (_GRID_ROW_H + _GRID_ROW_GAP) - _GRID_ROW_GAP

    if total_height > viewport.height:
        track = pygame.Rect(WIDTH - 24, viewport.top, 10, viewport.height)
        pygame.draw.rect(screen, (50, 50, 62), track, border_radius=5)

        max_scroll = character_select_max_scroll()
        thumb_height = max(30, viewport.height * viewport.height / total_height)
        scroll_fraction = character_select_scroll / max_scroll if max_scroll else 0
        thumb_y = track.top + scroll_fraction * (viewport.height - thumb_height)

        pygame.draw.rect(
            screen,
            (200, 200, 212),
            (track.left, thumb_y, track.width, thumb_height),
            border_radius=5,
        )

    pygame.draw.rect(screen, (75, 75, 90), back_button, border_radius=8)
    draw_text("BACK", 63, 36)


map_select_buttons = {}

_MAP_COLS = 2
_MAP_BTN_W = 320
_MAP_BTN_H = 130
_MAP_GAP_X = 30
_MAP_GAP_Y = 24
_MAP_ROW_WIDTH = _MAP_COLS * _MAP_BTN_W + (_MAP_COLS - 1) * _MAP_GAP_X
_MAP_START_X = (WIDTH - _MAP_ROW_WIDTH) / 2
_MAP_START_Y = 150

for _map_index in range(len(MAPS)):
    _map_col = _map_index % _MAP_COLS
    _map_row = _map_index // _MAP_COLS

    map_select_buttons[_map_index] = pygame.Rect(
        _MAP_START_X + _map_col * (_MAP_BTN_W + _MAP_GAP_X),
        _MAP_START_Y + _map_row * (_MAP_BTN_H + _MAP_GAP_Y),
        _MAP_BTN_W,
        _MAP_BTN_H,
    )

_MAP_RANDOM_ROW_Y = _MAP_START_Y + ((len(MAPS) + 1) // 2) * (_MAP_BTN_H + _MAP_GAP_Y)
map_random_button = pygame.Rect(WIDTH // 2 - 160, _MAP_RANDOM_ROW_Y, 320, 60)


def draw_map_preview(rect, map_def):
    preview = pygame.Rect(rect.x + 14, rect.y + 34, rect.width - 28, rect.height - 48)
    pygame.draw.rect(screen, (30, 33, 42), preview, border_radius=6)

    scale_x = preview.width / WORLD_WIDTH
    scale_y = preview.height / WORLD_HEIGHT

    for zone in map_def["zones"]:
        zone_x = preview.x + zone["pos"].x * scale_x
        zone_y = preview.y + zone["pos"].y * scale_y
        zone_r = max(3, zone["radius"] * min(scale_x, scale_y))
        pygame.draw.circle(screen, TERRAIN_COLORS[zone["type"]], (zone_x, zone_y), zone_r)

    pygame.draw.rect(screen, (80, 80, 92), preview, 1, border_radius=6)


def draw_map_select():
    title = big_font.render("CHOOSE A MAP", True, "white")
    screen.blit(title, title.get_rect(center=(WIDTH // 2, 90)))

    mouse = pygame.mouse.get_pos()

    for index, button in map_select_buttons.items():
        map_def = MAPS[index]
        is_selected = index == selected_map_index

        color = (90, 85, 75) if button.collidepoint(mouse) else (60, 58, 52)
        pygame.draw.rect(screen, color, button, border_radius=12)

        if is_selected:
            pygame.draw.rect(screen, (255, 210, 120), button, 3, border_radius=12)

        draw_text(map_def["name"], button.x + 14, button.y + 8, "white")
        draw_map_preview(button, map_def)

    random_selected = selected_map_index == MAP_RANDOM_INDEX
    random_color = (90, 75, 95) if map_random_button.collidepoint(mouse) else (65, 55, 68)
    pygame.draw.rect(screen, random_color, map_random_button, border_radius=12)

    if random_selected:
        pygame.draw.rect(screen, (255, 210, 120), map_random_button, 3, border_radius=12)

    random_text = font.render("RANDOM MAP", True, "white")
    screen.blit(random_text, random_text.get_rect(center=map_random_button.center))

    pygame.draw.rect(screen, (75, 75, 90), back_button, border_radius=8)
    draw_text("BACK", 63, 36)


def draw_opponent_select():
    title = big_font.render("HOW MANY OPPONENTS?", True, "white")
    screen.blit(title, title.get_rect(center=(WIDTH // 2, 190)))

    subtitle = font.render(
        "Choose 1 to 8 bots for a free-for-all match.",
        True,
        (210, 210, 220),
    )

    screen.blit(subtitle, subtitle.get_rect(center=(WIDTH // 2, 245)))

    mouse = pygame.mouse.get_pos()

    for count, button in count_buttons.items():
        color = (255, 185, 60) if button.collidepoint(mouse) else (125, 95, 55)

        pygame.draw.rect(screen, color, button, border_radius=14)

        label = big_font.render(str(count), True, "white")
        screen.blit(label, label.get_rect(center=button.center))

    pygame.draw.rect(screen, (75, 75, 90), back_button, border_radius=8)
    draw_text("BACK", 63, 36)


def draw_lava_zone(center, radius, decor, t):
    pygame.draw.circle(screen, (100, 28, 15), center, radius)
    pygame.draw.circle(screen, (150, 45, 22), center, radius * 0.88)

    for index in range(5):
        angle = index * 1.257 + t * 0.12
        offset = Vector2(math.cos(angle), math.sin(angle)) * radius * 0.42
        patch_color = (195, 75, 20) if index % 2 == 0 else (225, 120, 30)
        pygame.draw.circle(
            screen, patch_color,
            (center.x + offset.x, center.y + offset.y),
            radius * 0.24,
        )

    for bubble in decor["bubbles"]:
        cycle = (t * bubble["speed"] + bubble["phase"]) % 6.283
        progress = cycle / 6.283

        if progress < 0.75:
            bubble_r = bubble["max_r"] * (progress / 0.75)
            alpha = 255
        else:
            bubble_r = bubble["max_r"]
            alpha = max(0, int(255 * (1 - (progress - 0.75) / 0.25)))

        if bubble_r >= 1.5:
            size = int(bubble_r) + 2
            bubble_surf = pygame.Surface((size * 2, size * 2), pygame.SRCALPHA)
            pygame.draw.circle(bubble_surf, (255, 170, 50, alpha), (size, size), bubble_r)
            pygame.draw.circle(bubble_surf, (255, 225, 140, alpha), (size, size), max(1, bubble_r * 0.45))
            screen.blit(bubble_surf, (center.x + bubble["x"] - size, center.y + bubble["y"] - size))

    for ember in decor["embers"]:
        travel = (t * ember["speed"]) % (radius * 2)
        y_pos = ember["y"] - travel

        while y_pos < -radius:
            y_pos += radius * 2

        if ember["x"] ** 2 + y_pos ** 2 <= radius ** 2:
            fade = max(0, 1 - abs(y_pos + radius * 0.3) / radius)
            alpha = int(200 * fade)

            if alpha > 10:
                ember_surf = pygame.Surface((8, 8), pygame.SRCALPHA)
                pygame.draw.circle(ember_surf, (255, 160, 60, alpha), (4, 4), ember["size"])
                screen.blit(ember_surf, (center.x + ember["x"] - 4, center.y + y_pos - 4))


def draw_water_zone(center, radius, decor, t):
    pygame.draw.circle(screen, (22, 65, 115), center, radius)
    pygame.draw.circle(screen, (32, 92, 150), center, radius * 0.85)

    band_count = 4
    for band in range(band_count):
        band_y = math.sin(t * 0.8 + band * 1.4) * radius * 0.3
        band_alpha = 40
        band_surf = pygame.Surface((int(radius * 1.7), 14), pygame.SRCALPHA)
        pygame.draw.ellipse(band_surf, (140, 195, 235, band_alpha), band_surf.get_rect())
        screen.blit(band_surf, (center.x - radius * 0.85, center.y + band_y - 7))

    for ripple in decor["ripples"]:
        cycle = (t * 0.5 + ripple["phase"]) % 2.4
        ripple_r = (cycle / 2.4) * radius
        alpha = max(0, int(150 * (1 - cycle / 2.4)))

        if ripple_r > 2 and alpha > 0:
            size = int(ripple_r) + 3
            ripple_surf = pygame.Surface((size * 2, size * 2), pygame.SRCALPHA)
            pygame.draw.circle(ripple_surf, (175, 220, 255, alpha), (size, size), ripple_r, 2)
            screen.blit(ripple_surf, (center.x - size, center.y - size))

    for sparkle in decor["sparkles"]:
        twinkle = (math.sin(t * 2.2 + sparkle["phase"]) + 1) / 2

        if twinkle > 0.55:
            alpha = int((twinkle - 0.55) / 0.45 * 230)
            spark_surf = pygame.Surface((6, 6), pygame.SRCALPHA)
            pygame.draw.circle(spark_surf, (255, 255, 255, alpha), (3, 3), 2)
            screen.blit(spark_surf, (center.x + sparkle["x"] - 3, center.y + sparkle["y"] - 3))


def draw_ice_zone(center, radius, decor, t):
    pygame.draw.circle(screen, (145, 205, 235), center, radius)
    pygame.draw.circle(screen, (188, 228, 248), center, radius * 0.85)

    for crystal in decor["crystals"]:
        shimmer = (math.sin(t * 1.5 + crystal["phase"]) + 1) / 2
        alpha = int(90 + shimmer * 120)
        pos = Vector2(center.x + crystal["x"], center.y + crystal["y"])
        points = [
            pos + Vector2(0, -9), pos + Vector2(6, 0),
            pos + Vector2(0, 9), pos + Vector2(-6, 0),
        ]
        crystal_surf = pygame.Surface((20, 20), pygame.SRCALPHA)
        local_points = [(p.x - pos.x + 10, p.y - pos.y + 10) for p in points]
        pygame.draw.polygon(crystal_surf, (255, 255, 255, alpha), local_points)
        screen.blit(crystal_surf, (pos.x - 10, pos.y - 10))

    for flake in decor["snow"]:
        fall = (t * flake["speed"]) % (radius * 2)
        y_pos = flake["y"] + fall

        while y_pos > radius:
            y_pos -= radius * 2

        drift = math.sin(t * 1.2 + flake["drift_phase"]) * 6
        x_pos = flake["x"] + drift

        if x_pos ** 2 + y_pos ** 2 <= radius ** 2:
            pygame.draw.circle(screen, (255, 255, 255), (center.x + x_pos, center.y + y_pos), flake["size"])


def draw_grass_zone(center, radius, decor, t):
    pygame.draw.circle(screen, (38, 88, 46), center, radius)
    pygame.draw.circle(screen, (50, 106, 56), center, radius * 0.9)

    for blade in decor["blades"]:
        sway = math.sin(t * 1.6 + blade["phase"]) * 4
        base = (center.x + blade["x"], center.y + blade["y"])
        tip = (base[0] + sway, base[1] - blade["height"])
        shade = blade["shade"]
        color = (int(85 * shade), int(175 * shade), int(85 * shade))
        pygame.draw.line(screen, color, base, tip, 2)

    for flower in decor["flowers"]:
        pos = (center.x + flower["x"], center.y + flower["y"])
        pygame.draw.circle(screen, flower["color"], pos, 3)
        pygame.draw.circle(screen, (255, 235, 150), pos, 1)


def draw_stone_zone(center, radius, decor, t):
    pygame.draw.circle(screen, (85, 85, 96), center, radius)
    pygame.draw.circle(screen, (105, 105, 118), center, radius * 0.9)

    for rock in decor["rocks"]:
        shade = rock["shade"]
        color = (int(115 * shade), int(115 * shade), int(126 * shade))
        outline = (int(60 * shade), int(60 * shade), int(68 * shade))
        points = [
            (center.x + rock["x"] + dx, center.y + rock["y"] + dy)
            for dx, dy in rock["points"]
        ]
        pygame.draw.polygon(screen, color, points)
        pygame.draw.polygon(screen, outline, points, 2)


def draw_terrain():
    t = pygame.time.get_ticks() / 1000

    for zone in TERRAIN_ZONES:
        screen_pos = world_to_screen(zone["pos"])
        radius = zone["radius"]
        decor = zone["decor"]

        if zone["type"] == "lava":
            draw_lava_zone(screen_pos, radius, decor, t)
        elif zone["type"] == "water":
            draw_water_zone(screen_pos, radius, decor, t)
        elif zone["type"] == "ice":
            draw_ice_zone(screen_pos, radius, decor, t)
        elif zone["type"] == "grass":
            draw_grass_zone(screen_pos, radius, decor, t)
        elif zone["type"] == "stone":
            draw_stone_zone(screen_pos, radius, decor, t)

        pygame.draw.circle(screen, TERRAIN_BORDER_COLORS[zone["type"]], screen_pos, radius, 3)


def draw_shadow_pockets():
    """Soft dark-purple voids on the arena floor where shadow fighters can
    hide. Drawn before fighters so the player blends into them."""
    for pocket in SHADOW_POCKETS:
        screen_pos = world_to_screen(pocket["pos"])
        radius = int(pocket["radius"])

        # Layered translucent fill gives a soft "void" gradient.
        for alpha, scale in ((70, 1.0), (55, 0.7), (40, 0.4)):
            r = max(2, int(radius * scale))
            blob = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
            pygame.draw.circle(blob, (40, 25, 70, alpha), (r, r), r)
            screen.blit(blob, (int(screen_pos.x - r), int(screen_pos.y - r)))

        pygame.draw.circle(screen, (110, 70, 160), screen_pos, radius, 2)


def draw_rage_aura():
    """Pulsing red ring around the player while Bloodlust or Adrenaline is
    active. Drawn between terrain and projectiles so it sits on the floor
    but under incoming fire."""
    screen_pos = world_to_screen(player.pos)

    if bloodlust is not None:
        t = pygame.time.get_ticks() / 200
        radius = int(48 + 6 * math.sin(t))
        pulse = 0.5 + 0.5 * math.sin(t * 1.5)

        glow = pygame.Surface((radius * 4, radius * 4), pygame.SRCALPHA)
        pygame.draw.circle(
            glow,
            (255, 60, 60, int(70 + 50 * pulse)),
            (radius * 2, radius * 2),
            radius * 2,
        )
        screen.blit(glow, (int(screen_pos.x - radius * 2), int(screen_pos.y - radius * 2)))

        pygame.draw.circle(screen, (255, 70, 70), screen_pos, radius, 4)

    if adrenaline is not None:
        t = pygame.time.get_ticks() / 130
        radius = int(34 + 5 * math.sin(t))

        glow = pygame.Surface((radius * 3, radius * 3), pygame.SRCALPHA)
        pygame.draw.circle(
            glow,
            (255, 130, 90, 80),
            (radius * 1.5, radius * 1.5),
            radius * 1.5,
        )
        screen.blit(glow, (int(screen_pos.x - radius * 1.5), int(screen_pos.y - radius * 1.5)))

        pygame.draw.circle(screen, (255, 140, 95), screen_pos, radius, 3)


def draw_zigzag(surface, start, end, color, width=3, segments=5, jitter=7):
    direction = end - start

    if direction.length() == 0:
        return

    direction = direction.normalize()
    perpendicular = Vector2(-direction.y, direction.x)

    points = [start]

    for step in range(1, segments):
        t = step / segments
        base_point = start.lerp(end, t)
        offset = perpendicular * random.uniform(-jitter, jitter)
        points.append(base_point + offset)

    points.append(end)

    pygame.draw.lines(surface, color, False, [(p.x, p.y) for p in points], width)


def draw_projectile_shape(surface, screen_pos, velocity, element, color, radius):
    """Gives a handful of elements a distinct projectile silhouette
    instead of a plain circle. Anything not listed here (shadow, metal,
    and the fallback case) keeps the original circle look."""
    direction = velocity.normalize() if velocity.length() > 0 else Vector2(1, 0)
    perpendicular = Vector2(-direction.y, direction.x)

    if element == "fire":
        # Fireball: a bright core with a short flame lick trailing back.
        pygame.draw.circle(surface, color, screen_pos, radius)
        pygame.draw.circle(surface, (255, 230, 160), screen_pos, max(1, radius - 3))
        flame_tip = screen_pos - direction * (radius * 2.2)
        flame_points = [
            screen_pos - perpendicular * radius * 0.6,
            flame_tip,
            screen_pos + perpendicular * radius * 0.6,
        ]
        pygame.draw.polygon(surface, (255, 140, 40), [(p.x, p.y) for p in flame_points])

    elif element == "ice":
        # Icicle: an elongated triangle pointing the way it's travelling.
        tip = screen_pos + direction * radius * 2.2
        back_left = screen_pos - direction * radius - perpendicular * radius * 0.8
        back_right = screen_pos - direction * radius + perpendicular * radius * 0.8
        pygame.draw.polygon(
            surface, color, [(tip.x, tip.y), (back_left.x, back_left.y), (back_right.x, back_right.y)]
        )
        pygame.draw.polygon(
            surface, (230, 250, 255),
            [(tip.x, tip.y), (back_left.x, back_left.y), (back_right.x, back_right.y)],
            1,
        )

    elif element == "nature":
        # Flower: a ring of petal dots around a small bright center.
        for angle in range(0, 360, 72):
            petal_offset = Vector2(radius * 1.3, 0).rotate(angle)
            petal_pos = screen_pos + petal_offset
            pygame.draw.circle(surface, color, petal_pos, max(2, int(radius * 0.55)))
        pygame.draw.circle(surface, (255, 235, 140), screen_pos, max(2, int(radius * 0.6)))

    elif element == "earth":
        # Slab: a chunky rotated rectangle.
        half_length = radius * 1.6
        half_width = radius * 1.1
        corners = [
            direction * half_length + perpendicular * half_width,
            direction * half_length - perpendicular * half_width,
            -direction * half_length - perpendicular * half_width,
            -direction * half_length + perpendicular * half_width,
        ]
        points = [(screen_pos + corner) for corner in corners]
        pygame.draw.polygon(surface, color, [(p.x, p.y) for p in points])
        pygame.draw.polygon(surface, (90, 65, 40), [(p.x, p.y) for p in points], 2)

    elif element == "rage":
        # Dagger: a narrow blade shape with a small crossguard.
        tip = screen_pos + direction * radius * 2.4
        blade_back_left = screen_pos - perpendicular * radius * 0.5
        blade_back_right = screen_pos + perpendicular * radius * 0.5
        pygame.draw.polygon(
            surface, color,
            [(tip.x, tip.y), (blade_back_left.x, blade_back_left.y), (blade_back_right.x, blade_back_right.y)],
        )
        guard_a = screen_pos - direction * radius * 0.3 - perpendicular * radius * 1.1
        guard_b = screen_pos - direction * radius * 0.3 + perpendicular * radius * 1.1
        pygame.draw.line(surface, (120, 100, 80), (guard_a.x, guard_a.y), (guard_b.x, guard_b.y), 2)

    elif element == "animalia":
        # Arrow: a shaft with a triangular head and small fletching.
        tip = screen_pos + direction * radius * 2.2
        tail = screen_pos - direction * radius * 1.6
        pygame.draw.line(surface, (150, 110, 60), (tail.x, tail.y), (tip.x, tip.y), 3)

        head_left = tip - direction * radius * 1.1 - perpendicular * radius * 0.7
        head_right = tip - direction * radius * 1.1 + perpendicular * radius * 0.7
        pygame.draw.polygon(
            surface, color,
            [(tip.x, tip.y), (head_left.x, head_left.y), (head_right.x, head_right.y)],
        )

        fletch_left = tail + perpendicular * radius * 0.6
        fletch_right = tail - perpendicular * radius * 0.6
        pygame.draw.line(surface, (200, 200, 200), (tail.x, tail.y), (fletch_left.x, fletch_left.y), 2)
        pygame.draw.line(surface, (200, 200, 200), (tail.x, tail.y), (fletch_right.x, fletch_right.y), 2)

    elif element == "music":
        # Sound Wave: concentric arcs rippling outward, like a beat pulse.
        for ring in range(3):
            ring_radius = radius * (0.6 + ring * 0.5)
            arc_rect = pygame.Rect(0, 0, ring_radius * 2, ring_radius * 2)
            arc_rect.center = (screen_pos.x, screen_pos.y)
            start_angle = math.atan2(-direction.y, direction.x) - 0.9
            end_angle = math.atan2(-direction.y, direction.x) + 0.9
            pygame.draw.arc(surface, color, arc_rect, start_angle, end_angle, 2)
        pygame.draw.circle(surface, (255, 220, 250), screen_pos, max(2, int(radius * 0.4)))

    elif element == "wind":
        # Slipstream Blast: a trio of clean white slash marks streaking
        # behind the projectile, alternating angle, fading with distance.
        for slash in range(3):
            offset = slash * radius * 0.9
            center = screen_pos - direction * offset
            slash_dir = direction.rotate(35) if slash % 2 == 0 else direction.rotate(-35)
            half_length = radius * (0.9 - slash * 0.15)
            start = center - slash_dir * half_length
            end = center + slash_dir * half_length
            fade = max(90, 255 - slash * 70)
            pygame.draw.line(
                surface, (fade, fade, fade),
                (start.x, start.y), (end.x, end.y), 3,
            )

    else:
        pygame.draw.circle(surface, color, screen_pos, radius)


def draw_symphony_cone(symphony_state):
    owner = symphony_state["owner"]
    origin = world_to_screen(owner.pos)
    direction = symphony_state["direction"]
    facing_angle = math.degrees(math.atan2(-direction.y, direction.x))
    half_angle = MUSIC_ULT_CONE_HALF_ANGLE
    cone_range = MUSIC_ULT_RANGE

    # Translucent cone fill.
    cone_surface = pygame.Surface((cone_range * 2, cone_range * 2), pygame.SRCALPHA)
    center = (cone_range, cone_range)
    points = [center]
    steps = 20

    for step in range(steps + 1):
        angle = math.radians(facing_angle - half_angle + (2 * half_angle) * (step / steps))
        points.append((
            cone_range + math.cos(angle) * cone_range,
            cone_range - math.sin(angle) * cone_range,
        ))

    pygame.draw.polygon(cone_surface, (220, 100, 210, 45), points)
    screen.blit(cone_surface, (origin.x - cone_range, origin.y - cone_range))

    # Animated "sound wave" bands sweeping outward from the caster,
    # bounded by the cone's edges.
    t = pygame.time.get_ticks() / 1000

    for band in range(4):
        band_progress = ((t * 1.6 + band / 4) % 1.0)
        band_radius = band_progress * cone_range

        arc_points = []
        for step in range(steps + 1):
            angle = math.radians(facing_angle - half_angle + (2 * half_angle) * (step / steps))
            arc_points.append((
                origin.x + math.cos(angle) * band_radius,
                origin.y - math.sin(angle) * band_radius,
            ))

        if len(arc_points) > 1:
            fade = max(0, 255 - int(band_progress * 200))
            pygame.draw.lines(screen, (255, 200, 245), False, arc_points, 2)

    # Cone edge outlines.
    left_angle = math.radians(facing_angle - half_angle)
    right_angle = math.radians(facing_angle + half_angle)
    left_edge = (origin.x + math.cos(left_angle) * cone_range, origin.y - math.sin(left_angle) * cone_range)
    right_edge = (origin.x + math.cos(right_angle) * cone_range, origin.y - math.sin(right_angle) * cone_range)
    pygame.draw.line(screen, (255, 180, 240), (origin.x, origin.y), left_edge, 2)
    pygame.draw.line(screen, (255, 180, 240), (origin.x, origin.y), right_edge, 2)


def draw_fighter_weapon(screen_pos, fighter):
    """Draws each character's signature melee weapon in their hand -
    held at rest normally, and swung through an arc during a short
    attack (fighter.melee_swing_timer). Purely cosmetic - damage and
    timing are unaffected and still driven by player_short_attack()."""
    element = fighter.element
    swinging = fighter.melee_swing_timer > 0

    if swinging:
        swing_t = 1 - (fighter.melee_swing_timer / fighter.melee_swing_duration)
        forward = fighter.melee_swing_direction
        if forward.length() == 0:
            forward = Vector2(1, 0)
        forward = forward.normalize().rotate(-55 + 110 * swing_t)
    else:
        forward = fighter.facing_direction
        if forward.length() == 0:
            forward = Vector2(1, 0)
        forward = forward.normalize().rotate(-25)  # resting held-forward pose

    perp = Vector2(-forward.y, forward.x)
    hand = screen_pos + forward * 14
    metal = (215, 218, 225)
    dark_metal = (110, 112, 122)

    if element == "fire":
        tip = hand + forward * 34
        pygame.draw.line(screen, metal, hand, tip, 4)
        guard = hand + forward * 6
        pygame.draw.line(screen, (100, 75, 40), guard - perp * 7, guard + perp * 7, 3)
        if swinging:
            pygame.draw.circle(screen, (255, 150, 60), (int(tip.x), int(tip.y)), 5)

    elif element == "ice":
        head = hand + forward * 24
        pygame.draw.line(screen, (150, 110, 70), hand, head, 4)
        spike_a = head + forward.rotate(125) * 14
        spike_b = head + forward.rotate(-125) * 14
        pygame.draw.line(screen, (180, 230, 255), head, spike_a, 4)
        pygame.draw.line(screen, (180, 230, 255), head, spike_b, 4)

    elif element == "earth":
        knuckle = screen_pos + forward * 16
        poly = [
            knuckle + forward * dx + perp * dy
            for dx, dy in ((-7, -6), (7, -6), (7, 6), (-7, 6))
        ]
        pygame.draw.polygon(screen, (150, 120, 90), [(p.x, p.y) for p in poly])
        pygame.draw.polygon(screen, (90, 70, 50), [(p.x, p.y) for p in poly], 2)

    elif element == "nature":
        center = screen_pos + forward * 14

        if swinging:
            bloom = min(1.0, swing_t * 2)

            for petal in range(6):
                petal_dir = Vector2(1, 0).rotate(petal * 60)
                petal_tip = center + petal_dir * (6 + 14 * bloom)
                pygame.draw.line(screen, (255, 200, 230), (center.x, center.y), (petal_tip.x, petal_tip.y), 3)
                pygame.draw.circle(screen, (255, 220, 240), (int(petal_tip.x), int(petal_tip.y)), 3)

            pygame.draw.circle(screen, (255, 210, 90), (int(center.x), int(center.y)), 4)
        else:
            pygame.draw.circle(screen, (110, 190, 90), (int(center.x), int(center.y)), 4)
            leaf_tip = center + perp * 6
            pygame.draw.line(screen, (90, 170, 80), (center.x, center.y), (leaf_tip.x, leaf_tip.y), 2)

    elif element == "shadow":
        pole_end = hand + forward * 30
        pygame.draw.line(screen, (60, 55, 65), hand, pole_end, 3)
        blade_mid = pole_end + forward.rotate(45) * 16
        blade_end = pole_end + forward.rotate(95) * 12
        pygame.draw.lines(
            screen, (170, 120, 220), False,
            [(pole_end.x, pole_end.y), (blade_mid.x, blade_mid.y), (blade_end.x, blade_end.y)], 3,
        )

    elif element == "lightning":
        fist = screen_pos + forward * 16
        pygame.draw.circle(screen, (255, 250, 180), (int(fist.x), int(fist.y)), 6, 2)

        if swinging:
            for spark in range(3):
                spark_dir = forward.rotate(-40 + spark * 40)
                spark_end = fist + spark_dir * 12
                draw_zigzag(screen, fist, spark_end, (255, 240, 120), width=2, segments=3, jitter=4)

    elif element == "metal":
        tip = hand + forward * 30
        base_a = hand + perp * 6
        base_b = hand - perp * 6
        poly = [(base_a.x, base_a.y), (base_b.x, base_b.y), (tip.x, tip.y)]
        pygame.draw.polygon(screen, (200, 202, 210), poly)
        pygame.draw.polygon(screen, dark_metal, poly, 2)

    elif element == "rage":
        fist = screen_pos + forward * 15
        pygame.draw.circle(screen, (200, 60, 60), (int(fist.x), int(fist.y)), 6, 3)

        for bump in range(3):
            bump_pos = fist + perp * ((bump - 1) * 5) + forward * 4
            pygame.draw.circle(screen, (230, 90, 90), (int(bump_pos.x), int(bump_pos.y)), 2)

    elif element == "animalia":
        head_base = hand + forward * 32
        tip = hand + forward * 40
        pygame.draw.line(screen, (140, 100, 60), hand, head_base, 3)
        head_a = head_base + perp * 4
        head_b = head_base - perp * 4
        pygame.draw.polygon(
            screen, (200, 200, 205),
            [(head_a.x, head_a.y), (head_b.x, head_b.y), (tip.x, tip.y)],
        )

    elif element == "music":
        body = hand + forward * 18
        body_back = body - forward * 6
        pygame.draw.circle(screen, (150, 60, 140), (int(body.x), int(body.y)), 8)
        pygame.draw.circle(screen, (200, 100, 190), (int(body_back.x), int(body_back.y)), 6)
        neck_end = hand - forward * 6
        neck_start = body + forward * 6
        pygame.draw.line(screen, (90, 60, 50), (neck_start.x, neck_start.y), (neck_end.x, neck_end.y), 3)

    elif element == "wind":
        tip = hand + forward * 34
        pygame.draw.line(screen, (210, 235, 225), hand, tip, 3)
        pygame.draw.circle(screen, (230, 250, 245), (int(tip.x), int(tip.y)), 5, 2)

    elif element == "water":
        shaft_end = hand + forward * 24
        pygame.draw.line(screen, (90, 170, 230), hand, shaft_end, 3)

        for angle in (-25, 0, 25):
            prong_end = shaft_end + forward.rotate(angle) * 14
            pygame.draw.line(screen, (140, 200, 250), (shaft_end.x, shaft_end.y), (prong_end.x, prong_end.y), 3)

    elif element == "average":
        # Just a fist. Nothing special about it, on purpose.
        fist = screen_pos + forward * 14
        pygame.draw.circle(screen, (180, 150, 120), (int(fist.x), int(fist.y)), 6)

    elif element == "god":
        # An enormous glowing fist, because "1000 Punch Combo" demands one.
        fist = screen_pos + forward * 18
        glow_surface = pygame.Surface((60, 60), pygame.SRCALPHA)
        pygame.draw.circle(glow_surface, (255, 235, 180, 90), (30, 30), 26)
        screen.blit(glow_surface, (fist.x - 30, fist.y - 30))
        pygame.draw.circle(screen, (255, 225, 150), (int(fist.x), int(fist.y)), 11)
        pygame.draw.circle(screen, (255, 250, 220), (int(fist.x), int(fist.y)), 11, 2)


def draw_minimap():
    pygame.draw.rect(screen, (12, 15, 22), MINIMAP_RECT, border_radius=6)
    pygame.draw.rect(screen, (95, 100, 115), MINIMAP_RECT, 2, border_radius=6)

    arena_topleft = world_to_minimap(ARENA.topleft)
    arena_size = (ARENA.width * _MINIMAP_SX, ARENA.height * _MINIMAP_SY)
    pygame.draw.rect(screen, (70, 80, 95), (*arena_topleft, *arena_size), 1)

    for zone in TERRAIN_ZONES:
        center = world_to_minimap(zone["pos"])
        radius = max(3, zone["radius"] * _MINIMAP_SX)
        pygame.draw.circle(screen, TERRAIN_COLORS[zone["type"]], center, radius)

    for pocket in SHADOW_POCKETS:
        center = world_to_minimap(pocket["pos"])
        radius = max(2, pocket["radius"] * _MINIMAP_SX)
        pygame.draw.circle(screen, (70, 45, 110), center, radius)

    if not practice_mode:
        storm_center = world_to_minimap(ZONE_CENTER)
        pygame.draw.circle(
            screen,
            (110, 160, 220),
            storm_center,
            max(2, storm_radius * _MINIMAP_SX),
            1,
        )

    if game_state == "game":
        for fighter in living_fighters():
            if eternal_night is not None and fighter is eternal_night["owner"]:
                continue

            dot_color = (255, 255, 255) if fighter is player else ELEMENTS[fighter.element]["light_color"]
            pygame.draw.circle(screen, dot_color, world_to_minimap(fighter.pos), 4)

        view_topleft = world_to_minimap(camera)
        view_size = (VIEW_RECT.width * _MINIMAP_SX, VIEW_RECT.height * _MINIMAP_SY)
        pygame.draw.rect(screen, (255, 255, 255), (*view_topleft, *view_size), 1)


def draw_domination_points():
    for point in domination_points:
        screen_pos = world_to_screen(point["pos"])

        if point["owner"] == "blue":
            ring_color = (80, 150, 240)
        elif point["owner"] == "red":
            ring_color = (230, 80, 70)
        else:
            ring_color = (170, 170, 180)

        pygame.draw.circle(screen, ring_color, screen_pos, point["radius"], 3)

        # Fill wedge showing capture progress toward whichever side is
        # currently ahead - blue sweeps clockwise from the top, red
        # counter-clockwise, so a glance tells you who's winning it.
        fraction = abs(point["progress"]) / 100

        if fraction > 0:
            fill_color = (80, 150, 240, 70) if point["progress"] > 0 else (230, 80, 70, 70)
            wedge_surface = pygame.Surface((point["radius"] * 2, point["radius"] * 2), pygame.SRCALPHA)
            wedge_rect = pygame.Rect(0, 0, point["radius"] * 2, point["radius"] * 2)
            start_angle = math.pi / 2
            end_angle = start_angle + fraction * 2 * math.pi * (1 if point["progress"] > 0 else -1)
            points = [(point["radius"], point["radius"])]
            steps = max(2, int(fraction * 24))

            for step in range(steps + 1):
                t = step / steps
                angle = start_angle + (end_angle - start_angle) * t
                points.append((
                    point["radius"] + math.cos(angle) * point["radius"],
                    point["radius"] - math.sin(angle) * point["radius"],
                ))

            if len(points) > 2:
                pygame.draw.polygon(wedge_surface, fill_color, points)

            screen.blit(wedge_surface, (screen_pos.x - point["radius"], screen_pos.y - point["radius"]))

        label = big_font.render(point["name"], True, "white")
        screen.blit(label, label.get_rect(center=(screen_pos.x, screen_pos.y)))


def draw_domination_hud():
    bar = pygame.Rect(WIDTH // 2 - 220, 10, 440, 50)
    bar_surface = pygame.Surface((bar.width, bar.height), pygame.SRCALPHA)
    bar_surface.fill((10, 10, 16, 200))
    screen.blit(bar_surface, bar.topleft)
    pygame.draw.rect(screen, (90, 90, 105), bar, 2, border_radius=8)

    blue_text = big_font.render(str(domination_score["blue"]), True, (110, 170, 250))
    screen.blit(blue_text, blue_text.get_rect(center=(bar.left + 60, bar.centery)))

    red_text = big_font.render(str(domination_score["red"]), True, (250, 110, 100))
    screen.blit(red_text, red_text.get_rect(center=(bar.right - 60, bar.centery)))

    time_left = max(0, DOMINATION_TIME_LIMIT - domination_timer)
    minutes, seconds = divmod(int(time_left), 60)
    timer_text = font.render(f"{minutes}:{seconds:02d}", True, "white")
    screen.blit(timer_text, timer_text.get_rect(center=(bar.centerx, bar.centery)))

    owned_label = font.render("VS", True, (170, 170, 185))
    screen.blit(owned_label, owned_label.get_rect(center=(bar.centerx, bar.top + 12)))


def draw_match():
    arena_screen_rect = pygame.Rect(world_to_screen(ARENA.topleft), ARENA.size)
    pygame.draw.rect(screen, (45, 55, 70), arena_screen_rect, border_radius=12)

    draw_terrain()
    draw_shadow_pockets()
    draw_rage_aura()

    if domination_active:
        draw_domination_points()

    if not practice_mode:
        pygame.draw.circle(
            screen,
            (110, 160, 220),
            world_to_screen(ZONE_CENTER),
            int(storm_radius),
            3,
        )

    for trail in trails:
        trail.draw(screen, world_to_screen(trail.pos))

    if blizzard is not None:
        draw_ice_zone(
            world_to_screen(blizzard["owner"].pos),
            blizzard["radius"],
            blizzard["decor"],
            pygame.time.get_ticks() / 1000,
        )
        pygame.draw.circle(
            screen,
            (170, 240, 255),
            world_to_screen(blizzard["owner"].pos),
            blizzard["radius"],
            3,
        )

    if earthquake is not None:
        pygame.draw.circle(
            screen,
            (185, 135, 80),
            world_to_screen(earthquake["owner"].pos),
            earthquake["radius"],
            3,
        )

    if thunderstorm is not None:
        pygame.draw.circle(
            screen,
            (255, 235, 90),
            world_to_screen(thunderstorm["owner"].pos),
            thunderstorm["radius"],
            3,
        )

    if fire_zone is not None:
        fade = min(1, fire_zone["life"] / 0.8)
        draw_lava_zone(
            world_to_screen(fire_zone["pos"]),
            fire_zone["radius"] * fade,
            fire_zone["decor"],
            pygame.time.get_ticks() / 1000,
        )
        pygame.draw.circle(
            screen,
            (255, 140, 60),
            world_to_screen(fire_zone["pos"]),
            fire_zone["radius"] * fade,
            2,
        )

    if iron_maiden is not None and iron_maiden["target"].alive:
        pygame.draw.circle(
            screen,
            (210, 213, 222),
            world_to_screen(iron_maiden["target"].pos),
            iron_maiden["radius"],
            4,
        )

    if symphony is not None:
        draw_symphony_cone(symphony)

    if vine_whip is not None:
        pygame.draw.line(
            screen,
            (105, 220, 85),
            world_to_screen(player.pos),
            world_to_screen(vine_whip["target"]),
            5,
        )

    if vine_leech is not None:
        for target in opponents_of(vine_leech["owner"]):
            pygame.draw.line(
                screen,
                (105, 220, 85),
                world_to_screen(vine_leech["owner"].pos),
                world_to_screen(target.pos),
                4,
            )

    if water_beam_visual is not None:
        beam_start = world_to_screen(water_beam_visual["start"])
        beam_end = world_to_screen(water_beam_visual["end"])
        pygame.draw.line(screen, (150, 210, 250), beam_start, beam_end, 10)
        pygame.draw.line(screen, (220, 240, 255), beam_start, beam_end, 4)

    if tsunami is not None:
        wave_top = world_to_screen((tsunami["left_x"], ARENA.top)).y
        wave_bottom = world_to_screen((tsunami["left_x"], ARENA.bottom)).y

        for wall_x in (tsunami["left_x"], tsunami["right_x"]):
            screen_x = world_to_screen((wall_x, 0)).x
            wave_rect = pygame.Rect(screen_x - 18, wave_top, 36, wave_bottom - wave_top)
            wave_surface = pygame.Surface((wave_rect.width, wave_rect.height), pygame.SRCALPHA)
            wave_surface.fill((80, 160, 220, 160))
            screen.blit(wave_surface, wave_rect.topleft)
            pygame.draw.rect(screen, (200, 235, 255), wave_rect, 3)

    for arc in lightning_arcs:
        width = max(1, int(4 * arc["life"] / arc["max_life"]))
        draw_zigzag(
            screen,
            world_to_screen(arc["a"]),
            world_to_screen(arc["b"]),
            (190, 110, 255),
            width=width,
            segments=5,
            jitter=8,
        )

    for effect in effects:
        size = max(1, int(effect["radius"] * effect["life"] / effect["max_life"]))
        pygame.draw.circle(screen, effect["color"], world_to_screen(effect["pos"]), size, 3)

    for number in damage_numbers:
        alpha = max(0, min(255, int(255 * (number["life"] / number["max_life"]))))
        text_surface = font.render(number["text"], True, number["color"])
        text_surface.set_alpha(alpha)
        screen_pos = world_to_screen(number["pos"])
        screen.blit(text_surface, (screen_pos.x - text_surface.get_width() / 2, screen_pos.y))

    for projectile in projectiles:
        if projectile["element"] == "lightning":
            velocity = projectile["velocity"]
            trail_back = velocity.normalize() * 46 if velocity.length() > 0 else Vector2(0, 0)

            draw_zigzag(
                screen,
                world_to_screen(projectile["pos"] - trail_back),
                world_to_screen(projectile["pos"]),
                (190, 110, 255),
                width=3,
                segments=5,
                jitter=6,
            )
        else:
            draw_projectile_shape(
                screen,
                world_to_screen(projectile["pos"]),
                projectile["velocity"],
                projectile["element"],
                projectile["color"],
                projectile["radius"],
            )

    for fighter in living_fighters():
        data = ELEMENTS[fighter.element]
        color = data["color"]
        screen_pos = world_to_screen(fighter.pos)

        if fighter is player and burrow is not None:
            color = (95, 70, 45)

        if eternal_night is not None and fighter is eternal_night["owner"]:
            faded = pygame.Surface((44, 44), pygame.SRCALPHA)
            pygame.draw.circle(faded, (*color, 90), (22, 22), 18)
            pygame.draw.circle(faded, (255, 255, 255, 90), (22, 22), 18, 2)
            screen.blit(faded, (screen_pos.x - 22, screen_pos.y - 22))
        else:
            pygame.draw.circle(screen, color, screen_pos, 18)
            pygame.draw.circle(screen, "white", screen_pos, 18, 2)

            if not (fighter is player and in_shadow_pocket(player)):
                draw_fighter_weapon(screen_pos, fighter)

        draw_health_bar(screen_pos, fighter)

        if fighter is not player:
            draw_status_icons(screen_pos, fighter)

        label = "YOU" if fighter is player else fighter.name
        draw_text(label, screen_pos.x - 25, screen_pos.y + 25, data["light_color"])

        if fighter is player and in_shadow_pocket(player):
            draw_text(
                "HIDDEN",
                screen_pos.x - 25,
                screen_pos.y + 44,
                (190, 150, 240),
            )

    if monster is not None:
        monster_screen_pos = world_to_screen(monster["pos"])
        pygame.draw.circle(screen, (55, 95, 40), monster_screen_pos, 32)
        pygame.draw.circle(screen, (30, 55, 20), monster_screen_pos, 32, 3)
        pygame.draw.circle(screen, (210, 40, 30), (monster_screen_pos.x - 10, monster_screen_pos.y - 8), 4)
        pygame.draw.circle(screen, (210, 40, 30), (monster_screen_pos.x + 10, monster_screen_pos.y - 8), 4)
        draw_text("T-REX", monster_screen_pos.x - 22, monster_screen_pos.y + 34, (200, 230, 170))

        bar_width = 56
        bar_x = monster_screen_pos.x - bar_width / 2
        bar_y = monster_screen_pos.y - 48
        pygame.draw.rect(screen, (60, 20, 20), (bar_x, bar_y, bar_width, 7))
        pygame.draw.rect(
            screen,
            (190, 60, 50),
            (bar_x, bar_y, bar_width * max(0, monster["hp"]) / monster["max_hp"], 7),
        )

    if eternal_night is not None:
        overlay = pygame.Surface((VIEW_RECT.width, VIEW_RECT.height), pygame.SRCALPHA)
        overlay.fill((10, 5, 25, 120))
        screen.blit(overlay, VIEW_RECT.topleft)

    # --- HUD bar --------------------------------------------------------
    pygame.draw.rect(screen, (18, 21, 30), (0, 0, WIDTH, HUD_HEIGHT))

    player_data = ELEMENTS[player.element]

    draw_text(f"HP: {max(0, int(player.hp))}", 20, 14)

    if practice_mode:
        draw_text("PRACTICE MODE - dummy resets HP, no storm", 20, 38, (150, 220, 160))
    else:
        draw_text(f"FIGHTERS LEFT: {len(living_fighters())}", 20, 38)

        zone_text = (
            f"STORM IN: {max(0, storm_wait):.0f}s"
            if storm_wait > 0
            else "STORM SHRINKING"
        )

        draw_text(zone_text, 20, 62, (150, 190, 255))

    pygame.draw.rect(screen, (55, 55, 60), (480, 40, 230, 18))

    if player.element == "average":
        ascension_fraction = min(1.0, player.time_alive / AVERAGE_ASCENSION_TIME)
        pygame.draw.rect(
            screen, (200, 200, 210),
            (480, 40, int(230 * ascension_fraction), 18),
        )
        seconds_left = max(0, AVERAGE_ASCENSION_TIME - player.time_alive)
        draw_text(f"ASCENSION IN {seconds_left:.0f}s", 485, 39, "black")

    elif player.element == "god":
        draw_text("DIVINE - NO ULTIMATE", 485, 39, (150, 150, 150))

    else:
        pygame.draw.rect(
            screen,
            (255, 195, 45),
            (480, 40, int(230 * player.ult / 100), 18),
        )
        draw_text(player_data["ultimate_name"].upper(), 485, 39, "black")

    pygame.draw.rect(screen, (55, 55, 60), (480, 64, 230, 14))
    stamina_color = (90, 200, 120) if player.stamina > 25 else (210, 90, 70)
    pygame.draw.rect(
        screen,
        stamina_color,
        (480, 64, int(230 * player.stamina / player.MAX_STAMINA), 14),
    )
    draw_text("STAMINA", 485, 63, "black")

    draw_hud_status_icons(265, 45)

    draw_minimap()

    if domination_active:
        draw_domination_hud()

    feed_y = MINIMAP_RECT.bottom + 10

    for entry in kill_feed:
        alpha = max(0, min(255, int(255 * min(1, entry["life"] / 1.0))))
        feed_surface = font.render(entry["text"], True, (255, 220, 180))
        feed_surface.set_alpha(alpha)
        screen.blit(feed_surface, (WIDTH - feed_surface.get_width() - 12, feed_y))
        feed_y += 22

    if show_fps:
        fps_text = font.render(f"FPS: {int(clock.get_fps())}", True, (150, 255, 150))
        screen.blit(fps_text, (WIDTH - fps_text.get_width() - 12, HEIGHT - 50))

    bottom_bar = pygame.Surface((WIDTH, 26), pygame.SRCALPHA)
    bottom_bar.fill((0, 0, 0, 140))
    screen.blit(bottom_bar, (0, HEIGHT - 26))

    draw_text(
        "LMB: short | RMB: long | Both: ultimate | Shift: movement special | Esc: menu",
        145,
        HEIGHT - 22,
    )

    if game_over:
        label = big_font.render(winner_text, True, "white")
        screen.blit(label, label.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 40)))

        stats_lines = [
            f"Kills: {player.kills}",
            f"Damage dealt: {int(player.damage_dealt)}",
            f"Best hit streak: {player.best_hit_streak}",
        ]

        stats_y = HEIGHT // 2 + 10

        for line in stats_lines:
            stats_surface = font.render(line, True, (220, 220, 230))
            screen.blit(stats_surface, stats_surface.get_rect(center=(WIDTH // 2, stats_y)))
            stats_y += 24

        if story_active:
            prompt = font.render("Press SPACE or ENTER to continue", True, (255, 210, 120))
            screen.blit(prompt, prompt.get_rect(center=(WIDTH // 2, stats_y + 20)))

    if tutorial_active:
        draw_tutorial_overlay()


def draw_tutorial_overlay():
    if tutorial_step >= len(current_tutorial_steps):
        return

    step = current_tutorial_steps[tutorial_step]

    panel_width = 760
    lines = wrap_text(step["text"], panel_width - 40)
    panel_height = max(92, 34 + len(lines) * 24 + 14)

    panel = pygame.Rect(WIDTH // 2 - panel_width // 2, VIEW_RECT.top + 16, panel_width, panel_height)

    overlay = pygame.Surface((panel.width, panel.height), pygame.SRCALPHA)
    overlay.fill((10, 12, 20, 220))
    screen.blit(overlay, panel.topleft)
    pygame.draw.rect(screen, (255, 210, 120), panel, 2, border_radius=10)

    draw_text(
        f"TUTORIAL - STEP {tutorial_step + 1}/{len(current_tutorial_steps)}",
        panel.x + 20,
        panel.y + 10,
        (255, 210, 120),
    )

    y = panel.y + 34

    for line in lines:
        draw_text(line, panel.x + 20, y)
        y += 24


running = True
refresh_active_joystick()

while running:
    dt = clock.tick(60) / 1000

    update_music("game" if game_state == "game" else "menu")

    secret_toast_timer = max(0, secret_toast_timer - dt)

    if game_state == "story_cutscene" and story_cutscene_beats:
        current_beat = story_cutscene_beats[min(story_cutscene_index, len(story_cutscene_beats) - 1)]
        current_beat_text = current_beat.get("text", "")

        if story_cutscene_reveal < len(current_beat_text):
            story_cutscene_reveal = min(
                len(current_beat_text),
                story_cutscene_reveal + story.STORY_TEXT_CHARS_PER_SEC * dt,
            )

    if input_mode == "controller" and active_controller is not None and game_state != "game":
        cursor_dx = controller_axis(ROLE_LEFTX)
        cursor_dy = controller_axis(ROLE_LEFTY)

        if cursor_dx or cursor_dy:
            current = pygame.mouse.get_pos()
            new_x = max(0, min(WIDTH - 1, current[0] + cursor_dx * CONTROLLER_CURSOR_SPEED * dt))
            new_y = max(0, min(HEIGHT - 1, current[1] + cursor_dy * CONTROLLER_CURSOR_SPEED * dt))
            pygame.mouse.set_pos((int(new_x), int(new_y)))

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        if event.type in (
            pygame.CONTROLLERDEVICEADDED, pygame.CONTROLLERDEVICEREMOVED,
            pygame.JOYDEVICEADDED, pygame.JOYDEVICEREMOVED,
        ):
            active_controller = None
            controller_backend = None
            refresh_active_joystick()

        if input_mode == "controller":
            pressed_role = None

            if event.type == pygame.CONTROLLERBUTTONDOWN and controller_backend == "mapped":
                pressed_role = MAPPED_BUTTON_REVERSE.get(event.button)
            elif event.type == pygame.JOYBUTTONDOWN and controller_backend == "raw":
                pressed_role = RAW_BUTTON_REVERSE.get(event.button)

            if pressed_role == ROLE_LEFTSHOULDER:
                pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_LSHIFT, mod=0, unicode=""))
            elif pressed_role == ROLE_START:
                pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0, unicode=""))
            elif pressed_role == ROLE_A and game_state != "game":
                # Confirm/click, for every menu screen - see the virtual
                # cursor block below for how the click position is set.
                pygame.event.post(pygame.event.Event(
                    pygame.MOUSEBUTTONDOWN, pos=pygame.mouse.get_pos(), button=1,
                ))
            elif pressed_role == ROLE_A and game_state == "game" and game_over:
                pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE, mod=0, unicode=""))
            elif pressed_role == ROLE_B and game_state != "game":
                # Universal "back" - every hub/menu screen uses the same
                # fixed back_button rect, so this works everywhere at once.
                pygame.event.post(pygame.event.Event(
                    pygame.MOUSEBUTTONDOWN, pos=back_button.center, button=1,
                ))

        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            if game_state in (
                "game",
                "character_select",
                "opponent_select",
                "map_select",
                "encyclopedia",
                "how_to_play",
                "how_to_play_hub",
                "tutorial_select",
                "settings",
                "shop",
                "account_hub",
                "account_login",
                "account_register",
                "game_modes",
                "story_hub",
            ):
                game_state = "menu"
                tutorial_active = False
                story_active = False
                story_current_mission = None

        if game_state == "menu":
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if MENU_TITLE_RECT.collidepoint(event.pos) and not secret_progress.get("resonance"):
                    now = time.time()
                    secret_menu_click_times = [t for t in secret_menu_click_times if now - t < 4]
                    secret_menu_click_times.append(now)

                    if len(secret_menu_click_times) >= 7:
                        award_secret_fragment("resonance")
                        secret_menu_click_times = []

                if menu_buttons["play"].collidepoint(event.pos):
                    game_state = "game_modes"
                elif menu_buttons["characters"].collidepoint(event.pos):
                    game_state = "encyclopedia"
                elif menu_buttons["shop"].collidepoint(event.pos):
                    game_state = "shop"
                elif ACCOUNT_CORNER_BUTTON.collidepoint(event.pos):
                    account_error = ""
                    game_state = "account_hub"
                elif menu_buttons["settings"].collidepoint(event.pos):
                    game_state = "settings"
                elif menu_buttons["quit"].collidepoint(event.pos):
                    running = False
            continue

        if game_state == "game_modes":
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if GAME_MODE_BUTTONS["quick_match"].collidepoint(event.pos):
                    practice_mode = False
                    tutorial_active = False
                    pending_domination = False
                    character_select_scroll = 0
                    character_select_return_state = "game_modes"
                    game_state = "character_select"
                elif GAME_MODE_BUTTONS["domination"].collidepoint(event.pos):
                    practice_mode = False
                    tutorial_active = False
                    pending_domination = True
                    character_select_scroll = 0
                    character_select_return_state = "game_modes"
                    game_state = "character_select"
                elif GAME_MODE_BUTTONS["story_mode"].collidepoint(event.pos):
                    game_state = "story_hub"
                elif GAME_MODE_BUTTONS["how_to_play"].collidepoint(event.pos):
                    game_state = "how_to_play_hub"
                elif back_button.collidepoint(event.pos):
                    game_state = "menu"
            continue

        if game_state == "story_hub":
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if STORY_HUB_CONTINUE_BUTTON.collidepoint(event.pos):
                    next_index = story_progress % len(story.STORY_MISSIONS)
                    begin_story_mission(story.STORY_MISSIONS[next_index])
                elif back_button.collidepoint(event.pos):
                    game_state = "game_modes"
                else:
                    for index, element in enumerate(story.STORY_MISSIONS):
                        if index <= story_progress and story_hub_row_rect(index).collidepoint(event.pos):
                            begin_story_mission(element)
                            break
            continue

        if game_state == "story_cutscene":
            advance_requested = False

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                advance_requested = True
            elif event.type == pygame.KEYDOWN and event.key in (
                pygame.K_SPACE, pygame.K_RETURN, pygame.K_KP_ENTER,
            ):
                advance_requested = True
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                # Skip the whole cutscene straight to whatever it leads to.
                story_cutscene_reveal = 999999
                story_cutscene_index = len(story_cutscene_beats) - 1
                advance_requested = True

            if advance_requested and story_cutscene_beats:
                current_beat = story_cutscene_beats[story_cutscene_index]
                current_beat_text = current_beat.get("text", "")

                if story_cutscene_reveal < len(current_beat_text):
                    # First press just finishes the typewriter reveal.
                    story_cutscene_reveal = len(current_beat_text)
                elif story_cutscene_index + 1 < len(story_cutscene_beats):
                    story_cutscene_index += 1
                    story_cutscene_reveal = 0.0
                else:
                    advance_story_cutscene()
            continue

        if game_state == "shop":
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if account_username is None and ACCOUNT_LOGIN_BUTTON.collidepoint(event.pos):
                    account_error = ""
                    game_state = "account_hub"
                elif back_button.collidepoint(event.pos):
                    game_state = "menu"
            continue

        if game_state == "settings":
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if AUDIO_ENABLED and music_toggle_button.collidepoint(event.pos):
                    set_music_enabled(not music_enabled)
                elif AUDIO_ENABLED and menu_track_button.collidepoint(event.pos):
                    cycle_menu_track()
                elif AUDIO_ENABLED and game_track_button.collidepoint(event.pos):
                    cycle_game_track()
                elif dummy_behavior_button.collidepoint(event.pos):
                    current_index = TUTORIAL_BOT_BEHAVIORS.index(tutorial_bot_behavior)
                    tutorial_bot_behavior = TUTORIAL_BOT_BEHAVIORS[
                        (current_index + 1) % len(TUTORIAL_BOT_BEHAVIORS)
                    ]
                elif fps_toggle_button.collidepoint(event.pos):
                    show_fps = not show_fps

                    if show_fps and npc_difficulty == 9 and not secret_progress.get("extremes"):
                        award_secret_fragment("extremes")
                elif input_mode_button.collidepoint(event.pos):
                    current_index = INPUT_MODES.index(input_mode)
                    input_mode = INPUT_MODES[(current_index + 1) % len(INPUT_MODES)]
                elif DIFFICULTY_MINUS_BUTTON.collidepoint(event.pos):
                    npc_difficulty = max(1, npc_difficulty - 1)
                elif DIFFICULTY_PLUS_BUTTON.collidepoint(event.pos):
                    npc_difficulty = min(9, npc_difficulty + 1)

                    if show_fps and npc_difficulty == 9 and not secret_progress.get("extremes"):
                        award_secret_fragment("extremes")
                elif back_button.collidepoint(event.pos):
                    game_state = "menu"
            continue

        if game_state == "account_hub":
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if account_username is None:
                    if ACCOUNT_LOGIN_BUTTON.collidepoint(event.pos):
                        account_error = ""
                        account_field_username = ""
                        account_field_password = ""
                        account_active_field = "username"
                        account_show_password = False
                        game_state = "account_login"
                    elif ACCOUNT_REGISTER_BUTTON.collidepoint(event.pos):
                        account_error = ""
                        account_field_username = ""
                        account_field_password = ""
                        account_active_field = "username"
                        account_show_password = False
                        game_state = "account_register"
                    elif back_button.collidepoint(event.pos):
                        game_state = "menu"
                else:
                    if ACCOUNT_LOGOUT_BUTTON.collidepoint(event.pos):
                        account_username = None
                        account_stats = None
                        switch_account_progress(None)
                    elif ACCOUNT_DELETE_BUTTON.collidepoint(event.pos):
                        account_error = ""
                        account_delete_password = ""
                        account_delete_show_password = False
                        game_state = "account_delete_confirm"
                    elif account_stats.get("is_admin") and ACCOUNT_ADMIN_PANEL_BUTTON.collidepoint(event.pos):
                        admin_panel_error = ""
                        admin_password_field = ""
                        admin_password_show = False
                        game_state = "admin_password_confirm"
                    elif back_button.collidepoint(event.pos):
                        game_state = "menu"
            continue

        if game_state in ("account_login", "account_register"):
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if ACCOUNT_USERNAME_FIELD.collidepoint(event.pos):
                    account_active_field = "username"
                elif ACCOUNT_PASSWORD_FIELD.collidepoint(event.pos):
                    account_active_field = "password"
                elif ACCOUNT_SHOW_PASSWORD_BUTTON.collidepoint(event.pos):
                    account_show_password = not account_show_password
                elif ACCOUNT_SUBMIT_BUTTON.collidepoint(event.pos):
                    account_error = "Working..."

                    if game_state == "account_login":
                        success, result = account.login(account_field_username, account_field_password)
                    else:
                        success, result = account.register(account_field_username, account_field_password)

                    if success:
                        account_username = result["username"]
                        account_stats = result
                        account_error = ""
                        game_state = "account_hub"
                        switch_account_progress(account_username)
                    else:
                        account_error = result
                elif back_button.collidepoint(event.pos):
                    game_state = "account_hub"

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_TAB:
                    account_active_field = (
                        "password" if account_active_field == "username" else "username"
                    )
                elif event.key == pygame.K_RETURN:
                    account_error = "Working..."

                    if game_state == "account_login":
                        success, result = account.login(account_field_username, account_field_password)
                    else:
                        success, result = account.register(account_field_username, account_field_password)

                    if success:
                        account_username = result["username"]
                        account_stats = result
                        account_error = ""
                        game_state = "account_hub"
                        switch_account_progress(account_username)
                    else:
                        account_error = result
                elif event.key == pygame.K_BACKSPACE:
                    if account_active_field == "username":
                        account_field_username = account_field_username[:-1]
                    else:
                        account_field_password = account_field_password[:-1]
                elif event.unicode and event.unicode.isprintable():
                    if account_active_field == "username":
                        if len(account_field_username) < 20:
                            account_field_username += event.unicode
                    else:
                        if len(account_field_password) < 32:
                            account_field_password += event.unicode
            continue

        if game_state == "account_delete_confirm":
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if ACCOUNT_DELETE_SHOW_PASSWORD_BUTTON.collidepoint(event.pos):
                    account_delete_show_password = not account_delete_show_password
                elif ACCOUNT_DELETE_CONFIRM_BUTTON.collidepoint(event.pos):
                    account_error = "Working..."
                    success, result = account.delete_account(account_username, account_delete_password)

                    if success:
                        account_username = None
                        account_stats = None
                        account_delete_password = ""
                        account_error = ""
                        game_state = "account_hub"
                        switch_account_progress(None)
                    else:
                        account_error = result
                elif ACCOUNT_DELETE_CANCEL_BUTTON.collidepoint(event.pos):
                    account_delete_password = ""
                    account_error = ""
                    game_state = "account_hub"
                elif back_button.collidepoint(event.pos):
                    account_delete_password = ""
                    account_error = ""
                    game_state = "account_hub"

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_RETURN:
                    account_error = "Working..."
                    success, result = account.delete_account(account_username, account_delete_password)

                    if success:
                        account_username = None
                        account_stats = None
                        account_delete_password = ""
                        account_error = ""
                        game_state = "account_hub"
                        switch_account_progress(None)
                    else:
                        account_error = result
                elif event.key == pygame.K_ESCAPE:
                    account_delete_password = ""
                    account_error = ""
                    game_state = "account_hub"
                elif event.key == pygame.K_BACKSPACE:
                    account_delete_password = account_delete_password[:-1]
                elif event.unicode and event.unicode.isprintable():
                    if len(account_delete_password) < 32:
                        account_delete_password += event.unicode
            continue

        if game_state == "admin_password_confirm":
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if ADMIN_PASSWORD_SHOW_BUTTON.collidepoint(event.pos):
                    admin_password_show = not admin_password_show
                elif ADMIN_PASSWORD_CONFIRM_BUTTON.collidepoint(event.pos):
                    admin_panel_error = "Working..."
                    success, result = account.admin_list_accounts(account_username, admin_password_field)

                    if success:
                        admin_accounts = result
                        admin_panel_error = ""
                        admin_panel_scroll = 0
                        admin_confirm_delete_username = None
                        game_state = "admin_panel"
                    else:
                        admin_panel_error = result
                elif ADMIN_PASSWORD_CANCEL_BUTTON.collidepoint(event.pos):
                    admin_password_field = ""
                    admin_panel_error = ""
                    game_state = "account_hub"
                elif back_button.collidepoint(event.pos):
                    admin_password_field = ""
                    admin_panel_error = ""
                    game_state = "account_hub"

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_RETURN:
                    admin_panel_error = "Working..."
                    success, result = account.admin_list_accounts(account_username, admin_password_field)

                    if success:
                        admin_accounts = result
                        admin_panel_error = ""
                        admin_panel_scroll = 0
                        admin_confirm_delete_username = None
                        game_state = "admin_panel"
                    else:
                        admin_panel_error = result
                elif event.key == pygame.K_ESCAPE:
                    admin_password_field = ""
                    admin_panel_error = ""
                    game_state = "account_hub"
                elif event.key == pygame.K_BACKSPACE:
                    admin_password_field = admin_password_field[:-1]
                elif event.unicode and event.unicode.isprintable():
                    if len(admin_password_field) < 32:
                        admin_password_field += event.unicode
            continue

        if game_state == "admin_panel":
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if back_button.collidepoint(event.pos):
                    admin_confirm_delete_username = None
                    game_state = "account_hub"
                else:
                    for index, entry in enumerate(admin_accounts):
                        row_rect, delete_button = admin_panel_row_rects(index)

                        if not delete_button.collidepoint(event.pos) or entry.get("is_admin"):
                            continue

                        if admin_confirm_delete_username == entry["username"]:
                            # Second click on the same row - actually delete.
                            success, result = account.admin_delete_account(
                                account_username, admin_password_field, entry["username"],
                            )

                            if success:
                                admin_accounts = [a for a in admin_accounts if a["username"] != entry["username"]]
                                admin_panel_error = ""
                            else:
                                admin_panel_error = result

                            admin_confirm_delete_username = None
                        else:
                            # First click - arm the confirmation for this row.
                            admin_confirm_delete_username = entry["username"]

                        break

            elif event.type == pygame.MOUSEWHEEL:
                admin_panel_scroll = max(
                    0, min(admin_panel_max_scroll(), admin_panel_scroll - event.y * 30),
                )
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                admin_confirm_delete_username = None
                game_state = "account_hub"
            continue

        if game_state == "how_to_play_hub":
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if HUB_BUTTONS["controls"].collidepoint(event.pos):
                    game_state = "how_to_play"
                    how_to_play_scroll = 0
                elif HUB_BUTTONS["tutorials"].collidepoint(event.pos):
                    game_state = "tutorial_select"
                elif HUB_BUTTONS["practice"].collidepoint(event.pos):
                    practice_mode = True
                    tutorial_active = False
                    pending_domination = False
                    character_select_scroll = 0
                    character_select_return_state = "how_to_play_hub"
                    game_state = "character_select"
                elif back_button.collidepoint(event.pos):
                    game_state = "game_modes"
            continue

        if game_state == "tutorial_select":
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for element, button in tutorial_select_buttons.items():
                    if button.collidepoint(event.pos):
                        start_tutorial(element)
                        game_state = "game"

                if back_button.collidepoint(event.pos):
                    game_state = "how_to_play_hub"
            continue

        if game_state == "encyclopedia":
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for element, button in encyclopedia_list_buttons.items():
                    if button.collidepoint(event.pos):
                        encyclopedia_selected = element

                        if not secret_progress.get("old_rivals"):
                            secret_last_encyclopedia_views.append(element)
                            secret_last_encyclopedia_views = secret_last_encyclopedia_views[-2:]

                            if secret_last_encyclopedia_views == ["fire", "water"]:
                                award_secret_fragment("old_rivals")

                if back_button.collidepoint(event.pos):
                    game_state = "menu"
            continue

        if game_state == "how_to_play":
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if back_button.collidepoint(event.pos):
                    game_state = "how_to_play_hub"

            if event.type == pygame.MOUSEWHEEL:
                how_to_play_scroll -= event.y * 30
                how_to_play_scroll = max(
                    0, min(how_to_play_max_scroll(), how_to_play_scroll)
                )
            continue

        if game_state == "character_select":
            char_viewport = pygame.Rect(
                0, CHAR_SELECT_TOP, WIDTH, CHAR_SELECT_BOTTOM - CHAR_SELECT_TOP
            )

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for element, base_button in element_buttons.items():
                    button = character_select_screen_rect(base_button)

                    if (
                        button.collidepoint(event.pos)
                        and char_viewport.collidepoint(event.pos)
                        and is_character_unlocked(element)
                    ):
                        selected_element = element

                        if practice_mode:
                            start_match(practice=True)
                            game_state = "game"
                        else:
                            game_state = "map_select"

                if is_average_god_unlocked():
                    ag_button = character_select_screen_rect(AVERAGE_GOD_BUTTON)
                    ag_flip_button = pygame.Rect(0, 0, 26, 26)
                    ag_flip_button.topright = (ag_button.right - 10, ag_button.top + 10)

                    if ag_flip_button.collidepoint(event.pos) and char_viewport.collidepoint(event.pos):
                        average_god_flipped = not average_god_flipped
                    elif ag_button.collidepoint(event.pos) and char_viewport.collidepoint(event.pos):
                        # Always starts as Average - God is only ever
                        # reached by surviving 2 minutes mid-match, never
                        # picked directly, whichever face is previewed.
                        selected_element = "average"

                        if practice_mode:
                            start_match(practice=True)
                            game_state = "game"
                        else:
                            game_state = "map_select"

                if back_button.collidepoint(event.pos):
                    game_state = character_select_return_state

            if event.type == pygame.MOUSEWHEEL:
                character_select_scroll -= event.y * 30
                character_select_scroll = max(
                    0, min(character_select_max_scroll(), character_select_scroll)
                )
            continue

        if game_state == "map_select":
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for index, button in map_select_buttons.items():
                    if button.collidepoint(event.pos):
                        selected_map_index = index

                        if pending_domination:
                            start_match(domination=True)
                            game_state = "game"
                        else:
                            game_state = "opponent_select"

                if map_random_button.collidepoint(event.pos):
                    selected_map_index = MAP_RANDOM_INDEX

                    if pending_domination:
                        start_match(domination=True)
                        game_state = "game"
                    else:
                        game_state = "opponent_select"

                if back_button.collidepoint(event.pos):
                    game_state = "character_select"
            continue

        if game_state == "opponent_select":
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for count, button in count_buttons.items():
                    if button.collidepoint(event.pos):
                        opponent_count = count
                        start_match()
                        game_state = "game"

                if back_button.collidepoint(event.pos):
                    game_state = "map_select"
            continue

        if event.type == pygame.KEYDOWN:
            if game_over and story_active and event.key in (pygame.K_SPACE, pygame.K_RETURN):
                resolve_story_match_result(player.alive)
                continue

            if event.key == pygame.K_r and not (game_over and story_active):
                if tutorial_active:
                    start_tutorial(tutorial_element)
                else:
                    start_match(practice=practice_mode)

            if event.key == pygame.K_LSHIFT:
                if player.element == "ice":
                    # Endless skating: Shift toggles the glide on/off.
                    # Turning OFF is never blocked by anything, so it's
                    # always possible to stop. Turning ON respects the
                    # usual small cooldown to prevent spam-toggling.
                    if getattr(player, "ice_skating", False):
                        player.ice_skating = False
                        player.cooldowns["special"] = 0.15

                        if tutorial_active:
                            tutorial_special_used = True
                    elif player.cooldowns["special"] <= 0:
                        player.ice_skating = True
                        player.ice_trail_timer = 0
                        player.cooldowns["special"] = 0

                        if tutorial_active:
                            tutorial_special_used = True

                elif player.element == "animalia":
                    # Natural Taxi: same guaranteed-stoppable toggle as Ice.
                    if bear_ride is not None:
                        bear_ride = None
                        player.cooldowns["special"] = 0.15

                        if tutorial_active:
                            tutorial_special_used = True
                    elif player.cooldowns["special"] <= 0:
                        bear_ride = {"life": None, "slash_cooldown": 0, "trail_timer": 0}
                        add_effect(player.pos, (140, 100, 60), 40, 0.25)
                        player.cooldowns["special"] = 0

                        if tutorial_active:
                            tutorial_special_used = True

                elif player.cooldowns["special"] <= 0 and player.has_stamina(STAMINA_COST_SPECIAL):
                    player.spend_stamina(STAMINA_COST_SPECIAL)

                    if player.element == "fire":
                        old_pos = player.pos.copy()
                        player.dash(150, ARENA)

                        for number in range(5):
                            trails.append(
                                Trail(old_pos.lerp(player.pos, number / 4), "fire", team=player.team)
                            )

                        player.cooldowns["special"] = 2

                    elif player.element == "nature":
                        vine_whip = {
                            "life": 0.38,
                            "target": get_world_mouse(),
                        }

                        player.cooldowns["special"] = 2

                    elif player.element == "earth":
                        burrow = {
                            "life": 0.42,
                            "trail_timer": 0,
                        }

                        player.cooldowns["special"] = 2.5

                    elif player.element == "shadow":
                        player.dash(220, ARENA)
                        add_effect(player.pos, (170, 120, 220), 50, 0.3)
                        player.cooldowns["special"] = 1.8

                    elif player.element == "lightning":
                        old_pos = player.pos.copy()
                        player.dash(140, ARENA)

                        for number in range(5):
                            trails.append(
                                Trail(old_pos.lerp(player.pos, number / 4), "electric", team=player.team)
                            )

                        add_effect(player.pos, (255, 245, 150), 40, 0.25)
                        player.cooldowns["special"] = 0.65

                    elif player.element == "metal":
                        hover = {"life": 1.3, "trail_timer": 0}
                        player.cooldowns["special"] = 3.2

                    elif player.element == "rage":
                        adrenaline = {"life": 3, "trail_timer": 0}
                        add_effect(player.pos, (255, 90, 70), 55, 0.3)
                        player.cooldowns["special"] = 4

                    elif player.element == "water":
                        player.dash(160, ARENA)
                        add_effect(player.pos, (90, 170, 230), 45, 0.3)
                        player.cooldowns["special"] = 2

                    elif player.element == "music":
                        old_pos = player.pos.copy()
                        player.dash(180, ARENA)

                        for number in range(5):
                            trails.append(
                                Trail(old_pos.lerp(player.pos, number / 4), "music", team=player.team)
                            )

                        add_effect(player.pos, (220, 100, 210), 45, 0.25)
                        player.cooldowns["special"] = 1.5

                    elif player.element == "wind":
                        player.dash(220, ARENA)
                        add_effect(player.pos, (200, 235, 225), 55, 0.3)

                        for other in bots:
                            if other.alive and other.pos.distance_to(player.pos) < 90:
                                gust_direction = other.pos - player.pos

                                if gust_direction.length() > 0:
                                    other.pos += gust_direction.normalize() * 60
                                    other.keep_in_arena(ARENA)

                        player.cooldowns["special"] = 1.6

                    elif player.element == "average":
                        # Roly Poly - short, slow, a little undignified.
                        player.dash(90, ARENA)
                        add_effect(player.pos, (170, 170, 170), 30, 0.3)
                        player.cooldowns["special"] = 2.6

                    elif player.element == "god":
                        # Flight - the longest, fastest dash in the game.
                        player.dash(280, ARENA)
                        add_effect(player.pos, (255, 235, 180), 60, 0.35)
                        player.cooldowns["special"] = 1.4

                    if tutorial_active:
                        tutorial_special_used = True

            if event.key == pygame.K_SPACE and tutorial_active:
                tutorial_advance_pressed = True

    if game_state == "how_to_play":
        keys = pygame.key.get_pressed()

        if keys[pygame.K_DOWN] or keys[pygame.K_s]:
            how_to_play_scroll += 500 * dt
        if keys[pygame.K_UP] or keys[pygame.K_w]:
            how_to_play_scroll -= 500 * dt

        how_to_play_scroll = max(
            0, min(how_to_play_max_scroll(), how_to_play_scroll)
        )

    if game_state == "character_select":
        keys = pygame.key.get_pressed()

        if keys[pygame.K_DOWN] or keys[pygame.K_s]:
            character_select_scroll += 500 * dt
        if keys[pygame.K_UP] or keys[pygame.K_w]:
            character_select_scroll -= 500 * dt

        character_select_scroll = max(
            0, min(character_select_max_scroll(), character_select_scroll)
        )

    if game_state == "game" and not game_over:
        for fighter in living_fighters():
            fighter.update(dt)

        if player.element == "nature":
            player.hp = min(player.max_hp, player.hp + 2 * dt)

        keys = pygame.key.get_pressed()
        movement = Vector2(
            keys[pygame.K_d] - keys[pygame.K_a],
            keys[pygame.K_s] - keys[pygame.K_w],
        )

        if input_mode == "controller" and active_controller is not None:
            stick = Vector2(
                controller_axis(ROLE_LEFTX),
                controller_axis(ROLE_LEFTY),
            )

            if stick.length() > 0:
                # The stick already comes in analog and normalized-ish;
                # movement below expects a direction, so this overrides
                # (rather than adds to) any keyboard input this frame.
                movement = stick

        if tutorial_active and movement.length() > 0:
            tutorial_moved = True

        if getattr(player, "water_beam_exhausted", False) and player.stamina >= 20:
            player.water_beam_exhausted = False

        speed_multiplier = (
            (1.25 if player_on_ice_trail() else 1)
            * terrain_speed_multiplier(player)
            * (1.9 if hover is not None else 1)
            * (1.5 if adrenaline is not None else 1)
            * (1.5 if bear_ride is not None else 1)
        )
        player.move(movement, dt, ARENA, speed_multiplier)

        if adrenaline is not None:
            adrenaline["trail_timer"] -= dt

            if adrenaline["trail_timer"] <= 0:
                adrenaline["trail_timer"] = 0.05
                add_effect(player.pos, (255, 90, 70), 22, 0.2)

        if player.element == "ice" and getattr(player, "ice_skating", False):
            if not player.has_stamina(STAMINA_DRAIN_CHANNEL_PER_SEC * dt):
                player.ice_skating = False
            else:
                player.spend_stamina(STAMINA_DRAIN_CHANNEL_PER_SEC * dt)
                player.ice_trail_timer -= dt

                player.move(player.last_move_direction, dt, ARENA, 2.25)

                if player.ice_trail_timer <= 0:
                    trails.append(Trail(player.pos, "ice", team=player.team))
                    player.ice_trail_timer = 0.08

        if player.element == "animalia" and bear_ride is not None:
            if not player.has_stamina(STAMINA_DRAIN_CHANNEL_PER_SEC * dt):
                bear_ride = None
            else:
                player.spend_stamina(STAMINA_DRAIN_CHANNEL_PER_SEC * dt)

        mouse = pygame.mouse.get_pressed()
        aim = get_world_mouse() - player.pos

        if input_mode == "controller" and active_controller is not None:
            right_stick = Vector2(
                controller_axis(ROLE_RIGHTX),
                controller_axis(ROLE_RIGHTY),
            )

            if right_stick.length() > 0:
                player.controller_aim_direction = right_stick
            elif not hasattr(player, "controller_aim_direction"):
                player.controller_aim_direction = Vector2(1, 0)

            # No world mouse position while aiming with a stick - just
            # point in the remembered aim direction instead.
            aim = player.controller_aim_direction

            short_down = controller_button(ROLE_A)
            long_down = controller_button(ROLE_X)
            mouse = (short_down, False, long_down)

        if aim.length() > 0:
            player.facing_direction = aim

        if player.element == "music" and not (mouse[0] and mouse[2]):
            # Releasing either button stops the channel immediately -
            # this runs unconditionally so it still fires even on frames
            # that fall into a completely different elif branch below.
            stop_music_channel(player)

        water_beam_visual = None

        if combat_input_locked:
            if not mouse[0] and not mouse[2]:
                combat_input_locked = False

        elif mouse[0] and mouse[2] and player.element == "music":
            if not in_shadow_pocket(player) and player.ult > 0:
                update_music_channel(player, aim, dt)

                if tutorial_active:
                    tutorial_ultimate_used = True

        elif mouse[0] and mouse[2] and player.element in ("average", "god"):
            pass  # no ultimate to trigger here - see the HUD for what's shown instead

        elif mouse[0] and mouse[2]:
            if (
                player.ult >= 100
                and player.cooldowns["ultimate"] <= 0
                and player.has_stamina(STAMINA_COST_ULTIMATE)
                and ultimate_lock_timer <= 0
            ):
                trigger_ultimate(player)
                player.cooldowns["ultimate"] = 0.8

                if tutorial_active:
                    tutorial_ultimate_used = True

        elif mouse[0] and player.cooldowns["short"] <= 0:
            player_short_attack(aim)
            player.cooldowns["short"] = 0.38

            if tutorial_active:
                tutorial_short_used = True

        elif (
            player.element == "water"
            and mouse[2]
            and not in_shadow_pocket(player)
            and not getattr(player, "water_beam_exhausted", False)
            and player.stamina > 0
        ):
            # Water Beam: a continuous channel rather than a discrete shot -
            # no cooldown gate, it just deals tick damage every frame RMB
            # is held, to the first living target the beam corridor hits.
            player.spend_stamina(STAMINA_DRAIN_CHANNEL_PER_SEC * dt)

            if player.stamina <= 0:
                player.water_beam_exhausted = True

            beam_dir = aim.normalize() if aim.length() > 0 else Vector2(1, 0)
            beam_target = None
            best_projection = WATER_BEAM_RANGE

            for candidate in opponents_of(player):
                if in_shadow_pocket(candidate):
                    continue

                to_candidate = candidate.pos - player.pos
                projection = to_candidate.dot(beam_dir)

                if 0 <= projection <= best_projection:
                    perpendicular = (to_candidate - beam_dir * projection).length()

                    if perpendicular < WATER_BEAM_WIDTH:
                        best_projection = projection
                        beam_target = candidate

            beam_end = player.pos + beam_dir * best_projection

            if beam_target is not None:
                beam_target.damage(WATER_BEAM_DPS * dt * owner_damage_multiplier(player))
                beam_target.soak(1.5)
                player.ult = min(100, player.ult + 9 * dt)

            water_beam_visual = {"start": player.pos.copy(), "end": beam_end}

            if tutorial_active:
                tutorial_long_used = True

        elif mouse[2] and player.cooldowns["long"] <= 0:
            if player.element == "nature":
                for angle in (-12, 0, 12):
                    shoot_projectile(player, aim.rotate(angle))
            elif player.element == "metal":
                for angle in (-24, -12, 0, 12, 24):
                    shoot_projectile(player, aim.rotate(angle), life=0.85)
            elif player.element == "rage":
                for angle in (-6, 6):
                    shoot_projectile(player, aim.rotate(angle))
            else:
                shoot_projectile(player, aim)

            player.cooldowns["long"] = 0.34

            if tutorial_active:
                tutorial_long_used = True

        for bot in bots:
            if bot.alive and bot.stun_timer <= 0:
                if not practice_mode:
                    update_bot_ai(bot, dt)
                elif tutorial_bot_behavior == "attack":
                    update_bot_ai(bot, dt)
                elif tutorial_bot_behavior == "move":
                    update_dummy_wander(bot, dt)

        update_projectiles(dt)
        update_trails(dt)
        update_effects(dt)
        update_damage_numbers(dt)
        update_kill_feed(dt)
        update_screen_shake(dt)
        update_specials(dt)
        update_monster(dt)

        if ultimate_lock_timer > 0:
            ultimate_lock_timer -= dt

            if ultimate_lock_timer <= 0:
                ultimate_lock_timer = 0
                ultimate_lock_owner = None

        if not practice_mode:
            update_storm(dt)

        apply_terrain_effects(dt)
        resolve_fighter_collisions()
        update_camera()

        if practice_mode:
            for dummy in bots:
                dummy.hp = dummy.max_hp

            if player.hp <= 0:
                player.hp = player.max_hp
        elif domination_active:
            update_domination(dt)

            if game_over and account_username is not None and not match_result_recorded:
                match_result_recorded = True
                previous_level = (account_stats or {}).get("level", 1)
                success, result = account.record_result(account_username, winner_text.startswith("VICTORY"))

                if success:
                    account_stats = result

                    if result.get("level", 1) > previous_level:
                        play_sound(level_up_sound)
        else:
            alive = living_fighters()

            if not player.alive:
                game_over = True
                winner_text = "YOU WERE ELIMINATED"

            elif len(alive) == 1 and player.alive:
                game_over = True
                winner_text = "VICTORY!"

            if game_over and account_username is not None and not match_result_recorded:
                match_result_recorded = True
                previous_level = (account_stats or {}).get("level", 1)
                success, result = account.record_result(account_username, player.alive)

                if success:
                    account_stats = result

                    if result.get("level", 1) > previous_level:
                        play_sound(level_up_sound)

        if tutorial_active and tutorial_step < len(current_tutorial_steps):
            step_check = current_tutorial_steps[tutorial_step]["check"]

            if step_check is not None and step_check():
                tutorial_step += 1
                tutorial_advance_pressed = False

    screen.fill((20, 24, 35))

    if game_state == "menu":
        draw_menu()
    elif game_state == "game_modes":
        draw_game_modes()
    elif game_state == "story_hub":
        draw_story_hub()
    elif game_state == "story_cutscene":
        draw_story_cutscene()
    elif game_state == "encyclopedia":
        draw_encyclopedia()
    elif game_state == "settings":
        draw_settings()
    elif game_state == "shop":
        draw_shop()
    elif game_state == "account_hub":
        draw_account_hub()
    elif game_state == "account_login":
        draw_account_login()
    elif game_state == "account_register":
        draw_account_register()
    elif game_state == "account_delete_confirm":
        draw_account_delete_confirm()
    elif game_state == "admin_password_confirm":
        draw_admin_password_confirm()
    elif game_state == "admin_panel":
        draw_admin_panel()
    elif game_state == "how_to_play_hub":
        draw_how_to_play_hub()
    elif game_state == "tutorial_select":
        draw_tutorial_select()
    elif game_state == "how_to_play":
        draw_how_to_play()
    elif game_state == "character_select":
        draw_character_select()
    elif game_state == "map_select":
        draw_map_select()
    elif game_state == "opponent_select":
        draw_opponent_select()
    else:
        draw_match()

    draw_secret_toast()

    pygame.display.flip()

pygame.quit()
