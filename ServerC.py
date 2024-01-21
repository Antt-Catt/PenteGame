# python3 PenteClient.py localhost:12345
import sys
from time import sleep, localtime

from PodSixNet.Server import Server
from PodSixNet.Channel import Channel

from operator import itemgetter

ACTIVE = 1
NOT_PLAYING = 3
ASK = 4

class ClientChannel(Channel):
    """
    This is the server representation of a connected client.
    """
    nickname = "anonymous"
    
    def Close(self):
        self._server.DelPlayer(self)
        self._server.Send_ranking()
        
    def Network_check_nickname(self, data):
        """
        Verfie que le pseudo valide par le joueur n'existe pas
        Si c'est le cas, on fixe son score et on envoie son pseudo, son score, et son etat au tournoi
        Et on met a jour le classement (necessaire si tous les joueurs n'ont pas 1000pts)
        """
        for p in self._server.players:
            if p.nickname == data["nickname"]:
                return
        [p.Send({"action":"nickname_ok","nickname":data["nickname"]})]
        self.nickname = data["nickname"]
        self.score = 1000
        self.state = NOT_PLAYING
        self._server.PrintPlayers()
        self._server.tournament.add_player(self.nickname, self.score, self.state)
        list_sort = sorted(self._server.tournament.ranking, key = itemgetter(1), reverse = True)
        self._server.tournament.ranking = list_sort
        self._server.Send_ranking()
        
    def Network_ask(self, data):
        """
        Lance une fonction du client qui retourne si le joueur est deja dans une procedure de demande ou non
        """
        [p.Send({"action":"is_asking","asking":data["asking"],"asked":data["asked"]}) for p in self._server.players if p.nickname == data["asked"]]
        
    def Network_is_asking(self, data):
        """
        Si le joueur n'est pas dans une procedure de demande, on lui envoie la demande
        """
        if data["is_asking"] == False:
            self._server.ask(data["asking"], data["asked"])
        else:
            [p.Send({"action":"cant_ask"}) for p in self._server.players if p.nickname == data["asking"]]
        
    def Network_answer(self, data):
        """
        Si la reponse est 'oui', on cree un objet de la classe Game pour gerer la partie entre ces deux joueurs
        On met a jour l'etat des joueurs dans le classement pour le transmettre a tous les clients et que le bouton pour defier ne s'affiche pas
        """
        if data["answer"] == 'yes':
            for p in self._server.players:
                if p.nickname == data["asking"]:
                    players = (p.nickname, self.nickname)
            for r in self._server.tournament.ranking:
                if r[0] == players[0]:
                    r[2] = ACTIVE
                elif r[0] == players[1]:
                    r[2] = ACTIVE
            self._server.Send_ranking()
            [p.Send({"action":"start_game", "players":players, "type":"ask"}) for p in self._server.players if p == self or p.nickname == data["asking"]]
            self._server.tournament.start_game(players)
        else:
            [p.Send({"action" : "answer_no"}) for p in self._server.players if p.nickname == data["asking"]]
    
    def Network_click(self,data):
        """
        Recupere les coordonnees du clic de la souris et lance les fonctions necessaire au traitement du clic
        """
        if data["nicknames"] in self._server.tournament.games:
            self._server.tournament.games[data["nicknames"]].check_middleorsquare(data["click"], data["player"])
        else:
            self._server.tournament.games[(data["nicknames"][1], data["nicknames"][0])].check_middleorsquare(data["click"], data["player"])

