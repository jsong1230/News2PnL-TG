"""면책 문구 생성 모듈"""

DISCLAIMER = """
---
*⚠️ 면책 고지*
본 시스템은 리서치 및 교육용 시뮬레이션입니다. 실제 투자 권유가 아니며, 투자 결정에 대한 책임은 사용자에게 있습니다. 과거 성과는 미래 수익을 보장하지 않습니다. 투자 전 충분한 검토와 전문가 상담을 권장합니다.
"""


def get_disclaimer() -> str:
    """면책 문구 반환"""
    return DISCLAIMER.strip()


def append_disclaimer(text: str) -> str:
    """텍스트에 면책 문구 추가"""
    return text + "\n\n" + get_disclaimer()



