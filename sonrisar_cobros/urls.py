from django.contrib import admin
from django.urls import path, include

from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),

    # Dashboard principal
    path("caja/", include(("caja.urls", "caja"), namespace="caja")),

    path("pagos/", include(("pagos.urls", "pagos"), namespace="pagos")),

    path("reportes/", include(("reportes.urls", "reportes"), namespace="reportes")),

    path("config/", include(("configuracion.urls", "configuracion"), namespace="configuracion")),
]

# =========================================================
# STATIC FILES EN DESARROLLO
# =========================================================

if settings.DEBUG:
    urlpatterns += static(
        settings.STATIC_URL,
        document_root=settings.STATIC_ROOT
    )