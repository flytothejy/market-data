import sys, json, re, numpy as np, pandas as pd
sys.path.insert(0, 'narr'); from roles import narrative, company, feats
A0, A1 = pd.Timestamp('2015-04-01'), pd.Timestamp('2026-11-30')
X = lambda d: (pd.Timestamp(d) - A0).days / (A1 - A0).days * 1000
NM = {'MSFT':'마이크로소프트','GOOGL':'알파벳','AMZN':'아마존','META':'메타','ORCL':'오라클','NVDA':'엔비디아','AMD':'AMD','AVGO':'브로드컴','MU':'마이크론','SNDK':'샌디스크','SNDKOLD':'샌디스크(옛)','WDC':'웨스턴디지털','STX':'씨게이트','LRCX':'램리서치','AMAT':'어플라이드','KLAC':'KLA','TER':'테라다인','LLY':'일라이릴리','WST':'웨스트파마','TMO':'써모피셔','GIS':'제너럴밀스','KHC':'크래프트하인즈','MDLZ':'몬델리즈','HSY':'허쉬','CAG':'코나그라','CPB':'캠벨','SJM':'스머커','PEP':'펩시코','KO':'코카콜라','KDP':'큐리그닥터페퍼','RMD':'레즈메드','DXCM':'덱스콤','PODD':'인슐렛','TSLA':'테슬라','RIVN':'리비안','LCID':'루시드','ALB':'앨버말','MP':'MP머티리얼즈','ON':'온세미','APTV':'앱티브','BWA':'보그워너','CHPT':'차지포인트','EVGO':'EVgo','BLNK':'블링크'}
px = pd.concat([pd.read_parquet(f'r2dl/px_{y}.parquet', columns=['date','ticker','adj_close']) for y in range(2015, 2027)])
px['date'] = pd.to_datetime(px.date); P = px.pivot_table(index='date', columns='ticker', values='adj_close').astype(float)
P = P[P.index >= A0]
def runs(s):
    out = []
    for q, v in s.items():
        if not isinstance(v, str): continue
        a, b = X(max(q.end_time.normalize(), A0)), X(min((q + 1).end_time.normalize(), A1))
        if b <= 0: continue
        a = max(a, 0)
        if out and out[-1]['s'] == v and abs(out[-1]['x'] + out[-1]['w'] - a) < 0.5: out[-1]['w'] = round(b - out[-1]['x'], 2)
        else: out.append({'s': v, 'x': round(a, 2), 'w': round(b - a, 2)})
    return out
def basket(tks):
    tks = [t for t in tks if t in P]
    r = P[tks].pct_change().mean(axis=1, skipna=True).fillna(0)
    s = (1 + r).cumprod(); return s / s.iloc[0] * 100
def pth(s, H=170):
    s = s.dropna(); w = s.resample('W-FRI').last().dropna()
    w = pd.concat([w, s.iloc[[-1]]]); w = w[~w.index.duplicated(keep='last')]
    w = w / w.iloc[0] * 100
    lo, hi = w.min() * 0.85, w.max() * 1.12
    Y = lambda v: 8 + (np.log(hi) - np.log(v)) / (np.log(hi) - np.log(lo)) * (H - 16)
    d = 'M' + ' '.join(f'{X(i):.0f} {Y(v):.0f}' for i, v in w.items())
    ticks = [{'y': round(Y(g), 1), 'l': f'{g:,}'} for g in [12.5, 25, 50, 100, 200, 400, 800, 1600, 3200, 6400] if lo < g < hi]
    return {'d': d, 'ticks': (ticks[::2] if len(ticks) > 6 else ticks), 'end': {'x': round(X(w.index[-1]), 1), 'y': round(Y(w.iloc[-1]), 1), 'v': f'{w.iloc[-1]:,.0f}'}, 'base': w.index[0].strftime('%Y년 %-m월')}
def qlabel(q): return f'{q.year}년 {q.quarter}분기'
def since(s):
    s = s.dropna(); 
    if s.empty: return None, None
    cur = s.iloc[-1]; i = len(s) - 1
    while i > 0 and s.iloc[i - 1] == cur: i -= 1
    return cur, s.index[i]
def fmt(v, k='pct'):
    if pd.isna(v): return '—'
    return f'{v:+.0%}' if k == 'pct' else (f'{v:.0%}' if k == 'lvl' else f'{v:.2f}배')
