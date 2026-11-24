"""Проверка команд руководства на отдельном стенде без удаления исходного тома."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import time
import unittest
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
PROJECT = 'aster-guide-restore-20261010'
BACKUP = ROOT / 'tmp/guide/docker-backup-20261010'
QA = ROOT / 'docs/guide/qa'
ENV = dict(os.environ, ASTER_WEB_PORT='8095')


def compose(*args, restore=False):
    argv = ['docker', 'compose']
    if restore:
        argv += ['-p', PROJECT]
    completed = subprocess.run(argv + list(args), cwd=ROOT, env=ENV, text=True,
                               encoding='utf-8', capture_output=True)
    if completed.returncode:
        raise RuntimeError(completed.stderr)
    return completed.stdout


def api(port, path):
    with urllib.request.urlopen(f'http://127.0.0.1:{port}{path}', timeout=10) as response:
        return json.load(response)


def wait_ready(port):
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        try:
            workers = api(port, '/api/workers')
            if len(workers) == 2 and all(w['online'] for w in workers):
                return
        except (OSError, ValueError):
            pass
        time.sleep(.25)
    raise AssertionError('Вычислители не готовы')


class DockerBackupTests(unittest.TestCase):
    def test_01_stopped_container_copy_has_history_files(self):
        self.assertTrue(list((BACKUP / 'data').glob('*.json')))

    def test_02_restored_jobs_match_original_results(self):
        restored = api(8095, '/api/history')
        self.assertEqual({j['id'] for j in self.original}, {j['id'] for j in restored})
        for expected in self.original:
            actual = api(8095, '/api/job/' + expected['id'])
            self.assertEqual(self.jobs[expected['id']], actual)


def main():
    # Повторный запуск с тем же именем требует явного нового имени, чтобы не затронуть том.
    assert not BACKUP.exists(), 'Каталог проверки уже существует'
    existing = subprocess.check_output(['docker', 'volume', 'ls', '--format', '{{.Name}}'], text=True)
    assert PROJECT + '_aster-data' not in existing.splitlines(), 'Том проверки уже существует'
    wait_ready(8094)
    original = api(8094, '/api/history')
    assert original and not any(j['status'] == 'running' for j in original)
    jobs = {j['id']: api(8094, '/api/job/' + j['id']) for j in original}
    BACKUP.mkdir(parents=True)
    compose('stop')
    try:
        compose('cp', 'master:/data', str(BACKUP / 'data'))
    finally:
        compose('start')
    wait_ready(8094)
    compose('create', '--build', restore=True)
    try:
        # Та же форма source data\. из руководства; копируются содержимое и JSON-записи.
        compose('cp', str(BACKUP / 'data') + '/.', 'master:/data', restore=True)
        compose('start', restore=True)
        wait_ready(8095)
        DockerBackupTests.original = original
        DockerBackupTests.jobs = jobs
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(DockerBackupTests))
        hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (BACKUP / 'data').glob('*.json')}
        report = {'date': '2026-10-10', 'project': PROJECT, 'testsRun': result.testsRun,
                  'successful': result.wasSuccessful(), 'jobsRestoredAndCompared': len(original),
                  'sourcePort': 8094, 'restorePort': 8095, 'backup': str(BACKUP),
                  'backupJsonHashes': hashes, 'sourceVolumeDeleted': False,
                  'copyCommandsTested': True, 'restoreProjectStoppedAfterCheck': True}
        (QA / 'docker-backup-check.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        if not result.wasSuccessful():
            raise AssertionError('Проверки резервной копии не прошли')
        print(json.dumps({k: v for k, v in report.items() if k != 'backupJsonHashes'}, ensure_ascii=False))
    finally:
        compose('stop', restore=True)


if __name__ == '__main__':
    main()
