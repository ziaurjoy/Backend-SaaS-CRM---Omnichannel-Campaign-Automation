import json
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status

from apps.tenants.models import Business, BusinessMember
from apps.crm.models import Lead, LeadCollection, GooglePlaceScrapeSession, LeadActivity

User = get_user_model()

class GooglePlacesIntegrationTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="password123"
        )
        self.business = Business.objects.create(
            name="Test Tenant Corp"
        )
        self.user.business = self.business
        self.user.save()
        BusinessMember.objects.create(
            business=self.business,
            user=self.user,
            role='Owner'
        )
        
        self.collection = LeadCollection.objects.create(
            business=self.business,
            name="Target Tech Companies",
            description="Tech collection"
        )
        self.client.force_authenticate(user=self.user)
        self.client.credentials(HTTP_X_BUSINESS_ID=str(self.business.id))

    def test_request_validation_missing_query(self):
        """Validates that missing textQuery returns 400 Bad Request."""
        response = self.client.post('/api/leads/scrape_google_places/', {
            'collection_id': self.collection.id
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('textQuery', response.data.get('detail', ''))

    def test_request_validation_invalid_collection(self):
        """Validates that non-existent collection returns 404 Not Found."""
        response = self.client.post('/api/leads/scrape_google_places/', {
            'textQuery': 'coffee shops',
            'collection_id': 999999
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @patch('requests.post')
    def test_pagination_fetches_all_pages_using_next_page_token(self, mock_post):
        """
        Validates complete pagination:
        Page 1 returns nextPageToken -> triggers Page 2 request with pageToken -> terminates when no token remains.
        """
        page1_response = MagicMock()
        page1_response.status_code = 200
        page1_response.json.return_value = {
            "places": [
                {
                    "id": "place_001",
                    "displayName": {"text": "Alpha Software Corp"},
                    "formattedAddress": "100 Tech Blvd, Silicon Valley",
                    "internationalPhoneNumber": "+1 555-0101",
                    "websiteUri": "https://alphasoft.com",
                    "rating": 4.8,
                    "userRatingCount": 150,
                    "location": {"latitude": 37.7749, "longitude": -122.4194},
                    "businessStatus": "OPERATIONAL",
                    "types": ["software_company", "technology"],
                    "primaryType": "software_company",
                    "primaryTypeDisplayName": {"text": "Software Company"},
                    "priceLevel": "PRICE_LEVEL_MODERATE"
                }
            ],
            "nextPageToken": "token_for_page_2"
        }

        page2_response = MagicMock()
        page2_response.status_code = 200
        page2_response.json.return_value = {
            "places": [
                {
                    "id": "place_002",
                    "displayName": {"text": "Beta Cloud Labs"},
                    "formattedAddress": "200 Cloud Way, Silicon Valley",
                    "internationalPhoneNumber": "+1 555-0102",
                    "websiteUri": "https://betacloud.com",
                    "rating": 4.5,
                    "userRatingCount": 85,
                    "location": {"latitude": 37.7849, "longitude": -122.4094},
                    "businessStatus": "OPERATIONAL",
                    "types": ["software_company", "saas"],
                    "primaryType": "software_company",
                    "primaryTypeDisplayName": {"text": "Software Company"}
                }
            ]
            # No nextPageToken -> end of pagination
        }

        mock_post.side_effect = [page1_response, page2_response]

        response = self.client.post('/api/leads/scrape_google_places/', {
            'textQuery': 'software companies',
            'pageSize': 10,
            'collection_id': self.collection.id,
            'fetchAllPages': True
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['pages_fetched'], 2)
        self.assertEqual(response.data['total_scraped'], 2)
        self.assertEqual(response.data['created_count'], 2)
        self.assertEqual(response.data['updated_count'], 0)

        # Verify Google API calls were formatted correctly
        self.assertEqual(mock_post.call_count, 2)
        
        # Verify first call payload had textQuery and pageSize
        call1_kwargs = mock_post.call_args_list[0][1]
        self.assertEqual(call1_kwargs['json']['textQuery'], 'software companies')
        self.assertEqual(call1_kwargs['json']['pageSize'], 10)
        self.assertNotIn('pageToken', call1_kwargs['json'])

        # Verify second call passed pageToken
        call2_kwargs = mock_post.call_args_list[1][1]
        self.assertEqual(call2_kwargs['json']['pageToken'], 'token_for_page_2')

        # Verify database records
        lead1 = Lead.objects.get(business=self.business, place_id='place_001')
        self.assertEqual(lead1.name, 'Alpha Software Corp')
        self.assertEqual(lead1.phone, '+1 555-0101')
        self.assertEqual(lead1.primary_type, 'software_company')
        self.assertEqual(float(lead1.rating), 4.8)

        lead2 = Lead.objects.get(business=self.business, place_id='place_002')
        self.assertEqual(lead2.name, 'Beta Cloud Labs')

        # Verify session logged
        session = GooglePlaceScrapeSession.objects.get(id=response.data['session_id'])
        self.assertEqual(session.status, 'Completed')
        self.assertEqual(session.pages_fetched, 2)

    @patch('requests.post')
    def test_infinite_loop_prevention_on_repeated_token(self, mock_post):
        """Validates that encountering a repeated nextPageToken safely terminates pagination."""
        repeated_response = MagicMock()
        repeated_response.status_code = 200
        repeated_response.json.return_value = {
            "places": [
                {
                    "id": "place_loop_1",
                    "displayName": {"text": "Loop Test Place"}
                }
            ],
            "nextPageToken": "stuck_infinite_token"
        }
        # Simulate API returning the same token indefinitely
        mock_post.return_value = repeated_response

        response = self.client.post('/api/leads/scrape_google_places/', {
            'textQuery': 'loop test',
            'collection_id': self.collection.id,
            'fetchAllPages': True,
            'maxPages': 10
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        # Should stop immediately when detecting the repeated token on iteration 2
        self.assertLessEqual(mock_post.call_count, 2)

    @patch('requests.post')
    def test_duplicate_prevention_and_incremental_updates(self, mock_post):
        """
        Validates that re-scraping an existing place updates its details
        without duplicating records.
        """
        # 1. First scrape run
        resp1 = MagicMock()
        resp1.status_code = 200
        resp1.json.return_value = {
            "places": [
                {
                    "id": "place_dup_001",
                    "displayName": {"text": "Original Place Name"},
                    "formattedAddress": "Original Address 101",
                    "rating": 4.0,
                    "userRatingCount": 50,
                    "businessStatus": "OPERATIONAL"
                }
            ]
        }
        mock_post.return_value = resp1

        res1 = self.client.post('/api/leads/scrape_google_places/', {
            'textQuery': 'coffee',
            'collection_id': self.collection.id
        }, format='json')
        self.assertEqual(res1.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res1.data['created_count'], 1)
        self.assertEqual(res1.data['updated_count'], 0)
        self.assertEqual(Lead.objects.filter(business=self.business, place_id='place_dup_001').count(), 1)

        # 2. Second scrape run with updated ratings and address
        resp2 = MagicMock()
        resp2.status_code = 200
        resp2.json.return_value = {
            "places": [
                {
                    "id": "place_dup_001",
                    "displayName": {"text": "Original Place Name"},
                    "formattedAddress": "Updated New Address 999",
                    "rating": 4.9,
                    "userRatingCount": 120,
                    "internationalPhoneNumber": "+1 888-999-0000",
                    "businessStatus": "OPERATIONAL"
                }
            ]
        }
        mock_post.return_value = resp2

        res2 = self.client.post('/api/leads/scrape_google_places/', {
            'textQuery': 'coffee',
            'collection_id': self.collection.id
        }, format='json')
        self.assertEqual(res2.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res2.data['created_count'], 0)
        self.assertEqual(res2.data['updated_count'], 1)

        # Still strictly 1 record in database, but with updated values
        self.assertEqual(Lead.objects.filter(business=self.business, place_id='place_dup_001').count(), 1)
        updated_lead = Lead.objects.get(business=self.business, place_id='place_dup_001')
        self.assertEqual(updated_lead.address, "Updated New Address 999")
        self.assertEqual(float(updated_lead.rating), 4.9)
        self.assertEqual(updated_lead.user_ratings_total, 120)
        self.assertIn(updated_lead.phone, ["+18889990000", "+1 888-999-0000"])

    @patch('requests.post')
    def test_failure_recovery_on_google_api_error(self, mock_post):
        """Validates error recovery when Google Places API responds with 403 or 500."""
        err_resp = MagicMock()
        err_resp.status_code = 403
        err_resp.text = json.dumps({"error": {"message": "API key has expired or lacks permissions."}})
        err_resp.json.return_value = {"error": {"message": "API key has expired or lacks permissions."}}
        mock_post.return_value = err_resp

        response = self.client.post('/api/leads/scrape_google_places/', {
            'textQuery': 'failing query',
            'collection_id': self.collection.id
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertIn("API key has expired", response.data['detail'])

        # Verify session is marked as Failed
        failed_session = GooglePlaceScrapeSession.objects.filter(
            business=self.business,
            query='failing query'
        ).latest('created_at')
        self.assertEqual(failed_session.status, 'Failed')
        self.assertIn("API key has expired", failed_session.error_message)

    def test_server_side_pagination_search_and_sorting(self):
        """Validates server-side pagination, search, stage/rating filtering, and sorting."""
        # Create 5 test leads
        for i in range(1, 6):
            Lead.objects.create(
                business=self.business,
                collection=self.collection,
                name=f"Business {i}",
                rating=3.0 + (i * 0.4),
                user_ratings_total=i * 20,
                stage="Qualified" if i % 2 == 0 else "New",
                business_status="OPERATIONAL"
            )

        # 1. Test Pagination: page_size=2
        res_p1 = self.client.get(f'/api/leads/?collection={self.collection.id}&page=1&page_size=2')
        self.assertEqual(res_p1.status_code, status.HTTP_200_OK)
        self.assertEqual(res_p1.data['count'], 5)
        self.assertEqual(len(res_p1.data['results']), 2)
        self.assertIsNotNone(res_p1.data['next'])

        # 2. Test Search
        res_search = self.client.get(f'/api/leads/?collection={self.collection.id}&search=Business 3')
        self.assertEqual(res_search.data['count'], 1)
        self.assertEqual(res_search.data['results'][0]['name'], 'Business 3')

        # 3. Test Filter by Stage
        res_stage = self.client.get(f'/api/leads/?collection={self.collection.id}&stage=Qualified')
        self.assertEqual(res_stage.data['count'], 2)

        # 4. Test Sorting by rating descending
        res_sort = self.client.get(f'/api/leads/?collection={self.collection.id}&ordering=-rating')
        first_lead = res_sort.data['results'][0]
        self.assertEqual(first_lead['name'], 'Business 5')


class WhatsAppDetectionTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="wa_testuser",
            email="wa_test@example.com",
            password="password123"
        )
        self.business = Business.objects.create(
            name="WA Test Business",
            country="BD"
        )
        self.user.business = self.business
        self.user.save()
        BusinessMember.objects.create(
            business=self.business,
            user=self.user,
            role='Owner'
        )

        from apps.messaging.models import Integration
        self.integration = Integration.objects.create(
            business=self.business,
            provider='WhatsApp',
            status='Connected',
            connected_phone='+8801771833614',
            credentials={
                'link_type': 'WhatsApp_Standard_QR',
                'session_id': f"wa_business_{self.business.id}"
            }
        )

        self.collection = LeadCollection.objects.create(
            business=self.business,
            name="WA Leads Collection"
        )
        self.client.force_authenticate(user=self.user)
        self.client.credentials(HTTP_X_BUSINESS_ID=str(self.business.id))

    def test_phone_number_validation_and_e164_normalization(self):
        """Test that various national and international phone formats normalize to E.164."""
        from apps.crm.services.phone_validator import validate_and_normalize_phone, normalize_phone_e164

        # Bangladesh local format with country code context
        res_bd = validate_and_normalize_phone('01771833614', default_region='BD')
        self.assertTrue(res_bd['is_valid'])
        self.assertEqual(res_bd['e164'], '+8801771833614')

        # US format with dashes and parentheses
        res_us = validate_and_normalize_phone('+1 (415) 555-2671')
        self.assertTrue(res_us['is_valid'])
        self.assertEqual(res_us['e164'], '+14155552671')

        # Invalid phone string
        res_inv = validate_and_normalize_phone('not-a-number')
        self.assertFalse(res_inv['is_valid'])
        self.assertIsNone(res_inv['e164'])

    @patch('requests.post')
    def test_whatsapp_verification_success_sets_status_true(self, mock_post):
        """When the WhatsApp microservice verifies a number, whatsapp_status becomes True."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'status': 'success',
            'phone': '+8801771833614',
            'e164': '+8801771833614',
            'exists': True,
            'jid': '8801771833614@s.whatsapp.net'
        }
        mock_post.return_value = mock_response

        lead = Lead.objects.create(
            business=self.business,
            collection=self.collection,
            name="Verified Lead",
            phone="01771833614"
        )

        from apps.crm.services.whatsapp_verifier import WhatsAppVerifierService
        verifier = WhatsAppVerifierService()
        result = verifier.verify_lead(lead, force_check=True)

        lead.refresh_from_db()
        self.assertTrue(result['whatsapp_status'])
        self.assertTrue(lead.whatsapp_status)
        self.assertEqual(lead.phone, '+8801771833614')
        self.assertIsNotNone(lead.whatsapp_verified_at)
        self.assertEqual(lead.whatsapp_jid, '8801771833614@s.whatsapp.net')

        # Check that activity was logged
        activity = lead.activities.filter(activity_type='WhatsApp').first()
        self.assertIsNotNone(activity)
        self.assertIn('+8801771833614', activity.description)

    @patch('requests.post')
    def test_whatsapp_verification_unregistered_keeps_status_false(self, mock_post):
        """When number is not on WhatsApp, whatsapp_status remains False and no icon flag."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'status': 'success',
            'phone': '+15550009999',
            'e164': '+15550009999',
            'exists': False,
            'jid': None
        }
        mock_post.return_value = mock_response

        lead = Lead.objects.create(
            business=self.business,
            collection=self.collection,
            name="Unregistered Lead",
            phone="+15550009999"
        )

        from apps.crm.services.whatsapp_verifier import WhatsAppVerifierService
        verifier = WhatsAppVerifierService()
        result = verifier.verify_lead(lead, force_check=True)

        lead.refresh_from_db()
        self.assertFalse(result['whatsapp_status'])
        self.assertFalse(lead.whatsapp_status)
        self.assertIsNone(lead.whatsapp_verified_at)

    @patch('requests.post')
    def test_avoid_unnecessary_repeated_api_calls_if_already_verified(self, mock_post):
        """Verify that previously verified leads skip redundant API calls unless force=True."""
        lead = Lead.objects.create(
            business=self.business,
            collection=self.collection,
            name="Cached Lead",
            phone="+8801771833614",
            whatsapp_status=True
        )

        from apps.crm.services.whatsapp_verifier import WhatsAppVerifierService
        verifier = WhatsAppVerifierService()
        result = verifier.verify_lead(lead, force_check=False)

        self.assertTrue(result.get('cached'))
        mock_post.assert_not_called()

    @patch('requests.post')
    def test_automatic_verification_triggered_on_lead_creation(self, mock_post):
        """Creating a lead via API automatically normalizes phone and triggers WhatsApp check."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'status': 'success',
            'phone': '+8801771833614',
            'e164': '+8801771833614',
            'exists': True,
            'jid': '8801771833614@s.whatsapp.net'
        }
        mock_post.return_value = mock_response

        response = self.client.post('/api/leads/', {
            'name': 'Auto-Check Lead',
            'phone': '01771833614',
            'collection': self.collection.id,
            'source': 'Manual'
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        lead_id = response.data['id']
        lead = Lead.objects.get(id=lead_id)
        self.assertEqual(lead.phone, '+8801771833614')
        self.assertTrue(lead.whatsapp_status)

    @patch('requests.post')
    def test_verify_whatsapp_detail_action(self, mock_post):
        """Manual verification trigger on detail endpoint POST /api/leads/{id}/verify_whatsapp/"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'status': 'success',
            'phone': '+8801771833614',
            'e164': '+8801771833614',
            'exists': True,
            'jid': '8801771833614@s.whatsapp.net'
        }
        mock_post.return_value = mock_response

        lead = Lead.objects.create(
            business=self.business,
            collection=self.collection,
            name="Manual Check Lead",
            phone="+8801771833614",
            whatsapp_status=False
        )

        response = self.client.post(f'/api/leads/{lead.id}/verify_whatsapp/', {'force': True}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['lead']['whatsapp_status'])

    def test_filter_leads_by_whatsapp_status(self):
        """Filtering /api/leads/?whatsapp_status=true returns only WhatsApp verified leads."""
        Lead.objects.create(
            business=self.business,
            collection=self.collection,
            name="WA Lead 1",
            phone="+8801771833614",
            whatsapp_status=True
        )
        Lead.objects.create(
            business=self.business,
            collection=self.collection,
            name="Non-WA Lead 2",
            phone="+15550009999",
            whatsapp_status=False
        )

        res_true = self.client.get('/api/leads/?whatsapp_status=true')
        self.assertEqual(res_true.status_code, status.HTTP_200_OK)
        for item in res_true.data['results']:
            self.assertTrue(item['whatsapp_status'])

        res_false = self.client.get('/api/leads/?whatsapp_status=false')
        self.assertEqual(res_false.status_code, status.HTTP_200_OK)
        for item in res_false.data['results']:
            self.assertFalse(item['whatsapp_status'])

    @patch('requests.post')
    def test_graceful_error_handling_on_service_failure(self, mock_post):
        """API failures or service timeouts do not crash the system; whatsapp_status stays False."""
        mock_post.side_effect = Exception("Connection refused to WhatsApp microservice")

        lead = Lead.objects.create(
            business=self.business,
            collection=self.collection,
            name="Resilient Lead",
            phone="+8801771833614",
            whatsapp_status=False
        )

        from apps.crm.services.whatsapp_verifier import WhatsAppVerifierService
        verifier = WhatsAppVerifierService()
        result = verifier.verify_lead(lead, force_check=True)

        lead.refresh_from_db()
        self.assertFalse(lead.whatsapp_status)
        self.assertEqual(result['status'], 'service_error')
        self.assertIn("Could not connect to WhatsApp verification service", result['error'])

