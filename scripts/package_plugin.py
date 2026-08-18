"""Build and package the installable PeruSpatial Hub QGIS plugin ZIP for official release."""

from __future__ import annotations

import argparse
import configparser
import datetime
import re
import sys
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

MANDATORY_METADATA_KEYS = (
    "name",
    "qgisMinimumVersion",
    "description",
    "about",
    "version",
    "author",
    "email",
    "repository",
    "tracker",
    "homepage",
    "category",
    "icon",
    "tags",
    "experimental",
    "deprecated",
    "changelog",
)

# Keys in the exact order and casing used by the QGIS plugin validator.
METADATA_KEY_ORDER = (
    "name",
    "qgisMinimumVersion",
    "description",
    "about",
    "version",
    "author",
    "email",
    "repository",
    "tracker",
    "homepage",
    "category",
    "icon",
    "tags",
    "experimental",
    "deprecated",
    "changelog",
)


def load_metadata() -> configparser.ConfigParser:
    metadata = configparser.ConfigParser(interpolation=None)
    metadata.read(ROOT / "metadata.txt", encoding="utf-8")
    return metadata


def save_metadata(metadata: configparser.ConfigParser) -> None:
    """Write metadata.txt preserving QGIS-required format: key=value, camelCase, no spaces."""
    path = ROOT / "metadata.txt"
    general = metadata["general"]

    # Collect all keys preserving original casing and order.  Start with the
    # canonical order and append any extras that were added at runtime.
    written = set()
    lines = ["[general]\n"]
    for key in METADATA_KEY_ORDER:
        # ConfigParser lowercases keys internally, so look up with .lower().
        value = general.get(key.lower(), "").strip()
        if value or key.lower() in general:
            lines.append(f"{key}={value}\n")
            written.add(key.lower())
    # Append any non-standard keys that might have been added.
    for key in general:
        if key not in written:
            lines.append(f"{key}={general[key]}\n")

    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.writelines(lines)


def plugin_version() -> str:
    metadata = load_metadata()
    return metadata["general"]["version"]


def update_documentation_version(new_version: str, changelog_entry: str = "") -> None:
    readme_path = ROOT / "README.md"
    if readme_path.is_file():
        content = readme_path.read_text(encoding="utf-8")
        updated_content = re.sub(
            r"Versión estable:\s*[0-9A-Za-z.\-_]+",
            f"Versión estable: {new_version}",
            content,
        )
        readme_path.write_text(updated_content, encoding="utf-8")

    changelog_path = ROOT / "CHANGELOG.md"
    if changelog_path.is_file() and changelog_entry:
        today = datetime.date.today().isoformat()
        entry_header = f"## {new_version} - {today}"
        cl_content = changelog_path.read_text(encoding="utf-8")
        if f"## {new_version}" not in cl_content:
            new_block = f"{entry_header}\n\n- {changelog_entry.strip()}\n\n"
            if cl_content.startswith("# Changelog"):
                rest = cl_content[len("# Changelog"):].lstrip("\r\n")
                cl_content = f"# Changelog\n\n{new_block}{rest}"
            else:
                cl_content = f"# Changelog\n\n{new_block}{cl_content}"
            changelog_path.write_text(cl_content, encoding="utf-8")


