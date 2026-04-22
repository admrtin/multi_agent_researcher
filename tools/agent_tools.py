from __future__ import annotations

import json
import mimetypes
import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, TYPE_CHECKING

from google.adk.tools import BaseTool
from google.genai import types
import requests
from dotenv import load_dotenv

if TYPE_CHECKING:
    from google.adk.models.llm_request import LlmRequest
    from google.adk.tools import ToolContext

load_dotenv()

SEMANTIC_SCHOLAR_API_KEY = os.getenv("SEMANTIC_SCHOLAR_API_KEY")


def save_markdown_file(filename: str, content: str) -> str:
    """
    Saves markdown content to disk. Creates parent directories if needed.
    """
    path = Path(filename)

    if path.suffix.lower() != ".md":
        path = path.with_suffix(".md")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

    return f"Successfully saved {path.as_posix()} to disk."


def create_run_output_dir(base_dir: str = "outputs", keep_last: int = 3) -> str:
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

    timestamp = datetime.now().strftime("run_%Y_%m_%d_%H%M%S")
    run_dir = base_path / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)

    run_dirs = sorted(
        [path for path in base_path.iterdir() if path.is_dir() and path.name.startswith("run_")],
        key=lambda path: path.name,
    )

    if len(run_dirs) > keep_last:
        to_delete = run_dirs[:-keep_last]
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


def scrape_research_articles(
    topic: str,
    max_results: int = 10,
    max_references_per_paper: int = 5,
) -> str:
    """
    Search for research papers related to a topic and return abstracts plus references.
    """
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

    try:
        response = requests.get(
            url,
            params=params,
            headers=_semantic_scholar_headers(),
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        return json.dumps(
            {
                "topic": topic,
                "status": "error",
                "message": f"Failed to retrieve papers: {exc}",
                "papers": [],
            },
            indent=2,
        )

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
            }
        )

    return json.dumps(
        {
            "topic": topic,
            "status": "success",
            "paper_count": len(papers),
            "papers": papers,
        },
        indent=2,
    )


