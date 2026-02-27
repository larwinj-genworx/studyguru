from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from .base import BaseStructuredAgent
from ..config import Settings


class ResourceUnavailableError(RuntimeError):
    """Raised when no external resources can be found for a concept."""

try:
    from bs4 import BeautifulSoup
except Exception:  # pragma: no cover - optional runtime dependency
    BeautifulSoup = None  # type: ignore[assignment]


class ResourceFinderAgent(BaseStructuredAgent):
    def __init__(self, settings: Settings) -> None:
        super().__init__(
            settings,
            role="ResourceFinderAgent",
            goal="Find free and beginner-friendly learning resources.",
            backstory="Academic resource curator for school students.",
        )
        self._logger = logging.getLogger("uvicorn.error")

    async def execute(self, *, subject_name: str, grade_level: str, concept_name: str) -> dict[str, list[dict[str, str]]]:
        youtube_resources = await self._youtube_candidates(
            subject_name=subject_name,
            grade_level=grade_level,
            concept_name=concept_name,
        )

        searched_resources: list[dict[str, str]] = []
        try:
            searched_resources = await self._search_and_validate(
                subject_name=subject_name,
                grade_level=grade_level,
                concept_name=concept_name,
            )
        except ResourceUnavailableError as exc:
            self._logger.warning("[ResourceFinderAgent] Skipping web search: %s", exc)

        merged: list[dict[str, str]] = []
        seen_urls: set[str] = set()
        for resource in [*youtube_resources, *searched_resources]:
            url = resource.get("url", "").strip()
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            merged.append(
                {
                    "title": resource.get("title", "Resource").strip()[:120],
                    "url": url,
                    "note": resource.get("note", "Free learning resource").strip()[:240],
                }
            )
        if not merged:
            raise ResourceUnavailableError(
                "ResourceFinderAgent could not produce resources from external search."
            )
        return {"references": merged[:8]}

    def _generate_with_llm(self, *, subject_name: str, grade_level: str, concept_name: str) -> list[dict[str, str]]:
        return []

    async def _search_and_validate(self, *, subject_name: str, grade_level: str, concept_name: str) -> list[dict[str, str]]:
        if BeautifulSoup is None:
            raise ResourceUnavailableError(
                "beautifulsoup4 is not installed; cannot parse DuckDuckGo HTML results."
            )

        query = f"{grade_level} {subject_name} {concept_name} free study material"
        search_timeout = max(4, min(self.settings.resource_search_timeout_seconds, 12))
        try:
            candidates = await asyncio.wait_for(self._ddg_html_candidates(query), timeout=search_timeout)
        except Exception as exc:
            self._logger.warning("[ResourceFinderAgent] HTML search failed: %s", exc)
            candidates = []

        if not candidates:
            wiki_candidates = await self._wikipedia_candidates(concept_name)
            if wiki_candidates:
                candidates = wiki_candidates

        validated: list[dict[str, str]] = []
        timeout = httpx.Timeout(self.settings.resource_validation_timeout_seconds)

        async def _validate(item: dict[str, str], client: httpx.AsyncClient) -> dict[str, str] | None:
            try:
                response = await client.get(item["url"])
                if 200 <= response.status_code < 400:
                    return item
            except Exception:
                return None
            return None

        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            tasks = [_validate(item, client) for item in candidates[:5]]
            for result in await asyncio.gather(*tasks, return_exceptions=True):
                if isinstance(result, dict):
                    validated.append(result)
                if len(validated) >= 4:
                    break
        if validated:
            return validated
        if candidates:
            self._logger.warning(
                "[ResourceFinderAgent] Validation failed; returning unvalidated search results."
            )
            return candidates[:4]
        return []

    async def _ddg_html_candidates(self, query: str) -> list[dict[str, str]]:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        }
        timeout = httpx.Timeout(min(self.settings.resource_search_timeout_seconds, 12))

        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=headers) as client:
            # Prefer lightweight HTML to avoid JS/browser impersonation.
            lite_url = "https://duckduckgo.com/lite/"
            html_url = "https://duckduckgo.com/html/"
            for endpoint in (lite_url, html_url):
                try:
                    response = await client.get(endpoint, params={"q": query})
                    if response.status_code >= 400:
                        continue
                    candidates = self._parse_ddg_html(response.text)
                    if candidates:
                        return candidates
                except Exception as exc:
                    self._logger.warning("[ResourceFinderAgent] DDG HTML fetch failed: %s", exc)
                    continue
        return []

    @staticmethod
    def _normalize_ddg_url(raw_url: str) -> str | None:
        url = raw_url.strip()
        if not url:
            return None
        if url.startswith("//"):
            url = f"https:{url}"
        if url.startswith("/l/"):
            parsed = urlparse(f"https://duckduckgo.com{url}")
            target = parse_qs(parsed.query).get("uddg", [""])[0]
            if target:
                return unquote(target)
            return None
        if url.startswith("http://") or url.startswith("https://"):
            return url
        return None

    def _parse_ddg_html(self, html: str) -> list[dict[str, str]]:
        soup = BeautifulSoup(html, "lxml")
        candidates: list[dict[str, str]] = []

        # DuckDuckGo Lite results
        for anchor in soup.select("a.result-link"):
            href = anchor.get("href") or ""
            url = self._normalize_ddg_url(href)
            if not url:
                continue
            title = anchor.get_text(" ", strip=True) or "Resource"
            candidates.append(
                {
                    "title": title,
                    "url": url,
                    "note": "DuckDuckGo result",
                }
            )
            if len(candidates) >= 6:
                return candidates

        # DuckDuckGo HTML results
        for anchor in soup.select("a.result__a"):
            href = anchor.get("href") or ""
            url = self._normalize_ddg_url(href)
            if not url:
                continue
            title = anchor.get_text(" ", strip=True) or "Resource"
            candidates.append(
                {
                    "title": title,
                    "url": url,
                    "note": "DuckDuckGo result",
                }
            )
            if len(candidates) >= 6:
                break
        return candidates

    async def _wikipedia_candidates(self, concept_name: str) -> list[dict[str, str]]:
        timeout = httpx.Timeout(min(self.settings.resource_search_timeout_seconds, 10))
        params = {
            "action": "opensearch",
            "search": concept_name,
            "limit": 5,
            "namespace": 0,
            "format": "json",
        }
        url = "https://en.wikipedia.org/w/api.php"
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                response = await client.get(url, params=params)
                if response.status_code >= 400:
                    return []
                data = response.json()
        except Exception as exc:
            self._logger.warning("[ResourceFinderAgent] Wikipedia search failed: %s", exc)
            return []

        if not isinstance(data, list) or len(data) < 4:
            return []
        titles = data[1] or []
        links = data[3] or []
        candidates: list[dict[str, str]] = []
        for title, link in zip(titles, links):
            if not link:
                continue
            candidates.append(
                {
                    "title": str(title).strip() or "Wikipedia",
                    "url": str(link).strip(),
                    "note": "Wikipedia article",
                }
            )
            if len(candidates) >= 5:
                break
        return candidates

    async def _youtube_candidates(
        self,
        *,
        subject_name: str,
        grade_level: str,
        concept_name: str,
    ) -> list[dict[str, str]]:
        api_key = (self.settings.youtube_api_key or "").strip()
        if not api_key:
            return []

        query = f"{grade_level} {subject_name} {concept_name} tutorial"
        search_url = "https://www.googleapis.com/youtube/v3/search"
        videos_url = "https://www.googleapis.com/youtube/v3/videos"
        timeout = httpx.Timeout(min(self.settings.resource_search_timeout_seconds, 8))

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                search_response = await client.get(
                    search_url,
                    params={
                        "part": "snippet",
                        "q": query,
                        "type": "video",
                        "maxResults": 8,
                        "safeSearch": "strict",
                        "videoEmbeddable": "true",
                        "relevanceLanguage": "en",
                        "order": "viewCount",
                        "key": api_key,
                    },
                )
                if search_response.status_code >= 400:
                    return []
                search_data = search_response.json()
                items = search_data.get("items", []) if isinstance(search_data, dict) else []
                video_ids = [
                    item.get("id", {}).get("videoId")
                    for item in items
                    if isinstance(item, dict)
                ]
                video_ids = [vid for vid in video_ids if vid]
                if not video_ids:
                    return []

                videos_response = await client.get(
                    videos_url,
                    params={
                        "part": "snippet,statistics",
                        "id": ",".join(video_ids[:8]),
                        "key": api_key,
                    },
                )
                if videos_response.status_code >= 400:
                    return []
                videos_data = videos_response.json()
                video_items = videos_data.get("items", []) if isinstance(videos_data, dict) else []
        except Exception as exc:
            self._logger.warning("[ResourceFinderAgent] YouTube fetch failed: %s", exc)
            return []

        ranked: list[dict[str, Any]] = []
        for item in video_items:
            if not isinstance(item, dict):
                continue
            video_id = item.get("id")
            snippet = item.get("snippet", {}) or {}
            stats = item.get("statistics", {}) or {}
            if not video_id:
                continue
            try:
                views = int(stats.get("viewCount", 0))
            except (TypeError, ValueError):
                views = 0
            try:
                likes = int(stats.get("likeCount", 0))
            except (TypeError, ValueError):
                likes = 0
            ranked.append(
                {
                    "title": str(snippet.get("title", "YouTube Lesson")).strip(),
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                    "views": views,
                    "likes": likes,
                }
            )

        if not ranked:
            return []

        ranked.sort(key=lambda item: (item["views"], item["likes"]), reverse=True)
        best = ranked[0]
        note = f"YouTube video (views: {best['views']:,}, likes: {best['likes']:,})"
        return [
            {
                "title": best["title"][:120],
                "url": best["url"],
                "note": note[:240],
            }
        ]
