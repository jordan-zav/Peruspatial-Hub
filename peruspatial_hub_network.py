"""Scoped network compatibility for SENAMHI GeoServer with Qt 5 HTTP/2."""

from qgis.core import Qgis, QgsNetworkAccessManager
from qgis.PyQt.QtNetwork import QNetworkRequest

from .peruspatial_hub_urls import requires_http1


def prepare_request(request):
    """Keep HTTPS/TLS validation; use HTTP/1.1 for the affected GeoServer only."""
    if requires_http1(request.url().toString()):
        request.setAttribute(QNetworkRequest.Attribute.Http2AllowedAttribute, False)
    # Older QGIS Python bindings expect a QString result from preprocessors.
    return ""


class NetworkCompatibility:
    """Own and remove the native-provider request hook with the plugin lifetime."""

    def __init__(self):
        self.processor_id = None

    def install(self):
        # Older SIP bindings invoke Python APIs after releasing the GIL and
        # can crash on Python 3.12 (QGIS issue #55329). The 3.44 bindings move
        # those calls outside the released-GIL section. Metadata requests
        # still use prepare_request directly on every supported version.
        if Qgis.QGIS_VERSION_INT < 34400:
            return
        if self.processor_id is None:
            self.processor_id = QgsNetworkAccessManager.setRequestPreprocessor(prepare_request)

    def uninstall(self):
        if self.processor_id is not None:
            QgsNetworkAccessManager.removeRequestPreprocessor(self.processor_id)
            self.processor_id = None
