"""뉴스 제목 톤(긍정/중립/부정) — 금융 단어 사전 기반 규칙. AI를 쓰지 않으므로 빠르고 공짜지만 거칠다.
점수 = 긍정 단어 수 - 부정 단어 수 → +1 이상 긍정, -1 이하 부정, 그 외 중립."""
import re

POS = {
    "beat", "beats", "tops", "topped", "surge", "surges", "surged", "soar", "soars", "soared", "jump", "jumps", "jumped",
    "rally", "rallies", "rallied", "gain", "gains", "gained", "rise", "rises", "rose", "climb", "climbs", "climbed",
    "record", "upgrade", "upgrades", "upgraded", "outperform", "buy", "bullish", "raises", "raised", "boost", "boosts",
    "boosted", "strong", "stronger", "growth", "profit", "profitable", "wins", "win", "won", "award", "awarded",
    "approval", "approved", "approves", "breakthrough", "expands", "expansion", "partnership", "partners", "launch",
    "launches", "dividend", "buyback", "repurchase", "exceeds", "exceeded", "optimistic", "upbeat", "rebound",
    "rebounds", "highs", "milestone", "accelerates", "momentum", "upside", "skyrocket", "skyrockets", "skyrocketed", "soaring", "surging", "jumping", "climbing", "rallying", "triumph", "triumphs", "triumphed", "positive", "success", "successful",
}
NEG = {
    "miss", "misses", "missed", "plunge", "plunges", "plunged", "tumble", "tumbles", "tumbled", "sink", "sinks", "sank",
    "drop", "drops", "dropped", "fall", "falls", "fell", "slide", "slides", "slid", "slump", "slumps", "decline",
    "declines", "declined", "downgrade", "downgrades", "downgraded", "underperform", "sell", "bearish", "cuts", "cut",
    "lowers", "lowered", "weak", "weaker", "loss", "losses", "lawsuit", "sues", "sued", "probe", "investigation",
    "recall", "recalls", "layoffs", "layoff", "bankruptcy", "default", "fraud", "warning", "warns", "warned",
    "delay", "delays", "delayed", "halt", "halts", "halted", "fined", "penalty", "lows", "concern", "concerns",
    "risk", "risks", "downside", "negative", "crash", "crashes", "fears", "slowdown", "dilution", "resigns", "exits",
    "subpoena", "rejected", "rejects", "terminated", "suspends", "suspended", "headwinds", "plunging", "tumbling", "sinking", "sliding", "slumping", "crashing", "tanks", "tanked", "tanking", "trim", "trims", "trimmed", "slashes", "slashed",
}
NOT = {"not", "no", "never", "fails", "failed", "without"}
W = re.compile(r"[a-z']+")


def score(title):
    ws = W.findall(str(title or "").lower())
    s = 0
    for i, w in enumerate(ws):
        v = 1 if w in POS else -1 if w in NEG else 0
        if v and i and ws[i - 1] in NOT:
            v = -v
        s += v
    return s


def tone(title):
    s = score(title)
    return 1 if s >= 1 else -1 if s <= -1 else 0


if __name__ == "__main__":
    for t in ["Nvidia beats estimates, raises guidance", "Tesla shares tumble after delivery miss",
              "Apple to hold event on Oct 28", "Intel did not miss estimates"]:
        print(tone(t), t)
