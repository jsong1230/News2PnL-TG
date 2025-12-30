"""재시도 로직 및 Exponential Backoff 유틸리티"""
import time
import logging
from typing import Callable, TypeVar, Any, Optional, Tuple
from functools import wraps

logger = logging.getLogger(__name__)

T = TypeVar('T')


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    retryable_exceptions: Optional[Tuple[type, ...]] = None
):
    """
    Exponential backoff를 사용한 재시도 데코레이터
    
    Args:
        max_retries: 최대 재시도 횟수 (기본 3회)
        base_delay: 기본 지연 시간 (초, 기본 1초)
        max_delay: 최대 지연 시간 (초, 기본 60초)
        exponential_base: 지수 증가 배수 (기본 2.0)
        retryable_exceptions: 재시도 가능한 예외 튜플 (None이면 모든 예외)
    
    Returns:
        데코레이터 함수
    
    Example:
        @retry_with_backoff(max_retries=3, base_delay=1.0)
        def fetch_data():
            # API 호출 등
            pass
    """
    if retryable_exceptions is None:
        # 기본적으로 네트워크 관련 에러만 재시도
        retryable_exceptions = (
            ConnectionError,
            TimeoutError,
        )
    
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    result = func(*args, **kwargs)
                    
                    # 재시도 후 성공한 경우 로깅
                    if attempt > 0:
                        func_name = getattr(func, '__name__', 'unknown_function')
                        logger.info(
                            f"{func_name} 재시도 성공 "
                            f"(시도 {attempt + 1}/{max_retries + 1})"
                        )
                    
                    return result
                
                except retryable_exceptions as e:
                    last_exception = e
                    
                    # 마지막 시도인 경우 재시도하지 않음
                    if attempt >= max_retries:
                        func_name = getattr(func, '__name__', 'unknown_function')
                        logger.error(
                            f"{func_name} 최대 재시도 횟수 초과 "
                            f"({max_retries + 1}회): {e}"
                        )
                        raise
                    
                    # Exponential backoff 계산
                    delay = min(
                        base_delay * (exponential_base ** attempt),
                        max_delay
                    )
                    
                    logger.warning(
                        f"{getattr(func, '__name__', 'unknown_function')} 재시도 대기 중 "
                        f"(시도 {attempt + 1}/{max_retries + 1}, "
                        f"대기 {delay:.1f}초): {e}"
                    )
                    
                    time.sleep(delay)
                
                except Exception as e:
                    # 재시도 불가능한 예외는 즉시 발생
                    func_name = getattr(func, '__name__', 'unknown_function')
                    logger.error(
                        f"{func_name} 재시도 불가능한 예외 발생: "
                        f"{type(e).__name__}: {e}"
                    )
                    raise
            
            # 이 지점에 도달하면 안 되지만, 안전을 위해 마지막 예외 발생
            if last_exception:
                raise last_exception
            
            func_name = getattr(func, '__name__', 'unknown_function')
            raise RuntimeError(f"{func_name} 예상치 못한 재시도 종료")
        
        return wrapper
    
    return decorator


def classify_error(exception: Exception) -> str:
    """
    예외를 타입별로 분류
    
    Args:
        exception: 분류할 예외
    
    Returns:
        에러 타입 문자열 (network, timeout, data, unknown)
    """
    if isinstance(exception, TimeoutError):
        return "timeout"
    elif isinstance(exception, (ConnectionError, OSError)):
        return "network"
    elif isinstance(exception, (ValueError, KeyError, TypeError)):
        return "data"
    elif isinstance(exception, ImportError):
        return "import"
    else:
        return "unknown"


def is_retryable_error(exception: Exception) -> bool:
    """
    예외가 재시도 가능한지 판단
    
    Args:
        exception: 판단할 예외
    
    Returns:
        재시도 가능 여부
    """
    error_type = classify_error(exception)
    return error_type in ("network", "timeout")
