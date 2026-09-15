"""피플앤잡(peoplenjob.com) 스크레이퍼. 외국계 기업 채용에 특화된 사이트.

검색결과 페이지가 서버에서 HTML로 직접 렌더링되어(사람인/잡코리아와 동일한 방식) requests+BeautifulSoup으로 수집 가능하다.
주의: 사이트 개편 시 아래 CSS 셀렉터가 깨질 수 있다. 파싱 결과가 계속 0건이면
가장 먼저 `_ITEM_SELECTOR` 등 셀렉터를 실제 페이지 구조와 대조해 갱신할 것.
"""
from __future__ import annotations

import json
import logging
import re
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from src.models import JobPosting
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

SEARCH_URL = "https://www.peoplenjob.com/jobs"
BASE_URL = "https://www.peoplenjob.com"
MAX_PAGES_PER_KEYWORD = 3

# 2026-09 기준 실제 사이트 구조 확인 완료.
# 사이트 개편 시 가장 먼저 확인할 것: div.jd-card가 여전히 존재하는지.
_ITEM_SELECTOR = "div.jd-card"
_JOB_ID_RE = re.compile(r"/jobs/(\d+)")


class PeopleNJobScraper(BaseScraper):
    source_name = "peoplenjob"

    def fetch(self) -> list[JobPosting]:
        keywords: list[str] = self.config.get("_keywords") or [""]
        delay = float(self.config.get("request_delay_seconds", 2.0))
        headers = {
            "User-Agent": self.config.get(
                "user_agent", "JobAggregatorBot/1.0 (personal use)"
            )
        }

        seen_ids: set[str] = set()
        postings: list[JobPosting] = []

        with requests.Session() as session:
            session.headers.update(headers)

            for keyword in keywords:
                for page in range(1, MAX_PAGES_PER_KEYWORD + 1):
                    params = {"page": page}
                    if keyword:
                        params["keyword"] = keyword
                    try:
                        resp = session.get(SEARCH_URL, params=params, timeout=15)
                        resp.raise_for_status()
                    except requests.RequestException as e:
                        logger.warning(
                            "peoplenjob 요청 실패 (keyword=%s, page=%d): %s", keyword, page, e
                        )
                        break

                    page_postings = self._parse_page(resp.text, keyword)
                    if not page_postings:
                        break

                    new_on_page = 0
                    for posting in page_postings:
                        if posting.external_id in seen_ids:
                            continue
                        seen_ids.add(posting.external_id)
                        postings.append(posting)
                        new_on_page += 1

                    time.sleep(delay)
                    if new_on_page == 0:
                        break

        if not postings:
            logger.warning("peoplenjob: 파싱된 공고가 0건입니다. 셀렉터를 실제 사이트와 대조해 확인하세요.")

        logger.info("peoplenjob: %d건 수집", len(postings))
        return postings

    def _parse_page(self, html: str, keyword: str = "") -> list[JobPosting]:
        soup = BeautifulSoup(html, "lxml")
        items = soup.select(_ITEM_SELECTOR)
        results: list[JobPosting] = []

        for item in items:
            title_link = item.select_one("h5.jd-card-title a")
            if not title_link:
                continue

            href = title_link.get("href", "")
            match = _JOB_ID_RE.search(href)
            external_id = match.group(1) if match else ""
            if not external_id:
                continue

            title = title_link.get_text(strip=True)
            if not title:
                continue

            url = urljoin(BASE_URL, f"/jobs/{external_id}")

            company_el = item.select_one("a.jd-card-company")

            location_el = item.select_one("span.jd-card-meta-location-text")
            career_el = item.select_one("span.jd-card-meta-career-text")

            deadline_el = item.select_one("span.job-fin-date")

            results.append(
                JobPosting(
                    source=self.source_name,
                    external_id=external_id,
                    url=url,
                    title=title,
                    company=company_el.get_text(strip=True) if company_el else "",
                    location=location_el.get_text(strip=True) if location_el else "",
                    career_level=career_el.get_text(strip=True) if career_el else "",
                    employment_type="",
                    description="",  # 목록 페이지만 파싱 (상세 페이지는 v1 범위 밖)
                    # 목록 페이지에 태그가 없어 대신 검색에 사용한 키워드를 태그로 남긴다
                    # (조회 시점 키워드 필터가 title/tags만 보므로, 사이트 자체 검색 관련도를 보존하기 위함).
                    tags=[keyword] if keyword else [],
                    deadline=deadline_el.get_text(strip=True) if deadline_el else None,
                    raw_json=json.dumps({"html_snippet": str(item)[:2000]}, ensure_ascii=False),
                )
            )

        return results
