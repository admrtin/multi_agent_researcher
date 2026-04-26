from __future__ import annotations

import json
import os
import re
import shutil
import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from functools import lru_cache

import requests
from dotenv import load_dotenv
from google import genai

load_dotenv()

SEMANTIC_SCHOLAR_API_KEY = os.getenv("SEMANTIC_SCHOLAR_API_KEY")
PAPERS_DIR = Path("papers")


def stream_terminal_update(
    message: str,
    content_type: str = "info",
    agent_name: str = "SYSTEM",
) -> str:
    """
    Prints a colorized, immediate progress message to terminal output.
    Useful when running `adk run .` so users can see streaming status updates.
    """
    color_map = {
        "info": "\033[96m",
        "step": "\033[94m",
        "success": "\033[92m",
        "warning": "\033[93m",
        "error": "\033[91m",
        "planner": "\033[95m",
        "researcher": "\033[36m",
        "validator": "\033[33m",
        "synthesizer": "\033[35m",
    }
    reset = "\033[0m"

    key = (content_type or "info").strip().lower()
    color = color_map.get(key, color_map["info"])
    prefix = f"[{agent_name}:{key.upper()}]"
    rendered = f"{color}{prefix} {message}{reset}"

    print(rendered, flush=True)

    return f"{prefix} {message}"


def _slugify_filename(value: str, max_length: int = 100) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value.lower()).strip("_")
    return slug[:max_length] if slug else "item"


def _safe_path_with_limited_name(path: Path, max_name_length: int = 180) -> Path:
    """Truncates the filename portion of a path to avoid OS filename-length errors."""
    name = path.name
    if len(name) <= max_name_length:
        return path

    suffix = "".join(path.suffixes) if path.suffixes else ""
    stem = path.name[: -len(suffix)] if suffix else path.name
    base_name = stem[: max(1, max_name_length - len(suffix))]
    return path.with_name(f"{base_name}{suffix}")


def build_researcher_output_identity(researcher_id: str, paper_title: str) -> str:
    """
    Builds a stable, paper-specific output identity used in folder names,
    filenames, and the content of researcher artifacts.
    """
    title_slug = _slugify_filename(paper_title, max_length=32)
    researcher_slug = _slugify_filename(researcher_id, max_length=16)
    digest = hashlib.sha1(f"{researcher_id}:{paper_title}".encode("utf-8")).hexdigest()[:8]
    return f"{researcher_slug}_{title_slug}_{digest}"


def build_planner_output_identity(topic: str) -> str:
    """
    Builds a stable planner topic identity used in folder names, filenames,
    and the content of planner artifacts.
    """
    topic_slug = _slugify_filename(topic, max_length=70)
    digest = hashlib.sha1(topic.encode("utf-8")).hexdigest()[:8]
    return f"{topic_slug}_{digest}"


def _default_planning_aspects() -> list[tuple[str, str]]:
    return [
        ("A01", "Sampling-Based Motion Planning"),
        ("A02", "Optimization and Trajectory Planning"),
        ("A03", "Model Predictive Control"),
        ("A04", "Robust and Adaptive Control"),
        ("A05", "Model-Free Reinforcement Learning"),
        ("A06", "Model-Based Reinforcement Learning"),
        ("A07", "Sim-to-Real and Generalization"),
        ("A08", "Multi-Robot Coordination and Safety"),
    ]


