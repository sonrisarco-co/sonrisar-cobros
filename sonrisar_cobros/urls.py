from django.contrib import admin
from django.urls import path, include

from django.conf import settings
from django.conf.urls.static import static
from . import access_views

urlpatterns = [
    path("", access_views.home_redirect, name="home"),
    path("cuenta/ingresar/", access_views.access_login, name="acceso_login"),
    path("cuenta/salir/", access_views.access_logout, name="acceso_logout"),
    path("cuenta/turnos/", access_views.access_history, name="acceso_historial"),
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
