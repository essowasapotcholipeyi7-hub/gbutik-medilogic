import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json

# Configuration
SPREADSHEET_ID = "1TEluEvR3o-cWtVCQkueZFucHkLQzbhgtplmw7ZfVZLU"
NOMBRE_BOUTIQUES = 10

# Types d'onglets par boutique
ONGLETS = ['catalogue', 'ventes', 'stock', 'journal', 'vendeurs', 'config']

# En-têtes pour chaque type d'onglet
HEADERS = {
    'catalogue': ['id', 'nom', 'categorie', 'prixAchat', 'prixVente', 'stock', 'seuil'],
    'ventes': ['id', 'date', 'heure', 'produit', 'quantite', 'prixVente', 'remise', 'total', 'vendeur'],
    'stock': ['id', 'produit', 'stockActuel', 'seuil', 'dernierMouvement'],
    'journal': ['date', 'heure', 'type', 'produit', 'quantite', 'ancienStock', 'nouveauStock', 'utilisateur'],
    'vendeurs': ['id', 'username', 'password', 'nom', 'actif'],
    'config': ['parametre', 'valeur']
}

print("=" * 50)
print("🚀 CRÉATION DES BOUTIQUES DANS GOOGLE SHEETS")
print("=" * 50)
print(f"📊 Spreadsheet ID: {SPREADSHEET_ID}")
print(f"🏪 Nombre de boutiques: {NOMBRE_BOUTIQUES}")
print(f"📑 Onglets par boutique: {len(ONGLETS)}")
print("=" * 50)

# Authentification
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
client = gspread.authorize(creds)

# Ouvrir la feuille
sheet = client.open_by_key(SPREADSHEET_ID)
print(f"\n✅ Connecté à: {sheet.title}")

# Créer les onglets
for b in range(1, NOMBRE_BOUTIQUES + 1):
    for onglet in ONGLETS:
        nom_onglet = f"boutique{b}_{onglet}"
        try:
            worksheet = sheet.worksheet(nom_onglet)
            print(f"⚠️ {nom_onglet} existe déjà")
        except:
            worksheet = sheet.add_worksheet(title=nom_onglet, rows=1000, cols=20)
            worksheet.append_row(HEADERS[onglet])
            worksheet.format('A1:Z1', {'textFormat': {'bold': True}})
            print(f"✅ {nom_onglet} créé")

print("\n" + "=" * 50)
print("🎉 STRUCTURE COMPLÈTE CRÉÉE !")
print("=" * 50)
print(f"\n📁 {NOMBRE_BOUTIQUES} boutiques x {len(ONGLETS)} onglets = {NOMBRE_BOUTIQUES * len(ONGLETS)} onglets")