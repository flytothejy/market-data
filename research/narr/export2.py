import sys, json, numpy as np, pandas as pd
sys.path.insert(0, 'narr')
exec(open('narr/export.py').read().split('ROLE_KO =')[0].split("def company_snap")[0])
from roles import narrative3, feats, verdict
ROLE_KO = {'producer': '생산자형', 'seller': '매출형', 'spender': '지출형', 'victim': '피해형', 'defensive': '방어주형'}
DIR = {'other': '회사 기준'}
def metrics(m, role):
    r = m.dropna(subset=['rev_g']).iloc[-1] if m.rev_g.notna().any() else None
    if r is None: return [], ''
    if role == 'producer': st = [('매출총이익률', fmt(r.gm, 'lvl')), ('매출 1년', fmt(r.rev_g)), ('재고 1년', fmt(r.inv_g))]
    elif role == 'seller': st = [('매출 1년', fmt(r.rev_g)), ('재고 1년', fmt(r.inv_g)), ('매출총이익률', fmt(r.gm, 'lvl'))]
    elif role == 'spender': st = [('설비투자 1년 (4분기 합)', fmt(r.cap_g)), ('설비투자 ÷ 영업현금흐름', fmt(r.cap_r, 'x')), ('매출 1년', fmt(r.rev_g))]
    else:
        g = m.rev_g.dropna(); st = [('최근 4분기 매출 1년', f'{r.rg4:+.1%}' if pd.notna(r.rg4) else '—'), ('분기 매출 1년', f'{r.rev_g:+.1%}'), ('최근 6분기 중 감소', f'{(g.iloc[-6:] < 0).sum()}분기')]
    return [{'k': k, 'v': v} for k, v in st], qlabel(r.name)
def build(name, dirs):
    spec, C, PD, LF = narrative3(f'narr/narratives/{name}.yaml', start='2014Q1')
    out = {'rows': [], 'price': {}, 'band': {}, 'pend': {}, 'snap': {}}
    core = [L for L in spec['layers'] if L['id'] == spec['core']][0]
    out['price']['ALL'] = pth(basket([t for t in core['members'] if t != 'SNDKOLD']))
    out['band']['ALL'] = runs(C['narrative'])
    lastp = lambda k: (PD[k].iloc[-1] if isinstance(PD[k].iloc[-1], str) else None)
    out['pend']['ALL'] = lastp('narrative')
    for L in spec['layers']:
        lid = L['id']; mem = [t for t in L['members'] if t != 'SNDKOLD']
        pm = [t for t in mem if t in P and P[t].notna().sum() > 20]
        if pm: out['price'][lid] = pth(basket(pm))
        out['band'][lid] = runs(C[lid]); out['pend'][lid] = lastp(lid)
        cur, sq = since(C[lid]); stats, asof = metrics(LF[lid], L['role'])
        p = lastp(lid)
        line = f"{dirs.get(lid, DIR['other'])} · {ROLE_KO[L['role']]} 기준, 회원 {len(mem)}곳 " + ('합산' if L.get('agg') == 'sum' else '중앙값') + (f" · 최근 분기에 '{p}' 신호 (한 분기 더 이어지면 확정)" if p else '')
        out['snap'][lid] = {'name': L['name'], 'stage': cur, 'since': f'{qlabel(sq)}~ (확정)' if sq is not None else '', 'line': line, 'stats': stats, 'asof': asof}
        rowsub = dirs.get(lid, DIR['other']).split(' · ')[0] + ' · ' + ROLE_KO[L['role']]
        out['rows'].append({'id': lid, 'name': L['name'], 'role': rowsub, 'core': lid == spec['core'], 'members': mem})
        for t in mem:
            if t in P and P[t].notna().sum() > 20: out['price'][t] = pth(P[t])
            f = feats(t); st, asof = metrics(f, L['role'])
            out['snap'][t] = {'name': NM.get(t, t), 'stage': None, 'since': f'{asof} 기준' if asof else '', 'line': f"{L['name']} 층 회원 · 종목별 국면은 표시하지 않고 숫자만 보여줍니다" + ('' if (t in P and P[t].notna().sum() > 20) else ' · 티커맵 가격 미수집(재무만 반영)'), 'stats': st, 'asof': asof, 'mini': ' · '.join(f"{s['k'].split(' (')[0]} {s['v']}" for s in st[:2])}
    cur, sq = since(C['narrative'])
    p = out['pend']['ALL']
    gate = ' 원인 층이 견고 이상일 때만 성립합니다.' if spec.get('gate') else ''
    vd = verdict(spec, C); out['verdict'] = vd
    out['snap']['ALL'] = {'name': f"종합 · 주인공: {core['name']}", 'stage': cur, 'since': f'{qlabel(sq)}~ (확정)' if sq is not None else '', 'line': f"이야기 판정: {vd}. 종합 국면 = 주인공 층({core['name']}) 회사들의 국면(견고 = 좋음).{gate}" + (f" 최근 분기에 '{p}' 신호." if p else ''), 'stats': [{'k': L['name'], 'v': (out['snap'][L['id']]['stage'] or '—') + (f" → {out['pend'][L['id']]}?" if out['pend'][L['id']] else '')} for L in spec['layers']], 'asof': ''}
    out['nameOf'] = {**{t: NM.get(t, t) for t in NM}, **{L['id']: L['name'] for L in spec['layers']}, 'ALL': '종합'}
    out['live'] = round(X('2026-11-09'), 1)
    return out
mem = build('memory', {})
glp = build('glp1', {'driver': '원인 · 회사 기준', 'supply': '원인 쪽 · 회사 기준', 'food': '주인공 · 회사 기준', 'snack': '타격 예상 · 회사 기준', 'medtech': '타격 예상 · 회사 기준'})
ev = build('ev', {})
for nm, o in (('memory', mem), ('glp1', glp), ('ev', ev)):
    json.dump(o, open(f'narrmock/{nm}_data3.json', 'w'), ensure_ascii=False, separators=(',', ':'))
    print(nm, o['snap']['ALL']); print({k: v for k, v in o['pend'].items()})
    print(o['snap'][o['rows'][0]['id']])
    print(o['snap'][o['rows'][0]['members'][0]])
