from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action
from django.shortcuts import get_object_or_404
import datetime

from .models import Service, Specialist, TimeSlot, Appointment
from .serializers import (
    ServiceSerializer, 
    SpecialistSerializer, 
    TimeSlotSerializer, 
    AppointmentSerializer
)

class ServiceViewSet(viewsets.ReadOnlyModelViewSet):
    """API для получения списка услуг"""
    queryset = Service.objects.filter(is_active=True)
    serializer_class = ServiceSerializer
    permission_classes = [permissions.AllowAny]

class SpecialistViewSet(viewsets.ReadOnlyModelViewSet):
    """API для получения списка врачей/специалистов"""
    # select_related + prefetch_related устраняют проблему «N+1 запросов»
    queryset = (Specialist.objects.filter(is_active=True)
                .select_related('service').prefetch_related('reviews'))
    serializer_class = SpecialistSerializer
    permission_classes = [permissions.AllowAny]

    @action(detail=True, methods=['get'])
    def slots(self, request, pk=None):
        """Получить доступные слоты для конкретного врача"""
        specialist = self.get_object()
        today = datetime.date.today()
        # Только будущие слоты, начиная с сегодня
        slots = TimeSlot.objects.filter(
            specialist=specialist, 
            date__gte=today,
            is_available=True
        ).order_by('date', 'time')
        
        serializer = TimeSlotSerializer(slots, many=True)
        return Response(serializer.data)

class AppointmentViewSet(viewsets.ModelViewSet):
    """API для управления записями пациента (просмотр, создание, отмена)"""
    http_method_names = ["get", "post", "delete", "head", "options"]
    serializer_class = AppointmentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Пациент видит только свои записи
        return Appointment.objects.filter(patient=self.request.user).order_by('-created_at')

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def destroy(self, request, *args, **kwargs):
        """DELETE /api/v1/appointments/{id}/ — отмена записи пациентом (слот освобождается)."""
        from .services import cancel_appointment
        appointment = self.get_object()
        if not cancel_appointment(appointment, by_user=request.user):
            return Response({'detail': 'Эту запись нельзя отменить.'},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_204_NO_CONTENT)
