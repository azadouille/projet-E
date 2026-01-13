import http.server
import socketserver
from urllib.parse import urlparse, parse_qs, unquote
import json
import io
import os
import sqlite3
import matplotlib.pyplot as plt
import matplotlib.dates as pltd
from datetime import datetime

# Configuration
PORT = 8080
DB_NAME = "hydro_mesure.sqlite"


class RequestHandler(http.server.SimpleHTTPRequestHandler):
  """"Classe dérivée pour traiter les requêtes entrantes du serveur"""

  # sous-répertoire racine des documents statiques
  static_dir = 'client'
  
  def __init__(self, *args, **kwargs):
    """Surcharge du constructeur pour imposer 'client' comme sous répertoire racine"""

    super().__init__(*args, directory=self.static_dir, **kwargs)
    

  def do_GET(self):
    """Traiter les requêtes GET (surcharge la méthode héritée)"""

    # On récupère les éléments du chemin d'accès et les paramètres éventuels
    self.init_params()

    # le chemin d'accès commence par /regions
    if self.path_info[0] == 'regions':
      self.send_regions()

    # le chemin d'accès commence par /ponctualite
    elif self.path_info[0] == 'ponctualite':
      self.send_ponctualite()

    # sinon appel de la méthode parente...
    else:
      super().do_GET()


  def send_regions(self):
    """Envoi de la réponse HTTP avec la liste des régions sous forme de liste json"""
 
    # création du curseur (la connexion a été créée par le programme principal)
    c = conn.cursor()
    
    # récupération de la liste des régions et coordonnées (import de regions.csv)
    c.execute("SELECT nom,lat,lon FROM 'regions'")
    r = c.fetchall()
    body = json.dumps([{'nom':n, 'lat':lat, 'lon': lon} 
                       for (n,lat,lon) in r])    

    # envoi de la réponse
    headers = [('Content-Type','application/json')];
    self.send(body,headers)


  def send_ponctualite(self):
    """Envoi de la réponse HTTP en json donnant l'URL du graphique de ponctualite"""

    # création du curseur (la connexion a été créée par le programme principal)
    c = conn.cursor()

    # si pas de paramètre => erreur pas de région
    if len(self.path_info) <= 1 or self.path_info[1] == '' :
        # Région non spécifiée -> erreur 400 Bad Request
        print ('Erreur pas de nom')
        self.send_error(400,'Nom de région manquant')
        return None
    else:
        # on récupère le nom de la région dans le 1er paramètre
        region = self.path_info[1]
        # On teste que la région demandée existe bien
        c.execute("SELECT nom FROM 'regions' WHERE nom=?",(region,))
        r = c.fetchone()
        if r == None:
            # Région non trouvée -> erreur 404 Not Found
            print ('Erreur nom')
            self.send_error(404,f'{region} : nom de région inconnu')    
            return None
    
    # Test de la présence du fichier dans le cache
    URL_graphique = f'/courbes/ponctualite_{region}.png'
    fichier = self.static_dir + f'{URL_graphique}'
    if not os.path.exists(fichier):  # pas dans le cache ? => générer la courbe
        print('creer_graphique : ', region)
        self.creer_graphique (region, fichier)
    
    # réponse au format JSON
    body = json.dumps({
            'title': f'Régularité TER {region}', \
            'img': f'{URL_graphique}' \
             })
    
    # envoi de la réponse
    headers = [('Content-Type','application/json')];
    self.send(body,headers)


  def creer_graphique(self, region, nom_fichier):
    """Générer un graphique de ponctualite et l'enregistrer dans le cache"""
    
    # création du curseur (la connexion a été créée par le programme principal)
    c = conn.cursor()

    # configuration du tracé
    plt.figure(figsize=(18,6))
    plt.ylim(75,100)
    plt.grid(which='major', color='#888888', linestyle='-')
    plt.grid(which='minor',axis='x', color='#888888', linestyle=':')
    
    ax = plt.subplot(111)
    ax.xaxis.set_major_locator(pltd.YearLocator())
    ax.xaxis.set_minor_locator(pltd.MonthLocator())
    ax.xaxis.set_major_formatter(pltd.DateFormatter('%B %Y'))
    ax.xaxis.set_tick_params(labelsize=10)
    
    # interrogation de la base de données pour les données de la région
    c.execute("SELECT Date,`Tauxderégularité` FROM 'regularite-mensuelle-ter' WHERE Région=? ORDER BY Date", (region,))
    r = c.fetchall()

    # axe des abscisses : recupération de la date et transformation en date au format python
    x = [dt.date(int(d[:4]),int(d[5:]),1) for (d,t) in r if not (t == '' or t == None)]
    # axe des ordonnées : récupération du taux de régularité
    y = [float(t) for (d,t) in r if not (t == '' or  t==None)]

    # tracé de la courbe
    plt.plot(x,y,linewidth=1, linestyle='-', color='blue', label=region)
    
    # légendes
    plt.legend(loc='lower right')
    plt.title(f'Régularité des TER (en %) pour la Région {region}',fontsize=16)
    plt.ylabel('% de régularité')
    plt.xlabel('Date')
    
    # enregistrement de la courbe dans un fichier PNG
    plt.savefig(nom_fichier)
    plt.close()
    

  def send(self, body, headers=[]):
    """Envoyer la réponse HTTP au client avec le corps et les en-têtes fournis
    
    Paramètres:
      body: corps de la réponse
      headers: liste de tuples d'en-têtes Cf. HTTP (par défaut : liste vide)
    """
    # on encode la chaine de caractères à envoyer
    encoded = bytes(body, 'UTF-8')

    # on envoie la ligne de statut
    self.send_response(200)

    # on envoie les lignes d'entête et la ligne vide
    [self.send_header(*t) for t in headers]
    self.send_header('Content-Length', int(len(encoded)))
    self.end_headers()

    # on envoie le corps de la réponse
    self.wfile.write(encoded)


  def init_params(self):
    """Analyse la requête HTTP pour aider à son traitement
    
    Retourne : 
        dans self.path_info la liste des éléments de self.path
        dans self.params la liste des paramètres extraits de la query string ou du body
    """
    # analyse du path
    info = urlparse(self.path)
    self.path_info = [unquote(v) for v in info.path.split('/')[1:]]
    self.query_string = info.query
    
    # récupération des paramètres dans la query string
    self.params = parse_qs(info.query)

    # récupération du corps et des paramètres (2 encodages traités)
    length = self.headers.get('Content-Length')
    ctype = self.headers.get('Content-Type')
    if length:
      self.body = str(self.rfile.read(int(length)),'utf-8')
      if ctype == 'application/x-www-form-urlencoded' : 
        self.params = parse_qs(self.body)
      elif ctype == 'application/json' :
        self.params = json.loads(self.body)
    else:
      self.body = ''

    # traces
    print('init_params|path =', self.path_info)
    print('init_params|body =', length, ctype, self.body)
    print('init_params|params =', self.params)

# Programme principal
if __name__ == '__main__' :
    # Ouverture d'une connexion avec la base de données après vérification de sa présence
    if not os.path.exists(BD_name):
        raise FileNotFoundError(f"BD {BD_name} non trouvée !")
    conn = sqlite3.connect(BD_name)
    
    # Instanciation et lancement du serveur
    httpd = socketserver.TCPServer(("", port_serveur), RequestHandler)
    print("Serveur lancé sur port : ", port_serveur)
    httpd.serve_forever()

