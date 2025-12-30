"""재무 데이터 수집 모듈"""
from typing import Optional, Dict
from dataclasses import dataclass
import logging
from functools import lru_cache
from datetime import date

from src.utils.retry import retry_with_backoff, classify_error
from src.market.kis_auth import get_kis_base_url, get_kis_headers
from src.database import upsert_symbol, get_financial_metrics, upsert_financial_metrics

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
    재무 지표 수집 (캐싱 및 재시도 로직 포함)
    """
    return _fetch_financial_metrics_cached(symbol_code, stock_name, provider, date.today().isoformat())


@lru_cache(maxsize=128)
def _fetch_financial_metrics_cached(
    symbol_code: str,
    stock_name: str,
    provider: str,
    today_str: str
) -> FinancialMetrics:
    """
    캐시 레이어를 포함한 실제 수집 로직
    """
    metrics = FinancialMetrics(symbol=symbol_code, name=stock_name)
    symbol_id = None
    
    # 1. DB 캐시 확인
    try:
        symbol_id = upsert_symbol(stock_name, symbol_code)
        cached = get_financial_metrics(symbol_id, today_str)
        if cached:
            metrics.per = cached["per"]
            metrics.debt_ratio = cached["debt_ratio"]
            metrics.revenue_growth_3y = cached["revenue_growth_3y"]
            metrics.earnings_growth_3y = cached["earnings_growth_3y"]
            metrics.success = True
            logger.debug(f"DB 캐시 히트: {stock_name} ({symbol_code})")
            return metrics
    except Exception as e:
        logger.warning(f"DB 캐시 조회 실패: {e}")

    # 2. 실제 API 호출 로직
    # KIS API 시도
    if provider == "kis":
        if symbol_code.isdigit() and len(symbol_code) == 6:
            base_url = get_kis_base_url()
            url = f"{base_url}/uapi/domestic-stock/v1/quotations/inquire-price"
            headers = get_kis_headers(tr_id="FHKST01010100")
            params = {"FID_COND_MRKT_DIV": "J", "FID_INPUT_ISCD": symbol_code}
            try:
                import requests
                response = requests.get(url, headers=headers, params=params, timeout=10)
                response.raise_for_status()
                data = response.json()
                if data.get("rt_cd") == "0":
                    output = data.get("output", {})
                    if output.get("per"):
                        try:
                            val = float(output["per"])
                            if val != 0: metrics.per = val
                        except: pass
                else:
                    logger.debug(f"{stock_name} ({symbol_code}): KIS 연동 실패 - {data.get('msg1')}")
            except Exception as e:
                logger.debug(f"{stock_name} ({symbol_code}): KIS 조회 중 예외 - {e}")

    # Yahoo Finance 시도
    try:
        import yfinance as yf
        yahoo_symbols = [f"{symbol_code}.KS", f"{symbol_code}.KQ"]
        ticker = None
        info = None
        for yahoo_symbol in yahoo_symbols:
            try:
                ticker = yf.Ticker(yahoo_symbol)
                info = ticker.info
                if info and len(info) > 10: break
            except Exception as e:
                logger.debug(f"{yahoo_symbol} 재무 데이터 조회 실패: {e}")
                continue
        
        if ticker and info and len(info) > 10:
            if "trailingPE" in info and info["trailingPE"]: metrics.per = float(info["trailingPE"])
            elif "forwardPE" in info and info["forwardPE"]: metrics.per = float(info["forwardPE"])
            
            if "debtToEquity" in info and info["debtToEquity"]:
                metrics.debt_ratio = float(info["debtToEquity"]) * 100
            elif "totalDebt" in info and "totalStockholderEquity" in info:
                total_debt = info.get("totalDebt")
                total_equity = info.get("totalStockholderEquity")
                if total_debt and total_equity and total_equity > 0:
                    metrics.debt_ratio = (total_debt / total_equity) * 100
            
            if "revenueGrowth" in info and info["revenueGrowth"]:
                metrics.revenue_growth_3y = float(info["revenueGrowth"]) * 100
            if "earningsGrowth" in info and info["earningsGrowth"]:
                metrics.earnings_growth_3y = float(info["earningsGrowth"]) * 100
            
            if metrics.per is not None or metrics.debt_ratio is not None or metrics.revenue_growth_3y is not None:
                metrics.success = True
                logger.info(f"{stock_name} ({symbol_code}): 재무 데이터 수집 성공 (API)")
    except Exception as e:
        error_type = classify_error(e)
        metrics.error = str(e)
        metrics.error_type = error_type
        logger.warning(f"{stock_name} ({symbol_code}) 재무 데이터 API 조회 실패: {error_type}")

    # 3. 새로운 결과 DB에 저장
    if metrics.success and symbol_id:
        try:
            upsert_financial_metrics(
                symbol_id=symbol_id,
                date=today_str,
                per=metrics.per,
                debt_ratio=metrics.debt_ratio,
                revenue_growth_3y=metrics.revenue_growth_3y,
                earnings_growth_3y=metrics.earnings_growth_3y
            )
            logger.debug(f"DB 캐시 저장 완료: {stock_name} ({symbol_code})")
        except Exception as e:
            logger.warning(f"DB 캐시 저장 실패: {e}")

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
            elif 5 <= metrics.per < 10 or 20 < metrics.per <= 25:
                scores["per_10_20"] = 1
            else:
                # PER가 너무 높거나(>25) 너무 낮으면(<5) 0점
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
                # 부채비율 150% 초과 시 0점
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