def execute_planner_pipeline(
    topic: str,
    max_selected_papers: int = 8,
    max_aspects: int = 8,
) -> str:
    """
    Deterministic planner setup used to avoid prompt-only orchestration failures.

    It creates planner artifacts and shared state, then returns selected papers
    for downstream researcher spawning.
    """
    safe_max_papers = max(1, min(max_selected_papers, 12))
    safe_max_aspects = max(1, min(max_aspects, 8))

    # Always start from a clean output workspace for a fresh run.
    reset_output_workspace(outputs_dir="outputs")

    output_id = build_planner_output_identity(topic)
    planner_run_dir = create_run_output_dir(
        base_dir="outputs/planner_outputs",
        keep_last=3,
        run_name=output_id,
    )

    raw_search = scrape_research_articles(
        topic=topic,
        max_results=max(10, safe_max_papers),
        max_references_per_paper=5,
    )

    try:
        search_payload = json.loads(raw_search)
    except json.JSONDecodeError:
        search_payload = {"status": "error", "papers": [], "message": "Invalid search payload."}

    papers = search_payload.get("papers", []) if isinstance(search_payload, dict) else []
    unique_papers: list[dict[str, Any]] = []
    seen_titles: set[str] = set()
    for paper in papers:
        if not isinstance(paper, dict):
            continue
        title = str(paper.get("title", "")).strip()
        if not title:
            continue
        title_key = title.lower()
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)
        unique_papers.append(
            {
                "paper_title": title,
                "paper_url": paper.get("url") or "",
                "year": paper.get("year"),
                "source": paper.get("source") or search_payload.get("source") or "unknown",
            }
        )
        if len(unique_papers) >= safe_max_papers:
            break

    aspects_catalog = _default_planning_aspects()[:safe_max_aspects]
    aspect_records: list[dict[str, Any]] = []
    planner_overview_file = Path(planner_run_dir) / f"{output_id}_planning_overview.md"
    for index, (aspect_id, aspect_title) in enumerate(aspects_catalog, start=1):
        selected_for_aspect = [
            paper
            for paper_idx, paper in enumerate(unique_papers)
            if paper_idx % safe_max_aspects == (index - 1) % safe_max_aspects
        ]

        if not selected_for_aspect and unique_papers:
            selected_for_aspect = [unique_papers[(index - 1) % len(unique_papers)]]

        aspect_records.append(
            {
                "aspect_id": aspect_id,
                "aspect_title": aspect_title,
                "aspect_file": planner_overview_file.as_posix(),
                "seed_papers": selected_for_aspect,
            }
        )

    overview_lines: list[str] = [
        f"# Planner Overview ({output_id})",
        "",
        f"- Topic: {topic}",
        f"- Planner run dir: {planner_run_dir}",
        f"- Source: {search_payload.get('source', 'unknown') if isinstance(search_payload, dict) else 'unknown'}",
        "",
        "## Aspect Summary and Papers",
        "",
    ]

    for idx, aspect in enumerate(aspect_records, start=1):
        overview_lines.append(f"### Aspect {idx:02d}: {aspect.get('aspect_title', '')} ({aspect.get('aspect_id', '')})")
        seed_papers = aspect.get("seed_papers", [])
        if isinstance(seed_papers, list) and seed_papers:
            for paper in seed_papers:
                if not isinstance(paper, dict):
                    continue
                title = str(paper.get("paper_title", "Unknown title"))
                year = paper.get("year")
                url = str(paper.get("paper_url", ""))
                year_text = f" ({year})" if year else ""
                overview_lines.append(f"- {title}{year_text} - {url or 'no-url'}")
        else:
            overview_lines.append("- No seed papers available.")
        overview_lines.append("")

    save_markdown_file(planner_overview_file.as_posix(), "\n".join(overview_lines).strip() + "\n")

    canonical_manifest_path = Path(planner_run_dir) / "planner_manifest.json"
    prefixed_manifest_path = Path(planner_run_dir) / f"{output_id}_planner_manifest.json"

    init_shared = initialize_shared_run(
        planner_topic=topic,
        planner_manifest_path=canonical_manifest_path.as_posix(),
        base_dir="outputs/shared_runs",
        keep_last=3,
    )

    try:
        init_payload = json.loads(init_shared)
    except json.JSONDecodeError:
        init_payload = {}

    shared_state_file = init_payload.get("shared_state_file", "") if isinstance(init_payload, dict) else ""

    manifest = {
        "output_id": output_id,
        "topic": topic,
        "planner_run_dir": planner_run_dir,
        "planner_overview_file": planner_overview_file.as_posix(),
        "shared_state_file": shared_state_file,
        "source": search_payload.get("source", "unknown") if isinstance(search_payload, dict) else "unknown",
        "search_status": search_payload.get("status", "unknown") if isinstance(search_payload, dict) else "unknown",
        "aspects": aspect_records,
        "research_assignments": [],
    }

    save_json_file(canonical_manifest_path.as_posix(), manifest)
    save_json_file(prefixed_manifest_path.as_posix(), manifest)

    selected_papers: list[dict[str, Any]] = []
    for aspect in aspect_records:
        aspect_id = str(aspect.get("aspect_id", ""))
        aspect_title = str(aspect.get("aspect_title", ""))
        for paper in aspect.get("seed_papers", []):
            if not isinstance(paper, dict):
                continue
            selected_papers.append(
                {
                    "aspect_id": aspect_id,
                    "aspect_title": aspect_title,
                    "paper_title": paper.get("paper_title", ""),
                    "paper_url": paper.get("paper_url", ""),
                }
            )

    deduped: list[dict[str, Any]] = []
    seen_selected: set[str] = set()
    for record in selected_papers:
        title = str(record.get("paper_title", "")).strip()
        if not title:
            continue
        key = title.lower()
        if key in seen_selected:
            continue
        seen_selected.add(key)
        deduped.append(record)
        if len(deduped) >= safe_max_papers:
            break

    prepared_assignments: list[dict[str, Any]] = []
    pre_registered_count = 0
    pre_registration_errors: list[str] = []

    for index, record in enumerate(deduped, start=1):
        researcher_id = f"researcher_{index:02d}"
        assignment = {
            "researcher_id": researcher_id,
            "aspect_id": str(record.get("aspect_id", "")),
            "aspect_title": str(record.get("aspect_title", "")),
            "paper_title": str(record.get("paper_title", "")),
            "paper_url": str(record.get("paper_url", "")),
        }
        prepared_assignments.append(assignment)
        record["researcher_id"] = researcher_id

        if not shared_state_file:
            pre_registration_errors.append(f"missing shared_state_file for {researcher_id}")
            continue

        try:
            register_raw = register_planner_assignment(
                shared_state_file=shared_state_file,
                researcher_id=assignment["researcher_id"],
                aspect_id=assignment["aspect_id"],
                aspect_title=assignment["aspect_title"],
                paper_title=assignment["paper_title"],
                paper_url=assignment["paper_url"],
            )
            register_payload = json.loads(register_raw)
            if isinstance(register_payload, dict) and register_payload.get("status") == "success":
                pre_registered_count += 1
            else:
                pre_registration_errors.append(f"register failed for {researcher_id}")
        except Exception as exc:
            pre_registration_errors.append(f"register failed for {researcher_id}: {exc}")

    manifest["research_assignments"] = prepared_assignments
    save_json_file(canonical_manifest_path.as_posix(), manifest)
    save_json_file(prefixed_manifest_path.as_posix(), manifest)

    return json.dumps(
        {
            "status": "success",
            "output_id": output_id,
            "planner_run_dir": planner_run_dir,
            "planner_manifest": canonical_manifest_path.as_posix(),
            "planner_manifest_prefixed": prefixed_manifest_path.as_posix(),
            "planner_overview_file": planner_overview_file.as_posix(),
            "shared_state_file": shared_state_file,
            "selected_papers": deduped,
            "selected_paper_count": len(deduped),
            "pre_registered_count": pre_registered_count,
            "pre_registration_errors": pre_registration_errors,
            "aspect_count": len(aspect_records),
            "search_message": search_payload.get("message", "") if isinstance(search_payload, dict) else "",
        },
        indent=2,
    )


def planner_synthesis_fallback(shared_state_file: str) -> str:
    """
    Hard planner fallback checker.

    If researcher outputs exist but synthesis outputs are missing, this returns
    an explicit action instructing planner to invoke the synthesizer.
    """
    state_path = Path(shared_state_file)
    state = _load_json_object(state_path)

    assignments = state.get("assignments", []) if isinstance(state, dict) else []
    research_outputs = state.get("research_outputs", []) if isinstance(state, dict) else []
    synthesis_outputs = state.get("synthesis_outputs", []) if isinstance(state, dict) else []

    assignment_count = len(assignments) if isinstance(assignments, list) else 0
    research_count = len(research_outputs) if isinstance(research_outputs, list) else 0
    synthesis_count = len(synthesis_outputs) if isinstance(synthesis_outputs, list) else 0

    if research_count > 0 and synthesis_count == 0:
        return json.dumps(
            {
                "status": "success",
                "action": "invoke_synthesizer",
                "reason": "research_outputs_exist_but_synthesis_missing",
                "assignment_count": assignment_count,
                "research_output_count": research_count,
                "synthesis_output_count": synthesis_count,
            },
            indent=2,
        )

    return json.dumps(
        {
            "status": "success",
            "action": "no_action",
            "reason": "synthesis_present_or_no_research_outputs",
            "assignment_count": assignment_count,
            "research_output_count": research_count,
            "synthesis_output_count": synthesis_count,
        },
        indent=2,
    )


def _download_binary_file(url: str, destination: Path) -> bool:
    try:
        response = requests.get(
            url,
            timeout=60,
            headers={"User-Agent": "Mozilla/5.0 (multi-agent-researcher)"},
        )
        response.raise_for_status()
        content_type = (response.headers.get("content-type") or "").lower()
        body = response.content
        if "pdf" not in content_type and not body.startswith(b"%PDF") and not url.lower().endswith(".pdf"):
            return False
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(body)
        return True
    except requests.RequestException:
        return False


def _extract_pdf_text(pdf_path: Path, max_pages: int = 12, max_chars: int = 20000) -> str:
    try:
        from pypdf import PdfReader
    except Exception:
        return ""

    try:
        reader = PdfReader(str(pdf_path))
    except Exception:
        return ""

    extracted: list[str] = []
    for page in reader.pages[:max_pages]:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        if text:
            extracted.append(text.strip())
        if sum(len(part) for part in extracted) >= max_chars:
            break

    combined = "\n\n".join(extracted).strip()
    return combined[:max_chars]


