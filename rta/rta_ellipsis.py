from __future__ import division
import copy
from math import ceil
from schedcat.model.tasks import SporadicTask, TaskSystem

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
        return task.response_time - task.cost
    else:
        return get_jitter(task)

def _rta_ellipsis(task, own_demand, higher_prio_tasks, hp_jitter, delta):
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

def rta_ellipsis_jitter_aware(task, higher_prio_tasks, delta):
    own_demand = get_prio_inversion(task) + task.cost
    return _rta_ellipsis(task, own_demand, higher_prio_tasks, get_jitter, delta)

def rta_ellipsis_suspension_aware(task, higher_prio_tasks, delta):
    own_demand = get_prio_inversion(task) + task.cost + get_suspended(task)
    return _rta_ellipsis(task, own_demand, higher_prio_tasks, suspension_jitter, delta)

def legacy_rta_ellipsis_jitter_aware(task, higher_prio_tasks, delta):
    own_demand = get_blocked(task) + task.cost
    return _rta_ellipsis(task, own_demand, higher_prio_tasks, get_jitter)

def legacy_rta_suspension_aware(task, higher_prio_tasks, delta):
    own_demand = get_blocked(task) + task.cost
    return _rta_ellipsis(task, own_demand, higher_prio_tasks, suspension_jitter)

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

def bound_response_times_ellipsis(no_cpus, taskset, delta):
    legacy = uses_legacy_blocked_field(taskset)
    susp   = has_self_suspensions(taskset)
    if not (no_cpus == 1 and taskset.only_constrained_deadlines()):
        return False
    
    rta = rta_ellipsis_suspension_aware if susp else rta_ellipsis_jitter_aware
    
    for i, task in enumerate(taskset):
        if not rta(task, taskset[0:i], delta):
            return False
    return True

# def bound_response_times_ellipsis(consumer_cpu, tasks, delta, beta):
#     tasks.sort(key=lambda t: t.preemption_level)
#     consumer = next(t for t in tasks if t.is_consumer)
#     q_sigma = consumer.period

#     partitions = {}
#     for t in tasks:
#         if t.partition not in partitions:
#             partitions[t.partition] = []
#         partitions[t.partition].append(t)

#     for t in tasks:
#         t.response_time = 0
    
#     def S(W):
#         total_syscalls = 0
#         for t in tasks:
#             if not t.is_consumer:
#                 total_syscalls += ceil(float(W + t.response_time) / t.period) * t.syscall_count
#         return total_syscalls

#     converged = False
#     while not converged:
#         W = q_sigma + consumer.response_time
#         A_star = S(W)
#         consumer.cost = beta * A_star
#         converged = True

#         for cpu, part_tasks in partitions.items():
#             part_ts = TaskSystem(part_tasks)
#             part_ts.sort(key=lambda t: t.preemption_level)
#             for i, task in enumerate(part_ts):
#                 higher_prio_tasks = part_ts[:i]
#                 interference = sum(ceil(float(task.response_time) / t.period) * t.cost for t in higher_prio_tasks)
#                 r = task.cost + interference
                
#                 if r != task.response_time:
#                     task.response_time = r
#                     converged = False
                
#                 if r > task.deadline:
#                     return False
#     return True

def bound_response_times_ellipsis(consumer_cpu, tasks, delta, beta):
    tasks.sort(key=lambda t: t.preemption_level)
    
    # print_task_set(tasks)
    
    consumer = next(t for t in tasks if t.is_consumer)
    
    # debug
    # consumer_ts = TaskSystem([consumer])
    # print("\n")
    # print_task_set(consumer_ts)

    q_sigma = consumer.period

    # debug
    # print("q_sigma (consumer period): {:.2f}".format(q_sigma))

    partitions = {}
    for t in tasks:
        if t.partition not in partitions:
            partitions[t.partition] = []
        partitions[t.partition].append(t)

    max_adjust = 5
    adjust_count = 0

    while True:
        adjust_count += 1
        
        # debug
        # print("\n--- Adjustment iteration {} ---".format(adjust_count))
        
        for t in tasks:
            t.response_time = 0
            
            # debug
            # print("Task {} initial R: {:.2f}".format(t.id, t.response_time))
        
        def S(W):
            total_syscalls = 0
            for t in tasks:
                if not t.is_consumer:

                    # debug
                    # print("\nt{}: ".format(ceil(float(W + t.response_time) / t.period)))

                    total_syscalls += ceil(float(W + t.response_time) / t.period) * t.syscall_count
            return total_syscalls

        # debug
        # iteration = 0

        converged = False
        while not converged:

            # debug
            # iteration += 1

            W = q_sigma + consumer.response_time
            A_star = S(W)

            # debug
            # print("\nA_star {}:".format(A_star))

            consumer.cost = beta * A_star
            prev_r_sigma = consumer.response_time
            
            # debug
            # print("\nprev_r_sigma {}:".format(prev_r_sigma))
            
            converged = True

            for cpu, part_tasks in partitions.items():
                part_ts = TaskSystem(part_tasks)
                part_ts.sort(key=lambda t: t.preemption_level)
                for i, task in enumerate(part_ts):
                    higher_prio_tasks = part_ts[:i]
                    interference = sum(ceil(float(task.response_time) / t.period) * t.cost for t in higher_prio_tasks)
                    r = task.cost + interference
                    
                    if r != task.response_time:
                        task.response_time = r
                        converged = False
                    
                    if r > task.deadline:
                        return False
        
        user_rts = [t.response_time for t in tasks if not t.is_consumer]
        max_user_rt = max(user_rts) if user_rts else 0
        if max_user_rt > q_sigma and adjust_count < max_adjust:
            q_sigma *= 1.5
            consumer.period = q_sigma
            consumer.deadline = q_sigma
            continue
        break

    return True if adjust_count < max_adjust else False

