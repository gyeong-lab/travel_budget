# -*- coding: utf-8 -*-
import urllib.request
import json
import os
import sys
sys.stdout.reconfigure(encoding='utf-8')

base_url = 'http://127.0.0.1:5000'

# 1. Health
res = urllib.request.urlopen(f'{base_url}/health')
h = json.loads(res.read())
print('[TEST 1] Health OK:', h)

# 2. Inspect
csv_path = r'C:\AI-study\travelbudget\data\관광여행_만족도_관광지_물가_20261027135331.csv'
boundary = '----WebKitFormBoundary7MA4YWxkTrZu0gW'
with open(csv_path, 'rb') as f:
    csv_bytes = f.read()

body = (
    f'--{boundary}\r\n'
    f'Content-Disposition: form-data; name="file"; filename="{os.path.basename(csv_path)}"\r\n'
    f'Content-Type: text/csv\r\n\r\n'
).encode('utf-8') + csv_bytes + f'\r\n--{boundary}--\r\n'.encode('utf-8')

req = urllib.request.Request(
    f'{base_url}/inspect',
    data=body,
    headers={'Content-Type': f'multipart/form-data; boundary={boundary}'}
)
res = urllib.request.urlopen(req)
insp = json.loads(res.read())
print('[TEST 2] Inspect OK: rows =', insp['diagnosis']['rows'], 'cols =', insp['diagnosis']['columns'], 'encoding =', insp['diagnosis']['encoding'])

# 3. Suggest
req_sug = urllib.request.Request(
    f'{base_url}/suggest',
    data=b'{}',
    headers={'Content-Type': 'application/json'}
)
res_sug = urllib.request.urlopen(req_sug)
sug = json.loads(res_sug.read())
print('[TEST 3] Suggest OK: suggestions count =', len(sug['suggestions']), 'source =', sug.get('source'))

# 4. Run Tool
first_sug = sug['suggestions'][0]
print('Running tool:', first_sug['tool'], first_sug['params'])
req_run = urllib.request.Request(
    f'{base_url}/run',
    data=json.dumps({'tool': first_sug['tool'], 'params': first_sug['params']}).encode('utf-8'),
    headers={'Content-Type': 'application/json'}
)
res_run = urllib.request.urlopen(req_run)
run_res = json.loads(res_run.read())
print('[TEST 4] Run OK: tool =', run_res['data']['tool'], 'rows_used =', run_res['data']['rows_used'], 'rows_excluded =', run_res['data']['rows_excluded'])

# 5. Explain Mode B
req_exp_b = urllib.request.Request(
    f'{base_url}/explain',
    data=json.dumps({'mode': 'B'}).encode('utf-8'),
    headers={'Content-Type': 'application/json'}
)
res_exp_b = urllib.request.urlopen(req_exp_b)
exp_b = json.loads(res_exp_b.read())
print('[TEST 5] Explain Mode B OK! Report sample:\n' + exp_b['explanation'][:350])

# 6. Explain Mode A
req_exp_a = urllib.request.Request(
    f'{base_url}/explain',
    data=json.dumps({'mode': 'A'}).encode('utf-8'),
    headers={'Content-Type': 'application/json'}
)
res_exp_a = urllib.request.urlopen(req_exp_a)
exp_a = json.loads(res_exp_a.read())
print('\n[TEST 6] Explain Mode A OK! Report sample:\n' + exp_a['explanation'][:250])
