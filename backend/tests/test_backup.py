import os

from myopencode.config.schema import BackupConfig
from myopencode.core.backup import BackupManager


def test_backup_undo_modify(tmp_path):
    target = os.path.join(str(tmp_path), "f.txt")
    with open(target, "w") as fh:
        fh.write("old")

    bm = BackupManager(BackupConfig(enabled=True), base_dir=str(tmp_path / "bak"))
    bm.set_session("s1")
    bm.begin_group()
    bm.before_write(target, True)
    with open(target, "w") as fh:
        fh.write("new")
    bm.end_group()

    bm.set_session("s1")
    restored = bm.undo_last()
    assert restored == [os.path.realpath(target)]
    with open(target) as fh:
        assert fh.read() == "old"


def test_backup_undo_create(tmp_path):
    target = os.path.join(str(tmp_path), "created.txt")
    bm = BackupManager(BackupConfig(enabled=True), base_dir=str(tmp_path / "bak"))
    bm.set_session("s1")
    bm.begin_group()
    bm.before_write(target, False)
    with open(target, "w") as fh:
        fh.write("x")
    bm.end_group()

    bm.set_session("s1")
    restored = bm.undo_last()
    assert restored == [os.path.realpath(target)]
    assert not os.path.exists(target)


def test_backup_disabled_noop(tmp_path):
    target = os.path.join(str(tmp_path), "f.txt")
    bm = BackupManager(BackupConfig(enabled=False), base_dir=str(tmp_path / "bak"))
    bm.set_session("s1")
    bm.begin_group()
    assert bm.before_write(target, False) is None
    bm.end_group()
    assert bm.undo_last() == []
