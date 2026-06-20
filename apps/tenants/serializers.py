from rest_framework import serializers
from apps.tenants.models import Business, BusinessMember

class BusinessSerializer(serializers.ModelSerializer):
    class Meta:
        model = Business
        fields = '__all__'
        read_only_fields = ('id', 'created_at', 'updated_at')

class BusinessMemberSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)

    class Meta:
        model = BusinessMember
        fields = ('id', 'business', 'user', 'username', 'email', 'role', 'joined_at')
        read_only_fields = ('id', 'joined_at')
