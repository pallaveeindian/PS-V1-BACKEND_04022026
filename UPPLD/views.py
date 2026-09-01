import json
import base64
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction
from .serializers import AspirationalBlockAchievementSerializer
from .models import AspirationalBlockAchievement

class SyncAspirationalBlocksDataView(APIView):
    """
    Accepts the EXACT SAME PAYLOAD as the Planning Dept API.
    Decodes the Base64 JSON array and stores the 108 blocks data categorized by month/year.
    """
    def post(self, request, *args, **kwargs):
        user_hash = request.data.get('UserHash')
        json_data_b64 = request.data.get('JSON_Data')

        if not json_data_b64:
            return Response(
                {"status": "Error", "message": "JSON_Data payload is missing."}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # 1. Decode the Base64 Payload
            decoded_bytes = base64.b64decode(json_data_b64)
            decoded_str = decoded_bytes.decode('utf-8')
            
            # 2. Parse the JSON Array
            payload_array = json.loads(decoded_str)

            if not isinstance(payload_array, list):
                return Response(
                    {"status": "Error", "message": "Decoded JSON is not an array."}, 
                    status=status.HTTP_400_BAD_REQUEST
                )

            # 3. Process and Save the Data
            success_count = 0
            
            # Using transaction.atomic ensures that if the database fails halfway through, 
            # it rolls back so you don't get partial data saves.
            with transaction.atomic():
                for item in payload_array:
                    serializer = AspirationalBlockAchievementSerializer(data=item)
                    
                    if serializer.is_valid():
                        val_data = serializer.validated_data
                        
                        # update_or_create ensures we don't get duplicates if they push twice in the same month
                        AspirationalBlockAchievement.objects.update_or_create(
                            year=val_data['year'],
                            month=val_data['month'],
                            dist_code=val_data['dist_code'],
                            block_code=val_data['block_code'],
                            prog_code=val_data['prog_code'], # This handles BOTH 0511 and 0512 categorization automatically
                            defaults=val_data
                        )
                        success_count += 1
                    else:
                        # Log serializer errors for debugging but continue processing
                        print(f"Validation Error for block {item.get('Block_code')}: {serializer.errors}")

            return Response({
                "status": "Success",
                "message": f"Successfully synchronized and stored {success_count} block records.",
                "hash_received": bool(user_hash)
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                "status": "Error",
                "message": f"Server encountered an error while decoding/saving data: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)