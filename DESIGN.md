# News2PnL-TG 프로젝트 설계 문서

## 1. 폴더 구조

```
News2PnL-TG/
├── .github/
│   └── workflows/
│       ├── morning_report.yml      # 08:00 KST 실행
│       ├── evening_report.yml      # 16:30 KST 실행
│       └── monthly_report.yml      # 월말 실행
├── src/
│   ├── __init__.py
│   ├── config.py                   # 설정 관리 (환경변수, 상수)
│   ├── database.py                 # SQLite DB 연결 및 스키마 관리
│   ├── telegram.py                 # 텔레그램 메시지 전송
│   ├── news/
│   │   ├── __init__.py
│   │   ├── base.py                 # 뉴스 소스 추상 클래스
│   │   └── provider.py              # 실제 뉴스 소스 구현 (예: RSS, API)
│   ├── market/
│   │   ├── __init__.py
│   │   ├── base.py                 # 시세 소스 추상 클래스
│   │   └── provider.py             # 실제 시세 소스 구현 (예: yfinance, API)
│   ├── analysis/
│   │   ├── __init__.py
│   │   ├── news_analyzer.py        # 뉴스 요약 및 종목 추출
│   │   └── performance.py          # 수익률 계산, 승률, MDD 등
│   ├── reports/
│   │   ├── __init__.py
│   │   ├── morning.py               # 오전 리포트 생성
│   │   ├── evening.py               # 오후 리포트 생성
│   │   └── monthly.py               # 월간 리포트 생성
│   └── utils/
│       ├── __init__.py
│       ├── date_utils.py            # KST 시간 처리, 날짜 유틸
│       └── disclaimer.py            # 면책 문구 생성
├── db/
│   └── market.db                    # SQLite DB (git에 포함)
├── scripts/
│   ├── init_db.py                   # DB 초기화 스크립트
│   └── test_local.py                # 로컬 테스트용
├── tests/
│   └── (테스트 파일들)
├── .env.example                     # 환경변수 예시
├── .gitignore
├── requirements.txt
├── README.md
└── DESIGN.md                        # 이 문서
```

## 2. 각 모듈 책임

### 2.1 config.py
- 환경변수 로드 (텔레그램 봇 토큰, 채팅 ID 등)
- 상수 정의 (가정 투자 금액: 10,000,000원 등)
- 설정 검증

### 2.2 database.py
- SQLite 연결 관리
- 스키마 초기화/마이그레이션
- CRUD 작업 추상화

### 2.3 telegram.py
- 텔레그램 봇 API 래퍼
- Markdown 포맷팅 지원
- 에러 핸들링 및 재시도 로직

### 2.4 news/base.py & news/provider.py
- `NewsProvider` 추상 클래스 정의
- `fetch_news(date)` 메서드 인터페이스
- 실제 구현: RSS 피드, 뉴스 API 등

### 2.5 market/base.py & market/provider.py
- `MarketProvider` 추상 클래스 정의
- `get_price(symbol, date)`, `get_ohlc(symbol, date)` 메서드
- 실제 구현: yfinance, 다른 API 등

### 2.6 analysis/news_analyzer.py
- 뉴스 텍스트에서 종목명 추출 (LLM 또는 키워드 매칭)
- 뉴스 요약 생성
- 관찰 종목 선정 로직 (중요도 점수 등)

### 2.7 analysis/performance.py
- 가정 투자 수익률 계산
- 승률 계산 (추천 종목 중 상승/하락 비율)
- MDD (Maximum Drawdown) 계산
- 종목별 기여도 계산

### 2.8 reports/morning.py
- 지난밤 뉴스 수집 및 요약
- 관찰 종목 1~3개 선정
- 오전 리포트 메시지 포맷팅

### 2.9 reports/evening.py
- 추천 종목의 당일 OHLC/등락률 조회
- 가정 투자 수익 계산 (동일비중)
- 오후 리포트 메시지 포맷팅

