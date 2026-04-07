from decimal import Decimal
from django.utils import timezone
from django.db.models import Sum
from .models import CashSession

def get_or_create_today_cash():
    """
    Devuelve la caja del día.
    Si no existe, la crea automáticamente abierta.
    """
    today = timezone.localdate()

    caja, created = CashSession.objects.get_or_create(
        fecha=today,
        defaults={
            "estado": CashSession.Status.ABIERTA,
            "saldo_inicial": 0,
        }
    )
    return caja


def calcular_total_caja(caja):
    """
    Total real de caja = saldo inicial + suma de pagos NO anulados
    """
    total_pagos = (
        caja.pagos
        .filter(anulado=False)
        .aggregate(total=Sum("monto"))
        .get("total") or 0
    )

    return caja.saldo_inicial + total_pagos


def cerrar_caja(caja, saldo_declarado):
    """
    Cierra la caja y calcula la diferencia.
    TODO se maneja con Decimal (nunca float).
    """

    # Convertir saldo declarado a Decimal
    saldo_declarado = Decimal(saldo_declarado)

    total_pagos = (
        caja.pagos
        .filter(anulado=False)
        .aggregate(total=Sum("monto"))
        .get("total") or Decimal("0.00")
    )

    total_real = caja.saldo_inicial + total_pagos
    diferencia = saldo_declarado - total_real

    caja.saldo_final_declarado = saldo_declarado
    caja.estado = CashSession.Status.CERRADA
    caja.cerrada_en = timezone.now()
    caja.save()

    return total_real, diferencia

