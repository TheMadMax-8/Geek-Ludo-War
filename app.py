from gevent import monkey
monkey.patch_all()
import json
import random
import requests
import os
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit, join_room
from pymongo import MongoClient

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins="*")

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
    log_entry = {"timestamp": datetime.utcnow(), "event_type": event_type, "data": data}
    try:
        logs_collection.insert_one(log_entry)
    except Exception as e:
        print(f"Mongo Error: {e}")

def load_questions():
    try:
        with open('questions.json', 'r') as f: return json.load(f)
    except: return []

QUESTION_BANK = load_questions()

@app.route('/')
def index(): return render_template('index.html')

def pass_turn_logic(room, room_id):
    room['hack_state'] = {
        'active': False, 'victim': None, 'victim_code': None, 'victim_lang': None,
        'pending_hackers': [], 'hack_successful': False 
    }
    turn_order = room['turn_order']
    if not turn_order: return
    try:
        current_idx = turn_order.index(room['active_color'])
    except ValueError:
        current_idx = -1
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

@socketio.on('join_game')
def handle_join(data):
    room_id = data['room'].upper().strip()
    color = data['color'].lower()
    name = data['name'].strip()
    user_id = data.get('user_id', 'anonymous')
    sid = request.sid
    if room_id not in LOBBIES:
        LOBBIES[room_id] = {
            'players': {}, 'turn_order': [], 'active_color': None, 'started': False,
            'hack_state': { 'active': False, 'pending_hackers': [] }
        }
    room = LOBBIES[room_id]
    exact_match = next((p for p in room['players'].values() if p['color'] == color and p['name'] == name), None)
    color_taken = next((p for p in room['players'].values() if p['color'] == color and p['name'] != name), None)
    name_taken = next((p for p in room['players'].values() if p['name'] == name and p['color'] != color), None)
    if room['started'] and not exact_match:
        emit('join_error', {'message': f'⛔ MATCH STARTED!'}, room=sid)
        return
    if color_taken:
        emit('join_error', {'message': f'Color {color} taken!'}, room=sid)
        return
    if name_taken:
        emit('join_error', {'message': f'Name "{name}" taken!'}, room=sid)
        return
    if exact_match:
        if exact_match['id'] in room['players']:
            del room['players'][exact_match['id']]
        exact_match['id'] = sid
        exact_match['connected'] = True
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
        q_obj = next((q for q in QUESTION_BANK if q['id'] == int(h['question_id'])), None)
        if q_obj:
            sample = next((tc for tc in q_obj['test_cases'] if tc['type'] == 'sample'), q_obj['test_cases'][0])
            emit('hack_phase_start', {'victim_name': next(p['name'] for p in room['players'].values() if p['color'] == h['victim']), 'victim_color': h['victim'], 'code': h['victim_code'], 'question_text': q_obj['question'], 'sample_input': sample['input'], 'sample_output': sample['output']}, room=sid)

@socketio.on('start_game')
def handle_start(data):
    if data['room'] in LOBBIES:
        LOBBIES[data['room']]['started'] = True
        emit('game_started', {'message': 'The Game has Begun!'}, room=data['room'])
        log_event("session", {"room": data['room'], "action": "game_start"})

@socketio.on('disconnect')
def handle_disconnect():
    for rid, r in LOBBIES.items():
        if request.sid in r['players']:
            p = r['players'][request.sid]
            p['connected'] = False
            emit('update_player_list', {'players': [{'name': pl['name'], 'color': pl['color'], 'online': pl.get('connected', True)} for pl in r['players'].values()]}, room=rid)
            if p['color'] == r['active_color']: pass_turn_logic(r, rid)
            break

@socketio.on('submission_success')
def handle_submission_success(data):
    room = LOBBIES.get(data['room'])
    v = room['players'].get(request.sid)
    q_obj = next((q for q in QUESTION_BANK if q['id'] == int(data['q_id'])), None)
    log_event("gameplay", {"user_id": v.get('user_id'), "action": "solve_success", "rating": q_obj.get('rating', 0), "difficulty": q_obj.get('difficulty', 'unknown'), "language": data['language']})
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

