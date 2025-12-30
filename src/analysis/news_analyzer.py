"""뉴스 분석 및 다이제스트 생성 모듈"""
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import re
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from pytz import UTC

from src.news.base import NewsItem
from src.analysis.sector_keywords import SECTOR_KEYWORDS
from src.utils.text import normalize_title, jaccard_similarity

logger = logging.getLogger(__name__)


@dataclass
class NewsDigest:
    """뉴스 다이제스트"""
    top_headlines: List[str]  # 최대 8개
    macro_summary: str  # 5줄 이내
    sector_bullets: Dict[str, List[str]]  # 섹터별 뉴스 (섹터 5개 정도)
    korea_impact: str  # "상/중/하" + 이유 한 줄
    sources: List[str]  # URL 리스트 (중복 제거, 최대 5개)
    fetched_count: int  # 수집된 총 기사 수
    time_filtered_count: int  # 시간 필터 후 기사 수
    deduped_count: int  # 중복 제거 후 기사 수
    headline_debug: Optional[Dict[str, Dict[str, float]]] = None  # 헤드라인별 디버그 정보 (제목 -> 디버그 딕셔너리)


# 노이즈 필터 키워드
NOISE_KEYWORDS = [
    "할인", "이벤트", "프로모션", "쿠폰", "카톡 친구", "오픈", "출시 기념", "연휴",
    "맛집", "닭갈비", "연예", "결혼", "스캔들", "날씨", "운세", "부동산 분양",
    "기념일", "축제", "행사", "공연", "영화", "드라마", "예능", "가수", "아이돌",
    "패션", "뷰티", "화장품", "식품", "레시피", "요리", "여행", "관광", "호텔",
    "카지노", "로또", "복권", "경품", "추첨", "당첨", "무료", "증정", "사은품"
]

# 시장 관련도 우선순위 키워드 (가중치 높음)
MARKET_KEYWORDS = {
    # 증시/주가 (가중치 10)
    "증시": 10, "주가": 10, "코스피": 10, "코스닥": 10, "kospi": 10, "kosdaq": 10,
    "s&p": 10, "sp500": 10, "s&p 500": 10, "s&p500": 10,
    "나스닥": 10, "nasdaq": 10, "다우": 10, "dow": 10,
    
    # 금리/연준 (가중치 9)
    "연준": 9, "fed": 9, "기준금리": 9, "금리": 9, "cpi": 9, "ppi": 9, "pce": 9,
    "인플레이션": 9, "인플레": 9,
    
    # 환율/달러 (가중치 8)
    "환율": 8, "달러": 8, "원달러": 8, "dxy": 8, "달러인덱스": 8,
    
    # 유가/원자재 (가중치 8)
    "유가": 8, "원유": 8, "wti": 8, "브렌트": 8, "석유": 8,
    
    # 반도체/AI (가중치 9)
    "반도체": 9, "칩": 9, "메모리": 9, "dram": 9, "nand": 9, "hbm": 9,
    "ai": 9, "인공지능": 9, "chatgpt": 9, "gpt": 9, "llm": 9,
    "엔비디아": 9, "nvidia": 9, "amd": 9, "tsmc": 9, "대만반도체": 9,
    
    # 주요 종목 (가중치 8)
    "삼성전자": 8, "sk하이닉스": 8, "하이닉스": 8, "sk hynix": 8,
    
    # 실적/수출 (가중치 7)
    "실적": 7, "수출": 7, "수입": 7, "무역": 7,
    
    # 정책/규제 (가중치 7)
    "규제": 7, "관세": 7, "정책": 7, "법안": 7,
    
    # 지정학/방산 (가중치 7)
    "지정학": 7, "전쟁": 7, "방산": 7, "방위": 7,
}

# 클릭베이트 키워드 (감점 대상)
CLICKBAIT_KEYWORDS = [
    "폭발", "대박", "지금 담아라", "100조", "3배", "확정", "급등 예상", "급락 예상",
    "반드시", "확실히", "100%", "무조건", "절대", "완전", "엄청", "엄청난",
    "충격", "충격적", "폭락 예고", "폭등 예고", "급등장", "급락장", "대폭",
    "역대급", "최고", "최대", "최악", "최저", "신기록", "역사적"
]

