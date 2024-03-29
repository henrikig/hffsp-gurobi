import gurobipy as gp
from gurobipy import GRB
import time
import csv
from problem_parser import ProblemInstance

PROBLEM_NUMBER = 2


def create_model(problem: ProblemInstance, big_m, time_limit=3600):
    m = gp.Model("flowshop")
    m.setParam(GRB.Param.TimeLimit, time_limit)
    m.setParam(GRB.Param.Threads, 20)

    in_tuples = [(i, n) for i in problem.stages for n in problem.jobs]

    # (i, m) - define all possible stage/machine tuples
    im_tuples = [
        (stage, machine)
        for stage in problem.stages
        for machine in problem.machines[stage - 1]
    ]

    # (i, m, r) - define all possible machine run tuples
    imr_tuples = [
        (stage, machine, run)
        for stage, machine in im_tuples
        for run in problem.machine_runs[stage - 1][machine - 1]
    ]

    # (i, m, r, n, j) - define all possible tuples
    imrn_tuples = [
        (stage, machine, run, job)
        for stage, machine, run in imr_tuples
        for job in problem.jobs
    ]

    # Create decision variables
    tn = m.addVars(in_tuples, name="tn")
    tm = m.addVars(imr_tuples, name="tm")
    x = m.addVars(imrn_tuples, vtype=GRB.BINARY, name="x")
    z = m.addVars(imr_tuples, vtype=GRB.BINARY, name="z")
    c_max = m.addVar(name="c_max")

    ###################
    #### Objective ####
    ###################
    m.setObjective(c_max, GRB.MINIMIZE)

    ###################
    ### Constraints ###
    ###################
    BigM = big_m
    # 5.2 - batch and machine run finish time coupling I
    machine_finish_time = m.addConstrs(
        (tm[i, m, r] >= tn[i, n] + BigM * (x[i, m, r, n] - 1))
        for i, m, r, n in imrn_tuples
    )

    # 5.3 - batch and machine run finish time coupling II
    batch_finish_time = m.addConstrs(
        (tm[i, m, r] <= tn[i, n] + BigM * (1 - x[i, m, r, n]))
        for i, m, r, n in imrn_tuples
    )

    # 5.4 - earliest possible start time first machine
    earliest_start = m.addConstrs(
        (
            tm[i, m, 1]
            - problem.processing_times[n - 1][i - 1]
            - problem.setup_times[i - 1][n - 1][n - 1]
            >= BigM * (x[i, m, 1, n] - 1)
        )
        for i in problem.stages
        for m in problem.machines[i - 1]
        for n in problem.jobs
    )

    # 5.5 - Setup on machine can start only after its last run
    earliest_setup = m.addConstrs(
        (
            tm[i, m, r]
            - problem.processing_times[n - 1][i - 1]
            - problem.setup_times[i - 1][n - 1][p - 1]
            - tm[i, m, r - 1]
            >= BigM * (x[i, m, r - 1, p] + x[i, m, r, n] - 2)
        )
        for i, m, r, n in imrn_tuples
        for p in problem.jobs
        if r > 1
    )

    # 5.6 - earliest processing start for preceedence pairs (l, i) in first run
    processing_start_1 = m.addConstrs(
        (
            tm[i, m, 1]
            - problem.processing_times[n - 1][i - 1]
            - problem.setup_times[i - 1][n - 1][n - 1]
            - tm[l, k, u]
            >= BigM * (x[l, k, u, n] + x[i, m, 1, n] - 2)
        )
        for n in problem.jobs
        for l, i in problem.precedence_pairs[n - 1]
        for m in problem.machines[i - 1]
        for k in problem.machines[l - 1]
        for u in problem.machine_runs[l - 1][k - 1]
    )

    # 5.7 - earliest processing start for preceedence pairs (l, i) in run r > 1
    processing_start_2 = m.addConstrs(
        (
            tm[i, m, r]
            - problem.processing_times[n - 1][i - 1]
            - problem.setup_times[i - 1][n - 1][p - 1]
            - tm[l, k, u]
            >= BigM * (x[i, m, r - 1, p] + x[l, k, u, n] + x[i, m, r, n] - 3)
        )
        for n in problem.jobs
        for l, i in problem.precedence_pairs[n - 1]
        for m in problem.machines[i - 1]
        for r in problem.machine_runs[i - 1][m - 1]
        for k in problem.machines[l - 1]
        for u in problem.machine_runs[l - 1][k - 1]
        for p in problem.jobs
        if r > 1
    )

    #############################
    # Add machine run squeezing?
    #############################
    # 5.9 - Machine run variables coupling II
    runs_coupling_2 = m.addConstrs(
        (z[i, m, r] == gp.quicksum(x[i, m, r, n] for n in problem.jobs))
        for i, m, r in imr_tuples
    )

    # 5.10 - machine runs squeezing
    squeeze_runs = m.addConstrs(
        (z[i, m, r + 1] <= z[i, m, r]) for i, m, r in imr_tuples if r < problem.num_jobs
    )

    # 5.8 - All jobs processed in all necessary stages
    necessary_processing = m.addConstrs(
        (
            gp.quicksum(
                x[i, m, r, n]
                for m in problem.machines[i - 1]
                for r in problem.machine_runs[i - 1][m - 1]
            )
            == problem.needs_processing[i - 1][n - 1]
        )
        for i, n in in_tuples
    )

    # 5.9
    c_max_constraint = m.addConstrs(
        (c_max >= tn[i, n]) for i in problem.stages for n in problem.jobs
    )

    return m


