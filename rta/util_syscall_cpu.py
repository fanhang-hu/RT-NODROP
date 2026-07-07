import copy
import math
import random
from functools import partial
from toolbox.stats import mean
from schedcat.model.tasks import SporadicTask, TaskSystem
import schedcat.generator.generator_emstada as emstada
from toolbox.io import write_data, Config
from rta import bound_response_times
from rta_omnilog import bound_response_times_omnilog
from rta_ellipsis import bound_response_times_ellipsis, _event_residence_time_ellipsis
from rta_nodrop import bound_response_times_nodrop, _event_residence_time_nodrop
from datetime import datetime
import os
import socket
import sys
import time
from params import AuditFramework, FRAMEWORKS, get_framework
from math import ceil

# Helper to redirect stdout to a file
class RedirectStdoutToFile(object):
    def __init__(self, file_path):
        self.file_path = file_path
        self.original_stdout = sys.stdout

    def __enter__(self):
        self.file = open(self.file_path, 'w')
        sys.stdout = self.file

    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stdout = self.original_stdout
        self.file.close()

# Helper for printing/writing task sets
def print_task_set(ts):
    """Print detailed information of the task set."""
    print("Task Set Details:")
    print("{:<5} {:<10} {:<5} {:<10} {:<20} {:<10} {:<15}".format('ID', 'Type', 'CPU', 'Period', 'Preemption Level', 'Cost', 'Syscall count'))
    print("-" * 80)
    for task in ts:
        task_type = "Consumer" if getattr(task, 'is_consumer', False) else "User"
        preemption_level = getattr(task, 'preemption_level', '')
        print("{:<5} {:<10} {:<5} {:<10} {:<20} {:<10} {:<15}".format(
            task.id,
            task_type,
            task.partition,
            task.period,
            preemption_level,
            task.cost,
            task.syscall_count
        ))
    print("\n")

# Original utility functions and test setup
PERIODS = { 
    '10-100': (10, 100),
}

def generate_task_set(conf):
    ts = TaskSystem()
    
    for cpuid in range(int(conf.num_cpus)):
        ntask = int(conf.num_task)
        u = float(conf.util)
        user_tasks = emstada.gen_taskset(PERIODS[conf.periods], 'unif', ntask, u, 0.01)
        for user_task in user_tasks:
            user_task.partition = cpuid
            # user_task.syscall_count = conf.syscall_count if hasattr(conf, 'syscall_count') else 2000
            user_task.syscall_count = conf.syscall_count * (float(user_task.cost) / 1000)
            user_task.is_consumer = False
            ts.append(user_task)
    
    user_ts = TaskSystem([t for t in ts if not t.is_consumer])
    user_ts.sort_by_period()
    for i, t in enumerate(user_ts):
        t.preemption_level = float(i)
    
    for user_task in user_ts:
        consumer = SporadicTask(0,
            conf.consumer_period_factor * user_task.period,
            conf.consumer_period_factor * user_task.period)
        # consumer.syscall_count = conf.consumer_syscall_count
        consumer.syscall_count = user_task.syscall_count
        consumer.is_consumer = True
        consumer.partition = user_task.partition
        consumer.preemption_level = user_task.preemption_level - 0.5
        ts.append(consumer)
    
    ts.sort(key=lambda t: t.preemption_level)
    ts.assign_ids()
    
    # add check
    # print_task_set(ts)

    return ts

def iter_partitions_ts(taskset):
    partitions = {}
    for t in taskset:
        if t.partition not in partitions:
            partitions[t.partition] = []
        partitions[t.partition].append(t)
    for p in partitions.itervalues():
        yield TaskSystem(p)

def rta_test(taskset, oh, conf, include_consumers=False):
    ts = copy.deepcopy(taskset)
    if not include_consumers:
        ts = TaskSystem([t for t in ts if not t.is_consumer])
    framework = get_framework('rta')
    for t in ts:
        t.cost = framework.calculate_execution_time(t)
    
    for partition in iter_partitions_ts(ts):
        if not bound_response_times(1, partition):
            return (0, 0)
    
    return (1, 0)

