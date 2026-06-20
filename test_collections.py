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
    print("    STARTING CRM LEAD COLLECTIONS INTEGRATION TEST  ")
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
        "first_name": "Collections",
        "last_name": "Tester",
        "phone_number": "+1 888-999-1111",
        "timezone": "UTC",
        "business_name": f"Collections Test Corp {generate_random_string(4).upper()}",
        "industry": "Customer Relationship Management",
        "website": "https://collections.org",
        "country": "Germany",
        "address": "123 Collection Lane, Munich"
    }
    r = requests.post(f"{BASE_URL}/api/auth/onboard/", json=onboard_payload, headers=headers)
    if r.status_code == 200:
        data = r.json()
        business_id = data["business_id"]
        print(f"   -> Success: Onboard complete. Business ID: {business_id}")
    else:
        print(f"   -> Failed: {r.status_code} - {r.text}")
        return

    headers["X-Business-ID"] = business_id

    # 4. Create a Lead Collection
    print("\n4. Creating a Lead Collection ...")
    collection_payload = {
        "name": "Dhaka Software",
        "description": "Software companies located in Dhaka, Bangladesh"
    }
    r = requests.post(f"{BASE_URL}/api/collections/", json=collection_payload, headers=headers)
    if r.status_code == 201:
        collection_data = r.json()
        collection_id = collection_data["id"]
        print(f"   -> Success: Collection created. ID: {collection_id}, Name: {collection_data['name']}")
    else:
        print(f"   -> Failed: {r.status_code} - {r.text}")
        return

    # 5. Rename / Update the Lead Collection
    print("\n5. Updating the Lead Collection details ...")
    update_payload = {
        "name": "Dhaka Tech Hub",
        "description": "Tech companies located in Dhaka"
    }
    r = requests.patch(f"{BASE_URL}/api/collections/{collection_id}/", json=update_payload, headers=headers)
    if r.status_code == 200:
        updated_data = r.json()
        print(f"   -> Success: Collection renamed to '{updated_data['name']}'")
    else:
        print(f"   -> Failed: {r.status_code} - {r.text}")
        return

    # 6. Scrape Google Places (Targeting this Collection)
    print("\n6. Scraping Google Places into collection ...")
    scrape_payload = {
        "query": "restaurants in Munich",
        "collection_id": collection_id
    }
    r = requests.post(f"{BASE_URL}/api/leads/scrape_google_places/", json=scrape_payload, headers=headers)
    if r.status_code == 201:
        data = r.json()
        leads_scraped = data["leads"]
        print(f"   -> Success: {data['message']}")
        print(f"   -> Scraped {len(leads_scraped)} leads.")
        lead_id = leads_scraped[0]["id"]
        lead_name = leads_scraped[0]["name"]
    else:
        print(f"   -> Failed: {r.status_code} - {r.text}")
        return

    # 7. List leads in this collection
    print(f"\n7. Fetching leads under collection ID {collection_id} ...")
    r = requests.get(f"{BASE_URL}/api/leads/?collection={collection_id}", headers=headers)
    if r.status_code == 200:
        leads_list = r.json()
        leads_list = leads_list if isinstance(leads_list, list) else leads_list.get('results', [])
        print(f"   -> Success: Found {len(leads_list)} leads in collection.")
    else:
        print(f"   -> Failed: {r.status_code} - {r.text}")
        return

    # 8. Edit / Update individual Lead details
    print(f"\n8. Editing Lead details (ID: {lead_id}, Name: {lead_name}) ...")
    lead_update_payload = {
        "name": f"{lead_name} (Verified)",
        "stage": "Qualified",
        "phone": "+49 89 123456"
    }
    r = requests.patch(f"{BASE_URL}/api/leads/{lead_id}/", json=lead_update_payload, headers=headers)
    if r.status_code == 200:
        updated_lead = r.json()
        print(f"   -> Success: Lead renamed to '{updated_lead['name']}', Stage: '{updated_lead['stage']}'")
    else:
        print(f"   -> Failed: {r.status_code} - {r.text}")
        return

    # 9. Delete individual Lead
    print(f"\n9. Deleting Lead (ID: {lead_id}) ...")
    r = requests.delete(f"{BASE_URL}/api/leads/{lead_id}/", headers=headers)
    if r.status_code in [200, 204]:
        print("   -> Success: Lead deleted.")
    else:
        print(f"   -> Failed: {r.status_code} - {r.text}")
        return

    # 10. Delete Lead Collection (Cascading delete check)
    print(f"\n10. Deleting Collection (ID: {collection_id}) ...")
    r = requests.delete(f"{BASE_URL}/api/collections/{collection_id}/", headers=headers)
    if r.status_code in [200, 204]:
        print("   -> Success: Collection deleted.")
    else:
        print(f"   -> Failed: {r.status_code} - {r.text}")
        return

    # 11. Verify Leads are deleted too (Cascading)
    print("\n11. Verifying leads were cascadingly deleted ...")
    r = requests.get(f"{BASE_URL}/api/leads/?collection={collection_id}", headers=headers)
    if r.status_code == 200:
        leads_list = r.json()
        leads_list = leads_list if isinstance(leads_list, list) else leads_list.get('results', [])
        print(f"   -> Success: Found {len(leads_list)} leads left in this deleted collection.")
        if len(leads_list) != 0:
            print("   -> Failed: Leads were not cascadingly deleted!")
            return
    else:
        print(f"   -> Failed: {r.status_code} - {r.text}")
        return

    print("\n====================================================")
    print("    LEAD COLLECTIONS & CRUD TESTS PASSED SUCCESSFULLY! ")
    print("====================================================")

if __name__ == "__main__":
    run_tests()
