from django.contrib import admin

from .models import Pago, Gasto


@admin.register(Pago)
class PagoAdmin(admin.ModelAdmin):
    list_display = (
        "fecha",
        "paciente",
        "monto",
        "metodo",
        "concepto",
    )

    search_fields = (
        "paciente",
        "concepto",
    )

    list_filter = (
        "metodo",
        "fecha",
    )


@admin.register(Gasto)
class GastoAdmin(admin.ModelAdmin):
    list_display = (
        "fecha",
        "concepto",
        "monto",
        "metodo",
    )

    search_fields = (
        "concepto",
    )

    list_filter = (
        "metodo",
        "fecha",
    )