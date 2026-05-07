# Docket

A fork of [Yamtrack](https://github.com/FuzzyGrim/Yamtrack), a self-hosted media tracker for movies, TV, anime, manga, games, books, comics, and board games.

## Why fork it

I have a growing list of stuff I want to watch and read. The way I used to track it is leaving Google search tabs open across my phone and iPad. It worked until the browser clears them or I accidentally delete them. It also has no way to mark "I want to rewatch this," and half the list lives in my head anyway.

I tried the obvious replacements: AniList, Trakt, Simkl, TV Time, Serializd. None passed the bar I cared about, which is: don't be more friction than keeping a tab open. Two actions, max.

Yamtrack came closest. Self-hosted, covers every media type I care about, easy to modify. But it has friction in the wrong places. You pick a category before you can search. Adding something takes six clicks through a form. Your "want to watch" list is hidden on per-type pages. Docket is Yamtrack with that friction stripped out.

## What's different

- One search bar that queries every media type at once. No category dropdown.
- One-tap add to backlog from any search result. No modal, no form, no status picker.
- One unified backlog on the home page. Everything you haven't finished, on one screen.
- Synopsis shown on search cards, so you can tell what something is without clicking through.
- One-tap "Done" on backlog cards, so finishing something is as easy as adding it.

Everything else from upstream Yamtrack still works: per-type lists, the full tracking form, imports, calendar, notifications.

## What else changed

A few of the bigger pieces beyond the friction stuff:

- An add-by-link page. Paste any media URL (TMDB, MAL, IGDB, AniList, IMDB, Hardcover, BGG, ComicVine, etc.) and it pulls the slug, searches the right provider, and tracks the item. No clicking through results when you already know what you want.
- Auto-populated external links. Each tracked item picks up streaming/reading links automatically through pluggable link providers, so you can jump from the detail page to where the thing actually plays.
- Discover and Explore tabs. Trending sections, genre filters, and per-media-type browse. Books, comics, and board games got browse support.
- Live search suggestions. Typeahead that mixes results from your own library with fresh API hits, so re-finding something you already track is instant.
- Smarter status logic. Ongoing shows can't be marked completed by accident, they auto-resume to in-progress when a new season drops, and series without scheduled episodes get a "caught up" state instead of sitting in-progress forever.
- More user settings overall. Per-media-type preferences in their own table, configurable media type ordering, home page layout and grouping options, multi-select type filtering, archive sort, recent views, color theming.
