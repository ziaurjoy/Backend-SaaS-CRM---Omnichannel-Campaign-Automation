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

        # Enable WhatsApp status filtering
        whatsapp_status = self.request.query_params.get('whatsapp_status')
        if whatsapp_status is not None:
            if str(whatsapp_status).lower() in ['true', '1', 'yes']:
                queryset = queryset.filter(whatsapp_status=True)
            elif str(whatsapp_status).lower() in ['false', '0', 'no']:
                queryset = queryset.filter(whatsapp_status=False)
        
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
                'whatsapp_status', '-whatsapp_status',
            ]
            if ordering in valid_orderings:
                queryset = queryset.order_by(ordering)
            else:
                queryset = queryset.order_by('-created_at')
        else:
            queryset = queryset.order_by('-created_at')

        return queryset

    def perform_create(self, serializer):
        from apps.crm.services.phone_validator import validate_and_normalize_phone
        from apps.crm.tasks import trigger_lead_whatsapp_verification

        raw_phone = serializer.validated_data.get('phone')
        if raw_phone:
            val = validate_and_normalize_phone(raw_phone, getattr(self.request.business, 'country', None))
            normalized = val['e164'] if (val['is_valid'] and val['e164']) else raw_phone
            lead = serializer.save(business=self.request.business, phone=normalized)
            try:
                trigger_lead_whatsapp_verification(lead.id)
            except Exception as e:
                logger.warning(f"Error triggering WhatsApp verification on lead create: {e}")
        else:
            serializer.save(business=self.request.business)

    def perform_update(self, serializer):
        from apps.crm.services.phone_validator import validate_and_normalize_phone
        from apps.crm.tasks import trigger_lead_whatsapp_verification

        old_phone = serializer.instance.phone
        raw_phone = serializer.validated_data.get('phone')

        if raw_phone and raw_phone != old_phone:
            val = validate_and_normalize_phone(raw_phone, getattr(self.request.business, 'country', None))
            normalized = val['e164'] if (val['is_valid'] and val['e164']) else raw_phone
            lead = serializer.save(phone=normalized, whatsapp_status=False)
            try:
                trigger_lead_whatsapp_verification(lead.id, force_check=True)
            except Exception as e:
                logger.warning(f"Error triggering WhatsApp verification on lead update: {e}")
        else:
            serializer.save()

    @action(detail=True, methods=['post'], url_path='verify_whatsapp')
    def verify_whatsapp(self, request, pk=None):
        """
        Manually trigger or retry WhatsApp verification for a single lead.
        """
        from apps.crm.services.whatsapp_verifier import WhatsAppVerifierService
        lead = self.get_object()
        force = request.data.get('force', True)
        verifier = WhatsAppVerifierService()
        result = verifier.verify_lead(lead, force_check=bool(force))
        lead.refresh_from_db()
        serializer = self.get_serializer(lead)
        return Response({
            'message': 'WhatsApp verification completed.',
            'result': result,
            'lead': serializer.data
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='verify_whatsapp_batch')
    def verify_whatsapp_batch(self, request):
        """
        Bulk verify WhatsApp availability across multiple leads or an entire collection.
        """
        from apps.crm.tasks import trigger_bulk_whatsapp_verification
        lead_ids = request.data.get('lead_ids', [])
        collection_id = request.data.get('collection_id')
        force = request.data.get('force', False)

        queryset = self.get_queryset().filter(phone__isnull=False).exclude(phone='')
        if lead_ids:
            queryset = queryset.filter(id__in=lead_ids)
        elif collection_id:
            queryset = queryset.filter(collection_id=collection_id)

        target_ids = list(queryset.values_list('id', flat=True))
        if not target_ids:
            return Response({'detail': 'No eligible phone-number leads found to verify.'}, status=status.HTTP_400_BAD_REQUEST)

        trigger_bulk_whatsapp_verification(target_ids, force_check=bool(force))
        return Response({
            'message': f'Verification queued for {len(target_ids)} lead(s).',
            'count': len(target_ids)
        }, status=status.HTTP_200_OK)

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

