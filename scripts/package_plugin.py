"""Build the installable PeruSpatial Hub QGIS plugin ZIP."""

from __future__ import annotations

import configparser
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_NAME = "peruspatial_hub"
PLUGIN_FILES = (
    "__init__.py",
    "peruspatial_hub.py",
    "peruspatial_hub_panel.py",
    "peruspatial_hub_urls.py",
    "peruspatial_hub_catalog.py",
    "peruspatial_hub_sources.py",
    "catalog/catalog.json",
    "catalog/README.md",
    "metadata.txt",
    "logo.png",
    "logo_dev.png",
    "logo_solo.png",
    "LICENSE",
    "README.md",
)


def plugin_version() -> str:
    metadata = configparser.ConfigParser(interpolation=None)
    metadata.read(ROOT / "metadata.txt", encoding="utf-8")
    return metadata["general"]["version"]


def build_archive() -> Path:
    output_dir = ROOT / "dist"
    output_dir.mkdir(exist_ok=True)
    archive = output_dir / f"PeruSpatial-Hub-{plugin_version()}.zip"

    with ZipFile(archive, "w", compression=ZIP_DEFLATED) as bundle:
        for relative_name in PLUGIN_FILES:
            source = ROOT / relative_name
            if not source.is_file():
                raise FileNotFoundError(source)
            bundle.write(source, Path(PLUGIN_NAME) / relative_name)

    return archive


if __name__ == "__main__":
    print(build_archive())
