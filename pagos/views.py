from django.shortcuts import render, redirect
from .models import Pago
from django.core.paginator import Paginator
from django.db.models import Sum
from collections import OrderedDict
from caja.models import CashSession
from pagos.models import Pago

from itertools import groupby
from django.utils.timezone import localtime

from collections import defaultdict
import calendar

from django.utils.translation import gettext as _

from django.http import JsonResponse

from decimal import Decimal
from .models import (
    Gasto,
    CompraProveedor,
    PagoCompraProveedor
)



def nuevo_pago(request):
    if request.method == "POST":
        caja = CashSession.obtener_caja_del_dia()

        monto = request.POST.get("monto")
        concepto = request.POST.get("concepto", "").strip()
        metodo = request.POST.get("metodo")
        next_url = request.POST.get("next", "").strip()

        appointment_id = request.POST.get("appointment_id")
        patient_id = request.POST.get("patient_id")

        try:
            appointment_id = int(appointment_id) if appointment_id else None
        except:
            appointment_id = None

        try:
            patient_id = int(patient_id) if patient_id else None
        except:
            patient_id = None

        paciente = request.POST.get("paciente", "").strip()

        Pago.objects.create(
            monto=monto,
            paciente=paciente,
            concepto=concepto,
            metodo=metodo,
            caja=caja,
            appointment_id=appointment_id,
            patient_id=patient_id,
        )

        if next_url:
            return redirect(next_url)

        return redirect("caja:tablero")

    # 🔥 SIEMPRE RETORNAR ALGO EN GET
    initial = {
        "monto": request.GET.get("monto", ""),
        "paciente": request.GET.get("paciente", ""),
        "concepto": request.GET.get("concepto", ""),
        "metodo": request.GET.get("metodo", ""),
        "ci": request.GET.get("ci", ""),
        "next": request.GET.get("next", ""),
        "appointment_id": request.GET.get("appointment_id", ""),
        "patient_id": request.GET.get("patient_id", ""),
        "fecha_cita": request.GET.get("fecha_cita", ""),
    }

    return render(request, "pagos/nuevo.html", {
        "metodos": Pago.METODOS,
        "initial": initial,
    })


def historial(request):
    pagos = Pago.objects.order_by('-fecha')

    meses_es = [
        "", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
        "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
    ]

    pagos_por_mes = OrderedDict()

    for pago in pagos:
        mes_nombre = f"{meses_es[pago.fecha.month]} {pago.fecha.year}"

        if mes_nombre not in pagos_por_mes:
            pagos_por_mes[mes_nombre] = []

        pagos_por_mes[mes_nombre].append(pago)

    return render(request, "pagos/historial.html", {
        "pagos_por_mes": pagos_por_mes
    })



def _es_sena(concepto):
    concepto_texto = (concepto or "").strip().lower()
    return (
        "seña" in concepto_texto
        or "sena" in concepto_texto
        or "adelanto" in concepto_texto
        or "entrega" in concepto_texto
    )


def _pago_to_dict(pago):
    return {
        "id": pago.id,
        "paciente": pago.paciente,
        "monto": str(pago.monto),
        "metodo": pago.get_metodo_display(),
        "concepto": pago.concepto or "",
        "fecha": localtime(pago.fecha).strftime("%d/%m/%Y %H:%M"),
        "appointment_id": pago.appointment_id,
        "patient_id": pago.patient_id,
        "tipo_pago": "sena" if _es_sena(pago.concepto) else "pagado",
    }


def api_pagos_por_paciente(request):
    paciente = request.GET.get("paciente", "").strip()
    patient_id = request.GET.get("patient_id", "").strip()

    pagos_qs = Pago.objects.all()

    if patient_id:
        try:
            pagos_qs = pagos_qs.filter(patient_id=int(patient_id))
        except (TypeError, ValueError):
            return JsonResponse({
                "ok": False,
                "error": "patient_id inválido."
            }, status=400)
    elif paciente:
        pagos_qs = pagos_qs.filter(paciente__iexact=paciente)
    else:
        return JsonResponse({
            "ok": False,
            "error": "Falta el parámetro patient_id o paciente."
        }, status=400)

    pagos = pagos_qs.order_by("-fecha")
    total_pagado = sum((pago.monto or 0) for pago in pagos)
    data = [_pago_to_dict(pago) for pago in pagos[:50]]
    tiene_sena = any(_es_sena(pago.concepto) for pago in pagos)

    return JsonResponse({
        "ok": True,
        "paciente": paciente,
        "patient_id": patient_id or None,
        "total": pagos.count(),
        "total_pagado": str(total_pagado),
        "tipo_pago": "sena" if tiene_sena else "pagado",
        "pagos": data,
    })


