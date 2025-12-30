"""재무 데이터 수집 모듈"""
from typing import Optional, Dict
from dataclasses import dataclass
import logging

from src.utils.retry import retry_with_backoff, classify_error

logger = logging.getLogger(__name__)


@dataclass
class FinancialMetrics:
    """재무 지표"""
    symbol: str  # 종목코드
    name: str  # 종목명
    per: Optional[float] = None  # PER (Price-to-Earnings Ratio)
    debt_ratio: Optional[float] = None  # 부채비율 (%)
    revenue_growth_3y: Optional[float] = None  # 3년 매출 성장률 (%)
    earnings_growth_3y: Optional[float] = None  # 3년 이익 성장률 (%)
    success: bool = False  # 조회 성공 여부
    error: Optional[str] = None  # 에러 메시지
    error_type: Optional[str] = None  # 에러 타입 (network, data, timeout 등)
    retry_count: int = 0  # 재시도 횟수


@retry_with_backoff(
    max_retries=2,
    base_delay=1.0,
    max_delay=5.0,
    retryable_exceptions=(ConnectionError, TimeoutError, OSError)
)
def fetch_financial_metrics(
    symbol_code: str,
    stock_name: str,
    provider: str = "yahoo"
) -> FinancialMetrics:
    """
    재무 지표 수집 (재시도 로직 포함)
    
    Args:
        symbol_code: 종목코드 (예: "005930")
        stock_name: 종목명 (예: "삼성전자")
        provider: 데이터 제공자 (현재는 "yahoo"만 지원)
    
    Returns:
        FinancialMetrics 객체
    
    Note:
        네트워크 오류 시 exponential backoff로 최대 2회 재시도
    """
    metrics = FinancialMetrics(symbol=symbol_code, name=stock_name)
    
    if provider != "yahoo":
        metrics.error = f"지원하지 않는 provider: {provider}"
        return metrics
    
    try:
        import yfinance as yf
        
        # Yahoo Finance 심볼 변환
        yahoo_symbols = [f"{symbol_code}.KS", f"{symbol_code}.KQ"]
        
        ticker = None
        info = None
        for yahoo_symbol in yahoo_symbols:
            try:
                ticker = yf.Ticker(yahoo_symbol)
                info = ticker.info
                
                # info가 비어있거나 기본값만 있으면 다음 심볼 시도
                if info and len(info) > 10:  # 기본 정보 이상이 있는지 확인
                    logger.debug(f"{stock_name} ({symbol_code}): {yahoo_symbol}에서 재무 데이터 발견 (keys: {len(info)}개)")
                    break
                else:
                    logger.debug(f"{stock_name} ({symbol_code}): {yahoo_symbol} info가 비어있음")
            except Exception as e:
                logger.debug(f"{yahoo_symbol} 재무 데이터 조회 실패: {e}")
                continue
        
        if not ticker:
            metrics.error = "티커 초기화 실패"
            return metrics
        
        info = ticker.info
        
        # PER (Price-to-Earnings Ratio)
        # trailingPE 또는 forwardPE 사용
        if "trailingPE" in info and info["trailingPE"]:
            metrics.per = float(info["trailingPE"])
        elif "forwardPE" in info and info["forwardPE"]:
            metrics.per = float(info["forwardPE"])
        
        # 부채비율 (Debt-to-Equity Ratio)
        # debtToEquity를 부채비율로 사용 (실제로는 부채/자본비율이지만 근사치로 사용)
        if "debtToEquity" in info and info["debtToEquity"]:
            debt_to_equity = float(info["debtToEquity"])
            # debtToEquity를 부채비율(%)로 변환 (부채/자본 * 100)
            metrics.debt_ratio = debt_to_equity * 100
        elif "totalDebt" in info and "totalStockholderEquity" in info:
            total_debt = info.get("totalDebt")
            total_equity = info.get("totalStockholderEquity")
            if total_debt and total_equity and total_equity > 0:
                metrics.debt_ratio = (total_debt / total_equity) * 100
        
        # 3년 성장률
        # revenueGrowth (연간 매출 성장률) 또는 earningsGrowth 사용
        # 3년치 데이터가 없으므로 연간 성장률을 근사치로 사용
        if "revenueGrowth" in info and info["revenueGrowth"]:
            revenue_growth = float(info["revenueGrowth"])
            # 연간 성장률을 3년 성장률로 근사 (단순화)
            # 실제로는 과거 3년 데이터가 필요하지만, 연간 성장률을 사용
            metrics.revenue_growth_3y = revenue_growth * 100  # 퍼센트로 변환
        
        if "earningsGrowth" in info and info["earningsGrowth"]:
            earnings_growth = float(info["earningsGrowth"])
            metrics.earnings_growth_3y = earnings_growth * 100  # 퍼센트로 변환
        
        # 성공 여부 판단 (최소한 하나의 지표라도 있으면 성공)
        if metrics.per is not None or metrics.debt_ratio is not None or metrics.revenue_growth_3y is not None:
            metrics.success = True
            per_str = f"PER={metrics.per:.2f}" if metrics.per else "PER=None"
            debt_str = f"부채비율={metrics.debt_ratio:.1f}%" if metrics.debt_ratio else "부채비율=None"
            growth_str = f"성장률={metrics.revenue_growth_3y:.1f}%" if metrics.revenue_growth_3y else f"성장률={metrics.earnings_growth_3y:.1f}%" if metrics.earnings_growth_3y else "성장률=None"
            logger.info(f"{stock_name} ({symbol_code}): 재무 데이터 수집 성공 - {per_str}, {debt_str}, {growth_str}")
        else:
            metrics.error = "재무 지표 데이터 없음"
            if info:
                available_keys = [k for k in ["trailingPE", "forwardPE", "debtToEquity", "revenueGrowth", "earningsGrowth"] if k in info]
                logger.warning(f"{stock_name} ({symbol_code}): 재무 지표 데이터 없음 (사용 가능한 키: {available_keys}, 전체 키 수: {len(info)})")
            else:
                logger.warning(f"{stock_name} ({symbol_code}): 재무 지표 데이터 없음 (info가 None)")
    
    except Exception as e:
        error_type = classify_error(e)
        metrics.error = str(e)
        metrics.error_type = error_type
        logger.warning(
            f"{stock_name} ({symbol_code}) 재무 데이터 조회 실패: "
            f"[{error_type}] {type(e).__name__}: {e}"
        )
    
    return metrics


