from datetime import datetime
import pytz

class Player:
    def __init__(self, name, team, id, gametime, salary):
        self.id = id
        self.name = name
        self.team = team
        self.position = []
        self.salary = salary
        self.fpts = 0
        self.minutes = 0

        # Additional attributes to be populated
        self.ceiling = 0
        self.stddev = 0
        self.variance_score = 0
        self.boom_pct = 0
        self.bust_pct = 0
        self.ownership = 0
        self.gametime = gametime  
        self.std_minutes = 0
        self.std_boom_pct = 0
        self.std_ownership = 0
        self.eastern = pytz.timezone("US/Eastern")

    def __str__(self):
        return (
            f"Player(name={self.name}, team={self.team}, position={self.position}, "
            f"salary={self.salary}, fpts={self.fpts}, minutes={self.minutes}, "
            f"gametime={self.gametime}, ceiling={self.ceiling}, stddev={self.stddev}, boom_pct={self.boom_pct}, "
            f"bust_pct={self.bust_pct}, ownership={self.ownership}, id={self.id})"
        )
    
    def is_game_locked(self):
        """
        Check if the current time is past the player's lock time in Eastern Time.
        :return: True if the game is locked, otherwise False.
        """
        # Get the current time in Central Time
        central_time = pytz.timezone("US/Central").localize(datetime.now())
        
        # Convert Central Time to Eastern Time
        eastern_time = central_time.astimezone(pytz.timezone("US/Eastern"))
        
        return eastern_time >= self.gametime



    def __repr__(self):
        return self.__str__()

