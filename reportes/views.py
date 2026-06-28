# reportes/views.py
from django.shortcuts import render, redirect
from django.http import FileResponse, HttpResponse
from django.db.models import Sum
from urllib.parse import quote
from datetime import datetime
import datetime as datetime_module

from pagos.models import Pago, Gasto
from caja.models import MovimientoCaja

from .utils_pdf import generar_pdf_reporte


# ---------------------------------------
#  Nombre de los meses
# ---------------------------------------
MESES_ES = [
    "", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]


# ---------------------------------------
#  PROTECCIÓN CON PIN PARA REPORTES
# ---------------------------------------
def _validar_pin_reportes(request):
    """
    Reutiliza el mismo PIN que ya usa caja/validar-pin/.
    Una vez validado, deja Reportes habilitado durante la sesión actual.
    """
    if request.session.get("reportes_pin_ok"):
        return None

    full_path = request.get_full_path()
    permitido = request.session.get("pin_ok")

    if permitido == full_path:
        request.session.pop("pin_ok", None)
        request.session["reportes_pin_ok"] = True
        return None

    return redirect(
        f"/caja/validar-pin/?next={quote(full_path)}"
    )


# ---------------------------------------
#  FUNCIÓN PARA OBTENER EL CONTEXTO
# ---------------------------------------
def obtener_contexto_reporte(year, month):

    pagos_mes = Pago.objects.filter(
        fecha__year=year,
        fecha__month=month
    )

    total_pagado = pagos_mes.aggregate(Sum("monto"))["monto__sum"] or 0

    gastos_mes = Gasto.objects.filter(
        fecha__year=year,
        fecha__month=month
    )

    total_gastos = gastos_mes.aggregate(Sum("monto"))["monto__sum"] or 0
    resultado_real = total_pagado - total_gastos

    gastos_por_categoria = gastos_mes.values("categoria").annotate(
        total=Sum("monto")
    ).order_by("-total")

    pagos_por_metodo = pagos_mes.values("metodo").annotate(
        total=Sum("monto")
    )

    promedio_por_paciente = pagos_mes.values("paciente").annotate(
        total=Sum("monto")
    )

    ranking_pacientes = pagos_mes.values("paciente").annotate(
        total=Sum("monto")
    ).order_by("-total")[:5]

    movs_mes = MovimientoCaja.objects.filter(
        fecha__year=year,
        fecha__month=month
    )

    entradas = movs_mes.filter(tipo="entrada").aggregate(
        Sum("monto")
    )["monto__sum"] or 0

    salidas = movs_mes.filter(tipo="salida").aggregate(
        Sum("monto")
    )["monto__sum"] or 0

    balance_mov = entradas - salidas

    contexto = {
        "mes_nombre": MESES_ES[month],
        "year": year,
        "month": month,

        "total_pagado": total_pagado,
        "pagos_por_metodo": pagos_por_metodo,
        "promedio_por_paciente": promedio_por_paciente,
        "ranking_pacientes": ranking_pacientes,

        "entradas": entradas,
        "salidas": salidas,
        "balance_mov": balance_mov,
        "total_gastos": total_gastos,
        "resultado_real": resultado_real,
        "gastos_por_categoria": gastos_por_categoria,
    }

    return contexto


# ---------------------------------------
#  REPORTE HTML
# ---------------------------------------
def reporte_mensual(request, year, month):
    bloqueo = _validar_pin_reportes(request)
    if bloqueo:
        return bloqueo

    contexto = obtener_contexto_reporte(year, month)
    return render(request, "reportes/mensual.html", contexto)


# ---------------------------------------
#  EXPORTAR PDF (ReportLab)
# ---------------------------------------
def exportar_pdf(request, year, month):
    bloqueo = _validar_pin_reportes(request)
    if bloqueo:
        return bloqueo

    contexto = obtener_contexto_reporte(year, month)

    ruta_pdf = generar_pdf_reporte(
        contexto["mes_nombre"],
        year,
        contexto,
    )

    return FileResponse(
        open(ruta_pdf, "rb"),
        filename=f"Reporte_{contexto['mes_nombre']}_{contexto['year']}.pdf",
        content_type="application/pdf"
    )


# ---------------------------------------
#  HOME SIMPLE PARA TEST
# ---------------------------------------
def home(request):
    return HttpResponse("Reportes OK")


def selector_reportes(request):
    bloqueo = _validar_pin_reportes(request)
    if bloqueo:
        return bloqueo

    hoy = datetime_module.date.today()

    if request.method == "POST":
        year = request.POST.get("year")
        month = request.POST.get("month")
        return redirect("reportes:reporte_mensual", year=year, month=month)

    contexto = {
        "year_actual": hoy.year,
        "years": range(hoy.year - 5, hoy.year + 1),
        "months": [
            (1, "Enero"), (2, "Febrero"), (3, "Marzo"), (4, "Abril"),
            (5, "Mayo"), (6, "Junio"), (7, "Julio"), (8, "Agosto"),
            (9, "Septiembre"), (10, "Octubre"), (11, "Noviembre"), (12, "Diciembre")
        ]
    }

    return render(request, "reportes/selector.html", contexto)


def selector(request):
    bloqueo = _validar_pin_reportes(request)
    if bloqueo:
        return bloqueo

    years = range(2023, datetime.now().year + 1)
    meses = list(enumerate(MESES_ES))[1:]

    return render(request, "reportes/selector.html", {
        "years": years,
        "meses": meses
    })
