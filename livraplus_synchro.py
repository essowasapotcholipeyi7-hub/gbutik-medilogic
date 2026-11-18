"""Transition vers LivraPlus : chaque mouvement de stock d'une boutique est aussi envoyé à LivraPlus,
qui ajuste le stock du même article (même nom).

Ne s'active que pour les boutiques configurées (variables d'environnement) :
    LIVRAPLUS_URL          = https://<livraplus>/api/synchro/maboutik
    LIVRAPLUS_CLE_<id>     = clé créée dans LivraPlus (Ma boutique → Synchronisation Ma Boutik)
Les autres boutiques ne sont pas concernées. L'envoi se fait en arrière-plan : une vente dans
Ma Boutik ne l'attend jamais et n'échoue jamais à cause de LivraPlus."""
import json
import os
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime


def active(boutique_id):
    return bool(os.environ.get('LIVRAPLUS_URL') and os.environ.get(f'LIVRAPLUS_CLE_{boutique_id}'))


def signaler(boutique_id, type_, produit, delta=0, **extra):
    """type_ : vente | annulation | correction | approvisionnement | inventaire | nouveau."""
    try:
        if not active(boutique_id) or not produit:
            return
        evenement = {'ref': f'{boutique_id}-{uuid.uuid4().hex}', 'type': type_, 'produit': str(produit),
                     'delta': int(delta or 0), 'quand': datetime.now().strftime('%d/%m/%Y %H:%M'), **extra}
        threading.Thread(target=_envoyer, args=(os.environ['LIVRAPLUS_URL'], os.environ[f'LIVRAPLUS_CLE_{boutique_id}'],
                                                [evenement]), daemon=True).start()
    except Exception as e:                      # jamais d'effet sur Ma Boutik
        print(f'LivraPlus : envoi impossible ({e})')


def _envoyer(url, cle, evenements):
    donnees = json.dumps({'evenements': evenements}).encode('utf-8')
    for essai in range(5):
        try:
            requete = urllib.request.Request(url, data=donnees, method='POST', headers={
                'Content-Type': 'application/json', 'Authorization': f'Bearer {cle}'})
            # 1er essai long : LivraPlus peut être en train de se réveiller (hébergement gratuit)
            with urllib.request.urlopen(requete, timeout=60 if essai == 0 else 20) as r:
                if r.status == 200:
                    return
        except urllib.error.HTTPError as e:
            if e.code in (400, 401, 403):
                print(f'LivraPlus : envoi refusé ({e.code}) — vérifiez la clé LIVRAPLUS_CLE_…')
                return
        except Exception:
            pass
        time.sleep(10 * (essai + 1))
    print(f'LivraPlus : mouvement non transmis après plusieurs essais : {evenements}')
