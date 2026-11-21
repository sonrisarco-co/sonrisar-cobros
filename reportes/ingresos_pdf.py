from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas

from .templatetags.importes import importe_uy


def generar_ingresos_anuales_pdf(year, meses, filas, total):
    archivo = BytesIO()
    ancho, alto = landscape(A4)
    pdf = Canvas(archivo, pagesize=(ancho, alto))
    pdf.setTitle(f"Comparación anual de ingresos · {year}")
    margen = 30
    tinta = colors.HexColor("#0f172a")
    turquesa = colors.HexColor("#115e59")
    pdf.setFillColor(turquesa)
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(margen, alto - 32, "Sonrisar Cobros")
    pdf.setFillColor(tinta)
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(margen, alto - 56, f"Comparación anual de ingresos · {year}")
    pdf.setFont("Helvetica", 9)
    pdf.drawString(margen, alto - 73, "Pagos por fecha de registro · Pesos uruguayos (UYU)")

    encabezado = ["Día", *(mes["nombre"] for mes in meses)]
    subtotales = ["Total mes", *(importe_uy(mes["total"]) for mes in meses)]
    datos = [
        [str(dia), *("—" if valor is None else importe_uy(valor) for valor in fila)]
        for dia, fila in enumerate(filas, start=1)
    ]
    ancho_dia = 49
    ancho_mes = (ancho - 2 * margen - ancho_dia) / 12
    altura_fila = 13
    y = alto - 89
    for indice, fila in enumerate([encabezado, *datos, subtotales]):
        destacada = indice in (0, len(datos) + 1)
        fondo = "#e3f3f1" if destacada else ("#f5f8fa" if indice % 2 == 0 else "#ffffff")
        pdf.setFillColor(colors.HexColor(fondo))
        pdf.rect(margen, y - altura_fila, ancho - 2 * margen, altura_fila, fill=1, stroke=0)
        pdf.setFillColor(turquesa if destacada else tinta)
        fuente = "Helvetica-Bold" if destacada else "Helvetica"
        pdf.setFont(fuente, 8)
        pdf.drawString(margen + 5, y - 9, fila[0])
        for mes, valor in enumerate(fila[1:], start=1):
            derecha = margen + ancho_dia + mes * ancho_mes
            medida = stringWidth(valor, fuente, 8)
            pdf.setFont(fuente, 8 * min(1, (ancho_mes - 8) / medida) if medida else 8)
            pdf.drawRightString(derecha - 5, y - 9, valor)
        y -= altura_fila

    pdf.setStrokeColor(turquesa)
    pdf.line(margen, y, ancho - margen, y)
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawRightString(ancho - margen, y - 24, f"Total anual   $ {importe_uy(total)}")
    pdf.showPage()
    pdf.save()
    archivo.seek(0)
    return archivo
