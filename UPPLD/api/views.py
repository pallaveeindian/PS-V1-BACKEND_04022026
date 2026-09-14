from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.filters import OrderingFilter, SearchFilter
from django_filters.rest_framework import DjangoFilterBackend
import django_filters

from UPPLD.models import AspirationalBlockAchievement
from .serializers import AspirationalBlockAchievementListSerializer


class AspirationalBlockAchievementFilter(django_filters.FilterSet):
    year = django_filters.CharFilter(field_name='year', lookup_expr='exact')
    month = django_filters.NumberFilter(field_name='month', lookup_expr='exact')
    dist_code = django_filters.CharFilter(field_name='dist_code', lookup_expr='exact')
    block_code = django_filters.CharFilter(field_name='block_code', lookup_expr='exact')
    prog_code = django_filters.CharFilter(method='filter_prog_code')

    class Meta:
        model = AspirationalBlockAchievement
        fields = ['year', 'month', 'dist_code', 'block_code', 'prog_code']

    def filter_prog_code(self, queryset, name, value):
        if not value:
            return queryset
        # Match both zero-padded and non-zero-padded values (e.g. '0511' and '511')
        stripped = value.lstrip('0')
        padded = f"0{stripped}" if len(stripped) == 3 else stripped
        return queryset.filter(prog_code__in=[value, stripped, padded])


class AspirationalBlockAchievementListView(generics.ListAPIView):
    """
    Listing endpoint for Aspirational Block Achievements.
    
    Supported Query Parameters:
      - ?year=2026-27
      - ?month=9
      - ?dist_code=633
      - ?block_code=1064
      - ?prog_code=0511 (or ?prog_code=511)
      - ?ordering=cum_ach (or -cum_ach, month, etc.)
      - ?search=Amanpur
    """
    permission_classes = [IsAuthenticated]
    serializer_class = AspirationalBlockAchievementListSerializer
    filter_backends = [DjangoFilterBackend, OrderingFilter, SearchFilter]
    filterset_class = AspirationalBlockAchievementFilter
    search_fields = ['dist_code', 'block_code', 'prog_code', 'disclaimer']
    ordering_fields = ['year', 'month', 'dist_code', 'block_code', 'cum_ach', 'created_at']
    ordering = ['-year', '-month', 'dist_code', 'block_code']

    def get_queryset(self):
        queryset = AspirationalBlockAchievement.objects.all()

        # Direct fallback for standard query parameter extraction
        year = self.request.query_params.get('year')
        month = self.request.query_params.get('month')
        dist_code = self.request.query_params.get('dist_code')
        block_code = self.request.query_params.get('block_code')
        prog_code = self.request.query_params.get('prog_code')

        if year:
            queryset = queryset.filter(year=year)
        if month:
            queryset = queryset.filter(month=month)
        if dist_code:
            queryset = queryset.filter(dist_code=dist_code)
        if block_code:
            queryset = queryset.filter(block_code=block_code)
        if prog_code:
            clean = prog_code.lstrip('0')
            padded = f"0{clean}" if len(clean) == 3 else clean
            queryset = queryset.filter(prog_code__in=[prog_code, clean, padded])

        return queryset