"""Transition vers LivraPlus : chaque mouvement de stock d'une boutique est aussi envoyé à LivraPlus,
qui ajuste le stock du même article (même nom).

Ne s'active que pour les boutiques configurées : une ligne dans l'onglet « LIVRAPLUS » du classeur
Google (colonnes : boutique_id | cle | url facultative), ou bien les variables d'environnement
LIVRAPLUS_CLE_<id> (+ LIVRAPLUS_URL). Sans configuration, rien n'est envoyé.
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


URL_PAR_DEFAUT = 'https://cataligne.medilogicghp.com/api/synchro/maboutik'
_cache = {'quand': 0, 'config': {}}
_classeur = None       # donné par app_multi au démarrage (brancher)


def brancher(classeur):
    global _classeur
    _classeur = classeur


def _config():
    """{boutique_id: (url, cle)} lu dans l'onglet LIVRAPLUS (relu toutes les 5 minutes)."""
    if time.time() - _cache['quand'] < 300:
        return _cache['config']
    config = {}
    try:
        if _classeur is not None:
            for ligne in _classeur.worksheet('LIVRAPLUS').get_all_values()[1:]:
                if len(ligne) > 1 and ligne[0].strip() and ligne[1].strip():
                    url = ligne[2].strip() if len(ligne) > 2 and ligne[2].strip() else URL_PAR_DEFAUT
                    config[ligne[0].strip()] = (url, ligne[1].strip())
    except Exception:
        pass                       # onglet absent : aucune boutique liée
    _cache.update(quand=time.time(), config=config)
    return config


def _cible(boutique_id):
    cle = os.environ.get(f'LIVRAPLUS_CLE_{boutique_id}')
    if cle:
        return os.environ.get('LIVRAPLUS_URL') or URL_PAR_DEFAUT, cle
    return _config().get(str(boutique_id))


def active(boutique_id):
    return bool(_cible(boutique_id))


def signaler(boutique_id, type_, produit, delta=0, **extra):
    """type_ : vente | annulation | correction | approvisionnement | inventaire | nouveau."""
    try:
        cible = _cible(boutique_id)
        if not cible or not produit:
            return
        evenement = {'ref': f'{boutique_id}-{uuid.uuid4().hex}', 'type': type_, 'produit': str(produit),
                     'delta': int(delta or 0), 'quand': datetime.now().strftime('%d/%m/%Y %H:%M'), **extra}
        threading.Thread(target=_envoyer, args=(cible[0], cible[1], [evenement]), daemon=True).start()
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