# Define callback function to store improvements in objective and bound
def data_cb(model, where):
    if where == gp.GRB.Callback.MIP:
        cur_obj = round(model.cbGet(gp.GRB.Callback.MIP_OBJBST), 2)
        cur_bd = round(model.cbGet(gp.GRB.Callback.MIP_OBJBND), 2)

        # Did objective value or best bound change?
        if model._obj != cur_obj or model._bd != cur_bd:
            model._obj = cur_obj
            model._bd = cur_bd
            model._data.append([round(time.time() - model._start, 2), cur_obj, cur_bd])


def run_model(m, problem: ProblemInstance, time_limit, data_cb=data_cb):
    m.update()
    m._obj = None
    m._bd = None
    m._data = [["Time", "Objective", "Best Bound"]]
    m._start = round(time.time(), 2)

    m.optimize(callback=data_cb)

    c_max = m.getVarByName("c_max")
    gap = m.getAttr(GRB.Attr.MIPGap)
    print("CMAX:", c_max.x)
    print("GAP:", gap)

    # Write final objective and gap
    m._data.append([round(time_limit, 2), c_max.x, gap])

    # Write bound data to file
    with open(f"./gaps/{problem.problem_name}.csv", "w") as f:
        writer = csv.writer(f)
        writer.writerows(m._data)

    output = []

    output.append(f"GAP: {gap}\n")

    for v in m.getVars():
        if v.Xn > 1e-6:
            line = f"{v.varName}: {round(v.Xn, 3)}"
            output.append(line + "\n")

    with open(f"solutions/{problem.problem_name}.txt", "w") as f:
        f.writelines(output)


def get_problems():
    return [
        dict(problem="instances/n20m2-01.json", big_m=1200, time_limit=145000),
        dict(problem="instances/n20m2-02.json", big_m=1200, time_limit=145000),
        dict(problem="instances/n20m2-03.json", big_m=1200, time_limit=145000),
        dict(problem="instances/n20m2-04.json", big_m=1200, time_limit=145000),
        dict(problem="instances/n20m2-05.json", big_m=1000, time_limit=145000),
    ]


if __name__ == "__main__":
    config = get_problems()[PROBLEM_NUMBER]

    problem = ProblemInstance(config["problem"])
    time_limit = config["time_limit"]
    model = create_model(problem, big_m=config["big_m"], time_limit=time_limit)
    run_model(model, problem, time_limit)
