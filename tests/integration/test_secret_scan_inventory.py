import shutil
import sys
from pathlib import Path

from test_loop_git import git

from loop_engine.process import ProcessRunner


def test_source_scan_covers_new_and_force_tracked_ignored_files(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    (tmp_path / "scripts").mkdir()
    shutil.copy2(root / "scripts/secret_scan.py", tmp_path / "scripts/secret_scan.py")
    git(tmp_path, "init", "-b", "main")
    (tmp_path / ".gitignore").write_text("private/\n")
    (tmp_path / "private").mkdir()
    leak = 'key = "' + "AKIA" + "0123456789ABCDEF" + '"\n'
    (tmp_path / "new.py").write_text(leak)
    (tmp_path / "private/forced.py").write_text(leak)
    git(tmp_path, "add", "--force", "private/forced.py")
    result = ProcessRunner().run([sys.executable, "scripts/secret_scan.py"], tmp_path, timeout=30)
    assert result.returncode == 1
    assert "new.py" in result.stdout
    assert "forced.py" in result.stdout
    assert "AKIA" not in result.stdout
