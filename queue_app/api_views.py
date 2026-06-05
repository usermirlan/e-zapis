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
    queryset = Specialist.objects.filter(is_active=True)
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
    """API для управления записями"""
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
