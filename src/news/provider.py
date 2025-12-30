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
from src.news.quality import calculate_quality_score, filter_by_quality
from src.utils.date_utils import KST
from src.utils.text import normalize_title, jaccard_similarity
from src.config import GOOGLE_NEWS_MAX_PER_QUERY, NAVER_CLIENT_ID, NAVER_CLIENT_SECRET

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
        self.title_threshold = 0.85  # 제목 유사도 임계값
        self.min_quality_score = 0.4  # 최소 품질 점수 (수집 단계는 느슨하게)
    
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
        
        # 1. 품질 점수 계산 및 필터링
        items_with_quality = []
        for item in all_news_items:
            quality_score = calculate_quality_score(item)
            if quality_score >= self.min_quality_score:
                items_with_quality.append((item, quality_score))
        
        filtered_by_quality_count = len(items_with_quality)
        logger.info(f"품질 필터링: {total_fetched}건 → {filtered_by_quality_count}건 (임계값: {self.min_quality_score})")
        
        # 2. URL 및 제목 유사도 기준 중복 제거
        seen_urls: Set[str] = set()
        seen_titles = []  # (normalized_title, item)
        unique_items = []
        
        # 품질 점수 높은 순으로 정렬하여 중복 제거 시 고품질 뉴스 우선 유지
        items_with_quality.sort(key=lambda x: x[1], reverse=True)
        
        for item, score in items_with_quality:
            # URL 기준 중복 체크
            if item.url in seen_urls:
                continue
            
            # 제목 유사도 기준 중복 체크
            norm_title = normalize_title(item.title)
            is_title_duplicate = False
            for seen_norm, _ in seen_titles:
                if jaccard_similarity(norm_title, seen_norm) >= self.title_threshold:
                    is_title_duplicate = True
                    break
            
            if is_title_duplicate:
                continue
                
            # 신규 아이템 추가
            seen_urls.add(item.url)
            seen_titles.append((norm_title, item))
            unique_items.append(item)
        
        logger.info(f"최종 중복 제거: {filtered_by_quality_count}건 → {len(unique_items)}건 (URL + 제목 유사도)")
        
        # 파싱된 날짜 중 최신/가장 오래된 것 찾기
        parsed_dates = [item.published_at for item in unique_items if item.published_at]
        if parsed_dates:
            oldest = min(parsed_dates)
            newest = max(parsed_dates)
            logger.info(f"파싱된 날짜 범위: {oldest.strftime('%Y-%m-%d %H:%M:%S %Z')} ~ {newest.strftime('%Y-%m-%d %H:%M:%S %Z')} (UTC)")
            # KST로도 출력
            oldest_kst = oldest.astimezone(KST)
            newest_kst = newest.astimezone(KST)
            logger.info(f"파싱된 날짜 범위: {oldest_kst.strftime('%Y-%m-%d %H:%M:%S %Z')} ~ {newest_kst.strftime('%Y-%m-%d %H:%M:%S %Z')} (KST)")
        
        # 카운트 정보를 속성으로 저장
        self._last_fetched_count = total_fetched
        self._parsed_ok_count = self.parsed_ok_count
        self._parsed_fail_count = self.parsed_fail_count
        
        return unique_items


