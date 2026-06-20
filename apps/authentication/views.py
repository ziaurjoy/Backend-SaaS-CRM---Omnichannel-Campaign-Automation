from rest_framework import status, generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from django.contrib.auth import get_user_model
from apps.authentication.serializers import RegisterSerializer, UserSerializer, OnboardingSerializer

User = get_user_model()

class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    permission_classes = (permissions.AllowAny,)
    serializer_class = RegisterSerializer

class UserProfileView(generics.RetrieveUpdateAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user

class OnboardingView(APIView):
    def post(self, request, *args, **kwargs):
        serializer = OnboardingSerializer(data=request.data)
        if serializer.is_valid():
            user, business = serializer.save_onboarding(request.user)
            return Response({
                "message": "Onboarding completed successfully.",
                "business_id": str(business.id),
                "business_name": business.name
            }, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
