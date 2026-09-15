"""공고 필터 (키워드/지역/경력). 조회 시점에만 적용하며 DB에는 전량 저장한다."""
from __future__ import annotations

import re
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


class ExcludeKeywordFilter:
    """제목/tags에 제외 키워드가 하나라도 포함되면 제외 (긍정 키워드와 무관하게 우선 적용).
    예: '수입'이 '수입차'에도 부분일치하는 것처럼, 검색 키워드가 의도와 다른 업종에
    걸리는 경우를 걸러내기 위함."""

    def __init__(self, keywords: list[str]):
        self.keywords = [k.lower() for k in keywords if k]

    def matches(self, posting: JobPosting) -> bool:
        if not self.keywords:
            return True
        haystack = " ".join(
            [posting.title, posting.employment_type, " ".join(posting.tags)]
        ).lower()
        return not any(k in haystack for k in self.keywords)


class RegionFilter:
    """location에 지역명이 부분 일치하면 매치 (OR)."""

    def __init__(self, regions: list[str]):
        self.regions = [r for r in regions if r]

    def matches(self, posting: JobPosting) -> bool:
        if not self.regions:
            return True
        return any(r in posting.location for r in self.regions)


class CareerLevelFilter:
    """career_level에 지정한 값 중 하나라도 부분 일치하면 매치 (OR).

    exempt_sources에 포함된 출처는 이 필터를 적용하지 않는다. 피플앤잡처럼
    career_level 표기 체계가 달라(예: '대리.과장') 매칭 자체가 무의미한 사이트를 위함."""

    def __init__(self, career_levels: list[str], exempt_sources: list[str] | None = None):
        self.career_levels = [c for c in career_levels if c]
        self.exempt_sources = set(exempt_sources or [])

    def matches(self, posting: JobPosting) -> bool:
        if not self.career_levels or posting.source in self.exempt_sources:
            return True
        return any(c in posting.career_level for c in self.career_levels)


_YEAR_RANGE_RE = re.compile(r"(\d+)\s*[-~]\s*(\d+)\s*년")

_JUNIOR_TITLE_KEYWORDS = ["인턴", "사원", "주임", "사무보조", "아르바이트", "일용직", "수습"]

_SALARY_EOK_RE = re.compile(r"(?:초봉|연봉)\s*(\d(?:\.\d)?)\s*억")
_SALARY_CHEON_RE = re.compile(r"(?:초봉|연봉)\s*(\d{1,2})\s*천\s*만?\s*원?")
_SALARY_MANWON_RE = re.compile(r"(?:초봉|연봉)\s*(\d{3,5})\s*만\s*원?")


class ExperienceYearsFilter:
    """제목/career_level에 '1-3년'처럼 상한 연차가 명시된 공고만 대상으로,
    상한이 min_years 미만이면 제외한다. 연차가 명시 안 된 공고는 통과시킨다."""

    def __init__(self, min_years: int):
        self.min_years = min_years

    def matches(self, posting: JobPosting) -> bool:
        if self.min_years <= 0:
            return True
        haystack = f"{posting.title} {posting.career_level}"
        m = _YEAR_RANGE_RE.search(haystack)
        if not m:
            return True
        return int(m.group(2)) >= self.min_years


class JuniorTitleFilter:
    """제목에 '인턴/사원/주임' 등 주니어급 직급 표현이 있으면 제외."""

    def __init__(self, enabled: bool, keywords: list[str] | None = None):
        self.enabled = enabled
        self.keywords = keywords or _JUNIOR_TITLE_KEYWORDS

    def matches(self, posting: JobPosting) -> bool:
        if not self.enabled:
            return True
        return not any(k in posting.title for k in self.keywords)


class SalaryFilter:
    """제목에 '초봉4천', '연봉3000만원'처럼 구체적 금액이 명시된 경우만 대상으로,
    min_manwon(만원) 미만이면 제외한다. 금액이 명시 안 된 공고는 통과시킨다."""

    def __init__(self, min_manwon: int):
        self.min_manwon = min_manwon

    def _parse_manwon(self, text: str) -> int | None:
        m = _SALARY_EOK_RE.search(text)
        if m:
            return int(float(m.group(1)) * 10000)
        m = _SALARY_CHEON_RE.search(text)
        if m:
            return int(m.group(1)) * 1000
        m = _SALARY_MANWON_RE.search(text)
        if m:
            return int(m.group(1))
        return None

    def matches(self, posting: JobPosting) -> bool:
        if self.min_manwon <= 0:
            return True
        amount = self._parse_manwon(posting.title)
        if amount is None:
            return True
        return amount >= self.min_manwon


def build_filters_from_config(cfg: dict) -> list[Filter]:
    filters_cfg = cfg.get("filters", {})
    return [
        KeywordFilter(filters_cfg.get("keywords", [])),
        ExcludeKeywordFilter(filters_cfg.get("exclude_keywords", [])),
        RegionFilter(filters_cfg.get("regions", [])),
        CareerLevelFilter(
            filters_cfg.get("career_levels", []),
            exempt_sources=filters_cfg.get("career_level_exempt_sources", []),
        ),
        ExperienceYearsFilter(filters_cfg.get("min_experience_years", 0)),
        JuniorTitleFilter(filters_cfg.get("exclude_junior_titles", False)),
        SalaryFilter(filters_cfg.get("min_salary_manwon", 0)),
    ]


def apply_filters(postings: list[JobPosting], filters: list[Filter]) -> list[JobPosting]:
    """필터 종류 간 AND. 각 필터 내부는 위 클래스들이 OR로 처리."""
    return [p for p in postings if all(f.matches(p) for f in filters)]
