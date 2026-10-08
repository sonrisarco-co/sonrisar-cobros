from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("pagos", "0020_alter_gasto_fecha"),
    ]

    operations = [
        migrations.CreateModel(
            name="JornadaSofia",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("fecha", models.DateField(db_index=True)),
                ("hora_entrada", models.TimeField()),
                ("hora_salida", models.TimeField()),
                ("descanso_minutos", models.PositiveSmallIntegerField(default=0)),
                ("notas", models.CharField(blank=True, max_length=200)),
                ("creada", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-fecha", "-hora_entrada", "-id"]},
        ),
        migrations.AddConstraint(
            model_name="jornadasofia",
            constraint=models.CheckConstraint(
                condition=models.Q(hora_salida__gt=models.F("hora_entrada")),
                name="jornada_sofia_salida_despues_entrada",
            ),
        ),
        migrations.CreateModel(
            name="LiquidacionSofia",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("fecha_inicio", models.DateField()),
                ("fecha_fin", models.DateField()),
                ("horas_pagadas", models.DecimalField(decimal_places=2, max_digits=7)),
                ("monto_pagado", models.DecimalField(decimal_places=2, max_digits=10)),
                ("fecha_pago", models.DateField(default=django.utils.timezone.localdate)),
                ("metodo", models.CharField(choices=[("efectivo", "Efectivo"), ("transferencia", "Transferencia"), ("tarjeta", "Tarjeta")], max_length=20)),
                ("gasto", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="liquidacion_sofia", to="pagos.gasto")),
            ],
            options={"ordering": ["-fecha_fin", "-id"]},
        ),
        migrations.AddConstraint(
            model_name="liquidacionsofia",
            constraint=models.UniqueConstraint(fields=("fecha_inicio", "fecha_fin"), name="liquidacion_sofia_periodo_unico"),
        ),
        migrations.AddConstraint(
            model_name="liquidacionsofia",
            constraint=models.CheckConstraint(
                condition=models.Q(fecha_fin__gte=models.F("fecha_inicio")),
                name="liquidacion_sofia_periodo_valido",
            ),
        ),
    ]
