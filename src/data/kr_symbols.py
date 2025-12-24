"""한국 주식 종목 마스터 (종목명 ↔ 종목코드 매핑)"""
from typing import Dict, Optional

# 종목명 → 종목코드 매핑 (대표 종목 40~60개)
KR_SYMBOLS: Dict[str, str] = {
    # 반도체/AI
    "삼성전자": "005930",
    "SK하이닉스": "000660",
    "하이닉스": "000660",
    
    # 2차전지/원자재
    "LG에너지솔루션": "373220",
    "LG에너솔": "373220",
    "LG화학": "051910",
    "삼성SDI": "006400",
    "포스코케미칼": "003670",
    "포스코홀딩스": "005490",
    
    # 바이오/헬스
    "셀트리온": "068270",
    "삼성바이오로직스": "207940",
    "유한양행": "000100",
    "한미약품": "128940",
    "녹십자": "006280",
    "대웅제약": "069620",
    
    # IT/플랫폼
    "NAVER": "035420",
    "네이버": "035420",
    "카카오": "035720",
    "카카오페이": "377300",
    "카카오뱅크": "323410",
    "LG유플러스": "032640",
    "KT": "030200",
    "SK텔레콤": "017670",
    
    # 자동차
    "현대차": "005380",
    "현대자동차": "005380",
    "기아": "000270",
    "기아자동차": "000270",
    "현대모비스": "012330",
    "만도": "204320",
    
    # 금융
    "KB금융": "105560",
    "신한지주": "055550",
    "하나금융지주": "086790",
    "우리금융지주": "316140",
    "NH투자증권": "005940",
    "미래에셋증권": "006800",
    
    # 방산/조선
    "한화오션": "042660",
    "한화": "000880",
    "한화에어로스페이스": "012450",
    "LIG넥스원": "079550",
    "대우조선해양": "042660",
    
    # 화학/에너지
    "LG화학": "051910",
    "롯데케미칼": "011170",
    "SK이노베이션": "096770",
    "S-Oil": "010950",
    "GS": "078930",
    
    # 소비재
    "아모레퍼시픽": "090430",
    "LG생활건강": "051900",
    "롯데칠성": "005300",
    "오리온": "271560",
    
    # 건설/부동산
    "현대건설": "000720",
    "대림산업": "000210",
    "GS건설": "006360",
    
    # 기타 대형주
    "POSCO": "005490",
    "포스코": "005490",
    "한국전력": "015760",
    "KT&G": "033780",
}

# 해외 종목 → 한국 대체 종목 매핑 (가중치 상승용)
FOREIGN_TO_KR_MAPPING: Dict[str, list] = {
    "엔비디아": ["삼성전자", "SK하이닉스"],
    "nvidia": ["삼성전자", "SK하이닉스"],
    "amd": ["삼성전자", "SK하이닉스"],
    "테슬라": ["LG에너지솔루션", "삼성SDI"],
    "tesla": ["LG에너지솔루션", "삼성SDI"],
    "애플": ["삼성전자", "LG디스플레이"],
    "apple": ["삼성전자", "LG디스플레이"],
}


def get_symbol_code(name: str) -> Optional[str]:
    """
    종목명으로 종목코드 조회
    
    Args:
        name: 종목명
    
    Returns:
        종목코드 또는 None
    """
    # 정확한 매칭
    if name in KR_SYMBOLS:
        return KR_SYMBOLS[name]
    
    # 부분 매칭 (종목명이 텍스트에 포함된 경우)
    name_lower = name.lower()
    for symbol_name, code in KR_SYMBOLS.items():
        if symbol_name.lower() in name_lower or name_lower in symbol_name.lower():
            return code
    
    return None


def find_symbols_in_text(text: str) -> Dict[str, str]:
    """
    텍스트에서 종목명을 찾아 종목코드 매핑 반환
    
    Args:
        text: 검색할 텍스트
    
    Returns:
        {종목명: 종목코드} 딕셔너리
    """
    found = {}
    text_lower = text.lower()
    
    # 정확한 매칭
    for symbol_name, code in KR_SYMBOLS.items():
        if symbol_name.lower() in text_lower:
            found[symbol_name] = code
    
    return found


def get_foreign_substitute_symbols(foreign_name: str) -> list:
    """
    해외 종목명에 대한 한국 대체 종목 리스트 반환
    
    Args:
        foreign_name: 해외 종목명 (예: "엔비디아", "NVIDIA")
    
    Returns:
        한국 대체 종목명 리스트
    """
    foreign_lower = foreign_name.lower()
    return FOREIGN_TO_KR_MAPPING.get(foreign_lower, [])

