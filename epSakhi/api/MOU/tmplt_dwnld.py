from rest_framework.views import APIView
from django.http import FileResponse, Http404
from pathlib import Path


class MOUTemplateDownloadAPIView(APIView):

    def get(self, request):
        file_path = Path("media/MOUForm/MOU_Template.docx")

        if not file_path.exists():
            raise Http404("File not found")

        return FileResponse(
            open(file_path, "rb"),
            as_attachment=True,
            filename="MOU_Template.docx"
        )