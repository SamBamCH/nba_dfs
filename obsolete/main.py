from windows_inhibitor import *
from nba_late_swaptimizer import *
import sys
from nba_optimizer import *
from windows_inhibitor import *
from nba_late_swaptimizer import *
from nba_with_ownership import *
from ownership import *
from get_optimals_new import *
from calculate_ownership_limit import *

def main(arguments):
    if len(arguments) < 3:
        print('Incorrect usage. Please see `README.md` for proper usage.')
        exit()

    site = arguments[1]
    process = arguments[2]

    if process == 'opto':
        # Parse arguments
        num_lineups = int(arguments[3])
        num_uniques = int(arguments[4])

        # Ownership Calculation Run with static adjusted randomness
        optimizer = ownership_optimizer(site, 150, num_uniques)
        static_randomness_for_ownership_calc = 0.10  # Static randomness value for the first run
        optimizer.optimize(100, adjusted_randomness=static_randomness_for_ownership_calc)
        ownership_sums = optimizer.calculate_ownership_sums(optimizer.lineups)
        ownership_percentile = 90  # Specify the percentile here
        ownership_sum_threshold = optimizer.find_ownership_threshold(ownership_sums, ownership_percentile)

        # Print the calculated ownership sum threshold
        print(f"Calculated Ownership Sum Threshold ({ownership_percentile} percentile): {ownership_sum_threshold}")

        # Run the actual optimization with the ownership sum threshold
        final_optimizer = nba_optimizer(site, num_lineups, num_uniques)
        final_optimizer.optimize(num_lineups, ownership_sum_threshold=ownership_sum_threshold)
        final_optimizer.output()

    elif process == 'swap':
        num_uniques = arguments[3]
        swapto = NBA_Late_Swaptimizer(site, num_uniques)
        swapto.swaptimize()
        swapto.output()




if __name__ == "__main__":
    main(sys.argv)