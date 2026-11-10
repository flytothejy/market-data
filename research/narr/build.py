import pandas as pd, numpy as np, json
px = pd.concat([pd.read_parquet(f'r2dl/px_{y}.parquet', columns=['date','ticker','adj_close']) for y in (2024, 2025, 2026)])
px['date'] = pd.to_datetime(px.date); P = px.pivot_table(index='date', columns='ticker', values='adj_close').sort_index().astype(float)
P = P[P.index >= '2024-11-01']
END = P.index[-1]
CARDS = [
 dict(id='ai', q='AI 투자는 거품일까?', tag='AI', tk='NVDA AVGO AMD ORCL VRT ANET'.split(), st='주의', line='빅테크 설비투자가 벌어들이는 현금을 넘어섰다. 차이는 빚으로 메운다.', fact='설비투자 ÷ 영업현금흐름 1.16배'),
 dict(id='memory', q='메모리 호황, 정점은 지났을까?', tag='반도체', tk='MU SNDK WDC STX'.split(), st='변경', line='3분기에 재고와 증설, 두 신호가 처음 움직였다. 주가는 이미 −40%.', fact='마이크론 재고 +24% (2분기 −2%)'),
 dict(id='power', q='AI의 진짜 병목은 전력이다?', tag='전력·원전', tk='CEG VST GEV ETN VRT NRG TLN BWXT OKLO'.split(), st='동의', line='데이터센터 투자 대비 전력·냉각 투자는 아직 한참 모자란다.', fact='투자 격차 6.5배'),
 dict(id='space', q='우주, 이제 진짜 산업인가?', tag='우주', tk='RKLB ASTS PL'.split(), st='기대만', line='매출은 빠르게 늘지만 주가는 그보다 훨씬 앞서 있다. 지금은 거의 기대로 움직인다.', fact='시가총액 = 연매출의 수십 배'),
 dict(id='quantum', q='양자컴퓨터, 돈이 되기 시작했나?', tag='양자', tk=['IONQ'], st='기대만', line='매출이 1년 새 4배가 됐지만 아직 분기 8천만 달러다.', fact='아이온큐 분기 매출 $80M'),
 dict(id='saas', q='AI가 소프트웨어를 죽일까?', tag='소프트웨어', tk='CRM ADBE NOW WDAY TEAM HUBS INTU'.split(), st='주의', line='성장은 느려졌지만 고객은 떠나지 않았다. 다만 계약 잔고가 처음 내려왔다.', fact='매출 대비 주가 0.67배'),
 dict(id='glp1', q='비만약이 식품 회사를 무너뜨릴까?', tag='헬스케어', tk='LLY GIS KHC MDLZ HSY CAG CPB SJM'.split(), st='변경', line='식품 매출은 2년째 늘지 않는다. 시장의 판결이 맞아 가고 있다.', fact='포장식품 매출 −1.4%', basket_note='릴리 + 포장식품'),
 dict(id='gold', q='금값, 아직 더 갈까?', tag='금·원자재', tk='GLD NEM GDX'.split(), st='판정 중', line='광산 회사 매출이 금값을 따라 1년 새 15% 늘었다.', fact='뉴몬트 분기 매출 $6.4B'),
 dict(id='crypto', q='비트코인, 제도권에 들어왔나?', tag='암호화폐', tk='IBIT MSTR COIN HOOD'.split(), st='판정 중', line='거래소 매출은 오히려 1년 새 35% 줄었다. 가격과 사업이 따로 간다.', fact='코인베이스 분기 매출 −35%'),
 dict(id='consumer', q='미국 소비자, 지갑을 닫고 있나?', tag='소비', tk='MCD CMG SBUX DRI YUM QSR'.split(), st='변경', line='신용은 더 좋아졌는데 외식 매출 증가율이 반으로 줄었다.', fact='외식 매출 +3.4% (1년 전 +7.2%)'),
 dict(id='defense', q='전쟁의 시대, 방산은 이미 비싼가?', tag='방산', tk='LMT RTX GD NOC LHX HII'.split(), st='숫자가 앞섬', line='3년치 넘는 일감이 쌓였는데 주가는 매출만큼만 올랐다.', fact='계약 잔고 = 연매출 3.5년치'),
 dict(id='tariff', q='관세, 기업 이익을 망쳤나?', tag='관세', tk='WMT COST TGT HD NKE LULU HAS MAT'.split(), st='반대', line='장난감까지 이익률이 돌아왔다. 비용은 가격으로 넘어갔다.', fact='5개 묶음 중 4곳 이익률 플러스'),
]
SPY = P['SPY']
def idx(tk, start):
    x = P.loc[start:, [t for t in tk if t in P]].dropna(axis=1, how='all')
    x = x.ffill(); base = x.bfill().iloc[0]
    return (x / base).mean(axis=1) * 100
def r(s, d):
    s0 = s[s.index >= pd.Timestamp(d)].iloc[0]; return round(float(s.iloc[-1] / s0 - 1), 4)
out = []
for c in CARDS:
    s = idx(c['tk'], '2024-11-06')
    spark = s.resample('W-FRI').last()
    spark = spark[spark.index >= END - pd.Timedelta(days=372)]
    c2 = {k: v for k, v in c.items()}
    c2.update(ret1y=r(s, '2025-11-06'), ytd=r(s, '2026-01-02'), spy1y=r(SPY, '2025-11-06'), sinceq2=r(s, '2026-06-30'), spark=[round(float(v / spark.iloc[0] * 100), 1) for v in spark.values])
    out.append(c2)
# detail series: daily from 2025-01-02
def det(tk):
    s = idx(tk, '2025-01-02'); sp = SPY.loc['2025-01-02':]; sp = sp / sp.iloc[0] * 100
    return [{'d': d.strftime('%Y-%m-%d'), 'v': round(float(v), 2), 'spy': round(float(sp.loc[d]), 2)} for d, v in s.items()]
D = {'memory': det(CARDS[1]['tk']), 'space': det(CARDS[3]['tk'])}
# per-ticker 1y/ytd for tag lists
tick = {}
for c in CARDS:
    for t in c['tk']:
        if t in P and t not in tick:
            s = P[t].dropna(); tick[t] = dict(last=round(float(s.iloc[-1]), 2), ytd=r(s, '2026-01-02'), y1=r(s, '2025-11-06') if s.index[0] <= pd.Timestamp('2025-11-06') else None, q2=r(s, '2026-06-30'))
json.dump(dict(asof=END.strftime('%Y-%m-%d'), cards=out, detail=D, tick=tick), open('narr/data.json', 'w'), ensure_ascii=False)
for c in out: print(c['id'], c['ret1y'], c['ytd'], c['sinceq2'], 'spy', c['spy1y'])
print({t: tick[t] for t in ['MU','SNDK','WDC','STX','RKLB','ASTS','PL']})
