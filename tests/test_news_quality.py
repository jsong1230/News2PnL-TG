"""뉴스 품질 및 필터링 테스트"""
import pytest
from datetime import datetime
from pytz import UTC
from src.news.base import NewsItem
from src.news.quality import (
    calculate_quality_score,
    calculate_title_quality_score,
    get_source_reliability,
    is_high_quality_title,
    filter_by_quality,
    sort_by_quality
)
from src.utils.text import normalize_title, jaccard_similarity


def test_normalize_title():
    assert normalize_title("삼성전자, 반도체 업황 개선!") == "삼성전자 반도체 업황 개선"
    assert normalize_title("SK하이닉스 (000660)") == "sk하이닉스 000660"
    assert normalize_title("  공백   테스트  ") == "공백 테스트"
    assert normalize_title(None) == ""


def test_jaccard_similarity():
    s1 = "삼성전자 반도체 실적 발표"
    s2 = "실적 발표 삼성전자 반도체"
    assert jaccard_similarity(normalize_title(s1), normalize_title(s2)) == 1.0
    
    s3 = "삼성전자 주가 급등"
    assert jaccard_similarity(normalize_title(s1), normalize_title(s3)) < 0.5
    assert jaccard_similarity("", "") == 0.0


def test_get_source_reliability():
    assert get_source_reliability("연합뉴스") == 1.0
    assert get_source_reliability("한국경제TV") == 0.95
    assert get_source_reliability("매일경제") == 0.95
    assert get_source_reliability("알 수 없는 출처") == 0.5
    assert get_source_reliability("") == 0.5


def test_is_high_quality_title():
    # 고품질 제목
    assert is_high_quality_title("삼성전자, 4분기 영업이익 10조 원 돌파... 반도체 부활 신호탄") is True
    
    # 저품질 제목 (너무 짧음)
    assert is_high_quality_title("속보입니다") is False
    
    # 저품질 제목 (과도한 특수문자)
    assert is_high_quality_title("!!!대박!!! 100% 급등주 공개 !?!?") is False
    
    # 저품질 제목 (과도한 대문자)
    assert is_high_quality_title("BREAKING NEWS: SAMSUNG ELECTRONICS Q4 PROFITS SURGE") is False


def test_calculate_title_quality_score():
    score1 = calculate_title_quality_score("정상적인 뉴스 제목입니다")
    score2 = calculate_title_quality_score("!!!대박!!!")
    assert score1 > score2


def test_calculate_quality_score():
    item = NewsItem(
        title="삼성전자, HBM3E 양산 준비 완료... 엔비디아 공급 임박",
        url="https://news.naver.com/1",
        published_at=datetime.now(UTC),
        source="연합뉴스"
    )
    score = calculate_quality_score(item)
    assert score >= 0.75
    
    item_bad = NewsItem(
        title="헐 대박 ㅋ",
        url="https://unknown.com/1",
        published_at=None,
        source=None
    )
    score_bad = calculate_quality_score(item_bad)
    assert score_bad < 0.5


def test_filter_by_quality():
    items = [
        NewsItem("좋은 뉴스 제목입니다 (연합뉴스)", "url1", datetime.now(UTC), "연합뉴스"),
        NewsItem("나쁜! 뉴스! 제목!", "url2", datetime.now(UTC), "불확실"),
    ]
    filtered = filter_by_quality(items, min_quality_score=0.7)
    assert len(filtered) == 1
    assert filtered[0].source == "연합뉴스"


def test_sort_by_quality():
    items = [
        NewsItem("나쁜 뉴스", "url1", datetime.now(UTC), "출처"),
        NewsItem("아주 좋은 뉴스 제목 (연합뉴스)", "url2", datetime.now(UTC), "연합뉴스"),
    ]
    sorted_items = sort_by_quality(items)
    assert sorted_items[0].source == "연합뉴스"