def api_resumen_pacientes(request):
    """
    API rápida para Sonrisar Pro.
    Recibe: ?patient_ids=1,2,3
    Devuelve el total pagado por cada paciente en una sola consulta.
    """
    patient_ids_raw = request.GET.get("patient_ids", "").strip()

    if not patient_ids_raw:
        return JsonResponse({
            "ok": False,
            "error": "Falta el parámetro patient_ids."
        }, status=400)

    patient_ids = []

    for item in patient_ids_raw.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            patient_id = int(item)
        except (TypeError, ValueError):
            continue
        if patient_id not in patient_ids:
            patient_ids.append(patient_id)

    if not patient_ids:
        return JsonResponse({
            "ok": False,
            "error": "No se recibieron patient_ids válidos."
        }, status=400)

    pagos = Pago.objects.filter(patient_id__in=patient_ids)

    resumen = {
        patient_id: {
            "patient_id": patient_id,
            "total_pagado": "0",
            "cantidad_pagos": 0,
            "tipo_pago": "pagado",
        }
        for patient_id in patient_ids
    }

    acumulados = {}

    for pago in pagos:
        patient_id = pago.patient_id
        if patient_id not in resumen:
            continue

        if patient_id not in acumulados:
            acumulados[patient_id] = {
                "total_pagado": 0,
                "cantidad_pagos": 0,
                "tiene_sena": False,
            }

        acumulados[patient_id]["total_pagado"] += pago.monto or 0
        acumulados[patient_id]["cantidad_pagos"] += 1

        if _es_sena(pago.concepto):
            acumulados[patient_id]["tiene_sena"] = True

    for patient_id, datos in acumulados.items():
        resumen[patient_id]["total_pagado"] = str(datos["total_pagado"])
        resumen[patient_id]["cantidad_pagos"] = datos["cantidad_pagos"]
        resumen[patient_id]["tipo_pago"] = "sena" if datos["tiene_sena"] else "pagado"

    return JsonResponse({
        "ok": True,
        "pacientes": list(resumen.values()),
    })


def api_pago_por_cita(request):
    appointment_id = request.GET.get("appointment_id", "").strip()
    patient_id = request.GET.get("patient_id", "").strip()

    if not appointment_id:
        return JsonResponse({
            "ok": False,
            "error": "Falta el parámetro appointment_id."
        }, status=400)

    pagos = Pago.objects.filter(appointment_id=appointment_id)

    if patient_id:
        try:
            pagos = pagos.filter(patient_id=int(patient_id))
        except (TypeError, ValueError):
            pass

    pagos = pagos.order_by("-fecha")

    data = []
    total_pagado = 0
    tipo_pago = "pagado"

    for pago in pagos:
        total_pagado += pago.monto or 0

        if _es_sena(pago.concepto):
            tipo_pago = "sena"

        data.append(_pago_to_dict(pago))

    return JsonResponse({
        "ok": True,
        "appointment_id": appointment_id,
        "patient_id": patient_id or None,
        "total": len(data),
        "total_pagado": str(total_pagado),
        "tipo_pago": tipo_pago,
        "pagos": data,
    })


def nuevo_gasto(request):

    caja = CashSession.obtener_caja_del_dia()

    if request.method == "POST":

        afecta_caja = (
            request.POST.get("afecta_caja") == "on"
        )

        # ==========================================
        # SI AFECTA CAJA Y ESTÁ CERRADA → BLOQUEAR
        # ==========================================

        if (
            afecta_caja
            and caja.estado == CashSession.Status.CERRADA
        ):
            return redirect("caja:tablero")

        # ==========================================
        # SOLO ASIGNAR CAJA SI AFECTA
        # ==========================================

        caja_asignada = (
            caja if afecta_caja else None
        )

        Gasto.objects.create(
            proveedor=request.POST.get("proveedor"),
            categoria=request.POST.get("categoria"),
            concepto=request.POST.get("concepto"),
            monto=request.POST.get("monto"),
            metodo=request.POST.get("metodo"),
            afecta_caja=afecta_caja,
            caja=caja_asignada,
        )

        return redirect("caja:tablero")

    return render(request, "pagos/nuevo_gasto.html", {
        "metodos": Gasto.METODOS,
        "categorias": Gasto.CATEGORIAS,
    })


def lista_gastos(request):
    gastos = Gasto.objects.order_by("-fecha")

    total = sum(g.monto for g in gastos)

    return render(request, "pagos/lista_gastos.html", {
        "gastos": gastos,
        "total": total,
    })



# =====================================================
# COMPRAS A PROVEEDORES
# =====================================================

