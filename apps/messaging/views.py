from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.conf import settings
from apps.tenants.utils import IsTenantMember, TenantModelViewSetMixin
from apps.messaging.models import Message, Integration
from apps.messaging.serializers import MessageSerializer, IntegrationSerializer

class MessageViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = MessageSerializer
    permission_classes = [IsTenantMember]

    def get_queryset(self):
        # Filter messages belonging to the current active tenant
        return Message.objects.filter(lead__business=self.request.business).order_by('-created_at')

class IntegrationViewSet(TenantModelViewSetMixin, viewsets.ModelViewSet):
    queryset = Integration.objects.all()
    serializer_class = IntegrationSerializer

    @action(detail=False, methods=['get'], url_path='meta_config')
    def meta_config(self, request):
        app_id = getattr(settings, 'META_APP_ID', '')
        redirect_uri = getattr(settings, 'META_REDIRECT_URI', '')
        config_id = getattr(settings, 'META_CONFIG_ID', '')
        return Response({
            'meta_app_id': app_id,
            'meta_redirect_uri': redirect_uri,
            'meta_config_id': config_id,
            'is_mock_mode': not bool(app_id)
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='exchange_meta_code')
    def exchange_meta_code(self, request):
        code = request.data.get('code')
        mock_data = request.data.get('mock_data', {})
        
        # Check if code is provided (or mock data)
        if not code and not mock_data:
            return Response({'detail': 'code is required.'}, status=status.HTTP_400_BAD_REQUEST)
            
        app_id = request.data.get('meta_app_id') or getattr(settings, 'META_APP_ID', '')
        app_secret = request.data.get('meta_app_secret') or getattr(settings, 'META_APP_SECRET', '')
        redirect_uri = request.data.get('redirect_uri') or getattr(settings, 'META_REDIRECT_URI', '')
        
        if not app_id or not app_secret:
            # Sandbox Mock Mode
            phone_number = mock_data.get('phone_number', '+1 (555) 019-9992')
            waba_id = mock_data.get('waba_id', '102938475665748')
            phone_id = mock_data.get('phone_id', '109283746561')
            business_name = mock_data.get('business_name', 'Mock Business Meta')
            
            credentials = {
                'link_type': 'Meta_Embedded_Signup',
                'waba_id': waba_id,
                'phone_id': phone_id,
                'business_name': business_name,
                'token': 'EAAGb8vTz1...mock_meta_user_token',
                'mode': 'Sandbox Mock Mode'
            }
            
            integration, created = Integration.objects.update_or_create(
                business=request.business,
                provider='WhatsApp',
                defaults={
                    'credentials': credentials,
                    'status': 'Connected',
                    'connected_phone': phone_number
                }
            )
            serializer = self.get_serializer(integration)
            return Response({
                'message': 'WhatsApp successfully connected via simulated Meta Onboarding.',
                'integration': serializer.data
            }, status=status.HTTP_200_OK)
            
        # Live exchange
        import requests
        try:
            frontend_redirect_uri = request.data.get('redirect_uri')
            redirect_uri_options = []
            if frontend_redirect_uri:
                redirect_uri_options.append(frontend_redirect_uri)
            
            # Add settings redirect URI as fallback
            settings_redirect_uri = getattr(settings, 'META_REDIRECT_URI', '')
            if settings_redirect_uri and settings_redirect_uri not in redirect_uri_options:
                redirect_uri_options.append(settings_redirect_uri)
                
            # Add basic origins as further fallbacks if using localhost
            for opt in ['http://localhost:3000/dashboard/integrations', 'http://localhost:3000/', 'http://localhost:3000']:
                if opt not in redirect_uri_options:
                    redirect_uri_options.append(opt)

            user_access_token = None
            last_error_text = ""
            
            for r_uri in redirect_uri_options:
                try:
                    token_url = f"https://graph.facebook.com/v20.0/oauth/access_token?client_id={app_id}&redirect_uri={r_uri}&client_secret={app_secret}&code={code}"
                    r = requests.get(token_url)
                    if r.status_code == 200:
                        token_data = r.json()
                        user_access_token = token_data.get('access_token')
                        break
                    else:
                        last_error_text = r.text
                except Exception as e:
                    last_error_text = str(e)
                    
            if not user_access_token:
                return Response({'detail': f'Meta token exchange failed: {last_error_text}'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Step 2: Fetch WABA accounts
            waba_url = f"https://graph.facebook.com/v20.0/me/client_whatsapp_business_accounts?access_token={user_access_token}"
            waba_r = requests.get(waba_url)
            if waba_r.status_code != 200:
                return Response({'detail': f'Failed to fetch WABA accounts: {waba_r.text}'}, status=status.HTTP_400_BAD_REQUEST)
                
            waba_data = waba_r.json().get('data', [])
            if not waba_data:
                return Response({'detail': 'No WhatsApp Business Accounts found for this Meta user.'}, status=status.HTTP_400_BAD_REQUEST)
                
            # Select the first account for auto-provisioning
            waba_account = waba_data[0]
            waba_id = waba_account.get('id')
            waba_name = waba_account.get('name')
            
            # Step 3: Fetch phone numbers for this WABA
            phone_url = f"https://graph.facebook.com/v20.0/{waba_id}/phone_numbers?access_token={user_access_token}"
            phone_r = requests.get(phone_url)
            if phone_r.status_code != 200:
                return Response({'detail': f'Failed to fetch WhatsApp phone numbers: {phone_r.text}'}, status=status.HTTP_400_BAD_REQUEST)
                
            phone_data = phone_r.json().get('data', [])
            if not phone_data:
                return Response({'detail': f'No phone numbers registered under WABA ID {waba_id}.'}, status=status.HTTP_400_BAD_REQUEST)
                
            # Select the first phone number
            phone_info = phone_data[0]
            phone_id = phone_info.get('id')
            phone_number = phone_info.get('display_phone_number', '+1 (555) 000-0000')
            
            credentials = {
                'link_type': 'Meta_Embedded_Signup',
                'waba_id': waba_id,
                'phone_id': phone_id,
                'business_name': waba_name,
                'token': user_access_token
            }
            
            integration, created = Integration.objects.update_or_create(
                business=request.business,
                provider='WhatsApp',
                defaults={
                    'credentials': credentials,
                    'status': 'Connected',
                    'connected_phone': phone_number
                }
            )
            serializer = self.get_serializer(integration)
            return Response({
                'message': 'WhatsApp successfully connected via Meta Embedded Signup.',
                'integration': serializer.data
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({'detail': f'Meta connection error: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'], url_path='connect_whatsapp')
    def connect_whatsapp(self, request):
        phone_number = request.data.get('phone_number')
        credentials = request.data.get('credentials', {})
        status_val = request.data.get('status', 'Connected')

        if not phone_number:
            return Response({'detail': 'phone_number is required.'}, status=status.HTTP_400_BAD_REQUEST)

        integration, created = Integration.objects.update_or_create(
            business=request.business,
            provider='WhatsApp',
            defaults={
                'credentials': credentials,
                'status': status_val,
                'connected_phone': phone_number
            }
        )
        serializer = self.get_serializer(integration)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='connect_gmail')
    def connect_gmail(self, request):
        email = request.data.get('email')
        credentials = request.data.get('credentials', {})
        status_val = request.data.get('status', 'Connected')

        if not email:
            return Response({'detail': 'email is required.'}, status=status.HTTP_400_BAD_REQUEST)

        integration, created = Integration.objects.update_or_create(
            business=request.business,
            provider='Gmail',
            defaults={
                'credentials': credentials,
                'status': status_val,
                'connected_email': email
            }
        )
        serializer = self.get_serializer(integration)
        return Response(serializer.data, status=status.HTTP_200_OK)
