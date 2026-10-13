import urllib.request, json
req = urllib.request.Request(
    'http://127.0.0.1:8000/api/profile/chat', 
    data=json.dumps({"student_id": "demo_test", "messages": [{"role": "user", "content": "我学得很烂"}]}).encode(), 
    headers={'Content-Type': 'application/json'}
)
print(urllib.request.urlopen(req).read().decode())