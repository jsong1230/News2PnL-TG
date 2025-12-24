"""오후 리포트 생성 모듈"""
from typing import List, Optional
import logging

from src.config import MARKET_PROVIDER, PAPER_TRADE_AMOUNT
from src.market.provider import get_market_provider, DummyMarketProvider
from src.market.base import OHLC
from src.analysis.performance import calculate_paper_trade, calculate_performance_metrics, TradeResult
from src.database import (
    get_db_connection,
    get_recommendations_by_date,
    upsert_daily_price,
    upsert_paper_trade
)
from src.utils.disclaimer import append_disclaimer
from src.utils.date_utils import get_kst_date

logger = logging.getLogger(__name__)


def generate_evening_report() -> str:
    """
    오후 리포트 생성 (recommendations 테이블 기반)
    
    Returns:
        리포트 메시지 (Markdown 형식)
    """
    today = get_kst_date()
    
    # 1. 오늘 추천 종목 조회
    recommendations = get_recommendations_by_date(today)
    
    if not recommendations:
        report = f"*📊 오후 리포트 - {today}*\n\n"
        report += "오늘 관찰 종목이 없습니다.\n\n"
        report = append_disclaimer(report)
        return report
    
    # 2. 시세 조회 및 PnL 계산
    market_provider = get_market_provider(MARKET_PROVIDER)
    trade_results: List[TradeResult] = []
    failed_symbols: List[str] = []
    
    # 동일비중 계산
    amount_per_stock = PAPER_TRADE_AMOUNT / len(recommendations)
    
    for rec in recommendations:
        symbol_code = rec["symbol"]
        symbol_id = rec["symbol_id"]
        symbol_name = rec["name"]
        recommendation_id = rec["id"]
        
        try:
            # 시세 조회
            ohlc = market_provider.get_ohlc(symbol_code)
            
            # 진입가 = 시가, 청산가 = 종가
            entry_price = ohlc.open
            exit_price = ohlc.close
            
            # PnL 계산
            trade_result = calculate_paper_trade(
                symbol=symbol_code,
                name=symbol_name,
                entry_price=entry_price,
                exit_price=exit_price,
                per_stock_cash=amount_per_stock
            )
            
            # 디버그 로그
            print(f"종목 {symbol_name} ({symbol_code}): qty={trade_result.quantity}, invested={trade_result.invested_amount:.0f}, current={trade_result.current_value:.0f}, pnl={trade_result.pnl:+.0f}")
            trade_results.append(trade_result)
            
            # DB 저장: daily_prices
            upsert_daily_price(
                symbol_id=symbol_id,
                date=today,
                open_price=ohlc.open,
                high=ohlc.high,
                low=ohlc.low,
                close=ohlc.close,
                volume=ohlc.volume,
                change_rate=ohlc.change_rate
            )
            
            # DB 저장: paper_trades
            upsert_paper_trade(
                date=today,
                symbol_id=symbol_id,
                recommendation_id=recommendation_id,
                entry_date=today,
                entry_price=entry_price,
                current_price=exit_price,
                quantity=trade_result.quantity,
                invested_amount=trade_result.invested_amount,
                current_value=trade_result.current_value,
                pnl=trade_result.pnl,
                pnl_rate=trade_result.pnl_rate,
                market_provider=MARKET_PROVIDER
            )
            logger.info(f"저장된 trade provider={MARKET_PROVIDER}, symbol={symbol_code}, pnl={trade_result.pnl:+.0f}원")
            print(f"✓ 저장된 trade provider={MARKET_PROVIDER}, symbol={symbol_code}, pnl={trade_result.pnl:+.0f}원")
        
        except ValueError as e:
            # 시세 조회 실패 또는 데이터 오류
            logger.warning(f"종목 {symbol_name} ({symbol_code}) 시세 조회 실패: {e}")
            failed_symbols.append(f"{symbol_name} ({symbol_code}) - {str(e)}")
            continue
        except Exception as e:
            logger.warning(f"종목 {symbol_name} ({symbol_code}) 처리 중 오류: {e}")
            failed_symbols.append(f"{symbol_name} ({symbol_code}) - 조회 실패")
            continue
    
    # 시세 조회 실패한 종목이 모두인 경우
    if not trade_results:
        report = f"*📊 오후 리포트 - {today}*\n\n"
        report += "오늘은 시세 데이터 확보 실패로 성과 계산 불가\n\n"
        if failed_symbols:
            report += "*실패한 종목:*\n"
            for failed in failed_symbols:
                report += f"  · {failed}\n"
            report += "\n"
        report = append_disclaimer(report)
        return report
    
    # 3. 성과 계산
    metrics = calculate_performance_metrics(trade_results)
    
    # 4. 리포트 생성
    report = f"*📊 오후 리포트 - {today}*\n\n"
    report += f"*가정 투자: {PAPER_TRADE_AMOUNT:,}원 (동일비중)*\n\n"
    
    # 종목별 결과
    report += "*[종목별 결과]*\n"
    for tr in trade_results:
        # 이모지 결정
        if tr.pnl > 0:
            pnl_emoji = "📈"
        elif tr.pnl < 0:
            pnl_emoji = "📉"
        else:
            pnl_emoji = "➖"
        
        report += f"{pnl_emoji} *{tr.name}* ({tr.symbol})\n"
        report += f"  · 시가: {tr.entry_price:,.0f}원 / 종가: {tr.current_price:,.0f}원\n"
        report += f"  · 수량: {tr.quantity:,}주\n"
        report += f"  · 손익: {tr.pnl:+,.0f}원 ({tr.pnl_rate:+.2f}%)\n"
        
        # 개발 모드에서만 상세 정보 표시
        from src.config import NEWS_WINDOW_MODE
        if NEWS_WINDOW_MODE == "now":
            report += f"  · 투자금액: {tr.invested_amount:,.0f}원 / 평가액: {tr.current_value:,.0f}원\n"
        
        report += "\n"
    
    # 실패한 종목 표시
    if failed_symbols:
        report += "*데이터 없음 (조회 실패):*\n"
        for failed in failed_symbols:
            report += f"  · {failed}\n"
        report += "\n"
    
    # 전체 요약
    report += "*[전체 요약]*\n"
    report += f"  · 총 투자금: {metrics.total_invested:,.0f}원\n"
    report += f"  · 현재 평가액: {metrics.total_value:,.0f}원\n"
    report += f"  · 총 손익: {metrics.total_pnl:+,.0f}원 ({metrics.total_pnl_rate:+.2f}%)\n"
    report += f"  · 승률: {metrics.win_rate:.1f}% ({metrics.win_count}승 {metrics.loss_count}패)\n\n"
    
    # 한 줄 회고
    report += "*[한 줄 회고]*\n"
    review = generate_review(trade_results, metrics)
    report += f"{review}\n\n"
    
    # 면책 문구 추가
    report = append_disclaimer(report)
    
    return report


