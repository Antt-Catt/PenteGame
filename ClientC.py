import sys
from time import sleep
from sys import stdin, exit

from PodSixNet.Connection import connection, ConnectionListener

from tkinter import *
from tkinter import messagebox

from functools import partial

DEAD = -1
INITIAL = 0
ACTIVE = 1
WAIT = 2
NOT_PLAYING = 3
ASK = 4

NB_COLONNES = 20
NB_LIGNES = 20
CANV_X = 600
CANV_Y = CANV_X
DIAM = (CANV_X // NB_COLONNES)

COLOR = {"Player 1":"black", "Player 2":'white'}
STATE_GRID = {1:"en jeu", 2:"en jeu", 3:"en attente de match", 4:"en attente de match"}
TEXT = {1:"A toi de jouer !", 2:"Au tour de l'adversaire...", }

class Client(ConnectionListener):
    """
    Cette classe va permettre de recuperer toutes les informations importantes envoyees par le serveur
    """
    def __init__(self, host, port, window):
        self.window = window
        self.Connect((host, port))
        self.state = INITIAL
        print("Client started")
        print("Ctrl-C to exit")

    def Network_connected(self, data):
        print("You are now connected to the server")
    
    def Loop(self):
        connection.Pump()
        self.Pump()

    def quit(self):
        self.window.destroy()
        self.state = DEAD
    
    def Network_nickname_ok(self, data):
        """
        Est lancee lorsque le pseudo choisi par le joueur n'est pas utilise
        Supprime le champ de saisie, le texte et le bouton permettant de valider la saisie
        Et initialise l'etat du joueur sur NOT_PLAYING
        """
        self.nickname = data["nickname"]
        self.window.label_nickname.forget()
        self.window.entry_nickname.forget()
        self.window.button_nickname.forget()
        self.state = NOT_PLAYING
   
    def Network_ranking(self,data):
        """
        Reçois le classement des joueurs et le met a jour sur l'affiche de tous les clients
        """
        self.window.ranking = data["ranking"]
        self.window.show_ranking()
        
    def Network_asking(self, data):
        """
        Passe l'etat du joueur recevant la demande en ASK (necessaire pour ne pas recevoir plusieurs demandes en meme temps)
        Et lui affiche une fenetre avec le nom du joueur qui le defie et la possibilite d'accepter ou non
        Envoie la reponse au serveur
        """
        self.state = ASK
        resultat = messagebox.askquestion(None,
                                          str(data["asking"]) + ' veut jouer contre vous. Accepter ?')
        if resultat == 'yes':
            self.Send({"action" : "answer", "asking" : data["asking"],"answer":"yes"})
        else:
            self.state = NOT_PLAYING
            self.Send({"action" : "answer", "asking" : data["asking"],"answer":"no"})
    
    def Network_is_asking(self, data):
        """
        Verifie si un joueur est deja entrain de demander ou de recevoir une demande
        Si oui, il ne se passe rien
        Si non, la demande est bien envoyee
        """
        if self.state != ASK:
            self.Send({"action":"is_asking","is_asking":False,"asking":data["asking"],"asked":data["asked"]})
        else:
            self.Send({"action":"is_asking","is_asking":True,"asking":data["asking"],"asked":data["asked"]})
    
    def Network_cant_ask(self, data):
        """
        Si le joueur qui reçoit la demande est dans l'etat ASK, met a jour l'etat du joueur qui demande sur NOT_PLAYING pour permettre de refaire une demande
        OU si l'ecart entre les deux joueurs est de plus de 300pts
        """
        self.state = NOT_PLAYING
        
    def Network_answer_no(self, data):
        """
        Si le joueur defie refuse, on affiche une fenetre d'info pour le joueur qui demande pour lui donner la reponse
        Et lui permettre de refaire une demande
        """
        self.state = NOT_PLAYING
        messagebox.showinfo(None, 'Le Joueur a refuse ¯\_(ツ)_/¯')
    
    def Network_start_game(self, data):
        """
        Une partie est lancee et on attribue a chaque joueur un etat ACTIVE ou WAIT, pour jouer a tout de rôle
        Si c'est une demande automatique (moins de 200pts d'ecart), on previent le joueur receveur que quelqu'un l'a defie
        Sinon, on previent le joueur qui a fait la demande que l'autre joueur a accepte
        Puis on lance la fenetre de jeu pour chaque joueur
        """
        if data["players"][0] == self.nickname:
            self.state = ACTIVE
            self.opponent = data["players"][1]
            if data["type"] == "ask":
                messagebox.showinfo(None, data["players"][1] + " a accepte !")
        else:
            self.state = WAIT
            self.opponent = data["players"][0]
            if data["type"] == "auto":
                messagebox.showinfo(None, data["players"][0] + " a lance une partie contre vous !")
        self.game_window = GameWindow()
        
    def Network_placestone(self, data):
        """
        Lance une fonction pour afficher les pierres aux coordonnees reçues par le serveur
        On met a jour l'etat des joueurs pour jouer a tour de rôle
        On change le texte du label pour que les joueurs sachent si c'est a eux de jouer
        """
        self.game_window.place_stone(data["coords"], data["player"])
        if self.state == ACTIVE:
            self.state = WAIT
        elif self.state == WAIT:
            self.state = ACTIVE
        self.game_window.label_player['text'] = TEXT[self.state]

    def Network_killstones(self, data):
        """
        Lance une fonction pour supprimer les pierres aux coordonees reçues par le serveur
        On met a jour l'affiche du nombre de paires mangees par chaque joueur
        """
        if self.game_window.player == 'Player 1':
            self.game_window.label_nb_eat_self['text'] = "Paires mangees : " + str(data["nb"][0])
            self.game_window.label_nb_eat_opp['text'] = "Paires mangees par l'adversaire :" + str(data["nb"][1])
        else:
            self.game_window.label_nb_eat_self['text'] = "Paires mangees : " + str(data["nb"][1])
            self.game_window.label_nb_eat_opp['text'] = "Paires mangees par l'adversaire :" + str(data["nb"][0])
        self.game_window.kill_stones(data["coords"])
        
    def Network_end_game(self, data):
        """
        Met a jour l'etat des joueurs pour qu'ils puissent refaire une demande et en recevoir
        Ferme la fenetre de jeu des joueurs
        Affiche une fenetre d'info en fonction de qui est gagnant/perdant
        """
        self.state = NOT_PLAYING
        self.game_window.game.destroy()
        self.game_window.game = None
        if self.nickname == data["winner"]:
            messagebox.showinfo(None, 'Bravo ! Tu as gagne !')
        else:
            messagebox.showinfo(None, 'Dommage, tu as perdu...')
        
    def Network_error(self, data):
        print('error:', data['error'][1])
        connection.Close()
    
    def Network_disconnected(self, data):
        print('Server disconnected')
        exit()
    
#########################################################

class RankingWindow(Tk):
    """
    Permet de saisir un pseudo au debut
    Gere l'affichage du classement avec la possibilite de defier un joueur
    """
    def __init__(self, host, port):
        Tk.__init__(self)
        self.client = Client(host, int(port), self)
        self.frame_ranking = Frame(self)
        self.frame_ranking.pack()
        quit_but=Button(self,text='Quitter',command = self.client.quit)
        quit_but.pack(side=BOTTOM)

        #Widgets servant a la saisie du pseudo
        self.label_nickname = Label(self, text = 'Ecris ton pseudo')
        self.label_nickname.pack()
        self.entry_nickname = Entry(self)
        self.entry_nickname.pack()
        self.button_nickname = Button(self, text = 'Valider', command = self.send_nickname)
        self.button_nickname.pack()

    def send_nickname(self):
        """
        Envoie le pseudo au serveur apres appuie sur le bouton
        """
        self.client.Send({"action":"check_nickname", "nickname":self.entry_nickname.get()})
    
    def show_ranking(self):
        """
        Mets a jour l'affichage du classement
        Et met un bouton permettant de defier devant chaque joueur ne jouant pas
        """
        for widget in self.frame_ranking.winfo_children():
            widget.destroy()
        
        rank = Label(self.frame_ranking, text = 'Rang')
        rank.grid(row = 0, column = 0)
        nickname = Label(self.frame_ranking, text = 'Pseudo')
        nickname.grid(row = 0, column = 1)
        score = Label(self.frame_ranking, text = 'Score')
        score.grid(row = 0, column = 2)
        state = Label(self.frame_ranking, text = 'Etat')
        state.grid(row = 0, column = 3)     
        
        for i in range(len(self.ranking)):
            rank = Label(self.frame_ranking, text = i + 1)
            rank.grid(row = i + 1, column = 0)
            nickname = Label(self.frame_ranking, text = self.ranking[i][0])
            nickname.grid(row = i + 1, column = 1)
            score = Label(self.frame_ranking, text = self.ranking[i][1])
            score.grid(row = i + 1, column = 2)
            state = Label(self.frame_ranking, text = STATE_GRID[self.ranking[i][2]])
            state.grid(row = i + 1, column = 3)
            if self.ranking[i][2] == NOT_PLAYING and self.ranking[i][0] != self.client.nickname:
                button_ask = Button(self.frame_ranking, text = "Defier " + str(self.ranking[i][0]) + " !", command = partial(self.ask, i))
                button_ask.grid(row = i + 1, column = 4)
    
    def ask(self, i):
        """
        Permet d'empecher qu'un joueur ne se defie soit meme ou pendant qu'il joue
        """
        if self.client.nickname != self.ranking[i][0] and self.client.state == NOT_PLAYING:
            self.client.state = ASK
            self.client.Send({"action":"ask","asking":self.client.nickname,"asked":self.ranking[i][0]})
        
    def myMainLoop(self):
        while self.client.state != DEAD:   
            self.update()
            self.client.Loop()
            sleep(0.001)
        exit()    
    
class GameWindow(Tk):
    """
    Gere l'affichage au cours du deroulement de la partie
    Envoie au serveur les coordonnees des clics 
    """
    def __init__(self):
        self.game = Toplevel(ranking_window)
        self.window = ranking_window

        #Tailles grilles
        self.nb_colonnes = NB_COLONNES
        self.nb_lignes = NB_LIGNES
        self.canv_x = CANV_X
        self.canv_y = CANV_Y
        
        #Variable donnant le joueur
        if self.window.client.state == ACTIVE:
            self.player = 'Player 1'
        elif self.window.client.state == WAIT:
            self.player = 'Player 2'
        
        #Frame et Canvas
        self.canvas = Canvas(self.game, width = self.canv_x, height = self.canv_y, bg = 'green')
        self.canvas.pack(side = LEFT)
        self.affichage = Frame(self.game)
        self.affichage.pack(side = RIGHT)
        
        #Boutons et labels
        self.label_player = Label(self.affichage, text = TEXT[self.window.client.state])
        self.label_player.pack()
        self.label_nb_eat_self = Label(self.affichage, text = 'Paires mangees : 0')
        self.label_nb_eat_self.pack()
        self.label_nb_eat_opp = Label(self.affichage, text = "Paires mangees par l'adversaire : 0")
        self.label_nb_eat_opp.pack()
        
        # Creation de la grille de points
        self.make_grid()
        
        # Detecter clic souris sur les points
        self.canvas.bind('<ButtonPress-1>', self.mouse_click)


    def make_grid(self):
        """
        Affiche la grille, et le carre rouge necessaire pour le deuxieme tour du premier joueur
        Place les pierres invisibles sur chaque intersection
        """
        for i in range(self.nb_colonnes):
            self.zepoint = Point(i, 0)
            self.canvas.create_line(self.zepoint.coord_x, self.zepoint.coord_y + DIAM, self.zepoint.coord_x, self.canv_y - DIAM, fill = "white")
        for j in range(self.nb_lignes):
            self.zepoint2 = Point(0, j)
            self.canvas.create_line(self.zepoint2.coord_x + DIAM, self.zepoint2.coord_y, self.canv_x - DIAM, self.zepoint2.coord_y, fill = "white")
        for i in range(1, self.nb_colonnes):
            for j in range(1, self.nb_lignes):
                point_jeu = Point(i, j)
                nouveau_point = self.canvas.create_oval(point_jeu.coord_x - (DIAM // 2), point_jeu.coord_y - (DIAM // 2), point_jeu.coord_x + (DIAM // 2), point_jeu.coord_y + (DIAM // 2), state='hidden', fill = None)
                point_jeu.ligne += 1
            point_jeu.colonne += 1
        for i in range(2):
            redline = Point(7 + i * 6, 7 + i * 6)
            if i == 0:
                self.canvas.create_line(redline.coord_x + (DIAM // 2), redline.coord_y + (DIAM // 2), redline.coord_x + (DIAM // 2) + 5 * DIAM, redline.coord_y + (DIAM // 2), fill = "red")
                self.canvas.create_line(redline.coord_x + (DIAM // 2), redline.coord_y + (DIAM // 2), redline.coord_x + (DIAM // 2), redline.coord_y + (DIAM // 2) + 5 * DIAM, fill = "red")
            else:
                self.canvas.create_line(redline.coord_x - (DIAM // 2), redline.coord_y - (DIAM // 2), redline.coord_x - (DIAM // 2) - 5 * DIAM, redline.coord_y - (DIAM // 2), fill = "red")
                self.canvas.create_line(redline.coord_x - (DIAM // 2), redline.coord_y - (DIAM // 2), redline.coord_x - (DIAM // 2), redline.coord_y - (DIAM // 2) - 5 * DIAM, fill = "red")

    def conversion_back_to_column_line(self, x, y):
        """
        Convertit les coordonnees xy d'un clic en coordonnees colonnes/lignes
        """
        for i in range(self.nb_colonnes - 1):
            for j in range(self.nb_lignes - 1):
                if (DIAM * (i + 1/2) <= x < DIAM * (i + 3/2)) and (DIAM * (j + 1/2) <= y < DIAM * (j + 3/2)):
                    return(i, j)

    def mouse_click(self, click):
        """
        Recupere les coords du clic de la souris
        """
        if self.window.client.state == ACTIVE:
            coords_click = self.conversion_back_to_column_line(click.x, click.y)
            if coords_click != None:
                self.window.client.Send({"action":"click", "click":coords_click, "player":self.player, "nicknames":(self.window.client.nickname, self.window.client.opponent)})

    def place_stone(self, pt, player):
        """
        Change l'etat de la pierre placee pour qu'on puise la voir avec la couleur du bon joueur
        """
        color = COLOR[player]
        (c,l) = pt
        self.canvas.itemconfigure(41 + 19 * c + l, state = 'normal', fill = color, outline = color)

    def kill_stones(self, pt):
        """
        Change l'etat des pierres mangees pour qu'on ne puisse plus les voir
        """
        (c1, l1) = pt[0]
        (c2, l2) = pt[1]
        self.canvas.itemconfigure(41 + 19*c1 + l1, state = 'hidden')
        self.canvas.itemconfigure(41 + 19*c2 + l2, state = 'hidden')
    
    def myMainLoop(self):
        while self.client.state != DEAD:   
            self.update()
            self.client.Loop()
            sleep(0.001)
        exit()   

class Point:
    """
    Representation d'un point du canvas avec des coordonnees allant de 0 a 18
    Et avec les coordonnes xy associees
    """
    def __init__(self, colonne, ligne):
        self.colonne = colonne
        self.ligne = ligne
        self.coord_x = colonne * DIAM
        self.coord_y = ligne * DIAM

# get command line argument of client, port
if len(sys.argv) != 2:
    print("Please use: python3", sys.argv[0], "host:port")
    print("e.g., python3", sys.argv[0], "localhost:31425")
    host, port = "localhost", "31425"
else:
    host, port = sys.argv[1].split(":")
ranking_window = RankingWindow(host, port)
ranking_window.myMainLoop()