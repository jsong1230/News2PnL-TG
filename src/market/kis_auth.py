"""한국투자증권(KIS) API 인증 및 토큰 관리 모듈"""
import json
import logging
import time
from pathlib import Path
from typing import Optional, Dict, Any

import requests

from src.config import KIS_APP_KEY, KIS_APP_SECRET, KIS_CANOE

logger = logging.getLogger(__name__)

# 토큰 캐시 파일 경로
TOKEN_CACHE_PATH = Path(__file__).parent.parent.parent / ".kis_token_cache.json"

def get_kis_base_url() -> str:
    """KIS API 베이스 URL 반환"""
    if KIS_CANOE == "real":
        return "https://openapi.koreainvestment.com:9443"
    else:
        return "https://openapivts.koreainvestment.com:29443"

def _issue_new_token() -> Optional[Dict[str, Any]]:
    """새로운 접근 토큰 발급"""
    if not KIS_APP_KEY or not KIS_APP_SECRET:
        logger.error("KIS_APP_KEY 또는 KIS_APP_SECRET이 설정되지 않았습니다.")
        return None

    url = f"{get_kis_base_url()}/oauth2/tokenP"
    payload = {
        "grant_type": "client_credentials",
        "appkey": KIS_APP_KEY,
        "appsecret": KIS_APP_SECRET
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if "access_token" in data:
            # 보수적으로 1시간 일찍 만료되는 것으로 계산 (보통 24시간)
            data["expires_at"] = time.time() + data.get("expires_in", 86400) - 3600
            
            # 캐시에 저장
            try:
                with open(TOKEN_CACHE_PATH, "w") as f:
                    json.dump(data, f)
            except Exception as e:
                logger.warning(f"토큰 캐시 저장 실패: {e}")
                
            return data
        else:
            logger.error(f"토큰 발급 응답에 access_token 없음: {data}")
            return None
            
    except Exception as e:
        logger.error(f"KIS 토큰 발급 중 오류 발생: {e}")
        return None

def get_access_token() -> Optional[str]:
    """
    유효한 접근 토큰 반환 (캐시 확인 및 필요 시 재발급)
    """
    # 1. 캐시 확인
    if TOKEN_CACHE_PATH.exists():
        try:
            with open(TOKEN_CACHE_PATH, "r") as f:
                data = json.load(f)
                
            # 만료 여부 확인
            if data.get("expires_at", 0) > time.time():
                return data.get("access_token")
            else:
                logger.info("KIS 접근 토큰 만료됨. 재발급 진행.")
        except Exception as e:
            logger.debug(f"토큰 캐시 읽기 실패: {e}")
            
    # 2. 신규 발급
    token_data = _issue_new_token()
    if token_data:
        return token_data.get("access_token")
    
    return None

def get_kis_headers(tr_id: Optional[str] = None) -> Dict[str, str]:
    """KIS API 공통 헤더 생성"""
    token = get_access_token()
    if not token:
        return {}
        
    headers = {
        "Content-Type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": KIS_APP_KEY,
        "appsecret": KIS_APP_SECRET,
    }
    
    if tr_id:
        headers["tr_id"] = tr_id
        
    return headers
