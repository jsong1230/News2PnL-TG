"""종목 선정 로직 (뉴스 기반 관찰 리스트 생성)"""
from typing import List, Dict, Tuple, Optional, Any
from dataclasses import dataclass, asdict
import logging
import json

from src.news.base import NewsItem
from src.analysis.news_analyzer import NewsDigest, classify_sector
from src.data.kr_symbols import (
    KR_SYMBOLS, 
    find_symbols_in_text, 
    get_foreign_substitute_symbols,
    get_symbol_code
)
from src.config import WATCHLIST_KR, LLM_ENABLED, LLM_MODEL
from src.llm.client import generate_json

logger = logging.getLogger(__name__)


@dataclass
class WatchStock:
    """관찰 종목 정보"""
    name: str  # 종목명
    code: str  # 종목코드
    thesis: str  # 한 줄 thesis (왜 오늘 관찰?)
    catalysts: List[str]  # 관련 뉴스 제목 1~2개
    risks: List[str]  # 리스크 2개
    trigger: str  # 관찰 트리거
    checklist_scores: Dict[str, int]  # 체크리스트 점수 (총 12점)
    total_score: int  # 총점
    confidence: str  # 확신도: "상" | "중" | "하"
    confidence_reason: str  # 확신도 이유


def extract_stock_candidates(
    digest: NewsDigest, 
    news_items: List[NewsItem],
    overnight_signals: Optional[Dict] = None
) -> Dict[str, int]:
    """
    뉴스 다이제스트에서 종목 후보 추출 및 점수 계산
    
    Args:
        digest: 뉴스 다이제스트
        news_items: 뉴스 아이템 리스트
        overnight_signals: 오버나이트 선행 신호 (선택사항)
    
    Returns:
        {종목명: 점수} 딕셔너리
    """
    scores: Dict[str, int] = {}
    
    # 전체 텍스트 수집
    all_text = " ".join(digest.top_headlines)
    all_text += " " + " ".join([bullet for bullets in digest.sector_bullets.values() for bullet in bullets])
    
    # 헤드라인에서 종목명 찾기
    for headline in digest.top_headlines:
        found_symbols = find_symbols_in_text(headline)
        for symbol_name, code in found_symbols.items():
            if symbol_name not in scores:
                scores[symbol_name] = 0
            scores[symbol_name] += 3  # 헤드라인 직접 언급: +3
    
    # 섹터 bullets에서 종목명 찾기
    for bullets in digest.sector_bullets.values():
        for bullet in bullets:
            found_symbols = find_symbols_in_text(bullet)
            for symbol_name, code in found_symbols.items():
                if symbol_name not in scores:
                    scores[symbol_name] = 0
                scores[symbol_name] += 2  # 섹터 bullet 언급: +2
    
    # WATCHLIST_KR에 있는 종목 가중치 추가
    for watch_name in WATCHLIST_KR:
        if watch_name in scores:
            scores[watch_name] += 2  # WATCHLIST_KR 포함: +2
        else:
            # WATCHLIST_KR에 있지만 아직 언급되지 않은 경우
            code = get_symbol_code(watch_name)
            if code:
                scores[watch_name] = 2  # 기본 점수 부여
    
    # 해외 종목 → 한국 대체 종목 매핑
    all_text_lower = all_text.lower()
    for foreign_name, kr_substitutes in [
        ("엔비디아", ["삼성전자", "SK하이닉스"]),
        ("nvidia", ["삼성전자", "SK하이닉스"]),
        ("amd", ["삼성전자", "SK하이닉스"]),
        ("테슬라", ["LG에너지솔루션", "삼성SDI"]),
        ("tesla", ["LG에너지솔루션", "삼성SDI"]),
    ]:
        if foreign_name in all_text_lower:
            for kr_name in kr_substitutes:
                if kr_name not in scores:
                    scores[kr_name] = 0
                scores[kr_name] += 1  # 해외 종목 관련: +1
    
    # 오버나이트 선행 신호 기반 점수 조정
    if overnight_signals:
        # 반도체/AI 섹터: Nasdaq/NVDA 강하면 가점
        nvda = overnight_signals.get("NVDA")
        nasdaq = overnight_signals.get("Nasdaq")
        
        if nvda and nvda.success and nvda.pct_change:
            if nvda.pct_change > 1.0:  # NVDA +1% 이상
                for kr_name in ["삼성전자", "SK하이닉스"]:
                    if kr_name not in scores:
                        scores[kr_name] = 0
                    scores[kr_name] += 2  # NVDA 강세: +2
        
        if nasdaq and nasdaq.success and nasdaq.pct_change:
            if nasdaq.pct_change > 0.5:  # Nasdaq +0.5% 이상
                for kr_name in ["삼성전자", "SK하이닉스"]:
                    if kr_name not in scores:
                        scores[kr_name] = 0
                    scores[kr_name] += 1  # Nasdaq 강세: +1
        
        # 코인 관련: BTC 강하면 가점
        btc = overnight_signals.get("BTC")
        if btc and btc.success and btc.pct_change:
            if btc.pct_change > 2.0:  # BTC +2% 이상
                # 코인 관련 종목이 있으면 가점 (현재는 없지만 향후 확장 가능)
                pass
        
        # Risk-off 환경: 고변동 종목 감점
        from src.market.overnight import assess_market_tone
        market_tone = assess_market_tone(overnight_signals)
        if market_tone == "risk_off":
            # 고변동 종목 감점 (예: 2차전지, 바이오 등)
            high_volatility_stocks = ["LG에너지솔루션", "삼성SDI", "셀트리온"]
            for stock_name in high_volatility_stocks:
                if stock_name in scores:
                    scores[stock_name] = max(0, scores[stock_name] - 1)  # -1 감점
    
    return scores


