"""월간 성과 집계 모듈"""
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from collections import defaultdict
from datetime import date


@dataclass
class DaySummary:
    """일자별 집계"""
    date: str  # YYYY-MM-DD
    day_pnl: float
    day_invested: float
    day_return: float  # %
    trade_count: int


@dataclass
class MonthlySummary:
    """월간 집계"""
    year: int
    month: int
    month_pnl: float
    month_invested: float
    month_return: float  # %
    win_rate: float  # % (win/(win+loss), 무는 제외)
    win_count: int
    loss_count: int
    draw_count: int
    total_count: int
    mdd: Optional[float]  # % (None if 표본 부족)
    mdd_amount: float  # 원
    best_day: Optional[DaySummary]
    worst_day: Optional[DaySummary]
    best_stock: Optional[Dict]  # {name, symbol, pnl, pnl_rate}
    worst_stock: Optional[Dict]  # {name, symbol, pnl, pnl_rate}


def aggregate_daily_trades(trades: List[Dict]) -> List[DaySummary]:
    """
    일자별 집계
    
    Args:
        trades: 가정 투자 기록 리스트
    
    Returns:
        일자별 집계 리스트
    """
    daily = defaultdict(lambda: {"pnl": 0.0, "invested": 0.0, "count": 0})
    
    for trade in trades:
        trade_date = trade["date"]
        daily[trade_date]["pnl"] += trade["pnl"]
        daily[trade_date]["invested"] += trade["invested_amount"]
        daily[trade_date]["count"] += 1
    
    day_summaries = []
    for trade_date in sorted(daily.keys()):
        day_data = daily[trade_date]
        day_return = (day_data["pnl"] / day_data["invested"]) * 100 if day_data["invested"] > 0 else 0.0
        
        day_summaries.append(DaySummary(
            date=trade_date,
            day_pnl=round(day_data["pnl"], 2),
            day_invested=round(day_data["invested"], 2),
            day_return=round(day_return, 2),
            trade_count=day_data["count"]
        ))
    
    return day_summaries


def aggregate_monthly_trades(trades: List[Dict]) -> MonthlySummary:
    """
    월간 집계
    
    Args:
        trades: 가정 투자 기록 리스트
    
    Returns:
        월간 집계
    """
    if not trades:
        # 첫 번째 trade에서 연월 추출 시도
        if trades:
            first_date = date.fromisoformat(trades[0]["date"])
            year, month = first_date.year, first_date.month
        else:
            from src.utils.date_utils import get_kst_now
            now = get_kst_now()
            year, month = now.year, now.month
        
        return MonthlySummary(
            year=year,
            month=month,
            month_pnl=0.0,
            month_invested=0.0,
            month_return=0.0,
            win_rate=0.0,
            win_count=0,
            loss_count=0,
            draw_count=0,
            total_count=0,
            mdd=None,
            mdd_amount=0.0,
            best_day=None,
            worst_day=None,
            best_stock=None,
            worst_stock=None
        )
    
    # 첫 번째 trade에서 연월 추출
    first_date = date.fromisoformat(trades[0]["date"])
    year, month = first_date.year, first_date.month
    
    # 일자별 집계
    day_summaries = aggregate_daily_trades(trades)
    
    # 월간 합계
    month_pnl = sum(d.day_pnl for d in day_summaries)
    month_invested = sum(d.day_invested for d in day_summaries)
    month_return = (month_pnl / month_invested) * 100 if month_invested > 0 else 0.0
    
    # 승/패/무 카운트
    win_count = sum(1 for t in trades if t["pnl"] > 0)
    loss_count = sum(1 for t in trades if t["pnl"] < 0)
    draw_count = sum(1 for t in trades if t["pnl"] == 0)
    total_count = len(trades)
    
    # 승률 계산: win/(win+loss) (무는 제외)
    win_loss_total = win_count + loss_count
    win_rate = (win_count / win_loss_total) * 100 if win_loss_total > 0 else 0.0
    
    # 베스트/워스트 데이
    best_day = max(day_summaries, key=lambda d: d.day_pnl) if day_summaries else None
    worst_day = min(day_summaries, key=lambda d: d.day_pnl) if day_summaries else None
    
    # 베스트/워스트 종목
    best_stock = max(trades, key=lambda t: t["pnl"]) if trades else None
    worst_stock = min(trades, key=lambda t: t["pnl"]) if trades else None
    
    if best_stock:
        best_stock = {
            "name": best_stock["name"],
            "symbol": best_stock["symbol"],
            "pnl": best_stock["pnl"],
            "pnl_rate": best_stock["pnl_rate"]
        }
    
    if worst_stock:
        worst_stock = {
            "name": worst_stock["name"],
            "symbol": worst_stock["symbol"],
            "pnl": worst_stock["pnl"],
            "pnl_rate": worst_stock["pnl_rate"]
        }
    
    # MDD 계산 (equity curve 기반)
    # 표본이 2일 미만이면 MDD 계산 불가
    mdd = None
    mdd_amount = 0.0
    
    if len(day_summaries) >= 2:
        # 일자별 equity 계산
        from src.config import PAPER_TRADE_AMOUNT
        
        # base_cash는 월간 기준값 (PAPER_TRADE_AMOUNT 사용, 없으면 day_invested 누적으로 대체)
        base_cash = PAPER_TRADE_AMOUNT if PAPER_TRADE_AMOUNT > 0 else month_invested
        
        equity_curve = []
        cumulative_pnl = 0.0
        cumulative_invested = 0.0
        
        for day_sum in day_summaries:
            cumulative_pnl += day_sum.day_pnl
            cumulative_invested += day_sum.day_invested
            
            # equity = base_cash + cumulative_pnl
            # base_cash가 없으면 cumulative_invested를 기준으로 사용
            if base_cash > 0:
                equity = base_cash + cumulative_pnl
            else:
                # base_cash가 없으면 첫날 invested를 기준으로 사용
                if not equity_curve:
                    equity = cumulative_invested + cumulative_pnl
                else:
                    equity = equity_curve[0] + cumulative_pnl
            
            equity_curve.append(equity)
        
        # MDD 계산 (equity 기준)
        mdd_pct = 0.0
        
        if equity_curve:
            peak_equity = equity_curve[0]
            for equity in equity_curve:
                if equity > peak_equity:
                    peak_equity = equity
                
                # drawdown = (equity - peak_equity) / peak_equity
                if peak_equity > 0:
                    drawdown = peak_equity - equity
                    drawdown_pct = (drawdown / peak_equity) * 100
                    
                    if drawdown > mdd_amount:
                        mdd_amount = drawdown
                    if drawdown_pct > mdd_pct:
                        mdd_pct = drawdown_pct
        
        # MDD는 % 기준으로 사용 (원 단위도 저장)
        mdd = mdd_pct
    
    return MonthlySummary(
        year=year,
        month=month,
        month_pnl=round(month_pnl, 2),
        month_invested=round(month_invested, 2),
        month_return=round(month_return, 2),
        win_rate=round(win_rate, 2),
        win_count=win_count,
        loss_count=loss_count,
        draw_count=draw_count,
        total_count=total_count,
        mdd=round(mdd, 2) if mdd is not None else None,
        mdd_amount=round(mdd_amount, 2),
        best_day=best_day,
        worst_day=worst_day,
        best_stock=best_stock,
        worst_stock=worst_stock
    )