# 신뢰성 높은 출처 도메인 (클릭베이트 감점 완화)
CREDIBLE_DOMAINS = [
    "bloomberg.com", "reuters.com", "wsj.com", "ft.com", "economist.com",
    "yna.co.kr", "yna.kr", "yna.com",  # 연합뉴스
    "yna.co.kr", "yna.kr", "yna.com",  # 연합뉴스
    "chosun.com", "joongang.co.kr", "donga.com", "hani.co.kr",  # 한국 언론
    "mk.co.kr", "etnews.com", "fnnews.com", "edaily.co.kr"  # 경제 전문지
]


# ... (locally removed normalize_title and jaccard_similarity)


def is_noise_article(title: str, source: str = "", url: str = "") -> bool:
    """
    노이즈 기사 판단 (광고/생활뉴스 제외)
    
    Args:
        title: 기사 제목
        source: 출처 (선택)
        url: URL (선택)
    
    Returns:
        True면 노이즈 (제외 대상)
    """
    text = (title + " " + source + " " + url).lower()
    
    # 노이즈 키워드 체크
    for keyword in NOISE_KEYWORDS:
        if keyword in text:
            return True
    
    return False


def calculate_freshness_score(item: NewsItem, now_utc: Optional[datetime] = None) -> float:
    """
    신선도 점수 계산 (기사 시각 기반 감쇠)
    
    Args:
        item: 뉴스 아이템
        now_utc: 현재 시각 (UTC, None이면 현재 시각 사용)
    
    Returns:
        신선도 점수 (0.0 ~ 1.0, 높을수록 최근)
    """
    if not item.published_at:
        return 0.5  # 날짜 없으면 중간값
    
    if now_utc is None:
        now_utc = datetime.now(UTC)
    
    item_utc = item.published_at
    if item_utc.tzinfo != UTC:
        item_utc = item_utc.astimezone(UTC)
    
    hours_ago = (now_utc - item_utc).total_seconds() / 3600
    
    # 감쇠 함수: 0시간=1.0, 12시간=0.5, 24시간=0.2, 48시간=0.05
    if hours_ago <= 0:
        return 1.0
    elif hours_ago <= 12:
        # 0~12시간: 선형 감쇠 1.0 -> 0.5
        return 1.0 - (hours_ago / 12) * 0.5
    elif hours_ago <= 24:
        # 12~24시간: 선형 감쇠 0.5 -> 0.2
        return 0.5 - ((hours_ago - 12) / 12) * 0.3
    elif hours_ago <= 48:
        # 24~48시간: 선형 감쇠 0.2 -> 0.05
        return 0.2 - ((hours_ago - 24) / 24) * 0.15
    else:
        # 48시간 이상: 0.05 고정
        return 0.05


def calculate_novelty_score(
    item: NewsItem,
    other_items: List[NewsItem],
    now_utc: Optional[datetime] = None
) -> Tuple[float, float]:
    """
    새로움 점수 및 반복 페널티 계산
    
    Args:
        item: 현재 뉴스 아이템
        other_items: 다른 뉴스 아이템 리스트 (비교 대상)
        now_utc: 현재 시각 (UTC, None이면 현재 시각 사용)
    
    Returns:
        (novelty_score, repeat_penalty) 튜플
        - novelty_score: 0.0 ~ 1.0 (높을수록 새로움)
        - repeat_penalty: 0.0 ~ 1.0 (높을수록 반복 심함)
    """
    if not item.published_at:
        return (0.5, 0.0)  # 날짜 없으면 중간값
    
    if now_utc is None:
        now_utc = datetime.now(UTC)
    
    item_utc = item.published_at
    if item_utc.tzinfo != UTC:
        item_utc = item_utc.astimezone(UTC)
    
    item_normalized = normalize_title(item.title)
    
    # 24~72시간 내 유사한 제목 찾기
    similar_count = 0
    similar_items = []
    
    for other in other_items:
        if other == item or not other.published_at:
            continue
        
        other_utc = other.published_at
        if other_utc.tzinfo != UTC:
            other_utc = other_utc.astimezone(UTC)
        
        hours_diff = abs((item_utc - other_utc).total_seconds() / 3600)
        
        # 24~72시간 범위 내만 체크
        if 24 <= hours_diff <= 72:
            other_normalized = normalize_title(other.title)
            
            # Jaccard 유사도와 SequenceMatcher 유사도 중 높은 값 사용
            jaccard_sim = jaccard_similarity(item_normalized, other_normalized)
            seq_sim = SequenceMatcher(None, item_normalized, other_normalized).ratio()
            similarity = max(jaccard_sim, seq_sim)
            
            # 유사도 임계값: 0.4 이상이면 유사한 것으로 간주
            if similarity >= 0.4:
                similar_count += 1
                similar_items.append((other, similarity))
    
    # Novelty score: 유사한 기사가 적을수록 높음
    if similar_count == 0:
        novelty_score = 1.0
    elif similar_count <= 2:
        novelty_score = 0.7
    elif similar_count <= 4:
        novelty_score = 0.4
    else:
        novelty_score = 0.1
    
    # Repeat penalty: 같은 이슈가 5개 이상이면 강하게 감점
    if similar_count >= 5:
        repeat_penalty = 0.8
    elif similar_count >= 3:
        repeat_penalty = 0.5
    elif similar_count >= 1:
        repeat_penalty = 0.2
    else:
        repeat_penalty = 0.0
    
    return (novelty_score, repeat_penalty)


