"""역할별 국면 규칙. 회사 분기 패널 -> 분기별 국면. 모든 판단은 그 분기와 이전 값만 쓴다."""
import pandas as pd, numpy as np, yaml
from collections import Counter
W = pd.read_csv('narr/panel_long.csv'); W['q'] = pd.PeriodIndex(W.q, freq='Q')
ORDER = ['발화', '확산', '견고', '균열', '붕괴']

def feats(t):
    m = W[W.t == t].set_index('q').sort_index()
    m = m.reindex(pd.period_range(m.index.min(), m.index.max(), freq='Q'))
    gp = m.gp.where(m.gp.notna(), m.rev - m.cogs)
    m['gm'] = gp / m.rev
    m['rev_g'] = m.rev / m.rev.shift(4) - 1
    m['inv_g'] = m.inv / m.inv.shift(4) - 1
    m['gm_d'] = m.gm - m.gm.shift(1); m['gm_y'] = m.gm - m.gm.shift(4)
    r4 = m.rev.rolling(4).sum(); m['rg4'] = r4 / r4.shift(4) - 1
    cap4 = m.capex.rolling(4).sum(); cfo4 = m.cfo.rolling(4).sum()
    m['cap_g'] = cap4 / cap4.shift(4) - 1; m['cap_r'] = cap4 / cfo4
    return m

def run(m, step):
    st, out, why = None, [], []
    rows = list(m.iterrows())
    for i, (q, r) in enumerate(rows):
        hist = m.iloc[max(0, i - 7):i + 1]
        new, w = step(st, r, hist)
        out.append(new); why.append(w if new != st else ''); st = new
    m = m.copy(); m['stage'] = out; m['why'] = why; return m

def producer(st, r, h):
    if pd.isna(r.rev_g) or pd.isna(r.gm): return st, ''
    p = h.iloc[-2] if len(h) > 1 else r
    crack = []
    if r.gm_d < 0 and p.gm_d < 0: crack.append('이익률 2분기 연속 하락')
    if pd.notna(r.inv_g) and pd.notna(p.inv_g) and r.inv_g - p.inv_g >= 0.15 and r.inv_g > 0.10: crack.append('재고 증가율 급등')
    if pd.notna(r.inv_g) and r.inv_g > r.rev_g and r.rev_g > -0.10: crack.append('재고가 매출보다 빨리 증가')
    solid = r.gm >= 0.40 and r.rev_g >= 0.30 and (pd.isna(r.inv_g) or r.inv_g < r.rev_g / 2)
    if r.rev_g < -0.10 and pd.notna(r.gm_y) and r.gm_y < -0.10: return '붕괴', f'매출 {r.rev_g:+.0%}, 이익률 {r.gm_y*100:+.0f}%p'
    if st in ('견고', '균열') and crack: return '균열', ', '.join(crack)
    if st in ('붕괴', None) and r.gm_d > 0 and p.gm_d > 0: return '발화', '이익률 2분기 연속 개선'
    if st in ('발화', '확산', '균열', None) and solid: return '견고', f'이익률 {r.gm:.0%}, 매출 {r.rev_g:+.0%}'
    if st in ('발화', None) and r.rev_g >= 0.15: return '확산', f'매출 {r.rev_g:+.0%}'
    return st, ''

def seller(st, r, h):
    g = r.rev_g
    if pd.isna(g): return st, ''
    p = h.iloc[-2] if len(h) > 1 else r
    gmax = h.rev_g.iloc[-5:].max()
    if g < -0.10: return '붕괴', f'매출 {g:+.0%}'
    crack = []
    if st == '견고' and gmax - g >= 0.15 and g < 0.15: crack.append(f'매출 증가율 둔화 ({gmax:+.0%} → {g:+.0%})')
    if st == '견고' and pd.notna(r.inv_g) and r.inv_g - g >= 0.20: crack.append('재고가 매출보다 20%p 이상 빨리 증가')
    if crack: return '균열', ', '.join(crack)
    if st in ('붕괴', None) and pd.notna(p.rev_g) and g > p.rev_g and pd.notna(h.rev_g.iloc[-3] if len(h) > 2 else np.nan) and p.rev_g > h.rev_g.iloc[-3]: return '발화', '매출 증가율 2분기 연속 개선'
    if st in ('발화', '확산', '균열', None) and g >= 0.20 and (pd.isna(r.inv_g) or r.inv_g - g < 0.20): return '견고', f'매출 {g:+.0%}'
    if st in ('발화', None) and g >= 0.05: return '확산', f'매출 {g:+.0%}'
    return st, ''

