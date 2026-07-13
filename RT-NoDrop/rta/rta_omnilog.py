from __future__ import division
import copy
from math import ceil
from schedcat.model.tasks import SporadicTask, TaskSystem

def print_task_set(ts):
    """Print detailed information of the task set."""
    print("Task Set Details:")
    print("{:<5} {:<10} {:<5} {:<10} {:<20}".format('ID', 'Type', 'CPU', 'Period', 'Preemption Level', 'Cost',))
    print("-" * 60)
    for task in ts:
        task_type = "Consumer" if getattr(task, 'is_consumer', False) else "User"
        preemption_level = getattr(task, 'preemption_level', '')
        print("{:<5} {:<10} {:<5} {:<10} {:<20} {:<5}".format(
            task.id,
            task_type,
            task.partition,
            task.period,
            preemption_level,
            task.cost,
            # task.syscall_count
        ))
    print("\n")

def get_syscall_count(task):
    return task.__dict__.get('syscall_count', 0)

def get_blocked(task):
    return task.__dict__.get('blocked', 0)

def get_jitter(task):
    return task.__dict__.get('jitter', 0)

def get_suspended(task):
    return task.__dict__.get('suspended', 0)

def get_prio_inversion(task):
    return task.__dict__.get('prio_inversion', 0)

def suspension_jitter(task):
    if get_suspended(task) > 0:
        # Suspension to jitter reduction: max jitter is R_i - C_i
        return task.response_time - task.cost
    else:
        return get_jitter(task)

# def _calculate_total_execution_time(task, delta):
#     return task.cost + get_syscall_count(task) * delta

def _rta_omnilog(task, own_demand, higher_prio_tasks, hp_jitter, delta):
    total_demand = sum(t.cost for t in higher_prio_tasks) + own_demand
    while total_demand <= task.deadline:
        demand = own_demand
        for t in higher_prio_tasks:
            demand += t.cost * int(ceil((total_demand + hp_jitter(t)) / t.period))
        if demand == total_demand:
            task.response_time = total_demand + get_jitter(task)
            return True
        else:
            total_demand = demand
    return False

# def rta_omnilog_jitter_aware(task, higher_prio_tasks, delta):
#     own_demand = get_prio_inversion(task) + _calculate_total_execution_time(task, delta)
#     return _rta_omnilog(task, own_demand, higher_prio_tasks, get_jitter, delta)

def rta_omnilog_jitter_aware(task, higher_prio_tasks, delta):
    own_demand = get_prio_inversion(task) + task.cost
    return _rta_omnilog(task, own_demand, higher_prio_tasks, get_jitter, delta)

# def rta_omnilog_suspension_aware(task, higher_prio_tasks, delta):
#     own_demand = get_prio_inversion(task) + _calculate_total_execution_time(task, delta) + get_suspended(task)
#     return _rta_omnilog(task, own_demand, higher_prio_tasks, suspension_jitter, delta)

def rta_omnilog_suspension_aware(task, higher_prio_tasks, delta):
    own_demand = get_prio_inversion(task) + task.cost + get_suspended(task)
    return _rta_omnilog(task, own_demand, higher_prio_tasks, suspension_jitter, delta)

# def legacy_rta_omnilog_jitter_aware(task, higher_prio_tasks, delta):
#     own_demand = get_blocked(task) + _calculate_total_execution_time(task, delta)
#     return _rta_omnilog(task, own_demand, higher_prio_tasks, get_jitter)

def legacy_rta_omnilog_jitter_aware(task, higher_prio_tasks, delta):
    own_demand = get_blocked(task) + task.cost
    return _rta_omnilog(task, own_demand, higher_prio_tasks, get_jitter)

# def legacy_rta_suspension_aware(task, higher_prio_tasks, delta):
#     own_demand = get_blocked(task) + _calculate_total_execution_time(task, delta)
#     return _rta_omnilog(task, own_demand, higher_prio_tasks, suspension_jitter)

def legacy_rta_suspension_aware(task, higher_prio_tasks, delta):
    own_demand = get_blocked(task) + task.cost
    return _rta_omnilog(task, own_demand, higher_prio_tasks, suspension_jitter)

def has_self_suspensions(taskset):
    for t in taskset:
        if 'suspended' in t.__dict__ and t.suspended != 0:
            return True
    return False

def uses_legacy_blocked_field(taskset):
    for t in taskset:
        if 'blocked' in t.__dict__:
            return True
    return False

def bound_response_times_omnilog(no_cpus, taskset, delta):
    legacy = uses_legacy_blocked_field(taskset)
    susp   = has_self_suspensions(taskset)
    if not (no_cpus == 1 and taskset.only_constrained_deadlines()):
        return False
    
    rta = rta_omnilog_suspension_aware if susp else rta_omnilog_jitter_aware
    
    for i, task in enumerate(taskset):
        if not rta(task, taskset[0:i], delta):
            return False
    return True

