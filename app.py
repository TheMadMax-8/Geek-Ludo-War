from gevent import monkey
monkey.patch_all()

import json
import random
import requests
import time
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
    log_entry = {
        "timestamp": datetime.utcnow(),
        "event_type": event_type,
        "data": data
    }
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
        LOBBIES[room_id] = {
            'players': {}, 'turn_order': [], 'active_color': None, 'started': False,
            'hack_state': { 'active': False, 'pending_hackers': [] }
        }
    
    room = LOBBIES[room_id]
    
    exact_match = next((p for p in room['players'].values() if p['color'] == color and p['name'] == name), None)
    color_taken = next((p for p in room['players'].values() if p['color'] == color and p['name'] != name), None)
    name_taken = next((p for p in room['players'].values() if p['name'] == name and p['color'] != color), None)

    if room['started'] and not exact_match:
        emit('join_error', {'message': f'⛔ MATCH STARTED! No new players allowed.'}, room=sid)
        return

    if color_taken:
        emit('join_error', {'message': f'Color {color} taken by {color_taken["name"]}!'}, room=sid)
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
    current_positions = {p['color']: p['step'] for p in room['players'].values()}
    emit('sync_state', {'positions': current_positions}, room=room_id)
    emit('turn_change', {'active_color': room['active_color']}, room=room_id)

    if room['hack_state']['active']:
        h_state = room['hack_state']
        q_obj = next((q for q in QUESTION_BANK if q['id'] == int(h_state['question_id'])), None)
        q_text, s_in, s_out = "Loading...", "", ""
        if q_obj:
            q_text = q_obj['question']
            sample = next((tc for tc in q_obj['test_cases'] if tc['type'] == 'sample'), None)
            if sample: s_in, s_out = sample['input'], sample['output']
        
        vic_obj = next((p for p in room['players'].values() if p['color'] == h_state['victim']), None)
        vic_name = vic_obj['name'] if vic_obj else "Unknown"

        emit('hack_phase_start', {
            'victim_name': vic_name,
            'victim_color': h_state['victim'],
            'code': h_state['victim_code'],
            'question_text': q_text,
            'sample_input': s_in,
            'sample_output': s_out
        }, room=sid)

@socketio.on('start_game')
def handle_start(data):
    if data['room'] in LOBBIES:
        LOBBIES[data['room']]['started'] = True
        emit('game_started', {'message': 'The Game has Begun!'}, room=data['room'])
        log_event("session", {"room": data['room'], "action": "game_start"})

@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    for room_id, room in LOBBIES.items():
        if sid in room['players']:
            player = room['players'][sid]
            player['connected'] = False
            
            player_list = [{'name': p['name'], 'color': p['color'], 'online': False} if p['id'] == sid else {'name': p['name'], 'color': p['color'], 'online': p.get('connected', True)} for p in room['players'].values()]
            emit('update_player_list', {'players': player_list}, room=room_id)
            
            if player['color'] == room['active_color']:
                pass_turn_logic(room, room_id)
            break

@socketio.on('submission_success')
def handle_submission_success(data):
    room_id = data['room']
    if room_id not in LOBBIES: return
    room = LOBBIES[room_id]
    victim = room['players'].get(request.sid)

    q_obj = next((q for q in QUESTION_BANK if q['id'] == int(data['q_id'])), None)
    difficulty = q_obj.get('difficulty', 'unknown') if q_obj else 'unknown'
    rating = q_obj.get('rating', 0) if q_obj else 0

    log_event("gameplay", {
        "room": room_id,
        "user_id": victim.get('user_id'),
        "action": "solve_success",
        "difficulty": difficulty,
        "rating": rating,
        "language": data.get('language')
    })

    move_amount = data.get('steps', 3)
    
    victim['prev_step'] = victim['step'] 
    victim['step'] += move_amount 
    
    emit('animate_move', {'color': victim['color'], 'total_steps_moved': move_amount}, room=room_id)
    
    hackers = [p['color'] for p in room['players'].values() if p['color'] != victim['color'] and p.get('connected', True)]
    
    if not hackers:
        pass_turn_logic(room, room_id)
        return

    room['hack_state'] = {
        'active': True, 'victim': victim['color'], 'victim_code': data['code'],
        'victim_lang': data['language'], 'question_id': data['q_id'],
        'pending_hackers': hackers, 'hack_successful': False
    }

    q_text = "Loading..."
    sample_in = "No Input Found"
    sample_out = "No Output Found"

    if q_obj:
        q_text = q_obj.get('question', 'Unknown Question')
        test_cases = q_obj.get('test_cases', [])
        
        sample = next((tc for tc in test_cases if tc.get('type') == 'sample'), None)
        
        if not sample and len(test_cases) > 0:
            sample = test_cases[0]

        if sample:
            sample_in = sample.get('input', 'Empty')
            sample_out = sample.get('output', 'Empty')

    emit('hack_phase_start', {
        'victim_name': victim['name'], 'victim_color': victim['color'],
        'code': data['code'], 'question_text': q_text,
        'sample_input': sample_in, 'sample_output': sample_out
    }, room=room_id)

