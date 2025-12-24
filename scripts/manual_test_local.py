#!/usr/bin/env python3
"""로컬 수동 테스트 스크립트 (pytest에서 제외)"""
import sys
import logging
from pathlib import Path

# 프로젝트 루트를 경로에 추가 (어디서 실행해도 동작하도록)
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

from src.config import NEWS_PROVIDER, GOOGLE_NEWS_QUERY
from src.news.provider import get_news_provider
from src.analysis.news_analyzer import create_digest
from src.utils.date_utils import get_last_night_range, get_kst_now


def test_rss_fetch():
    """RSS fetch 테스트"""
    print("=" * 60)
    print("테스트 1: RSS 뉴스 수집")
    print("=" * 60)
    
    try:
        provider = get_news_provider("rss", query=GOOGLE_NEWS_QUERY)
        start_dt, end_dt = get_last_night_range()
        
        print(f"검색 쿼리: {GOOGLE_NEWS_QUERY}")
        print(f"기간: {start_dt} ~ {end_dt}")
        print("\n뉴스 수집 중...")
        
        news_items = provider.fetch_news(start_dt=start_dt, end_dt=end_dt)
        
        print(f"\n✓ 수집 완료: {len(news_items)}건")
        if news_items:
            print("\n샘플 뉴스:")
            for i, item in enumerate(news_items[:3], 1):
                print(f"{i}. {item.title}")
                print(f"   출처: {item.source}")
                print(f"   URL: {item.url}")
                print(f"   발행: {item.published_at}")
                print()
        
        return news_items
    
    except Exception as e:
        print(f"✗ RSS 수집 실패: {e}")
        import traceback
        traceback.print_exc()
        return []


def test_digest(news_items):
    """다이제스트 생성 테스트"""
    print("=" * 60)
    print("테스트 2: 다이제스트 생성")
    print("=" * 60)
    
    if not news_items:
        print("뉴스가 없어 다이제스트를 생성할 수 없습니다.")
        return
    
    try:
        digest = create_digest(news_items)
        
        print(f"\n✓ 다이제스트 생성 완료")
        print(f"\n핵심 헤드라인 ({len(digest.top_headlines)}개):")
        for i, headline in enumerate(digest.top_headlines[:5], 1):
            print(f"  {i}. {headline}")
        
        print(f"\n거시 요약:")
        print(digest.macro_summary)
        
        print(f"\n섹터별 뉴스:")
        for sector, bullets in digest.sector_bullets.items():
            print(f"  {sector}: {len(bullets)}건")
            for bullet in bullets[:2]:
                print(f"    - {bullet}")
        
        print(f"\n한국장 영향도: {digest.korea_impact}")
        
        print(f"\n근거 링크 ({len(digest.sources)}개):")
        for i, url in enumerate(digest.sources[:3], 1):
            print(f"  {i}. {url}")
    
    except Exception as e:
        print(f"✗ 다이제스트 생성 실패: {e}")
        import traceback
        traceback.print_exc()


def test_fallback():
    """Fallback 테스트"""
    print("=" * 60)
    print("테스트 3: Fallback (더미 provider)")
    print("=" * 60)
    
    try:
        # 잘못된 provider로 시도 (fallback 테스트)
        provider = get_news_provider("dummy")
        start_dt, end_dt = get_last_night_range()
        
        news_items = provider.fetch_news(start_dt=start_dt, end_dt=end_dt)
        
        print(f"✓ 더미 provider로 {len(news_items)}건 수집")
        print("\n샘플:")
        for item in news_items[:2]:
            print(f"  - {item.title}")
    
    except Exception as e:
        print(f"✗ Fallback 실패: {e}")


def main():
    """메인 테스트"""
    print("\n" + "=" * 60)
    print("News2PnL-TG 로컬 테스트")
    print("=" * 60 + "\n")
    
    # 테스트 1: RSS 수집
    news_items = test_rss_fetch()
    
    # 테스트 2: 다이제스트 생성
    if news_items:
        test_digest(news_items)
    
    # 테스트 3: Fallback
    test_fallback()
    
    print("\n" + "=" * 60)
    print("테스트 완료")
    print("=" * 60)


if __name__ == "__main__":
    main()

