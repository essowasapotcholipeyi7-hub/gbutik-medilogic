import gspread
from oauth2client.service_account import ServiceAccountCredentials
import time

SPREADSHEET_ID = "1TEluEvR3o-cWtVCQkueZFucHkLQzbhgtplmw7ZfVZLU"
NOMBRE_BOUTIQUES = 10
ONGLETS = ['catalogue', 'ventes', 'stock', 'journal', 'vendeurs', 'config']
HEADERS = {
    'catalogue': ['id', 'nom', 'categorie', 'prixAchat', 'prixVente', 'stock', 'seuil'],
    'ventes': ['id', 'date', 'heure', 'produit', 'quantite', 'prixVente', 'remise', 'total', 'vendeur'],
    'stock': ['id', 'produit', 'stockActuel', 'seuil', 'dernierMouvement'],
    'journal': ['date', 'heure', 'type', 'produit', 'quantite', 'ancienStock', 'nouveauStock', 'utilisateur'],
    'vendeurs': ['id', 'username', 'password', 'nom', 'actif'],
    'config': ['parametre', 'valeur']
}

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
client = gspread.authorize(creds)
sheet = client.open_by_key(SPREADSHEET_ID)

print("🚀 Création des boutiques (version douce)...")
print("=" * 50)

for b in range(1, NOMBRE_BOUTIQUES + 1):
    for onglet in ONGLETS:
        nom_onglet = f"boutique{b}_{onglet}"
        try:
            worksheet = sheet.worksheet(nom_onglet)
            print(f"⚠️ {nom_onglet} existe déjà")
        except:
            try:
                worksheet = sheet.add_worksheet(title=nom_onglet, rows=1000, cols=20)
                worksheet.append_row(HEADERS[onglet])
                worksheet.format('A1:Z1', {'textFormat': {'bold': True}})
                print(f"✅ {nom_onglet} créé")
                time.sleep(2)  # Pause de 2 secondes entre chaque création
            except Exception as e:
                print(f"❌ Erreur pour {nom_onglet}: {e}")
                time.sleep(10)  # Pause plus longue en cas d'erreur
    print(f"--- Boutique {b} terminée ---")
    time.sleep(5)

print("\n🎉 FIN DE LA CRÉATION !")