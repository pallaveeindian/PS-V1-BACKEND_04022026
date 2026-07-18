import uuid
from django.db import transaction
from django.db.models import Q
from rest_framework.views import APIView
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination

from core.models import MasterUser
from TMS.models import MasterTrainer, MasterTrainerCertificate
from .serializers import (
    MasterTrainerListSerializer, 
    MasterTrainerDetailSerializer,
    MasterTrainerWriteSerializer
)

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 1000

# ---------------------------------------------------------
# 1) Master Trainer Listing API (with Filters)
# ---------------------------------------------------------
class MasterTrainerListAPIView(ListAPIView):
    serializer_class = MasterTrainerListSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        queryset = MasterTrainer.objects.filter(is_active=True).select_related('empanel_district', 'theme')

        # Extract Query Params
        mandal_id = self.request.query_params.get('mandal')
        district_category_id = self.request.query_params.get('district_category')
        district_id = self.request.query_params.get('district')
        theme_id = self.request.query_params.get('theme')
        designation = self.request.query_params.get('designation')
        gender = self.request.query_params.get('gender')
        smmu_recommended = self.request.query_params.get('smmu_recommended')
        search_query = self.request.query_params.get('search')

        # Apply Filters
        if mandal_id:
            queryset = queryset.filter(empanel_district__mandal_id=mandal_id)
        
        if district_category_id:
            # Traverses the bridge table MasterDistrictCategoryMapping
            queryset = queryset.filter(empanel_district__masterdistrictcategorymapping__category_id=district_category_id)
        
        if district_id:
            queryset = queryset.filter(empanel_district_id=district_id)
            
        if theme_id:
            queryset = queryset.filter(theme_id=theme_id)
            
        if designation:
            queryset = queryset.filter(designation__iexact=designation)
            
        if gender:
            queryset = queryset.filter(gender__iexact=gender)
            
        if smmu_recommended:
            queryset = queryset.filter(thematic_expert_recommendation__icontains=smmu_recommended)

        if search_query:
            queryset = queryset.filter(
                Q(full_name__icontains=search_query) |
                Q(mobile_no__icontains=search_query) |
                Q(aadhaar_no__icontains=search_query)
            )

        return queryset

# ---------------------------------------------------------
# 2) Master Trainer Detail API
# ---------------------------------------------------------
class MasterTrainerDetailAPIView(RetrieveAPIView):
    queryset = MasterTrainer.objects.filter(is_active=True)
    serializer_class = MasterTrainerDetailSerializer
    permission_classes = [IsAuthenticated]

