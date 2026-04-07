from django.urls import path
from . import views

app_name = "reportes"

urlpatterns = [
    path("selector/", views.selector, name="selector"),
    path("<int:year>/<int:month>/", views.reporte_mensual, name="reporte_mensual"),
    path("<int:year>/<int:month>/pdf/", views.exportar_pdf, name="reporte_pdf"),
]
