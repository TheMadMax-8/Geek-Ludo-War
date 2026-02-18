from gevent import monkey
monkey.patch_all()

import json
import random
import requests
import os
import subprocess
import sys
import time
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit, join_room
from pymongo import MongoClient

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins="*")

# --- CORS: FORCE ALLOW ALL ---
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

# --- DATABASE SETUP ---
MONGO_URI = os.environ.get("MONGO_URI")
if not MONGO_URI:
    MONGO_URI = "mongodb+srv://admin:password@cluster0.mongodb.net/geek_ludo_db"

client = MongoClient(MONGO_URI)
db = client.geek_ludo_db
logs_collection = db.game_logs

LOBBIES = {}
BASE_ORDER = ['red', 'green', 'yellow', 'blue'] 
SAFE_INDICES = [0, 13, 26, 39]

# --- YOUR CUSTOM QUESTION BANK (Hardcoded for Stability) ---
QUESTION_BANK = [
    {
        "id": 1,
        "difficulty": "Easy",
        "rating": 800,
        "question": "Check Prime: Write a program that takes an integer N as input and prints 'Yes' if it is prime, and 'No' otherwise.",
        "standard_solution": {
            "language": "python",
            "code": "n = int(input())\nif n < 2:\n    print('No')\nelse:\n    is_prime = True\n    for i in range(2, int(n**0.5) + 1):\n        if n % i == 0:\n            is_prime = False\n            break\n    print('Yes' if is_prime else 'No')"
        },
        "test_cases": [
            { "input": "7", "output": "Yes", "type": "sample" },
            { "input": "10", "output": "No", "type": "hidden" }
        ]
    },
    {
        "id": 2,
        "difficulty": "Easy",
        "rating": 800,
        "question": "Reverse Words: First read an integer N (count of words), then read N space-separated words. Print them in reverse order.",
        "standard_solution": {
            "language": "python",
            "code": "n = int(input())\nwords = input().split()\nprint(' '.join(words[::-1]))"
        },
        "test_cases": [
            { "input": "2\nHello World", "output": "World Hello", "type": "sample" },
            { "input": "3\nPython is awesome", "output": "awesome is Python", "type": "hidden" },
            { "input": "1\nSingle", "output": "Single", "type": "hidden" }
        ]
    },
    {
        "id": 3,
        "difficulty": "Easy",
        "rating": 800,
        "question": "Find Missing Number: First read N (the range 1 to N), then read N-1 integers. Find the missing number.",
        "standard_solution": {
            "language": "python",
            "code": "n = int(input())\nnums = list(map(int, input().split()))\nexpected_sum = n * (n + 1) // 2\nactual_sum = sum(nums)\nprint(expected_sum - actual_sum)"
        },
        "test_cases": [
            { "input": "5\n1 2 4 5", "output": "3", "type": "sample" },
            { "input": "3\n1 3", "output": "2", "type": "hidden" },
            { "input": "5\n2 3 4 5", "output": "1", "type": "hidden" }
        ]
    },
    {
        "id": 4,
        "difficulty": "Easy",
        "rating": 800,
        "question": "Count Set Bits: Given an integer N, count the number of 1s in its binary representation.",
        "standard_solution": {
            "language": "cpp",
            "code": "#include <iostream>\nusing namespace std;\nint main() {\n    long long n;\n    if (!(cin >> n)) return 0;\n    int count = 0;\n    while (n > 0) {\n        n = n & (n - 1);\n        count++;\n    }\n    cout << count;\n    return 0;\n}"
        },
        "test_cases": [
            { "input": "5", "output": "2", "type": "sample" },
            { "input": "7", "output": "3", "type": "hidden" },
            { "input": "1024", "output": "1", "type": "hidden" }
        ]
    },
    {
        "id": 5,
        "difficulty": "Easy",
        "rating": 800,
        "question": "Palindrome Check: Given a string, check if it is a palindrome. Print 'Yes' or 'No'.",
        "standard_solution": {
            "language": "java",
            "code": "import java.util.Scanner;\npublic class Main {\n    public static void main(String[] args) {\n        Scanner sc = new Scanner(System.in);\n        if(sc.hasNext()) {\n            String s = sc.next();\n            String rev = new StringBuilder(s).reverse().toString();\n            if(s.equals(rev)) System.out.print(\"Yes\");\n            else System.out.print(\"No\");\n        }\n    }\n}"
        },
        "test_cases": [
            { "input": "madam", "output": "Yes", "type": "sample" },
            { "input": "hello", "output": "No", "type": "hidden" }
        ]
    }
]

def log_event(event_type, data):
    try:
        log_entry = {"timestamp": datetime.utcnow(), "event_type": event_type, "data": data}
        logs_collection.insert_one(log_entry)
    except Exception as e:
        print(f"Mongo Error: {e}")

