from pygame.math import Vector2

# Average -> God transformation tuning. Kept here since fighters.py is
# the one place that actually performs the swap (Fighter.ascend()).
AVERAGE_ASCENSION_TIME = 120  # seconds of survival before ascending
GOD_MAX_HP = 220
GOD_DAMAGE_REDUCTION = 0.3  # Divine Protection


class Fighter:
    MAX_STAMINA = 100
    STAMINA_REGEN_PER_SEC = 14
    STREAK_TIMEOUT = 3.0

    def __init__(self, element, position, name, base_speed, starting_ult=0, team=None):
        self.element = element
        self.pos = Vector2(position)
        self.name = name
        self.team = team  # None everywhere except Domination ("blue"/"red")

        self.max_hp = 100
        self.hp = 100
        self.base_speed = base_speed
        self.ult = starting_ult

        self.stamina = self.MAX_STAMINA

        # Only meaningful for "average" - counts up toward
        # AVERAGE_ASCENSION_TIME, at which point ascend() fires and
        # turns this fighter into "god" for the rest of the match.
        # Harmless (just an unused counter) for every other element.
        self.time_alive = 0

        self.last_move_direction = Vector2(1, 0)

        # Where this fighter is currently aiming (mouse/right stick for
        # the player, target direction for bots) - independent of which
        # way they're moving. Drives weapon orientation so it always
        # points where attacks will actually go.
        self.facing_direction = Vector2(1, 0)

        # Purely visual - drives the held-weapon swing animation on a
        # short attack. Doesn't affect gameplay/damage timing at all,
        # which still runs off cooldowns["short"] as before.
        self.melee_swing_timer = 0
        self.melee_swing_duration = 0.28
        self.melee_swing_direction = Vector2(1, 0)

        self.burn_timer = 0
        self.slow_timer = 0
        self.root_timer = 0
        self.magnet_timer = 0
        self.stun_timer = 0
        self.fear_timer = 0
        self.soak_timer = 0

        # Domination only: brief invulnerability right after an
        # instant respawn, so you can't be re-killed the instant you
        # reappear. 0 everywhere else, always.
        self.respawn_grace_timer = 0

        # Generic hook for passive damage-reduction abilities
        # (e.g. Shadow's Dark Veil, God's Divine Protection).
        # 0 = no reduction, 0.3 = takes 30% less damage, etc.
        self.damage_reduction = 0

        self.cooldowns = {
            "short": 0,
            "long": 0,
            "special": 0,
            "ultimate": 0,
        }

        # Idle-wander state, used by bot AI when it has no visible target
        # (e.g. the player is stealthed during Shadow's Eternal Night).
        self.wander_timer = 0
        self.wander_direction = Vector2(1, 0)

        # Per-match combat stats - purely for display (kill feed, end-of-
        # match summary, HUD combo counter). Never read by gameplay logic.
        self.kills = 0
        self.damage_dealt = 0
        self.damage_taken = 0
        self.hit_streak = 0
        self.best_hit_streak = 0
        self.streak_timer = 0

    @property
    def alive(self):
        return self.hp > 0

    @property
    def speed(self):
        if self.root_timer > 0 or self.stun_timer > 0:
            return 0

        base = self.base_speed

        if self.element == "wind":
            # Featherweight: Wind is simply faster than everyone else,
            # all the time, not just while dashing.
            base *= 1.25

        if self.slow_timer > 0:
            return base * 0.55

        return base

    def update(self, dt):
        cooldown_dt = dt * 0.5 if self.soak_timer > 0 else dt

        for cooldown_name in self.cooldowns:
            self.cooldowns[cooldown_name] = max(
                0,
                self.cooldowns[cooldown_name] - cooldown_dt
            )

        self.burn_timer = max(0, self.burn_timer - dt)
        self.slow_timer = max(0, self.slow_timer - dt)
        self.root_timer = max(0, self.root_timer - dt)
        self.magnet_timer = max(0, self.magnet_timer - dt)
        self.stun_timer = max(0, self.stun_timer - dt)
        self.fear_timer = max(0, self.fear_timer - dt)
        self.soak_timer = max(0, self.soak_timer - dt)
        self.melee_swing_timer = max(0, self.melee_swing_timer - dt)
        self.respawn_grace_timer = max(0, self.respawn_grace_timer - dt)

        if self.burn_timer > 0 and self.respawn_grace_timer <= 0:
            self.hp -= 4 * dt

        self.stamina = min(self.MAX_STAMINA, self.stamina + self.STAMINA_REGEN_PER_SEC * dt)

        self.streak_timer += dt

        if self.streak_timer > self.STREAK_TIMEOUT:
            self.hit_streak = 0

        if self.element == "average" and self.alive:
            self.time_alive += dt

            if self.time_alive >= AVERAGE_ASCENSION_TIME:
                self.ascend()

    def ascend(self):
        """Average survives long enough and becomes God for the rest of
        the match - full heal, a real health/damage upgrade, and a
        clean slate on negative status effects (Divine Protection kicks
        in from this point via damage_reduction)."""
        self.element = "god"
        self.max_hp = GOD_MAX_HP
        self.hp = self.max_hp
        self.stamina = self.MAX_STAMINA
        self.damage_reduction = GOD_DAMAGE_REDUCTION

        self.burn_timer = 0
        self.slow_timer = 0
        self.root_timer = 0
        self.magnet_timer = 0
        self.stun_timer = 0
        self.fear_timer = 0
        self.soak_timer = 0

    def has_stamina(self, cost):
        return self.stamina >= cost

    def spend_stamina(self, cost):
        self.stamina = max(0, self.stamina - cost)

    def move(self, direction, dt, arena, speed_multiplier=1):
        if direction.length() == 0:
            return

        self.last_move_direction = direction.normalize()
        self.pos += self.last_move_direction * self.speed * speed_multiplier * dt
        self.keep_in_arena(arena)

    def dash(self, distance, arena):
        self.pos += self.last_move_direction * distance
        self.keep_in_arena(arena)

    def keep_in_arena(self, arena):
        self.pos.x = max(arena.left + 18, min(arena.right - 18, self.pos.x))
        self.pos.y = max(arena.top + 18, min(arena.bottom - 18, self.pos.y))

    def damage(self, amount):
        if self.respawn_grace_timer > 0:
            return

        actual = amount * (1 - self.damage_reduction)
        self.hp -= actual
        self.damage_taken += max(0, actual)

    def register_hit(self, amount):
        """Called by the attacker (not the target) when a hit lands, to
        track damage dealt and combo streaks for the kill feed/HUD."""
        self.damage_dealt += max(0, amount)
        self.hit_streak += 1
        self.best_hit_streak = max(self.best_hit_streak, self.hit_streak)
        self.streak_timer = 0

    def register_kill(self):
        self.kills += 1

    def burn(self, duration):
        self.burn_timer = max(self.burn_timer, duration)

    def slow(self, duration):
        self.slow_timer = max(self.slow_timer, duration)

    def root(self, duration):
        self.root_timer = max(self.root_timer, duration)

    def magnetize(self, duration):
        self.magnet_timer = max(self.magnet_timer, duration)

    def stun(self, duration):
        self.stun_timer = max(self.stun_timer, duration)

    def fear(self, duration):
        self.fear_timer = max(self.fear_timer, duration)

    def soak(self, duration):
        self.soak_timer = max(self.soak_timer, duration)

    def trigger_melee_swing(self, direction):
        """Purely visual: kicks off the held-weapon swing animation in
        the given facing direction. Called alongside a short attack,
        whether or not it actually connects with anything."""
        if direction.length() > 0:
            self.melee_swing_direction = direction.normalize()

        self.melee_swing_timer = self.melee_swing_duration