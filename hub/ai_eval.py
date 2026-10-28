"""AI 문장 검색 평가 — features/ai-screen/eval.json의 문장을 Worker /ai/screen에 보내 기대 조건과 비교

  python -m hub.ai_eval [API 주소]      (기본 https://tickermap-api.flytothejy.workers.dev)

통과 기준: 기대한 key가 모두 있고 숫자가 허용 구간 안, unsupported·refused 있음/없음 일치 (assumptions는 참고만)
주의: 문장 수만큼 하루 횟수를 씀(같은 문장은 저장된 결과라 다시 돌리면 안 셈)
"""
import json, os, sys, time
from pathlib import Path

import requests

EVAL = Path(__file__).resolve().parent.parent / "features" / "ai-screen" / "eval.json"


def check(exp, got):
    why = []
    if exp.get("refused"):
        return ([] if got.get("refused") else ["거절해야 함"])
    if got.get("refused"):
        return ["거절하면 안 됨"]
    gc = {c["k"]: c for c in got.get("conds", [])}
    for k, rule in exp.get("conds", {}).items():
        c = gc.get(k)
        if not c:
            why.append(f"{k} 없음")
            continue
        for op, v in rule.items():
            if op == "in":
                if sorted(map(str, c.get("in", []))) != sorted(map(str, v)):
                    why.append(f"{k}.in {c.get('in')} ≠ {v}")
            else:
                x = c.get(op)
                if x is None or not (v[0] - 1e-9 <= x <= v[1] + 1e-9):
                    why.append(f"{k}.{op}={x} (기대 {v})")
    if "unsupported" in exp and bool(exp["unsupported"]) != bool(got.get("unsupported")):
        why.append(f"unsupported {'있어야' if exp['unsupported'] else '없어야'} 함: {got.get('unsupported')}")
    if exp.get("sort") and (got.get("sort") or {}) != exp["sort"]:
        why.append(f"sort {got.get('sort')} ≠ {exp['sort']}")
    return why


def main(api):
    cases = json.loads(EVAL.read_text(encoding="utf-8"))["cases"]
    ok = 0
    for c in cases:
        t = time.time()
        r = requests.post(api.rstrip("/") + "/ai/screen", json={"q": c["q"]}, timeout=60,
                          headers={"x-ai-eval": os.environ["ALERT_KEY"]} if os.environ.get("ALERT_KEY") else {})
        got = r.json()
        if r.status_code != 200:
            print(f"✗ [{r.status_code}] {c['q'][:40]} → {got}")
            if r.status_code in (404, 429):
                break
            continue
        why = check(c["expect"], got)
        ok += not why
        print(f"{'✓' if not why else '✗'} {time.time() - t:4.1f}s {'(저장)' if got.get('cached') else '      '} {c['q'][:44]}")
        if why:
            print("     ", "; ".join(why), "|", json.dumps({k: got.get(k) for k in ('conds', 'unsupported', 'sort')}, ensure_ascii=False)[:300])
    print(f"\n통과 {ok}/{len(cases)} ({ok / len(cases):.0%}) — 목표 92%")
    return ok, len(cases)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "https://tickermap-api.flytothejy.workers.dev")
