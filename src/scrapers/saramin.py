"""사람인(Saramin) 스크레이퍼.

공식 오픈 API 대신 검색결과 페이지를 직접 파싱한다 (jobkorea.py와 동일한 방식).
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

SEARCH_URL = "https://www.saramin.co.kr/zf_user/search/recruit"
BASE_URL = "https://www.saramin.co.kr"
MAX_PAGES_PER_KEYWORD = 3

# 2026-08 기준 실제 사이트 구조 확인 완료 (전통적인 semantic class 구조라 비교적 안정적).
# 사이트 개편 시 가장 먼저 확인할 것: div.item_recruit이 여전히 존재하는지.
_ITEM_SELECTOR = "div.item_recruit"
_REC_IDX_RE = re.compile(r"rec_idx=(\d+)")


class SaraminScraper(BaseScraper):
    source_name = "saramin"

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
                    params = {"recruitPage": page}
                    if keyword:
                        params["searchword"] = keyword
                    try:
                        resp = session.get(SEARCH_URL, params=params, timeout=15)
                        resp.raise_for_status()
                    except requests.RequestException as e:
                        logger.warning("saramin 요청 실패 (keyword=%s, page=%d): %s", keyword, page, e)
                        break

                    page_postings = self._parse_page(resp.text)
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
            logger.warning("saramin: 파싱된 공고가 0건입니다. 셀렉터를 실제 사이트와 대조해 확인하세요.")

        logger.info("saramin: %d건 수집", len(postings))
        return postings

    def _parse_page(self, html: str) -> list[JobPosting]:
        soup = BeautifulSoup(html, "lxml")
        items = soup.select(_ITEM_SELECTOR)
        results: list[JobPosting] = []

        for item in items:
            title_link = item.select_one("h2.job_tit a")
            if not title_link:
                continue

            external_id = item.get("value", "")
            if not external_id:
                match = _REC_IDX_RE.search(title_link.get("href", ""))
                external_id = match.group(1) if match else ""
            if not external_id:
                continue

            title = title_link.get("title") or title_link.get_text(strip=True)
            if not title:
                continue

            url = urljoin(BASE_URL, f"/zf_user/jobs/relay/view?rec_idx={external_id}")

            company_el = item.select_one("div.area_corp strong.corp_name a")

            conditions = item.select("div.job_condition > span")
            location = conditions[0].get_text(" ", strip=True) if len(conditions) > 0 else ""
            career_level = conditions[1].get_text(strip=True) if len(conditions) > 1 else ""
            employment_type = conditions[3].get_text(strip=True) if len(conditions) > 3 else ""

            deadline_el = item.select_one("div.job_date span.date")

            sector_el = item.select_one("div.job_sector")
            tags = [a.get_text(strip=True) for a in sector_el.select("a")] if sector_el else []

            results.append(
                JobPosting(
                    source=self.source_name,
                    external_id=external_id,
                    url=url,
                    title=title,
                    company=company_el.get_text(strip=True) if company_el else "",
                    location=location,
                    career_level=career_level,
                    employment_type=employment_type,
                    description="",  # 목록 페이지만 파싱 (상세 페이지는 v1 범위 밖)
                    tags=tags,
                    deadline=deadline_el.get_text(strip=True) if deadline_el else None,
                    raw_json=json.dumps({"html_snippet": str(item)[:2000]}, ensure_ascii=False),
                )
            )

        return results
