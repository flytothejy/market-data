import pandas as pd, numpy as np
W = pd.read_csv('narr/panel_long.csv'); W['q'] = pd.PeriodIndex(W.q, freq='Q')
def feats(t):
    m = W[W.t == t].set_index('q').sort_index()
    m = m.reindex(pd.period_range(m.index.min(), m.index.max(), freq='Q'))
    gp = m.gp.where(m.gp.notna(), m.rev - m.cogs)
    m['gm'] = gp / m.rev
    m['rev_g'] = m.rev / m.rev.shift(4) - 1; m['inv_g'] = m.inv / m.inv.shift(4) - 1
    m['gm_d'] = m.gm - m.gm.shift(1); m['gm_y'] = m.gm - m.gm.shift(4)
    return m
def stage(m):
    st, out, why = None, [], []
    for q, r in m.iterrows():
        if pd.isna(r.rev_g) or pd.isna(r.gm): out.append(st); why.append(''); continue
        prev = m.shift(1).loc[q]
        crack = []
        if r.gm_d < 0 and prev.gm_d < 0: crack.append('이익률 2분기 연속 하락')
        if pd.notna(r.inv_g) and pd.notna(prev.inv_g) and r.inv_g - prev.inv_g >= 0.15 and r.inv_g > 0.10: crack.append('재고 증가율 급등')
        if pd.notna(r.inv_g) and r.inv_g > r.rev_g and r.rev_g > -0.10: crack.append('재고 > 매출 증가')
        solid = r.gm >= 0.40 and r.rev_g >= 0.30 and (pd.isna(r.inv_g) or r.inv_g < r.rev_g / 2)
        new, w = st, ''
        if r.rev_g < -0.10 and pd.notna(r.gm_y) and r.gm_y < -0.10: new, w = '붕괴', f'매출 {r.rev_g:+.0%}, 이익률 {r.gm_y*100:+.0f}%p'
        elif st in ('견고', '균열') and crack: new, w = '균열', ', '.join(crack)
        elif st in ('붕괴', None) and r.gm_d > 0 and prev.gm_d > 0: new, w = '발화', '이익률 2분기 연속 개선'
        elif st in ('발화', '확산', '균열', None) and solid: new, w = '견고', f'이익률 {r.gm:.0%}, 매출 {r.rev_g:+.0%}'
        elif st in ('발화', None) and r.rev_g >= 0.15: new, w = '확산', f'매출 {r.rev_g:+.0%}'
        out.append(new); why.append(w if new != st else ''); st = new
    m = m.copy(); m['stage'] = out; m['why'] = why; return m
if __name__ == '__main__':
    for t in ['MU', 'SNDKOLD', 'WDC', 'STX', 'LRCX', 'AMAT', 'KLAC']:
        s = stage(feats(t)); ch = s[s.why != '']
        print('\n==', t); print('\n'.join(f'{q} {r.stage:3} | {r.why} | gm {r.gm:.0%} rev {r.rev_g:+.0%} inv {r.inv_g:+.0%}' for q, r in ch.iterrows()))
