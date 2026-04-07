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

        Pago.objects.create(
            monto=monto,
            paciente=paciente,
            concepto=concepto,
            metodo=metodo,
            caja=caja
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
        })

    return JsonResponse({
        "ok": True,
        "paciente": paciente,
        "total": len(data),
        "pagos": data,
    })