def rta_omnilog_0_test(taskset, oh, conf, include_consumers=False):
    ts = copy.deepcopy(taskset)
    if not include_consumers:
        ts = TaskSystem([t for t in ts if not t.is_consumer])
    framework = get_framework('omnilog_0')
    
    consumer_cpu = 0
    non_consumer_tasks = [t for t in ts if not t.is_consumer]
    if non_consumer_tasks:
        q_sigma = min(t.period for t in non_consumer_tasks)
    else:
        return (0, 0)
    
    consumer = SporadicTask(0, q_sigma, q_sigma)
    consumer.is_consumer = True
    consumer.preemption_level = -1
    consumer.partition = consumer_cpu
    ts.append(consumer)

    # test
    # print("omnilog\n")
    # print_task_set(ts)
    
    for t in ts:
        t.cost = framework.calculate_execution_time(t)
    
    # for partition in iter_partitions_ts(ts):
    #     part_ts = TaskSystem(partition)
    #     if not bound_response_times_omnilog(1, part_ts, framework.delta, framework.beta):
    #         return (0, 0)
    
    # if not bound_response_times_omnilog(conf.num_cpus, ts, framework.delta, framework.beta) :
    #     return (0, 0)

    if not bound_response_times_omnilog(consumer_cpu, ts, framework.delta, framework.beta) :
        return (0, 0)

    return (1, 0)

def rta_omnilog_1_test(taskset, oh, conf, include_consumers=False):
    ts = copy.deepcopy(taskset)
    if not include_consumers:
        ts = TaskSystem([t for t in ts if not t.is_consumer])
    framework = get_framework('omnilog_1')
    
    consumer_cpu = 0
    non_consumer_tasks = [t for t in ts if not t.is_consumer]
    if non_consumer_tasks:
        q_sigma = min(t.period for t in non_consumer_tasks)
    else:
        return (0, 0)
    
    consumer = SporadicTask(0, q_sigma, q_sigma)
    consumer.is_consumer = True
    consumer.preemption_level = -1
    consumer.partition = consumer_cpu
    ts.append(consumer)
    
    for t in ts:
        t.cost = framework.calculate_execution_time(t)
    
    # for partition in iter_partitions_ts(ts):
    #     part_ts = TaskSystem(partition)
    #     if not bound_response_times_omnilog(1, part_ts, framework.delta, framework.beta):
    #         return (0, 0)
    
    # if not bound_response_times_omnilog(conf.num_cpus, ts, framework.delta, framework.beta) :
    #     return (0, 0)

    if not bound_response_times_omnilog(consumer_cpu, ts, framework.delta, framework.beta) :
        return (0, 0)

    return (1, 0)

# def rta_audit_test(taskset, oh, conf, include_consumers=False):
#     ts = copy.deepcopy(taskset)
#     if not include_consumers:
#         ts = TaskSystem([t for t in ts if not t.is_consumer])
#     framework = get_framework('audit')
    
#     consumer_cpu = 0
#     non_consumer_tasks = [t for t in ts if not t.is_consumer]
#     if non_consumer_tasks:
#         q_sigma = max(t.period for t in non_consumer_tasks)
#     else:
#         return (0, 0)
    
#     consumer = SporadicTask(0, q_sigma, q_sigma)
#     consumer.is_consumer = True
#     max_preemption_level = max(t.preemption_level for t in non_consumer_tasks) if non_consumer_tasks else 0
#     consumer.preemption_level = max_preemption_level + 1
#     consumer.partition = consumer_cpu
#     ts.append(consumer)
    
#     for t in ts:
#         t.cost = framework.calculate_execution_time(t)
    
#     if not bound_response_times_ellipsis(consumer_cpu, ts, framework.delta, framework.beta) :
#         return (0, 0)

#     return (1, 0)

