from django import forms
from .models import Service, Specialist


class BookingForm(forms.Form):
    """Форма для записи на приём — поле жалобы/причины обращения."""

    complaint = forms.CharField(
        label='Причина обращения',
        required=False,
        max_length=1000,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 4,
            'placeholder': 'Опишите симптомы или причину визита (необязательно)...',
            'id': 'id_complaint',
        }),
        help_text='Кратко опишите жалобу, чтобы врач мог подготовиться к приёму.'
    )

    def clean_complaint(self):
        complaint = self.cleaned_data.get('complaint', '').strip()
        return complaint


class ServiceForm(forms.ModelForm):
    class Meta:
        model = Service
        fields = ['name', 'description', 'icon', 'duration_minutes', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'icon': forms.TextInput(attrs={'class': 'form-control'}),
            'duration_minutes': forms.NumberInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class SpecialistForm(forms.ModelForm):
    class Meta:
        model = Specialist
        fields = [
            'first_name', 'last_name', 'middle_name', 'service', 
            'bio', 'experience_years', 'photo', 'cabinet', 
            'work_start', 'work_end', 'is_active'
        ]
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'middle_name': forms.TextInput(attrs={'class': 'form-control'}),
            'service': forms.Select(attrs={'class': 'form-select'}),
            'bio': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'experience_years': forms.NumberInput(attrs={'class': 'form-control'}),
            'photo': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'cabinet': forms.TextInput(attrs={'class': 'form-control'}),
            'work_start': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'work_end': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
