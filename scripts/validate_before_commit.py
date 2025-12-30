#!/usr/bin/env python3
"""커밋 전 GitHub Actions 동작 검증 스크립트"""
import sys
import subprocess
from pathlib import Path

# 프로젝트 루트를 경로에 추가
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

def run_command(cmd, description):
    """명령어 실행 및 결과 반환"""
    print(f"\n{'='*60}")
    print(f"검증: {description}")
    print(f"명령어: {cmd}")
    print(f"{'='*60}")
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            cwd=project_root
        )
        if result.returncode == 0:
            print(f"✓ 성공")
            if result.stdout:
                print(result.stdout)
            return True
        else:
            print(f"✗ 실패 (exit code: {result.returncode})")
            if result.stderr:
                print("에러 출력:")
                print(result.stderr)
            if result.stdout:
                print("표준 출력:")
                print(result.stdout)
            return False
    except Exception as e:
        print(f"✗ 예외 발생: {e}")
        return False

def check_python_syntax():
    """Python 문법 오류 확인"""
    print("\n[1/5] Python 문법 검증")
    
    # 주요 스크립트 파일들
    scripts = [
        "scripts/run_morning.py",
        "scripts/run_evening.py",
        "scripts/run_monthly.py",
    ]
    
    # src 디렉토리의 모든 Python 파일
    src_files = list(Path("src").rglob("*.py"))
    
    all_files = scripts + [str(f) for f in src_files]
    
    success = True
    for file_path in all_files:
        if not Path(file_path).exists():
            continue
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", file_path],
            capture_output=True,
            text=True,
            cwd=project_root
        )
        if result.returncode != 0:
            print(f"✗ {file_path}: 문법 오류")
            print(result.stderr)
            success = False
    
    if success:
        print(f"✓ 모든 Python 파일 문법 검증 통과 ({len(all_files)}개 파일)")
    return success

def check_imports():
    """Import 오류 확인"""
    print("\n[2/5] Import 검증")
    
    test_cases = [
        ("scripts.run_morning", "run_morning.py"),
        ("scripts.run_evening", "run_evening.py"),
        ("scripts.run_monthly", "run_monthly.py"),
        ("src.config", "config.py"),
        ("src.reports.morning", "morning.py"),
        ("src.reports.evening", "evening.py"),
        ("src.reports.monthly", "monthly.py"),
        ("src.market.overnight", "overnight.py"),
        ("src.analysis.news_analyzer", "news_analyzer.py"),
        ("src.analysis.stock_picker", "stock_picker.py"),
    ]
    
    success = True
    for module_name, display_name in test_cases:
        try:
            __import__(module_name)
            print(f"✓ {display_name}")
        except ImportError as e:
            print(f"✗ {display_name}: {e}")
            success = False
        except SyntaxError as e:
            print(f"✗ {display_name}: 문법 오류 - {e}")
            success = False
        except Exception as e:
            print(f"✗ {display_name}: 예외 - {e}")
            success = False
    
    return success

def check_core_functions():
    """핵심 함수 import 확인"""
    print("\n[3/5] 핵심 함수 검증")
    
    try:
        from src.config import validate_config
        from src.reports.morning import generate_morning_report
        from src.reports.evening import generate_evening_report
        from src.reports.monthly import generate_monthly_report
        from src.market.overnight import fetch_overnight_signals, assess_market_tone
        from src.analysis.news_analyzer import create_digest
        from src.analysis.stock_picker import pick_watch_stocks
        print("✓ 모든 핵심 함수 import 성공")
        return True
    except ImportError as e:
        print(f"✗ 핵심 함수 import 실패: {e}")
        return False
    except Exception as e:
        print(f"✗ 예외 발생: {e}")
        return False

def check_workflow_files():
    """GitHub Actions 워크플로우 파일 검증"""
    print("\n[4/5] GitHub Actions 워크플로우 파일 검증")
    
    workflow_files = [
        ".github/workflows/morning.yml",
        ".github/workflows/evening.yml",
        ".github/workflows/monthly.yml",
    ]
    
    success = True
    for workflow_file in workflow_files:
        path = Path(project_root / workflow_file)
        if path.exists():
            # YAML 문법 검증 (간단히 파일이 존재하고 읽을 수 있는지만 확인)
            try:
                with open(path, 'r') as f:
                    content = f.read()
                    # 기본적인 YAML 구조 확인
                    if 'name:' in content and 'on:' in content and 'jobs:' in content:
                        print(f"✓ {workflow_file}")
                    else:
                        print(f"⚠ {workflow_file}: YAML 구조가 불완전할 수 있습니다")
            except Exception as e:
                print(f"✗ {workflow_file}: 읽기 실패 - {e}")
                success = False
        else:
            print(f"⚠ {workflow_file}: 파일이 없습니다")
    
    return success

def run_basic_tests():
    """기본 테스트 실행"""
    print("\n[5/5] 기본 테스트 실행")
    
    return run_command(
        f"{sys.executable} -m pytest tests/ -q --tb=short",
        "pytest 기본 테스트"
    )

def main():
    """메인 검증 함수"""
    print("\n" + "="*60)
    print("GitHub Actions 동작 검증 시작")
    print("="*60)
    
    results = []
    
    # 1. Python 문법 검증
    results.append(("Python 문법", check_python_syntax()))
    
    # 2. Import 검증
    results.append(("Import 검증", check_imports()))
    
    # 3. 핵심 함수 검증
    results.append(("핵심 함수", check_core_functions()))
    
    # 4. 워크플로우 파일 검증
    results.append(("워크플로우 파일", check_workflow_files()))
    
    # 5. 기본 테스트 실행
    results.append(("기본 테스트", run_basic_tests()))
    
    # 결과 요약
    print("\n" + "="*60)
    print("검증 결과 요약")
    print("="*60)
    
    all_passed = True
    for name, passed in results:
        status = "✓ 통과" if passed else "✗ 실패"
        print(f"{name}: {status}")
        if not passed:
            all_passed = False
    
    print("="*60)
    
    if all_passed:
        print("✓ 모든 검증 통과! 커밋해도 안전합니다.")
        return 0
    else:
        print("✗ 일부 검증 실패. 커밋 전에 문제를 해결하세요.")
        return 1

if __name__ == "__main__":
    sys.exit(main())


