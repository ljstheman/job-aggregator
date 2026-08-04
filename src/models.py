"""공고 데이터 모델."""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class JobPosting:
    source: str  # "saramin" | "jobkorea" | ...
    external_id: str  # 출처 내 원본 공고 ID
    url: str  # 공고 원문 링크 (external_id를 못 구할 때 dedupe 대체 키)
    title: str
    company: str
    location: str = ""
    career_level: str = ""  # 정규화: "신입" | "경력" | "신입/경력" | "무관"
    employment_type: str = ""
    description: str = ""  # 전체 설명 텍스트 (향후 이력서 매칭용)
    tags: list[str] = field(default_factory=list)
    posted_at: str | None = None
    deadline: str | None = None
    fetched_at: str = ""
    raw_json: str = ""

    def tags_json(self) -> str:
        return json.dumps(self.tags, ensure_ascii=False)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
