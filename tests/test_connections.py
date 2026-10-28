import pytest

from peruspatial_hub_connections import connection_root, register_connection


class Settings:
    """In-memory QSettings subset; native QGIS compatibility is checked by UI tests."""

    def __init__(self):
        self.values = {}
        self.group = ""

    def beginGroup(self, group):
        self.group = group.rstrip("/") + "/"

    def endGroup(self):
        self.group = ""

    def childGroups(self):
        return list({key[len(self.group):].split("/")[0] for key in self.values if key.startswith(self.group)})

    def value(self, key, default=None):
        return self.values.get(key, default)

    def setValue(self, key, value):
        self.values[key] = value

    def contains(self, key):
        return key in self.values


def test_name_collision_preserves_url_and_authentication():
    settings = Settings()
    register_connection(settings, "Shared", "https://one.test/wms", "wms", "auth123")
    original = dict(settings.values)
    renamed = register_connection(settings, "Shared", "https://two.test/wms", "wms")
    assert renamed != "Shared"
    assert all(settings.value(key) == value for key, value in original.items())
    assert register_connection(settings, "Shared", "https://two.test/wms", "wms") == renamed
    assert len(settings.values) == 4


def test_same_endpoint_preserves_auth_unless_explicitly_anonymous():
    settings = Settings()
    url = "https://example.test/rest/services"
    register_connection(settings, "Private", url, "arcgis_rest", "auth123")
    register_connection(settings, "Private", url, "arcgis_rest")
    key = connection_root("arcgis_rest") + "/Private/authcfg"
    assert settings.value(key) == "auth123"
    register_connection(settings, "Private", url, "arcgis_rest", anonymous_override=True)
    assert settings.value(key) == ""


def test_case_variant_does_not_overwrite_another_connection():
    settings = Settings()
    register_connection(settings, "Shared", "https://one.test/wms", "wms", "auth123")
    assert register_connection(settings, "SHARED", "https://one.test/wms", "wms") == "Shared"
    original = dict(settings.values)
    assert register_connection(settings, "shared", "https://two.test/wms", "wms").casefold() != "shared"
    assert all(settings.value(key) == value for key, value in original.items())


@pytest.mark.parametrize("name", ["A/B", "A\\B", "A\nB", "\t", ""])
def test_connection_names_cannot_create_nested_groups(name):
    settings = Settings()
    saved = register_connection(settings, name, "https://example.test/wms", "wms")
    assert saved and "/" not in saved and "\\" not in saved
    settings.beginGroup(connection_root("wms"))
    assert settings.childGroups() == [saved]


@pytest.mark.parametrize("url", ["http://example.test", "https://user:secret@example.test", "file:///tmp/map", "https://"])
def test_invalid_connection_is_rejected_without_writing_settings(url):
    settings = Settings()
    with pytest.raises(ValueError):
        register_connection(settings, "Invalid", url, "wms")
    assert settings.values == {}


def test_unsupported_type_is_rejected_without_writing_settings():
    settings = Settings()
    with pytest.raises(ValueError):
        register_connection(settings, "Unsupported", "https://example.test", "unknown")
    assert settings.values == {}
