"""SEC EDGAR 수집 — 제출 목록(8-K 항목·13D/G·144·10-K/Q …), Form 4 내부자 거래, XBRL 재무

저장
  data/hub/sec/filings.parquet     cik, ticker, accession, form, filed, report_date, accepted, items, doc, size
  data/hub/sec/insider.parquet     거래 1건 = 1행 (Form 4 비파생 거래표)
  data/hub/sec/insider_done.parquet 처리한 Form 4 접수번호
  data/hub/sec/facts.parquet       cik, taxonomy, tag, unit, start, end, val, fy, fp, form, filed, accn, frame
SEC 정책: 초당 10회 이하 + 연락처 User-Agent (환경변수 SEC_CONTACT_EMAIL)
"""
import datetime as dt
import xml.etree.ElementTree as ET
import pandas as pd

from .core import DATA, Run, log, read, sec_http, upsert, write
from . import universe

S_DIR = DATA / "sec"
FORMS = {"8-K", "8-K/A", "10-K", "10-K/A", "10-Q", "10-Q/A", "20-F", "20-F/A", "40-F", "6-K", "DEF 14A",
         "3", "4", "4/A", "5", "144", "S-1", "S-3", "S-4", "SC 13D", "SC 13D/A", "SC 13G", "SC 13G/A",
         "SCHEDULE 13D", "SCHEDULE 13D/A", "SCHEDULE 13G", "SCHEDULE 13G/A", "SC TO-T", "SC 14D9", "11-K", "NT 10-K", "NT 10-Q"}
ITEMS_8K = {"1.01": "중요 계약 체결", "1.02": "중요 계약 해지", "1.03": "파산", "1.05": "사이버 보안 사고",
            "2.01": "인수·매각 완료", "2.02": "실적 발표", "2.03": "채무 발생", "2.05": "구조조정 비용",
            "2.06": "자산 손상", "3.01": "상장 요건 미달", "3.02": "미등록 증권 발행", "3.03": "주주 권리 변경",
            "4.01": "감사인 변경", "4.02": "재무제표 신뢰 불가", "5.01": "지배권 변경", "5.02": "임원·이사 변동",
            "5.03": "정관 변경", "5.07": "주총 결과", "7.01": "공정 공시(Reg FD)", "8.01": "기타 사건", "9.01": "재무제표·첨부"}


def _cik10(c):
    return f"{int(c):010d}"


# ---------------------------------------------------------------- 제출 목록
def run_filings(limit=0, **_):
    R = Run("sec_filings")
    http = sec_http()
    U = universe.load("stock").dropna(subset=["cik"])
    if limit:
        U = U.head(limit)
    rows, fail = [], []
    for i, r in enumerate(U.itertuples()):
        try:
            j = http.get(f"https://data.sec.gov/submissions/CIK{_cik10(r.cik)}.json").json()
        except Exception as e:
            fail.append(r.ticker)
            continue
        rc = j.get("filings", {}).get("recent", {})
        if not rc:
            continue
        df = pd.DataFrame(rc)
        for c in ("items", "reportDate", "acceptanceDateTime", "primaryDocument", "primaryDocDescription", "size"):
            if c not in df:
                df[c] = None
        df = df[df["form"].isin(FORMS)]
        if df.empty:
            continue
        rows.append(pd.DataFrame({
            "cik": int(r.cik), "ticker": r.ticker, "accession": df["accessionNumber"], "form": df["form"],
            "filed": pd.to_datetime(df["filingDate"], errors="coerce"), "report_date": pd.to_datetime(df.get("reportDate"), errors="coerce"),
            "accepted": df.get("acceptanceDateTime"), "items": df.get("items", "").fillna(""),
            "doc": df.get("primaryDocument"), "doc_desc": df.get("primaryDocDescription"), "size": df.get("size")}))
        if (i + 1) % 100 == 0:
            log(f"  제출 목록 {i+1}/{len(U)}")
    if not rows:
        R.warning("치명: 받은 제출 목록이 없음")
        return R.done(ok=False)
    new = pd.concat(rows, ignore_index=True)
    old = read(S_DIR / "filings.parquet")
    old_acc = set(old.accession) if not old.empty else set()
    added = new[~new.accession.isin(old_acc)].drop_duplicates("accession")
    allf = upsert(S_DIR / "filings.parquet", new, ["accession", "cik"], sort=["filed", "accession"])
    if fail:
        R.warning(f"실패 {len(fail)}개: {', '.join(fail[:15])}")
    last7 = allf[allf.filed >= allf.filed.max() - pd.Timedelta(days=7)]
    k8 = last7[last7.form.str.startswith("8-K")]
    item_cnt = pd.Series([x for s in k8["items"] for x in str(s).split(",") if x]).value_counts().head(6)
    R.set(http=http.stats())
    R.set(companies=len(U) - len(fail), rows_total=len(allf), rows_new=len(added), latest_filed=str(allf.filed.max().date()),
          first_filed=str(allf.filed.min().date()),
          new_by_form=", ".join(f"{k} {v}" for k, v in added.form.value_counts().head(8).items()) or "-",
          last7d_8k_items=", ".join(f"{ITEMS_8K.get(k, k)} {v}" for k, v in item_cnt.items()) or "-")
    return R.done()


