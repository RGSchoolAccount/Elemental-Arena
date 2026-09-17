"""
Elemental Arena - character variants (purchasable alternate kits/skins).

Pure data, no pygame/game-state dependency - both main.py (the client)
and server.py (which validates purchases without trusting the client's
word for what things cost) import this module.

Each variant belongs to a base element and swaps in a different
short/long attack and color scheme while keeping that element's
passive, ultimate, and movement special the same. A fighter with no
variant equipped just plays as the normal version of their element.
"""

VARIANTS = {
    "fire": [
        {
            "id": "fire_blueflame",
            "name": "Blue Inferno",
            "cost": 1000,
            "color": (60, 140, 255),
            "light_color": (160, 210, 255),
            "short_name": "Ashwalker Slash",
            "long_name": "Wildfire Ring",
            "description": (
                "A cursed variant of the Blade of Flame technique, said "
                "to burn colder than it looks. Trades single-target "
                "punch for a dash-in slash that catches everyone in "
                "front of it, and trades the fireball for a short-lived "
                "ring of fire that burns anyone standing too close."
            ),
        },
    ],
    "animalia": [
        {
            "id": "animalia_arachnid",
            "name": "Arachnid Ascendant",
            "cost": 1350,
            "color": (95, 40, 120),
            "light_color": (215, 120, 235),
            "short_name": "Stab Frenzy",
            "long_name": "Bear Trap",
            "description": (
                "The bond went the other way round for this one - "
                "something older answered, and it had eight legs. Trades "
                "the bow for twin fangs: two quick stabs open into an "
                "unbroken frenzy, and the arrow becomes a hidden bear "
                "trap that locks whoever finds it in place. Ancient "
                "Monster answers with a spider the size of the arena."
            ),
        },
    ],
}


def get_variant(element, variant_id):
    for variant in VARIANTS.get(element, []):
        if variant["id"] == variant_id:
            return variant

    return None


def variant_exists(element, variant_id):
    return get_variant(element, variant_id) is not None


def all_variant_ids():
    return [variant["id"] for variants in VARIANTS.values() for variant in variants]