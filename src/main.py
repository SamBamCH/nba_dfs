import os
from data.data_manager import DataManager
from optimizer.optimizer import Optimizer
from lineups.lineups import Lineups
from lineups.lineup_metrics import calculate_exposure
from optimizer.late_swaptimizer import LateSwaptimizer
import pandas as pd

### Entry point of the application

def main():
    pd.set_option('display.max_rows', None)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', None)
    pd.set_option('display.max_colwidth', None)
    # Initialize DataManager for the desired site (e.g., 'dk')
    site = "dk"  # Or "fd" depending on the use case
    process = 'swap'

    data_manager = DataManager(site)

    # Load player data
    try:
        data_manager.load_player_data()
        print("Player data loaded successfully.")
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return

    # Filter out invalid players and capture removed players
    removed_players = [
        player for player in data_manager.players
        if player.ownership in [0, None] or player.id in [0, None]
    ]
    print("Players removed before optimizer initialization:")
    for player in removed_players:
        print(f"Name: {player.name}, Ownership: {player.ownership}, ID: {player.id}")

    players = [
        player for player in data_manager.players
        if player.ownership not in [0, None] and player.id not in [0, None]
    ]

    ### up to this point, the optimization process is the exact same, assuming that the projections, boom_bust, and player_ids are all the same format. 

    # Initialize the optimizer
    if process == 'main':
        num_lineups = 115  # Number of lineups to generate
        num_uniques = 1 # Minimum unique players between lineups
        optimizer = Optimizer(site, players, num_lineups, num_uniques, data_manager.config)

        # Generate lineups
        lineups = optimizer.run()

        # Calculate and display player exposure
        exposure_df = calculate_exposure(lineups.lineups, players)
        print(exposure_df)

        # Export the lineups
        lineups.export_to_csv("data/output/optimal_lineups.csv", site=optimizer.site)

    else :
        data_manager.populate_ids_to_gametime()
        data_manager.load_player_lineups(data_manager.config['late_swap_path'])
        late_swap = LateSwaptimizer(site, players, data_manager.config, data_manager.lineups)
        late_swap.run(output_csv_path="data/output/swapped_lineups.csv")

        # for lineup in data_manager.lineups:
        #     print(lineup)
            ### {'entry_id': '4561617468', 'contest_id': '171700955', 'contest_name': 'DFS Hero - Friday Night Hoops by Momar89', 'PG': 'Vasilije Micic (37001127)', 'SG': 'Brandon Miller (37000948)', 'SF': 'Justin Champagnie (37001198) (LOCKED)', 'PF': 'Miles Bridges (37001074)', 'C': 'Jalen Smith (37001372)', 'G': 'Kevin Porter Jr. (37001233)', 'F': 'Bilal Coulibaly (37001115) (LOCKED)', 'UTIL': 'Nikola Jokic (37000929)', 'PG_is_locked': False, 'SG_is_locked': False, 'SF_is_locked': True, 'PF_is_locked': False, 'C_is_locked': False, 'G_is_locked': False, 'F_is_locked': True, 'UTIL_is_locked': False}


if __name__ == "__main__":
    main()


#TODO: lateswap - test after lock to dial in lock constraint. need to check that the player.gametime matches the new and old format. 
#TODO: modularize logic to be able to use with other sports, with a few additions
    ###wrangle constraints all into the constraints class. 
        ### could have different functions for different sports' constraints? i.e. add_{sport}_constraints()
#TODO: NFL correlated samples for optimization. 
#TODO: set min proj as a tight constraint and optimize for leverage? 
#TODO: can add other factors to the count variables. i.e. variance score * count to make the more variant players penalized more quickly. 
