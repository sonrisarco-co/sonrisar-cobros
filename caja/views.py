from decimal import Decimal
from django.shortcuts import render, redirect
from django.utils import timezone
from .models import CashSession, MovimientoCaja
from pagos.models import Pago


def _sum_montos(queryset):
    total = Decimal("0.00")
    for obj in queryset:
        total += obj.monto
    return total


# ============================
# TABLERO (CAJA DEL DÍA)
# ============================
def tablero(request):
    caja_actual = CashSession.obtener_caja_del_dia()

    # PAGOS DEL DÍA
    pagos = Pago.objects.filter(
        fecha__date=caja_actual.fecha
    ).order_by("-fecha")

    total_pagos = sum(p.monto for p in pagos)
    cantidad_pagos = pagos.count()
    promedio = total_pagos / cantidad_pagos if cantidad_pagos > 0 else 0
    ultimo_pago = pagos.first() if cantidad_pagos > 0 else None

    # MOVIMIENTOS MANUALES
    movimientos = MovimientoCaja.objects.filter(caja=caja_actual).order_by("-fecha")
    entradas = movimientos.filter(tipo="entrada")
    salidas = movimientos.filter(tipo="salida")

    total_entradas = _sum_montos(entradas)
    total_salidas = _sum_montos(salidas)
    balance_mov = total_entradas - total_salidas

    # ============================
    # CÁLCULOS IMPORTANTES
    # ============================

    # ❗❗ Total del día → SOLO pagos + movimientos
    total_del_dia = total_pagos + balance_mov

    # ❗❗ Total calculado de la caja → saldo inicial incluido
    total_caja = (caja_actual.saldo_inicial or Decimal("0.00")) + total_del_dia

    return render(request, "caja/tablero.html", {
        "caja": caja_actual,

        # PAGOS
        "pagos": pagos,
        "total_pagos": total_pagos,
        "cantidad_pagos": cantidad_pagos,
        "promedio": promedio,
        "ultimo_pago": ultimo_pago,

        # MOVIMIENTOS
        "movimientos": movimientos,
        "ultimos_mov": movimientos[:5],
        "total_entradas": total_entradas,
        "total_salidas": total_salidas,
        "balance": balance_mov,

        # TOTALES
        "total_del_dia": total_del_dia,   # ← Este es el nuevo correcto
        "total_caja": total_caja,         # ← Este incluye saldo inicial
    })


# ============================
# EDITAR SALDO INICIAL
# ============================
def saldo_inicial(request):
    caja = CashSession.obtener_caja_del_dia()

    if request.method == "POST":
        nuevo_saldo = request.POST.get("saldo_inicial", "").strip()
        try:
            nuevo_saldo = Decimal(nuevo_saldo)
            caja.saldo_inicial = nuevo_saldo
            caja.save()
        except:
            pass

    return redirect("caja:tablero")


# ============================
# NUEVO MOVIMIENTO
# ============================
def movimiento_nuevo(request):
    if request.method == "POST":
        caja = CashSession.obtener_caja_del_dia()

        tipo = request.POST.get("tipo", "").strip()
        concepto = request.POST.get("concepto", "").strip()
        monto = request.POST.get("monto", "").strip()

        if tipo in ("entrada", "salida") and concepto and monto:
            MovimientoCaja.objects.create(
                caja=caja,
                tipo=tipo,
                concepto=concepto,
                monto=monto
            )

    return redirect("caja:tablero")


# ============================
# CERRAR CAJA
# ============================
def cerrar_caja(request):
    caja = CashSession.obtener_caja_del_dia()

    pagos = Pago.objects.filter(caja=caja)
    total_pagos = _sum_montos(pagos)

    # 🔥 DESGLOSE POR MEDIO DE PAGO
    efectivo = _sum_montos(pagos.filter(metodo="efectivo"))
    tarjeta = _sum_montos(pagos.filter(metodo="tarjeta"))
    transferencia = _sum_montos(pagos.filter(metodo="transferencia"))

    movimientos = MovimientoCaja.objects.filter(caja=caja)
    total_entradas = _sum_montos(movimientos.filter(tipo="entrada"))
    total_salidas = _sum_montos(movimientos.filter(tipo="salida"))
    balance_mov = total_entradas - total_salidas

    total_caja = (caja.saldo_inicial or Decimal("0.00")) + total_pagos + balance_mov
    
    # Calcular por medio de pago
    efectivo = _sum_montos(pagos.filter(metodo="efectivo"))
    tarjeta = _sum_montos(pagos.filter(metodo="tarjeta"))
    transferencia = _sum_montos(pagos.filter(metodo="transferencia"))

    total_pagos = efectivo + tarjeta + transferencia

    # =================================
    # POST → CERRAR DEFINITIVAMENTE
    # =================================
    if request.method == "POST":
        saldo_final = request.POST.get("saldo_final", "").strip()

        # 🔥 GUARDAR TOTALES POR MEDIO DE PAGO
        caja.efectivo = efectivo
        caja.tarjeta = tarjeta
        caja.transferencia = transferencia
        caja.total_pagos = total_pagos

        caja.saldo_final_declarado = saldo_final
        caja.estado = CashSession.Status.CERRADA
        caja.cerrada_en = timezone.now()
        caja.save()

        return redirect("caja:cerradas")

    # ================================
    # GET → MOSTRAR CIERRE PREVIO
    # ================================
    return render(request, "caja/cerrar_caja.html", {
        "caja": caja,
        "total_caja": total_caja,
        "total_pagos": total_pagos,
        "balance": balance_mov,

        # 🔥 ENVIARLOS AL TEMPLATE
        "efectivo": efectivo,
        "tarjeta": tarjeta,
        "transferencia": transferencia,
    })


# ============================
# LISTADO DE CAJAS CERRADAS
# ============================
def cajas_cerradas(request):
    cajas = CashSession.objects.filter(
        estado=CashSession.Status.CERRADA
    ).order_by("-fecha")

    for c in cajas:
        pagos = Pago.objects.filter(caja=c)
        total_pagos = _sum_montos(pagos)

        movimientos = MovimientoCaja.objects.filter(caja=c)
        total_entradas = _sum_montos(movimientos.filter(tipo="entrada"))
        total_salidas = _sum_montos(movimientos.filter(tipo="salida"))
        balance_mov = total_entradas - total_salidas

        c.total_pagos_calc = total_pagos
        c.balance_mov_calc = balance_mov
        c.total_caja_calc = (c.saldo_inicial or Decimal("0.00")) + total_pagos + balance_mov

    return render(request, "caja/cajas_cerradas.html", {"cajas": cajas})
