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

from django.test import TestCase, RequestFactory
from django.contrib.messages.storage.fallback import FallbackStorage
from .models import Recepcionista, LiquidacionRecepcionista, Gasto
from .views import _base_periodo, horas_recepcionista


class PeriodosPersonalizadosTests(TestCase):
    def setUp(self):
        self.persona, _ = Recepcionista.objects.get_or_create(nombre="Geisha Labrada")
        self.factory = RequestFactory()

    def request(self, inicio, fin, pagar=False):
        url = f"/pagos/horas-recepcionista/?inicio={inicio}&fin={fin}"
        req = (self.factory.post(url, {"accion": "pagar_quincena", "metodo": "transferencia"})
               if pagar else self.factory.get(url))
        req.session = {"finanzas_pin_ok": True}
        req._messages = FallbackStorage(req)
        return horas_recepcionista(req)

    def test_calculos_y_quincenas_historicas(self):
        for inicio, fin, esperado in [(13, 16, "6000.00"), (19, 30, "15000.00"),
                                     (1, 15, "15000.00"), (16, 31, "15000.00")]:
            self.assertEqual(_base_periodo(self.persona, date(2026, 10, inicio), date(2026, 10, fin)), Decimal(esperado))

    def test_paga_dos_periodos_y_no_duplica_gastos_por_solapamiento(self):
        for inicio, fin in [("2026-10-13", "2026-10-16"), ("2026-10-19", "2026-10-30")]:
            self.assertEqual(self.request(inicio, fin, True).status_code, 302)
        self.assertEqual(LiquidacionRecepcionista.objects.count(), 2)
        self.assertEqual(sum(Gasto.objects.values_list("monto", flat=True)), Decimal("21000"))
        for inicio, fin in [("2026-10-13", "2026-10-16"), ("2026-10-16", "2026-10-31"),
                            ("2026-10-12", "2026-10-14")]:
            self.request(inicio, fin, True)
        self.assertEqual(LiquidacionRecepcionista.objects.count(), 2)
        self.assertEqual(Gasto.objects.count(), 2)

    def test_render_y_fechas_invalidas_sin_pago(self):
        response = self.request("2026-10-13", "2026-10-16")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Ver período personalizado", response.content.decode())
        for inicio, fin in [("2026-10-30", "2026-10-13"), ("2026-10-13", "2026-11-16"),
                            ("2026-10-17", "2026-10-18")]:
            self.request(inicio, fin, True)
        self.assertFalse(LiquidacionRecepcionista.objects.exists())

from .models import HoraExtraRecepcionista


class CargaExtrasRangoTests(TestCase):
    def setUp(self):
        self.persona, _ = Recepcionista.objects.get_or_create(nombre="Geisha Labrada")

    def cargar(self, **datos):
        req = RequestFactory().post(
            '/pagos/horas-recepcionista/?inicio=2026-10-16&fin=2026-10-31',
            dict(accion='agregar_hora_extra', **datos))
        req.session = {'finanzas_pin_ok': True}
        req._messages = FallbackStorage(req)
        return horas_recepcionista(req)

    def test_semana_y_reenvio_no_duplica(self):
        datos = dict(modo='rango', fecha='2026-10-19', hasta='2026-10-25', horas='1', notas='Semana')
        self.assertEqual(self.cargar(**datos).status_code, 302)
        filas = HoraExtraRecepcionista.objects.all()
        self.assertEqual(filas.count(), 5)
        self.assertEqual(sum(f.horas for f in filas), Decimal('5'))
        self.assertTrue(all(f.fecha.weekday() < 5 for f in filas))
        self.assertEqual(self.cargar(**datos).status_code, 200)
        self.assertEqual(filas.count(), 5)

    def test_carga_diaria_sigue_disponible(self):
        self.assertEqual(self.cargar(fecha='2026-10-20', horas='1.5').status_code, 302)
        self.assertEqual(HoraExtraRecepcionista.objects.get().horas, Decimal('1.5'))

    def test_rangos_invalidos_no_guardan_nada(self):
        for fecha, hasta in [('2026-10-25', '2026-10-19'), ('2026-10-17', '2026-10-18'),
                             ('2026-10-13', '2026-10-20'), ('2026-10-19', '')]:
            self.cargar(modo='rango', fecha=fecha, hasta=hasta, horas='1')
        self.assertFalse(HoraExtraRecepcionista.objects.exists())

    def test_fecha_pagada_bloquea_todo_el_lote(self):
        LiquidacionRecepcionista.objects.create(
            recepcionista=self.persona, fecha_inicio=date(2026,10,21), fecha_fin=date(2026,10,21),
            sueldo_base=1500, monto_pagado=1500, metodo='transferencia')
        self.cargar(modo='rango', fecha='2026-10-19', hasta='2026-10-23', horas='1')
        self.assertFalse(HoraExtraRecepcionista.objects.exists())
