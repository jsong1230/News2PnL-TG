"""SQLite 데이터베이스 관리 모듈"""
import sqlite3
from pathlib import Path
from typing import Optional, List
from contextlib import contextmanager

from src.config import DB_PATH, SCHEMA_PATH


@contextmanager
def get_db_connection():
    """DB 연결 컨텍스트 매니저"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_schema():
    """스키마 초기화 (테이블 생성)"""
    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(f"스키마 파일을 찾을 수 없습니다: {SCHEMA_PATH}")
    
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema_sql = f.read()
    
    with get_db_connection() as conn:
        conn.executescript(schema_sql)
    
    print(f"✓ 스키마 초기화 완료: {DB_PATH}")


def ensure_db():
    """DB 파일 및 스키마 확인/생성"""
    # DB 디렉토리 생성
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    # DB 파일이 없거나 스키마가 없으면 초기화
    if not DB_PATH.exists():
        init_schema()
    else:
        # 스키마 확인 (간단히 symbols 테이블 존재 여부로 체크)
        with get_db_connection() as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='symbols'"
            )
            if not cursor.fetchone():
                init_schema()
            else:
                # 마이그레이션: paper_trades에 market_provider 컬럼 추가
                try:
                    cursor = conn.execute(
                        "SELECT market_provider FROM paper_trades LIMIT 1"
                    )
                    cursor.fetchone()
                except sqlite3.OperationalError:
                    # market_provider 컬럼이 없으면 추가
                    conn.execute(
                        "ALTER TABLE paper_trades ADD COLUMN market_provider TEXT DEFAULT 'unknown'"
                    )
                    conn.commit()
                    print("✓ paper_trades 테이블에 market_provider 컬럼 추가 완료")


def upsert_symbol(name: str, code: str, market: Optional[str] = None) -> int:
    """
    종목 정보 upsert (INSERT OR REPLACE)
    
    Args:
        name: 종목명
        code: 종목코드
        market: 시장 구분 (선택)
    
    Returns:
        symbol_id
    """
    with get_db_connection() as conn:
        cursor = conn.execute(
            """
            INSERT OR REPLACE INTO symbols (symbol, name, market, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (code, name, market)
        )
        # symbol_id 조회
        cursor = conn.execute(
            "SELECT id FROM symbols WHERE symbol = ?",
            (code,)
        )
        row = cursor.fetchone()
        return row["id"] if row else cursor.lastrowid


