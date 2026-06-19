from app.link_providers import http as link_http
from app.link_providers.base import LinkProvider, LinkProviderError, LinkResult

GRAPHQL_URL = "https://api.allanime.day/api"
DEEP_LINK = "https://allmanga.to/manga/{_id}"

_QUERY = """query(
    $search: SearchInput,
    $limit: Int,
    $page: Int,
    $translationType: VaildTranslationTypeMangaEnumType,
    $countryOrigin: VaildCountryOriginEnumType
) {
    mangas(
        search: $search,
        limit: $limit,
        page: $page,
        translationType: $translationType,
        countryOrigin: $countryOrigin
    ) {
        edges {
            _id
            name
            englishName
        }
    }
}"""

_HEADERS = {
    "Origin": "https://allmanga.to",
    "Referer": "https://allmanga.to/",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    ),
}


def _build_variables(query):
    return {
        "search": {
            "allowAdult": False,
            "allowUnknown": False,
            "query": query,
        },
        "limit": 3,
        "page": 1,
        "translationType": "sub",
        "countryOrigin": "ALL",
    }


class AllMangaProvider(LinkProvider):
    """Manga link provider for allmanga.to backed by the allanime GraphQL API."""

    site_id = "allmanga"
    label = "AllManga (allmanga.to)"
    media_types = ("manga",)

    def find(self, item):
        """Search by english_title (preferred) then native title."""
        query = item.english_title or item.title
        edges = self._search(query)
        if not edges and item.english_title and item.english_title != item.title:
            edges = self._search(item.title)
        if not edges:
            return None
        return LinkResult(
            url=DEEP_LINK.format(_id=edges[0]["_id"]),
            site_id=self.site_id,
        )

    def _search(self, query):
        try:
            response = link_http.http_post(
                GRAPHQL_URL,
                json_body={"query": _QUERY, "variables": _build_variables(query)},
                headers=_HEADERS,
            )
        except LinkProviderError:
            return []
        data = response.json()
        return data.get("data", {}).get("mangas", {}).get("edges", []) or []