def calculate_checklist_score(stock_name: str, has_catalyst: bool) -> Tuple[Dict[str, int], int]:
    """
    6단계 체크리스트 점수 계산
    
    Args:
        stock_name: 종목명
        has_catalyst: 뉴스 catalyst가 있는지 여부
    
    Returns:
        (체크리스트 점수 딕셔너리, 총점) 튜플
    """
    scores = {}
    
    # 1) 내가 아는 회사인가?
    if stock_name in WATCHLIST_KR:
        scores["내가 아는 회사"] = 2
    else:
        scores["내가 아는 회사"] = 1
    
    # 2) 비즈니스 설명 가능?
    if stock_name in KR_SYMBOLS:
        scores["비즈니스 설명 가능"] = 2
    else:
        scores["비즈니스 설명 가능"] = 1
    
    # 3) 3년간 실적 성장?
    scores["3년간 실적 성장"] = 1  # 데이터 없으므로 기본 1점
    
    # 4) PER 10~20?
    scores["PER 10~20"] = 1  # 데이터 없으므로 기본 1점
    
    # 5) 부채비율 100% 이하?
    scores["부채비율 100% 이하"] = 1  # 데이터 없으므로 기본 1점
    
    # 6) 살 이유가 명확한가?
    if has_catalyst:
        scores["살 이유 명확"] = 2
    else:
        scores["살 이유 명확"] = 1
    
    total = sum(scores.values())
    return (scores, total)


def assess_confidence(total_score: int, has_catalyst: bool, in_watchlist: bool) -> Tuple[str, str]:
    """
    확신도 평가
    
    Args:
        total_score: 체크리스트 총점
        has_catalyst: 뉴스 catalyst가 있는지
        in_watchlist: WATCHLIST_KR에 있는지
    
    Returns:
        (확신도, 이유) 튜플
    """
    if total_score >= 10 and has_catalyst and in_watchlist:
        return ("상", "체크리스트 점수 높음 + catalyst + 관찰 리스트 포함")
    elif total_score >= 8 and has_catalyst:
        return ("중", "체크리스트 점수 양호 + catalyst 존재")
    elif total_score >= 8:
        return ("중", "체크리스트 점수 양호")
    else:
        return ("하", "체크리스트 점수 낮음 또는 catalyst 부족")