# ---------------------------------------------------------
# 3) OneSHOT Master Trainer Creation API
# ---------------------------------------------------------
class MasterTrainerCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        username = request.data.get('username')
        if not username:
            return Response({"error": "username is required."}, status=status.HTTP_400_BAD_REQUEST)
        
        if MasterUser.objects.filter(username=username).exists():
            return Response({"error": "Username already exists."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = MasterTrainerWriteSerializer(data=request.data)
        if serializer.is_valid():
            try:
                with transaction.atomic():
                    # 1. Create Master User
                    new_user = MasterUser.objects.create(
                        username=username,
                        password="mt@tms",  # Cleartext password assignment as requested
                        is_active=1,
                        role=7,
                        TH_urid=str(uuid.uuid4())
                    )
                    # 2. Create Master Trainer
                    trainer = serializer.save(master_user=new_user)
                    
                return Response({
                    "message": "Master Trainer and User created successfully.",
                    "trainer_id": trainer.id,
                    "username": new_user.username,
                    "password": "mt@tms"
                }, status=status.HTTP_201_CREATED)
            except Exception as e:
                return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# ---------------------------------------------------------
# 4) OneSHOT Master Trainer Update API
# ---------------------------------------------------------
class MasterTrainerUpdateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request, pk, *args, **kwargs):
        try:
            trainer = MasterTrainer.objects.get(id=pk, is_active=True)
        except MasterTrainer.DoesNotExist:
            return Response({"error": "Master Trainer not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = MasterTrainerWriteSerializer(trainer, data=request.data, partial=True)
        
        if serializer.is_valid():
            new_username = request.data.get('username')
            reset_password = request.data.get('reset_password')
            
            try:
                with transaction.atomic():
                    # 1. Update Trainer Fields
                    serializer.save()
                    
                    # 2. Update User Fields if requested
                    master_user = trainer.master_user
                    password_reset_flag = False
                    
                    if master_user:
                        if new_username and new_username != master_user.username:
                            if MasterUser.objects.filter(username=new_username).exists():
                                raise ValueError("Requested new username already exists.")
                            master_user.username = new_username
                            
                        # Custom Param: Reset Password
                        if str(reset_password).lower() in ['true', '1', 'yes']:
                            master_user.password = "mt@tms"
                            password_reset_flag = True
                            
                        master_user.save()

                resp_data = {"message": "Master Trainer updated successfully."}
                if password_reset_flag:
                    resp_data["new_password"] = "mt@tms"
                    
                return Response(resp_data, status=status.HTTP_200_OK)

            except Exception as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# ---------------------------------------------------------
# 5) OneSHOT Master Trainer Deletion API
# ---------------------------------------------------------
class MasterTrainerDeleteAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk, *args, **kwargs):
        try:
            trainer = MasterTrainer.objects.get(id=pk)
        except MasterTrainer.DoesNotExist:
            return Response({"error": "Master Trainer not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            with transaction.atomic():
                master_user = trainer.master_user
                
                # Soft delete Certificates
                MasterTrainerCertificate.objects.filter(trainer=trainer).delete()
                
                # Soft delete Trainer
                trainer.delete()
                
                # Delete MasterUser (Usually hard delete unless soft delete is implemented on MasterUser)
                if master_user:
                    master_user.delete()
                    
            return Response({"message": "Trainer, User, and Certificates successfully deleted."}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# ---------------------------------------------------------
# 6) Bulk Certificate Upload API
# ---------------------------------------------------------
class CertificateBulkUploadAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk, *args, **kwargs):
        try:
            trainer = MasterTrainer.objects.get(id=pk, is_active=True)
        except MasterTrainer.DoesNotExist:
            return Response({"error": "Master Trainer not found."}, status=status.HTTP_404_NOT_FOUND)

        # Expected format from frontend (FormData):
        # training_plans = [1, 2], themes = [3, 4], certificate_nos = ["A1", "B2"], 
        # issued_ons = ["2026-01-01", "2026-02-01"], files = [file1, file2]
        
        # Get MasterUser from authenticated user
        try:
            master_user = MasterUser.objects.get(
                username=request.user.username
            )
        except MasterUser.DoesNotExist:
            raise PermissionDenied("Invalid user")        

        training_plans = request.data.getlist('training_plans')
        themes = request.data.getlist('themes')
        certificate_nos = request.data.getlist('certificate_nos')
        issued_ons = request.data.getlist('issued_ons')
        files = request.FILES.getlist('files')

        if not files:
            return Response({"error": "No files provided."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                created_certs = []
                for i in range(len(files)):
                    cert = MasterTrainerCertificate.objects.create(
                        trainer=trainer,
                        training_plan_id=training_plans[i] if i < len(training_plans) and training_plans[i] else None,
                        theme_id=themes[i] if i < len(themes) and themes[i] else None,
                        certificate_no=certificate_nos[i] if i < len(certificate_nos) else None,
                        issued_on=issued_ons[i] if i < len(issued_ons) and issued_ons[i] else None,
                        certificate_file=files[i],
                        created_by=master_user
                    )
                    created_certs.append(cert.id)

            return Response({
                "message": f"{len(created_certs)} certificates uploaded successfully.",
                "certificate_ids": created_certs
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# ---------------------------------------------------------
# 7) Certificate Deletion API
# ---------------------------------------------------------
class CertificateDeleteAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, trainer_id, cert_id, *args, **kwargs):
        try:
            cert = MasterTrainerCertificate.objects.get(id=cert_id, trainer_id=trainer_id)
            cert.delete() # Trigger SoftDeleteMixin delete
            return Response({"message": "Certificate deleted successfully."}, status=status.HTTP_200_OK)
        except MasterTrainerCertificate.DoesNotExist:
            return Response({"error": "Certificate not found."}, status=status.HTTP_404_NOT_FOUND)