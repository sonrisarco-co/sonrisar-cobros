from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from .models import Pago
from django.core.paginator import Paginator
from django.db.models import Sum, Q, Prefetch
from django.db import transaction
from collections import OrderedDict
import json
from caja.models import CashSession, MovimientoCaja
from pagos.models import Pago

from itertools import groupby
from django.utils.timezone import localtime
from django.utils import timezone

from collections import defaultdict
import calendar

from django.utils.translation import gettext as _

from django.http import JsonResponse, Http404, HttpResponseNotAllowed, HttpResponse
from django.conf import settings

from django.contrib import messages
from django.views.decorators.http import require_POST

from decimal import Decimal
from urllib.parse import quote, urlencode, urlsplit, urlunsplit, parse_qsl
from .models import (
    Gasto,
    DevolucionPaciente,
    CompraProveedor,
    PagoCompraProveedor
)

from .facture_service import (
    probar_conexion,
    emitir_pago,
    emitir_nota_credito_pago,
    emitir_nota_credito_devolucion,
    obtener_pdf_cfe_por_folio,
    FactureError,
)


def _agregar_params_url(url, **params):
    """Agrega parámetros a una URL preservando los que ya existan."""
    if not url:
        return url

    partes = urlsplit(url)
    query = dict(parse_qsl(partes.query, keep_blank_values=True))

    for clave, valor in params.items():
        if valor not in (None, ""):
            query[clave] = str(valor)

    return urlunsplit((
        partes.scheme,
        partes.netloc,
        partes.path,
        urlencode(query),
        partes.fragment,
    ))


