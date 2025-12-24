"""종목 선정 로직 (뉴스 기반 관찰 리스트 생성)"""
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import logging

from src.news.base import NewsItem
from src.analysis.news_analyzer import NewsDigest
from src.data.kr_symbols import (
    KR_SYMBOLS, 
    find_symbols_in_text, 
    get_foreign_substitute_symbols,
    get_symbol_code
)
from src.config import WATCHLIST_KR

logger = logging.getLogger(__name__)


@dataclass
class WatchStock:
    """관찰 종목 정보"""
    name: str  # 종목명
    code: str  # 종목코드
    thesis: str  # 한 줄 thesis (왜 오늘 관찰?)
    catalysts: List[str]  # 관련 뉴스 제목 1~2개
    risks: List[str]  # 리스크 2개
    trigger: str  # 관찰 트리거
    checklist_scores: Dict[str, int]  # 체크리스트 점수 (총 12점)
    total_score: int  # 총점
    confidence: str  # 확신도: "상" | "중" | "하"
    confidence_reason: str  # 확신도 이유


def extract_stock_candidates(digest: NewsDigest, news_items: List[NewsItem]) -> Dict[str, int]:
    """
    뉴스 다이제스트에서 종목 후보 추출 및 점수 계산
    
    Args:
        digest: 뉴스 다이제스트
        news_items: 뉴스 아이템 리스트
    
    Returns:
        {종목명: 점수} 딕셔너리
    """
    scores: Dict[str, int] = {}
    
    # 전체 텍스트 수집
    all_text = " ".join(digest.top_headlines)
    all_text += " " + " ".join([bullet for bullets in digest.sector_bullets.values() for bullet in bullets])
    
    # 헤드라인에서 종목명 찾기
    for headline in digest.top_headlines:
        found_symbols = find_symbols_in_text(headline)
        for symbol_name, code in found_symbols.items():
            if symbol_name not in scores:
                scores[symbol_name] = 0
            scores[symbol_name] += 3  # 헤드라인 직접 언급: +3
    
    # 섹터 bullets에서 종목명 찾기
    for bullets in digest.sector_bullets.values():
        for bullet in bullets:
            found_symbols = find_symbols_in_text(bullet)
            for symbol_name, code in found_symbols.items():
                if symbol_name not in scores:
                    scores[symbol_name] = 0
                scores[symbol_name] += 2  # 섹터 bullet 언급: +2
    
    # WATCHLIST_KR에 있는 종목 가중치 추가
    for watch_name in WATCHLIST_KR:
        if watch_name in scores:
            scores[watch_name] += 2  # WATCHLIST_KR 포함: +2
        else:
            # WATCHLIST_KR에 있지만 아직 언급되지 않은 경우
            code = get_symbol_code(watch_name)
            if code:
                scores[watch_name] = 2  # 기본 점수 부여
    
    # 해외 종목 → 한국 대체 종목 매핑
    all_text_lower = all_text.lower()
    for foreign_name, kr_substitutes in [
        ("엔비디아", ["삼성전자", "SK하이닉스"]),
        ("nvidia", ["삼성전자", "SK하이닉스"]),
        ("amd", ["삼성전자", "SK하이닉스"]),
        ("테슬라", ["LG에너지솔루션", "삼성SDI"]),
        ("tesla", ["LG에너지솔루션", "삼성SDI"]),
    ]:
        if foreign_name in all_text_lower:
            for kr_name in kr_substitutes:
                if kr_name not in scores:
                    scores[kr_name] = 0
                scores[kr_name] += 1  # 해외 종목 관련: +1
    
    return scores


def calculate_checklist_score(stock_name: str, has_catalyst: bool) -> Tuple[Dict[str, int], int]:
    """
    6단계 체크리스트 점수 계산
    
    Args:
        stock_name: 종목명
        has_catalyst: 뉴스 catalyst가 있는지 여부
    
    Returns:
        (체크리스트 점수 딕셔너리, 총점) 튜플
    """
    scores = {}
    
    # 1) 내가 아는 회사인가?
    if stock_name in WATCHLIST_KR:
        scores["내가 아는 회사"] = 2
    else:
        scores["내가 아는 회사"] = 1
    
    # 2) 비즈니스 설명 가능?
    if stock_name in KR_SYMBOLS:
        scores["비즈니스 설명 가능"] = 2
    else:
        scores["비즈니스 설명 가능"] = 1
    
    # 3) 3년간 실적 성장?
    scores["3년간 실적 성장"] = 1  # 데이터 없으므로 기본 1점
    
    # 4) PER 10~20?
    scores["PER 10~20"] = 1  # 데이터 없으므로 기본 1점
    
    # 5) 부채비율 100% 이하?
    scores["부채비율 100% 이하"] = 1  # 데이터 없으므로 기본 1점
    
    # 6) 살 이유가 명확한가?
    if has_catalyst:
        scores["살 이유 명확"] = 2
    else:
        scores["살 이유 명확"] = 1
    
    total = sum(scores.values())
    return (scores, total)


