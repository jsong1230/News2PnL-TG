"""테스트 공통 fixture 및 유틸리티"""
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import pytest
from pytz import UTC

# 프로젝트 루트를 경로에 추가
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.news.base import NewsItem
from src.analysis.news_analyzer import NewsDigest
from src.market.overnight import OvernightSignal


@pytest.fixture
def fixed_datetime():
    """고정된 datetime (2024-01-15 09:00 UTC)"""
    return datetime(2024, 1, 15, 9, 0, 0, tzinfo=UTC)


@pytest.fixture
def sample_news_items(fixed_datetime) -> List[NewsItem]:
    """샘플 뉴스 아이템 리스트"""
    base_time = fixed_datetime
    
    return [
        NewsItem(
            title="NVIDIA AI 칩 수요 급증, 주가 5% 상승",
            url="https://example.com/news1",
            source="TechNews",
            published_at=base_time - timedelta(hours=1),
            content="NVIDIA의 AI 칩 수요가 급증하면서 주가가 5% 상승했습니다."
        ),
        NewsItem(
            title="삼성전자, 새로운 반도체 공장 건설 발표",
            url="https://example.com/news2",
            source="BusinessDaily",
            published_at=base_time - timedelta(hours=2),
            content="삼성전자가 미국에 새로운 반도체 공장을 건설한다고 발표했습니다."
        ),
        NewsItem(
            title="SK하이닉스, HBM3 양산 본격화",
            url="https://example.com/news3",
            source="KoreaEconomy",
            published_at=base_time - timedelta(hours=3),
            content="SK하이닉스가 차세대 메모리 HBM3 양산을 본격화합니다."
        ),
        NewsItem(
            title="테슬라 전기차 판매량 전년 대비 20% 증가",
            url="https://example.com/news4",
            source="AutoNews",
            published_at=base_time - timedelta(hours=4),
            content="테슬라의 전기차 판매량이 전년 대비 20% 증가했습니다."
        ),
        NewsItem(
            title="애플, 새로운 아이폰 출시 예정",
            url="https://example.com/news5",
            source="TechCrunch",
            published_at=base_time - timedelta(hours=5),
            content="애플이 다음 달 새로운 아이폰을 출시할 예정입니다."
        ),
    ]


@pytest.fixture
def sample_digest() -> NewsDigest:
    """샘플 뉴스 다이제스트"""
    return NewsDigest(
        top_headlines=[
            "NVIDIA AI 칩 수요 급증, 주가 5% 상승",
            "삼성전자, 새로운 반도체 공장 건설 발표",
            "SK하이닉스, HBM3 양산 본격화"
        ],
        macro_summary="반도체 업계가 활황을 보이고 있으며, AI 칩 수요가 급증하고 있습니다.",
        sector_bullets={
            "반도체": [
                "NVIDIA AI 칩 수요 급증",
                "삼성전자 반도체 공장 건설",
                "SK하이닉스 HBM3 양산"
            ],
            "자동차": [
                "테슬라 판매량 증가"
            ]
        },
        korea_impact="상",
        sources=["TechNews", "BusinessDaily", "KoreaEconomy"],
        fetched_count=10,
        time_filtered_count=8,
        deduped_count=5
    )


@pytest.fixture
def sample_overnight_signals() -> Dict[str, OvernightSignal]:
    """샘플 오버나이트 신호"""
    return {
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


def create_news_item(
    title: str,
    hours_ago: int = 1,
    source: str = "TestSource",
    content: str = "",
    base_time: Optional[datetime] = None
) -> NewsItem:
    """뉴스 아이템 생성 헬퍼 함수"""
    if base_time is None:
        base_time = datetime.now(UTC)
    
    if not content:
        content = f"테스트 콘텐츠: {title}"
    
    return NewsItem(
        title=title,
        url=f"https://example.com/{title.replace(' ', '-').lower()}",
        source=source,
        published_at=base_time - timedelta(hours=hours_ago),
        content=content
    )