def spender(st, r, h):
    g, cr = r.cap_g, r.cap_r
    if pd.isna(g): return st, ''
    if g < -0.10: return '붕괴', f'설비투자 {g:+.0%}'
    gp = h.cap_g.iloc[-3] if len(h) > 2 else np.nan
    if st == '견고' and pd.notna(cr) and cr >= 1.0: return '균열', f'설비투자가 영업현금흐름의 {cr:.2f}배'
    if st == '견고' and pd.notna(gp) and gp - g >= 0.20 and g < 0.15: return '균열', f'설비투자 증가율 둔화 ({gp:+.0%} → {g:+.0%})'
    if st in ('붕괴', None) and pd.notna(gp) and g > h.cap_g.iloc[-2] > gp: return '발화', '설비투자 증가율 2분기 연속 개선'
    if st in ('발화', '확산', '균열', None) and g >= 0.25 and (pd.isna(cr) or cr < 1.0): return '견고', f'설비투자 {g:+.0%}, 현금흐름의 {cr:.2f}배'
    if st in ('발화', None) and g >= 0.10: return '확산', f'설비투자 {g:+.0%}'
    return st, ''

def victim(st, r, h):
    g = r.rev_g
    if pd.isna(g): return st, ''
    gs = h.rev_g.dropna()
    neg = (gs.iloc[-6:] < 0).sum(); last2 = gs.iloc[-2:]; last4 = gs.iloc[-4:]
    if len(last4) == 4 and (last4 >= 0.03).all() and st != '붕괴': return '붕괴', '매출 4분기 연속 +3% 이상 (피해 부정)'
    if st == '견고' and len(last2) == 2 and (last2 > 0).all(): return '균열', '매출 2분기 연속 플러스'
    if st in ('확산', '균열') and neg >= 4 and g < 0: return '견고', f'최근 6분기 중 {neg}분기 매출 감소'
    if st == '발화' and len(last2) == 2 and (last2 < 0).all(): return '확산', '매출 2분기 연속 감소'
    if st in (None, '붕괴') and g < 0: return '발화', f'매출 감소 시작 ({g:+.0%})'
    return st, ''

def defensive(st, r, h):
    """방어주형: 최근 4분기 합 매출의 1년 증가율(rg4)로 판정. 견고 = 회사에 좋음."""
    g = r.rg4
    if pd.isna(g): return st, ''
    gs = h.rg4.dropna()
    if g <= -0.04 or (g <= -0.02 and pd.notna(r.gm_y) and r.gm_y < 0): return '붕괴', f'최근 4분기 매출 {g:+.1%}'
    if st in ('견고', '확산') and g < 0: return '균열', f'최근 4분기 매출 {g:+.1%}'
    if st in ('붕괴', None) and len(gs) >= 3 and gs.iloc[-1] - gs.iloc[-2] >= 0.005 and gs.iloc[-2] - gs.iloc[-3] >= 0.005: return '발화', '매출 증가율 2분기 연속 개선'
    if st in ('발화', '확산', '균열', None) and g >= 0.02: return '견고', f'최근 4분기 매출 {g:+.1%}'
    if st in ('발화', '균열', None) and g >= 0: return '확산', f'최근 4분기 매출 {g:+.1%}'
    return st, ''

ROLE = {'producer': producer, 'seller': seller, 'spender': spender, 'victim': victim, 'defensive': defensive}
POS = {'발화': '시작 단계', '확산': '번지는 중', '견고': '맞아 가는 중', '균열': '흔들리는 중', '붕괴': '끝나 가는 중'}
NEG = {'붕괴': '맞아 가는 중', '균열': '맞기 시작', '발화': '약해지는 중', '확산': '틀려 가는 중', '견고': '틀려 가는 중'}
def verdict(spec, C, q=-1):
    core = C[spec['core']].iloc[q]
    if spec.get('gate') and C[spec['gate']].iloc[q] not in ('견고', '균열'): return '성립 전'
    if not isinstance(core, str): return '판정 없음'
    past = C[spec['core']].iloc[max(0, len(C) + q - 12 if q < 0 else q - 12):(len(C) + q if q < 0 else q)].tolist()
    if core == '발화' and '붕괴' in past: return '되살아나는 중' if spec.get('polarity') != 'negative' else '다시 약해지는 중'
    return (NEG if spec.get('polarity') == 'negative' else POS)[core]

def company(t, role):
    return run(feats(t), ROLE[role])

def layer_stage(stages):
    s = [x for x in stages if isinstance(x, str)]
    if not s: return None
    c = Counter(s); top = max(c.values())
    tied = [k for k in ORDER if c.get(k) == top]
    return tied[-1]  # 동률이면 더 진행된(나쁜) 쪽

def narrative(spec_path, start='2009Q1', end='2026Q3'):
    spec = yaml.safe_load(open(spec_path))
    qs = pd.period_range(start, end, freq='Q')
    comp, lay = {}, {}
    for L in spec['layers']:
        cols = {}
        for t in L['members']:
            s = company(t, L['role'])
            cols[t] = s['stage'].reindex(qs)
            comp[t] = s.reindex(qs)
        df = pd.DataFrame(cols)
        lay[L['id']] = df.apply(lambda row: layer_stage(row.tolist()), axis=1)
        lay[L['id'] + '__n'] = df.notna().sum(axis=1)
    LS = pd.DataFrame(lay)
    nar = LS[spec['core']].copy()
    if spec.get('gate'):
        ok = LS[spec['gate']].isin(['견고', '균열'])
        nar = nar.where(ok, None)
    LS['narrative'] = nar
    return spec, LS, comp

