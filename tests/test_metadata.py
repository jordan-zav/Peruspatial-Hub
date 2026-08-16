import configparser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def metadata():
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(ROOT / "metadata.txt", encoding="utf-8")
    return parser["general"]


def test_metadata_links_use_canonical_repository():
    general = metadata()
    assert general["repository"].rstrip("/").lower() == "https://github.com/jordan-zav/peruspatial-hub"
    assert general["tracker"].rstrip("/").lower().endswith("/peruspatial-hub/issues")


def test_documentation_uses_metadata_version():
    version = metadata()["version"]
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"Versión estable: {version}" in readme
    assert f"## {version} " in changelog