def calculate_late_news_penalty(
    item: NewsItem,
    sector: str,
    overnight_signals: Optional[Dict] = None
) -> float:
    """
    늦은 뉴스 페널티 계산 (선행지표 변동 기반)
    
    Args:
        item: 뉴스 아이템
        sector: 섹터명
        overnight_signals: 오버나이트 선행 신호 (선택사항)
    
    Returns:
        늦은 뉴스 페널티 (0.0 ~ 1.0, 높을수록 이미 반영됨)
    """
    if not overnight_signals:
        return 0.0
    
    # 섹터별 선행지표 매핑 (강화)
    sector_indicators = {
        "반도체/AI": ["NVDA", "Nasdaq", "S&P500"],
        "코인/크립토": ["BTC"],
        "거시/금리/달러": ["USDKRW", "US10Y", "DXY"],
        "에너지/원유": ["WTI", "S&P500"],
        "금/귀금속": ["Gold", "DXY"],
        "변동성/리스크": ["VIX", "Nasdaq"],
    }
    
    if sector not in sector_indicators:
        return 0.0
    
    # 해당 섹터의 선행지표들 확인
    indicators = sector_indicators[sector]
    max_change = 0.0
    weighted_change = 0.0
    indicator_count = 0
    
    # 섹터별 가중치 (중요한 지표에 더 높은 가중치)
    indicator_weights = {
        "반도체/AI": {"NVDA": 2.0, "Nasdaq": 1.5, "S&P500": 1.0},
        "코인/크립토": {"BTC": 2.0},
        "거시/금리/달러": {"USDKRW": 2.0, "US10Y": 1.5, "DXY": 1.0},
        "에너지/원유": {"WTI": 2.0, "S&P500": 1.0},
        "금/귀금속": {"Gold": 2.0, "DXY": 1.0},
        "변동성/리스크": {"VIX": 2.0, "Nasdaq": 1.0},
    }
    
    weights = indicator_weights.get(sector, {})
    
    for indicator_name in indicators:
        signal = overnight_signals.get(indicator_name)
        if signal and signal.success and signal.pct_change is not None:
            abs_change = abs(signal.pct_change)
            max_change = max(max_change, abs_change)
            
            # 가중 평균 계산
            weight = weights.get(indicator_name, 1.0)
            weighted_change += abs_change * weight
            indicator_count += weight
    
    # 선행지표가 크게 움직였으면 late penalty 증가
    if max_change > 3.0:  # 3% 이상 변동
        return 0.7
    elif max_change > 2.0:  # 2% 이상 변동
        return 0.5
    elif max_change > 1.0:  # 1% 이상 변동
        return 0.3
    else:
        return 0.0


def calculate_clickbait_penalty(item: NewsItem) -> float:
    """
    클릭베이트 페널티 계산
    
    Args:
        item: 뉴스 아이템
    
    Returns:
        클릭베이트 페널티 (0.0 ~ 1.0, 높을수록 자극적)
    """
    text = (item.title + " " + (item.content or "")).lower()
    
    # 클릭베이트 키워드 체크
    clickbait_count = 0
    for keyword in CLICKBAIT_KEYWORDS:
        if keyword in text:
            clickbait_count += 1
    
    # 신뢰성 높은 출처는 감점 완화
    is_credible = False
    if item.url:
        url_lower = item.url.lower()
        for domain in CREDIBLE_DOMAINS:
            if domain in url_lower:
                is_credible = True
                break
    
    if item.source:
        source_lower = item.source.lower()
        for domain in CREDIBLE_DOMAINS:
            if domain in source_lower:
                is_credible = True
                break
    
    # 페널티 계산
    if clickbait_count == 0:
        penalty = 0.0
    elif clickbait_count == 1:
        penalty = 0.3 if not is_credible else 0.1
    elif clickbait_count == 2:
        penalty = 0.6 if not is_credible else 0.3
    else:
        penalty = 0.9 if not is_credible else 0.5
    
    return penalty


