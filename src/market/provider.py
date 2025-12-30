"""시세 제공자 구현"""
from datetime import datetime, date, timedelta
from typing import Optional, Tuple
import random
import logging

from src.market.base import MarketProvider, OHLC
from src.utils.retry import retry_with_backoff, classify_error
from src.market.kis_auth import get_kis_base_url, get_kis_headers

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
    
    @retry_with_backoff(
        max_retries=3,
        base_delay=1.0,
        max_delay=10.0,
        retryable_exceptions=(ConnectionError, TimeoutError, OSError)
    )
    def _fetch_ohlc_for_date(
        self, 
        yahoo_symbol: str, 
        target_date: date,
        window_days: int = 3
    ) -> Optional[OHLC]:
        """
        특정 날짜의 OHLC 조회 (재시도 로직 포함)
        
        Args:
            yahoo_symbol: Yahoo Finance 심볼
            target_date: 목표 날짜
            window_days: 전후 조회 일수
        
        Returns:
            OHLC 데이터 또는 None
        
        Note:
            네트워크 오류 시 exponential backoff로 최대 3회 재시도
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
            
            # 실시간성 경고 (요청한 날짜보다 오래된 데이터인 경우)
            if closest_date < target_date:
                logger.warning(
                    f"{yahoo_symbol}: 시세 지연 가능성 - "
                    f"요청일({target_date}) 대비 최신 데이터({closest_date})가 과거 데이터임"
                )
            
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
            error_type = classify_error(e)
            logger.warning(
                f"Yahoo Finance 조회 실패 ({yahoo_symbol}): "
                f"[{error_type}] {type(e).__name__}: {e}"
            )
            # 재시도 가능한 에러는 데코레이터가 처리하므로 여기서는 None 반환
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


class KISMarketProvider(MarketProvider):
    """한국투자증권(KIS) 시세 제공자"""
    
    def __init__(self):
        import requests
        self.requests = requests
        self.base_url = get_kis_base_url()
        
    def get_price(self, symbol: str, date: Optional[datetime] = None) -> float:
        """현재가(또는 특정일 종가) 조회"""
        ohlc = self.get_ohlc(symbol, date)
        return ohlc.close
        
    def get_ohlc(self, symbol: str, date: Optional[datetime] = None) -> OHLC:
        """OHLC 및 당일 데이터 조회"""
        # Domestic Stock 전용 (6자리 숫자)
        if not symbol.isdigit() or len(symbol) != 6:
            logger.warning(f"KISMarketProvider는 6자리 국내 종목코드만 지원합니다: {symbol}")
            raise ValueError(f"지원하지 않는 종목코드 형식: {symbol}")
            
        # 1. 특정 날짜 조회 (Daily Chart API 사용)
        # Morning Report는 보통 '오늘 오전'에 '어제 종가' 혹은 '현재가'를 필요로 함
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
        headers = get_kis_headers(tr_id="FHKST03010100")
        
        # 날짜 포맷 (YYYYMMDD)
        if date:
            target_date_str = date.strftime("%Y%m%d")
        else:
            target_date_str = datetime.now().strftime("%Y%m%d")
            
        params = {
            "FID_COND_MRKT_DIV": "J",
            "FID_INPUT_ISCD": symbol,
            "FID_PERIOD_DIV": "D",
            "FID_ORG_ADJ_PRC": "0"
        }
        
        try:
            logger.info(f"KIS 시세 조회 시도: {symbol} (날짜: {target_date_str})")
            response = self.requests.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get("rt_cd") != "0":
                logger.error(f"KIS API 오류: {data.get('msg1')}")
                raise ValueError(f"KIS API 오류: {data.get('msg1')}")
                
            output2 = data.get("output2", [])
            if not output2:
                raise ValueError(f"KIS 데이터 없음: {symbol}")
                
            # 가장 최신 데이터 (첫 번째 항목)
            row = output2[0]
            
            # target_date가 지정된 경우 해당 날짜 찾기 (없으면 최신 데이터가 target_date보다 과거인지 확인)
            if date:
                # KIS output2는 역순(최신순) 정렬됨
                found_row = None
                for r in output2:
                    if r["stck_bsop_date"] <= target_date_str:
                        found_row = r
                        break
                if not found_row:
                    raise ValueError(f"KIS {target_date_str} 이전 데이터 없음")
                row = found_row
                
            ohlc = OHLC(
                open=float(row["stck_oprc"]),
                high=float(row["stck_hgpr"]),
                low=float(row["stck_lwpr"]),
                close=float(row["stck_clpr"]),
                volume=int(row["acml_vol"]) if row.get("acml_vol") else 0,
                change_rate=float(row["prdy_ctrt"]) if row.get("prdy_ctrt") else None
            )
            
            # Sanity check
            is_valid, error_msg = validate_ohlc(ohlc, symbol)
            if not is_valid:
                logger.warning(f"KIS 데이터 오류 ({symbol}): {error_msg}")
                # KIS 데이터가 오판일 수 있으므로 그대로 반환하되 로그 남김
                
            return ohlc
            
        except Exception as e:
            logger.error(f"KIS 시세 조회 실패 ({symbol}): {e}")
            raise


class HybridMarketProvider(MarketProvider):
    """여러 제공자를 순차적으로 시도하는 하이브리드 제공자"""
    
    def __init__(self, providers: list):
        self.providers = providers
        
    def get_price(self, symbol: str, date: Optional[datetime] = None) -> float:
        """순차적으로 시도하여 첫 번째 성공한 종가 반환"""
        last_error = None
        for provider in self.providers:
            try:
                return provider.get_price(symbol, date)
            except Exception as e:
                logger.debug(f"{type(provider).__name__} get_price 실패: {e}")
                last_error = e
                continue
        raise last_error or ValueError(f"모든 제공자 시세 조회 실패: {symbol}")
        
    def get_ohlc(self, symbol: str, date: Optional[datetime] = None) -> OHLC:
        """순차적으로 시도하여 첫 번째 성공한 OHLC 반환"""
        last_error = None
        for provider in self.providers:
            try:
                return provider.get_ohlc(symbol, date)
            except Exception as e:
                logger.debug(f"{type(provider).__name__} get_ohlc 실패: {e}")
                last_error = e
                continue
        raise last_error or ValueError(f"모든 제공자 OHLC 조회 실패: {symbol}")


def get_market_provider(provider_name: str = "dummy") -> MarketProvider:
    """
    시세 제공자 팩토리
    
    Args:
        provider_name: 제공자 이름 ("dummy" | "yahoo" | "kis" | "kis,yahoo" 등)
    """
    from src.config import MARKET_PROVIDER as DEFAULT_PROVIDER
    
    name = provider_name or DEFAULT_PROVIDER
    
    # 쉼표로 구분된 경우 HybridMarketProvider 생성
    if "," in name:
        names = [n.strip() for n in name.split(",") if n.strip()]
        providers = []
        for n in names:
            try:
                providers.append(get_market_provider(n))
            except ValueError:
                logger.warning(f"지원하지 않는 시세 제공자 무시: {n}")
        if not providers:
            return DummyMarketProvider()
        return HybridMarketProvider(providers)
    
    if name == "dummy":
        return DummyMarketProvider()
    elif name == "yahoo":
        return YahooMarketProvider()
    elif name == "kis":
        return KISMarketProvider()
    else:
        raise ValueError(f"지원하지 않는 시세 제공자: {name}")