def company_snap(t, role, comp):
    s = comp[t]; cur, sq = since(s['stage'])
    r = s.dropna(subset=['rev']).iloc[-1] if s.rev.notna().any() else None
    why = s[s.why != ''].why
    line = (f'{qlabel(why.index[-1])} {s.stage.loc[why.index[-1]]}: {why.iloc[-1]}' if len(why) else '')
    if role == 'producer': st = [('매출총이익률', fmt(r.gm, 'lvl')), ('매출 1년', fmt(r.rev_g)), ('재고 1년', fmt(r.inv_g))]
    elif role == 'seller': st = [('매출 1년', fmt(r.rev_g)), ('재고 1년', fmt(r.inv_g)), ('매출총이익률', fmt(r.gm, 'lvl'))]
    elif role == 'spender': st = [('설비투자 1년 (4분기 합)', fmt(r.cap_g)), ('설비투자 ÷ 영업현금흐름', fmt(r.cap_r, 'x')), ('매출 1년', fmt(r.rev_g))]
    else:
        g = s.rev_g.dropna(); st = [('매출 1년', fmt(r.rev_g)), ('최근 6분기 중 감소', f'{(g.iloc[-6:] < 0).sum()}분기'), ('매출총이익률 1년', f'{r.gm_y*100:+.1f}%p' if pd.notna(r.gm_y) else '—')]
    return {'name': NM.get(t, t), 'stage': cur, 'since': f'{qlabel(sq)}~' if sq is not None else '', 'line': line, 'stats': [{'k': k, 'v': v} for k, v in st], 'asof': qlabel(r.name) if r is not None else ''}
ROLE_KO = {'producer': '생산자형', 'seller': '매출형', 'spender': '지출형', 'victim': '피해형'}
def build(name, story):
    spec, LS, comp = narrative(f'narr/narratives/{name}.yaml', start='2014Q1')
    out = {'title': spec['title'], 'question': spec['question'], 'rows': [], 'price': {}, 'band': {}, 'snap': {}, 'story': story}
    core = [L for L in spec['layers'] if L['id'] == spec['core']][0]
    out['price']['ALL'] = pth(basket([t for t in core['members'] if t != 'SNDKOLD']))
    out['band']['ALL'] = runs(LS['narrative'])
    cur, sq = since(LS['narrative'])
    for L in spec['layers']:
        lid = L['id']; mem = [t for t in L['members'] if t != 'SNDKOLD']
        out['price'][lid] = pth(basket(mem)); out['band'][lid] = runs(LS[lid])
        lc, lq = since(LS[lid])
        latest = {t: (comp[t]['stage'].dropna().iloc[-1] if comp[t]['stage'].notna().any() else None) for t in mem}
        cnt = pd.Series([v for v in latest.values() if v]).value_counts()
        out['snap'][lid] = {'name': L['name'], 'stage': lc, 'since': f'{qlabel(lq)}~' if lq is not None else '', 'line': f"{ROLE_KO[L['role']]} 기준 · " + ' · '.join(f'{k} {v}곳' for k, v in cnt.items()), 'stats': [{'k': NM[t], 'v': latest[t] or '—'} for t in mem], 'asof': ''}
        out['rows'].append({'id': lid, 'name': L['name'], 'role': ROLE_KO[L['role']], 'core': lid == spec['core'], 'members': mem})
        for t in mem:
            if t == 'SNDK' and 'SNDKOLD' in L['members']:
                s = pd.concat([comp['SNDKOLD']['stage'].loc[:'2016Q1'], comp['SNDK']['stage'].loc['2016Q2':]])
                comp['SNDK'] = comp['SNDK'].copy(); comp['SNDK']['stage'] = s
            out['band'][t] = runs(comp[t]['stage'])
            if t in P: out['price'][t] = pth(P[t])
            out['snap'][t] = company_snap(t, L['role'], comp)
    gate = ''
    if spec.get('gate'): gate = ' · 원인 층(일라이릴리)이 견고 이상일 때만 성립'
    lay_now = ' · '.join(f"{L['name'].split(' (')[0].replace('피해 예상 — ','')} {out['snap'][L['id']]['stage'] or '—'}" for L in spec['layers'])
    out['snap']['ALL'] = {'name': '종합 (핵심 층: ' + core['name'] + ')', 'stage': cur, 'since': f'{qlabel(sq)}~' if sq is not None else '', 'line': lay_now + gate, 'stats': [], 'asof': ''}
    out['nameOf'] = {**{t: NM.get(t, t) for t in NM}, **{L['id']: L['name'] for L in spec['layers']}, 'ALL': '종합'}
    out['years'] = [{'x': round(X(f'{y}-01-01'), 1), 'l': str(y)} for y in range(2016, 2027, 2)]
    out['live'] = round(X('2026-11-09'), 1)
    return out, LS
mem, LSm = build('memory', '')
glp, LSg = build('glp1', '')
json.dump(mem, open('narr/memory_data.json', 'w'), ensure_ascii=False, separators=(',', ':'))
json.dump(glp, open('narr/glp1_data.json', 'w'), ensure_ascii=False, separators=(',', ':'))
import os
print(os.path.getsize('narr/memory_data.json'), os.path.getsize('narr/glp1_data.json'))
for o in (mem, glp):
    print(o['snap']['ALL'])
    for r in o['rows']: print(' ', r['id'], o['snap'][r['id']]['stage'], o['snap'][r['id']]['line'])
    for t in ['MU', 'SNDK', 'GIS', 'LLY', 'MSFT', 'RMD']:
        if t in o['snap']: print('   ', t, o['snap'][t])
