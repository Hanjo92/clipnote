#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import shutil
import socket
import sys
import tempfile
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from html import unescape
from pathlib import Path
from urllib.error import URLError, HTTPError
from urllib.parse import ParseResult, parse_qs, urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener
import xml.etree.ElementTree as ET

__version__ = "0.1.1"

OBSIDIAN_CONFIG = Path.home() / "Library/Application Support/obsidian/obsidian.json"
USER_AGENT = f"clipnote/{__version__} (+OpenClaw MVP)"
ARXIV_API = "https://export.arxiv.org/api/query?id_list={id_list}"
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
MAX_FETCH_BYTES = int(os.environ.get("CLIPNOTE_MAX_FETCH_BYTES", str(2 * 1024 * 1024)))
FETCH_CHUNK_BYTES = 64 * 1024
MAX_FETCH_REDIRECTS = 5
REDIRECT_STATUS_CODES = {301, 302, 303, 307, 308}
BLOCKED_FETCH_HOSTS = {"localhost"}
TITLE_PATTERNS = [
    re.compile(r'<meta[^>]+name=["\']citation_title["\'][^>]+content=["\'](.*?)["\']', re.I),
    re.compile(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\'](.*?)["\']', re.I),
    re.compile(r'<title[^>]*>(.*?)</title>', re.I | re.S),
]
DESCRIPTION_PATTERNS = [
    re.compile(r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']', re.I),
    re.compile(r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\'](.*?)["\']', re.I),
    re.compile(r'<meta[^>]+name=["\']twitter:description["\'][^>]+content=["\'](.*?)["\']', re.I),
]
ABSTRACT_PATTERNS = [
    re.compile(r'<blockquote[^>]*class=["\'][^"\']*abstract[^"\']*["\'][^>]*>(.*?)</blockquote>', re.I | re.S),
    re.compile(r'<span[^>]*class=["\'][^"\']*abstract-full[^"\']*["\'][^>]*>(.*?)</span>', re.I | re.S),
]
PARAGRAPH_PATTERN = re.compile(r'<p[^>]*>(.*?)</p>', re.I | re.S)
URL_PATTERNS = [
    re.compile(r"-\s+Link:\s+(https?://\S+)", re.I),
    re.compile(r"https?://\S+", re.I),
]
IGNORE_TITLE_KEYS = {"aimorningbrief"}
MERGE_MARKER = "## Merge candidates"
SUMMARY_HEADERS = ("## TL;DR", "## One-line summary", "## Brief take", "## Why it matters", "## Why save this")
THEME_STOPWORDS = {
    "the", "a", "an", "and", "or", "to", "of", "for", "in", "on", "with", "from", "by", "at",
    "is", "are", "be", "this", "that", "it", "as", "into", "about", "over", "after", "using",
    "new", "how", "why", "what", "your", "their", "more", "less", "than", "via", "vs", "v",
    "ai", "paper", "papers", "link", "links", "update", "model", "models",
    "post", "old", "latest", "earlier", "shared", "improved", "team", "article", "blog",
    "builders", "products", "platform", "focused", "focus", "overview",
}
THEME_NORMALIZATION = {
    "agents": "agent",
    "workflows": "workflow",
    "evaluations": "eval",
    "evaluation": "eval",
    "tooling": "tool",
    "tools": "tool",
    "benchmarks": "benchmark",
    "models": "model",
    "controls": "control",
    "orchestration": "orchestrate",
}
NOTE_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TITLE_SUFFIX_PATTERNS: dict[str, list[str]] = {
    "arxiv": [r"\s*[-|:–—]\s*arxiv\s*$"],
    "openai.com": [r"\s*[-|:–—]\s*openai\s*$", r"\s*\|\s*openai\s*$"],
    "github.blog": [r"\s*[-|:–—]\s*github blog\s*$", r"\s*\|\s*github blog\s*$"],
    "github.com": [r"\s*[-|:–—]\s*github\s*$", r"\s*\|\s*github\s*$"],
    "anthropic.com": [r"\s*[-|:–—]\s*anthropic\s*$", r"\s*\|\s*anthropic\s*$"],
    "vercel.com": [r"\s*[-|:–—]\s*vercel\s*$", r"\s*\|\s*vercel\s*$"],
    "huggingface.co": [r"\s*[-|:–—]\s*hugging\s*face\s*$", r"\s*\|\s*hugging\s*face\s*$"],
    "huggingface.blog": [r"\s*[-|:–—]\s*hugging\s*face\s*$", r"\s*\|\s*hugging\s*face\s*$"],
}
TITLE_PREFIX_PATTERNS: dict[str, list[str]] = {
    "openai.com": [r"^introducing\s+", r"^announcing\s+"],
    "anthropic.com": [r"^introducing\s+", r"^announcing\s+"],
    "vercel.com": [r"^introducing\s+", r"^announcing\s+"],
}
SOURCE_TAGS: dict[str, list[str]] = {
    "arxiv": ["#arxiv"],
    "openai.com": ["#openai"],
    "anthropic.com": ["#anthropic"],
    "github.blog": ["#github", "#devtools"],
    "github.com": ["#github", "#devtools"],
    "vercel.com": ["#vercel", "#devtools"],
    "huggingface.co": ["#huggingface", "#openmodels"],
    "huggingface.blog": ["#huggingface", "#openmodels"],
}


@dataclass
class RecapItem:
    path: Path
    title: str
    kind: str
    note_date: str
    source: str
    link: str
    summary: str


@dataclass
class NoteMeta:
    source: str
    title: str
    link: str
    kind: str
    note_date: str
    folder: Path
    path: Path
    duplicate_urls: list[Path]
    duplicate_titles: list[Path]
    summary: str = ""
    why_save: str = ""
    key_points: list[str] | None = None
    extra_meta: dict[str, str | list[str]] | None = None
    tags: list[str] | None = None
    selected_text: str = ""


@dataclass
class ArxivMeta:
    arxiv_id: str
    title: str
    summary: str
    authors: list[str]
    published: str
    updated: str
    categories: list[str]


class NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


NO_REDIRECT_OPENER = build_opener(NoRedirectHandler)


def eprint(*args: object) -> None:
    print(*args, file=sys.stderr)


