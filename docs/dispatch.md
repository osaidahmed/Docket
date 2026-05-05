# Media-type dispatch

Two registries handle per-media-type variation in the codebase. They have separate purposes and live in separate places.

## `MEDIA_TYPE_REGISTRY` — behavior dispatch

`src/app/_media_type_registry.py` holds a `dict[str, MediaTypeSpec]`, keyed on `MediaTypes.X.value`. Each spec carries:

- the underlying display config (icons, verbs, colors, sources) via the `config` dict
- optional behavior hooks: `prefetch_builder`, `progress_annotator`, `sort_resolver`, `user_filter_builder`, `parent_filter_builder`, `calendar_processor`, `notification_key_builder`, `import_kwargs_builder`, `webhook_dispatcher`

Hooks are wired in by the consuming module at import time, e.g. `_media_prefetch.py` registers `tv_prefetch` / `season_prefetch` and dispatches via `(spec.prefetch_builder or default_prefetch)(qs)`. When a hook is `None`, the caller falls through to a documented default — types that need no override stay boilerplate-free.

## `services.get_media_metadata` — provider dispatch

`src/app/providers/services.py` holds a `(media_type, source) → callable` lambda dict that picks the right provider for fetching metadata. This is sibling to `MEDIA_TYPE_REGISTRY` but separate by design: providers can change without behavior changing (a book moving from OpenLibrary to Hardcover doesn't affect prefetch shape).

## Adding a new media type

1. Add a value to `MediaTypes` in `src/app/_types.py` and add a `MEDIA_TYPE_CONFIG` entry in `src/app/_media_type_config.py` for display tokens (icon, verb, colors, sources). The registry entry is auto-built.
2. Register provider lookups in `services.get_media_metadata`'s dispatch dict.
3. If the type needs custom behavior, write the hook function and assign it to the registered spec in the relevant consumer module — no other call sites change.

## Predicates

`src/app/_types.py` exposes `is_episode_media`, `is_season_media`, `is_tv_media`, `is_movie_media`, `is_anime_media`, `is_manga_media`, `is_game_media`, `is_tv_structured`. Predicate-style sites (`if media_type == "X"`) use these instead of inline string comparisons.
