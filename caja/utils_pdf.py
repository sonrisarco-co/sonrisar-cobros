# caja/utils_pdf.py

from io import BytesIO
from decimal import Decimal
import os

from django.http import HttpResponse
from django.conf import settings

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
    Paragraph,
    Image,
)
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.enums import TA_RIGHT, TA_CENTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus.flowables import HRFlowable
from reportlab.lib.units import mm

from pagos.models import Pago, Gasto
from .models import MovimientoCaja


# =========================================================
# COLORES
# =========================================================

COLOR_PRINCIPAL = colors.HexColor("#26ABA5")
COLOR_TEXTO = colors.HexColor("#303030")
COLOR_VERDE = colors.HexColor("#1F8B3B")
COLOR_ROJO = colors.HexColor("#D62828")
COLOR_NARANJA = colors.HexColor("#E58A1F")
COLOR_BORDE = colors.HexColor("#DCE5E8")
COLOR_FONDO = colors.HexColor("#F8FBFC")


# =========================================================
# FORMATO DINERO
# =========================================================

def money(valor):

    return (
        f"$ {valor:,.2f}"
        .replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )


# =========================================================
# PDF
# =========================================================

def generar_pdf_cierre(caja):

    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=12 * mm,
        leftMargin=12 * mm,
        topMargin=10 * mm,
        bottomMargin=8 * mm,
    )

    elementos = []

    styles = getSampleStyleSheet()

    # =====================================================
    # ESTILOS
    # =====================================================

    titulo_style = ParagraphStyle(
        "titulo",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=22,
        leading=24,
        textColor=COLOR_PRINCIPAL,
        alignment=TA_RIGHT,
    )

    info_style = ParagraphStyle(
        "info",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=COLOR_TEXTO,
        alignment=TA_RIGHT,
    )

    footer_style = ParagraphStyle(
        "footer",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=11,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#667085"),
    )

    # =====================================================
    # DATOS
    # =====================================================

    pagos = Pago.objects.filter(
        fecha__date=caja.fecha
    )

    gastos = Gasto.objects.filter(
        fecha__date=caja.fecha,
        afecta_caja=True
    )

    gastos_efectivo = gastos.filter(
        metodo="efectivo"
    )

    movimientos = MovimientoCaja.objects.filter(
        caja=caja
    )

    total_pagos = sum(
        [p.monto for p in pagos],
        Decimal("0.00")
    )

    efectivo = sum(
        [
            p.monto
            for p in pagos.filter(metodo="efectivo")
        ],
        Decimal("0.00")
    )

    tarjeta = sum(
        [
            p.monto
            for p in pagos.filter(metodo="tarjeta")
        ],
        Decimal("0.00")
    )

    transferencia = sum(
        [
            p.monto
            for p in pagos.filter(metodo="transferencia")
        ],
        Decimal("0.00")
    )

    total_gastos = sum(
        [g.monto for g in gastos],
        Decimal("0.00")
    )

    total_gastos_efectivo = sum(
        [g.monto for g in gastos_efectivo],
        Decimal("0.00")
    )

    total_entradas = sum(
        [
            m.monto
            for m in movimientos.filter(tipo="entrada")
        ],
        Decimal("0.00")
    )

    total_salidas = sum(
        [
            m.monto
            for m in movimientos.filter(tipo="salida")
        ],
        Decimal("0.00")
    )

    balance_movimientos = (
        total_entradas - total_salidas
    )

    resultado_general = (
        total_pagos
        + total_entradas
        - total_gastos
        - total_salidas
    )

    efectivo_esperado = (
        (caja.saldo_inicial or Decimal("0.00"))
        + efectivo
        + total_entradas
        - total_gastos_efectivo
        - total_salidas
    )

    efectivo_contado = (
        caja.saldo_final_declarado
        or Decimal("0.00")
    )

    diferencia = (
        efectivo_contado
        - efectivo_esperado
    )

    # =====================================================
    # LOGO
    # =====================================================

    logo_path = os.path.join(
        settings.BASE_DIR,
        "static",
        "img",
        "logo.png"
    )

    if os.path.exists(logo_path):

        logo = Image(
            logo_path,
            width=60 * mm,
            height=25 * mm,
            kind='proportional'
        )

    else:

        logo = Paragraph(
            "SONRISAR",
            styles["Heading2"]
        )

    # =====================================================
    # CABECERA
    # =====================================================

    derecha = [

        Paragraph(
            "Cierre de Caja",
            titulo_style
        ),

        Spacer(1, 2),

        Paragraph(
            f"<b>Fecha:</b> "
            f"{caja.fecha.strftime('%d/%m/%Y')}",
            info_style
        ),

        Paragraph(
            f"<b>Estado:</b> "
            f"{caja.estado.upper()}",
            info_style
        ),
    ]

    cabecera = Table(
        [[logo, derecha]],
        colWidths=[95 * mm, 85 * mm]
    )

    cabecera.setStyle(TableStyle([

        ("VALIGN", (0, 0), (-1, -1), "TOP"),

        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
    ]))

    elementos.append(cabecera)

    elementos.append(
        Spacer(1, 6 * mm)
    )

    # =====================================================
    # RESUMEN GENERAL
    # =====================================================

    resumen_data = [

        ["Ingresos totales", money(total_pagos)],

        ["Gastos", money(total_gastos)],

        ["Balance movimientos", money(balance_movimientos)],

        ["Resultado general", money(resultado_general)],
    ]

    resumen = Table(
        resumen_data,
        colWidths=[95 * mm, 85 * mm],
        rowHeights=9 * mm
    )

    resumen.setStyle(TableStyle([

        ("BACKGROUND", (0, 0), (-1, -1), colors.white),

        ("GRID", (0, 0), (-1, -1), 0.5, COLOR_BORDE),

        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),

        ("FONTSIZE", (0, 0), (-1, -1), 10),

        ("ALIGN", (1, 0), (1, -1), "RIGHT"),

        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),

        ("TOPPADDING", (0, 0), (-1, -1), 7),

        ("TEXTCOLOR", (0, 0), (-1, -1), COLOR_TEXTO),

        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
    ]))

    elementos.append(
        Paragraph(
            "<b>Resumen general</b>",
            styles["Heading3"]
        )
    )

    elementos.append(
        Spacer(1, 2 * mm)
    )

    elementos.append(resumen)

    elementos.append(
        Spacer(1, 6 * mm)
    )

    # =====================================================
    # CAJA FÍSICA
    # =====================================================

    caja_data = [

        [
            "Saldo inicial",
            money(caja.saldo_inicial or Decimal("0.00"))
        ],

        [
            "Efectivo cobrado",
            money(efectivo)
        ],

        [
            "Entradas manuales",
            money(total_entradas)
        ],

        [
            "Gastos / salidas en efectivo",
            money(total_gastos_efectivo + total_salidas)
        ],

        [
            "Efectivo esperado",
            money(efectivo_esperado)
        ],

        [
            "Efectivo contado",
            money(efectivo_contado)
        ],

        [
            "Diferencia",
            money(diferencia)
        ],
    ]

    caja_table = Table(
        caja_data,
        colWidths=[95 * mm, 85 * mm],
        rowHeights=10 * mm
    )

    caja_table.setStyle(TableStyle([

        ("BOX", (0, 0), (-1, -1), 1, COLOR_PRINCIPAL),

        ("GRID", (0, 0), (-1, -1), 0.4, COLOR_BORDE),

        ("BACKGROUND", (0, 4), (-1, 5), colors.HexColor("#F5FFFD")),

        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),

        ("FONTSIZE", (0, 0), (-1, -1), 10.5),

        ("ALIGN", (1, 0), (1, -1), "RIGHT"),

        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),

        ("TOPPADDING", (0, 0), (-1, -1), 7),

        ("FONTNAME", (0, 4), (-1, 6), "Helvetica-Bold"),

        ("TEXTCOLOR", (0, 6), (1, 6),
            COLOR_VERDE if diferencia == 0
            else COLOR_ROJO
        ),
    ]))

    elementos.append(
        Paragraph(
            "<b>Caja física</b>",
            styles["Heading3"]
        )
    )

    elementos.append(
        Spacer(1, 2 * mm)
    )

    elementos.append(caja_table)

    elementos.append(
        Spacer(1, 6 * mm)
    )

    # =====================================================
    # MEDIOS DIGITALES
    # =====================================================

    medios_data = [

        ["Transferencias", money(transferencia)],

        ["Tarjetas", money(tarjeta)],
    ]

    medios = Table(
        medios_data,
        colWidths=[95 * mm, 85 * mm],
        rowHeights=9 * mm
    )

    medios.setStyle(TableStyle([

        ("GRID", (0, 0), (-1, -1), 0.4, COLOR_BORDE),

        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FAFCFC")),

        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),

        ("FONTSIZE", (0, 0), (-1, -1), 10),

        ("ALIGN", (1, 0), (1, -1), "RIGHT"),

        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),

        ("TOPPADDING", (0, 0), (-1, -1), 7),
    ]))

    elementos.append(
        Paragraph(
            "<b>Medios digitales</b>",
            styles["Heading3"]
        )
    )

    elementos.append(
        Spacer(1, 2 * mm)
    )

    elementos.append(medios)

    elementos.append(
        Spacer(1, 10 * mm)
    )

    # =====================================================
    # MENSAJE FINAL
    # =====================================================

    if diferencia == 0:

        estado_final = Paragraph(
            "<font color='#1F8B3B'><b>✔ Caja cerrada correctamente</b></font>",
            styles["BodyText"]
        )

    else:

        estado_final = Paragraph(
            "<font color='#D62828'><b>⚠ Diferencia detectada en caja</b></font>",
            styles["BodyText"]
        )

    elementos.append(estado_final)

    elementos.append(
        Spacer(1, 8 * mm)
    )

    # =====================================================
    # FOOTER
    # =====================================================

    footer_line = HRFlowable(
        width="100%",
        thickness=1,
        color=COLOR_PRINCIPAL
    )

    elementos.append(footer_line)

    elementos.append(
        Spacer(1, 3 * mm)
    )

    footer_data = Table(
        [[
            "📍 Román Guerra 752",
            "☎ 092706293",
            "📷 sonrisar_",
            "✉ sonrisarco@gmail.com",
        ]],
        colWidths=[
            45 * mm,
            40 * mm,
            40 * mm,
            55 * mm,
        ]
    )

    footer_data.setStyle(TableStyle([

        ("ALIGN", (0, 0), (-1, -1), "CENTER"),

        ("TEXTCOLOR", (0, 0), (-1, -1),
            colors.HexColor("#64748b")
        ),

        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),

        ("FONTSIZE", (0, 0), (-1, -1), 8),
    ]))

    elementos.append(footer_data)

    elementos.append(
        Spacer(1, 3 * mm)
    )

    footer_text = Paragraph(
        """
        Documento generado automáticamente por Sistema Sonrisar
        """,
        footer_style
    )

    elementos.append(footer_text)

    doc.build(elementos)

    pdf = buffer.getvalue()

    buffer.close()

    response = HttpResponse(
        content_type="application/pdf"
    )

    response["Content-Disposition"] = (
        f'inline; filename="cierre_{caja.fecha}.pdf"'
    )

    response.write(pdf)

    return response