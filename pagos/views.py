from django.shortcuts import render, redirect, get_object_or_404
from .models import Pago
from django.core.paginator import Paginator
from django.db.models import Sum
from collections import OrderedDict
import json
from caja.models import CashSession
from pagos.models import Pago

from itertools import groupby
from django.utils.timezone import localtime

from collections import defaultdict
import calendar

from django.utils.translation import gettext as _

from django.http import JsonResponse, Http404, HttpResponseNotAllowed, HttpResponse
from django.conf import settings
from django.contrib import messages

from decimal import Decimal
from urllib.parse import quote
from .models import (
    Gasto,
    CompraProveedor,
    PagoCompraProveedor
)

from .facture_service import probar_conexion, emitir_pago_sandbox, emitir_nota_credito_pago_sandbox, obtener_pdf_cfe_por_folio, FactureError



def nuevo_pago(request):
    if request.method == "POST":
        caja = CashSession.obtener_caja_del_dia()

        monto = request.POST.get("monto")
        concepto = request.POST.get("concepto", "").strip()
        metodo_form = request.POST.get("metodo")

        # En la interfaz distinguimos Débito y Crédito, pero internamente
        # seguimos guardando metodo="tarjeta" para mantener compatibilidad
        # con caja, reportes y pagos históricos.
        tipo_tarjeta = ""
        if metodo_form == Pago.TARJETA_DEBITO:
            metodo = Pago.TARJETA
            tipo_tarjeta = Pago.TARJETA_DEBITO
        elif metodo_form == Pago.TARJETA_CREDITO:
            metodo = Pago.TARJETA
            tipo_tarjeta = Pago.TARJETA_CREDITO
        else:
            metodo = metodo_form

        solicitar_cfe = request.POST.get("solicitar_cfe") == "on"
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
            tipo_tarjeta=tipo_tarjeta,
            caja=caja,
            appointment_id=appointment_id,
            patient_id=patient_id,
            protesis_id=protesis_id,
            cfe_solicitado=solicitar_cfe,
            cfe_estado=(
                Pago.CFE_PENDIENTE
                if solicitar_cfe
                else Pago.CFE_NO_SOLICITADO
            ),
            tasa_iva_cfe=Decimal("10.00"),
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
        .only(
            "id", "fecha", "monto", "metodo", "paciente", "concepto",
            "cfe_solicitado", "cfe_estado", "tasa_iva_cfe",
            "cfe_tipo", "cfe_serie", "cfe_numero", "cfe_error", "facture_cfe_id", "tipo_tarjeta", "cfe_xml_firmado", "nc_cfe_id", "nc_serie", "nc_numero", "nc_xml_firmado", "nc_error"
        )
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
        "metodo_detallado": pago.metodo_detallado,
        "tipo_tarjeta": pago.tipo_tarjeta or "",
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
    

