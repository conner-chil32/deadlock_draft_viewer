import pygame


class Button:
    """Simple rectangular pygame button with hover highlight."""

    def __init__(self, rect, text, font,
                 color=(40, 40, 40), hover_color=(70, 70, 70),
                 text_color=(255, 255, 255), border_color=(180, 180, 180)):
        self.rect         = pygame.Rect(rect)
        self.text         = text
        self.font         = font
        self.color        = color
        self.hover_color  = hover_color
        self.text_color   = text_color
        self.border_color = border_color

    def draw(self, surface) -> None:
        hovered = self.rect.collidepoint(pygame.mouse.get_pos())
        fill    = self.hover_color if hovered else self.color
        pygame.draw.rect(surface, fill,             self.rect, border_radius=8)
        pygame.draw.rect(surface, self.border_color, self.rect, width=2, border_radius=8)
        label = self.font.render(self.text, True, self.text_color)
        surface.blit(label, label.get_rect(center=self.rect.center))

    def is_clicked(self, event) -> bool:
        return (
            event.type == pygame.MOUSEBUTTONDOWN
            and event.button == 1
            and self.rect.collidepoint(event.pos)
        )
