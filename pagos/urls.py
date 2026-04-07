from django.urls import path
from . import views

app_name = "pagos"

urlpatterns = [
    path("nuevo/", views.nuevo_pago, name="nuevo"),
    path("historial/", views.historial, name="historial"),
    path("api/por-paciente/", views.api_pagos_por_paciente, name="api_pagos_por_paciente"),
]