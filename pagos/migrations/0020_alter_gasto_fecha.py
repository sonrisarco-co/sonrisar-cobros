# Generated manually for the editable accounting date of expenses.

import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pagos", "0019_sesionacceso"),
    ]

    operations = [
        migrations.AlterField(
            model_name="gasto",
            name="fecha",
            field=models.DateTimeField(
                db_index=True,
                default=django.utils.timezone.now,
                verbose_name="Fecha del gasto",
            ),
        ),
    ]
