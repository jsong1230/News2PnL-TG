"""뉴스 제공자 구현"""
from datetime import datetime, timedelta
from typing import List, Optional, Set
import xml.etree.ElementTree as ET
import re
import logging
from urllib.parse import quote, urlparse
from email.utils import parsedate_to_datetime

import requests
from pytz import UTC

from src.news.base import NewsProvider, NewsItem
from src.utils.date_utils import KST
from src.config import GOOGLE_NEWS_MAX_PER_QUERY

logger = logging.getLogger(__name__)


class DummyNewsProvider(NewsProvider):
    """더미 뉴스 제공자 (테스트용)"""
    
    def fetch_news(self, start_dt: Optional[datetime] = None,
                   end_dt: Optional[datetime] = None) -> List[NewsItem]:
        """더미 뉴스 반환"""
        if end_dt is None:
            end_dt = datetime.now(KST)
        if start_dt is None:
            start_dt = end_dt - timedelta(days=1)
        
        # KST로 변환
        if start_dt.tzinfo is None:
            start_dt = KST.localize(start_dt)
        if end_dt.tzinfo is None:
            end_dt = KST.localize(end_dt)
        
        # 더미 뉴스 생성 (더 많은 샘플)
        dummy_news = [
            NewsItem(
                title="삼성전자, 반도체 업황 개선 기대감 확산",
                url="https://example.com/news/1",
                published_at=(end_dt - timedelta(hours=2)).astimezone(KST),
                source="더미 뉴스",
                content="삼성전자가 최근 반도체 업황 개선 기대감에 힘입어 주가가 상승세를 보이고 있습니다."
            ),
            NewsItem(
                title="SK하이닉스, HBM 수요 증가로 실적 개선 전망",
                url="https://example.com/news/2",
                published_at=(end_dt - timedelta(hours=3)).astimezone(KST),
                source="더미 뉴스",
                content="SK하이닉스가 AI 반도체 수요 증가로 HBM 매출이 크게 늘어날 것으로 예상됩니다."
            ),
            NewsItem(
                title="엔비디아, AI 반도체 수요 급증으로 실적 상승",
                url="https://example.com/news/3",
                published_at=(end_dt - timedelta(hours=4)).astimezone(KST),
                source="더미 뉴스",
                content="엔비디아가 AI 반도체 수요 급증으로 실적이 크게 상승했습니다."
            ),
            NewsItem(
                title="연준, 기준금리 동결 결정 발표",
                url="https://example.com/news/4",
                published_at=(end_dt - timedelta(hours=5)).astimezone(KST),
                source="더미 뉴스",
                content="연준이 기준금리를 동결하기로 결정했습니다."
            ),
            NewsItem(
                title="나스닥, AI 주도 상승세 지속",
                url="https://example.com/news/5",
                published_at=(end_dt - timedelta(hours=6)).astimezone(KST),
                source="더미 뉴스",
                content="나스닥이 AI 관련 주식의 상승세로 인해 지속적인 상승을 보이고 있습니다."
            ),
            NewsItem(
                title="비트코인, 현물 ETF 승인 기대감 확산",
                url="https://example.com/news/6",
                published_at=(end_dt - timedelta(hours=7)).astimezone(KST),
                source="더미 뉴스",
                content="비트코인 현물 ETF 승인 기대감이 확산되며 가격이 상승했습니다."
            ),
            NewsItem(
                title="LG에너지솔루션, 전기차 배터리 수주 증가",
                url="https://example.com/news/7",
                published_at=(end_dt - timedelta(hours=8)).astimezone(KST),
                source="더미 뉴스",
                content="LG에너지솔루션이 전기차 배터리 수주가 증가했다고 발표했습니다."
            ),
            NewsItem(
                title="원달러 환율, 하락세 지속",
                url="https://example.com/news/8",
                published_at=(end_dt - timedelta(hours=9)).astimezone(KST),
                source="더미 뉴스",
                content="원달러 환율이 하락세를 보이며 달러 약세가 지속되고 있습니다."
            ),
        ]
        
        return dummy_news


