from pulp import lpSum


class ConstraintManager:
    def __init__(self, site, problem, players, lp_variables, config):
        self.site = site
        self.problem = problem
        self.players = players
        self.lp_variables = lp_variables
        self.config = config

    def add_salary_constraints(self):
        max_salary = 50000 if self.site == "dk" else 60000
        min_salary = self.config.get("min_lineup_salary") if self.site == "dk" else 59000

        self.problem += lpSum(
            player.salary * self.lp_variables[(player, position)]
            for player in self.players
            for position in player.position
        ) <= max_salary, "Max_Salary"

        self.problem += lpSum(
            player.salary * self.lp_variables[(player, position)]
            for player in self.players
            for position in player.position
        ) >= min_salary, "Min_Salary"

    def add_position_constraints(self):
        # Hard-coded position constraints
        if self.site == "dk":
            position_limits = {
                "PG": 1, "SG": 1, "SF": 1, "PF": 1, "C": 1, "G": 1, "F": 1, "UTIL": 1
            }
        else:  # Assuming "fd"
            position_limits = {
                "PG": 2, "SG": 2, "SF": 2, "PF": 2, "C": 1
            }

        for pos, limit in position_limits.items():
            eligible = [(player, pos) for player in self.players if pos in player.position]
            self.problem += lpSum(self.lp_variables[key] for key in eligible) == limit, f"Position_{pos}"

    def add_matchup_constraints(self):
        matchup_limits = self.config.get("matchup_limits", {})
        for matchup, limit in matchup_limits.items():
            eligible = [(player, position) for player in self.players if player.matchup == matchup]
            self.problem += lpSum(self.lp_variables[key] for key in eligible) <= limit, f"Matchup_{matchup}"

    def add_team_constraints(self):
        team_limits = self.config.get("team_limits", {})
        for team, limit in team_limits.items():
            eligible = [(player, position) for player in self.players if player.team == team]
            self.problem += lpSum(self.lp_variables[key] for key in eligible) <= limit, f"Team_{team}"

    def add_global_team_limit(self):
        global_limit = self.config.get("global_team_limit")
        if global_limit:
            for team in set(player.team for player in self.players):
                eligible = [
                    (player, pos) for player in self.players for pos in player.position if player.team == team
                ]
                self.problem += lpSum(self.lp_variables[key] for key in eligible) <= global_limit, f"Global_Team_{team}"


    def exclude_exact_lineup(self, lineup, lineup_index):
        """
        Add a constraint to exclude the exact lineup from being selected again.
        :param lineup: List of (player, position) tuples in the lineup.
        :param lineup_index: The index of the lineup being excluded.
        """
        constraint_name = f"Exclude_Lineup_{lineup_index}"
        self.problem += (
            lpSum(self.lp_variables[(player, position)] for player, position in lineup) <= len(lineup) - 1,
            constraint_name
        )


    def add_single_player_constraints(self):
        for player in self.players:
            self.problem += lpSum(
                self.lp_variables[(player, position)] for position in player.position
            ) <= 1, f"Single_Use_{player.name}"

    def add_static_constraints(self):
        '''
        This is used for static constraints for the site you are optimizing for (i.e. draftkings, nba). 
        '''
        self.add_salary_constraints()
        self.add_position_constraints()
        self.add_single_player_constraints()

    def add_lineup_pool_constraints(self, selected_lineups, num_uniques):
        '''
        This is used for looping constraints(i.e. exposure caps, uniqueness, etc.)
        '''
        pass

    def add_optional_constraints(self, max_ownership=None, min_fpts=None):
        """
        Add optional constraints such as ownership maximum and FPTS minimum.
        :param max_ownership: Maximum allowable cumulative ownership.
        :param min_fpts: Minimum required cumulative fpts.
        """
        if max_ownership is not None:
            lineup_ownership = lpSum(
                player.ownership * self.lp_variables[(player, position)]
                for player in self.players
                for position in player.position
            )
            self.problem += lineup_ownership <= max_ownership, "Max_Ownership"

        if min_fpts is not None:
            lineup_fpts = lpSum(
                player.fpts * self.lp_variables[(player, position)]
                for player in self.players
                for position in player.position
            )
            self.problem += lineup_fpts >= min_fpts, "Min_FPTS"

        self.add_global_team_limit()
        self.add_matchup_constraints()
        self.add_team_constraints()