def bound_response_times_omnilog(consumer_cpu, tasks, delta, beta):
    """Debug print for omnilog response time convergence."""
    # Sort tasks by preemption level
    tasks.sort(key=lambda t: t.preemption_level)
    # Identify the consumer task
    consumer = next(t for t in tasks if t.is_consumer)

    # add if consumer
    # if consumer is None:
    #     print("No consumer task found for debug.")
    #     return
    
    q_sigma = consumer.period
    
    # add print
    # print("\nq_sigma {}: ".format(q_sigma))

    partitions = {}
    for t in tasks:
        if t.partition not in partitions:
            partitions[t.partition] = []
        partitions[t.partition].append(t)

    for t in tasks:
        t.response_time = 0
    
    def S(W):
        total_syscalls = 0
        for t in tasks:
            if not t.is_consumer:
                # add print
                # print("\nt {}: ".format(ceil(float(W + t.response_time) / t.period)))
                total_syscalls += ceil(float(W + t.response_time) / t.period) * t.syscall_count
        return total_syscalls

    # add iteration
    # iteration = 0

    # converged = False
    # while not converged:

    #     # add interation
    #     # iteration += 1
    #     # print("\nIteration {}: ".format(iteration))

    #     converged = True
    #     prev_r_sigma = consumer.response_time

    #     # add prev_r_sigma
    #     # print("\nprev_r_sigma {}: ".format(prev_r_sigma))

    #     A_star = S(q_sigma + prev_r_sigma)
        
    #     # add print
    #     print("\nA_star {}:".format(A_star))

    #     consumer_cost = beta * A_star
    #     consumer.response_time = consumer_cost
        
    #     # add print
    #     # print("  r_sigma: {:.2f}".format(consumer.response_time))
        
    #     if consumer.response_time != prev_r_sigma:
    #         converged = False
        
    #     for task in tasks:
    #         if not task.is_consumer:
    #             E_i = task.cost
    #             b_i = 0
    #             interference = 0

    #             for t in tasks:
    #                 if t.preemption_level < task.preemption_level and not t.is_consumer:
    #                     interference += ceil(float(task.response_time) / t.period) * t.cost
                
    #             A_star = S(q_sigma + consumer.response_time)
    #             I_sigma_i = ceil(float(task.response_time) / q_sigma) * beta * A_star
                
    #             # add I_sigma_i
    #             # print("  I_sigma_i: {:.2f}".format(I_sigma_i))
                
    #             new_r_i = E_i + b_i + interference + I_sigma_i
    #             if new_r_i != task.response_time:
    #                 task.response_time = new_r_i
    #                 converged = False

    #             # add print
    #             # print("  r_{}: {:.2f}".format(task.period, task.response_time))
    
    # for t in tasks:
    #     if not t.is_consumer and t.response_time > t.deadline:
    #         return False

    # add print
    # interation = 0

    converged = False
    while not converged:
        # W = q_sigma + consumer.response_time
        # A_star = S(W)

        # # add print
        # print("\nA_star {}:".format(A_star))

        # consumer.cost = beta * A_star
        
        # converged = True

        # for cpu, part_tasks in partitions.items():
        #     part_ts = TaskSystem(part_tasks)
        #     part_ts.sort(key=lambda t: t.preemption_level)
        #     for i, task in enumerate(part_ts):
        #         higher_prio_tasks = part_ts[:i]
        #         if task.is_consumer:
        #             interference = sum(ceil(float(task.response_time) / t.period) * t.cost for t in higher_prio_tasks)
        #             r = task.cost + interference
        #         else:
        #             interference = sum(ceil(float(task.response_time) / t.period) * t.cost for t in higher_prio_tasks)
        #             if cpu == consumer_cpu and consumer.preemption_level < task.preemption_level:
        #                 interference += ceil(task.response_time / consumer.period) * consumer.cost
        #             r = task.cost + interference
                
        #         if r != task.response_time:
        #             task.response_time = r
        #             converged = False
                
        #         if r > task.deadline:
        #             return False
        
        # add print
        # interation += 1
        # print("\ninteration {}".format(interation))

        W = q_sigma + consumer.response_time
        A_star = S(W)
        # add print
        # print("\nA_star {}:".format(A_star))

        consumer.cost = beta * A_star
        # add print
        prev_r_sigma = consumer.response_time
        # print("\nprev_r_sigma {}:".format(prev_r_sigma))

        converged = True

        for cpu, part_tasks in partitions.items():
            part_ts = TaskSystem(part_tasks)
            # part_ts = copy.deepcopy(part_tasks)
            
            # add print
            # print_task_set(part_ts)
            
            part_ts.sort(key=lambda t: t.preemption_level)
            for i, task in enumerate(part_ts):
                higher_prio_tasks = part_ts[:i]
                # if task.is_consumer:
                #     interference = sum(ceil(float(task.response_time) / t.period) * t.cost for t in higher_prio_tasks)
                #     print("\nconsumer interference {}:".format(interference))
                #     r = task.cost + interference
                # else:
                #     interference = sum(ceil(float(task.response_time) / t.period) * t.cost for t in higher_prio_tasks)
                #     if cpu == consumer_cpu and consumer.preemption_level < task.preemption_level:
                #         interference += ceil(float(task.response_time) / consumer.period) * consumer.cost
                #         print("\nregular interference {}:".format(interference))
                #     r = task.cost + interference
                if task.is_consumer:
                    r = task.cost
                else:
                    interference = sum(ceil(float(task.response_time) / t.period) * t.cost for t in higher_prio_tasks)
                    # print("\nregular interference {}".format(interference))
                    # print("\nconsumer cost {}".format(consumer.cost))
                    interference += ceil(float(task.response_time) / q_sigma) * consumer.cost
                    # print("\ntotal interference {}".format(interference))
                    # print("\ntask cost {}".format(task.cost))
                    r = task.cost + interference
                
                if r != task.response_time:
                    task.response_time = r
                    converged = False
                
                # add print
                # print("\nr{} {}:".format(i, r))

                if r > task.deadline:
                    # print("\nFalse")
                    return False
    # print("\nTrue")
    return True

is_schedulable_with_omnilog = bound_response_times_omnilog