@socketio.on('submit_hack_attempt')
def handle_hack_attempt(data):
    room_id = data['room']
    action = data['action'] 
    hacker_input = data.get('input', '')
    hacker_expected = data.get('expected', '')
    
    room = LOBBIES[room_id]
    hacker = room['players'][request.sid]
    victim_color = room['hack_state']['victim']
    victim = next((p for p in room['players'].values() if p['color'] == victim_color), None)

    if hacker['color'] in room['hack_state']['pending_hackers']:
        room['hack_state']['pending_hackers'].remove(hacker['color'])

    if action == 'skip':
        emit('hack_log', {'message': f"{hacker['name']} skipped."}, room=room_id)
        log_event("hack", {"hacker": hacker.get('user_id'), "victim": victim.get('user_id'), "action": "skip"})

    elif action == 'hack':
        q_id = room['hack_state'].get('question_id')
        question_obj = next((q for q in QUESTION_BANK if q['id'] == int(q_id)), None)
        is_hack_valid = False
        
        if question_obj and 'standard_solution' in question_obj:
            std_sol = question_obj['standard_solution']
            std_out, std_err = run_code_piston(std_sol['code'], std_sol['language'], hacker_input)
            if not std_err and std_out.strip() == hacker_expected.strip():
                is_hack_valid = True
        
        if not is_hack_valid:
            hacker['step'] -= 2
            if hacker['step'] < -1: hacker['step'] = -1
            emit('animate_move', {'color': hacker['color'], 'total_steps_moved': -2}, room=room_id)
            emit('hack_log', {'message': f"🚫 INVALID HACK! Expected output incorrect. (-2)"}, room=room_id)
            log_event("hack", {"hacker": hacker.get('user_id'), "victim": victim.get('user_id'), "action": "fail_invalid"})
        else:
            vic_out, vic_err = run_code_piston(room['hack_state']['victim_code'], room['hack_state']['victim_lang'], hacker_input)
            
            if vic_err or vic_out.strip() != hacker_expected.strip():
                hacker['step'] += 2
                emit('animate_move', {'color': hacker['color'], 'total_steps_moved': 2}, room=room_id)
                emit('hack_log', {'message': f"⚔️ {hacker['name']} SUCCESS! (+2)"}, room=room_id)
                log_event("hack", {"hacker": hacker.get('user_id'), "victim": victim.get('user_id'), "action": "success"})
                
                if not room['hack_state']['hack_successful']:
                    room['hack_state']['hack_successful'] = True
                    
                    was_safe = victim['prev_step'] in SAFE_INDICES
                    
                    old_pos = victim['step']
                    target_pos = victim['prev_step'] 
                    
                    if was_safe:
                        msg = f"🛡️ {victim['name']} BLOCKED PENALTY (Safe Spot)!"
                    else:
                        target_pos -= 3
                        if target_pos < -1: target_pos = -1
                        msg = f"💔 SOLUTION CRASHED! {victim['name']} penalized (-3)."

                    emit('animate_move', {'color': victim['color'], 'total_steps_moved': target_pos - old_pos}, room=room_id)
                    victim['step'] = target_pos
                    emit('checkpoint_alert', {'message': msg}, room=room_id)
            else:
                hacker['step'] -= 2
                if hacker['step'] < -1: hacker['step'] = -1
                emit('animate_move', {'color': hacker['color'], 'total_steps_moved': -2}, room=room_id)
                emit('hack_log', {'message': f"🛡️ Hack Failed. Victim code works. (-2)"}, room=room_id)
                log_event("hack", {"hacker": hacker.get('user_id'), "victim": victim.get('user_id'), "action": "fail_survival"})

    if not room['hack_state']['pending_hackers']:
        emit('hack_phase_end', {}, room=room_id)
        pass_turn_logic(room, room_id)