def generate_risks(stock_name: str) -> List[str]:
    """
    기본 리스크 생성 (초기 버전)
    
    Args:
        stock_name: 종목명
    
    Returns:
        리스크 리스트 (2개)
    """
    # 기본 리스크 템플릿
    risks = [
        "시장 변동성 및 리스크 존재",
        "재무데이터 확인 필요 (PER, 부채비율 등)"
    ]
    
    # 종목별 특화 리스크
    if "반도체" in stock_name or stock_name in ["삼성전자", "SK하이닉스"]:
        risks[0] = "반도체 업황 사이클 변동성"
    elif "2차전지" in stock_name or "배터리" in stock_name:
        risks[0] = "전기차 수요 변동성 및 원자재 가격 변동"
    elif "바이오" in stock_name or "제약" in stock_name:
        risks[0] = "신약 개발 및 규제 승인 불확실성"
    
    return risks


def generate_trigger(stock_name: str) -> str:
    """
    관찰 트리거 생성
    
    Args:
        stock_name: 종목명
    
    Returns:
        관찰 트리거 텍스트
    """
    return "갭상승 시 추격 금지, 변동성 확인 후 관찰"


def create_stock_candidates(
    digest: NewsDigest,
    news_items: List[NewsItem],
    max_candidates: int = 15,
    overnight_signals: Optional[Dict] = None
) -> List[Dict[str, Any]]:
    """
    LLM 입력을 위한 후보 종목 리스트 생성 (8~15개)
    
    Args:
        digest: 뉴스 다이제스트
        news_items: 뉴스 아이템 리스트
        max_candidates: 최대 후보 수
        overnight_signals: 오버나이트 선행 신호 (선택사항)
    
    Returns:
        후보 종목 리스트 [{name, code, score, matched_headlines, sector}]
    """
    # 1. 후보 종목 추출 및 점수 계산
    candidate_scores = extract_stock_candidates(digest, news_items, overnight_signals=overnight_signals)
    
    if not candidate_scores:
        # 후보가 없으면 섹터 대표주로 fallback
        fallback_stocks = ["삼성전자", "SK하이닉스", "LG에너지솔루션"]
        for stock_name in fallback_stocks:
            code = get_symbol_code(stock_name)
            if code:
                candidate_scores[stock_name] = 1
                break
    
    # 2. 점수 상위 종목 선택 (중복 종목코드 제거)
    sorted_candidates = sorted(candidate_scores.items(), key=lambda x: x[1], reverse=True)
    
    # 종목코드 기준으로 중복 제거
    seen_codes = set()
    candidates = []
    
    for stock_name, score in sorted_candidates:
        code = get_symbol_code(stock_name)
        if not code or code in seen_codes:
            continue
        
        seen_codes.add(code)
        
        # 관련 헤드라인 찾기 (최대 3개)
        matched_headlines = []
        for headline in digest.top_headlines:
            if stock_name in headline or stock_name.lower() in headline.lower():
                matched_headlines.append(headline)
                if len(matched_headlines) >= 3:
                    break
        
        # 섹터 분류
        sector = None
        for headline in matched_headlines:
            sector = classify_sector(headline, "")
            if sector:
                break
        
        # 섹터 bullets에서도 확인
        if not sector:
            for bullets in digest.sector_bullets.values():
                for bullet in bullets:
                    if stock_name in bullet:
                        sector = classify_sector(bullet, "")
                        if sector:
                            break
                if sector:
                    break
        
        candidates.append({
            "name": stock_name,
            "code": code,
            "score": score,
            "matched_headlines": matched_headlines[:3],
            "sector": sector
        })
        
        if len(candidates) >= max_candidates:
            break
    
    return candidates


