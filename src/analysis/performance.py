"""성과 분석 모듈"""
from typing import List, Optional
from dataclasses import dataclass


@dataclass
class TradeResult:
    """거래 결과"""
    symbol: str
    name: str
    entry_price: float
    current_price: float
    quantity: int
    invested_amount: float
    current_value: float
    pnl: float
    pnl_rate: float  # 손익률 (%)


@dataclass
class PerformanceMetrics:
    """성과 지표"""
    total_invested: float
    total_value: float
    total_pnl: float
    total_pnl_rate: float
    win_rate: float  # 승률 (%)
    win_count: int
    loss_count: int
    mdd: float  # Maximum Drawdown (%)


def calculate_paper_trade(
    symbol: str,
    name: str,
    entry_price: float,
    exit_price: float,
    per_stock_cash: float
) -> TradeResult:
    """
    가정 투자 수익 계산
    
    Args:
        symbol: 종목코드
        name: 종목명
        entry_price: 진입가 (시가)
        exit_price: 청산가 (종가)
        per_stock_cash: 종목당 할당 현금
    
    Returns:
        거래 결과
    """
    # 수량 계산 (floor)
    quantity = int(per_stock_cash / entry_price)
    
    # 실제 투자 금액 = 수량 * 진입가
    invested_amount = quantity * entry_price
    
    # 현재 평가액 = 수량 * 청산가
    current_value = quantity * exit_price
    
    # 손익 = 현재 평가액 - 투자 금액
    pnl = current_value - invested_amount
    
    # 손익률 = 손익 / 투자 금액 (투자 금액 > 0일 때)
    pnl_rate = (pnl / invested_amount) * 100 if invested_amount > 0 else 0.0
    
    return TradeResult(
        symbol=symbol,
        name=name,
        entry_price=entry_price,
        current_price=exit_price,  # 호환성을 위해 current_price로 저장
        quantity=quantity,
        invested_amount=invested_amount,
        current_value=current_value,
        pnl=pnl,
        pnl_rate=round(pnl_rate, 2)
    )


def calculate_performance_metrics(trade_results: List[TradeResult]) -> PerformanceMetrics:
    """
    성과 지표 계산
    
    Args:
        trade_results: 거래 결과 리스트
    
    Returns:
        성과 지표
    """
    if not trade_results:
        return PerformanceMetrics(
            total_invested=0.0,
            total_value=0.0,
            total_pnl=0.0,
            total_pnl_rate=0.0,
            win_rate=0.0,
            win_count=0,
            loss_count=0,
            mdd=0.0
        )
    
    total_invested = sum(t.invested_amount for t in trade_results)
    total_value = sum(t.current_value for t in trade_results)
    total_pnl = total_value - total_invested
    total_pnl_rate = (total_pnl / total_invested) * 100 if total_invested > 0 else 0.0
    
    win_count = sum(1 for t in trade_results if t.pnl > 0)
    loss_count = sum(1 for t in trade_results if t.pnl < 0)
    win_rate = (win_count / len(trade_results)) * 100 if trade_results else 0.0
    
    # MDD 계산 (간단한 버전)
    max_drawdown = min((t.pnl_rate for t in trade_results), default=0.0)
    mdd = abs(max_drawdown) if max_drawdown < 0 else 0.0
    
    return PerformanceMetrics(
        total_invested=round(total_invested, 2),
        total_value=round(total_value, 2),
        total_pnl=round(total_pnl, 2),
        total_pnl_rate=round(total_pnl_rate, 2),
        win_rate=round(win_rate, 2),
        win_count=win_count,
        loss_count=loss_count,
        mdd=round(mdd, 2)
    )


def calculate_mdd(prices: List[float]) -> float:
    """
    Maximum Drawdown 계산
    
    Args:
        prices: 가격 리스트 (시간순)
    
    Returns:
        MDD (%)
    """
    if not prices or len(prices) < 2:
        return 0.0
    
    peak = prices[0]
    max_drawdown = 0.0
    
    for price in prices[1:]:
        if price > peak:
            peak = price
        drawdown = ((peak - price) / peak) * 100
        if drawdown > max_drawdown:
            max_drawdown = drawdown
    
    return round(max_drawdown, 2)

