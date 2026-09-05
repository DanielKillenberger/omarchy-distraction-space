import json
import os
from pathlib import Path
import subprocess
import sys

root, parent_namespace, uid = sys.argv[1:]
if os.readlink('/proc/self/ns/net') == parent_namespace:
    raise SystemExit('refusing parent network namespace')
sys.path.insert(0, root)
from ds import net

os.environ['SUDO_UID'] = uid
os.environ.pop('DS_CGROUP_ROOT', None)
original = net.run_command
calls = []

def namespace_command(args, **kwargs):
    if args[:2] != ['sudo', '-n']:
        raise AssertionError(args)
    calls.append(args[-2])
    return original([sys.executable, str(Path(root) / 'distractions-nft'), *args[-2:]], **kwargs)

net.run_command = namespace_command
reconciler = net._Reconciler()
addresses = ['203.0.113.2', '2001:db8::8', '203.0.113.8']
for desired in [addresses, list(reversed(addresses)), addresses + addresses]:
    assert reconciler.reconcile(desired) == 'on'
assert calls == ['replace', 'check', 'check', 'check'], calls
equal_calls = list(calls)
repairs = []
for mutation in [['nft', 'add', 'rule', 'inet', 'omarchy_ds', 'output', 'accept'],
                 ['nft', 'delete', 'table', 'inet', 'omarchy_ds']]:
    subprocess.run(mutation, check=True, capture_output=True, timeout=5)
    calls.clear()
    assert reconciler.reconcile(addresses) == 'on'
    assert calls == ['check', 'replace', 'check'], calls
    repairs.append(list(calls))
calls.clear()
assert reconciler.reconcile([]) == 'off'
assert reconciler.reconcile([]) == 'off'
assert calls == ['flush', 'flush'] and reconciler.baseline is None
print(json.dumps({'result': 'PASS', 'namespace_isolated': True,
                  'transport': 'direct branch wrapper under mapped namespace root; sudo authorization not exercised',
                  'equal_policy_three_cycles': equal_calls,
                  'extra_rule_and_deleted_table_repairs': repairs,
                  'empty_policy_two_cycles': calls}, indent=2))
