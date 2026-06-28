from django.contrib import messages

from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.core.paginator import Paginator
from django.db.models import Sum, Q
from django.db.models.functions import TruncDate

from .models import CashSession, MovimientoCaja
from pagos.models import Pago, Gasto

from django.http import HttpResponse

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from reportlab.lib import colors
from reportlab.lib.units import mm

import os
from django.conf import settings

from .utils_pdf import generar_pdf_cierre

from urllib.parse import quote


def _sum_montos(queryset):
    total = Decimal("0.00")

    for obj in queryset:
        total += obj.monto

    return total


# =====================================================
# TABLERO
# =====================================================

def tablero(request):

    caja_actual = CashSession.obtener_caja_del_dia()

    caja_bloqueada = (
        caja_actual.estado == CashSession.Status.CERRADA
    )

    pagos = Pago.objects.filter(
        fecha__date=caja_actual.fecha
    ).order_by("-fecha")

    total_pagos = _sum_montos(pagos)

    efectivo = _sum_montos(
        pagos.filter(metodo="efectivo")
    )

    tarjeta = _sum_montos(
        pagos.filter(metodo="tarjeta")
    )

    transferencia = _sum_montos(
        pagos.filter(metodo="transferencia")
    )

    cantidad_pagos = pagos.count()

    promedio = (
        total_pagos / cantidad_pagos
        if cantidad_pagos > 0 else Decimal("0.00")
    )

    ultimo_pago = pagos.first()

    gastos = Gasto.objects.filter(
        fecha__date=caja_actual.fecha,
        afecta_caja=True
    )

    total_gastos = _sum_montos(gastos)

    gastos_efectivo = gastos.filter(
        metodo="efectivo"
    )

    total_gastos_efectivo = _sum_montos(
        gastos_efectivo
    )

    movimientos = MovimientoCaja.objects.filter(
        caja=caja_actual
    ).order_by("-fecha")

    entradas = movimientos.filter(tipo="entrada")
    salidas = movimientos.filter(tipo="salida")

    total_entradas = _sum_montos(entradas)
    total_salidas = _sum_montos(salidas)

    egresos_totales = total_gastos_efectivo + total_salidas

    saldo_esperado = (
        (caja_actual.saldo_inicial or Decimal("0.00"))
        + efectivo
        + total_entradas
        - egresos_totales
    )

    diferencia = (
        (caja_actual.saldo_final_declarado or saldo_esperado)
        - saldo_esperado
    )

    return render(request, "caja/tablero.html", {

        "caja": caja_actual,

        "pagos": pagos,
        "total_pagos": total_pagos,
        "cantidad_pagos": cantidad_pagos,
        "promedio": promedio,
        "ultimo_pago": ultimo_pago,

        "efectivo": efectivo,
        "tarjeta": tarjeta,
        "transferencia": transferencia,

        "gastos": gastos,
        "total_gastos": total_gastos,

        "movimientos": movimientos,
        "ultimos_mov": movimientos[:5],

        "total_entradas": total_entradas,
        "total_salidas": total_salidas,

        "ingresos_totales": total_pagos,
        "egresos_totales": egresos_totales,

        "saldo_esperado": saldo_esperado,
        "balance": saldo_esperado,

        "resultado_real": (
            total_pagos
            + total_entradas
            - total_gastos
            - total_salidas
        ),

        "total_calculado": saldo_esperado,

        "diferencia": diferencia,

        "caja_bloqueada": caja_bloqueada,
    })



# =====================================================
# SALDO INICIAL
# =====================================================

def saldo_inicial(request):

    caja = CashSession.obtener_caja_del_dia()

    
    if (
        caja.estado == CashSession.Status.CERRADA
        or caja.saldo_inicial > 0
    ):
        return redirect("caja:tablero")



    if request.method == "POST":

        saldo = request.POST.get(
            "saldo_inicial",
            "0"
        )

        print("VALOR RECIBIDO:", repr(saldo))

        try:

            saldo = (
                saldo
                .replace(",", ".")
                .strip()
            )

            caja.saldo_inicial = Decimal(saldo)

            caja.save()

            # =====================================
            # VERIFICAR GUARDADO REAL
            # =====================================

            caja.refresh_from_db()

            print(
                "SALDO GUARDADO REAL:",
                caja.saldo_inicial
            )

            print("CAJA ID:", caja.id)

        except Exception as e:

            print("ERROR SALDO INICIAL:", e)

    return redirect("caja:tablero")



