"""날짜 유틸리티 모듈"""
from datetime import datetime, timedelta
from typing import Optional
import pytz

# KST 타임존
KST = pytz.timezone("Asia/Seoul")


def get_kst_now() -> datetime:
    """현재 KST 시간 반환"""
    return datetime.now(KST)


def get_kst_date() -> str:
    """현재 KST 날짜 반환 (YYYY-MM-DD)"""
    return get_kst_now().strftime("%Y-%m-%d")


def get_kst_datetime() -> str:
    """현재 KST 날짜시간 반환 (YYYY-MM-DD HH:MM:SS)"""
    return get_kst_now().strftime("%Y-%m-%d %H:%M:%S")


def is_weekday(date: Optional[datetime] = None) -> bool:
    """평일 여부 확인"""
    if date is None:
        date = get_kst_now()
    # KST로 변환
    if date.tzinfo is None:
        date = KST.localize(date)
    elif date.tzinfo != KST:
        date = date.astimezone(KST)
    
    # 월요일=0, 일요일=6
    return date.weekday() < 5


def get_yesterday_kst() -> str:
    """어제 날짜 반환 (YYYY-MM-DD)"""
    yesterday = get_kst_now() - timedelta(days=1)
    return yesterday.strftime("%Y-%m-%d")


def get_last_month_end() -> datetime:
    """지난 달 마지막 날 반환"""
    now = get_kst_now()
    # 이번 달 1일
    first_day = now.replace(day=1)
    # 지난 달 마지막 날
    last_month_end = first_day - timedelta(days=1)
    return last_month_end


def get_month_range(year: int, month: int) -> tuple[datetime, datetime]:
    """
    특정 월의 시작일과 종료일 반환
    
    Args:
        year: 연도
        month: 월 (1-12)
    
    Returns:
        (시작일, 종료일) 튜플 (둘 다 KST, 시작일 00:00:00, 종료일 23:59:59)
    """
    from calendar import monthrange
    
    # 시작일: 해당 월 1일 00:00:00
    start_dt = KST.localize(datetime(year, month, 1, 0, 0, 0))
    
    # 종료일: 해당 월 말일 23:59:59
    _, last_day = monthrange(year, month)
    end_dt = KST.localize(datetime(year, month, last_day, 23, 59, 59))
    
    return (start_dt, end_dt)


def get_current_month_range() -> tuple[datetime, datetime]:
    """
    현재 월의 시작일과 종료일 반환
    
    Returns:
        (시작일, 종료일) 튜플 (둘 다 KST)
    """
    now = get_kst_now()
    return get_month_range(now.year, now.month)


def is_month_end(date: Optional[datetime] = None) -> bool:
    """월말 여부 확인"""
    if date is None:
        date = get_kst_now()
    # KST로 변환
    if date.tzinfo is None:
        date = KST.localize(date)
    elif date.tzinfo != KST:
        date = date.astimezone(KST)
    
    # 다음 날이 다음 달 1일인지 확인
    next_day = date + timedelta(days=1)
    return next_day.day == 1


def get_news_window_strict(now_kst: datetime) -> tuple[datetime, datetime]:
    """
    뉴스 수집 시간 윈도우 (strict 모드)
    
    Args:
        now_kst: 현재 KST 시간
    
    Returns:
        (start_dt, end_dt) 튜플 (둘 다 KST)
        - start_dt: 전날 18:00 KST
        - end_dt: 오늘 08:00 KST
    """
    # KST로 변환
    if now_kst.tzinfo is None:
        now_kst = KST.localize(now_kst)
    elif now_kst.tzinfo != KST:
        now_kst = now_kst.astimezone(KST)
    
    # 오늘 00:00:00
    today_start = now_kst.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # 전날 18:00
    yesterday = today_start - timedelta(days=1)
    start_dt = yesterday.replace(hour=18, minute=0, second=0, microsecond=0)
    
    # 오늘 08:00
    end_dt = today_start.replace(hour=8, minute=0, second=0, microsecond=0)
    
    return (start_dt, end_dt)


def get_news_window_now(now_kst: datetime, lookback_hours: int = 24) -> tuple[datetime, datetime]:
    """
    뉴스 수집 시간 윈도우 (now 모드)
    
    Args:
        now_kst: 현재 KST 시간
        lookback_hours: lookback 시간 (시간 단위, 기본값 24)
    
    Returns:
        (start_dt, end_dt) 튜플 (둘 다 KST)
        - start_dt: (now - lookback_hours) KST
        - end_dt: 현재 시각 KST
    """
    from src.config import NEWS_LOOKBACK_HOURS
    
    if lookback_hours is None:
        lookback_hours = NEWS_LOOKBACK_HOURS
    
    # KST로 변환
    if now_kst.tzinfo is None:
        now_kst = KST.localize(now_kst)
    elif now_kst.tzinfo != KST:
        now_kst = now_kst.astimezone(KST)
    
    # 현재 시각
    end_dt = now_kst
    
    # lookback 시간 전
    start_dt = end_dt - timedelta(hours=lookback_hours)
    
    return (start_dt, end_dt)


def get_news_window(now_kst: Optional[datetime] = None, mode: Optional[str] = None, lookback_hours: Optional[int] = None) -> tuple[datetime, datetime, str, int]:
    """
    뉴스 수집 시간 윈도우 라우터 함수
    
    Args:
        now_kst: 현재 KST 시간 (None이면 get_kst_now())
        mode: "strict" 또는 "now" (None이면 config에서 읽음)
        lookback_hours: now 모드에서 lookback 시간 (None이면 config에서 읽음)
    
    Returns:
        (start_dt, end_dt, mode, lookback_hours) 튜플 (둘 다 KST, mode는 "strict" 또는 "now")
    """
    from src.config import NEWS_WINDOW_MODE, NEWS_LOOKBACK_HOURS
    
    if now_kst is None:
        now_kst = get_kst_now()
    
    if mode is None:
        mode = NEWS_WINDOW_MODE
    
    if lookback_hours is None:
        lookback_hours = NEWS_LOOKBACK_HOURS
    
    # 모드 검증
    if mode not in ["strict", "now"]:
        import logging
        logging.warning(f"잘못된 mode 값: {mode}, 'strict'로 fallback")
        mode = "strict"
    
    if mode == "now":
        start_dt, end_dt = get_news_window_now(now_kst, lookback_hours)
    else:
        start_dt, end_dt = get_news_window_strict(now_kst)
        mode = "strict"
        lookback_hours = None  # strict 모드는 lookback_hours 없음
    
    return (start_dt, end_dt, mode, lookback_hours)


def get_last_night_range(report_time: Optional[datetime] = None) -> tuple[datetime, datetime]:
    """
    지난 밤 범위 계산 (오전 리포트용, 하위 호환)
    
    예: 오늘 08:00 KST 기준이면 전날 18:00 ~ 오늘 08:00
    
    Args:
        report_time: 리포트 생성 시간 (None이면 현재 KST)
    
    Returns:
        (start_dt, end_dt) 튜플 (둘 다 KST)
    """
    start_dt, end_dt, _, _ = get_news_window(report_time, mode="strict")
    return (start_dt, end_dt)
