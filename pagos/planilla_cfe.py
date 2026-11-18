from decimal import Decimal

from django.http import HttpResponse
from django.utils.timezone import localtime
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill


COLUMNAS = (
    "Emisión CFE", "Fecha de pago", "Tipo", "Serie", "Número",
    "Medio de pago", "Tasa IVA", "Neto ($)", "IVA ($)", "Total ($)",
)


def filas_planilla_cfe(pagos):
    for pago in pagos:
        yield (
            pago.cfe_fecha_emision,
            localtime(pago.fecha).date(),
            pago.cfe_tipo,
            pago.cfe_serie,
            pago.cfe_numero,
            pago.metodo_detallado,
            pago.tasa_iva_cfe,
            pago.monto_neto_cfe,
            pago.monto_iva_cfe,
            pago.monto,
        )


def descargar_planilla_cfe(pagos):
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Pagos con CFE"
    hoja.append(COLUMNAS)
    hoja.freeze_panes = "A2"
    for celda in hoja[1]:
        celda.font = Font(bold=True, color="FFFFFF")
        celda.fill = PatternFill("solid", fgColor="147873")

    totales = [Decimal("0.00")] * 3
    for fila in filas_planilla_cfe(pagos):
        for indice, importe in enumerate(fila[-3:]):
            totales[indice] += importe
        hoja.append(fila)
        for celda in hoja[hoja.max_row]:
            if celda.column in (3, 4, 5, 6):
                # Conservar identificadores como texto, incluidos ceros iniciales.
                celda.data_type = "s"
            elif celda.column in (1, 2):
                celda.number_format = "dd/mm/yyyy"
            elif celda.column == 7:
                celda.value /= 100
                celda.number_format = "0.00%"
            else:
                celda.number_format = "#,##0.00"

    for celda in hoja[1]:
        hoja.column_dimensions[celda.column_letter].width = max(15, len(celda.value) + 3)
    hoja.auto_filter.ref = hoja.dimensions
    if hoja.max_row > 1:
        hoja.append(("Totales de la planilla", *([None] * 6), *totales))
        for celda in hoja[hoja.max_row]:
            celda.font = Font(bold=True)
            if celda.column >= 8:
                celda.number_format = "#,##0.00"

    respuesta = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    respuesta["Content-Disposition"] = 'attachment; filename="Sonrisar_Pagos_CFE.xlsx"'
    libro.save(respuesta)
    return respuesta
