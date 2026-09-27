"""Clasificación de traslados de fondos ya pertenecientes a Sonrisar."""

from decimal import Decimal

from django.db.models import Q


CATEGORIA_INGRESO_RESGUARDO = "Ingreso desde resguardo"


def ingresos_desde_resguardo(movimientos):
    """Incluye la categoría nueva y los tres traslados conocidos de agosto 2026.

    No se cambia la base histórica automáticamente. Los importes, fechas y
    concepto hacen explícita la reclasificación confirmada por administración.
    """
    anteriores = (
        Q(fecha__date="2026-08-14", fecha__hour=14, fecha__minute=25, monto=Decimal("1550.00"))
        | Q(fecha__date="2026-08-31", fecha__hour=16, fecha__minute=17, monto=Decimal("1200.00"))
        | Q(fecha__date="2026-08-31", fecha__hour=16, fecha__minute=49, monto=Decimal("1000.00"))
    )
    return movimientos.filter(tipo="entrada").filter(
        Q(categoria=CATEGORIA_INGRESO_RESGUARDO)
        | (Q(categoria="Ingreso manual", concepto__iexact="cambio") & anteriores)
    )
