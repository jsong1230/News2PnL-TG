"""시세 제공자 구현"""
from datetime import datetime, date, timedelta
from typing import Optional, Tuple
import random
import logging

from src.market.base import MarketProvider, OHLC

logger = logging.getLogger(__name__)


class DummyMarketProvider(MarketProvider):
    """더미 시세 제공자 (테스트용)"""
    
    def get_price(self, symbol: str, date: Optional[datetime] = None) -> float:
        """더미 종가 반환"""
        # 심볼 기반 시드로 일관된 가격 생성
        base_price = hash(symbol) % 100000 + 50000  # 50,000 ~ 150,000원
        # 날짜별로 약간의 변동 추가
        if date:
            variation = (hash(f"{symbol}{date.date()}") % 1000 - 500) / 100
        else:
            variation = random.uniform(-5, 5)
        return round(base_price + variation, 2)
    
    def get_ohlc(self, symbol: str, date: Optional[datetime] = None) -> OHLC:
        """더미 OHLC 반환"""
        close = self.get_price(symbol, date)
        # 일일 변동폭 ±3%
        change_pct = random.uniform(-3, 3)
        change_rate = round(change_pct, 2)
        
        high = round(close * (1 + abs(change_pct) * 0.5), 2)
        low = round(close * (1 - abs(change_pct) * 0.5), 2)
        open_price = round(close * (1 + change_pct * 0.3), 2)
        volume = random.randint(1000000, 10000000)
        
        return OHLC(
            open=open_price,
            high=high,
            low=low,
            close=close,
            volume=volume,
            change_rate=change_rate
        )


def validate_ohlc(ohlc: OHLC, symbol: str) -> Tuple[bool, str]:
    """
    OHLC 데이터 sanity check
    
    Args:
        ohlc: OHLC 데이터
        symbol: 종목코드 (로그용)
    
    Returns:
        (유효 여부, 오류 메시지) 튜플
    """
    # 1. None 체크
    if ohlc.open is None or ohlc.high is None or ohlc.low is None or ohlc.close is None:
        return (False, "OHLC 값 중 None 존재")
    
    # 2. 0 체크
    if ohlc.open == 0 or ohlc.high == 0 or ohlc.low == 0 or ohlc.close == 0:
        return (False, "OHLC 값 중 0 존재")
    
    # 3. 고가 < 저가 체크
    if ohlc.high < ohlc.low:
        return (False, f"고가({ohlc.high}) < 저가({ohlc.low})")
    
    # 4. 시가 범위 체크 (고가 >= 시가 >= 저가)
    if not (ohlc.low <= ohlc.open <= ohlc.high):
        return (False, f"시가({ohlc.open})가 고가/저가 범위 밖")
    
    # 5. 종가 범위 체크 (고가 >= 종가 >= 저가)
    if not (ohlc.low <= ohlc.close <= ohlc.high):
        return (False, f"종가({ohlc.close})가 고가/저가 범위 밖")
    
    # 6. 종가가 시가 대비 ±50% 초과 체크
    if ohlc.open > 0:
        change_pct = abs((ohlc.close - ohlc.open) / ohlc.open) * 100
        if change_pct > 50:
            return (False, f"종가가 시가 대비 {change_pct:.2f}% 변동 (50% 초과)")
    
    return (True, "")


