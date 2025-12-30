import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime
from src.market.provider import KISMarketProvider, YahooMarketProvider, HybridMarketProvider, OHLC

@pytest.fixture
def mock_kis_response():
    return {
        "rt_cd": "0",
        "msg1": "성공",
        "output2": [
            {
                "stck_bsop_date": "20251230",
                "stck_oprc": "50000",
                "stck_hgpr": "51000",
                "stck_lwpr": "49000",
                "stck_clpr": "50500",
                "acml_vol": "1000000",
                "prdy_ctrt": "1.0"
            }
        ]
    }

@patch("requests.get")
@patch("src.market.kis_auth.get_access_token")
def test_kis_provider_fetch_ohlc(mock_token, mock_get, mock_kis_response):
    mock_token.return_value = "fake_token"
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = mock_kis_response
    
    provider = KISMarketProvider()
    ohlc = provider.get_ohlc("005930", date=datetime(2025, 12, 30))
    
    assert ohlc.close == 50500.0
    assert ohlc.open == 50000.0
    assert ohlc.high == 51000.0
    assert ohlc.low == 49000.0
    assert ohlc.volume == 1000000
    assert ohlc.change_rate == 1.0

def test_hybrid_provider_fallback():
    # KIS provider가 실패하도록 설정
    kis_mock = MagicMock(spec=KISMarketProvider)
    kis_mock.get_ohlc.side_effect = ValueError("KIS Error")
    
    # Yahoo provider는 성공하도록 설정
    yahoo_mock = MagicMock(spec=YahooMarketProvider)
    expected_ohlc = OHLC(open=100, high=110, low=90, close=105, volume=1000, change_rate=5.0)
    yahoo_mock.get_ohlc.return_value = expected_ohlc
    
    hybrid = HybridMarketProvider([kis_mock, yahoo_mock])
    ohlc = hybrid.get_ohlc("005930")
    
    assert ohlc == expected_ohlc
    kis_mock.get_ohlc.assert_called_once()
    yahoo_mock.get_ohlc.assert_called_once()

def test_hybrid_provider_success_first():
    kis_mock = MagicMock(spec=KISMarketProvider)
    expected_ohlc = OHLC(open=500, high=510, low=490, close=505, volume=2000, change_rate=1.0)
    kis_mock.get_ohlc.return_value = expected_ohlc
    
    yahoo_mock = MagicMock(spec=YahooMarketProvider)
    
    hybrid = HybridMarketProvider([kis_mock, yahoo_mock])
    ohlc = hybrid.get_ohlc("005930")
    
    assert ohlc == expected_ohlc
    kis_mock.get_ohlc.assert_called_once()
    yahoo_mock.get_ohlc.assert_not_called()
