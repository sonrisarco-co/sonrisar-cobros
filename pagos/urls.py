from django.urls import path
from . import views

app_name = "pagos"

urlpatterns = [
    path("nuevo/", views.nuevo_pago, name="nuevo"),
    path("historial/", views.historial, name="historial"),
    path("facture/test-conexion/", views.facture_test_conexion, name="facture_test_conexion"),
    path("facture/emitir-sandbox/<int:pago_id>/", views.facture_emitir_pago_sandbox, name="facture_emitir_pago_sandbox"),
    path("facture/anular-sandbox/<int:pago_id>/", views.facture_anular_pago_sandbox, name="facture_anular_pago_sandbox"),
    path("facture/pdf/<int:pago_id>/", views.facture_pdf_pago, name="facture_pdf_pago"),
    path("facture/xml/<int:pago_id>/", views.facture_xml_pago, name="facture_xml_pago"),
    path("facture/nc/pdf/<int:pago_id>/", views.facture_pdf_nota_credito_pago, name="facture_pdf_nota_credito_pago"),
    path("facture/nc/xml/<int:pago_id>/", views.facture_xml_nota_credito_pago, name="facture_xml_nota_credito_pago"),
    path("<int:pago_id>/recibo/", views.recibo_pago, name="recibo"),

    path("api/por-paciente/", views.api_pagos_por_paciente, name="api_pagos_por_paciente"),
    path("api/por-cita/", views.api_pago_por_cita, name="api_pago_por_cita"),
    path("api/por-protesis/", views.api_pago_por_protesis, name="api_pago_por_protesis"),
    path("api/resumen-pacientes/", views.api_resumen_pacientes, name="api_resumen_pacientes"),
    path("api/resumen-citas/", views.api_resumen_citas, name="api_resumen_citas"),

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