# =====================================================
# NUEVO MOVIMIENTO
# =====================================================

def movimiento_nuevo(request):

    if request.method == "POST":

        caja = CashSession.obtener_caja_del_dia()

        if caja.estado == CashSession.Status.CERRADA:
            return redirect("caja:tablero")

        categoria = request.POST.get(
            "categoria",
            ""
        ).strip()

        concepto = request.POST.get(
            "descripcion",
            ""
        ).strip()

        monto = request.POST.get(
            "monto",
            ""
        ).strip()

        # =====================================
        # DEFINIR TIPO AUTOMÁTICAMENTE
        # =====================================

        if categoria == "Ingreso manual":

            tipo = "entrada"

        else:

            tipo = "salida"

        # =====================================
        # GUARDAR
        # =====================================

        if concepto and monto:

            MovimientoCaja.objects.create(
                caja=caja,
                tipo=tipo,
                categoria=categoria,
                concepto=concepto,
                monto=Decimal(monto)
            )

    return redirect("caja:tablero")


# =====================================================
# CERRAR CAJA
# =====================================================

def cerrar_caja(request):

    caja = CashSession.obtener_caja_del_dia()

    if caja.estado == CashSession.Status.CERRADA:
        return redirect("caja:cerradas")

    pagos = Pago.objects.filter(
        fecha__date=caja.fecha
    )

    gastos = Gasto.objects.filter(
        fecha__date=caja.fecha,
        afecta_caja=True
    )

    gastos_efectivo = gastos.filter(
        metodo="efectivo"
    )

    movimientos = MovimientoCaja.objects.filter(
        caja=caja
    )

    total_pagos = _sum_montos(pagos)

    total_gastos = _sum_montos(gastos)

    total_gastos_efectivo = _sum_montos(
        gastos_efectivo
    )

    total_entradas = _sum_montos(
        movimientos.filter(tipo="entrada")
    )

    total_salidas = _sum_montos(
        movimientos.filter(tipo="salida")
    )

    balance_movimientos = total_entradas - total_salidas

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
    # EFECTIVO REAL EN CAJA
    # Solo descuentan caja los gastos en efectivo
    # =====================================================

    efectivo_esperado = (
        (caja.saldo_inicial or Decimal("0.00"))
        + efectivo
        + total_entradas
        - total_gastos_efectivo
        - total_salidas
    )

    # =====================================================
    # RESULTADO GENERAL
    # Acá sí cuentan todos los gastos
    # =====================================================

    resultado_real = (
        total_pagos
        + total_entradas
        - total_gastos
        - total_salidas
    )

    if request.method == "POST":

        saldo_final = request.POST.get(
            "saldo_final",
            "0"
        ).strip()

        try:

            caja.saldo_final_declarado = Decimal(saldo_final)

        except:

            caja.saldo_final_declarado = Decimal("0.00")

        caja.efectivo = efectivo
        caja.tarjeta = tarjeta
        caja.transferencia = transferencia

        caja.total_pagos = total_pagos

        caja.estado = CashSession.Status.CERRADA

        caja.cerrada_en = timezone.now()

        caja.save()

        return redirect("caja:cerradas")

    return render(request, "caja/cerrar_caja.html", {

        "caja": caja,

        "efectivo": efectivo,
        "tarjeta": tarjeta,
        "transferencia": transferencia,

        "total_pagos": total_pagos,
        "total_gastos": total_gastos,

        "total_entradas": total_entradas,
        "total_salidas": total_salidas,

        "balance": balance_movimientos,

        "resultado_real": resultado_real,

        "efectivo_esperado": efectivo_esperado,
    })


# =====================================================
# CAJAS CERRADAS
# =====================================================

