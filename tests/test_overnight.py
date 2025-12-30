"""오버나이트 신호 수집 테스트"""
import sys
from pathlib import Path
from datetime import date, datetime
from unittest.mock import Mock, patch
import pytest

# 프로젝트 루트를 경로에 추가
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.market.overnight import (
    OvernightSignal,
    fetch_overnight_signals,
    assess_market_tone,
    DEFAULT_TICKERS,
)
from src.market.base import OHLC


class TestOvernightSignal:
    """OvernightSignal 데이터 클래스 테스트"""
    
    def test_signal_creation(self):
        """신호 생성"""
        signal = OvernightSignal(
            name="Nasdaq",
            ticker="^IXIC",
            prev_close=15000.0,
            last=15150.0,
            pct_change=1.0,
            success=True
        )
        
        assert signal.name == "Nasdaq"
        assert signal.ticker == "^IXIC"
        assert signal.prev_close == 15000.0
        assert signal.last == 15150.0
        assert signal.pct_change == 1.0
        assert signal.success is True
    
    def test_failed_signal(self):
        """실패한 신호"""
        signal = OvernightSignal(
            name="Test",
            ticker="TEST",
            success=False,
            error="데이터 없음"
        )
        
        assert signal.success is False
        assert signal.error == "데이터 없음"


class TestFetchOvernightSignals:
    """오버나이트 신호 수집 테스트"""
    
    @patch('src.market.overnight.YahooMarketProvider')
    def test_successful_fetch(self, mock_provider_class):
        """성공적인 신호 수집"""
        # Mock OHLC 데이터
        mock_ohlc = OHLC(
            open=15000.0,
            high=15200.0,
            low=14900.0,
            close=15150.0,
            volume=1000000,
            change_rate=1.0
        )
        
        # Mock provider 설정
        mock_provider = Mock()
        mock_provider.get_ohlc.return_value = mock_ohlc
        mock_provider_class.return_value = mock_provider
        
        # 신호 수집
        signals = fetch_overnight_signals(
            target_date=date(2024, 1, 15),
            tickers={"Nasdaq": "^IXIC"}
        )
        
        assert "Nasdaq" in signals
        assert signals["Nasdaq"].success is True
        assert signals["Nasdaq"].last == 15150.0
    
    @patch('src.market.overnight.YahooMarketProvider')
    def test_failed_fetch(self, mock_provider_class):
        """실패한 신호 수집"""
        # Mock provider 설정 (에러 발생)
        mock_provider = Mock()
        mock_provider.get_ohlc.side_effect = Exception("API 오류")
        mock_provider_class.return_value = mock_provider
        
        # 신호 수집
        signals = fetch_overnight_signals(
            target_date=date(2024, 1, 15),
            tickers={"Nasdaq": "^IXIC"}
        )
        
        assert "Nasdaq" in signals
        assert signals["Nasdaq"].success is False
        assert signals["Nasdaq"].error is not None
    
    @patch('src.market.overnight.YahooMarketProvider')
    def test_multiple_tickers(self, mock_provider_class):
        """여러 티커 수집"""
        # Mock OHLC 데이터
        mock_ohlc = OHLC(
            open=15000.0,
            high=15200.0,
            low=14900.0,
            close=15150.0,
            volume=1000000,
            change_rate=1.0
        )
        
        # Mock provider 설정
        mock_provider = Mock()
        mock_provider.get_ohlc.return_value = mock_ohlc
        mock_provider_class.return_value = mock_provider
        
        # 여러 티커로 신호 수집
        tickers = {
            "Nasdaq": "^IXIC",
            "S&P500": "^GSPC",
            "VIX": "^VIX"
        }
        
        signals = fetch_overnight_signals(
            target_date=date(2024, 1, 15),
            tickers=tickers
        )
        
        assert len(signals) == 3
        assert "Nasdaq" in signals
        assert "S&P500" in signals
        assert "VIX" in signals
    
    def test_default_tickers(self):
        """기본 티커 확인"""
        assert "Nasdaq" in DEFAULT_TICKERS
        assert "S&P500" in DEFAULT_TICKERS
        assert "VIX" in DEFAULT_TICKERS
        assert "USDKRW" in DEFAULT_TICKERS


