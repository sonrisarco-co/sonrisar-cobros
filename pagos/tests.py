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
        historica = LiquidacionRecepcionista.objects.create(
            recepcionista=self.persona, fecha_inicio=date(2026,10,21), fecha_fin=date(2026,10,21),
            sueldo_base=1500, monto_pagado=1500, metodo='transferencia')
        HoraExtraRecepcionista.objects.create(recepcionista=self.persona, fecha=date(2026,10,21), horas=1, liquidacion_historica=historica)
        self.cargar(modo='rango', fecha='2026-10-19', hasta='2026-10-23', horas='1')
        self.assertEqual(HoraExtraRecepcionista.objects.count(), 1)

from .models import PagoExtrasRecepcionista
from unittest.mock import patch


class PagosSeparadosExtrasTests(TestCase):
    def setUp(self):
        self.persona, _ = Recepcionista.objects.get_or_create(nombre='Geisha Labrada')
        self.extra = HoraExtraRecepcionista.objects.create(
            recepcionista=self.persona, fecha=date(2026,10,20), horas=Decimal('2'))

    def ejecutar(self, accion, **datos):
        if accion in {'pagar_extras', 'marcar_extras_pagadas'} and 'extras_ids' not in datos:
            datos['extras_ids'] = list(HoraExtraRecepcionista.objects.filter(
                recepcionista=self.persona, pago_extras__isnull=True,
                liquidacion_historica__isnull=True, pagada_previamente=False).values_list('pk', flat=True))
        req = RequestFactory().post('/pagos/horas-recepcionista/?inicio=2026-10-19&fin=2026-10-30',
                                    dict(accion=accion, metodo=datos.pop('metodo', 'transferencia'), **datos))
        req.session = {'finanzas_pin_ok': True}
        req._messages = FallbackStorage(req)
        return horas_recepcionista(req)

    def test_sueldo_y_extras_independientes_y_sin_duplicados(self):
        self.ejecutar('pagar_quincena', metodo='efectivo')
        sueldo = LiquidacionRecepcionista.objects.get()
        self.assertEqual(sueldo.metodo, 'efectivo')
        self.assertEqual(sueldo.monto_pagado, Decimal('15000'))
        self.assertEqual(sueldo.monto_horas_extra, Decimal('0'))
        self.extra.refresh_from_db()
        self.assertIsNone(self.extra.pago_extras_id)
        self.ejecutar('pagar_extras')
        pago = PagoExtrasRecepcionista.objects.get()
        self.assertEqual(pago.monto_pagado, Decimal('500'))
        self.assertEqual(pago.gasto.metodo, 'transferencia')
        self.assertFalse(pago.gasto.afecta_caja)
        self.assertIsNone(pago.gasto.caja_id)
        self.ejecutar('pagar_extras')
        self.assertEqual(PagoExtrasRecepcionista.objects.count(), 1)
        self.assertEqual(Gasto.objects.count(), 2)
        self.extra.refresh_from_db()
        self.assertEqual(self.extra.pago_extras_id, pago.pk)
        self.ejecutar('eliminar_hora_extra', hora_extra_id=self.extra.pk)
        self.assertTrue(HoraExtraRecepcionista.objects.filter(pk=self.extra.pk).exists())

    def test_extras_antes_del_sueldo_y_nuevas_extras_despues(self):
        self.ejecutar('pagar_extras')
        self.assertFalse(LiquidacionRecepcionista.objects.exists())
        self.ejecutar('pagar_quincena')
        self.ejecutar('agregar_hora_extra', fecha='2026-10-21', horas='1')
        self.ejecutar('pagar_extras')
        self.assertEqual(PagoExtrasRecepcionista.objects.count(), 2)
        self.assertEqual(sum(Gasto.objects.values_list('monto',flat=True)), Decimal('15750'))

    def test_caja_cerrada_y_metodo_invalido_no_crean_pago(self):
        from types import SimpleNamespace
        from caja.models import CashSession
        with patch.object(CashSession, 'obtener_caja_del_dia', return_value=SimpleNamespace(estado=CashSession.Status.CERRADA)):
            self.ejecutar('pagar_extras', afecta_caja='on')
        req = RequestFactory().post('/pagos/horas-recepcionista/?inicio=2026-10-19&fin=2026-10-30',
                                    {'accion':'pagar_extras','metodo':'invalido'})
        req.session={'finanzas_pin_ok':True}; req._messages=FallbackStorage(req)
        horas_recepcionista(req)
        self.assertFalse(PagoExtrasRecepcionista.objects.exists())
        self.assertFalse(Gasto.objects.exists())

    def test_migracion_conserva_extras_historicas_como_pagadas(self):
        from importlib import import_module
        from django.apps import apps
        from django.db import connection
        historica = LiquidacionRecepcionista.objects.create(
            recepcionista=self.persona, fecha_inicio=date(2026,10,19), fecha_fin=date(2026,10,30),
            sueldo_base=15000, monto_pagado=15500, horas_extra_pagadas=2,
            monto_horas_extra=500, metodo='efectivo')
        migracion = import_module('pagos.migrations.0023_horaextrarecepcionista_liquidacion_historica_and_more')
        migracion.vincular_extras_historicas(apps, SimpleNamespace(connection=connection))
        self.extra.refresh_from_db()
        self.assertEqual(self.extra.liquidacion_historica_id, historica.pk)
        self.ejecutar('pagar_extras')
        self.assertFalse(PagoExtrasRecepcionista.objects.exists())
        historica.refresh_from_db()
        self.assertEqual(historica.monto_pagado, Decimal('15500'))


