"""Настоящие unittest запускают C# узлы и обмениваются кадрами по TCP."""
import copy
import json
import math
import os
from pathlib import Path
import socket
import struct
import subprocess
import tempfile
import time
import unittest
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
DLL = ROOT / 'src/AsterRisk/bin/Release/net8.0/AsterRisk.dll'
KEY = 'aster-local-course-demo-2026'
DEFAULT = json.loads((ROOT / 'examples/portfolio.json').read_text(encoding='utf-8'))


def port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def exact(s, count):
    data = b''
    while len(data) < count:
        part = s.recv(count - len(data))
        if not part:
            raise EOFError('Кадр оборван')
        data += part
    return data


def call(p, command, data=None, key=KEY, version=1):
    request_id = uuid.uuid4().hex
    b = json.dumps(dict(version=version, key=key, id=request_id, command=command,
                        data=data if data is not None else {}), ensure_ascii=False).encode()
    with socket.create_connection(('127.0.0.1', p), timeout=10) as s:
        s.settimeout(15)
        s.sendall(struct.pack('!I', len(b)) + b)
        length = struct.unpack('!I', exact(s, 4))[0]
        result = json.loads(exact(s, length))
    assert result['id'] == request_id
    return result


class Cluster:
    def __init__(self, workers=2, directory=None):
        self.tmp = tempfile.TemporaryDirectory() if directory is None else None
        self.directory = Path(self.tmp.name) if self.tmp else Path(directory)
        self.processes = []
        self.logs = []
        self.worker_ports = [port() for _ in range(workers)]
        self.master_port = port()
        for i, p in enumerate(self.worker_ports):
            self.spawn('worker', '--listen', f'127.0.0.1:{p}', '--threads', str(i+1))
        self.spawn('master', '--listen', f'127.0.0.1:{self.master_port}', '--workers',
                   ','.join(f'127.0.0.1:{p}' for p in self.worker_ports), '--data', str(self.directory / 'data'))
        for p in [*self.worker_ports, self.master_port]:
            self.ready(p)

    def spawn(self, *args):
        self.directory.mkdir(parents=True, exist_ok=True)
        log = open(self.directory / f'{args[0]}-{len(self.processes)}.log', 'w', encoding='utf-8')
        self.logs.append(log)
        proc = subprocess.Popen(['dotnet', str(DLL), *args], cwd=ROOT, stdout=log,
                                stderr=subprocess.STDOUT, env={**os.environ, 'ASTER_KEY': KEY})
        self.processes.append(proc)
        return proc

    def ready(self, p):
        until = time.monotonic() + 8
        while time.monotonic() < until:
            try:
                if call(p, 'ping')['ok']:
                    return
            except (OSError, EOFError):
                time.sleep(.05)
        raise RuntimeError('Процесс не запустился')

    def submit(self, simulation, request_id=None):
        reply = call(self.master_port, 'submit', {'simulation': simulation,
                          'requestId': request_id or str(uuid.uuid4())})
        if not reply['ok']:
            raise RuntimeError(reply['error'])
        return reply['data']

    def wait(self, job, timeout=60):
        until = time.monotonic() + timeout
        while time.monotonic() < until:
            value = call(self.master_port, 'job', {'id': job['id']})['data']
            if value['status'] != 'running':
                return value
            time.sleep(.05)
        raise TimeoutError('Расчёт не завершился')

    def calculate(self, simulation):
        job = self.wait(self.submit(simulation))
        if job['status'] != 'completed':
            raise RuntimeError(job['error'])
        return job

    def delete(self, job):
        assert call(self.master_port, 'delete', {'id': job['id']})['ok']

    def close(self):
        for process in reversed(self.processes):
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=10)
        for log in self.logs:
            log.close()
        if self.tmp:
            self.tmp.cleanup()


class MathAndNetworkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cluster = Cluster()

    @classmethod
    def tearDownClass(cls):
        cls.cluster.close()

    def simulation(self, paths=1000):
        s = copy.deepcopy(DEFAULT)
        s['paths'] = paths
        return s

    def reject(self, s):
        r = call(self.cluster.master_port, 'submit', {'simulation': s, 'requestId': str(uuid.uuid4())})
        self.assertFalse(r['ok'], r)

    def test_01_distinct_processes_and_tcp(self):
        nodes = call(self.cluster.master_port, 'workers')['data']
        self.assertTrue(all(n['online'] for n in nodes))
        self.assertEqual(len({n['info']['pid'] for n in nodes}), 2)
        master_pid = call(self.cluster.master_port, 'ping')['data']['pid']
        self.assertNotIn(master_pid, {n['info']['pid'] for n in nodes})

    def test_02_fragmented_frame(self):
        b = json.dumps(dict(version=1,key=KEY,id='fragmented',command='ping',data={})).encode()
        with socket.create_connection(('127.0.0.1', self.cluster.master_port)) as s:
            for byte in struct.pack('!I',len(b))+b:
                s.sendall(bytes([byte]))
            size = struct.unpack('!I', exact(s,4))[0]
            self.assertTrue(json.loads(exact(s,size))['ok'])

    def test_03_wrong_key(self):
        self.assertFalse(call(self.cluster.master_port,'ping',key='wrong')['ok'])

    def test_04_wrong_version(self):
        self.assertFalse(call(self.cluster.master_port,'ping',version=2)['ok'])

    def test_05_duplicate_json(self):
        b = ('{"version":1,"version":1,"key":"'+KEY+'","id":"d","command":"ping","data":{}}').encode()
        with socket.create_connection(('127.0.0.1',self.cluster.master_port)) as s:
            s.sendall(struct.pack('!I',len(b))+b)
            # Отмена ReadExactlyAsync может закрыть NetworkStream до отправки ошибки.
            # Допустимы явная ошибка либо разрыв; успешный ответ недопустим.
            try:
                size=struct.unpack('!I',exact(s,4))[0]
                self.assertFalse(json.loads(exact(s,size))['ok'])
            except (EOFError, ConnectionResetError):
                pass

    def test_06_oversize_frame(self):
        with socket.create_connection(('127.0.0.1',self.cluster.master_port)) as s:
            s.sendall(struct.pack('!I',4*1024*1024+1))
            size=struct.unpack('!I',exact(s,4))[0]
            self.assertFalse(json.loads(exact(s,size))['ok'])

    def test_07_truncated_frame_timeout(self):
        start=time.monotonic()
        with socket.create_connection(('127.0.0.1',self.cluster.master_port)) as s:
            s.settimeout(8);s.sendall(struct.pack('!I',100)+b'{')
            try:
                size=struct.unpack('!I',exact(s,4))[0]
                self.assertFalse(json.loads(exact(s,size))['ok'])
            except (EOFError, ConnectionResetError):
                pass
        self.assertLess(time.monotonic()-start,7)

    def test_08_invalid_price(self):
        s=self.simulation();s['assets'][0]['price']=-1;self.reject(s)

    def test_09_duplicate_names(self):
        s=self.simulation();s['assets'][1]['name']=s['assets'][0]['name'];self.reject(s)

    def test_10_asymmetric_correlation(self):
        s=self.simulation();s['correlation'][0][1]=.8;self.reject(s)

    def test_11_non_psd_correlation(self):
        s=self.simulation();s['correlation']=[[1,.9,.9],[.9,1,-.9],[.9,-.9,1]];self.reject(s)

    def test_12_semidefinite_correlation(self):
        s=self.simulation();s['correlation']=[[1,1,1],[1,1,1],[1,1,1]]
        job=self.cluster.calculate(s);self.assertEqual(job['completed'],1000);self.cluster.delete(job)

    def test_13_resource_limits(self):
        for field,value in [('paths',500001),('steps',365),('confidence',.9)]:
            with self.subTest(field=field):
                s=self.simulation();s[field]=value;self.reject(s)

    def test_14_zero_volatility_analytic(self):
        s=self.simulation();s['assets']=[dict(name='Детерминированный',kind='stock',price=100,quantity=10,drift=.08,volatility=0)];s['correlation']=[[1]]
        job=self.cluster.calculate(s);expected=1000*(1-math.exp(.08))
        self.assertAlmostEqual(job['result']['var95'],expected,places=9)
        self.assertAlmostEqual(job['result']['meanLoss'],expected,places=9);self.cluster.delete(job)

    def test_15_initial_shock_is_loss(self):
        s=self.simulation();s['assets']=[dict(name='Акция',kind='stock',price=100,quantity=10,drift=0,volatility=0)];s['correlation']=[[1]];s['stress']['stockShock']=-.25
        job=self.cluster.calculate(s);self.assertAlmostEqual(job['result']['var95'],250,places=9)
        self.assertEqual(job['result']['lossProbability'],1);self.cluster.delete(job)

    def test_16_quantile_and_histogram(self):
        job=self.cluster.calculate(self.simulation(12000));r=job['result']
        losses=[]
        for offset in range(0,job['total'],5000):losses.extend(call(self.cluster.master_port,'losses',{'id':job['id'],'offset':offset})['data']['values'])
        self.assertEqual(len(losses),12000);self.assertEqual(losses,sorted(losses))
        self.assertEqual(r['var95'],losses[math.ceil(.95*len(losses))-1]);self.assertEqual(r['var99'],losses[math.ceil(.99*len(losses))-1])
        self.assertEqual(sum(b['count'] for b in r['histogram']),12000)
        self.assertEqual(sum(w['paths'] for w in r['workers']),12000)
        self.assertTrue(all(w['paths']>0 for w in r['workers']));self.cluster.delete(job)

    def test_17_repeat_request_is_idempotent(self):
        s=self.simulation();key=str(uuid.uuid4());a=self.cluster.submit(s,key);b=self.cluster.submit(s,key)
        self.assertEqual(a['id'],b['id']);self.cluster.wait(a);self.cluster.delete(a)

    def test_18_repeat_request_conflict(self):
        s=self.simulation();key=str(uuid.uuid4());job=self.cluster.submit(s,key);s['seed']+=1
        self.assertFalse(call(self.cluster.master_port,'submit',{'simulation':s,'requestId':key})['ok']);self.cluster.wait(job);self.cluster.delete(job)

    def test_19_seed_reproducibility(self):
        s=self.simulation(11000);a=self.cluster.calculate(s);b=self.cluster.calculate(s)
        for k in ['var95','var99','meanLoss','histogram','samples']:self.assertEqual(a['result'][k],b['result'][k])
        self.cluster.delete(a);self.cluster.delete(b)

    def test_20_single_asset_distribution(self):
        s=self.simulation(100000);s['assets']=[dict(name='Акция',kind='stock',price=100,quantity=10,drift=.07,volatility=.2)];s['correlation']=[[1]]
        job=self.cluster.calculate(s);expected=1000*(1-math.exp(.07));var=1000*(1-math.exp(.07-.5*.2**2-.2*1.644853626951))
        self.assertAlmostEqual(job['result']['meanLoss'],expected,delta=3)
        self.assertAlmostEqual(job['result']['var95'],var,delta=4);self.cluster.delete(job)

    def test_21_missing_id(self):
        self.assertFalse(call(self.cluster.master_port,'job',{})['ok'])


