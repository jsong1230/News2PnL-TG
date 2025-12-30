import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime
from pytz import UTC
from src.news.provider import NaverNewsProvider
from src.news.base import NewsItem

@pytest.fixture
def naver_provider():
    return NaverNewsProvider(
        client_id="test_id",
        client_secret="test_secret",
        queries=["삼성전자"],
        max_per_query=10
    )

def test_naver_parse_pubdate(naver_provider):
    # Naver RFC 822 format: Tue, 30 Dec 2025 17:00:00 +0900
    date_str = "Tue, 30 Dec 2025 17:00:00 +0900"
    dt = naver_provider._parse_pubdate(date_str)
    assert dt is not None
    assert dt.astimezone(UTC).hour == 8  # 17 - 9 = 8

def test_naver_fetch_news_mocked(naver_provider):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "items": [
            {
                "title": "<b>삼성전자</b>, 실적 발표",
                "originallink": "https://example.com/1",
                "link": "https://n.news.naver.com/1",
                "description": "삼성전자 실적...",
                "pubDate": "Tue, 30 Dec 2025 17:00:00 +0900"
            },
            {
                "title": "삼성전자 주가 상승",
                "originallink": "https://example.com/2",
                "link": "https://n.news.naver.com/2",
                "description": "삼성전자 주가...",
                "pubDate": "Tue, 30 Dec 2025 18:00:00 +0900"
            }
        ]
    }

    with patch("requests.get", return_value=mock_response):
        news = naver_provider.fetch_news()
        
        assert len(news) == 2
        titles = [n.title for n in news]
        assert "삼성전자 주가 상승" in titles
        assert "삼성전자, 실적 발표" in titles
        assert not any("<b>" in n.title for n in news)
        # Check if the URL is correctly picked (originallink preferred)
        urls = [n.url for n in news]
        assert "https://example.com/1" in urls
        assert "https://example.com/2" in urls

def test_naver_fetch_news_deduplication(naver_provider):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "items": [
            {
                "title": "삼성전자 실적 발표",
                "originallink": "https://example.com/1",
                "pubDate": "Tue, 30 Dec 2025 17:00:00 +0900"
            },
            {
                "title": "삼성전자 실적 발표!!!",  # Duplicate title
                "originallink": "https://example.com/2",
                "pubDate": "Tue, 30 Dec 2025 17:01:00 +0900"
            }
        ]
    }

    with patch("requests.get", return_value=mock_response):
        news = naver_provider.fetch_news()
        assert len(news) == 1  # Should be deduplicated by title

def test_multi_provider():
    from src.news.provider import MultiNewsProvider, DummyNewsProvider
    p1 = DummyNewsProvider()
    p2 = DummyNewsProvider()
    multi = MultiNewsProvider([p1, p2])
    
    news = multi.fetch_news()
    # Dummy returns 8 items. 8 + 8 = 16. 
    # But MultiNewsProvider also does deduplication. 
    # Since Dummy items are identical, it should deduplicate to 8.
    assert len(news) == 8 

def test_get_news_provider_combined():
    from src.news.provider import get_news_provider, MultiNewsProvider
    provider = get_news_provider("rss,naver")
    assert isinstance(provider, MultiNewsProvider)
    assert len(provider.providers) == 2