def compras_proveedores(request):

    query = request.GET.get("q", "").strip()

    compras = (
        CompraProveedor.objects
        .all()
        .order_by("-fecha", "-id")
    )

    if query:
        compras = compras.filter(
            proveedor__icontains=query
        )

    total_adeudado = Decimal("0.00")

    pendientes = 0
    parciales = 0
    pagadas = 0

    for compra in compras:

        saldo = compra.saldo_pendiente()

        total_adeudado += saldo

        if compra.estado() == "Pendiente":
            pendientes += 1

        elif compra.estado() == "Parcial":
            parciales += 1

        else:
            pagadas += 1

    return render(
        request,
        "pagos/compras_proveedores.html",
        {
            "compras": compras,
            "total_adeudado": total_adeudado,
            "pendientes": pendientes,
            "parciales": parciales,
            "pagadas": pagadas,
            "query": query,
        }
    )


def compra_proveedor_nueva(request):

    if request.method == "POST":

        fecha_vencimiento = request.POST.get(
            "fecha_vencimiento",
            ""
        )

        CompraProveedor.objects.create(
            proveedor=request.POST.get("proveedor"),
            fecha=request.POST.get("fecha"),
            fecha_vencimiento=(
                fecha_vencimiento
                if fecha_vencimiento
                else None
            ),
            numero_boleta=request.POST.get(
                "numero_boleta",
                ""
            ),
            concepto=request.POST.get(
                "concepto",
                ""
            ),
            monto_total=Decimal(
                request.POST.get(
                    "monto_total",
                    "0"
                )
            ),
            observaciones=request.POST.get(
                "observaciones",
                ""
            ),
        )

        return redirect(
            "pagos:compras_proveedores"
        )

    return render(
        request,
        "pagos/compra_proveedor_nueva.html"
    )


def compra_proveedor_detalle(
    request,
    compra_id
):

    compra = CompraProveedor.objects.get(
        id=compra_id
    )

    pagos = (
        compra.pagos
        .all()
        .order_by("-fecha")
    )

    return render(
        request,
        "pagos/compra_proveedor_detalle.html",
        {
            "compra": compra,
            "pagos": pagos,
        }
    )


def compra_proveedor_pago(
    request,
    compra_id
):

    compra = CompraProveedor.objects.get(
        id=compra_id
    )

    if request.method == "POST":

        monto = Decimal(
            request.POST.get(
                "monto",
                "0"
            )
        )

        metodo = request.POST.get(
            "metodo"
        )

        afecta_caja = (
            request.POST.get(
                "afecta_caja"
            ) == "on"
        )

        gasto = None

        if afecta_caja:

            caja = (
                CashSession
                .obtener_caja_del_dia()
            )

            gasto = Gasto.objects.create(
                proveedor=compra.proveedor,
                categoria="insumos",
                concepto=f"Pago proveedor: {compra.proveedor}",
                monto=monto,
                metodo=metodo,
                afecta_caja=True,
                caja=caja,
            )

        PagoCompraProveedor.objects.create(
            compra=compra,
            monto=monto,
            metodo=metodo,
            afecta_caja=afecta_caja,
            gasto=gasto,
            observaciones=request.POST.get(
                "observaciones",
                ""
            ),
        )

        return redirect(
            "pagos:compra_proveedor_detalle",
            compra_id=compra.id
        )

    return render(
        request,
        "pagos/compra_proveedor_pago.html",
        {
            "compra": compra
        }
    )


def compra_proveedor_editar(
    request,
    compra_id
):

    compra = CompraProveedor.objects.get(
        id=compra_id
    )

    if request.method == "POST":

        fecha_vencimiento = request.POST.get(
            "fecha_vencimiento",
            ""
        )

        compra.proveedor = request.POST.get(
            "proveedor"
        )

        compra.fecha = request.POST.get(
            "fecha"
        )

        compra.fecha_vencimiento = (
            fecha_vencimiento
            if fecha_vencimiento
            else None
        )

        compra.numero_boleta = request.POST.get(
            "numero_boleta",
            ""
        )

        compra.concepto = request.POST.get(
            "concepto",
            ""
        )

        compra.monto_total = Decimal(
            request.POST.get(
                "monto_total",
                "0"
            )
        )

        compra.observaciones = request.POST.get(
            "observaciones",
            ""
        )

        compra.save()

        return redirect(
            "pagos:compra_proveedor_detalle",
            compra_id=compra.id
        )

    return render(
        request,
        "pagos/compra_proveedor_editar.html",
        {
            "compra": compra
        }
    )


def compra_proveedor_eliminar(
    request,
    compra_id
):

    compra = CompraProveedor.objects.get(
        id=compra_id
    )

    if compra.pagos.exists():

        return redirect(
            "pagos:compra_proveedor_detalle",
            compra_id=compra.id
        )

    compra.delete()

    return redirect(
        "pagos:compras_proveedores"
    )


def pago_compra_eliminar(
    request,
    pago_id
):

    pago = PagoCompraProveedor.objects.get(
        id=pago_id
    )

    compra_id = pago.compra.id

    if pago.gasto:
        pago.gasto.delete()

    pago.delete()

    return redirect(
        "pagos:compra_proveedor_detalle",
        compra_id=compra_id
    )