def run_code_piston(code, lang, stdin):
    version_map = { "python": "3.10.0", "cpp": "10.2.0", "java": "15.0.2" }
    url = "https://emkc.org/api/v2/piston/execute"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Content-Type": "application/json"
    }
    payload = { "language": lang, "version": version_map.get(lang, "3.10.0"), "files": [{"content": code}], "stdin": stdin }
    
    for attempt in range(3):
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if 'run' in data: return data['run']['stdout'], data['run']['stderr']
            time.sleep(1)
        except:
            time.sleep(1)
            
    return "", "System Error: Runner Busy"

@socketio.on('player_move')
def handle_move(data):
    room_id = data.get('room')
    steps = data.get('steps')
    sid = request.sid
    if not room_id or room_id not in LOBBIES: return
    room = LOBBIES[room_id]
    player = room['players'].get(sid)
    if not player or player['color'] != room['active_color']: return

    if steps < 0 and player['step'] in SAFE_INDICES:
        emit('checkpoint_alert', {'message': f"🛡️ {player['name']} IS SAFE!"}, room=room_id)
        steps = 0
    
    player['step'] += steps
    if player['step'] < -1: player['step'] = -1
    emit('animate_move', {'color': player['color'], 'total_steps_moved': steps}, room=room_id)
    pass_turn_logic(room, room_id)

@app.route('/get_question', methods=['GET'])
def get_question():
    if not QUESTION_BANK: return jsonify({"error": "No questions!"}), 404
    q = random.choice(QUESTION_BANK)
    sample = next((tc for tc in q.get('test_cases', []) if tc['type'] == 'sample'), None)
    return jsonify({ "id": q['id'], "question": q['question'], "sample_input": sample['input'] if sample else "", "sample_output": sample['output'] if sample else "" })

@app.route('/submit_code', methods=['POST'])
def submit_code():
    d = request.json
    try:
        q_id = int(d.get('q_id'))
    except:
        return jsonify({"success": False, "type": "system", "output": "Invalid QID"})

    q = next((qu for qu in QUESTION_BANK if qu['id'] == q_id), None)
    if not q: 
        return jsonify({"success": False, "type": "system", "output": "Question Not Found"})

    version_map = { "python": "3.10.0", "cpp": "10.2.0", "java": "15.0.2" }
    url = "https://emkc.org/api/v2/piston/execute"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Content-Type": "application/json"
    }

    test_cases = q.get('test_cases', [])

    for i, case in enumerate(test_cases):
        payload = { 
            "language": d['language'], 
            "version": version_map.get(d['language'], "3.10.0"), 
            "files": [{"content": d['code']}], 
            "stdin": case['input'] 
        }
        
        success = False
        last_error = ""

        for attempt in range(3):
            try:
                response = requests.post(url, json=payload, headers=headers, timeout=5)
                
                if response.status_code == 200:
                    result = response.json()
                    if 'run' in result:
                        actual = result['run']['stdout'].strip()
                        err = result['run']['stderr']
                        
                        if err: 
                            return jsonify({"success": False, "type": "player", "output": f"Runtime Error on Test Case {i+1}:\n{err}"})
                        
                        if actual != case['output'].strip():
                            return jsonify({ 
                                "success": False, 
                                "type": "player", 
                                "output": f"❌ FAILED Test Case {i+1}\nInput:\n{case['input']}\nExpected:\n{case['output']}\nGot:\n{actual}" 
                            })
                        
                        success = True
                        break
            
                time.sleep(1)
            except Exception as e:
                last_error = str(e)
                time.sleep(1)
        
        if not success:
            print(f"FAILED after 3 retries. Last error: {last_error}")
            return jsonify({"success": False, "type": "system", "output": "System Busy: Please Click Run Again"})
    
    response = jsonify({"success": True, "output": "✅ PASSED"})
    response.headers.add('Access-Control-Allow-Origin', '*')
    return response

if __name__ == '__main__':
    socketio.run(app, debug=True)
