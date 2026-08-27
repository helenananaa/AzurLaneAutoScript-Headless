from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "wsl" / "build-redroid-images.sh"


def test_kvm_repository_redroid_entrypoint_is_fail_closed():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "Redroid builds are disabled in the KVM control repository" in text
    assert "v2 dual-domain Redroid entrypoint" in text
    assert "exit 2" in text
    assert "repo sync" not in text
    assert "source build/envsetup.sh" not in text
    assert " m " not in text
    assert ".alas-redroid" not in text