def cajas_cerradas(request):

    permitido = request.session.get("pin_ok")
    full_path = request.get_full_path()

    if permitido != full_path:
        return redirect(
            f"/caja/validar-pin/?next={quote(full_path)}"
        )

    request.session.pop("pin_ok", None)

    cajas_qs = (
        CashSession.objects
        .filter(
            estado=CashSession.Status.CERRADA
        )
        .order_by("-fecha")
    )

    paginator = Paginator(cajas_qs, 20)
    page_number = request.GET.get("page")
    cajas = paginator.get_page(page_number)

    fechas = [c.fecha for c in cajas]
    caja_ids = [c.id for c in cajas]

    cero = Decimal("0.00")

    # =====================================================
    # RESUMEN DE PAGOS POR FECHA
    # Una sola consulta para todas las cajas de la página.
    # =====================================================

    pagos_por_fecha = {}

    if fechas:
        pagos_resumen = (
            Pago.objects
            .filter(fecha__date__in=fechas)
            .annotate(dia=TruncDate("fecha"))
            .values("dia")
            .annotate(
                total_pagos=Sum("monto"),
                efectivo=Sum(
                    "monto",
                    filter=Q(metodo="efectivo")
                ),
            )
        )

        pagos_por_fecha = {
            item["dia"]: {
                "total_pagos": item["total_pagos"] or cero,
                "efectivo": item["efectivo"] or cero,
            }
            for item in pagos_resumen
        }

    # =====================================================
    # RESUMEN DE GASTOS POR FECHA
    # Una sola consulta para todos los gastos de la página.
    # =====================================================

    gastos_por_fecha = {}

    if fechas:
        gastos_resumen = (
            Gasto.objects
            .filter(
                fecha__date__in=fechas,
                afecta_caja=True
            )
            .annotate(dia=TruncDate("fecha"))
            .values("dia")
            .annotate(
                total_gastos=Sum("monto"),
                gastos_efectivo=Sum(
                    "monto",
                    filter=Q(metodo="efectivo")
                ),
            )
        )

        gastos_por_fecha = {
            item["dia"]: {
                "total_gastos": item["total_gastos"] or cero,
                "gastos_efectivo": item["gastos_efectivo"] or cero,
            }
            for item in gastos_resumen
        }

    # =====================================================
    # RESUMEN DE MOVIMIENTOS POR CAJA
    # Una sola consulta para entradas y salidas de la página.
    # =====================================================

    movimientos_por_caja = {}

    if caja_ids:
        movimientos_resumen = (
            MovimientoCaja.objects
            .filter(caja_id__in=caja_ids)
            .values("caja_id")
            .annotate(
                total_entradas=Sum(
                    "monto",
                    filter=Q(tipo="entrada")
                ),
                total_salidas=Sum(
                    "monto",
                    filter=Q(tipo="salida")
                ),
            )
        )

        movimientos_por_caja = {
            item["caja_id"]: {
                "total_entradas": item["total_entradas"] or cero,
                "total_salidas": item["total_salidas"] or cero,
            }
            for item in movimientos_resumen
        }

    # =====================================================
    # CALCULOS FINALES POR CAJA
    # Sin consultas extra dentro del for.
    # =====================================================

    for c in cajas:

        pagos_data = pagos_por_fecha.get(c.fecha, {})
        gastos_data = gastos_por_fecha.get(c.fecha, {})
        mov_data = movimientos_por_caja.get(c.id, {})

        total_pagos = pagos_data.get("total_pagos", cero)
        efectivo = pagos_data.get("efectivo", cero)

        total_gastos = gastos_data.get("total_gastos", cero)
        total_gastos_efectivo = gastos_data.get(
            "gastos_efectivo",
            cero
        )

        total_entradas = mov_data.get("total_entradas", cero)
        total_salidas = mov_data.get("total_salidas", cero)

        # =============================================
        # RESULTADO REAL GENERAL
        # Incluye todos los gastos: efectivo, transferencia y tarjeta
        # =============================================

        c.total_pagos_calc = (
            total_pagos + total_entradas
        )

        c.total_gastos_calc = (
            total_gastos + total_salidas
        )

        c.resultado_calc = (
            c.total_pagos_calc
            - c.total_gastos_calc
        )

        # =============================================
        # BALANCE MOVIMIENTOS
        # =============================================

        c.balance_mov_calc = (
            total_entradas - total_salidas
        )

        # =============================================
        # TOTAL CAJA FÍSICA
        # Solo descuenta gastos en efectivo
        # =============================================

        c.total_caja_calc = (
            (c.saldo_inicial or cero)
            + efectivo
            + total_entradas
            - total_gastos_efectivo
            - total_salidas
        )

    return render(
        request,
        "caja/cajas_cerradas.html",
        {
            "cajas": cajas
        }
    )



# =====================================================
# PDF CIERRE DE CAJA
# =====================================================

def pdf_cierre(request, caja_id):

    caja = get_object_or_404(
        CashSession,
        id=caja_id
    )

    return generar_pdf_cierre(caja)



# =====================================================
# MOVIMIENTOS FINANCIEROS
# =====================================================

