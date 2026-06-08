# AI 동향 — 매일 자동 다이제스트

매일 한국시간 오전 10시에 RSS를 크롤링해 AI 관련 글 2개를 골라
`data.json`에 쌓고, GitHub Pages로 보여주는 정적 사이트.

```
index.html   ← 보여주는 페이지 (data.json을 읽음)
data.json    ← 글 목록 (크롤러가 자동 갱신)
crawl.py     ← RSS 크롤러 (글 2개 선별)
requirements.txt
.github/workflows/daily.yml  ← 매일 10시 자동 실행
```

## 처음 한 번만 설정

1. GitHub에서 새 저장소(repository) 생성 → 이 폴더 파일 전부 업로드
2. **Settings → Actions → General → Workflow permissions**
   → "Read and write permissions" 선택 후 저장
   (크롤러가 data.json을 커밋하려면 필요)
3. **Settings → Pages**
   → Source: "Deploy from a branch", Branch: `main` / `/(root)` → 저장
   → 잠시 뒤 `https://<아이디>.github.io/<저장소이름>/` 에서 페이지가 열림

## 동작 확인

- **Actions** 탭 → "Daily AI digest" → **Run workflow** 버튼으로 즉시 한 번 실행해보기
- 끝나면 `data.json`에 새 글 2개가 추가되고, 페이지가 자동 갱신됨
- 이후로는 매일 오전 10시에 알아서 실행됨

## 선정 기준 (점수)

매일 후보 글에 점수를 매겨 상위 2개를 고른다:

```
점수 = 0.40·인기 + 0.30·실용 + 0.20·관심키워드 + 0.10·최신성
```

- **인기**: PyTorch KR은 조회수+좋아요(실제 숫자), GeekNews는 투표 랭킹 순위
- **실용**: 도구·코드·가이드류인가 (`PRACTICAL_KEYWORDS`)
- **관심**: 내 관심 주제와 맞나 (`INTEREST_KEYWORDS` ← 꼭 내 걸로 수정)
- **최신성**: 나온 지 7일에 걸쳐 점수 감소

Actions 실행 로그에 각 글의 점수와 탈락 후보가 찍히니, 보면서 가중치를 조절하면 된다.

## 바꾸고 싶을 때

- **유용함 비중**: `crawl.py`의 `WEIGHTS` (합이 1)
- **내 관심 주제**: `crawl.py`의 `INTEREST_KEYWORDS`
- **실용 신호**: `crawl.py`의 `PRACTICAL_KEYWORDS`
- **선별 개수/소스**: `crawl.py` 위쪽 `SOURCES`, `PICK`, `MAX_KEEP`
- **AI 필터 키워드**: `crawl.py`의 `AI_KEYWORDS`
- **실행 시각**: `.github/workflows/daily.yml`의 `cron`
  (UTC 기준 — 10시 KST = `0 1 * * *`)
- **요약 직접 다듬기**: `data.json`을 열어 `summary`를 손으로 고쳐도 됨

## 참고

- GitHub Actions의 예약 실행은 트래픽에 따라 몇 분~십여 분 늦을 수 있음
- 공개 저장소는 Actions 무료. 저장소를 60일간 안 건드리면
  예약 실행이 멈출 수 있는데, 가끔 수동 실행하거나 커밋하면 유지됨
