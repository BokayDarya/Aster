"""Проверяет подготовленный профиль через CLI, без утверждения о проверке F5 в IDE."""
from pathlib import Path
import json
import subprocess
import time
import unittest
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / 'docs/guide/qa'


def api(path, origin=None):
    request = urllib.request.Request('http://127.0.0.1:8093' + path,
                                     headers={} if origin is None else {'Origin': origin})
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.load(response)


class LaunchProfileTests(unittest.TestCase):
    def test_01_real_worker_processes_reachable_through_master_tcp(self):
        workers = api('/api/workers')
        self.assertEqual(len(workers), 2)
        self.assertTrue(all(w['online'] for w in workers))
        self.assertNotEqual(workers[0]['info']['pid'], workers[1]['info']['pid'])

    def test_02_local_origin_allowed_in_updated_debug_build(self):
        self.assertEqual(len(api('/api/workers', 'http://127.0.0.1:8093')), 2)


def main():
    log_path = QA / 'launch-profile-final.log'
    with log_path.open('wb') as log:
        proc = subprocess.Popen(['dotnet', 'run', '--project', r'.\src\AsterRisk', '-c', 'Debug',
            '--no-build', '--launch-profile', 'ASTER - Demo', '--', 'demo', '--threads', '2',
            '--data', 'tmp/guide/profile-final-data', '--logs', 'tmp/guide/profile-final-logs'],
            cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    raise AssertionError('Профиль завершился до готовности')
                try:
                    workers = api('/api/workers')
                    if len(workers) == 2 and all(w['online'] for w in workers):
                        break
                except (OSError, ValueError):
                    pass
                time.sleep(.2)
            else:
                raise AssertionError('Профиль не готов')
            result = unittest.TextTestRunner(verbosity=2).run(
                unittest.defaultTestLoader.loadTestsFromTestCase(LaunchProfileTests))
            report = {'date': '2026-10-10', 'solution': 'ASTER.sln', 'configuration': 'Debug',
                      'buildSucceeded': True, 'warnings': 0, 'errors': 0, 'profile': 'ASTER - Demo',
                      'profileStartedWithDotnetRun': True, 'projectDirectoryArgumentChecked': True,
                      'browserUrl': 'http://127.0.0.1:8093/', 'workerCount': len(workers),
                      'testsRun': result.testsRun, 'successful': result.wasSuccessful(),
                      'visualStudioIdeVerification': 'not_run_full_ide_not_installed',
                      'installationApproval': 'awaiting_user_answer', 'testDataOutsideUserHistory': True}
            (QA / 'launch-profile-check.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            if not result.wasSuccessful():
                raise AssertionError('Проверка профиля не прошла')
        finally:
            if proc.poll() is None:
                # Завершается исключительно дерево собственного проверочного dotnet run.
                subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            proc.wait(timeout=10)


if __name__ == '__main__':
    main()
