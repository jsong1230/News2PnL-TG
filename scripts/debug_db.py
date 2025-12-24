#!/usr/bin/env python3
"""DB 디버그 스크립트 - paper_trades의 market_provider 확인"""
import sys
from pathlib import Path

# 프로젝트 루트를 경로에 추가
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.database import get_db_connection
from src.utils.date_utils import get_kst_date


def main():
    """오늘 날짜의 paper_trades 조회"""
    today = get_kst_date()
    
    with get_db_connection() as conn:
        cursor = conn.execute(
            """
            SELECT 
                pt.date,
                pt.symbol_id,
                pt.market_provider,
                pt.pnl,
                pt.pnl_rate,
                s.symbol,
                s.name
            FROM paper_trades pt
            JOIN symbols s ON pt.symbol_id = s.id
            WHERE pt.date = ?
            ORDER BY pt.id DESC
            LIMIT 10
            """,
            (today,)
        )
        rows = cursor.fetchall()
        
        if not rows:
            print(f"오늘({today}) 거래 기록이 없습니다.")
            return
        
        print(f"오늘({today}) paper_trades 기록 (최근 {len(rows)}건):\n")
        print(f"{'날짜':<12} {'종목코드':<10} {'종목명':<20} {'provider':<15} {'손익':<15} {'손익률':<10}")
        print("-" * 90)
        
        for row in rows:
            date = row["date"]
            symbol = row["symbol"]
            name = row["name"]
            provider = row["market_provider"] if "market_provider" in row.keys() else "NULL"
            if provider is None:
                provider = "NULL"
            pnl = row["pnl"]
            pnl_rate = row["pnl_rate"]
            
            print(f"{date:<12} {symbol:<10} {name:<20} {provider:<15} {pnl:>+12,.0f}원 {pnl_rate:>+7.2f}%")
        
        # provider별 통계
        cursor = conn.execute(
            """
            SELECT 
                COALESCE(market_provider, 'NULL') as provider,
                COUNT(*) as count
            FROM paper_trades
            WHERE date = ?
            GROUP BY provider
            """,
            (today,)
        )
        stats = cursor.fetchall()
        
        print("\n[Provider별 통계]")
        for stat in stats:
            print(f"  {stat['provider']}: {stat['count']}건")


if __name__ == "__main__":
    main()

