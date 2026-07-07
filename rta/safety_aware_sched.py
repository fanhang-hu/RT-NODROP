from __future__ import division

import argparse
import copy
from datetime import datetime
import os
import random
import socket
import sys
import time
from functools import partial


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
SCHEDCAT_ROOT = os.path.join(PROJECT_ROOT, 'lib', 'schedcat')

TaskSystem = None
mean = None
get_framework = None
_event_residence_time_nodrop = None
generate_task_set = None
setup_tests = None


EXPERIMENT_UTILIZATION = 'utilization'
EXPERIMENT_SYSCALL_COUNT = 'syscall_count'
EXPERIMENT_CPU_COUNT = 'cpu_count'


def load_runtime_dependencies():
    global TaskSystem
    global mean
    global get_framework
    global _event_residence_time_nodrop
    global generate_task_set
    global setup_tests

    if generate_task_set is not None:
        return

    for path in (PROJECT_ROOT, SCHEDCAT_ROOT, CURRENT_DIR):
        if path not in sys.path:
            sys.path.insert(0, path)

    try:
        from schedcat.model.tasks import TaskSystem as schedcat_task_system
        from toolbox.stats import mean as stats_mean
        from params import get_framework as load_framework
        from rta_nodrop import _event_residence_time_nodrop as load_residence
        from util_syscall_cpu import generate_task_set as load_taskset
        from util_syscall_cpu import setup_tests as load_tests
    except ImportError as error:
        raise SystemExit(
            'Missing runtime dependency: {0}\n'
            'Initialize the SchedCAT dependency first, then run again:\n'
            '  git submodule update --init --recursive\n'
            '  source setpath.sh\n'
            '  cd lib/schedcat && make && cd ../../'.format(error))

    TaskSystem = schedcat_task_system
    mean = stats_mean
    get_framework = load_framework
    _event_residence_time_nodrop = load_residence
    generate_task_set = load_taskset
    setup_tests = load_tests


class SafetyAwareConfig(object):
    def __init__(self):
        self.experiment = EXPERIMENT_UTILIZATION
        self.output = None
        self.seed = 20260707

        self.num_task = 10
        self.samples = 1000
        self.periods = '10-100'
        self.num_cpus = 1
        self.util = 0.75
        self.syscall_count = 10
        self.consumer_period_factor = 1.0

        self.util_num_min = 0.5
        self.util_num_max = 1.0
        self.step = 0.01

        self.syscall_count_min = 5
        self.syscall_count_max = 15
        self.syscall_count_step = 1

        self.cpu_num_min = 1
        self.cpu_num_max = 10
        self.cpu_num_step = 1

        self.var = None
        self.make_taskset = None


def float_range(start, stop, step):
    values = []
    current = float(start)
    stop = float(stop)
    step = float(step)
    while current <= stop + 1e-9:
        values.append(round(current, 10))
        current += step
    return values


def build_configs(base_conf, experiment):
    if experiment == EXPERIMENT_UTILIZATION:
        values = float_range(base_conf.util_num_min,
                             base_conf.util_num_max,
                             base_conf.step)
        attr = 'util'
    elif experiment == EXPERIMENT_SYSCALL_COUNT:
        values = range(int(base_conf.syscall_count_min),
                       int(base_conf.syscall_count_max) + 1,
                       int(base_conf.syscall_count_step))
        attr = 'syscall_count'
    elif experiment == EXPERIMENT_CPU_COUNT:
        values = range(int(base_conf.cpu_num_min),
                       int(base_conf.cpu_num_max) + 1,
                       int(base_conf.cpu_num_step))
        attr = 'num_cpus'
    else:
        raise ValueError('Unknown experiment: {0}'.format(experiment))

    confs = []
    for index, value in enumerate(values):
        conf = copy.copy(base_conf)
        conf.experiment = experiment
        conf.var = value
        conf.seed_offset = index * 100000
        setattr(conf, attr, value)
        conf.make_taskset = partial(generate_task_set, conf)
        confs.append(conf)
    return confs


def iter_partitions(taskset):
    partitions = {}
    for task in taskset:
        partitions.setdefault(task.partition, []).append(task)
    for tasks in partitions.values():
        yield TaskSystem(tasks)


def run_tests(confs, tests):
    nodrop = get_framework('nodrop_0')
    nodrop_index = next(i for i, (name, _) in enumerate(tests)
                         if name.startswith('#rta_nodrop'))

    for conf in confs:
        samples = [[] for _ in tests]
        residence_times = []

        for sample in range(int(conf.samples)):
            if sample % 100 == 0:
                print('Finished {0} samples for variable {1}'.format(
                    sample, conf.var))

            random.seed(int(conf.seed) + int(conf.seed_offset) + sample)
            taskset = conf.make_taskset()
            results = []

            for index, (_, test_fn) in enumerate(tests):
                ok, _ = test_fn(taskset, None, conf)
                samples[index].append(ok)
                results.append(ok)

            if results[nodrop_index] == 1:
                collect_nodrop_residence_times(taskset, nodrop,
                                               residence_times)

        yield [conf.var] + [mean(column) for column in samples] + \
              summarize_residence_times(residence_times)


def collect_nodrop_residence_times(taskset, framework, residence_times):
    for partition in iter_partitions(taskset):
        users = [task for task in partition if not task.is_consumer]
        users.sort(key=lambda task: task.preemption_level)
        for index, task in enumerate(users):
            higher = users[:index]
            residence_time = _event_residence_time_nodrop(
                task, higher, framework.delta, framework.alpha, framework.beta)
            if not is_invalid_number(residence_time):
                residence_times.append(residence_time)


