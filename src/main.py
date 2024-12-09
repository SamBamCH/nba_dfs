from data.data_manager import DataManager
from optimizer.optimizer import Optimizer
from lineups.lineup import LineupPool, LineupMetrics
import os

def main():
    # Load config and setup

    site = "dk"
    num_lineups = 150
    num_uniques = 1
    randomness = 15
    base_dir = os.path.abspath(os.path.dirname(__file__))  # Current directory of main.py
    config_path = os.path.join(base_dir, f"../data/config/{site}_config.json")  # Navigate back to data/config/config.json


    # Load data and rules from JSON config
    data_manager = DataManager(config_path, site)
    data_manager.load_player_data()

    # Initialize optimizer
    optimizer = Optimizer(
        site=site,
        num_lineups=num_lineups,
        num_uniques=num_uniques,
        randomness_amount=randomness,
        config=data_manager.config,
    )
    optimizer.set_players(data_manager.players)

    # Optimize and generate lineups
    lineup_pool = optimizer.optimize()

    # Metrics calculations
    ownership_sums = lineup_pool.calculate_all_ownership_sums()
    ownership_threshold = LineupMetrics.calculate_ownership_threshold(ownership_sums)
    filtered_lineups = LineupMetrics.filter_lineups_by_metric(
        lineup_pool, lambda lineup: lineup.calculate_ownership_sum(), ownership_threshold
    )

    # Output results
    print(f"Generated {len(filtered_lineups)} filtered lineups.")
    LineupPool.save_to_csv(filtered_lineups, "output/filtered_lineups.csv")


if __name__ == "__main__":
    main()
