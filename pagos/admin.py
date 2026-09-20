from datetime import datetime, time

from django import forms
from django.contrib import admin
from django.utils import timezone

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


class GastoAdminForm(forms.ModelForm):
    """Muestra una sola fecha, sin exponer una hora innecesaria en el admin."""

    fecha = forms.DateField(
        label="Fecha del gasto",
        input_formats=["%Y-%m-%d", "%d/%m/%Y"],
        widget=forms.DateInput(
            format="%Y-%m-%d",
            attrs={"type": "date"},
        ),
    )

    class Meta:
        model = Gasto
        fields = "__all__"

    def clean_fecha(self):
        fecha = self.cleaned_data["fecha"]
        fecha_hora = datetime.combine(fecha, time.min)
        return timezone.make_aware(fecha_hora, timezone.get_current_timezone())


@admin.register(Gasto)
class GastoAdmin(admin.ModelAdmin):
    form = GastoAdminForm
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