def load_vault_path(name: str | None, explicit_path: str | None) -> Path:
    if explicit_path:
        return Path(explicit_path).expanduser()
    if not OBSIDIAN_CONFIG.exists():
        raise SystemExit(f"Obsidian config not found: {OBSIDIAN_CONFIG}")
    data = json.loads(OBSIDIAN_CONFIG.read_text())
    vaults = data.get("vaults", {})
    if name:
        for item in vaults.values():
            path = item.get("path", "")
            if Path(path).name == name:
                return Path(path)
        raise SystemExit(f"Vault named '{name}' not found in {OBSIDIAN_CONFIG}")
    for item in vaults.values():
        if item.get("open"):
            return Path(item["path"])
    raise SystemExit("No open Obsidian vault found")


def iter_markdown_files(vault_path: Path):
    for path in vault_path.rglob("*.md"):
        if ".obsidian" in path.parts or "Archive" in path.parts:
            continue
        yield path


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(errors="ignore")


def fetch_html(url: str) -> str:
    with open_safe_url(url, timeout=15) as resp:
        return read_response_text(resp)


def fetch_text(url: str) -> str:
    with open_safe_url(url, timeout=15) as resp:
        return read_response_text(resp)


def open_safe_url(url: str, timeout: int = 15):
    current_url = url
    for _ in range(MAX_FETCH_REDIRECTS + 1):
        validate_fetch_url(current_url)
        req = Request(current_url, headers={"User-Agent": USER_AGENT})
        try:
            resp = open_url_once(req, timeout=timeout)
        except HTTPError as exc:
            location = exc.headers.get("Location", "")
            if exc.code in REDIRECT_STATUS_CODES and location:
                current_url = urljoin(current_url, location)
                validate_fetch_url(current_url)
                continue
            raise
        final_url = getattr(resp, "geturl", lambda: current_url)()
        validate_fetch_url(final_url)
        return resp
    raise ValueError("Too many redirects while fetching URL")


def open_url_once(req: Request, timeout: int = 15):
    return NO_REDIRECT_OPENER.open(req, timeout=timeout)


def validate_fetch_url(url: str) -> None:
    parsed = validate_http_url(url)
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL must be an absolute http(s) URL")
    normalized_host = hostname.rstrip(".").casefold()
    if normalized_host in BLOCKED_FETCH_HOSTS or normalized_host.endswith(".localhost"):
        raise ValueError("URL host is not allowed")
    if is_blocked_ip_literal(normalized_host):
        raise ValueError("URL host is not allowed")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise URLError(f"Could not resolve URL host: {hostname}") from exc
    for info in infos:
        address = info[4][0].split("%", 1)[0]
        if is_blocked_ip_literal(address):
            raise ValueError("URL host is not allowed")


def is_blocked_ip_literal(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value.split("%", 1)[0])
    except ValueError:
        return False
    return (
        address.is_loopback
        or address.is_private
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
        or not address.is_global
    )


