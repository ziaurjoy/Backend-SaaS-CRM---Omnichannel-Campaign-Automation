import os
import time
import logging
import requests
from typing import Dict, Any, List, Optional, Tuple
from django.db import transaction
from django.conf import settings
from apps.crm.models import Lead, LeadCollection, LeadActivity, GooglePlaceScrapeSession

logger = logging.getLogger(__name__)

class GooglePlacesScraperService:
    """
    Service for searching Google Places Text Search (New) API,
    paginating through all available pages with nextPageToken,
    and storing/updating businesses into the CRM while preventing duplicates.
    """

    def __init__(self):
        self.api_key = os.environ.get('GOOGLE_PLACES_API_KEY', '').strip(' "\'')
        self.search_url = (
            os.environ.get('Place_Text_Search(New)_URL')
            or os.environ.get('PLACE_TEXT_SEARCH_NEW_URL')
            or os.environ.get('PLACE_TEXT_SEARCH_URL')
            or 'https://places.googleapis.com/v1/places:searchText'
        ).strip(' "\'')
        
        raw_mask = os.environ.get(
            'X_Goog_FieldMask',
            'places.id,places.displayName,places.formattedAddress,places.internationalPhoneNumber,'
            'places.nationalPhoneNumber,places.websiteUri,places.rating,places.userRatingCount,'
            'places.location,places.businessStatus,places.types,places.primaryType,'
            'places.primaryTypeDisplayName,places.priceLevel'
        ).strip(' "\'')
        
        # Ensure nextPageToken is in field mask so Places API (New) returns it
        if 'nextPageToken' not in raw_mask:
            self.field_mask = f"{raw_mask.rstrip(',')},nextPageToken"
        else:
            self.field_mask = raw_mask

    def scrape_places(
        self,
        business,
        text_query: str,
        collection: Optional[LeadCollection] = None,
        user=None,
        page_size: int = 20,
        max_pages: Optional[int] = None,
        page_token: Optional[str] = None,
        fetch_all_pages: bool = True,
    ) -> Dict[str, Any]:
        """
        Execute Google Places search with full pagination support.
        
        :param business: The tenant Business instance
        :param text_query: The search term (e.g., 'software companies in Dhaka')
        :param collection: LeadCollection instance to assign leads to
        :param user: The requesting user (optional, for audit trail)
        :param page_size: Results per page (1 to 20, default 20)
        :param max_pages: Maximum number of pages to fetch (None for all available)
        :param page_token: Optional starting page token for incremental step-by-step
        :param fetch_all_pages: If True, loops through all available pages until token exhausts
        :return: Dict with message, leads, pagination stats, session_id
        """
        if not text_query or not text_query.strip():
            raise ValueError("textQuery parameter is required and cannot be empty.")

        text_query = text_query.strip()
        
        # Google Places API (New) limits pageSize between 1 and 20
        page_size = max(1, min(int(page_size), 20))

        if not self.api_key:
            raise ValueError("GOOGLE_PLACES_API_KEY environment variable is not configured.")

        # Create scrape session record
        session = GooglePlaceScrapeSession.objects.create(
            business=business,
            collection=collection,
            user=user if user and user.is_authenticated else None,
            query=text_query,
            page_size=page_size,
            status='Running',
        )

        headers = {
            'Content-Type': 'application/json',
            'X-Goog-Api-Key': self.api_key,
            'X-Goog-FieldMask': self.field_mask,
        }

        all_places_data: List[Dict[str, Any]] = []
        current_token = page_token
        pages_fetched = 0
        seen_tokens = set()
        
        # Safety bound for max pages to avoid infinite loops
        # Google Places Text Search (New) typically returns a max of ~60 places (3 pages).
        max_pages_ceiling = max_pages if (max_pages and max_pages > 0) else 10
        if not fetch_all_pages:
            max_pages_ceiling = 1

        last_next_page_token: Optional[str] = None

        try:
            while pages_fetched < max_pages_ceiling:
                payload: Dict[str, Any] = {
                    'textQuery': text_query,
                    'pageSize': page_size,
                }
                if current_token:
                    payload['pageToken'] = current_token
                    seen_tokens.add(current_token)

                logger.info(
                    f"Fetching Google Places page {pages_fetched + 1} for query='{text_query}' "
                    f"using URL={self.search_url}"
                )

                response = requests.post(
                    self.search_url,
                    headers=headers,
                    json=payload,
                    timeout=25
                )

                if response.status_code != 200:
                    err_detail = response.text
                    try:
                        err_json = response.json()
                        err_detail = err_json.get('error', {}).get('message', response.text)
                    except Exception:
                        pass
                    raise RuntimeError(f"Google Places API error ({response.status_code}): {err_detail}")

                res_json = response.json()
                print(f"Google Places API response: {res_json}")
                places = res_json.get('places', [])
                all_places_data.extend(places)
                pages_fetched += 1

                next_token = res_json.get('nextPageToken')
                last_next_page_token = next_token

                # Break conditions:
                # 1. No next page token returned
                if not next_token:
                    logger.info("No nextPageToken returned. Pagination completed.")
                    break

                # 2. Prevent infinite loops if token was already encountered
                if next_token in seen_tokens:
                    logger.warning(f"Detected duplicate nextPageToken '{next_token[:15]}...'. Breaking loop.")
                    break

                # 3. If requested not to fetch all pages, break after 1 page
                if not fetch_all_pages or pages_fetched >= max_pages_ceiling:
                    break

                current_token = next_token
                
                # Small pause between pages to respect API quotas
                time.sleep(1.0)

            # Persist and incrementally update businesses in database
            processed_leads, created_count, updated_count = self._persist_places(
                business=business,
                collection=collection,
                places_data=all_places_data,
                text_query=text_query,
                session=session,
            )

            # Trigger automatic WhatsApp account verification for newly scraped/updated leads with phones
            from apps.crm.tasks import trigger_bulk_whatsapp_verification
            leads_to_verify_ids = [lead.id for lead in processed_leads if lead.phone and not lead.whatsapp_status]
            if leads_to_verify_ids:
                try:
                    trigger_bulk_whatsapp_verification(leads_to_verify_ids)
                except Exception as task_err:
                    logger.warning(f"Failed to trigger automatic WhatsApp verification: {task_err}")

            session.pages_fetched = pages_fetched
            session.total_scraped = len(processed_leads)
            session.created_count = created_count
            session.updated_count = updated_count
            session.status = 'Completed'
            session.save()

            message = (
                f"Successfully processed {len(processed_leads)} places across {pages_fetched} page(s) "
                f"({created_count} created, {updated_count} updated)."
            )

            return {
                'message': message,
                'session_id': session.id,
                'pages_fetched': pages_fetched,
                'total_scraped': len(processed_leads),
                'created_count': created_count,
                'updated_count': updated_count,
                'has_more': bool(last_next_page_token),
                'next_page_token': last_next_page_token if last_next_page_token else None,
                'leads': processed_leads,
            }

        except Exception as e:
            logger.exception(f"Failed to scrape Google Places: {e}")
            session.pages_fetched = pages_fetched
            session.status = 'Failed'
            session.error_message = str(e)
            session.save()
            raise

    def _persist_places(
        self,
        business,
        collection: Optional[LeadCollection],
        places_data: List[Dict[str, Any]],
        text_query: str,
        session: GooglePlaceScrapeSession,
    ) -> Tuple[List[Lead], int, int]:
        """
        Atomically saves or incrementally updates places in the database,
        preventing duplicate records and recording activity history.
        """
        processed_leads: List[Lead] = []
        created_count = 0
        updated_count = 0

        with transaction.atomic():
            for item in places_data:
                place_id = item.get('id') or item.get('place_id')
                
                # Extract Display Name / Business Name
                display_name_obj = item.get('displayName')
                if isinstance(display_name_obj, dict):
                    name = display_name_obj.get('text', '')
                elif isinstance(display_name_obj, str):
                    name = display_name_obj
                else:
                    name = item.get('name', 'Unknown Business')

                if not name:
                    name = 'Unknown Business'

                # Extract address
                address = item.get('formattedAddress') or item.get('formatted_address', '')

                # Extract phone (international preferred, fallback to national) and normalize to E.164
                raw_phone = (
                    item.get('internationalPhoneNumber')
                    or item.get('nationalPhoneNumber')
                    or item.get('formatted_phone_number', '')
                )
                phone = raw_phone
                if raw_phone:
                    from apps.crm.services.phone_validator import validate_and_normalize_phone
                    val = validate_and_normalize_phone(raw_phone, default_region=getattr(business, 'country', None))
                    if val['is_valid'] and val['e164']:
                        phone = val['e164']

                # Extract website
                website = item.get('websiteUri') or item.get('website', '')

                # Extract rating & review counts
                rating = item.get('rating')
                user_ratings_total = item.get('userRatingCount') or item.get('user_ratings_total', 0)

                # Extract location coordinates
                location_data = item.get('location', {})
                if not location_data and 'geometry' in item:
                    location_data = item.get('geometry', {}).get('location', {})
                
                lat = location_data.get('latitude') or location_data.get('lat')
                lng = location_data.get('longitude') or location_data.get('lng')

                # Extract business status & categories
                business_status = item.get('businessStatus') or item.get('business_status', '')
                types = item.get('types', [])
                primary_type = item.get('primaryType', '')
                
                primary_display_obj = item.get('primaryTypeDisplayName')
                if isinstance(primary_display_obj, dict):
                    primary_type_display_name = primary_display_obj.get('text', '')
                elif isinstance(primary_display_obj, str):
                    primary_type_display_name = primary_display_obj
                else:
                    primary_type_display_name = ''

                price_level = item.get('priceLevel', '')

                # Duplicate Prevention Strategy:
                # 1. Match existing Lead by place_id within the active business tenant
                # 2. If no place_id match, match by identical name within the tenant
                existing_lead = None
                if place_id:
                    existing_lead = Lead.objects.filter(
                        business=business,
                        place_id=place_id
                    ).first()

                if not existing_lead and name:
                    existing_lead = Lead.objects.filter(
                        business=business,
                        name=name
                    ).first()

                if existing_lead:
                    # Incremental update: update details without creating duplicates
                    existing_lead.address = address or existing_lead.address
                    if phone:
                        existing_lead.phone = phone
                    if website:
                        existing_lead.website = website
                    if rating is not None:
                        existing_lead.rating = rating
                    if user_ratings_total is not None:
                        existing_lead.user_ratings_total = user_ratings_total
                    if lat is not None:
                        existing_lead.latitude = lat
                    if lng is not None:
                        existing_lead.longitude = lng
                    if business_status:
                        existing_lead.business_status = business_status
                    if types:
                        existing_lead.types = types
                    if primary_type:
                        existing_lead.primary_type = primary_type
                    if primary_type_display_name:
                        existing_lead.primary_type_display_name = primary_type_display_name
                    if price_level:
                        existing_lead.price_level = price_level
                    if place_id and not existing_lead.place_id:
                        existing_lead.place_id = place_id
                    
                    # Merge metadata
                    existing_metadata = existing_lead.google_metadata or {}
                    existing_metadata.update(item)
                    existing_lead.google_metadata = existing_metadata
                    existing_lead.scrape_session = session

                    # If collection is provided and lead has none, associate it
                    if collection and not existing_lead.collection:
                        existing_lead.collection = collection

                    existing_lead.save()

                    LeadActivity.objects.create(
                        lead=existing_lead,
                        activity_type="Log",
                        description=(
                            f"Lead updated via Google Places API search for '{text_query}'. "
                            f"Rating: {rating or 'N/A'}, Reviews: {user_ratings_total}."
                        )
                    )

                    processed_leads.append(existing_lead)
                    updated_count += 1

                else:
                    # Create new Lead
                    new_lead = Lead.objects.create(
                        business=business,
                        collection=collection,
                        scrape_session=session,
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
                        primary_type=primary_type,
                        primary_type_display_name=primary_type_display_name,
                        price_level=price_level,
                        google_metadata=item,
                    )

                    LeadActivity.objects.create(
                        lead=new_lead,
                        activity_type="Log",
                        description=f"Lead automatically created via Google Places API search for '{text_query}'."
                    )

                    processed_leads.append(new_lead)
                    created_count += 1

        return processed_leads, created_count, updated_count
