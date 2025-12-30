"""PnL 계산 테스트"""
import sys
from pathlib import Path

# 프로젝트 루트를 경로에 추가
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.analysis.performance import calculate_paper_trade


def test_pnl_calculation():
    """PnL 계산 테스트"""
    
    # 테스트 케이스 1: 상승
    # entry=100, exit=110, cash=1000, N=1 -> qty=10, pnl=100
    result1 = calculate_paper_trade(
        symbol="TEST1",
        name="테스트1",
        entry_price=100,
        exit_price=110,
        per_stock_cash=1000
    )
    assert result1.quantity == 10, f"Expected qty=10, got {result1.quantity}"
    assert result1.invested_amount == 1000, f"Expected invested=1000, got {result1.invested_amount}"
    assert result1.current_value == 1100, f"Expected current=1100, got {result1.current_value}"
    assert result1.pnl == 100, f"Expected pnl=100, got {result1.pnl}"
    assert result1.pnl_rate == 10.0, f"Expected pnl_rate=10.0, got {result1.pnl_rate}"
    print("✓ 테스트 1 통과: 상승 케이스")
    
    # 테스트 케이스 2: 하락
    # entry=100, exit=90, cash=1000, N=1 -> qty=10, pnl=-100
    result2 = calculate_paper_trade(
        symbol="TEST2",
        name="테스트2",
        entry_price=100,
        exit_price=90,
        per_stock_cash=1000
    )
    assert result2.quantity == 10, f"Expected qty=10, got {result2.quantity}"
    assert result2.invested_amount == 1000, f"Expected invested=1000, got {result2.invested_amount}"
    assert result2.current_value == 900, f"Expected current=900, got {result2.current_value}"
    assert result2.pnl == -100, f"Expected pnl=-100, got {result2.pnl}"
    assert result2.pnl_rate == -10.0, f"Expected pnl_rate=-10.0, got {result2.pnl_rate}"
    print("✓ 테스트 2 통과: 하락 케이스")
    
    # 테스트 케이스 3: SK하이닉스 케이스
    # entry=587000, exit=590000, cash_per_stock=3333333 -> qty=5, pnl=15000
    result3 = calculate_paper_trade(
        symbol="000660",
        name="SK하이닉스",
        entry_price=587000,
        exit_price=590000,
        per_stock_cash=3333333
    )
    assert result3.quantity == 5, f"Expected qty=5, got {result3.quantity}"
    assert result3.invested_amount == 2935000, f"Expected invested=2935000, got {result3.invested_amount}"
    assert result3.current_value == 2950000, f"Expected current=2950000, got {result3.current_value}"
    assert result3.pnl == 15000, f"Expected pnl=15000, got {result3.pnl}"
    pnl_rate_expected = (15000 / 2935000) * 100
    assert abs(result3.pnl_rate - pnl_rate_expected) < 0.01, f"Expected pnl_rate≈{pnl_rate_expected}, got {result3.pnl_rate}"
    print("✓ 테스트 3 통과: SK하이닉스 케이스")
    
    print("\n모든 테스트 통과!")


if __name__ == "__main__":
    test_pnl_calculation()





