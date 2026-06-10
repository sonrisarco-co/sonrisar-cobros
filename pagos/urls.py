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

    path("compras/", views.compras_proveedores, name="compras_proveedores"),
    path("compras/nueva/", views.compra_proveedor_nueva, name="compra_proveedor_nueva"),

    path(
        "compras/<int:compra_id>/",
        views.compra_proveedor_detalle,
        name="compra_proveedor_detalle"
    ),

    path(
        "compras/<int:compra_id>/editar/",
        views.compra_proveedor_editar,
        name="compra_proveedor_editar"
    ),

    path(
        "compras/<int:compra_id>/eliminar/",
        views.compra_proveedor_eliminar,
        name="compra_proveedor_eliminar"
    ),

    path(
        "compras/<int:compra_id>/pago/",
        views.compra_proveedor_pago,
        name="compra_proveedor_pago"
    ),

    path(
        "pagos-proveedor/<int:pago_id>/eliminar/",
        views.pago_compra_eliminar,
        name="pago_compra_eliminar"
    ),
]