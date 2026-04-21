import gspread
from oauth2client.service_account import ServiceAccountCredentials

print("🔐 Connexion à Google Sheets...")

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
client = gspread.authorize(creds)

SPREADSHEET_ID = "1XqayvXdvhUkvQKlzsBOTqAPbJzysdjUVdgNw704VfBA"

try:
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    print(f"✅ CONNEXION RÉUSSIE !")
    print(f"📊 Titre de la feuille : {spreadsheet.title}")
    
    # Essayer de lire la première feuille
    sheet = spreadsheet.get_worksheet(0)
    print(f"📄 Première feuille : {sheet.title}")
    
except Exception as e:
    print(f"❌ Erreur : {e}")
    print("\n💡 Vérifiez que :")
    print("  1. Les APIs Sheets et Drive sont activées")
    print("  2. Vous avez partagé la feuille avec : cnss-stats@fleet-bus-492816-m8.iam.gserviceaccount.com")
    print("  3. Le rôle est 'Éditeur'")