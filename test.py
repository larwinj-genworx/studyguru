import re
import time
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Optional
import sys
import urllib.parse

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )
}
TIMEOUT = 10
MAX_CONTENT_CHARS = 3000
MAX_WORKERS = 5


@dataclass
class ScrapedPage:
    rank: int
    url: str
    title: str = ""
    content: str = ""
    error: Optional[str] = None


# ──────────────────────────────────────────────
# Step 1: Search — tries multiple methods
# ──────────────────────────────────────────────
def search_web(query: str, top_k: int = 5) -> list[str]:
    """Try search methods in order until one works."""

    # Method 1: duckduckgo-search library (most reliable)
    urls = _ddgs_library_search(query, top_k)
    if urls:
        print(f"  [search] Found {len(urls)} URLs via duckduckgo-search library")
        return urls

    # Method 2: DuckDuckGo HTML POST (fallback)
    urls = _ddg_html_search(query, top_k)
    if urls:
        print(f"  [search] Found {len(urls)} URLs via DuckDuckGo HTML")
        return urls

    # Method 3: Bing HTML scrape (last resort)
    urls = _bing_search(query, top_k)
    if urls:
        print(f"  [search] Found {len(urls)} URLs via Bing")
        return urls

    print("  [error] All search methods failed.")
    return []


def _ddgs_library_search(query: str, top_k: int) -> list[str]:
    """Uses the `duckduckgo-search` pip package (DDGS)."""
    try:
        from duckduckgo_search import DDGS
        results = DDGS().text(query, max_results=top_k)
        return [r["href"] for r in results if "href" in r]
    except ImportError:
        print("  [info] duckduckgo-search not installed. Run: uv add duckduckgo-search")
        return []
    except Exception as e:
        print(f"  [warn] DDGS library error: {e}")
        return []


def _ddg_html_search(query: str, top_k: int) -> list[str]:
    """Scrapes DuckDuckGo HTML page — tries multiple selectors."""
    try:
        url = "https://html.duckduckgo.com/html/"
        resp = requests.post(url, data={"q": query}, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "lxml")
        links = []

        # Try multiple selectors — DDG changes their HTML periodically
        selectors = [
            "a.result__a",           # old selector
            "h2.result__title a",    # variant
            "a[href*='uddg=']",      # redirect links
            ".results a[href^='http']",  # generic
        ]

        for selector in selectors:
            for a in soup.select(selector):
                href = a.get("href", "")
                # Decode DDG redirect wrapper
                if "uddg=" in href:
                    match = re.search(r"uddg=(https?[^&]+)", href)
                    if match:
                        href = urllib.parse.unquote(match.group(1))
                if href.startswith("http") and "duckduckgo.com" not in href:
                    if href not in links:
                        links.append(href)
                if len(links) >= top_k:
                    break
            if links:
                break

        return links

    except Exception as e:
        print(f"  [warn] DDG HTML error: {e}")
        return []


def _bing_search(query: str, top_k: int) -> list[str]:
    """Scrapes Bing search results as last resort."""
    try:
        url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}&count={top_k}"
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "lxml")
        links = []

        for a in soup.select("li.b_algo h2 a"):
            href = a.get("href", "")
            if href.startswith("http") and "bing.com" not in href:
                links.append(href)
            if len(links) >= top_k:
                break

        return links

    except Exception as e:
        print(f"  [warn] Bing search error: {e}")
        return []


# ──────────────────────────────────────────────
# Step 2: Scrape a single URL
# ──────────────────────────────────────────────
def scrape_page(rank: int, url: str) -> ScrapedPage:
    page = ScrapedPage(rank=rank, url=url)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "lxml")

        # Remove noise tags
        for tag in soup(["script", "style", "nav", "footer", "header",
                          "aside", "form", "noscript", "iframe", "ads"]):
            tag.decompose()

        # Title
        page.title = soup.title.get_text(strip=True) if soup.title else url

        # Main content: prefer <article> or <main>, else <body>
        container = soup.find("article") or soup.find("main") or soup.body
        raw = (
            container.get_text(separator=" ", strip=True)
            if container
            else soup.get_text(separator=" ", strip=True)
        )

        # Clean whitespace
        clean = re.sub(r"\s{2,}", " ", raw).strip()
        page.content = clean[:MAX_CONTENT_CHARS]

    except Exception as e:
        page.error = str(e)

    return page


# ──────────────────────────────────────────────
# Step 3: Scrape all URLs in parallel
# ──────────────────────────────────────────────
def scrape_all(urls: list[str]) -> list[ScrapedPage]:
    results: list[Optional[ScrapedPage]] = [None] * len(urls)
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(scrape_page, i + 1, url): i
            for i, url in enumerate(urls)
        }
        for future in as_completed(futures):
            idx = futures[future]
            results[idx] = future.result()
    return results


# ──────────────────────────────────────────────
# Step 4: Format output
# ──────────────────────────────────────────────
def format_results(question: str, pages: list[ScrapedPage]) -> str:
    lines = [
        "=" * 60,
        f"Question : {question}",
        f"Sources  : {len(pages)} pages scraped",
        "=" * 60 + "\n",
    ]
    for page in pages:
        lines.append(f"[{page.rank}] {page.title}")
        lines.append(f"    URL: {page.url}")
        if page.error:
            lines.append(f"    ⚠ Error: {page.error}")
        else:
            lines.append(f"\n{page.content}\n")
        lines.append("-" * 60)
    return "\n".join(lines)


# ──────────────────────────────────────────────
# Main entry point
# ──────────────────────────────────────────────
def answer_question(question: str, top_k: int = 5) -> str:
    print(f"\nSearching: '{question}' (top {top_k} results)...")
    urls = search_web(question, top_k)

    if not urls:
        return "No URLs found. Check your internet connection or query."

    print(f"Found {len(urls)} URLs. Scraping in parallel...")
    t0 = time.time()
    pages = scrape_all(urls)
    elapsed = time.time() - t0
    print(f"Done in {elapsed:.1f}s\n")

    return format_results(question, pages)


# ──────────────────────────────────────────────
# CLI usage
# ──────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 2:
        question = input("Enter your question: ").strip()
    else:
        question = " ".join(sys.argv[1:])

    top_k = 5
    result = answer_question(question, top_k=top_k)
    print(result)