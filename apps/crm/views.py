import os
import time
import logging
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.db.models import Q

from apps.tenants.utils import TenantModelViewSetMixin
from apps.crm.models import Lead, Tag, LeadActivity, LeadCollection, GooglePlaceScrapeSession
from apps.crm.serializers import (
    LeadSerializer,
    TagSerializer,
    LeadActivitySerializer,
    LeadCollectionSerializer,
    GooglePlaceScrapeSessionSerializer
)
from apps.crm.services.places_scraper import GooglePlacesScraperService

from config.pagination import StandardResultsSetPagination

logger = logging.getLogger(__name__)

LeadPagination = StandardResultsSetPagination

class TagViewSet(TenantModelViewSetMixin, viewsets.ModelViewSet):
    queryset = Tag.objects.all()
    serializer_class = TagSerializer
    pagination_class = StandardResultsSetPagination

class LeadCollectionViewSet(TenantModelViewSetMixin, viewsets.ModelViewSet):
    queryset = LeadCollection.objects.all()
    serializer_class = LeadCollectionSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        queryset = super().get_queryset()
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(description__icontains=search)
            )
        return queryset.order_by('-created_at')

class GooglePlaceScrapeSessionViewSet(TenantModelViewSetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = GooglePlaceScrapeSession.objects.all()
    serializer_class = GooglePlaceScrapeSessionSerializer
    pagination_class = StandardResultsSetPagination

class LeadViewSet(TenantModelViewSetMixin, viewsets.ModelViewSet):
    queryset = Lead.objects.all()
    serializer_class = LeadSerializer
    pagination_class = LeadPagination

    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Enable stage filtering
        stage = self.request.query_params.get('stage')
        if stage:
            queryset = queryset.filter(stage=stage)
            
        # Enable collection filtering
        collection_id = self.request.query_params.get('collection') or self.request.query_params.get('collection_id')
        if collection_id:
            queryset = queryset.filter(collection_id=collection_id)

        # Enable business_status filtering
        business_status = self.request.query_params.get('business_status')
        if business_status:
            queryset = queryset.filter(business_status=business_status)

        # Enable minimum rating filtering
        min_rating = self.request.query_params.get('min_rating') or self.request.query_params.get('rating')
        if min_rating:
            try:
                queryset = queryset.filter(rating__gte=float(min_rating))
            except ValueError:
                pass

        # Enable source filtering
        source = self.request.query_params.get('source')
        if source:
            queryset = queryset.filter(source=source)
        
        # Enable comprehensive search filtering
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(email__icontains=search) |
                Q(phone__icontains=search) |
                Q(website__icontains=search) |
                Q(address__icontains=search) |
                Q(primary_type__icontains=search) |
                Q(primary_type_display_name__icontains=search) |
                Q(place_id__icontains=search)
            )

        # Sorting / ordering
        ordering = self.request.query_params.get('ordering')
        if ordering:
            valid_orderings = [
                'name', '-name',
                'rating', '-rating',
                'user_ratings_total', '-user_ratings_total',
                'created_at', '-created_at',
                'stage', '-stage',
            ]
            if ordering in valid_orderings:
                queryset = queryset.order_by(ordering)
            else:
                queryset = queryset.order_by('-created_at')
        else:
            queryset = queryset.order_by('-created_at')

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
        text_query = request.data.get('textQuery') or request.data.get('query')
        page_size = request.data.get('pageSize') or request.data.get('page_size', 20)
        collection_id = request.data.get('collection_id') or request.data.get('collection')
        max_pages = request.data.get('maxPages') or request.data.get('max_pages')
        page_token = request.data.get('pageToken') or request.data.get('page_token')
        fetch_all_pages = request.data.get('fetchAllPages', request.data.get('fetch_all_pages', True))

        if not text_query or not str(text_query).strip():
            return Response(
                {'detail': 'textQuery (or query) parameter is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        collection = None
        if collection_id:
            try:
                collection = LeadCollection.objects.get(id=collection_id, business=request.business)
            except LeadCollection.DoesNotExist:
                return Response({'detail': 'Collection not found.'}, status=status.HTTP_404_NOT_FOUND)
        else:
            # Create or use default collection for backward compatibility
            collection, _ = LeadCollection.objects.get_or_create(
                business=request.business,
                name="Scraped Leads",
                defaults={'description': 'Automatically created collection for scraped leads.'}
            )

        try:
            scraper = GooglePlacesScraperService()
            result = scraper.scrape_places(
                business=request.business,
                text_query=str(text_query).strip(),
                collection=collection,
                user=request.user,
                page_size=page_size,
                max_pages=int(max_pages) if max_pages else None,
                page_token=page_token,
                fetch_all_pages=bool(fetch_all_pages),
            )

            serializer = LeadSerializer(result['leads'], many=True, context={'request': request})
            return Response({
                'message': result['message'],
                'session_id': result['session_id'],
                'pages_fetched': result['pages_fetched'],
                'total_scraped': result['total_scraped'],
                'created_count': result['created_count'],
                'updated_count': result['updated_count'],
                'has_more': result['has_more'],
                'next_page_token': result['next_page_token'],
                'leads': serializer.data,
            }, status=status.HTTP_201_CREATED)

        except ValueError as ve:
            return Response({'detail': str(ve)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.exception("Error in scrape_google_places endpoint")
            return Response(
                {'detail': f'Failed to search Google Places API: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['get'], url_path='scrape_sessions')
    def scrape_sessions(self, request):
        sessions = GooglePlaceScrapeSession.objects.filter(
            business=request.business
        ).order_by('-created_at')[:20]
        serializer = GooglePlaceScrapeSessionSerializer(sessions, many=True)
        return Response(serializer.data)

