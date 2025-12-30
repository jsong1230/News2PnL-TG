"""LLM 클라이언트 (OpenAI Responses API 전용, Structured Outputs)"""
import json
import time
import logging
from typing import Dict, Optional, Any
from datetime import date

from src.config import (
    OPENAI_API_KEY, LLM_MODEL, LLM_MAX_TOKENS, LLM_TEMPERATURE,
    LLM_DAILY_BUDGET_TOKENS
)
from src.utils.logging import track_performance, log_with_extra

logger = logging.getLogger(__name__)

# 일일 토큰 사용량 추적 (간단한 메모리 기반)
_daily_token_usage = {"tokens": 0, "date": None}


def _check_daily_budget() -> bool:
    """일일 토큰 예산 확인"""
    today = date.today()
    
    if _daily_token_usage["date"] != today:
        _daily_token_usage["tokens"] = 0
        _daily_token_usage["date"] = today
    
    return _daily_token_usage["tokens"] < LLM_DAILY_BUDGET_TOKENS


def _add_token_usage(tokens: int):
    """토큰 사용량 추가"""
    _daily_token_usage["tokens"] += tokens


def get_daily_token_usage() -> Dict[str, Any]:
    """현재까지의 일일 토큰 사용량 정보 반환"""
    _check_daily_budget() # 날짜 갱신 보장
    return {
        "tokens": _daily_token_usage["tokens"],
        "limit": LLM_DAILY_BUDGET_TOKENS,
        "percent": (_daily_token_usage["tokens"] / LLM_DAILY_BUDGET_TOKENS * 100) if LLM_DAILY_BUDGET_TOKENS > 0 else 0
    }


@track_performance("llm_generate_json")
def generate_json(
    system_prompt: str,
    user_prompt: str,
    json_schema: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    OpenAI Responses API를 사용하여 JSON 생성 (Structured Outputs)
    
    Args:
        system_prompt: 시스템 프롬프트
        user_prompt: 사용자 프롬프트
        json_schema: JSON Schema (Structured Outputs용, 선택사항)
    
    Returns:
        파싱된 JSON 딕셔너리
    
    Raises:
        Exception: API 호출 실패 또는 JSON 파싱 실패
    """
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY가 설정되지 않았습니다")
    
    if not _check_daily_budget():
        raise ValueError(f"일일 토큰 예산 초과: {_daily_token_usage['tokens']}/{LLM_DAILY_BUDGET_TOKENS}")
    
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("openai 패키지가 설치되지 않았습니다. pip install openai")
    
    client = OpenAI(api_key=OPENAI_API_KEY)
    
    try:
        # Structured Outputs 사용 (JSON Schema가 있는 경우)
        if json_schema:
            # OpenAI Responses API (Structured Outputs)
            response = client.beta.chat.completions.parse(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_schema", "json_schema": json_schema},
                temperature=LLM_TEMPERATURE,
                max_tokens=LLM_MAX_TOKENS
            )
            
            # Structured Outputs는 파싱된 객체 반환
            parsed_object = response.choices[0].message.parsed
            if hasattr(parsed_object, 'model_dump'):
                # Pydantic 모델
                result = parsed_object.model_dump()
            elif isinstance(parsed_object, dict):
                result = parsed_object
            else:
                # 기타 객체는 JSON으로 변환
                result = json.loads(parsed_object.json() if hasattr(parsed_object, 'json') else json.dumps(parsed_object))
        else:
            # 기본 JSON 모드 (response_format={"type": "json_object"})
            response = client.chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"},
                temperature=LLM_TEMPERATURE,
                max_tokens=LLM_MAX_TOKENS
            )
            
            content = response.choices[0].message.content
            if not content:
                raise ValueError("LLM 응답이 비어있습니다")
            
            result = json.loads(content)
        
        # 토큰 사용량
        usage = response.usage
        tokens_used = usage.total_tokens if usage else 0
        _add_token_usage(tokens_used)
        
        # 누적 사용량 확인
        daily = get_daily_token_usage()
        
        log_with_extra(
            logger, logging.INFO,
            f"OpenAI API 호출 완료: model={LLM_MODEL}, tokens={tokens_used}, "
            f"daily_total={daily['tokens']}/{daily['limit']} ({daily['percent']:.1f}%)",
            extra={
                "model": LLM_MODEL,
                "tokens": tokens_used,
                "daily_tokens": daily['tokens'],
                "daily_limit": daily['limit']
            }
        )
        print(
            f"[LLM] OpenAI 호출: tokens={tokens_used}, "
            f"누적={daily['tokens']}/{daily['limit']} ({daily['percent']:.1f}%)"
        )
        
        return result
        
    except json.JSONDecodeError as e:
        logger.error(f"JSON 파싱 실패: {e}")
        raise ValueError(f"LLM 응답 JSON 파싱 실패: {e}")
    except Exception as e:
        logger.error(f"OpenAI API 호출 실패: {e}", exc_info=True)
        raise
