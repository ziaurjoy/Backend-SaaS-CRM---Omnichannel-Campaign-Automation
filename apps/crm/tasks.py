import logging
from typing import List
from celery import shared_task

from apps.messaging.tasks import is_redis_running
from apps.crm.models import Lead
from apps.crm.services.whatsapp_verifier import WhatsAppVerifierService

logger = logging.getLogger(__name__)

@shared_task
def verify_lead_whatsapp_task(lead_id: int, force_check: bool = False):
    """Celery background task to detect and verify WhatsApp account for a single lead."""
    try:
        lead = Lead.objects.select_related('business').get(id=lead_id)
    except Lead.DoesNotExist:
        logger.warning(f"verify_lead_whatsapp_task: Lead {lead_id} does not exist.")
        return {'status': 'error', 'error': 'Lead not found'}

    verifier = WhatsAppVerifierService()
    result = verifier.verify_lead(lead, force_check=force_check)
    logger.info(f"WhatsApp verification completed for Lead {lead_id}: {result}")
    return result

@shared_task
def verify_leads_bulk_task(lead_ids: List[int], force_check: bool = False):
    """Celery background task to verify WhatsApp accounts in bulk for multiple leads."""
    leads = Lead.objects.select_related('business').filter(id__in=lead_ids)
    verifier = WhatsAppVerifierService()
    results = verifier.verify_leads_batch(leads, force_check=force_check)
    logger.info(f"Bulk WhatsApp verification completed for {len(results)} leads.")
    return results

def trigger_lead_whatsapp_verification(lead_id: int, force_check: bool = False):
    """
    Triggers lead verification using Celery background queue if Redis is running,
    otherwise runs synchronously for instant consistency.
    """
    if is_redis_running():
        try:
            return verify_lead_whatsapp_task.delay(lead_id, force_check=force_check)
        except Exception as e:
            logger.warning(f"Failed to enqueue Celery task, running synchronously: {e}")
            return verify_lead_whatsapp_task(lead_id, force_check=force_check)
    else:
        return verify_lead_whatsapp_task(lead_id, force_check=force_check)

def trigger_bulk_whatsapp_verification(lead_ids: List[int], force_check: bool = False):
    """
    Triggers bulk lead verification using Celery background queue if Redis is running,
    otherwise runs synchronously.
    """
    if not lead_ids:
        return None

    if is_redis_running():
        try:
            return verify_leads_bulk_task.delay(lead_ids, force_check=force_check)
        except Exception as e:
            logger.warning(f"Failed to enqueue bulk Celery task, running synchronously: {e}")
            return verify_leads_bulk_task(lead_ids, force_check=force_check)
    else:
        return verify_leads_bulk_task(lead_ids, force_check=force_check)
