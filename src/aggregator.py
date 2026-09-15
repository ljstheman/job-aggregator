"""취업공고 수집 CLI 진입점.

사용법: python -m src.aggregator [--config config.json] [--verbose]
"""
from __future__ import annotations

import argparse
import logging
import sys

from src.config import load_config
from src.scrapers.base import BaseScraper
from src.scrapers.saramin import SaraminScraper
from src.scrapers.jobkorea import JobKoreaScraper
from src.scrapers.peoplenjob import PeopleNJobScraper
from src.storage import count_postings, init_db, upsert_posting

logger = logging.getLogger(__name__)

# 새 사이트 추가 시: scrapers/에 클래스 구현 + 여기 한 줄만 등록
SCRAPERS: dict[str, type[BaseScraper]] = {
    "saramin": SaraminScraper,
    "jobkorea": JobKoreaScraper,
    "peoplenjob": PeopleNJobScraper,
}


def run(config_path: str = "config.json") -> int:
    try:
        cfg = load_config(config_path)
    except FileNotFoundError as e:
        logger.error(str(e))
        return 1

    try:
        conn = init_db(cfg.get("db_path", "data/jobs.db"))
    except Exception as e:  # noqa: BLE001 - DB 접근 실패는 치명적 오류
        logger.error("DB 초기화 실패: %s", e)
        return 1

    summary_lines = []
    total_new = 0

    for name, scraper_cls in SCRAPERS.items():
        site_cfg = cfg.get(name, {})
        if not site_cfg.get("enabled", False):
            continue

        # 필터의 키워드를 스크레이퍼에 힌트로 전달 (서버 사이드 검색 최적화용, 최종 필터는 조회 시점에 적용)
        site_cfg = {**site_cfg, "_keywords": cfg.get("filters", {}).get("keywords", [])}

        try:
            scraper = scraper_cls(site_cfg)
            postings = scraper.fetch()
        except Exception as e:  # noqa: BLE001 - 한 사이트 실패해도 나머지는 계속 진행
            logger.warning("%s 수집 실패: %s", name, e)
            summary_lines.append(f"  {name:8s}: 수집 실패 ({e})")
            continue

        new_count = 0
        for posting in postings:
            if upsert_posting(conn, posting):
                new_count += 1
        total_new += new_count

        if postings and new_count == 0 and len(postings) == 0:
            logger.warning("%s: 파싱된 공고가 0건입니다. 사이트 구조가 바뀌었을 수 있습니다.", name)

        summary_lines.append(
            f"  {name:8s}: {len(postings)}건 수집, {new_count}건 신규, "
            f"{len(postings) - new_count}건 기존"
        )

    total = count_postings(conn)
    conn.close()

    print("취업공고 수집 완료")
    print("\n".join(summary_lines))
    print(f"이번 실행 신규 공고: {total_new}건")
    print(f"DB 누적 공고 수: {total}건 ({cfg.get('db_path', 'data/jobs.db')})")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="취업공고 취합 도구")
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    sys.exit(run(args.config))


if __name__ == "__main__":
    main()
