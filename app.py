from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import json
import os
from datetime import datetime
import hashlib

app = Flask(__name__)
app.secret_key = 'gbutik_secret_key_2024'

DB_FILE = 'database.json'

def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        'produits': [],
        'ventes': [],
        'journal': [],
        'utilisateurs': [
            {'id': 1, 'username': 'vendeur1', 'password': hashlib.sha256('vendeur123'.encode()).hexdigest(), 'role': 'vendeur', 'nom': 'Vendeur Test', 'actif': True}
        ],
        'messages': []
    }

def save_db(data):
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# Initialisation des données
def init_db():
    db = load_db()
    if len(db['produits']) == 0:
        db['produits'] = [
            {'id': 'PROD_001', 'nom': 'Produit Test A', 'categorie': 'Électronique', 'prixAchat': 500, 'prixVente': 1000, 'stock': 100, 'seuil': 10},
            {'id': 'PROD_002', 'nom': 'Produit Test B', 'categorie': 'Accessoires', 'prixAchat': 250, 'prixVente': 500, 'stock': 50, 'seuil': 5},
            {'id': 'PROD_003', 'nom': 'Produit Test C', 'categorie': 'Consommables', 'prixAchat': 100, 'prixVente': 200, 'stock': 200, 'seuil': 20}
        ]
    if len(db['ventes']) == 0:
        db['ventes'] = []
    if len(db['journal']) == 0:
        db['journal'] = []
    if len(db['messages']) == 0:
        db['messages'] = []
    save_db(db)

init_db()

# Routes HTML
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@app.route('/catalogue')
def catalogue():
    return render_template('catalogue.html')

@app.route('/stock')
def stock():
    return render_template('stock.html')

@app.route('/vente')
def vente():
    return render_template('vente.html')

@app.route('/journal')
def journal():
    return render_template('journal.html')

@app.route('/historique')
def historique():
    return render_template('historique.html')

@app.route('/caisse-jour')
def caisse_jour():
    return render_template('caisse-jour.html')

@app.route('/corrections')
def corrections():
    return render_template('corrections.html')

@app.route('/statistiques')
def statistiques():
    return render_template('statistiques.html')

@app.route('/admin')
def admin():
    return render_template('admin.html')

@app.route('/approvisionnement')
def approvisionnement():
    return render_template('approvisionnement.html')

@app.route('/messages-vendeur')
def messages_vendeur():
    return render_template('messages-vendeur.html')

@app.route('/messages-gerant')
def messages_gerant():
    return render_template('messages-gerant.html')

# ========== API ROUTES ==========

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    interface = data.get('interface')
    
    password_hash = hash_password(password)
    
    if interface == 'gerant' and password == 'admin123':
        session['user_role'] = 'gerant'
        session['user_nom'] = 'Gérant'
        return jsonify({'success': True, 'role': 'gerant'})
    
    db = load_db()
    for user in db.get('utilisateurs', []):
        if user['username'] == username and user['password'] == password_hash and user['actif']:
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['user_role'] = user['role']
            session['user_nom'] = user['nom']
            return jsonify({'success': True, 'role': user['role']})
    
    return jsonify({'success': False, 'error': 'Identifiants incorrects'})

@app.route('/api/logout', methods=['POST'])
def api_logout():
    session.clear()
    return jsonify({'success': True})

@app.route('/api/getDashboardStats')
def api_dashboard_stats():
    db = load_db()
    produits = db.get('produits', [])
    alertes = [p for p in produits if p.get('stock', 0) <= p.get('seuil', 10)]
    return jsonify({
        'ca_jour': 0,
        'ca_mois': 0,
        'nb_produits': len(produits),
        'alertes': len(alertes),
        'produits_critiques': [{'produit_nom': p['nom'], 'stock_restant': p['stock'], 'seuil_alerte': p['seuil']} for p in alertes]
    })

@app.route('/api/getProduitsPourWeb')
def api_produits():
    db = load_db()
    produits = [{'nom': p['nom'], 'stock': p['stock'], 'prixFixe': p['prixVente'], 'categorie': p.get('categorie', '')} for p in db.get('produits', [])]
    return jsonify(produits)

@app.route('/api/getCatalogueComplet')
def api_catalogue():
    db = load_db()
    return jsonify(db.get('produits', []))

@app.route('/api/getStockComplet')
def api_stock():
    db = load_db()
    produits = db.get('produits', [])
    return jsonify({
        'stock': produits,
        'nbProduits': len(produits),
        'valeurStock': sum(p['prixVente'] * p['stock'] for p in produits),
        'alertes': sum(1 for p in produits if p['stock'] <= p['seuil']),
        'ruptures': sum(1 for p in produits if p['stock'] <= 0)
    })

@app.route('/api/getVentesDuJour')
def api_ventes_jour():
    db = load_db()
    aujourd_hui = datetime.now().strftime('%d/%m/%Y')
    ventes = db.get('ventes', [])
    ventes_jour = [v for v in ventes if v.get('date') == aujourd_hui]
    return jsonify({
        'totalVentes': sum(v.get('total_net', 0) for v in ventes_jour),
        'nbVentes': len(ventes_jour),
        'nbProduitsVendus': sum(v.get('quantite', 0) for v in ventes_jour),
        'remiseTotale': sum(v.get('remise', 0) for v in ventes_jour),
        'date': aujourd_hui,
        'ventes': ventes_jour
    })

@app.route('/api/getHistoriqueVentes')
def api_historique():
    db = load_db()
    return jsonify(db.get('ventes', [])[::-1])

