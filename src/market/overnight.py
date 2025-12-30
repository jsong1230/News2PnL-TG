"""오버나이트 선행 신호 수집 모듈"""
from typing import Dict, Optional, List
from dataclasses import dataclass
from datetime import date, datetime, timedelta
import logging
import json

from src.market.provider import YahooMarketProvider
from src.market.base import OHLC

logger = logging.getLogger(__name__)


@dataclass
class OvernightSignal:
    """오버나이트 선행 신호"""
    name: str  # 신호 이름 (예: "Nasdaq", "NVDA")
    ticker: str  # Yahoo Finance 티커
    prev_close: Optional[float] = None  # 전일 종가
    last: Optional[float] = None  # 최신 가격 (또는 종가)
    pct_change: Optional[float] = None  # 변동률 (%)
    success: bool = False  # 조회 성공 여부
    error: Optional[str] = None  # 에러 메시지


# 기본 티커 매핑
DEFAULT_TICKERS = {
    "S&P500": "^GSPC",
    "Nasdaq": "^IXIC",
    "US10Y": "^TNX",
    "BTC": "BTC-USD",
    "NVDA": "NVDA",
    "DXY": "DX-Y.NYB",
    "EWY": "EWY",
    "USDKRW": "KRW=X",
    "VIX": "^VIX",  # 변동성 지수
    "WTI": "CL=F",  # 원유 (WTI)
    "Gold": "GC=F",  # 금
}


def fetch_overnight_signals(
    target_date: Optional[date] = None,
    provider: str = "yahoo",
    tickers: Optional[Dict[str, str]] = None,
    debug: bool = False
) -> Dict[str, OvernightSignal]:
    """
    오버나이트 선행 신호 수집
    
    Args:
        target_date: 목표 날짜 (None이면 오늘)
        provider: 시세 제공자 (현재는 "yahoo"만 지원)
        tickers: 티커 매핑 (None이면 기본값 사용)
        debug: 디버그 모드
    
    Returns:
        {신호명: OvernightSignal} 딕셔너리
    """
    if target_date is None:
        target_date = date.today()
    
    if tickers is None:
        tickers = DEFAULT_TICKERS.copy()
    
    signals: Dict[str, OvernightSignal] = {}
    
    if provider != "yahoo":
        logger.warning(f"지원하지 않는 provider: {provider}, yahoo만 지원")
        return signals
    
    try:
        market_provider = YahooMarketProvider()
    except Exception as e:
        logger.error(f"YahooMarketProvider 초기화 실패: {e}")
        return signals
    
    # 각 티커별로 신호 수집
    for signal_name, ticker in tickers.items():
        signal = OvernightSignal(name=signal_name, ticker=ticker)
        
        try:
            # 전일 날짜 계산 (주말/공휴일 고려)
            prev_date = target_date - timedelta(days=1)
            # 최대 5일 전까지 거슬러 올라가며 데이터 찾기
            for days_back in range(5):
                check_date = prev_date - timedelta(days=days_back)
                try:
                    ohlc = market_provider.get_ohlc(ticker, datetime.combine(check_date, datetime.min.time()))
                    if ohlc:
                        signal.prev_close = ohlc.close
                        signal.last = ohlc.close
                        signal.success = True
                        
                        # 전전일 종가와 비교하여 변동률 계산
                        if days_back == 0 and ohlc.change_rate is not None:
                            signal.pct_change = ohlc.change_rate
                        else:
                            # 전전일 데이터 조회 시도
                            prev_prev_date = check_date - timedelta(days=1)
                            for prev_days_back in range(3):
                                prev_check_date = prev_prev_date - timedelta(days=prev_days_back)
                                try:
                                    prev_ohlc = market_provider.get_ohlc(
                                        ticker, 
                                        datetime.combine(prev_check_date, datetime.min.time())
                                    )
                                    if prev_ohlc and prev_ohlc.close and prev_ohlc.close > 0:
                                        signal.pct_change = ((ohlc.close - prev_ohlc.close) / prev_ohlc.close) * 100
                                        break
                                except:
                                    continue
                        
                        if debug:
                            logger.info(f"{signal_name} ({ticker}): prev_close={signal.prev_close:.2f}, "
                                      f"last={signal.last:.2f}, pct_change={signal.pct_change:.2f}%")
                        break
                except Exception as e:
                    if days_back == 4:  # 마지막 시도
                        signal.error = str(e)
                        if debug:
                            logger.debug(f"{signal_name} ({ticker}) 조회 실패: {e}")
                    continue
            
            if not signal.success:
                signal.error = "데이터 없음"
                if debug:
                    logger.warning(f"{signal_name} ({ticker}): 데이터 조회 실패")
        
        except Exception as e:
            signal.error = str(e)
            logger.warning(f"{signal_name} ({ticker}) 처리 중 오류: {e}")
        
        signals[signal_name] = signal
    
    return signals


