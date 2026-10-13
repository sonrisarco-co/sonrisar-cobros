# Sueldo de Geisha Labrada

Esta actualización reemplaza el acceso visible a las horas de Sofía por el control de sueldo y horas extra de Geisha Labrada. Los modelos y datos históricos de Sofía permanecen en la base, sin mezclarse con las nuevas liquidaciones.

## Condiciones configuradas

- Sueldo fijo mensual: $30.000.
- Pago quincenal: $15.000 por cada quincena calendario (del 1 al 15 y del 16 al último día del mes).
- Horario: lunes a viernes, 11:00–14:00 y 15:00–18:00 (6 horas diarias).
- Hora extra común: $15.000 ÷ 60 horas por quincena = $250.
- El recibo mensual desglosa sueldo base y horas extra, e incluye botón para imprimir.
- Al liquidar una quincena se crea un gasto de Sueldos, con la casilla habitual para decidir si afecta la caja abierta.

## Aplicar

1. Haz una copia de seguridad de la base de datos actual.
2. Copia los archivos de la actualización en sus rutas correspondientes. Conserva `db.sqlite3`, `.env` y los demás archivos locales.
3. Ejecuta desde la carpeta del proyecto:

   ```bat
   python manage.py migrate
   ```

4. Reinicia el servidor y entra en Caja → **Sueldo de Geisha**. La pantalla utiliza el PIN financiero de gastos.

La migración crea a Geisha Labrada si aún no existe y no modifica ni elimina las liquidaciones o jornadas históricas de Sofía.
