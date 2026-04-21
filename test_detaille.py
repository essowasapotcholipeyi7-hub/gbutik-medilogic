import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json

print("=" * 50)
print("DIAGNOSTIC GOOGLE SHEETS")
print("=" * 50)

# 1. Vérifier que credentials.json existe
try:
    with open('credentials.json', 'r') as f:
        creds_data = json.load(f)
    print("✅ credentials.json trouvé")
    print(f"   Client email: {creds_data.get('client_email', 'NON TROUVE')}")
except Exception as e:
    print(f"❌ credentials.json non trouvé: {e}")
    exit()

# 2. Tenter la connexion
print("\n🔐 Tentative de connexion...")

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

try:
    creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
    print("✅ Credentials chargés")
    
    client = gspread.authorize(creds)
    print("✅ Authorisation réussie")
    
    SPREADSHEET_ID = "1TEluEvR3o-cWtVCQkueZFucHkLQzbhgtplmw7ZfVZLU"
    
    # Essayer d'ouvrir la feuille
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    print(f"✅ Feuille ouverte: {spreadsheet.title}")
    
    # Lire la première feuille
    worksheet = spreadsheet.get_worksheet(0)
    print(f"✅ Première feuille: {worksheet.title}")
    
except gspread.exceptions.APIError as e:
    print(f"❌ Erreur API: {e}")
    print("\n👉 SOLUTION: Partagez votre Google Sheets avec:")
    print("   cnss-stats@fleet-bus-492816-m8.iam.gserviceaccount.com")
    
except Exception as e:
    print(f"❌ Erreur: {type(e).__name__}: {e}")