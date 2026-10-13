from datetime import date, time
from decimal import Decimal
from types import SimpleNamespace

from django.test import SimpleTestCase

from .models import JornadaSofia
from .views import _monto_horas_extra


class CalculoHorasExtraRecepcionistaTests(SimpleTestCase):
    def setUp(self):
        self.recepcionista = SimpleNamespace(valor_hora_extra=Decimal("250.00"))

    def test_una_hora_extra_se_calcula_sobre_15000_por_60_horas(self):
        valor_hora = Decimal("15000.00") / Decimal("60")
        recepcionista = SimpleNamespace(valor_hora_extra=valor_hora)

        self.assertEqual(_monto_horas_extra(recepcionista, Decimal("1.00")), Decimal("250.00"))

    def test_admite_fracciones_de_hora_y_redondea_a_centimos(self):
        self.assertEqual(_monto_horas_extra(self.recepcionista, Decimal("1.50")), Decimal("375.00"))
        self.assertEqual(_monto_horas_extra(self.recepcionista, Decimal("0.25")), Decimal("62.50"))


class ArchivoHistoricoSofiaTests(SimpleTestCase):
    def test_jornada_historica_conserva_calculo_de_duracion(self):
        jornada = JornadaSofia(
            fecha=date(2025, 1, 1),
            hora_entrada=time(11, 0),
            hora_salida=time(18, 0),
            descanso_minutos=60,
        )

        # La estructura histórica queda disponible sin aparecer como una
        # jornada editable de la nueva liquidación de Geisha.
        self.assertEqual(jornada.horas_trabajadas, Decimal("7"))
