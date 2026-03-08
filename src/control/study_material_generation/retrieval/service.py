from __future__ import annotations

import asyncio
import logging
import math
import re
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from src.config.settings import Settings

from .models import EvidenceSnippet, SearchResult, SourceDocument, extract_domain, utc_now_iso

try:
    from ddgs import DDGS
except Exception:  # pragma: no cover - dependency is declared but keep runtime-safe
    try:
        from duckduckgo_search import DDGS  # type: ignore[no-redef]
    except Exception:
        DDGS = None  # type: ignore[assignment]

logger = logging.getLogger("uvicorn.error")


def _extract_literal_values(type_stub: str, alias_name: str) -> tuple[str, ...]:
    match = re.search(rf"{alias_name}\s*=\s*Literal\[(.*?)\]", type_stub, flags=re.DOTALL)
    if not match:
        return ()
    values = re.findall(r'"([^"]+)"|\'([^\']+)\'', match.group(1))
    flattened = [double or single for double, single in values if double or single]
    return tuple(dict.fromkeys(flattened))


def _load_primp_impersonation_support() -> tuple[tuple[str, ...], tuple[str, ...]]:
    try:
        import primp
    except Exception:
        return (), ()

    stub_path = Path(primp.__file__).with_name("primp.pyi")
    if not stub_path.exists():
        return (), ()

    try:
        stub_contents = stub_path.read_text(encoding="utf-8")
    except Exception:
        return (), ()

    return (
        _extract_literal_values(stub_contents, "IMPERSONATE"),
        _extract_literal_values(stub_contents, "IMPERSONATE_OS"),
    )


def _configure_ddgs_impersonation_compatibility() -> None:
    if DDGS is None or not getattr(DDGS, "__module__", "").startswith("ddgs"):
        return

    try:
        from ddgs.http_client import HttpClient
    except Exception:
        return

    supported_profiles, supported_os = _load_primp_impersonation_support()
    if not supported_profiles:
        return

    current_profiles = tuple(getattr(HttpClient, "_impersonates", ()) or ())
    current_os = tuple(getattr(HttpClient, "_impersonates_os", ()) or ())

    supported_profile_set = set(supported_profiles)
    supported_os_set = set(supported_os)

    compatible_profiles = tuple(profile for profile in current_profiles if profile in supported_profile_set)
    if not compatible_profiles:
        compatible_profiles = tuple(profile for profile in supported_profiles if profile != "random") or ("random",)

    compatible_os = tuple(os_name for os_name in current_os if os_name in supported_os_set)
    if not compatible_os:
        compatible_os = tuple(os_name for os_name in supported_os if os_name != "random")
    if not compatible_os:
        compatible_os = ("random",)

    if current_profiles == compatible_profiles and current_os == compatible_os:
        return

    HttpClient._impersonates = compatible_profiles
    HttpClient._impersonates_os = compatible_os
    logger.info(
        "[EvidenceRetrievalService] Patched DDGS impersonation compatibility. browsers=%s os=%s",
        ", ".join(compatible_profiles),
        ", ".join(compatible_os),
    )


_configure_ddgs_impersonation_compatibility()


class AccessRestrictedSourceError(RuntimeError):
    def __init__(self, status_code: int, domain: str) -> None:
        super().__init__(f"status={status_code}")
        self.status_code = status_code
        self.domain = domain


class SourceUnavailableError(RuntimeError):
    def __init__(self, domain: str, reason: str) -> None:
        super().__init__(reason)
        self.domain = domain
        self.reason = reason


class DeadSourceError(RuntimeError):
    def __init__(self, url: str, status_code: int | None = None, reason: str | None = None) -> None:
        message = reason or (f"status={status_code}" if status_code is not None else "dead_source")
        super().__init__(message)
        self.url = url
        self.status_code = status_code


