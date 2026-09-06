"""Social media post detection, validation, and metadata extraction filter.

Filters raw reverse-image search matches, validates genuine social media posts
(X/Twitter, Reddit, LinkedIn, Instagram, YouTube, Facebook, Threads, Pinterest, TikTok),
verifies URL availability, and structures metadata for blockchain attestation.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional
from urllib.parse import urlparse

import requests


@dataclass
class SocialMediaPostMatch:
    """Represents a validated social media post/profile matching the face."""

    platform: str
    post_type: str  # post, pin, profile, video, discussion
    url: str
    title: str
    snippet: str
    post_id: Optional[str]
    author: Optional[str]
    is_live: bool
    status_code: int
    confidence_score: float

    def to_dict(self) -> dict:
        return asdict(self)


class SocialMediaFilter:
    """Filter and enrich social media reverse image search matches."""

    PLATFORM_PATTERNS: Dict[str, Dict[str, str]] = {
        "twitter": {
            "domain_pattern": r"(?:twitter\.com|x\.com)",
            "post_pattern": r"(?:twitter\.com|x\.com)/([^/]+)/status/(\d+)",
            "profile_pattern": r"(?:twitter\.com|x\.com)/([a-zA-Z0-9_]+)/?$",
            "display_name": "X (formerly Twitter)",
        },
        "reddit": {
            "domain_pattern": r"(?:reddit\.com|redd\.it)",
            "post_pattern": r"reddit\.com/r/([^/]+)/comments/([a-zA-Z0-9]+)",
            "profile_pattern": r"reddit\.com/user/([^/]+)",
            "display_name": "Reddit",
        },
        "linkedin": {
            "domain_pattern": r"linkedin\.com",
            "post_pattern": r"linkedin\.com/posts/([^/?]+)",
            "profile_pattern": r"linkedin\.com/in/([^/?]+)",
            "display_name": "LinkedIn",
        },
        "instagram": {
            "domain_pattern": r"instagram\.com",
            "post_pattern": r"instagram\.com/(?:p|reel)/([^/?]+)",
            "profile_pattern": r"instagram\.com/([^/?]+)/?$",
            "display_name": "Instagram",
        },
        "pinterest": {
            "domain_pattern": r"(?:pinterest\.com|pin\.it)",
            "post_pattern": r"pinterest\.[a-z.]+/pin/([^/?]+)",
            "profile_pattern": r"pinterest\.[a-z.]+/([^/?]+)/?$",
            "display_name": "Pinterest",
        },
        "youtube": {
            "domain_pattern": r"(?:youtube\.com|youtu\.be)",
            "post_pattern": r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)([^&/?]+)",
            "profile_pattern": r"youtube\.com/@?([^/?]+)",
            "display_name": "YouTube",
        },
        "facebook": {
            "domain_pattern": r"facebook\.com",
            "post_pattern": r"facebook\.com/[^/]+/(?:posts|videos|reel)/([^/?]+)",
            "profile_pattern": r"facebook\.com/([^/?]+)/?$",
            "display_name": "Facebook",
        },
        "threads": {
            "domain_pattern": r"threads\.net",
            "post_pattern": r"threads\.net/@([^/]+)/post/([^/?]+)",
            "profile_pattern": r"threads\.net/@([^/?]+)/?$",
            "display_name": "Threads",
        },
        "tiktok": {
            "domain_pattern": r"tiktok\.com",
            "post_pattern": r"tiktok\.com/@([^/]+)/video/(\d+)",
            "profile_pattern": r"tiktok\.com/@([^/?]+)/?$",
            "display_name": "TikTok",
        },
    }

    def __init__(self, timeout: int = 6, check_live: bool = True) -> None:
        self.timeout = timeout
        self.check_live = check_live
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/130.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.9",
            }
        )

    def identify_platform(self, url: str) -> Optional[str]:
        """Returns the platform key if URL belongs to a supported social platform."""
        for key, conf in self.PLATFORM_PATTERNS.items():
            if re.search(conf["domain_pattern"], url, re.IGNORECASE):
                return key
        return None

    def analyze_url(self, platform_key: str, url: str) -> dict:
        """Extracts post_type, post_id, author from URL."""
        conf = self.PLATFORM_PATTERNS[platform_key]
        post_match = re.search(conf["post_pattern"], url, re.IGNORECASE)
        if post_match:
            groups = post_match.groups()
            if len(groups) == 2:
                author, post_id = groups[0], groups[1]
            else:
                author, post_id = None, groups[0]
            return {"post_type": "post", "post_id": post_id, "author": author}

        profile_match = re.search(conf["profile_pattern"], url, re.IGNORECASE)
        if profile_match:
            author = profile_match.group(1)
            return {"post_type": "profile", "post_id": author, "author": author}

        return {"post_type": "social_content", "post_id": None, "author": None}

    def verify_liveness(self, url: str) -> tuple[bool, int]:
        """Performs a quick HTTP HEAD/GET request to verify the URL exists."""
        if not self.check_live:
            return True, 200

        try:
            # First try HEAD request to save bandwidth
            r = self.session.head(url, timeout=self.timeout, allow_redirects=True)
            if r.status_code in (200, 301, 302, 307, 308, 403, 999):
                # 403 / 999 often returned by Twitter/LinkedIn bot blocks but confirms URL exists
                return True, r.status_code

            # If HEAD is rejected with 405 Method Not Allowed, fallback to GET
            if r.status_code == 405:
                r = self.session.get(url, timeout=self.timeout, stream=True)
                return r.status_code < 500, r.status_code

            return r.status_code < 400, r.status_code
        except Exception:
            # Fallback check
            return False, 0

    def calculate_confidence(
        self,
        raw_match: dict,
        platform_info: dict,
        is_live: bool,
    ) -> float:
        """Calculates a match confidence score between 0.0 and 1.0."""
        score = 0.60  # Base score for genuine reverse image match
        if is_live:
            score += 0.20
        if platform_info["post_type"] == "post":
            score += 0.15
        elif platform_info["post_type"] == "profile":
            score += 0.10

        title = raw_match.get("title", "").lower()
        snippet = raw_match.get("snippet", "").lower()
        if len(title) > 5 or len(snippet) > 10:
            score += 0.05

        return min(round(score, 4), 0.99)

    def filter_matches(
        self, raw_matches: List[dict]
    ) -> List[SocialMediaPostMatch]:
        """Filters a list of reverse search matches and returns validated social media posts."""
        results: List[SocialMediaPostMatch] = []
        seen_urls = set()

        for match in raw_matches:
            url = match.get("url", "")
            if not url or url in seen_urls:
                continue

            platform_key = self.identify_platform(url)
            if not platform_key:
                continue

            seen_urls.add(url)
            platform_meta = self.analyze_url(platform_key, url)
            is_live, status_code = self.verify_liveness(url)

            confidence = self.calculate_confidence(match, platform_meta, is_live)

            results.append(
                SocialMediaPostMatch(
                    platform=self.PLATFORM_PATTERNS[platform_key]["display_name"],
                    post_type=platform_meta["post_type"],
                    url=url,
                    title=match.get("title", "Social Media Match"),
                    snippet=match.get("snippet", ""),
                    post_id=platform_meta["post_id"],
                    author=platform_meta["author"],
                    is_live=is_live,
                    status_code=status_code,
                    confidence_score=confidence,
                )
            )

        # Sort by confidence score descending, preferring live and specific posts
        results.sort(key=lambda x: (x.confidence_score, x.is_live), reverse=True)
        return results