def get_stock_selection_json_schema() -> Dict[str, Any]:
    """
    LLM 출력을 위한 JSON Schema (Structured Outputs)
    
    Returns:
        JSON Schema 딕셔너리
    """
    return {
        "type": "object",
        "properties": {
            "selected": {
                "type": "array",
                "minItems": 1,
                "maxItems": 3,
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "code": {"type": "string"},
                        "confidence": {"type": "string", "enum": ["low", "mid", "high"]},
                        "thesis": {"type": "string"},
                        "catalyst": {
                            "type": "array",
                            "maxItems": 2,
                            "items": {"type": "string"}
                        },
                        "risks": {
                            "type": "array",
                            "minItems": 2,
                            "maxItems": 2,
                            "items": {"type": "string"}
                        },
                        "watch_trigger": {"type": "string"},
                        "checklist": {
                            "type": "object",
                            "properties": {
                                "known_company": {"type": "integer", "minimum": 0, "maximum": 2},
                                "business_explainable": {"type": "integer", "minimum": 0, "maximum": 2},
                                "growth_3y": {"type": "integer", "minimum": 0, "maximum": 2},
                                "per_10_20": {"type": "integer", "minimum": 0, "maximum": 2},
                                "debt_lt_100": {"type": "integer", "minimum": 0, "maximum": 2},
                                "clear_reason": {"type": "integer", "minimum": 0, "maximum": 2}
                            },
                            "required": ["known_company", "business_explainable", "growth_3y", "per_10_20", "debt_lt_100", "clear_reason"]
                        },
                        "must_use_news_refs": {
                            "type": "array",
                            "items": {"type": "integer"}
                        }
                    },
                    "required": ["name", "code", "confidence", "thesis", "catalyst", "risks", "watch_trigger", "checklist"]
                }
            },
            "meta": {
                "type": "object",
                "properties": {
                    "policy": {"type": "string"},
                    "notes": {"type": "string"}
                },
                "required": ["policy", "notes"]
            }
        },
        "required": ["selected", "meta"]
    }


def create_llm_prompt(
    date_str: str,
    digest: NewsDigest,
    candidates: List[Dict[str, Any]]
) -> Tuple[str, str]:
    """
    LLM 프롬프트 생성
    
    Args:
        date_str: 날짜 문자열 (YYYY-MM-DD)
        digest: 뉴스 다이제스트
        candidates: 후보 종목 리스트
    
    Returns:
        (system_prompt, user_prompt) 튜플
    """
    system_prompt = """너는 투자 권유가 아닌 교육용 리서치 요약가입니다.

핵심 정책:
1. watchlist_only_no_buy: 절대 매수 추천하지 않으며, "관찰 리스트" 톤만 사용
2. 후보 목록 밖 종목 선택 금지: 반드시 제공된 candidates 리스트 안에서만 선택
3. 출력은 오직 JSON 형식만

금지 표현:
- "매수", "목표가", "비중", "수익 보장", "확정적" 등
- 후보 목록에 없는 종목명/코드 사용

필수 표현:
- "관찰", "시나리오", "확인 필요", "변동성 주의" 등"""
    
    # 뉴스 요약 구성
    news_summary = f"""## 오늘 날짜: {date_str}

## 핵심 헤드라인 (최대 8개):
"""
    for i, headline in enumerate(digest.top_headlines[:8], 1):
        news_summary += f"{i}. {headline}\n"
    
    news_summary += "\n## 섹터별 요약:\n"
    for sector, bullets in list(digest.sector_bullets.items())[:5]:
        news_summary += f"\n### {sector}:\n"
        for bullet in bullets[:3]:
            news_summary += f"- {bullet}\n"
    
    news_summary += f"\n## 한국장 영향: {digest.korea_impact}\n"
    news_summary += f"\n## 수집 정보: 수집={digest.fetched_count}건, 시간필터={digest.time_filtered_count}건, 중복제거={digest.deduped_count}건\n"
    
    # 후보 종목 JSON
    candidates_json = json.dumps(candidates, ensure_ascii=False, indent=2)
    
    user_prompt = f"""{news_summary}

## 후보 종목 리스트 (반드시 이 중에서만 선택):
```json
{candidates_json}
```

## 출력 요구사항:
1. selected 배열: 1~3개 종목 선택 (반드시 위 candidates의 name+code와 정확히 일치)
2. 각 종목별:
   - confidence: "low" | "mid" | "high"
   - thesis: 한 줄 (관찰 이유)
   - catalyst: 최대 2개 (관련 뉴스 요약)
   - risks: 정확히 2개 (리스크)
   - watch_trigger: 한 줄 (관찰 트리거)
   - checklist: 각 항목 0~2점 (재무데이터 연동 전이므로 가정치 가능)
   - must_use_news_refs: [0..N-1] (근거로 사용한 뉴스 헤드라인 인덱스)
3. meta.notes에 "재무데이터 연동 전 가정치 포함" 문구 포함

## 출력 JSON 스키마:
{{
  "selected": [
    {{
      "name": "종목명 (candidates와 정확히 일치)",
      "code": "종목코드 (candidates와 정확히 일치)",
      "confidence": "low|mid|high",
      "thesis": "한 줄",
      "catalyst": ["최대 2개"],
      "risks": ["정확히 2개"],
      "watch_trigger": "한 줄",
      "checklist": {{
        "known_company": 0|1|2,
        "business_explainable": 0|1|2,
        "growth_3y": 0|1|2,
        "per_10_20": 0|1|2,
        "debt_lt_100": 0|1|2,
        "clear_reason": 0|1|2
      }},
      "must_use_news_refs": [0, 1, ...]
    }}
  ],
  "meta": {{
    "policy": "watchlist_only_no_buy",
    "notes": "재무데이터 연동 전 가정치 포함"
  }}
}}"""
    
    return (system_prompt, user_prompt)


