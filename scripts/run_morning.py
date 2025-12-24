#!/usr/bin/env python3
"""오전 리포트 실행 스크립트"""
import sys
import traceback
from pathlib import Path

# 프로젝트 루트를 경로에 추가 (어디서 실행해도 동작하도록)
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.config import validate_config, NEWS_WINDOW_MODE, TELEGRAM_REQUIRED
from src.database import ensure_db
from src.reports.morning import generate_morning_report
from src.telegram import send_message, send_error_notification
from src.utils.date_utils import get_kst_now, get_news_window


def main():
    """메인 실행 함수"""
    try:
        # 1. 설정 로딩 및 검증
        validate_config()
        
        # 2. DB 연결/초기화
        ensure_db()
        
        # 3. 뉴스 윈도우 정보 출력 (로컬 검증용)
        now = get_kst_now()
        start_dt, end_dt, mode, lookback_hours = get_news_window(now, mode=NEWS_WINDOW_MODE)
        print(f"[NEWS_WINDOW_MODE]={NEWS_WINDOW_MODE}")
        if lookback_hours:
            print(f"[NEWS_LOOKBACK_HOURS]={lookback_hours}")
        print(f"start_dt={start_dt.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        print(f"end_dt={end_dt.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        
        # 4. 리포트 생성
        report = generate_morning_report()
        
        # 5. 리포트에서 카운트 정보 추출 (로컬 검증용)
        # 리포트에서 "수집: X건 → 시간필터: Y건 → 중복제거: Z건" 패턴 찾기
        import re
        count_match = re.search(r'\*수집:\* (\d+)건 → 시간필터: (\d+)건 → 중복제거: (\d+)건', report)
        if count_match:
            fetched = count_match.group(1)
            time_filtered = count_match.group(2)
            deduped = count_match.group(3)
            print(f"fetched={fetched} time_filtered={time_filtered} deduped={deduped}")
        
        # 6. 텔레그램 전송
        success = send_message(report)
        
        if success:
            print("✓ 오전 리포트 전송 완료")
        else:
            print("✗ 오전 리포트 전송 실패")
            if TELEGRAM_REQUIRED:
                sys.exit(1)
            else:
                print("⚠️  TELEGRAM_REQUIRED=false이므로 워크플로우는 계속 진행됩니다.")
    
    except Exception as e:
        error_msg = f"오전 리포트 생성 중 오류 발생: {e}\n{traceback.format_exc()}"
        print(error_msg)
        
        # 에러 알림 전송
        send_error_notification(e, "오전 리포트 생성")
        
        sys.exit(1)


if __name__ == "__main__":
    main()