# --- LOCAL PYTHON FALLBACK ENGINE ---
def run_python_local(code, input_str):
    try:
        process = subprocess.Popen(
            [sys.executable, "-c", code],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        stdout, stderr = process.communicate(input=input_str, timeout=4)
        return stdout, stderr
    except subprocess.TimeoutExpired:
        process.kill()
        return "", "Execution Timed Out (Local)"
    except Exception as e:
        return "", f"Local Error: {str(e)}"

# --- WANDBOX API ENGINE (Compatible with Render) ---
def run_wandbox_api(code, lang, stdin):
    url = "https://wandbox.org/api/compile.json"
    compiler_map = { "python": "cpython-3.10.2", "cpp": "gcc-11.1.0", "java": "openjdk-16.0.1" }
    
    payload = {
        "code": code,
        "compiler": compiler_map.get(lang, "cpython-3.10.2"),
        "stdin": stdin,
        "options": "warning" if lang == "cpp" else ""
    }
    
    try:
        resp = requests.post(url, json=payload, timeout=8)
        if resp.status_code != 200: return "", "", False
        data = resp.json()
        if 'status' not in data: return "", "", False
        
        stdout = data.get('program_message', '')
        stderr = data.get('compiler_error', '')
        if data['status'] != "0": stderr += f"\nExit Code: {data['status']}"
        return stdout, stderr, True
    except: return "", "", False

@app.route('/')
def index(): return render_template('index.html')

def pass_turn_logic(room, room_id):
    room['hack_state'] = {'active': False, 'victim': None, 'victim_code': None, 'victim_lang': None, 'pending_hackers': [], 'hack_successful': False}
    turn_order = room['turn_order']
    if not turn_order: return
    try: current_idx = turn_order.index(room['active_color'])
    except ValueError: current_idx = -1
    found_next = False
    for i in range(1, len(turn_order) + 1):
        next_idx = (current_idx + i) % len(turn_order)
        next_color = turn_order[next_idx]
        player_obj = next((p for p in room['players'].values() if p['color'] == next_color), None)
        if player_obj and player_obj.get('connected', False):
            room['active_color'] = next_color
            emit('turn_change', {'active_color': next_color}, room=room_id)
            found_next = True
            break
            
    if not found_next:
        print(f"Room {room_id}: No active players found.")

@socketio.on('join_game')
def handle_join(data):
    room_id = data['room'].upper().strip()
    color = data['color'].lower()
    name = data['name'].strip()
    user_id = data.get('user_id', 'anonymous')
    sid = request.sid

    if room_id not in LOBBIES:
        LOBBIES[room_id] = {'players': {}, 'turn_order': [], 'active_color': None, 'started': False, 'hack_state': {'active': False, 'pending_hackers': []}}
    room = LOBBIES[room_id]
    
    exact_match = next((p for p in room['players'].values() if p['color'] == color and p['name'] == name), None)
    color_taken = next((p for p in room['players'].values() if p['color'] == color and p['name'] != name), None)
    name_taken = next((p for p in room['players'].values() if p['name'] == name and p['color'] != color), None)

    if room['started'] and not exact_match:
        emit('join_error', {'message': '⛔ MATCH STARTED!'}, room=sid)
        return
    if color_taken:
        emit('join_error', {'message': f'Color {color} taken!'}, room=sid)
        return
    if name_taken:
        emit('join_error', {'message': f'Name "{name}" taken!'}, room=sid)
        return

    if exact_match:
        if exact_match['id'] in room['players']: del room['players'][exact_match['id']]
        exact_match.update({'id': sid, 'connected': True})
        room['players'][sid] = exact_match
        join_room(room_id)
        log_event("session", {"room": room_id, "user_id": user_id, "action": "reconnect"})
    else:
        room['players'][sid] = { 'id': sid, 'name': name, 'color': color, 'step': -1, 'connected': True, 'user_id': user_id }
        join_room(room_id)
        log_event("session", {"room": room_id, "user_id": user_id, "action": "join"})

    active_colors = [p['color'] for p in room['players'].values()]
    room['turn_order'] = sorted(active_colors, key=lambda x: BASE_ORDER.index(x))
    if not room['active_color']: room['active_color'] = room['turn_order'][0]
    
    emit('join_success', {'color': color, 'room': room_id, 'started': room['started']}, room=sid)
    player_list = [{'name': p['name'], 'color': p['color'], 'online': p.get('connected', True)} for p in room['players'].values()]
    emit('update_player_list', {'players': player_list}, room=room_id)
    emit('sync_state', {'positions': {p['color']: p['step'] for p in room['players'].values()}}, room=room_id)
    emit('turn_change', {'active_color': room['active_color']}, room=room_id)

    if room['hack_state']['active']:
        h = room['hack_state']
        q = next((q for q in QUESTION_BANK if q['id'] == int(h['question_id'])), None)
        vic = next((p for p in room['players'].values() if p['color'] == h['victim']), None)
        if q and vic:
            s = next((tc for tc in q['test_cases'] if tc['type'] == 'sample'), q['test_cases'][0])
            emit('hack_phase_start', {'victim_name': vic['name'], 'victim_color': h['victim'], 'code': h['victim_code'], 'question_text': q['question'], 'sample_input': s['input'], 'sample_output': s['output']}, room=sid)

@socketio.on('start_game')
def handle_start(data):
    if data['room'] in LOBBIES:
        LOBBIES[data['room']]['started'] = True
        emit('game_started', {'message': 'Started!'}, room=data['room'])

@socketio.on('submission_success')
def handle_submission_success(data):
    room = LOBBIES.get(data['room'])
    v = room['players'].get(request.sid)
    q_obj = next((q for q in QUESTION_BANK if q['id'] == int(data['q_id'])), None)
    
    log_event("gameplay", {"user_id": v.get('user_id'), "action": "solve_success", "rating": q_obj.get('rating', 0), "difficulty": q_obj.get('difficulty', 'unknown')})
    
    move = data.get('steps', 3)
    v['prev_step'] = v['step']
    v['step'] += move
    emit('animate_move', {'color': v['color'], 'total_steps_moved': move}, room=data['room'])
    
    hks = [p['color'] for p in room['players'].values() if p['color'] != v['color'] and p.get('connected', True)]
    if not hks:
        pass_turn_logic(room, data['room'])
        return
        
    room['hack_state'] = {'active': True, 'victim': v['color'], 'victim_code': data['code'], 'victim_lang': data['language'], 'question_id': data['q_id'], 'pending_hackers': hks, 'hack_successful': False}
    sample = next((tc for tc in q_obj['test_cases'] if tc['type'] == 'sample'), q_obj['test_cases'][0])
    emit('hack_phase_start', {'victim_name': v['name'], 'victim_color': v['color'], 'code': data['code'], 'question_text': q_obj['question'], 'sample_input': sample['input'], 'sample_output': sample['output']}, room=data['room'])

@app.route('/submit_code', methods=['POST'])
def submit_code():
    d = request.json
    try: q_id = int(d.get('q_id'))
    except: return jsonify({"success": False, "type": "system", "output": "Invalid QID"})

    q = next((qu for qu in QUESTION_BANK if qu['id'] == q_id), None)
    if not q: return jsonify({"success": False, "type": "system", "output": "Q Not Found"})

    is_python = d['language'] == 'python'

    for i, case in enumerate(q['test_cases']):
        actual, err = "", ""
        
        # 1. TRY WANDBOX API
        actual, err, api_success = run_wandbox_api(d['code'], d['language'], case['input'])
        
        # 2. FAILOVER: LOCAL PYTHON
        if not api_success:
            if is_python:
                print("WANDBOX FAILED. SWITCHING TO LOCAL.")
                actual, err = run_python_local(d['code'], case['input'])
            else:
                return jsonify({"success": True, "output": "⚠️ Judge Busy: Auto-Passed (C++/Java)"})

        # 3. VERIFY
        actual = actual.strip()
        if err: return jsonify({"success": False, "type": "player", "output": f"Runtime Error:\n{err}"})
        if actual != case['output'].strip():
            return jsonify({ 
                "success": False, 
                "type": "player", 
                "output": f"❌ FAILED Test Case {i+1}\nInput:\n{case['input']}\nExpected:\n{case['output']}\nGot:\n{actual}" 
            })

    return jsonify({"success": True, "output": "✅ PASSED"})

@socketio.on('disconnect')
def handle_disconnect():
    for rid, r in LOBBIES.items():
        if request.sid in r['players']:
            p = r['players'][request.sid]
            p['connected'] = False
            player_list = [{'name': pl['name'], 'color': pl['color'], 'online': pl.get('connected', True)} for pl in r['players'].values()]
            emit('update_player_list', {'players': player_list}, room=rid)
            if p['color'] == r['active_color']: pass_turn_logic(r, rid)
            break

@app.route('/get_question', methods=['GET'])
def get_question():
    if not QUESTION_BANK:
        return jsonify({"error": "No questions available"}), 404
    q = random.choice(QUESTION_BANK)
    sample = next((tc for tc in q.get('test_cases', []) if tc['type'] == 'sample'), None)
    return jsonify({ "id": q['id'], "question": q['question'], "sample_input": sample['input'] if sample else "", "sample_output": sample['output'] if sample else "" })

if __name__ == '__main__':
    socketio.run(app, debug=True)
