from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WSL = ROOT / "scripts" / "wsl"


def test_kvm_angle_scripts_have_backend_owned_defaults():
    names = (
        "bootstrap-angle.sh",
        "apply-angle-patches.sh",
        "apply-angle-g3-patches.sh",
        "build-angle-null.sh",
        "build-angle-null-observer.sh",
        "build-gles-contract.sh",
    )
    for name in names:
        text = (WSL / name).read_text(encoding="utf-8")
        assert "${HOME}/src/alas-headless-angle-kvm" in text
        assert "${HOME}/src/alas-headless-angle}/" not in text

    for name in ("bootstrap-angle.sh", "build-angle-null.sh", "build-angle-null-observer.sh"):
        text = (WSL / name).read_text(encoding="utf-8")
        assert "${HOME}/src/depot_tools-kvm" in text
        assert "${HOME}/src/depot_tools}" not in text

    for name in ("build-angle-null.sh", "build-angle-null-observer.sh"):
        text = (WSL / name).read_text(encoding="utf-8")
        assert 'default_out_dir="out-kvm/' in text
        assert 'default_out_dir="out/' not in text
