from django.urls import path
from . import views

app_name = "pagos"

urlpatterns = [
    path("nuevo/", views.nuevo_pago, name="nuevo"),
    path("historial/", views.historial, name="historial"),
    path("api/por-paciente/", views.api_pagos_por_paciente, name="api_pagos_por_paciente"),
    path("api/por-cita/", views.api_pago_por_cita, name="api_pago_por_cita"),
    path("api/resumen-pacientes/", views.api_resumen_pacientes, name="api_resumen_pacientes"),
    path("gastos/", views.lista_gastos, name="lista_gastos"),
    path("gastos/nuevo/", views.nuevo_gasto, name="nuevo_gasto"),
    
]