"""Phase 3 확장 기능 테스트"""
import pytest
from src.data.kr_symbols import KR_SYMBOLS, get_symbol_code, get_foreign_substitute_symbols

def test_new_kr_symbols():
    """새로 추가된 한국 종목 코드 조회 테스트"""
    assert get_symbol_code("한미반도체") == "042700"
    assert get_symbol_code("현대일렉트릭") == "267260"
    assert get_symbol_code("가온칩스") == "399720"
    assert get_symbol_code("에코프로비엠") == "247540"
    assert get_symbol_code("알테오젠") == "196170"
    assert get_symbol_code("비에이치") == "090460"

def test_expanded_foreign_mapping():
    """확장된 해외-국내 종목 매핑 테스트"""
    # AI/반도체
    nvda_subs = get_foreign_substitute_symbols("엔비디아")
    assert "한미반도체" in nvda_subs
    assert "이수페타시스" in nvda_subs
    
    asml_subs = get_foreign_substitute_symbols("asml")
    assert "에프에스티" in asml_subs
    assert "HPSP" in asml_subs
    
    arm_subs = get_foreign_substitute_symbols("arm")
    assert "가온칩스" in arm_subs
    
    # 빅테크
    ms_subs = get_foreign_substitute_symbols("microsoft")
    assert "NAVER" in ms_subs
    
    # 바이오
    lilly_subs = get_foreign_substitute_symbols("일라이릴리")
    assert "한미약품" in lilly_subs
    assert "펩트론" in lilly_subs

def test_partial_match_get_symbol():
    """부분 일치 종목명 조회 테스트"""
    # '현대일렉'만 쳐도 'HD현대일렉트릭'(267260) 또는 '현대일렉트릭'이 나와야 함
    # 현재 로직은 KR_SYMBOLS 순서에 따라 다를 수 있지만 코드는 같아야 함
    code = get_symbol_code("현대일렉")
    assert code == "267260"
    
    code = get_symbol_code("에코프로")
    assert code in ["086520", "247540"] # 에코프로 또는 에코프로비엠
