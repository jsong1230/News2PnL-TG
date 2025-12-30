"""Retry 유틸리티 테스트"""
import sys
from pathlib import Path
import time
from unittest.mock import Mock, patch
import pytest

# 프로젝트 루트를 경로에 추가
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.utils.retry import (
    retry_with_backoff,
    classify_error,
    is_retryable_error,
)


class TestRetryWithBackoff:
    """Exponential backoff 재시도 테스트"""
    
    def test_successful_first_attempt(self):
        """첫 시도에서 성공"""
        mock_func = Mock(return_value="success")
        decorated = retry_with_backoff(max_retries=3)(mock_func)
        
        result = decorated()
        
        assert result == "success"
        assert mock_func.call_count == 1
    
    def test_retry_on_connection_error(self):
        """ConnectionError 발생 시 재시도"""
        mock_func = Mock(side_effect=[
            ConnectionError("Network error"),
            ConnectionError("Network error"),
            "success"
        ])
        decorated = retry_with_backoff(
            max_retries=3,
            base_delay=0.1  # 테스트 속도를 위해 짧게 설정
        )(mock_func)
        
        result = decorated()
        
        assert result == "success"
        assert mock_func.call_count == 3
    
    def test_max_retries_exceeded(self):
        """최대 재시도 횟수 초과"""
        mock_func = Mock(side_effect=ConnectionError("Network error"))
        decorated = retry_with_backoff(
            max_retries=2,
            base_delay=0.1
        )(mock_func)
        
        with pytest.raises(ConnectionError):
            decorated()
        
        assert mock_func.call_count == 3  # 초기 시도 + 2회 재시도
    
    def test_non_retryable_error(self):
        """재시도 불가능한 에러는 즉시 발생"""
        mock_func = Mock(side_effect=ValueError("Invalid value"))
        decorated = retry_with_backoff(
            max_retries=3,
            retryable_exceptions=(ConnectionError, TimeoutError)
        )(mock_func)
        
        with pytest.raises(ValueError):
            decorated()
        
        assert mock_func.call_count == 1  # 재시도 없음
    
    def test_exponential_backoff_timing(self):
        """Exponential backoff 시간 검증"""
        mock_func = Mock(side_effect=[
            ConnectionError("Error 1"),
            ConnectionError("Error 2"),
            "success"
        ])
        decorated = retry_with_backoff(
            max_retries=3,
            base_delay=0.1,
            exponential_base=2.0
        )(mock_func)
        
        start_time = time.time()
        result = decorated()
        elapsed_time = time.time() - start_time
        
        assert result == "success"
        # 0.1초 (1차 대기) + 0.2초 (2차 대기) = 약 0.3초
        assert 0.25 < elapsed_time < 0.5
    
    def test_max_delay_limit(self):
        """최대 지연 시간 제한"""
        mock_func = Mock(side_effect=[
            ConnectionError("Error"),
            "success"
        ])
        decorated = retry_with_backoff(
            max_retries=3,
            base_delay=10.0,
            max_delay=0.2,  # 최대 0.2초로 제한
            exponential_base=2.0
        )(mock_func)
        
        start_time = time.time()
        result = decorated()
        elapsed_time = time.time() - start_time
        
        assert result == "success"
        # max_delay가 0.2초이므로 그 이상 대기하지 않음
        assert elapsed_time < 0.5


class TestClassifyError:
    """에러 분류 테스트"""
    
    def test_network_error(self):
        """네트워크 에러 분류"""
        assert classify_error(ConnectionError()) == "network"
        assert classify_error(OSError()) == "network"
    
    def test_timeout_error(self):
        """타임아웃 에러 분류"""
        assert classify_error(TimeoutError()) == "timeout"
    
    def test_data_error(self):
        """데이터 에러 분류"""
        assert classify_error(ValueError()) == "data"
        assert classify_error(KeyError()) == "data"
        assert classify_error(TypeError()) == "data"
    
    def test_import_error(self):
        """Import 에러 분류"""
        assert classify_error(ImportError()) == "import"
    
    def test_unknown_error(self):
        """알 수 없는 에러 분류"""
        assert classify_error(RuntimeError()) == "unknown"
        assert classify_error(Exception()) == "unknown"


class TestIsRetryableError:
    """재시도 가능 에러 판단 테스트"""
    
    def test_retryable_errors(self):
        """재시도 가능한 에러"""
        assert is_retryable_error(ConnectionError()) is True
        assert is_retryable_error(TimeoutError()) is True
        assert is_retryable_error(OSError()) is True
    
    def test_non_retryable_errors(self):
        """재시도 불가능한 에러"""
        assert is_retryable_error(ValueError()) is False
        assert is_retryable_error(KeyError()) is False
        assert is_retryable_error(ImportError()) is False
        assert is_retryable_error(RuntimeError()) is False


class TestRetryWithCustomExceptions:
    """커스텀 예외 설정 테스트"""
    
    def test_custom_retryable_exceptions(self):
        """커스텀 재시도 가능 예외"""
        mock_func = Mock(side_effect=[
            ValueError("Error"),
            "success"
        ])
        decorated = retry_with_backoff(
            max_retries=2,
            base_delay=0.1,
            retryable_exceptions=(ValueError,)  # ValueError를 재시도 가능하게 설정
        )(mock_func)
        
        result = decorated()
        
        assert result == "success"
        assert mock_func.call_count == 2
    
    def test_multiple_custom_exceptions(self):
        """여러 커스텀 예외"""
        mock_func = Mock(side_effect=[
            ValueError("Error 1"),
            KeyError("Error 2"),
            "success"
        ])
        decorated = retry_with_backoff(
            max_retries=3,
            base_delay=0.1,
            retryable_exceptions=(ValueError, KeyError)
        )(mock_func)
        
        result = decorated()
        
        assert result == "success"
        assert mock_func.call_count == 3
