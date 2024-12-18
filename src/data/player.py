class Player:
    def __init__(self, name, team, position, salary, fpts, minutes):
        self.name = name
        self.team = team
        self.position = position
        self.salary = salary
        self.fpts = fpts
        self.minutes = minutes

        # Additional attributes to be populated
        self.ceiling = 0
        self.stddev = 0
        self.variance_score = self.stddev / self.fpts
        self.boom_pct = 0
        self.bust_pct = 0
        self.ownership = 0
        self.id = None
        self.gametime = None  
        self.std_minutes = self.minutes / 3
        self.std_boom_pct = self.ceiling / 5
        self.std_ownership = self.ownership / 8

    def __str__(self):
        return (
            f"Player(name={self.name}, team={self.team}, position={self.position}, "
            f"salary={self.salary}, fpts={self.fpts}, minutes={self.minutes}, "
            f"gametime={self.gametime}, ceiling={self.ceiling}, stddev={self.stddev}, boom_pct={self.boom_pct}, "
            f"bust_pct={self.bust_pct}, ownership={self.ownership}, id={self.id})"
        )

    def __repr__(self):
        return self.__str__()