def rta_audit_test(taskset, oh, conf, include_consumers=False):
    ts = copy.deepcopy(taskset)
    if not include_consumers:
        ts = TaskSystem([t for t in ts if not t.is_consumer])
    framework = get_framework('audit')
    
    consumer_cpu = 0
    non_consumer_tasks = [t for t in ts if not t.is_consumer]
    if non_consumer_tasks:
        q_sigma = max(t.period for t in non_consumer_tasks)
    else:
        return (0, 0)
    
    consumer = SporadicTask(0, q_sigma, q_sigma)
    consumer.is_consumer = True

    highest_priority_task = max(non_consumer_tasks, key=lambda t: t.preemption_level) if non_consumer_tasks else None
    max_preemption_level = highest_priority_task.preemption_level if highest_priority_task else 0
    consumer.syscall_count = highest_priority_task.syscall_count if highest_priority_task else 0

    consumer.preemption_level = max_preemption_level + 1
    consumer.partition = consumer_cpu
    ts.append(consumer)
    
    for t in ts:
        t.cost = framework.calculate_execution_time(t)

    if not bound_response_times_ellipsis(consumer_cpu, taskset, framework.delta, framework.beta) :
        return (0, 0)

    return (1, 0)

def rta_ellipsis_test(taskset, oh, conf, include_consumers=False):
    ts = copy.deepcopy(taskset)
    if not include_consumers:
        ts = TaskSystem([t for t in ts if not t.is_consumer])
    framework = get_framework('ellipsis')
    
    consumer_cpu = 0
    non_consumer_tasks = [t for t in ts if not t.is_consumer]
    if non_consumer_tasks:
        q_sigma = max(t.period for t in non_consumer_tasks)
    else:
        # return (0, 0, 0)
        return (0, 0)
    
    consumer = SporadicTask(0, q_sigma, q_sigma)
    consumer.is_consumer = True
    
    # max_preemption_level = max(t.preemption_level for t in non_consumer_tasks) if non_consumer_tasks else 0
    highest_priority_task = max(non_consumer_tasks, key=lambda t: t.preemption_level) if non_consumer_tasks else None
    max_preemption_level = highest_priority_task.preemption_level if highest_priority_task else 0
    consumer.syscall_count = highest_priority_task.syscall_count if highest_priority_task else 0

    consumer.preemption_level = max_preemption_level + 1
    consumer.partition = consumer_cpu
    ts.append(consumer)

    # print("ellipsis\n")
    # print_task_set(ts)
    
    for t in ts:
        t.cost = framework.calculate_execution_time(t)
    
    # ellipsis_fw = get_framework('ellipsis')
    # delta_el, alpha_el, beta_el = ellipsis_fw.delta, ellipsis_fw.alpha, ellipsis_fw.beta
    # residence_time = _event_residence_time_ellipsis(ts, non_consumer_tasks, delta_el, alpha_el, beta_el)
    # print("residence_time {}:" .format(residence_time))

    # residence_time_file = 'output/result0921/residence_times.txt'
    # residence_time_dir = os.path.dirname(residence_time_file)
    # if not os.path.exists(residence_time_dir):
    #     os.makedirs(residence_time_dir)

    # with open(residence_time_file, 'a') as f:
    #     # f.write(f"{residence_time}")
    #     f.write(str(residence_time) + "\n")

    if not bound_response_times_ellipsis(consumer_cpu, taskset, framework.delta, framework.beta) :
        # return (0, 0, residence_time)
        return (0, 0)

    # return (1, 0, residence_time)
    return (1, 0)

def rta_omnilog_2_test(taskset, oh, conf, include_consumers=False):
    ts = copy.deepcopy(taskset)
    if not include_consumers:
        ts = TaskSystem([t for t in ts if not t.is_consumer])
    framework = get_framework('ellipsis')
    
    consumer_cpu = 0
    non_consumer_tasks = [t for t in ts if not t.is_consumer]
    if non_consumer_tasks:
        q_sigma = max(t.period for t in non_consumer_tasks)
    else:
        return (0, 0)
    
    consumer = SporadicTask(0, q_sigma, q_sigma)
    consumer.is_consumer = True
    consumer.preemption_level = -1
    consumer.partition = consumer_cpu
    ts.append(consumer)

    # test
    # print("omnilog\n")
    # print_task_set(ts)
    
    for t in ts:
        t.cost = framework.calculate_execution_time(t)
    
    # for partition in iter_partitions_ts(ts):
    #     part_ts = TaskSystem(partition)
    #     if not bound_response_times_omnilog(1, part_ts, framework.delta, framework.beta):
    #         return (0, 0)
    
    # if not bound_response_times_omnilog(conf.num_cpus, ts, framework.delta, framework.beta) :
    #     return (0, 0)

    if not bound_response_times_omnilog(consumer_cpu, ts, framework.delta, framework.beta) :
        return (0, 0)

    return (1, 0)

