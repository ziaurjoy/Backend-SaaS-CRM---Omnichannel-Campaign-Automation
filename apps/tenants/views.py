from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from apps.tenants.models import Business, BusinessMember
from apps.tenants.serializers import BusinessSerializer, BusinessMemberSerializer

class BusinessViewSet(viewsets.ModelViewSet):
    serializer_class = BusinessSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Users should only see businesses they are members of
        return Business.objects.filter(members__user=self.request.user)

    def perform_create(self, serializer):
        business = serializer.save()
        # Automatically create Owner membership
        BusinessMember.objects.create(
            business=business,
            user=self.request.user,
            role='Owner'
        )

    @action(detail=True, methods=['get'], url_path='members')
    def get_members(self, request, pk=None):
        business = self.get_object()
        members = BusinessMember.objects.filter(business=business)
        serializer = BusinessMemberSerializer(members, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='invite')
    def invite_member(self, request, pk=None):
        # Simple invite/add logic for MVP
        business = self.get_object()
        user_id = request.data.get('user_id')
        role = request.data.get('role', 'Member')

        if not user_id:
            return Response({'detail': 'user_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        # Check if already a member
        if BusinessMember.objects.filter(business=business, user_id=user_id).exists():
            return Response({'detail': 'User is already a member of this workspace'}, status=status.HTTP_400_BAD_REQUEST)

        member = BusinessMember.objects.create(
            business=business,
            user_id=user_id,
            role=role
        )
        serializer = BusinessMemberSerializer(member)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
