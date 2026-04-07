# reportes/views.py
from django.shortcuts import render
from django.http import FileResponse, HttpResponse
from django.db.models import Sum

from pagos.models import Pago
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
#  FUNCIÓN PARA OBTENER EL CONTEXTO
# ---------------------------------------
def obtener_contexto_reporte(year, month):

    pagos_mes = Pago.objects.filter(
        fecha__year=year,
        fecha__month=month
    )

    total_pagado = pagos_mes.aggregate(Sum("monto"))["monto__sum"] or 0

    pagos_por_metodo = pagos_mes.values("metodo").annotate(total=Sum("monto"))
    promedio_por_paciente = pagos_mes.values("paciente").annotate(total=Sum("monto"))

    ranking_pacientes = pagos_mes.values("paciente").annotate(
        total=Sum("monto")
    ).order_by("-total")[:5]

    movs_mes = MovimientoCaja.objects.filter(
        fecha__year=year,
        fecha__month=month
    )

    entradas = movs_mes.filter(tipo="entrada").aggregate(Sum("monto"))["monto__sum"] or 0
    salidas = movs_mes.filter(tipo="salida").aggregate(Sum("monto"))["monto__sum"] or 0
    balance_mov = entradas - salidas

    # ---- CONTEXTO COMPLETO (IMPORTANTE: year y month INCLUIDOS) ----
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
    }

    return contexto


# ---------------------------------------
#  REPORTE HTML
# ---------------------------------------
def reporte_mensual(request, year, month):
    contexto = obtener_contexto_reporte(year, month)
    return render(request, "reportes/mensual.html", contexto)


# ---------------------------------------
#  EXPORTAR PDF (ReportLab)
# ---------------------------------------
def exportar_pdf(request, year, month):

    contexto = obtener_contexto_reporte(year, month)

    # Generar PDF temporal
    ruta_pdf = generar_pdf_reporte(
        contexto["mes_nombre"],
        year,
        contexto,
    )

    # Retornar PDF al navegador
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


from django.shortcuts import redirect
import datetime

def selector_reportes(request):
    hoy = datetime.date.today()

    if request.method == "POST":
        year = request.POST.get("year")
        month = request.POST.get("month")
        return redirect("reportes:reporte_mensual", year=year, month=month)

    contexto = {
        "year_actual": hoy.year,
        "years": range(hoy.year - 5, hoy.year + 1),
        "months": [
            (1,"Enero"), (2,"Febrero"), (3,"Marzo"), (4,"Abril"),
            (5,"Mayo"), (6,"Junio"), (7,"Julio"), (8,"Agosto"),
            (9,"Septiembre"), (10,"Octubre"), (11,"Noviembre"), (12,"Diciembre")
        ]
    }

    return render(request, "reportes/selector.html", contexto)


from datetime import datetime

def selector(request):
    years = range(2023, datetime.now().year + 1)

    MESES_ES = [
        "", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
        "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
    ]

    meses = list(enumerate(MESES_ES))[1:]

    return render(request, "reportes/selector.html", {
        "years": years,
        "meses": meses
    })

