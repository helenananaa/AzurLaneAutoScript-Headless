from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "wsl" / "build-redroid-images.sh"


def test_unified_repository_redroid_entrypoint_requires_isolated_domains():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "REDROID_BUILD_DOMAIN_JSON KVM_BUILD_DOMAIN_JSON" in text
    assert "--expected-backend redroid" in text
    assert "--expected-backend kvm" in text
    assert "require_isolated_domain_pair" in text
    assert "source build/envsetup.sh" in text