def _emitir_cfe_y_guardar(pago):
    """
    Emite el eTicket y guarda el resultado fiscal en el pago.
    El pago ya existe antes de llamar a Facture: si la emisión falla,
    el cobro NO se pierde.
    """
    try:
        resultado = emitir_pago(pago)
    except FactureError as exc:
        pago.cfe_estado = Pago.CFE_RECHAZADO
        pago.cfe_error = str(exc)
        pago.save(update_fields=["cfe_estado", "cfe_error"])
        return False, str(exc)

    if not resultado.get("ok"):
        detalle = resultado.get("error", {})
        pago.cfe_estado = Pago.CFE_RECHAZADO
        pago.cfe_error = json.dumps(
            detalle,
            ensure_ascii=False,
        )[:5000]
        pago.save(update_fields=["cfe_estado", "cfe_error"])
        return (
            False,
            f"Facture rechazó la emisión (HTTP {resultado.get('status')})."
        )

    data = resultado.get("data") or {}
    cod_respuesta = str(data.get("CodRespuesta", "")).strip()

    if cod_respuesta and cod_respuesta != "00":
        pago.cfe_estado = Pago.CFE_RECHAZADO
        pago.cfe_error = json.dumps(
            data,
            ensure_ascii=False,
        )[:5000]
        pago.save(update_fields=["cfe_estado", "cfe_error"])
        return (
            False,
            f"Facture respondió {cod_respuesta}: "
            f"{data.get('MensajeRespuesta', 'Error')}"
        )

    pago.cfe_estado = Pago.CFE_EMITIDO
    pago.cfe_tipo = "eTicket"
    pago.cfe_serie = str(data.get("Serie") or "")
    pago.cfe_numero = str(data.get("Nro") or "")
    pago.cfe_fecha_emision = timezone.localdate()
    pago.facture_cfe_id = str(
        data.get("_Id")
        or data.get("IdComprobante")
        or ""
    )
    pago.cfe_xml_firmado = str(data.get("XmlFirmado") or "")
    pago.cfe_error = ""
    pago.save(update_fields=[
        "cfe_estado",
        "cfe_tipo",
        "cfe_serie",
        "cfe_numero",
        "cfe_fecha_emision",
        "facture_cfe_id",
        "cfe_xml_firmado",
        "cfe_error",
    ])

    return True, (
        f"{pago.cfe_tipo} {pago.cfe_serie} {pago.cfe_numero}".strip()
    )


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

        # La misma casilla histórica ahora significa:
        # registrar el pago + emitir el CFE inmediatamente.
        solicitar_cfe = request.POST.get("solicitar_cfe") == "on"
        next_url = request.POST.get("next", "").strip()

        appointment_id = request.POST.get("appointment_id")
        patient_id = request.POST.get("patient_id")
        protesis_id = request.POST.get("protesis_id")

        try:
            appointment_id = int(appointment_id) if appointment_id else None
        except (TypeError, ValueError):
            appointment_id = None

        try:
            patient_id = int(patient_id) if patient_id else None
        except (TypeError, ValueError):
            patient_id = None

        try:
            protesis_id = int(protesis_id) if protesis_id else None
        except (TypeError, ValueError):
            protesis_id = None

        paciente = request.POST.get("paciente", "").strip()

        # El pago se guarda PRIMERO. Así, aun si Facture tiene una caída
        # o rechaza el CFE, el cobro queda registrado en Sonrisar Cobros.
        pago = Pago.objects.create(
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

        cfe_ok = None
        cfe_mensaje = ""

        if solicitar_cfe:
            cfe_ok, cfe_mensaje = _emitir_cfe_y_guardar(pago)

        if next_url:
            params_retorno = {
                "cobro": "ok",
                "pago_id": pago.id,
            }

            if solicitar_cfe and cfe_ok:
                pdf_url = request.build_absolute_uri(
                    reverse("pagos:facture_pdf_pago", args=[pago.id])
                )
                params_retorno.update({
                    "cfe": "emitido",
                    "cfe_serie": pago.cfe_serie,
                    "cfe_numero": pago.cfe_numero,
                    "cfe_pdf": pdf_url,
                })
            elif solicitar_cfe:
                params_retorno.update({
                    "cfe": "error",
                    "cfe_mensaje": cfe_mensaje,
                })
            else:
                params_retorno["cfe"] = "no"

            return redirect(
                _agregar_params_url(
                    next_url,
                    **params_retorno,
                )
            )

        if solicitar_cfe and cfe_ok:
            messages.success(
                request,
                f"Pago registrado y CFE emitido: {cfe_mensaje}."
            )
        elif solicitar_cfe:
            messages.warning(
                request,
                "Pago registrado, pero el CFE no pudo emitirse. "
                f"{cfe_mensaje}"
            )
        else:
            messages.success(request, "Pago registrado correctamente.")

        return redirect("caja:tablero")

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
        "facture_modo": getattr(settings, "FACTURE_MODO", "sandbox"),
        "facture_envio_habilitado": getattr(
            settings,
            "FACTURE_ENVIO_HABILITADO",
            False,
        ),
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

    devoluciones_historial_qs = (
        DevolucionPaciente.objects
        .only(
            "id",
            "pago_original_id",
            "fecha",
            "monto",
            "metodo",
            "concepto",
            "tipo",
            "reintegrada",
            "fecha_reintegro",
            "nc_solicitada",
            "nc_cfe_id",
            "nc_serie",
            "nc_numero",
            "nc_fecha_emision",
            "nc_xml_firmado",
            "nc_error",
        )
        .order_by("fecha", "id")
    )

    pagos_qs = (
        Pago.objects
        .only(
            "id",
            "fecha",
            "monto",
            "metodo",
            "paciente",
            "concepto",
            "cfe_solicitado",
            "cfe_estado",
            "tasa_iva_cfe",
            "cfe_tipo",
            "cfe_serie",
            "cfe_numero",
            "cfe_error",
            "facture_cfe_id",
            "tipo_tarjeta",
            "cfe_xml_firmado",
            "nc_cfe_id",
            "nc_serie",
            "nc_numero",
            "nc_xml_firmado",
            "nc_error",
        )
        .prefetch_related(
            Prefetch(
                "devoluciones",
                queryset=devoluciones_historial_qs,
                to_attr="devoluciones_historial",
            )
        )
        .order_by("-fecha", "-id")
    )

    paginator = Paginator(pagos_qs, 120)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

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

    pagos_por_mes = OrderedDict()

    for pago in page_obj.object_list:
        fecha_local = localtime(pago.fecha)
        mes_nombre = (
            f"{meses_es[fecha_local.month]} "
            f"{fecha_local.year}"
        )

        if mes_nombre not in pagos_por_mes:
            pagos_por_mes[mes_nombre] = []

        # Datos útiles para el historial.
        pago.total_devuelto_historial = sum(
            (devolucion.monto or Decimal("0.00"))
            for devolucion in pago.devoluciones_historial
            if devolucion.afecta_saldo_odontologico
        )

        pago.total_temporal_pendiente_historial = sum(
            (devolucion.monto or Decimal("0.00"))
            for devolucion in pago.devoluciones_historial
            if devolucion.pendiente_reintegro
        )

        pago.total_nc_devoluciones_historial = sum(
            (
                devolucion.monto
                or Decimal("0.00")
            )
            for devolucion
            in pago.devoluciones_historial
            if devolucion.nc_numero
        )

        pagos_por_mes[mes_nombre].append(pago)

    return render(
        request,
        "pagos/historial.html",
        {
            "pagos_por_mes": pagos_por_mes,
            "page_obj": page_obj,
            "total_pagos": paginator.count,
            "facture_modo": getattr(
                settings,
                "FACTURE_MODO",
                "sandbox",
            ),
            "facture_envio_habilitado": getattr(
                settings,
                "FACTURE_ENVIO_HABILITADO",
                False,
            ),
        },
    )



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
        "tipo": devolucion.tipo,
        "tipo_display": devolucion.get_tipo_display(),
        "reintegrada": devolucion.reintegrada,
        "pendiente_reintegro": devolucion.pendiente_reintegro,
        "fecha_reintegro": (
            localtime(devolucion.fecha_reintegro).strftime("%d/%m/%Y %H:%M")
            if devolucion.fecha_reintegro else None
        ),
        "afecta_saldo_odontologico": devolucion.afecta_saldo_odontologico,
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
            return JsonResponse({"ok": False, "error": "patient_id inválido."}, status=400)
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
    total_devuelto = sum(
        (dev.monto or 0) for dev in devoluciones
        if dev.afecta_saldo_odontologico
    )
    total_temporal_pendiente = sum(
        (dev.monto or 0) for dev in devoluciones
        if dev.pendiente_reintegro
    )
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
        "total_temporal_pendiente": str(total_temporal_pendiente),
        "total_pagado": str(total_pagado),
        "tipo_pago": "sena" if tiene_sena else "pagado",
        "pagos": data,
        "devoluciones": devoluciones_data,
    })