def interactive_metadata_update() -> None:
    metadata = load_metadata()
    general = metadata["general"]
    current_ver = general.get("version", "1.0.0")

    print("\n" + "=" * 60)
    print("  GESTION DE METADATA Y RELEASE - PERUSPATIAL HUB (QGIS)")
    print("=" * 60)
    print(f"Version actual        : {current_ver}")
    print(f"Nombre del plugin     : {general.get('name', 'PeruSpatial Hub')}")
    print(f"Version minima QGIS   : {general.get('qgisminimumversion', '3.34')}")
    print(f"Autor                 : {general.get('author', '')} <{general.get('email', '')}>")
    print("-" * 60)

    resp = input("Desea actualizar la version / metadata? [s/N]: ").strip().lower()
    if resp not in ("s", "si", "y", "yes"):
        print("Manteniendo metadata actual.")
        return

    # Prompt new version
    ver_input = input(f"Nueva version [{current_ver}]: ").strip()
    new_version = ver_input if ver_input else current_ver

    # Prompt changelog for this version
    current_cl = general.get("changelog", "")
    print(f"\nChangelog actual:\n  {current_cl}")
    cl_input = input(f"\nNovedades para v{new_version} (dejar vacio si no cambia):\n> ").strip()

    if cl_input:
        # Prepend new changelog note in metadata.txt
        new_cl = f"{new_version} - {cl_input}. {current_cl}".strip()
        general["changelog"] = new_cl
        update_documentation_version(new_version, cl_input)
    else:
        update_documentation_version(new_version)

    general["version"] = new_version

    save_metadata(metadata)
    print(f"\n[OK] 'metadata.txt' actualizado con exito a la version {new_version}.\n")


def validate_plugin() -> list[str]:
    errors = []
    metadata = load_metadata()
    if "general" not in metadata:
        errors.append("Falta la seccion [general] en metadata.txt")
        return errors

    general = metadata["general"]
    for key in MANDATORY_METADATA_KEYS:
        # ConfigParser lowercases keys; check with .lower().
        if not general.get(key.lower(), "").strip():
            errors.append(f"Falta el campo obligatorio '{key}' en metadata.txt")

    for rel_path in PLUGIN_FILES:
        full_path = ROOT / rel_path
        if not full_path.is_file():
            errors.append(f"Archivo requerido no encontrado: {rel_path}")

    return errors


def build_archive(output_directory: str = "releases") -> Path:
    errors = validate_plugin()
    if errors:
        print("\n[ERROR] Se encontraron fallas en la validacion de QGIS:")
        for err in errors:
            print(f" - {err}")
        sys.exit(1)

    version = plugin_version()
    output_dir = ROOT / output_directory
    output_dir.mkdir(exist_ok=True)

    archive_filename = f"PeruSpatial_Hub_QGIS_v{version}.zip"
    archive = output_dir / archive_filename

    # Also build to dist for backward compatibility with CI artifact uploads.
    dist_dir = ROOT / "dist"
    dist_dir.mkdir(exist_ok=True)
    legacy_archive = dist_dir / f"PeruSpatial-Hub-{version}.zip"

    with ZipFile(archive, "w", compression=ZIP_DEFLATED) as bundle:
        for relative_name in PLUGIN_FILES:
            source = ROOT / relative_name
            bundle.write(source, Path(PLUGIN_NAME) / relative_name)

    # Legacy copy in dist (consumed by GitHub Actions upload-artifact step).
    with ZipFile(legacy_archive, "w", compression=ZIP_DEFLATED) as bundle:
        for relative_name in PLUGIN_FILES:
            source = ROOT / relative_name
            bundle.write(source, Path(PLUGIN_NAME) / relative_name)

    return archive


def main() -> None:
    parser = argparse.ArgumentParser(description="Package PeruSpatial Hub QGIS Plugin.")
    parser.add_argument(
        "--interactive",
        "-i",
        action="store_true",
        help="Prompt to update metadata and version interactively before packaging.",
    )
    parser.add_argument(
        "--outdir",
        "-o",
        default="releases",
        help="Target folder for release ZIP (default: releases).",
    )
    args = parser.parse_args()

    if args.interactive:
        interactive_metadata_update()

    zip_path = build_archive(args.outdir)
    size_kb = zip_path.stat().st_size / 1024

    print("\n" + "=" * 60)
    print("  EMPAQUETADO EXITOSO LISTO PARA QGIS OFFICIAL REPOSITORY")
    print("=" * 60)
    print(f"Archivo generado : {zip_path.name}")
    print(f"Ubicacion        : {zip_path}")
    print(f"Tamano           : {size_kb:.2f} KB")
    print(f"Estructura raiz  : {PLUGIN_NAME}/")
    print(f"Archivos empaq.  : {len(PLUGIN_FILES)}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
