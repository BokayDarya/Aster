"""Собирает итоговый комплект без личного ключа, данных сессии и чужого образца."""
from datetime import datetime, timezone
from pathlib import Path
import argparse
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'output/Бокая_ДВ_Курсовой.zip'
ROOT_FILES = [
    'README.md', 'ROADMAP.md', 'AGENTS.md', 'Dockerfile', 'compose.yaml',
    '.dockerignore', '.env.example', 'Start-Demo.ps1', 'Start-Docker.ps1',
    'прыоговос.docx', 'прыоговос.pdf', 'Бокая_ПЗ.docx', 'Бокая_ПЗ.pdf',
    'Бокая_Диаграмма_А1.pdf',
]
TOOL_FILES = [
    'run_tests.py', 'aprobation.py', 'verify_docker.py', 'show_tests.py',
    'make_diagrams.py', 'package_project.py',
]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--with-guide', action='store_true', help='Отдельный комплект с руководством; исходный ZIP не заменяется')
    args = parser.parse_args()
    dest = ROOT / 'output/Бокая_ДВ_Курсовой_с_руководством.zip' if args.with_guide else DEST
    files = [ROOT / name for name in ROOT_FILES]
    files += [ROOT / 'tools' / name for name in TOOL_FILES]
    if args.with_guide:
        files += [ROOT / name for name in ['ASTER.sln', 'ASTER_Подробное_руководство.docx',
                                          'ASTER_Подробное_руководство.pdf']]
        files += [ROOT / 'tools' / name for name in ['build_guide.py', 'Export-Guide.ps1',
                                                    'check_guide_backup.py', 'check_guide_profile.py']]
    for directory in ['src/AsterRisk', 'tests', 'examples', 'docs', 'output/ASTER']:
        for path in sorted((ROOT / directory).rglob('*')):
            rel = path.relative_to(ROOT)
            if not path.is_file() or any(p in ['bin', 'obj', '__pycache__', 'reference', 'user-edits'] for p in rel.parts):
                continue
            if rel.as_posix() in ['docs/qa/word-first-export.pdf', 'docs/images/ui-mobile.jpg', 'docs/qa/package-checks.json']:
                continue
            if 'before-origin-fix' in rel.parts or rel.as_posix() in ['docs/guide/qa/first-export.pdf', 'docs/guide/qa/package-checks.json']:
                continue
            files.append(path)
    files = sorted(set(files))
    assert all(p.is_file() for p in files), 'Не хватает обязательного файла'
    assert (ROOT / 'output/ASTER/AsterRisk.dll') in files
    assert not any(p.name == '.env' for p in files)
    manifest = [{'path': p.relative_to(ROOT).as_posix(), 'bytes': p.stat().st_size,
                 'sha256': digest(p.read_bytes())} for p in files]
    dest.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(dest, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            archive.write(path, path.relative_to(ROOT).as_posix())
        archive.writestr('СОСТАВ_КОМПЛЕКТА.json', json.dumps(manifest, ensure_ascii=False, indent=2))
    with zipfile.ZipFile(dest) as archive:
        assert archive.testzip() is None, 'Нарушена целостность ZIP'
        for item in manifest:
            data = archive.read(item['path'])
            assert len(data) == item['bytes'] and digest(data) == item['sha256'], item['path']
        assert '.env' not in archive.namelist()
        assert not any('/bin/' in n or '/obj/' in n or '/reference/' in n for n in archive.namelist())
    report = {'date': datetime.now(timezone.utc).isoformat(), 'archive': dest.relative_to(ROOT).as_posix(),
              'files': len(manifest) + 1, 'bytes': dest.stat().st_size, 'sha256': digest(dest.read_bytes()),
              'crcPassed': True, 'allFileHashesMatch': True, 'privateEnvExcluded': True,
              'runtimeDataExcluded': True, 'otherStudentReferenceExcluded': True}
    report_path = ROOT / ('docs/guide/qa/package-checks.json' if args.with_guide else 'docs/qa/package-checks.json')
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
