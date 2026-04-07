from django.contrib import admin
from .models import CashSession, MovimientoCaja


@admin.register(CashSession)
class CashSessionAdmin(admin.ModelAdmin):
    list_display = ("fecha", "estado", "saldo_inicial", "saldo_final_declarado", "cerrada_en")
    list_filter = ("estado", "fecha")
    ordering = ("-fecha",)
    search_fields = ("fecha",)


@admin.register(MovimientoCaja)
class MovimientoCajaAdmin(admin.ModelAdmin):
    list_display = ("fecha", "tipo", "concepto", "monto", "caja")
    list_filter = ("tipo", "fecha")
    search_fields = ("concepto",)
    ordering = ("-fecha",)