# ---------------------------------------------------------------- Form 4
def _t(e, path):
    x = e.find(path)
    return x.text.strip() if x is not None and x.text else None


def parse_form4(xml_text):
    root = ET.fromstring(xml_text)
    owners = root.findall("reportingOwner")
    names = "; ".join(filter(None, (_t(o, "reportingOwnerId/rptOwnerName") for o in owners)))
    rel = owners[0].find("reportingOwnerRelationship") if owners else None
    role = {"director": _t(rel, "isDirector") if rel is not None else None, "officer": _t(rel, "isOfficer") if rel is not None else None,
            "ten_pct": _t(rel, "isTenPercentOwner") if rel is not None else None,
            "title": _t(rel, "officerTitle") if rel is not None else None}
    flag = lambda v: str(v).strip().lower() in ("1", "true")
    plan = flag(_t(root, "aff10b5One"))
    base = {"issuer_cik": _t(root, "issuer/issuerCik"), "issuer_symbol": _t(root, "issuer/issuerTradingSymbol"), "owner": names, "owner_cik": _t(owners[0], "reportingOwnerId/rptOwnerCik") if owners else None,
            "is_director": flag(role["director"]), "is_officer": flag(role["officer"]), "is_10pct": flag(role["ten_pct"]),
            "title": role["title"], "plan_10b5_1": plan}
    out = []
    for tr in root.findall("nonDerivativeTable/nonDerivativeTransaction"):
        sh = _t(tr, "transactionAmounts/transactionShares/value")
        px = _t(tr, "transactionAmounts/transactionPricePerShare/value")
        out.append({**base, "security": _t(tr, "securityTitle/value"),
                    "date": _t(tr, "transactionDate/value"), "code": _t(tr, "transactionCoding/transactionCode"),
                    "shares": float(sh) if sh else None, "price": float(px) if px else None,
                    "acq_disp": _t(tr, "transactionAmounts/transactionAcquiredDisposedCode/value"),
                    "owned_after": float(_t(tr, "postTransactionAmounts/sharesOwnedFollowingTransaction/value") or "nan"),
                    "direct": _t(tr, "ownershipNature/directOrIndirectOwnership/value")})
    return out


