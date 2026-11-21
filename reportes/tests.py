from datetime import date, datetime, timezone
from decimal import Decimal
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from pagos.models import Pago


class IngresosDiariosTests(TestCase):
    def setUp(self):
        self.client.force_login(get_user_model().objects.create_user(username="reportes"))
        self.url = reverse("reportes:ingresos_diarios")

    def test_requiere_pin_y_conserva_filtros(self):
        respuesta = self.client.get(self.url, {"periodo": "2024-02", "orden": "mayor"})
        self.assertEqual(respuesta.status_code, 302)
        destino = urlsplit(respuesta.url)
        self.assertEqual(destino.path, reverse("caja:validar_pin"))
        self.assertEqual(
            parse_qs(destino.query)["next"],
            [f"{self.url}?periodo=2024-02&orden=mayor"],
        )

    def test_agrupa_por_fecha_uruguaya_y_ordena_por_monto(self):
        sesion = self.client.session
        sesion["finanzas_pin_ok"] = True
        sesion.save()
        pagos = [
            (datetime(2024, 2, 1, 2, tzinfo=timezone.utc), "99.00"),
            (datetime(2024, 2, 1, 3, tzinfo=timezone.utc), "4.50"),
            (datetime(2024, 2, 1, 17, tzinfo=timezone.utc), "6.25"),
            (datetime(2024, 3, 1, 2, tzinfo=timezone.utc), "20.00"),
            (datetime(2024, 3, 1, 3, tzinfo=timezone.utc), "99.00"),
        ]
        for fecha, monto in pagos:
            Pago.objects.create(fecha=fecha, monto=Decimal(monto), metodo=Pago.EFECTIVO)

        parametros = {"periodo": "2024-02", "orden": "mayor"}
        respuesta = self.client.get(self.url, parametros)
        filas = respuesta.context["filas"]
        self.assertEqual(len(filas), 29)
        self.assertEqual(filas[:2], [
            (date(2024, 2, 29), "Jueves", Decimal("20.00")),
            (date(2024, 2, 1), "Jueves", Decimal("10.75")),
        ])
        self.assertEqual(respuesta.context["total"], Decimal("30.75"))

        parametros["orden"] = "menor"
        filas = self.client.get(self.url, parametros).context["filas"]
        self.assertEqual(filas[0], (date(2024, 2, 2), "Viernes", Decimal("0.00")))
        self.assertEqual(filas[-1][0], date(2024, 2, 29))

    def test_comparacion_anual_incluye_meses_vacios_y_dia_bisiesto(self):
        url = reverse("reportes:ingresos_anuales")
        self.assertEqual(self.client.get(url).status_code, 302)
        sesion = self.client.session
        sesion["finanzas_pin_ok"] = True
        sesion.save()
        for fecha, monto in [
            (datetime(2024, 3, 1, 2, tzinfo=timezone.utc), "20.00"),
            (datetime(2024, 3, 1, 3, tzinfo=timezone.utc), "5.00"),
            (datetime(2025, 1, 1, 3, tzinfo=timezone.utc), "99.00"),
        ]:
            Pago.objects.create(fecha=fecha, monto=Decimal(monto), metodo=Pago.EFECTIVO)

        respuesta = self.client.get(url, {"year": "2024"})
        self.assertContains(respuesta, "PDF para imprimir")
        meses = respuesta.context["meses"]
        self.assertEqual(len(meses), 12)
        self.assertEqual(meses[0]["total"], Decimal("0.00"))
        self.assertEqual(meses[1]["valores"][28:], [Decimal("20.00"), None, None])
        self.assertEqual(meses[2]["valores"][0], Decimal("5.00"))
        self.assertEqual(respuesta.context["total"], Decimal("25.00"))

        pdf = self.client.get(url, {"year": "2024", "formato": "pdf"})
        self.assertEqual(pdf["Content-Type"], "application/pdf")
        contenido = b"".join(pdf.streaming_content)
        self.assertIn(b"/Count 1", contenido)