class MyServer(Server):
    channelClass = ClientChannel
    def __init__(self, mylocaladdr):
        Server.__init__(self, localaddr = mylocaladdr)
        self.players = {}
        self.tournament = Tournament(self)
        print('Server launched')

    def Connected(self, channel, addr):
        self.AddPlayer(channel)
    
    def AddPlayer(self, player):
        print("New Player connected")
        self.players[player] = True
        print(self.players)
 
    def PrintPlayers(self):
        print("players' nicknames :",[p.nickname for p in self.players])
  
    def DelPlayer(self, player):
        print("Deleting Player " + player.nickname + " at "+str(player.addr))
        del self.players[player]
        self.tournament.del_player(player.nickname)
    
    def ask(self, asking, asked):
        """
        Lance la fonction pour comparer les scores des joueurs dans le cadre d'une demande
        """
        for p in self.players:
            if p.nickname == asking:
                p_asking = p
            elif p.nickname == asked:
                p_asked = p
        self.check_score(p_asking, p_asked)
    
    def check_score(self, p_asking, p_asked):
        """
        Si l'ecart est de plus de 300pts, le joueur qui devrait recevoir la demande ne reçoit rien et on lance une fonction du client qui demande pour qu'il puisse faire d'autres demandes
        Si l'ecart est de moins de 200pts, une partie est directement lancee
        Si l'ecart est entre 200 et 300pts, on envoie la demande a l'autre joueur
        """
        diff_score = abs(p_asking.score - p_asked.score)
        if diff_score <= 300:
            if diff_score >= 200:
                [p_asked.Send({"action":"asking", "asking":p_asking.nickname})]
            else:
                for r in self.tournament.ranking:
                    if r[0] == p_asking.nickname:
                        r[2] = ACTIVE
                    elif r[0] == p_asked.nickname:
                        r[2] = ACTIVE
                self.tournament.start_game((p_asking.nickname, p_asked.nickname))
                print('start', p_asking.nickname, p_asked.nickname)
                [p.Send({"action":"start_game", "players":(p_asking.nickname, p_asked.nickname), "type":"auto"}) for p in self.players if p.nickname in (p_asking.nickname, p_asked.nickname)]
            self.Send_ranking()
        else:
            [p_asking.Send({"action":"cant_ask"})]
    
    def Send_if_free(self, pt, player, game):
        """
        Envoie aux deux clients de la meme partie les coordonnees des pierres placees
        """
        for players, games in self.tournament.games.items():
            if games == game:
                [p.Send({"action":"placestone", "coords":pt, "player":player}) for p in self.players if (p.nickname == players[0] or p.nickname == players[1])]

    def Send_if_eat(self, pt, game):
        """
        Envoie aux deux clients de la meme partie les coordonnees des pierres mangees
        """        
        for players, games in self.tournament.games.items():
            if games == game:
                [p.Send({"action":"killstones", "coords":pt, "nb":(game.eatenby1, game.eatenby2)}) for p in self.players if (p.nickname == players[0] or p.nickname == players[1])]

    def Send_if_win(self, winner, looser):
        """
        Envoie aux deux clients de la meme partie qui a gagne/perdu
        """
        [p.Send({"action":"end_game", "winner":winner, "looser":looser}) for p in self.players if (p.nickname == winner or p.nickname == looser)]
                
    def Send_ranking(self):
        """
        Envoie a tous les clients le classement mis a jour
        """
        [p.Send({"action":"ranking", "ranking":self.tournament.ranking}) for p in self.players]
    
    def Launch(self):
        while True:
            self.Pump()
            sleep(0.001)

