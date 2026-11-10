import sys, json, re, numpy as np, pandas as pd, yaml
sys.path.insert(0, 'narr')
src = open('narr/export2.py').read().split('mem = build(')[0]
exec(src)
from roles import narrative3, feats, verdict
SPY = P['SPY']
def pth2(s, H=170):
    s = s.dropna(); w = s.resample('W-FRI').last().dropna(); w = pd.concat([w, s.iloc[[-1]]]); w = w[~w.index.duplicated(keep='last')]
    w = w / w.iloc[0] * 100
    sp = SPY.reindex(w.index, method='ffill'); sp = sp / sp.iloc[0] * 100
    lo, hi = min(w.min(), sp.min()) * 0.85, max(w.max(), sp.max()) * 1.12
    Y = lambda v: 8 + (np.log(hi) - np.log(v)) / (np.log(hi) - np.log(lo)) * (H - 16)
    d = lambda ser: 'M' + ' '.join(f'{X(i):.0f} {Y(v):.0f}' for i, v in ser.items())
    ticks = [{'y': round(Y(g), 1), 'l': f'{g:,}'} for g in [12.5, 25, 50, 100, 200, 400, 800, 1600, 3200, 6400] if lo < g < hi]
    return {'d': d(w), 'spy': d(sp), 'ticks': (ticks[::2] if len(ticks) > 6 else ticks), 'end': {'x': round(X(w.index[-1]), 1), 'y': round(Y(w.iloc[-1]), 1), 'v': f'{w.iloc[-1]:,.0f}'}, 'spyEnd': f'{sp.iloc[-1]:,.0f}', 'Y': (lo, hi), 'w': w}
