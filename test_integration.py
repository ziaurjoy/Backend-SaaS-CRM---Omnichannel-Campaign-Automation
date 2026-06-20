import requests
import random
import string
import time

BASE_URL = "http://localhost:8000"

def generate_random_string(length=8):
    letters = string.ascii_lowercase
    return ''.join(random.choice(letters) for i in range(length))

def run_tests():
    print("====================================================")
    print("    STARTING END-TO-END INTEGRATION TEST            ")
    print("====================================================")
    
    # Generate unique test user
    username = f"user_{generate_random_string()}"
    password = "testpassword123"
    email = f"{username}@test.com"
    
    # 1. Register User
    print(f"\n1. Registering user: {username} ...")
    register_payload = {
        "username": username,
        "password": password,
        "email": email
    }
    r = requests.post(f"{BASE_URL}/api/auth/register/", json=register_payload)
    if r.status_code == 201:
        print("   -> Success: User registered.")
    else:
        print(f"   -> Failed: {r.status_code} - {r.text}")
        return

    # 2. Login User (Obtain JWT)
    print("\n2. Logging in to obtain JWT Pair ...")
    login_payload = {
        "username": username,
        "password": password
    }
    r = requests.post(f"{BASE_URL}/api/auth/login/", json=login_payload)
    if r.status_code == 200:
        tokens = r.json()
        access_token = tokens["access"]
        print("   -> Success: Token obtained.")
    else:
        print(f"   -> Failed: {r.status_code} - {r.text}")
        return

    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    # 3. Complete Onboarding
    print("\n3. Submitting Onboarding details ...")
    onboard_payload = {
        "first_name": "Integration",
        "last_name": "Tester",
        "phone_number": "+1 888-999-0000",
        "timezone": "UTC",
        "business_name": "Integration Test Corporation",
        "industry": "Quality Assurance",
        "website": "https://integrationtest.org",
        "country": "Canada",
        "address": "456 QA Boulevard, Toronto"
    }
    r = requests.post(f"{BASE_URL}/api/auth/onboard/", json=onboard_payload, headers=headers)
    if r.status_code == 200:
        data = r.json()
        business_id = data["business_id"]
        print(f"   -> Success: Onboard complete. Business ID: {business_id}")
    else:
        print(f"   -> Failed: {r.status_code} - {r.text}")
        return

    # Set business ID header for subsequent calls
    headers["X-Business-ID"] = business_id

    # 3.5. Test Integrations Endpoints
    print("\n3.5. Testing Integrations endpoints ...")
    # List integrations (should be empty)
    r = requests.get(f"{BASE_URL}/api/integrations/", headers=headers)
    if r.status_code == 200:
        integrations = r.json()
        integrations_list = integrations if isinstance(integrations, list) else integrations.get('results', [])
        print(f"   -> Initial integrations list: {len(integrations_list)} items.")
    else:
        print(f"   -> Failed listing integrations: {r.status_code} - {r.text}")
        return

    # Connect Gmail
    print("   -> Connecting Gmail integration ...")
    gmail_payload = {
        "email": "test-integration@gmail.com",
        "credentials": {"oauth_token": "test_token_123"},
        "status": "Connected"
    }
    r = requests.post(f"{BASE_URL}/api/integrations/connect_gmail/", json=gmail_payload, headers=headers)
    if r.status_code == 200:
        gmail_data = r.json()
        gmail_id = gmail_data["id"]
        print(f"      -> Success: Connected Gmail (ID: {gmail_id})")
    else:
        print(f"      -> Failed connecting Gmail: {r.status_code} - {r.text}")
        return

    # Connect WhatsApp
    print("   -> Connecting WhatsApp integration ...")
    whatsapp_payload = {
        "phone_number": "+1 (555) 777-8888",
        "credentials": {"link_type": "QR_Code", "session_id": "test_session"},
        "status": "Connected"
    }
    r = requests.post(f"{BASE_URL}/api/integrations/connect_whatsapp/", json=whatsapp_payload, headers=headers)
    if r.status_code == 200:
        whatsapp_data = r.json()
        whatsapp_id = whatsapp_data["id"]
        print(f"      -> Success: Connected WhatsApp (ID: {whatsapp_id})")
    else:
        print(f"      -> Failed connecting WhatsApp: {r.status_code} - {r.text}")
        return

    # List integrations (should have 2 items now)
    r = requests.get(f"{BASE_URL}/api/integrations/", headers=headers)
    if r.status_code == 200:
        integrations = r.json()
        integrations_list = integrations if isinstance(integrations, list) else integrations.get('results', [])
        print(f"   -> Current integrations list: {len(integrations_list)} items.")
        if len(integrations_list) != 2:
            print(f"   -> Failed: Expected 2 integrations, got {len(integrations_list)}")
            return
    else:
        print(f"   -> Failed listing integrations: {r.status_code} - {r.text}")
        return

    # Disconnect Gmail
    print(f"   -> Disconnecting Gmail (ID: {gmail_id}) ...")
    r = requests.delete(f"{BASE_URL}/api/integrations/{gmail_id}/", headers=headers)
    if r.status_code in [200, 204]:
        print("      -> Success: Gmail disconnected.")
    else:
        print(f"      -> Failed disconnecting Gmail: {r.status_code} - {r.text}")
        return

    # List integrations (should have 1 item now)
    r = requests.get(f"{BASE_URL}/api/integrations/", headers=headers)
    if r.status_code == 200:
        integrations = r.json()
        integrations_list = integrations if isinstance(integrations, list) else integrations.get('results', [])
        print(f"   -> Final integrations list: {len(integrations_list)} items.")
        if len(integrations_list) != 1:
            print(f"   -> Failed: Expected 1 integration, got {len(integrations_list)}")
            return
    else:
        print(f"   -> Failed listing integrations: {r.status_code} - {r.text}")
        return

    # 4. Create a Lead
    print("\n4. Creating custom Lead ...")
    lead_payload = {
        "name": "Target Lead A",
        "email": "target.a@example.com",
        "phone": "+1 555-9001",
        "website": "https://target-a.com",
        "address": "789 Target Lane",
        "source": "Manual",
        "stage": "New"
    }
    r = requests.post(f"{BASE_URL}/api/leads/", json=lead_payload, headers=headers)
    if r.status_code == 201:
        lead_data = r.json()
        lead_id = lead_data["id"]
        print(f"   -> Success: Custom lead created. Lead ID: {lead_id}")
    else:
        print(f"   -> Failed: {r.status_code} - {r.text}")
        return

    # 5. Scrape Google Places (Sandbox Mock Mode)
    print("\n5. Testing Google Places Scraper Endpoint (Mock Mode) ...")
    scrape_payload = {
        "query": "restaurants in New York"
    }
    r = requests.post(f"{BASE_URL}/api/leads/scrape_google_places/", json=scrape_payload, headers=headers)
    if r.status_code == 201:
        data = r.json()
        leads_count = len(data["leads"])
        print(f"   -> Success: {data['message']}")
        print(f"   -> Scraped {leads_count} mock leads.")
    else:
        print(f"   -> Failed: {r.status_code} - {r.text}")
        return

    # 6. Create Message Template
    print("\n6. Creating outreach message Template ...")
    template_payload = {
        "name": "Integration Test Template",
        "type": "Email",
        "subject": "Hello {{first_name}}, let's audit your software!",
        "body": "Hi {{first_name}},\n\nI noticed {{company_name}} operates in QA and wanted to outreach.\n\nBest,\nTester"
    }
    r = requests.post(f"{BASE_URL}/api/templates/", json=template_payload, headers=headers)
    if r.status_code == 201:
        template_data = r.json()
        template_id = template_data["id"]
        print(f"   -> Success: Template created. Template ID: {template_id}")
    else:
        print(f"   -> Failed: {r.status_code} - {r.text}")
        return

    # 7. Create Campaign
    print("\n7. Creating Campaign ...")
    campaign_payload = {
        "name": "Integration Test Campaign",
        "template": template_id,
        "channel": "Email",
        "schedule_type": "Immediate"
    }
    r = requests.post(f"{BASE_URL}/api/campaigns/", json=campaign_payload, headers=headers)
    if r.status_code == 201:
        campaign_data = r.json()
        campaign_id = campaign_data["id"]
        print(f"   -> Success: Campaign created. Campaign ID: {campaign_id}")
    else:
        print(f"   -> Failed: {r.status_code} - {r.text}")
        return

    # 8. Trigger Campaign Execution
    print("\n8. Triggering Campaign ...")
    r = requests.post(f"{BASE_URL}/api/campaigns/{campaign_id}/trigger/", headers=headers)
    if r.status_code == 201:
        data = r.json()
        print(f"   -> Success: Campaign run status: {data['run']['status']}")
        print(f"   -> Async Execution: {data['async_execution']}")
    else:
        print(f"   -> Failed: {r.status_code} - {r.text}")
        return

    # Wait briefly for delivery simulator
    print("\n   Waiting for delivery simulator tasks (1.5s)...")
    time.sleep(1.5)

    # 9. Get Messages Log
    print("\n9. Fetching Message delivery logs ...")
    r = requests.get(f"{BASE_URL}/api/messages/", headers=headers)
    if r.status_code == 200:
        messages = r.json()
        # Parse paginated results
        messages_list = messages if isinstance(messages, list) else messages.get('results', [])
        print(f"   -> Success: Retrieved {len(messages_list)} messages.")
        for m in messages_list[:3]:
            print(f"      - Msg ID {m['id']} to {m['recipient']}: {m['status']} (Opened: {m['opened_at'] is not None})")
    else:
        print(f"   -> Failed: {r.status_code} - {r.text}")
        return

    # 10. Fetch Dashboard Metrics
    print("\n10. Fetching Dashboard Analytics metrics ...")
    r = requests.get(f"{BASE_URL}/api/analytics/dashboard/", headers=headers)
    if r.status_code == 200:
        metrics = r.json()
        print("   -> Success: Analytics metrics returned.")
        print(f"      - Total Leads in CRM: {metrics['leads']['total']}")
        print(f"      - Total Campaigns Run: {metrics['campaigns']['total']}")
        print(f"      - Sent / Delivered: {metrics['messages']['sent']} / {metrics['messages']['delivered']}")
        print(f"      - Open Rate: {metrics['messages']['open_rate']}%")
    else:
        print(f"   -> Failed: {r.status_code} - {r.text}")
        return

    print("\n====================================================")
    print("    INTEGRATION TESTS PASSED SUCCESSFULLY!          ")
    print("====================================================")

if __name__ == "__main__":
    run_tests()
