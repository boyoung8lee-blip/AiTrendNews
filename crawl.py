"""
매일 RSS/API를 읽어 '유용한' AI 글 2개를 점수로 골라 data.json에 누적한다.
GitHub Actions가 한국시간 오전 10시에 자동 실행한다.

── 선정 점수 (가중치 합, 클수록 우선) ──────────────────────
    점수 = 0.40·인기 + 0.30·실용 + 0.20·관심키워드 + 0.10·최신성

  인기   : 많은 사람이 추천·주목했나
           - PyTorch KR : Discourse JSON의 조회수 + 좋아요 (실제 숫자)
           - GeekNews   : 투표 랭킹 피드의 상위 순위 (숫자 API가 없어 순위로 대용)
  실용   : 도구·코드·가이드처럼 바로 써먹는 글인가 (키워드)
  관심   : 내 관심 주제와 맞는가 (키워드)
  최신성 : 나온 지 얼마 안 됐나 (7일에 걸쳐 감소)
"""

import json
import re
import html
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

import os

import feedparser

# ── 설정 (여기를 손보면 됨) ───────────────────────────────
DATA_FILE = Path(__file__).parent / "data.json"
MAX_KEEP = 60          # data.json에 보관할 최대 글 수
PICK = 3               # 매일 뽑을 글 개수

WEIGHTS = {            # ★ 유용함 기준의 비중 (합이 1)
    "popularity": 0.40,
    "practical":  0.30,
    "interest":   0.20,
    "recency":    0.10,
}

SOURCES = [
    {"name": "PyTorch KR", "type": "discourse",
     "url": "https://discuss.pytorch.kr/c/news/14.json", "ai_only": False},
    {"name": "GeekNews", "type": "rss_ranked",
     "url": "https://news.hada.io/rss/topics", "ai_only": True},
]

# GeekNews에서 AI 글만 거르는 키워드
AI_KEYWORDS = [
    "ai", "llm", "gpt", "claude", "gemini", "gemma", "qwen", "llama", "mistral",
    "agent", "에이전트", "모델", "머신러닝", "딥러닝", "neural", "트랜스포머",
    "transformer", "rag", "파인튜닝", "fine-tun", "멀티모달", "multimodal",
    "추론", "reasoning", "openai", "anthropic", "nvidia", "diffusion",
    "생성형", "genai", "인공지능", "프롬프트", "prompt", "mcp",
]

# '실용 정보' 신호 — 도구·코드·가이드류
PRACTICAL_KEYWORDS = [
    "도구", "라이브러리", "프레임워크", "툴", "tool", "library", "framework",
    "sdk", "cli", "api", "가이드", "guide", "튜토리얼", "tutorial", "how-to",
    "예제", "example", "오픈소스", "opensource", "open-source", "github",
    "출시", "공개", "release", "스킬", "skill", "실전", "코드", "code", "구현",
]

# ★ 내 관심 주제 — 여기를 네 것으로 바꿔라 (예전 대화 기반 기본값)
INTEREST_KEYWORDS = [
    "agent", "에이전트", "온디바이스", "on-device", "edge", "보안", "security",
    "mcp", "langgraph", "langchain", "self-improving", "평가", "eval",
    "워크플로우", "workflow", "orchestration",
]

KST = timezone(timedelta(hours=9))
UA = {"User-Agent": "ai-daily-bot/1.0 (+github actions)"}


# ── 도우미 ────────────────────────────────────────────────
def clean_text(raw, limit=140):
    t = re.sub(r"<[^>]+>", "", raw or "")
    t = html.unescape(t)
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) > limit:
        t = t[:limit].rsplit(" ", 1)[0] + "…"
    return t


def kw_score(text, keywords):
    """키워드가 몇 개 맞나 → 0~1 (2개 이상이면 만점)."""
    low = text.lower()
    hits = sum(1 for k in keywords if k in low)
    return min(1.0, hits * 0.5)


def recency_score(dt):
    """나온 지 0일=1.0, 7일이면 0."""
    if not dt:
        return 0.0
    age_days = (datetime.now(timezone.utc) - dt).total_seconds() / 86400
    return max(0.0, 1.0 - age_days / 7.0)


