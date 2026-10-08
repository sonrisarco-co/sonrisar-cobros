# Horas y sueldo de Sofía

La actualización agrega el control quincenal de jornadas y la liquidación de sueldo en Sonrisar Cobros.

## Puesta en marcha

1. Haz una copia de seguridad de la base de datos que ya usa Sonrisar Cobros.
2. Copia los archivos de esta actualización sobre el proyecto actual, conservando la base de datos y el archivo `.env` existentes.
3. Desde la carpeta del proyecto, ejecuta:

   ```bat
   python manage.py migrate
   ```

4. Reinicia el servidor. En Caja, abre **Horas de Sofía**. La pantalla también solicitará el PIN financiero utilizado para los gastos.

## Cálculo y registro

- La referencia es 62 horas por $14.000.
- El importe se calcula con la proporción exacta `horas registradas × 14.000 ÷ 62` y se guarda con dos decimales.
- Las 62 horas incluyen los descansos. El campo de descanso es informativo y no se resta de la duración entre entrada y salida.
- Las jornadas se registran en quincenas calendario: del 1 al 15 o del 16 al último día del mes.
- Al registrar el pago, se genera un gasto de categoría **Sueldos**, con fecha del pago y vínculo a la liquidación.
- La casilla **Descontar de la caja abierta** controla si el egreso se carga a la caja del día. Las horas registradas no alteran la caja.
- Una quincena pagada queda cerrada y no puede liquidarse de nuevo.

El paquete no contiene `db.sqlite3`; conserva la base de datos y el `.env` que ya utilizas al copiar la actualización.
