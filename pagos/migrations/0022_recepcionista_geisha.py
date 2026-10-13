from decimal import Decimal

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


def crear_geisha(apps, schema_editor):
    Recepcionista = apps.get_model("pagos", "Recepcionista")
    Recepcionista.objects.get_or_create(
        nombre="Geisha Labrada",
        defaults={
            "sueldo_mensual": Decimal("30000.00"),
            "sueldo_quincenal": Decimal("15000.00"),
            "horas_diarias": Decimal("6.00"),
            "valor_hora_extra": Decimal("250.00"),
            "horario": "Lunes a viernes: 11:00–14:00 y 15:00–18:00",
            "activa": True,
        },
    )


class Migration(migrations.Migration):
    dependencies = [("pagos", "0021_jornada_liquidacion_sofia")]

    operations = [
        migrations.CreateModel(
            name="Recepcionista",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nombre", models.CharField(max_length=120, unique=True)),
                ("sueldo_mensual", models.DecimalField(decimal_places=2, default=Decimal("30000.00"), max_digits=10)),
                ("sueldo_quincenal", models.DecimalField(decimal_places=2, default=Decimal("15000.00"), max_digits=10)),
                ("horas_diarias", models.DecimalField(decimal_places=2, default=Decimal("6.00"), max_digits=4)),
                ("valor_hora_extra", models.DecimalField(decimal_places=2, default=Decimal("250.00"), max_digits=8)),
                ("horario", models.CharField(blank=True, max_length=240)),
                ("activa", models.BooleanField(default=True)),
            ],
            options={"ordering": ["nombre"]},
        ),
        migrations.CreateModel(
            name="HoraExtraRecepcionista",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("fecha", models.DateField(db_index=True)),
                ("horas", models.DecimalField(decimal_places=2, max_digits=5)),
                ("notas", models.CharField(blank=True, max_length=200)),
                ("creada", models.DateTimeField(auto_now_add=True)),
                ("recepcionista", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="horas_extra", to="pagos.recepcionista")),
            ],
            options={"ordering": ["-fecha", "-id"]},
        ),
        migrations.AddConstraint(
            model_name="horaextrarecepcionista",
            constraint=models.CheckConstraint(condition=models.Q(horas__gt=0), name="hora_extra_recepcionista_positiva"),
        ),
        migrations.CreateModel(
            name="LiquidacionRecepcionista",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("fecha_inicio", models.DateField()),
                ("fecha_fin", models.DateField()),
                ("sueldo_base", models.DecimalField(decimal_places=2, max_digits=10)),
                ("horas_extra_pagadas", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=7)),
                ("monto_horas_extra", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=10)),
                ("monto_pagado", models.DecimalField(decimal_places=2, max_digits=10)),
                ("fecha_pago", models.DateField(default=django.utils.timezone.localdate)),
                ("metodo", models.CharField(choices=[("efectivo", "Efectivo"), ("transferencia", "Transferencia"), ("tarjeta", "Tarjeta")], max_length=20)),
                ("gasto", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="liquidacion_recepcionista", to="pagos.gasto")),
                ("recepcionista", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="liquidaciones", to="pagos.recepcionista")),
            ],
            options={"ordering": ["-fecha_fin", "-id"]},
        ),
        migrations.AddConstraint(
            model_name="liquidacionrecepcionista",
            constraint=models.UniqueConstraint(fields=("recepcionista", "fecha_inicio", "fecha_fin"), name="liquidacion_recepcionista_periodo_unico"),
        ),
        migrations.AddConstraint(
            model_name="liquidacionrecepcionista",
            constraint=models.CheckConstraint(condition=models.Q(fecha_fin__gte=models.F("fecha_inicio")), name="liquidacion_recepcionista_periodo_valido"),
        ),
        migrations.RunPython(crear_geisha, migrations.RunPython.noop),
    ]
