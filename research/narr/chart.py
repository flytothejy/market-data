import sys, json, numpy as np, pandas as pd
sys.path.insert(0, 'narr'); from stage import feats, stage
TK = ['MU', 'SNDK', 'WDC', 'STX', 'LRCX']
NM = {'MU': '마이크론', 'SNDK': '샌디스크', 'WDC': '웨스턴디지털', 'STX': '씨게이트', 'LRCX': '램리서치'}
L, R = 56, 1024; D0, D1 = pd.Timestamp('2022-01-03'), pd.Timestamp('2026-11-06')
X = lambda d: L + (pd.Timestamp(d) - D0).days / (D1 - D0).days * (R - L)
MUD = {'2021Q4': '2021-12-20', '2022Q1': '2022-03-29', '2022Q2': '2022-06-30', '2022Q3': '2022-09-29', '2022Q4': '2022-12-21', '2023Q1': '2023-03-28', '2023Q2': '2023-06-28', '2023Q3': '2023-09-27', '2023Q4': '2023-12-20', '2024Q1': '2024-03-20', '2024Q2': '2024-06-26', '2024Q3': '2024-09-25', '2024Q4': '2024-12-18', '2025Q1': '2025-03-20', '2025Q2': '2025-06-25', '2025Q3': '2025-09-23', '2025Q4': '2025-12-17', '2026Q1': '2026-03-18', '2026Q2': '2026-06-24', '2026Q3': '2026-09-30'}
def eff(t, q):  # date the quarter becomes known
    if t == 'MU': return pd.Timestamp(MUD.get(str(q), str(q.end_time.date())))
    return (q.end_time + pd.Timedelta(days=30)).normalize()
ST = {}
for t in TK:
    s = stage(feats(t)); s = s[s.index >= pd.Period('2021Q1')]
    ST[t] = [(eff(t, q), r.stage, float(r.rev) if pd.notna(r.rev) else 0.0) for q, r in s.iterrows() if isinstance(r.stage, str)]
# segments per company
COL = {'발화': '#C7D2FE', '확산': '#7DA7F5', '견고': '#1D4ED8', '균열': '#E59A1C', '붕괴': '#B42318'}
def segs(t):
    out = []
    ev = [(d, s) for d, s, _ in ST[t] if d <= D1]
    for i, (d, s) in enumerate(ev):
        e = ev[i + 1][0] if i + 1 < len(ev) else D1
        a, b = max(d, D0), min(e, D1)
        if b <= D0 or a >= b: continue
        if out and out[-1]['s'] == s: out[-1]['w'] = round(X(b) - out[-1]['x'], 1); continue
        out.append({'s': s, 'x': round(X(a), 1), 'w': round(X(b) - X(a), 1), 'c': COL[s]})
    return out
# composite: per quarter boundaries using calendar quarter + 30d, revenue weights
comp = []
qs = pd.period_range('2021Q4', '2026Q3', freq='Q')
for i, q in enumerate(qs):
    a = q.end_time + pd.Timedelta(days=30); b = (qs[i + 1].end_time + pd.Timedelta(days=30)) if i + 1 < len(qs) else D1
    a, b = max(a.normalize(), D0), min(b.normalize(), D1)
    if a >= b: continue
    w = {}
    for t in ['MU', 'SNDK', 'WDC', 'STX']:
        cur = [x for x in ST[t] if x[0] <= a + pd.Timedelta(days=20)]
        if not cur: continue
        d, s, _ = cur[-1]
        rv = [x for x in ST[t] if x[0] <= a + pd.Timedelta(days=20)][-1][2]
        w[s] = w.get(s, 0) + 1
    tot = sum(w.values()); y = 212; parts = []
    for s in ['붕괴', '균열', '견고', '확산', '발화']:
        if s in w:
            h = 40 * w[s] / tot; parts.append({'c': COL[s], 'y': round(y, 1), 'h': round(h, 1), 's': s}); y += h
    top = max(w, key=w.get)
    comp.append({'x': round(X(a), 1), 'w': round(X(b) - X(a), 1), 'parts': parts, 'top': top, 'q': str(q)})
# prices
px = pd.concat([pd.read_parquet(f'r2dl/px_{y}.parquet', columns=['date', 'ticker', 'adj_close']) for y in range(2022, 2027)])
px = px[px.ticker.isin(TK)]; px['date'] = pd.to_datetime(px.date)
P = px.pivot_table(index='date', columns='ticker', values='adj_close').astype(float)
ret = P.pct_change(); bask = (1 + ret.mean(axis=1, skipna=True).fillna(0)).cumprod(); bask = bask / bask.iloc[0] * 100
series = {'ALL': bask}
for t in TK: s = P[t].dropna(); series[t] = s / s.iloc[0] * 100
def pth(s):
    w = s.resample('W-FRI').last().dropna(); w = w.iloc[::2]._append(s.iloc[[-1]]) if hasattr(w, '_append') else pd.concat([w.iloc[::2], s.iloc[[-1]]])
    lo, hi = w.min() * 0.85, w.max() * 1.1
    Y = lambda v: 14 + (np.log(hi) - np.log(v)) / (np.log(hi) - np.log(lo)) * 186
    d = 'M' + ' '.join(f'{X(i):.0f} {Y(v):.0f}' for i, v in w.items())
    ticks = []
    for g in [25, 50, 100, 200, 400, 800, 1600, 3200]:
        if lo < g < hi: ticks.append({'y': round(Y(g)), 'l': f'{g:,}'})
    return {'d': d, 'ticks': ticks, 'end': {'x': round(X(w.index[-1])), 'y': round(Y(w.iloc[-1])), 'v': f'{w.iloc[-1]:,.0f}'}, 'start': s.index[0].strftime('%Y-%m')}
out = {'segs': {t: segs(t) for t in TK}, 'comp': comp, 'price': {k: pth(v) for k, v in series.items()}}
# current snapshot per company
for t in TK:
    s = stage(feats(t)); r = s.dropna(subset=['rev']).iloc[-1]
    print(t, r.stage, f'{r.gm:.0%} {r.rev_g:+.0%} {r.inv_g:+.0%}', out['price'][t]['start'], out['price'][t]['end'])
print('composite last', comp[-1]['top'], [p['s'] for p in comp[-1]['parts']], [round(p['h']/40*100) for p in comp[-1]['parts']])
print('ALL end', out['price']['ALL']['end'])
for c in comp: print(c['q'], c['top'], {p['s']: round(p['h']/40*100) for p in c['parts']})
json.dump(out, open('narr/chart.json', 'w'), ensure_ascii=False, separators=(',', ':'))
import os; print(os.path.getsize('narr/chart.json'))
