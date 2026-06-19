import random
import os
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from apps.tenants.utils import TenantModelViewSetMixin
from apps.crm.models import Lead, Tag, LeadActivity
from apps.crm.serializers import LeadSerializer, TagSerializer, LeadActivitySerializer

class TagViewSet(TenantModelViewSetMixin, viewsets.ModelViewSet):
    queryset = Tag.objects.all()
    serializer_class = TagSerializer

class LeadViewSet(TenantModelViewSetMixin, viewsets.ModelViewSet):
    queryset = Lead.objects.all()
    serializer_class = LeadSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        # Enable basic stage filtering
        stage = self.request.query_params.get('stage')
        if stage:
            queryset = queryset.filter(stage=stage)
        return queryset

    @action(detail=True, methods=['get'], url_path='activities')
    def get_activities(self, request, pk=None):
        lead = self.get_object()
        activities = lead.activities.all().order_by('-created_at')
        serializer = LeadActivitySerializer(activities, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='activities/add')
    def add_activity(self, request, pk=None):
        lead = self.get_object()
        serializer = LeadActivitySerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(lead=lead, user=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], url_path='scrape_google_places')
    def scrape_google_places(self, request):
        query = request.data.get('query')
        if not query:
            return Response({'detail': 'query parameter is required.'}, status=status.HTTP_400_BAD_REQUEST)

        api_key = os.environ.get('GOOGLE_PLACES_API_KEY')
        scraped_leads = []

        if not api_key:
            # Sandbox / Mock Mode
            mock_names = []
            q_lower = query.lower()
            if 'cafe' in q_lower or 'coffee' in q_lower:
                mock_names = [
                    ("Bean & Brew Cafe", "https://beanandbrew.com"),
                    ("Central Park Coffee", "https://centralparkcoffee.com"),
                    ("The Roast & Toast", "https://roastandtoast.com"),
                    ("Espresso Express", "https://espressoexpress.com"),
                    ("Golden Mug Coffee House", "https://goldenmug.com")
                ]
            elif 'restaurant' in q_lower or 'food' in q_lower or 'dine' in q_lower:
                mock_names = [
                    ("The Tasty Table Bistro", "https://tastytable.com"),
                    ("Spice Route Restaurant", "https://spiceroute.com"),
                    ("Bella Italia Pizzeria", "https://bellaitaliapizza.com"),
                    ("Ocean Catch Seafood Grill", "https://oceancatchgrill.com"),
                    ("Garden Green Eatery", "https://gardengreeneatery.com")
                ]
            else:
                mock_names = [
                    (f"{query.title()} Hub", f"https://{query.replace(' ', '').lower()}hub.com"),
                    (f"Apex {query.title()} Services", f"https://apex{query.replace(' ', '').lower()}.com"),
                    (f"Global {query.title()} Group", f"https://global{query.replace(' ', '').lower()}.com"),
                    (f"Main Street {query.title()} Co.", f"https://mainstreet{query.replace(' ', '').lower()}.com"),
                    (f"Smart {query.title()} Solutions", f"https://smart{query.replace(' ', '').lower()}.com")
                ]

            for name, website in mock_names:
                phone = f"+1 (555) {random.randint(100, 999)}-{random.randint(1000, 9999)}"
                address = f"{random.randint(100, 999)} Main Street, Suite {random.randint(1, 20)}, New York, NY"
                rating = round(random.uniform(3.8, 5.0), 1)
                
                # Check for duplicates within this tenant
                if not Lead.objects.filter(business=request.business, name=name).exists():
                    lead = Lead.objects.create(
                        business=request.business,
                        name=name,
                        email=f"info@{name.lower().replace(' ', '').replace('&', 'and')}.com",
                        phone=phone,
                        website=website,
                        address=address,
                        rating=rating,
                        source="Google Places (Sandbox Mock)"
                    )
                    
                    LeadActivity.objects.create(
                        lead=lead,
                        activity_type="Log",
                        description=f"Lead automatically created via Google Places search for '{query}' (Sandbox Mock Mode)."
                    )
                    scraped_leads.append(lead)
            
            mode_used = "Sandbox Mock Mode (no API key configured)"
        else:
            # Here we would do a real request to Google Places API
            # For brevity and safety, we fallback to a structured result or implement the API call.
            # Let's write the real Google Places API textsearch integration:
            import requests
            url = f"https://maps.googleapis.com/maps/api/place/textsearch/json?query={query}&key={api_key}"
            try:
                r = requests.get(url)
                if r.status_code == 200:
                    results = r.json().get('results', [])[:5] # limit to 5
                    for item in results:
                        name = item.get('name')
                        address = item.get('formatted_address', '')
                        rating = item.get('rating')
                        place_id = item.get('place_id')
                        
                        # Get details (phone, website)
                        phone = ''
                        website = ''
                        details_url = f"https://maps.googleapis.com/maps/api/place/details/json?place_id={place_id}&fields=formatted_phone_number,website&key={api_key}"
                        dr = requests.get(details_url)
                        if dr.status_code == 200:
                            details = dr.json().get('result', {})
                            phone = details.get('formatted_phone_number', '')
                            website = details.get('website', '')

                        if not Lead.objects.filter(business=request.business, name=name).exists():
                            lead = Lead.objects.create(
                                business=request.business,
                                name=name,
                                email=f"contact@{name.lower().replace(' ', '')}.com" if not website else f"info@{website.split('//')[-1].replace('www.', '')}",
                                phone=phone,
                                website=website,
                                address=address,
                                rating=rating,
                                source="Google Places API"
                            )
                            LeadActivity.objects.create(
                                lead=lead,
                                activity_type="Log",
                                description=f"Lead automatically created via Google Places API search for '{query}'."
                            )
                            scraped_leads.append(lead)
                    mode_used = "Google Places API Live"
                else:
                    return Response({'detail': f'Google API returned error: {r.text}'}, status=status.HTTP_400_BAD_REQUEST)
            except Exception as e:
                return Response({'detail': f'Failed to search Google Places API: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        serializer = LeadSerializer(scraped_leads, many=True)
        return Response({
            "message": f"Successfully imported {len(scraped_leads)} leads using {mode_used}.",
            "leads": serializer.data
        }, status=status.HTTP_201_CREATED)
