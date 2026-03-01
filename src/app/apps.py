from django.apps import AppConfig


class AppConfig(AppConfig):
    """Default app config."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "app"

    def ready(self):
        """Import signals when the app is ready."""
        from django.db.models.signals import post_delete, post_save  # noqa: PLC0415

        import app.signals  # noqa: PLC0415
        from app.models import (  # noqa: PLC0415
            TV,
            Anime,
            BoardGame,
            Book,
            Comic,
            Game,
            Manga,
            Movie,
            Season,
        )

        for model in [TV, Anime, BoardGame, Book, Comic, Game, Manga, Movie, Season]:
            post_save.connect(
                app.signals.invalidate_recommendations_cache, sender=model
            )
            post_delete.connect(
                app.signals.invalidate_recommendations_cache, sender=model
            )
