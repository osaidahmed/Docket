import re

from django import forms
from django.conf import settings

from app import config
from app._types import is_episode_media, is_season_media
from app.models import (
    TV,
    Anime,
    BoardGame,
    Book,
    Comic,
    Episode,
    Game,
    Item,
    Manga,
    MediaTypes,
    Movie,
    Season,
    Sources,
)


def get_form_class(media_type):
    """Return the form class for the media type."""
    class_name = media_type.capitalize() + "Form"
    return globals().get(class_name, None)


_TIME_RE = re.compile(
    r"^(\d+)$"
    r"|^(\d+):(\d+)$"
    r"|^(\d+)\s*h\s*(?:(\d+)\s*min)?$"
    r"|^(\d+)\s*min$"
)


class CustomDurationField(forms.CharField):
    """Custom form field for duration input that accepts multiple time formats."""

    def _parse_hours_minutes(self, value):
        m = _TIME_RE.fullmatch(value.strip())
        if not m:
            msg = (
                "Invalid time played format. "
                "Please use hh:mm, 5h 30min, or 5h30min format."
            )
            raise forms.ValidationError(msg)
        if m.group(1) is not None:
            return int(m.group(1)), 0
        if m.group(2) is not None:
            return int(m.group(2)), int(m.group(3))
        if m.group(6) is not None:
            return 0, int(m.group(6))
        return int(m.group(4)), int(m.group(5) or 0)

    def _validate_minutes(self, minutes):
        """Validate that minutes are within acceptable range."""
        max_min = 59
        if not (0 <= minutes <= max_min):
            msg = f"Minutes must be between 0 and {max_min}."
            raise forms.ValidationError(msg)

    def clean(self, value):
        """Validate and convert the time string to total minutes."""
        cleaned_value = super().clean(value)
        if not cleaned_value:
            return 0
        hours, minutes = self._parse_hours_minutes(cleaned_value)
        self._validate_minutes(minutes)
        return hours * 60 + minutes


class ManualItemForm(forms.ModelForm):
    """Form for adding items to the database."""

    parent_tv = forms.ModelChoiceField(
        required=False,
        queryset=TV.objects.none(),
        empty_label="Select",
        label="Parent TV Show",
    )

    parent_season = forms.ModelChoiceField(
        required=False,
        queryset=Season.objects.none(),
        empty_label="Select",
        label="Parent Season",
    )

    class Meta:
        """Bind form to model."""

        model = Item
        fields = [
            "media_type",
            "title",
            "english_title",
            "synopsis",
            "image",
            "season_number",
            "episode_number",
        ]

    def __init__(self, *args, **kwargs):
        """Initialize the form."""
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        if self.user:
            self.fields["parent_tv"].queryset = TV.objects.filter(
                user=self.user,
                item__source=Sources.MANUAL.value,
                item__media_type=MediaTypes.TV.value,
            )
            self.fields["parent_season"].queryset = Season.objects.filter(
                user=self.user,
                item__source=Sources.MANUAL.value,
                item__media_type=MediaTypes.SEASON.value,
            )
        self.fields["image"].required = False
        self.fields["title"].required = False

    def _validate_parent(self, cleaned_data, media_type):
        if is_season_media(media_type):
            parent = cleaned_data.get("parent_tv")
            if not parent:
                self.add_error(
                    "parent_tv",
                    "Parent TV show is required for seasons.",
                )
                return
            cleaned_data["title"] = parent.item.title
            cleaned_data["episode_number"] = None
        else:
            parent = cleaned_data.get("parent_season")
            if not parent:
                self.add_error(
                    "parent_season",
                    "Parent season is required for episodes.",
                )
                return
            cleaned_data["title"] = parent.item.title
            cleaned_data["season_number"] = parent.item.season_number

    def clean(self):
        """Validate the form."""
        cleaned_data = super().clean()
        cleaned_data["image"] = cleaned_data.get("image") or settings.IMG_NONE
        media_type = cleaned_data.get("media_type")

        if is_season_media(media_type) or is_episode_media(media_type):
            self._validate_parent(cleaned_data, media_type)
        else:
            if not cleaned_data.get("title"):
                self.add_error("title", "Title is required for this media type.")
            cleaned_data["season_number"] = None
            cleaned_data["episode_number"] = None

        return cleaned_data

    def save(self, commit=True):  # noqa: FBT002
        """Save the form and handle manual media ID generation."""
        instance = super().save(commit=False)
        instance.source = Sources.MANUAL.value

        if is_season_media(instance.media_type):
            parent_tv = self.cleaned_data["parent_tv"]
            instance.media_id = parent_tv.manual_media_id
        elif is_episode_media(instance.media_type):
            parent_season = self.cleaned_data["parent_season"]
            instance.media_id = parent_season.manual_media_id
            instance.season_number = parent_season.manual_season_number
        else:
            instance.media_id = Item.generate_manual_id(instance.media_type)

        if commit:
            instance.save()
        return instance