class EvidenceRetrievalService:
    _TRUSTED_DOMAIN_SCORES = {
        "ncert.nic.in": 1.00,
        "cbseacademic.nic.in": 0.99,
        "khanacademy.org": 0.98,
        "ck12.org": 0.96,
        "openstax.org": 0.95,
        "britannica.com": 0.93,
        "mathsisfun.com": 0.91,
        "bbc.co.uk": 0.88,
        "bbc.com": 0.88,
        "wikipedia.org": 0.82,
    }
    _SEARCH_RESULT_BUFFER_MULTIPLIER = 4
    _SEARCH_RESULT_BUFFER_CAP = 12
    _ACCESS_RESTRICTED_STATUS_CODES = {401, 403, 429, 451}
    _DEAD_STATUS_CODES = {404, 410}
    _EXCLUDED_DOMAIN_SUFFIXES = (
        "studocu.com",
        "coursehero.com",
        "superprof.com",
        "superprof.ie",
        "scribd.com",
        "docsity.com",
    )
    _SOFT_404_MARKERS = (
        "page not found",
        "road ends here",
        "content no longer available",
        "this page does not exist",
        "sorry, we can't find",
        "sorry, we couldnt find",
        "lesson not found",
        "resource not found",
        "404 not found",
        "uh oh!",
    )
    _NOISE_SELECTORS = (
        "script",
        "style",
        "nav",
        "footer",
        "header",
        "aside",
        "form",
        "noscript",
        "iframe",
        "svg",
        "canvas",
        ".ads",
        ".advertisement",
        ".promo",
        ".related",
        ".sidebar",
        ".cookie",
        ".breadcrumbs",
    )

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def gather(
        self,
        *,
        subject_name: str,
        grade_level: str,
        concept_name: str,
        concept_description: str | None = None,
        query_focus: str | None = None,
    ) -> dict[str, Any]:
        logger.info(
            "[EvidenceRetrievalService] Started evidence retrieval for subject='%s' concept='%s'.",
            subject_name,
            concept_name,
        )
        queries = self._build_queries(
            subject_name=subject_name,
            grade_level=grade_level,
            concept_name=concept_name,
            concept_description=concept_description,
            query_focus=query_focus,
        )
        search_results = await self._search_queries(
            queries,
            max_results_per_query=max(self.settings.evidence_search_results_per_query, 1),
        )
        logger.info(
            "[EvidenceRetrievalService] Search completed for concept='%s'. queries=%d candidates=%d",
            concept_name,
            len(queries),
            len(search_results),
        )
        fetch_candidate_limit = max(self.settings.evidence_max_sources * 2, 8)
        access_restricted_domains: set[str] = set()
        unavailable_domains: set[str] = set()
        dead_urls: set[str] = set()
        documents = await self._fetch_documents(
            search_results[:fetch_candidate_limit],
            access_restricted_domains=access_restricted_domains,
            unavailable_domains=unavailable_domains,
            dead_urls=dead_urls,
        )
        logger.info(
            (
                "[EvidenceRetrievalService] Scraping process completed for concept='%s'. "
                "selected=%d full_content=%d snippet_only=%d access_restricted=%d "
                "source_unavailable=%d non_html=%d dead_urls=%d"
            ),
            concept_name,
            len(documents),
            self._count_documents_by_status(documents, "full_content"),
            self._count_documents_by_status(documents, "search_snippet_only"),
            self._count_documents_by_status(documents, "access_restricted"),
            self._count_documents_by_status(documents, "source_unavailable"),
            self._count_documents_by_status(documents, "non_html_snippet"),
            len(dead_urls),
        )
        ranked_snippets = self._rank_snippets(
            query=f"{grade_level} {subject_name} {concept_name}",
            documents=documents[: self.settings.evidence_max_sources],
            max_snippets=max(self.settings.evidence_max_snippets, 4),
        )
        selected_documents = documents[: self.settings.evidence_max_sources]
        references = self._build_references(selected_documents, search_results, excluded_urls=dead_urls)
        retrieval_status = self._resolve_retrieval_status(selected_documents, ranked_snippets, references)
        for document in selected_documents:
            logger.info(
                "[EvidenceRetrievalService] Scraped link for concept='%s'. status=%s url=%s",
                concept_name,
                document.retrieval_status,
                document.url,
            )
        for reference in references[:8]:
            logger.info(
                "[EvidenceRetrievalService] Reference link for concept='%s'. url=%s",
                concept_name,
                str(reference.get("url", "")).strip(),
            )
        logger.info(
            (
                "[EvidenceRetrievalService] Evidence packaging completed for concept='%s'. "
                "retrieval_status=%s source_documents=%d evidence_snippets=%d references=%d"
            ),
            concept_name,
            retrieval_status,
            len(selected_documents),
            len(ranked_snippets),
            len(references),
        )
        return {
            "query_variants": queries,
            "retrieved_at": utc_now_iso(),
            "retrieval_status": retrieval_status,
            "source_documents": [doc.to_dict() for doc in selected_documents],
            "evidence_snippets": [snippet.to_dict() for snippet in ranked_snippets[: self.settings.evidence_max_snippets]],
            "coverage_summary": self._build_coverage_summary(selected_documents, ranked_snippets),
            "references": references[:8],
        }

    def _build_queries(
        self,
        *,
        subject_name: str,
        grade_level: str,
        concept_name: str,
        concept_description: str | None,
        query_focus: str | None,
    ) -> list[str]:
        description = (concept_description or "").strip()
        focus = " ".join((query_focus or "").split()).strip()
        normalized_grade = grade_level.strip()
        normalized_subject = subject_name.strip()
        normalized_concept = concept_name.strip()
        queries = [
            f"{normalized_grade} {normalized_subject} {normalized_concept} explained",
            f"{normalized_grade} {normalized_subject} {normalized_concept} formulas examples",
            f"{normalized_subject} {normalized_concept} lesson for {normalized_grade}",
        ]
        if focus:
            queries.insert(1, f"{normalized_subject} {normalized_concept} {focus[:100]}")
        if description:
            queries.append(f"{normalized_subject} {normalized_concept} {description[:80]}")
        deduped: list[str] = []
        seen: set[str] = set()
        for query in queries:
            cleaned = " ".join(query.split()).strip()
            key = cleaned.lower()
            if not cleaned or key in seen:
                continue
            seen.add(key)
            deduped.append(cleaned)
        return deduped[:3]

    async def _search_queries(self, queries: list[str], max_results_per_query: int) -> list[SearchResult]:
        if DDGS is None:
            logger.warning("[EvidenceRetrievalService] duckduckgo_search is unavailable.")
            return []

        collected: list[SearchResult] = []
        seen_urls: set[str] = set()
        for query in queries:
            try:
                query_result = await asyncio.to_thread(self._search_single_query, query, max_results_per_query)
            except Exception as exc:
                logger.warning("[EvidenceRetrievalService] Search query failed for '%s': %s", query, exc)
                continue
            for item in query_result:
                canonical = self._canonical_url(item.url)
                if not canonical or canonical in seen_urls:
                    continue
                seen_urls.add(canonical)
                item.url = canonical
                collected.append(item)
        collected.sort(key=lambda item: (-item.domain_score, item.rank))
        return collected

    def _search_single_query(self, query: str, max_results: int) -> list[SearchResult]:
        requested_results = min(
            max(max_results * self._SEARCH_RESULT_BUFFER_MULTIPLIER, max_results),
            self._SEARCH_RESULT_BUFFER_CAP,
        )
        try:
            raw_results = list(
                DDGS(timeout=max(self.settings.resource_search_timeout_seconds, 5)).text(
                    query,
                    max_results=requested_results,
                )
            )
        except Exception as exc:
            logger.warning("[EvidenceRetrievalService] DDGS search failed for '%s': %s", query, exc)
            return []

        results: list[SearchResult] = []
        for index, item in enumerate(raw_results, start=1):
            if not isinstance(item, dict):
                continue
            url = str(item.get("href") or item.get("url") or "").strip()
            title = str(item.get("title") or "").strip()
            snippet = str(item.get("body") or item.get("snippet") or "").strip()
            if not url or not title:
                continue
            domain = extract_domain(url)
            results.append(
                SearchResult(
                    title=title[:180],
                    url=url,
                    snippet=snippet[:500],
                    rank=index,
                    query=query,
                    domain=domain,
                    domain_score=self._score_domain(domain),
                )
            )
            candidate = results[-1]
            if not self._is_fetchable_candidate(candidate):
                results.pop()
                continue
            if len(results) >= max_results:
                break
        return results

    async def _fetch_documents(
        self,
        search_results: list[SearchResult],
        *,
        access_restricted_domains: set[str],
        unavailable_domains: set[str],
        dead_urls: set[str],
    ) -> list[SourceDocument]:
        if not search_results:
            return []

        timeout = httpx.Timeout(max(self.settings.resource_search_timeout_seconds, 8))
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        }
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=headers) as client:
            tasks = [
                self._fetch_document(
                    client,
                    result,
                    access_restricted_domains=access_restricted_domains,
                    unavailable_domains=unavailable_domains,
                    dead_urls=dead_urls,
                )
                for result in search_results
            ]
            resolved = await asyncio.gather(*tasks, return_exceptions=True)

        documents: list[SourceDocument] = []
        for fallback, item in zip(search_results, resolved, strict=False):
            if isinstance(item, SourceDocument):
                documents.append(item)
            elif isinstance(item, DeadSourceError):
                dead_urls.add(fallback.url)
            elif isinstance(item, AccessRestrictedSourceError):
                access_restricted_domains.add(fallback.domain)
            elif isinstance(item, SourceUnavailableError):
                unavailable_domains.add(fallback.domain)
            else:
                message = str(item) if isinstance(item, Exception) else "fetch_failed"
                logger.warning(
                    "[EvidenceRetrievalService] Document fetch failed for '%s': %s",
                    fallback.url,
                    message,
                )
                if fallback.snippet:
                    documents.append(
                        SourceDocument(
                            title=fallback.title,
                            url=fallback.url,
                            domain=fallback.domain,
                            rank=fallback.rank,
                            query=fallback.query,
                            snippet=fallback.snippet,
                            content_excerpt=fallback.snippet,
                            retrieval_status="search_snippet_only",
                            quality_score=max(0.45, fallback.domain_score * 0.75),
                            content_length=len(fallback.snippet),
                            retrieved_at=utc_now_iso(),
                            provider=fallback.provider,
                            source_type="search_result",
                        )
                    )
        documents.sort(key=lambda doc: (-doc.quality_score, doc.rank))
        return documents

    async def _fetch_document(
        self,
        client: httpx.AsyncClient,
        result: SearchResult,
        *,
        access_restricted_domains: set[str],
        unavailable_domains: set[str],
        dead_urls: set[str],
    ) -> SourceDocument:
        if result.url in dead_urls:
            raise DeadSourceError(url=result.url, reason="dead_source_cached")
        if result.domain in access_restricted_domains:
            if result.snippet:
                return self._build_search_snippet_document(result, retrieval_status="access_restricted")
            raise AccessRestrictedSourceError(status_code=403, domain=result.domain)
        if result.domain in unavailable_domains:
            if result.snippet:
                return self._build_search_snippet_document(result, retrieval_status="source_unavailable")
            raise SourceUnavailableError(domain=result.domain, reason="source_unavailable")

        try:
            response = await client.get(result.url)
        except (httpx.TimeoutException, httpx.RequestError, OSError) as exc:
            unavailable_domains.add(result.domain)
            if result.snippet:
                return self._build_search_snippet_document(result, retrieval_status="source_unavailable")
            raise SourceUnavailableError(domain=result.domain, reason=str(exc)) from exc
        content_type = (response.headers.get("content-type") or "").lower()
        if response.status_code in self._DEAD_STATUS_CODES:
            dead_urls.add(result.url)
            raise DeadSourceError(url=result.url, status_code=response.status_code)
        if response.status_code in self._ACCESS_RESTRICTED_STATUS_CODES:
            access_restricted_domains.add(result.domain)
            if result.snippet:
                return self._build_search_snippet_document(result, retrieval_status="access_restricted")
            raise AccessRestrictedSourceError(status_code=response.status_code, domain=result.domain)
        if response.status_code >= 400:
            raise RuntimeError(f"status={response.status_code}")

        if "html" not in content_type and "text" not in content_type:
            excerpt = result.snippet or result.title
            return SourceDocument(
                title=result.title,
                url=result.url,
                domain=result.domain,
                rank=result.rank,
                query=result.query,
                snippet=result.snippet,
                content_excerpt=excerpt[:1400],
                retrieval_status="non_html_snippet",
                quality_score=max(0.42, result.domain_score * 0.72),
                content_length=len(excerpt),
                retrieved_at=utc_now_iso(),
                provider=result.provider,
                source_type="document",
            )

        html = response.text
        title, body = self._extract_main_text(html)
        if self._looks_like_soft_404(title=title, body=body):
            dead_urls.add(result.url)
            raise DeadSourceError(url=result.url, status_code=response.status_code, reason="soft_404")
        excerpt = body[:3000] if body else result.snippet
        quality = self._score_document_quality(
            domain_score=result.domain_score,
            content_length=len(excerpt),
            snippet_present=bool(result.snippet),
        )
        status = "full_content" if body else "search_snippet_only"
        return SourceDocument(
            title=(title or result.title or "Resource")[:180],
            url=result.url,
            domain=result.domain,
            rank=result.rank,
            query=result.query,
            snippet=result.snippet,
            content_excerpt=excerpt,
            retrieval_status=status,
            quality_score=quality,
            content_length=len(excerpt),
            retrieved_at=utc_now_iso(),
            provider=result.provider,
            source_type="webpage",
        )

    @classmethod
    def _is_fetchable_candidate(cls, result: SearchResult) -> bool:
        if not result.url or not result.domain:
            return False
        return not cls._is_excluded_domain(result.domain)

    @classmethod
    def _is_excluded_domain(cls, domain: str) -> bool:
        normalized = domain.strip().lower()
        if not normalized:
            return True
        return any(
            normalized == suffix or normalized.endswith(f".{suffix}")
            for suffix in cls._EXCLUDED_DOMAIN_SUFFIXES
        )

    @staticmethod
    def _build_search_snippet_document(result: SearchResult, *, retrieval_status: str) -> SourceDocument:
        return SourceDocument(
            title=result.title,
            url=result.url,
            domain=result.domain,
            rank=result.rank,
            query=result.query,
            snippet=result.snippet,
            content_excerpt=result.snippet,
            retrieval_status=retrieval_status,
            quality_score=max(0.45, result.domain_score * 0.72),
            content_length=len(result.snippet),
            retrieved_at=utc_now_iso(),
            provider=result.provider,
            source_type="search_result",
        )

    def _extract_main_text(self, html: str) -> tuple[str, str]:
        soup = BeautifulSoup(html, "lxml")
        for selector in self._NOISE_SELECTORS:
            for node in soup.select(selector):
                node.decompose()

        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        container = (
            soup.find("article")
            or soup.find("main")
            or soup.select_one("[role='main']")
            or soup.select_one(".content")
            or soup.select_one(".post-content")
            or soup.body
        )
        if container is None:
            return title, ""

        texts: list[str] = []
        for node in container.find_all(["h1", "h2", "h3", "p", "li"], limit=120):
            text = node.get_text(" ", strip=True)
            cleaned = self._clean_text(text)
            if len(cleaned) < 35:
                continue
            texts.append(cleaned)

        if not texts:
            body = self._clean_text(container.get_text(" ", strip=True))
            return title, body[:3000]

        deduped: list[str] = []
        seen: set[str] = set()
        for text in texts:
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(text)
        return title, " ".join(deduped)[:6000]

    def _rank_snippets(
        self,
        *,
        query: str,
        documents: list[SourceDocument],
        max_snippets: int,
    ) -> list[EvidenceSnippet]:
        candidates: list[tuple[SourceDocument, str, str]] = []
        for document in documents:
            if document.content_excerpt:
                for chunk in self._chunk_text(document.content_excerpt):
                    candidates.append((document, chunk, "content"))
            elif document.snippet:
                candidates.append((document, document.snippet, "search_snippet"))
            if document.snippet:
                candidates.append((document, document.snippet, "search_snippet"))

        if not candidates:
            return []

        texts = [chunk for _, chunk, _ in candidates]
        try:
            vectorizer = TfidfVectorizer(stop_words="english")
            matrix = vectorizer.fit_transform([query, *texts])
            scores = cosine_similarity(matrix[0:1], matrix[1:]).flatten()
        except Exception as exc:
            logger.warning("[EvidenceRetrievalService] TF-IDF ranking failed: %s", exc)
            scores = [0.0 for _ in texts]

        ranked: list[EvidenceSnippet] = []
        seen_keys: set[str] = set()
        for index, ((document, chunk, snippet_type), relevance) in enumerate(
            sorted(
                zip(candidates, scores, strict=False),
                key=lambda item: (
                    item[1] + item[0][0].quality_score * 0.35 + self._rank_bonus(item[0][0].rank),
                    item[0][0].quality_score,
                ),
                reverse=True,
            ),
            start=1,
        ):
            text = self._clean_text(chunk)[:420]
            if len(text) < 40:
                continue
            key = f"{document.url}|{text.lower()}"
            if key in seen_keys:
                continue
            seen_keys.add(key)
            score = float(relevance) + document.quality_score * 0.35 + self._rank_bonus(document.rank)
            ranked.append(
                EvidenceSnippet(
                    text=text,
                    source_url=document.url,
                    source_title=document.title,
                    domain=document.domain,
                    query=document.query,
                    score=score,
                    snippet_type=snippet_type,
                )
            )
            if len(ranked) >= max_snippets:
                break
        return ranked

    def _chunk_text(self, text: str, max_chars: int = 520) -> Iterable[str]:
        paragraphs = [
            self._clean_text(part)
            for part in re.split(r"(?<=[.!?])\s+", text)
            if self._clean_text(part)
        ]
        if not paragraphs:
            return []

        chunks: list[str] = []
        current = ""
        for paragraph in paragraphs:
            if len(paragraph) > max_chars:
                paragraph = paragraph[:max_chars]
            if not current:
                current = paragraph
                continue
            if len(current) + len(paragraph) + 1 <= max_chars:
                current = f"{current} {paragraph}"
            else:
                chunks.append(current)
                current = paragraph
        if current:
            chunks.append(current)
        return chunks

    def _build_references(
        self,
        documents: list[SourceDocument],
        search_results: list[SearchResult],
        *,
        excluded_urls: set[str] | None = None,
    ) -> list[dict[str, str]]:
        references: list[dict[str, str]] = []
        seen_urls: set[str] = set()
        excluded = excluded_urls or set()
        for document in documents:
            if document.url in seen_urls or document.url in excluded:
                continue
            seen_urls.add(document.url)
            references.append(document.to_reference())
            if len(references) >= 6:
                return references
        for result in search_results:
            if result.url in seen_urls or result.url in excluded:
                continue
            seen_urls.add(result.url)
            note = f"{result.domain or 'web'} | search result"
            references.append(
                {
                    "title": result.title[:120] or "Resource",
                    "url": result.url,
                    "note": note[:240],
                }
            )
            if len(references) >= 6:
                break
        return references

    def _build_coverage_summary(
        self,
        documents: list[SourceDocument],
        snippets: list[EvidenceSnippet],
    ) -> str:
        if not documents and not snippets:
            return "No external evidence could be extracted; generation should use cautious fallback phrasing."
        source_titles = [doc.title for doc in documents[:3] if doc.title]
        snippet_domains = [snippet.domain for snippet in snippets[:4] if snippet.domain]
        domain_text = ", ".join(dict.fromkeys(snippet_domains)) or "web sources"
        title_text = "; ".join(source_titles) or "retrieved sources"
        return (
            f"Grounded from {max(len(documents), len(snippets))} retrieved evidence items. "
            f"Primary sources include {title_text}. Dominant source domains: {domain_text}."
        )[:420]

    @staticmethod
    def _resolve_retrieval_status(
        documents: list[SourceDocument],
        snippets: list[EvidenceSnippet],
        references: list[dict[str, str]],
    ) -> str:
        if documents and snippets:
            return "grounded"
        if snippets or references:
            return "partial"
        return "fallback"

    @classmethod
    def _score_domain(cls, domain: str) -> float:
        if not domain:
            return 0.45
        for trusted_domain, score in cls._TRUSTED_DOMAIN_SCORES.items():
            if domain == trusted_domain or domain.endswith(f".{trusted_domain}"):
                return score
        if domain.endswith(".edu") or domain.endswith(".gov"):
            return 0.92
        if domain.endswith(".org"):
            return 0.78
        return 0.60

    @staticmethod
    def _score_document_quality(*, domain_score: float, content_length: int, snippet_present: bool) -> float:
        length_bonus = min(content_length / 3200, 1.0) * 0.18
        snippet_bonus = 0.04 if snippet_present else 0.0
        return min(domain_score * 0.78 + length_bonus + snippet_bonus, 0.99)

    @staticmethod
    def _count_documents_by_status(documents: list[SourceDocument], status: str) -> int:
        return sum(1 for document in documents if document.retrieval_status == status)

    @classmethod
    def _looks_like_soft_404(cls, *, title: str, body: str) -> bool:
        haystack = f"{title} {body[:1200]}".strip().lower()
        if not haystack:
            return False
        return any(marker in haystack for marker in cls._SOFT_404_MARKERS)

    @staticmethod
    def _rank_bonus(rank: int) -> float:
        if rank <= 1:
            return 0.12
        if rank == 2:
            return 0.08
        if rank == 3:
            return 0.05
        return max(0.01, 0.04 - math.log(rank + 1, 10) * 0.02)

    @staticmethod
    def _clean_text(value: str) -> str:
        cleaned = re.sub(r"\s+", " ", str(value or "")).strip()
        return cleaned

    @staticmethod
    def _canonical_url(url: str) -> str:
        try:
            parsed = urlparse(url.strip())
        except Exception:
            return ""
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return ""
        query_pairs = [
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=False)
            if not key.lower().startswith(("utm_", "ref", "fbclid", "gclid"))
        ]
        normalized = parsed._replace(query=urlencode(query_pairs), fragment="")
        return urlunparse(normalized)