def _search_arxiv_paper(paper_title: str, max_results: int = 5) -> list[dict[str, Any]]:
    try:
        import arxiv
    except Exception:
        return []

    query = _normalize_search_topic(paper_title)
    try:
        search = arxiv.Search(
            query=f'ti:"{query}"',
            max_results=max_results,
            sort_by=arxiv.SortCriterion.Relevance,
        )
        results = list(search.results())
    except Exception:
        return []

    papers: list[dict[str, Any]] = []
    for result in results:
        pdf_url = getattr(result, "pdf_url", "") or ""
        entry_id = getattr(result, "entry_id", "") or ""
        arxiv_id = (result.get_short_id() if hasattr(result, "get_short_id") else "") or ""
        title = getattr(result, "title", "Unknown Title") or "Unknown Title"
        summary = getattr(result, "summary", "") or ""
        authors = [author.name for author in getattr(result, "authors", [])[:10]]
        published = getattr(result, "published", None)
        year = getattr(published, "year", None) if published else None

        papers.append(
            {
                "title": title,
                "year": year,
                "venue": "arXiv",
                "url": entry_id or pdf_url,
                "authors": authors,
                "abstract": summary or "No abstract available.",
                "reference_count": 0,
                "references": [],
                "source": "arxiv",
                "arxiv_id": arxiv_id,
                "pdf_url": pdf_url,
            }
        )

    return papers