def rich(name, dirs):
    out = build(name, dirs)
    spec, C, PD, LF = narrative3(f'narr/narratives/{name}.yaml', start='2014Q1')
    core = [L for L in spec['layers'] if L['id'] == spec['core']][0]
    cm = [t for t in core['members'] if t != 'SNDKOLD' and t in P]
    # prices with SPY
    keys = list(out['price'].keys())
    for k in keys:
        if k == 'ALL': ser = basket(cm)
        elif k in [L['id'] for L in spec['layers']]:
            L = [L for L in spec['layers'] if L['id'] == k][0]; ser = basket([t for t in L['members'] if t in P and P[t].notna().sum() > 20])
        else: ser = P[k]
        p = pth2(ser); out['price'][k] = {kk: v for kk, v in p.items() if kk not in ('Y', 'w')}
        if k == 'ALL': wall = p['w']
    # tooltips per quarter
    lf = LF[spec['core']]
    tips = []
    for q in pd.period_range('2015Q2', '2026Q3', freq='Q'):
        a, b = X(max(q.end_time.normalize(), A0)), X(min((q + 1).end_time.normalize(), A1))
        st = C['narrative'].get(q); r = lf.loc[q] if q in lf.index else None
        pv = wall[wall.index <= q.end_time].iloc[-1] if (wall.index <= q.end_time).any() else np.nan
        why = r.why if r is not None and isinstance(r.why, str) and r.why else ''
        m = []
        if r is not None:
            if pd.notna(r.gm): m.append(f'이익률 {r.gm:.0%}')
            if pd.notna(r.rev_g): m.append(f'매출 {r.rev_g:+.0%}')
            if pd.notna(r.inv_g): m.append(f'재고 {r.inv_g:+.0%}')
        tips.append({'x0': round(a, 1), 'x1': round(b, 1), 'q': qlabel(q) + ' 실적', 'st': st if isinstance(st, str) else '—', 'm': ' · '.join(m), 'why': why, 'p': f'{pv:,.0f}' if pd.notna(pv) else '—', 'pend': PD['narrative'].get(q) if isinstance(PD['narrative'].get(q), str) else ''})
    out['tips'] = tips
    # events: confirmed stage changes on ALL band
    ev = []
    for s in out['band']['ALL'][1:]: ev.append({'x': s['x'], 'l': s['s']})
    out['events'] = ev
    # metric mini charts for core layer (median/sum)
    s15 = lf.loc['2015Q1':]
    xs = lambda q: (X(q.end_time.normalize()) + X((q + 1).end_time.normalize())) / 2
    def line(series, lo, hi, H=120):
        pts = [(xs(q), v) for q, v in series.items() if pd.notna(v)]
        Yv = lambda v: 6 + (hi - min(max(v, lo), hi)) / (hi - lo) * (H - 12)
        return 'M' + ' '.join(f'{x:.0f} {Yv(v):.0f}' for x, v in pts), Yv
    gmd, Yg = line(s15.gm, -0.4, 1.0)
    rg, Yr = line(s15.rev_g, -0.6, 2.0); ig, _ = line(s15.inv_g, -0.6, 2.0)
    out['mini'] = {'gm': {'d': gmd, 'th': round(Yg(0.40), 1), 'zero': round(Yg(0), 1), 'last': f'{s15.gm.dropna().iloc[-1]:.0%}', 'ticks': [{'y': round(Yg(v), 1), 'l': f'{v:.0%}'} for v in (0, 0.4, 0.8)]},
                   'ri': {'rev': rg, 'inv': ig, 'zero': round(Yr(0), 1), 'lastR': f'{s15.rev_g.dropna().iloc[-1]:+.0%}', 'lastI': f'{s15.inv_g.dropna().iloc[-1]:+.0%}', 'ticks': [{'y': round(Yr(v), 1), 'l': f'{v:+.0%}'} for v in (0, 1.0, 2.0)]}}
    # analogs: past entries into the current core stage
    cs = C['narrative'].dropna(); cur = cs.iloc[-1]
    entries = [q for i, q in enumerate(cs.index) if i > 0 and cs.iloc[i] == cur and cs.iloc[i - 1] != cur and q < cs.index[-1] - 1]
    an = []
    for q in entries:
        after = cs.loc[q:]; nxt = after[after != cur]
        if len(nxt):
            n_q = nxt.index[0]; dur = (n_q - q).n
            an.append({'start': qlabel(q), 'next': nxt.iloc[0], 'after': f'{dur}분기 뒤', 'path': ' → '.join([cur] + [v for i, v in enumerate(after.loc[n_q:].tolist()[:8]) if i == 0 or v != after.loc[n_q:].tolist()[i - 1]][:3])})
    out['analog'] = {'cur': cur, 'list': an}
    # table
    tb = []
    for L in spec['layers']:
        for t in [t for t in L['members'] if t != 'SNDKOLD']:
            f = feats(t); r = f.dropna(subset=['rev_g']).iloc[-1]
            pr = P[t].dropna() if t in P else None
            y1 = (pr.iloc[-1] / pr[pr.index <= pr.index[-1] - pd.Timedelta(days=365)].iloc[-1] - 1) if pr is not None and len(pr) > 260 else np.nan
            tb.append({'layer': L['name'], 't': t, 'n': NM.get(t, t), 'rev': fmt(r.rev_g), 'gm': fmt(r.gm, 'lvl'), 'inv': fmt(r.inv_g), 'y1': fmt(y1), 'up': bool(pd.notna(y1) and y1 >= 0), 'q': qlabel(r.name)})
    out['table'] = tb
    # talk snapshot
    T = pd.read_parquet('r2dl/tenk_newsents.parquet'); kw = re.compile(spec['keywords'], re.I)
    tk = []
    for L in spec['layers']:
        mem = [t for t in L['members'] if t != 'SNDKOLD']
        hit = sum(T[(T.ticker == t)].sentence.str.contains(kw).any() for t in mem)
        tk.append({'layer': L['name'], 'hit': int(hit), 'n': len(mem), 'pct': round(100 * hit / len(mem))})
    out['talk'] = tk
    out['verdict'] = verdict(spec, C)
    return out
o = rich('memory', {})
json.dump(o, open('narrmock/memory_rich.json', 'w'), ensure_ascii=False, separators=(',', ':'))
print(len(json.dumps(o)), o['analog'], o['talk'], o['mini']['gm']['last'], o['mini']['ri']['lastR'], o['mini']['ri']['lastI'])
print(o['tips'][-3:]); print(o['events'][-4:]); print(o['table'][:3])
