"""잡코리아(JobKorea) 스크레이퍼.

잡코리아는 공식 오픈 API가 없어 검색결과 페이지를 직접 파싱한다.
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

SEARCH_URL = "https://www.jobkorea.co.kr/Search/"
BASE_URL = "https://www.jobkorea.co.kr"
MAX_PAGES_PER_KEYWORD = 3

# 검색결과 목록의 공고 카드 하나에 해당하는 셀렉터 (2026-08 기준 실제 사이트 구조 확인 완료).
# 잡코리아는 React 기반이라 CSS 클래스는 유틸리티성(예: "flex gap-5")이라 불안정하지만,
# data-sentry-component 속성은 컴포넌트 단위로 비교적 안정적이어서 이를 기준으로 삼는다.
# 사이트 개편 시 가장 먼저 확인할 것: div[data-sentry-component="CardJob"]이 여전히 존재하는지.
_ITEM_SELECTOR = 'div[data-sentry-component="CardJob"]'
_EXTERNAL_ID_RE = re.compile(r"/Recruit/GI_Read/(\d+)")
_CAREER_RE = re.compile(r"(신입/경력|경력무관|신입|경력)")


class JobKoreaScraper(BaseScraper):
    source_name = "jobkorea"

    def fetch(self) -> list[JobPosting]:
        keywords: list[str] = self.config.get("_keywords") or [""]
        delay = float(self.config.get("request_delay_seconds", 2.0))
        headers = {
            "User-Agent": self.config.get(
                "user_agent", "JobAggregatorBot/1.0 (personal use)"
            )
        }

        seen_urls: set[str] = set()
        postings: list[JobPosting] = []

        with requests.Session() as session:
            session.headers.update(headers)

            for keyword in keywords:
                for page in range(1, MAX_PAGES_PER_KEYWORD + 1):
                    params = {"stext": keyword, "Page_No": page} if keyword else {"Page_No": page}
                    try:
                        resp = session.get(SEARCH_URL, params=params, timeout=15)
                        resp.raise_for_status()
                    except requests.RequestException as e:
                        logger.warning("jobkorea 요청 실패 (keyword=%s, page=%d): %s", keyword, page, e)
                        break

                    page_postings = self._parse_page(resp.text)
                    if not page_postings:
                        break

                    new_on_page = 0
                    for posting in page_postings:
                        if posting.url in seen_urls:
                            continue
                        seen_urls.add(posting.url)
                        postings.append(posting)
                        new_on_page += 1

                    time.sleep(delay)
                    if new_on_page == 0:
                        break

        if not postings:
            logger.warning("jobkorea: 파싱된 공고가 0건입니다. 셀렉터를 실제 사이트와 대조해 확인하세요.")

        logger.info("jobkorea: %d건 수집", len(postings))
        return postings

    def _parse_page(self, html: str) -> list[JobPosting]:
        soup = BeautifulSoup(html, "lxml")
        items = soup.select(_ITEM_SELECTOR)
        results: list[JobPosting] = []

        for item in items:
            title_link = item.select_one('a[data-sentry-component="Title"]')
            if not title_link or not title_link.get("href"):
                continue

            href = urljoin(BASE_URL, title_link["href"]).split("?")[0]
            match = _EXTERNAL_ID_RE.search(title_link["href"])
            external_id = match.group(1) if match else href

            title = title_link.get_text(strip=True)
            if not title:
                continue

            company_el = item.select_one("span.text-gray700")
            chips = item.select('[data-sentry-component="GrayChip"]')
            location = chips[0].get_text(strip=True) if chips else ""
            # 직무 태그(2번째 칩)를 tags로 저장 (쉼표/가운뎃점 구분자를 모두 분리)
            tags: list[str] = []
            if len(chips) > 1:
                raw = chips[1].get_text(strip=True)
                tags = [t.strip() for t in re.split(r"[,·]", raw) if t.strip()]

            career_match = _CAREER_RE.search(title)
            career_level = career_match.group(1) if career_match else ""

            results.append(
                JobPosting(
                    source=self.source_name,
                    external_id=external_id,
                    url=href,
                    title=title,
                    company=company_el.get_text(strip=True) if company_el else "",
                    location=location,
                    career_level=career_level,
                    description="",  # 목록 페이지만 파싱 (상세 페이지는 v1 범위 밖)
                    tags=tags,
                    raw_json=json.dumps({"html_snippet": str(item)[:2000]}, ensure_ascii=False),
                )
            )

        return results
