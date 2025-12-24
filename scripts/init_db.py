#!/usr/bin/env python3
"""DB 초기화 스크립트"""
import sys
from pathlib import Path

# 프로젝트 루트를 경로에 추가 (어디서 실행해도 동작하도록)
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.database import init_schema


def main():
    """DB 초기화"""
    try:
        init_schema()
        print("✓ DB 초기화 완료")
    except Exception as e:
        print(f"✗ DB 초기화 실패: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

