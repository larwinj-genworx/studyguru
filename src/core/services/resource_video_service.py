from __future__ import annotations

import logging
from threading import Lock
from time import monotonic
from typing import Any

import httpx

from src.config.settings import Settings, get_settings


_logger = logging.getLogger("uvicorn.error")
_CACHE_MISS = object()


class YouTubeVideoService:
    _cache_lock = Lock()
    _result_cache: dict[tuple[str, str, str, tuple[str, ...]], tuple[float, dict[str, Any] | None]] = {}

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    async def find_best_video(
        self,
        *,
        subject_name: str,
        grade_level: str,
        concept_name: str,
        exclude_video_ids: set[str] | None = None,
    ) -> dict[str, Any] | None:
        api_key = (self.settings.youtube_api_key or "").strip()
        if not api_key:
            return None

        excluded_ids = tuple(sorted(exclude_video_ids or set()))
        cache_key = (subject_name.strip(), grade_level.strip(), concept_name.strip(), excluded_ids)
        cached = self._get_cached_result(cache_key)
        if cached is not _CACHE_MISS:
            return cached

        query = f"{grade_level} {subject_name} {concept_name} tutorial"
        search_url = self.settings.youtube_search_url
        videos_url = self.settings.youtube_videos_url
        timeout = httpx.Timeout(min(self.settings.resource_search_timeout_seconds, 8))

        exclude_video_ids = set(excluded_ids)

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                search_response = await client.get(
                    search_url,
                    params={
                        "part": "snippet",
                        "q": query,
                        "type": "video",
                        "maxResults": 10,
                        "safeSearch": "strict",
                        "videoEmbeddable": "true",
                        "relevanceLanguage": "en",
                        "order": "viewCount",
                        "key": api_key,
                    },
                )
                if search_response.status_code >= 400:
                    self._store_cached_result(cache_key, None)
                    return None
                search_data = search_response.json()
                items = search_data.get("items", []) if isinstance(search_data, dict) else []
                video_ids = [
                    item.get("id", {}).get("videoId")
                    for item in items
                    if isinstance(item, dict)
                ]
                video_ids = [vid for vid in video_ids if vid and vid not in exclude_video_ids]
                if not video_ids:
                    self._store_cached_result(cache_key, None)
                    return None

                videos_response = await client.get(
                    videos_url,
                    params={
                        "part": "snippet,statistics",
                        "id": ",".join(video_ids[:10]),
                        "key": api_key,
                    },
                )
                if videos_response.status_code >= 400:
                    self._store_cached_result(cache_key, None)
                    return None
                videos_data = videos_response.json()
                video_items = videos_data.get("items", []) if isinstance(videos_data, dict) else []
        except httpx.HTTPError:
            _logger.error("[YouTubeVideoService] YouTube fetch failed.", exc_info=True)
            self._store_cached_result(cache_key, None)
            return None

        ranked: list[dict[str, Any]] = []
        for item in video_items:
            if not isinstance(item, dict):
                continue
            video_id = item.get("id")
            if not video_id or video_id in exclude_video_ids:
                continue
            snippet = item.get("snippet", {}) or {}
            stats = item.get("statistics", {}) or {}
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
                    "video_id": video_id,
                    "title": str(snippet.get("title", "YouTube Lesson")).strip(),
                    "url": f"{self.settings.youtube_watch_base_url}?v={video_id}",
                    "views": views,
                    "likes": likes,
                }
            )

        if not ranked:
            self._store_cached_result(cache_key, None)
            return None

        ranked.sort(key=lambda item: (item["views"], item["likes"]), reverse=True)
        result = ranked[0]
        self._store_cached_result(cache_key, result)
        return result.copy()

    def _get_cached_result(
        self,
        cache_key: tuple[str, str, str, tuple[str, ...]],
    ) -> dict[str, Any] | None | object:
        ttl_seconds = max(self.settings.resource_cache_ttl_seconds, 0)
        if ttl_seconds <= 0:
            return _CACHE_MISS
        now = monotonic()
        with self._cache_lock:
            cached = self._result_cache.get(cache_key)
            if cached is None:
                return _CACHE_MISS
            expires_at, value = cached
            if expires_at <= now:
                self._result_cache.pop(cache_key, None)
                return _CACHE_MISS
        return value.copy() if isinstance(value, dict) else value

    def _store_cached_result(
        self,
        cache_key: tuple[str, str, str, tuple[str, ...]],
        value: dict[str, Any] | None,
    ) -> None:
        ttl_seconds = max(self.settings.resource_cache_ttl_seconds, 0)
        if ttl_seconds <= 0:
            return
        expires_at = monotonic() + ttl_seconds
        cached_value = value.copy() if isinstance(value, dict) else None
        with self._cache_lock:
            self._result_cache[cache_key] = (expires_at, cached_value)
            overflow = len(self._result_cache) - max(self.settings.resource_cache_max_entries, 1)
            if overflow > 0:
                for key in sorted(self._result_cache, key=lambda item: self._result_cache[item][0])[:overflow]:
                    self._result_cache.pop(key, None)
