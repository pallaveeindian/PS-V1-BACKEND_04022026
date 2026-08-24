from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from django.db.models import Q

from core.models import MasterUser
from TMS.models import LearningMaterial
from .serializers import LearningMaterialSerializer

class LearningMaterialListCreateAPIView(APIView):
    """
    API View to list and create Learning Materials.
    Supports filtering by 'theme_id' and 'plan_id'.
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser] # Required for File Uploads

    def get(self, request, *args, **kwargs):
        queryset = LearningMaterial.objects.filter(is_active=True).order_by('-created_at')
        
        # 1. Extract Filters
        theme_id = request.query_params.get('theme_id')
        plan_id = request.query_params.get('plan_id')
        search = request.query_params.get('search')
        
        # 2. Apply Filters
        if theme_id:
            queryset = queryset.filter(theme_id=theme_id)
        if plan_id:
            queryset = queryset.filter(training_plan_id=plan_id)
        if search:
            queryset = queryset.filter(Q(title__icontains=search) | Q(description__icontains=search))
            
        serializer = LearningMaterialSerializer(queryset, many=True, context={'request': request})
        
        return Response({
            "status": "success", 
            "count": queryset.count(),
            "data": serializer.data
        }, status=status.HTTP_200_OK)

    def post(self, request, *args, **kwargs):
        try:
            auth_user = MasterUser.objects.get(username=request.user.username)
        except MasterUser.DoesNotExist:
            auth_user = None

        # Optional strict backend enforcement for role_id = 3
        if auth_user and str(getattr(auth_user, 'role_id', '')) != '3':
            return Response({"error": "Only SMMU can upload learning materials."}, status=status.HTTP_403_FORBIDDEN)

        serializer = LearningMaterialSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            serializer.save(created_by=auth_user)
            return Response({
                "status": "success", 
                "message": "Learning Material uploaded successfully.", 
                "data": serializer.data
            }, status=status.HTTP_201_CREATED)
            
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LearningMaterialDetailAPIView(APIView):
    """
    API View to retrieve or soft-delete a specific Learning Material.
    """
    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        try:
            return LearningMaterial.objects.get(pk=pk, is_active=True)
        except LearningMaterial.DoesNotExist:
            return None

    def get(self, request, pk, *args, **kwargs):
        material = self.get_object(pk)
        if not material:
            return Response({"error": "Learning material not found or deleted."}, status=status.HTTP_404_NOT_FOUND)
        
        serializer = LearningMaterialSerializer(material, context={'request': request})
        return Response({"status": "success", "data": serializer.data}, status=status.HTTP_200_OK)
        
    def delete(self, request, pk, *args, **kwargs):
        material = self.get_object(pk)
        if not material:
            return Response({"error": "Learning material not found or already deleted."}, status=status.HTTP_404_NOT_FOUND)
            
        try:
            auth_user = MasterUser.objects.get(username=request.user.username)
        except MasterUser.DoesNotExist:
            auth_user = None
            
        # Soft deletes via the SoftDeleteMixin
        material.delete(by_user=auth_user)
        
        return Response({
            "status": "success", 
            "message": "Learning Material deleted successfully."
        }, status=status.HTTP_200_OK)