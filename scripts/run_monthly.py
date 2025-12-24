#!/usr/bin/env python3
"""월간 리포트 실행 스크립트"""
import sys
import traceback
from pathlib import Path

# 프로젝트 루트를 경로에 추가 (어디서 실행해도 동작하도록)
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.config import validate_config, MONTH_OVERRIDE, TELEGRAM_REQUIRED
from src.database import ensure_db
from src.reports.monthly import generate_monthly_report
from src.telegram import send_message, send_error_notification
from src.utils.date_utils import is_month_end


def main():
    """메인 실행 함수"""
    try:
        # 월말 체크 (MONTH_OVERRIDE가 있으면 스킵)
        if not MONTH_OVERRIDE and not is_month_end():
            print("월말이 아니므로 월간 리포트를 생성하지 않습니다.")
            print("개발용으로 MONTH_OVERRIDE=YYYY-MM 환경변수를 설정하면 언제든 실행 가능합니다.")
            sys.exit(0)
        
        # 1. 설정 로딩 및 검증
        validate_config()
        
        # 2. DB 연결/초기화
        ensure_db()
        
        # 3. 리포트 생성
        if MONTH_OVERRIDE:
            print(f"MONTH_OVERRIDE={MONTH_OVERRIDE}로 월간 리포트 생성")
        report = generate_monthly_report()
        
        # 4. 텔레그램 전송
        success = send_message(report)
        
        if success:
            print("✓ 월간 리포트 전송 완료")
        else:
            print("✗ 월간 리포트 전송 실패")
            if TELEGRAM_REQUIRED:
                sys.exit(1)
            else:
                print("⚠️  TELEGRAM_REQUIRED=false이므로 워크플로우는 계속 진행됩니다.")
    
    except Exception as e:
        error_msg = f"월간 리포트 생성 중 오류 발생: {e}\n{traceback.format_exc()}"
        print(error_msg)
        
        # 에러 알림 전송
        send_error_notification(e, "월간 리포트 생성")
        
        sys.exit(1)


if __name__ == "__main__":
    main()