def score_headline(
    item: NewsItem,
    all_items: Optional[List[NewsItem]] = None,
    now_utc: Optional[datetime] = None,
    overnight_signals: Optional[Dict] = None
) -> Tuple[float, Dict[str, float]]:
    """
    헤드라인 종합 점수 계산 (신선도/새로움/늦은뉴스/클릭베이트 반영)
    
    Args:
        item: 뉴스 아이템
        all_items: 전체 뉴스 아이템 리스트 (novelty 계산용, None이면 빈 리스트 사용)
        now_utc: 현재 시각 (UTC, None이면 현재 시각 사용)
    
    Returns:
        (최종 점수, 디버그 정보 딕셔너리) 튜플
    """
    if all_items is None:
        all_items = []
    
    if now_utc is None:
        now_utc = datetime.now(UTC)
    
    text = (item.title + " " + (item.content or "")).lower()
    
    # 1. 기본 관련도 점수 (기존 로직)
    base_relevance = 0.0
    for keyword, weight in MARKET_KEYWORDS.items():
        if keyword in text:
            base_relevance += weight
    
    # 2. Freshness score
    freshness_score = calculate_freshness_score(item, now_utc)
    
    # 3. Novelty / Repeat penalty
    novelty_score, repeat_penalty = calculate_novelty_score(item, all_items, now_utc)
    
    # 4. Late-news penalty
    sector = classify_sector(item.title, item.content or "")
    late_penalty = calculate_late_news_penalty(item, sector, overnight_signals=overnight_signals)
    
    # 5. Clickbait penalty
    clickbait_penalty = calculate_clickbait_penalty(item)
    
    # 6. 최종 점수 계산 (가중치 적용)
    # 가중치 설정 (환경변수로 조정 가능하도록 향후 개선)
    w_fresh = 10.0  # 신선도 가중치
    w_novel = 5.0   # 새로움 가중치
    w_repeat = 8.0  # 반복 페널티 가중치
    w_late = 6.0    # 늦은뉴스 페널티 가중치
    w_click = 4.0   # 클릭베이트 페널티 가중치
    
    final_score = (
        base_relevance
        + w_fresh * freshness_score
        + w_novel * novelty_score
        - w_repeat * repeat_penalty
        - w_late * late_penalty
        - w_click * clickbait_penalty
    )
    
    # 디버그 정보
    debug_info = {
        "base_relevance": base_relevance,
        "freshness_score": freshness_score,
        "novelty_score": novelty_score,
        "repeat_penalty": repeat_penalty,
        "late_penalty": late_penalty,
        "clickbait_penalty": clickbait_penalty,
        "final_score": final_score,
        "sector": sector
    }
    
    return (final_score, debug_info)


def remove_duplicates(news_items: List[NewsItem], 
                     title_threshold: float = 0.85) -> List[NewsItem]:
    """
    중복 뉴스 제거 (제목 유사도만 사용)
    
    Google News 링크의 경우 도메인/슬러그 유사도는 적용하지 않음
    
    Args:
        news_items: 뉴스 아이템 리스트
        title_threshold: 제목 유사도 임계값 (0.85)
    
    Returns:
        중복 제거된 뉴스 리스트
    """
    if not news_items:
        return []
    
    # 정규화된 제목으로 중복 체크
    seen = []
    unique_items = []
    
    for item in news_items:
        normalized = normalize_title(item.title)
        is_duplicate = False
        
        for seen_normalized, seen_item in seen:
            # 제목 유사도만 체크 (Google News 링크는 도메인/슬러그 유사도 제외)
            title_sim = jaccard_similarity(normalized, seen_normalized)
            
            if title_sim >= title_threshold:
                is_duplicate = True
                break
        
        if not is_duplicate:
            seen.append((normalized, item))
            unique_items.append(item)
    
    return unique_items


