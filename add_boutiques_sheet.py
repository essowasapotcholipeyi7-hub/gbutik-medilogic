import gspread
from oauth2client.service_account import ServiceAccountCredentials

SPREADSHEET_ID = "1TEluEvR3o-cWtVCQkueZFucHkLQzbhgtplmw7ZfVZLU"

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
client = gspread.authorize(creds)
sheet = client.open_by_key(SPREADSHEET_ID)

# Créer l'onglet BOUTIQUES
try:
    boutique_sheet = sheet.worksheet("BOUTIQUES")
    print("⚠️ L'onglet BOUTIQUES existe déjà")
except:
    boutique_sheet = sheet.add_worksheet(title="BOUTIQUES", rows=100, cols=20)
    headers = ['id', 'nom_boutique', 'email_gerant', 'password', 'telephone', 'adresse', 'date_inscription', 'actif']
    boutique_sheet.append_row(headers)
    boutique_sheet.format('A1:H1', {'textFormat': {'bold': True}})
    print("✅ Onglet BOUTIQUES créé")