from concurrent.futures import ThreadPoolExecutor

def collect_parallel(call, roles):
    with ThreadPoolExecutor(max_workers=len(roles)) as pool:
        futures = {role: pool.submit(call, role) for role in roles}
        return {role: future.result() for role, future in futures.items()}

def supervise(results, round_no):
    if any(r.get('verdict') == 'BLOCK' for r in results.values()):
        return {'action': 'BLOCKED', 'target': None, 'reason': 'Blocking evidence'}
    missing = [role for role in ('policy', 'order', 'risk')
               if results.get(role, {}).get('verdict') != 'CLEAR']
    if missing:
        if round_no == 1 and missing == ['risk']:
            return {'action': 'FOLLOW_UP', 'target': 'risk', 'reason': 'One risk follow-up'}
        return {'action': 'BLOCKED', 'target': None, 'reason': 'Required evidence missing'}
    return {'action': 'READY', 'target': None, 'reason': 'All checks clear'}
