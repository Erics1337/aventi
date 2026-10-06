"""Explicit post-deployment API -> outbox -> SQS -> worker smoke test."""
import json
import os
import time
import urllib.request

base=os.environ['AVENTI_API_URL'].rstrip('/')
key=os.environ['AVENTI_INTERNAL_API_KEY']
def request(path, payload=None):
    body=json.dumps(payload).encode() if payload is not None else None
    req=urllib.request.Request(base+path,data=body,headers={'Content-Type':'application/json','x-aventi-internal-key':key})
    with urllib.request.urlopen(req,timeout=15) as response:
        return json.load(response)
assert request('/v1/health')['status']=='ok'
job=request('/internal/jobs/enqueue',{'type':'HEALTH_CHECK','payload':{}})['job']['id']
deadline=time.monotonic()+180
while time.monotonic()<deadline:
    state=request(f'/internal/jobs/{job}')
    if state['status']=='completed':
        assert state['result']['ok'] is True
        print('API and durable worker smoke check passed')
        break
    if state['status'] in {'dead','cancelled'}:
        raise SystemExit('Worker smoke check failed')
    time.sleep(5)
else:
    raise SystemExit('Worker smoke check timed out')