def _extract_duckduckgo_result_links(html: str) -> list[str]:
    links: list[str] = []
    for match in re.finditer(r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"', html):
        href = match.group(1)
        if href:
            links.append(href)
    return links


def _decode_duckduckgo_redirect(url: str) -> str:
    from urllib.parse import parse_qs, unquote, urlparse

    if "duckduckgo.com/l/?" not in url and "duckduckgo.com/l/?kh=" not in url:
        return url

    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    if "uddg" in query and query["uddg"]:
        return unquote(query["uddg"][0])
    return url


def _search_web_paper_candidates(paper_title: str, max_results: int = 10) -> list[dict[str, Any]]:
    query = _normalize_search_topic(paper_title)
    search_terms = [
        f'"{query}" pdf',
        f'"{query}" paper pdf',
        f'"{query}" arxiv',
    ]

    candidates: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for terms in search_terms:
        try:
            response = requests.get(
                "https://duckduckgo.com/html/",
                params={"q": terms},
                headers={"User-Agent": "Mozilla/5.0 (multi-agent-researcher)"},
                timeout=30,
            )
            response.raise_for_status()
        except requests.RequestException:
            continue

        for raw_url in _extract_duckduckgo_result_links(response.text):
            url = _decode_duckduckgo_redirect(raw_url)
            if url in seen_urls:
                continue
            seen_urls.add(url)

            lower = url.lower()
            if not ("pdf" in lower or "arxiv.org" in lower or "openalex.org" in lower or "doi.org" in lower):
                continue

            candidates.append(
                {
                    "title": paper_title,
                    "url": url,
                    "source": "web",
                }
            )
            if len(candidates) >= max_results:
                return candidates

    return candidates


def _discover_and_download_paper_assets(paper_title: str) -> dict[str, Any]:
    """
    Attempts paper discovery and PDF download in the following order:
    1. arXiv exact-title search
    2. web search for PDF/landing page links

    Returns metadata about the best found source, including any downloaded PDF.
    """
    PAPERS_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = _slugify_filename(paper_title, max_length=100)

    arxiv_hits = _search_arxiv_paper(paper_title)
    if arxiv_hits:
        best = arxiv_hits[0]
        pdf_url = best.get("pdf_url") or ""
        pdf_path = PAPERS_DIR / f"{safe_name}.pdf"
        downloaded = False
        if pdf_url:
            downloaded = _download_binary_file(pdf_url, pdf_path)
        if downloaded:
            pdf_text = _extract_pdf_text(pdf_path)
        else:
            pdf_text = ""

        return {
            "title": best.get("title", paper_title),
            "year": best.get("year"),
            "venue": best.get("venue", "arXiv"),
            "authors": best.get("authors", []),
            "best_available_link": pdf_url or best.get("url", ""),
            "direct_pdf_link": pdf_url,
            "pdf_path": pdf_path.as_posix() if downloaded else "",
            "pdf_downloaded": downloaded,
            "pdf_text_excerpt": pdf_text,
            "source": "arxiv",
            "discovery_type": "arxiv",
            "discovered_title": best.get("title", paper_title),
        }

    web_hits = _search_web_paper_candidates(paper_title)
    for idx, candidate in enumerate(web_hits, start=1):
        url = candidate.get("url", "")
        if not url:
            continue

        pdf_path = PAPERS_DIR / f"{safe_name}_{idx}.pdf"
        downloaded = _download_binary_file(url, pdf_path)
        if downloaded:
            pdf_text = _extract_pdf_text(pdf_path)
            return {
                "title": paper_title,
                "year": None,
                "venue": "web",
                "authors": [],
                "best_available_link": url,
                "direct_pdf_link": url,
                "pdf_path": pdf_path.as_posix(),
                "pdf_downloaded": True,
                "pdf_text_excerpt": pdf_text,
                "source": "web",
                "discovery_type": "web",
                "discovered_title": paper_title,
            }

    return {
        "title": paper_title,
        "year": None,
        "venue": "",
        "authors": [],
        "best_available_link": "",
        "direct_pdf_link": "",
        "pdf_path": "",
        "pdf_downloaded": False,
        "pdf_text_excerpt": "",
        "source": "none",
        "discovery_type": "none",
        "discovered_title": paper_title,
    }


def reset_output_workspace(outputs_dir: str = "outputs") -> str:
    """
    Deletes previous output artifacts so only files from the current work remain.
    Preserves top-level .gitkeep when present.
    """
    base = Path(outputs_dir)
    base.mkdir(parents=True, exist_ok=True)

    deleted_items: list[str] = []
    for child in base.iterdir():
        if child.name == ".gitkeep":
            continue
        try:
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
            deleted_items.append(child.as_posix())
        except OSError as exc:
            return json.dumps(
                {
                    "status": "error",
                    "message": f"Failed to remove {child.as_posix()}: {exc}",
                },
                indent=2,
            )

    return json.dumps(
        {
            "status": "success",
            "outputs_dir": base.as_posix(),
            "deleted_count": len(deleted_items),
            "deleted_items": deleted_items,
        },
        indent=2,
    )


def save_markdown_file(filename: str, content: str) -> str:
    """
    Saves markdown content to disk. Creates parent directories if needed.
    """
    path = _safe_path_with_limited_name(Path(filename))

    if path.suffix.lower() != ".md":
        path = path.with_suffix(".md")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

    return f"Successfully saved {path.as_posix()} to disk."


def create_run_output_dir(base_dir: str = "outputs", keep_last: int = 3, run_name: str = "") -> str:
    """
    Creates a timestamped run folder inside the outputs directory and
    automatically deletes older run folders, keeping only the newest N runs.

    Example:
        outputs/run_2026_04_04_1530

    Args:
        base_dir: The parent directory where run folders should be created.
        keep_last: Number of most recent runs to keep.

    Returns:
        The path to the created run directory as a string.
    """
    base_path = Path(base_dir)
    base_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y_%m_%d_%H%M%S")
    safe_run_name = _slugify_filename(run_name, max_length=80)
    if safe_run_name:
        run_dir = base_path / f"run_{safe_run_name}_{timestamp}"
    else:
        run_dir = base_path / f"run_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)

    # Parallel researcher runs can exceed low retention quickly and delete files
    # before synthesizer consumes them. Enforce safe minimums by output type.
    effective_keep_last = keep_last
    if base_path.name == "researcher_outputs":
        effective_keep_last = max(keep_last, 50)
    elif base_path.name == "synthesizer_outputs":
        effective_keep_last = max(keep_last, 20)

    run_dirs = sorted(
        [path for path in base_path.iterdir() if path.is_dir() and path.name.startswith("run_")],
        key=lambda path: path.name,
    )

    if len(run_dirs) > effective_keep_last:
        to_delete = run_dirs[:-effective_keep_last]
        for old_dir in to_delete:
            try:
                shutil.rmtree(old_dir)
            except PermissionError:
                print(f"Warning: Could not delete locked run folder: {old_dir}")
            except OSError as exc:
                print(f"Warning: Could not delete {old_dir}: {exc}")

    return run_dir.as_posix()


def _semantic_scholar_headers() -> dict[str, str]:
    """
    Build request headers for Semantic Scholar. If an API key is available
    in the environment, include it. Otherwise return empty headers so the
    app can still work without authentication.
    """
    headers: dict[str, str] = {}
    if SEMANTIC_SCHOLAR_API_KEY:
        headers["x-api-key"] = SEMANTIC_SCHOLAR_API_KEY
    return headers


def _normalize_search_topic(topic: str) -> str:
    return " ".join(topic.split()).strip()


def _reconstruct_openalex_abstract(abstract_index: Any) -> str:
    if not isinstance(abstract_index, dict) or not abstract_index:
        return ""

    words: list[str] = []
    for term, positions in abstract_index.items():
        if not isinstance(positions, list):
            continue
        for position in positions:
            if isinstance(position, int) and position >= 0:
                while len(words) <= position:
                    words.append("")
                words[position] = term

    return " ".join(word for word in words if word).strip()


def _search_arxiv(topic: str, max_results: int) -> list[dict[str, Any]]:
    query = _normalize_search_topic(topic)
    url = "http://export.arxiv.org/api/query"
    params = {
        "search_query": f'all:"{query}"',
        "start": 0,
        "max_results": max_results,
        "sortBy": "relevance",
        "sortOrder": "descending",
    }

    response = requests.get(
        url,
        params=params,
        headers={"User-Agent": "multi-agent-researcher/1.0"},
        timeout=30,
    )
    response.raise_for_status()

    try:
        import xml.etree.ElementTree as ET

        root = ET.fromstring(response.text)
    except Exception:
        return []

    atom_ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
    papers: list[dict[str, Any]] = []
    for entry in root.findall("atom:entry", atom_ns):
        title = (entry.findtext("atom:title", default="Unknown Title", namespaces=atom_ns) or "Unknown Title").strip()
        summary = (entry.findtext("atom:summary", default="", namespaces=atom_ns) or "").strip()
        published = (entry.findtext("atom:published", default="", namespaces=atom_ns) or "").strip()
        year = int(published[:4]) if published[:4].isdigit() else None

        authors = [
            (author.findtext("atom:name", default="Unknown Author", namespaces=atom_ns) or "Unknown Author").strip()
            for author in entry.findall("atom:author", atom_ns)
        ]

        links = entry.findall("atom:link", atom_ns)
        html_url = ""
        pdf_url = ""
        for link in links:
            href = link.attrib.get("href", "")
            rel = link.attrib.get("rel", "")
            title_attr = link.attrib.get("title", "")
            if rel == "alternate" and href:
                html_url = href
            if title_attr.lower() == "pdf" and href:
                pdf_url = href

        arxiv_id = ""
        id_text = (entry.findtext("atom:id", default="", namespaces=atom_ns) or "").strip()
        if "/abs/" in id_text:
            arxiv_id = id_text.rsplit("/abs/", 1)[-1]

        papers.append(
            {
                "title": title,
                "year": year,
                "venue": "arXiv",
                "url": html_url or pdf_url or id_text,
                "authors": authors,
                "abstract": summary or "No abstract available.",
                "reference_count": 0,
                "references": [],
                "source": "arxiv",
                "arxiv_id": arxiv_id,
                "pdf_url": pdf_url,
            }
        )

    return papers


def _search_openalex(topic: str, max_results: int) -> list[dict[str, Any]]:
    query = _normalize_search_topic(topic)
    url = "https://api.openalex.org/works"
    params = {
        "search": query,
        "per-page": max_results,
    }

    response = requests.get(
        url,
        params=params,
        headers={"User-Agent": "multi-agent-researcher/1.0"},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()

    papers: list[dict[str, Any]] = []
    for work in payload.get("results", []):
        title = work.get("title") or "Unknown Title"
        authors = []
        for auth in work.get("authorships", [])[:5]:
            author = auth.get("author") or {}
            authors.append(author.get("display_name", "Unknown Author"))

        abstract = _reconstruct_openalex_abstract(work.get("abstract_inverted_index")) or "No abstract available."
        primary_location = work.get("primary_location") or {}
        source = primary_location.get("source") or {}
        landing_url = primary_location.get("landing_page_url") or work.get("doi") or work.get("id") or ""
        year = None
        pub_date = work.get("publication_date") or ""
        if isinstance(pub_date, str) and pub_date[:4].isdigit():
            year = int(pub_date[:4])

        papers.append(
            {
                "title": title,
                "year": year,
                "venue": source.get("display_name") if isinstance(source, dict) else None,
                "url": landing_url,
                "authors": authors,
                "abstract": abstract,
                "reference_count": work.get("referenced_works_count", 0),
                "references": [],
                "source": "openalex",
            }
        )

    return papers


def _search_semantic_scholar(topic: str, max_results: int, max_references_per_paper: int) -> list[dict[str, Any]]:
    url = "https://api.semanticscholar.org/graph/v1/paper/search"

    params = {
        "query": topic,
        "limit": max_results,
        "fields": ",".join(
            [
                "title",
                "year",
                "abstract",
                "url",
                "venue",
                "authors",
                "referenceCount",
                "references.title",
                "references.year",
                "references.url",
            ]
        ),
    }

    response = requests.get(
        url,
        params=params,
        headers=_semantic_scholar_headers(),
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()

    papers: list[dict[str, Any]] = []
    for paper in payload.get("data", []):
        author_list = paper.get("authors") or []
        authors = [
            author.get("name", "Unknown Author")
            for author in author_list[:5]
        ]

        raw_references = paper.get("references") or []
        references = []
        for ref in raw_references[:max_references_per_paper]:
            references.append(
                {
                    "title": ref.get("title", "Unknown Title"),
                    "year": ref.get("year"),
                    "url": ref.get("url"),
                }
            )

        papers.append(
            {
                "title": paper.get("title", "Unknown Title"),
                "year": paper.get("year"),
                "venue": paper.get("venue"),
                "url": paper.get("url"),
                "authors": authors,
                "abstract": paper.get("abstract") or "No abstract available.",
                "reference_count": paper.get("referenceCount", 0),
                "references": references,
                "source": "semanticscholar",
            }
        )

    return papers


def scrape_research_articles(
    topic: str,
    max_results: int = 10,
    max_references_per_paper: int = 5,
) -> str:
    """
    Search for research papers related to a topic and return abstracts plus references.

    Search order:
    1. arXiv (no-auth, broad coverage)
    2. Semantic Scholar (rich metadata, may rate limit)
    3. OpenAlex (no-auth fallback, broad coverage)
    """
    papers: list[dict[str, Any]] = []
    source_used = "none"
    semantic_error = ""

    search_order = [
        ("arxiv", lambda: _search_arxiv(topic, max_results)),
        ("semanticscholar", lambda: _search_semantic_scholar(topic, max_results, max_references_per_paper)),
        ("openalex", lambda: _search_openalex(topic, max_results)),
    ]

    for source_name, search_fn in search_order:
        try:
            papers = search_fn()
            if papers:
                source_used = source_name
                break
        except requests.RequestException as exc:
            if source_name == "semanticscholar":
                semantic_error = str(exc)
            continue

    if not papers:
        return json.dumps(
            {
                "topic": topic,
                "status": "error",
                "message": f"Failed to retrieve papers from arXiv, Semantic Scholar, and OpenAlex. Semantic Scholar error: {semantic_error}",
                "papers": [],
            },
            indent=2,
        )

    return json.dumps(
        {
            "topic": topic,
            "status": "success",
            "source": source_used,
            "paper_count": len(papers),
            "papers": papers,
            "message": "Search completed using the best available source order: arXiv -> Semantic Scholar -> OpenAlex.",
        },
        indent=2,
    )


def research_single_paper(
    paper_title: str,
    max_references: int = 5,
    max_citations: int = 5,
) -> str:
    """
    Retrieve metadata for a single paper and prefer a downloaded PDF when available.

    Discovery order:
    1. arXiv PDF (download and extract text if available)
    2. Web search fallback for direct PDF links
    3. Semantic Scholar metadata for bibliographic enrichment
    """
    discovery = _discover_and_download_paper_assets(paper_title)

    semantic_error = ""
    semantic_paper: dict[str, Any] = {}
    try:
        response = requests.get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            params={
                "query": paper_title,
                "limit": 1,
                "fields": ",".join(
                    [
                        "title",
                        "year",
                        "abstract",
                        "url",
                        "venue",
                        "authors",
                        "citationCount",
                        "referenceCount",
                        "references.title",
                        "references.year",
                        "references.url",
                        "citations.title",
                        "citations.year",
                        "citations.url",
                    ]
                ),
            },
            headers=_semantic_scholar_headers(),
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data", [])
        if data:
            semantic_paper = data[0]
    except requests.RequestException as exc:
        semantic_error = str(exc)

    authors: list[str] = []
    if semantic_paper.get("authors"):
        authors = [author.get("name", "Unknown Author") for author in semantic_paper.get("authors")[:10]]
    elif discovery.get("authors"):
        authors = [str(author) for author in discovery.get("authors", [])[:10]]
    else:
        authors = ["Unknown Author"]

    raw_references = semantic_paper.get("references") or []
    references = [
        {
            "title": ref.get("title", "Unknown Title"),
            "year": ref.get("year"),
            "url": ref.get("url"),
        }
        for ref in raw_references[:max_references]
    ]

    raw_citations = semantic_paper.get("citations") or []
    citations = [
        {
            "title": cite.get("title", "Unknown Title"),
            "year": cite.get("year"),
            "url": cite.get("url"),
        }
        for cite in raw_citations[:max_citations]
    ]

    pdf_text_excerpt = discovery.get("pdf_text_excerpt") or ""
    extracted_text_available = bool(pdf_text_excerpt)
    summary_source = "downloaded_pdf" if extracted_text_available else "metadata_abstract"

    best_available_link = discovery.get("best_available_link") or semantic_paper.get("url") or ""
    paper_url = semantic_paper.get("url") or best_available_link

    paper_payload = {
        "title": semantic_paper.get("title") or discovery.get("discovered_title") or paper_title,
        "year": semantic_paper.get("year") or discovery.get("year"),
        "venue": semantic_paper.get("venue") or discovery.get("venue") or discovery.get("source") or "Unknown Venue",
        "url": paper_url,
        "best_available_link": best_available_link,
        "direct_pdf_link": discovery.get("direct_pdf_link", ""),
        "downloaded_pdf_path": discovery.get("pdf_path", ""),
        "pdf_downloaded": discovery.get("pdf_downloaded", False),
        "paper_text_source": summary_source,
        "paper_text_excerpt": pdf_text_excerpt,
        "authors": authors,
        "abstract": semantic_paper.get("abstract") or pdf_text_excerpt[:2000] or "No abstract available.",
        "citation_count": semantic_paper.get("citationCount", 0),
        "reference_count": semantic_paper.get("referenceCount", 0),
        "references": references,
        "citations": citations,
        "discovery_source": discovery.get("source", "none"),
        "search_notes": (
            "Used arXiv PDF download and extracted text." if discovery.get("source") == "arxiv" and extracted_text_available
            else "Used web search PDF download and extracted text." if discovery.get("source") == "web" and extracted_text_available
            else "No PDF downloaded; used metadata only."
        ),
    }

    if semantic_error and discovery.get("source") in {"arxiv", "web"}:
        paper_payload["semantic_scholar_error"] = semantic_error

    return json.dumps(
        {
            "status": "success",
            "paper": paper_payload,
        },
        indent=2,
    )


def _normalize_json_text(data: str) -> str:
    """
    Normalizes model-produced JSON text by removing markdown code fences.
    """
    text = data.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3 and lines[0].startswith("```") and lines[-1].strip() == "```":
            text = "\n".join(lines[1:-1]).strip()
            if text.lower().startswith("json\n"):
                text = text[5:].lstrip()
    return text


def _parse_json_payload(data: Any) -> tuple[Any | None, str | None]:
    """
    Parses tool input into JSON-compatible Python data.
    Returns (parsed_data, error_message).
    """
    if isinstance(data, (dict, list, int, float, bool)) or data is None:
        return data, None

    if not isinstance(data, str):
        return None, f"Unsupported JSON payload type: {type(data).__name__}"

    normalized = _normalize_json_text(data)

    try:
        return json.loads(normalized), None
    except json.JSONDecodeError as exc:
        # Best-effort recovery when model wraps JSON with surrounding text.
        obj_start = normalized.find("{")
        obj_end = normalized.rfind("}")
        arr_start = normalized.find("[")
        arr_end = normalized.rfind("]")

        candidates: list[str] = []
        if obj_start != -1 and obj_end > obj_start:
            candidates.append(normalized[obj_start : obj_end + 1])
        if arr_start != -1 and arr_end > arr_start:
            candidates.append(normalized[arr_start : arr_end + 1])

        for candidate in candidates:
            try:
                return json.loads(candidate), None
            except json.JSONDecodeError:
                continue

        return None, f"Invalid JSON payload: {exc.msg} at line {exc.lineno} column {exc.colno}."


def save_json_file(filename: str, data: Any) -> str:
    """
    Saves JSON content to disk.
    Accepts Python dict/list primitives or JSON text.
    """
    path = _safe_path_with_limited_name(Path(filename))

    if path.suffix.lower() != ".json":
        path = path.with_suffix(".json")

    path.parent.mkdir(parents=True, exist_ok=True)

    parsed, error = _parse_json_payload(data)
    if error:
        return json.dumps(
            {
                "status": "error",
                "target_file": path.as_posix(),
                "message": error,
            },
            indent=2,
        )

    path.write_text(json.dumps(parsed, indent=2), encoding="utf-8")

    return f"Successfully saved {path.as_posix()} to disk."


def load_json_file(filename: str) -> str:
    """
    Loads a JSON file from disk and returns it as a JSON string.
    """
    path = Path(filename)
    return path.read_text(encoding="utf-8")


def get_latest_planner_manifest(base_dir: str = "outputs/planner_outputs") -> str:
    """
    Returns the path to the most recent planner_manifest.json file
    inside the planner outputs directory.

    Args:
        base_dir: Base directory containing planner run folders.

    Returns:
        The path to the latest planner_manifest.json file as a string.

    Raises:
        FileNotFoundError: If no planner manifest files are found.
    """
    base_path = Path(base_dir)
    if not base_path.exists():
        raise FileNotFoundError(f"Planner output directory does not exist: {base_dir}")

    run_dirs = sorted(
        [path for path in base_path.iterdir() if path.is_dir() and path.name.startswith("run_")],
        key=lambda path: path.name,
    )

    if not run_dirs:
        raise FileNotFoundError(f"No planner run folders found in: {base_dir}")

    for run_dir in reversed(run_dirs):
        canonical_manifest = run_dir / "planner_manifest.json"
        if canonical_manifest.exists():
            return canonical_manifest.as_posix()

        # Backward/alternate compatibility for identity-prefixed manifests.
        prefixed_manifests = sorted(run_dir.glob("*_planner_manifest.json"))
        if prefixed_manifests:
            return prefixed_manifests[-1].as_posix()

    raise FileNotFoundError(
        f"No planner manifest found in any run folder under: {base_dir}"
    )

def list_researcher_outputs(base_dir: str = "outputs") -> str:
    """Lists all researcher output files available for validation."""
    path = Path(base_dir)
    files = list(path.rglob("*.json")) + list(path.rglob("*.md"))
    return json.dumps([f.as_posix() for f in files], indent=2)

def read_researcher_output(researcher_output_path: str) -> str:
    """Reads a researcher output file and returns its content for validation."""
    path = Path(researcher_output_path)
    if not path.exists():
        return json.dumps({"status": "error", "message": f"File not found: {researcher_output_path}"})
    return json.dumps({"status": "success", "content": path.read_text(encoding="utf-8")})

def get_latest_run_dir(base_dir: str = "outputs") -> str:
    """Returns the most recent run directory path.

    Looks for run folders directly under base_dir first, then recursively under
    nested subdirectories (for example outputs/researcher_outputs/run_*).
    """
    base_path = Path(base_dir)
    if not base_path.exists():
        raise FileNotFoundError(f"Base directory does not exist: {base_dir}")

    direct_runs = [path for path in base_path.iterdir() if path.is_dir() and path.name.startswith("run_")]
    if direct_runs:
        latest = max(direct_runs, key=lambda p: p.name)
        return latest.as_posix()

    nested_runs = [path for path in base_path.rglob("run_*") if path.is_dir()]
    if nested_runs:
        latest = max(nested_runs, key=lambda p: p.name)
        return latest.as_posix()

    raise FileNotFoundError(f"No run directories found under: {base_dir}")


def _load_json_object(path: Path) -> dict[str, Any]:
    content = path.read_text(encoding="utf-8")
    data = json.loads(content)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path.as_posix()}")
    return data


def initialize_shared_run(
    planner_topic: str,
    planner_manifest_path: str = "",
    base_dir: str = "outputs/shared_runs",
    keep_last: int = 3,
) -> str:
    """
    Creates a shared run folder and initializes shared_state.json used by all agents.
    """
    run_dir = create_run_output_dir(base_dir=base_dir, keep_last=keep_last)
    state_path = Path(run_dir) / "shared_state.json"

    state = {
        "planner_topic": planner_topic,
        "planner_manifest_path": planner_manifest_path or None,
        "run_dir": run_dir,
        "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "assignments": [],
        "research_outputs": [],
        "validations": [],
        "synthesis_outputs": [],
    }

    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    return json.dumps(
        {
            "status": "success",
            "run_dir": run_dir,
            "shared_state_file": state_path.as_posix(),
        },
        indent=2,
    )


def register_planner_assignment(
    shared_state_file: str,
    researcher_id: str,
    aspect_id: str,
    aspect_title: str,
    paper_title: str,
    paper_url: str = "",
) -> str:
    """
    Appends one planner->researcher assignment into shared_state.json.
    """
    state_path = Path(shared_state_file)
    state = _load_json_object(state_path)

    assignments = state.setdefault("assignments", [])
    if not isinstance(assignments, list):
        raise ValueError("shared_state.json field 'assignments' must be a list")

    assignments.append(
        {
            "researcher_id": researcher_id,
            "aspect_id": aspect_id,
            "aspect_title": aspect_title,
            "paper_title": paper_title,
            "paper_url": paper_url or None,
            "status": "assigned",
            "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        }
    )

    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    return json.dumps(
        {
            "status": "success",
            "shared_state_file": state_path.as_posix(),
            "assignment_count": len(assignments),
        },
        indent=2,
    )


def register_research_output(
    shared_state_file: str,
    researcher_id: str,
    paper_title: str,
    review_markdown_file: str,
    review_json_file: str,
    validation_report_file: str = "",
    validation_status: str = "pending",
) -> str:
    """
    Appends one researcher output record and updates matching assignment status.
    """
    state_path = Path(shared_state_file)
    state = _load_json_object(state_path)

    outputs = state.setdefault("research_outputs", [])
    if not isinstance(outputs, list):
        raise ValueError("shared_state.json field 'research_outputs' must be a list")

    outputs.append(
        {
            "researcher_id": researcher_id,
            "paper_title": paper_title,
            "review_markdown_file": review_markdown_file,
            "review_json_file": review_json_file,
            "validation_report_file": validation_report_file or None,
            "validation_status": validation_status,
            "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        }
    )

    assignments = state.get("assignments", [])
    if isinstance(assignments, list):
        for assignment in assignments:
            if not isinstance(assignment, dict):
                continue
            matches_researcher = assignment.get("researcher_id") == researcher_id
            matches_title = assignment.get("paper_title") == paper_title
            if matches_researcher and matches_title:
                assignment["status"] = "completed"

    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    return json.dumps(
        {
            "status": "success",
            "shared_state_file": state_path.as_posix(),
            "research_output_count": len(outputs),
        },
        indent=2,
    )


def register_synthesis_output(
    shared_state_file: str,
    synthesis_markdown_file: str,
    synthesis_json_file: str = "",
    validation_report_file: str = "",
    validation_status: str = "pending",
) -> str:
    """
    Stores synthesizer outputs in shared_state.json.
    """
    state_path = Path(shared_state_file)
    state = _load_json_object(state_path)

    synth_outputs = state.setdefault("synthesis_outputs", [])
    if not isinstance(synth_outputs, list):
        raise ValueError("shared_state.json field 'synthesis_outputs' must be a list")

    synth_outputs.append(
        {
            "synthesis_markdown_file": synthesis_markdown_file,
            "synthesis_json_file": synthesis_json_file or None,
            "validation_report_file": validation_report_file or None,
            "validation_status": validation_status,
            "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        }
    )

    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    return json.dumps(
        {
            "status": "success",
            "shared_state_file": state_path.as_posix(),
            "synthesis_output_count": len(synth_outputs),
        },
        indent=2,
    )


def register_validation_result(
    shared_state_file: str,
    validator_scope: str,
    target_id: str,
    status: str,
    notes: str,
    report_file: str = "",
) -> str:
    """
    Appends validator decisions for researcher-level or synthesis-level outputs.
    """
    state_path = Path(shared_state_file)
    state = _load_json_object(state_path)

    validations = state.setdefault("validations", [])
    if not isinstance(validations, list):
        raise ValueError("shared_state.json field 'validations' must be a list")

    validations.append(
        {
            "validator_scope": validator_scope,
            "target_id": target_id,
            "status": status,
            "notes": notes,
            "report_file": report_file or None,
            "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        }
    )

    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    return json.dumps(
        {
            "status": "success",
            "shared_state_file": state_path.as_posix(),
            "validation_count": len(validations),
        },
        indent=2,
    )


def _validation_report_path_from_artifact(artifact_path: Path) -> Path:
    return artifact_path.with_name("validation_report.json")


def _simple_text_score(text: str, keywords: list[str]) -> int:
    lowered = text.lower()
    return sum(1 for keyword in keywords if keyword and keyword.lower() in lowered)


def validate_researcher_artifacts(
    shared_state_file: str,
    target_id: str,
    review_markdown_file: str,
    review_json_file: str,
    planner_topic: str,
) -> str:
    """
    Deterministic researcher validation fallback.

    This avoids empty nested-validator responses by always returning a concrete
    validation decision based on the produced artifacts.
    """
    md_path = Path(review_markdown_file)
    json_path = Path(review_json_file)
    report_path = _validation_report_path_from_artifact(md_path if md_path.exists() else json_path)

    reasons: list[str] = []
    status = "pass"
    correlation = "medium"
    grounding = "medium"

    markdown_text = md_path.read_text(encoding="utf-8") if md_path.exists() else ""
    json_text = json_path.read_text(encoding="utf-8") if json_path.exists() else ""

    if not md_path.exists():
        status = "fail"
        reasons.append("markdown review file is missing")
    if not json_path.exists():
        status = "fail"
        reasons.append("review JSON file is missing")

    if markdown_text and len(markdown_text) < 400:
        status = "fail"
        reasons.append("markdown review is too short to be grounded")

    if not markdown_text:
        reasons.append("markdown content is empty")

    try:
        review_payload = json.loads(json_text) if json_text else {}
    except json.JSONDecodeError:
        review_payload = {}
        status = "fail"
        reasons.append("review JSON is not valid JSON")

    if isinstance(review_payload, dict):
        output_text = json.dumps(review_payload, ensure_ascii=False).lower()
        if not review_payload:
            status = "fail"
            reasons.append("review JSON payload is empty")
        if "output_id" not in review_payload:
            status = "fail"
            reasons.append("review JSON is missing output_id")
        if _simple_text_score(output_text, [planner_topic, "method", "results", "limitations", "paper"] ) < 2:
            correlation = "low"
            status = "fail"
            reasons.append("review JSON does not strongly reflect the planner topic")
        if _simple_text_score(output_text, ["abstract", "method", "results", "limitations", "references"]) >= 3:
            grounding = "high"
        else:
            grounding = "medium"
    else:
        status = "fail"
        reasons.append("review JSON payload is not an object")

    if markdown_text:
        md_score = _simple_text_score(markdown_text, ["method", "results", "limitations", "relevance", planner_topic])
        if md_score >= 3:
            grounding = "high"
        elif md_score <= 1:
            grounding = "low"
            status = "fail"
            reasons.append("markdown review lacks evidence-focused sections")

    if not reasons:
        reasons.append("review is present, structured, and sufficiently grounded for downstream synthesis")

    report = {
        "validator_scope": "researcher",
        "target_id": target_id,
        "status": status,
        "reasons": reasons,
        "correlation_to_planner_question": correlation,
        "scientific_grounding": grounding,
    }

    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    if shared_state_file:
        register_validation_result(
            shared_state_file=shared_state_file,
            validator_scope="researcher",
            target_id=target_id,
            status=status,
            notes="; ".join(reasons),
            report_file=report_path.as_posix(),
        )

    return json.dumps(
        {
            "status": status,
            "report_file": report_path.as_posix(),
            "reasons": reasons,
            "correlation_to_planner_question": correlation,
            "scientific_grounding": grounding,
            "shared_state_file": shared_state_file or None,
        },
        indent=2,
    )


def validate_synthesis_artifacts(
    shared_state_file: str,
    target_id: str,
    synthesis_markdown_file: str,
    synthesis_json_file: str,
    planner_topic: str,
) -> str:
    """Deterministic synthesis validation fallback."""
    md_path = Path(synthesis_markdown_file)
    json_path = Path(synthesis_json_file)
    report_path = _validation_report_path_from_artifact(md_path if md_path.exists() else json_path)

    reasons: list[str] = []
    status = "pass"
    correlation = "medium"
    grounding = "medium"

    markdown_text = md_path.read_text(encoding="utf-8") if md_path.exists() else ""
    json_text = json_path.read_text(encoding="utf-8") if json_path.exists() else ""

    if not md_path.exists():
        status = "fail"
        reasons.append("synthesis markdown file is missing")
    if not json_path.exists():
        status = "fail"
        reasons.append("synthesis JSON file is missing")

    try:
        synthesis_payload = json.loads(json_text) if json_text else {}
    except json.JSONDecodeError:
        synthesis_payload = {}
        status = "fail"
        reasons.append("synthesis JSON is not valid JSON")

    if markdown_text and len(markdown_text) < 600:
        status = "fail"
        reasons.append("synthesis markdown is too short to represent a real synthesis")

    if isinstance(synthesis_payload, dict):
        payload_text = json.dumps(synthesis_payload, ensure_ascii=False).lower()
        if _simple_text_score(payload_text, [planner_topic, "theme", "gap", "future", "comparison"]) < 2:
            correlation = "low"
            status = "fail"
            reasons.append("synthesis JSON does not clearly align with the planner topic")
        if _simple_text_score(payload_text, ["research", "paper", "method", "results", "gap"]) >= 3:
            grounding = "high"
    else:
        status = "fail"
        reasons.append("synthesis JSON payload is not an object")

    if markdown_text:
        md_score = _simple_text_score(markdown_text, ["theme", "comparison", "gap", "future", planner_topic])
        if md_score >= 3:
            grounding = "high"
        elif md_score <= 1:
            grounding = "low"
            status = "fail"
            reasons.append("synthesis markdown lacks cross-paper comparison")

    if not reasons:
        reasons.append("synthesis is structured and sufficiently aligned with the planner question")

    report = {
        "validator_scope": "synthesizer",
        "target_id": target_id,
        "status": status,
        "reasons": reasons,
        "correlation_to_planner_question": correlation,
        "scientific_grounding": grounding,
    }

    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    if shared_state_file:
        register_validation_result(
            shared_state_file=shared_state_file,
            validator_scope="synthesizer",
            target_id=target_id,
            status=status,
            notes="; ".join(reasons),
            report_file=report_path.as_posix(),
        )

    return json.dumps(
        {
            "status": status,
            "report_file": report_path.as_posix(),
            "reasons": reasons,
            "correlation_to_planner_question": correlation,
            "scientific_grounding": grounding,
        },
        indent=2,
    )


def get_latest_shared_state(base_dir: str = "outputs/shared_runs") -> str:
    """
    Returns path to the newest shared_state.json under outputs/shared_runs/run_*/.
    """
    base_path = Path(base_dir)
    if not base_path.exists():
        raise FileNotFoundError(f"Shared run directory does not exist: {base_dir}")

    run_dirs = sorted(
        [path for path in base_path.iterdir() if path.is_dir() and path.name.startswith("run_")],
        key=lambda path: path.name,
    )
    if not run_dirs:
        raise FileNotFoundError(f"No shared run folders found in: {base_dir}")

    for run_dir in reversed(run_dirs):
        state_path = run_dir / "shared_state.json"
        if state_path.exists():
            return state_path.as_posix()

    raise FileNotFoundError("No shared_state.json found in shared run folders.")


def list_registered_research_outputs(shared_state_file: str) -> str:
    """
    Returns registered researcher outputs from shared_state.json.
    """
    state_path = Path(shared_state_file)
    state = _load_json_object(state_path)
    outputs = state.get("research_outputs", [])

    if not isinstance(outputs, list):
        raise ValueError("shared_state.json field 'research_outputs' must be a list")

    return json.dumps(outputs, indent=2)


@lru_cache(maxsize=1)
def list_available_vertex_gemini_models() -> list[str]:
    """
    Returns the Gemini model IDs currently available in the configured Vertex project.
    """
    project = (os.getenv("GOOGLE_CLOUD_PROJECT") or "").strip()
    location = (os.getenv("GOOGLE_CLOUD_LOCATION") or "us-central1").strip()

    if not project:
        return []

    try:
        client = genai.Client(vertexai=True, project=project, location=location)
        models: list[str] = []
        for model in client.models.list():
            name = getattr(model, "name", "") or ""
            if not name:
                continue
            models.append(name.split("/models/")[-1] if "/models/" in name else name)
        return sorted(set(models))
    except Exception:
        return []


@lru_cache(maxsize=None)
def _probe_vertex_gemini_model(model_name: str) -> bool:
    """
    Returns True if a tiny generate_content call succeeds for the given model.
    This is more reliable than catalog listing alone because some models may be
    visible in the catalog but not actually accessible for the current project.
    """
    project = (os.getenv("GOOGLE_CLOUD_PROJECT") or "").strip()
    location = (os.getenv("GOOGLE_CLOUD_LOCATION") or "us-central1").strip()

    if not project or not model_name:
        return False

    try:
        client = genai.Client(vertexai=True, project=project, location=location)
        response = client.models.generate_content(model=model_name, contents="ping")
        return bool(getattr(response, "text", "") or True)
    except Exception:
        return False


@lru_cache(maxsize=None)
def _resolve_vertex_gemini_model_cached(preferences: tuple[str, ...], fallback: str) -> str:
    """
    Returns the first preferred model that exists in the current Vertex catalog.
    It probes models with a tiny request so we only select a model that is both
    listed and actually callable for the current project.
    """
    available = set(list_available_vertex_gemini_models())
    for model_name in preferences:
        if model_name in available and _probe_vertex_gemini_model(model_name):
            return model_name

    if fallback in available and _probe_vertex_gemini_model(fallback):
        return fallback

    for model_name in available:
        if _probe_vertex_gemini_model(model_name):
            return model_name

    return fallback


def resolve_vertex_gemini_model(preferences: list[str], fallback: str) -> str:
    return _resolve_vertex_gemini_model_cached(tuple(preferences), fallback)

@dataclass(frozen=True)
class GeminiModel:
    ROOT: str = resolve_vertex_gemini_model(
        ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.5-flash-lite", "gemini-3-pro-preview", "gemini-3-flash-preview"],
        "gemini-2.5-flash",
    )
    PLANNER: str = resolve_vertex_gemini_model(
        ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.5-flash-lite", "gemini-3-pro-preview", "gemini-3-flash-preview"],
        "gemini-2.5-flash",
    )
    RESEARCHER: str = resolve_vertex_gemini_model(
        ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.5-flash-lite", "gemini-3-pro-preview", "gemini-3-flash-preview"],
        "gemini-2.5-flash",
    )
    VALIDATOR: str = resolve_vertex_gemini_model(
        ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.5-flash-lite", "gemini-3-pro-preview", "gemini-3-flash-preview"],
        "gemini-2.5-flash",
    )
    SYNTHESIZER: str = resolve_vertex_gemini_model(
        ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.5-flash-lite", "gemini-3-pro-preview", "gemini-3-flash-preview"],
        "gemini-2.5-flash",
    )

# Instance for easy import
gemini_models = GeminiModel()