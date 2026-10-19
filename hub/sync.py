"""Cloudflare R2 동기화 — data/hub 폴더 ↔ R2 버킷 (S3 호환 API)

  python -m hub sync push [--dry]   PC/Actions의 data/hub 변경분을 R2로 올림 (크기·MD5가 같으면 건너뜀)
  python -m hub sync pull [--dry]   R2의 파일을 data/hub로 내려받음 (같은 파일은 건너뜀)
  python -m hub sync ls             R2에 있는 파일 목록·총 용량

필요한 환경변수(.env 또는 GitHub Secrets)
  R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET
올리지 않는 것: _status 이외의 임시 파일(.tmp), 10-K 원문(저장소 밖 data_ext에 있음)
"""
import hashlib, os, sys
from pathlib import Path

from .core import DATA, log

PREFIX = "hub/"


def client():
    need = ["R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET"]
    miss = [k for k in need if not os.environ.get(k)]
    if miss:
        sys.exit("R2 설정이 없습니다: " + ", ".join(miss) + "\n  .env 파일이나 GitHub Secrets에 넣어 주세요")
    import boto3
    from botocore.config import Config
    s3 = boto3.client("s3", endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
                      aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"], aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
                      region_name="auto", config=Config(retries={"max_attempts": 5, "mode": "standard"}))
    return s3, os.environ["R2_BUCKET"]


def _md5(p):
    h = hashlib.md5()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def remote_index(s3, bucket):
    out, tok = {}, None
    while True:
        kw = {"Bucket": bucket, "Prefix": PREFIX}
        if tok:
            kw["ContinuationToken"] = tok
        r = s3.list_objects_v2(**kw)
        for o in r.get("Contents", []):
            out[o["Key"][len(PREFIX):]] = (o["Size"], o["ETag"].strip('"'))
        if not r.get("IsTruncated"):
            return out
        tok = r["NextContinuationToken"]


def local_files():
    for p in DATA.rglob("*"):
        if p.is_file() and not p.name.endswith(".tmp"):
            yield p.relative_to(DATA).as_posix(), p


def push(dry=False):
    s3, b = client()
    rem = remote_index(s3, b)
    n = size = 0
    for rel, p in local_files():
        st = p.stat().st_size
        r = rem.get(rel)
        if r and r[0] == st and ("-" in r[1] or r[1] == _md5(p)):   # 여러 조각 업로드면 크기만 비교
            continue
        n += 1; size += st
        if not dry:
            s3.upload_file(str(p), b, PREFIX + rel)
    log(f"올림 {n}개 · {size/1e6:,.1f}MB" + (" (시험)" if dry else ""))


def pull(dry=False, only=None):
    s3, b = client()
    rem = remote_index(s3, b)
    n = size = 0
    for rel, (sz, etag) in rem.items():
        if only and not any(rel.startswith(o) for o in only):
            continue
        p = DATA / rel
        if p.exists() and p.stat().st_size == sz and ("-" in etag or _md5(p) == etag):
            continue
        n += 1; size += sz
        if not dry:
            p.parent.mkdir(parents=True, exist_ok=True)
            s3.download_file(b, PREFIX + rel, str(p))
    log(f"받음 {n}개 · {size/1e6:,.1f}MB" + (" (시험)" if dry else ""))


def ls():
    s3, b = client()
    rem = remote_index(s3, b)
    tot = sum(v[0] for v in rem.values())
    top = {}
    for k, (sz, _) in rem.items():
        top[k.split("/")[0]] = top.get(k.split("/")[0], 0) + sz
    for k, v in sorted(top.items(), key=lambda x: -x[1]):
        print(f"  {k:<14} {v/1e6:>9,.1f}MB")
    print(f"  합계 {len(rem)}개 · {tot/1e6:,.1f}MB (무료 한도 10GB)")
