from datetime import date, time
from decimal import Decimal

from django.test import SimpleTestCase

from .models import JornadaSofia
from .views import _calcular_horas_y_sueldo


class CalculoSueldoSofiaTests(SimpleTestCase):
    def test_sesenta_y_dos_horas_corresponden_a_catorce_mil(self):
        jornada = JornadaSofia(
            fecha=date(2026, 10, 1),
            hora_entrada=time(0, 0),
            hora_salida=time(15, 30),
            descanso_minutos=0,
        )

        horas, sueldo = _calcular_horas_y_sueldo([jornada] * 4)

        self.assertEqual(horas, Decimal("62.00"))
        self.assertEqual(sueldo, Decimal("14000.00"))

    def test_incluye_el_descanso_en_las_horas_pagadas(self):
        jornada = JornadaSofia(
            fecha=date(2026, 10, 2),
            hora_entrada=time(9, 0),
            hora_salida=time(17, 0),
            descanso_minutos=30,
        )

        horas, _ = _calcular_horas_y_sueldo([jornada])

        self.assertEqual(horas, Decimal("8.00"))

    def test_jornada_de_ocho_horas_se_paga_a_prorrata_incluyendo_descanso(self):
        jornada = JornadaSofia(
            fecha=date(2026, 10, 6),
            hora_entrada=time(10, 0),
            hora_salida=time(18, 0),
            descanso_minutos=60,
        )

        horas, sueldo = _calcular_horas_y_sueldo([jornada])

        self.assertEqual(horas, Decimal("8.00"))
        self.assertEqual(sueldo, Decimal("1806.45"))