def api_resumen_pacientes(request):
    """API rápida. Las devoluciones temporales NO reducen el pago clínico."""
    patient_ids_raw = request.GET.get("patient_ids", "").strip()
    if not patient_ids_raw:
        return JsonResponse({"ok": False, "error": "Falta el parámetro patient_ids."}, status=400)

    patient_ids = []
    for item in patient_ids_raw.split(","):
        patient_id = _to_int_or_none(item.strip())
        if patient_id is not None and patient_id not in patient_ids:
            patient_ids.append(patient_id)
    if not patient_ids:
        return JsonResponse({"ok": False, "error": "No se recibieron patient_ids válidos."}, status=400)

    pagos = Pago.objects.filter(patient_id__in=patient_ids)
    devoluciones = DevolucionPaciente.objects.filter(patient_id__in=patient_ids)

    resumen = {
        patient_id: {
            "patient_id": patient_id,
            "total_pagado": "0",
            "total_pagado_bruto": "0",
            "total_devuelto": "0",
            "total_temporal_pendiente": "0",
            "cantidad_pagos": 0,
            "cantidad_devoluciones": 0,
            "cantidad_temporales_pendientes": 0,
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
        datos["cantidad_devoluciones"] += 1
        if devolucion.afecta_saldo_odontologico:
            datos["total_devuelto"] = str(
                Decimal(datos["total_devuelto"]) + (devolucion.monto or Decimal("0.00"))
            )
        if devolucion.pendiente_reintegro:
            datos["total_temporal_pendiente"] = str(
                Decimal(datos["total_temporal_pendiente"]) + (devolucion.monto or Decimal("0.00"))
            )
            datos["cantidad_temporales_pendientes"] += 1

    for datos in resumen.values():
        datos["total_pagado"] = str(
            Decimal(datos["total_pagado_bruto"]) - Decimal(datos["total_devuelto"])
        )

    return JsonResponse({"ok": True, "pacientes": list(resumen.values())})

def api_pago_por_cita(request):
    appointment_id = request.GET.get("appointment_id", "").strip()
    patient_id = request.GET.get("patient_id", "").strip()
    if not appointment_id:
        return JsonResponse({"ok": False, "error": "Falta el parámetro appointment_id."}, status=400)

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
    total_temporal_pendiente = Decimal("0.00")
    tipo_pago = "pagado"

    for pago in pagos:
        total_pagado_bruto += pago.monto or Decimal("0.00")
        if _es_sena(pago.concepto):
            tipo_pago = "sena"
        data.append(_pago_to_dict(pago))

    devoluciones_data = []
    for devolucion in devoluciones:
        if devolucion.afecta_saldo_odontologico:
            total_devuelto += devolucion.monto or Decimal("0.00")
        if devolucion.pendiente_reintegro:
            total_temporal_pendiente += devolucion.monto or Decimal("0.00")
        devoluciones_data.append(_devolucion_to_dict(devolucion))

    return JsonResponse({
        "ok": True,
        "appointment_id": appointment_id,
        "patient_id": patient_id or None,
        "total": len(data),
        "cantidad_devoluciones": len(devoluciones_data),
        "total_pagado_bruto": str(total_pagado_bruto),
        "total_devuelto": str(total_devuelto),
        "total_temporal_pendiente": str(total_temporal_pendiente),
        "total_pagado": str(total_pagado_bruto - total_devuelto),
        "tipo_pago": tipo_pago,
        "pagos": data,
        "devoluciones": devoluciones_data,
    })

def api_resumen_citas(request):
    appointment_ids_raw = request.GET.get("appointment_ids", "").strip()
    if not appointment_ids_raw:
        return JsonResponse({"ok": False, "error": "Falta el parámetro appointment_ids."}, status=400)

    appointment_ids = []
    for item in appointment_ids_raw.split(","):
        appointment_id = _to_int_or_none(item.strip())
        if appointment_id is not None and appointment_id not in appointment_ids:
            appointment_ids.append(appointment_id)
    if not appointment_ids:
        return JsonResponse({"ok": False, "error": "No se recibieron appointment_ids válidos."}, status=400)

    pagos = Pago.objects.filter(appointment_id__in=appointment_ids).order_by("-fecha")
    devoluciones = DevolucionPaciente.objects.filter(appointment_id__in=appointment_ids).order_by("-fecha")
    resumen = {
        appointment_id: {
            "appointment_id": appointment_id,
            "total_pagado": "0",
            "total_pagado_bruto": "0",
            "total_devuelto": "0",
            "total_temporal_pendiente": "0",
            "cantidad_pagos": 0,
            "cantidad_devoluciones": 0,
            "cantidad_temporales_pendientes": 0,
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
        datos["total_pagado_bruto"] = str(
            Decimal(datos["total_pagado_bruto"]) + (pago.monto or Decimal("0.00"))
        )
        datos["cantidad_pagos"] += 1
        datos["pagos"].append(_pago_to_dict(pago))
        if _es_sena(pago.concepto):
            datos["tipo_pago"] = "sena"

    for devolucion in devoluciones:
        datos = resumen.get(devolucion.appointment_id)
        if not datos:
            continue
        datos["cantidad_devoluciones"] += 1
        if devolucion.afecta_saldo_odontologico:
            datos["total_devuelto"] = str(
                Decimal(datos["total_devuelto"]) + (devolucion.monto or Decimal("0.00"))
            )
        if devolucion.pendiente_reintegro:
            datos["total_temporal_pendiente"] = str(
                Decimal(datos["total_temporal_pendiente"]) + (devolucion.monto or Decimal("0.00"))
            )
            datos["cantidad_temporales_pendientes"] += 1
        datos["devoluciones"].append(_devolucion_to_dict(devolucion))

    for datos in resumen.values():
        datos["total_pagado"] = str(
            Decimal(datos["total_pagado_bruto"]) - Decimal(datos["total_devuelto"])
        )
    return JsonResponse({"ok": True, "citas": list(resumen.values())})

def api_pago_por_protesis(request):
    protesis_id = request.GET.get("protesis_id", "").strip()
    if not protesis_id:
        return JsonResponse({"ok": False, "error": "Falta el parámetro protesis_id."}, status=400)

    pagos = Pago.objects.filter(protesis_id=protesis_id).order_by("-fecha")
    devoluciones = DevolucionPaciente.objects.filter(protesis_id=protesis_id).order_by("-fecha")
    total_pagado_bruto = Decimal("0.00")
    total_devuelto = Decimal("0.00")
    total_temporal_pendiente = Decimal("0.00")
    data = []
    devoluciones_data = []
    for pago in pagos:
        total_pagado_bruto += pago.monto or Decimal("0.00")
        data.append(_pago_to_dict(pago))
    for devolucion in devoluciones:
        if devolucion.afecta_saldo_odontologico:
            total_devuelto += devolucion.monto or Decimal("0.00")
        if devolucion.pendiente_reintegro:
            total_temporal_pendiente += devolucion.monto or Decimal("0.00")
        devoluciones_data.append(_devolucion_to_dict(devolucion))

    return JsonResponse({
        "ok": True,
        "protesis_id": protesis_id,
        "total": len(data),
        "cantidad_devoluciones": len(devoluciones_data),
        "total_pagado_bruto": str(total_pagado_bruto),
        "total_devuelto": str(total_devuelto),
        "total_temporal_pendiente": str(total_temporal_pendiente),
        "total_pagado": str(total_pagado_bruto - total_devuelto),
        "pagos": data,
        "devoluciones": devoluciones_data,
    })

def _emitir_nc_devolucion_y_guardar(devolucion):
    """
    Emite la Nota de Crédito correspondiente a una devolución
    y guarda el resultado fiscal sin borrar la devolución si
    Facture/DGI rechaza la emisión.
    """
    pago = devolucion.pago_original

    if not pago:
        devolucion.nc_error = "La devolución no tiene un pago original asociado."
        devolucion.save(update_fields=["nc_error"])
        return False, devolucion.nc_error

    if pago.cfe_estado != Pago.CFE_EMITIDO:
        devolucion.nc_error = (
            "El pago original no tiene un eTicket emitido disponible "
            "para generar una Nota de Crédito."
        )
        devolucion.save(update_fields=["nc_error"])
        return False, devolucion.nc_error

    if not pago.cfe_serie or not pago.cfe_numero:
        devolucion.nc_error = (
            "El eTicket original no tiene serie o número para referenciarlo."
        )
        devolucion.save(update_fields=["nc_error"])
        return False, devolucion.nc_error

    if devolucion.nc_numero or devolucion.nc_cfe_id:
        return False, "Esta devolución ya tiene una Nota de Crédito asociada."

    # Seguridad adicional:
    # si estamos en PRODUCCIÓN pero el envío real está deshabilitado,
    # NO se llama a Facture y por lo tanto NO se envía nada a DGI.
    facture_modo = getattr(settings, "FACTURE_MODO", "sandbox")
    facture_envio_habilitado = getattr(
        settings,
        "FACTURE_ENVIO_HABILITADO",
        False,
    )

    if (
        facture_modo == "produccion"
        and not facture_envio_habilitado
    ):
        devolucion.nc_error = (
            "Emisión real de Nota de Crédito deshabilitada por seguridad. "
            "No se envió ningún comprobante a Facture/DGI."
        )
        devolucion.save(update_fields=["nc_error"])
        return False, devolucion.nc_error

    try:
        resultado = emitir_nota_credito_devolucion(
            devolucion,
            razon=devolucion.concepto or "Devolución a paciente",
        )
    except FactureError as exc:
        devolucion.nc_error = str(exc)
        devolucion.save(update_fields=["nc_error"])
        return False, str(exc)

    if not resultado.get("ok"):
        detalle = resultado.get("error", {})
        devolucion.nc_error = json.dumps(
            detalle,
            ensure_ascii=False,
        )[:5000]
        devolucion.save(update_fields=["nc_error"])

        return (
            False,
            f"Facture rechazó la Nota de Crédito "
            f"(HTTP {resultado.get('status')})."
        )

    data = resultado.get("data") or {}
    cod_respuesta = str(data.get("CodRespuesta", "")).strip()

    if cod_respuesta and cod_respuesta != "00":
        devolucion.nc_error = json.dumps(
            data,
            ensure_ascii=False,
        )[:5000]
        devolucion.save(update_fields=["nc_error"])

        return (
            False,
            f"Facture respondió {cod_respuesta}: "
            f"{data.get('MensajeRespuesta', 'Error')}"
        )

    devolucion.nc_cfe_id = str(
        data.get("_Id")
        or data.get("IdComprobante")
        or ""
    )
    devolucion.nc_serie = str(data.get("Serie") or "")
    devolucion.nc_numero = str(data.get("Nro") or "")
    devolucion.nc_fecha_emision = timezone.localdate()
    devolucion.nc_xml_firmado = str(data.get("XmlFirmado") or "")
    devolucion.nc_error = ""

    devolucion.save(update_fields=[
        "nc_cfe_id",
        "nc_serie",
        "nc_numero",
        "nc_fecha_emision",
        "nc_xml_firmado",
        "nc_error",
    ])

    # Sumamos únicamente devoluciones que efectivamente tienen NC emitida.
    total_acreditado = (
        DevolucionPaciente.objects
        .filter(
            pago_original=pago,
            nc_numero__gt="",
        )
        .aggregate(total=Sum("monto"))["total"]
        or Decimal("0.00")
    )

    # Solo cuando las NC cubren todo el eTicket,
    # el comprobante original queda totalmente anulado.
    if total_acreditado >= pago.monto:
        pago.cfe_estado = Pago.CFE_ANULADO
        pago.save(update_fields=["cfe_estado"])

    return True, (
        f"Nota de Crédito "
        f"{devolucion.nc_serie} {devolucion.nc_numero}".strip()
    )



def nueva_devolucion(request):
    caja = CashSession.obtener_caja_del_dia()

    if request.method == "POST":
        afecta_caja = request.POST.get("afecta_caja") == "on"
        solicitar_nc = request.POST.get("solicitar_nc") == "on"
        tipo_devolucion = request.POST.get(
            "tipo_devolucion", DevolucionPaciente.TIPO_DEFINITIVA
        ).strip()
        if tipo_devolucion not in {
            DevolucionPaciente.TIPO_DEFINITIVA,
            DevolucionPaciente.TIPO_TEMPORAL,
        }:
            tipo_devolucion = DevolucionPaciente.TIPO_DEFINITIVA
        if tipo_devolucion == DevolucionPaciente.TIPO_TEMPORAL:
            solicitar_nc = False

        if afecta_caja and caja.estado == CashSession.Status.CERRADA:
            messages.error(
                request,
                "La caja del día está cerrada. Puedes registrar la devolución, "
                "pero no descontarla de la caja actual."
            )
            return redirect("pagos:nueva_devolucion")

        pago_original_id = _to_int_or_none(
            request.POST.get("pago_original_id")
        )

        pago_original = (
            Pago.objects.filter(id=pago_original_id).first()
            if pago_original_id is not None
            else None
        )

        paciente = request.POST.get("paciente", "").strip()
        patient_id = _to_int_or_none(
            request.POST.get("patient_id")
        )
        appointment_id = _to_int_or_none(
            request.POST.get("appointment_id")
        )
        protesis_id = _to_int_or_none(
            request.POST.get("protesis_id")
        )
        metodo = request.POST.get("metodo", "").strip()
        concepto = request.POST.get("concepto", "").strip()
        next_url = request.POST.get("next", "").strip()

        if pago_original:
            paciente = pago_original.paciente or paciente
            patient_id = (
                pago_original.patient_id
                or patient_id
            )
            appointment_id = (
                pago_original.appointment_id
                or appointment_id
            )
            protesis_id = (
                pago_original.protesis_id
                or protesis_id
            )

        monto_texto = (
            request.POST.get("monto", "")
            .strip()
            .replace(",", ".")
        )

        try:
            monto = Decimal(monto_texto)

            if monto <= 0:
                raise ValueError

        except (ValueError, ArithmeticError):
            monto = None

        metodos_validos = {
            valor
            for valor, _ in DevolucionPaciente.METODOS
        }

        if not pago_original:
            messages.error(
                request,
                "Selecciona el pago original que corresponde "
                "a la devolución."
            )

        elif not paciente:
            messages.error(
                request,
                "Debes indicar el paciente de la devolución."
            )

        elif monto is None:
            messages.error(
                request,
                "El monto de la devolución debe ser mayor a cero."
            )

        elif metodo not in metodos_validos:
            messages.error(
                request,
                "Selecciona un método de devolución válido."
            )

        elif solicitar_nc and (
            pago_original.cfe_estado != Pago.CFE_EMITIDO
        ):
            messages.error(
                request,
                "Para emitir una Nota de Crédito, el pago original "
                "debe tener un eTicket emitido."
            )

        elif solicitar_nc and (
            not pago_original.cfe_serie
            or not pago_original.cfe_numero
        ):
            messages.error(
                request,
                "El eTicket original no tiene serie o número "
                "para poder emitir la Nota de Crédito."
            )

        elif (
            solicitar_nc
            and getattr(settings, "FACTURE_MODO", "sandbox") == "produccion"
            and not getattr(
                settings,
                "FACTURE_ENVIO_HABILITADO",
                False,
            )
        ):
            messages.error(
                request,
                "La emisión real de Nota de Crédito está deshabilitada "
                "por seguridad. No se registró la devolución y no se envió "
                "nada a Facture/DGI."
            )

        else:
            ya_devuelto = (
                DevolucionPaciente.objects
                .filter(pago_original=pago_original)
                .filter(
                    Q(tipo=DevolucionPaciente.TIPO_DEFINITIVA)
                    | Q(tipo=DevolucionPaciente.TIPO_TEMPORAL, reintegrada=False)
                )
                .aggregate(total=Sum("monto"))["total"]
                or Decimal("0.00")
            )

            disponible = (
                pago_original.monto
                or Decimal("0.00")
            ) - ya_devuelto

            if disponible <= 0:
                messages.error(
                    request,
                    "Ese pago ya fue devuelto completamente "
                    "y no tiene saldo disponible para otra devolución."
                )
                monto = None

            elif monto > disponible:
                messages.error(
                    request,
                    (
                        f"No puedes devolver ${monto:.2f}. "
                        f"De ese pago quedan ${disponible:.2f} "
                        "disponibles para devolución."
                    )
                )
                monto = None

            if monto is not None:
                concepto_final = (
                    concepto
                    or "Devolución de pago a paciente"
                )

                # Primero registramos la devolución económica.
                # Si Facture/DGI falla después, esta devolución
                # no se pierde.
                with transaction.atomic():
                    caja_asignada = (
                        caja if afecta_caja else None
                    )

                    es_temporal = tipo_devolucion == DevolucionPaciente.TIPO_TEMPORAL
                    gasto = Gasto.objects.create(
                        proveedor=paciente,
                        categoria=("entrega_temporal_paciente" if es_temporal else "devolucion_paciente"),
                        concepto=((f"Entrega temporal a {paciente}: " if es_temporal else f"Devolución a {paciente}: ") + concepto_final),
                        monto=monto,
                        metodo=metodo,
                        afecta_caja=afecta_caja,
                        caja=caja_asignada,
                    )

                    devolucion = (
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
                            tipo=tipo_devolucion,
                            reintegrada=False,
                            nc_solicitada=solicitar_nc,
                        )
                    )

                # La emisión fiscal ocurre DESPUÉS
                # de guardar la devolución.
                nc_ok = None
                nc_mensaje = ""

                if solicitar_nc:
                    nc_ok, nc_mensaje = (
                        _emitir_nc_devolucion_y_guardar(
                            devolucion
                        )
                    )

                detalle_caja = (
                    " Se descontó de la caja del día."
                    if afecta_caja
                    else
                    " No afectó la caja del día."
                )

                if solicitar_nc and nc_ok:
                    messages.success(
                        request,
                        (
                            f"Devolución de ${monto:.2f} "
                            f"registrada para {paciente}."
                            f"{detalle_caja} "
                            f"{nc_mensaje} emitida correctamente."
                        )
                    )

                elif solicitar_nc:
                    messages.warning(
                        request,
                        (
                            f"Devolución de ${monto:.2f} "
                            f"registrada para {paciente}."
                            f"{detalle_caja} "
                            "La Nota de Crédito no pudo emitirse: "
                            f"{nc_mensaje}"
                        )
                    )

                else:
                    messages.success(
                        request,
                        (
                            f"Devolución de ${monto:.2f} "
                            f"registrada para {paciente}."
                            f"{detalle_caja}"
                        )
                    )

                if next_url:
                    return redirect(next_url)

                return redirect("caja:tablero")

    if request.method == "POST":
        initial = {
            "paciente": request.POST.get(
                "paciente",
                ""
            ),
            "patient_id": request.POST.get(
                "patient_id",
                ""
            ),
            "appointment_id": request.POST.get(
                "appointment_id",
                ""
            ),
            "protesis_id": request.POST.get(
                "protesis_id",
                ""
            ),
            "monto": request.POST.get(
                "monto",
                ""
            ),
            "concepto": request.POST.get(
                "concepto",
                ""
            ),
            "pago_original_id": request.POST.get(
                "pago_original_id",
                ""
            ),
            "next": request.POST.get(
                "next",
                ""
            ),
            "metodo": request.POST.get(
                "metodo",
                ""
            ),
            "tipo_devolucion": request.POST.get(
                "tipo_devolucion", DevolucionPaciente.TIPO_DEFINITIVA
            ),
            "afecta_caja": (
                request.POST.get(
                    "afecta_caja"
                ) == "on"
            ),
            "solicitar_nc": (
                request.POST.get(
                    "solicitar_nc"
                ) == "on"
            ),
        }

        busqueda_pago = (
            request.POST.get(
                "busqueda_pago",
                ""
            ).strip()
        )

    else:
        initial = {
            "paciente": request.GET.get(
                "paciente",
                ""
            ),
            "patient_id": request.GET.get(
                "patient_id",
                ""
            ),
            "appointment_id": request.GET.get(
                "appointment_id",
                ""
            ),
            "protesis_id": request.GET.get(
                "protesis_id",
                ""
            ),
            "monto": request.GET.get(
                "monto",
                ""
            ),
            "concepto": request.GET.get(
                "concepto",
                ""
            ),
            "pago_original_id": request.GET.get(
                "pago_id",
                ""
            ),
            "next": request.GET.get(
                "next",
                ""
            ),
            "metodo": "",
            "tipo_devolucion": DevolucionPaciente.TIPO_DEFINITIVA,
            "afecta_caja": False,
            "solicitar_nc": False,
        }

        busqueda_pago = (
            request.GET.get(
                "buscar_pago",
                ""
            ).strip()
        )

    pagos_qs = (
        Pago.objects
        .annotate(
            total_devuelto_calc=Sum(
                "devoluciones__monto",
                filter=(
                    Q(devoluciones__tipo=DevolucionPaciente.TIPO_DEFINITIVA)
                    | Q(devoluciones__tipo=DevolucionPaciente.TIPO_TEMPORAL, devoluciones__reintegrada=False)
                ),
            )
        )
        .only(
            "id",
            "fecha",
            "paciente",
            "monto",
            "concepto",
            "patient_id",
            "appointment_id",
            "protesis_id",
            "cfe_solicitado",
            "cfe_estado",
            "cfe_tipo",
            "cfe_serie",
            "cfe_numero",
        )
        .order_by(
            "-fecha",
            "-id"
        )
    )

    if busqueda_pago:
        filtro = (
            Q(
                paciente__icontains=busqueda_pago
            )
            | Q(
                concepto__icontains=busqueda_pago
            )
        )

        # También permite buscar por ID: #302
        texto_id = busqueda_pago.strip()

        if texto_id.startswith("#"):
            try:
                filtro |= Q(
                    id=int(
                        texto_id[1:].strip()
                    )
                )

            except (
                TypeError,
                ValueError,
            ):
                pass

        texto_monto = (
            busqueda_pago
            .replace("$", "")
            .replace(".", "")
            .replace(",", ".")
            .strip()
        )

        try:
            monto_buscado = Decimal(
                texto_monto
            )

            filtro |= Q(
                monto=monto_buscado
            )

        except (
            ValueError,
            ArithmeticError,
        ):
            pass

        pagos_qs = pagos_qs.filter(
            filtro
        )

    limite = (
        150
        if busqueda_pago
        else 80
    )

    pagos_encontrados = list(
        pagos_qs[:limite]
    )

    pago_inicial_id = (
        _to_int_or_none(
            initial.get(
                "pago_original_id"
            )
        )
    )

    if (
        pago_inicial_id
        and not any(
            p.id == pago_inicial_id
            for p in pagos_encontrados
        )
    ):
        pago_inicial = (
            Pago.objects
            .filter(
                id=pago_inicial_id
            )
            .annotate(
                total_devuelto_calc=Sum(
                    "devoluciones__monto"
                )
            )
            .first()
        )

        if pago_inicial:
            pagos_encontrados.insert(
                0,
                pago_inicial
            )

    for pago in pagos_encontrados:
        pago.total_devuelto_mostrado = (
            pago.total_devuelto_calc
            or Decimal("0.00")
        )

        pago.disponible_devolver = max(
            (
                pago.monto
                or Decimal("0.00")
            )
            - pago.total_devuelto_mostrado,
            Decimal("0.00"),
        )

    return render(
        request,
        "pagos/nueva_devolucion.html",
        {
            "caja": caja,
            "metodos": (
                DevolucionPaciente.METODOS
            ),
            "tipos_devolucion": DevolucionPaciente.TIPOS,
            "pagos_recientes": (
                pagos_encontrados
            ),
            "initial": initial,
            "busqueda_pago": (
                busqueda_pago
            ),
            "cantidad_resultados": len(
                pagos_encontrados
            ),
            "facture_modo": getattr(
                settings,
                "FACTURE_MODO",
                "sandbox",
            ),
            "facture_envio_habilitado": getattr(
                settings,
                "FACTURE_ENVIO_HABILITADO",
                False,
            ),
        },
    )


@require_POST
def reintegrar_devolucion_temporal(request, devolucion_id):
    devolucion = get_object_or_404(DevolucionPaciente, id=devolucion_id)
    if not devolucion.es_temporal:
        messages.error(request, "Solo las devoluciones temporales pueden reintegrarse.")
        return redirect("pagos:historial")
    if devolucion.reintegrada:
        messages.info(request, "Esta entrega temporal ya figura como reintegrada.")
        return redirect("pagos:historial")

    afecta_caja = request.POST.get("afecta_caja") == "on"
    caja = CashSession.obtener_caja_del_dia()
    if afecta_caja and caja.estado == CashSession.Status.CERRADA:
        messages.error(request, "La caja del día está cerrada. No se registró el reintegro.")
        return redirect("pagos:historial")

    with transaction.atomic():
        devolucion.reintegrada = True
        devolucion.fecha_reintegro = timezone.now()
        devolucion.save(update_fields=["reintegrada", "fecha_reintegro"])
        if afecta_caja:
            MovimientoCaja.objects.create(
                caja=caja,
                tipo=MovimientoCaja.Tipo.ENTRADA,
                categoria="Reintegro devolución temporal",
                concepto=f"Reintegro de {devolucion.paciente}: {devolucion.concepto or 'devolución temporal'}",
                monto=devolucion.monto,
            )

    messages.success(
        request,
        f"Reintegro de ${devolucion.monto:.2f} registrado para {devolucion.paciente}."
        + (" Se agregó como entrada de caja." if afecta_caja else " No afectó la caja del día."),
    )
    return redirect("pagos:historial")


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
# FACTURE - PRUEBA DE CONEXIÓN
# =====================================================

def facture_test_conexion(request):
    """
    Diagnóstico local de autenticación con Facture.
    NO emite comprobantes.
    Disponible solo con DEBUG=True.
    Funciona tanto en sandbox como en producción.
    """
    if not settings.DEBUG:
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
# FACTURE - EMISIÓN DE ETICKET
# =====================================================

def facture_emitir_pago_sandbox(request, pago_id):
    """
    Emite un eTicket desde un pago Pendiente CFE.
    Solo acepta POST.
    Puede trabajar en sandbox o producción según FACTURE_MODO.
    """
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    if not settings.DEBUG:
        raise Http404

    try:
        with transaction.atomic():
            pago = (
                Pago.objects
                .select_for_update()
                .get(id=pago_id)
            )

            if not pago.cfe_solicitado:
                messages.error(
                    request,
                    "Este pago no está marcado para CFE."
                )
                return redirect("pagos:historial")

            if pago.cfe_estado == Pago.CFE_EMITIDO:
                messages.warning(
                    request,
                    "Este pago ya tiene un CFE emitido."
                )
                return redirect("pagos:historial")

            if pago.cfe_estado != Pago.CFE_PENDIENTE:
                messages.warning(
                    request,
                    f"El pago no está Pendiente CFE "
                    f"(estado actual: {pago.get_cfe_estado_display()})."
                )
                return redirect("pagos:historial")

            resultado = emitir_pago(pago)

            if not resultado.get("ok"):
                detalle = resultado.get("error", {})
                pago.cfe_estado = Pago.CFE_RECHAZADO
                pago.cfe_error = json.dumps(
                    detalle,
                    ensure_ascii=False,
                )[:5000]
                pago.save(
                    update_fields=[
                        "cfe_estado",
                        "cfe_error",
                    ]
                )
                messages.error(
                    request,
                    f"Facture rechazó la emisión "
                    f"(HTTP {resultado.get('status')})."
                )
                return redirect("pagos:historial")

            data = resultado.get("data") or {}

            # Contrato documentado por Facture:
            # _Id, CodRespuesta, MensajeRespuesta, TipoCfe, Serie, Nro, XmlFirmado.
            cod_respuesta = str(data.get("CodRespuesta", "")).strip()

            if cod_respuesta and cod_respuesta != "00":
                pago.cfe_estado = Pago.CFE_RECHAZADO
                pago.cfe_error = json.dumps(
                    data,
                    ensure_ascii=False,
                )[:5000]
                pago.save(
                    update_fields=[
                        "cfe_estado",
                        "cfe_error",
                    ]
                )
                messages.error(
                    request,
                    f"Facture respondió {cod_respuesta}: "
                    f"{data.get('MensajeRespuesta', 'Error')}"
                )
                return redirect("pagos:historial")

            pago.cfe_estado = Pago.CFE_EMITIDO
            pago.cfe_tipo = "eTicket"
            pago.cfe_serie = str(data.get("Serie") or "")
            pago.cfe_numero = str(data.get("Nro") or "")
            pago.cfe_fecha_emision = timezone.localdate()
            pago.facture_cfe_id = str(
                data.get("_Id")
                or data.get("IdComprobante")
                or ""
            )
            pago.cfe_xml_firmado = str(data.get("XmlFirmado") or "")
            pago.cfe_error = ""
            pago.save(
                update_fields=[
                    "cfe_estado",
                    "cfe_tipo",
                    "cfe_serie",
                    "cfe_numero",
                    "cfe_fecha_emision",
                    "facture_cfe_id",
                    "cfe_xml_firmado",
                    "cfe_error",
                ]
            )

    except Pago.DoesNotExist:
        raise Http404

    except FactureError as exc:
        pago = Pago.objects.filter(id=pago_id).first()

        if pago:
            pago.cfe_estado = Pago.CFE_RECHAZADO
            pago.cfe_error = str(exc)
            pago.save(
                update_fields=[
                    "cfe_estado",
                    "cfe_error",
                ]
            )

        messages.error(
            request,
            f"No se pudo emitir el CFE: {exc}"
        )
        return redirect("pagos:historial")

    messages.success(
        request,
        f"CFE emitido: "
        f"{pago.cfe_tipo} {pago.cfe_serie} {pago.cfe_numero}".strip()
    )
    return redirect("pagos:historial")


def facture_anular_pago_sandbox(request, pago_id):
    """
    Emite una Nota de Crédito de eTicket (CFE 102)
    para anular totalmente el eTicket original de un pago.
    Funciona en sandbox o producción según FACTURE_MODO.
    """
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    if not settings.DEBUG:
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

    tiene_nc_por_devolucion = (
        DevolucionPaciente.objects
        .filter(pago_original=pago)
        .filter(
            Q(nc_numero__gt="")
            | Q(nc_cfe_id__gt="")
        )
        .exists()
    )

    if tiene_nc_por_devolucion:
        messages.warning(
            request,
            (
                "Este eTicket ya tiene una o más "
                "Notas de Crédito por devolución. "
                "No se puede usar la anulación total "
                "antigua porque podría acreditar "
                "más dinero que el importe original."
            ),
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
        resultado = emitir_nota_credito_pago(
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
            "Nota de Crédito emitida: "
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


def facture_pdf_nota_credito_devolucion(
    request,
    devolucion_id,
):
    """
    Muestra el PDF de la Nota de Crédito emitida
    para una devolución a paciente.

    No emite ningún comprobante nuevo.
    """
    devolucion = get_object_or_404(
        DevolucionPaciente,
        id=devolucion_id,
    )

    if (
        not devolucion.nc_serie
        or not devolucion.nc_numero
    ):
        messages.error(
            request,
            (
                "Esta devolución todavía no tiene "
                "una Nota de Crédito emitida."
            ),
        )
        return redirect("pagos:historial")

    try:
        resultado = obtener_pdf_cfe_por_folio(
            tipo_cfe=102,
            serie=devolucion.nc_serie,
            numero=devolucion.nc_numero,
        )

    except FactureError as exc:
        messages.error(
            request,
            (
                "No se pudo obtener el PDF de la "
                f"Nota de Crédito: {exc}"
            ),
        )
        return redirect("pagos:historial")

    if not resultado.get("ok"):
        detalle = resultado.get(
            "error",
            {},
        )

        messages.error(
            request,
            (
                "Facture no pudo generar el PDF "
                "de la Nota de Crédito "
                f"(HTTP {resultado.get('status')}): "
                f"{detalle}"
            ),
        )
        return redirect("pagos:historial")

    response = HttpResponse(
        resultado["content"],
        content_type="application/pdf",
    )

    response["Content-Disposition"] = (
        f'inline; filename="'
        f'NC_DEV_{devolucion.nc_serie}_'
        f'{devolucion.nc_numero}.pdf"'
    )

    return response


def facture_xml_nota_credito_devolucion(
    request,
    devolucion_id,
):
    """
    Descarga el XML firmado de una Nota de Crédito
    asociada a una devolución.

    No realiza ninguna llamada de emisión.
    """
    devolucion = get_object_or_404(
        DevolucionPaciente,
        id=devolucion_id,
    )

    if not devolucion.nc_xml_firmado:
        messages.warning(
            request,
            (
                "Esta devolución todavía no tiene "
                "XML de Nota de Crédito guardado."
            ),
        )
        return redirect("pagos:historial")

    response = HttpResponse(
        devolucion.nc_xml_firmado,
        content_type=(
            "application/xml; charset=utf-8"
        ),
    )

    response["Content-Disposition"] = (
        f'attachment; filename="'
        f'NC_DEV_{devolucion.nc_serie}_'
        f'{devolucion.nc_numero}.xml"'
    )

    return response