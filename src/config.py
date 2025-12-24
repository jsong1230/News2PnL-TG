"""설정 관리 모듈"""
import os
from pathlib import Path
from dotenv import load_dotenv

# .env 파일 로드
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

# 텔레그램 설정
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# 데이터 소스 설정
NEWS_PROVIDER = os.getenv("NEWS_PROVIDER", "dummy")
MARKET_PROVIDER = os.getenv("MARKET_PROVIDER", "dummy")
GOOGLE_NEWS_QUERY = os.getenv("GOOGLE_NEWS_QUERY", "한국 주식 시장")  # 단일 쿼리 (하위 호환)
GOOGLE_NEWS_QUERIES = os.getenv("GOOGLE_NEWS_QUERIES", "").strip()  # 여러 쿼리 (쉼표 구분)
GOOGLE_NEWS_MAX_PER_QUERY = int(os.getenv("GOOGLE_NEWS_MAX_PER_QUERY", "30"))  # 쿼리별 최대 수집 개수 (기본값 30으로 상향)

# 기본 쿼리 세트 (GOOGLE_NEWS_QUERIES가 비어있을 때 사용)
DEFAULT_NEWS_QUERIES = [
    "미국 증시", "나스닥", "S&P500", "연준 금리", "달러 환율", "유가",
    "엔비디아", "반도체", "AI", "비트코인", "한국 증시", "외국인 수급",
    "삼성전자", "SK하이닉스"
]

# 뉴스 시간 윈도우 모드
# "strict": 전날 18:00 ~ 오늘 08:00 KST (운영 모드, GitHub Actions 기본)
# "now": (now - NEWS_LOOKBACK_HOURS) ~ now KST (개발/디버그 모드)
_news_window_mode_raw = os.getenv("NEWS_WINDOW_MODE", "strict").lower()
if _news_window_mode_raw not in ["strict", "now"]:
    import logging
    logging.warning(f"잘못된 NEWS_WINDOW_MODE 값: {_news_window_mode_raw}, 'strict'로 fallback")
    NEWS_WINDOW_MODE = "strict"
else:
    NEWS_WINDOW_MODE = _news_window_mode_raw

# now 모드에서 lookback 시간 (시간 단위, 기본값 24)
NEWS_LOOKBACK_HOURS = int(os.getenv("NEWS_LOOKBACK_HOURS", "24"))

# 가정 투자 금액 (원)
PAPER_TRADE_AMOUNT = int(os.getenv("PAPER_TRADE_AMOUNT", "10000000"))

# 관찰 리스트 (선택사항, 쉼표 구분)
WATCHLIST_KR = os.getenv("WATCHLIST_KR", "").strip()
if WATCHLIST_KR:
    WATCHLIST_KR = [name.strip() for name in WATCHLIST_KR.split(",") if name.strip()]
else:
    WATCHLIST_KR = []

# 월간 리포트 월 오버라이드 (개발용, YYYY-MM 형식)
MONTH_OVERRIDE = os.getenv("MONTH_OVERRIDE", "").strip()

# 월간 리포트에 dummy provider 거래 포함 여부 (기본: False, yahoo만)
MONTHLY_INCLUDE_DUMMY = os.getenv("MONTHLY_INCLUDE_DUMMY", "false").lower() == "true"

# 텔레그램 전송 실패 시 워크플로우 실패 여부 (기본: False, warning만)
TELEGRAM_REQUIRED = os.getenv("TELEGRAM_REQUIRED", "false").lower() == "true"

# DB 경로
DB_PATH = Path(__file__).parent.parent / "db" / "market.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# 스키마 경로
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def validate_config():
    """설정 검증"""
    errors = []
    
    # 텔레그램 설정은 선택사항 (dry-run 모드 지원)
    # if not TELEGRAM_BOT_TOKEN:
    #     errors.append("TELEGRAM_BOT_TOKEN이 설정되지 않았습니다 (dry-run 모드로 실행됩니다)")
    
    if PAPER_TRADE_AMOUNT <= 0:
        errors.append("PAPER_TRADE_AMOUNT은 0보다 커야 합니다")
    
    if errors:
        raise ValueError("설정 오류:\n" + "\n".join(f"  - {e}" for e in errors))
    
    return True


def is_dry_run():
    """dry-run 모드 여부 확인"""
    return not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID

