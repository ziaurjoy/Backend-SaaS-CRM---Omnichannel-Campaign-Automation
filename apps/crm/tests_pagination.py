from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient, APIRequestFactory
from rest_framework import status

from apps.tenants.models import Business
from apps.crm.models import Lead, LeadCollection
from apps.campaigns.models import Campaign, CampaignRun
from apps.templates.models import Template
from apps.messaging.models import Message
from config.pagination import StandardResultsSetPagination

User = get_user_model()

class StandardResultsSetPaginationTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="pagination_user",
            email="pagination@example.com",
            password="securepassword123"
        )
        self.business = Business.objects.create(name="Pagination Test Tenant")
        self.user.business = self.business
        self.user.save()
        
        self.client.force_authenticate(user=self.user)
        self.client.credentials(HTTP_X_BUSINESS_ID=str(self.business.id))

    def test_empty_results_pagination_structure(self):
        """Verifies that an empty dataset returns standard pagination structure with total_pages=1."""
        response = self.client.get('/api/leads/?page=1&page_size=20')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('count', response.data)
        self.assertIn('total_pages', response.data)
        self.assertIn('page', response.data)
        self.assertIn('page_size', response.data)
        self.assertIn('next', response.data)
        self.assertIn('previous', response.data)
        self.assertIn('results', response.data)
        self.assertEqual(response.data['count'], 0)
        self.assertEqual(response.data['total_pages'], 1)
        self.assertEqual(response.data['page'], 1)
        self.assertEqual(response.data['page_size'], 20)
        self.assertIsNone(response.data['next'])
        self.assertIsNone(response.data['previous'])
        self.assertEqual(response.data['results'], [])

    def test_pagination_metadata_and_limits(self):
        """Verifies total_pages, page, count, page_size, next, and previous across multi-page dataset."""
        collection = LeadCollection.objects.create(
            business=self.business,
            name="Pagination Leads"
        )
        # Create 25 leads
        leads = [
            Lead(
                business=self.business,
                collection=collection,
                name=f"Lead {i:02d}",
                stage="New"
            )
            for i in range(1, 26)
        ]
        Lead.objects.bulk_create(leads)

        # Page 1 with page_size=10
        res_p1 = self.client.get(f'/api/leads/?collection={collection.id}&page=1&page_size=10')
        self.assertEqual(res_p1.status_code, status.HTTP_200_OK)
        self.assertEqual(res_p1.data['count'], 25)
        self.assertEqual(res_p1.data['total_pages'], 3)
        self.assertEqual(res_p1.data['page'], 1)
        self.assertEqual(res_p1.data['page_size'], 10)
        self.assertEqual(len(res_p1.data['results']), 10)
        self.assertIsNotNone(res_p1.data['next'])
        self.assertIsNone(res_p1.data['previous'])

        # Page 2
        res_p2 = self.client.get(f'/api/leads/?collection={collection.id}&page=2&page_size=10')
        self.assertEqual(res_p2.status_code, status.HTTP_200_OK)
        self.assertEqual(res_p2.data['page'], 2)
        self.assertEqual(len(res_p2.data['results']), 10)
        self.assertIsNotNone(res_p2.data['next'])
        self.assertIsNotNone(res_p2.data['previous'])

        # Page 3 (final page with 5 items)
        res_p3 = self.client.get(f'/api/leads/?collection={collection.id}&page=3&page_size=10')
        self.assertEqual(res_p3.status_code, status.HTTP_200_OK)
        self.assertEqual(res_p3.data['page'], 3)
        self.assertEqual(len(res_p3.data['results']), 5)
        self.assertIsNone(res_p3.data['next'])
        self.assertIsNotNone(res_p3.data['previous'])

    def test_out_of_bounds_page_returns_404(self):
        """Verifies that requesting a page beyond total_pages returns 404."""
        response = self.client.get('/api/leads/?page=999&page_size=10')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_max_page_size_enforcement(self):
        """Verifies that page_size is capped at max_page_size (100)."""
        paginator = StandardResultsSetPagination()
        factory = APIRequestFactory()
        request = factory.get('/api/leads/?page_size=500')
        size = paginator.get_page_size(request)
        self.assertEqual(size, 100)

    def test_campaign_messages_endpoint_pagination(self):
        """Verifies that the Campaign messages action endpoint adheres to standard pagination."""
        campaign = Campaign.objects.create(
            business=self.business,
            name="Test Outreach Campaign",
            channel="Email"
        )
        campaign_run = CampaignRun.objects.create(
            campaign=campaign,
            status="Running"
        )
        lead = Lead.objects.create(
            business=self.business,
            name="Target Recipient",
            email="target@example.com"
        )
        # Create 15 messages
        messages = [
            Message(
                business=self.business,
                lead=lead,
                campaign_run=campaign_run,
                channel="Email",
                recipient=f"user{i}@example.com",
                status="Sent"
            )
            for i in range(1, 16)
        ]
        Message.objects.bulk_create(messages)

        res = self.client.get(f'/api/campaigns/{campaign.id}/messages/?page=1&page_size=5')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['count'], 15)
        self.assertEqual(res.data['total_pages'], 3)
        self.assertEqual(res.data['page'], 1)
        self.assertEqual(res.data['page_size'], 5)
        self.assertEqual(len(res.data['results']), 5)
        self.assertIsNotNone(res.data['next'])

    def test_template_endpoint_pagination(self):
        """Verifies that TemplateViewSet produces standardized pagination."""
        templates = [
            Template(
                business=self.business,
                name=f"Template {i}",
                type="Email",
                body=f"Hello user {i}"
            )
            for i in range(1, 12)
        ]
        Template.objects.bulk_create(templates)

        res = self.client.get('/api/templates/?page=1&page_size=5')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['count'], 11)
        self.assertEqual(res.data['total_pages'], 3)
        self.assertEqual(len(res.data['results']), 5)

    def test_collections_endpoint_pagination(self):
        """Verifies that LeadCollectionViewSet produces standardized pagination."""
        collections = [
            LeadCollection(
                business=self.business,
                name=f"Collection {i}"
            )
            for i in range(1, 8)
        ]
        LeadCollection.objects.bulk_create(collections)

        res = self.client.get('/api/collections/?page=1&page_size=3')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['count'], 7)
        self.assertEqual(res.data['total_pages'], 3)
        self.assertEqual(len(res.data['results']), 3)
