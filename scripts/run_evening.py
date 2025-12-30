#!/usr/bin/env python3
"""오후 리포트 실행 스크립트"""
import sys
import traceback
from pathlib import Path

# 프로젝트 루트를 경로에 추가 (어디서 실행해도 동작하도록)
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.config import validate_config, MARKET_PROVIDER, TELEGRAM_REQUIRED
from src.database import ensure_db
from src.reports.evening import generate_evening_report
from src.telegram import send_message, send_error_notification
from src.market.provider import get_market_provider
from src.utils.logging import setup_logging, track_performance, PerformanceTracker


def main():
    """메인 실행 함수"""
    try:
        # 1. 로깅 초기화 및 설정 검증
        setup_logging()
        validate_config()
        
        # 2. DB 연결/초기화
        ensure_db()
        
        # 3. Market Provider 정보 출력 (디버그)
        print(f"[MARKET_PROVIDER]={MARKET_PROVIDER}")
        try:
            provider = get_market_provider(MARKET_PROVIDER)
            print(f"Provider 타입: {type(provider).__name__}")
        except Exception as e:
            print(f"Provider 초기화 실패: {e}")
        
        # 4. 리포트 생성
        with track_performance("generate_evening_report"):
            report = generate_evening_report()
        
        # 5. 저장된 거래 확인 (디버그)
        from src.database import get_db_connection
        from src.utils.date_utils import get_kst_date
        today = get_kst_date()
        with get_db_connection() as conn:
            cursor = conn.execute(
                """
                SELECT 
                    pt.market_provider,
                    COUNT(*) as count
                FROM paper_trades pt
                WHERE pt.date = ?
                GROUP BY pt.market_provider
                """,
                (today,)
            )
            stats = cursor.fetchall()
            if stats:
                print(f"\n[오늘 저장된 거래 provider 통계]")
                for stat in stats:
                    provider = stat["market_provider"] or "NULL"
                    print(f"  {provider}: {stat['count']}건")
        
        # 6. 텔레그램 전송
        with track_performance("send_telegram"):
            success = send_message(report)
        
        # 7. 성능 요약 출력
        print(PerformanceTracker().get_summary())
        
        if success:
            print("✓ 오후 리포트 전송 완료")
        else:
            print("✗ 오후 리포트 전송 실패")
            if TELEGRAM_REQUIRED:
                sys.exit(1)
            else:
                print("⚠️  TELEGRAM_REQUIRED=false이므로 워크플로우는 계속 진행됩니다.")
    
    except Exception as e:
        error_msg = f"오후 리포트 생성 중 오류 발생: {e}\n{traceback.format_exc()}"
        print(error_msg)
        
        # 에러 알림 전송
        send_error_notification(e, "오후 리포트 생성")
        
        sys.exit(1)


if __name__ == "__main__":
    main()

