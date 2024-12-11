import os
from data.data_manager import DataManager
from optimizer.optimizer import Optimizer
from lineups.lineups import Lineups
from lineups.lineup_metrics import calculate_exposure
import pandas as pd


def main():
    # Initialize DataManager for the desired site (e.g., 'dk')
    site = "dk"  # Or "fd" depending on the use case
    data_manager = DataManager(site)

    pd.set_option('display.max_rows', None)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', None)
    pd.set_option('display.max_colwidth', None)

    # Load player data
    try:
        data_manager.load_player_data()
        print("Player data loaded successfully.")
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return

    # Filter out invalid players
    players = [
        player for player in data_manager.players
        if player.ownership not in [0, None] and player.id not in [0, None]
    ]

    # Initialize the optimizer
    num_lineups = 150  # Number of lineups to generate
    num_uniques = 3  # Minimum unique players between lineups
    optimizer = Optimizer(site, players, num_lineups, num_uniques, data_manager.config)

    # Generate lineups
    lineups = optimizer.run()

    # Calculate and display player exposure
    exposure_df = calculate_exposure(lineups.lineups, players)
    print(exposure_df)

    # Export the lineups
    lineups.export_to_csv("data/output/optimal_lineups.csv", site=optimizer.site)


if __name__ == "__main__":
    main()
