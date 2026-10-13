import urllib.request
import json
import time

BASE_URL = 'http://127.0.0.1:8000/api'
STUDENT_ID = 'test_student_001'

def post(path, data):
    req = urllib.request.Request(
        f'{BASE_URL}{path}', 
        data=json.dumps(data).encode('utf-8'), 
        headers={'Content-Type': 'application/json'}
    )
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        print(f"Error {e.code}: {e.read().decode('utf-8')}")
        return None

def post_stream(path, data):
    req = urllib.request.Request(
        f'{BASE_URL}{path}', 
        data=json.dumps(data).encode('utf-8'), 
        headers={'Content-Type': 'application/json'}
    )
    events = []
    try:
        with urllib.request.urlopen(req) as response:
            for line in response:
                line = line.decode('utf-8').strip()
                if line.startswith('data:'):
                    try:
                        events.append(json.loads(line[5:]))
                    except:
                        pass
    except urllib.error.HTTPError as e:
        print(f"Error {e.code}: {e.read().decode('utf-8')}")
    return events

print("1. Profile Chat...")
profile_resp = post('/profile/chat', {
    "student_id": STUDENT_ID,
    "major": "计算机科学与技术",
    "goals": "准备期末考试",
    "messages": [
        {"role": "user", "content": "我的数据结构链表部分总是写错指针"}
    ]
})
print("Profile Response:", profile_resp)
print("-" * 40)

print("2. Workshop Clarify...")
clarify_resp = post('/workshop/clarify', {
    "student_id": STUDENT_ID,
    "messages": [
        {"role": "user", "content": "帮我生成一份数据结构链表复习资料，多给我点图解"}
    ]
})
print("Clarify Response:", clarify_resp)
print("-" * 40)

requirement = clarify_resp.get("requirement", {})

print("3. Workshop Generate (Stream)...")
generate_events = post_stream('/workshop/generate', {
    "student_id": STUDENT_ID,
    "requirement": requirement,
    "stream": True
})
print(f"Received {len(generate_events)} stream events.")
resources = []
for e in generate_events:
    if "event" in e and e["event"].get("type") == "agent_done":
        resources.append(e["event"].get("resource"))
print(f"Generated {len(resources)} resources.")
print("-" * 40)

if resources:
    res_id = resources[0]["id"]
    print("4. Resource Usage (dislike)...")
    usage_resp = post('/resources/usage', {
        "student_id": STUDENT_ID,
        "resource_id": res_id,
        "action": "dislike",
        "duration_sec": 120,
        "feedback": {"reason": "太难了"}
    })
    print("Usage Response:", usage_resp)
    print("-" * 40)

print("5. Tutor Chat...")
tutor_resp = post('/tutor/ask', {
    "student_id": STUDENT_ID,
    "question": "红黑树怎么理解？",
    "context": {}
})
print("Tutor Response:", tutor_resp)
print("-" * 40)

print("6. Path Plan...")
plan_resp = post('/path/plan', {
    "student_id": STUDENT_ID,
    "goals": "期末考90分"
})
print("Plan Response:", plan_resp)
print("-" * 40)

print("7. Evaluate Report...")
eval_resp = post('/evaluate/report', {
    "student_id": STUDENT_ID
})
print("Evaluate Response:", eval_resp)
print("-" * 40)

print("Done! Local file persistence should have captured these events.")
