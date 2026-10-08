from django import forms
from .models import Pago, JornadaSofia


class PagoForm(forms.ModelForm):

    class Meta:
        model = Pago

        fields = [
            "monto",
            "paciente",
            "concepto",
            "metodo",
        ]

        widgets = {

            "monto": forms.NumberInput(attrs={
                "class": "form-control",
                "placeholder": "0.00",
            }),

            "paciente": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Ej: Luis Hernández",
            }),

            "concepto": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Ej: Control / Ortodoncia / Limpieza",
            }),

            "metodo": forms.Select(attrs={
                "class": "form-control",
            }),
        }


class JornadaSofiaForm(forms.ModelForm):
    class Meta:
        model = JornadaSofia
        fields = [
            "fecha",
            "hora_entrada",
            "hora_salida",
            "descanso_minutos",
            "notas",
        ]
        labels = {
            "fecha": "Fecha",
            "hora_entrada": "Hora de entrada",
            "hora_salida": "Hora de salida",
            "descanso_minutos": "Descanso (minutos, incluido en el pago)",
            "notas": "Notas",
        }
        widgets = {
            "fecha": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "hora_entrada": forms.TimeInput(attrs={"type": "time", "class": "form-control"}),
            "hora_salida": forms.TimeInput(attrs={"type": "time", "class": "form-control"}),
            "descanso_minutos": forms.NumberInput(attrs={"min": "0", "step": "1", "class": "form-control"}),
            "notas": forms.TextInput(attrs={"class": "form-control", "placeholder": "Opcional"}),
        }

    def clean(self):
        cleaned = super().clean()
        entrada = cleaned.get("hora_entrada")
        salida = cleaned.get("hora_salida")
        descanso = cleaned.get("descanso_minutos") or 0
        if entrada and salida and salida <= entrada:
            self.add_error("hora_salida", "La salida debe ser posterior a la entrada.")
        if entrada and salida:
            minutos = (
                salida.hour * 60 + salida.minute
                - entrada.hour * 60 - entrada.minute
            )
            if descanso > minutos:
                self.add_error("descanso_minutos", "El descanso no puede superar la duración de la jornada.")
        return cleaned
