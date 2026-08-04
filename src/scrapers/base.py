"""스크레이퍼 공통 인터페이스."""
from __future__ import annotations

from abc import ABC, abstractmethod

from src.models import JobPosting


class BaseScraper(ABC):
    source_name: str

    def __init__(self, config: dict):
        self.config = config

    @abstractmethod
    def fetch(self) -> list[JobPosting]:
        """공고 목록을 수집해 JobPosting 리스트로 정규화한다.
        페이지네이션/재시도/속도 조절은 구현체가 책임진다."""
        raise NotImplementedError
