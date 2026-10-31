import logging
import requests
from typing import Dict, Any, List, Optional, Iterable
from django.utils import timezone
from django.conf import settings

from apps.crm.services.phone_validator import validate_and_normalize_phone
from apps.messaging.models import Integration

logger = logging.getLogger(__name__)

class WhatsAppVerifierService:
    """
    Enterprise WhatsApp account detection and verification service.
    
    Supports:
    1. WhatsApp Multi-Device (Baileys microservice via official socket onWhatsApp query)
    2. Meta WhatsApp Business Cloud API (Meta Embedded Signup / On-Premises contacts check)
    3. Graceful handling of network timeouts, rate limits, and unlinked sessions.
    4. Caching and avoidance of redundant API checks for already-verified numbers.
    """

    def __init__(self):
        url = getattr(settings, 'WHATSAPP_SERVICE_URL', 'http://localhost:3001').rstrip('/')
        if 'host.docker.internal' in url:
            import socket
            try:
                socket.gethostbyname('host.docker.internal')
            except Exception:
                url = url.replace('host.docker.internal', 'localhost')
        self.service_url = url

    def get_whatsapp_integration(self, business) -> Optional[Integration]:
        """Fetch the active WhatsApp integration for the given business tenant."""
        if not business:
            return None
        return Integration.objects.filter(
            business=business,
            provider='WhatsApp',
            status='Connected'
        ).first()

    def verify_number(
        self,
        business,
        raw_phone: str,
        force_check: bool = False,
        default_region: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Validates the phone number format and queries WhatsApp for registration status.
        """
        # Step 1: Normalize and validate phone number into E.164
        val_res = validate_and_normalize_phone(raw_phone, default_region)
        if not val_res['is_valid']:
            return {
                'phone': raw_phone,
                'e164': None,
                'exists': False,
                'jid': None,
                'status': 'invalid_number',
                'error': val_res['error']
            }

        e164_phone = val_res['e164']
        clean_digits = e164_phone.replace('+', '')

        # Step 2: Determine which WhatsApp provider/integration is connected
        integration = self.get_whatsapp_integration(business)

        # Provider 1: Baileys Standard Multi-Device microservice
        if integration and integration.credentials.get('link_type') == 'WhatsApp_Standard_QR':
            session_id = integration.credentials.get('session_id', f"wa_business_{business.id}")
            return self._check_baileys(session_id, e164_phone)

        # Provider 2: Meta WhatsApp Cloud API
        elif integration and integration.credentials.get('link_type') == 'Meta_Embedded_Signup':
            return self._check_meta_cloud_api(integration, e164_phone, clean_digits)

        # Provider 3: Fallback check against microservice if active session exists
        else:
            session_id = f"wa_business_{business.id}" if business else "default_session"
            baileys_res = self._check_baileys(session_id, e164_phone)
            if baileys_res.get('status') != 'service_error' and 'not active' not in str(baileys_res.get('error', '')).lower():
                return baileys_res

            # No integration connected
            return {
                'phone': raw_phone,
                'e164': e164_phone,
                'exists': False,
                'jid': None,
                'status': 'no_integration',
                'error': 'No active WhatsApp integration or connected session found for this workspace.'
            }

    def _check_baileys(self, session_id: str, e164_phone: str) -> Dict[str, Any]:
        """Query Baileys microservice /whatsapp/check-number endpoint."""
        url = f"{self.service_url}/whatsapp/check-number"
        payload = {
            'sessionId': session_id,
            'phone': e164_phone
        }

        try:
            res = requests.post(url, json=payload, timeout=10)
            if res.status_code == 200:
                data = res.json()
                exists = bool(data.get('exists', False))
                jid = data.get('jid')
                return {
                    'phone': e164_phone,
                    'e164': e164_phone,
                    'exists': exists,
                    'jid': jid,
                    'status': 'verified' if exists else 'not_registered',
                    'error': None
                }
            else:
                err_detail = res.text
                try:
                    err_json = res.json()
                    err_detail = err_json.get('error') or err_json.get('detail') or res.text
                except Exception:
                    pass

                logger.warning(f"WhatsApp microservice verification returned {res.status_code}: {err_detail}")
                return {
                    'phone': e164_phone,
                    'e164': e164_phone,
                    'exists': False,
                    'jid': None,
                    'status': 'failed',
                    'error': f"WhatsApp service: {err_detail}"
                }
        except requests.exceptions.Timeout:
            logger.error("WhatsApp microservice check timed out.")
            return {
                'phone': e164_phone,
                'e164': e164_phone,
                'exists': False,
                'jid': None,
                'status': 'timeout',
                'error': 'WhatsApp verification request timed out.'
            }
        except Exception as e:
            logger.error(f"WhatsApp microservice connection error: {e}")
            return {
                'phone': e164_phone,
                'e164': e164_phone,
                'exists': False,
                'jid': None,
                'status': 'service_error',
                'error': f"Could not connect to WhatsApp verification service: {str(e)}"
            }

    def _check_meta_cloud_api(self, integration: Integration, e164_phone: str, clean_digits: str) -> Dict[str, Any]:
        """Verify phone number using Meta WhatsApp Cloud API / contacts endpoint."""
        credentials = integration.credentials or {}
        token = credentials.get('token', '')
        phone_id = credentials.get('phone_id', '')
        is_mock = credentials.get('mode') == 'Sandbox Mock Mode' or token.startswith('mock_') or token.startswith('EAAGb8vTz1...mock')

        if is_mock or not token or not phone_id:
            # Simulated Meta response in sandbox/mock mode
            return {
                'phone': e164_phone,
                'e164': e164_phone,
                'exists': True,
                'jid': f"{clean_digits}@s.whatsapp.net",
                'status': 'verified',
                'error': None
            }

        # Real Meta Graph API check
        url = f"https://graph.facebook.com/v20.0/{phone_id}/contacts"
        headers = {
            'Authorization': f"Bearer {token}",
            'Content-Type': 'application/json'
        }
        payload = {
            'blocking': 'wait',
            'contacts': [clean_digits],
            'force_check': True
        }

        try:
            res = requests.post(url, headers=headers, json=payload, timeout=10)
            if res.status_code == 200:
                contacts = res.json().get('contacts', [])
                if contacts and contacts[0].get('status') == 'valid':
                    wa_id = contacts[0].get('wa_id') or clean_digits
                    return {
                        'phone': e164_phone,
                        'e164': e164_phone,
                        'exists': True,
                        'jid': f"{wa_id}@s.whatsapp.net",
                        'status': 'verified',
                        'error': None
                    }
                else:
                    return {
                        'phone': e164_phone,
                        'e164': e164_phone,
                        'exists': False,
                        'jid': None,
                        'status': 'not_registered',
                        'error': None
                    }
            else:
                return {
                    'phone': e164_phone,
                    'e164': e164_phone,
                    'exists': False,
                    'jid': None,
                    'status': 'failed',
                    'error': f"Meta Cloud API error ({res.status_code}): {res.text}"
                }
        except Exception as e:
            logger.error(f"Meta Cloud API error: {e}")
            return {
                'phone': e164_phone,
                'e164': e164_phone,
                'exists': False,
                'jid': None,
                'status': 'failed',
                'error': str(e)
            }

    def verify_lead(self, lead, force_check: bool = False) -> Dict[str, Any]:
        """
        Verify a single Lead model instance and persist the result in the database.
        Logs activity if verified.
        """
        from apps.crm.models import LeadActivity

        # Skip repeated API calls if already verified and force_check is False
        if lead.whatsapp_status and not force_check:
            return {
                'lead_id': lead.id,
                'phone': lead.phone,
                'whatsapp_status': True,
                'cached': True,
                'status': 'already_verified'
            }

        if not lead.phone:
            if lead.whatsapp_status:
                lead.whatsapp_status = False
                lead.save(update_fields=['whatsapp_status'])
            return {
                'lead_id': lead.id,
                'phone': None,
                'whatsapp_status': False,
                'status': 'no_phone',
                'error': 'Lead has no phone number.'
            }

        default_region = getattr(lead.business, 'country', None)
        result = self.verify_number(
            business=lead.business,
            raw_phone=lead.phone,
            force_check=force_check,
            default_region=default_region
        )

        update_fields = ['whatsapp_status']

        if result['exists']:
            lead.whatsapp_status = True
            if hasattr(lead, 'whatsapp_verified_at'):
                lead.whatsapp_verified_at = timezone.now()
                update_fields.append('whatsapp_verified_at')
            if hasattr(lead, 'whatsapp_jid') and result.get('jid'):
                lead.whatsapp_jid = result['jid']
                update_fields.append('whatsapp_jid')

            # Normalize the phone number in the model to E.164 if valid
            if result.get('e164') and lead.phone != result['e164']:
                lead.phone = result['e164']
                update_fields.append('phone')

            lead.save(update_fields=update_fields)

            # Record audit activity
            try:
                LeadActivity.objects.create(
                    lead=lead,
                    activity_type='WhatsApp',
                    description=f"Phone {lead.phone} verified as an active WhatsApp account."
                )
            except Exception as e:
                logger.warning(f"Failed to record LeadActivity for lead {lead.id}: {e}")

        elif result.get('status') == 'not_registered':
            lead.whatsapp_status = False
            # If the phone was normalized into E.164, update lead.phone
            if result.get('e164') and lead.phone != result['e164']:
                lead.phone = result['e164']
                update_fields.append('phone')

            lead.save(update_fields=update_fields)

        elif result.get('status') in ['failed', 'timeout', 'service_error']:
            # Inconclusive check or API failure: preserve lead status, do not mark as unavailable
            logger.warning(
                f"WhatsApp verification inconclusive for lead {lead.id} ({lead.phone}): {result.get('error')}"
            )
            if result.get('e164') and lead.phone != result['e164']:
                lead.phone = result['e164']
                lead.save(update_fields=['phone'])

        return {
            'lead_id': lead.id,
            'phone': lead.phone,
            'whatsapp_status': lead.whatsapp_status,
            'status': result.get('status'),
            'error': result.get('error')
        }

    def verify_leads_batch(self, leads: Iterable, force_check: bool = False) -> List[Dict[str, Any]]:
        """
        Verify multiple leads efficiently, using batch verification where possible.
        """
        results = []
        leads_list = list(leads)
        if not leads_list:
            return results

        business = leads_list[0].business
        integration = self.get_whatsapp_integration(business)

        # If Baileys microservice is available, do a bulk check
        if integration and integration.credentials.get('link_type') == 'WhatsApp_Standard_QR':
            session_id = integration.credentials.get('session_id', f"wa_business_{business.id}")
            
            # Filter leads that need verification
            to_verify = []
            for lead in leads_list:
                if not force_check and lead.whatsapp_status:
                    results.append({
                        'lead_id': lead.id,
                        'phone': lead.phone,
                        'whatsapp_status': True,
                        'cached': True
                    })
                    continue

                if not lead.phone:
                    lead.whatsapp_status = False
                    lead.save(update_fields=['whatsapp_status'])
                    results.append({
                        'lead_id': lead.id,
                        'phone': None,
                        'whatsapp_status': False,
                        'status': 'no_phone'
                    })
                    continue

                val = validate_and_normalize_phone(lead.phone, getattr(business, 'country', None))
                if not val['is_valid']:
                    lead.whatsapp_status = False
                    lead.save(update_fields=['whatsapp_status'])
                    results.append({
                        'lead_id': lead.id,
                        'phone': lead.phone,
                        'whatsapp_status': False,
                        'status': 'invalid_number',
                        'error': val['error']
                    })
                    continue

                to_verify.append((lead, val['e164']))

            if to_verify:
                phones = [e164 for _, e164 in to_verify]
                try:
                    res = requests.post(
                        f"{self.service_url}/whatsapp/check-number",
                        json={'sessionId': session_id, 'phones': phones},
                        timeout=25
                    )
                    if res.status_code == 200:
                        batch_res = res.json().get('results', [])
                        res_map = {item['phone']: item for item in batch_res}

                        from apps.crm.models import LeadActivity
                        for lead, e164 in to_verify:
                            match = res_map.get(e164) or res_map.get(lead.phone)
                            if match and match.get('error'):
                                results.append({
                                    'lead_id': lead.id,
                                    'phone': lead.phone,
                                    'whatsapp_status': lead.whatsapp_status,
                                    'status': 'inconclusive',
                                    'error': match.get('error')
                                })
                                continue

                            exists = bool(match and match.get('exists'))
                            lead.whatsapp_status = exists
                            update_fields = ['whatsapp_status']
                            if lead.phone != e164:
                                lead.phone = e164
                                update_fields.append('phone')
                            if exists:
                                if hasattr(lead, 'whatsapp_verified_at'):
                                    lead.whatsapp_verified_at = timezone.now()
                                    update_fields.append('whatsapp_verified_at')
                                if hasattr(lead, 'whatsapp_jid') and match.get('jid'):
                                    lead.whatsapp_jid = match['jid']
                                    update_fields.append('whatsapp_jid')

                            lead.save(update_fields=update_fields)

                            if exists:
                                try:
                                    LeadActivity.objects.create(
                                        lead=lead,
                                        activity_type='WhatsApp',
                                        description=f"Phone {lead.phone} verified as an active WhatsApp account."
                                    )
                                except Exception:
                                    pass

                            results.append({
                                'lead_id': lead.id,
                                'phone': lead.phone,
                                'whatsapp_status': exists,
                                'status': 'verified' if exists else 'not_registered'
                            })
                        return results
                except Exception as e:
                    logger.warning(f"Batch check failed, falling back to individual checks: {e}")

        # Fallback to individual checks
        for lead in leads_list:
            res = self.verify_lead(lead, force_check=force_check)
            results.append(res)

        return results