class NaverNewsProvider(NewsProvider):
    """네이버 뉴스 API 제공자"""
    
    def __init__(self, client_id: str, client_secret: str, queries: List[str], max_per_query: int = 30):
        """
        Args:
            client_id: 네이버 API 클라이언트 ID
            client_secret: 네이버 API 클라이언트 시크릿
            queries: 검색 쿼리 리스트
            max_per_query: 쿼리별 최대 수집 개수 (네이버 최대 100)
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.queries = queries if queries else ["한국 주식 시장"]
        self.max_per_query = min(max_per_query, 100)
        self.api_url = "https://openapi.naver.com/v1/search/news.json"
        self.parsed_ok_count = 0
        self.parsed_fail_count = 0
        self.title_threshold = 0.85
        self.min_quality_score = 0.4

    def _parse_pubdate(self, pub_date_text: str) -> Optional[datetime]:
        """RFC 822 형식 날짜 파싱"""
        try:
            dt = parsedate_to_datetime(pub_date_text)
            if dt.tzinfo is None:
                dt = KST.localize(dt)  # 네이버는 기본적으로 한국 시간대 (+0900)
            return dt.astimezone(UTC)
        except Exception as e:
            logger.debug(f"네이버 날짜 파싱 실패: {pub_date_text}, {e}")
            return None

    def _fetch_single_query(self, query: str) -> List[NewsItem]:
        if not self.client_id or not self.client_secret:
            logger.warning("네이버 API 키가 설정되지 않았습니다.")
            return []

        headers = {
            "X-Naver-Client-Id": self.client_id,
            "X-Naver-Client-Secret": self.client_secret
        }
        params = {
            "query": query,
            "display": self.max_per_query,
            "sort": "date"  # 최신순
        }

        try:
            response = requests.get(self.api_url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            news_items = []
            for item in data.get("items", []):
                # HTML 태그 제거 (<b> 등)
                title = re.sub(r'<[^>]*>', '', item.get("title", ""))
                link = item.get("originallink") or item.get("link")
                
                published_at = self._parse_pubdate(item.get("pubDate", ""))
                if published_at:
                    self.parsed_ok_count += 1
                else:
                    self.parsed_fail_count += 1

                news_items.append(NewsItem(
                    title=title,
                    url=link,
                    published_at=published_at,
                    source=None  # 네이버 API는 개별 기사 출처를 따로 주지 않음
                ))
            
            return news_items
        except Exception as e:
            logger.warning(f"네이버 쿼리 '{query}' 호출 실패: {e}")
            return []

    def fetch_news(self, start_dt: Optional[datetime] = None,
                   end_dt: Optional[datetime] = None) -> List[NewsItem]:
        self.parsed_ok_count = 0
        self.parsed_fail_count = 0
        all_news_items = []

        for query in self.queries:
            items = self._fetch_single_query(query)
            all_news_items.extend(items)
        
        total_fetched = len(all_news_items)
        
        # 품질 및 중복 제거
        items_with_quality = []
        for item in all_news_items:
            quality_score = calculate_quality_score(item)
            if quality_score >= self.min_quality_score:
                items_with_quality.append((item, quality_score))
        
        items_with_quality.sort(key=lambda x: x[1], reverse=True)
        
        seen_urls = set()
        seen_titles = []
        unique_items = []
        
        for item, score in items_with_quality:
            if item.url in seen_urls:
                continue
            
            norm_title = normalize_title(item.title)
            is_title_duplicate = False
            for seen_norm, _ in seen_titles:
                if jaccard_similarity(norm_title, seen_norm) >= self.title_threshold:
                    is_title_duplicate = True
                    break
            
            if is_title_duplicate:
                continue
                
            seen_urls.add(item.url)
            seen_titles.append((norm_title, item))
            unique_items.append(item)
            
        logger.info(f"네이버 뉴스 수집: {total_fetched}건 → 최종 {len(unique_items)}건")
        
        self._last_fetched_count = total_fetched
        self._parsed_ok_count = self.parsed_ok_count
        self._parsed_fail_count = self.parsed_fail_count
        
        return unique_items


class MultiNewsProvider(NewsProvider):
    """여러 뉴스 제공자를 결합하여 수집"""
    
    def __init__(self, providers: List[NewsProvider]):
        self.providers = providers
        self._last_fetched_count = 0
        self._parsed_ok_count = 0
        self._parsed_fail_count = 0

    def fetch_news(self, start_dt: Optional[datetime] = None,
                   end_dt: Optional[datetime] = None) -> List[NewsItem]:
        all_items = []
        self._last_fetched_count = 0
        self._parsed_ok_count = 0
        self._parsed_fail_count = 0
        
        for provider in self.providers:
            # 개별 제공자에서 이미 품질 필터링 및 중복 제거가 어느 정도 되어 있음
            items = provider.fetch_news(start_dt, end_dt)
            all_items.extend(items)
            
            self._last_fetched_count += getattr(provider, '_last_fetched_count', len(items))
            self._parsed_ok_count += getattr(provider, '_parsed_ok_count', sum(1 for i in items if i.published_at))
            self._parsed_fail_count += getattr(provider, '_parsed_fail_count', sum(1 for i in items if not i.published_at))
        
        # 전체 항목에 대해 최종 중복 제거 (URL 기준 및 제목 유사도 기준)
        # 이미 개별 제공자 내에서 처리되었지만, 제공자 간 중복이 있을 수 있음
        unique_items = []
        seen_urls = set()
        seen_titles = []
        title_threshold = 0.85
        
        # 품질 점수 순으로 정렬 (이미 개별 제공자에서 정렬되어 있을 수 있으나 전체 병합 후 다시 정렬)
        items_with_quality = [(item, calculate_quality_score(item)) for item in all_items]
        items_with_quality.sort(key=lambda x: x[1], reverse=True)
        
        for item, score in items_with_quality:
            if item.url in seen_urls:
                continue
            
            norm_title = normalize_title(item.title)
            is_title_duplicate = False
            for seen_norm, _ in seen_titles:
                if jaccard_similarity(norm_title, seen_norm) >= title_threshold:
                    is_title_duplicate = True
                    break
            
            if is_title_duplicate:
                continue
                
            seen_urls.add(item.url)
            seen_titles.append((norm_title, item))
            unique_items.append(item)
            
        logger.info(f"MultiNewsProvider: 총 {len(all_items)}건 → 최종 {len(unique_items)}건")
        return unique_items


def get_news_provider(provider_name: str = "dummy", **kwargs) -> NewsProvider:
    """
    뉴스 제공자 팩토리
    
    Args:
        provider_name: 제공자 이름 ("dummy" | "rss" | "naver" 또는 이들의 조합 "rss,naver")
    """
    if not provider_name or provider_name == "dummy":
        return DummyNewsProvider()
    
    # 여러 제공자 지원 (쉼표 구분)
    if "," in provider_name:
        provider_names = [p.strip() for p in provider_name.split(",") if p.strip()]
        providers = []
        for name in provider_names:
            providers.append(get_news_provider(name, **kwargs))
        return MultiNewsProvider(providers)
    
    from src.config import DEFAULT_NEWS_QUERIES, NAVER_CLIENT_ID, NAVER_CLIENT_SECRET
    
    queries = kwargs.get("queries") or kwargs.get("query")
    if not queries:
        queries = DEFAULT_NEWS_QUERIES
    elif isinstance(queries, str):
        queries = [queries]
    
    max_per_query = kwargs.get("max_per_query", GOOGLE_NEWS_MAX_PER_QUERY)
    
    if provider_name == "rss":
        return GoogleNewsRSSProvider(queries=queries, max_per_query=max_per_query)
    elif provider_name == "naver":
        client_id = kwargs.get("client_id") or NAVER_CLIENT_ID
        client_secret = kwargs.get("client_secret") or NAVER_CLIENT_SECRET
        return NaverNewsProvider(
            client_id=client_id,
            client_secret=client_secret,
            queries=queries,
            max_per_query=max_per_query
        )
    else:
        raise ValueError(f"지원하지 않는 뉴스 제공자: {provider_name}")
