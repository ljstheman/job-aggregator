"""공고 필터 (키워드/지역/경력). 조회 시점에만 적용하며 DB에는 전량 저장한다."""
from __future__ import annotations

from typing import Protocol

from src.models import JobPosting


class Filter(Protocol):
    def matches(self, posting: JobPosting) -> bool: ...


class KeywordFilter:
    """제목/tags/description 중 하나라도 키워드를 포함하면 매치 (OR)."""

    def __init__(self, keywords: list[str]):
        self.keywords = [k.lower() for k in keywords if k]

    def matches(self, posting: JobPosting) -> bool:
        if not self.keywords:
            return True
        haystack = " ".join(
            [posting.title, posting.description, " ".join(posting.tags)]
        ).lower()
        return any(k in haystack for k in self.keywords)


class RegionFilter:
    """location에 지역명이 부분 일치하면 매치 (OR)."""

    def __init__(self, regions: list[str]):
        self.regions = [r for r in regions if r]

    def matches(self, posting: JobPosting) -> bool:
        if not self.regions:
            return True
        return any(r in posting.location for r in self.regions)


class CareerLevelFilter:
    """career_level에 지정한 값 중 하나라도 부분 일치하면 매치 (OR)."""

    def __init__(self, career_levels: list[str]):
        self.career_levels = [c for c in career_levels if c]

    def matches(self, posting: JobPosting) -> bool:
        if not self.career_levels:
            return True
        return any(c in posting.career_level for c in self.career_levels)


def build_filters_from_config(cfg: dict) -> list[Filter]:
    filters_cfg = cfg.get("filters", {})
    return [
        KeywordFilter(filters_cfg.get("keywords", [])),
        RegionFilter(filters_cfg.get("regions", [])),
        CareerLevelFilter(filters_cfg.get("career_levels", [])),
    ]


def apply_filters(postings: list[JobPosting], filters: list[Filter]) -> list[JobPosting]:
    """필터 종류 간 AND. 각 필터 내부는 위 클래스들이 OR로 처리."""
    return [p for p in postings if all(f.matches(p) for f in filters)]
