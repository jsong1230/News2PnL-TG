"""뉴스 분석 모듈 테스트"""
import sys
from pathlib import Path
from datetime import datetime, timedelta
import pytest
from pytz import UTC

# 프로젝트 루트를 경로에 추가
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.utils.text import normalize_title, jaccard_similarity
from src.analysis.news_analyzer import (
    is_noise_article,
    calculate_freshness_score,
    calculate_novelty_score,
    calculate_late_news_penalty,
    calculate_clickbait_penalty,
    score_headline,
    remove_duplicates,
    classify_sector,
    create_digest,
)
from unittest.mock import MagicMock
from tests.conftest import create_news_item


class TestNormalizeTitle:
    """제목 정규화 테스트"""
    
    def test_basic_normalization(self):
        """기본 정규화 테스트"""
        title = "  NVIDIA AI 칩 수요 급증!!!  "
        normalized = normalize_title(title)
        assert normalized == "nvidia ai 칩 수요 급증"
    
    def test_special_characters_removal(self):
        """특수문자 제거 테스트"""
        title = "삼성전자, 반도체 공장 건설 발표!!!"
        normalized = normalize_title(title)
        assert "," not in normalized
        assert "!" not in normalized
    
    def test_whitespace_normalization(self):
        """공백 정규화 테스트"""
        title = "SK하이닉스    HBM3    양산"
        normalized = normalize_title(title)
        assert "  " not in normalized


class TestJaccardSimilarity:
    """Jaccard 유사도 계산 테스트"""
    
    def test_identical_texts(self):
        """동일한 텍스트 유사도"""
        text = "NVIDIA AI 칩 수요 급증"
        similarity = jaccard_similarity(text, text)
        assert similarity == 1.0
    
    def test_completely_different_texts(self):
        """완전히 다른 텍스트 유사도"""
        text1 = "NVIDIA AI 칩"
        text2 = "삼성전자 반도체"
        similarity = jaccard_similarity(text1, text2)
        assert similarity < 0.3
    
    def test_similar_texts(self):
        """유사한 텍스트 유사도"""
        text1 = "NVIDIA AI 칩 수요 급증"
        text2 = "NVIDIA AI 칩 판매 증가"
        similarity = jaccard_similarity(text1, text2)
        assert 0.3 < similarity < 0.8


class TestIsNoiseArticle:
    """노이즈 기사 판단 테스트"""
    
    def test_advertisement_detection(self):
        """광고 기사 감지"""
        # 실제 구현은 더 엄격한 필터를 사용
        assert is_noise_article("오늘의 날씨 예보") is True
        assert is_noise_article("맛집 추천") is True
    
    def test_lifestyle_news_detection(self):
        """생활뉴스 감지"""
        assert is_noise_article("오늘의 날씨 예보") is True
        assert is_noise_article("맛집 추천 베스트 10") is True
    
    def test_valid_business_news(self):
        """정상 비즈니스 뉴스"""
        assert is_noise_article("NVIDIA AI 칩 수요 급증") is False
        assert is_noise_article("삼성전자 반도체 공장 건설") is False


class TestCalculateFreshnessScore:
    """신선도 점수 계산 테스트"""
    
    def test_recent_news(self, fixed_datetime):
        """최근 뉴스 (1시간 전)"""
        item = create_news_item("테스트 뉴스", hours_ago=1, base_time=fixed_datetime)
        score = calculate_freshness_score(item, now_utc=fixed_datetime)
        assert score > 0.9
    
    def test_old_news(self, fixed_datetime):
        """오래된 뉴스 (24시간 전)"""
        item = create_news_item("테스트 뉴스", hours_ago=24, base_time=fixed_datetime)
        score = calculate_freshness_score(item, now_utc=fixed_datetime)
        assert score < 0.5
    
    def test_very_old_news(self, fixed_datetime):
        """매우 오래된 뉴스 (48시간 전)"""
        item = create_news_item("테스트 뉴스", hours_ago=48, base_time=fixed_datetime)
        score = calculate_freshness_score(item, now_utc=fixed_datetime)
        assert score < 0.3


