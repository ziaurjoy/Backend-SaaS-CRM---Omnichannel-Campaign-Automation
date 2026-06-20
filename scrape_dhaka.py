import os
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.tenants.models import Business, BusinessMember
from apps.crm.models import Lead
from apps.crm.views import LeadViewSet
from rest_framework.test import APIRequestFactory, force_authenticate
from django.contrib.auth import get_user_model

User = get_user_model()

# Get the first business and user in the database
business = Business.objects.first()
user = User.objects.first()

if not business:
    print("Error: No business found. Please make sure the database is initialized and seeded.")
    exit(1)
if not user:
    print("Error: No user found. Please make sure the database is initialized and seeded.")
    exit(1)

# Ensure membership exists for the user in this business
BusinessMember.objects.get_or_create(
    business=business, 
    user=user, 
    defaults={'role': 'Admin'}
)

print(f"Using Business: {business.name} (ID: {business.id})")
print(f"Using User: {user.username}")

# Construct the API request with the query
factory = APIRequestFactory()
request = factory.post('/api/leads/scrape_google_places/', {'query': 'software company dhaka'}, format='json')

# Authenticate request
force_authenticate(request, user=user)

# Inject header in request META
request.META['HTTP_X_BUSINESS_ID'] = str(business.id)

# Inject headers/attributes required by IsTenantMember and TenantModelViewSetMixin
request.business = business
request.user = user

# Execute the view action
print("\nInitiating Google Places scraping for 'software company dhaka'...")
view = LeadViewSet.as_view({'post': 'scrape_google_places'})
response = view(request)

print(f"\nResponse Status: {response.status_code}")
if response.status_code == 201:
    print("Success! Response Details:")
    print(response.data.get('message'))
    leads = response.data.get('leads', [])
    print(f"Imported {len(leads)} leads:")
    for lead in leads:
        print(f"- {lead['name']} | Phone: {lead['phone']} | Website: {lead['website']} | Rating: {lead['rating']}")
else:
    print("Failed to scrape leads:")
    print(response.data)
