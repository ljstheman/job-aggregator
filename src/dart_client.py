"""금융감독원 OpenDART API 연동 (회사 매출액 조회).

회사명으로 매출 규모를 조회해 공고 정렬에 사용한다. 상장사/외부감사대상 법인만
DART에 데이터가 있으므로, 조회 안 되는 회사는 규모 미상으로 처리한다.
"""
from __future__ import annotations

import io
import json
import logging
import re
import time
import zipfile
from pathlib import Path
from xml.etree import ElementTree

import requests

logger = logging.getLogger(__name__)

CORP_CODE_URL = "https://opendart.fss.or.kr/api/corpCode.xml"
FINANCIALS_URL = "https://opendart.fss.or.kr/api/fnlttSinglAcnt.json"

CORP_CODE_CACHE_PATH = "data/dart_corp_codes.json"
FINANCIALS_CACHE_PATH = "data/dart_financials.json"

CORP_CODE_CACHE_TTL_DAYS = 30
FINANCIALS_CACHE_TTL_DAYS = 90

# 최근 연도부터 역순으로 조회 시도 (당해 사업보고서는 다음해 3월 이후 제출됨)
_REPORT_CODE_ANNUAL = "11011"

_STRIP_RE = re.compile(r"(주식회사|㈜|\(주\)|\(유\)|유한회사|외투기업협의회)")
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_company_name(name: str) -> str:
    name = _STRIP_RE.sub("", name)
    name = _WHITESPACE_RE.sub("", name)
    return name.strip().lower()


def _load_json(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_json(path: str, data: dict) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _is_stale(fetched_at: str | None, ttl_days: int) -> bool:
    if not fetched_at:
        return True
    from datetime import datetime, timezone

    try:
        ts = datetime.fromisoformat(fetched_at)
    except ValueError:
        return True
    age_days = (datetime.now(timezone.utc) - ts).total_seconds() / 86400
    return age_days > ttl_days


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def load_or_fetch_corp_codes(api_key: str, cache_path: str = CORP_CODE_CACHE_PATH) -> dict:
    """정규화된 회사명 -> corp_code 매핑. 로컬 캐시가 유효하면 재사용."""
    cache = _load_json(cache_path)
    if cache.get("entries") and not _is_stale(cache.get("fetched_at"), CORP_CODE_CACHE_TTL_DAYS):
        return cache["entries"]

    logger.info("DART 기업코드 전체 목록 다운로드 중...")
    resp = requests.get(CORP_CODE_URL, params={"crtfc_key": api_key}, timeout=30)
    resp.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        xml_bytes = zf.read("CORPCODE.xml")

    root = ElementTree.fromstring(xml_bytes)
    entries: dict[str, list[dict]] = {}
    for item in root.iter("list"):
        corp_name = (item.findtext("corp_name") or "").strip()
        corp_code = (item.findtext("corp_code") or "").strip()
        stock_code = (item.findtext("stock_code") or "").strip()
        if not corp_name or not corp_code:
            continue
        key = normalize_company_name(corp_name)
        entries.setdefault(key, []).append(
            {"corp_code": corp_code, "corp_name": corp_name, "stock_code": stock_code}
        )

    _save_json(cache_path, {"fetched_at": _now_iso(), "entries": entries})
    logger.info("DART 기업코드 %d개 회사명 매핑 완료", len(entries))
    return entries


def _pick_corp_entry(candidates: list[dict]) -> dict:
    """동명 회사가 여러 개면 상장사(stock_code 있음)를 우선한다."""
    for c in candidates:
        if c.get("stock_code"):
            return c
    return candidates[0]


def _fetch_revenue_for_year(api_key: str, corp_code: str, year: int) -> int | None:
    params = {
        "crtfc_key": api_key,
        "corp_code": corp_code,
        "bsns_year": str(year),
        "reprt_code": _REPORT_CODE_ANNUAL,
    }
    try:
        resp = requests.get(FINANCIALS_URL, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError):
        return None

    if data.get("status") != "000":
        return None

    for row in data.get("list", []):
        if row.get("sj_div") == "IS" and row.get("account_nm") in ("매출액", "수익(매출액)"):
            amount_str = row.get("thstrm_amount", "").replace(",", "")
            if amount_str.lstrip("-").isdigit():
                return int(amount_str)
    return None


def build_company_revenue_map(
    company_names: set[str], api_key: str, years_back: int = 3
) -> dict[str, dict]:
    """회사명 -> {"revenue": 원단위 매출액 또는 None, "year": 조회연도 또는 None}."""
    from datetime import datetime

    corp_codes = load_or_fetch_corp_codes(api_key)
    cache = _load_json(FINANCIALS_CACHE_PATH)
    cache.setdefault("companies", {})

    result: dict[str, dict] = {}
    current_year = datetime.now().year

    for name in company_names:
        key = normalize_company_name(name)
        cached = cache["companies"].get(key)
        if cached and not _is_stale(cached.get("fetched_at"), FINANCIALS_CACHE_TTL_DAYS):
            result[name] = {"revenue": cached.get("revenue"), "year": cached.get("year")}
            continue

        candidates = corp_codes.get(key)
        revenue = None
        found_year = None
        if candidates:
            entry = _pick_corp_entry(candidates)
            for y in range(current_year - 1, current_year - 1 - years_back, -1):
                revenue = _fetch_revenue_for_year(api_key, entry["corp_code"], y)
                if revenue is not None:
                    found_year = y
                    break

        cache["companies"][key] = {
            "revenue": revenue,
            "year": found_year,
            "fetched_at": _now_iso(),
        }
        result[name] = {"revenue": revenue, "year": found_year}

    _save_json(FINANCIALS_CACHE_PATH, cache)
    return result
