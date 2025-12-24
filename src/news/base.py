"""뉴스 소스 추상 클래스"""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional
from dataclasses import dataclass


@dataclass
class NewsItem:
    """뉴스 아이템"""
    title: str
    url: str  # 필수
    published_at: datetime  # UTC ISO 형식 (필수)
    source: Optional[str] = None
    content: Optional[str] = None  # 선택사항 (RSS에서는 보통 없음)


class NewsProvider(ABC):
    """뉴스 제공자 추상 클래스"""
    
    @abstractmethod
    def fetch_news(self, start_dt: Optional[datetime] = None, 
                   end_dt: Optional[datetime] = None) -> List[NewsItem]:
        """
        뉴스 수집
        
        Args:
            start_dt: 시작 날짜/시간 (KST 또는 UTC)
            end_dt: 종료 날짜/시간 (KST 또는 UTC)
        
        Returns:
            뉴스 아이템 리스트
        """
        pass

