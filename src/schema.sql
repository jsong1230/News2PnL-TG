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
    market_provider TEXT DEFAULT 'unknown', -- 시세 제공자 ('yahoo', 'dummy', 'unknown')
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (symbol_id) REFERENCES symbols(id),
    FOREIGN KEY (recommendation_id) REFERENCES recommendations(id)
);

-- 재무 지표 캐시
CREATE TABLE IF NOT EXISTS financial_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol_id INTEGER NOT NULL,
    date DATE NOT NULL,
    per REAL,
    debt_ratio REAL,
    revenue_growth_3y REAL,
    earnings_growth_3y REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (symbol_id) REFERENCES symbols(id),
    UNIQUE(symbol_id, date)
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_recommendations_date ON recommendations(date);
CREATE INDEX IF NOT EXISTS idx_daily_prices_symbol_date ON daily_prices(symbol_id, date);
CREATE INDEX IF NOT EXISTS idx_paper_trades_date ON paper_trades(date);
CREATE INDEX IF NOT EXISTS idx_paper_trades_symbol ON paper_trades(symbol_id);
CREATE INDEX IF NOT EXISTS idx_news_published_at ON news(published_at);
CREATE INDEX IF NOT EXISTS idx_news_symbols_symbol_id ON news_symbols(symbol_id);
CREATE INDEX IF NOT EXISTS idx_financial_metrics_symbol_date ON financial_metrics(symbol_id, date);

