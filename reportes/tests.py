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