def classify_sector(title: str, content: str = "") -> str:
    """
    섹터 분류 (키워드 기반, 우선순위 개선)
    
    Returns:
        섹터명 (없으면 "기타")
    """
    text = (title + " " + content).lower()
    
    # 코인/크립토 우선 체크 (거시 섹터보다 우선)
    crypto_keywords = [
        "비트코인", "btc", "이더리움", "eth", "코인", "크립토", "암호화폐",
        "블록체인", "디파이", "defi", "nft", "가상자산", "가상화폐",
        "비트코인 etf", "비트코인 현물 etf"
    ]
    if any(kw in text for kw in crypto_keywords):
        return "코인/크립토"
    
    # 바이오/헬스 우선 체크 (AI보다 우선)
    bio_keywords = [
        "셀트리온", "노보", "glp-1", "fda", "임상", "신약", "제약", "바이오",
        "삼성바이오로직스", "유한양행", "한미약품", "헬스케어", "의료", "바이오텍"
    ]
    if any(kw in text for kw in bio_keywords):
        return "바이오/헬스"
    
    # 반도체/AI 섹터 (명확한 키워드 중심)
    semi_keywords = [
        "nvidia", "엔비디아", "반도체", "dram", "hbm", "파운드리", "tsmc", "amd",
        "삼성전자", "sk하이닉스", "하이닉스", "sk hynix", "메모리", "칩"
    ]
    if any(kw in text for kw in semi_keywords):
        return "반도체/AI"
    
    # 섹터별로 키워드 매칭 (우선순위 순, 코인은 이미 처리됨)
    for sector, keywords in SECTOR_KEYWORDS.items():
        if sector == "코인/크립토":  # 이미 처리됨
            continue
        if any(keyword.lower() in text for keyword in keywords):
            return sector
    
    return "기타"


def generate_macro_summary(news_items: List[NewsItem]) -> str:
    """
    거시 요약 생성 (키워드 기반 템플릿)
    
    Args:
        news_items: 뉴스 아이템 리스트
    
    Returns:
        5줄 이내 요약 텍스트
    """
    if not news_items:
        return "수집된 뉴스가 없습니다."
    
    # 키워드 빈도 계산
    all_text = " ".join([item.title + " " + (item.content or "") for item in news_items])
    all_text_lower = all_text.lower()
    
    # 주요 거시 지표 키워드 체크
    macro_indicators = {
        "S&P": ["s&p", "sp500", "s&p 500", "s&p500"],
        "나스닥": ["나스닥", "nasdaq", "nasdaq 100"],
        "금리": ["금리", "연준", "fed", "기준금리", "인플레이션", "인플레", "cpi"],
        "달러": ["달러", "dxy", "달러인덱스", "원달러", "환율"],
        "유가": ["유가", "원유", "wti", "브렌트", "석유"],
        "비트코인": ["비트코인", "btc", "비트코인 etf", "비트코인 현물 etf"],
    }
    
    found_indicators = []
    for indicator, keywords in macro_indicators.items():
        if any(kw in all_text_lower for kw in keywords):
            found_indicators.append(indicator)
    
    # 키워드 빈도 계산
    keywords = {
        "상승": ["상승", "급등", "반등", "회복", "개선", "증가"],
        "하락": ["하락", "급락", "폭락", "약세", "감소", "축소"],
        "긍정": ["긍정", "호재", "기대", "전망", "낙관", "성장"],
        "부정": ["부정", "악재", "우려", "불안", "비관", "위험"],
    }
    
    keyword_counts = {}
    for category, words in keywords.items():
        count = sum(1 for word in words if word in all_text_lower)
        keyword_counts[category] = count
    
    # 템플릿 기반 요약 생성
    lines = []
    
    # 1. 거시 지표 언급
    if found_indicators:
        indicators_str = ", ".join(found_indicators[:3])
        lines.append(f"• 주요 거시 지표: {indicators_str}")
    
    # 2. 전체 톤
    if keyword_counts.get("긍정", 0) > keyword_counts.get("부정", 0):
        tone = "긍정적"
    elif keyword_counts.get("부정", 0) > keyword_counts.get("긍정", 0):
        tone = "신중"
    else:
        tone = "중립"
    
    lines.append(f"• 전반적 톤: {tone}적 분위기")
    
    # 3. 주요 섹터
    sector_counts = defaultdict(int)
    for item in news_items:
        sector = classify_sector(item.title, item.content or "")
        if sector != "기타":
            sector_counts[sector] += 1
    
    if sector_counts:
        top_sectors = sorted(sector_counts.items(), key=lambda x: x[1], reverse=True)[:3]
        sector_names = ", ".join([s for s, _ in top_sectors])
        lines.append(f"• 주요 섹터: {sector_names}")
    
    # 4. 시장 동향
    if keyword_counts.get("상승", 0) > keyword_counts.get("하락", 0):
        lines.append("• 시장 동향: 상승 기대감 우세")
    elif keyword_counts.get("하락", 0) > keyword_counts.get("상승", 0):
        lines.append("• 시장 동향: 하락 우려 존재")
    else:
        lines.append("• 시장 동향: 혼조세")
    
    return "\n".join(lines[:5])  # 최대 5줄


