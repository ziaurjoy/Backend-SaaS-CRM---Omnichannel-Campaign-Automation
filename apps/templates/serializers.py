from rest_framework import serializers
from apps.templates.models import Template

class TemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Template
        fields = '__all__'
        read_only_fields = ('id', 'business', 'created_at', 'updated_at')
