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


def nuevo_pago(request):
    if request.method == "POST":
        caja = CashSession.obtener_caja_del_dia()

        monto = request.POST.get("monto")
        paciente = request.POST.get("paciente", "")
        concepto = request.POST.get("concepto", "")
        metodo = request.POST.get("metodo")
        next_url = request.POST.get("next", "").strip()
        appointment_id = request.POST.get("appointment_id") or None
        patient_id = request.POST.get("patient_id") or None

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


def api_pagos_por_paciente(request):
    paciente = request.GET.get("paciente", "").strip()

    if not paciente:
        return JsonResponse({
            "ok": False,
            "error": "Falta el parámetro paciente."
        }, status=400)

    pagos = (
        Pago.objects
        .filter(paciente__iexact=paciente)
        .order_by("-fecha")[:20]
    )

    data = []
    for pago in pagos:
        data.append({
            "id": pago.id,
            "paciente": pago.paciente,
            "monto": str(pago.monto),
            "metodo": pago.get_metodo_display(),
            "concepto": pago.concepto or "",
            "fecha": localtime(pago.fecha).strftime("%d/%m/%Y %H:%M"),
            "appointment_id": pago.appointment_id,
            "patient_id": pago.patient_id,
        })

    return JsonResponse({
        "ok": True,
        "paciente": paciente,
        "total": len(data),
        "pagos": data,
    })


def api_pago_por_cita(request):
    appointment_id = request.GET.get("appointment_id", "").strip()

    if not appointment_id:
        return JsonResponse({
            "ok": False,
            "error": "Falta el parámetro appointment_id."
        }, status=400)

    pagos = (
        Pago.objects
        .filter(appointment_id=appointment_id)
        .order_by("-fecha")
    )

    data = []
    total_pagado = 0
    tipo_pago = "pagado"

    for pago in pagos:
        monto = pago.monto or 0
        total_pagado += monto

        concepto_texto = (pago.concepto or "").strip().lower()

        if "seña" in concepto_texto or "sena" in concepto_texto or "adelanto" in concepto_texto:
            tipo_pago = "sena"

        data.append({
            "id": pago.id,
            "paciente": pago.paciente,
            "monto": str(pago.monto),
            "metodo": pago.get_metodo_display(),
            "concepto": pago.concepto or "",
            "fecha": localtime(pago.fecha).strftime("%d/%m/%Y %H:%M"),
            "appointment_id": pago.appointment_id,
            "patient_id": pago.patient_id,
        })

    return JsonResponse({
        "ok": True,
        "appointment_id": appointment_id,
        "total": len(data),
        "total_pagado": str(total_pagado),
        "tipo_pago": tipo_pago,
        "pagos": data,
    })