import json, sys, numpy as np, pandas as pd
sys.path.insert(0, 'themes'); from config import THEMES
S = '.'
CON = {'rev': ['RevenueFromContractWithCustomerExcludingAssessedTax', 'Revenues', 'RevenuesNetOfInterestExpense', 'RevenueFromContractWithCustomerIncludingAssessedTax', 'SalesRevenueNet'],
       'cogs': ['CostOfGoodsAndServicesSold', 'CostOfRevenue', 'CostOfGoodsSold', 'CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization'],
       'gp': ['GrossProfit'], 'ni': ['NetIncomeLoss'], 'cfo': ['NetCashProvidedByUsedInOperatingActivities'],
       'capex': ['PaymentsToAcquirePropertyPlantAndEquipment', 'PaymentsToAcquireProductiveAssets'],
       'prov': ['ProvisionForLoanLeaseAndOtherLosses', 'FinancingReceivableExcludingAccruedInterestCreditLossExpenseReversal', 'FinancingReceivableCreditLossExpenseReversal', 'ProvisionForLoanAndLeaseLosses', 'ProvisionForLoanLossesExpensed', 'CreditLossExpense'],
       'intexp': ['InterestExpense', 'InterestExpenseNonoperating', 'InterestExpenseDebt', 'InterestExpenseOperating'],
       'nii': ['InterestIncomeExpenseNet'],
       'shares': ['WeightedAverageNumberOfDilutedSharesOutstanding'],
       'sbc': ['ShareBasedCompensation', 'AllocatedShareBasedCompensationExpense'],
       'buyback': ['PaymentsForRepurchaseOfCommonStock'],
       'nco': ['FinancingReceivableExcludingAccruedInterestAllowanceForCreditLossWriteoffAfterRecovery', 'FinancingReceivableAllowanceForCreditLossesWriteOffsNet']}
INST = {'inv': ['InventoryNet'], 'ar': ['AccountsReceivableNetCurrent'], 'rpo': ['RevenueRemainingPerformanceObligation'],
        'debt': ['LongTermDebt', 'LongTermDebtNoncurrent'], 'allow': ['FinancingReceivableAllowanceForCreditLossExcludingAccruedInterest', 'FinancingReceivableAllowanceForCreditLosses', 'AllowanceForLoanAndLeaseLosses']}
cq = lambda end: (pd.Timestamp(end) - pd.Timedelta(days=45)).to_period('Q')
rows = []
T = 'ORCL NVDA AMD AVGO MU SNDK SNDKOLD WDC STX LRCX AMAT KLAC TER MSFT GOOGL AMZN META LLY WST TMO BDX GIS KHC MDLZ HSY CAG CPB SJM PEP KO KDP RMD DXCM PODD ISRG TSLA RIVN LCID ALB MP ON APTV BWA CHPT EVGO BLNK GM F'.split()
for t in T:
    g = json.load(open(f'{S}/secdl/{t}.json'))['facts'].get('us-gaap', {})
    U = lambda tag: g.get(tag, {}).get('units', {}).get('USD', []) or g.get(tag, {}).get('units', {}).get('shares', [])
    for k, tags in CON.items():
        q = {}
        for tag in tags:
            e = pd.DataFrame([x for x in U(tag) if x.get('form') in ('10-Q', '10-K', '10-Q/A', '10-K/A') and 'start' in x])
            if e.empty: continue
            e['start'] = pd.to_datetime(e['start']); e['end'] = pd.to_datetime(e['end']); e['days'] = (e['end'] - e['start']).dt.days
            e = e.sort_values('filed').drop_duplicates(['start', 'end'], keep='last')
            for _, r in e[e['days'].between(80, 100)].iterrows(): q.setdefault(cq(r['end']), r['val'])
            for s, y in (e[e['days'] > 100] if k != 'shares' else e.iloc[0:0]).groupby('start'):
                y = y.sort_values('end'); first = e[(e['start'] == s) & e['days'].between(80, 100)]
                prev = first.iloc[0] if len(first) else None
                for _, r in y.iterrows():
                    if prev is not None and 80 <= (r['end'] - prev['end']).days <= 100: q.setdefault(cq(r['end']), r['val'] - prev['val'])
                    prev = r
        for p, v in q.items(): rows.append((t, k, p, v))
    for k, tags in INST.items():
        q = {}
        for tag in tags:
            for x in sorted([x for x in U(tag) if x.get('form') in ('10-Q', '10-K', '10-Q/A', '10-K/A')], key=lambda x: x['filed']):
                if 'start' in x: continue
                q[(tag, cq(x['end']))] = x['val']
        best = {}
        for tag in tags:
            for (tg, p), v in q.items():
                if tg == tag: best.setdefault(p, v)
        for p, v in best.items(): rows.append((t, k, p, v))
D = pd.DataFrame(rows, columns=['t', 'k', 'q', 'v'])
D = D[(D['q'] >= pd.Period('2008Q1')) & (D['q'] <= pd.Period('2026Q3'))]
W = D.pivot_table(index=['t', 'q'], columns='k', values='v', aggfunc='first').reset_index()
W['gp'] = W['gp'].fillna(W['rev'] - W['cogs'])
W.to_csv('narr/panel_long.csv', index=False)
print(W.groupby('t')['q'].agg(['min','max','count']))
