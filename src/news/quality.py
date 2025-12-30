"""뉴스 품질 평가 모듈"""
from typing import Dict, List
import re
from src.news.base import NewsItem


# 출처별 신뢰도 매핑 (0.0 ~ 1.0)
SOURCE_RELIABILITY: Dict[str, float] = {
    # 주요 경제 언론
    "연합뉴스": 1.0,
    "한국경제": 0.95,
    "매일경제": 0.95,
    "서울경제": 0.95,
    "이데일리": 0.9,
    "뉴스1": 0.9,
    "뉴시스": 0.9,
    
    # 종합 일간지
    "조선일보": 0.9,
    "중앙일보": 0.9,
    "동아일보": 0.9,
    "경향신문": 0.85,
    "한겨레": 0.85,
    
    # IT/기술 전문
    "전자신문": 0.9,
    "디지털타임스": 0.85,
    "ZDNet Korea": 0.85,
    
    # 방송사
    "KBS": 0.9,
    "MBC": 0.85,
    "SBS": 0.85,
    "JTBC": 0.85,
    
    # 해외 주요 언론
    "Bloomberg": 1.0,
    "Reuters": 1.0,
    "Wall Street Journal": 0.95,
    "Financial Times": 0.95,
    "CNBC": 0.9,
    "CNN": 0.85,
    
    # 기타
    "기타": 0.5,
}


def get_source_reliability(source: str) -> float:
    """
    출처별 신뢰도 반환
    
    Args:
        source: 뉴스 출처명
    
    Returns:
        신뢰도 점수 (0.0 ~ 1.0)
    """
    if not source:
        return SOURCE_RELIABILITY["기타"]
    
    # 정확히 일치하는 출처 찾기
    if source in SOURCE_RELIABILITY:
        return SOURCE_RELIABILITY[source]
    
    # 부분 일치 찾기 (예: "한국경제TV" -> "한국경제")
    for known_source, reliability in SOURCE_RELIABILITY.items():
        if known_source in source or source in known_source:
            return reliability
    
    return SOURCE_RELIABILITY["기타"]


def is_high_quality_title(title: str) -> bool:
    """
    제목이 고품질인지 판단
    
    Args:
        title: 뉴스 제목
    
    Returns:
        고품질 여부
    """
    if not title or len(title.strip()) == 0:
        return False
    
    title = title.strip()
    
    # 너무 짧은 제목 (10자 미만)
    if len(title) < 10:
        return False
    
    # 너무 긴 제목 (200자 초과)
    if len(title) > 200:
        return False
    
    # 과도한 특수문자 (전체의 30% 이상)
    special_chars = re.findall(r'[!?@#$%^&*()_+=\[\]{}|\\:;"\'<>,.~`]', title)
    if len(special_chars) / len(title) > 0.3:
        return False
    
    # 과도한 대문자 (영문의 70% 이상)
    english_chars = re.findall(r'[a-zA-Z]', title)
    if english_chars:
        uppercase_chars = re.findall(r'[A-Z]', title)
        if len(uppercase_chars) / len(english_chars) > 0.7:
            return False
    
    # 연속된 특수문자 (3개 이상)
    if re.search(r'[!?]{3,}', title):
        return False
    
    return True


def calculate_title_quality_score(title: str) -> float:
    """
    제목 품질 점수 계산
    
    Args:
        title: 뉴스 제목
    
    Returns:
        품질 점수 (0.0 ~ 1.0)
    """
    if not title:
        return 0.0
    
    title = title.strip()
    score = 1.0
    
    # 길이 평가 (최적: 20~100자)
    length = len(title)
    if length < 10:
        score *= 0.5
    elif length < 20:
        score *= 0.8
    elif length > 150:
        score *= 0.8
    elif length > 200:
        score *= 0.5
    
    # 특수문자 비율 평가
    special_chars = re.findall(r'[!?@#$%^&*()_+=\[\]{}|\\:;"\'<>,.~`]', title)
    special_ratio = len(special_chars) / len(title) if len(title) > 0 else 0
    if special_ratio > 0.3:
        score *= 0.5
    elif special_ratio > 0.2:
        score *= 0.7
    elif special_ratio > 0.1:
        score *= 0.9
    
    # 연속 특수문자 페널티
    if re.search(r'[!?]{3,}', title):
        score *= 0.3
    elif re.search(r'[!?]{2}', title):
        score *= 0.8
    
    # 대문자 비율 평가 (영문만)
    english_chars = re.findall(r'[a-zA-Z]', title)
    if english_chars:
        uppercase_chars = re.findall(r'[A-Z]', title)
        uppercase_ratio = len(uppercase_chars) / len(english_chars)
        if uppercase_ratio > 0.7:
            score *= 0.5
        elif uppercase_ratio > 0.5:
            score *= 0.8
    
    return max(0.0, min(1.0, score))


def calculate_quality_score(item: NewsItem) -> float:
    """
    뉴스 아이템의 종합 품질 점수 계산
    
    Args:
        item: 뉴스 아이템
    
    Returns:
        품질 점수 (0.0 ~ 1.0)
    
    평가 기준:
    - 제목 품질 (40%)
    - 출처 신뢰도 (40%)
    - 발행 시간 유무 (20%)
    """
    # 제목 품질 (40%)
    title_score = calculate_title_quality_score(item.title) * 0.4
    
    # 출처 신뢰도 (40%)
    source_score = get_source_reliability(item.source) * 0.4
    
    # 발행 시간 유무 (20%)
    time_score = 0.2 if item.published_at else 0.0
    
    total_score = title_score + source_score + time_score
    
    return round(total_score, 3)


def filter_by_quality(
    news_items: List[NewsItem],
    min_quality_score: float = 0.5
) -> List[NewsItem]:
    """
    품질 점수 기준으로 뉴스 필터링
    
    Args:
        news_items: 뉴스 아이템 리스트
        min_quality_score: 최소 품질 점수 (기본 0.5)
    
    Returns:
        필터링된 뉴스 리스트
    """
    filtered = []
    
    for item in news_items:
        quality_score = calculate_quality_score(item)
        if quality_score >= min_quality_score:
            filtered.append(item)
    
    return filtered


def sort_by_quality(news_items: List[NewsItem], reverse: bool = True) -> List[NewsItem]:
    """
    품질 점수 기준으로 뉴스 정렬
    
    Args:
        news_items: 뉴스 아이템 리스트
        reverse: True면 높은 점수부터 (기본), False면 낮은 점수부터
    
    Returns:
        정렬된 뉴스 리스트
    """
    return sorted(
        news_items,
        key=lambda item: calculate_quality_score(item),
        reverse=reverse
    )
