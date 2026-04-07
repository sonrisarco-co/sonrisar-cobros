from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),

    # Dashboard principal
    path("caja/", include(("caja.urls", "caja"), namespace="caja")),

    path("pagos/", include(("pagos.urls", "pagos"), namespace="pagos")),
    path("reportes/", include(("reportes.urls", "reportes"), namespace="reportes")),
    path("config/", include(("configuracion.urls", "configuracion"), namespace="configuracion")),

]