def rta_ellipsis_delta0_test(taskset, oh, conf, include_consumers=False):
    ts = copy.deepcopy(taskset)
    if not include_consumers:
        ts = TaskSystem([t for t in ts if not t.is_consumer])
    framework = get_framework('ellipsis_delta0')
    
    consumer_cpu = 0
    non_consumer_tasks = [t for t in ts if not t.is_consumer]
    if non_consumer_tasks:
        q_sigma = max(t.period for t in non_consumer_tasks)
    else:
        return (0, 0)
    
    consumer = SporadicTask(0, q_sigma, q_sigma)
    consumer.is_consumer = True
    max_preemption_level = max(t.preemption_level for t in non_consumer_tasks) if non_consumer_tasks else 0
    consumer.preemption_level = max_preemption_level + 1
    consumer.partition = consumer_cpu
    ts.append(consumer)
    
    for t in ts:
        t.cost = framework.calculate_execution_time(t)
    
    if not bound_response_times_ellipsis(consumer_cpu, ts, framework.delta, framework.beta) :
        return (0, 0)

    return (1, 0)

def rta_ellipsis_delta_audit_test(taskset, oh, conf, include_consumers=False):
    ts = copy.deepcopy(taskset)
    if not include_consumers:
        ts = TaskSystem([t for t in ts if not t.is_consumer])
    framework = get_framework('ellipsis_delta_audit')
    
    consumer_cpu = 0
    non_consumer_tasks = [t for t in ts if not t.is_consumer]
    if non_consumer_tasks:
        q_sigma = max(t.period for t in non_consumer_tasks)
    else:
        return (0, 0)
    
    consumer = SporadicTask(0, q_sigma, q_sigma)
    consumer.is_consumer = True
    max_preemption_level = max(t.preemption_level for t in non_consumer_tasks) if non_consumer_tasks else 0
    consumer.preemption_level = max_preemption_level + 1
    consumer.partition = consumer_cpu
    ts.append(consumer)
    
    for t in ts:
        t.cost = framework.calculate_execution_time(t)
    
    if not bound_response_times_ellipsis(consumer_cpu, ts, framework.delta, framework.beta) :
        return (0, 0)

    return (1, 0)

def rta_nodrop_0_test(taskset, oh, conf, include_consumers=True):
    ts = copy.deepcopy(taskset)
    if not include_consumers:
        ts = TaskSystem([t for t in ts if not t.is_consumer])
    framework = get_framework('nodrop_0')
    
    for partition in iter_partitions_ts(ts):
        part_ts = TaskSystem(partition)
        for t in part_ts:
            t.cost = framework.calculate_execution_time(t)
        if not bound_response_times_nodrop(part_ts, framework.delta, framework.alpha, framework.beta):
            return (0, 0)
    
    return (1, 0)

# def rta_nodrop_1_test(taskset, oh, conf, include_consumers=True):
#     ts = copy.deepcopy(taskset)
#     if not include_consumers:
#         ts = TaskSystem([t for t in ts if not t.is_consumer])
#     framework = get_framework('nodrop_1')
    
#     for partition in iter_partitions_ts(ts):
#         part_ts = TaskSystem(partition)
#         for t in part_ts:
#             t.cost = framework.calculate_execution_time(t)
#         if not bound_response_times_nodrop(part_ts, framework.delta, framework.alpha, framework.beta):
#             return (0, 0)
    
#     return (1, 0)

# def rta_nodrop_2_test(taskset, oh, conf, include_consumers=True):
#     ts = copy.deepcopy(taskset)
#     if not include_consumers:
#         ts = TaskSystem([t for t in ts if not t.is_consumer])
#     framework = get_framework('nodrop_2')
    