def run_insider(limit=0, days=90, **_):
    R = Run("sec_insider")
    http = sec_http()
    F = read(S_DIR / "filings.parquet")
    if F.empty:
        raise SystemExit("제출 목록이 없습니다. 먼저  python -m hub run sec_filings")
    done = read(S_DIR / "insider_done.parquet")
    done_acc = set(done.accession) if not done.empty else set()
    cut = pd.Timestamp(dt.date.today() - dt.timedelta(days=days))
    todo = F[F.form.isin(["4", "4/A"]) & (F.filed >= cut) & ~F.accession.isin(done_acc)].drop_duplicates("accession").sort_values("filed", ascending=False)
    if limit:
        todo = todo.head(limit)
    log(f"Form 4 {len(todo)}건 처리 (최근 {days}일, 이미 처리 {len(done_acc)}건 제외)")
    US = universe.load("stock").dropna(subset=["cik"]).drop_duplicates("cik")
    cik2t = dict(zip(US.cik.astype(int), US.ticker))
    rows, ok, bad, foreign = [], [], [], 0
    for i, r in enumerate(todo.itertuples()):
        doc = str(r.doc or "")
        doc = doc.split("/")[-1] if doc.startswith("xsl") else doc
        url = f"https://www.sec.gov/Archives/edgar/data/{int(r.cik)}/{r.accession.replace('-', '')}/{doc}"
        try:
            for x in parse_form4(http.get(url).content):
                # 제출 목록에는 '그 회사가 남의 주식을 산 신고'(예: 버크셔의 OXY 매수)도 섞여 있음 → 발행회사 기준으로 귀속
                icik = int(x["issuer_cik"]) if x.get("issuer_cik") and str(x["issuer_cik"]).strip().isdigit() else None
                if icik is None or icik not in cik2t:
                    foreign += 1
                    continue
                rows.append({"accession": r.accession, "cik": icik, "ticker": cik2t[icik], "filed": r.filed, **x})
            ok.append(r.accession)
        except Exception as e:
            bad.append(f"{r.ticker} {r.accession}: {str(e)[:60]}")
        if (i + 1) % 200 == 0:
            log(f"  Form 4 {i+1}/{len(todo)}")
            _flush(rows, ok); rows, ok = [], []
    _flush(rows, ok)
    I = read(S_DIR / "insider.parquet")
    if not I.empty:                                     # 예전 방식으로 잘못 귀속된 행 정리 (발행회사 ≠ 귀속 종목)
        sym = I["issuer_symbol"].astype(str).str.upper().str.replace(r"[./ ]", "-", regex=True)
        ic = pd.to_numeric(I.get("issuer_cik"), errors="coerce") if "issuer_cik" in I else pd.Series(float("nan"), index=I.index)
        US2 = universe.load("stock").dropna(subset=["cik"])
        s2c = dict(zip(US2.ticker, US2.cik.astype(int)))
        symc = sym.map(s2c)
        wrong = (ic.notna() & (ic != I["cik"])) | (ic.isna() & (symc != I["cik"]))   # 우리 대상이 아닌 발행회사도 제외
        if wrong.any():
            I = I[~wrong]
            write(S_DIR / "insider.parquet", I)
            R.set(fixed_misattributed=int(wrong.sum()))
    if bad:
        R.warning(f"해석 실패 {len(bad)}건 — 예: {bad[0]}")
    if not I.empty:
        I["date"] = pd.to_datetime(I["date"], errors="coerce")
        recent = I[I.date >= I.date.max() - pd.Timedelta(days=30)]
        buys = recent[recent.code == "P"]
        sells = recent[recent.code == "S"]
        R.set(rows_total=len(I), latest_trade=str(I.date.max().date()),
              last30d_buy=f"{len(buys)}건 ${(buys.shares*buys.price).sum()/1e6:,.1f}M",
              last30d_sell=f"{len(sells)}건 ${(sells.shares*sells.price).sum()/1e6:,.1f}M",
              top_buy=", ".join(buys.assign(v=buys.shares*buys.price).groupby("ticker").v.sum().nlargest(5).index) or "-")
    R.set(skipped_not_issuer=foreign)
    R.set(processed=len(todo) - len(bad), failed=len(bad), rows_new=len(todo) - len(bad), http=http.stats())
    return R.done()


def _flush(rows, ok):
    if rows:
        upsert(S_DIR / "insider.parquet", pd.DataFrame(rows), ["accession", "owner", "date", "code", "shares", "price", "security"], sort=["filed", "accession"])
    if ok:
        upsert(S_DIR / "insider_done.parquet", pd.DataFrame({"accession": ok}), ["accession"])


