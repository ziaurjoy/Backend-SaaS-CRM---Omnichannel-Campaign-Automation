import requests
import random
import string

BASE_URL = "http://localhost:8000"

def generate_random_string(length=8):
    letters = string.ascii_lowercase
    return ''.join(random.choice(letters) for i in range(length))

def run_tests():
    print("======================================================")
    print("      STARTING META EMBEDDED SIGNUP INTEGRATION TEST   ")
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
    print("   -> Success: User registered.")

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
    print("   -> Success: Token obtained.")

    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    # 3. Complete Onboarding
    print("\n3. Submitting Onboarding details ...")
    onboard_payload = {
        "first_name": "Meta",
        "last_name": "Embedded",
        "phone_number": "+1 555-999-1111",
        "timezone": "UTC",
        "business_name": f"Meta Test Corp {generate_random_string(4).upper()}",
        "industry": "Marketing Automation",
        "website": "https://metasignup.org",
        "country": "United States",
        "address": "1601 Willow Rd, Menlo Park"
    }
    r = requests.post(f"{BASE_URL}/api/auth/onboard/", json=onboard_payload, headers=headers)
    if r.status_code != 200:
        print(f"   -> Failed: {r.status_code} - {r.text}")
        return
    business_id = r.json()["business_id"]
    headers["X-Business-ID"] = business_id
    print(f"   -> Success: Onboard complete. Business ID: {business_id}")

    # 4. Fetch Meta App configurations
    print("\n4. Fetching Meta Configuration details ...")
    r = requests.get(f"{BASE_URL}/api/integrations/meta_config/", headers=headers)
    if r.status_code != 200:
        print(f"   -> Failed: {r.status_code} - {r.text}")
        return
    config = r.json()
    print(f"   -> Success: Config retrieved.")
    print(f"      * Meta App ID: {config['meta_app_id'] or 'None (Mock Mode)'}")
    print(f"      * Meta Redirect URI: {config['meta_redirect_uri']}")
    print(f"      * Is Mock Mode: {config['is_mock_mode']}")
    assert "meta_app_id" in config
    assert "meta_redirect_uri" in config
    assert "is_mock_mode" in config

    # 5. Test Code Exchange (Mock Mode)
    print("\n5. Testing Code Exchange (Simulating Onboarding completion) ...")
    mock_bm_name = "Nobo IT Solutions (ID: 9812739)"
    mock_phone_num = "+880 1700-112233"
    mock_waba_id = "87162"
    mock_phone_id = "2981739"
    
    exchange_payload = {
        "code": "mock_auth_code",
        "mock_data": {
            "phone_number": mock_phone_num,
            "waba_id": mock_waba_id,
            "phone_id": mock_phone_id,
            "business_name": mock_bm_name
        }
    }
    r = requests.post(f"{BASE_URL}/api/integrations/exchange_meta_code/", json=exchange_payload, headers=headers)
    if r.status_code != 200:
        print(f"   -> Failed: {r.status_code} - {r.text}")
        return
    
    res = r.json()
    print("   -> Success: Connected Integration details:")
    integration = res["integration"]
    print(f"      * Provider: {integration['provider']}")
    print(f"      * Status: {integration['status']}")
    print(f"      * Connected Phone: {integration['connected_phone']}")
    print(f"      * Credentials: {integration['credentials']}")
    
    assert integration["provider"] == "WhatsApp"
    assert integration["status"] == "Connected"
    assert integration["connected_phone"] == mock_phone_num
    assert integration["credentials"]["waba_id"] == mock_waba_id
    assert integration["credentials"]["phone_id"] == mock_phone_id
    assert integration["credentials"]["link_type"] == "Meta_Embedded_Signup"

    # 6. Fetch Integration List to verify persistence
    print("\n6. Fetching Integrations List ...")
    r = requests.get(f"{BASE_URL}/api/integrations/", headers=headers)
    if r.status_code != 200:
        print(f"   -> Failed: {r.status_code} - {r.text}")
        return
    integrations_list = r.json()
    integrations_list = integrations_list if isinstance(integrations_list, list) else integrations_list.get('results', [])
    print(f"   -> Success: Found {len(integrations_list)} integrations in workspace.")
    assert len(integrations_list) == 1, "Integration should be persisted."
    assert integrations_list[0]["provider"] == "WhatsApp"

    print("\n======================================================")
    print("  META EMBEDDED SIGNUP TESTS PASSED SUCCESSFULLY!     ")
    print("======================================================")

if __name__ == "__main__":
    run_tests()
