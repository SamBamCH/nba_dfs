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
        self.boom_pct = 0
        self.bust_pct = 0
        self.ownership = 0
        self.id = None