class YahooMarketProvider(MarketProvider):
    """Yahoo Finance 시세 제공자"""
    
    def __init__(self):
        try:
            import yfinance as yf
            self.yf = yf
        except ImportError:
            raise ImportError("yfinance가 설치되지 않았습니다. pip install yfinance로 설치하세요.")
    
    def _convert_symbol(self, symbol_code: str) -> list:
        """
        한국 종목코드를 Yahoo Finance 심볼로 변환 (시도 순서)
        
        Args:
            symbol_code: 종목코드 (예: "005930")
        
        Returns:
            시도할 Yahoo Finance 심볼 리스트 (예: ["005930.KS", "005930.KQ"])
        """
        # .KS (KOSPI) 우선, 실패 시 .KQ (KOSDAQ) 시도
        return [f"{symbol_code}.KS", f"{symbol_code}.KQ"]
    
    def _fetch_ohlc_for_date(
        self, 
        yahoo_symbol: str, 
        target_date: date,
        window_days: int = 3
    ) -> Optional[OHLC]:
        """
        특정 날짜의 OHLC 조회
        
        Args:
            yahoo_symbol: Yahoo Finance 심볼
            target_date: 목표 날짜
            window_days: 전후 조회 일수
        
        Returns:
            OHLC 데이터 또는 None
        """
        try:
            # 전후 window_days일 범위로 데이터 조회
            start_date = target_date - timedelta(days=window_days)
            end_date = target_date + timedelta(days=1)  # 다음날까지
            
            hist = self.yf.download(
                yahoo_symbol,
                start=start_date.strftime("%Y-%m-%d"),
                end=end_date.strftime("%Y-%m-%d"),
                progress=False
            )
            
            if hist.empty:
                logger.debug(f"{yahoo_symbol} 데이터 없음 (empty)")
                return None
            
            # MultiIndex columns 처리 (yfinance.download는 MultiIndex 반환)
            # columns 형태: ('Close', '005930.KS'), ('High', '005930.KS'), ...
            if hasattr(hist.columns, 'levels') and len(hist.columns.levels) > 1:
                # 첫 번째 레벨(Price)로 접근하여 단일 레벨로 변환
                # 또는 직접 컬럼명으로 접근
                hist_flat = {}
                for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
                    if (col, hist.columns.levels[1][0]) in hist.columns:
                        hist_flat[col] = hist[(col, hist.columns.levels[1][0])]
                    elif col in hist.columns:
                        hist_flat[col] = hist[col]
                
                if not hist_flat:
                    logger.debug(f"{yahoo_symbol} 컬럼 추출 실패")
                    return None
                
                # DataFrame 재구성
                import pandas as pd
                hist = pd.DataFrame(hist_flat)
            
            # 날짜 인덱스를 date 객체로 변환
            date_index = []
            for idx in hist.index:
                if hasattr(idx, 'date'):
                    date_index.append(idx.date())
                elif hasattr(idx, 'to_pydatetime'):
                    date_index.append(idx.to_pydatetime().date())
                else:
                    # 이미 date인 경우
                    date_index.append(idx)
            
            # 목표 날짜와 가장 가까운 날짜 찾기
            available_dates = [d for d in date_index if d <= target_date]
            if not available_dates:
                logger.debug(f"{yahoo_symbol} 목표 날짜({target_date}) 이전 데이터 없음")
                return None
            
            closest_date = max(available_dates)
            closest_idx = date_index.index(closest_date)
            
            row_data = hist.iloc[closest_idx]
            
            # 등락률 계산 (전일 종가 기준)
            change_rate = None
            if closest_idx > 0:
                prev_close = hist.iloc[closest_idx - 1]["Close"]
                if prev_close and prev_close > 0:
                    change_rate = ((row_data["Close"] - prev_close) / prev_close) * 100
            
            return OHLC(
                open=float(row_data["Open"]),
                high=float(row_data["High"]),
                low=float(row_data["Low"]),
                close=float(row_data["Close"]),
                volume=int(row_data["Volume"]) if row_data["Volume"] and not row_data["Volume"] is None else None,
                change_rate=round(change_rate, 2) if change_rate is not None else None
            )
        
        except Exception as e:
            logger.debug(f"Yahoo Finance 조회 실패 ({yahoo_symbol}): {e}", exc_info=True)
            return None
    
    def get_price(self, symbol: str, date: Optional[datetime] = None) -> float:
        """종가 조회"""
        ohlc = self.get_ohlc(symbol, date)
        return ohlc.close
    
    def get_ohlc(self, symbol: str, date: Optional[datetime] = None) -> OHLC:
        """
        OHLC 조회
        
        Args:
            symbol: 종목코드
            date: 날짜 (None이면 오늘)
        
        Returns:
            OHLC 데이터
        
        Raises:
            ValueError: 시세 조회 실패 또는 데이터 오류
        """
        # 날짜 지정
        if date:
            target_date = date.date() if isinstance(date, datetime) else date
        else:
            from datetime import date as date_class
            target_date = date_class.today()
        
        # 시도할 심볼 리스트
        yahoo_symbols = self._convert_symbol(symbol)
        
        for yahoo_symbol in yahoo_symbols:
            print(f"시세 조회 시도: {symbol} -> {yahoo_symbol} (날짜: {target_date})")
            logger.info(f"시세 조회 시도: {symbol} -> {yahoo_symbol} (날짜: {target_date})")
            
            ohlc = self._fetch_ohlc_for_date(yahoo_symbol, target_date)
            
            if ohlc is None:
                print(f"  {yahoo_symbol} 조회 실패, 다음 심볼 시도")
                logger.debug(f"{yahoo_symbol} 조회 실패, 다음 심볼 시도")
                continue
            
            # Sanity check
            is_valid, error_msg = validate_ohlc(ohlc, symbol)
            
            if not is_valid:
                print(f"  {yahoo_symbol} 데이터 오류: {error_msg}")
                logger.warning(f"{yahoo_symbol} 데이터 오류: {error_msg}")
                continue
            
            # 성공
            print(f"  시세 조회 성공: {symbol} -> {yahoo_symbol}, OHLC: O={ohlc.open:.0f}, H={ohlc.high:.0f}, L={ohlc.low:.0f}, C={ohlc.close:.0f}")
            logger.info(f"시세 조회 성공: {symbol} -> {yahoo_symbol}, OHLC: O={ohlc.open:.0f}, H={ohlc.high:.0f}, L={ohlc.low:.0f}, C={ohlc.close:.0f}")
            return ohlc
        
        # 모든 심볼 시도 실패
        raise ValueError(f"시세 조회 실패: {symbol} (시도한 심볼: {', '.join(yahoo_symbols)})")


def get_market_provider(provider_name: str = "dummy") -> MarketProvider:
    """
    시세 제공자 팩토리
    
    Args:
        provider_name: 제공자 이름 ("dummy" | "yahoo")
    
    Returns:
        MarketProvider 인스턴스
    """
    if provider_name == "dummy":
        return DummyMarketProvider()
    elif provider_name == "yahoo":
        return YahooMarketProvider()
    else:
        raise ValueError(f"지원하지 않는 시세 제공자: {provider_name}")
