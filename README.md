# News2PnL-TG

GitHub Actions 기반 텔레그램 페이퍼 트레이딩 봇

## 프로젝트 개요

이 프로젝트는 뉴스 기반으로 종목을 추천하고, 가정 투자 성과를 추적하는 텔레그램 봇입니다. 서버 없이 GitHub Actions의 cron 스케줄로만 동작합니다.

### 주요 기능

- **오전 리포트 (08:00 KST)**: 지난밤 주요 뉴스 요약 + 오늘의 관찰 종목 1~3개 제안
- **오후 리포트 (16:30 KST)**: 추천 종목의 당일 OHLC/등락률 + 가정 투자 수익 계산
- **월간 리포트 (월말)**: 한 달 누적 성과, 승률, MDD, TOP 기여/손실 종목, 개선 제안

### 중요 원칙

- ⚠️ **리서치/교육용 시뮬레이션**: 실제 투자 권유가 아닙니다 (모든 메시지에 면책 문구 포함)
- 확정적 표현 금지, 리스크/불확실성 포함
- 데이터 소스 모듈화 (뉴스/시세 제공자 교체 가능)
- 서버 없이 GitHub Actions cron으로만 실행
- SQLite DB를 git에 포함하여 상태 유지

## 프로젝트 구조

```
News2PnL-TG/
├── .github/workflows/     # GitHub Actions 워크플로우
├── src/                   # 핵심 로직
│   ├── config.py          # 설정 관리
│   ├── database.py        # SQLite 관리
│   ├── telegram.py        # 텔레그램 전송
│   ├── news/              # 뉴스 수집 모듈
│   ├── market/            # 시세 조회 모듈
│   ├── analysis/          # 분석 모듈
│   ├── reports/           # 리포트 생성 모듈
│   └── utils/             # 유틸리티
├── db/                    # SQLite DB (git에 포함)
├── scripts/               # 실행 스크립트
└── tests/                 # 테스트
```

자세한 설계는 [DESIGN.md](DESIGN.md)를 참고하세요.

## 설치 및 설정

### 1. 저장소 클론

```bash
git clone https://github.com/jsong1230/News2PnL-TG.git
cd News2PnL-TG
```

### 2. Python 환경 설정

Python 3.11 이상이 필요합니다.

```bash
python3.11 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. 환경변수 설정

`.env.example`을 참고하여 `.env` 파일을 생성하세요:

```bash
cp .env.example .env
```

`.env` 파일 편집:

```env
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
NEWS_PROVIDER=dummy  # 또는 "rss" (실제 뉴스 수집)
MARKET_PROVIDER=dummy
PAPER_TRADE_AMOUNT=10000000
GOOGLE_NEWS_QUERY=한국 주식 시장  # RSS provider 사용 시 검색 쿼리
```

### 뉴스 제공자 설정

- `NEWS_PROVIDER=dummy`: 더미 데이터 사용 (테스트용)
- `NEWS_PROVIDER=rss`: Google News RSS 사용 (실제 뉴스 수집)

RSS provider 사용 시 검색 쿼리를 설정할 수 있습니다:

**단일 쿼리 (하위 호환):**
- `GOOGLE_NEWS_QUERY=한국 주식 시장` (기본값)

**여러 쿼리 (권장, 더 많은 뉴스 수집):**
- `GOOGLE_NEWS_QUERIES=미국 증시,나스닥,S&P500,연준 금리,달러 환율,유가,엔비디아,반도체,AI,비트코인,한국 증시,외국인 수급,삼성전자,SK하이닉스`
- 쉼표로 구분하여 여러 쿼리를 지정하면 각 쿼리별로 뉴스를 수집하고 병합합니다
- `GOOGLE_NEWS_MAX_PER_QUERY=30` (기본값)으로 쿼리별 최대 수집 개수를 설정할 수 있습니다
- `GOOGLE_NEWS_QUERIES`가 비어있으면 기본 쿼리 세트가 자동으로 사용됩니다
- 중복 제거 후 최종 10건 이상의 뉴스가 유지됩니다

**뉴스 시간 윈도우 모드:**
- `NEWS_WINDOW_MODE=strict` (기본값): 전날 18:00 ~ 오늘 08:00 KST (운영 모드, GitHub Actions 기본)
- `NEWS_WINDOW_MODE=now`: (현재 시각 - NEWS_LOOKBACK_HOURS) ~ 현재 시각 KST (개발/디버그 모드, 로컬 테스트용)
- `NEWS_LOOKBACK_HOURS=24` (기본값): now 모드에서 lookback 시간 (시간 단위)
- 로컬에서 09:xx에 실행할 때는 `NEWS_WINDOW_MODE=now`로 설정하면 더 많은 뉴스를 수집할 수 있습니다
- 예: `NEWS_WINDOW_MODE=now NEWS_LOOKBACK_HOURS=24` → 지난 24시간 동안의 뉴스 수집

**관찰 리스트 설정:**
- `WATCHLIST_KR`: 관찰 우선 종목 리스트 (선택사항, 쉼표 구분)
- 예: `WATCHLIST_KR=삼성전자,SK하이닉스,LG에너지솔루션`
- 설정된 종목은 뉴스에서 언급되면 가중치가 추가되어 관찰 리스트에 포함될 가능성이 높아집니다

### 4. DB 초기화

```bash
python -m scripts.init_db
# 또는
python scripts/init_db.py
```

## 로컬 실행 방법

### 오전 리포트

```bash
# 권장: python -m 방식 (어디서 실행해도 동작)
python -m scripts.run_morning