class MediaForm(forms.ModelForm):
    """Base form for all media types."""

    instance_id = forms.CharField(widget=forms.HiddenInput(), required=False)
    media_type = forms.CharField(widget=forms.HiddenInput(), required=True)
    source = forms.CharField(widget=forms.HiddenInput(), required=True)
    media_id = forms.CharField(widget=forms.HiddenInput(), required=True)

    class Meta:
        """Define fields and input types."""

        fields = [
            "score",
            "progress",
            "status",
            "start_date",
            "end_date",
            "notes",
            "link",
            "caught_up",
            "is_rewatch",
        ]
        widgets = {
            "score": forms.NumberInput(
                attrs={"min": 0, "max": 10, "step": 0.1, "placeholder": "0-10"},
            ),
            "progress": forms.NumberInput(attrs={"min": 0}),
            "start_date": forms.DateTimeInput(attrs={"type": "datetime-local"})
            if settings.TRACK_TIME
            else forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateTimeInput(attrs={"type": "datetime-local"})
            if settings.TRACK_TIME
            else forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(
                attrs={"placeholder": "Add any notes or comments...", "rows": "5"},
            ),
            "link": forms.URLInput(
                attrs={"placeholder": "https://..."},
            ),
        }


class MangaForm(MediaForm):
    """Form for manga."""

    class Meta(MediaForm.Meta):
        """Bind form to model."""

        model = Manga
        labels = {
            "progress": (
                f"Progress ({config.get_unit(MediaTypes.MANGA.value, short=False)}s)"
            ),
            "is_rewatch": "Reread",
        }


class AnimeForm(MediaForm):
    """Form for anime."""

    class Meta(MediaForm.Meta):
        """Bind form to model."""

        model = Anime
        labels = {"is_rewatch": "Rewatch"}


class MovieForm(MediaForm):
    """Form for movies."""

    class Meta(MediaForm.Meta):
        """Bind form to model."""

        model = Movie
        fields = [
            "score",
            "status",
            "start_date",
            "end_date",
            "notes",
            "link",
            "is_rewatch",
        ]
        labels = {"is_rewatch": "Rewatch"}


class GameForm(MediaForm):
    """Form for games."""

    progress = CustomDurationField(
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "hh:mm"}),
        label="Progress (Time Played)",
    )

    class Meta(MediaForm.Meta):
        """Bind form to model."""

        model = Game
        labels = {"is_rewatch": "Replay"}


class BookForm(MediaForm):
    """Form for books."""

    class Meta(MediaForm.Meta):
        """Bind form to model."""

        model = Book
        labels = {
            "progress": (
                f"Progress ({config.get_unit(MediaTypes.BOOK.value, short=False)}s)"
            ),
            "is_rewatch": "Reread",
        }


class ComicForm(MediaForm):
    """Form for comics."""

    class Meta(MediaForm.Meta):
        """Bind form to model."""

        model = Comic
        labels = {
            "progress": (
                f"Progress ({config.get_unit(MediaTypes.COMIC.value, short=False)}s)"
            ),
            "is_rewatch": "Reread",
        }


class BoardgameForm(MediaForm):
    """Form for board games."""

    class Meta(MediaForm.Meta):
        """Bind form to model."""

        model = BoardGame
        labels = {
            "progress": (
                "Progress "
                f"({config.get_unit(MediaTypes.BOARDGAME.value, short=False)}s)"
            ),
            "is_rewatch": "Replay",
        }


class TvForm(MediaForm):
    """Form for TV shows."""

    class Meta(MediaForm.Meta):
        """Bind form to model."""

        model = TV
        fields = ["score", "status", "notes", "link", "is_rewatch"]
        labels = {"is_rewatch": "Rewatch"}


class SeasonForm(MediaForm):
    """Form for seasons."""

    season_number = forms.IntegerField(widget=forms.HiddenInput(), required=False)

    class Meta(MediaForm.Meta):
        """Bind form to model."""

        model = Season
        fields = [
            "score",
            "status",
            "notes",
            "link",
            "is_rewatch",
        ]
        labels = {"is_rewatch": "Rewatch"}


class EpisodeForm(forms.ModelForm):
    """Form for episodes."""

    class Meta:
        """Bind form to model."""

        model = Episode
        fields = ("end_date",)
        widgets = {
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        """Initialize the form."""
        super().__init__(*args, **kwargs)

        if settings.TRACK_TIME:
            self.fields["end_date"].widget = forms.DateTimeInput(
                attrs={"type": "datetime-local"},
            )
        else:
            self.fields["end_date"].widget = forms.DateInput(
                attrs={"type": "date"},
            )
