"""Run only against an explicitly configured staging API with 50 distinct test users."""
import asyncio
import json
import math
import os
import time

import httpx


async def main():
    base = os.environ['AVENTI_STAGING_API_URL'].rstrip('/')
    if not base.startswith('https://'):
        raise SystemExit('Use an explicit HTTPS staging API URL')
    accounts = json.loads(os.environ['AVENTI_LOAD_TEST_ACCOUNTS'])
    if len(accounts) < 50 or len({account['userId'] for account in accounts}) < 50:
        raise SystemExit('At least 50 distinct staging users are required')
    timings, failures = [], []
    async with httpx.AsyncClient(timeout=10, limits=httpx.Limits(max_connections=50)) as client:
        async def request(account):
            start = time.perf_counter()
            try:
                response = await client.get(f'{base}/v1/feed', headers={'Authorization': f"Bearer {account['token']}"},
                    params={'date':'week','latitude':account['latitude'],'longitude':account['longitude'],'limit':20})
                failures.append(response.status_code >= 500)
                if response.status_code >= 400:
                    raise RuntimeError(f'Non-success response: {response.status_code}')
                if not response.json().get('items'):
                    raise RuntimeError('Use populated staging accounts to measure cached inventory')
            except httpx.HTTPError:
                failures.append(True)
            finally:
                timings.append(time.perf_counter()-start)
        for _ in range(4):
            await asyncio.gather(*(request(account) for account in accounts[:50]))
    p95 = sorted(timings)[math.ceil(len(timings)*.95)-1]
    error_rate = sum(failures)/len(timings)
    print(json.dumps({'requests':len(timings),'concurrentUsers':50,'p95Seconds':round(p95,3),'serverErrorRate':error_rate}))
    if p95 >= 2 or error_rate >= .01:
        raise SystemExit('Cached feed release gate failed')


if __name__ == '__main__':
    asyncio.run(main())
