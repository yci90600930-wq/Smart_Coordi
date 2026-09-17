"""Create a consistent, portable ZIP backup of the application and its data."""
from datetime import datetime
from pathlib import Path
import shutil
import sqlite3
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parent
DATA=ROOT/'data'

SKIP_NAMES={
    '__pycache__','.pytest_cache','server.log','server-error.log','server.pid',
    'mobile-access.txt','coordinator.sqlite3','coordinator.sqlite3-wal','coordinator.sqlite3-shm'
}

def _ignore(_directory,names):
    return [name for name in names if name in SKIP_NAMES or name.endswith(('.pyc','.pyo'))]

def create_backup(root=ROOT,data_dir=DATA,destination=None):
    root=Path(root).resolve();data_dir=Path(data_dir).resolve()
    destination=Path(destination or (Path.home()/'Documents'/'SmartManufacturingBackups')).resolve()
    if not root.is_dir():raise FileNotFoundError('프로그램 폴더를 찾을 수 없습니다.')
    database=data_dir/'coordinator.sqlite3'
    if not database.is_file():raise FileNotFoundError('데이터베이스를 찾을 수 없습니다.')
    destination.mkdir(parents=True,exist_ok=True)
    stamp=datetime.now().strftime('%Y%m%d-%H%M%S')
    archive_base=destination/f'coordinator-mvp-backup-{stamp}'
    archive=archive_base.with_suffix('.zip')
    suffix=1
    while archive.exists():
        archive_base=destination/f'coordinator-mvp-backup-{stamp}-{suffix}'
        archive=archive_base.with_suffix('.zip');suffix+=1
    with tempfile.TemporaryDirectory(prefix='coordinator-backup-') as temporary:
        temporary=Path(temporary);stage=temporary/'coordinator-mvp'
        shutil.copytree(root,stage,ignore=_ignore)
        staged_data=stage/'data';staged_data.mkdir(parents=True,exist_ok=True)
        source=sqlite3.connect(f'file:{database.as_posix()}?mode=ro',uri=True)
        target=sqlite3.connect(staged_data/'coordinator.sqlite3')
        try:source.backup(target)
        finally:target.close();source.close()
        shutil.make_archive(str(archive_base),'zip',root_dir=temporary,base_dir='coordinator-mvp')
    with zipfile.ZipFile(archive) as package:
        bad=package.testzip()
        if bad:raise RuntimeError('백업 ZIP 검증 실패: '+bad)
        required={'coordinator-mvp/app.py','coordinator-mvp/data/coordinator.sqlite3'}
        if not required.issubset(package.namelist()):raise RuntimeError('백업 필수파일이 누락되었습니다.')
    return archive

if __name__=='__main__':
    result=create_backup()
    print('백업 완료')
    print(result)

