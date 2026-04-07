from django.contrib import admin
from .models import Pago

@admin.register(Pago)
class PagoAdmin(admin.ModelAdmin):
    list_display = ("fecha", "paciente", "monto", "metodo")
    list_filter = ("metodo",)
    search_fields = ("paciente", "concepto")
