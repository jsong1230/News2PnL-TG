"""로깅 및 성능 측정 유틸리티"""
import logging
import time
import json
import sys
from datetime import datetime
from typing import Optional, Dict, List, Any
from contextlib import contextmanager

from src.config import LOG_FORMAT, LOG_LEVEL

class JsonFormatter(logging.Formatter):
    """JSON 로그 포매터"""
    def format(self, record):
        log_obj = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        
        # extra 데이터 포함
        if hasattr(record, "extra_data"):
            log_obj.update(record.extra_data)
        
        return json.dumps(log_obj, ensure_ascii=False)

class PerformanceTracker:
    """성능 측정 및 통계 추적 클래스"""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(PerformanceTracker, cls).__new__(cls)
            cls._instance.metrics = []
        return cls._instance
    
    def add_metric(self, component: str, duration: float, metadata: Optional[Dict] = None):
        metric = {
            "component": component,
            "duration": duration,
            "timestamp": datetime.now().isoformat(),
        }
        if metadata:
            metric.update(metadata)
        self.metrics.append(metric)
    
    def get_summary(self) -> str:
        if not self.metrics:
            return "측정된 성능 지표가 없습니다."
        
        summary = ["\n=== 성능 통계 요약 ==="]
        # 컴포넌트별 합계 및 평균 계산
        stats = {}
        for m in self.metrics:
            comp = m["component"]
            if comp not in stats:
                stats[comp] = []
            stats[comp].append(m["duration"])
        
        total_time = 0
        for comp, durations in stats.items():
            total = sum(durations)
            avg = total / len(durations)
            count = len(durations)
            summary.append(f"• {comp}: 총 {total:.2f}s (평균 {avg:.2f}s, {count}회)")
            total_time += total
        
        summary.append(f"----------------------")
        summary.append(f"전체 측정 소요 시간: {total_time:.2f}s")
        return "\n".join(summary)

def setup_logging():
    """로깅 초기 설정"""
    root_logger = logging.getLogger()
    
    # 이미 설정되어 있으면 스킵
    if root_logger.handlers:
        return
        
    root_logger.setLevel(LOG_LEVEL)
    
    handler = logging.StreamHandler(sys.stdout)
    
    if LOG_FORMAT == "json":
        formatter = JsonFormatter(datefmt="%Y-%m-%dT%H:%M:%S")
    else:
        formatter = logging.Formatter(
            '[%(levelname)s] %(asctime)s [%(name)s] %(message)s',
            datefmt="%Y-%m-%d %H:%M:%S"
        )
    
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)
    
    # 외부 라이브러리 로그 레벨 조정
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("yfinance").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)

@contextmanager
def track_performance(component: str, metadata: Optional[Dict] = None):
    """성능 측정을 위한 컨텍스트 매니저"""
    start_time = time.time()
    logger = logging.getLogger(f"perf.{component}")
    
    try:
        yield
    finally:
        duration = time.time() - start_time
        PerformanceTracker().add_metric(component, duration, metadata)
        
        # 구조화된 로그 기록
        extra = {"component": component, "duration": duration}
        if metadata:
            extra.update(metadata)
            
        if LOG_FORMAT == "json":
            logger.info(f"{component} completed", extra={"extra_data": extra})
        else:
            logger.info(f"{component} 소요 시간: {duration:.2f}s")

def log_with_extra(logger, level, msg, extra_data: Dict[str, Any]):
    """메타데이터와 함께 로그 기록 (JSON 모드 최적화)"""
    if LOG_FORMAT == "json":
        logger.log(level, msg, extra={"extra_data": extra_data})
    else:
        meta_str = " ".join([f"{k}={v}" for k, v in extra_data.items()])
        logger.log(level, f"{msg} ({meta_str})")
