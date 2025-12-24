"""시세 소스 추상 클래스"""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional
from dataclasses import dataclass


@dataclass
class OHLC:
    """OHLC 데이터"""
    open: float
    high: float
    low: float
    close: float
    volume: Optional[int] = None
    change_rate: Optional[float] = None  # 등락률 (%)


class MarketProvider(ABC):
    """시세 제공자 추상 클래스"""
    
    @abstractmethod
    def get_price(self, symbol: str, date: Optional[datetime] = None) -> float:
        """
        종가 조회
        
        Args:
            symbol: 종목코드
            date: 날짜 (None이면 오늘)
        
        Returns:
            종가
        """
        pass
    
    @abstractmethod
    def get_ohlc(self, symbol: str, date: Optional[datetime] = None) -> OHLC:
        """
        OHLC 조회
        
        Args:
            symbol: 종목코드
            date: 날짜 (None이면 오늘)
        
        Returns:
            OHLC 데이터
        """
        pass

