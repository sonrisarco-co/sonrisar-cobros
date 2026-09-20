"""Read-only inventory for reviewing patient links; this is not a backup."""
import hashlib
import json
from datetime import datetime, time

from django import forms
from django.core.exceptions import PermissionDenied
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone


def download_inventory(request, models, source):
    if not request.user.is_active or not request.user.is_superuser:
        raise PermissionDenied
    tables = {}
    with transaction.atomic():
        for model in models:
            fields = [field.attname for field in model._meta.concrete_fields]
            rows = []
            for record in model.objects.order_by(model._meta.pk.name).values(*fields).iterator():
                encoded = json.dumps(record, cls=DjangoJSONEncoder, sort_keys=True,
                                     ensure_ascii=False, separators=(",", ":"))
                # Keep clinical free text and fiscal XML out of the inventory.
                visible = {key: value for key, value in record.items()
                           if key == model._meta.pk.attname or key.endswith("_id")
                           or key in ("nombre", "apellido", "ci", "telefono", "paciente",
                                      "monto", "monto_total", "total", "fecha", "estado",
                                      "pieza", "cara", "numero", "tipo", "categoria")}
                visible["record_sha256"] = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
                rows.append(visible)
            tables[model._meta.label_lower] = {"count": len(rows), "records": rows}
    response = JsonResponse({
        "format": "sonrisar-patient-inventory-v1", "source": source,
        "generated_at": timezone.now(), "is_backup": False,
        "note": "Solo inventario. No contiene historias ni archivos completos. "
                "Puede reflejar cambios concurrentes; no usar como respaldo.",
        "tables": tables,
    }, json_dumps_params={"ensure_ascii": False, "indent": 2})
    response["Content-Disposition"] = f'attachment; filename="diagnostico-{source}.json"'
    response["Cache-Control"] = "no-store"
    return response


from django.contrib import admin
from django.apps import apps
from django.urls import path

from .models import Pago, Gasto


@admin.register(Pago)
class PagoAdmin(admin.ModelAdmin):
    change_list_template = "admin/pagos/pago/change_list.html"

    def get_urls(self):
        return [path("diagnostico/", self.admin_site.admin_view(self.export_inventory),
                     name="pagos_pago_inventory")] + super().get_urls()

    def export_inventory(self, request):
        models = [apps.get_model(label) for label in (
            "pagos.Pago", "pagos.DevolucionPaciente", "pagos.Gasto",
            "caja.CashSession", "caja.MovimientoCaja",
        )]
        return download_inventory(request, models, "cobros")

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