def calculate_checklist_scores_from_metrics(
    metrics: FinancialMetrics,
    has_catalyst: bool,
    in_watchlist: bool
) -> Dict[str, int]:
    """
    재무 지표를 기반으로 체크리스트 점수 계산
    
    Args:
        metrics: 재무 지표
        has_catalyst: 뉴스 catalyst가 있는지 여부
        in_watchlist: 관찰 리스트에 있는지 여부
    
    Returns:
        체크리스트 점수 딕셔너리
    """
    scores = {}
    
    # 1) 내가 아는 회사인가?
    if in_watchlist:
        scores["known_company"] = 2
    else:
        scores["known_company"] = 1
    
    # 2) 비즈니스 설명 가능? (항상 1점 이상, 재무 데이터가 있으면 2점)
    if metrics.success:
        scores["business_explainable"] = 2
    else:
        scores["business_explainable"] = 1
    
        # 3) 3년간 실적 성장?
        if metrics.revenue_growth_3y is not None:
            if metrics.revenue_growth_3y > 10:  # 10% 이상 성장
                scores["growth_3y"] = 2
            elif metrics.revenue_growth_3y > 0:
                scores["growth_3y"] = 1
            else:
                scores["growth_3y"] = 0
            logger.debug(f"{metrics.name}: 매출성장률={metrics.revenue_growth_3y:.1f}% -> 점수={scores['growth_3y']}")
        elif metrics.earnings_growth_3y is not None:
            if metrics.earnings_growth_3y > 10:
                scores["growth_3y"] = 2
            elif metrics.earnings_growth_3y > 0:
                scores["growth_3y"] = 1
            else:
                scores["growth_3y"] = 0
            logger.debug(f"{metrics.name}: 이익성장률={metrics.earnings_growth_3y:.1f}% -> 점수={scores['growth_3y']}")
        else:
            scores["growth_3y"] = 1  # 데이터 없으면 기본 1점
    
        # 4) PER 10~20?
        if metrics.per is not None:
            if 10 <= metrics.per <= 20:
                scores["per_10_20"] = 2
            elif 5 <= metrics.per < 10 or 20 < metrics.per <= 30:
                scores["per_10_20"] = 1
            else:
                scores["per_10_20"] = 0
            logger.debug(f"{metrics.name}: PER={metrics.per:.2f} -> 점수={scores['per_10_20']}")
        else:
            scores["per_10_20"] = 1  # 데이터 없으면 기본 1점
    
        # 5) 부채비율 100% 이하?
        if metrics.debt_ratio is not None:
            if metrics.debt_ratio <= 100:
                scores["debt_lt_100"] = 2
            elif metrics.debt_ratio <= 150:
                scores["debt_lt_100"] = 1
            else:
                scores["debt_lt_100"] = 0
            logger.debug(f"{metrics.name}: 부채비율={metrics.debt_ratio:.1f}% -> 점수={scores['debt_lt_100']}")
        else:
            scores["debt_lt_100"] = 1  # 데이터 없으면 기본 1점
    
    # 6) 살 이유가 명확한가?
    if has_catalyst:
        scores["clear_reason"] = 2
    else:
        scores["clear_reason"] = 1
    
    return scores