# ---- 층 단위 판정: 회사 국면 다수결 대신, 회원 지표의 중앙값 시계열에 역할 규칙을 그대로 적용 ----
MET = ['rev_g', 'rg4', 'gm', 'inv_g', 'gm_d', 'gm_y', 'cap_g', 'cap_r']
def layer_feats(members, qs):
    fr = {t: feats(t).reindex(qs) for t in members}
    m = pd.DataFrame(index=qs)
    for k in MET:
        m[k] = pd.concat([f[k].rename(t) for t, f in fr.items()], axis=1).median(axis=1, skipna=True)
    m['rev'] = 1.0; m['n'] = pd.concat([f['rev_g'].notna().rename(t) for t, f in fr.items()], axis=1).sum(axis=1)
    m.loc[m.n == 0, MET] = np.nan
    return m
def narrative2(spec_path, start='2009Q1', end='2026Q3'):
    spec = yaml.safe_load(open(spec_path))
    qs = pd.period_range(start, end, freq='Q')
    LS, LF = {}, {}
    for L in spec['layers']:
        f = layer_feats(L['members'], qs, L.get('agg', 'median'))
        s = run(f, ROLE[L['role']]); LS[L['id']] = s['stage']; LF[L['id']] = s
    LS = pd.DataFrame(LS)
    nar = LS[spec['core']].copy()
    if spec.get('gate'): nar = nar.where(LS[spec['gate']].isin(['견고', '균열']), None)
    LS['narrative'] = nar
    return spec, LS, LF

def confirm(s):
    """새 국면은 2분기 연속일 때 확정. 첫 분기는 신호(pending)로만 남긴다."""
    out, pend, cur = [], [], None
    vals = list(s.values)
    for i, v in enumerate(vals):
        v = v if isinstance(v, str) else None
        prev = vals[i - 1] if i > 0 and isinstance(vals[i - 1], str) else None
        if cur is None and v is not None and prev == v: cur = v
        elif v is not None and v != cur and prev == v: cur = v
        out.append(cur); pend.append(v if (v is not None and v != cur) else None)
    return pd.Series(out, index=s.index), pd.Series(pend, index=s.index)
def narrative3(spec_path, start='2009Q1', end='2026Q3'):
    spec, LS, LF = narrative2(spec_path, start, end)
    C, PD = {}, {}
    for L in spec['layers']:
        C[L['id']], PD[L['id']] = confirm(LS[L['id']])
    C = pd.DataFrame(C); PD = pd.DataFrame(PD)
    nar = C[spec['core']].copy(); npd = PD[spec['core']].copy()
    C['narrative'] = nar; PD['narrative'] = npd
    return spec, C, PD, LF

def layer_feats_sum(members, qs):
    """합산 방식: 4분기 전에도 숫자가 있는 회원만 모아 매출·매출총이익·재고를 더한 뒤 비율을 구한다(초기 기업의 폭증률이 중앙값을 왜곡할 때)."""
    fr = {t: feats(t).reindex(qs) for t in members}
    m = pd.DataFrame(index=qs)
    def g(col, i, lag):
        num = den = 0.0; ok = False
        for f in fr.values():
            a, b = f[col].iloc[i], f[col].iloc[i - lag] if i - lag >= 0 else np.nan
            if pd.notna(a) and pd.notna(b): num += a; den += b; ok = True
        return num / den - 1 if ok and den else np.nan
    for c in ['rev', 'inv']: [f.__setitem__(c, f[c]) for f in fr.values()]
    for f in fr.values(): f['gp2'] = f.gm * f.rev; f['r4'] = f.rev.rolling(4).sum()
    rows = []
    for i in range(len(qs)):
        rv = sum(f.rev.iloc[i] for f in fr.values() if pd.notna(f.rev.iloc[i]) and pd.notna(f.gm.iloc[i]))
        gp = sum(f.gp2.iloc[i] for f in fr.values() if pd.notna(f.rev.iloc[i]) and pd.notna(f.gm.iloc[i]))
        rows.append({'rev_g': g('rev', i, 4), 'inv_g': g('inv', i, 4), 'rg4': g('r4', i, 4), 'gm': gp / rv if rv else np.nan,
                     'n': sum(pd.notna(f.rev.iloc[i]) for f in fr.values())})
    m = pd.DataFrame(rows, index=qs)
    m['gm_d'] = m.gm - m.gm.shift(1); m['gm_y'] = m.gm - m.gm.shift(4); m['cap_g'] = np.nan; m['cap_r'] = np.nan; m['rev'] = 1.0
    return m
_lf_median = layer_feats
def layer_feats(members, qs, agg='median'):
    return layer_feats_sum(members, qs) if agg == 'sum' else _lf_median(members, qs)
