# AI 동향 — 매일 자동 다이제스트

매일 한국시간 오전 10시에 RSS를 크롤링해 AI 관련 글 **3개**를 골라
`data.json`에 쌓고, GitHub Pages로 보여주는 정적 사이트.

**라이브 사이트**: https://boyoung8lee-blip.github.io/AiTrendNews/

```
index.html        ← 정적 사이트 (data.json + config.json을 읽음)
data.json         ← 선정 글 누적 목록 (크롤러가 자동 갱신)
config.json       ← 관심 키워드 등 설정 (웹 UI에서 복사 후 편집 가능)
crawl.py          ← RSS 크롤러 + Gemini 채점
requirements.txt
.github/workflows/daily.yml  ← 매일 오전 10시 KST 자동 실행
```

## 처음 한 번만 설정

1. 저장소를 fork하거나 이 파일들을 새 저장소에 push
2. **Settings → Actions → General → Workflow permissions**
   → "Read and write permissions" 선택 후 저장
3. **Settings → Pages**
   → Source: "Deploy from a branch", Branch: `main` / `/(root)` → 저장
4. **Settings → Secrets and variables → Actions → New repository secret**
   → Name: `GEMINI_API_KEY`, Value: [Google AI Studio에서 발급한 키](https://aistudio.google.com/apikey)
5. **Actions** 탭 → "Daily AI digest" → **Run workflow**로 첫 실행 확인

## 동작 방식

1. PyTorch KR(discuss.pytorch.kr)과 GeekNews(news.hada.io)에서 글 수집
2. **소스별 최소 1건 보장** 후 나머지는 점수순으로 채움
3. 오늘 이미 3건이 있으면 재실행해도 스킵 (중복 방지)

### 점수 계산

```
점수 = 0.40·인기 + 0.30·실용 + 0.20·관심키워드 + 0.10·최신성
```

- **인기**: PyTorch KR은 조회수+좋아요 수치, GeekNews는 랭킹 순위
- **실용**: 도구·코드·가이드·튜토리얼 키워드 매칭
- **관심**: `config.json`의 `interest_keywords` 매칭
- **최신성**: 7일에 걸쳐 선형 감소

위 규칙 기반 점수를 먼저 매긴 뒤, **Gemini 1.5 Flash**로 상위 20개를 일괄 채점해 50% 반영 (API 키 없으면 규칙 기반만 사용).

## 관심 키워드 수정

**방법 1 — 웹 UI (간편)**
1. 사이트에서 **⚙ 수집 설정** 패널 열기
2. 키워드 추가/삭제 후 **"config.json 복사"** 클릭
3. GitHub에서 `config.json` 파일 열어 붙여넣기 → 저장
4. 다음 crawl부터 새 키워드 반영

**방법 2 — 직접 편집**
`config.json`의 `interest_keywords` 배열을 수정 후 commit

## 기타 설정

| 항목 | 위치 |
|------|------|
| 선정 개수 | `crawl.py` → `PICK` |
| 점수 가중치 | `crawl.py` → `WEIGHTS` |
| 실용 키워드 | `crawl.py` → `PRACTICAL_KEYWORDS` |
| AI 필터 키워드 | `crawl.py` → `AI_KEYWORDS` |
| 실행 시각 | `daily.yml` → `cron` (UTC, 현재 01:00 = KST 10:00) |
| 최대 보관 수 | `crawl.py` → `MAX_KEEP` (현재 60건) |

## 참고

- GitHub Actions 예약 실행은 트래픽에 따라 몇 분~십여 분 늦을 수 있음
- 저장소를 60일간 방치하면 예약 실행이 멈춤 → 가끔 수동 실행하거나 커밋하면 유지됨
- Gemini 무료 티어: 하루 50회 제한. 테스트 실행을 많이 하면 당일 소진될 수 있으나, 다음 날 자동 리셋됨
