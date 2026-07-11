from rest_framework.views import APIView
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.db import transaction
from django_filters import rest_framework as filters

from .models import Ticket, TicketBody, TicketMedia
from core.models import MasterUser
from .serializers import TicketDetailSerializer

# ==========================================
# CUSTOM FILTER SET FOR LISTING
# ==========================================
class TicketFilter(filters.FilterSet):
    district_id = filters.NumberFilter(field_name='ticket_body__district_id')
    block_id = filters.NumberFilter(field_name='ticket_body__block_id')
    exact_date = filters.DateFilter(field_name='created_at', lookup_expr='date')
    from_date = filters.DateFilter(field_name='created_at', lookup_expr='date__gte')
    to_date = filters.DateFilter(field_name='created_at', lookup_expr='date__lte')
    mobile_no = filters.CharFilter(field_name='ticket_body__mobile_no', lookup_expr='icontains')

    class Meta:
        model = Ticket
        fields = ['district_id', 'block_id', 'exact_date', 'from_date', 'to_date', 'mobile_no']


# ==========================================
# 1) ONE-SHOT TICKET CREATION API
# ==========================================
class TicketCreateAPIView(APIView):
    permission_classes = [AllowAny]
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request, *args, **kwargs):
        data = request.data
        username = data.get('username')
        district_id = data.get('district_id')
        block_id = data.get('block_id')
        problem_message = data.get('problem_message')
        mobile_no = data.get('mobile_no')
        screenshots = request.FILES.getlist('screenshots')

        if len(screenshots) > 3:
            return Response(
                {"error": "A maximum of 3 screenshots are allowed per ticket."}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get MasterUser by provided username
        try:
            master_user = MasterUser.objects.get(username=username, is_active=True)
        except MasterUser.DoesNotExist:
            return Response({"error": f"Active user with username '{username}' not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            with transaction.atomic():
                # 1. Create the Ticket instance
                ticket = Ticket.objects.create(
                    master_user=master_user,
                    created_by=master_user,
                    pmu_response="" # default empty
                )

                # 2. Create the TicketBody instance
                TicketBody.objects.create(
                    ticket=ticket,
                    district_id=district_id,
                    block_id=block_id,
                    username=username,
                    problem_message=problem_message,
                    mobile_no=mobile_no,
                    created_by=master_user
                )

                # 3. Create TicketMedia instances (if any images are provided)
                for img in screenshots:
                    TicketMedia.objects.create(
                        ticket=ticket,
                        screenshot=img,
                        created_by=master_user
                    )

            return Response({
                "message": "Ticket created successfully.", 
                "ticket_code": ticket.ticket_code
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


# ==========================================
# 2) ONE-SHOT TICKET DELETION API
# ==========================================
class TicketDeleteAPIView(APIView):
    permission_classes = [IsAuthenticated]
    def delete(self, request, ticket_code, *args, **kwargs):
        # Fetch the requesting user object (Assuming request.user or request.username is available)
        request_username = getattr(request, 'username', request.user.username if hasattr(request.user, 'username') else None)
        
        if not request_username:
             return Response({"error": "Authentication details not found in request."}, status=status.HTTP_401_UNAUTHORIZED)
             
        try:
            deleted_by_user = MasterUser.objects.get(username=request_username)
        except MasterUser.DoesNotExist:
            return Response({"error": "Requesting user not found in MasterUser table."}, status=status.HTTP_403_FORBIDDEN)

        # Fetch active Ticket
        try:
            ticket = Ticket.objects.get(ticket_code=ticket_code, is_active=True)
        except Ticket.DoesNotExist:
            return Response({"error": "Active ticket not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            with transaction.atomic():
                # Soft delete Media
                for media in ticket.ticket_media.filter(is_active=True):
                    media.delete(by_user=deleted_by_user)
                
                # Soft delete Body
                if hasattr(ticket, 'ticket_body') and ticket.ticket_body.is_active:
                    ticket.ticket_body.delete(by_user=deleted_by_user)
                
                # Soft delete Ticket
                ticket.delete(by_user=deleted_by_user)

            return Response({"message": f"Ticket '{ticket_code}' and all related data successfully deleted."}, status=status.HTTP_200_OK)
        
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


# ==========================================
# 3) TICKET LISTING API
# ==========================================
class TicketListAPIView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = TicketDetailSerializer
    filter_backends = (filters.DjangoFilterBackend,)
    filterset_class = TicketFilter

    def get_queryset(self):
        request_username = getattr(self.request, 'username', self.request.user.username if hasattr(self.request.user, 'username') else None)
        
        if not request_username:
            return Ticket.objects.none()

        try:
            master_user = MasterUser.objects.get(username=request_username)
        except MasterUser.DoesNotExist:
            return Ticket.objects.none()

        # Start with all active tickets; Optimize query by prefetching
        qs = (
            Ticket.objects.filter(is_active=True)
            .select_related(
                "ticket_body",
                "ticket_body__district",
                "ticket_body__block",
            )
            .prefetch_related("ticket_media")
        )

        # Role Based Access logic
        # Assuming role_id is accessible via master_user.role_id (adjust based on your actual Core implementation)
        role_id = getattr(master_user, 'role_id', None)
        
        if role_id != 9:
            # If not role 9, restrict to tickets created by this user
            qs = qs.filter(created_by=master_user)

        return qs.order_by('-created_at')


# ==========================================
# 4) TICKET DETAIL API
# ==========================================
class TicketDetailAPIView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = TicketDetailSerializer
    lookup_field = 'ticket_code'

    def get_queryset(self):
        # We only return active tickets, optimized with select_related & prefetch_related
        return Ticket.objects.filter(is_active=True)\
            .select_related('ticket_body')\
            .prefetch_related('ticket_media')


# ==========================================
# 5) TICKET RESOLUTION API
# ==========================================
class TicketResolveAPIView(APIView):
    permission_classes = [IsAuthenticated] 

    def patch(self, request, ticket_code, *args, **kwargs):
        pmu_response = request.data.get('pmu_response')

        if not pmu_response or str(pmu_response).strip() == "":
            return Response(
                {"error": "The 'pmu_response' field is required to resolve a ticket."}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # Fetch the active Ticket
        try:
            ticket = Ticket.objects.get(ticket_code=ticket_code, is_active=True)
        except Ticket.DoesNotExist:
            return Response(
                {"error": "Active ticket not found."}, 
                status=status.HTTP_404_NOT_FOUND
            )

        # Fetch the requesting user object to log in 'updated_by'
        request_username = getattr(request, 'username', request.user.username if hasattr(request.user, 'username') else None)
        updated_by_user = None
        
        if request_username:
            try:
                updated_by_user = MasterUser.objects.get(username=request_username)
            except MasterUser.DoesNotExist:
                pass

        # Apply updates
        ticket.pmu_response = str(pmu_response).strip()
        ticket.is_solved = True
        
        if updated_by_user:
            ticket.updated_by = updated_by_user
            
        ticket.save()

        return Response({
            "message": f"Ticket '{ticket_code}' has been successfully resolved.",
            "ticket_code": ticket.ticket_code,
            "is_solved": ticket.is_solved,
            "pmu_response": ticket.pmu_response
        }, status=status.HTTP_200_OK)