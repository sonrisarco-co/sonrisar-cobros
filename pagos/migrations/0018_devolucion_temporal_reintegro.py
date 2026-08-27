from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('pagos', '0017_devolucionpaciente_nc_cfe_id_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='devolucionpaciente',
            name='tipo',
            field=models.CharField(
                choices=[
                    ('definitiva', 'Definitiva'),
                    ('temporal', 'Temporal / pendiente de reintegro'),
                ],
                db_index=True,
                default='definitiva',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='devolucionpaciente',
            name='reintegrada',
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name='devolucionpaciente',
            name='fecha_reintegro',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='gasto',
            name='categoria',
            field=models.CharField(
                choices=[
                    ('insumos', 'Insumos'),
                    ('laboratorio', 'Laboratorio'),
                    ('alquiler', 'Alquiler'),
                    ('servicios', 'Servicios'),
                    ('sueldos', 'Sueldos'),
                    ('mantenimiento', 'Mantenimiento'),
                    ('devolucion_paciente', 'Devolución a paciente'),
                    ('entrega_temporal_paciente', 'Entrega temporal a paciente'),
                    ('otros', 'Otros'),
                ],
                max_length=50,
            ),
        ),
    ]
