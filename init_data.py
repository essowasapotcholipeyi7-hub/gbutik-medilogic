import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

SPREADSHEET_ID = "1TEluEvR3o-cWtVCQkueZFucHkLQzbhgtplmw7ZfVZLU"

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
client = gspread.authorize(creds)
spreadsheet = client.open_by_key(SPREADSHEET_ID)

# Pour chaque boutique de 1 à 10
for boutique_id in range(1, 11):
    print(f"\n📦 Initialisation boutique {boutique_id}...")
    
    # 1. Vérifier/Créer la feuille catalogue
    try:
        sheet = spreadsheet.worksheet(f"boutique{boutique_id}_catalogue")
        data = sheet.get_all_values()
        if len(data) <= 1:
            # Ajouter des produits de test
            sheet.append_row(['PROD_001', 'Produit Test 1', 'Électronique', 5000, 10000, 50, 10])
            sheet.append_row(['PROD_002', 'Produit Test 2', 'Accessoires', 2000, 4000, 30, 5])
            sheet.append_row(['PROD_003', 'Produit Test 3', 'Consommables', 1000, 2000, 100, 20])
            print(f"  ✅ Produits ajoutés au catalogue boutique {boutique_id}")
    except Exception as e:
        print(f"  ❌ Erreur catalogue: {e}")
    
    # 2. Vérifier/Créer la feuille stock
    try:
        sheet = spreadsheet.worksheet(f"boutique{boutique_id}_stock")
        data = sheet.get_all_values()
        if len(data) <= 1:
            sheet.append_row(['PROD_001', 'Produit Test 1', 50, 10, ''])
            sheet.append_row(['PROD_002', 'Produit Test 2', 30, 5, ''])
            sheet.append_row(['PROD_003', 'Produit Test 3', 100, 20, ''])
            print(f"  ✅ Stock ajouté pour boutique {boutique_id}")
    except Exception as e:
        print(f"  ❌ Erreur stock: {e}")
    
    # 3. Vérifier/Créer la feuille ventes
    try:
        sheet = spreadsheet.worksheet(f"boutique{boutique_id}_ventes")
        data = sheet.get_all_values()
        if len(data) <= 1:
            # Ajouter des ventes de test
            today = datetime.now().strftime('%d/%m/%Y')
            now = datetime.now().strftime('%H:%M:%S')
            sheet.append_row(['VENTE_001', today, now, 'Produit Test 1', 2, 10000, 0, 20000, 'Gérant'])
            sheet.append_row(['VENTE_002', today, now, 'Produit Test 2', 1, 4000, 0, 4000, 'Gérant'])
            print(f"  ✅ Ventes test ajoutées pour boutique {boutique_id}")
    except Exception as e:
        print(f"  ❌ Erreur ventes: {e}")
    
    # 4. Vérifier/Créer la feuille journal
    try:
        sheet = spreadsheet.worksheet(f"boutique{boutique_id}_journal")
        data = sheet.get_all_values()
        if len(data) <= 1:
            today = datetime.now().strftime('%d/%m/%Y')
            now = datetime.now().strftime('%H:%M:%S')
            sheet.append_row([today, now, 'VENTE', 'Produit Test 1', 2, 50, 48, 'Gérant'])
            sheet.append_row([today, now, 'VENTE', 'Produit Test 2', 1, 30, 29, 'Gérant'])
            print(f"  ✅ Journal test ajouté pour boutique {boutique_id}")
    except Exception as e:
        print(f"  ❌ Erreur journal: {e}")
    
    # 5. Vérifier/Créer la feuille vendeurs
    try:
        sheet = spreadsheet.worksheet(f"boutique{boutique_id}_vendeurs")
        data = sheet.get_all_values()
        if len(data) <= 1:
            sheet.append_row([1, 'vendeur1', 'vendeur123', 'Vendeur Test 1', 'oui'])
            sheet.append_row([2, 'vendeur2', 'vendeur123', 'Vendeur Test 2', 'oui'])
            print(f"  ✅ Vendeurs test ajoutés pour boutique {boutique_id}")
    except Exception as e:
        print(f"  ❌ Erreur vendeurs: {e}")

print("\n" + "="*50)
print("🎉 INITIALISATION TERMINÉE !")
print("="*50)