class SeleccionExtrasTests(TestCase):
    setUp = PagosSeparadosExtrasTests.setUp
    ejecutar = PagosSeparadosExtrasTests.ejecutar

    def test_marcar_pago_previo_no_genera_gasto_y_resto_sigue_pendiente(self):
        otra = HoraExtraRecepcionista.objects.create(recepcionista=self.persona, fecha=date(2026,10,23), horas=1)
        self.ejecutar('marcar_extras_pagadas', extras_ids=[self.extra.pk], afecta_caja='on')
        self.extra.refresh_from_db(); otra.refresh_from_db()
        self.assertTrue(self.extra.pagada_previamente)
        self.assertFalse(otra.pagada_previamente)
        self.assertFalse(Gasto.objects.exists())
        self.assertFalse(PagoExtrasRecepcionista.objects.exists())
        self.ejecutar('pagar_extras', extras_ids=[otra.pk])
        self.assertEqual(PagoExtrasRecepcionista.objects.get().monto_pagado, Decimal('250'))
        self.ejecutar('eliminar_hora_extra', hora_extra_id=self.extra.pk)
        self.assertTrue(HoraExtraRecepcionista.objects.filter(pk=self.extra.pk).exists())

    def test_pagar_solo_seleccionadas_y_rechazar_seleccion_obsoleta(self):
        otra = HoraExtraRecepcionista.objects.create(recepcionista=self.persona, fecha=date(2026,10,23), horas=1)
        self.ejecutar('pagar_extras', extras_ids=[self.extra.pk])
        self.assertEqual(PagoExtrasRecepcionista.objects.get().monto_pagado, Decimal('500'))
        self.ejecutar('marcar_extras_pagadas', extras_ids=[self.extra.pk, otra.pk])
        otra.refresh_from_db()
        self.assertFalse(otra.pagada_previamente)
        self.assertIsNone(otra.pago_extras_id)
        self.assertEqual(Gasto.objects.count(), 1)

    def test_vacia_o_fuera_del_periodo_no_modifica_nada(self):
        fuera = HoraExtraRecepcionista.objects.create(recepcionista=self.persona, fecha=date(2026,10,13), horas=1)
        for seleccion in [[], [fuera.pk], ['invalido']]:
            self.ejecutar('marcar_extras_pagadas', extras_ids=seleccion)
            self.ejecutar('pagar_extras', extras_ids=seleccion)
        self.assertFalse(HoraExtraRecepcionista.objects.filter(pagada_previamente=True).exists())
        self.assertFalse(Gasto.objects.exists())