@app.route('/api/getJournalMouvements')
def api_journal():
    db = load_db()
    return jsonify(db.get('journal', [])[::-1])

@app.route('/api/validerVenteWeb', methods=['POST'])
def api_valider_vente():
    data = request.get_json()
    db = load_db()
    
    vente = {
        'id': 'VENTE_' + str(len(db['ventes']) + 1),
        'date': datetime.now().strftime('%d/%m/%Y'),
        'heure': datetime.now().strftime('%H:%M:%S'),
        'produit': data.get('produit'),
        'quantite': data.get('quantite'),
        'prix_unitaire': 0,
        'prix_vendu': data.get('prixVendu'),
        'remise': data.get('remise', 0),
        'total_net': data.get('totalNet'),
        'vendeur': 'Vendeur'
    }
    db['ventes'].append(vente)
    
    # Mettre à jour le stock
    for p in db['produits']:
        if p['nom'] == data.get('produit'):
            p['stock'] -= data.get('quantite')
            break
    
    # Journal
    db['journal'].append({
        'date': datetime.now().strftime('%d/%m/%Y'),
        'heure': datetime.now().strftime('%H:%M:%S'),
        'type': 'VENTE',
        'produit': data.get('produit'),
        'quantite': data.get('quantite'),
        'stockAvant': 0,
        'stockApres': 0,
        'utilisateur': 'Vendeur'
    })
    
    save_db(db)
    return jsonify("✅ Vente enregistrée!")

@app.route('/api/ajouterProduitWeb', methods=['POST'])
def api_ajouter_produit():
    data = request.get_json()
    db = load_db()
    
    new_id = 'PROD_' + str(len(db['produits']) + 1).zfill(3)
    produit = {
        'id': new_id,
        'nom': data.get('nom'),
        'categorie': data.get('categorie', ''),
        'prixAchat': data.get('prixAchat', 0),
        'prixVente': data.get('prixVente', 0),
        'stock': data.get('stock', 0),
        'seuil': data.get('seuil', 10)
    }
    db['produits'].append(produit)
    save_db(db)
    return jsonify("✅ Produit ajouté avec succès!")

@app.route('/api/approvisionnerWeb', methods=['POST'])
def api_approvisionner():
    data = request.get_json()
    db = load_db()
    
    for p in db['produits']:
        if p['nom'] == data.get('produit'):
            p['stock'] += data.get('quantite')
            break
    
    db['journal'].append({
        'date': datetime.now().strftime('%d/%m/%Y'),
        'heure': datetime.now().strftime('%H:%M:%S'),
        'type': 'APPROVISIONNEMENT',
        'produit': data.get('produit'),
        'quantite': data.get('quantite'),
        'stockAvant': 0,
        'stockApres': 0,
        'utilisateur': 'Gérant'
    })
    save_db(db)
    return jsonify("✅ Approvisionnement effectué!")

@app.route('/api/getStatistiques')
def api_statistiques():
    periode = request.args.get('periode', 'jour')
    return jsonify({
        'chiffreAffaire': 0,
        'nbVentes': 0,
        'nbProduitsVendus': 0,
        'remiseTotale': 0,
        'ticketMoyen': 0,
        'topProduits': [],
        'topVendeurs': [],
        'evolution': []
    })

@app.route('/api/getAllVendeurs')
def api_vendeurs():
    db = load_db()
    return jsonify(db.get('utilisateurs', []))

@app.route('/api/ajouterVendeurWeb', methods=['POST'])
def api_ajouter_vendeur():
    data = request.get_json()
    db = load_db()
    new_id = len(db.get('utilisateurs', [])) + 1
    vendeur = {
        'id': new_id,
        'username': data.get('username'),
        'password': hash_password(data.get('password')),
        'nom': data.get('nom'),
        'role': 'vendeur',
        'actif': True
    }
    if 'utilisateurs' not in db:
        db['utilisateurs'] = []
    db['utilisateurs'].append(vendeur)
    save_db(db)
    return jsonify("✅ Vendeur ajouté avec succès!")

@app.route('/api/desactiverVendeurWeb', methods=['POST'])
def api_desactiver_vendeur():
    data = request.get_json()
    db = load_db()
    for u in db.get('utilisateurs', []):
        if u['id'] == data.get('id'):
            u['actif'] = not data.get('actif', True)
            break
    save_db(db)
    return jsonify("✅ Statut modifié!")

@app.route('/api/envoyerMessage', methods=['POST'])
def api_envoyer_message():
    data = request.get_json()
    db = load_db()
    message = {
        'id': len(db.get('messages', [])) + 1,
        'date': datetime.now().strftime('%d/%m/%Y'),
        'heure': datetime.now().strftime('%H:%M:%S'),
        'de': data.get('expediteur'),
        'message': data.get('message'),
        'lu': 'NON'
    }
    if 'messages' not in db:
        db['messages'] = []
    db['messages'].append(message)
    save_db(db)
    return jsonify("✅ Message envoyé!")

@app.route('/api/getMessages')
def api_messages():
    db = load_db()
    return jsonify(db.get('messages', [])[::-1])

@app.route('/api/getMessagesByVendeur')
def api_messages_vendeur():
    vendeur = request.args.get('vendeur', '')
    db = load_db()
    messages = [m for m in db.get('messages', []) if m.get('de') == vendeur or m.get('de') == 'Gérant']
    return jsonify(messages[::-1])

if __name__ == '__main__':
    app.run(debug=True, port=5000)