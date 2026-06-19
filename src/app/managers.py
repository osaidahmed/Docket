from django.apps import apps
from django.db import models
from django.db.models import Count, F, Q, Window
from django.db.models.functions import RowNumber
from django.utils import timezone

import users
from app import _media_filters, _media_prefetch, _media_sorting
from app._types import MediaTypes


class MediaManager(models.Manager):
    """Custom manager for media models."""

    def _model_for(self, media_type):
        """Resolve a sibling model in this manager's app by media_type."""
        app_label = self.model._meta.app_label if self.model else "app"
        return apps.get_model(app_label, media_type)

    def get_historical_models(self):
        """Return list of historical model names."""
        _ = self.model
        return [f"historical{media_type}" for media_type in MediaTypes.values]

    def get_media_list(
        self, user, media_type, status_filter, sort_filter, search=None, sort_dir=None
    ):
        """Get media list based on filters, sorting and search."""
        model = self._model_for(media_type)
        queryset = model.objects.filter(user=user.id)

        if isinstance(status_filter, list):
            queryset = queryset.filter(status__in=status_filter)
        elif status_filter != users.models.MediaStatusChoices.ALL:
            queryset = queryset.filter(status=status_filter)

        if search:
            queryset = queryset.filter(
                Q(item__title__icontains=search)
                | Q(item__english_title__icontains=search)
            )

        queryset = queryset.annotate(
            repeats=Window(
                expression=Count("id"),
                partition_by=[F("item")],
            ),
            row_number=Window(
                expression=RowNumber(),
                partition_by=[F("item")],
                order_by=F("created_at").desc(),
            ),
        ).filter(row_number=1)

        queryset = queryset.select_related("item")
        queryset = _media_prefetch.apply_prefetch_related(queryset, media_type)

        if sort_filter:
            return _media_sorting.sort_media_list(
                queryset, sort_filter, media_type, sort_dir
            )
        return queryset

    def annotate_max_progress(self, media_list, media_type):
        """Annotate max_progress for all media items."""
        _ = self.model
        _media_prefetch.annotate_max_progress(media_list, media_type, timezone.now())

    def _apply_prefetch_related(self, queryset, media_type):
        """Attach prefetch_related calls based on media type."""
        _ = self.model
        return _media_prefetch.apply_prefetch_related(queryset, media_type)

    def fetch_media_for_items(self, media_types, item_ids, user, status_filter=None):
        """Fetch media objects for given items, optionally filtering by status."""
        media_by_item_id = {}

        for media_type in media_types:
            model = self._model_for(media_type)
            filter_kwargs = _media_filters.build_item_filter(
                media_type, item_ids, user, status_filter
            )
            queryset = model.objects.filter(**filter_kwargs).select_related("item")
            queryset = _media_prefetch.apply_prefetch_related(queryset, media_type)
            self.annotate_max_progress(queryset, media_type)

            for entry in queryset:
                media_by_item_id.setdefault(entry.item_id, entry)

        return media_by_item_id

    def get_media(self, user, media_type, instance_id):
        """Get user media object given the media type and item."""
        model = self._model_for(media_type)
        params = _media_filters.get_media_params(user, media_type, instance_id)
        return model.objects.get(**params)

    def get_media_prefetch(self, user, media_type, instance_id):
        """Get user media object with prefetch_related applied."""
        model = self._model_for(media_type)
        params = _media_filters.get_media_params(user, media_type, instance_id)

        queryset = model.objects.filter(**params)
        queryset = _media_prefetch.apply_prefetch_related(queryset, media_type)
        self.annotate_max_progress(queryset, media_type)

        return queryset[0]

    def filter_media(
        self,
        user,
        media_id,
        media_type,
        source,
        season_number=None,
        episode_number=None,
    ):
        """Filter media objects based on parameters."""
        model = self._model_for(media_type)
        params = _media_filters.filter_media_params(
            media_type,
            media_id,
            source,
            user,
            season_number,
            episode_number,
        )
        return model.objects.filter(**params)

    def filter_media_prefetch(
        self,
        user,
        media_id,
        media_type,
        source,
        season_number=None,
        episode_number=None,
    ):
        """Filter user media object with prefetch_related applied."""
        queryset = self.filter_media(
            user,
            media_id,
            media_type,
            source,
            season_number,
            episode_number,
        )
        queryset = _media_prefetch.apply_prefetch_related(queryset, media_type)
        self.annotate_max_progress(queryset, media_type)
        return queryset
