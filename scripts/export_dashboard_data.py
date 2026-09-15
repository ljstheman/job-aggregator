"""DB에서 필터링된 공고를 JSON으로 추출한다 (아티팩트 생성용).

사용법: python -m scripts.export_dashboard_data [--config config.json] [--out dashboard_data.json]
결과 JSON은 아티팩트 대시보드가 그대로 임베드할 수 있는 형태다.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import load_config
from src.dart_client import build_company_revenue_map
from src.filters import apply_filters, build_filters_from_config
from src.storage import init_db, query_postings

PHARMA_KEYWORDS = ["제약", "바이오", "파마", "의약품"]


def _to_display_dict(posting) -> dict:
    d = posting.to_dict()
    d.pop("raw_json", None)  # 대시보드 표시에 불필요, 용량만 키움
    return d


def _is_pharma(d: dict) -> bool:
    haystack = " ".join([d.get("title", ""), d.get("company", ""), " ".join(d.get("tags", []))])
    return any(k in haystack for k in PHARMA_KEYWORDS)


def _broaden_with_conditional_keywords(all_postings: list, cfg: dict, base_keys: set) -> list:
    """conditional_keywords(예: 해외영업/수출)까지 포함해서 다시 필터링하고,
    기본 필터 결과에는 없던 공고만 후보로 반환한다. 최종 포함 여부는
    회사 매출(중견기업 이상)로 별도 검증한다."""
    conditional_keywords = cfg.get("filters", {}).get("conditional_keywords", [])
    if not conditional_keywords:
        return []

    broadened_cfg = {**cfg, "filters": {**cfg.get("filters", {})}}
    broadened_cfg["filters"]["keywords"] = (
        cfg.get("filters", {}).get("keywords", []) + conditional_keywords
    )
    broadened = apply_filters(all_postings, build_filters_from_config(broadened_cfg))
    return [p for p in broadened if (p.source, p.external_id) not in base_keys]


def export(config_path: str = "config.json", out_path: str | None = None) -> dict:
    cfg = load_config(config_path)
    conn = init_db(cfg.get("db_path", "data/jobs.db"))
    all_postings = query_postings(conn)
    conn.close()

    base_filtered = apply_filters(all_postings, build_filters_from_config(cfg))
    base_keys = {(p.source, p.external_id) for p in base_filtered}

    extra_candidates = _broaden_with_conditional_keywords(all_postings, cfg, base_keys)

    base_dicts = [_to_display_dict(p) for p in base_filtered]
    extra_dicts = [_to_display_dict(p) for p in extra_candidates]

    dart_api_key = cfg.get("dart_api_key", "")
    all_company_names = {d["company"] for d in base_dicts + extra_dicts if d.get("company")}
    revenue_map = (
        build_company_revenue_map(all_company_names, dart_api_key) if dart_api_key else {}
    )

    # 조건부 후보(해외영업/수출 등)는 회사 매출이 중견기업 이상 기준을 넘을 때만 최종 포함
    min_revenue_won = (
        cfg.get("filters", {}).get("conditional_keywords_min_revenue_eok", 0) * 100_000_000
    )
    qualifying_extra = []
    for d in extra_dicts:
        revenue = revenue_map.get(d["company"], {}).get("revenue")
        if revenue is not None and revenue >= min_revenue_won:
            qualifying_extra.append(d)

    final_dicts = base_dicts + qualifying_extra
    for d in final_dicts:
        info = revenue_map.get(d["company"], {})
        d["revenue"] = info.get("revenue")
        d["revenue_year"] = info.get("year")
        d["pharma"] = _is_pharma(d)

    # 제약/바이오 업계 최상단 우선, 그 다음 매출 내림차순 (매출 정보 없으면 맨 뒤)
    final_dicts.sort(key=lambda d: (0 if d["pharma"] else 1, d["revenue"] is None, -(d["revenue"] or 0)))

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_postings": len(all_postings),
        "filtered_postings": len(final_dicts),
        "filters": cfg.get("filters", {}),
        "postings": final_dicts,
    }

    if out_path:
        out_file = Path(out_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="대시보드용 데이터 추출")
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--out", default="artifact/dashboard_data.json")
    args = parser.parse_args()

    payload = export(args.config, args.out)
    print(f"{payload['filtered_postings']}건 추출 (전체 {payload['total_postings']}건) -> {args.out}")


if __name__ == "__main__":
    main()