def upsert_recommendation(
    date: str,
    symbol_id: int,
    reason: str,
    priority: int,
    news_ids: Optional[List[int]] = None
) -> int:
    """
    추천 기록 upsert
    
    Args:
        date: 날짜 (YYYY-MM-DD)
        symbol_id: 종목 ID
        reason: 추천 이유
        priority: 우선순위 (1~3)
        news_ids: 관련 뉴스 ID 리스트 (선택)
    
    Returns:
        recommendation_id
    """
    import json
    
    news_ids_json = json.dumps(news_ids) if news_ids else None
    
    with get_db_connection() as conn:
        cursor = conn.execute(
            """
            INSERT OR REPLACE INTO recommendations 
            (date, symbol_id, reason, priority, news_ids, created_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (date, symbol_id, reason, priority, news_ids_json)
        )
        # recommendation_id 조회
        cursor = conn.execute(
            """
            SELECT id FROM recommendations 
            WHERE date = ? AND symbol_id = ?
            """,
            (date, symbol_id)
        )
        row = cursor.fetchone()
        return row["id"] if row else cursor.lastrowid


def get_recommendations_by_date(target_date: str) -> List[dict]:
    """
    특정 날짜의 추천 종목 조회
    
    Args:
        target_date: 날짜 (YYYY-MM-DD)
    
    Returns:
        추천 종목 리스트 [{id, symbol_id, symbol, name, reason, priority}]
    """
    with get_db_connection() as conn:
        cursor = conn.execute(
            """
            SELECT 
                r.id,
                r.symbol_id,
                r.reason,
                r.priority,
                s.symbol,
                s.name
            FROM recommendations r
            JOIN symbols s ON r.symbol_id = s.id
            WHERE r.date = ?
            ORDER BY r.priority ASC
            """,
            (target_date,)
        )
        rows = cursor.fetchall()
        return [
            {
                "id": row["id"],
                "symbol_id": row["symbol_id"],
                "symbol": row["symbol"],
                "name": row["name"],
                "reason": row["reason"],
                "priority": row["priority"]
            }
            for row in rows
        ]


def upsert_daily_price(
    symbol_id: int,
    date: str,
    open_price: float,
    high: float,
    low: float,
    close: float,
    volume: Optional[int] = None,
    change_rate: Optional[float] = None
) -> int:
    """
    일일 시세 저장
    
    Args:
        symbol_id: 종목 ID
        date: 날짜 (YYYY-MM-DD)
        open_price: 시가
        high: 고가
        low: 저가
        close: 종가
        volume: 거래량 (선택)
        change_rate: 등락률 (선택)
    
    Returns:
        daily_price_id
    """
    with get_db_connection() as conn:
        cursor = conn.execute(
            """
            INSERT OR REPLACE INTO daily_prices 
            (symbol_id, date, open, high, low, close, volume, change_rate, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (symbol_id, date, open_price, high, low, close, volume, change_rate)
        )
        cursor = conn.execute(
            """
            SELECT id FROM daily_prices 
            WHERE symbol_id = ? AND date = ?
            """,
            (symbol_id, date)
        )
        row = cursor.fetchone()
        return row["id"] if row else cursor.lastrowid


def upsert_paper_trade(
    date: str,
    symbol_id: int,
    recommendation_id: int,
    entry_date: str,
    entry_price: float,
    current_price: float,
    quantity: int,
    invested_amount: float,
    current_value: float,
    pnl: float,
    pnl_rate: float,
    market_provider: str = "unknown"
) -> int:
    """
    가정 투자 기록 저장
    
    Args:
        date: 날짜 (YYYY-MM-DD)
        symbol_id: 종목 ID
        recommendation_id: 추천 기록 ID
        entry_date: 진입일 (YYYY-MM-DD)
        entry_price: 진입가
        current_price: 현재가
        quantity: 수량
        invested_amount: 투자금액
        current_value: 현재 평가액
        pnl: 손익
        pnl_rate: 손익률 (%)
        market_provider: 시세 제공자 ('yahoo', 'dummy', 'unknown')
    
    Returns:
        paper_trade_id
    """
    with get_db_connection() as conn:
        cursor = conn.execute(
            """
            INSERT OR REPLACE INTO paper_trades 
            (date, symbol_id, recommendation_id, entry_date, entry_price, current_price,
             quantity, invested_amount, current_value, pnl, pnl_rate, market_provider, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (date, symbol_id, recommendation_id, entry_date, entry_price, current_price,
             quantity, invested_amount, current_value, pnl, pnl_rate, market_provider)
        )
        cursor = conn.execute(
            """
            SELECT id FROM paper_trades 
            WHERE date = ? AND symbol_id = ?
            """,
            (date, symbol_id)
        )
        row = cursor.fetchone()
        return row["id"] if row else cursor.lastrowid


def get_paper_trades_by_month(year: int, month: int, include_dummy: bool = False) -> List[dict]:
    """
    특정 월의 가정 투자 기록 조회
    
    Args:
        year: 연도
        month: 월 (1-12)
        include_dummy: dummy provider 거래 포함 여부 (기본: False, yahoo만)
    
    Returns:
        가정 투자 기록 리스트 [{date, symbol_id, symbol, name, pnl, pnl_rate, invested_amount, current_value, market_provider, ...}]
    """
    from calendar import monthrange
    _, last_day = monthrange(year, month)
    start_date = f"{year}-{month:02d}-01"
    end_date = f"{year}-{month:02d}-{last_day:02d}"
    
    with get_db_connection() as conn:
        if include_dummy:
            # 모든 provider 포함
            where_clause = "pt.date >= ? AND pt.date <= ?"
            params = (start_date, end_date)
        else:
            # yahoo만 포함
            where_clause = "pt.date >= ? AND pt.date <= ? AND pt.market_provider = 'yahoo'"
            params = (start_date, end_date)
        
        cursor = conn.execute(
            f"""
            SELECT 
                pt.date,
                pt.symbol_id,
                pt.recommendation_id,
                pt.entry_date,
                pt.entry_price,
                pt.current_price,
                pt.quantity,
                pt.invested_amount,
                pt.current_value,
                pt.pnl,
                pt.pnl_rate,
                COALESCE(pt.market_provider, 'unknown') as market_provider,
                s.symbol,
                s.name
            FROM paper_trades pt
            JOIN symbols s ON pt.symbol_id = s.id
            WHERE {where_clause}
            ORDER BY pt.date ASC, pt.symbol_id ASC
            """,
            params
        )
        rows = cursor.fetchall()
        return [
            {
                "date": row["date"],
                "symbol_id": row["symbol_id"],
                "symbol": row["symbol"],
                "name": row["name"],
                "recommendation_id": row["recommendation_id"],
                "entry_date": row["entry_date"],
                "entry_price": row["entry_price"],
                "current_price": row["current_price"],
                "quantity": row["quantity"],
                "invested_amount": row["invested_amount"],
                "current_value": row["current_value"],
                "pnl": row["pnl"],
                "pnl_rate": row["pnl_rate"],
                "market_provider": row["market_provider"]
            }
            for row in rows
        ]

