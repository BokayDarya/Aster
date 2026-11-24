"""Реальные контрольные расчёты и сравнение локальных конфигураций процессов."""
from datetime import datetime, timezone
import copy
import json
from pathlib import Path
import platform
import statistics
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from test_system import Cluster, DEFAULT, call

folder=ROOT/'docs/qa';folder.mkdir(parents=True,exist_ok=True)
c=Cluster(2)
experiments=[]
try:
    for paths,steps,stress in [(100000,12,False),(200000,252,False),(500000,12,False),(200000,12,True)]:
        s=copy.deepcopy(DEFAULT);s['paths']=paths;s['steps']=steps
        if stress:s['stress']={'name':'Падение рынка','driftShift':-.12,'volatilityMultiplier':1.7,'stockShock':-.25,'bondShock':-.08,'currencyShock':.12}
        job=c.calculate(s);experiments.append(job)
        print(paths,steps,s['stress']['name'],'VaR95',job['result']['var95'],'seconds',job['result']['elapsedSeconds'],flush=True)
finally:c.close()
timings=[]
for workers in [1,2]:
    cluster=Cluster(workers)
    try:
        s=copy.deepcopy(DEFAULT);s['paths']=200000;s['steps']=252
        runs=[cluster.calculate(s)['result'] for _ in range(3)]
        timings.append({'workers':workers,'workerThreads':list(range(1,workers+1)),
                        'runsSeconds':[r['elapsedSeconds'] for r in runs],
                        'medianSeconds':statistics.median(r['elapsedSeconds'] for r in runs),
                        'var95':runs[0]['var95'],'var99':runs[0]['var99']})
        print('benchmark',timings[-1],flush=True)
    finally:cluster.close()
data={'timestamp':datetime.now(timezone.utc).isoformat(),'platform':platform.platform(),
      'processor':platform.processor(),'physicalHosts':1,'experiments':experiments,'timings':timings,
      'note':'Локальные отдельные процессы и реальные TCP. Одно физическое устройство; разное суммарное число потоков. Это не испытание разных сетевых компьютеров.'}
(folder/'aprobation.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
