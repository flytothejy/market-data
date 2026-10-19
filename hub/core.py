"""공통: 경로, HTTP(재시도·속도 제한), 저장(parquet upsert), 실행 상태 기록·점검표"""
import json, os, sys, time, datetime as dt
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent


def _load_env_file():
    """저장소 최상위의 .env (KEY=VALUE, 커밋 안 됨)를 읽어 환경변수로 — setx가 안 먹을 때를 위한 대안"""
    p = ROOT / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and v and not os.environ.get(k):
            os.environ[k] = v


_load_env_file()
DATA = Path(os.environ.get("HUB_DATA", ROOT / "data" / "hub"))
STATUS = DATA / "_status"
UA_BROWSER = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def now_utc():
    return dt.datetime.now(dt.timezone.utc)


def log(*a):
    print(f"[{dt.datetime.now():%H:%M:%S}]", *a, flush=True)


# ---------------------------------------------------------------- HTTP
class Http:
    """요청 간 최소 간격(rate)과 재시도를 갖춘 세션"""

    def __init__(self, headers=None, rate=5.0, retries=4, timeout=30):
        self.s = requests.Session()
        self.s.headers.update(headers or {"User-Agent": UA_BROWSER})
        self.gap = 1.0 / rate
        self.retries, self.timeout = retries, timeout
        self._last = 0.0
        self.calls, self.retries_used, self.net_sec = 0, 0, 0.0

    def stats(self):
        return f"{self.calls}회 · 재시도 {self.retries_used}회 · 평균 {self.net_sec/max(self.calls,1):.2f}초"

    def get(self, url, ok404=False, **kw):
        err = None
        for i in range(self.retries):
            if i:
                self.retries_used += 1
            wait = self._last + self.gap - time.time()
            if wait > 0:
                time.sleep(wait)
            self._last = time.time()
            self.calls += 1
            try:
                t0 = time.time()
                r = self.s.get(url, timeout=self.timeout, **kw)
                self.net_sec += time.time() - t0
                if r.status_code in (403, 404) and ok404:
                    return None
                if r.status_code in (429, 500, 502, 503, 504):
                    err = f"HTTP {r.status_code}"
                    time.sleep(2 ** i * 2)
                    continue
                r.raise_for_status()
                return r
            except requests.RequestException as e:
                err = str(e)
                time.sleep(2 ** i)
        raise RuntimeError(f"GET 실패 ({err}): {url}")


def sec_http():
    email = os.environ.get("SEC_CONTACT_EMAIL", "").strip()
    if "@" not in email:
        sys.exit("SEC_CONTACT_EMAIL 환경변수가 없습니다. SEC는 연락처 이메일을 요구합니다.\n"
                 "  Windows:  setx SEC_CONTACT_EMAIL \"you@example.com\"  (새 터미널부터 적용)\n"
                 "  GitHub:   저장소 Settings → Secrets → SEC_CONTACT_EMAIL")
    # SEC 공정 접근 정책: 초당 10회 이하, 연락처가 담긴 User-Agent
    return Http({"User-Agent": f"market-data-hub {email}", "Accept-Encoding": "gzip, deflate"}, rate=8)


def data_go_kr_key(api):
    """공공데이터포털 키: 계정당 하나라 보통 DATA_GO_KR_KEY 하나로 충분.
    특정 API만 다른 키를 써야 하면 DATA_GO_KR_KEY_<API> 로 덮어씀 (예: DATA_GO_KR_KEY_ETF)"""
    return (os.environ.get(f"DATA_GO_KR_KEY_{api.upper()}") or os.environ.get("DATA_GO_KR_KEY") or "").strip()


# ---------------------------------------------------------------- 저장
def upsert(path: Path, new: pd.DataFrame, keys, sort=None):
    """parquet 파일에 행 추가 — 같은 키는 새 값으로 덮어씀"""
    path.parent.mkdir(parents=True, exist_ok=True)
    if new is None or new.empty:
        return pd.read_parquet(path) if path.exists() else pd.DataFrame()
    if path.exists():
        old = pd.read_parquet(path)
        new = pd.concat([old, new], ignore_index=True)
    new = new.drop_duplicates(subset=keys, keep="last")
    new = new.sort_values(sort or keys).reset_index(drop=True)
    tmp = path.with_suffix(".tmp")
    new.to_parquet(tmp, index=False)
    tmp.replace(path)
    return new


def write(path: Path, df: pd.DataFrame):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    df.to_parquet(tmp, index=False)
    tmp.replace(path)


def read(path: Path, **kw):
    return pd.read_parquet(path, **kw) if Path(path).exists() else pd.DataFrame()


# ---------------------------------------------------------------- 상태·점검표
class Run:
    """수집기 1회 실행 기록 — 끝나면 _status/<name>.json 저장 + 점검표 출력"""

    def __init__(self, name):
        self.name, self.t0 = name, time.time()
        self.info, self.warn = {}, []

    def set(self, **kw):
        self.info.update(kw)

    def warning(self, msg):
        self.warn.append(str(msg))
        log("주의:", msg)

    def done(self, ok=True):
        rec = {"source": self.name, "ok": ok and not any(w.startswith("치명") for w in self.warn),
               "finished_utc": now_utc().isoformat(timespec="seconds"),
               "seconds": round(time.time() - self.t0, 1), **self.info,
               "warnings": self.warn[:30], "n_warnings": len(self.warn)}
        STATUS.mkdir(parents=True, exist_ok=True)
        prev = {}
        p = STATUS / f"{self.name}.json"
        if p.exists():
            try:
                prev = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
        rec["history"] = ([{k: prev.get(k) for k in ("finished_utc", "ok", "seconds", "rows_new")}] + prev.get("history", []))[:30] if prev else []
        p.write_text(json.dumps(rec, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        print_report([rec])
        return rec


def print_report(recs):
    print("\n" + "=" * 78)
    for r in recs:
        flag = "정상" if r.get("ok") else "확인 필요"
        print(f"■ {r['source']}  [{flag}]  {r.get('seconds', '?')}초  ({r.get('finished_utc', '')})")
        skip = {"source", "ok", "finished_utc", "seconds", "warnings", "n_warnings", "history"}
        for k, v in r.items():
            if k in skip:
                continue
            print(f"    {k:<22} {v}")
        if r.get("n_warnings"):
            print(f"    주의 {r['n_warnings']}건:")
            for w in r.get("warnings", [])[:8]:
                print(f"      - {w}")
    print("=" * 78 + "\n")


def load_status():
    if not STATUS.exists():
        return []
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(STATUS.glob("*.json"))]
