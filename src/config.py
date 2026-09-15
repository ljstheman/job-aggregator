"""config.json 로더."""
from __future__ import annotations

import json
import os
from pathlib import Path

DEFAULT_CONFIG_PATH = "config.json"


def load_config(path: str = DEFAULT_CONFIG_PATH) -> dict:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(
            f"{path} 파일이 없습니다. config.example.json을 복사해 config.json으로 만들고 "
            "사람인 API 키 등을 채워주세요."
        )
    with config_path.open(encoding="utf-8") as f:
        cfg = json.load(f)

    cfg.setdefault("filters", {})
    cfg["filters"].setdefault("keywords", [])
    cfg["filters"].setdefault("regions", [])
    cfg["filters"].setdefault("exclude_keywords", [])
    cfg["filters"].setdefault("career_levels", [])
    cfg["filters"].setdefault("career_level_exempt_sources", [])
    cfg["filters"].setdefault("min_experience_years", 0)
    cfg["filters"].setdefault("exclude_junior_titles", False)
    cfg["filters"].setdefault("min_salary_manwon", 0)
    cfg.setdefault("db_path", "data/jobs.db")
    # DART_API_KEY 환경변수가 있으면 최우선 사용 (git에 커밋되는 어떤 파일에도
    # 실제 키를 넣지 않기 위함). config.json의 dart_api_key는 로컬 전용 대체 수단.
    cfg["dart_api_key"] = os.environ.get("DART_API_KEY") or cfg.get("dart_api_key", "")
    return cfg
