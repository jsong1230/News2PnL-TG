"""오전 리포트 생성 모듈"""
import logging
from typing import List
from datetime import datetime
from collections import defaultdict

from src.config import (
    NEWS_PROVIDER, GOOGLE_NEWS_QUERY, GOOGLE_NEWS_QUERIES, GOOGLE_NEWS_MAX_PER_QUERY,
    NEWS_WINDOW_MODE, DEFAULT_NEWS_QUERIES, LLM_ENABLED, LLM_MODEL, NEWS_DEBUG_TAGS,
    OVERNIGHT_ENABLED, OVERNIGHT_DEBUG, OVERNIGHT_TICKERS
)
from src.news.provider import get_news_provider, DummyNewsProvider
from src.news.base import NewsItem
from src.analysis.news_analyzer import create_digest, NewsDigest
from src.analysis.stock_picker import pick_watch_stocks, WatchStock
from src.database import get_db_connection, upsert_symbol, upsert_recommendation
from src.utils.disclaimer import append_disclaimer
from src.utils.date_utils import get_kst_now, get_kst_date, get_news_window, KST
from src.market.overnight import fetch_overnight_signals, assess_market_tone
from pytz import UTC

logger = logging.getLogger(__name__)


def filter_by_time_range(news_items: List[NewsItem], 
                         start_dt: datetime, 
                         end_dt: datetime) -> tuple[List[NewsItem], dict]:
    """
    시간 범위로 필터링 (디버그 정보 포함)
    
    Args:
        news_items: 뉴스 아이템 리스트
        start_dt: 시작 날짜/시간 (KST)
        end_dt: 종료 날짜/시간 (KST)
    
    Returns:
        (필터링된 뉴스 아이템 리스트, 디버그 정보 딕셔너리)
    """
    # KST를 UTC로 변환 (내부 비교는 UTC로)
    if start_dt.tzinfo != KST:
        start_dt = start_dt.astimezone(KST)
    if end_dt.tzinfo != KST:
        end_dt = end_dt.astimezone(KST)
    
    start_dt_utc = start_dt.astimezone(UTC)
    end_dt_utc = end_dt.astimezone(UTC)
    
    filtered = []
    too_old_count = 0
    too_new_count = 0
    no_time_count = 0
    
    for item in news_items:
        if not item.published_at:
            # 날짜가 없으면 일단 포함 (정렬 시 아래로)
            no_time_count += 1
            filtered.append(item)
            continue
        
        # UTC로 변환 (이미 UTC일 수도 있음)
        item_dt_utc = item.published_at
        if item_dt_utc.tzinfo != UTC:
            item_dt_utc = item_dt_utc.astimezone(UTC)
        
        # 범위 체크 (UTC로 비교)
        if item_dt_utc < start_dt_utc:
            too_old_count += 1
            continue
        if item_dt_utc > end_dt_utc:
            too_new_count += 1
            continue
        
        filtered.append(item)
    
    debug_info = {
        "too_old_count": too_old_count,
        "too_new_count": too_new_count,
        "no_time_count": no_time_count,
    }
    
    return (filtered, debug_info)


