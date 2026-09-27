from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from apps.tenants.models import Business
from apps.authentication.models import User
from apps.messaging.models import Integration

class WhatsAppQRIntegrationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser@example.com',
            email='testuser@example.com',
            password='testpassword123',
            first_name='Test',
            last_name='User'
        )
        self.business = Business.objects.create(
            name='Test Business',
            owner=self.user
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_generate_whatsapp_qr(self):
        response = self.client.post(
            '/api/integrations/generate_whatsapp_qr/',
            HTTP_X_BUSINESS_ID=str(self.business.id)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('session_id', response.data)
        self.assertIn('qr_code', response.data)
        self.assertEqual(response.data['status'], 'pending_scan')

    def test_confirm_whatsapp_qr(self):
        # Generate session first
        gen_res = self.client.post(
            '/api/integrations/generate_whatsapp_qr/',
            HTTP_X_BUSINESS_ID=str(self.business.id)
        )
        session_id = gen_res.data['session_id']

        # Confirm QR pairing
        confirm_res = self.client.post(
            '/api/integrations/confirm_whatsapp_qr/',
            {
                'session_id': session_id,
                'phone_number': '+1 (555) 123-4567',
                'device_name': 'Test WhatsApp Web'
            },
            format='json',
            HTTP_X_BUSINESS_ID=str(self.business.id)
        )
        self.assertEqual(confirm_res.status_code, status.HTTP_200_OK)
        self.assertEqual(confirm_res.data['integration']['connected_phone'], '+1 (555) 123-4567')

        # Verify Integration record in DB
        integration = Integration.objects.get(business=self.business, provider='WhatsApp')
        self.assertEqual(integration.status, 'Connected')
        self.assertEqual(integration.credentials.get('link_type'), 'WhatsApp_Standard_QR')
