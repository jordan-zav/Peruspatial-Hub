<p align="center"><strong>English</strong> · <a href="README.es.md">Español</a></p>

<div align="center">
  <img src="logo_solo.png" alt="PeruSpatial Hub" width="112">

# PeruSpatial Hub

**Find official Peruvian geospatial services and load them directly in QGIS.**

Search a bundled offline catalogue, explore public ArcGIS REST and WMS
directories, and load native raster or vector services without copying viewer URLs.

[![Source 1.3.0](https://img.shields.io/badge/source-1.3.0-2563eb)](metadata.txt)
[![Release](https://img.shields.io/github/v/release/jordan-zav/Peruspatial-Hub?color=7c3aed)](https://github.com/jordan-zav/Peruspatial-Hub/releases/latest)
[![QGIS 3.34+](https://img.shields.io/badge/QGIS-3.34%2B-589632?logo=qgis&logoColor=white)](https://qgis.org/)
[![License: GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-0f766e)](LICENSE)

</div>

## Install and start

1. Download the ZIP from the [latest release](https://github.com/jordan-zav/Peruspatial-Hub/releases/latest).
2. In QGIS 3.34+, open Plugins → Manage and Install Plugins → Install from ZIP.
3. Enable PeruSpatial Hub and open Database → PeruSpatial Hub.
4. Search a keyword or choose a category.
5. Expand a service and double-click a layer, or use Add to map.
6. Review institutional attribution and the layer's datum/CRS before analysis.

The source declares 1.3.0. The release badge points to the actually published
ZIP, which may lag behind the source version.

## Fast local search

The bundled inventory contains over 8,000 official services and layers. Typing
filters this local file with a short debounce and at most 200 visible results.
**Search does not send HTTP requests.** Live requests occur only when you
explicitly expand a server/service or add a layer.

Unavailable or authentication-protected servers do not block local search.
The inventory can be regenerated outside QGIS:

~~~powershell
python scripts/build_catalog.py
~~~

## Main features

| Feature | What you can do |
| --- | --- |
| Unified catalogue | Browse official directories by institution and topic |
| Local search | Search keywords such as sismos, concesiones or cuencas |
| Native layers | Add REST or WMS sublayers through the corresponding QGIS provider |
| Browser integration | Register one or all connections in the native QGIS Browser |
| Datum reminders | Review sources marked as possibly containing PSAD56 layers |
| Sources | Read availability notes recorded in the catalogue |
| Tools | Copy URLs, open browser pages, verify servers and configure private access |

The project covers geology, geography, remote sensing, environment,
hydrocarbons, hydrogeology, archaeology and territorial management. It does not
change the ownership or terms of the services it accesses.

## Institutions and recorded availability

The following checks belong to **15 July 2026**, not to this documentation
update. External services can change or become unavailable at any time.

| Institution | Directory / recorded contents |
| --- | --- |
| INGEMMET / GEOCATMIN | Two ArcGIS REST directories with mining cadastre, geology and geochemistry |
| IGN / IDEP | National mapping and institutional ArcGIS directories |
| ANA through IDEP | Wetlands, springs, glaciers, stations and hydrographic units |
| IGP | REST, general WMS, direct recent NDVI condition/anomaly services and other public layers |
| MINAM | Environmental and zoning services in Geoservidor MINAM |
| SERNANP | Protected-area management, monitoring and mapping |
| SERFOR | GeoSERFOR forest services, imagery and geoprocessing |
| Ministry of Culture | Official SIGDA directory |
| OSINERGMIN | Electricity, gas, hydrocarbons, mining and mapping |
| OEFA | PIFA monitoring, inspections, environmental emergencies and interoperable data |

IGP includes services used by Zonifica Perú, isotope stations, seismic/volcanic
monitoring and base maps. REST and WMS layers can be explored directly.

### Sources not currently integrated

- CENEPRED: SIGRID offers account/email access, but its Web Adaptor could not
  reach internal servers during the recorded check; this is not merely a REST login prompt.
- COFOPRI: the historical domain had an incomplete certificate chain and its
  REST endpoint returned 404. The plugin does not disable TLS verification.
- SUNARP: Visor BGR requires DNI, issue date and captcha. No anonymous REST
  directory was verified for responsible registration.

The Sources information keeps these notes visible. The plugin does not bundle
credentials, bypass captchas or turn off certificate validation.

## Manual installation

Copy the complete peruspatial_hub folder into python/plugins in your active
QGIS profile. Typical profile plugin directories are:

| System | Location |
| --- | --- |
| Windows | %APPDATA%/QGIS/QGIS3/profiles/default/python/plugins |
| Linux | ~/.local/share/QGIS/QGIS3/profiles/default/python/plugins |
| macOS | ~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins |

Restart QGIS, enable the installed plugin and open its toolbar or Database menu
entry. Use your actual profile directory if it is not named default.

## Datum and spatial accuracy

Do not assume that historical layers are WGS84. Legacy Peruvian maps may use
PSAD56; merely assigning WGS84 can misplace the data, with shifts of up to
200 metres noted in the original guidance. Inspect source metadata and use an
appropriate documented datum transformation instead of relabelling coordinates.

Keep a consistent projected project CRS, typically UTM 17S, 18S or 19S according
to location. The PSAD56 reminder is a prompt to review the data, not a verified
transformation. Absence of the reminder does not certify a layer's CRS.

## Panel layout

Search and category controls sit above the catalogue. Details for the selected
service or layer appear below it. Add to map is the primary action; Register
connection saves the choice in the QGIS Browser. Tools groups URL copying,
browser opening, authentication, connection registration and server checks.
The panel follows the QGIS font and palette.

## Development and project status

~~~powershell
python -m pip install -r requirements-dev.txt
python -m pytest
python scripts/package_plugin.py
~~~

The packager creates a ZIP with the peruspatial_hub directory QGIS expects.
Pure URL-building functions can be tested without QGIS. Before a release,
also check the ZIP, plugin loading and a sample of real services in QGIS.
A responsive endpoint does not prove that all its sublayers, metadata or
access policies remain unchanged.

## Licensing and contact

[GNU GPL v3](LICENSE) applies to the software. Public-service data retain each
institution's authorship, attribution and access conditions.
Jordan Zavaleta — [GisGeo Dev](https://gisgeo.dev) ·
[jordanzav@gisgeo.dev](mailto:jordanzav@gisgeo.dev) ·
[Source and issues](https://github.com/jordan-zav/Peruspatial-Hub).
