from django.shortcuts import render, redirect, get_object_or_404
from .models import Pago
from django.core.paginator import Paginator
from django.db.models import Sum, Q
from django.db import transaction
from collections import OrderedDict
from caja.models import CashSession
from pagos.models import Pago

from itertools import groupby
from django.utils.timezone import localtime

from collections import defaultdict
import calendar

from django.utils.translation import gettext as _

from django.http import JsonResponse
from django.contrib import messages

from decimal import Decimal
from urllib.parse import quote
from .models import (
    Gasto,
    DevolucionPaciente,
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

        protesis_id = request.POST.get("protesis_id")

        try:
            appointment_id = int(appointment_id) if appointment_id else None
        except:
            appointment_id = None

        try:
            patient_id = int(patient_id) if patient_id else None
        except:
            patient_id = None

        try:
            protesis_id = int(protesis_id) if protesis_id else None
        except:
            protesis_id = None

        paciente = request.POST.get("paciente", "").strip()

        Pago.objects.create(
            monto=monto,
            paciente=paciente,
            concepto=concepto,
            metodo=metodo,
            caja=caja,
            appointment_id=appointment_id,
            patient_id=patient_id,
            protesis_id=protesis_id,
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
        "protesis_id": request.GET.get("protesis_id", ""),
        "fecha_cita": request.GET.get("fecha_cita", ""),
    }

    return render(request, "pagos/nuevo.html", {
        "metodos": Pago.METODOS,
        "initial": initial,
    })


def recibo_pago(request, pago_id):
    pago = get_object_or_404(Pago, id=pago_id)
    ci = request.GET.get("ci", "").strip()

    return render(request, "pagos/recibo.html", {
        "pago": pago,
        "ci": ci,
    })


def historial(request):

    permitido = request.session.get("pin_ok")
    full_path = request.get_full_path()

    if permitido != full_path:
        return redirect(
            f"/caja/validar-pin/?next={quote(full_path)}"
        )

    request.session.pop("pin_ok", None)

    pagos_qs = (
        Pago.objects
        .only("id", "fecha", "monto", "metodo", "paciente", "concepto")
        .order_by("-fecha", "-id")
    )

    paginator = Paginator(pagos_qs, 120)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    meses_es = [
        "", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
        "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
    ]

    pagos_por_mes = OrderedDict()

    for pago in page_obj.object_list:
        fecha_local = localtime(pago.fecha)
        mes_nombre = f"{meses_es[fecha_local.month]} {fecha_local.year}"

        if mes_nombre not in pagos_por_mes:
            pagos_por_mes[mes_nombre] = []

        pagos_por_mes[mes_nombre].append(pago)

    return render(request, "pagos/historial.html", {
        "pagos_por_mes": pagos_por_mes,
        "page_obj": page_obj,
        "total_pagos": paginator.count,
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


def _devolucion_to_dict(devolucion):
    return {
        "id": devolucion.id,
        "paciente": devolucion.paciente,
        "monto": str(devolucion.monto),
        "metodo": devolucion.get_metodo_display(),
        "concepto": devolucion.concepto or "",
        "fecha": localtime(devolucion.fecha).strftime("%d/%m/%Y %H:%M"),
        "appointment_id": devolucion.appointment_id,
        "patient_id": devolucion.patient_id,
        "protesis_id": devolucion.protesis_id,
        "pago_original_id": devolucion.pago_original_id,
        "tipo_movimiento": "devolucion",
    }


def _to_int_or_none(value):
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def api_pagos_por_paciente(request):
    paciente = request.GET.get("paciente", "").strip()
    patient_id = request.GET.get("patient_id", "").strip()

    pagos_qs = Pago.objects.all()
    devoluciones_qs = DevolucionPaciente.objects.all()

    if patient_id:
        try:
            patient_id_int = int(patient_id)
        except (TypeError, ValueError):
            return JsonResponse({
                "ok": False,
                "error": "patient_id inválido."
            }, status=400)

        pagos_qs = pagos_qs.filter(patient_id=patient_id_int)
        devoluciones_qs = devoluciones_qs.filter(patient_id=patient_id_int)
    elif paciente:
        pagos_qs = pagos_qs.filter(paciente__iexact=paciente)
        devoluciones_qs = devoluciones_qs.filter(paciente__iexact=paciente)
    else:
        return JsonResponse({
            "ok": False,
            "error": "Falta el parámetro patient_id o paciente."
        }, status=400)

    pagos = pagos_qs.order_by("-fecha")
    devoluciones = devoluciones_qs.order_by("-fecha")

    total_pagado_bruto = sum((pago.monto or 0) for pago in pagos)
    total_devuelto = sum((dev.monto or 0) for dev in devoluciones)
    total_pagado = total_pagado_bruto - total_devuelto

    data = [_pago_to_dict(pago) for pago in pagos[:50]]
    devoluciones_data = [_devolucion_to_dict(dev) for dev in devoluciones[:50]]
    tiene_sena = any(_es_sena(pago.concepto) for pago in pagos)

    return JsonResponse({
        "ok": True,
        "paciente": paciente,
        "patient_id": patient_id or None,
        "total": pagos.count(),
        "cantidad_devoluciones": devoluciones.count(),
        "total_pagado_bruto": str(total_pagado_bruto),
        "total_devuelto": str(total_devuelto),
        "total_pagado": str(total_pagado),
        "tipo_pago": "sena" if tiene_sena else "pagado",
        "pagos": data,
        "devoluciones": devoluciones_data,
    })


def api_resumen_pacientes(request):
    """
    API rápida para Sonrisar Pro.
    Devuelve el total neto pagado por cada paciente: pagos - devoluciones.
    """
    patient_ids_raw = request.GET.get("patient_ids", "").strip()

    if not patient_ids_raw:
        return JsonResponse({
            "ok": False,
            "error": "Falta el parámetro patient_ids."
        }, status=400)

    patient_ids = []
    for item in patient_ids_raw.split(","):
        patient_id = _to_int_or_none(item.strip())
        if patient_id is not None and patient_id not in patient_ids:
            patient_ids.append(patient_id)

    if not patient_ids:
        return JsonResponse({
            "ok": False,
            "error": "No se recibieron patient_ids válidos."
        }, status=400)

    pagos = Pago.objects.filter(patient_id__in=patient_ids)
    devoluciones = DevolucionPaciente.objects.filter(patient_id__in=patient_ids)

    resumen = {
        patient_id: {
            "patient_id": patient_id,
            "total_pagado": "0",
            "total_pagado_bruto": "0",
            "total_devuelto": "0",
            "cantidad_pagos": 0,
            "cantidad_devoluciones": 0,
            "tipo_pago": "pagado",
        }
        for patient_id in patient_ids
    }

    for pago in pagos:
        datos = resumen.get(pago.patient_id)
        if not datos:
            continue
        bruto = Decimal(datos["total_pagado_bruto"]) + (pago.monto or Decimal("0.00"))
        datos["total_pagado_bruto"] = str(bruto)
        datos["cantidad_pagos"] += 1
        if _es_sena(pago.concepto):
            datos["tipo_pago"] = "sena"

    for devolucion in devoluciones:
        datos = resumen.get(devolucion.patient_id)
        if not datos:
            continue
        devuelto = Decimal(datos["total_devuelto"]) + (devolucion.monto or Decimal("0.00"))
        datos["total_devuelto"] = str(devuelto)
        datos["cantidad_devoluciones"] += 1

    for datos in resumen.values():
        neto = Decimal(datos["total_pagado_bruto"]) - Decimal(datos["total_devuelto"])
        datos["total_pagado"] = str(neto)

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
    devoluciones = DevolucionPaciente.objects.filter(appointment_id=appointment_id)

    if patient_id:
        patient_id_int = _to_int_or_none(patient_id)
        if patient_id_int is not None:
            pagos = pagos.filter(patient_id=patient_id_int)
            devoluciones = devoluciones.filter(patient_id=patient_id_int)

    pagos = pagos.order_by("-fecha")
    devoluciones = devoluciones.order_by("-fecha")

    data = []
    total_pagado_bruto = Decimal("0.00")
    total_devuelto = Decimal("0.00")
    tipo_pago = "pagado"

    for pago in pagos:
        total_pagado_bruto += pago.monto or Decimal("0.00")
        if _es_sena(pago.concepto):
            tipo_pago = "sena"
        data.append(_pago_to_dict(pago))

    devoluciones_data = []
    for devolucion in devoluciones:
        total_devuelto += devolucion.monto or Decimal("0.00")
        devoluciones_data.append(_devolucion_to_dict(devolucion))

    return JsonResponse({
        "ok": True,
        "appointment_id": appointment_id,
        "patient_id": patient_id or None,
        "total": len(data),
        "cantidad_devoluciones": len(devoluciones_data),
        "total_pagado_bruto": str(total_pagado_bruto),
        "total_devuelto": str(total_devuelto),
        "total_pagado": str(total_pagado_bruto - total_devuelto),
        "tipo_pago": tipo_pago,
        "pagos": data,
        "devoluciones": devoluciones_data,
    })


def api_resumen_citas(request):
    appointment_ids_raw = request.GET.get("appointment_ids", "").strip()

    if not appointment_ids_raw:
        return JsonResponse({
            "ok": False,
            "error": "Falta el parámetro appointment_ids."
        }, status=400)

    appointment_ids = []
    for item in appointment_ids_raw.split(","):
        appointment_id = _to_int_or_none(item.strip())
        if appointment_id is not None and appointment_id not in appointment_ids:
            appointment_ids.append(appointment_id)

    if not appointment_ids:
        return JsonResponse({
            "ok": False,
            "error": "No se recibieron appointment_ids válidos."
        }, status=400)

    pagos = Pago.objects.filter(appointment_id__in=appointment_ids).order_by("-fecha")
    devoluciones = DevolucionPaciente.objects.filter(appointment_id__in=appointment_ids).order_by("-fecha")

    resumen = {
        appointment_id: {
            "appointment_id": appointment_id,
            "total_pagado": "0",
            "total_pagado_bruto": "0",
            "total_devuelto": "0",
            "cantidad_pagos": 0,
            "cantidad_devoluciones": 0,
            "tipo_pago": "pagado",
            "pagos": [],
            "devoluciones": [],
        }
        for appointment_id in appointment_ids
    }

    for pago in pagos:
        datos = resumen.get(pago.appointment_id)
        if not datos:
            continue
        bruto = Decimal(datos["total_pagado_bruto"]) + (pago.monto or Decimal("0.00"))
        datos["total_pagado_bruto"] = str(bruto)
        datos["cantidad_pagos"] += 1
        datos["pagos"].append(_pago_to_dict(pago))
        if _es_sena(pago.concepto):
            datos["tipo_pago"] = "sena"

    for devolucion in devoluciones:
        datos = resumen.get(devolucion.appointment_id)
        if not datos:
            continue
        devuelto = Decimal(datos["total_devuelto"]) + (devolucion.monto or Decimal("0.00"))
        datos["total_devuelto"] = str(devuelto)
        datos["cantidad_devoluciones"] += 1
        datos["devoluciones"].append(_devolucion_to_dict(devolucion))

    for datos in resumen.values():
        datos["total_pagado"] = str(
            Decimal(datos["total_pagado_bruto"]) - Decimal(datos["total_devuelto"])
        )

    return JsonResponse({
        "ok": True,
        "citas": list(resumen.values()),
    })


def api_pago_por_protesis(request):
    protesis_id = request.GET.get("protesis_id", "").strip()

    if not protesis_id:
        return JsonResponse({
            "ok": False,
            "error": "Falta el parámetro protesis_id."
        }, status=400)

    pagos = Pago.objects.filter(protesis_id=protesis_id).order_by("-fecha")
    devoluciones = DevolucionPaciente.objects.filter(protesis_id=protesis_id).order_by("-fecha")

    total_pagado_bruto = Decimal("0.00")
    total_devuelto = Decimal("0.00")
    data = []
    devoluciones_data = []

    for pago in pagos:
        total_pagado_bruto += pago.monto or Decimal("0.00")
        data.append(_pago_to_dict(pago))

    for devolucion in devoluciones:
        total_devuelto += devolucion.monto or Decimal("0.00")
        devoluciones_data.append(_devolucion_to_dict(devolucion))

    return JsonResponse({
        "ok": True,
        "protesis_id": protesis_id,
        "total": len(data),
        "cantidad_devoluciones": len(devoluciones_data),
        "total_pagado_bruto": str(total_pagado_bruto),
        "total_devuelto": str(total_devuelto),
        "total_pagado": str(total_pagado_bruto - total_devuelto),
        "pagos": data,
        "devoluciones": devoluciones_data,
    })


def nueva_devolucion(request):
    caja = CashSession.obtener_caja_del_dia()

    if request.method == "POST":
        afecta_caja = request.POST.get("afecta_caja") == "on"

        if afecta_caja and caja.estado == CashSession.Status.CERRADA:
            messages.error(
                request,
                "La caja del día está cerrada. Puedes registrar la devolución, pero no descontarla de la caja actual."
            )
            return redirect("pagos:nueva_devolucion")

        pago_original_id = _to_int_or_none(request.POST.get("pago_original_id"))
        pago_original = (
            Pago.objects.filter(id=pago_original_id).first()
            if pago_original_id is not None
            else None
        )

        paciente = request.POST.get("paciente", "").strip()
        patient_id = _to_int_or_none(request.POST.get("patient_id"))
        appointment_id = _to_int_or_none(request.POST.get("appointment_id"))
        protesis_id = _to_int_or_none(request.POST.get("protesis_id"))
        metodo = request.POST.get("metodo", "").strip()
        concepto = request.POST.get("concepto", "").strip()
        next_url = request.POST.get("next", "").strip()

        if pago_original:
            paciente = pago_original.paciente or paciente
            patient_id = pago_original.patient_id or patient_id
            appointment_id = pago_original.appointment_id or appointment_id
            protesis_id = pago_original.protesis_id or protesis_id

        monto_texto = request.POST.get("monto", "").strip().replace(",", ".")

        try:
            monto = Decimal(monto_texto)
            if monto <= 0:
                raise ValueError
        except (ValueError, ArithmeticError):
            monto = None

        metodos_validos = {valor for valor, _ in DevolucionPaciente.METODOS}

        if not pago_original:
            messages.error(request, "Selecciona el pago original que corresponde a la devolución.")
        elif not paciente:
            messages.error(request, "Debes indicar el paciente de la devolución.")
        elif monto is None:
            messages.error(request, "El monto de la devolución debe ser mayor a cero.")
        elif metodo not in metodos_validos:
            messages.error(request, "Selecciona un método de devolución válido.")
        else:
            ya_devuelto = (
                DevolucionPaciente.objects
                .filter(pago_original=pago_original)
                .aggregate(total=Sum("monto"))["total"]
                or Decimal("0.00")
            )
            disponible = (pago_original.monto or Decimal("0.00")) - ya_devuelto

            if disponible <= 0:
                messages.error(
                    request,
                    "Ese pago ya fue devuelto completamente y no tiene saldo disponible para otra devolución."
                )
                monto = None
            elif monto > disponible:
                messages.error(
                    request,
                    f"No puedes devolver ${monto:.2f}. De ese pago quedan ${disponible:.2f} disponibles para devolución."
                )
                monto = None

            if monto is not None:
                concepto_final = concepto or "Devolución de pago a paciente"

                with transaction.atomic():
                    caja_asignada = caja if afecta_caja else None

                    gasto = Gasto.objects.create(
                        proveedor=paciente,
                        categoria="devolucion_paciente",
                        concepto=f"Devolución a {paciente}: {concepto_final}",
                        monto=monto,
                        metodo=metodo,
                        afecta_caja=afecta_caja,
                        caja=caja_asignada,
                    )

                    DevolucionPaciente.objects.create(
                        pago_original=pago_original,
                        gasto=gasto,
                        paciente=paciente,
                        patient_id=patient_id,
                        appointment_id=appointment_id,
                        protesis_id=protesis_id,
                        monto=monto,
                        metodo=metodo,
                        concepto=concepto_final,
                    )

                detalle_caja = (
                    " Se descontó de la caja del día."
                    if afecta_caja
                    else " No afectó la caja del día."
                )

                messages.success(
                    request,
                    f"Devolución de ${monto:.2f} registrada para {paciente}.{detalle_caja}"
                )

                if next_url:
                    return redirect(next_url)
                return redirect("caja:tablero")

    if request.method == "POST":
        initial = {
            "paciente": request.POST.get("paciente", ""),
            "patient_id": request.POST.get("patient_id", ""),
            "appointment_id": request.POST.get("appointment_id", ""),
            "protesis_id": request.POST.get("protesis_id", ""),
            "monto": request.POST.get("monto", ""),
            "concepto": request.POST.get("concepto", ""),
            "pago_original_id": request.POST.get("pago_original_id", ""),
            "next": request.POST.get("next", ""),
            "metodo": request.POST.get("metodo", ""),
            "afecta_caja": request.POST.get("afecta_caja") == "on",
        }
        busqueda_pago = request.POST.get("busqueda_pago", "").strip()
    else:
        initial = {
            "paciente": request.GET.get("paciente", ""),
            "patient_id": request.GET.get("patient_id", ""),
            "appointment_id": request.GET.get("appointment_id", ""),
            "protesis_id": request.GET.get("protesis_id", ""),
            "monto": request.GET.get("monto", ""),
            "concepto": request.GET.get("concepto", ""),
            "pago_original_id": request.GET.get("pago_id", ""),
            "next": request.GET.get("next", ""),
            "metodo": "",
            "afecta_caja": False,
        }
        busqueda_pago = request.GET.get("buscar_pago", "").strip()

    pagos_qs = (
        Pago.objects
        .annotate(total_devuelto_calc=Sum("devoluciones__monto"))
        .only(
            "id", "fecha", "paciente", "monto", "concepto",
            "patient_id", "appointment_id", "protesis_id"
        )
        .order_by("-fecha", "-id")
    )

    if busqueda_pago:
        filtro = (
            Q(paciente__icontains=busqueda_pago)
            | Q(concepto__icontains=busqueda_pago)
        )

        # También permite buscar un pago puntual escribiendo su ID como #302.
        texto_id = busqueda_pago.strip()
        if texto_id.startswith("#"):
            try:
                filtro |= Q(id=int(texto_id[1:].strip()))
            except (TypeError, ValueError):
                pass

        texto_monto = busqueda_pago.replace("$", "").replace(".", "").replace(",", ".").strip()
        try:
            monto_buscado = Decimal(texto_monto)
            filtro |= Q(monto=monto_buscado)
        except (ValueError, ArithmeticError):
            pass

        pagos_qs = pagos_qs.filter(filtro)

    # Con búsqueda mostramos más resultados del historial completo. Sin búsqueda,
    # solo los últimos para mantener la pantalla liviana.
    limite = 150 if busqueda_pago else 80
    pagos_encontrados = list(pagos_qs[:limite])

    pago_inicial_id = _to_int_or_none(initial.get("pago_original_id"))
    if pago_inicial_id and not any(p.id == pago_inicial_id for p in pagos_encontrados):
        pago_inicial = (
            Pago.objects
            .filter(id=pago_inicial_id)
            .annotate(total_devuelto_calc=Sum("devoluciones__monto"))
            .first()
        )
        if pago_inicial:
            pagos_encontrados.insert(0, pago_inicial)

    for pago in pagos_encontrados:
        pago.total_devuelto_mostrado = pago.total_devuelto_calc or Decimal("0.00")
        pago.disponible_devolver = max(
            (pago.monto or Decimal("0.00")) - pago.total_devuelto_mostrado,
            Decimal("0.00")
        )

    return render(request, "pagos/nueva_devolucion.html", {
        "caja": caja,
        "metodos": DevolucionPaciente.METODOS,
        "pagos_recientes": pagos_encontrados,
        "initial": initial,
        "busqueda_pago": busqueda_pago,
        "cantidad_resultados": len(pagos_encontrados),
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



