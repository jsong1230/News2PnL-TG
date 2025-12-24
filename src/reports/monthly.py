"""월간 리포트 생성 모듈"""
from typing import Optional
import logging

from src.database import get_db_connection, get_paper_trades_by_month
from src.analysis.monthly_summary import aggregate_monthly_trades, MonthlySummary
from src.utils.disclaimer import append_disclaimer
from src.utils.date_utils import get_kst_now, get_month_range, get_current_month_range
from src.config import MONTH_OVERRIDE, MONTHLY_INCLUDE_DUMMY

logger = logging.getLogger(__name__)


def generate_monthly_report() -> str:
    """
    월간 리포트 생성
    
    Returns:
        리포트 메시지 (Markdown 형식)
    """
    # 월 범위 결정
    if MONTH_OVERRIDE:
        # MONTH_OVERRIDE가 있으면 해당 월 사용
        try:
            year, month = map(int, MONTH_OVERRIDE.split("-"))
            start_dt, end_dt = get_month_range(year, month)
            month_str = f"{year}-{month:02d}"
        except ValueError:
            logger.error(f"잘못된 MONTH_OVERRIDE 형식: {MONTH_OVERRIDE}, 현재 월 사용")
            start_dt, end_dt = get_current_month_range()
            now = get_kst_now()
            month_str = f"{now.year}-{now.month:02d}"
    else:
        # 기본: 현재 월
        start_dt, end_dt = get_current_month_range()
        now = get_kst_now()
        month_str = f"{now.year}-{now.month:02d}"
    
    year, month = int(month_str.split("-")[0]), int(month_str.split("-")[1])
    
    # DB에서 월간 데이터 조회 (전체 거래 수 확인용)
    all_trades = get_paper_trades_by_month(year, month, include_dummy=True)
    # 필터링된 거래 (기본: yahoo만)
    trades = get_paper_trades_by_month(year, month, include_dummy=MONTHLY_INCLUDE_DUMMY)
    
    # provider별 거래 수 계산
    provider_counts = {}
    for trade in all_trades:
        provider = trade.get("market_provider", "unknown")
        provider_counts[provider] = provider_counts.get(provider, 0) + 1
    
    # yahoo 거래 수 확인
    yahoo_count = len([t for t in all_trades if t.get("market_provider") == "yahoo"])
    
    if not trades:
        report = f"*📅 월간 성적표 - {month_str}*\n\n"
        report += "이번 달 데이터가 없습니다.\n"
        if all_trades:
            report += f"(전체 거래: {len(all_trades)}건, yahoo 거래: {yahoo_count}건)\n"
            if yahoo_count == 0:
                report += "\n⚠️ *yahoo 거래가 없어 신뢰할 수 있는 집계가 불가능합니다.*\n"
                report += "MARKET_PROVIDER=yahoo로 evening 리포트를 실행하여 실제 시세 기반 거래를 생성하세요.\n"
        report += "\n"
        report = append_disclaimer(report)
        return report
    
    # yahoo 거래가 0건인 경우 경고 추가 (trades가 있지만 yahoo가 아닌 경우)
    if yahoo_count == 0 and not MONTHLY_INCLUDE_DUMMY:
        report = f"*📅 월간 성적표 - {month_str}*\n\n"
        report += "⚠️ *yahoo 거래가 없어 신뢰할 수 있는 집계가 불가능합니다.*\n"
        report += f"(전체 거래: {len(all_trades)}건, yahoo 거래: 0건)\n"
        report += "MARKET_PROVIDER=yahoo로 evening 리포트를 실행하여 실제 시세 기반 거래를 생성하세요.\n\n"
        report = append_disclaimer(report)
        return report
    
    # 월간 집계
    summary = aggregate_monthly_trades(trades)
    
    # 거래 수 정보 생성
    trade_count_info = f"집계 대상 거래수: {len(trades)}"
    if len(all_trades) > len(trades):
        excluded = len(all_trades) - len(trades)
        provider_detail = ", ".join([f"{k}={v}" for k, v in sorted(provider_counts.items())])
        trade_count_info += f" (전체={len(all_trades)}, 제외={excluded}, {provider_detail})"
    else:
        # 모든 거래가 포함된 경우
        provider_detail = ", ".join([f"{k}={v}" for k, v in sorted(provider_counts.items())])
        if provider_detail:
            trade_count_info += f" ({provider_detail})"
    
    # 리포트 생성
    report = f"*📅 월간 성적표 - {month_str}*\n\n"
    
    # 요약
    report += "*[요약]*\n"
    report += f"  · 총 손익: {summary.month_pnl:+,.0f}원 ({summary.month_return:+.2f}%)\n"
    
    # 승률 표시: win승 loss패 draw무
    win_loss_draw = f"{summary.win_count}승 {summary.loss_count}패"
    if summary.draw_count > 0:
        win_loss_draw += f" {summary.draw_count}무"
    report += f"  · 승률: {summary.win_rate:.1f}% ({win_loss_draw})\n"
    
    # MDD 표시
    if summary.mdd is not None:
        report += f"  · 최대낙폭(MDD): -{summary.mdd:.2f}% (-{summary.mdd_amount:,.0f}원)\n"
    else:
        report += f"  · 최대낙폭(MDD): N/A (표본 부족)\n"
    
    report += f"  · {trade_count_info}\n\n"
    
    # 일별 하이라이트
    if summary.best_day and summary.worst_day:
        report += "*[일별 하이라이트]*\n"
        if summary.best_day.date == summary.worst_day.date:
            report += f"  · 이번 달 데이터가 1일뿐: {summary.best_day.date} {summary.best_day.day_pnl:+,.0f}원 ({summary.best_day.day_return:+.2f}%)\n"
        else:
            report += f"  · 베스트 데이: {summary.best_day.date} {summary.best_day.day_pnl:+,.0f}원 ({summary.best_day.day_return:+.2f}%)\n"
            report += f"  · 워스트 데이: {summary.worst_day.date} {summary.worst_day.day_pnl:+,.0f}원 ({summary.worst_day.day_return:+.2f}%)\n"
        report += "\n"
    
    # 종목 하이라이트
    if summary.best_stock or summary.worst_stock:
        report += "*[종목 하이라이트]*\n"
        if summary.best_stock:
            report += f"  · 베스트 종목: {summary.best_stock['name']} ({summary.best_stock['symbol']}) {summary.best_stock['pnl']:+,.0f}원 ({summary.best_stock['pnl_rate']:+.2f}%)\n"
        if summary.worst_stock:
            report += f"  · 워스트 종목: {summary.worst_stock['name']} ({summary.worst_stock['symbol']}) {summary.worst_stock['pnl']:+,.0f}원 ({summary.worst_stock['pnl_rate']:+.2f}%)\n"
        report += "\n"
    
    # 코멘트
    report += "*[코멘트]*\n"
    comment = generate_monthly_comment(summary)
    report += f"{comment}\n\n"
    
    # 면책 문구 추가
    report = append_disclaimer(report)
    
    return report


