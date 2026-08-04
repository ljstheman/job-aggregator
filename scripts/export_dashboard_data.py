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
from src.filters import apply_filters, build_filters_from_config
from src.storage import init_db, query_postings


def export(config_path: str = "config.json", out_path: str | None = None) -> dict:
    cfg = load_config(config_path)
    conn = init_db(cfg.get("db_path", "data/jobs.db"))
    all_postings = query_postings(conn)
    conn.close()

    filters = build_filters_from_config(cfg)
    filtered = apply_filters(all_postings, filters)

    def to_display_dict(posting):
        d = posting.to_dict()
        d.pop("raw_json", None)  # 대시보드 표시에 불필요, 용량만 키움
        return d

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_postings": len(all_postings),
        "filtered_postings": len(filtered),
        "filters": cfg.get("filters", {}),
        "postings": [to_display_dict(p) for p in filtered],
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