class FailureAndPersistenceTests(unittest.TestCase):
    def test_22_worker_failure_reassigned(self):
        c=Cluster()
        try:
            c.processes[0].terminate();c.processes[0].wait()
            s=copy.deepcopy(DEFAULT);s['paths']=15000;job=c.calculate(s)
            self.assertEqual(job['completed'],15000);self.assertEqual(job['result']['workers'][1]['paths'],15000)
            self.assertGreater(job['result']['workers'][0]['failures'],0)
        finally:c.close()

    def test_23_all_workers_failure_not_success(self):
        c=Cluster()
        try:
            for p in c.processes[:2]:p.terminate();p.wait()
            s=copy.deepcopy(DEFAULT);s['paths']=1000;job=c.wait(c.submit(s))
            self.assertEqual(job['status'],'failed');self.assertIsNone(job['result'])
        finally:c.close()

    def test_24_restart_preserves_complete_result(self):
        c=Cluster()
        try:
            s=copy.deepcopy(DEFAULT);s['paths']=1000;job=c.calculate(s)
            c.processes[-1].terminate();c.processes[-1].wait()
            c.spawn('master','--listen',f'127.0.0.1:{c.master_port}','--workers',','.join(f'127.0.0.1:{p}' for p in c.worker_ports),'--data',str(c.directory/'data'));c.ready(c.master_port)
            loaded=call(c.master_port,'job',{'id':job['id']})['data'];self.assertEqual(loaded,job)
        finally:c.close()

    def test_25_corrupt_storage_fails_closed(self):
        c=Cluster()
        try:
            s=copy.deepcopy(DEFAULT);s['paths']=1000;job=c.calculate(s)
            c.processes[-1].terminate();c.processes[-1].wait();path=c.directory/'data'/f"{job['id']}.json"
            value=json.loads(path.read_text());value['content']['job']['completed']=0;path.write_text(json.dumps(value),encoding='utf-8')
            p=c.spawn('master','--listen',f'127.0.0.1:{c.master_port}','--workers',f'127.0.0.1:{c.worker_ports[0]}','--data',str(c.directory/'data'))
            self.assertNotEqual(p.wait(timeout=5),0)
        finally:c.close()

    def test_26_exclusive_storage_lock(self):
        c=Cluster()
        try:
            p=c.spawn('master','--listen',f'127.0.0.1:{port()}','--workers',f'127.0.0.1:{c.worker_ports[0]}','--data',str(c.directory/'data'))
            self.assertNotEqual(p.wait(timeout=5),0)
        finally:c.close()

    def test_27_cancel_no_partial_result(self):
        c=Cluster()
        try:
            s=copy.deepcopy(DEFAULT);s['paths']=500000;s['steps']=252;job=c.submit(s)
            self.assertTrue(call(c.master_port,'cancel',{'id':job['id']})['ok']);job=c.wait(job)
            self.assertEqual(job['status'],'cancelled');self.assertIsNone(job['result'])
        finally:c.close()

    def test_28_restart_marks_incomplete(self):
        c=Cluster()
        try:
            s=copy.deepcopy(DEFAULT);s['paths']=500000;s['steps']=252;job=c.submit(s)
            c.processes[-1].terminate();c.processes[-1].wait()
            c.spawn('master','--listen',f'127.0.0.1:{c.master_port}','--workers',','.join(f'127.0.0.1:{p}' for p in c.worker_ports),'--data',str(c.directory/'data'));c.ready(c.master_port)
            loaded=call(c.master_port,'job',{'id':job['id']})['data'];self.assertEqual(loaded['status'],'interrupted');self.assertIsNone(loaded['result'])
        finally:c.close()

    def test_29_topology_does_not_change_results(self):
        a=Cluster(1);b=Cluster(2)
        try:
            s=copy.deepcopy(DEFAULT);s['paths']=11000;x=a.calculate(s)['result'];y=b.calculate(s)['result']
            for k in ['var95','var99','meanLoss','samples','histogram']:self.assertEqual(x[k],y[k])
        finally:a.close();b.close()

    def test_30_http_gateway_and_exports(self):
        c=Cluster();p=port()
        try:
            c.spawn('web','--url',f'http://127.0.0.1:{p}/','--master',f'127.0.0.1:{c.master_port}')
            url=f'http://127.0.0.1:{p}'
            for _ in range(50):
                try:
                    with urllib.request.urlopen(url,timeout=1) as r:self.assertIn(b'ASTER',r.read())
                    break
                except OSError:time.sleep(.05)
            s=copy.deepcopy(DEFAULT);s['paths']=1000
            req=urllib.request.Request(url+'/api/submit',data=json.dumps({'simulation':s,'requestId':str(uuid.uuid4())}).encode(),headers={'Content-Type':'application/json','X-Aster':'1'})
            with urllib.request.urlopen(req) as r:job=json.load(r)
            job=c.wait(job)
            with urllib.request.urlopen(url+'/api/export/'+job['id']+'?format=csv') as r:
                rows=r.read().decode('utf-8-sig').splitlines();self.assertEqual(len(rows),1001)
            with urllib.request.urlopen(url+'/api/export/'+job['id']) as r:self.assertEqual(json.load(r)['result'],job['result'])
            req=urllib.request.Request(url+'/api/delete',data=json.dumps({'id':job['id']}).encode(),headers={'Content-Type':'application/json','X-Aster':'1','Origin':'http://foreign.example'})
            with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen(req)
            self.assertEqual(e.exception.code,400)
        finally:c.close()


if __name__ == '__main__':
    unittest.main(verbosity=2)
