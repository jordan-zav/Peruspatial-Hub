"""Check public catalogue endpoints without downloading data or changing the inventory."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from peruspatial_hub_sources import LIVE_SERVERS
from peruspatial_hub_urls import url_with_json, wms_capabilities_url


def probe_source(source, timeout=12):
    """Verify protocol content, not merely an HTTP 200 response."""
    started = time.monotonic()
    result = dict(source)
    url = url_with_json(source["url"]) if source["stype"] == "arcgis_rest" else wms_capabilities_url(source["url"])
    result["request_url"] = url
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "PeruSpatial-Hub-Audit/1.0"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            result["http_status"] = response.status
            result["response_url"] = response.url
            payload = response.read(25 * 1024 * 1024 + 1)
        if len(payload) > 25 * 1024 * 1024:
            raise ValueError("Response exceeds 25 MiB")
        if source["stype"] == "arcgis_rest":
            data = json.loads(payload.decode("utf-8-sig"))
            if not isinstance(data, dict):
                raise ValueError("Expected an ArcGIS JSON object")
            if data.get("error"):
                result["arcgis_error"] = data["error"]
                raise ValueError(f"ArcGIS error: {data['error']}")
            if not ("folders" in data or "services" in data):
                raise ValueError("Response is not an ArcGIS service directory")
            result["folders"] = data.get("folders", [])
            result["services"] = data.get("services", [])
        else:
            if b"<!ENTITY" in payload.upper():
                raise ValueError("XML entities not accepted")
            root = ET.fromstring(payload)
            if root.tag.rsplit("}", 1)[-1] not in ("WMS_Capabilities", "WMT_MS_Capabilities"):
                raise ValueError("Response is not WMS GetCapabilities")
            result["layer_count"] = sum(1 for node in root.iter() if node.tag.rsplit("}", 1)[-1] == "Layer")
            if not result["layer_count"]:
                raise ValueError("WMS publishes no layers")
            result["has_doctype"] = b"<!DOCTYPE" in payload.upper()
        result["status"] = "ok"
    except Exception as exc:
        result["status"] = "unavailable"
        result["error"] = str(exc)
        if isinstance(exc, urllib.error.HTTPError):
            result["http_status"] = exc.code
    result["seconds"] = round(time.monotonic() - started, 3)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--extra", type=Path, help="JSON array of additional candidate sources")
    parser.add_argument("--timeout", type=float, default=12)
    args = parser.parse_args()
    sources = list(LIVE_SERVERS)
    if args.extra:
        sources.extend(json.loads(args.extra.read_text(encoding="utf-8-sig")))
    results = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(probe_source, source, args.timeout) for source in sources]
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            print(f"[{result['status']}] {result['institution']} {result['url']}: "
                  f"{result.get('error', 'verified protocol response')}", flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"checked_at": datetime.now(timezone.utc).isoformat(),
        "sources": results}, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
