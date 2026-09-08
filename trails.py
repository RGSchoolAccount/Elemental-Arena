import pygame
from pygame.math import Vector2


class Trail:
    def __init__(self, position, element, team=None):
        self.pos = Vector2(position)
        self.element = element
        self.team = team  # None everywhere except Domination - who left this trail
        self.radius = 28
        self.life = 3
        self.max_life = 3
        self.damage_cooldown = 0

    @property
    def alive(self):
        return self.life > 0

    def update(self, dt):
        self.life -= dt
        self.damage_cooldown = max(0, self.damage_cooldown - dt)

    def contains(self, position):
        return self.pos.distance_to(position) < self.radius

    def draw(self, surface, screen_pos):
        if self.element == "fire":
            color = (255, 105, 25)
        elif self.element == "metal":
            color = (195, 200, 210)
        elif self.element == "electric":
            color = (190, 110, 255)
        elif self.element == "music":
            color = (220, 100, 210)
        elif self.element == "wind":
            color = (200, 235, 225)
        else:
            color = (130, 230, 255)

        # Fade out over the final third of its life instead of popping
        # out of existence the instant life hits zero.
        fade_window = self.max_life * 0.35
        alpha = 255

        if self.life < fade_window and fade_window > 0:
            alpha = max(0, int(255 * (self.life / fade_window)))

        if alpha >= 255:
            pygame.draw.circle(surface, color, screen_pos, self.radius)
            pygame.draw.circle(surface, (255, 255, 255), screen_pos, self.radius, 1)
        else:
            size = self.radius * 2 + 4
            fade_surf = pygame.Surface((size, size), pygame.SRCALPHA)
            center = (size // 2, size // 2)
            pygame.draw.circle(fade_surf, (*color, alpha), center, self.radius)
            pygame.draw.circle(fade_surf, (255, 255, 255, alpha), center, self.radius, 1)
            surface.blit(fade_surf, (screen_pos[0] - size // 2, screen_pos[1] - size // 2))