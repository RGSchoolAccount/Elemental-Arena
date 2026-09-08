"""
Elemental Arena - Story Mode content.

Everything in this file is narrative DATA and small self-contained
helpers (mission order, dialogue beats, save/load of campaign
progress) - it has no dependency on main.py, pygame, or any live game
state. main.py imports this module and drives the actual cutscene
playback / duel-launching logic itself, since that part needs tight
access to the game loop's state (game_state, the player Fighter, etc).

Edit mission dialogue, add new missions, or rebalance the mission
order here without touching any game code.

Beat schema: each beat is a dict with either:
  - "title" + "subtitle": a chapter card (no portraits, no speaker)
  - "speaker" (None for narration, an element key, "fire", or the son's
    name lowercased) + "text": a normal dialogue line
Both kinds may optionally set "scene", which selects a background from
STORY_SCENE_BACKGROUNDS in main.py. A beat with no "scene" reuses
whatever scene the previous beat set, so it's only set on entering a
new location, not repeated every line.
"""

import json
import os


# --- Story Mode -------------------------------------------------------
#
# Fire's son, Ash, is taken by the Elemental Ninja Clan. Fire fights his
# way through the Clan in the same order the roster unlocks (skipping
# himself), with Water - the Clan's leader - as the final confrontation.

STORY_SON_NAME = "Ash"
# Mirrors main.py's CHARACTER_UNLOCK_LEVEL order (everything after Fire,
# who is always the story-mode protagonist). Kept as a plain literal here
# so story.py has no dependency on main.py.
STORY_MISSIONS = [
    "ice", "nature", "earth", "shadow", "lightning", "metal",
    "rage", "animalia", "music", "wind", "water",
]
STORY_SAVE_DIR = os.path.dirname(os.path.abspath(__file__))

STORY_CHAPTER_TITLES = {
    "ice": "Frozen Trail",
    "nature": "Thorns and Glass",
    "earth": "Under the Old Town",
    "shadow": "Where the Lights Don't Work",
    "lightning": "Static in the Storm Towers",
    "metal": "The Last Torch on the Floor",
    "rage": "The Fire That Won't Go Out",
    "animalia": "Eyes in the Treeline",
    "music": "A Song for No One",
    "wind": "Chasing the Unforecast Storm",
    "water": "The Tide Listens",
}


def _save_path_for(username):
    """Story progress is per-account, not per-install - each login
    (or nobody logged in at all) gets its own save file, so switching
    accounts doesn't show someone else's progress as your own."""
    safe_name = "".join(c for c in (username or "").lower() if c.isalnum() or c in ("-", "_"))
    safe_name = safe_name or "guest"
    return os.path.join(STORY_SAVE_DIR, f"story_progress_{safe_name}.json")


def load_story_progress(username=None):
    try:
        with open(_save_path_for(username), "r") as save_file:
            data = json.load(save_file)
            progress = int(data.get("mission_index", 0))
            return max(0, min(len(STORY_MISSIONS), progress))
    except (OSError, ValueError, TypeError):
        return 0


def save_story_progress(mission_index, username=None):
    try:
        with open(_save_path_for(username), "w") as save_file:
            json.dump({"mission_index": mission_index}, save_file)
    except OSError:
        pass


STORY_INTRO_BEATS = [
    {"title": "PROLOGUE", "subtitle": "The Forge Goes Quiet"},
    {"scene": "home", "speaker": None, "text": "Fire's forge, late at night. The hammering has stopped an hour ago, but the light's still on."},
    {"scene": "home", "speaker": "fire", "text": f"{STORY_SON_NAME}? I said five more minutes, not five more hours."},
    {"scene": "home", "speaker": None, "text": "No answer. Just the low hiss of a dying furnace, and a workshop door hanging open to the dark."},
    {"scene": "home", "speaker": "fire", "text": f"{STORY_SON_NAME}, this isn't funny anymore."},
    {"scene": "home", "speaker": None, "text": "It still isn't funny an hour later, when Fire finds the anvil - and what's pinned to it."},
    {"scene": "capture", "speaker": None, "text": "A scrap of black cloth. A single shard of ice, driven clean through the fabric and an inch into the steel."},
    {"scene": "capture", "speaker": "fire", "text": "'The Elemental Ninja Clan.'"},
    {"scene": "capture", "speaker": "fire", "text": "Never heard of them. Doesn't matter. They wanted my attention - they've got it."},
    {"scene": "capture", "speaker": None, "text": "No note. No demand. Just a shard of ice pointing, unmistakably, north."},
    {"scene": "capture", "speaker": "fire", "text": "One at a time, then. However many of you there are. I'm not stopping until I'm holding my son again."},
    {"scene": "capture", "speaker": None, "text": "The trail starts cold - literally. Ice territory, first light."},
]

