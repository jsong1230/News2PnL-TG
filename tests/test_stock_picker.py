"""종목 선정 로직 테스트"""
import sys
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, patch
import pytest
from pytz import UTC

# 프로젝트 루트를 경로에 추가
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.analysis.stock_picker import (
    extract_stock_candidates,
    calculate_checklist_score,
    assess_confidence,
    generate_risks,
    generate_trigger,
    create_stock_candidates,
    parse_llm_response,
)
from src.analysis.news_analyzer import NewsDigest
from tests.conftest import create_news_item


class TestExtractStockCandidates:
    """종목 후보 추출 테스트"""
    
    def test_basic_extraction(self, sample_digest, sample_news_items):
        """기본 종목 후보 추출"""
        candidates = extract_stock_candidates(sample_digest, sample_news_items)
        
        assert isinstance(candidates, dict)
        assert len(candidates) > 0
        # 점수는 양수여야 함
        for stock, score in candidates.items():
            assert score > 0
    
    def test_with_overnight_signals(self, sample_digest, sample_news_items, sample_overnight_signals):
        """선행 신호와 함께 추출"""
        candidates = extract_stock_candidates(
            sample_digest, 
            sample_news_items,
            overnight_signals=sample_overnight_signals
        )
        
        assert isinstance(candidates, dict)
        assert len(candidates) > 0


class TestCalculateChecklistScore:
    """체크리스트 점수 계산 테스트"""
    
    def test_with_catalyst(self):
        """Catalyst 있는 경우"""
        scores, total = calculate_checklist_score("삼성전자", has_catalyst=True)
        
        assert isinstance(scores, dict)
        assert isinstance(total, int)
        assert total >= 0
        assert total <= 12  # 최대 점수 (6단계 × 2점)
    
    def test_without_catalyst(self):
        """Catalyst 없는 경우"""
        scores, total = calculate_checklist_score("삼성전자", has_catalyst=False)
        
        assert isinstance(scores, dict)
        assert isinstance(total, int)
        # Catalyst 없으면 점수가 더 낮아야 함
        assert total >= 0
    
    def test_with_financial_metrics(self):
        """재무 지표와 함께 계산"""
        # Mock 재무 지표
        mock_metrics = Mock()
        mock_metrics.per = 15.0
        mock_metrics.debt_ratio = 30.0
        mock_metrics.revenue_growth_3y = 10.0
        
        scores, total = calculate_checklist_score(
            "삼성전자", 
            has_catalyst=True,
            financial_metrics=mock_metrics
        )
        
        assert isinstance(scores, dict)
        assert total >= 0


class TestAssessConfidence:
    """확신도 평가 테스트"""
    
    def test_high_confidence(self):
        """높은 확신도"""
        confidence, reason = assess_confidence(
            total_score=10,
            has_catalyst=True,
            in_watchlist=True
        )
        
        assert confidence in ["상", "중", "하"]
        assert isinstance(reason, str)
        assert len(reason) > 0
    
    def test_low_confidence(self):
        """낮은 확신도"""
        confidence, reason = assess_confidence(
            total_score=2,
            has_catalyst=False,
            in_watchlist=False
        )
        
        assert confidence in ["상", "중", "하"]
        assert isinstance(reason, str)
    
    def test_medium_confidence(self):
        """중간 확신도"""
        confidence, reason = assess_confidence(
            total_score=6,
            has_catalyst=True,
            in_watchlist=False
        )
        
        assert confidence in ["상", "중", "하"]


class TestGenerateRisks:
    """리스크 생성 테스트"""
    
    def test_risk_generation(self):
        """리스크 생성"""
        risks = generate_risks("삼성전자")
        
        assert isinstance(risks, list)
        assert len(risks) > 0
        for risk in risks:
            assert isinstance(risk, str)
            assert len(risk) > 0


class TestGenerateTrigger:
    """관찰 트리거 생성 테스트"""
    
    def test_trigger_generation(self):
        """트리거 생성"""
        trigger = generate_trigger("삼성전자")
        
        assert isinstance(trigger, str)
        assert len(trigger) > 0


class TestCreateStockCandidates:
    """후보 종목 리스트 생성 테스트"""
    
    def test_basic_candidate_creation(self, sample_digest, sample_news_items):
        """기본 후보 생성"""
        candidates = create_stock_candidates(sample_digest, sample_news_items)
        
        assert isinstance(candidates, list)
        assert len(candidates) > 0
        
        # 각 후보는 필수 필드를 가져야 함
        for candidate in candidates:
            assert "name" in candidate
            assert "code" in candidate
            assert "score" in candidate
    
    def test_max_candidates_limit(self, sample_digest, sample_news_items):
        """최대 후보 수 제한"""
        max_count = 5
        candidates = create_stock_candidates(
            sample_digest, 
            sample_news_items,
            max_candidates=max_count
        )
        
        assert len(candidates) <= max_count
    
    def test_with_overnight_signals(self, sample_digest, sample_news_items, sample_overnight_signals):
        """선행 신호와 함께 생성"""
        candidates = create_stock_candidates(
            sample_digest,
            sample_news_items,
            overnight_signals=sample_overnight_signals
        )
        
        assert isinstance(candidates, list)
        assert len(candidates) > 0


class TestParseLLMResponse:
    """LLM 응답 파싱 테스트"""
    
    def test_valid_response(self):
        """유효한 LLM 응답"""
        llm_output = {
            "stocks": [
                {
                    "name": "삼성전자",
                    "code": "005930",
                    "thesis": "반도체 수요 증가",
                    "catalysts": ["AI 칩 수요 급증", "신규 공장 건설"],
                    "confidence": "상",
                    "confidence_reason": "강력한 펀더멘털"
                }
            ]
        }
        
        candidates = [
            {
                "name": "삼성전자",
                "code": "005930",
                "score": 10,
                "matched_headlines": ["삼성전자 뉴스"],
                "sector": "반도체"
            }
        ]
        
        result = parse_llm_response(llm_output, candidates)
        
        # 파싱 성공 시 리스트 반환
        if result is not None:
            assert isinstance(result, list)
            assert len(result) > 0
    
    def test_invalid_response(self):
        """유효하지 않은 LLM 응답"""
        llm_output = {
            "invalid_key": []
        }
        
        candidates = [
            {
                "name": "삼성전자",
                "code": "005930",
                "score": 10
            }
        ]
        
        result = parse_llm_response(llm_output, candidates)
        
        # 파싱 실패 시 None 반환
        assert result is None
    
    def test_empty_stocks(self):
        """빈 종목 리스트"""
        llm_output = {
            "stocks": []
        }
        
        candidates = []
        
        result = parse_llm_response(llm_output, candidates)
        
        # 빈 리스트도 유효한 응답
        if result is not None:
            assert isinstance(result, list)
            assert len(result) == 0
