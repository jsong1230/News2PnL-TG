import pytest
from datetime import date, timedelta
from unittest.mock import patch, MagicMock
from src.market.financial import fetch_financial_metrics, _fetch_financial_metrics_cached
from src.market.provider import YahooMarketProvider, KISMarketProvider
from src.database import get_db_connection, init_schema

import pytest
import os
import tempfile
from datetime import date, timedelta
from unittest.mock import patch, MagicMock
from src.market.financial import fetch_financial_metrics, _fetch_financial_metrics_cached
from src.market.provider import YahooMarketProvider, KISMarketProvider
from src.database import get_db_connection, init_schema
from src.market.base import OHLC

@pytest.fixture
def temp_db():
    """테스트별로 독립된 임시 DB 사용"""
    fd, path = tempfile.mkstemp()
    os.close(fd)
    
    with patch("src.database.DB_PATH", path), patch("src.config.DB_PATH", path):
        init_schema()
        # lru_cache 초기화
        _fetch_financial_metrics_cached.cache_clear()
        yield path
        
    if os.path.exists(path):
        os.remove(path)

def test_financial_metrics_caching(temp_db):
    """재무 지표 캐싱 동작 테스트"""
    symbol = "005930"
    name = "삼성전자"
    
    with patch("yfinance.Ticker") as mock_ticker:
        mock_info = {
            "trailingPE": 15.0,
            "debtToEquity": 0.5,
            "revenueGrowth": 0.1,
            "trailingEps": 5000,
            "marketCap": 1000000,
            "totalRevenue": 1000000,
            "grossMargins": 0.3,
            "operatingMargins": 0.1,
            "returnOnEquity": 0.2,
            "freeCashflow": 100000,
            "currentRatio": 1.5,
            "quickRatio": 1.2
        }
        mock_ticker.return_value.info = mock_info
        
        # lru_cache 초기화
        _fetch_financial_metrics_cached.cache_clear()
        
        # 1. 첫 번째 호출: API 호출 발생
        metrics1 = fetch_financial_metrics(symbol, name, provider="yahoo")
        assert metrics1.success is True, f"수집 실패: {metrics1.error}"
        assert metrics1.per == 15.0
        assert mock_ticker.called is True
        
        # 2. 두 번째 호출: DB 또는 LRU 캐시 히트
        mock_ticker.reset_mock()
        metrics2 = fetch_financial_metrics(symbol, name, provider="yahoo")
        assert metrics2.success is True
        assert metrics2.per == 15.0
        assert mock_ticker.called is False  # 캐시 히트!

def test_market_provider_db_caching(temp_db):
    """시세 데이터 DB 캐싱 테스트"""
    symbol = "005930"
    past_date = date.today() - timedelta(days=2)
    
    # Provider를 patch 안에서 생성하거나 patch를 instance method에 적용
    provider = YahooMarketProvider()
    
    with patch.object(provider, "_fetch_ohlc_for_date") as mock_fetch:
        mock_ohlc = OHLC(open=100, high=110, low=90, close=105, volume=1000, change_rate=5.0)
        mock_fetch.return_value = mock_ohlc
        
        # 1. 첫 호출: API 호출
        ohlc1 = provider.get_ohlc(symbol, past_date)
        assert ohlc1.close == 105
        assert mock_fetch.call_count == 1
        
        # 2. 두 번째 호출: DB 캐시 히트
        mock_fetch.reset_mock()
        ohlc2 = provider.get_ohlc(symbol, past_date)
        assert ohlc2.close == 105
        assert mock_fetch.call_count == 0, "DB 캐시 히트 실패: API가 다시 호출됨"

def test_kis_provider_db_caching(temp_db):
    """KIS 시세 데이터 DB 캐싱 테스트"""
    symbol = "005930"
    past_date = date.today() - timedelta(days=2)
    provider = KISMarketProvider()
    
    with patch("requests.get") as mock_get:
        # Mock KIS API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "rt_cd": "0",
            "output2": [{
                "stck_bsop_date": past_date.strftime("%Y%m%d"),
                "stck_oprc": "100",
                "stck_hgpr": "110",
                "stck_lwpr": "90",
                "stck_clpr": "105",
                "acml_vol": "1000",
                "prdy_ctrt": "5.0"
            }]
        }
        mock_get.return_value = mock_response
        
        # 1. 첫 호출: API 호출
        ohlc1 = provider.get_ohlc(symbol, past_date)
        assert ohlc1.close == 105
        assert mock_get.call_count == 1
        
        # 2. 두 번째 호출: DB 캐시 히트
        mock_get.reset_mock()
        ohlc2 = provider.get_ohlc(symbol, past_date)
        assert ohlc2.close == 105
        assert mock_get.call_count == 0, "KIS DB 캐시 히트 실패"