class TestAssessMarketTone:
    """시장 톤 평가 테스트"""
    
    def test_risk_on_market(self):
        """리스크 온 시장"""
        signals = {
            "Nasdaq": OvernightSignal(
                name="Nasdaq",
                ticker="^IXIC",
                prev_close=15000.0,
                last=15150.0,
                pct_change=1.0,
                success=True
            ),
            "S&P500": OvernightSignal(
                name="S&P500",
                ticker="^GSPC",
                prev_close=4800.0,
                last=4824.0,
                pct_change=0.5,
                success=True
            ),
            "VIX": OvernightSignal(
                name="VIX",
                ticker="^VIX",
                prev_close=15.0,
                last=14.0,
                pct_change=-6.67,
                success=True
            ),
            "USDKRW": OvernightSignal(
                name="USDKRW",
                ticker="KRW=X",
                prev_close=1300.0,
                last=1295.0,
                pct_change=-0.38,
                success=True
            ),
        }
        
        tone = assess_market_tone(signals)
        assert tone == "risk_on"
    
    def test_risk_off_market(self):
        """리스크 오프 시장"""
        signals = {
            "Nasdaq": OvernightSignal(
                name="Nasdaq",
                ticker="^IXIC",
                prev_close=15000.0,
                last=14850.0,
                pct_change=-1.0,
                success=True
            ),
            "S&P500": OvernightSignal(
                name="S&P500",
                ticker="^GSPC",
                prev_close=4800.0,
                last=4776.0,
                pct_change=-0.5,
                success=True
            ),
            "VIX": OvernightSignal(
                name="VIX",
                ticker="^VIX",
                prev_close=15.0,
                last=18.0,
                pct_change=20.0,
                success=True
            ),
            "USDKRW": OvernightSignal(
                name="USDKRW",
                ticker="KRW=X",
                prev_close=1300.0,
                last=1310.0,
                pct_change=0.77,
                success=True
            ),
        }
        
        tone = assess_market_tone(signals)
        assert tone == "risk_off"
    
    def test_mixed_market(self):
        """혼조 시장"""
        signals = {
            "Nasdaq": OvernightSignal(
                name="Nasdaq",
                ticker="^IXIC",
                prev_close=15000.0,
                last=15050.0,
                pct_change=0.33,
                success=True
            ),
            "S&P500": OvernightSignal(
                name="S&P500",
                ticker="^GSPC",
                prev_close=4800.0,
                last=4790.0,
                pct_change=-0.21,
                success=True
            ),
            "VIX": OvernightSignal(
                name="VIX",
                ticker="^VIX",
                prev_close=15.0,
                last=15.5,
                pct_change=3.33,
                success=True
            ),
        }
        
        tone = assess_market_tone(signals)
        assert tone in ["risk_on", "risk_off", "mixed"]
    
    def test_empty_signals(self):
        """빈 신호"""
        signals = {}
        tone = assess_market_tone(signals)
        assert tone in ["risk_on", "risk_off", "mixed"]
    
    def test_failed_signals(self):
        """실패한 신호들"""
        signals = {
            "Nasdaq": OvernightSignal(
                name="Nasdaq",
                ticker="^IXIC",
                success=False,
                error="데이터 없음"
            ),
            "S&P500": OvernightSignal(
                name="S&P500",
                ticker="^GSPC",
                success=False,
                error="데이터 없음"
            ),
        }
        
        tone = assess_market_tone(signals)
        # 실패한 신호만 있어도 판단은 가능해야 함
        assert tone in ["risk_on", "risk_off", "mixed"]
