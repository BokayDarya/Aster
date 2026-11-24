"""Реальные HTTP/TCP проверки четырёх контейнеров Compose. Том не удаляется."""
from pathlib import Path
from datetime import datetime,timezone
import json
import os
import subprocess
import time
import uuid
import urllib.request
import urllib.error

ROOT=Path(__file__).resolve().parents[1]
BASE='http://127.0.0.1:'+os.environ.get('ASTER_WEB_PORT','8094')


def compose(*args):
    """Службы берут тот же ключ из .env; постоянный том не удаляется."""
    return subprocess.check_output(['docker','compose',*args],cwd=ROOT,text=True,encoding='utf-8')


def api(path,data=None):
    """Шлюз создаёт действительный TCP-вызов управляющего процесса."""
    body=None if data is None else json.dumps(data).encode()
    req=urllib.request.Request(BASE+path,data=body,headers={'Content-Type':'application/json','X-Aster':'1'})
    with urllib.request.urlopen(req,timeout=30) as r:return json.load(r)


def ready():
    """Дождаться возврата обоих endpoint после запуска или рестарта."""
    for _ in range(40):
        try:
            r=api('/api/workers')
            if all(x['online'] for x in r):return r
        except (OSError,ValueError):pass
        time.sleep(.5)
    raise AssertionError('Workers not ready')


def run(paths):
    """Принять только полный результат, используя новый UUID опыта."""
    s=json.loads((ROOT/'examples/portfolio.json').read_text(encoding='utf-8'));s['paths']=paths
    j=api('/api/submit',{'simulation':s,'requestId':str(uuid.uuid4())})
    deadline=time.monotonic()+60
    while time.monotonic()<deadline:
        j=api('/api/job/'+j['id'])
        if j['status']!='running':
            assert j['status']=='completed',j;assert j['completed']==paths;return j
        time.sleep(.1)
    raise AssertionError('Job timeout')


if __name__=='__main__':
    checks=[]
    initial=ready()
    checks.append('Два вычислителя доступны по TCP из master внутри Compose.')
    full=run(100000)
    checks.append('Полный расчёт 100000 траекторий completed, проверено принятое количество.')
    with urllib.request.urlopen(BASE+'/api/export/'+full['id']+'?format=csv') as r:
        assert len(r.read().decode('utf-8').splitlines())==100001
    checks.append('CSV содержит заголовок и 100000 потерь.')
    try:
        compose('stop','worker-a')
        repeat=run(10000)
        checks.append('При остановке worker-a полный расчёт 10000 выполнен worker-b.')
    finally:
        compose('start','worker-a')
    ready()
    compose('restart','master')
    ready()
    restored=api('/api/job/'+full['id'])
    assert restored['result']['var95']==full['result']['var95']
    checks.append('После рестарта master результат восстановлен из именованного тома.')
    report={'date':datetime.now(timezone.utc).date().isoformat(),'successful':True,'engine':subprocess.check_output(['docker','info','--format','{{.ServerVersion}}'],text=True).strip(),'url':BASE,'checks':checks,'containers':compose('ps','--format','json'),'job':{k:v for k,v in full.items() if k not in ('result','simulation')},'result':{k:v for k,v in full['result'].items() if k not in ('samples','histogram')}}
    (ROOT/'docs/qa/docker-checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('containers','job','result')},ensure_ascii=False,indent=2))
