class Lineup:
    def __init__(self, players):
        self.players = players

    def calculate_ownership_sum(self):
        return sum(player.ownership for player in self.players)

    def calculate_salary_sum(self):
        return sum(player.salary for player in self.players)

    def calculate_fpts_sum(self):
        return sum(player.fpts for player in self.players)


class LineupPool:
    def __init__(self, lineups):
        self.lineups = lineups

    def calculate_all_ownership_sums(self):
        return [lineup.calculate_ownership_sum() for lineup in self.lineups]


class LineupMetrics:
    @staticmethod
    def calculate_ownership_threshold(ownership_sums, percentile=90):
        import numpy as np
        return np.percentile(ownership_sums, percentile)

    @staticmethod
    def filter_lineups_by_metric(lineup_pool, metric_func, threshold):
        return [
            lineup for lineup in lineup_pool.lineups if metric_func(lineup) <= threshold
        ]
