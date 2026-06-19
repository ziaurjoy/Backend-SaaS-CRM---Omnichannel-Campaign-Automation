import requests
import random
import string

BASE_URL = "http://localhost:8000"

def generate_random_string(length=8):
    letters = string.ascii_lowercase
    return ''.join(random.choice(letters) for i in range(length))

def run_tests():
    print("======================================================")
    print("  STARTING GOOGLE PLACES METADATA & SEARCH API TESTS  ")
    print("======================================================")
    
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
    if r.status_code != 201:
        print(f"   -> Failed: {r.status_code} - {r.text}")
        return

    # 2. Login User (Obtain JWT)
    print("\n2. Logging in to obtain JWT Pair ...")
    login_payload = {
        "username": username,
        "password": password
    }
    r = requests.post(f"{BASE_URL}/api/auth/login/", json=login_payload)
    if r.status_code != 200:
        print(f"   -> Failed: {r.status_code} - {r.text}")
        return
    access_token = r.json()["access"]

    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    # 3. Complete Onboarding
    print("\n3. Submitting Onboarding details ...")
    onboard_payload = {
        "first_name": "Metadata",
        "last_name": "Tester",
        "phone_number": "+1 555-000-1111",
        "timezone": "UTC",
        "business_name": f"Metadata Test Corp {generate_random_string(4).upper()}",
        "industry": "Software Engineering",
        "website": "https://metadatatest.org",
        "country": "Germany",
        "address": "123 Metadata St, Berlin"
    }
    r = requests.post(f"{BASE_URL}/api/auth/onboard/", json=onboard_payload, headers=headers)
    if r.status_code != 200:
        print(f"   -> Failed: {r.status_code} - {r.text}")
        return
    business_id = r.json()["business_id"]
    headers["X-Business-ID"] = business_id

    # 4. Create Two Collections to Test Search
    print("\n4. Creating two collections for search verification ...")
    col1 = requests.post(f"{BASE_URL}/api/collections/", json={"name": "Dhaka Software Companies", "description": "Software firms"}, headers=headers).json()
    col2 = requests.post(f"{BASE_URL}/api/collections/", json={"name": "Munich Cafes", "description": "Coffee shops"}, headers=headers).json()
    print(f"   -> Success: Created '{col1['name']}' (ID: {col1['id']}) and '{col2['name']}' (ID: {col2['id']})")

    # 5. Test Collection Search
    print("\n5. Testing Collection Search endpoint ...")
    r_dhaka = requests.get(f"{BASE_URL}/api/collections/?search=Dhaka", headers=headers).json()
    r_dhaka = r_dhaka if isinstance(r_dhaka, list) else r_dhaka.get('results', [])
    r_cafe = requests.get(f"{BASE_URL}/api/collections/?search=Munich", headers=headers).json()
    r_cafe = r_cafe if isinstance(r_cafe, list) else r_cafe.get('results', [])
    r_none = requests.get(f"{BASE_URL}/api/collections/?search=NonExistentCollection", headers=headers).json()
    r_none = r_none if isinstance(r_none, list) else r_none.get('results', [])

    print(f"   -> Search query 'Dhaka' returned {len(r_dhaka)} results (Expected: 1)")
    print(f"   -> Search query 'Munich' returned {len(r_cafe)} results (Expected: 1)")
    print(f"   -> Search query 'NonExistentCollection' returned {len(r_none)} results (Expected: 0)")
    assert len(r_dhaka) == 1, "Dhaka search failed"
    assert len(r_cafe) == 1, "Munich search failed"
    assert len(r_none) == 0, "NonExistent search failed"

    # 6. Scrape Google Places (Mock) under Dhaka Software Collection
    print("\n6. Triggering Places Scrape (Mock mode) ...")
    scrape_payload = {
        "query": "coffee shop",
        "collection_id": col2["id"]
    }
    r = requests.post(f"{BASE_URL}/api/leads/scrape_google_places/", json=scrape_payload, headers=headers)
    if r.status_code != 201:
        print(f"   -> Failed: {r.status_code} - {r.text}")
        return
    scrape_data = r.json()
    scraped_leads = scrape_data["leads"]
    print(f"   -> Success: Scraped and imported {len(scraped_leads)} leads.")

    # 7. Verify all Metadata fields are populated
    print("\n7. Verifying Google Places metadata fields in Database ...")
    for lead in scraped_leads:
        print(f"   -> Verifying lead: '{lead['name']}'")
        assert lead["place_id"] is not None and lead["place_id"].startswith("ChIJ"), "place_id is missing or incorrect"
        assert lead["user_ratings_total"] is not None and lead["user_ratings_total"] >= 0, "user_ratings_total is missing"
        assert lead["latitude"] is not None, "latitude is missing"
        assert lead["longitude"] is not None, "longitude is missing"
        assert lead["business_status"] is not None and len(lead["business_status"]) > 0, "business_status is missing or empty"
        assert isinstance(lead["types"], list) and len(lead["types"]) > 0, "types list is missing or empty"
        assert lead["google_metadata"] is not None and isinstance(lead["google_metadata"], dict), "google_metadata raw JSON is missing"
        print(f"      * place_id: {lead['place_id']}")
        print(f"      * ratings: {lead['user_ratings_total']}")
        print(f"      * location: ({lead['latitude']}, {lead['longitude']})")
        print(f"      * status: {lead['business_status']}")
        print(f"      * types: {lead['types']}")
        print("      * Status: OK")

    # 8. Test Lead Search API Filter
    print("\n8. Testing Universal Lead Search endpoint ...")
    # Fetch first lead name
    sample_lead_name = scraped_leads[0]["name"]
    sample_lead_part = sample_lead_name.split()[0]
    
    r_lead = requests.get(f"{BASE_URL}/api/leads/?collection={col2['id']}&search={sample_lead_part}", headers=headers).json()
    r_lead = r_lead if isinstance(r_lead, list) else r_lead.get('results', [])
    
    r_empty = requests.get(f"{BASE_URL}/api/leads/?collection={col2['id']}&search=NonExistentBusiness", headers=headers).json()
    r_empty = r_empty if isinstance(r_empty, list) else r_empty.get('results', [])

    print(f"   -> Search query '{sample_lead_part}' returned {len(r_lead)} results (Expected: >=1)")
    print(f"   -> Search query 'NonExistentBusiness' returned {len(r_empty)} results (Expected: 0)")
    assert len(r_lead) >= 1, "Lead search failed"
    assert len(r_empty) == 0, "Lead search should have returned 0 results"

    print("\n======================================================")
    print("  ALL METADATA & SEARCH API TESTS PASSED SUCCESSFULLY! ")
    print("======================================================")

if __name__ == "__main__":
    run_tests()
