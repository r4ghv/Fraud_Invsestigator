"""Reverse image search engine wrapper.

Orchestrates reverse image search via automated visual search
and optional external APIs, returning structured web matches.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from typing import List, Optional


@dataclass
class SearchMatch:
    """Individual match from reverse image search."""

    title: str
    url: str
    source_type: str
    snippet: str
    image_url: Optional[str] = None


@dataclass
class SearchResult:
    """Full reverse image search output."""

    query_image: str
    search_url: str
    search_title: str
    total_matches: int
    matches: List[SearchMatch]

    def to_dict(self) -> dict:
        return asdict(self)


class ReverseSearchEngine:
    """Production reverse image search provider."""

    def __init__(
        self,
        runner_script: Optional[str] = None,
        timeout_seconds: int = 45,
    ) -> None:
        self.runner_script = os.path.abspath(
            runner_script
            or os.path.join(
                os.path.dirname(__file__), "..", "scripts", "reverse_search.js"
            )
        )
        self.timeout_seconds = timeout_seconds

        if not os.path.exists(self.runner_script):
            raise FileNotFoundError(
                f"Reverse search runner script not found: {self.runner_script}"
            )

    def search(self, image_path: str) -> SearchResult:
        """Executes genuine reverse image search on the specified image file."""
        abs_image_path = os.path.abspath(image_path)
        if not os.path.exists(abs_image_path):
            raise FileNotFoundError(f"Image not found at: {abs_image_path}")

        # Create temporary file for runner JSON output
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            tmp_json_path = tmp.name

        try:
            cmd = ["bun", self.runner_script, abs_image_path, tmp_json_path]
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )

            if proc.returncode != 0:
                raise RuntimeError(
                    f"Reverse search process failed (code {proc.returncode}):\n"
                    f"STDOUT: {proc.stdout}\nSTDERR: {proc.stderr}"
                )

            if not os.path.exists(tmp_json_path) or os.path.getsize(tmp_json_path) == 0:
                raise RuntimeError("Reverse search completed but produced no output JSON")

            with open(tmp_json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            matches = [
                SearchMatch(
                    title=m.get("title", ""),
                    url=m.get("url", ""),
                    source_type=m.get("source_type", "unknown"),
                    snippet=m.get("snippet", ""),
                    image_url=m.get("image_url"),
                )
                for m in data.get("matches", [])
            ]

            return SearchResult(
                query_image=data.get("query_image", abs_image_path),
                search_url=data.get("search_url", ""),
                search_title=data.get("title", ""),
                total_matches=len(matches),
                matches=matches,
            )

        finally:
            if os.path.exists(tmp_json_path):
                os.remove(tmp_json_path)
