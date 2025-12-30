"""텍스트 처리 유틸리티"""
import re


def normalize_title(title: str) -> str:
    """제목 정규화 (중복 제거용)"""
    if not title:
        return ""
        
    # 소문자 변환
    title = title.lower()
    # 특수문자 제거 (한글, 영문, 숫자만 남김)
    title = re.sub(r'[^\w\s가-힣]', '', title)
    # 공백 정규화
    title = re.sub(r'\s+', ' ', title).strip()
    return title


def jaccard_similarity(text1: str, text2: str) -> float:
    """Jaccard 유사도 계산 (단어 기반)"""
    if not text1 or not text2:
        return 0.0
        
    words1 = set(text1.split())
    words2 = set(text2.split())
    
    if not words1 or not words2:
        return 0.0
    
    intersection = len(words1 & words2)
    union = len(words1 | words2)
    
    return intersection / union if union > 0 else 0.0
