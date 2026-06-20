import os
import requests
import json
from dotenv import load_dotenv

# Load env variables from backend/.env
load_dotenv(dotenv_path='.env')

def debug_places():
    api_key = os.environ.get('GOOGLE_PLACES_API_KEY')
    print(f"Loaded API Key: {api_key[:10]}...{api_key[-5:] if api_key else ''}")
    
    if not api_key:
        print("Error: GOOGLE_PLACES_API_KEY not found in environment!")
        return

    # 1. Test TextSearch Endpoint
    query = "software company dhaka"
    print(f"\n--- [1] Requesting Text Search for query: '{query}' ---")
    search_url = f"https://maps.googleapis.com/maps/api/place/textsearch/json?query={query}&key={api_key}"
    
    try:
        r = requests.get(search_url)
        print(f"Status Code: {r.status_code}")
        if r.status_code == 200:
            res_data = r.json()
            results = res_data.get('results', [])
            print(f"Total results returned in list: {len(results)}")
            
            if results:
                # Print the first result structure in a pretty format
                print("\n--- Raw JSON structure of the first search result in list: ---")
                print(json.dumps(results[0], indent=2))
                
                place_id = results[0].get('place_id')
                name = results[0].get('name')
                
                # 2. Test Details Endpoint
                print(f"\n--- [2] Requesting Place Details for: '{name}' (Place ID: {place_id}) ---")
                fields = "formatted_phone_number,website,user_ratings_total,geometry,business_status,types"
                details_url = f"https://maps.googleapis.com/maps/api/place/details/json?place_id={place_id}&fields={fields}&key={api_key}"
                
                dr = requests.get(details_url)
                print(f"Status Code: {dr.status_code}")
                if dr.status_code == 200:
                    details_data = dr.json()
                    print("\n--- Raw JSON structure of Place Details response: ---")
                    print(json.dumps(details_data, indent=2))
                else:
                    print(f"Details Error response: {dr.text}")
            else:
                print("No results found.")
        else:
            print(f"Search Error response: {r.text}")
            
    except Exception as e:
        print(f"Exception during request: {e}")

if __name__ == "__main__":
    debug_places()