def generate_review(trade_results: List[TradeResult], metrics: 'PerformanceMetrics') -> str:
    """
    한 줄 회고 생성
    
    Args:
        trade_results: 거래 결과 리스트
        metrics: 성과 지표
    
    Returns:
        회고 텍스트
    """
    if not trade_results:
        return "관찰 종목이 없어 회고할 내용이 없습니다."
    
    # 종목명 리스트
    names = [tr.name for tr in trade_results]
    
    # 전체 톤 판단
    if metrics.total_pnl_rate > 1.0:
        tone = "긍정적"
    elif metrics.total_pnl_rate < -1.0:
        tone = "신중"
    else:
        tone = "중립"
    
    # 섹터 추정 (종목명 기반)
    sectors = []
    for name in names:
        if "반도체" in name or name in ["삼성전자", "SK하이닉스"]:
            sectors.append("반도체")
        elif "2차전지" in name or "배터리" in name or "에너지" in name:
            sectors.append("2차전지")
        elif "바이오" in name or "제약" in name:
            sectors.append("바이오")
    
    sector_text = ", ".join(set(sectors)) if sectors else "관찰 종목"
    
    # 회고 텍스트 생성 (단정 금지, 관찰 결과 중심)
    if metrics.win_rate >= 66.7:
        review = f"뉴스 기반 {sector_text} 관찰은 단기 모멘텀 확인, 변동성은 여전히 큼"
    elif metrics.win_rate >= 33.3:
        review = f"{sector_text} 관찰 결과 혼조세, 개별 종목 변동성 확인 필요"
    else:
        review = f"{sector_text} 관찰 결과 하락세, 시장 환경 재검토 필요"
    
    # 다음날 관찰 포인트 추가
    if metrics.total_pnl_rate > 0:
        review += " | 다음날 상승 지속 여부 관찰"
    else:
        review += " | 다음날 반등 여부 관찰"
    
    return review
