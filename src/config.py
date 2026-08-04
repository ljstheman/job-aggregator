"""config.json 로더."""
from __future__ import annotations

import json
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
    cfg["filters"].setdefault("career_levels", [])
    cfg.setdefault("db_path", "data/jobs.db")
    return cfg
