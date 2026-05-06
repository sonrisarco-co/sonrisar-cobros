# reportes/utils_pdf.py
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from django.conf import settings
import os

COLOR_SONRISAR = colors.HexColor("#26ABA5")
COLOR_TEXTO = colors.HexColor("#263238")
COLOR_ROJO = colors.HexColor("#B42318")
COLOR_VERDE = colors.HexColor("#15803D")
COLOR_GRIS = colors.HexColor("#F4F8F8")


def money(valor):
    try:
        return f"${valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return f"${valor}"


def nueva_pagina_si_necesita(c, y, minimo=90):
    if y < minimo:
        c.showPage()
        return 720
    return y


def titulo_seccion(c, y, texto):
    c.setFillColor(COLOR_SONRISAR)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, y, texto)
    c.setStrokeColor(COLOR_SONRISAR)
    c.line(40, y - 6, 555, y - 6)
    return y - 24


def fila_tabla(c, y, col1, col2, color_col2=COLOR_TEXTO):
    c.setFillColor(COLOR_TEXTO)
    c.setFont("Helvetica", 10)
    c.drawString(50, y, str(col1))

    c.setFillColor(color_col2)
    c.setFont("Helvetica-Bold", 10)
    c.drawRightString(545, y, str(col2))

    c.setStrokeColor(colors.HexColor("#E6EEEE"))
    c.line(45, y - 6, 550, y - 6)

    return y - 18


def generar_pdf_reporte(mes_nombre, year, datos):
    ruta_pdf = os.path.join(settings.BASE_DIR, "reporte_temp.pdf")

    c = canvas.Canvas(ruta_pdf, pagesize=letter)
    ancho, alto = letter

    logo_path = os.path.join(settings.BASE_DIR, "static/img/logo.png")

    # MARCA DE AGUA
    if os.path.exists(logo_path):
        c.saveState()
        c.setFillAlpha(0.06)
        marca_ancho = 430
        marca_alto = 430
        c.drawImage(
            logo_path,
            (ancho - marca_ancho) / 2,
            210,
            width=marca_ancho,
            height=marca_alto,
            preserveAspectRatio=True,
            mask="auto"
        )
        c.restoreState()

    # LOGO ARRIBA
    if os.path.exists(logo_path):
        c.drawImage(
            logo_path,
            40,
            alto - 82,
            width=130,
            height=55,
            preserveAspectRatio=True,
            mask="auto"
        )

    # TITULO
    c.setFillColor(COLOR_TEXTO)
    c.setFont("Helvetica-Bold", 24)
    c.drawRightString(ancho - 40, alto - 45, "Reporte Mensual")

    c.setFillColor(COLOR_SONRISAR)
    c.setFont("Helvetica-Bold", 15)
    c.drawRightString(ancho - 40, alto - 68, f"{mes_nombre} {year}")

    y = alto - 120

    total_pagado = datos.get("total_pagado", 0)
    total_gastos = datos.get("total_gastos", 0)
    resultado_real = datos.get("resultado_real", total_pagado - total_gastos)

    # KPIS
    card_w = 165
    card_h = 62
    x_positions = [40, 215, 390]

    kpis = [
        ("Ingresos por pagos", money(total_pagado), COLOR_TEXTO),
        ("Gastos del mes", "-" + money(total_gastos), COLOR_ROJO),
        ("Resultado real", money(resultado_real), COLOR_VERDE if resultado_real >= 0 else COLOR_ROJO),
    ]

    for i, (label, valor, color_valor) in enumerate(kpis):
        x = x_positions[i]
        c.setFillColor(colors.white)
        c.setStrokeColor(colors.HexColor("#D9EEEE"))
        c.roundRect(x, y - card_h, card_w, card_h, 10, fill=True, stroke=True)

        c.setFillColor(colors.HexColor("#667777"))
        c.setFont("Helvetica-Bold", 9)
        c.drawString(x + 12, y - 22, label)

        c.setFillColor(color_valor)
        c.setFont("Helvetica-Bold", 16)
        c.drawString(x + 12, y - 45, valor)

    y -= 95

    # MOVIMIENTOS
    y = titulo_seccion(c, y, "Movimientos de caja")
    y = fila_tabla(c, y, "Entradas manuales", money(datos.get("entradas", 0)))
    y = fila_tabla(c, y, "Salidas manuales", money(datos.get("salidas", 0)), COLOR_ROJO)
    y = fila_tabla(c, y, "Balance de movimientos", money(datos.get("balance_mov", 0)))
    y -= 18

    # METODOS DE PAGO
    y = nueva_pagina_si_necesita(c, y)
    y = titulo_seccion(c, y, "Métodos de pago")

    pagos_por_metodo = datos.get("pagos_por_metodo", [])
    if pagos_por_metodo:
        for item in pagos_por_metodo:
            y = nueva_pagina_si_necesita(c, y)
            metodo = str(item.get("metodo", "")).capitalize()
            total = item.get("total", 0)
            y = fila_tabla(c, y, metodo, money(total))
    else:
        c.setFillColor(colors.gray)
        c.setFont("Helvetica-Oblique", 10)
        c.drawString(50, y, "No hay pagos registrados.")
        y -= 20

    y -= 18

    # GASTOS POR CATEGORIA
    y = nueva_pagina_si_necesita(c, y)
    y = titulo_seccion(c, y, "Gastos por categoría")

    gastos_por_categoria = datos.get("gastos_por_categoria", [])
    if gastos_por_categoria:
        for item in gastos_por_categoria:
            y = nueva_pagina_si_necesita(c, y)
            categoria = str(item.get("categoria", "")).capitalize()
            total = item.get("total", 0)
            y = fila_tabla(c, y, categoria, "-" + money(total), COLOR_ROJO)
    else:
        c.setFillColor(colors.gray)
        c.setFont("Helvetica-Oblique", 10)
        c.drawString(50, y, "No hay gastos registrados.")
        y -= 20

    y -= 18

    

    # FOOTER
    c.setFillColor(colors.gray)
    c.setFont("Helvetica", 9)
    c.drawCentredString(ancho / 2, 30, "Sonrisar Centro Odontológico - Reporte generado automáticamente")

    c.showPage()
    c.save()

    return ruta_pdf