#     for partition in iter_partitions_ts(ts):
#         part_ts = TaskSystem(partition)
#         for t in part_ts:
#             t.cost = framework.calculate_execution_time(t)
#         if not bound_response_times_nodrop(part_ts, framework.delta, framework.alpha, framework.beta):
#             return (0, 0)
    
#     return (1, 0)

# def rta_nodrop_3_test(taskset, oh, conf, include_consumers=True):
#     ts = copy.deepcopy(taskset)
#     if not include_consumers:
#         ts = TaskSystem([t for t in ts if not t.is_consumer])
#     framework = get_framework('nodrop_3')
    
#     for partition in iter_partitions_ts(ts):
#         part_ts = TaskSystem(partition)
#         for t in part_ts:
#             t.cost = framework.calculate_execution_time(t)
#         if not bound_response_times_nodrop(part_ts, framework.delta, framework.alpha, framework.beta):
#             return (0, 0)
    
#     return (1, 0)

def setup_tests():
    return [
        ("#rta", partial(rta_test, include_consumers=False)),
        ("#rta_omnilog_delta=3.42", partial(rta_omnilog_0_test, include_consumers=False)),
        ("#rta_omnilog_delta=0.31", partial(rta_omnilog_1_test, include_consumers=False)),
        ("#rta_omnilog_delta=3.52", partial(rta_omnilog_2_test, include_consumers=False)),
        ("#rta_audit", partial(rta_audit_test, include_consumers=False)),
        ("#rta_ellipsis", partial(rta_ellipsis_test, include_consumers=False)),
        # nodrop = rta_ellipsis_delta0
        # ("#rta_ellipsis_delta0", partial(rta_ellipsis_delta0_test, include_consumers=False)),
        # ("#rta_ellipsis_delta_audit", partial(rta_ellipsis_delta_audit_test, include_consumers=False)),
        ("#rta_nodrop", partial(rta_nodrop_0_test, include_consumers=True)),
        # ("#rta_nodrop_1", partial(rta_nodrop_1_test, include_consumers=True)),
        # ("#rta_nodrop_2", partial(rta_nodrop_2_test, include_consumers=True)),
        # ("#rta_nodrop_3", partial(rta_nodrop_3_test, include_consumers=True)),
    ]

# def run_tests(confs, tests, oh):
#     for conf in confs:
#         samples = [[] for _ in tests]
#         for sample in range(int(conf.samples)):
#             if sample % 100 == 0:
#                 print("Finished {} samples for variable {}".format(sample, conf.var))
#             ts = conf.make_taskset()
#             for i, test in enumerate(tests):
#                 result = test[1](ts, oh, conf)
#                 # add print
#                 # print("Sample {}, Test {}: {}".format(sample, test[0], result))
#                 samples[i].append(result[0])
#         yield [conf.var] + [mean(s) for s in samples]

