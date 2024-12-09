from pulp import lpSum


class ConstraintManager:
    def __init__(self, site, problem, players, lp_variables, config):
        """
        Initialize ConstraintManager with relevant details.
        :param site: The platform (e.g., 'dk' or 'fd').
        :param problem: The optimization problem instance.
        :param players: List of Player objects.
        :param lp_variables: Dictionary of LP variables.
        :param config: Configuration dictionary with limits and rules.
        """
        self.site = site
        self.problem = problem
        self.players = players
        self.lp_variables = lp_variables
        self.config = config

    def add_salary_constraints(self):
        max_salary = self.config.get("max_salary", 50000 if self.site == "dk" else 60000)
        min_salary = self.config.get("min_salary", 49000 if self.site == "dk" else 59000)

        self.problem += lpSum(
            player.salary * self.lp_variables[player][pos]
            for player in self.players
            for pos in player.position
        ) <= max_salary, "Max Salary"

        self.problem += lpSum(
            player.salary * self.lp_variables[player][pos]
            for player in self.players
            for pos in player.position
        ) >= min_salary, "Min Salary"

    def add_position_constraints(self):
        position_limits = (
            {"PG": 1, "SG": 1, "SF": 1, "PF": 1, "C": 1, "G": 1, "F": 1, "UTIL": 1}
            if self.site == "dk"
            else {"PG": 2, "SG": 2, "SF": 2, "PF": 2, "C": 1}
        )

        for pos, limit in position_limits.items():
            self.problem += lpSum(
                self.lp_variables[player][pos]
                for player in self.players
                if pos in player.position
            ) == limit, f"Position Constraint: {pos} = {limit}"

    def add_team_constraints(self):
        global_team_limit = self.config.get("global_team_limit", None)
        team_limits = self.config.get("team_limits", {})

        for team, limit in team_limits.items():
            self.problem += lpSum(
                self.lp_variables[player][pos]
                for player in self.players
                for pos in player.position
                if player.team == team
            ) <= limit, f"Team Limit: {team} <= {limit}"

        if global_team_limit is not None:
            for team in {player.team for player in self.players}:
                self.problem += lpSum(
                    self.lp_variables[player][pos]
                    for player in self.players
                    for pos in player.position
                    if player.team == team
                ) <= global_team_limit, f"Global Team Limit: {team} <= {global_team_limit}"

    def add_uniqueness_constraints(self, num_uniques, selected_lineups):
        """
        Adds constraints to ensure uniqueness between lineups.
        :param num_uniques: Minimum number of unique players between lineups.
        :param selected_lineups: Already generated lineups to enforce uniqueness against.
        """
        for index, lineup in enumerate(selected_lineups):
            constraint_name = f"Uniqueness_Constraint_{index}"
            self.problem += lpSum(
                self.lp_variables[player][pos]
                for player in lineup
                for pos in player.position
            ) <= len(lineup) - num_uniques, constraint_name


    def add_combination_limits(self):
        combination_limits = self.config.get("combination_limits", {}).get("pairs", [])
        for combo in combination_limits:
            players = combo["players"]
            limit = combo["limit"]

            self.problem += lpSum(
                self.lp_variables[player][pos]
                for player in self.players
                for pos in player.position
                if player.name in players
            ) <= limit, f"Combination Limit: {players} <= {limit}"

    def add_all_constraints(self, selected_lineups=None, num_uniques=None):
        """
        Add all constraints to the problem.
        :param selected_lineups: Existing lineups to enforce uniqueness constraints.
        :param num_uniques: Number of unique players required between lineups.
        """
        self.add_salary_constraints()
        self.add_position_constraints()
        self.add_team_constraints()
        self.add_combination_limits()
        if selected_lineups is not None and num_uniques is not None:
            self.add_uniqueness_constraints(num_uniques, selected_lineups)

