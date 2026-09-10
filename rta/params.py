from __future__ import division

class AuditFramework:
    def __init__(self, name, delta=None, alpha=None, beta=None):
        self.name = name
        self.delta = delta
        self.alpha = alpha
        self.beta = beta

    def calculate_execution_time(self, task):
        if self.name == 'rta':
            return task.cost
        # elif self.name == 'omnilog':
        elif self.name == 'omnilog_0' or self.name == 'omnilog_1':
            if self.delta is None:
                raise ValueError("Delta parameter required for omnilog framework")
            if task.is_consumer:
                return 0
            else:
                # add print
                # print("\n syscall count {}:" .format(task.syscall_count))
                # print("\n delta {}:" .format(self.delta))
                # print("\n cost {}:" .format(task.cost))
                # print("\n omnilog execution time {}: ".format(task.cost + task.syscall_count * self.delta))
                return task.cost + task.syscall_count * self.delta
            
        # elif self.name == 'ellipsis':
        #     if self.delta is None or self.alpha is None or self.beta is None:
        #         raise ValueError("Delta, alpha, and beta parameters required for omnilog framework")
        #     if task.is_consumer:
        #         return 0
        #     else:
        #         return task.cost + task.syscall_count * self.delta

        # elif self.name == 'nodrop':
        elif self.name == 'nodrop_0' or self.name == 'nodrop_1' or self.name == 'nodrop_2' or self.name == 'nodrop_3':
            if self.delta is None or self.alpha is None or self.beta is None:
                raise ValueError("Delta, alpha, and beta parameters required for nodrop framework")
            if task.is_consumer:
                # add print
                # print("\n nodrop consumer execution time {}: ".format(self.alpha + task.syscall_count * self.beta))
                return 0
            else:
                # add print
                # print("\n syscall count {}:" .format(task.syscall_count))
                # print("\n delta {}:" .format(self.delta))
                # print("\n cost {}:" .format(task.cost))
                # print("\n nodrop user execution time {}: ".format(task.cost + task.syscall_count * self.delta))
                return task.cost + task.syscall_count * self.delta
        
        # audit ellipsis ellipsis_delta0 ellipsi_delta_audit
        elif self.name == 'audit' or self.name == 'ellipsis' or self.name == 'ellipsis_delta0' or self.name == 'ellipsis_delta_audit':
            if self.delta is None or self.alpha is None or self.beta is None:
                raise ValueError("Delta, alpha, and beta parameters required for ellipsis framework")
            if task.is_consumer:
                return 0
            else:
                # print("*******************\n")
                return task.cost + task.syscall_count * self.delta

        else:
            raise ValueError("Unknown framework: {}".format(self.name))
        

FRAMEWORKS = {
    'rta': AuditFramework('rta'),
    # 'omnilog': AuditFramework('omnilog', delta=0.3, beta=0.05),

    # syscall = 2000, omnilog_delta = 0.3/0.1, utilization = 0.8, schedulable
    # 'omnilog_0': AuditFramework('omnilog_0', delta=0.3, beta=0.05),
    # 'omnilog_1': AuditFramework('omnilog_1', delta=0.1, beta=0.05),

    # 'nodrop_0': AuditFramework('nodrop_0', delta=0.1, alpha=0.2, beta=0.05),
    # 'nodrop_1': AuditFramework('nodrop_1', delta=0.1, alpha=0.5, beta=0.05),
    # 'nodrop_2': AuditFramework('nodrop_2', delta=0.1, alpha=0.8, beta=0.05),
    # 'nodrop_3': AuditFramework('nodrop_3', delta=0.1, alpha=1.0, beta=0.05)

    # syscall = 2000, omnilog_delta = 0.31, beta = 0.15, schedulable
    'omnilog_0': AuditFramework('omnilog_0', delta=3.42, beta=0.98),
    'omnilog_1': AuditFramework('omnilog_1', delta=0.31, beta=0.98),
    'omnilog_2': AuditFramework('omnilog_2', delta=3.52, beta=0),
    # ellipsis
    # 'ellipsis': AuditFramework('ellipsis', delta=0.342, alpha=20, beta=0.098),
    # 'ellipsis': AuditFramework('ellipsis', delta=0.031, alpha=50, beta=0.098),
    # 'ellipsis': AuditFramework('ellipsis', delta=0.31, alpha=200, beta=0.98),

    # delta is not sure
    'audit': AuditFramework('audit', delta=7.04, alpha=0, beta=0.98),
    'ellipsis': AuditFramework('ellipsis', delta=3.52, alpha=0, beta=0),
    # 'ellipsis_delta0': AuditFramework('ellipsis_delta0', delta=0, alpha=0, beta=0),
    # 'ellipsis_delta_audit': AuditFramework('ellipsis_delta_audit', delta=4.71, alpha=0, beta=0),

    # 'ellipsis_hp': AuditFramework('ellipsis_hp', delta=0.15, alpha=100, beta=0.5),
    'nodrop_0': AuditFramework('nodrop_0', delta=0.31, alpha=200, beta=0.98),
    # 'nodrop_1': AuditFramework('nodrop_1', delta=0.31, alpha=500, beta=0.98),
    # 'nodrop_2': AuditFramework('nodrop_2', delta=0.31, alpha=800, beta=0.98),
    # 'nodrop_3': AuditFramework('nodrop_3', delta=0.31, alpha=1000, beta=0.98)
    
    # syscall 2000
    # 1 ms 1 2 5 10

    # nodrop_delta = 0.31 us
    # nodrop_alpha = 200 - 1000 us
    # nodrop_beta = 0.98 us

    # omnilog_delta = 3.42 / 2 / 2.2 / 2.3 us
    # omnilog_delta = 0.31 us
    # omnilog_beta = 0.98 us

    # nodrop
}

def get_framework(framework_name):
    if framework_name not in FRAMEWORKS:
        raise ValueError("Framework {} not found".format(framework_name))
    return FRAMEWORKS[framework_name]