class Tournament():
    def __init__(self, server):
        self.server = server
        self.ranking = []
        self.games = {}
        
    def add_player(self, nickname, score, state):
        """
        Ajoute un joueur au classement
        """
        self.ranking.append([nickname, score, state])
        print(self.ranking)
    
    def del_player(self, nickname):
        """
        Supprime un joueur du classement
        """
        for p in self.ranking:
            if p[0] == nickname:
                self.ranking.remove(p)
    
    def start_game(self, players):
        """
        Cree une clef (couple des joueurs) dans le dictionnaire des parites, associee a l'objet de la classe Game correspondant
        """
        self.games[players] = Game(players)

    def end_game(self, game):
        """
        Supprime la clef du dictionnaire des parties des joueurs
        Lance la fonction pour envoyer aux clients qui a gagne/perdu
        Lance la fonction qui met a jour les scores
        """
        for p in self.games:
            if self.games[p] == game:
                self.server.Send_if_win(game.winner, game.looser)
                self.maj_score(game.winner, game.looser)
                self.server.Send_ranking()
                del self.games[p]
                return
    
    def maj_score(self, winner, looser):
        """
        Met a jour les scores des joueurs en fonction de qui a gagne/perdu
        Lance la fonction pour mettre a jour le classemement
        """
        for p in self.server.players:
            if p.nickname == winner:
                player_win = p
            elif p.nickname == looser:
                player_loose = p
        plus_minus_score = 100 + (abs(player_win.score - player_loose.score) // 3)
        player_win.score += plus_minus_score
        player_loose.score -= plus_minus_score
        if player_loose.score < 0:
            player_loose.score = 0
        self.maj_ranking(winner, looser, player_win.score, player_loose.score)
        
    def maj_ranking(self, winner, looser, win_score, loose_score):
        """
        Met a jour le classement et l'etat des joueurs
        Trie le tableau du classement par rapport a la variable des scores
        """
        for couple in self.ranking:
            if couple[0] == winner:
                couple[1] = win_score
                couple[2] = NOT_PLAYING
            elif couple[0] == looser:
                couple[1] = loose_score
                couple[2] = NOT_PLAYING
        list_sort = sorted(self.ranking, key = itemgetter(1), reverse = True)
        self.ranking = list_sort
        
class Game():
    """
    #Gere le systeme du jeu, regles du jeu
    """
    def __init__(self, players):
        self.server = s
        self.players = players
        self.list_stones = []
        self.list_stones_players = []
        self.eatenby1 = 0
        self.eatenby2 = 0

    def check_middleorsquare(self, pt, player):
        """
        Regarde si les conditions sont reunies pour placer les pierres du joueur 1 (jouer au milieu au premier tour, et jouer en dehors du carre au second)
        """
        if len(self.list_stones) == 0:
            if pt == (9,9):
                self.check_if_free(pt, player)
                
        elif len(self.list_stones) == 2:
                if not (7 <= pt[0] <= 11 and 7 <= pt[1] <= 11):
                    self.check_if_free(pt, player)
                    
        else:
            self.check_if_free(pt, player)


    def check_if_free(self, pt, player):
        """
        Regarde si le point seleletionne est libre
        """
        if pt not in self.list_stones:
            self.server.Send_if_free(pt, player, self)
            self.list_stones.append(pt)
            self.list_stones_players.append([pt, player])
            self.eat_stones(pt, player)
            self.winninglourson(player)

    def eat_stones(self, pt, player):
        """
        Regarde si des pierres peuvent etre mangees
        """
        (a, b) = pt
        l = self.list_stones_players
        stones_eat = []
        if player == 'Player 1':
            for i in range (-1,2):
                for j in range (-1, 2):
                    (x, y)=(a+i,b+j)
                    for z in range(len(l)):
                        if l[z][0]==(x,y) and l[z][1]=='Player 2':
                            for w in range(len(l)):
                                if l[w][0]==(x+i,y+j) and l[w][1]=='Player 2':
                                    for f in range(len(l)):
                                        if l[f][0]==(x + 2*i,y + 2*j) and l[f][1]=='Player 1':
                                            stones_eat.append((x, y))
                                            stones_eat.append((x+i, y+j))
                                            self.eatenby1 += 1
                                            self.server.Send_if_eat(((x+i, y+j),(x,y)), self)
            for stone in stones_eat:
                self.list_stones_players.remove([stone, 'Player 2'])
                self.list_stones.remove(stone)   
                                         
        elif player == 'Player 2':
            for i in range (-1,2):
                for j in range (-1, 2):
                    (x, y)=(a+i,b+j)
                    for z in range(len(l)):
                        if l[z][0]==(x,y) and l[z][1]=='Player 1':
                            for w in range(len(l)):
                                if l[w][0]==(x+i,y+j) and l[w][1]=='Player 1':
                                    for f in range(len(l)):
                                        if l[f][0]==(x + 2*i,y + 2*j) and l[f][1]=='Player 2':
                                            stones_eat.append((x, y))
                                            stones_eat.append((x+i, y+j))
                                            self.eatenby2 += 1
                                            self.server.Send_if_eat(((x+i, y+j),(x,y)), self)
            for stone in stones_eat:
                self.list_stones_players.remove([stone, 'Player 1'])
                self.list_stones.remove(stone)

    def winninglourson(self, player):
        """
        Regarde si un joueur a gagne
        """
        l = self.list_stones_players
        if self.eatenby1 >= 5:
            self.winner = self.players[0]
            self.looser = self.players[1]
            self.server.tournament.end_game(self)
        if self.eatenby2 >= 5:
            self.winner = self.players[1]
            self.looser = self.players[0]
            self.server.tournament.end_game(self)
        for pt in self.list_stones_players:
            if pt[1] == player:
                (a, b) = pt[0]
                for i in range (-1,2):
                        for j in range (-1,2):
                            nb = 0
                            for stone in l:
                                if stone[0]==(a + i, b + j) and stone[1] == player:
                                    nb += 1
                                elif stone[0]==(a + 2*i, b + 2*j) and stone[1] == player:
                                    nb += 1
                                elif stone[0]==(a + 3*i, b + 3*j) and stone[1] == player:
                                    nb += 1
                                elif stone[0]==(a + 4*i, b + 4*j) and stone[1] == player:
                                    nb += 1
                            if nb == 4 :
                                if player == 'Player 1':
                                    self.winner = self.players[0]
                                    self.looser = self.players[1]
                                    self.server.tournament.end_game(self)
                                else:
                                    self.winner = self.players[1]
                                    self.looser = self.players[0]
                                    self.server.tournament.end_game(self)


# get command line argument of server, port
if len(sys.argv) != 2:
    print("Please use: python3", sys.argv[0], "host:port")
    print("e.g., python3", sys.argv[0], "localhost:31425")
    host, port = "localhost","31425"
else:
    host, port = sys.argv[1].split(":")
s = MyServer((host, int(port)))
s.Launch()