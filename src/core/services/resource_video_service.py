from __future__ import annotations

import logging
from typing import Any

import httpx

from src.config.settings import Settings, get_settings


_logger = logging.getLogger("uvicorn.error")


class YouTubeVideoService:
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

        query = f"{grade_level} {subject_name} {concept_name} tutorial"
        search_url = "https://www.googleapis.com/youtube/v3/search"
        videos_url = "https://www.googleapis.com/youtube/v3/videos"
        timeout = httpx.Timeout(min(self.settings.resource_search_timeout_seconds, 8))

        exclude_video_ids = exclude_video_ids or set()

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
                    return None
                videos_data = videos_response.json()
                video_items = videos_data.get("items", []) if isinstance(videos_data, dict) else []
        except Exception as exc:
            _logger.warning("[YouTubeVideoService] YouTube fetch failed: %s", exc)
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
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                    "views": views,
                    "likes": likes,
                }
            )

        if not ranked:
            return None

        ranked.sort(key=lambda item: (item["views"], item["likes"]), reverse=True)
        return ranked[0]