# ---------------------------------------------------------------- XBRL 재무
TAGS = {
    "us-gaap": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet", "RevenueFromContractWithCustomerIncludingAssessedTax",
                "RevenuesNetOfInterestExpense", "InterestAndDividendIncomeOperating", "NoninterestIncome", "InterestIncomeExpenseNet",
                "InterestIncomeOperating", "RegulatedAndUnregulatedOperatingRevenue", "ElectricUtilityRevenue",
                "OperatingLeasesIncomeStatementLeaseRevenue", "RevenueFromContractWithCustomerProductAndServiceExcludingAssessedTax",
                "CostOfRevenue", "CostOfGoodsAndServicesSold", "GrossProfit", "OperatingIncomeLoss", "NetIncomeLoss", "ProfitLoss",
                "NetIncomeLossAvailableToCommonStockholdersBasic", "IncomeLossFromContinuingOperations",
                "EarningsPerShareDiluted", "EarningsPerShareBasic", "WeightedAverageNumberOfDilutedSharesOutstanding",
                "ResearchAndDevelopmentExpense", "SellingGeneralAndAdministrativeExpense", "IncomeTaxExpenseBenefit", "InterestExpense",
                "DepreciationDepletionAndAmortization", "Assets", "Liabilities", "StockholdersEquity", "AssetsCurrent", "LiabilitiesCurrent",
                "CashAndCashEquivalentsAtCarryingValue", "LongTermDebt", "LongTermDebtNoncurrent", "InventoryNet", "AccountsReceivableNetCurrent",
                "NetCashProvidedByUsedInOperatingActivities", "PaymentsToAcquirePropertyPlantAndEquipment",
                "PaymentsForRepurchaseOfCommonStock", "PaymentsOfDividends", "PaymentsOfDividendsCommonStock", "ShareBasedCompensation"],
    "ifrs-full": ["Revenue", "RevenueFromContractsWithCustomers", "InterestIncome", "GrossProfit", "ProfitLossFromOperatingActivities", "ProfitLoss", "ProfitLossAttributableToOwnersOfParent",
                  "DilutedEarningsLossPerShare", "Assets", "Liabilities", "Equity", "CashAndCashEquivalents",
                  "CashFlowsFromUsedInOperatingActivities", "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"],
    "dei": ["EntityCommonStockSharesOutstanding", "EntityPublicFloat"],
}
REPORT_FORMS = {"10-K", "10-Q", "10-K/A", "10-Q/A", "20-F", "20-F/A", "40-F", "6-K"}


def parse_facts(j, cik):
    out = []
    facts = j.get("facts", {})
    for tax, tags in TAGS.items():
        for tag in tags:
            node = facts.get(tax, {}).get(tag)
            if not node:
                continue
            for unit, arr in node.get("units", {}).items():
                for f in arr:
                    if f.get("form") not in REPORT_FORMS:
                        continue
                    out.append((cik, tax, tag, unit, f.get("start"), f.get("end"), f.get("val"), f.get("fy"), f.get("fp"),
                                f.get("form"), f.get("filed"), f.get("accn"), f.get("frame")))
    return out


FACT_COLS = ["cik", "taxonomy", "tag", "unit", "start", "end", "val", "fy", "fp", "form", "filed", "accn", "frame"]