def generate_monthly_comment(summary: MonthlySummary) -> str:
    """
    월간 관찰 코멘트 생성
    
    Args:
        summary: 월간 집계
    
    Returns:
        코멘트 텍스트
    """
    comments = []
    
    # 월간 관찰의 한 줄 회고
    if summary.month_return > 5.0:
        review = "월간 수익률이 양호했으나, 변동성 관리가 필요"
    elif summary.month_return > 0:
        review = "월간 소폭 수익, 개별 종목 선택의 중요성 확인"
    elif summary.month_return > -5.0:
        review = "월간 소폭 손실, 진입 타이밍과 리스크 관리 재검토 필요"
    else:
        review = "월간 손실 발생, 시장 환경과 관찰 기준 재점검 필요"
    
    comments.append(f"• {review}")
    
    # 다음 달 개선 포인트
    if summary.win_rate < 50:
        comments.append("• 승률 개선: 노이즈 필터 강화 및 섹터 분산 고려")
    
    if summary.mdd is not None:
        if summary.mdd > 10:
            comments.append("• MDD 관리: 손절 기준 명확화 및 포지션 크기 조정")
        elif summary.mdd > 5:
            comments.append("• 변동성 관리: 리스크 관리 강화")
    
    if not comments:
        comments.append("• 지속적인 관찰과 데이터 축적")
        comments.append("• 섹터별 성과 패턴 분석")
    
    return "\n".join(comments)
