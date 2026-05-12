from decimal import Decimal

from pagos.models import Pago, Gasto
from .models import MovimientoCaja


def _sum_montos(queryset):
    total = Decimal("0.00")

    for obj in queryset:
        total += obj.monto

    return total


def calcular_resumen_caja(caja):
    """
    Función CENTRAL del sistema financiero.
    TODO el sistema debe usar esto.
    """

    # =====================================================
    # PAGOS (INGRESOS CLÍNICOS)
    # =====================================================

    pagos = Pago.objects.filter(
        fecha__date=caja.fecha
    )

    ingresos_pagos = _sum_montos(pagos)

    # =====================================================
    # GASTOS
    # =====================================================

    gastos = Gasto.objects.filter(
        fecha__date=caja.fecha
    )

    total_gastos = _sum_montos(gastos)

    # =====================================================
    # MOVIMIENTOS MANUALES
    # =====================================================

    movimientos = MovimientoCaja.objects.filter(
        caja=caja
    )

    entradas = movimientos.filter(tipo="entrada")
    salidas = movimientos.filter(tipo="salida")

    total_entradas = _sum_montos(entradas)
    total_salidas = _sum_montos(salidas)

    # =====================================================
    # EGRESOS TOTALES
    # =====================================================

    egresos_totales = total_gastos + total_salidas

    # =====================================================
    # SALDO ESPERADO REAL
    # =====================================================

    saldo_esperado = (
        (caja.saldo_inicial or Decimal("0.00"))
        + ingresos_pagos
        + total_entradas
        - egresos_totales
    )

    # =====================================================
    # DIFERENCIA
    # =====================================================

    saldo_declarado = caja.saldo_final_declarado or Decimal("0.00")

    diferencia = saldo_declarado - saldo_esperado

    # =====================================================
    # MÉTODOS DE PAGO
    # =====================================================

    efectivo = _sum_montos(
        pagos.filter(metodo="efectivo")
    )

    tarjeta = _sum_montos(
        pagos.filter(metodo="tarjeta")
    )

    transferencia = _sum_montos(
        pagos.filter(metodo="transferencia")
    )

    # =====================================================
    # RESPUESTA CENTRAL
    # =====================================================

    return {
        "pagos": pagos,
        "gastos": gastos,
        "movimientos": movimientos,

        "ingresos_pagos": ingresos_pagos,

        "total_gastos": total_gastos,

        "total_entradas": total_entradas,
        "total_salidas": total_salidas,

        "egresos_totales": egresos_totales,

        "saldo_esperado": saldo_esperado,

        "saldo_declarado": saldo_declarado,

        "diferencia": diferencia,

        "efectivo": efectivo,
        "tarjeta": tarjeta,
        "transferencia": transferencia,
    }