def research_single_paper(
    paper_title: str,
    max_references: int = 5,
    max_citations: int = 5,
) -> str:
    """
    Retrieve metadata for a single paper from Semantic Scholar, including
    abstract, references, and citations when available.
    """
    url = "https://api.semanticscholar.org/graph/v1/paper/search"

    params = {
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
    }

    try:
        response = requests.get(
            url,
            params=params,
            headers=_semantic_scholar_headers(),
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        return json.dumps(
            {
                "paper_title": paper_title,
                "status": "error",
                "message": f"Failed to retrieve paper: {exc}",
            },
            indent=2,
        )

    data = payload.get("data", [])
    if not data:
        return json.dumps(
            {
                "paper_title": paper_title,
                "status": "error",
                "message": "No paper found for the given title.",
            },
            indent=2,
        )

    paper = data[0]

    author_list = paper.get("authors") or []
    authors = [author.get("name", "Unknown Author") for author in author_list[:10]]

    raw_references = paper.get("references") or []
    references = [
        {
            "title": ref.get("title", "Unknown Title"),
            "year": ref.get("year"),
            "url": ref.get("url"),
        }
        for ref in raw_references[:max_references]
    ]

    raw_citations = paper.get("citations") or []
    citations = [
        {
            "title": cite.get("title", "Unknown Title"),
            "year": cite.get("year"),
            "url": cite.get("url"),
        }
        for cite in raw_citations[:max_citations]
    ]

    return json.dumps(
        {
            "status": "success",
            "paper": {
                "title": paper.get("title", "Unknown Title"),
                "year": paper.get("year"),
                "venue": paper.get("venue"),
                "url": paper.get("url"),
                "authors": authors,
                "abstract": paper.get("abstract") or "No abstract available.",
                "citation_count": paper.get("citationCount", 0),
                "reference_count": paper.get("referenceCount", 0),
                "references": references,
                "citations": citations,
            },
        },
        indent=2,
    )


def save_json_file(filename: str, data: str) -> str:
    """
    Saves JSON content to disk. Expects `data` to be a JSON string.
    """
    path = Path(filename)

    if path.suffix.lower() != ".json":
        path = path.with_suffix(".json")

    path.parent.mkdir(parents=True, exist_ok=True)

    parsed = json.loads(data)
    path.write_text(json.dumps(parsed, indent=2), encoding="utf-8")

    return f"Successfully saved {path.as_posix()} to disk."


def load_json_file(filename: str) -> str:
    """
    Loads a JSON file from disk and returns it as a JSON string.
    """
    path = Path(filename)
    return path.read_text(encoding="utf-8")


class LoadPdfFileTool(BaseTool):
    """Load a local PDF and attach it to the next Gemini request as PDF bytes."""

    def __init__(self) -> None:
        super().__init__(
            name="load_pdf_file",
            description=(
                "Loads a local PDF file by path and attaches it directly to the "
                "model request as application/pdf inline data. Use this for PDFs "
                "where layout, tables, figures, or page structure matter."
            ),
        )

    def _get_declaration(self) -> types.FunctionDeclaration:
        return types.FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "filename": types.Schema(
                        type=types.Type.STRING,
                        description="Local filesystem path to the PDF file.",
                    ),
                },
                required=["filename"],
            ),
        )

    async def run_async(
        self,
        *,
        args: dict[str, Any],
        tool_context: "ToolContext",
    ) -> dict[str, Any]:
        filename = str(args.get("filename", "")).strip()
        if not filename:
            return {"status": "error", "message": "Missing filename."}

        path = Path(filename).expanduser()
        if not path.exists():
            return {"status": "error", "message": f"File not found: {filename}"}
        if not path.is_file():
            return {"status": "error", "message": f"Not a file: {filename}"}

        mime_type = mimetypes.guess_type(path.name)[0] or "application/pdf"
        if path.suffix.lower() != ".pdf" and mime_type != "application/pdf":
            return {
                "status": "error",
                "message": f"Expected a PDF file, got: {path.name}",
            }

        return {
            "status": "success",
            "filename": path.as_posix(),
            "mime_type": "application/pdf",
            "size_bytes": path.stat().st_size,
            "message": (
                "PDF will be attached directly to the next model request as "
                "application/pdf inline data."
            ),
        }

    async def process_llm_request(
        self,
        *,
        tool_context: "ToolContext",
        llm_request: "LlmRequest",
    ) -> None:
        await super().process_llm_request(
            tool_context=tool_context,
            llm_request=llm_request,
        )

        filenames = self._filenames_from_last_tool_response(llm_request)
        for filename in filenames:
            path = Path(filename)
            try:
                data = path.read_bytes()
            except OSError:
                continue

            llm_request.contents.append(
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(
                            text=(
                                f"PDF file {path.as_posix()} is attached as "
                                "application/pdf inline data. Analyze the "
                                "document directly, preserving table and "
                                "layout information when relevant."
                            )
                        ),
                        types.Part.from_bytes(
                            data=data,
                            mime_type="application/pdf",
                        ),
                    ],
                )
            )

    def _filenames_from_last_tool_response(
        self,
        llm_request: "LlmRequest",
    ) -> list[str]:
        if not llm_request.contents or not llm_request.contents[-1].parts:
            return []

        filenames: list[str] = []
        for part in llm_request.contents[-1].parts:
            function_response = part.function_response
            if not function_response or function_response.name != self.name:
                continue

            response = function_response.response or {}
            if response.get("status") == "success" and response.get("filename"):
                filenames.append(str(response["filename"]))

        return filenames


load_pdf_file = LoadPdfFileTool()

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
        manifest_path = run_dir / "planner_manifest.json"
        if manifest_path.exists():
            return manifest_path.as_posix()

    raise FileNotFoundError(f"No planner_manifest.json found in any run folder under: {base_dir}")

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
    """Returns the most recent run directory path."""
    base_path = Path(base_dir)
    run_dirs = sorted(base_path.glob("run_*"), key=lambda p: p.name)
    if not run_dirs:
        raise FileNotFoundError("No run directories found.")
    return run_dirs[-1].as_posix()

@dataclass(frozen=True)
class GeminiModel:
    ROOT: str = "gemini-2.5-flash"
    PLANNER: str = "gemini-2.5-flash"
    RESEARCHER: str = "gemini-2.5-flash"
    VALIDATOR: str = "gemini-2.5-flash"
    SYNTHESIZER: str = "gemini-2.5-flash"

# Instance for easy import
gemini_models = GeminiModel()
