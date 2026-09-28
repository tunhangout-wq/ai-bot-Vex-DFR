import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_gitignore_excludes_runtime_data_and_temporary_files():
    ignore_file = ROOT / ".gitignore"
    assert ignore_file.is_file()
    patterns = set(ignore_file.read_text(encoding="utf-8").splitlines())
    assert {
        "bot/data/*.json",
        "*.bak",
        "*.corrupt",
        "*.tmp",
        "*.sqlite3",
    } <= patterns


def test_staff_example_contains_no_activation_codes():
    staff = json.loads((ROOT / "bot/data/staff.json").read_text(encoding="utf-8"))
    assert staff.get("codes") == {}
    assert not any("CB-" in str(code) for code in staff.get("codes", {}))
