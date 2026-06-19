from rest_framework import viewsets
from apps.tenants.utils import TenantModelViewSetMixin
from apps.templates.models import Template
from apps.templates.serializers import TemplateSerializer

class TemplateViewSet(TenantModelViewSetMixin, viewsets.ModelViewSet):
    queryset = Template.objects.all()
    serializer_class = TemplateSerializer
