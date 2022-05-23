import json


class ProblemInstance:
    def __init__(self, problem_file) -> None:
        self.problem_file = problem_file
        self.problem_name = self.__parse_problem_file()

        self.num_stages = None
        self.stages = []

        self.num_machines = []
        self.machines = []

        self.num_jobs = None
        self.jobs = []

        self.precedence_pairs = []

        self.machine_runs = []

        self.processing_times = []
        self.setup_times = []
        self.needs_processing = []

        # Do the actual parsing of the specified problem
        self.__parse_problem()

    def __parse_problem(self):
        with open(self.problem_file) as f:
            instance = json.load(f)

        self.num_jobs = instance["jobs"]
        self.jobs = [j for j in range(1, self.num_jobs + 1)]

        self.num_stages = instance["stages"]
        self.stages = [i for i in range(1, self.num_stages + 1)]

        self.num_machines = instance["machines"]
        for j in range(len(self.num_machines)):
            self.machines.append([k for k in range(1, self.num_machines[j] + 1)])

        self.processing_times = instance["processing_times"]
        self.setup_times = instance["setup_times"]

        for job_processing_times in self.processing_times:
            # [0, 4, 6, 0, 8] -> [(1, 2), (2, 4)]
            precedence = [
                i for (i, ptime) in enumerate(job_processing_times) if ptime > 0
            ]
            precedence = [
                (precedence[i] + 1, precedence[i + 1] + 1)
                for i in range(len(precedence) - 1)
            ]
            self.precedence_pairs.append(precedence)

        for stage in range(self.num_stages):
            runs = []
            for i in range(self.num_machines[stage]):
                runs.append([i for i in range(1, self.num_jobs + 1)])
            self.machine_runs.append(runs)

        for stage in range(0, self.num_stages):
            needs_processing = [
                1 if self.processing_times[job][stage] > 0 else 0
                for job in range(self.num_jobs)
            ]
            self.needs_processing.append(needs_processing)

    def __parse_problem_file(self):
        name = self.problem_file.split("/")[-1]
        name = name.split(".")[0]
        return name


if __name__ == "__main__":
    problem = ProblemInstance("./instances/n20m2-01.json")
    print(problem.problem_name)
