from rest_framework import serializers
from apps.messaging.models import Message, Integration

class MessageSerializer(serializers.ModelSerializer):
    lead_name = serializers.CharField(source='lead.name', read_only=True)
    template_name = serializers.CharField(source='template.name', read_only=True)

    class Meta:
        model = Message
        fields = '__all__'
        read_only_fields = ('id', 'created_at')

class IntegrationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Integration
        fields = '__all__'
        read_only_fields = ('id', 'business', 'created_at', 'updated_at')