def api_resumen_citas(request):
    appointment_ids_raw = request.GET.get("appointment_ids", "").strip()

    if not appointment_ids_raw:
        return JsonResponse({
            "ok": False,
            "error": "Falta el parámetro appointment_ids."
        }, status=400)

    appointment_ids = []

    for item in appointment_ids_raw.split(","):
        item = item.strip()
        if not item:
            continue

        try:
            appointment_id = int(item)
        except (TypeError, ValueError):
            continue

        if appointment_id not in appointment_ids:
            appointment_ids.append(appointment_id)

    if not appointment_ids:
        return JsonResponse({
            "ok": False,
            "error": "No se recibieron appointment_ids válidos."
        }, status=400)

    pagos = Pago.objects.filter(
        appointment_id__in=appointment_ids
    ).order_by("-fecha")

    resumen = {
        appointment_id: {
            "appointment_id": appointment_id,
            "total_pagado": "0",
            "cantidad_pagos": 0,
            "tipo_pago": "pagado",
            "pagos": [],
        }
        for appointment_id in appointment_ids
    }

    for pago in pagos:
        appointment_id = pago.appointment_id

        if appointment_id not in resumen:
            continue

        actual = Decimal(resumen[appointment_id]["total_pagado"])
        actual += pago.monto or Decimal("0.00")

        resumen[appointment_id]["total_pagado"] = str(actual)
        resumen[appointment_id]["cantidad_pagos"] += 1
        resumen[appointment_id]["pagos"].append(_pago_to_dict(pago))

        if _es_sena(pago.concepto):
            resumen[appointment_id]["tipo_pago"] = "sena"

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

    total_pagado = Decimal("0.00")
    data = []

    for pago in pagos:
        total_pagado += pago.monto or Decimal("0.00")
        data.append(_pago_to_dict(pago))

    return JsonResponse({
        "ok": True,
        "protesis_id": protesis_id,
        "total": len(data),
        "total_pagado": str(total_pagado),
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





# =====================================================
# FACTURE - PRUEBA DE CONEXIÓN SANDBOX
# =====================================================

def facture_test_conexion(request):
    """
    Diagnóstico local de autenticación con Facture.
    NO emite comprobantes.
    Disponible solo con DEBUG=True y FACTURE_MODO=sandbox.
    """
    if not settings.DEBUG or getattr(settings, "FACTURE_MODO", "") != "sandbox":
        raise Http404

    try:
        resultado = probar_conexion()
    except FactureError as exc:
        return JsonResponse({
            "ok": False,
            "mensaje": str(exc),
        }, status=500)

    status = 200 if resultado.get("ok") else 502

    return JsonResponse({
        "ok": resultado.get("ok", False),
        "mensaje": (
            "Conexión con Facture OK."
            if resultado.get("ok")
            else "Facture respondió, pero la autenticación/consulta falló."
        ),
        "http_status_facture": resultado.get("status"),
        "config": resultado.get("config", {}),
        "respuesta": resultado.get("data") if resultado.get("ok") else resultado.get("error"),
    }, status=status)


# =====================================================
# FACTURE - PRIMERA EMISIÓN DE PRUEBA (SANDBOX)
# =====================================================

def facture_emitir_pago_sandbox(request, pago_id):
    """
    Emite UN eTicket de prueba desde un pago Pendiente CFE.
    Solo POST, solo DEBUG, solo sandbox.
    Para esta primera prueba el medio enviado a Facture es Efectivo
    (idMedioPago=1), porque es el único ID confirmado en la guía oficial.
    """
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    if not settings.DEBUG or getattr(settings, "FACTURE_MODO", "") != "sandbox":
        raise Http404

    pago = get_object_or_404(Pago, id=pago_id)

    if not pago.cfe_solicitado:
        messages.error(request, "Este pago no está marcado para CFE.")
        return redirect("pagos:historial")

    if pago.cfe_estado == Pago.CFE_EMITIDO:
        messages.warning(request, "Este pago ya tiene un CFE emitido.")
        return redirect("pagos:historial")

    if pago.cfe_estado != Pago.CFE_PENDIENTE:
        messages.warning(
            request,
            f"El pago no está Pendiente CFE (estado actual: {pago.get_cfe_estado_display()})."
        )
        return redirect("pagos:historial")

    try:
        resultado = emitir_pago_sandbox(pago)
    except FactureError as exc:
        pago.cfe_estado = Pago.CFE_RECHAZADO
        pago.cfe_error = str(exc)
        pago.save(update_fields=["cfe_estado", "cfe_error"])
        messages.error(request, f"No se pudo emitir el CFE: {exc}")
        return redirect("pagos:historial")

    if not resultado.get("ok"):
        detalle = resultado.get("error", {})
        pago.cfe_estado = Pago.CFE_RECHAZADO
        pago.cfe_error = json.dumps(detalle, ensure_ascii=False)[:5000]
        pago.save(update_fields=["cfe_estado", "cfe_error"])
        messages.error(
            request,
            f"Facture rechazó la emisión (HTTP {resultado.get('status')})."
        )
        return redirect("pagos:historial")

    data = resultado.get("data") or {}

    # Contrato documentado por Facture:
    # _Id, CodRespuesta, MensajeRespuesta, TipoCfe, Serie, Nro, XmlFirmado.
    cod_respuesta = str(data.get("CodRespuesta", "")).strip()

    if cod_respuesta and cod_respuesta != "00":
        pago.cfe_estado = Pago.CFE_RECHAZADO
        pago.cfe_error = json.dumps(data, ensure_ascii=False)[:5000]
        pago.save(update_fields=["cfe_estado", "cfe_error"])
        messages.error(
            request,
            f"Facture respondió {cod_respuesta}: {data.get('MensajeRespuesta', 'Error')}"
        )
        return redirect("pagos:historial")

    pago.cfe_estado = Pago.CFE_EMITIDO
    pago.cfe_tipo = "eTicket"
    pago.cfe_serie = str(data.get("Serie") or "")
    pago.cfe_numero = str(data.get("Nro") or "")
    pago.facture_cfe_id = str(data.get("_Id") or data.get("IdComprobante") or "")
    pago.cfe_xml_firmado = str(data.get("XmlFirmado") or "")
    pago.cfe_error = ""
    pago.save(update_fields=[
        "cfe_estado",
        "cfe_tipo",
        "cfe_serie",
        "cfe_numero",
        "facture_cfe_id",
        "cfe_xml_firmado",
        "cfe_error",
    ])

    messages.success(
        request,
        f"CFE de prueba emitido: {pago.cfe_tipo} {pago.cfe_serie} {pago.cfe_numero}".strip()
    )
    return redirect("pagos:historial")


def facture_anular_pago_sandbox(request, pago_id):
    """
    Emite una Nota de Crédito de eTicket (CFE 102) en sandbox
    para anular totalmente el eTicket original de un pago.
    """
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    if not settings.DEBUG or getattr(settings, "FACTURE_MODO", "") != "sandbox":
        raise Http404

    pago = get_object_or_404(Pago, id=pago_id)

    if pago.cfe_estado != Pago.CFE_EMITIDO:
        messages.warning(
            request,
            "Solo se puede anular un pago que tenga un CFE emitido."
        )
        return redirect("pagos:historial")

    if pago.nc_numero or pago.nc_cfe_id:
        messages.warning(
            request,
            "Este pago ya tiene una Nota de Crédito asociada."
        )
        return redirect("pagos:historial")

    if not pago.cfe_serie or not pago.cfe_numero:
        messages.error(
            request,
            "El CFE original no tiene serie o número para poder referenciarlo."
        )
        return redirect("pagos:historial")

    razon = request.POST.get(
        "razon",
        "Anulación total de eTicket"
    ).strip() or "Anulación total de eTicket"

    try:
        resultado = emitir_nota_credito_pago_sandbox(
            pago,
            razon=razon,
        )
    except FactureError as exc:
        pago.nc_error = str(exc)
        pago.save(update_fields=["nc_error"])
        messages.error(
            request,
            f"No se pudo emitir la Nota de Crédito: {exc}"
        )
        return redirect("pagos:historial")

    if not resultado.get("ok"):
        detalle = resultado.get("error", {})
        pago.nc_error = json.dumps(
            detalle,
            ensure_ascii=False
        )[:5000]
        pago.save(update_fields=["nc_error"])
        messages.error(
            request,
            f"Facture rechazó la Nota de Crédito (HTTP {resultado.get('status')})."
        )
        return redirect("pagos:historial")

    data = resultado.get("data") or {}
    cod_respuesta = str(
        data.get("CodRespuesta", "")
    ).strip()

    if cod_respuesta and cod_respuesta != "00":
        pago.nc_error = json.dumps(
            data,
            ensure_ascii=False
        )[:5000]
        pago.save(update_fields=["nc_error"])
        messages.error(
            request,
            f"Facture respondió {cod_respuesta}: "
            f"{data.get('MensajeRespuesta', 'Error')}"
        )
        return redirect("pagos:historial")

    pago.nc_cfe_id = str(
        data.get("_Id") or data.get("IdComprobante") or ""
    )
    pago.nc_serie = str(data.get("Serie") or "")
    pago.nc_numero = str(data.get("Nro") or "")
    pago.nc_xml_firmado = str(data.get("XmlFirmado") or "")
    pago.nc_error = ""
    pago.cfe_estado = Pago.CFE_ANULADO

    pago.save(update_fields=[
        "nc_cfe_id",
        "nc_serie",
        "nc_numero",
        "nc_xml_firmado",
        "nc_error",
        "cfe_estado",
    ])

    messages.success(
        request,
        (
            "Nota de Crédito de prueba emitida: "
            f"{pago.nc_serie} {pago.nc_numero}. "
            f"El eTicket {pago.cfe_serie} {pago.cfe_numero} quedó marcado como anulado."
        ).strip()
    )
    return redirect("pagos:historial")


def facture_pdf_pago(request, pago_id):
    """Muestra el PDF de un CFE ya emitido. No emite un comprobante nuevo."""
    pago = get_object_or_404(Pago, id=pago_id)

    if pago.cfe_estado not in (Pago.CFE_EMITIDO, Pago.CFE_ANULADO):
        messages.error(request, "Este pago todavía no tiene un CFE emitido.")
        return redirect("pagos:historial")

    if not pago.cfe_serie or not pago.cfe_numero:
        messages.error(request, "Faltan serie o número del CFE.")
        return redirect("pagos:historial")

    try:
        resultado = obtener_pdf_cfe_por_folio(
            tipo_cfe=101,
            serie=pago.cfe_serie,
            numero=pago.cfe_numero,
        )
    except FactureError as exc:
        messages.error(request, f"No se pudo obtener el PDF: {exc}")
        return redirect("pagos:historial")

    if not resultado.get("ok"):
        detalle = resultado.get("error", {})
        messages.error(
            request,
            f"Facture no pudo generar el PDF (HTTP {resultado.get('status')}): {detalle}"
        )
        return redirect("pagos:historial")

    response = HttpResponse(resultado["content"], content_type="application/pdf")
    response["Content-Disposition"] = (
        f'inline; filename="CFE_{pago.cfe_serie}_{pago.cfe_numero}.pdf"'
    )
    return response


def facture_xml_pago(request, pago_id):
    """
    Descarga el XML firmado guardado al momento de emitir el CFE.
    No realiza una nueva llamada a Facture.
    """
    pago = get_object_or_404(Pago, id=pago_id)

    if pago.cfe_estado not in (Pago.CFE_EMITIDO, Pago.CFE_ANULADO):
        messages.error(request, "Este pago todavía no tiene un CFE emitido.")
        return redirect("pagos:historial")

    if not pago.cfe_xml_firmado:
        messages.warning(
            request,
            "Este CFE fue emitido antes de comenzar a guardar el XML firmado."
        )
        return redirect("pagos:historial")

    response = HttpResponse(
        pago.cfe_xml_firmado,
        content_type="application/xml; charset=utf-8",
    )
    response["Content-Disposition"] = (
        f'attachment; filename="CFE_{pago.cfe_serie}_{pago.cfe_numero}.xml"'
    )
    return response

def facture_pdf_nota_credito_pago(request, pago_id):
    """Muestra el PDF de la Nota de Crédito asociada al pago."""
    pago = get_object_or_404(Pago, id=pago_id)

    if not pago.nc_serie or not pago.nc_numero:
        messages.error(
            request,
            "Este pago todavía no tiene una Nota de Crédito emitida."
        )
        return redirect("pagos:historial")

    try:
        resultado = obtener_pdf_cfe_por_folio(
            tipo_cfe=102,
            serie=pago.nc_serie,
            numero=pago.nc_numero,
        )
    except FactureError as exc:
        messages.error(
            request,
            f"No se pudo obtener el PDF de la Nota de Crédito: {exc}"
        )
        return redirect("pagos:historial")

    if not resultado.get("ok"):
        detalle = resultado.get("error", {})
        messages.error(
            request,
            f"Facture no pudo generar el PDF de la Nota de Crédito "
            f"(HTTP {resultado.get('status')}): {detalle}"
        )
        return redirect("pagos:historial")

    response = HttpResponse(
        resultado["content"],
        content_type="application/pdf"
    )
    response["Content-Disposition"] = (
        f'inline; filename="NC_{pago.nc_serie}_{pago.nc_numero}.pdf"'
    )
    return response


def facture_xml_nota_credito_pago(request, pago_id):
    """Descarga el XML firmado de la Nota de Crédito."""
    pago = get_object_or_404(Pago, id=pago_id)

    if not pago.nc_xml_firmado:
        messages.warning(
            request,
            "Este pago todavía no tiene XML de Nota de Crédito guardado."
        )
        return redirect("pagos:historial")

    response = HttpResponse(
        pago.nc_xml_firmado,
        content_type="application/xml; charset=utf-8",
    )
    response["Content-Disposition"] = (
        f'attachment; filename="NC_{pago.nc_serie}_{pago.nc_numero}.xml"'
    )
    return response