STORY_MISSION_BEATS = {
    "ice": {
        "pre": [
            {"title": "CHAPTER 1", "subtitle": "Frozen Trail"},
            {"scene": "ice_ridge", "speaker": None, "text": "Frost creeps up the rock walls in patterns too neat to be weather. Someone is waiting at the top of the ridge, perfectly still."},
            {"scene": "ice_ridge", "speaker": "ice", "text": "A blacksmith, out here? You're further from your forge than you realize."},
            {"scene": "ice_ridge", "speaker": "fire", "text": f"You know exactly why I'm here. Where's {STORY_SON_NAME}?"},
            {"scene": "ice_ridge", "speaker": "ice", "text": "The Clan doesn't repeat its instructions to outsiders. And I don't repeat myself either."},
            {"scene": "ice_ridge", "speaker": "fire", "text": "Then we're both about to be disappointed."},
            {"scene": "ice_ridge", "speaker": "ice", "text": "We'll see. Let's skate."},
        ],
        "post": [
            {"scene": "ice_ridge", "speaker": "ice", "text": "...Fine! FINE. He's not with me - I'm just the first name on a very long list."},
            {"scene": "ice_ridge", "speaker": "fire", "text": "Whose list?"},
            {"scene": "ice_ridge", "speaker": "ice", "text": "Does it matter? You'll find out eventually. Everyone does."},
            {"scene": "ice_ridge", "speaker": "ice", "text": "They marched him through the greenhouse district. Ask for the one who talks to flowers - he won't shut up about it."},
            {"scene": "ice_ridge", "speaker": "fire", "text": "Then that's where I'm going. Thank you."},
            {"scene": "ice_ridge", "speaker": "ice", "text": "Don't thank me. I'd have told you nothing if you'd lost."},
        ],
    },
    "nature": {
        "pre": [
            {"title": "CHAPTER 2", "subtitle": "Thorns and Glass"},
            {"scene": "greenhouse", "speaker": None, "text": "Vines have swallowed the old greenhouse whole - glass panes long gone under a decade of green."},
            {"scene": "greenhouse", "speaker": "nature", "text": "Ice sent word you'd be coming. Said you hit like a forge accident."},
            {"scene": "greenhouse", "speaker": "fire", "text": "You've got my son's trail. I'd like it back. Please, this time."},
            {"scene": "greenhouse", "speaker": "nature", "text": "Manners. Cute. The vines don't give anything back for free, though - and neither do I."},
            {"scene": "greenhouse", "speaker": "fire", "text": "Then I suppose we're doing this the other way."},
            {"scene": "greenhouse", "speaker": "nature", "text": "Prove you're worth the clue. I'll try not to enjoy this too much."},
        ],
        "post": [
            {"scene": "greenhouse", "speaker": "nature", "text": "...Ha. You fight like something that's used to losing things it loves and hating every second of it."},
            {"scene": "greenhouse", "speaker": "fire", "text": "That's not a fight tip. That's a diagnosis."},
            {"scene": "greenhouse", "speaker": "nature", "text": "Free of charge, unlike the directions. He went down through the old mine shaft - the one still being dug by hand."},
            {"scene": "greenhouse", "speaker": "nature", "text": "Careful down there. Earth doesn't lose arguments, and he definitely won't lose to a stranger."},
            {"scene": "greenhouse", "speaker": "fire", "text": "Then I'll try not to be a stranger for long."},
        ],
    },
    "earth": {
        "pre": [
            {"title": "CHAPTER 3", "subtitle": "Under the Old Town"},
            {"scene": "mine", "speaker": None, "text": "The mine tunnels groan under their own weight, timber supports older than the town above them. Something huge shifts in the dark ahead."},
            {"scene": "mine", "speaker": "earth", "text": "You're loud, for a man sneaking into someone else's tunnel."},
            {"scene": "mine", "speaker": "fire", "text": "I'm not sneaking. I'm looking for my son, and you happen to be in the way."},
            {"scene": "mine", "speaker": "earth", "text": "Everyone's in someone's way down here eventually. That's what tunnels are for."},
            {"scene": "mine", "speaker": "fire", "text": "Is that a threat or a proverb?"},
            {"scene": "mine", "speaker": "earth", "text": "Ask again after. Come on, then - the mountain's not going anywhere, but you might."},
        ],
        "post": [
            {"scene": "mine", "speaker": "earth", "text": "Heh. Solid hits, for someone who spends his days hammering things that don't hit back."},
            {"scene": "mine", "speaker": "fire", "text": "Where is he."},
            {"scene": "mine", "speaker": "earth", "text": "Not down here. They only ever used my tunnels as a shortcut - didn't ask, either, if it makes you feel better."},
            {"scene": "mine", "speaker": "earth", "text": "Came out the other side near the old part of town, where the streetlights stopped working years ago and nobody bothered to ask why."},
            {"scene": "mine", "speaker": "fire", "text": "The Shadow district."},
            {"scene": "mine", "speaker": "earth", "text": "If you can even call it that anymore. Watch yourself down there - he doesn't fight fair, and he doesn't fight loud."},
        ],
    },
    "shadow": {
        "pre": [
            {"title": "CHAPTER 4", "subtitle": "Where the Lights Don't Work"},
            {"scene": "shadow_district", "speaker": None, "text": "No streetlights. No shadows that behave the way shadows should. Something is watching from all of them at once."},
            {"scene": "shadow_district", "speaker": "shadow", "text": "No one remembers my name. They'll remember yours even less, once I'm through with you."},
            {"scene": "shadow_district", "speaker": "fire", "text": f"I don't need your name. I need to know where {STORY_SON_NAME} is, and I'm not leaving until I do."},
            {"scene": "shadow_district", "speaker": "shadow", "text": "Then you'd better be able to hit what you can't see. Most people can't."},
            {"scene": "shadow_district", "speaker": "fire", "text": "I've never needed to see something to know it's there."},
            {"scene": "shadow_district", "speaker": "shadow", "text": "...Interesting answer. We'll test it."},
        ],
        "post": [
            {"scene": "shadow_district", "speaker": "shadow", "text": "...Impressive. Genuinely. Fine - he passed through here. Crying, at first. Angry, by the end."},
            {"scene": "shadow_district", "speaker": "fire", "text": "Angry's good. Angry means he hasn't given up."},
            {"scene": "shadow_district", "speaker": "shadow", "text": "Funny. She said the exact same thing when she heard."},
            {"scene": "shadow_district", "speaker": "fire", "text": "She?"},
            {"scene": "shadow_district", "speaker": "shadow", "text": "You'll meet her eventually, if you keep this up. They took the substation route out toward the storm towers. Lightning's territory now."},
            {"scene": "shadow_district", "speaker": "fire", "text": "Then that's where I'm headed."},
        ],
    },
    "lightning": {
        "pre": [
            {"title": "CHAPTER 5", "subtitle": "Static in the Storm Towers"},
            {"scene": "storm_towers", "speaker": None, "text": "The storm towers crackle overhead, the air thick enough to taste copper on your tongue before the first strike lands."},
            {"scene": "storm_towers", "speaker": "lightning", "text": "Three times before I was ten years old. After the fourth, you stop counting and start collecting."},
            {"scene": "storm_towers", "speaker": "fire", "text": "Collect this instead: where's my son?"},
            {"scene": "storm_towers", "speaker": "lightning", "text": "Cute line. Rehearsed it the whole walk over, did you?"},
            {"scene": "storm_towers", "speaker": "fire", "text": "Little bit, yeah."},
            {"scene": "storm_towers", "speaker": "lightning", "text": "Respect the effort. Let's see if you can back it up before the storm gets bored of watching."},
        ],
        "post": [
            {"scene": "storm_towers", "speaker": "lightning", "text": "Ha! GOOD. Better than good. He's not far now - they've got a welder holding the next checkpoint."},
            {"scene": "storm_towers", "speaker": "fire", "text": "A welder."},
            {"scene": "storm_towers", "speaker": "lightning", "text": "Careful with that one. He doesn't feel much of anything anymore, cold or otherwise. Might not feel guilty either. Might."},
            {"scene": "storm_towers", "speaker": "fire", "text": "Neither will I, if he's laid one finger on my son."},
            {"scene": "storm_towers", "speaker": "lightning", "text": "Didn't say he did. Said might not feel guilty. Different sentence. Go easy on him if you can - I mean that."},
        ],
    },
    "metal": {
        "pre": [
            {"title": "CHAPTER 6", "subtitle": "The Last Torch on the Floor"},
            {"scene": "factory", "speaker": None, "text": "A factory floor gone quiet, rows of dead machines, and one welding torch still lit somewhere in the dark ahead."},
            {"scene": "factory", "speaker": "metal", "text": "The blacksmith. Heard the forge fits in your fists now. Mine fits in my whole body - it never really left."},
            {"scene": "factory", "speaker": "fire", "text": "Then you understand exactly why I'm not turning around, whatever's waiting for me."},
            {"scene": "factory", "speaker": "metal", "text": "I do understand. Doesn't change anything I'm about to do."},
            {"scene": "factory", "speaker": "fire", "text": "Didn't expect it to."},
            {"scene": "factory", "speaker": "metal", "text": "Good. Come on, then. Let's not waste either of our nights pretending otherwise."},
        ],
        "post": [
            {"scene": "factory", "speaker": "metal", "text": "...Huh. Didn't expect that, either. He's fine, for what it's worth to you. Scared. Not hurt."},
            {"scene": "factory", "speaker": "fire", "text": "Scared, not hurt. I can work with scared, not hurt."},
            {"scene": "factory", "speaker": "metal", "text": "They've got him at the old fairgrounds now. Whoever's angriest in the Clan is running the door tonight - and he's always angry."},
            {"scene": "factory", "speaker": "fire", "text": "Sounds like we'll get along great, then."},
            {"scene": "factory", "speaker": "metal", "text": "You won't. Go anyway."},
        ],
    },
    "rage": {
        "pre": [
            {"title": "CHAPTER 7", "subtitle": "The Fire That Won't Go Out"},
            {"scene": "fairground", "speaker": None, "text": "The fairgrounds: rusted rides frozen mid-turn, and one bonfire in the center that's been burning far longer than any fire should."},
            {"scene": "fairground", "speaker": "rage", "text": "Nobody remembers what started this fight, mine or the Clan's. Doesn't matter anymore. It's not going to end quiet, either way."},
            {"scene": "fairground", "speaker": "fire", "text": "I don't want your fight. I want my son."},
            {"scene": "fairground", "speaker": "rage", "text": "Then you're already in the wrong place, because you're not leaving this fairground without one."},
            {"scene": "fairground", "speaker": "fire", "text": "Fine by me. I've got a fire of my own that hasn't gone out in eight days."},
            {"scene": "fairground", "speaker": "rage", "text": "Now THAT'S a line I respect."},
        ],
        "post": [
            {"scene": "fairground", "speaker": "rage", "text": "...Heh. Didn't think a blacksmith had it in him. Most people burn out before the third minute."},
            {"scene": "fairground", "speaker": "fire", "text": "Most people don't have what I've got waiting for them at the end of this."},
            {"scene": "fairground", "speaker": "rage", "text": "Fair. He's past the treeline now, with the animals. Wasn't my call to take him that far - for whatever that's worth to you."},
            {"scene": "fairground", "speaker": "fire", "text": "It's worth something. Not enough. But something."},
            {"scene": "fairground", "speaker": "rage", "text": "It'll have to do. Go get him."},
        ],
    },
    "animalia": {
        "pre": [
            {"title": "CHAPTER 8", "subtitle": "Eyes in the Treeline"},
            {"scene": "treeline", "speaker": None, "text": "The treeline swallows the fairground lights whole. Somewhere close, a lot of eyes are watching, and none of them blink first."},
            {"scene": "treeline", "speaker": "animalia", "text": "He's safe. Scared of the wolves, mostly - not of me. Kids can usually tell the difference, if you let them."},
            {"scene": "treeline", "speaker": "fire", "text": "Then step aside and let him tell me that himself."},
            {"scene": "treeline", "speaker": "animalia", "text": "Not my call to make, unfortunately. But I'll make you earn the chance to ask her."},
            {"scene": "treeline", "speaker": "fire", "text": "Her again. Everyone keeps saying 'her' like I'm supposed to already know."},
            {"scene": "treeline", "speaker": "animalia", "text": "You'll know soon enough. Everyone does, eventually. Ready?"},
        ],
        "post": [
            {"scene": "treeline", "speaker": "animalia", "text": "...Good. Really good. He's got your stubbornness - kept telling me the whole time that you'd come."},
            {"scene": "treeline", "speaker": "fire", "text": "He always was a stubborn kid. Wonder where he gets it."},
            {"scene": "treeline", "speaker": "animalia", "text": "There's a busker two streets over who knows exactly where they took him next. Ask nicely. Or don't - clearly that's not really your style."},
            {"scene": "treeline", "speaker": "fire", "text": "Tell him I said thank you. When I see him again, I mean."},
            {"scene": "treeline", "speaker": "animalia", "text": "I'll tell the wolves too. They liked him."},
        ],
    },
    "music": {
        "pre": [
            {"title": "CHAPTER 9", "subtitle": "A Song for No One"},
            {"scene": "street", "speaker": None, "text": "A street corner, well past midnight. One guitar plays itself under a flickering lamp, and nobody's stopped to listen but you."},
            {"scene": "street", "speaker": "music", "text": "Used to play for tips nobody threw. Funny how that changes once people don't have a choice but to listen."},
            {"scene": "street", "speaker": "fire", "text": "I don't want a show. I want directions, and I'm running out of patience for detours."},
            {"scene": "street", "speaker": "music", "text": "Everyone wants something, blacksmith. Question is whether you can keep the beat long enough to earn it."},
            {"scene": "street", "speaker": "fire", "text": "Try me."},
            {"scene": "street", "speaker": "music", "text": "Oh, I intend to."},
        ],
        "post": [
            {"scene": "street", "speaker": "music", "text": "...Not bad rhythm, for a hammer-and-anvil type. Didn't expect that from someone whose whole job is one note, over and over."},
            {"scene": "street", "speaker": "fire", "text": "You'd be surprised how much range a hammer actually has."},
            {"scene": "street", "speaker": "music", "text": "Fine. I'll play it straight, this once. He's up at the old airfield. Whoever's next moves fast - don't blink, don't breathe, don't slow down."},
            {"scene": "street", "speaker": "fire", "text": "I haven't blinked since this whole thing started."},
            {"scene": "street", "speaker": "music", "text": "Good. You'll need that. It gets stranger from here."},
        ],
    },
    "wind": {
        "pre": [
            {"title": "CHAPTER 10", "subtitle": "Chasing the Unforecast Storm"},
            {"scene": "airfield", "speaker": None, "text": "An abandoned airfield, wind screaming sideways across the cracked runway, loud enough to swallow footsteps."},
            {"scene": "airfield", "speaker": "wind", "text": "Chased a storm once that wasn't on any forecast anywhere. Never really landed since. You'll understand that feeling by the end of tonight."},
            {"scene": "airfield", "speaker": "fire", "text": "I just need to know where the last one is. Where she is."},
            {"scene": "airfield", "speaker": "wind", "text": "She. So you've finally figured out who's really running this whole thing."},
            {"scene": "airfield", "speaker": "fire", "text": "I've figured out I'm sick of hearing about her secondhand. Catch me up, or catch me if you can - your choice."},
            {"scene": "airfield", "speaker": "wind", "text": "Catch ME first, and I'll tell you exactly where to find her. Deal?"},
        ],
        "post": [
            {"scene": "airfield", "speaker": "wind", "text": "...Ha! Slower than the storm, but you hit a lot harder than it does. He's with her. At the coast."},
            {"scene": "airfield", "speaker": "fire", "text": "The coast. Finally."},
            {"scene": "airfield", "speaker": "wind", "text": "Be careful out there. Whatever she wants him for, it's not a ransom - she's never once asked you for anything."},
            {"scene": "airfield", "speaker": "fire", "text": "Then what does she want?"},
            {"scene": "airfield", "speaker": "wind", "text": "She doesn't listen to anyone but the tide. Ask her yourself. I think, deep down, she wants to be asked."},
        ],
    },
    "water": {
        "pre": [
            {"title": "FINAL CHAPTER", "subtitle": "The Tide Listens"},
            {"scene": "coast", "speaker": None, "text": "The coast. Storm-black water stretching out past where the eye can follow it, and one small figure standing very still on the sand."},
            {"scene": "coast", "speaker": "fire", "text": f"{STORY_SON_NAME}!"},
            {"scene": "coast", "speaker": "water", "text": "He's fine. He's been fine the entire time - which is more than I can say for you, judging by the state of you."},
            {"scene": "coast", "speaker": "fire", "text": "Then let him go. Right now. No more clues, no more tests, no more of your Clan standing in my way."},
            {"scene": "coast", "speaker": "water", "text": "I will. I only ever needed to know one thing: whether a father who once fell into his own forge and walked out without a scratch would do the same for his son."},
            {"scene": "coast", "speaker": "water", "text": "Consider it tested. Thoroughly."},
            {"scene": "coast", "speaker": "fire", "text": "You put my son through eight days of terror to run an experiment?"},
            {"scene": "coast", "speaker": "water", "text": "I put the entire Clan through it with you, one at a time - and every single one of them let you pass, in the end. That wasn't an accident."},
            {"scene": "coast", "speaker": "fire", "text": "Then what was it?"},
            {"scene": "coast", "speaker": "water", "text": "A question I needed answered. I won't be as generous as they were. Show me what's left after eight days of this. Show me all of it."},
        ],
        "post": [
            {"scene": "coast", "speaker": None, "text": "The tide pulls back, slow and final, and for the first time in eight days, the coast is quiet."},
            {"scene": "coast", "speaker": "water", "text": "...Good. That's all I needed to see."},
            {"scene": "coast", "speaker": "fire", "text": "Needed to see for what?"},
            {"scene": "coast", "speaker": "water", "text": "Later. Go to him first. He's waited long enough."},
            {"scene": "coast", "speaker": None, "text": f"{STORY_SON_NAME} breaks free and runs. Fire drops to one knee in the sand to catch him."},
            {"scene": "coast", "speaker": "fire", "text": "Are you hurt? Did any of them-"},
            {"scene": "coast", "speaker": STORY_SON_NAME.lower(), "text": "I'm okay, Dad. They were actually kind of nice about it, mostly. Can we please go home now?"},
            {"scene": "coast", "speaker": "fire", "text": "Yeah. Yeah, we're going home."},
            {"scene": "coast", "speaker": "water", "text": "Fire. For what it's worth - I am sorry for the eight days. I'm not sorry for the answer."},
            {"scene": "coast", "speaker": "fire", "text": "...Ask me again sometime. When I'm not still shaking."},
        ],
    },
}

STORY_FINALE_BEATS = [
    {"title": "EPILOGUE", "subtitle": "Anytime, Anywhere"},
    {"scene": "home", "speaker": None, "text": "The forge, days later. The hammering has started again - a little louder than before, maybe."},
    {"scene": "home", "speaker": STORY_SON_NAME.lower(), "text": "Dad, the Ice one keeps asking if you're free next week. Something about a rematch."},
    {"scene": "home", "speaker": "fire", "text": "Tell her I said the same thing I told all of them: anytime, anywhere."},
    {"scene": "home", "speaker": STORY_SON_NAME.lower(), "text": "The Nature guy sent a flower. It's already trying to eat the mailbox."},
    {"scene": "home", "speaker": "fire", "text": "...Tell him thank you. And to come get it before it succeeds."},
    {"scene": "home", "speaker": None, "text": "Somewhere out past the treeline, the whole Clan is already listening - and, for the first time in a long while, none of them are being tested."},
]

STORY_TEXT_CHARS_PER_SEC = 45