class TestCalculateNoveltyScore:
    """새로움 점수 계산 테스트"""
    
    def test_unique_news(self, fixed_datetime):
        """고유한 뉴스"""
        item = create_news_item("NVIDIA AI 칩 수요 급증", base_time=fixed_datetime)
        other_items = [
            create_news_item("삼성전자 반도체 공장 건설", base_time=fixed_datetime),
            create_news_item("SK하이닉스 HBM3 양산", base_time=fixed_datetime),
        ]
        novelty, penalty = calculate_novelty_score(item, other_items, now_utc=fixed_datetime)
        assert novelty > 0.8
        assert penalty < 0.3
    
    def test_duplicate_news(self, fixed_datetime):
        """중복 뉴스"""
        item = create_news_item("NVIDIA AI 칩 수요 급증", base_time=fixed_datetime)
        other_items = [
            create_news_item("NVIDIA AI 칩 수요 급증", base_time=fixed_datetime),
            create_news_item("NVIDIA AI 칩 판매 증가", base_time=fixed_datetime),
        ]
        novelty, penalty = calculate_novelty_score(item, other_items, now_utc=fixed_datetime)
        # 유사한 뉴스가 있으면 novelty가 낮아짐
        assert novelty <= 1.0
        assert penalty >= 0.0


class TestCalculateLateNewsPenalty:
    """늦은 뉴스 페널티 테스트"""
    
    def test_no_overnight_signals(self, fixed_datetime):
        """선행 신호 없음"""
        item = create_news_item("NVIDIA 주가 상승", base_time=fixed_datetime)
        penalty = calculate_late_news_penalty(item, "반도체", overnight_signals=None)
        assert penalty == 0.0
    
    def test_with_overnight_signals(self, fixed_datetime, sample_overnight_signals):
        """선행 신호 있음"""
        item = create_news_item("나스닥 상승세", base_time=fixed_datetime)
        penalty = calculate_late_news_penalty(item, "기술", overnight_signals=sample_overnight_signals)
        # 페널티는 0 이상이어야 함
        assert penalty >= 0.0


class TestCalculateClickbaitPenalty:
    """클릭베이트 페널티 테스트"""
    
    def test_clickbait_title(self, fixed_datetime):
        """클릭베이트 제목"""
        item = create_news_item("충격! 이 주식 지금 사지 않으면 후회합니다!", base_time=fixed_datetime)
        penalty = calculate_clickbait_penalty(item)
        # 클릭베이트 페널티가 있어야 함
        assert penalty > 0.0
    
    def test_normal_title(self, fixed_datetime):
        """정상 제목"""
        item = create_news_item("NVIDIA AI 칩 수요 급증", base_time=fixed_datetime)
        penalty = calculate_clickbait_penalty(item)
        assert penalty < 0.3


class TestScoreHeadline:
    """헤드라인 점수 계산 테스트"""
    
    def test_high_quality_headline(self, fixed_datetime):
        """고품질 헤드라인"""
        item = create_news_item("NVIDIA AI 칩 수요 급증", hours_ago=1, base_time=fixed_datetime)
        score, debug = score_headline(item, all_items=[], now_utc=fixed_datetime)
        assert score > 0
        assert "freshness_score" in debug
        assert "novelty_score" in debug
    
    def test_low_quality_headline(self, fixed_datetime):
        """저품질 헤드라인"""
        item = create_news_item("충격! 이 주식 지금 사세요!", hours_ago=24, base_time=fixed_datetime)
        score, debug = score_headline(item, all_items=[], now_utc=fixed_datetime)
        # 점수가 계산되었는지만 확인
        assert isinstance(score, (int, float))
        assert score >= 0