def normalize(values):
    """리스트를 0~1로 min-max 정규화 (모두 같으면 1.0)."""
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi == lo:
        return [1.0] * len(values)
    return [(v - lo) / (hi - lo) for v in values]


def is_ai(text):
    low = text.lower()
    return any(k in low for k in AI_KEYWORDS)


# ── 소스별 수집 ────────────────────────────────────────────
def fetch_discourse(src):
    """Discourse JSON에서 조회수·좋아요까지 가져온다."""
    try:
        req = urllib.request.Request(src["url"], headers=UA)
        data = json.loads(urllib.request.urlopen(req, timeout=20).read())
        topics = data["topic_list"]["topics"]
    except Exception as e:
        print(f"[warn] {src['name']} JSON 실패: {e}")
        return []

    base = src["url"].split("/c/")[0]
    items = []
    for t in topics:
        if t.get("pinned") or "카테고리" in t.get("title", ""):
            continue  # 카테고리 설명/공지 글 제외
        created = t.get("created_at")
        dt = None
        if created:
            try:
                dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            except ValueError:
                pass
        items.append({
            "source": src["name"],
            "title": clean_text(t.get("title", "제목 없음"), 120),
            "url": f"{base}/t/{t.get('slug','topic')}/{t.get('id')}",
            "summary": "",  # JSON에는 본문 발췌가 없어 비워둠
            "tags": [tag["name"] if isinstance(tag, dict) else tag for tag in (t.get("tags") or [])[:4]],
            "_dt": dt,
            # 조회수 + 좋아요(가중) 를 인기 원점수로
            "_pop_raw": t.get("views", 0) + 30 * t.get("like_count", 0),
        })
    print(f"[info] {src['name']}: {len(items)}건")
    return items


def fetch_rss_ranked(src):
    """투표 랭킹 RSS — 피드 상위 순위를 인기 점수로 대용."""
    try:
        feed = feedparser.parse(src["url"])
        entries = feed.entries
    except Exception as e:
        print(f"[warn] {src['name']} RSS 실패: {e}")
        return []

    n = len(entries)
    items = []
    for rank, e in enumerate(entries):
        t = e.get("published_parsed") or e.get("updated_parsed")
        dt = datetime(*t[:6], tzinfo=timezone.utc) if t else None
        items.append({
            "source": src["name"],
            "title": clean_text(e.get("title", "제목 없음"), 120),
            "url": e.get("link", ""),
            "summary": clean_text(e.get("summary", "")),
            "tags": [x.get("term", "") for x in e.get("tags", []) if x.get("term")][:4],
            "_dt": dt,
            "_pop_raw": n - rank,  # 위에 있을수록 큼
        })
    print(f"[info] {src['name']}: {len(items)}건")
    return items


def fetch(src):
    items = fetch_discourse(src) if src["type"] == "discourse" else fetch_rss_ranked(src)
    # 인기 원점수를 소스 안에서 0~1로 정규화 (소스 간 비교 가능하게)
    norm = normalize([i["_pop_raw"] for i in items])
    for i, p in zip(items, norm):
        i["_pop"] = p
    return items