# add Ri
def run_tests(confs, tests, oh):
    nodrop_fw = get_framework('nodrop_0')
    delta_nd, alpha_nd, beta_nd = nodrop_fw.delta, nodrop_fw.alpha, nodrop_fw.beta
    
    # ellipsis_fw = get_framework('ellipsis')
    # delta_el, alpha_el, beta_el = ellipsis_fw.delta, ellipsis_fw.alpha, ellipsis_fw.beta
    

    for conf in confs:
        samples = [[] for _ in tests]
        R_all = []
        # residence_times = []
        # R_all_ellipsis = []

        for sample in range(int(conf.samples)):
            if sample % 100 == 0:
                print("Finished {} samples for variable {}".format(sample, conf.var))
            ts = conf.make_taskset()

            results = []
            # residence_time_sample = None

            for i, (_, test_fn) in enumerate(tests):
                ok, _ = test_fn(ts, oh, conf)
                samples[i].append(ok)
                results.append(ok)

            # nodrop_index = next(i for i, (name, _) in enumerate(tests) if name == 'nodrop_0')
            # if results[nodrop_index] == 1:

            nodrop_index = next(i for i, (name, _) in enumerate(tests) if name.startswith('#rta_nodrop'))
            if results[nodrop_index] == 1:

            # if results[2] == 1:
                for part in iter_partitions_ts(ts):
                    part_ts = TaskSystem(part)
                    users = [t for t in part_ts if not t.is_consumer]
                    users.sort(key=lambda t: t.preemption_level)
                    for idx, task in enumerate(users):
                        higher = users[:idx]
                        ri = _event_residence_time_nodrop(
                            task, higher, delta_nd, alpha_nd, beta_nd
                        )
                        if not (math.isinf(ri) or math.isnan(ri)):
                        # if math.isfinite(ri):
                            R_all.append(ri)


            # ellipsis_index = next(i for i, (name, _) in enumerate(tests) if name == 'ellipsis')
            # # if results[ellipsis_index] == 1:
            # #     ellipsis_index = next(i for i, (name, _) in enumerate(tests) if name == '#rta_ellipsis')
            # if results[ellipsis_index] == 1:
            #     for part in iter_partitions_ts(ts):
            #         part_ts = TaskSystem(part)
                    
            #         # users = [t for t in part_ts if not t.is_consumer]
            #         users = part_ts

            #         users.sort(key=lambda t: t.preemption_level)
            #         for idx, task in enumerate(users):
            #             higher = users[:idx]
            #             ri = _event_residence_time_ellipsis(
            #                 task, higher, delta_el, alpha_el, beta_el
            #             )
            #             if not (math.isinf(ri) or math.isnan(ri)):
            #                 R_all_ellipsis.append(ri)

        if R_all:
            res_max  = max(R_all)
            res_min  = min(R_all)
            res_mean = mean(R_all)
        else:
            res_max = res_min = res_mean = 0

        # if R_all_ellipsis:
        #     res_max_el  = max(R_all_ellipsis)
        #     res_min_el  = min(R_all_ellipsis)
        #     res_mean_el = mean(R_all_ellipsis)
        # else:
        #     res_max_el = res_min_el = res_mean_el = 0

        # yield [conf.var] + [mean(col) for col in samples] + [res_max, res_min, res_mean, res_max_el, res_min_el, res_mean_el]
        yield [conf.var] + [mean(col) for col in samples] + [res_max, res_min, res_mean]

def run_util_num_config(conf):
    start_time = time.time()
    oh = None
    util_range = [float(conf.util_num_min) + i * float(conf.step)
                  for i in range(int((float(conf.util_num_max) - float(conf.util_num_min)) / float(conf.step)) + 1)]
    confs = [copy.copy(conf) for _ in util_range]
    for i, util in enumerate(util_range):
        confs[i].util = util
        confs[i].var = util
        confs[i].make_taskset = partial(generate_task_set, confs[i])
    
    tests = setup_tests()
    
    header = ['UTILIZATION'] + [t for t, _ in tests] + ['RES_MAX_ND', 'RES_MIN_ND', 'RES_MEAN_ND']
    
    # header = ['UTILIZATION'] + [t for t, _ in tests] + ['RES_MAX', 'RES_MIN', 'RES_MEAN']
    data = run_tests(confs, tests, oh)
    completed_time = time.time()
    # write_util_data(conf.output, data, header, conf, start_time, completed_time)
    write_util_data('output/result0926-test/util_cpu=1_syscall=10_test-10.txt', data, header, conf, start_time, completed_time)

def run_syscall_count_config(conf):
    start_time = time.time()
    oh = None
    syscall_count_range = range(int(conf.syscall_count_min), int(conf.syscall_count_max) + 1, int(conf.syscall_count_step))
    confs = [copy.copy(conf) for _ in syscall_count_range]
    for i, syscall_count in enumerate(syscall_count_range):
        confs[i].syscall_count = syscall_count
        confs[i].var = syscall_count
        confs[i].make_taskset = partial(generate_task_set, confs[i])
    
    tests = setup_tests()
    
    header = ['UTILIZATION'] + [t for t, _ in tests] + ['RES_MAX_ND', 'RES_MIN_ND', 'RES_MEAN_ND', 'RES_MAX_EL', 'RES_MIN_EL', 'RES_MEAN_EL']

    # header = ['SYSCALL_COUNT'] + [t for t, _ in tests] + ['RES_MAX', 'RES_MIN', 'RES_MEAN']
    data = run_tests(confs, tests, oh)
    completed_time = time.time()
    write_util_data('output/result0926-test/syscall_count_5_15_cpu=1_util=0.75_test.txt', data, header, conf, start_time, completed_time)