def generate_morning_report() -> str:
    """
    오전 리포트 생성
    
    Returns:
        리포트 메시지 (Markdown 형식)
    """
    now = get_kst_now()
    today = get_kst_date()
    datetime_str = now.strftime("%Y-%m-%d %H:%M KST")
    
    # 1. 뉴스 수집 시간 윈도우 계산 (무조건 get_news_window 사용)
    start_dt, end_dt, window_mode, lookback_hours = get_news_window(now, mode=NEWS_WINDOW_MODE)
    
    # 2. 뉴스 수집 (에러 시 fallback)
    news_items: List[NewsItem] = []
    fetched_count = 0
    parsed_ok_count = 0
    parsed_fail_count = 0
    
    try:
        # 쿼리 리스트 준비
        if GOOGLE_NEWS_QUERIES:
            # 여러 쿼리 (쉼표 구분)
            queries = [q.strip() for q in GOOGLE_NEWS_QUERIES.split(",") if q.strip()]
        else:
            # 기본 쿼리 세트 사용
            queries = DEFAULT_NEWS_QUERIES
        
        news_provider = get_news_provider(
            NEWS_PROVIDER,
            queries=queries,
            max_per_query=GOOGLE_NEWS_MAX_PER_QUERY
        )
        
        # Provider는 시간 필터링 없이 가능한 많이 가져옴
        news_items = news_provider.fetch_news()
        
        if NEWS_PROVIDER == "rss" and hasattr(news_provider, '_last_fetched_count'):
            fetched_count = news_provider._last_fetched_count
            parsed_ok_count = getattr(news_provider, '_parsed_ok_count', 0)
            parsed_fail_count = getattr(news_provider, '_parsed_fail_count', 0)
        else:
            fetched_count = len(news_items)
            parsed_ok_count = sum(1 for item in news_items if item.published_at)
            parsed_fail_count = sum(1 for item in news_items if not item.published_at)
        
        logger.info(f"뉴스 수집 완료: {fetched_count}건 (쿼리: {len(queries)}개)")
        print(f"parsed_ok={parsed_ok_count} parsed_fail={parsed_fail_count}")
    except Exception as e:
        logger.error(f"뉴스 수집 실패: {e}, 더미 provider로 전환", exc_info=True)
        # Fallback: 더미 provider 사용
        try:
            dummy_provider = DummyNewsProvider()
            news_items = dummy_provider.fetch_news()
            fetched_count = len(news_items)
            parsed_ok_count = sum(1 for item in news_items if item.published_at)
            parsed_fail_count = sum(1 for item in news_items if not item.published_at)
            print(f"parsed_ok={parsed_ok_count} parsed_fail={parsed_fail_count}")
        except Exception as fallback_error:
            logger.error(f"더미 provider도 실패: {fallback_error}")
            # 최종 fallback: 빈 리포트
            report = f"*📰 오전 리포트 - {today}*\n\n"
            report += f"*수집 시간:* {datetime_str}\n\n"
            report += "*⚠️ 뉴스 수집 실패*\n"
            report += f"오류: {str(e)}\n\n"
            report = append_disclaimer(report)
            return report
    
    if not news_items:
        report = f"*📰 오전 리포트 - {today}*\n\n"
        report += f"*수집 시간:* {datetime_str}\n\n"
        report += "*지난밤 주요 뉴스*\n"
        report += "수집된 뉴스가 없습니다.\n\n"
        report = append_disclaimer(report)
        return report
    
    # 3. 시간 필터링 (reports에서 적용)
    time_filtered_items, debug_info = filter_by_time_range(news_items, start_dt, end_dt)
    time_filtered_count = len(time_filtered_items)
    
    print(f"too_old_count={debug_info['too_old_count']} too_new_count={debug_info['too_new_count']} no_time_count={debug_info['no_time_count']}")
    logger.info(f"시간 필터 ({start_dt.strftime('%m/%d %H:%M')} ~ {end_dt.strftime('%m/%d %H:%M')}): {fetched_count}건 → {time_filtered_count}건")
    logger.info(f"탈락 이유: too_old={debug_info['too_old_count']}, too_new={debug_info['too_new_count']}, no_time={debug_info['no_time_count']}")
    
    if not time_filtered_items:
        report = f"*📰 오전 리포트 - {today}*\n\n"
        report += f"*수집 시간:* {datetime_str}\n"
        report += f"*기간:* {start_dt.strftime('%m/%d %H:%M')} ~ {end_dt.strftime('%m/%d %H:%M')} KST ({window_mode} 모드)\n"
        report += f"*수집:* {fetched_count}건 → 시간필터: {time_filtered_count}건\n\n"
        report += "해당 시간 범위에 뉴스가 없습니다.\n\n"
        report = append_disclaimer(report)
        return report
    
    # 4. published_at이 None인 항목을 정렬 시 아래로 보내기
    time_filtered_items.sort(
        key=lambda x: (x.published_at is None, x.published_at or datetime.min.replace(tzinfo=UTC)),
        reverse=True
    )
    
    # 5. 오버나이트 선행 신호 수집 (다이제스트 생성 전에)
    overnight_signals = None
    if OVERNIGHT_ENABLED:
        try:
            from datetime import date as date_class
            target_date = date_class.today()
            overnight_signals = fetch_overnight_signals(
                target_date=target_date,
                provider="yahoo",
                tickers=OVERNIGHT_TICKERS,
                debug=OVERNIGHT_DEBUG
            )
        except Exception as e:
            logger.warning(f"오버나이트 신호 수집 실패: {e}", exc_info=True)
    
    # 6. 다이제스트 생성 (오버나이트 신호 반영)
    digest = create_digest(
        time_filtered_items, 
        fetched_count=fetched_count,
        time_filtered_count=time_filtered_count,
        overnight_signals=overnight_signals
    )
    
    # 7. 섹터별 분배 수 로깅
    sector_counts = defaultdict(int)
    for item in time_filtered_items:
        from src.analysis.news_analyzer import classify_sector
        sector = classify_sector(item.title, item.content or "")
        sector_counts[sector] += 1
    
    logger.info(f"섹터별 분배: {dict(sector_counts)}")
    
    # 8. DB 저장 (향후 구현)
    # 실제로는 news, news_symbols 테이블에 저장
    # 나머지 링크는 DB에 저장만 하고 메시지에는 출력하지 않음
    
    # 9. 리포트 생성
    mode_label = "운영" if window_mode == "strict" else "개발"
    report = f"*📰 오전 리포트 - {today}*\n\n"
    report += f"*수집 시간:* {datetime_str}\n"
    report += f"*모드:* {window_mode}"
    if window_mode == "now" and lookback_hours:
        report += f" (lookback {lookback_hours}시간)"
    report += "\n"
    report += f"*기간:* {start_dt.strftime('%m/%d %H:%M')} ~ {end_dt.strftime('%m/%d %H:%M')} KST ({mode_label} 모드)\n"
    report += f"*수집:* {digest.fetched_count}건 → 시간필터: {digest.time_filtered_count}건 → 중복제거: {digest.deduped_count}건"
    
    # 개발 모드에서만 파싱 정보 표시
    if window_mode == "now":
        no_time_count = debug_info['no_time_count']
        report += f" (parsed_ok={parsed_ok_count}, parsed_fail={parsed_fail_count}, no_time={no_time_count})"
    report += "\n"
    
    # 개발 모드에서만 헤드라인 선정 방식 표시
    if window_mode == "now":
        report += "*헤드라인: 시장 관련도 점수 기반 선정*\n"
    report += "\n"
    
    # 핵심 헤드라인 (최대 8개)
    if digest.top_headlines:
        report += "*📌 핵심 헤드라인*\n"
        for i, headline in enumerate(digest.top_headlines[:8], 1):
            # 디버그 태그 추가
            tags = []
            if NEWS_DEBUG_TAGS and digest.headline_debug is not None:
                debug_info = digest.headline_debug.get(headline, {})
                if debug_info.get("freshness_score", 0) > 0.7:
                    tags.append("[FRESH]")
                if debug_info.get("repeat_penalty", 0) > 0.3:
                    tags.append("[REPEAT]")
                if debug_info.get("late_penalty", 0) > 0.2:
                    tags.append("[LATE?]")
            
            tag_str = " " + " ".join(tags) if tags else ""
            report += f"{i}. {headline}{tag_str}\n"
        report += "\n"
    
    # 거시 요약
    if digest.macro_summary:
        report += "*📊 거시 요약*\n"
        report += f"{digest.macro_summary}\n\n"
    
    # 오버나이트 선행 신호 (이미 수집됨)
    market_tone = None
    if OVERNIGHT_ENABLED and overnight_signals:
        market_tone = assess_market_tone(overnight_signals)
            
            if overnight_signals:
                report += "*📈 Overnight Signals*\n"
                # 성공한 신호만 표시
                successful_signals = [
                    (name, sig) for name, sig in overnight_signals.items()
                    if sig.success and sig.pct_change is not None
                ]
                
                if successful_signals:
                    # 중요도 순으로 정렬 (Nasdaq, S&P500, NVDA, BTC, USDKRW 등)
                    priority_order = ["Nasdaq", "S&P500", "NVDA", "BTC", "USDKRW", "US10Y", "EWY", "DXY"]
                    sorted_signals = sorted(
                        successful_signals,
                        key=lambda x: (
                            priority_order.index(x[0]) if x[0] in priority_order else 999,
                            -abs(x[1].pct_change or 0)  # 변동률 큰 순
                        )
                    )
                    
                    for name, sig in sorted_signals[:8]:  # 최대 8개
                        pct = sig.pct_change
                        emoji = "📈" if pct > 0 else "📉" if pct < 0 else "➖"
                        report += f"  {emoji} {name}: {pct:+.1f}%\n"
                    
                    # 시장 톤 요약
                    tone_emoji = {
                        "risk_on": "🟢",
                        "risk_off": "🔴",
                        "mixed": "🟡"
                    }
                    tone_label = {
                        "risk_on": "Risk On",
                        "risk_off": "Risk Off",
                        "mixed": "Mixed"
                    }
                    report += f"\n*오늘의 톤: {tone_emoji.get(market_tone, '⚪')} {tone_label.get(market_tone, 'Unknown')}*\n\n"
                else:
                    report += "  (신호 수집 실패)\n\n"
            else:
                if OVERNIGHT_DEBUG:
                    report += "*📈 Overnight Signals*\n"
                    report += "  (신호 수집 실패)\n\n"
        except Exception as e:
            logger.warning(f"오버나이트 신호 수집 실패: {e}", exc_info=True)
            if OVERNIGHT_DEBUG:
                report += "*📈 Overnight Signals*\n"
                report += f"  (오류: {str(e)})\n\n"
    
    # 섹터별 뉴스
    if digest.sector_bullets:
        report += "*🏷️ 섹터별 주요 뉴스*\n"
        for sector, bullets in list(digest.sector_bullets.items())[:5]:
            report += f"*{sector}*\n"
            for bullet in bullets[:2]:  # 섹터당 최대 2개
                report += f"  • {bullet}\n"
        report += "\n"
    
    # 한국장 영향도
    report += f"*🇰🇷 한국장 영향도: {digest.korea_impact}*\n\n"
    
    # 근거 링크 (최대 5개만)
    if digest.sources:
        report += "*🔗 근거 링크*\n"
        for i, url in enumerate(digest.sources[:5], 1):
            # URL을 짧게 표시 (도메인만)
            try:
                from urllib.parse import urlparse
                domain = urlparse(url).netloc
                display_url = domain if domain else url[:50]
            except:
                display_url = url[:50]
            report += f"{i}. [{display_url}]({url})\n"
        report += "\n"
    else:
        # 근거 링크가 없을 때도 로그 출력
        logger.warning("근거 링크가 없습니다 (sources가 비어있음)")
        # 리포트에는 표시하지 않음 (깔끔하게)
    
    # 9. 관찰 종목 선정 및 리포트 추가
    try:
        # LLM 사용 여부 로그
        if LLM_ENABLED:
            logger.info(f"LLM 사용: model={LLM_MODEL}")
            print(f"[LLM] 사용: model={LLM_MODEL}")
        else:
            logger.info("LLM 비활성화, 룰 기반 선정 사용")
            print("[LLM] 비활성화, 룰 기반 선정 사용")
        
        watch_stocks = pick_watch_stocks(
            digest, 
            time_filtered_items, 
            max_count=3, 
            date_str=today,
            overnight_signals=overnight_signals
        )
        
        if watch_stocks:
            report += "*👀 오늘의 관찰 리스트 (교육용 시뮬레이션)*\n\n"
            
            for idx, stock in enumerate(watch_stocks, 1):
                report += f"*{idx}. {stock.name} ({stock.code})*\n"
                report += f"*Thesis:* {stock.thesis}\n\n"
                
                # Catalyst
                report += "*Catalyst:*\n"
                for catalyst in stock.catalysts:
                    report += f"  • {catalyst}\n"
                report += "\n"
                
                # Risks
                report += "*Risk:*\n"
                for risk in stock.risks:
                    report += f"  • {risk}\n"
                report += "\n"
                
                # Trigger
                report += f"*관찰 트리거:* {stock.trigger}\n\n"
                
                # 체크리스트 점수
                report += "*체크리스트 점수:*\n"
                for item, score in stock.checklist_scores.items():
                    report += f"  • {item}: {score}/2점\n"
                report += f"*총점: {stock.total_score}/12점*\n\n"
                
                # 확신도
                report += f"*확신도: {stock.confidence} - {stock.confidence_reason}*\n\n"
                
                # DB 저장
                try:
                    symbol_id = upsert_symbol(stock.name, stock.code)
                    upsert_recommendation(
                        date=today,
                        symbol_id=symbol_id,
                        reason=stock.thesis,
                        priority=idx,
                        news_ids=None  # 향후 구현
                    )
                except Exception as e:
                    logger.warning(f"종목 {stock.name} DB 저장 실패: {e}")
            
            report += "※ 일부 점수는 재무데이터 연동 전 가정치입니다\n\n"
        else:
            logger.info("관찰 종목이 선정되지 않았습니다")
    
    except Exception as e:
        logger.error(f"관찰 종목 선정 중 오류: {e}", exc_info=True)
        # 오류가 있어도 리포트는 계속 진행
    
    # 면책 문구 추가
    report = append_disclaimer(report)
    
    return report