def assess_confidence(total_score: int, has_catalyst: bool, in_watchlist: bool) -> Tuple[str, str]:
    """
    확신도 평가
    
    Args:
        total_score: 체크리스트 총점
        has_catalyst: 뉴스 catalyst가 있는지
        in_watchlist: WATCHLIST_KR에 있는지
    
    Returns:
        (확신도, 이유) 튜플
    """
    if total_score >= 10 and has_catalyst and in_watchlist:
        return ("상", "체크리스트 점수 높음 + catalyst + 관찰 리스트 포함")
    elif total_score >= 8 and has_catalyst:
        return ("중", "체크리스트 점수 양호 + catalyst 존재")
    elif total_score >= 8:
        return ("중", "체크리스트 점수 양호")
    else:
        return ("하", "체크리스트 점수 낮음 또는 catalyst 부족")


def generate_risks(stock_name: str) -> List[str]:
    """
    기본 리스크 생성 (초기 버전)
    
    Args:
        stock_name: 종목명
    
    Returns:
        리스크 리스트 (2개)
    """
    # 기본 리스크 템플릿
    risks = [
        "시장 변동성 및 리스크 존재",
        "재무데이터 확인 필요 (PER, 부채비율 등)"
    ]
    
    # 종목별 특화 리스크
    if "반도체" in stock_name or stock_name in ["삼성전자", "SK하이닉스"]:
        risks[0] = "반도체 업황 사이클 변동성"
    elif "2차전지" in stock_name or "배터리" in stock_name:
        risks[0] = "전기차 수요 변동성 및 원자재 가격 변동"
    elif "바이오" in stock_name or "제약" in stock_name:
        risks[0] = "신약 개발 및 규제 승인 불확실성"
    
    return risks


def generate_trigger(stock_name: str) -> str:
    """
    관찰 트리거 생성
    
    Args:
        stock_name: 종목명
    
    Returns:
        관찰 트리거 텍스트
    """
    return "갭상승 시 추격 금지, 변동성 확인 후 관찰"


def pick_watch_stocks(digest: NewsDigest, news_items: List[NewsItem], max_count: int = 3) -> List[WatchStock]:
    """
    관찰 종목 선정
    
    Args:
        digest: 뉴스 다이제스트
        news_items: 뉴스 아이템 리스트
        max_count: 최대 선정 개수 (기본 3개)
    
    Returns:
        관찰 종목 리스트
    """
    # 1. 후보 종목 추출 및 점수 계산
    candidate_scores = extract_stock_candidates(digest, news_items)
    
    if not candidate_scores:
        # 후보가 없으면 섹터 대표주 1개 fallback
        logger.warning("종목 후보가 없어 섹터 대표주로 fallback")
        fallback_stocks = ["삼성전자", "SK하이닉스", "LG에너지솔루션"]
        for stock_name in fallback_stocks:
            code = get_symbol_code(stock_name)
            if code:
                candidate_scores[stock_name] = 1
                break
    
    # 2. 점수 상위 종목 선택 (중복 종목코드 제거)
    sorted_candidates = sorted(candidate_scores.items(), key=lambda x: x[1], reverse=True)
    
    # 종목코드 기준으로 중복 제거 (같은 코드면 점수 높은 것만 선택)
    seen_codes = set()
    selected = []
    for stock_name, score in sorted_candidates:
        code = get_symbol_code(stock_name)
        if code and code not in seen_codes:
            selected.append((stock_name, score))
            seen_codes.add(code)
        if len(selected) >= max_count:
            break
    
    watch_stocks = []
    
    for stock_name, score in selected:
        code = get_symbol_code(stock_name)
        if not code:
            logger.warning(f"종목코드를 찾을 수 없음: {stock_name}")
            continue
        
        # 관련 뉴스 찾기
        catalysts = []
        for item in news_items:
            if stock_name in item.title or stock_name.lower() in item.title.lower():
                catalysts.append(item.title)
                if len(catalysts) >= 2:
                    break
        
        # catalyst가 없으면 기본 메시지
        if not catalysts:
            catalysts = [f"{stock_name} 관련 뉴스"]
        
        # thesis 생성
        if catalysts:
            thesis = f"{stock_name} 관련 뉴스로 인한 관찰 필요"
        else:
            thesis = f"{stock_name} 섹터 동향 관찰"
        
        # 체크리스트 점수 계산
        has_catalyst = len(catalysts) > 0
        checklist_scores, total_score = calculate_checklist_score(stock_name, has_catalyst)
        
        # 확신도 평가
        in_watchlist = stock_name in WATCHLIST_KR
        confidence, confidence_reason = assess_confidence(total_score, has_catalyst, in_watchlist)
        
        # 리스크 생성
        risks = generate_risks(stock_name)
        
        # 트리거 생성
        trigger = generate_trigger(stock_name)
        
        watch_stock = WatchStock(
            name=stock_name,
            code=code,
            thesis=thesis,
            catalysts=catalysts,
            risks=risks,
            trigger=trigger,
            checklist_scores=checklist_scores,
            total_score=total_score,
            confidence=confidence,
            confidence_reason=confidence_reason
        )
        
        watch_stocks.append(watch_stock)
    
    return watch_stocks