def parse_llm_response(
    llm_output: Dict[str, Any],
    candidates: List[Dict[str, Any]]
) -> Optional[List[WatchStock]]:
    """
    LLM 출력 파싱 및 검증
    
    Args:
        llm_output: LLM 출력 JSON
        candidates: 후보 종목 리스트
    
    Returns:
        WatchStock 리스트 또는 None (검증 실패 시)
    """
    try:
        if "selected" not in llm_output:
            logger.warning("LLM 출력에 'selected' 키가 없습니다")
            return None
        
        selected = llm_output["selected"]
        if not isinstance(selected, list) or len(selected) == 0 or len(selected) > 3:
            logger.warning(f"LLM 출력의 selected가 유효하지 않습니다: {len(selected) if isinstance(selected, list) else 'not list'}")
            return None
        
        # 후보 종목 매핑 (name+code로)
        candidate_map = {(c["name"], c["code"]): c for c in candidates}
        
        watch_stocks = []
        
        for item in selected:
            # 필수 필드 확인
            if "name" not in item or "code" not in item:
                logger.warning("LLM 출력에 name 또는 code가 없습니다")
                return None
            
            name = item["name"]
            code = item["code"]
            
            # 후보 목록에 있는지 확인
            if (name, code) not in candidate_map:
                logger.warning(f"LLM이 후보 목록 밖 종목을 선택했습니다: {name} ({code})")
                return None
            
            # 필수 필드 기본값 설정
            confidence = item.get("confidence", "mid")
            thesis = item.get("thesis", f"{name} 관련 관찰 필요")
            catalyst = item.get("catalyst", [])
            risks = item.get("risks", ["시장 변동성 및 리스크 존재", "재무데이터 확인 필요"])
            watch_trigger = item.get("watch_trigger", "갭상승 시 추격 금지, 변동성 확인 후 관찰")
            
            # 체크리스트 점수
            checklist_raw = item.get("checklist", {})
            checklist_scores = {
                "내가 아는 회사": checklist_raw.get("known_company", 1),
                "비즈니스 설명 가능": checklist_raw.get("business_explainable", 1),
                "3년간 실적 성장": checklist_raw.get("growth_3y", 1),
                "PER 10~20": checklist_raw.get("per_10_20", 1),
                "부채비율 100% 이하": checklist_raw.get("debt_lt_100", 1),
                "살 이유 명확": checklist_raw.get("clear_reason", 1)
            }
            total_score = sum(checklist_scores.values())
            
            # 확신도 변환 (low/mid/high -> 하/중/상)
            confidence_map = {"low": "하", "mid": "중", "high": "상"}
            confidence_kr = confidence_map.get(confidence, "중")
            confidence_reason = f"LLM 평가: {confidence}"
            
            watch_stock = WatchStock(
                name=name,
                code=code,
                thesis=thesis,
                catalysts=catalyst[:2] if catalyst else [f"{name} 관련 뉴스"],
                risks=risks[:2] if len(risks) >= 2 else risks + ["재무데이터 확인 필요"],
                trigger=watch_trigger,
                checklist_scores=checklist_scores,
                total_score=total_score,
                confidence=confidence_kr,
                confidence_reason=confidence_reason
            )
            
            watch_stocks.append(watch_stock)
        
        return watch_stocks
        
    except Exception as e:
        logger.error(f"LLM 출력 파싱 실패: {e}", exc_info=True)
        return None


