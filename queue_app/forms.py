from django import forms


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
