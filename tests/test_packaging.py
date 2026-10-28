import zipfile

from scripts.package_plugin import PLUGIN_FILES, build_archive, plugin_version


def test_archive_contains_runtime_parser_catalog_and_bilingual_docs(tmp_path):
    archive = build_archive(str(tmp_path), legacy_copy=False)
    assert archive.name == f"PeruSpatial_Hub_QGIS_v{plugin_version()}.zip"
    with zipfile.ZipFile(archive) as bundle:
        assert bundle.testzip() is None
        assert set(bundle.namelist()) == {f"peruspatial_hub/{path}" for path in PLUGIN_FILES}
        for path in ("peruspatial_hub_ogc.py", "peruspatial_hub_connections.py", "README.es.md", "docs/AUDIT_20261028.md"):
            assert bundle.read(f"peruspatial_hub/{path}")
