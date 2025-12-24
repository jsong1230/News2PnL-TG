"""텔레그램 메시지 전송 모듈 (requests 기반 동기 API)"""
import logging
import time
from typing import Optional

import requests

from src.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, is_dry_run, TELEGRAM_REQUIRED

logger = logging.getLogger(__name__)

# 텔레그램 메시지 최대 길이 (4096자)
MAX_MESSAGE_LENGTH = 4096
# 텔레그램 Bot API 기본 URL
TELEGRAM_API_BASE = "https://api.telegram.org/bot"
# 재시도 횟수 (rate limit 대비)
MAX_RETRIES = 2
# 재시도 간격 (초)
RETRY_DELAY = 2
# 타임아웃 (초)
TIMEOUT = 10


def split_message(text: str, max_length: int = MAX_MESSAGE_LENGTH) -> list[str]:
    """긴 메시지를 여러 개로 분할"""
    if len(text) <= max_length:
        return [text]
    
    messages = []
    lines = text.split("\n")
    current_message = ""
    
    for line in lines:
        if len(current_message) + len(line) + 1 > max_length:
            if current_message:
                messages.append(current_message)
                current_message = ""
            # 한 줄이 너무 길면 강제로 자름
            if len(line) > max_length:
                while len(line) > max_length:
                    messages.append(line[:max_length])
                    line = line[max_length:]
                current_message = line
            else:
                current_message = line
        else:
            current_message += "\n" + line if current_message else line
    
    if current_message:
        messages.append(current_message)
    
    return messages


def send_message(text: str, parse_mode: Optional[str] = "Markdown") -> bool:
    """
    텔레그램 메시지 전송 (동기 API)
    
    Args:
        text: 전송할 메시지
        parse_mode: 파싱 모드 (Markdown, HTML, None)
    
    Returns:
        전송 성공 여부
    """
    if is_dry_run():
        print("=" * 60)
        print("[DRY-RUN] 텔레그램 메시지 (전송하지 않음):")
        print("=" * 60)
        print(text)
        print("=" * 60)
        return True
    
    # 토큰이 없거나 기본값인 경우 dry-run
    if (not TELEGRAM_BOT_TOKEN or 
        not TELEGRAM_CHAT_ID or 
        TELEGRAM_BOT_TOKEN == "your_bot_token_here" or
        TELEGRAM_CHAT_ID == "your_chat_id_here"):
        logger.warning("텔레그램 토큰 또는 채팅 ID가 설정되지 않았습니다 (dry-run 모드)")
        print("=" * 60)
        print("[DRY-RUN] 텔레그램 메시지 (전송하지 않음):")
        print("=" * 60)
        print(text)
        print("=" * 60)
        return True
    
    messages = split_message(text)
    api_url = f"{TELEGRAM_API_BASE}{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    for i, msg in enumerate(messages, 1):
        if len(messages) > 1:
            header = f"*[메시지 {i}/{len(messages)}]*\n\n"
            msg = header + msg
        
        # 재시도 로직
        success = False
        last_error = None
        
        for attempt in range(MAX_RETRIES):
            try:
                payload = {
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": msg,
                }
                
                if parse_mode:
                    payload["parse_mode"] = parse_mode
                
                response = requests.post(
                    api_url,
                    json=payload,
                    timeout=TIMEOUT
                )
                
                # 400 Bad Request 등의 상세 정보 로깅
                if response.status_code == 400:
                    try:
                        error_json = response.json()
                        error_desc = error_json.get("description", "")
                        logger.error(f"텔레그램 API 400 에러 상세: {error_desc}")
                        print(f"⚠️  텔레그램 API 400 에러: {error_desc}")
                    except:
                        pass
                
                response.raise_for_status()
                
                result = response.json()
                if result.get("ok"):
                    logger.info(f"텔레그램 메시지 전송 완료 ({i}/{len(messages)})")
                    print(f"✓ 텔레그램 메시지 전송 완료 ({i}/{len(messages)})")
                    success = True
                    break
                else:
                    error_desc = result.get("description", "Unknown error")
                    raise Exception(f"Telegram API error: {error_desc}")
            
            except requests.exceptions.Timeout:
                last_error = f"타임아웃 (시도 {attempt + 1}/{MAX_RETRIES})"
                logger.warning(last_error)
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY)  # 2초 대기 후 재시도
            
            except requests.exceptions.RequestException as e:
                # 400 Bad Request 등의 상세 정보 추출
                error_detail = str(e)
                if hasattr(e, 'response') and e.response is not None:
                    try:
                        error_json = e.response.json()
                        error_desc = error_json.get("description", "")
                        error_code = error_json.get("error_code", "")
                        if error_desc:
                            error_detail = f"{error_detail} - {error_desc}"
                        if error_code:
                            error_detail = f"{error_detail} (code: {error_code})"
                    except:
                        pass
                last_error = f"네트워크 오류: {error_detail}"
                logger.warning(f"{last_error} (시도 {attempt + 1}/{MAX_RETRIES})")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY)  # 2초 대기 후 재시도
            
            except Exception as e:
                last_error = f"예상치 못한 오류: {e}"
                logger.error(last_error, exc_info=True)
                break
        
        if not success:
            error_msg = f"텔레그램 메시지 전송 실패 ({i}/{len(messages)}): {last_error}"
            logger.error(error_msg)
            print(f"✗ {error_msg}")
            if TELEGRAM_REQUIRED:
                raise Exception(error_msg)
            return False
    
    print("✓ 모든 텔레그램 메시지 전송 완료")
    return True


def send_error_notification(error: Exception, context: str = "") -> bool:
    """에러 알림 메시지 전송"""
    error_msg = f"*⚠️ 에러 발생*\n\n"
    error_msg += f"*컨텍스트:* {context}\n\n"
    error_msg += f"*에러:* `{type(error).__name__}`\n"
    error_msg += f"*메시지:* {str(error)}\n"
    
    return send_message(error_msg)
