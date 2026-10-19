import pulp

from src.ml.bess.battery import BatteryParams, optimize_day

if __name__ == "__main__":
    print(pulp.listSolvers(onlyAvailable=True))
    params = BatteryParams(power_mw=1, capacity_mwh=1)
    resu = optimize_day([100, 100, 500, 500], params=params)
    print(resu)
