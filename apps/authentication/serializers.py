from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.db import transaction
from apps.tenants.models import Business, BusinessMember

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'phone_number', 'profile_photo', 'timezone', 'first_name', 'last_name')
        read_only_fields = ('id', 'username', 'email')

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ('username', 'email', 'password', 'phone_number', 'timezone', 'first_name', 'last_name')

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data.get('email'),
            password=validated_data['password'],
            phone_number=validated_data.get('phone_number', ''),
            timezone=validated_data.get('timezone', 'UTC'),
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', '')
        )
        return user

class OnboardingSerializer(serializers.Serializer):
    # User fields
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    phone_number = serializers.CharField(max_length=20, required=False, allow_blank=True)
    timezone = serializers.CharField(max_length=50, default='UTC')
    profile_photo = serializers.CharField(max_length=500, required=False, allow_blank=True)

    # Business fields
    business_name = serializers.CharField(max_length=255)
    business_logo = serializers.CharField(max_length=500, required=False, allow_blank=True)
    industry = serializers.CharField(max_length=100, required=False, allow_blank=True)
    website = serializers.URLField(required=False, allow_null=True)
    country = serializers.CharField(max_length=100, required=False, allow_blank=True)
    address = serializers.CharField(required=False, allow_blank=True)

    @transaction.atomic
    def save_onboarding(self, user):
        # Update user details
        user.first_name = self.validated_data['first_name']
        user.last_name = self.validated_data['last_name']
        user.phone_number = self.validated_data.get('phone_number', '')
        user.timezone = self.validated_data.get('timezone', 'UTC')
        if self.validated_data.get('profile_photo'):
            user.profile_photo = self.validated_data['profile_photo']
        user.save()

        # Create Business
        business = Business.objects.create(
            name=self.validated_data['business_name'],
            logo=self.validated_data.get('business_logo', ''),
            industry=self.validated_data.get('industry', ''),
            website=self.validated_data.get('website'),
            country=self.validated_data.get('country', ''),
            address=self.validated_data.get('address', ''),
            timezone=user.timezone
        )

        # Create Business Member as Owner
        BusinessMember.objects.create(
            business=business,
            user=user,
            role='Owner'
        )

        return user, business
