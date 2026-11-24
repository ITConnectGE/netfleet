"""Path-traversal guard for backup downloads and deletes."""

import pytest

from app.core.paths import safe_child


def test_plain_names_resolve_inside_base(tmp_path):
    for name in ("20261124-120000.backup", "netfleet-system-acme-v0.59.5-20261124-120000.tar.gz"):
        assert safe_child(tmp_path, name) == (tmp_path / name).resolve()


@pytest.mark.parametrize(
    "name",
    [
        "..",
        ".",
        "",
        ".hidden",
        "../x",
        "../system-old/x.tar.gz",  # sibling sharing the base's prefix
        "a/b",
        "a\b",
        "/etc/passwd",
        "C:x",
        "x\x00y",
        "a" * 300,
    ],
)
def test_traversal_and_odd_names_rejected(tmp_path, name):
    with pytest.raises(ValueError):
        safe_child(tmp_path / "system", name)


def test_symlink_out_of_base_rejected(tmp_path):
    base = tmp_path / "system"
    base.mkdir()
    (tmp_path / "secret.txt").write_text("x")
    try:
        (base / "link.tar.gz").symlink_to(tmp_path / "secret.txt")
    except OSError:
        pytest.skip("symlinks not permitted on this host")
    with pytest.raises(ValueError):
        safe_child(base, "link.tar.gz")