def movimientos_financieros(request):

    permitido = request.session.get("pin_ok")

    full_path = request.get_full_path()

    if permitido != full_path:
        return redirect(
            f"/caja/validar-pin/?next={quote(full_path)}"
        )

    request.session.pop("pin_ok", None)

    movimientos = []

    hoy = timezone.now()

    
    # ==========================================
    # FILTROS
    # ==========================================

    try:

        mes_actual = int(
            request.GET.get("mes", hoy.month)
        )

    except:

        mes_actual = hoy.month

    try:

        anio_actual = int(
            request.GET.get("anio", hoy.year)
        )

    except:

        anio_actual = hoy.year

    # ==========================================
    # PAGOS
    # ==========================================

    pagos = Pago.objects.filter(
        fecha__month=mes_actual,
        fecha__year=anio_actual
    )

    for pago in pagos:

        movimientos.append({

            "fecha": pago.fecha,

            "tipo": "Ingreso",

            "categoria": "Pago",

            "concepto": (
                pago.concepto
                or "Pago registrado"
            ),

            "metodo": pago.get_metodo_display(),

            "entrada": pago.monto,

            "salida": None,

            "color": "verde",
        })

    # ==========================================
    # GASTOS
    # ==========================================

    gastos = Gasto.objects.filter(
        fecha__month=mes_actual,
        fecha__year=anio_actual
    )

    for gasto in gastos:

        movimientos.append({

            "fecha": gasto.fecha,

            "tipo": "Egreso",

            "categoria": (
                gasto.get_categoria_display()
            ),

            "concepto": gasto.concepto,

            "metodo": (
                gasto.get_metodo_display()
            ),

            "entrada": None,

            "salida": gasto.monto,

            "color": "rojo",
        })

    # ==========================================
    # MOVIMIENTOS MANUALES
    # ==========================================

    movs = MovimientoCaja.objects.filter(
        fecha__month=mes_actual,
        fecha__year=anio_actual
    )

    for mov in movs:

        movimientos.append({

            "fecha": mov.fecha,

            "tipo": (
                "Ingreso"
                if mov.tipo == "entrada"
                else "Egreso"
            ),

            "categoria": (
                mov.categoria
                or "Movimiento"
            ),

            "concepto": mov.concepto,

            "metodo": "Caja",

            "entrada": (
                mov.monto
                if mov.tipo == "entrada"
                else None
            ),

            "salida": (
                mov.monto
                if mov.tipo == "salida"
                else None
            ),

            "color": (
                "verde"
                if mov.tipo == "entrada"
                else "rojo"
            ),
        })

    # ==========================================
    # ORDENAR
    # ==========================================

    movimientos.sort(
        key=lambda x: x["fecha"],
        reverse=True
    )

    # ==========================================
    # TOTALES
    # ==========================================

    total_ingresos = Decimal("0.00")

    total_egresos = Decimal("0.00")

    for mov in movimientos:

        if mov["entrada"]:

            total_ingresos += mov["entrada"]

        if mov["salida"]:

            total_egresos += mov["salida"]

    balance = (
        total_ingresos
        - total_egresos
    )

    # ==========================================
    # NOMBRES MESES
    # ==========================================

    meses_es = [
        "",
        "Enero",
        "Febrero",
        "Marzo",
        "Abril",
        "Mayo",
        "Junio",
        "Julio",
        "Agosto",
        "Septiembre",
        "Octubre",
        "Noviembre",
        "Diciembre",
    ]

    mes_nombre = (
        f"{meses_es[mes_actual]} {anio_actual}"
    )

    anios = list(
        range(
            hoy.year - 5,
            hoy.year + 1
        )
    )

    return render(

        request,

        "caja/movimientos_financieros.html",

        {

            "movimientos": movimientos,

            "total_ingresos": total_ingresos,

            "total_egresos": total_egresos,

            "balance": balance,

            "mes_actual": mes_nombre,

            "mes_seleccionado": mes_actual,

            "anio_seleccionado": anio_actual,

            "meses": meses_es,

            "anios": anios,
        }
    )


def validar_pin(request):

    siguiente = request.GET.get("next", "/")

    if request.method == "POST":
        pin = request.POST.get("pin")

        if pin == settings.ADMIN_PIN:
            request.session["pin_ok"] = siguiente
            return redirect(siguiente)

        messages.error(request, "PIN incorrecto")

    return render(
        request,
        "caja/validar_pin.html",
        {
            "next": siguiente
        }
    )


