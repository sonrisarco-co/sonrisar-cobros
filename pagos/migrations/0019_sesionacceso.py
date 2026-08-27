from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("pagos", "0018_devolucion_temporal_reintegro"),
    ]

    operations = [
        migrations.CreateModel(
            name="SesionAcceso",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ingreso", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("ultima_actividad", models.DateTimeField(default=django.utils.timezone.now)),
                ("salida", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("motivo_salida", models.CharField(blank=True, choices=[("manual", "Salida registrada"), ("nueva_sesion", "Cierre al iniciar una nueva sesión"), ("expirada", "Sesión expirada")], max_length=20)),
                ("direccion_ip", models.GenericIPAddressField(blank=True, null=True)),
                ("navegador", models.CharField(blank=True, max_length=255)),
                ("clave_sesion", models.CharField(blank=True, db_index=True, max_length=40)),
                ("usuario", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="sesiones_sonrisar_cobros", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "sesión de acceso",
                "verbose_name_plural": "sesiones de acceso",
                "ordering": ["-ingreso", "-id"],
            },
        ),
    ]