# def bound_response_times_omnilog(tasks, delta, beta):
#     consumer = next((t for t in tasks if getattr(t, 'is_consumer', False)), None)
#     if consumer is None:
#         return False

#     tasks.sort(key=lambda t: (getattr(t, 'is_consumer', False), getattr(t, 'preemption_level', 0)))

#     for t in tasks:
#         t.response_time = 0

#     q_sigma = consumer.period

#     def S(W):
#         total_syscalls = 0
#         for t in tasks:
#             if not getattr(t, 'is_consumer', False):
#                 total_syscalls += ceil(float(W + t.response_time) / t.period) * getattr(t, 'syscall_count', 0)
#         return total_syscalls

#     converged = False
#     max_outer_iters = 200
#     outer_iter = 0

#     while not converged and outer_iter < max_outer_iters:
#         outer_iter += 1
#         W = q_sigma + consumer.response_time
#         A_star = S(W)
#         consumer.cost = beta * A_star

#         converged = True

#         partitions = {}
#         for t in tasks:
#             partitions.setdefault(t.partition, []).append(t)

#         for cpu, part_tasks in partitions.items():
#             part_tasks.sort(key=lambda t: (getattr(t, 'is_consumer', False), getattr(t, 'preemption_level', 0)))
#             for i, task in enumerate(part_tasks):
#                 if not getattr(task, 'is_consumer', False):
#                     higher = part_tasks[:i]
#                     interference = sum(ceil(float(task.response_time) / t.period) * t.cost for t in higher)
#                     r = task.cost + interference
#                 else:
#                     higher_than_consumer = [t for t in tasks if not getattr(t, 'is_consumer', False)]
#                     interference = sum(ceil(float(task.response_time) / t.period) * t.cost for t in higher_than_consumer)
#                     r = task.cost + interference

#                 if r != task.response_time:
#                     task.response_time = r
#                     converged = False

#                 if r > task.deadline:
#                     return False

#         if consumer.response_time > q_sigma:
#             q_sigma = int(ceil(consumer.response_time))
#             consumer.period = q_sigma
#             converged = False

#     if not converged:
#         return False

#     return True


# def _event_residence_time_ellipsis(task, higher_prio_tasks, delta, alpha, beta):
#     higher_prio_regular = [t for t in higher_prio_tasks if not t.is_consumer]
#     # T_p_base = alpha + get_syscall_count(task) * beta
#     # T_p = T_p_base + sum(t.cost for t in higher_prio_regular)
#     T_p_base = alpha + sum(t.syscall_count for t in higher_prio_regular) * beta
#     T_p = T_p_base + sum(t.cost for t in higher_prio_regular)
#     while True:
#         interference_regular = sum(ceil(float(T_p) / t.period) * t.cost for t in higher_prio_regular)
#         demand = T_p_base + interference_regular
#         if demand <= T_p:
#             T_p = demand
#             break
#         else:
#             T_p = demand
#     R_i = T_p
#     return R_i

def _event_residence_time_ellipsis(task, higher_prio_tasks, delta, alpha, beta):
    consumer = next(t for t in task if t.is_consumer)
    users = [t for t in higher_prio_tasks]
    
    C_sigma = alpha + beta * sum(get_syscall_count(t) for t in users)
    r_sigma = C_sigma
    prev_r_sigma = 0
    while r_sigma != prev_r_sigma:
        prev_r_sigma = r_sigma
        interference = sum(ceil(float(r_sigma) / t.period) * (t.cost + get_syscall_count(t) * delta) for t in users)
        r_sigma = C_sigma + interference
    
    residence_time = consumer.period + r_sigma
    return residence_time

# def _event_residence_time_ellipsis(task, higher_prio_tasks, delta, alpha, beta):
#     users = [t for t in higher_prio_tasks if not getattr(t, 'is_consumer', False)]
    
#     # debug
#     print ("Computing event residence time for task {}".format(task.id))
#     print ("Number of users: {}".format(len(users)))
    
#     consumer = next((t for t in tasks if getattr(t, 'is_consumer', False)), None)
    
#     if consumer is None:
#         C_sigma = alpha + beta * sum(get_syscall_count(t) for t in users)
#     else:
#         C_sigma = alpha + beta * sum(get_syscall_count(t) for t in users)
    
#     # debug
#     print ("C_sigma = {:.2f}".format(C_sigma))
    
#     r_sigma = C_sigma
#     prev_r_sigma = 0
#     iter = 0
    
#     while r_sigma != prev_r_sigma:
#         iter += 1
#         prev_r_sigma = r_sigma
#         interference = sum(ceil(float(r_sigma) / t.period) * (t.cost + get_syscall_count(t) * delta) for t in users)
#         r_sigma = C_sigma + interference
        
#         # debug
#         print ("Iteration {}: interference = {:.2f}, r_sigma = {:.2f}".format(iter, interference, r_sigma))
    
#     residence_time = consumer.period + r_sigma if consumer else 0 + r_sigma  # If no consumer, just r_sigma, but assume present
    
#     # debug
#     print ("Event residence time: {:.2f}".format(residence_time))
    
#     return residence_time