def read_response_text(resp, max_bytes: int | None = None) -> str:
    max_bytes = MAX_FETCH_BYTES if max_bytes is None else max_bytes
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = resp.read(min(FETCH_CHUNK_BYTES, max_bytes + 1 - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > max_bytes:
            raise ValueError("Fetched response is too large")
    charset = resp.headers.get_content_charset() or "utf-8"
    return b"".join(chunks).decode(charset, errors="replace")


def write_note_file(path: Path, content: str, force: bool = False) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not force:
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
        except FileExistsError:
            return False
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        return True

    temp_name = ""
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False) as handle:
            temp_name = handle.name
            handle.write(content)
        os.replace(temp_name, path)
        return True
    finally:
        if temp_name and Path(temp_name).exists():
            Path(temp_name).unlink()


def html_to_text(fragment: str) -> str:
    fragment = re.sub(r"<script.*?</script>", " ", fragment, flags=re.I | re.S)
    fragment = re.sub(r"<style.*?</style>", " ", fragment, flags=re.I | re.S)
    fragment = re.sub(r"<[^>]+>", " ", fragment)
    fragment = unescape(fragment)
    fragment = re.sub(r"\s+", " ", fragment)
    return fragment.strip()


def extract_title(html: str) -> str | None:
    for pattern in TITLE_PATTERNS:
        match = pattern.search(html)
        if match:
            title = html_to_text(match.group(1))
            if title:
                return title
    return None


def extract_description(html: str) -> str | None:
    for pattern in DESCRIPTION_PATTERNS:
        match = pattern.search(html)
        if match:
            desc = html_to_text(match.group(1))
            if desc:
                return desc
    return None


def extract_meta_content(html: str, keys: list[str]) -> str | None:
    for key in keys:
        pattern = re.compile(
            rf'<meta[^>]+(?:name|property)=["\']{re.escape(key)}["\'][^>]+content=["\'](.*?)["\']',
            re.I,
        )
        match = pattern.search(html)
        if match:
            text = html_to_text(match.group(1))
            if text:
                return text
    return None


def extract_abstract(html: str) -> str | None:
    for pattern in ABSTRACT_PATTERNS:
        match = pattern.search(html)
        if match:
            text = html_to_text(match.group(1))
            text = re.sub(r'^Abstract:\s*', '', text, flags=re.I)
            if text:
                return text
    return None


def extract_paragraphs(html: str, limit: int = 5) -> list[str]:
    out: list[str] = []
    for match in PARAGRAPH_PATTERN.finditer(html):
        text = html_to_text(match.group(1))
        if len(text) < 60:
            continue
        out.append(text)
        if len(out) >= limit:
            break
    return out


def extract_arxiv_id(url: str) -> str | None:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if "arxiv.org" not in host:
        return None
    path = parsed.path.strip("/")
    if path.startswith("abs/") or path.startswith("pdf/"):
        ident = path.split("/", 1)[1]
        ident = ident.removesuffix(".pdf")
        return ident or None
    query = parse_qs(parsed.query)
    if "id" in query and query["id"]:
        return query["id"][0]
    return None


def parse_arxiv_date(text: str) -> str:
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return text.strip()


def fetch_arxiv_meta(arxiv_id: str) -> ArxivMeta | None:
    xml_text = fetch_text(ARXIV_API.format(id_list=arxiv_id))
    root = ET.fromstring(xml_text)
    entry = root.find("atom:entry", ATOM_NS)
    if entry is None:
        return None
    title = html_to_text(entry.findtext("atom:title", default="", namespaces=ATOM_NS))
    summary = html_to_text(entry.findtext("atom:summary", default="", namespaces=ATOM_NS))
    authors = [
        html_to_text(author.findtext("atom:name", default="", namespaces=ATOM_NS))
        for author in entry.findall("atom:author", ATOM_NS)
        if html_to_text(author.findtext("atom:name", default="", namespaces=ATOM_NS))
    ]
    categories = []
    for cat in entry.findall("atom:category", ATOM_NS):
        term = (cat.attrib.get("term") or "").strip()
        if term and term not in categories:
            categories.append(term)
    return ArxivMeta(
        arxiv_id=arxiv_id,
        title=title,
        summary=summary,
        authors=authors,
        published=parse_arxiv_date(entry.findtext("atom:published", default="", namespaces=ATOM_NS)),
        updated=parse_arxiv_date(entry.findtext("atom:updated", default="", namespaces=ATOM_NS)),
        categories=categories,
    )


def clean_title(title: str, source: str = "") -> str:
    source_key = source.casefold()
    title = html_to_text(title)
    title = re.sub(r"\s+", " ", title).strip()
    title = re.sub(r"^(introducing|announcing)\s+", "", title, flags=re.I) if source_key in TITLE_PREFIX_PATTERNS else title
    for pattern in TITLE_PREFIX_PATTERNS.get(source_key, []):
        title = re.sub(pattern, "", title, flags=re.I)
    for pattern in TITLE_SUFFIX_PATTERNS.get(source_key, []):
        title = re.sub(pattern, "", title, flags=re.I)
    title = re.sub(r"\s+[-|:–—]\s+(arXiv|OpenAI|Anthropic|Google DeepMind|GitHub|Vercel|Hugging Face).*$", "", title, flags=re.I)
    title = re.sub(r"\s+\|\s+(OpenAI|Anthropic|GitHub( Blog)?|Vercel|Hugging Face).*$", "", title, flags=re.I)
    title = re.sub(r"\s*[:\-–—|]\s*$", "", title)
    return re.sub(r"\s+", " ", title).strip()


def infer_kind(url: str, explicit_kind: str) -> str:
    if explicit_kind != "auto":
        return explicit_kind
    host = urlparse(url).netloc.lower()
    if "arxiv.org" in host or "/abs/" in url or "/pdf/" in url:
        return "papers"
    return "links"


def infer_source(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if "arxiv.org" in host:
        return "arXiv"
    if host.startswith("www."):
        host = host[4:]
    return host or "Unknown"


def infer_kind_from_path(path: Path) -> str:
    parts = path.parts
    if "Papers" in parts:
        return "papers"
    if "Links" in parts:
        return "links"
    return "other"


def slugify_filename(title: str) -> str:
    normalized = unicodedata.normalize("NFKC", title)
    normalized = re.sub(r"[/:*?\"<>|]", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip().rstrip(".")
    return normalized or "Untitled"


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    return re.sub(r"[^\w]+", "", text)


def score_note(path: Path, content: str) -> tuple[int, list[str]]:
    reasons: list[str] = []
    score = 0
    kind = infer_kind_from_path(path)
    if kind == "papers":
        score += 4
        reasons.append("Papers 폴더")
    elif kind == "links":
        score += 1
        reasons.append("Links 폴더")
    else:
        reasons.append("기타 폴더")
    length = len(content.strip())
    if length > 400:
        score += 2
        reasons.append(f"내용이 더 김({length}자)")
    elif length > 180:
        score += 1
        reasons.append(f"내용이 어느 정도 있음({length}자)")
    heading_count = len(re.findall(r"^##\s+", content, re.M))
    if heading_count >= 3:
        score += 2
        reasons.append(f"구조화된 섹션 {heading_count}개")
    elif heading_count >= 1:
        score += 1
        reasons.append(f"섹션 {heading_count}개")
    bullet_count = len(re.findall(r"^-\s+", content, re.M))
    if bullet_count >= 6:
        score += 1
        reasons.append(f"메모 포인트 {bullet_count}개")
    return score, reasons


def choose_canonical(paths: list[Path]) -> tuple[Path, dict[Path, tuple[int, list[str]]]]:
    scored: dict[Path, tuple[int, list[str]]] = {}
    for path in paths:
        scored[path] = score_note(path, read_text(path))
    best = sorted(paths, key=lambda p: (-scored[p][0], str(p)))[0]
    return best, scored


def scan_duplicates(vault_path: Path, title: str, url: str) -> tuple[list[Path], list[Path]]:
    duplicate_urls: list[Path] = []
    duplicate_titles: list[Path] = []
    title_key = normalize_text(title)
    for path in iter_markdown_files(vault_path):
        content = read_text(path)
        if url and url in content:
            duplicate_urls.append(path)
        if normalize_text(path.stem) == title_key:
            duplicate_titles.append(path)
    return duplicate_urls, duplicate_titles


def extract_note_url(content: str) -> str | None:
    for pattern in URL_PATTERNS:
        match = pattern.search(content)
        if match:
            return match.group(1) if match.lastindex else match.group(0)
    return None


def extract_note_field(content: str, label: str) -> str:
    match = re.search(rf"^-\s+{re.escape(label)}:\s+(.*)$", content, re.M)
    return match.group(1).strip() if match else ""


def extract_summary_from_note(content: str) -> str:
    lines = content.splitlines()
    for header in SUMMARY_HEADERS:
        for idx, line in enumerate(lines):
            if line.strip() != header:
                continue
            for next_line in lines[idx + 1:]:
                stripped = next_line.strip()
                if not stripped:
                    continue
                if stripped.startswith("## "):
                    return ""
                return sentenceish(stripped.removeprefix("- ").strip(), max_len=180)
    return ""


def parse_note_date(value: str) -> date | None:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def validate_note_date_text(value: str) -> None:
    if not NOTE_DATE_PATTERN.match(value) or parse_note_date(value) is None:
        raise ValueError("Date must use YYYY-MM-DD")


def validate_http_url(url: str) -> ParseResult:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("URL must be an absolute http(s) URL")
    return parsed


def collect_recap_items(vault_path: Path, start: date, end: date) -> list[RecapItem]:
    items: list[RecapItem] = []
    for path in iter_markdown_files(vault_path):
        content = read_text(path)
        note_date_text = extract_note_field(content, "Date")
        note_day = parse_note_date(note_date_text)
        if not note_day or note_day < start or note_day > end:
            continue
        items.append(
            RecapItem(
                path=path,
                title=path.stem,
                kind=infer_kind_from_path(path),
                note_date=note_date_text,
                source=extract_note_field(content, "Source") or "Unknown",
                link=extract_note_field(content, "Link"),
                summary=extract_summary_from_note(content),
            )
        )
    return sorted(items, key=lambda item: (item.note_date, item.kind, item.title))


def format_recap_section(title: str, items: list[RecapItem], vault_path: Path) -> list[str]:
    lines = [f"## {title}"]
    if not items:
        lines.append("- 없음")
        return lines
    for item in items:
        rel = item.path.relative_to(vault_path)
        summary = item.summary or "요약 없음"
        lines.append(f"- {item.note_date} — [{item.source}] {item.title}")
        lines.append(f"  - {summary}")
        lines.append(f"  - {rel}")
    return lines


def recap_item_score(item: RecapItem) -> tuple[int, int, int, str]:
    kind_score = 3 if item.kind == "papers" else 1 if item.kind == "links" else 0
    summary_score = min(len(item.summary) // 40, 4)
    source_score = 1 if item.source not in {"Unknown", ""} else 0
    return (kind_score + summary_score + source_score, kind_score, summary_score, item.title)


def build_highlights(items: list[RecapItem], limit: int = 5) -> list[str]:
    ranked = sorted(items, key=recap_item_score, reverse=True)
    highlights: list[str] = []
    for item in ranked[:limit]:
        summary = item.summary or "요약 없음"
        highlights.append(f"{item.title} ({item.source}, {item.note_date}) — {summary}")
    return highlights


def extract_theme_terms(items: list[RecapItem]) -> list[tuple[str, int]]:
    counter: Counter[str] = Counter()
    for item in items:
        text = f"{item.title} {item.summary}"
        seen: set[str] = set()
        for token in re.findall(r"[A-Za-z][A-Za-z0-9+\-]{2,}", text):
            norm = token.casefold()
            norm = THEME_NORMALIZATION.get(norm, norm)
            if norm in THEME_STOPWORDS or norm.isdigit():
                continue
            seen.add(norm)
        for norm in seen:
            counter[norm] += 1
    return [(term, count) for term, count in counter.most_common() if count >= 2][:5]


def build_recurring_themes(items: list[RecapItem]) -> list[str]:
    themes = extract_theme_terms(items)
    if not themes:
        return []
    out: list[str] = []
    for term, count in themes:
        matched = [item.title for item in items if re.search(rf"\b{re.escape(term)}\b", f"{item.title} {item.summary}", re.I)]
        sample = ", ".join(matched[:2])
        out.append(f"{term} — {count}개 노트에서 반복 ({sample})")
    return out


def build_source_breakdown(items: list[RecapItem]) -> list[str]:
    source_map: dict[str, list[RecapItem]] = defaultdict(list)
    for item in items:
        source_map[item.source].append(item)
    lines: list[str] = []
    for source, group in sorted(source_map.items(), key=lambda entry: (-len(entry[1]), entry[0])):
        papers = sum(1 for item in group if item.kind == "papers")
        links = sum(1 for item in group if item.kind == "links")
        parts = []
        if papers:
            parts.append(f"papers {papers}")
        if links:
            parts.append(f"links {links}")
        latest = max(group, key=lambda item: (item.note_date, item.title))
        tail = f" | latest: {latest.title}" if latest.title else ""
        lines.append(f"{source} — {len(group)} ({', '.join(parts)}){tail}")
    return lines


def format_delta(current: int, previous: int) -> str:
    delta = current - previous
    if delta > 0:
        return f"+{delta}"
    return str(delta)


def compare_sources(current_items: list[RecapItem], previous_items: list[RecapItem]) -> list[str]:
    current_counts = Counter(item.source for item in current_items)
    previous_counts = Counter(item.source for item in previous_items)
    all_sources = sorted(set(current_counts) | set(previous_counts), key=lambda s: (-(current_counts[s] + previous_counts[s]), s))
    lines: list[str] = []
    for source in all_sources[:5]:
        cur = current_counts[source]
        prev = previous_counts[source]
        if cur == prev == 0:
            continue
        lines.append(f"{source} — {cur} ({format_delta(cur, prev)} vs prev {prev})")
    return lines


def compare_terms(current_items: list[RecapItem], previous_items: list[RecapItem]) -> list[str]:
    current_terms = dict(extract_theme_terms(current_items))
    previous_terms = dict(extract_theme_terms(previous_items))
    gained = [term for term in current_terms if term not in previous_terms]
    strengthened = [term for term in current_terms if term in previous_terms and current_terms[term] > previous_terms[term]]
    lines: list[str] = []
    if gained:
        lines.append("new themes: " + ", ".join(gained[:4]))
    if strengthened:
        bits = [f"{term} ({previous_terms[term]}→{current_terms[term]})" for term in strengthened[:4]]
        lines.append("stronger themes: " + ", ".join(bits))
    dropped = [term for term in previous_terms if term not in current_terms]
    if dropped:
        lines.append("faded themes: " + ", ".join(dropped[:4]))
    return lines


def build_period_compare(current_items: list[RecapItem], previous_items: list[RecapItem], current_start: date, current_end: date, previous_start: date, previous_end: date) -> list[str]:
    current_papers = sum(1 for item in current_items if item.kind == "papers")
    previous_papers = sum(1 for item in previous_items if item.kind == "papers")
    current_links = sum(1 for item in current_items if item.kind == "links")
    previous_links = sum(1 for item in previous_items if item.kind == "links")
    lines = [
        f"## Compared to previous period ({previous_start.isoformat()} → {previous_end.isoformat()})",
        f"- total: {len(current_items)} ({format_delta(len(current_items), len(previous_items))} vs prev {len(previous_items)})",
        f"- papers: {current_papers} ({format_delta(current_papers, previous_papers)} vs prev {previous_papers})",
        f"- links: {current_links} ({format_delta(current_links, previous_links)} vs prev {previous_links})",
    ]
    source_lines = compare_sources(current_items, previous_items)
    if source_lines:
        lines.append("- source shifts:")
        lines.extend(f"  - {line}" for line in source_lines)
    term_lines = compare_terms(current_items, previous_items)
    if term_lines:
        lines.append("- theme shifts:")
        lines.extend(f"  - {line}" for line in term_lines)
    return lines


def build_recap_output(items: list[RecapItem], papers: list[RecapItem], links: list[RecapItem], sources: dict[str, int], start: date, end: date, vault_path: Path, previous_items: list[RecapItem] | None = None, previous_start: date | None = None, previous_end: date | None = None) -> str:
    highlights = build_highlights(items)
    themes = build_recurring_themes(items)
    source_breakdown = build_source_breakdown(items)
    lines = [
        f"# AI recap ({start.isoformat()} → {end.isoformat()})",
        "",
        f"- total: {len(items)}",
        f"- papers: {len(papers)}",
        f"- links: {len(links)}",
        f"- Tags: #ai #recap",
    ]
    if sources:
        top_sources = ", ".join(f"{name} {count}" for name, count in sorted(sources.items(), key=lambda item: (-item[1], item[0]))[:5])
        lines.append(f"- top sources: {top_sources}")
    if previous_items is not None and previous_start is not None and previous_end is not None:
        lines.append("")
        lines.extend(build_period_compare(items, previous_items, start, end, previous_start, previous_end))
    lines.append("")
    lines.append("## Highlights")
    if highlights:
        lines.extend(f"- {line}" for line in highlights)
    else:
        lines.append("- 없음")
    lines.append("")
    lines.append("## Recurring themes")
    if themes:
        lines.extend(f"- {line}" for line in themes)
    else:
        lines.append("- 뚜렷한 반복 키워드 없음")
    lines.append("")
    lines.append("## Source breakdown")
    if source_breakdown:
        lines.extend(f"- {line}" for line in source_breakdown)
    else:
        lines.append("- 없음")
    lines.append("")
    lines.extend(format_recap_section("Papers", papers, vault_path))
    lines.append("")
    lines.extend(format_recap_section("Links", links, vault_path))
    return "\n".join(lines).rstrip() + "\n"


def recap_note_path(vault_path: Path, start: date, end: date) -> Path:
    folder = vault_path / "Recaps" / end.isoformat()
    filename = slugify_filename(f"AI recap {start.isoformat()} to {end.isoformat()}") + ".md"
    return folder / filename


def collect_duplicate_groups(vault_path: Path) -> tuple[dict[str, list[Path]], dict[str, list[Path]]]:
    by_url: dict[str, list[Path]] = defaultdict(list)
    by_title: dict[str, list[Path]] = defaultdict(list)
    for path in iter_markdown_files(vault_path):
        content = read_text(path)
        url = extract_note_url(content)
        if url:
            by_url[url].append(path)
        title_key = normalize_text(path.stem)
        if title_key not in IGNORE_TITLE_KEYS:
            by_title[title_key].append(path)
    return (
        {key: paths for key, paths in by_url.items() if len(paths) > 1},
        {key: paths for key, paths in by_title.items() if len(paths) > 1},
    )


def sentenceish(text: str, max_len: int = 220) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_len:
        return text
    m = re.match(rf"^(.{{1,{max_len}}}[.!?])\b", text)
    if m:
        return m.group(1).strip()
    return text[:max_len].rstrip() + "…"


def normalize_summary_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"^(By|Posted by)\s+[^.]+\.\s*", "", text, flags=re.I)
    text = re.sub(r"\s+(Read more|Learn more|Continue reading)\b.*$", "", text, flags=re.I)
    text = re.sub(r"^(Introducing|Announcing)\s+", "", text, flags=re.I)
    return text.strip(" -—:")


def choose_summary_basis(source: str, html: str, desc: str, abstract: str, paragraphs: list[str]) -> str:
    source_key = source.casefold()
    if source_key == "arxiv":
        if abstract:
            return abstract
        return desc or (paragraphs[0] if paragraphs else "")
    if source_key in {"openai.com", "anthropic.com", "vercel.com"}:
        return (
            extract_meta_content(html, ["og:description", "twitter:description", "description"])
            or (paragraphs[0] if paragraphs else "")
            or desc
        )
    if source_key in {"github.blog", "github.com", "huggingface.co", "huggingface.blog"}:
        return (
            extract_meta_content(html, ["og:description", "description", "twitter:description"])
            or (paragraphs[0] if paragraphs else "")
            or desc
        )
    return desc or abstract or (paragraphs[0] if paragraphs else "")


def build_why_save(kind: str, source: str, summary: str) -> str:
    source_key = source.casefold()
    if kind == "papers":
        if source_key == "arxiv":
            return "- arXiv 논문이라 나중에 아이디어/실험 설계 참고용으로 다시 보기 좋음"
        return f"- {source} 자료라서 나중에 다시 참고할 가치가 있음"
    if source_key == "openai.com":
        return "- OpenAI 제품/연구 방향 업데이트라 도구 변화 추적용으로 저장할 만함"
    if source_key == "anthropic.com":
        return "- Anthropic 연구/제품 방향 업데이트라 모델 활용 전략 변화 체크용으로 저장할 만함"
    if source_key == "vercel.com":
        return "- Vercel 플랫폼 변화라 배포/개발 워크플로우 영향 체크용으로 보관할 만함"
    if source_key in {"github.blog", "github.com"}:
        return "- GitHub 생태계 변화라 개발 워크플로우 영향 체크용으로 보관할 만함"
    if source_key in {"huggingface.co", "huggingface.blog"}:
        return "- Hugging Face 생태계 업데이트라 오픈모델/툴링 흐름 추적용으로 저장할 만함"
    if summary:
        return f"- {source} 업데이트/글이라 흐름 추적용으로 저장할 만함"
    return "- 나중에 다시 확인할 만한 참고 링크"


def build_tags(kind: str, source: str, arxiv_meta: ArxivMeta | None = None) -> list[str]:
    tags = ["#ai"]
    if kind == "papers":
        tags.append("#paper")
    elif kind == "links":
        tags.append("#link")
    tags.extend(SOURCE_TAGS.get(source.casefold(), []))
    if arxiv_meta:
        for category in arxiv_meta.categories[:3]:
            tag = "#" + re.sub(r"[^a-z0-9]+", "-", category.casefold()).strip("-")
            if tag != "#" and tag not in tags:
                tags.append(tag)
    out: list[str] = []
    for tag in tags:
        if tag not in out:
            out.append(tag)
    return out


def format_authors(authors: list[str], max_names: int = 4) -> tuple[str, str]:
    if not authors:
        return "", ""
    full = ", ".join(authors)
    if len(authors) <= max_names:
        return full, ""
    short = ", ".join(authors[:max_names]) + f", et al. ({len(authors)} authors)"
    return short, full


def normalize_selected_text(text: str, max_len: int = 900) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= max_len:
        return text
    return text[:max_len].rstrip() + "…"


def normalize_summary_override(text: str, max_len: int = 900) -> str:
    text = normalize_summary_text(text)
    if len(text) <= max_len:
        return text
    return text[:max_len].rstrip() + "…"


def merge_arxiv_into_summary(summary: str, abstract: str, arxiv_meta: ArxivMeta | None) -> str:
    if arxiv_meta and arxiv_meta.summary:
        return sentenceish(normalize_summary_text(arxiv_meta.summary))
    if abstract:
        return sentenceish(normalize_summary_text(abstract))
    return summary


def derive_summary_fields(html: str, title: str, kind: str, source: str, arxiv_meta: ArxivMeta | None = None) -> tuple[str, str, list[str]]:
    abstract = extract_abstract(html) or ""
    desc = extract_description(html) or ""
    paragraphs = extract_paragraphs(html)
    basis = choose_summary_basis(source, html, desc, abstract, paragraphs)
    summary = sentenceish(normalize_summary_text(basis)) if basis else ""
    if source.casefold() == "arxiv":
        summary = merge_arxiv_into_summary(summary, abstract, arxiv_meta)
    why = build_why_save(kind, source, summary)
    points: list[str] = []
    seed_points = ([arxiv_meta.summary] if arxiv_meta and arxiv_meta.summary else [abstract] if abstract else [])
    if source.casefold() in {"openai.com", "anthropic.com", "vercel.com"} and desc:
        seed_points = [desc] + seed_points
    if source.casefold() in {"github.blog", "github.com", "huggingface.co", "huggingface.blog"} and desc:
        seed_points = [desc] + seed_points
    if not abstract or source != 'arXiv':
        seed_points += paragraphs
    for para in seed_points[:4]:
        point = sentenceish(normalize_summary_text(para), max_len=160)
        if point and point not in points:
            points.append(point)
    if not points and summary:
        points.append(summary)
    return summary, why, points[:3]


def build_note(meta: NoteMeta) -> str:
    tags_line = " ".join(meta.tags or (["#ai", "#paper"] if meta.kind == "papers" else ["#ai", "#link"]))
    selected_block = (
        f"## Selected excerpt\n> {meta.selected_text.replace(chr(10), chr(10) + '> ')}\n\n"
        if meta.selected_text else ""
    )
    if meta.kind == "papers":
        points = meta.key_points or [""]
        points_block = "\n".join(f"- {p}" if p else "- " for p in points[:3])
        summary = meta.summary or ""
        why = meta.why_save or ""
        extra = meta.extra_meta or {}
        authors = extra.get("authors") if isinstance(extra.get("authors"), list) else []
        categories = extra.get("categories") if isinstance(extra.get("categories"), list) else []
        arxiv_id = extra.get("arxiv_id") if isinstance(extra.get("arxiv_id"), str) else ""
        published = extra.get("published") if isinstance(extra.get("published"), str) else ""
        updated = extra.get("updated") if isinstance(extra.get("updated"), str) else ""
        author_display, all_authors = format_authors(authors)
        author_line = f"- Authors: {author_display}\n" if author_display else ""
        arxiv_line = f"- arXiv: {arxiv_id}\n" if arxiv_id else ""
        published_line = f"- Published: {published}\n" if published else ""
        updated_line = f"- Updated: {updated}\n" if updated and updated != published else ""
        category_line = f"- Categories: {', '.join(categories)}\n" if categories else ""
        all_authors_block = f"## All authors\n- {all_authors}\n\n" if all_authors else ""
        return (
            f"# {meta.title}\n\n"
            f"- Source: {meta.source}\n"
            f"- Date: {meta.note_date}\n"
            f"- Link: {meta.link}\n"
            f"{arxiv_line}"
            f"{published_line}"
            f"{updated_line}"
            f"{author_line}"
            f"{category_line}"
            f"- Tags: {tags_line}\n\n"
            f"## TL;DR\n- {summary}\n\n"
            f"## Why it matters\n{why or '- '}\n\n"
            f"{selected_block}"
            f"{all_authors_block}"
            f"## Key points\n{points_block}\n\n"
            f"## Notes\n- \n"
        )
    summary = meta.summary or ""
    why = meta.why_save or "- "
    return (
        f"# {meta.title}\n\n"
        f"- Source: {meta.source}\n"
        f"- Date: {meta.note_date}\n"
        f"- Link: {meta.link}\n"
        f"- Tags: {tags_line}\n\n"
        f"## One-line summary\n- {summary}\n\n"
        f"## Why save this\n{why}\n\n"
        f"{selected_block}"
        f"## Notes\n- \n"
    )


def prepare_note(
    url: str,
    vault_path: Path,
    note_date: str,
    explicit_kind: str,
    title_override: str | None,
    selected_text: str = "",
    summary_override: str = "",
) -> NoteMeta:
    validate_http_url(url)
    validate_note_date_text(note_date)
    html = fetch_html(url)
    kind = infer_kind(url, explicit_kind)
    source = infer_source(url)
    arxiv_meta = None
    if source == "arXiv":
        arxiv_id = extract_arxiv_id(url)
        if arxiv_id:
            arxiv_meta = fetch_arxiv_meta(arxiv_id)
    title = clean_title(title_override or (arxiv_meta.title if arxiv_meta and arxiv_meta.title else "") or extract_title(html) or url, source)
    summary, why_save, points = derive_summary_fields(html, title, kind, source, arxiv_meta)
    override = normalize_summary_override(summary_override)
    if override:
        summary = override
        why_save = build_why_save(kind, source, summary)
    folder = vault_path / ("Papers" if kind == "papers" else "Links") / note_date
    filename = slugify_filename(title) + ".md"
    duplicate_urls, duplicate_titles = scan_duplicates(vault_path, title, url)
    extra_meta = None
    if arxiv_meta:
        extra_meta = {
            "arxiv_id": arxiv_meta.arxiv_id,
            "authors": arxiv_meta.authors,
            "published": arxiv_meta.published,
            "updated": arxiv_meta.updated,
            "categories": arxiv_meta.categories,
        }
    tags = build_tags(kind, source, arxiv_meta)
    return NoteMeta(source, title, url, kind, note_date, folder, folder / filename, duplicate_urls, duplicate_titles, summary, why_save, points, extra_meta, tags, normalize_selected_text(selected_text))


def archive_destination(vault_path: Path, path: Path) -> Path:
    return vault_path / "Archive" / path.relative_to(vault_path)


def excerpt_for_merge(content: str, max_lines: int = 12) -> str:
    lines = [line.rstrip() for line in content.splitlines()]
    filtered = []
    for line in lines:
        if line.startswith("# "):
            continue
        if line.startswith("- Date:") or line.startswith("- 날짜:"):
            continue
        filtered.append(line)
    filtered = [line for line in filtered if line.strip()]
    return "\n".join(filtered[:max_lines]).strip()


def print_recommendation(paths: list[Path], vault_path: Path) -> tuple[Path, dict[Path, tuple[int, list[str]]]]:
    keep, scored = choose_canonical(paths)
    keep_score, keep_reasons = scored[keep]
    print(f"  keep: {keep.relative_to(vault_path)}")
    print(f"    score: {keep_score} | {', '.join(keep_reasons)}")
    for path in paths:
        if path == keep:
            continue
        score, reasons = scored[path]
        print(f"  candidate: {path.relative_to(vault_path)}")
        print(f"    score: {score} | {', '.join(reasons)}")
    return keep, scored


def apply_archive(vault_path: Path, paths: list[Path], keep: Path, dry_run: bool) -> list[str]:
    actions = []
    for path in paths:
        if path == keep:
            continue
        dest = archive_destination(vault_path, path)
        actions.append(f"archive {path.relative_to(vault_path)} -> {dest.relative_to(vault_path)}")
        if dry_run:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            stem = dest.stem
            suffix = dest.suffix
            idx = 2
            while True:
                alt = dest.with_name(f"{stem} ({idx}){suffix}")
                if not alt.exists():
                    dest = alt
                    break
                idx += 1
        shutil.move(str(path), str(dest))
    return actions


def apply_merge_assist(vault_path: Path, paths: list[Path], keep: Path, dry_run: bool) -> list[str]:
    keep_text = read_text(keep)
    blocks = []
    actions = []
    for path in paths:
        if path == keep:
            continue
        rel = path.relative_to(vault_path)
        block_header = f"### From {rel}"
        if block_header in keep_text:
            actions.append(f"skip merge {rel} (already noted)")
            continue
        excerpt = excerpt_for_merge(read_text(path))
        if not excerpt:
            continue
        blocks.append(f"{block_header}\n\n```markdown\n{excerpt}\n```")
        actions.append(f"merge excerpt from {rel}")
    if not blocks:
        return actions
    addition = "\n\n" + MERGE_MARKER + "\n\n" + "\n\n".join(blocks) + "\n"
    if dry_run:
        return actions
    updated = keep_text.rstrip() + ("\n\n" + "\n\n".join(blocks) + "\n" if MERGE_MARKER in keep_text else addition)
    keep.write_text(updated, encoding="utf-8")
    return actions


def process_group(label: str, paths: list[Path], vault_path: Path, args: argparse.Namespace) -> bool:
    print(label)
    for path in paths:
        print(f"  - {path.relative_to(vault_path)}")
    need_keep = args.recommend or args.archive_recommended or args.merge_assist or getattr(args, "cleanup", False)
    keep = None
    if need_keep:
        keep, _ = print_recommendation(paths, vault_path)
    summary_actions: list[str] = []
    if args.merge_assist or getattr(args, "cleanup", False):
        keep = keep or choose_canonical(paths)[0]
        summary_actions.extend(apply_merge_assist(vault_path, paths, keep, dry_run=not args.apply))
    if args.archive_recommended or getattr(args, "cleanup", False):
        keep = keep or choose_canonical(paths)[0]
        summary_actions.extend(apply_archive(vault_path, paths, keep, dry_run=not args.apply))
    if summary_actions:
        print("  planned actions:" if not args.apply else "  applied actions:")
        for action in summary_actions:
            print(f"    - {action}")
    print()
    return True


def run_dedupe_like(args: argparse.Namespace) -> int:
    vault_path = load_vault_path(args.vault_name, args.vault_path)
    by_url, by_title = collect_duplicate_groups(vault_path)
    printed = False
    if not args.titles_only:
        for url, paths in sorted(by_url.items(), key=lambda item: (-len(item[1]), item[0])):
            printed = process_group(f"URL DUPLICATE: {url}", paths, vault_path, args) or printed
    if not args.urls_only:
        for _, paths in sorted(by_title.items(), key=lambda item: (-len(item[1]), str(item[1][0]))):
            printed = process_group(f"TITLE DUPLICATE: {paths[0].stem}", paths, vault_path, args) or printed
    if not printed:
        print("No duplicates found")
    if (getattr(args, "archive_recommended", False) or getattr(args, "merge_assist", False) or getattr(args, "cleanup", False)) and not args.apply:
        print("SUMMARY: dry run only. Add --apply to actually write merges or archive duplicates.")
    return 0


def cmd_save(args: argparse.Namespace) -> int:
    vault_path = load_vault_path(args.vault_name, args.vault_path)
    note_date = args.date or date.today().isoformat()
    try:
        meta = prepare_note(args.url, vault_path, note_date, args.kind, args.title)
    except ValueError as exc:
        eprint(str(exc))
        return 2
    print(f"vault: {vault_path}")
    print(f"kind: {meta.kind}")
    print(f"title: {meta.title}")
    print(f"path: {meta.path}")
    if meta.tags:
        print(f"tags: {' '.join(meta.tags)}")
    if meta.extra_meta:
        for key in ("arxiv_id", "published", "updated"):
            value = meta.extra_meta.get(key)
            if value:
                print(f"{key}: {value}")
        authors = meta.extra_meta.get("authors")
        if authors:
            author_display, _ = format_authors(authors)
            print(f"authors: {author_display}")
        categories = meta.extra_meta.get("categories")
        if categories:
            print(f"categories: {', '.join(categories)}")
    if meta.summary:
        print(f"summary_draft: {meta.summary}")
    if meta.key_points:
        for idx, point in enumerate(meta.key_points[:3], start=1):
            print(f"key_point_{idx}: {point}")
    if meta.duplicate_urls:
        print("duplicate_url:")
        for path in meta.duplicate_urls:
            print(f"  - {path.relative_to(vault_path)}")
    if meta.duplicate_titles:
        print("duplicate_title:")
        for path in meta.duplicate_titles:
            print(f"  - {path.relative_to(vault_path)}")
    if args.dry_run:
        return 0
    if not write_note_file(meta.path, build_note(meta), force=args.force):
        eprint(f"Refusing to overwrite existing note: {meta.path}")
        eprint("Use --force to overwrite or --dry-run to inspect.")
        return 2
    print("saved")
    return 0


def cmd_dedupe(args: argparse.Namespace) -> int:
    return run_dedupe_like(args)


def cmd_cleanup(args: argparse.Namespace) -> int:
    args.cleanup = True
    args.recommend = True
    args.merge_assist = False
    args.archive_recommended = False
    return run_dedupe_like(args)


def cmd_recap(args: argparse.Namespace) -> int:
    vault_path = load_vault_path(args.vault_name, args.vault_path)
    anchor = parse_note_date(args.anchor_date) if args.anchor_date else date.today()
    if anchor is None:
        eprint(f"Invalid anchor date: {args.anchor_date}")
        return 2
    if args.week:
        start = anchor - timedelta(days=anchor.weekday())
        end = start + timedelta(days=6)
    else:
        start = anchor - timedelta(days=6)
        end = anchor
    items = collect_recap_items(vault_path, start, end)
    papers = [item for item in items if item.kind == "papers"]
    links = [item for item in items if item.kind == "links"]
    sources: dict[str, int] = defaultdict(int)
    for item in items:
        sources[item.source] += 1
    previous_items = None
    previous_start = None
    previous_end = None
    if args.compare_previous:
        span_days = (end - start).days + 1
        previous_end = start - timedelta(days=1)
        previous_start = previous_end - timedelta(days=span_days - 1)
        previous_items = collect_recap_items(vault_path, previous_start, previous_end)

    output = build_recap_output(items, papers, links, sources, start, end, vault_path, previous_items, previous_start, previous_end)
    note_path = recap_note_path(vault_path, start, end)
    if args.save_note:
        print(f"note_path: {note_path}")
        if args.dry_run:
            print(output, end="")
            return 0
        if not write_note_file(note_path, output, force=args.force):
            eprint(f"Refusing to overwrite existing recap note: {note_path}")
            eprint("Use --force to overwrite or --dry-run to inspect.")
            return 2
        print("saved")
        return 0
    if args.output:
        out_path = Path(args.output).expanduser()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output, encoding="utf-8")
        print(out_path)
        return 0
    print(output, end="")
    return 0


def add_common_scan_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--vault-name", default="AI", help="Vault folder name from obsidian.json")
    parser.add_argument("--vault-path", help="Explicit vault path")
    parser.add_argument("--urls-only", action="store_true", help="Show URL duplicates only")
    parser.add_argument("--titles-only", action="store_true", help="Show title duplicates only")
    parser.add_argument("--apply", action="store_true", help="Actually perform merge/archive writes (default is dry run)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Save AI paper/link notes into an Obsidian vault")
    sub = parser.add_subparsers(dest="command", required=True)

    save = sub.add_parser("save", help="Create a note from a URL")
    save.add_argument("url", help="Article or paper URL")
    save.add_argument("--title", help="Manual title override")
    save.add_argument("--kind", choices=["auto", "papers", "links"], default="auto")
    save.add_argument("--date", help="Override date folder (YYYY-MM-DD)")
    save.add_argument("--vault-name", default="AI", help="Vault folder name from obsidian.json")
    save.add_argument("--vault-path", help="Explicit vault path")
    save.add_argument("--dry-run", action="store_true", help="Preview without writing")
    save.add_argument("--force", action="store_true", help="Overwrite if target file exists")
    save.set_defaults(func=cmd_save)

    dedupe = sub.add_parser("dedupe", help="List duplicate notes by URL/title")
    add_common_scan_args(dedupe)
    dedupe.add_argument("--recommend", action="store_true", help="Suggest which note to keep")
    dedupe.add_argument("--merge-assist", action="store_true", help="Append candidate excerpts into the kept note")
    dedupe.add_argument("--archive-recommended", action="store_true", help="Archive non-kept duplicate candidates")
    dedupe.set_defaults(func=cmd_dedupe, cleanup=False)

    cleanup = sub.add_parser("cleanup", help="One-shot merge-assist + archive flow for duplicates")
    add_common_scan_args(cleanup)
    cleanup.set_defaults(func=cmd_cleanup, cleanup=True)

    recap = sub.add_parser("recap", help="Generate a markdown recap from recent notes")
    recap.add_argument("--week", action="store_true", help="Use the Monday-Sunday week containing the anchor date")
    recap.add_argument("--anchor-date", help="Anchor date for the recap range (YYYY-MM-DD)")
    recap.add_argument("--vault-name", default="AI", help="Vault folder name from obsidian.json")
    recap.add_argument("--vault-path", help="Explicit vault path")
    recap.add_argument("--output", help="Write recap markdown to a file instead of stdout")
    recap.add_argument("--save-note", action="store_true", help="Save recap into the vault under Recaps/<end-date>/")
    recap.add_argument("--dry-run", action="store_true", help="Preview recap note path/content without writing")
    recap.add_argument("--force", action="store_true", help="Overwrite recap note if it already exists")
    recap.add_argument("--compare-previous", action="store_true", help="Compare against the immediately preceding period of the same length")
    recap.set_defaults(func=cmd_recap)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except (URLError, HTTPError) as exc:
        eprint(f"Network error: {exc}")
        return 1
    except KeyboardInterrupt:
        eprint("Cancelled")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