### 2.10 reports/monthly.py
- 한 달 누적 데이터 집계
- 승률, MDD, TOP 기여/손실 종목
- 개선 제안 생성
- 월간 리포트 메시지 포맷팅

### 2.11 utils/date_utils.py
- KST 시간 처리
- 거래일 체크
- 날짜 범위 계산

### 2.12 utils/disclaimer.py
- 면책 문구 템플릿
- 리포트 타입별 맞춤 문구

## 3. DB 스키마 (SQL)

```sql
-- 종목 마스터
CREATE TABLE IF NOT EXISTS symbols (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL UNIQUE,           -- 종목코드 (예: "005930")
    name TEXT NOT NULL,                    -- 종목명 (예: "삼성전자")
    market TEXT,                           -- 시장 구분 (예: "KOSPI", "KOSDAQ")
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 뉴스 기록
CREATE TABLE IF NOT EXISTS news (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    content TEXT,
    source TEXT,                           -- 뉴스 출처
    url TEXT,
    published_at TIMESTAMP,                -- 뉴스 발행 시간
    collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    summary TEXT                           -- 요약본
);

-- 뉴스-종목 연결 (다대다)
CREATE TABLE IF NOT EXISTS news_symbols (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    news_id INTEGER NOT NULL,
    symbol_id INTEGER NOT NULL,
    relevance_score REAL,                 -- 관련도 점수 (0.0~1.0)
    FOREIGN KEY (news_id) REFERENCES news(id) ON DELETE CASCADE,
    FOREIGN KEY (symbol_id) REFERENCES symbols(id) ON DELETE CASCADE,
    UNIQUE(news_id, symbol_id)
);

-- 추천 기록 (매일 오전 추천)
CREATE TABLE IF NOT EXISTS recommendations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,                    -- 추천일 (YYYY-MM-DD)
    symbol_id INTEGER NOT NULL,
    reason TEXT,                           -- 추천 이유
    news_ids TEXT,                         -- 관련 뉴스 ID 목록 (JSON 배열)
    priority INTEGER,                      -- 우선순위 (1=최우선)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (symbol_id) REFERENCES symbols(id),
    UNIQUE(date, symbol_id)
);

-- 일일 시세 기록
CREATE TABLE IF NOT EXISTS daily_prices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol_id INTEGER NOT NULL,
    date DATE NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume INTEGER,
    change_rate REAL,                      -- 등락률 (%)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (symbol_id) REFERENCES symbols(id),
    UNIQUE(symbol_id, date)
);

-- 가정 투자 기록 (매일 오후 계산)
CREATE TABLE IF NOT EXISTS paper_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    symbol_id INTEGER NOT NULL,
    recommendation_id INTEGER,             -- 추천 기록 참조
    entry_date DATE,                       -- 진입일 (추천일)
    entry_price REAL,                      -- 진입가
    current_price REAL,                    -- 현재가 (당일 종가)
    quantity INTEGER,                      -- 수량 (동일비중 계산)
    invested_amount REAL,                 -- 투자금액
    current_value REAL,                    -- 현재 평가액
    pnl REAL,                              -- 손익
    pnl_rate REAL,                         -- 손익률 (%)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (symbol_id) REFERENCES symbols(id),
    FOREIGN KEY (recommendation_id) REFERENCES recommendations(id)
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_recommendations_date ON recommendations(date);
CREATE INDEX IF NOT EXISTS idx_daily_prices_symbol_date ON daily_prices(symbol_id, date);
CREATE INDEX IF NOT EXISTS idx_paper_trades_date ON paper_trades(date);
CREATE INDEX IF NOT EXISTS idx_paper_trades_symbol ON paper_trades(symbol_id);
```

## 4. 실행 흐름

### 4.1 오전 리포트 (08:00 KST)