def is_invalid_number(value):
    return value == float('inf') or value != value


def summarize_residence_times(values):
    if not values:
        return [0, 0, 0]
    return [max(values), min(values), mean(values)]


def experiment_header(experiment, tests):
    if experiment == EXPERIMENT_UTILIZATION:
        axis = 'UTILIZATION'
    elif experiment == EXPERIMENT_SYSCALL_COUNT:
        axis = 'SYSCALL_COUNT'
    else:
        axis = 'CPU_COUNT'
    return [axis] + [name for name, _ in tests] + [
        'RES_MAX_ND', 'RES_MIN_ND', 'RES_MEAN_ND']


def output_path(output_dir, experiment):
    return os.path.join(output_dir, '{0}.txt'.format(experiment))


def write_result(output_file, data, header, conf, start_time, completed_time):
    output_dir = os.path.dirname(output_file)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    with open(output_file, 'w') as output:
        output.write('############### CONFIGURATION ###############\n')
        for key in sorted(conf.__dict__):
            if key == 'make_taskset':
                continue
            output.write('# {0:<20}: {1}\n'.format(key, getattr(conf, key)))

        output.write('################ ENVIRONMENT ################\n')
        output.write('# CWD................: {0}\n'.format(os.getcwd()))
        output.write('# Host...............: {0}\n'.format(socket.gethostname()))
        output.write('# Python.............: {0}\n'.format(sys.version.split()[0]))

        output.write('#################### DATA ###################\n')
        output.write('# ' + ' '.join(['{0:>18}'.format(item)
                                for item in header]) + '\n')
        for row in data:
            output.write(' '.join(['{0:>18}'.format(str(item))
                                   for item in row]) + '\n')

        output.write('#################### RUN ####################\n')
        output.write('# Started............: {0}\n'.format(
            datetime.fromtimestamp(start_time).strftime('%Y-%m-%d %H:%M:%S')))
        output.write('# Completed..........: {0}\n'.format(
            datetime.fromtimestamp(completed_time).strftime('%Y-%m-%d %H:%M:%S')))
        output.write('# Duration...........: {0:.2f} seconds\n'.format(
            completed_time - start_time))


def run_experiment(conf, experiment, output_dir):
    load_runtime_dependencies()
    tests = setup_tests()
    confs = build_configs(conf, experiment)
    start_time = time.time()
    data = list(run_tests(confs, tests))
    completed_time = time.time()
    output_file = output_path(output_dir, experiment)
    write_result(output_file, data, experiment_header(experiment, tests),
                 confs[0], start_time, completed_time)
    return output_file


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description='Reproduce the safety-aware task scheduling experiment.')
    parser.add_argument('--experiment', default=EXPERIMENT_UTILIZATION,
                        choices=[EXPERIMENT_UTILIZATION,
                                 EXPERIMENT_SYSCALL_COUNT,
                                 EXPERIMENT_CPU_COUNT,
                                 'all'])
    parser.add_argument('--output-dir', default='output/safety_aware_sched')
    parser.add_argument('--seed', type=int, default=20260707)
    parser.add_argument('--samples', type=int, default=1000)
    parser.add_argument('--num-task', type=int, default=10)
    parser.add_argument('--num-cpus', type=int, default=1)
    parser.add_argument('--util', type=float, default=0.75)
    parser.add_argument('--syscall-count', type=int, default=10)
    parser.add_argument('--util-min', type=float, default=0.5)
    parser.add_argument('--util-max', type=float, default=1.0)
    parser.add_argument('--util-step', type=float, default=0.01)
    parser.add_argument('--syscall-min', type=int, default=5)
    parser.add_argument('--syscall-max', type=int, default=15)
    parser.add_argument('--syscall-step', type=int, default=1)
    parser.add_argument('--cpu-min', type=int, default=1)
    parser.add_argument('--cpu-max', type=int, default=10)
    parser.add_argument('--cpu-step', type=int, default=1)
    return parser.parse_args(argv)


def config_from_args(args):
    conf = SafetyAwareConfig()
    conf.seed = args.seed
    conf.samples = args.samples
    conf.num_task = args.num_task
    conf.num_cpus = args.num_cpus
    conf.util = args.util
    conf.syscall_count = args.syscall_count
    conf.util_num_min = args.util_min
    conf.util_num_max = args.util_max
    conf.step = args.util_step
    conf.syscall_count_min = args.syscall_min
    conf.syscall_count_max = args.syscall_max
    conf.syscall_count_step = args.syscall_step
    conf.cpu_num_min = args.cpu_min
    conf.cpu_num_max = args.cpu_max
    conf.cpu_num_step = args.cpu_step
    return conf


def main(argv=None):
    args = parse_args(argv or sys.argv[1:])
    conf = config_from_args(args)

    if args.experiment == 'all':
        experiments = [EXPERIMENT_UTILIZATION,
                       EXPERIMENT_SYSCALL_COUNT,
                       EXPERIMENT_CPU_COUNT]
    else:
        experiments = [args.experiment]

    for experiment in experiments:
        output_file = run_experiment(conf, experiment, args.output_dir)
        print('Wrote {0}'.format(output_file))


if __name__ == '__main__':
    main()
