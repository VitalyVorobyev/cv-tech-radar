from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import feedparser
import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from radar.models import Item, RawItem, Source
from radar.schemas import ItemType, NormalizedItem, SourceConfig
from radar.utils import normalize_title, normalize_whitespace, utc_now


@dataclass(frozen=True)
class ArxivFetchStats:
    fetched: int = 0
    stored: int = 0
    updated: int = 0
    skipped_old: int = 0


def fetch_and_store_arxiv(
    session: Session,
    source: Source,
    source_config: SourceConfig,
    *,
    days: int,
    max_results: int = 100,
    client: httpx.Client | None = None,
    now: datetime | None = None,
) -> ArxivFetchStats:
    now = now or utc_now()
    cutoff = now - timedelta(days=days)
    fetched = stored = updated = skipped_old = 0

    owns_client = client is None
    if client is None:
        client = httpx.Client(timeout=30, follow_redirects=True)

    try:
        for category in source_config.categories:
            entries = _fetch_category_entries(
                client=client,
                base_url=str(source_config.url),
                category=category,
                max_results=max_results,
            )
            fetched += len(entries)
            for entry in entries:
                normalized, raw_payload = normalize_arxiv_entry(
                    entry, source_name=source_config.name, category=category
                )
                if normalized.published_at < cutoff:
                    skipped_old += 1
                    continue
                was_stored = store_normalized_item(
                    session=session,
                    source=source,
                    normalized=normalized,
                    raw_payload=raw_payload,
                )
                if was_stored:
                    stored += 1
                else:
                    updated += 1
    finally:
        if owns_client:
            client.close()

    return ArxivFetchStats(fetched=fetched, stored=stored, updated=updated, skipped_old=skipped_old)


def _fetch_category_entries(
    *,
    client: httpx.Client,
    base_url: str,
    category: str,
    max_results: int,
) -> list[dict[str, Any]]:
    response = client.get(
        base_url,
        params={
            "search_query": f"cat:{category}",
            "start": 0,
            "max_results": max_results,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        },
    )
    response.raise_for_status()
    feed = feedparser.parse(response.text)
    return list(feed.entries)


def normalize_arxiv_entry(
    entry: dict[str, Any],
    *,
    source_name: str = "arXiv",
    category: str = "cs.CV",
) -> tuple[NormalizedItem, dict[str, Any]]:
    title = normalize_whitespace(entry.get("title"))
    summary = normalize_whitespace(entry.get("summary"))
    abs_url = entry.get("id") or entry.get("link") or ""
    arxiv_id = _extract_arxiv_id(abs_url)
    pdf_url = _extract_pdf_url(entry, arxiv_id)
    published_at = _parsed_datetime(entry.get("published_parsed")) or utc_now()
    updated_at = _parsed_datetime(entry.get("updated_parsed"))
    authors = _extract_authors(entry)
    categories = _extract_categories(entry)

    metadata = {
        "category": category,
        "categories": categories,
        "primary_category": entry.get("arxiv_primary_category", {}).get("term"),
        "comment": normalize_whitespace(entry.get("arxiv_comment")),
        "journal_ref": normalize_whitespace(entry.get("arxiv_journal_ref")),
    }
    raw_payload = {
        "id": entry.get("id"),
        "title": title,
        "summary": summary,
        "link": entry.get("link"),
        "links": [
            {
                "href": link.get("href"),
                "rel": link.get("rel"),
                "type": link.get("type"),
                "title": link.get("title"),
            }
            for link in entry.get("links", [])
        ],
        "authors": authors,
        "published": entry.get("published"),
        "updated": entry.get("updated"),
        "categories": categories,
        "metadata": metadata,
    }

    normalized = NormalizedItem(
        type=ItemType.PAPER,
        title=title,
        abstract_or_summary=summary,
        url=abs_url,
        pdf_url=pdf_url,
        published_at=published_at,
        updated_at=updated_at,
        source_name=source_name,
        external_id=arxiv_id,
        arxiv_id=arxiv_id,
        authors=authors,
        metadata=metadata,
    )
    return normalized, raw_payload


def store_normalized_item(
    *,
    session: Session,
    source: Source,
    normalized: NormalizedItem,
    raw_payload: dict[str, Any],
) -> bool:
    raw_item = None
    if normalized.external_id:
        raw_item = session.scalar(
            select(RawItem).where(
                RawItem.source_id == source.id,
                RawItem.external_id == normalized.external_id,
            )
        )
    if raw_item is None:
        raw_item = RawItem(
            source_id=source.id,
            external_id=normalized.external_id,
            url=normalized.url,
            raw_payload_json=raw_payload,
        )
        session.add(raw_item)
    else:
        raw_item.url = normalized.url
        raw_item.raw_payload_json = raw_payload
        raw_item.fetched_at = utc_now()

    item = _find_existing_item(session, normalized)
    created = item is None
    if item is None:
        item = Item(
            type=normalized.type.value,
            title=normalized.title,
            normalized_title=normalize_title(normalized.title),
            url=normalized.url,
            published_at=normalized.published_at,
            source_name=normalized.source_name,
            external_id=normalized.external_id,
        )
        session.add(item)

    item.type = normalized.type.value
    item.title = normalized.title
    item.normalized_title = normalize_title(normalized.title)
    item.abstract_or_summary = normalized.abstract_or_summary
    item.url = normalized.url
    item.pdf_url = normalized.pdf_url
    item.published_at = normalized.published_at
    item.updated_at = normalized.updated_at
    item.source_name = normalized.source_name
    item.external_id = normalized.external_id
    item.doi = normalized.doi
    item.arxiv_id = normalized.arxiv_id
    item.authors_json = normalized.authors
    item.organizations_json = normalized.organizations
    item.metadata_json = normalized.metadata
    return created


def _find_existing_item(session: Session, normalized: NormalizedItem) -> Item | None:
    if normalized.external_id:
        found = session.scalar(
            select(Item).where(
                Item.source_name == normalized.source_name,
                Item.external_id == normalized.external_id,
            )
        )
        if found is not None:
            return found
    return session.scalar(
        select(Item).where(Item.normalized_title == normalize_title(normalized.title))
    )


def _extract_arxiv_id(url: str) -> str | None:
    match = re.search(r"arxiv\.org/(?:abs|pdf)/([^?#]+)", url)
    if match is None:
        return None
    arxiv_id = match.group(1).removesuffix(".pdf")
    return re.sub(r"v\d+$", "", arxiv_id)


def _extract_pdf_url(entry: dict[str, Any], arxiv_id: str | None) -> str | None:
    for link in entry.get("links", []):
        if link.get("type") == "application/pdf" or link.get("title") == "pdf":
            return link.get("href")
    if arxiv_id:
        return f"https://arxiv.org/pdf/{arxiv_id}"
    return None


def _parsed_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    return datetime.fromtimestamp(calendar.timegm(value), tz=UTC)


def _extract_authors(entry: dict[str, Any]) -> list[str]:
    authors = entry.get("authors") or []
    names = [normalize_whitespace(author.get("name")) for author in authors if author.get("name")]
    if names:
        return names
    author = normalize_whitespace(entry.get("author"))
    return [author] if author else []


def _extract_categories(entry: dict[str, Any]) -> list[str]:
    return [
        tag.get("term")
        for tag in entry.get("tags", [])
        if isinstance(tag, dict) and tag.get("term")
    ]