def assess_korea_impact(news_items: List[NewsItem]) -> tuple[str, str]:
    """
    한국장 영향도 평가
    
    Returns:
        (등급, 이유) 튜플 - 등급: "상" | "중" | "하"
    """
    if not news_items:
        return ("중", "뉴스 부족")
    
    all_text = " ".join([item.title + " " + (item.content or "") for item in news_items])
    all_text_lower = all_text.lower()
    
    # 긍정/부정 키워드
    positive_keywords = ["상승", "급등", "호재", "기대", "개선", "증가", "성장", "반등"]
    negative_keywords = ["하락", "급락", "악재", "우려", "감소", "축소", "위험", "불안"]
    
    positive_count = sum(1 for kw in positive_keywords if kw in all_text_lower)
    negative_count = sum(1 for kw in negative_keywords if kw in all_text_lower)
    
    # 주요 종목 언급 여부
    major_stocks = ["삼성", "sk하이닉스", "네이버", "카카오", "lg", "현대", "기아"]
    stock_mentions = sum(1 for stock in major_stocks if stock in all_text_lower)
    
    # 영향도 계산
    if positive_count > negative_count * 1.5 and stock_mentions >= 2:
        return ("상", "주요 종목 긍정 뉴스 다수")
    elif negative_count > positive_count * 1.5 and stock_mentions >= 2:
        return ("하", "주요 종목 부정 뉴스 존재")
    elif stock_mentions >= 3:
        return ("중", "주요 종목 다수 언급")
    elif positive_count > negative_count:
        return ("중", "전반적 긍정 톤")
    elif negative_count > positive_count:
        return ("중", "전반적 신중 톤")
    else:
        return ("중", "혼조세")