```
1. GitHub Actions 트리거 (cron: 0 0 * * * KST=UTC+9 → 23:00 UTC)
2. main() 실행
   ├─ 2.1 DB 연결 확인/초기화
   ├─ 2.2 뉴스 수집 (news/provider.py)
   │   └─ 지난밤 ~ 오늘 08:00 사이 뉴스
   ├─ 2.3 뉴스 분석 (analysis/news_analyzer.py)
   │   ├─ 뉴스 요약 생성
   │   └─ 종목 추출 및 관련도 점수 계산
   ├─ 2.4 관찰 종목 선정 (상위 1~3개)
   ├─ 2.5 DB 저장
   │   ├─ news 테이블에 뉴스 저장
   │   ├─ news_symbols 연결 저장
   │   └─ recommendations 테이블에 추천 저장
   ├─ 2.6 리포트 생성 (reports/morning.py)
   │   ├─ 뉴스 요약 텍스트 생성
   │   ├─ 추천 종목 리스트 생성
   │   └─ 면책 문구 추가
   └─ 2.7 텔레그램 전송 (telegram.py)
       └─ Markdown 포맷팅하여 전송
```

### 4.2 오후 리포트 (16:30 KST)

```
1. GitHub Actions 트리거 (cron: 30 8 * * * KST=UTC+9 → 07:30 UTC)
2. main() 실행
   ├─ 2.1 DB 연결
   ├─ 2.2 오늘 추천 종목 조회 (recommendations 테이블)
   ├─ 2.3 시세 조회 (market/provider.py)
   │   └─ 각 종목의 당일 OHLC/등락률
   ├─ 2.4 가정 투자 수익 계산 (analysis/performance.py)
   │   ├─ 동일비중 계산 (총 1,000만원 / 종목 수)
   │   ├─ 진입가 = 추천일 시가 또는 전일 종가
   │   ├─ 현재가 = 당일 종가
   │   └─ 손익/손익률 계산
   ├─ 2.5 DB 저장
   │   ├─ daily_prices 테이블에 시세 저장
   │   └─ paper_trades 테이블에 가정 투자 기록 저장
   ├─ 2.6 리포트 생성 (reports/evening.py)
   │   ├─ 종목별 OHLC/등락률 표시
   │   ├─ 가정 투자 수익 요약
   │   └─ 면책 문구 추가
   └─ 2.7 텔레그램 전송
```

### 4.3 월간 리포트 (월말)

```
1. GitHub Actions 트리거 (매월 마지막 거래일 18:00 KST)
2. main() 실행
   ├─ 2.1 DB 연결
   ├─ 2.2 지난 달 데이터 집계
   │   ├─ paper_trades에서 해당 월 데이터 조회
   │   ├─ 승률 계산 (상승 종목 수 / 전체 종목 수)
   │   ├─ 누적 수익률 계산
   │   ├─ MDD 계산
   │   └─ TOP 기여/손실 종목 선정
   ├─ 2.3 리포트 생성 (reports/monthly.py)
   │   ├─ 성과 지표 요약
   │   ├─ 종목별 기여도 분석
   │   ├─ 개선 제안 (패턴 분석 기반)
   │   └─ 면책 문구 추가
   └─ 2.4 텔레그램 전송
```

## 5. 주요 고려사항

### 5.1 GitHub Actions 환경
- SQLite DB 파일을 git에 커밋/푸시하여 상태 유지
- 주의: DB 파일 크기 모니터링 필요
- DB 충돌 방지: 각 워크플로우는 순차 실행 또는 락 메커니즘 고려

### 5.2 데이터 소스 모듈화
- `base.py`에 추상 클래스 정의로 교체 용이
- 환경변수로 provider 선택 가능

### 5.3 에러 핸들링
- 네트워크 오류 시 재시도
- 부분 실패 시에도 가능한 리포트 전송
- 에러 로그는 Actions 로그에 기록

### 5.4 면책 문구
- 모든 리포트에 포함
- "본 시스템은 리서치/교육용 시뮬레이션이며 실제 투자 권유가 아닙니다"
- "과거 성과는 미래 수익을 보장하지 않습니다" 등