def run_financials(limit=0, full=False, **_):
    R = Run("sec_financials")
    http = sec_http()
    U = universe.load("stock").dropna(subset=["cik"])
    if limit:
        U = U.head(limit)
    facts_p = S_DIR / "facts.parquet"
    stamp = read(S_DIR / "facts_fetched.parquet")        # cik, fetched
    F = read(S_DIR / "filings.parquet")
    if full or stamp.empty:
        todo = U
    else:
        last = stamp.set_index("cik").fetched
        rep = F[F.form.isin(REPORT_FORMS)].groupby("cik").filed.max() if not F.empty else pd.Series(dtype="datetime64[ns]")
        need = [c for c in U.cik.astype(int) if c not in last.index or (c in rep.index and rep[c] > last[c])]
        todo = U[U.cik.astype(int).isin(need)]
    log(f"재무 수집 {len(todo)}개 회사 ({'전체' if full or stamp.empty else '새 보고서가 나온 회사만'})")
    rows, fetched, fail = [], [], []
    for i, r in enumerate(todo.itertuples()):
        cik = int(r.cik)
        try:
            resp = http.get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{_cik10(cik)}.json", ok404=True)
            if resp is not None:
                rows += parse_facts(resp.json(), cik)
            fetched.append(cik)
        except Exception as e:
            fail.append(r.ticker)
        if (i + 1) % 100 == 0:
            log(f"  재무 {i+1}/{len(todo)}")
            _save_facts(rows, fetched, facts_p); rows, fetched = [], []
    _save_facts(rows, fetched, facts_p)
    A = read(facts_p)
    if fail:
        R.warning(f"실패 {len(fail)}개: {', '.join(fail[:15])}")
    if not A.empty:
        rev_tags = {"Revenues", "RevenuesNetOfInterestExpense", "InterestIncomeExpenseNet", "InterestIncomeOperating",
                    "RegulatedAndUnregulatedOperatingRevenue", "ElectricUtilityRevenue", "OperatingLeasesIncomeStatementLeaseRevenue",
                    "RevenueFromContractsWithCustomers", "InterestAndDividendIncomeOperating", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet",
                    "RevenueFromContractWithCustomerIncludingAssessedTax", "Revenue"}
        A["end"] = pd.to_datetime(A["end"], errors="coerce")
        recent = A[(A.end >= pd.Timestamp.today() - pd.Timedelta(days=550))]
        has_rev = recent[recent.tag.isin(rev_tags)].cik.nunique()
        has_ni = recent[recent.tag.isin({"NetIncomeLoss", "ProfitLoss", "NetIncomeLossAvailableToCommonStockholdersBasic", "ProfitLossAttributableToOwnersOfParent"})].cik.nunique()
        nU = U.cik.nunique()
        ncomp = A.cik.nunique()
        R.set(companies=ncomp, facts_rows=len(A), first_period=str(A.end.min().date()),
              revenue_coverage=f"{has_rev}/{nU} ({has_rev/nU*100:.0f}%)", net_income_coverage=f"{has_ni}/{nU} ({has_ni/nU*100:.0f}%)")
        missing_rev = sorted(set(U.cik.astype(int)) - set(recent[recent.tag.isin(rev_tags)].cik))
        if missing_rev:
            R.set(no_recent_revenue=", ".join(U[U.cik.astype(int).isin(missing_rev)].ticker.tolist()[:20]))
        missing_ni = sorted(set(U.cik.astype(int)) - set(recent[recent.tag.isin({"NetIncomeLoss", "ProfitLoss", "NetIncomeLossAvailableToCommonStockholdersBasic", "ProfitLossAttributableToOwnersOfParent"})].cik))
        if missing_ni:
            R.set(no_recent_net_income=", ".join(U[U.cik.astype(int).isin(missing_ni)].ticker.tolist()[:20]))
        if has_rev / max(nU, 1) < 0.9:
            R.warning("최근 매출 값이 있는 회사가 90% 미만 — 매출 태그 보강 필요 (은행·보험은 매출 태그가 다름)")
    R.set(fetched=len(todo) - len(fail), rows_new=len(todo) - len(fail), http=http.stats())
    return R.done()


def _save_facts(rows, fetched, facts_p):
    if rows:
        df = pd.DataFrame(rows, columns=FACT_COLS)
        df["val"] = pd.to_numeric(df["val"], errors="coerce")
        df["fy"] = pd.to_numeric(df["fy"], errors="coerce").astype("Int64")
        # 회사 단위로 통째로 교체 (재작성된 값 반영)
        old = read(facts_p)
        if not old.empty:
            old = old[~old.cik.isin(set(df.cik))]
            df = pd.concat([old, df], ignore_index=True)
        write(facts_p, df)
    if fetched:
        upsert(S_DIR / "facts_fetched.parquet", pd.DataFrame({"cik": fetched, "fetched": pd.Timestamp.now().normalize()}), ["cik"])
