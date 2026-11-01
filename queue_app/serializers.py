from rest_framework import serializers
from .models import Service, Specialist, TimeSlot, Appointment
from django.contrib.auth import get_user_model

User = get_user_model()


class BookingConflict(serializers.ValidationError):
    """Ошибка бронирования, возвращаемая клиенту API с кодом HTTP 409 Conflict."""
    status_code = 409

    def __init__(self, message, code='conflict'):
        super().__init__({'detail': message, 'code': code})

class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name', 'phone', 'full_name']

    def get_full_name(self, obj):
        return obj.get_full_name()

class ServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Service
        fields = ['id', 'name', 'description', 'icon', 'duration_minutes']

class SpecialistSerializer(serializers.ModelSerializer):
    service = ServiceSerializer(read_only=True)
    full_name = serializers.SerializerMethodField()
    average_rating = serializers.FloatField(read_only=True)

    class Meta:
        model = Specialist
        fields = ['id', 'full_name', 'service', 'bio', 'experience_years', 'photo', 'cabinet', 'average_rating']

    def get_full_name(self, obj):
        return obj.get_full_name()

class TimeSlotSerializer(serializers.ModelSerializer):
    class Meta:
        model = TimeSlot
        fields = ['id', 'date', 'time', 'is_available']

class AppointmentSerializer(serializers.ModelSerializer):
    patient = UserSerializer(read_only=True)
    specialist = SpecialistSerializer(read_only=True)
    service = ServiceSerializer(read_only=True)
    time_slot = TimeSlotSerializer(read_only=True)
    
    # Write fields for creating appointment
    specialist_id = serializers.IntegerField(write_only=True)
    service_id = serializers.IntegerField(write_only=True)
    time_slot_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = Appointment
        fields = [
            'id', 'patient', 'service', 'specialist', 'time_slot', 
            'queue_number', 'status', 'complaint', 'created_at',
            'specialist_id', 'service_id', 'time_slot_id'
        ]
        read_only_fields = ['queue_number', 'status', 'created_at']

    def create(self, validated_data):
        """Создание записи через тот же атомарный сервис, что и в веб-интерфейсе."""
        from .services import book_slot, BookingError
        patient = self.context['request'].user
        validated_data.pop('specialist_id', None)
        validated_data.pop('service_id', None)
        time_slot_id = validated_data.pop('time_slot_id')
        try:
            return book_slot(patient, time_slot_id, validated_data.get('complaint', ''))
        except BookingError as exc:
            raise BookingConflict(exc.message, exc.code)
