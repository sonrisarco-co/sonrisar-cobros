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
        rightMargin=10 * mm,
        leftMargin=10 * mm,
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
        fontSize=16,
        leading=18,
        textColor=COLOR_PRINCIPAL,
        alignment=TA_RIGHT,
    )

    info_style = ParagraphStyle(
        "info",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=15,
        textColor=COLOR_TEXTO,
        alignment=TA_RIGHT,
    )

    footer_style = ParagraphStyle(
        "footer",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=12,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#666666"),
    )

    # =====================================================
    # DATOS
    # =====================================================

    pagos = Pago.objects.filter(
        fecha__date=caja.fecha
    )

    gastos = Gasto.objects.filter(
        fecha__date=caja.fecha
    )

    movimientos = MovimientoCaja.objects.filter(
        caja=caja
    )

    total_pagos = sum(
        [p.monto for p in pagos],
        Decimal("0.00")
    )

    total_gastos = sum(
        [g.monto for g in gastos],
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

    resultado_real = (
        total_pagos
        - total_gastos
        + balance_movimientos
    )

    total_calculado = (
        (caja.saldo_inicial or Decimal("0.00"))
        + resultado_real
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
            width=58 * mm,
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
        [
            [
                logo,
                derecha
            ]
        ],
        colWidths=[110 * mm, 70 * mm]
    )

    cabecera.setStyle(TableStyle([

        ("VALIGN", (0, 0), (-1, -1), "TOP"),

        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
    ]))

    elementos.append(cabecera)

    elementos.append(
        Spacer(1, 5 * mm)
    )

    # =====================================================
    # TITULO RESUMEN
    # =====================================================

    resumen_header = Table(
        [[
            "Resumen financiero"
        ]],
        colWidths=[190 * mm]
    )

    resumen_header.setStyle(TableStyle([

        ("BACKGROUND", (0, 0), (-1, -1), COLOR_FONDO),

        ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDE),

        ("TEXTCOLOR", (0, 0), (-1, -1), COLOR_PRINCIPAL),

        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),

        ("FONTSIZE", (0, 0), (-1, -1), 13),

        ("TOPPADDING", (0, 0), (-1, -1), 8),

        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),

        ("LEFTPADDING", (0, 0), (-1, -1), 12),
    ]))

    elementos.append(resumen_header)

    # =====================================================
    # TABLA RESUMEN
    # =====================================================

    resumen_data = [

        [
            "Saldo inicial",
            money(caja.saldo_inicial or Decimal("0.00"))
        ],

        [
            "Ingresos",
            money(total_pagos)
        ],

        [
            "Gastos",
            money(total_gastos)
        ],

        [
            "Resultado real",
            money(resultado_real)
        ],

        [
            "Balance movimientos",
            money(balance_movimientos)
        ],

        [
            "Saldo declarado",
            money(
                caja.saldo_final_declarado
                or Decimal("0.00")
            )
        ],
    ]

    resumen = Table(
        resumen_data,
        colWidths=[95 * mm, 95 * mm],
        rowHeights=10 * mm
    )

    resumen.setStyle(TableStyle([

        ("GRID", (0, 0), (-1, -1), 0.4, COLOR_BORDE),

        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),

        ("FONTSIZE", (0, 0), (-1, -1), 10.5),

        ("ALIGN", (1, 0), (1, -1), "RIGHT"),

        ("TOPPADDING", (0, 0), (-1, -1), 7),

        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),

        ("TEXTCOLOR", (0, 1), (1, 1), COLOR_VERDE),

        ("TEXTCOLOR", (0, 2), (1, 2), COLOR_ROJO),

        ("TEXTCOLOR", (0, 3), (1, 3), COLOR_VERDE),

        ("TEXTCOLOR", (0, 4), (1, 4), COLOR_NARANJA),

        ("FONTNAME", (0, 1), (-1, 4), "Helvetica-Bold"),
    ]))

    elementos.append(resumen)

    elementos.append(
        Spacer(1, 5 * mm)
    )

    # =====================================================
    # TOTAL CALCULADO
    # =====================================================

    total_table = Table(
        [[
            "TOTAL CALCULADO",
            money(total_calculado)
        ]],
        colWidths=[100 * mm, 70 * mm],
        rowHeights=12 * mm
    )

    total_table.setStyle(TableStyle([

        ("BOX", (0, 0), (-1, -1), 1, COLOR_VERDE),

        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F7FFF9")),

        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),

        ("TEXTCOLOR", (0, 0), (0, 0), COLOR_PRINCIPAL),

        ("TEXTCOLOR", (1, 0), (1, 0), COLOR_VERDE),

        ("FONTSIZE", (0, 0), (0, 0), 14),

        ("FONTSIZE", (1, 0), (1, 0), 20),

        ("ALIGN", (1, 0), (1, 0), "RIGHT"),

        ("LEFTPADDING", (0, 0), (0, 0), 12),

        ("RIGHTPADDING", (1, 0), (1, 0), 12),

        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))

    elementos.append(total_table)

    elementos.append(
        Spacer(1, 5 * mm)
    )

    # =====================================================
    # MEDIOS HEADER
    # =====================================================

    medios_header = Table(
        [[
            "Medios de pago"
        ]],
        colWidths=[190 * mm]
    )

    medios_header.setStyle(TableStyle([

        ("BACKGROUND", (0, 0), (-1, -1), COLOR_FONDO),

        ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDE),

        ("TEXTCOLOR", (0, 0), (-1, -1), COLOR_PRINCIPAL),

        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),

        ("FONTSIZE", (0, 0), (-1, -1), 13),

        ("TOPPADDING", (0, 0), (-1, -1), 8),

        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),

        ("LEFTPADDING", (0, 0), (-1, -1), 12),
    ]))

    elementos.append(medios_header)

    # =====================================================
    # TABLA MEDIOS
    # =====================================================

    medios_data = [

        [
            "Efectivo",
            money(caja.efectivo or Decimal("0.00"))
        ],

        [
            "Tarjeta",
            money(caja.tarjeta or Decimal("0.00"))
        ],

        [
            "Transferencia",
            money(caja.transferencia or Decimal("0.00"))
        ],

        [
            "Total pagos",
            money(total_pagos)
        ],
    ]

    medios = Table(
        medios_data,
        colWidths=[95 * mm, 95 * mm],
        rowHeights=9 * mm
    )

    medios.setStyle(TableStyle([

        ("GRID", (0, 0), (-1, -1), 0.4, COLOR_BORDE),

        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),

        ("FONTSIZE", (0, 0), (-1, -1), 10.5),

        ("ALIGN", (1, 0), (1, -1), "RIGHT"),

        ("TOPPADDING", (0, 0), (-1, -1), 6),

        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),

        ("TEXTCOLOR", (0, -1), (1, -1), COLOR_VERDE),

        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
    ]))

    elementos.append(medios)

    elementos.append(
        Spacer(1, 5 * mm)
    )

    
    # =====================================================
    # FOOTER
    # =====================================================

    elementos.append(
        Spacer(1, 8 * mm)
    )

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

        ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#475569")),

        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),

        ("FONTSIZE", (0, 0), (-1, -1), 8.5),

        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))

    elementos.append(footer_data)

    elementos.append(
        Spacer(1, 4 * mm)
    )

    footer_text = Paragraph(
        """
        Documento generado automáticamente por Sonrisar Pro<br/>
        Este documento no requiere firma.
        """,
        footer_style
    )

    elementos.append(footer_text)

    # =====================================================
    # GENERAR PDF
    # =====================================================

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