@socketio.on('submit_hack_attempt')
def handle_hack_attempt(data):
    room = LOBBIES.get(data['room'])
    hkr = room['players'][request.sid]
    v = next(p for p in room['players'].values() if p['color'] == room['hack_state']['victim'])
    if hkr['color'] in room['hack_state']['pending_hackers']: room['hack_state']['pending_hackers'].remove(hkr['color'])
    if data['action'] == 'hack':
        q_obj = next(q for q in QUESTION_BANK if q['id'] == int(room['hack_state']['question_id']))
        std_out, std_err = run_code_piston(q_obj['standard_solution']['code'], q_obj['standard_solution']['language'], data['input'])
        if not std_err and std_out.strip() == data['expected'].strip():
            v_out, v_err = run_code_piston(room['hack_state']['victim_code'], room['hack_state']['victim_lang'], data['input'])
            if v_err or v_out.strip() != data['expected'].strip():
                hkr['step'] += 2
                emit('animate_move', {'color': hkr['color'], 'total_steps_moved': 2}, room=data['room'])
                if not room['hack_state']['hack_successful']:
                    room['hack_state']['hack_successful'] = True
                    target = v['prev_step'] if v['prev_step'] in SAFE_INDICES else v['prev_step'] - 3
                    v['step'] = max(-1, target)
                    emit('animate_move', {'color': v['color'], 'total_steps_moved': v['step'] - (v['prev_step'] + 3)}, room=data['room'])
                log_event("hack", {"hacker": hkr.get('user_id'), "victim": v.get('user_id'), "result": "success"})
            else:
                hkr['step'] = max(-1, hkr['step'] - 2)
                emit('animate_move', {'color': hkr['color'], 'total_steps_moved': -2}, room=data['room'])
                log_event("hack", {"hacker": hkr.get('user_id'), "victim": v.get('user_id'), "result": "fail_survival"})
        else:
            hkr['step'] = max(-1, hkr['step'] - 2)
            emit('animate_move', {'color': hkr['color'], 'total_steps_moved': -2}, room=data['room'])
            log_event("hack", {"hacker": hkr.get('user_id'), "victim": v.get('user_id'), "result": "invalid_input"})
    if not room['hack_state']['pending_hackers']:
        emit('hack_phase_end', {}, room=data['room'])
        pass_turn_logic(room, data['room'])

def run_code_piston(code, lang, stdin):
    v_map = { "python": "3.10.0", "cpp": "10.2.0", "java": "15.0.2" }
    url = "https://emkc.org/api/v2/piston/execute"
    payload = { "language": lang, "version": v_map.get(lang, "3.10.0"), "files": [{"content": code}], "stdin": stdin }
    try:
        r = requests.post(url, json=payload).json()
        return r['run']['stdout'], r['run']['stderr']
    except: return "", "Error"

@socketio.on('player_move')
def handle_move(data):
    room = LOBBIES.get(data['room'])
    p = room['players'].get(request.sid)
    st = data['steps']
    if st < 0 and p['step'] in SAFE_INDICES: st = 0
    p['step'] = max(-1, p['step'] + st)
    emit('animate_move', {'color': p['color'], 'total_steps_moved': st}, room=data['room'])
    pass_turn_logic(room, data['room'])

@app.route('/get_question', methods=['GET'])
def get_question():
    q = random.choice(QUESTION_BANK)
    s = next((tc for tc in q.get('test_cases', []) if tc['type'] == 'sample'), q['test_cases'][0])
    return jsonify({ "id": q['id'], "question": q['question'], "sample_input": s['input'], "sample_output": s['output'] })

@app.route('/submit_code', methods=['POST'])
def submit_code():
    d = request.json
    q = next(qu for qu in QUESTION_BANK if qu['id'] == d['q_id'])
    v_map = { "python": "3.10.0", "cpp": "10.2.0", "java": "15.0.2" }
    for c in q['test_cases']:
        res = requests.post("https://emkc.org/api/v2/piston/execute", json={"language": d['language'], "version": v_map.get(d['language'], "3.10.0"), "files": [{"content": d['code']}], "stdin": c['input']}).json()
        if res['run']['stderr'] or res['run']['stdout'].strip() != c['output'].strip(): return jsonify({"success": False, "output": "Failed"})
    return jsonify({"success": True})

if __name__ == '__main__': socketio.run(app, debug=True)