def run_cpu_num_config(conf):
    start_time = time.time()
    oh = None
    cpu_num_range = range(int(conf.cpu_num_min), int(conf.cpu_num_max) + 1, int(conf.cpu_num_step))
    confs = [copy.copy(conf) for _ in cpu_num_range]
    for i, num_cpus in enumerate(cpu_num_range):
        confs[i].num_cpus = num_cpus
        confs[i].var = num_cpus
        confs[i].make_taskset = partial(generate_task_set, confs[i])
    
    tests = setup_tests()
    
    header = ['UTILIZATION'] + [t for t, _ in tests] + ['RES_MAX_ND', 'RES_MIN_ND', 'RES_MEAN_ND', 'RES_MAX_EL', 'RES_MIN_EL', 'RES_MEAN_EL']
    
    # header = ['CPU_NUMBER'] + [t for t, _ in tests] + ['RES_MAX', 'RES_MIN', 'RES_MEAN']
    data = run_tests(confs, tests, oh)
    completed_time = time.time()
    write_util_data('output/result0926-test/cpu_num_1_10_util=0.75_syscall=2_test.txt', data, header, conf, start_time, completed_time)

def write_util_data(output_file, data, header, conf, start_time, completed_time):
    output_dir = os.path.dirname(output_file)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    with open(output_file, 'w') as f:
        f.write("############### CONFIGURATION ###############\n")
        for key, value in conf.__dict__.items():
            f.write("# {:<15}: {}\n".format(key, value))
        f.write("################ ENVIRONMENT ################\n")
        f.write("# CWD............: {}\n".format(os.getcwd()))
        f.write("# Host...........: {}\n".format(socket.gethostname()))
        f.write("# Python.........: {}\n".format(sys.version.split()[0]))
        f.write("#################### DATA ###################\n")
        f.write("# " + " ".join(["{0:>13}".format(h) for h in header]) + "\n")
        for row in data:
            f.write(" ".join(["{0:>13}".format(str(x)) for x in row]) + "\n")
        f.write("#################### RUN ####################\n")
        f.write("# Started........: {}\n".format(datetime.fromtimestamp(start_time).strftime('%Y-%m-%d %H:%M:%S')))
        f.write("# Completed......: {}\n".format(datetime.fromtimestamp(completed_time).strftime('%Y-%m-%d %H:%M:%S')))
        f.write("# Duration.......: {:.2f} seconds\n".format(completed_time - start_time))

EXPERIMENTS = {
    'util_num': run_util_num_config,
    'syscall_count': run_syscall_count_config,
    'cpu_num': run_cpu_num_config,
}

CONFIG_GENERATORS = {
    'rtas18': lambda options: None,
}

if __name__ == "__main__":
    class Conf:
        def __init__(self):
            self.experiment = 'util_num'
            # self.experiment = 'syscall_count'
            # self.experiment = 'cpu_num'
            # self.output = 'output/test_util_add_cpu_syscall.txt'
            self.num_task = 10
            self.samples = 1000
            self.periods = '10-100'
            self.syscall_count = 10
            self.num_cpus = 1

            self.util_num_min = 0.5
            self.util_num_max = 1.0
            self.step = 0.01
            
            self.consumer_period_factor = 1.0
            # self.consumer_syscall_count = 1

            # util 0.76-0.78
            self.util = 0.75
            
            # New attributes for syscall_count and cpu_num experiments
            
            # 
            self.syscall_count_min = 5
            self.syscall_count_max = 15
            self.syscall_count_step = 1
            
            self.cpu_num_min = 1
            self.cpu_num_max = 10
            self.cpu_num_step = 1

    conf = Conf()
    
    # for experiment in ['util_num', 'syscall_count', 'cpu_num']:
    #     conf.experiment = experiment
    #     EXPERIMENTS[experiment](conf)
    EXPERIMENTS[conf.experiment](conf)