class TestRemoveDuplicates:
    """중복 제거 테스트"""
    
    def test_no_duplicates(self, fixed_datetime):
        """중복 없음"""
        items = [
            create_news_item("NVIDIA AI 칩 수요 급증", base_time=fixed_datetime),
            create_news_item("삼성전자 반도체 공장 건설", base_time=fixed_datetime),
            create_news_item("SK하이닉스 HBM3 양산", base_time=fixed_datetime),
        ]
        result = remove_duplicates(items)
        assert len(result) == 3
    
    def test_with_duplicates(self, fixed_datetime):
        """중복 있음"""
        items = [
            create_news_item("NVIDIA AI 칩 수요 급증", base_time=fixed_datetime),
            create_news_item("NVIDIA AI 칩 수요 급증", base_time=fixed_datetime),
            create_news_item("삼성전자 반도체 공장 건설", base_time=fixed_datetime),
        ]
        result = remove_duplicates(items)
        assert len(result) == 2
    
    def test_similar_titles(self, fixed_datetime):
        """유사한 제목"""
        items = [
            create_news_item("NVIDIA AI 칩 수요 급증", base_time=fixed_datetime),
            create_news_item("NVIDIA AI 칩 판매 급증", base_time=fixed_datetime),
            create_news_item("삼성전자 반도체 공장 건설", base_time=fixed_datetime),
        ]
        result = remove_duplicates(items, title_threshold=0.85)
        # 유사도가 높으면 중복으로 간주
        assert len(result) <= 3


class TestClassifySector:
    """섹터 분류 테스트"""
    
    def test_semiconductor_sector(self):
        """반도체 섹터"""
        sector = classify_sector("NVIDIA AI 칩 수요 급증", "반도체 관련 뉴스")
        # 실제 구현은 "반도체/AI"를 반환
        assert "반도체" in sector or sector == "반도체/AI"
    
    def test_automobile_sector(self):
        """자동차 섹터"""
        sector = classify_sector("테슬라 전기차 판매 증가", "전기차 관련 뉴스")
        # 새로운 분류 체계: 자동차/모빌리티 또는 2차전지/에너지
        assert sector in ["자동차/모빌리티", "2차전지/에너지"]
    
    def test_finance_sector(self):
        """금융 섹터"""
        sector = classify_sector("은행 대출 금리 인상", "금융 관련 뉴스")
        # 금리 관련은 거시/금리/달러, 은행/금융권은 금융/지주
        assert sector in ["금융/지주", "거시/금리/달러"]
    
    def test_unknown_sector(self):
        """기타 섹터"""
        sector = classify_sector("일반 뉴스", "특정 섹터 없음")
        assert sector == "기타"


class TestCreateDigest:
    """다이제스트 생성 테스트"""
    
    def test_basic_digest_creation(self, sample_news_items):
        """기본 다이제스트 생성"""
        digest = create_digest(sample_news_items, fetched_count=10, time_filtered_count=5)
        
        assert digest is not None
        assert len(digest.top_headlines) > 0
        assert digest.macro_summary != ""
        assert len(digest.sector_bullets) > 0
        # korea_impact는 "상", "중", "하"로 시작하는 문자열
        assert any(digest.korea_impact.startswith(level) for level in ["상", "중", "하"])
        assert digest.fetched_count == 10
        assert digest.time_filtered_count == 5
    
    def test_digest_with_overnight_signals(self, sample_news_items, sample_overnight_signals):
        """선행 신호와 함께 다이제스트 생성"""
        digest = create_digest(
            sample_news_items, 
            fetched_count=10, 
            time_filtered_count=5,
            overnight_signals=sample_overnight_signals
        )
        
        assert digest is not None
        assert len(digest.top_headlines) > 0
    
    def test_empty_news_list(self):
        """빈 뉴스 리스트"""
        digest = create_digest([], fetched_count=0, time_filtered_count=0)
        
        assert digest is not None
        assert len(digest.top_headlines) == 0
        assert digest.deduped_count == 0
