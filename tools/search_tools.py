"""
Search tools using DuckDuckGo (ddgs) — free, no API key.
Internal (proprietary) search is a local keyword-search placeholder; replace
with a real vector store when internal documents are available.
"""

import os
import queue
import threading

from ddgs import DDGS
from config import Config

# ``ddgs`` (via primp/TLS impersonation) can hang indefinitely on rate-limited
# or challenged responses, so run the search on a daemon thread with a hard
# timeout. A timed-out search returns a message instead of blocking the run.
WEB_SEARCH_TIMEOUT = 20


def web_search(query: str, max_results: int = 5, timeout: int = WEB_SEARCH_TIMEOUT) -> str:
    """
    Perform a web search using DuckDuckGo with a hard timeout.

    Returns a string of concatenated snippets, or a friendly failure/timed-out
    message so the pipeline can continue. Never blocks longer than ``timeout``.
    """
    result_queue = queue.Queue()

    def _run():
        try:
            with DDGS(timeout=min(timeout, 15)) as ddgs:
                results = ddgs.text(query, max_results=max_results)
            snippets = [result.get("body", "") for result in results]
            result_queue.put("\n".join(snippets) if snippets else "No results found.")
        except Exception as exc:  # noqa: BLE001 - surface any ddgs failure as text
            result_queue.put(f"DDGS search failed: {exc}")

    # Daemon thread: if the underlying client hangs, it cannot keep the process
    # alive past the timeout.
    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    try:
        return result_queue.get(timeout=timeout)
    except queue.Empty:
        return f"DDGS search timed out after {timeout}s"


def internal_search(query: str) -> str:
    """
    Placeholder for internal proprietary data search.

    Searches plain-text files under Config.INTERNAL_DOCS_DIR using simple
    keyword matching — no external API or embeddings required. Replace with a
    vector store when real internal documents are available.
    """
    docs_dir = Config.INTERNAL_DOCS_DIR
    if not os.path.isdir(docs_dir):
        return f"Internal search not configured: directory '{docs_dir}' not found."

    terms = [t.lower() for t in query.split() if len(t) > 2]
    if not terms:
        return "Internal search not configured: query has no searchable terms."

    matches = []
    for filename in sorted(os.listdir(docs_dir)):
        path = os.path.join(docs_dir, filename)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
        except OSError:
            continue
        lowered = text.lower()
        score = sum(1 for term in terms if term in lowered)
        if score:
            matches.append((score, filename, text))

    if not matches:
        return "No internal documents found."

    matches.sort(key=lambda m: (-m[0], m[1]))
    return "\n\n".join(
        f"[{filename}] (matched {score}/{len(terms)} terms)\n{text[:1000]}"
        for score, filename, text in matches[:3]
    )