def create_digest(news_items: List[NewsItem], 
                  fetched_count: int = 0,
                  time_filtered_count: int = 0,
                  overnight_signals: Optional[Dict] = None) -> NewsDigest:
    """
    뉴스 다이제스트 생성 (노이즈 필터 + 랭킹 적용)
    
    Args:
        news_items: 뉴스 아이템 리스트 (시간 필터 후)
        fetched_count: 수집된 총 기사 수
        time_filtered_count: 시간 필터 후 기사 수
    
    Returns:
        NewsDigest 객체
    """
    if not news_items:
        return NewsDigest(
            top_headlines=[],
            macro_summary="수집된 뉴스가 없습니다.",
            sector_bullets={},
            korea_impact="중 - 뉴스 부족",
            sources=[],
            fetched_count=fetched_count,
            time_filtered_count=time_filtered_count,
            deduped_count=0,
            headline_debug={}
        )
    
    # 1. 중복 제거
    before_dedup = len(news_items)
    unique_news = remove_duplicates(news_items, title_threshold=0.85)
    after_dedup = len(unique_news)
    
    logger.info(f"중복 제거: {before_dedup}건 → {after_dedup}건")
    
    # 2. 노이즈 필터 적용
    filtered_news = []
    noise_count = 0
    for item in unique_news:
        if is_noise_article(item.title, item.source or "", item.url):
            noise_count += 1
        else:
            filtered_news.append(item)
    
    logger.info(f"노이즈 필터: {len(unique_news)}건 → {len(filtered_news)}건 (제외: {noise_count}건)")
    
    # 노이즈 필터가 너무 많이 제외하면 완화 (후보가 10개 미만이면)
    if len(filtered_news) < 10:
        logger.warning(f"노이즈 필터 후 후보가 {len(filtered_news)}개로 부족, 일부 복구")
        # 노이즈 제외된 항목 중 일부 복구 (점수 높은 것부터)
        noise_items = [item for item in unique_news if is_noise_article(item.title, item.source or "", item.url)]
        # score_headline이 튜플을 반환하므로 첫 번째 요소(점수)로 정렬
        now_utc_temp = datetime.now(UTC)
        noise_items_with_scores = [
            (item, score_headline(item, unique_news, now_utc_temp, overnight_signals=overnight_signals)[0]) 
            for item in noise_items
        ]
        noise_items_with_scores.sort(key=lambda x: x[1], reverse=True)
        # 상위 5개만 복구
        filtered_news.extend([item for item, _ in noise_items_with_scores[:5]])
        logger.info(f"노이즈 항목 {min(5, len(noise_items))}개 복구")
    
    # 3. 시장 관련도 점수 계산 및 정렬 (전체 unique_news를 비교 대상으로 전달)
    now_utc = datetime.now(UTC)
    scored_news = []
    headline_debug = {}
    for item in filtered_news:
        score, debug_info = score_headline(item, unique_news, now_utc, overnight_signals=overnight_signals)
        scored_news.append((item, score))
        headline_debug[item.title] = debug_info
    
    scored_news.sort(key=lambda x: x[1], reverse=True)
    
    # 4. 섹터 다양성 보정 (한 섹터 최대 3개)
    sector_counts = defaultdict(int)
    selected_headlines = []
    selected_items = []
    
    for item, score in scored_news:
        sector = classify_sector(item.title, item.content or "")
        
        # 섹터별 최대 3개 제한
        if sector_counts[sector] >= 3:
            continue
        
        selected_headlines.append(item.title)
        selected_items.append(item)
        sector_counts[sector] += 1
        
        if len(selected_headlines) >= 8:
            break
    
    # 5. 최신순 정렬 (published_at 기준)
    selected_items.sort(key=lambda x: x.published_at, reverse=True)
    top_headlines = [item.title for item in selected_items[:8]]
    
    # 6. 거시 요약 (전체 unique_news 기준)
    macro_summary = generate_macro_summary(unique_news)
    
    # 7. 섹터별 분류 (전체 unique_news 기준)
    sector_bullets: Dict[str, List[str]] = defaultdict(list)
    for item in unique_news:
        sector = classify_sector(item.title, item.content or "")
        if len(sector_bullets[sector]) < 3:  # 섹터당 최대 3개
            sector_bullets[sector].append(item.title)
    
    # "기타" 제외하고 상위 5개 섹터만
    sector_items = [(k, v) for k, v in sector_bullets.items() if k != "기타"]
    sector_items.sort(key=lambda x: len(x[1]), reverse=True)
    sector_bullets = dict(sector_items[:5])
    
    # 8. 한국장 영향도
    impact_level, impact_reason = assess_korea_impact(unique_news)
    korea_impact = f"{impact_level} - {impact_reason}"
    
    # 9. 소스 URL (중복 제거, 최대 5개)
    # selected_items에서 유효한 URL만 추출 (example.com 제외)
    valid_urls = []
    for item in selected_items[:10]:
        url = item.url.strip() if item.url else ""
        # example.com이나 더미 URL 제외
        if url and not url.startswith("https://example.com") and "example.com" not in url:
            valid_urls.append(url)
    
    # 유효한 URL이 부족하면 전체 unique_news에서도 가져오기
    if len(valid_urls) < 5:
        for item in unique_news:
            if len(valid_urls) >= 5:
                break
            url = item.url.strip() if item.url else ""
            if url and url not in valid_urls and not url.startswith("https://example.com") and "example.com" not in url:
                valid_urls.append(url)
    
    sources = valid_urls[:5]
    
    # 디버그 로그
    if sources:
        logger.info(f"근거 링크 {len(sources)}개 추출: {sources[:2]}...")
    else:
        logger.warning("근거 링크가 없습니다 (모든 URL이 example.com이거나 유효하지 않음)")
    
    return NewsDigest(
        top_headlines=top_headlines,
        macro_summary=macro_summary,
        sector_bullets=sector_bullets,
        korea_impact=korea_impact,
        sources=sources,
        fetched_count=fetched_count,
        time_filtered_count=time_filtered_count,
        deduped_count=after_dedup,
        headline_debug=headline_debug
    )