class GoogleNewsRSSProvider(NewsProvider):
    """Google News RSS 제공자 (여러 쿼리 지원)"""
    
    def __init__(self, queries: List[str], max_per_query: int = 30):
        """
        Args:
            queries: Google News 검색 쿼리 리스트
            max_per_query: 쿼리별 최대 수집 개수
        """
        self.queries = queries if queries else ["한국 주식 시장"]
        self.max_per_query = max_per_query
        self.base_url = "https://news.google.com/rss/search"
        self.parsed_ok_count = 0
        self.parsed_fail_count = 0
    
    def _parse_pubdate(self, pub_date_text: str) -> Optional[datetime]:
        """
        pubDate 파싱 (안정화 버전)
        
        Args:
            pub_date_text: RFC 822 형식 날짜 문자열
        
        Returns:
            UTC timezone-aware datetime 또는 None
        """
        try:
            # email.utils.parsedate_to_datetime() 사용
            dt = parsedate_to_datetime(pub_date_text)
            
            # timezone-aware로 변환 (없으면 UTC로 가정)
            if dt.tzinfo is None:
                dt = UTC.localize(dt)
            else:
                # UTC로 변환
                dt = dt.astimezone(UTC)
            
            self.parsed_ok_count += 1
            return dt
        
        except Exception as e:
            logger.debug(f"날짜 파싱 실패: {pub_date_text}, {e}")
            self.parsed_fail_count += 1
            return None
    
    def _fetch_single_query(self, query: str) -> List[NewsItem]:
        """단일 쿼리로 뉴스 수집"""
        try:
            # URL 인코딩
            encoded_query = quote(query)
            url = f"{self.base_url}?q={encoded_query}&hl=ko&gl=KR&ceid=KR:ko"
            
            # 요청 (타임아웃 10초)
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            # XML 파싱
            root = ET.fromstring(response.content)
            
            news_items = []
            for item in root.findall(".//item")[:self.max_per_query]:  # 최대 개수 제한
                try:
                    title = item.find("title")
                    if title is None or title.text is None:
                        continue
                    
                    link = item.find("link")
                    if link is None or link.text is None:
                        continue
                    
                    pub_date = item.find("pubDate")
                    published_at = None
                    if pub_date is not None and pub_date.text:
                        published_at = self._parse_pubdate(pub_date.text)
                    
                    # source 추출 (title에서 " - 출처명" 형식)
                    source = None
                    title_text = title.text.strip()
                    if " - " in title_text:
                        parts = title_text.rsplit(" - ", 1)
                        if len(parts) == 2:
                            title_text = parts[0]
                            source = parts[1]
                    
                    news_item = NewsItem(
                        title=title_text,
                        url=link.text.strip(),
                        published_at=published_at,  # None이어도 포함
                        source=source
                    )
                    news_items.append(news_item)
                
                except Exception as e:
                    logger.warning(f"뉴스 아이템 파싱 실패: {e}")
                    continue
            
            logger.info(f"쿼리 '{query}': {len(news_items)}건 수집 (최대 {self.max_per_query}개)")
            return news_items
        
        except requests.RequestException as e:
            logger.warning(f"쿼리 '{query}' RSS 요청 실패: {e}")
            return []
        except ET.ParseError as e:
            logger.warning(f"쿼리 '{query}' XML 파싱 실패: {e}")
            return []
        except Exception as e:
            logger.warning(f"쿼리 '{query}' 수집 중 오류: {e}")
            return []
    
    def fetch_news(self, start_dt: Optional[datetime] = None,
                    end_dt: Optional[datetime] = None) -> List[NewsItem]:
        """
        여러 쿼리로 뉴스 수집 및 병합 (시간 필터링은 하지 않음)
        
        Args:
            start_dt: 시작 날짜/시간 (사용하지 않음, 하위 호환용)
            end_dt: 종료 날짜/시간 (사용하지 않음, 하위 호환용)
        
        Returns:
            뉴스 아이템 리스트 (URL 기준 unique만 적용)
        """
        # 파싱 카운터 초기화
        self.parsed_ok_count = 0
        self.parsed_fail_count = 0
        
        all_news_items = []
        
        # 각 쿼리별로 순차 수집
        for query in self.queries:
            query = query.strip()
            if not query:
                continue
            
            items = self._fetch_single_query(query)
            all_news_items.extend(items)
            logger.info(f"쿼리 '{query}': {len(items)}건 수집")
        
        total_fetched = len(all_news_items)
        logger.info(f"전체 수집: {total_fetched}건 (쿼리 {len(self.queries)}개)")
        logger.info(f"published_at 파싱: 성공 {self.parsed_ok_count}건, 실패 {self.parsed_fail_count}건")
        
        # 파싱된 날짜 중 최신/가장 오래된 것 찾기
        parsed_dates = [item.published_at for item in all_news_items if item.published_at]
        if parsed_dates:
            oldest = min(parsed_dates)
            newest = max(parsed_dates)
            logger.info(f"파싱된 날짜 범위: {oldest.strftime('%Y-%m-%d %H:%M:%S %Z')} ~ {newest.strftime('%Y-%m-%d %H:%M:%S %Z')} (UTC)")
            # KST로도 출력
            oldest_kst = oldest.astimezone(KST)
            newest_kst = newest.astimezone(KST)
            logger.info(f"파싱된 날짜 범위: {oldest_kst.strftime('%Y-%m-%d %H:%M:%S %Z')} ~ {newest_kst.strftime('%Y-%m-%d %H:%M:%S %Z')} (KST)")
        
        # URL 완전 동일 기준 unique
        seen_urls: Set[str] = set()
        unique_by_url = []
        for item in all_news_items:
            if item.url not in seen_urls:
                seen_urls.add(item.url)
                unique_by_url.append(item)
        
        logger.info(f"URL unique: {len(all_news_items)}건 → {len(unique_by_url)}건")
        
        # 카운트 정보를 속성으로 저장 (morning.py에서 접근)
        self._last_fetched_count = total_fetched
        self._parsed_ok_count = self.parsed_ok_count
        self._parsed_fail_count = self.parsed_fail_count
        
        return unique_by_url


def get_news_provider(provider_name: str = "dummy", **kwargs) -> NewsProvider:
    """
    뉴스 제공자 팩토리
    
    Args:
        provider_name: 제공자 이름 ("dummy" | "rss")
        **kwargs: 제공자별 추가 인자
            - queries: 쿼리 리스트 (우선)
            - query: 단일 쿼리 (하위 호환)
            - max_per_query: 쿼리별 최대 수집 개수
    
    Returns:
        NewsProvider 인스턴스
    """
    if provider_name == "dummy":
        return DummyNewsProvider()
    elif provider_name == "rss":
        # queries가 있으면 사용, 없으면 query 사용, 둘 다 없으면 기본 쿼리 세트 사용
        from src.config import DEFAULT_NEWS_QUERIES
        queries = kwargs.get("queries")
        if not queries:
            query = kwargs.get("query")
            if query:
                queries = [query]
            else:
                queries = DEFAULT_NEWS_QUERIES
        max_per_query = kwargs.get("max_per_query", GOOGLE_NEWS_MAX_PER_QUERY)
        return GoogleNewsRSSProvider(queries=queries, max_per_query=max_per_query)
    else:
        raise ValueError(f"지원하지 않는 뉴스 제공자: {provider_name}")
