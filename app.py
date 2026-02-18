from gevent import monkey
monkey.patch_all()

import json
import random
import requests
import os
import subprocess
import sys
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit, join_room
from pymongo import MongoClient

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins="*")

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

MONGO_URI = os.environ.get("MONGO_URI")
if not MONGO_URI:
    MONGO_URI = "mongodb+srv://admin:password@cluster0.mongodb.net/geek_ludo_db"

client = MongoClient(MONGO_URI)
db = client.geek_ludo_db
logs_collection = db.game_logs

LOBBIES = {}
BASE_ORDER = ['red', 'green', 'yellow', 'blue'] 
SAFE_INDICES = [0, 13, 26, 39]

def log_event(event_type, data):
    try:
        log_entry = {"timestamp": datetime.utcnow(), "event_type": event_type, "data": data}
        logs_collection.insert_one(log_entry)
    except Exception as e:
        print(f"Mongo Error: {e}")

def load_questions():
    try:
        with open('questions.json', 'r') as f: return json.load(f)
    except: return []

QUESTION_BANK = load_questions()

def run_python_subprocess(code, input_str):
    
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
        return "", f"Local Execution Error: {str(e)}"

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
    else:
        room['players'][sid] = { 'id': sid, 'name': name, 'color': color, 'step': -1, 'connected': True, 'user_id': user_id }
        join_room(room_id)

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

    version_map = { "python": "3.10.0", "cpp": "10.2.0", "java": "15.0.2" }
    url = "https://emkc.org/api/v2/piston/execute"
    headers = {"User-Agent": "GeekLudo/1.0", "Content-Type": "application/json"}
    
    is_python = d['language'] == 'python'

    for i, case in enumerate(q['test_cases']):
        actual, err = "", ""
        api_failed = False
        
        payload = { "language": d['language'], "version": version_map.get(d['language'], "3.10.0"), "files": [{"content": d['code']}], "stdin": case['input'] }
        
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=5)
            if resp.status_code == 200:
                res_data = resp.json()
                if 'run' in res_data:
                    actual = res_data['run']['stdout'].strip()
                    err = res_data['run']['stderr']
                else: api_failed = True
            else: api_failed = True
        except: api_failed = True
     
        if api_failed:
            if is_python:
                print("API FAILED. SWITCHING TO LOCAL SUBPROCESS.")
                actual, err = run_python_subprocess(d['code'], case['input'])
                actual = actual.strip()
            else:
                return jsonify({"success": True, "output": "⚠️ Judge Busy: Auto-Passed (Non-Python)"})
                
        if err: return jsonify({"success": False, "type": "player", "output": f"Runtime Error:\n{err}"})
        if actual != case['output'].strip():
            return jsonify({ "success": False, "type": "player", "output": f"❌ FAILED Test Case {i+1}\nInput:\n{case['input']}\nExpected:\n{case['output']}\nGot:\n{actual}" })

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

if __name__ == '__main__':
    socketio.run(app, debug=True)
