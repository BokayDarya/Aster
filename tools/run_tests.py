"""Запускает unittest и сохраняет журнал и машинные результаты без подмены тестов."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))


class Recorded(unittest.TextTestResult):
    def startTest(self, test):
        self.start = time.perf_counter()
        super().startTest(test)
    def record(self, test, status, detail=''):
        self.records.append({'id': test.id(), 'status': status,
                             'seconds': time.perf_counter()-self.start, 'detail': detail})
    def addSuccess(self,test):
        super().addSuccess(test);self.record(test,'passed')
    def addFailure(self,test,err):
        super().addFailure(test,err);self.record(test,'failed',self._exc_info_to_string(err,test))
    def addError(self,test,err):
        super().addError(test,err);self.record(test,'error',self._exc_info_to_string(err,test))
    def __init__(self,*a,**kw):
        super().__init__(*a,**kw);self.records=[]


class Tee:
    def __init__(self,log):self.log=log
    def write(self,s):sys.stderr.write(s);self.log.write(s);self.log.flush()
    def flush(self):sys.stderr.flush();self.log.flush()


if __name__=='__main__':
    folder=ROOT/'docs/qa';folder.mkdir(parents=True,exist_ok=True)
    start=time.perf_counter()
    with (folder/'unittest.log').open('w',encoding='utf-8') as log:
        result=unittest.TextTestRunner(stream=Tee(log),verbosity=2,resultclass=Recorded).run(
            unittest.defaultTestLoader.discover(str(ROOT/'tests'),pattern='test_*.py'))
    (folder/'test-results.json').write_text(json.dumps({'timestamp':datetime.now(timezone.utc).isoformat(),
        'runtime':sys.version,'testsRun':result.testsRun,'successful':result.wasSuccessful(),
        'elapsedSeconds':time.perf_counter()-start,'tests':result.records},ensure_ascii=False,indent=2),encoding='utf-8')
    sys.exit(0 if result.wasSuccessful() else 1)