# 또는 직접 실행
python scripts/run_morning.py
```

### 오후 리포트

```bash
# 권장: python -m 방식
python -m scripts.run_evening

# 또는 직접 실행
python scripts/run_evening.py
```

**오후 리포트 설명:**
- 오전 리포트에서 생성된 관찰 종목을 기준으로 장 마감 후 실제 시세를 반영한 가정 투자 성과 리포트를 생성합니다
- 가정 투자 금액은 `PAPER_TRADE_AMOUNT` 환경변수로 설정 (기본값: 10,000,000원)
- 동일 비중으로 투자 가정 (종목당 투자금 = 총금액 / 종목 수)
- 진입가: 당일 시가, 청산가: 당일 종가
- 시세 Provider는 `MARKET_PROVIDER` 환경변수로 선택:
  - `dummy` (기본값): 더미 데이터 사용
  - `yahoo`: Yahoo Finance 사용 (yfinance 패키지 필요)

### 월간 리포트

```bash
# 권장: python -m 방식
python -m scripts.run_monthly

# 또는 직접 실행
python scripts/run_monthly.py

# 개발용: 특정 월 리포트 생성 (월말 체크 스킵)
MONTH_OVERRIDE=2025-12 python -m scripts.run_monthly
```

**월간 리포트 설명:**
- DB에 저장된 `paper_trades` 데이터를 기반으로 해당 월의 누적 성과를 집계합니다
- 기본적으로 현재 월의 데이터를 조회하며, `MONTH_OVERRIDE=YYYY-MM` 환경변수로 특정 월을 지정할 수 있습니다
- 월말이 아니면 자동으로 스킵됩니다 (개발용으로 `MONTH_OVERRIDE` 사용)
- 리포트 내용:
  - 총 손익 및 수익률
  - 승률 (수익 종목 수 / 전체 종목 수)
  - 최대낙폭(MDD): 누적 손익 기준으로 계산
  - 일별 하이라이트: 베스트/워스트 데이
  - 종목 하이라이트: 베스트/워스트 종목
  - 월간 관찰 코멘트 및 개선 포인트

### 로컬 수동 테스트

```bash
# RSS 수집 및 다이제스트 생성 테스트
python scripts/manual_test_local.py
```

### Dry-run 모드

텔레그램 토큰이 설정되지 않으면 자동으로 dry-run 모드로 실행됩니다. 메시지는 콘솔에 출력됩니다.

### 로컬 수동 테스트

뉴스 수집 및 다이제스트 생성 기능을 수동으로 테스트하려면:

```bash
python scripts/manual_test_local.py
```

이 스크립트는 다음을 테스트합니다:
1. RSS 뉴스 수집 (Google News)
2. 다이제스트 생성 (중복 제거, 섹터 분류, 영향도 평가)
3. Fallback 동작 (더미 provider)

## 운영 설정 (GitHub Actions)

### 1. 텔레그램 채널 설정

#### 채널 생성 및 봇 추가

1. 텔레그램에서 새 채널 생성
2. 채널 설정 > 관리자 > 관리자 추가
3. 봇을 관리자(Admin)로 추가 (메시지 전송 권한 필요)
4. 채널 ID 확인:
   - 채널에 봇이 메시지를 보내도록 설정
   - [@userinfobot](https://t.me/userinfobot) 또는 [@getidsbot](https://t.me/getidsbot) 사용
   - 채널 ID는 `-100...` 형태입니다 (예: `-1001234567890`)

#### 텔레그램 봇 토큰 발급

1. 텔레그램에서 [@BotFather](https://t.me/botfather) 검색
2. `/newbot` 명령으로 새 봇 생성
3. 봇 이름과 username 설정
4. 발급된 토큰을 복사

### 2. GitHub Secrets 설정

GitHub 저장소의 **Settings > Secrets and variables > Actions**에서 다음 Secrets를 추가하세요:

| Secret 이름 | 설명 | 필수 | 예시 |
|------------|------|------|------|
| `TELEGRAM_BOT_TOKEN` | 텔레그램 봇 토큰 (BotFather에서 발급) | 예 | `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz` |
| `TELEGRAM_CHAT_ID` | 텔레그램 채널 ID (`-100...` 형태) | 예 | `-1001234567890` |
| `OPENAI_API_KEY` | OpenAI API 키 (LLM 사용 시) | 선택 | `sk-...` |
| `LLM_MODEL` | LLM 모델명 (기본값: gpt-4o-mini) | 선택 | `gpt-4o-mini` |

### 3. 워크플로우 스케줄 (KST ↔ UTC 변환)

GitHub Actions의 cron은 **UTC 기준**입니다. 한국 시간(KST)과의 변환:

| 리포트 | KST 시간 | UTC 시간 | Cron 표현 | 설명 |
|--------|----------|----------|-----------|------|
| **오전 리포트** | 08:00 (월~금) | 23:00 (전날 일~목) | `0 23 * * 0-4` | 한국 평일 아침 실행 |
| **오후 리포트** | 16:30 (월~금) | 07:30 (월~금) | `30 7 * * 1-5` | 한국 평일 저녁 실행 |
| **월간 리포트** | 18:00 (말일) | 09:00 (매일) | `0 9 * * *` | 매일 실행 후 내부에서 월말 체크 |

**참고**: 
- KST = UTC + 9시간
- 월간 리포트는 cron으로 정확한 말일을 잡을 수 없으므로, 매일 실행 후 `scripts/run_monthly.py` 내부에서 월말 여부를 확인합니다.

### 4. 환경변수 설정

워크플로우에서 자동으로 설정되는 환경변수:

| 환경변수 | 기본값 | 설명 |
|----------|--------|------|
| `NEWS_WINDOW_MODE` | `strict` | 뉴스 시간 윈도우 모드 (운영 기본) |
| `MARKET_PROVIDER` | `yahoo` | 시세 제공자 (운영 기본) |
| `TZ` | `Asia/Seoul` | 타임존 (로그용) |
| `TELEGRAM_REQUIRED` | `false` | 텔레그램 전송 실패 시 워크플로우 실패 여부 |
| `LLM_ENABLED` | `false` | LLM 사용 여부 (관찰 종목 선정) |
| `OPENAI_API_KEY` | - | OpenAI API 키 (LLM_ENABLED=true일 때 필요) |
| `LLM_MODEL` | `gpt-4o-mini` | LLM 모델명 |
| `LLM_MAX_TOKENS` | `800` | 최대 토큰 수 |
| `LLM_TEMPERATURE` | `0.2` | 온도 (0.0~1.0) |
| `LLM_DAILY_BUDGET_TOKENS` | `20000` | 일일 토큰 예산 |

**개발/디버그용 환경변수** (로컬 실행 시):

| 환경변수 | 설명 | 예시 |
|----------|------|------|
| `NEWS_WINDOW_MODE` | `now`로 설정 시 현재 시간 기준으로 뉴스 수집 | `now` |
| `NEWS_LOOKBACK_HOURS` | `now` 모드에서 lookback 시간 (시간 단위) | `24` |
| `MONTH_OVERRIDE` | 특정 월 리포트 생성 (YYYY-MM 형식) | `2025-12` |
| `MONTHLY_INCLUDE_DUMMY` | 월간 리포트에 dummy provider 거래 포함 | `true` |

### 5. 수동 실행

각 워크플로우는 `workflow_dispatch`로 수동 실행도 가능합니다:
- GitHub 저장소 > **Actions** 탭 > 해당 워크플로우 선택 > **Run workflow** 버튼 클릭

### 6. DB 자동 커밋

워크플로우 실행 후 `db/market.db`가 변경되면 자동으로 커밋/푸시됩니다.

### 7. 안전장치

- **텔레그램 전송 실패**: 기본적으로 `TELEGRAM_REQUIRED=false`이므로, 전송 실패 시 warning만 출력하고 워크플로우는 계속 진행됩니다.
- **재시도 로직**: 네트워크 오류나 rate limit 발생 시 2회까지 재시도 (간격 2초)
- **Dry-run 모드**: 토큰이나 채팅 ID가 없으면 자동으로 dry-run 모드로 실행되어 메시지는 콘솔에 출력됩니다.

## 개발 가이드

### 데이터 소스 교체

#### 뉴스 제공자

현재 지원하는 뉴스 제공자:
- `dummy`: 더미 데이터 (테스트용)
- `rss`: Google News RSS (실제 뉴스 수집)

RSS provider는 Google News RSS 검색 API를 사용합니다:
- URL 형식: `https://news.google.com/rss/search?q={query}&hl=ko&gl=KR&ceid=KR:ko`
- 검색 쿼리는 `GOOGLE_NEWS_QUERY` 환경변수로 설정
- 네트워크 실패 시 자동으로 더미 provider로 fallback

