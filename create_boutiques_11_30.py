import gspread
from oauth2client.service_account import ServiceAccountCredentials
import time

SPREADSHEET_ID = "1TEluEvR3o-cWtVCQkueZFucHkLQzbhgtplmw7ZfVZLU"
DEBUT = 11
FIN = 20

ONGLETS = ['catalogue', 'ventes', 'stock', 'journal', 'vendeurs', 'config']
HEADERS = {
    'catalogue': ['id', 'nom', 'categorie', 'prixAchat', 'prixVente', 'stock', 'seuil'],
    'ventes': ['id', 'date', 'heure', 'produit', 'quantite', 'prixVente', 'remise', 'total', 'vendeur'],
    'stock': ['id', 'produit', 'stockActuel', 'seuil', 'dernierMouvement'],
    'journal': ['date', 'heure', 'type', 'produit', 'quantite', 'ancienStock', 'nouveauStock', 'utilisateur', 'details'],
    'vendeurs': ['id', 'username', 'password', 'nom', 'actif'],
    'config': ['parametre', 'valeur']
}

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
client = gspread.authorize(creds)
spreadsheet = client.open_by_key(SPREADSHEET_ID)

print(f"🚀 Création des boutiques {DEBUT} à {FIN}...")
print("="*50)

for b in range(DEBUT, FIN + 1):
    for onglet in ONGLETS:
        nom_onglet = f"boutique{b}_{onglet}"
        try:
            worksheet = spreadsheet.worksheet(nom_onglet)
            print(f"⚠️ {nom_onglet} existe déjà")
        except:
            worksheet = spreadsheet.add_worksheet(title=nom_onglet, rows=1000, cols=20)
            worksheet.append_row(HEADERS[onglet])
            worksheet.format('A1:Z1', {'textFormat': {'bold': True}})
            print(f"✅ {nom_onglet} créé")
            time.sleep(0.5)  # Pause pour éviter les limites API
    print(f"--- Boutique {b} terminée ---")

print("\n🎉 Création terminée !")