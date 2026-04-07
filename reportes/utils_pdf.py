# reportes/utils_pdf.py
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib import colors
from django.conf import settings
import os

COLOR_SONRISAR = colors.HexColor("#26ABA5")

def generar_pdf_reporte(mes_nombre, year, datos):
    ruta_pdf = os.path.join(settings.BASE_DIR, "reporte_temp.pdf")

    c = canvas.Canvas(ruta_pdf, pagesize=letter)
    ancho, alto = letter

    # ============================
    #  MARCA DE AGUA SONRISAR
    # ============================
    logo_path = os.path.join(settings.BASE_DIR, "static/img/logo.png")
    if os.path.exists(logo_path):
        c.saveState()
        c.setFillAlpha(0.08)          # transparencia suave
        marca_ancho = 420             # tamaño grande
        marca_alto = 420
        c.drawImage(
            logo_path,
            (ancho - marca_ancho) / 2,
            (alto - marca_alto) / 2,
            width=marca_ancho,
            height=marca_alto,
            preserveAspectRatio=True,
            mask='auto'
        )
        c.restoreState()

    # ============================
    #  LOGO CHICO ARRIBA
    # ============================
    if os.path.exists(logo_path):
        c.drawImage(logo_path, 30, alto - 80, width=150, preserveAspectRatio=True)

    # ============================
    #  TÍTULOS
    # ============================
    c.setFont("Helvetica-Bold", 20)
    c.setFillColor(COLOR_SONRISAR)
    c.drawCentredString(ancho / 2, alto - 40, "Reporte Mensual")

    c.setFont("Helvetica", 14)
    c.setFillColor(colors.black)
    c.drawCentredString(ancho / 2, alto - 60, f"{mes_nombre} {year}")

    y = alto - 110

    # ============================
    #  RESUMEN GENERAL
    # ============================
    c.setFont("Helvetica-Bold", 14)
    c.setFillColor(COLOR_SONRISAR)
    c.drawString(30, y, "Resumen General")
    y -= 20

    c.setFont("Helvetica", 12)
    c.setFillColor(colors.black)
    c.drawString(40, y, f"Total Pagado del Mes: ${datos['total_pagado']:,}")
    y -= 20
    c.drawString(40, y, f"Entradas de Caja: ${datos['entradas']:,}")
    y -= 20
    c.drawString(40, y, f"Salidas de Caja: ${datos['salidas']:,}")
    y -= 20

    balance = datos["entradas"] - datos["salidas"]
    c.drawString(40, y, f"Balance de Movimientos: ${balance:,}")
    y -= 35

    # ============================
    #  MÉTODOS DE PAGO
    # ============================
    c.setFont("Helvetica-Bold", 14)
    c.setFillColor(COLOR_SONRISAR)
    c.drawString(30, y, "Métodos de Pago")
    y -= 25

    # Encabezado
    c.setFillColor(colors.white)
    c.setStrokeColor(COLOR_SONRISAR)
    c.setFillColor(COLOR_SONRISAR)
    c.rect(30, y - 20, 500, 20, fill=True, stroke=False)

    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y - 15, "Método")
    c.drawString(300, y - 15, "Total")

    y -= 35
    c.setFont("Helvetica", 12)
    c.setFillColor(colors.black)

    for item in datos["pagos_por_metodo"]:
        metodo = item["metodo"].capitalize()
        total = f"${item['total']:,}"

        c.drawString(40, y, metodo)
        c.drawString(300, y, total)
        y -= 20

    c.showPage()
    c.save()

    return ruta_pdf