새로운 뉴스 제공자를 추가하려면:
1. `src/news/base.py`의 `NewsProvider` 추상 클래스 구현
2. `src/news/provider.py`에 구현 클래스 추가
3. `get_news_provider()` 팩토리 함수에 등록

#### 시세 제공자

현재 지원하는 시세 제공자:
- `dummy`: 더미 데이터 (테스트용)
- `yahoo`: Yahoo Finance (실제 시세, `yfinance` 패키지 사용)

Yahoo provider는 한국 주식 코드를 `.KS` (KOSPI) 또는 `.KQ` (KOSDAQ) 형식으로 변환하여 조회합니다.

### 모듈 구조

- **추상 클래스**: `src/news/base.py`, `src/market/base.py`
- **구현 클래스**: `src/news/provider.py`, `src/market/provider.py`
- **팩토리 함수**: `get_news_provider()`, `get_market_provider()`

## 주의사항

1. **DB 파일 크기**: SQLite DB 파일이 git에 포함되므로 크기 모니터링이 필요합니다.
2. **워크플로우 충돌**: `concurrency` 설정으로 중복 실행을 방지합니다.
3. **면책 문구**: 모든 리포트에 면책 문구가 자동으로 포함됩니다.
4. **에러 처리**: 스크립트 실행 중 에러 발생 시 텔레그램으로 알림이 전송됩니다.
5. **RSS 수집 실패**: Google News RSS가 일시적으로 차단되거나 타임아웃될 수 있습니다. 이 경우 자동으로 더미 provider로 fallback되며, "뉴스 수집 실패" 메시지가 포함됩니다.
   - GitHub Actions에서 실행 시 네트워크 제한으로 인해 실패할 수 있습니다.
   - 로컬 테스트에서는 정상 동작하지만 Actions에서는 실패하는 경우, 더미 provider 사용을 권장합니다.

## 라이선스

MIT

## 기여

이슈 및 Pull Request를 환영합니다!