def assess_market_tone(signals: Dict[str, OvernightSignal]) -> str:
    """
    시장 톤 평가 (risk_on / risk_off / mixed)
    VIX, 원유, 금 등 추가 지표를 고려하여 개선
    
    Args:
        signals: 오버나이트 신호 딕셔너리
    
    Returns:
        "risk_on" | "risk_off" | "mixed"
    """
    nasdaq = signals.get("Nasdaq")
    sp500 = signals.get("S&P500")
    usdkrw = signals.get("USDKRW")
    vix = signals.get("VIX")
    wti = signals.get("WTI")
    gold = signals.get("Gold")
    
    # Nasdaq/S&P 상승 여부
    nasdaq_up = nasdaq and nasdaq.success and nasdaq.pct_change and nasdaq.pct_change > 0
    sp500_up = sp500 and sp500.success and sp500.pct_change and sp500.pct_change > 0
    us_market_up = nasdaq_up or sp500_up
    
    # USDKRW 하락 여부 (원화 강세)
    krw_strong = usdkrw and usdkrw.success and usdkrw.pct_change and usdkrw.pct_change < 0
    
    # VIX 하락 여부 (변동성 감소 = 리스크 온)
    vix_down = vix and vix.success and vix.pct_change and vix.pct_change < 0
    
    # 원유 상승 여부 (경기 회복 신호)
    wti_up = wti and wti.success and wti.pct_change and wti.pct_change > 0
    
    # 금 하락 여부 (리스크 온일 때 금은 하락)
    gold_down = gold and gold.success and gold.pct_change and gold.pct_change < 0
    
    # 종합 판단 (가중치 적용)
    risk_on_signals = 0
    risk_off_signals = 0
    
    if us_market_up:
        risk_on_signals += 2  # 미국 증시 상승은 강한 신호
    else:
        risk_off_signals += 2
    
    if krw_strong:
        risk_on_signals += 1  # 원화 강세
    else:
        risk_off_signals += 1
    
    if vix_down:
        risk_on_signals += 1  # 변동성 감소
    elif vix and vix.success and vix.pct_change and vix.pct_change > 5:
        risk_off_signals += 2  # VIX 급등은 강한 리스크 오프 신호
    
    if wti_up:
        risk_on_signals += 1  # 원유 상승 (경기 회복)
    elif wti and wti.success and wti.pct_change and wti.pct_change < -2:
        risk_off_signals += 1  # 원유 급락
    
    if gold_down:
        risk_on_signals += 0.5  # 금 하락 (약한 신호)
    elif gold and gold.success and gold.pct_change and gold.pct_change > 2:
        risk_off_signals += 1  # 금 상승 (안전자산 선호)
    
    # 판단 로직
    if risk_on_signals > risk_off_signals + 1:
        return "risk_on"
    elif risk_off_signals > risk_on_signals + 1:
        return "risk_off"
    else:
        return "mixed"