def gemini_score_batch(candidates):
    """Gemini REST API로 후보글 최대 20개를 한 번에 채점 (0~1). 실패 시 빈 dict 반환."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return {}
    batch = candidates[:20]
    lines = [
        f"{i}. 제목: {c['title']}\n   요약: {c['summary'] or '없음'}"
        for i, c in enumerate(batch)
    ]
    prompt = (
        "아래 AI 관련 글 목록을 보고 AI 실무자에게 얼마나 유용한지 0~10으로 채점해라.\n"
        "기준: 실용적 도구·코드·가이드·튜토리얼이면 높게, 단순 뉴스·홍보·요약이면 낮게.\n"
        "반드시 숫자만 담긴 JSON 배열로만 답해라. 예: [8,3,7,...]\n\n"
        + "\n".join(lines)
    )
    payload = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode()
    # v1 → v1beta 순으로 시도, 모델도 두 가지 시도
    endpoints = [
        "https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent",
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent",
    ]
    for url in endpoints:
        try:
            req = urllib.request.Request(
                f"{url}?key={api_key}", data=payload,
                headers={"Content-Type": "application/json"}, method="POST"
            )
            resp = json.loads(urllib.request.urlopen(req, timeout=30).read())
            text = resp["candidates"][0]["content"]["parts"][0]["text"]
            match = re.search(r'\[[\d\s,]+\]', text)
            if match:
                scores = json.loads(match.group())
                print(f"[info] Gemini 채점 적용 ({url.split('/models/')[1].split(':')[0]})")
                return {i: s / 10.0 for i, s in enumerate(scores) if i < len(batch)}
        except Exception as e:
            print(f"[warn] {url.split('/models/')[1].split(':')[0]} 실패: {e}")
    print("[warn] Gemini 채점 전체 실패, 규칙 기반으로 폴백")
    return {}


def fetch_topic_summary(topic_url):
    """Discourse 개별 토픽에서 첫 게시글 본문을 가져온다 (선정된 글만 호출)."""
    try:
        req = urllib.request.Request(topic_url + ".json", headers=UA)
        data = json.loads(urllib.request.urlopen(req, timeout=10).read())
        posts = data.get("post_stream", {}).get("posts", [])
        if posts:
            return clean_text(posts[0].get("cooked", ""), 140)
    except Exception:
        pass
    return ""


# ── 점수 매기기 ────────────────────────────────────────────
def score(item):
    text = f"{item['title']} {item['summary']} {' '.join(item['tags'])}"
    s = (
        WEIGHTS["popularity"] * item["_pop"]
        + WEIGHTS["practical"] * kw_score(text, PRACTICAL_KEYWORDS)
        + WEIGHTS["interest"] * kw_score(text, INTEREST_KEYWORDS)
        + WEIGHTS["recency"] * recency_score(item["_dt"])
    )
    return s


# ── 메인 ──────────────────────────────────────────────────
def main():
    existing = []
    if DATA_FILE.exists():
        existing = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    seen = {e["url"] for e in existing}

    # 1) 후보 모으기 (이미 본 글 제외, GeekNews는 AI 필터)
    candidates = []
    for src in SOURCES:
        for it in fetch(src):
            if not it["url"] or it["url"] in seen:
                continue
            if src["ai_only"] and not is_ai(f"{it['title']} {it['summary']}"):
                continue
            candidates.append(it)

    if not candidates:
        print("[info] 새 후보 없음. 종료.")
        return

    # 2) 점수 매겨 상위 PICK개 선정
    for it in candidates:
        it["_score"] = score(it)
    candidates.sort(key=lambda x: x["_score"], reverse=True)

    # 2-1) Gemini로 상위 20개 재채점 (API 키 없으면 스킵)
    gemini_scores = gemini_score_batch(candidates)
    if gemini_scores:
        for i, it in enumerate(candidates[:20]):
            rule = it["_score"]
            gem = gemini_scores.get(i, rule)
            it["_score"] = 0.5 * gem + 0.5 * rule
        candidates.sort(key=lambda x: x["_score"], reverse=True)
        print(f"[info] Gemini 채점 적용 ({len(gemini_scores)}건)")

    picks = candidates[:PICK]

    # 2-1) Discourse 글은 목록 API에 본문이 없으므로 개별 토픽에서 요약 보충
    for p in picks:
        if not p["summary"] and p["source"] == "PyTorch KR":
            p["summary"] = fetch_topic_summary(p["url"])

    # 3) 저장 형태로 변환 (오늘 날짜로 묶음, 점수도 기록)
    today = datetime.now(KST).strftime("%Y-%m-%d")
    new_entries = [{
        "date": today,
        "source": p["source"],
        "title": p["title"],
        "url": p["url"],
        "summary": p["summary"] or "(요약 없음 — data.json에서 직접 채워도 됨)",
        "tags": p["tags"],
        "score": round(p["_score"], 2),
    } for p in picks]

    merged = (new_entries + existing)[:MAX_KEEP]
    DATA_FILE.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[done] {len(new_entries)}건 추가:")
    for p in picks:
        print(f"   {p['_score']:.2f}  [{p['source']}] {p['title']}")
    # 떨어진 후보들도 로그로 (왜 안 뽑혔는지 확인용)
    for p in candidates[PICK:PICK + 5]:
        print(f"   (탈락 {p['_score']:.2f}) {p['title']}")


if __name__ == "__main__":
    main()
