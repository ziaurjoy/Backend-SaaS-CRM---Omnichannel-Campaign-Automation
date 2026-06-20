from rest_framework.permissions import BasePermission
from rest_framework.exceptions import PermissionDenied, ValidationError
from apps.tenants.models import BusinessMember, Business

class IsTenantMember(BasePermission):
    """
    Permission check that the user is a member of the tenant (Business).
    Expects X-Business-ID header in the request.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
            
        business_id = request.headers.get('X-Business-ID') or request.query_params.get('business_id')
        if not business_id:
            # Let's see if the user belongs to exactly one business
            memberships = BusinessMember.objects.filter(user=request.user)
            if memberships.count() == 1:
                request.business = memberships.first().business
                request.business_role = memberships.first().role
                return True
            raise ValidationError({'detail': 'X-Business-ID header or business_id query parameter is required.'})

        try:
            membership = BusinessMember.objects.get(business_id=business_id, user=request.user)
            request.business = membership.business
            request.business_role = membership.role
            return True
        except BusinessMember.DoesNotExist:
            raise PermissionDenied({'detail': 'You do not have access to this business workspace.'})

class TenantModelViewSetMixin:
    """
    Mixin for ViewSets to automatically filter querysets by the current active business.
    """
    permission_classes = [IsTenantMember]

    def get_queryset(self):
        # Assumes the model has a foreign key named 'business'
        queryset = super().get_queryset()
        return queryset.filter(business=self.request.business)

    def perform_create(self, serializer):
        # Automatically assign the current tenant to the object on creation
        serializer.save(business=self.request.business)
