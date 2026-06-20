import os
import time
import random
import requests
from urllib.parse import urlparse
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from apps.tenants.utils import TenantModelViewSetMixin
from django.db.models import Q
from apps.crm.models import Lead, Tag, LeadActivity, LeadCollection
from apps.crm.serializers import LeadSerializer, TagSerializer, LeadActivitySerializer, LeadCollectionSerializer

class TagViewSet(TenantModelViewSetMixin, viewsets.ModelViewSet):
    queryset = Tag.objects.all()
    serializer_class = TagSerializer

class LeadCollectionViewSet(TenantModelViewSetMixin, viewsets.ModelViewSet):
    queryset = LeadCollection.objects.all()
    serializer_class = LeadCollectionSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(description__icontains=search)
            )
        return queryset

class LeadViewSet(TenantModelViewSetMixin, viewsets.ModelViewSet):
    queryset = Lead.objects.all()
    serializer_class = LeadSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        # Enable basic stage filtering
        stage = self.request.query_params.get('stage')
        if stage:
            queryset = queryset.filter(stage=stage)
        collection_id = self.request.query_params.get('collection')
        if collection_id:
            queryset = queryset.filter(collection_id=collection_id)
        
        # Enable search filtering
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(email__icontains=search) |
                Q(phone__icontains=search) |
                Q(website__icontains=search) |
                Q(address__icontains=search)
            )
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
        collection_id = request.data.get('collection_id') or request.data.get('collection')
        if not query:
            return Response({'detail': 'query parameter is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if not collection_id:
            return Response({'detail': 'collection_id or collection parameter is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            collection = LeadCollection.objects.get(id=collection_id, business=request.business)
        except LeadCollection.DoesNotExist:
            return Response({'detail': 'Collection not found.'}, status=status.HTTP_404_NOT_FOUND)

        api_key = os.environ.get('GOOGLE_PLACES_API_KEY')
        scraped_leads = []

        next_page_token = None
        pages_fetched = 0
        
        try:
            while pages_fetched < 3:
                url = f"https://maps.googleapis.com/maps/api/place/textsearch/json?query={query}&key={api_key}"
                if next_page_token:
                    url += f"&pagetoken={next_page_token}"
                    
                r = requests.get(url)
                if r.status_code != 200:
                    return Response({'detail': f'Google API returned error: {r.text}'}, status=status.HTTP_400_BAD_REQUEST)
                    
                data = r.json()
                results = data.get('results', [])
                for item in results:
                    name = item.get('name')
                    address = item.get('formatted_address', '')
                    rating = item.get('rating')
                    place_id = item.get('place_id')
                    
                    # Get details (phone, website, ratings, location, types, status)
                    phone = ''
                    website = ''
                    details = {}
                    
                    fields = "formatted_phone_number,website,user_ratings_total,geometry,business_status,types"
                    details_url = f"https://maps.googleapis.com/maps/api/place/details/json?place_id={place_id}&fields={fields}&key={api_key}"
                    
                    dr = requests.get(details_url)
                    if dr.status_code == 200:
                        details = dr.json().get('result', {})
                        phone = details.get('formatted_phone_number', '')
                        website = details.get('website', '')

                    if not Lead.objects.filter(business=request.business, name=name).exists():

                        # Extract metadata values
                        user_ratings_total = details.get('user_ratings_total', item.get('user_ratings_total', 0))
                        business_status = details.get('business_status', item.get('business_status', ''))
                        types = details.get('types', item.get('types', []))
                        location = details.get('geometry', {}).get('location', item.get('geometry', {}).get('location', {}))
                        lat = location.get('lat')
                        lng = location.get('lng')

                        # Merge both result lists to save all response details
                        google_metadata = {**item, **details}

                        lead = Lead.objects.create(
                            business=request.business,
                            collection=collection,
                            name=name,
                            email='',
                            phone=phone,
                            website=website,
                            address=address,
                            rating=rating,
                            source="Google Places API",
                            place_id=place_id,
                            user_ratings_total=user_ratings_total,
                            latitude=lat,
                            longitude=lng,
                            business_status=business_status,
                            types=types,
                            google_metadata=google_metadata
                        )
                        LeadActivity.objects.create(
                            lead=lead,
                            activity_type="Log",
                            description=f"Lead automatically created via Google Places API search for '{query}'."
                        )
                        scraped_leads.append(lead)
                        
                next_page_token = data.get('next_page_token')
                pages_fetched += 1
                
                if not next_page_token:
                    break
                
                # Google requires a small delay before the next page token is activated
                time.sleep(2)
                
            mode_used = f"Google Places API Live ({pages_fetched} pages)"
        except Exception as e:
            return Response({'detail': f'Failed to search Google Places API: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        serializer = LeadSerializer(scraped_leads, many=True)
        return Response({
            "message": f"Successfully imported {len(scraped_leads)} leads using {mode_used}.",
            "leads": serializer.data
        }, status=status.HTTP_201_CREATED)