def pick_watch_stocks(
    digest: NewsDigest,
    news_items: List[NewsItem],
    max_count: int = 3,
    date_str: Optional[str] = None,
    overnight_signals: Optional[Dict] = None
) -> List[WatchStock]:
    """
    관찰 종목 선정 (LLM 지원)
    
    Args:
        digest: 뉴스 다이제스트
        news_items: 뉴스 아이템 리스트
        max_count: 최대 선정 개수 (기본 3개)
        date_str: 날짜 문자열 (YYYY-MM-DD, LLM 사용 시 필요)
        overnight_signals: 오버나이트 선행 신호 (선택사항)
    
    Returns:
        관찰 종목 리스트
    """
    # 1. 후보 종목 생성 (8~15개)
    candidates = create_stock_candidates(digest, news_items, max_candidates=15, overnight_signals=overnight_signals)
    
    if not candidates:
        logger.warning("종목 후보가 없습니다")
        return []
    
    # 2. LLM 사용 시도
    if LLM_ENABLED and date_str:
        try:
            system_prompt, user_prompt = create_llm_prompt(date_str, digest, candidates)
            json_schema = get_stock_selection_json_schema()
            llm_output = generate_json(system_prompt, user_prompt, json_schema=json_schema)
            
            if llm_output:
                logger.info(f"LLM 사용: model={LLM_MODEL}")
                print(f"[LLM] 사용: model={LLM_MODEL}")
                watch_stocks = parse_llm_response(llm_output, candidates)
                
                if watch_stocks:
                    logger.info(f"LLM으로 {len(watch_stocks)}개 종목 선정 완료")
                    return watch_stocks[:max_count]
                else:
                    logger.warning("LLM 출력 검증 실패, 룰 기반으로 fallback")
            else:
                logger.warning("LLM 호출 실패, 룰 기반으로 fallback")
        except Exception as e:
            logger.warning(f"LLM 처리 중 오류 발생, 룰 기반으로 fallback: {e}")
    
    # 3. 룰 기반 fallback (기존 로직)
    logger.info("룰 기반 종목 선정 사용")
    candidate_scores = {c["name"]: c["score"] for c in candidates}
    
    # 점수 상위 종목 선택
    sorted_candidates = sorted(candidate_scores.items(), key=lambda x: x[1], reverse=True)
    
    # 종목코드 기준으로 중복 제거
    seen_codes = set()
    selected = []
    for stock_name, score in sorted_candidates:
        code = get_symbol_code(stock_name)
        if code and code not in seen_codes:
            selected.append((stock_name, score))
            seen_codes.add(code)
        if len(selected) >= max_count:
            break
    
    watch_stocks = []
    
    for stock_name, score in selected:
        code = get_symbol_code(stock_name)
        if not code:
            logger.warning(f"종목코드를 찾을 수 없음: {stock_name}")
            continue
        
        # 관련 뉴스 찾기 (더 넓은 범위에서 검색)
        catalysts = []
        
        # 해외 종목 매핑 확인 (엔비디아 → 삼성전자/SK하이닉스 등)
        foreign_substitutes = get_foreign_substitute_symbols(stock_name)
        related_stock_names = [stock_name] + foreign_substitutes
        
        # 1. news_items에서 직접 매칭 (종목명 + 해외 대체 종목)
        for item in news_items:
            title_lower = item.title.lower()
            for related_name in related_stock_names:
                related_lower = related_name.lower()
                if related_lower in title_lower or related_name in item.title:
                    catalysts.append(item.title)
                    if len(catalysts) >= 2:
                        break
            if len(catalysts) >= 2:
                break
        
        # 2. digest의 헤드라인에서도 찾기 (종목명 + 해외 대체 종목)
        if len(catalysts) < 2:
            for headline in digest.top_headlines:
                headline_lower = headline.lower()
                for related_name in related_stock_names:
                    related_lower = related_name.lower()
                    if related_lower in headline_lower or related_name in headline:
                        if headline not in catalysts:
                            catalysts.append(headline)
                            if len(catalysts) >= 2:
                                break
                if len(catalysts) >= 2:
                    break
        
        # 3. 섹터 bullets에서도 찾기 (종목명 + 해외 대체 종목)
        if len(catalysts) < 2:
            for sector, bullets in digest.sector_bullets.items():
                for bullet in bullets:
                    bullet_lower = bullet.lower()
                    for related_name in related_stock_names:
                        related_lower = related_name.lower()
                        if related_lower in bullet_lower or related_name in bullet:
                            if bullet not in catalysts:
                                catalysts.append(bullet)
                                if len(catalysts) >= 2:
                                    break
                    if len(catalysts) >= 2:
                        break
                if len(catalysts) >= 2:
                    break
        
        # 4. 해외 종목 관련 뉴스도 찾기 (역방향: 엔비디아 뉴스 → 삼성전자 Catalyst)
        if len(catalysts) < 2:
            # FOREIGN_TO_KR_MAPPING에서 이 종목이 대체 종목인 해외 종목 찾기
            from src.data.kr_symbols import FOREIGN_TO_KR_MAPPING
            for foreign_name, kr_stocks in FOREIGN_TO_KR_MAPPING.items():
                if stock_name in kr_stocks:
                    # 이 해외 종목이 언급된 뉴스 찾기
                    for item in news_items:
                        title_lower = item.title.lower()
                        foreign_lower = foreign_name.lower()
                        if foreign_lower in title_lower or foreign_name in item.title:
                            if item.title not in catalysts:
                                catalysts.append(item.title)
                                if len(catalysts) >= 2:
                                    break
                    if len(catalysts) >= 2:
                        break
                    
                    # 헤드라인에서도 찾기
                    for headline in digest.top_headlines:
                        headline_lower = headline.lower()
                        foreign_lower = foreign_name.lower()
                        if foreign_lower in headline_lower or foreign_name in headline:
                            if headline not in catalysts:
                                catalysts.append(headline)
                                if len(catalysts) >= 2:
                                    break
                    if len(catalysts) >= 2:
                        break
        
        # catalyst가 없으면 섹터 기반으로 생성
        if not catalysts:
            # 섹터 분류로 대체 메시지 생성
            sector = None
            for headline in digest.top_headlines[:5]:
                sector = classify_sector(headline, "")
                if sector and sector != "기타":
                    break
            
            if sector:
                catalysts = [f"{stock_name}, {sector} 섹터 동향"]
            else:
                catalysts = [f"{stock_name} 관련 시장 동향"]
        
        # thesis 생성 (더 구체적으로)
        if catalysts and len(catalysts) > 0:
            # 첫 번째 catalyst에서 핵심 키워드 추출
            first_catalyst = catalysts[0]
            # 간단한 요약 생성
            if "실적" in first_catalyst or "수익" in first_catalyst or "성장" in first_catalyst:
                thesis = f"{stock_name}, 실적/성장 관련 뉴스로 관찰 필요"
            elif "AI" in first_catalyst or "반도체" in first_catalyst:
                thesis = f"{stock_name}, AI/반도체 동향 관련 관찰 필요"
            elif "전기차" in first_catalyst or "배터리" in first_catalyst:
                thesis = f"{stock_name}, 전기차/배터리 동향 관련 관찰 필요"
            elif "금리" in first_catalyst or "환율" in first_catalyst:
                thesis = f"{stock_name}, 거시 환경 변화 관련 관찰 필요"
            else:
                # catalyst의 핵심 내용을 간단히 요약
                thesis = f"{stock_name}, {first_catalyst[:30]}... 관련 관찰 필요"
        else:
            thesis = f"{stock_name} 섹터 동향 관찰"
        
        # 체크리스트 점수 계산
        has_catalyst = len(catalysts) > 0
        checklist_scores, total_score = calculate_checklist_score(stock_name, has_catalyst)
        
        # 확신도 평가
        in_watchlist = stock_name in WATCHLIST_KR
        confidence, confidence_reason = assess_confidence(total_score, has_catalyst, in_watchlist)
        
        # 리스크 생성
        risks = generate_risks(stock_name)
        
        # 트리거 생성
        trigger = generate_trigger(stock_name)
        
        watch_stock = WatchStock(
            name=stock_name,
            code=code,
            thesis=thesis,
            catalysts=catalysts,
            risks=risks,
            trigger=trigger,
            checklist_scores=checklist_scores,
            total_score=total_score,
            confidence=confidence,
            confidence_reason=confidence_reason
        )
        
        watch_stocks.append(watch_stock)
    
    return watch_stocks

