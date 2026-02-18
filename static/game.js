function getUserId() {
    let uid = localStorage.getItem("geek_ludo_uid");
    if (!uid) {
        uid = 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
            var r = Math.random() * 16 | 0, v = c == 'x' ? r : (r & 0x3 | 0x8);
            return v.toString(16);
        });
        localStorage.setItem("geek_ludo_uid", uid);
    }
    return uid;
}
const USER_ID = getUserId();
const socket = io();
let myColor = null, myTurn = false, currentRoom = null, currentQuestionId = null;
let playerPositions = { 'red': -1, 'green': -1, 'yellow': -1, 'blue': -1 };

var myEditor = CodeMirror.fromTextArea(document.getElementById("code-editor"), {
    lineNumbers: true, mode: "python", theme: "dracula", lineWrapping: true
});

const paths = {
    'red': [[7,2],[7,3],[7,4],[7,5],[7,6],[6,7],[5,7],[4,7],[3,7],[2,7],[1,7],[1,8],[1,9],[2,9],[3,9],[4,9],[5,9],[6,9],[7,10],[7,11],[7,12],[7,13],[7,14],[7,15],[8,15],[9,15],[9,14],[9,13],[9,12],[9,11],[9,10],[10,9],[11,9],[12,9],[13,9],[14,9],[15,9],[15,8],[15,7],[14,7],[13,7],[12,7],[11,7],[10,7],[9,6],[9,5],[9,4],[9,3],[9,2],[9,1],[8,1],[8,2],[8,3],[8,4],[8,5],[8,6],[8,7]],
    'green': [[2,9],[3,9],[4,9],[5,9],[6,9],[7,10],[7,11],[7,12],[7,13],[7,14],[7,15],[8,15],[9,15],[9,14],[9,13],[9,12],[9,11],[9,10],[10,9],[11,9],[12,9],[13,9],[14,9],[15,9],[15,8],[15,7],[14,7],[13,7],[12,7],[11,7],[10,7],[9,6],[9,5],[9,4],[9,3],[9,2],[9,1],[8,1],[7,1],[7,2],[7,3],[7,4],[7,5],[7,6],[6,7],[5,7],[4,7],[3,7],[2,7],[1,7],[1,8],[2,8],[3,8],[4,8],[5,8],[6,8],[7,8]],
    'yellow': [[9,14],[9,13],[9,12],[9,11],[9,10],[10,9],[11,9],[12,9],[13,9],[14,9],[15,9],[15,8],[15,7],[14,7],[13,7],[12,7],[11,7],[10,7],[9,6],[9,5],[9,4],[9,3],[9,2],[9,1],[8,1],[7,1],[7,2],[7,3],[7,4],[7,5],[7,6],[6,7],[5,7],[4,7],[3,7],[2,7],[1,7],[1,8],[1,9],[2,9],[3,9],[4,9],[5,9],[6,9],[7,10],[7,11],[7,12],[7,13],[7,14],[7,15],[8,15],[8,14],[8,13],[8,12],[8,11],[8,10],[8,9]],
    'blue': [[14,7],[13,7],[12,7],[11,7],[10,7],[9,6],[9,5],[9,4],[9,3],[9,2],[9,1],[8,1],[7,1],[7,2],[7,3],[7,4],[7,5],[7,6],[6,7],[5,7],[4,7],[3,7],[2,7],[1,7],[1,8],[1,9],[2,9],[3,9],[4,9],[5,9],[6,9],[7,10],[7,11],[7,12],[7,13],[7,14],[7,15],[8,15],[9,15],[9,14],[9,13],[9,12],[9,11],[9,10],[10,9],[11,9],[12,9],[13,9],[14,9],[15,9],[15,8],[14,8],[13,8],[12,8],[11,8],[10,8],[9,8]]
};

window.onload = function() {
    document.getElementById('player-name').value = localStorage.getItem('geek_ludo_name') || "";
    document.getElementById('room-code').value = localStorage.getItem('geek_ludo_room') || "";
}

function joinGame(color) {
    const n = document.getElementById('player-name').value, r = document.getElementById('room-code').value;
    if(!n || !r) return;
    localStorage.setItem('geek_ludo_name', n); localStorage.setItem('geek_ludo_room', r);
    socket.emit('join_game', { name: n, color: color, room: r, user_id: USER_ID });
}

function startGame() { socket.emit('start_game', { room: currentRoom }); }

socket.on('join_success', (data) => {
    myColor = data.color; currentRoom = data.room;
    document.getElementById('lobby-waiting-area').style.display = 'block';
    document.getElementById('start-btn').style.display = data.started ? 'none' : 'block';
});

socket.on('game_started', (data) => { document.getElementById('lobby-modal').style.display = 'none'; });

socket.on('update_player_list', (data) => {
    const sl = document.getElementById('player-list'); sl.innerHTML = "";
    data.players.forEach(p => {
        const item = document.createElement('div');
        item.style.color = p.online ? getHexColor(p.color) : "#7f8c8d";
        item.innerText = `● ${p.name.toUpperCase()} (${p.color.toUpperCase()})`;
        sl.appendChild(item);
    });
});

socket.on('sync_state', (data) => { playerPositions = data.positions; renderBoard(); });

socket.on('turn_change', (data) => {
    const bar = document.getElementById('turn-indicator');
    bar.innerText = `TURN: ${data.active_color.toUpperCase()}`;
    bar.style.backgroundColor = getHexColor(data.active_color);
    myTurn = (data.active_color === myColor);
    document.getElementById('roll-btn').disabled = !myTurn;
});

socket.on('animate_move', (data) => {
    const dist = Math.abs(data.total_steps_moved), dir = data.total_steps_moved > 0 ? 1 : -1;
    let s = 0;
    const loop = setInterval(() => {
        playerPositions[data.color] += dir; renderBoard(); s++;
        if(s >= dist) clearInterval(loop);
    }, 300);
});

socket.on('hack_phase_start', (data) => {
    if (myColor === data.victim_color) return;
    document.getElementById('hack-interface').style.display = 'flex';
    document.getElementById('victim-code-display').value = data.code;
    document.getElementById('hack-q-text').innerText = data.question_text;
    document.getElementById('hack-sample-in').innerText = data.sample_input;
    document.getElementById('hack-sample-out').innerText = data.sample_output;
});

async function openQuestion() {
    if(!myTurn) return;
    document.getElementById('question-modal').style.display = 'flex';
    const res = await fetch('/get_question');
    const d = await res.json();
    currentQuestionId = d.id;
    document.getElementById('q-text').innerText = d.question;
    document.getElementById('sample-in').innerText = d.sample_input;
    document.getElementById('sample-out').innerText = d.sample_output;
}

async function runCode() {
    const code = myEditor.getValue(), lang = document.getElementById('language-select').value;
    const res = await fetch('/submit_code', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ code: code, q_id: currentQuestionId, language: lang }) });
    const result = await res.json();
    if (result.success) {
        let steps = document.getElementById('mode-toggle').checked ? Math.floor(Math.random() * 6) + 1 : 3;
        socket.emit('submission_success', { room: currentRoom, code: code, language: lang, q_id: currentQuestionId, steps: steps });
        document.getElementById('question-modal').style.display = 'none';
    }
}

function handleSuccess(steps) { socket.emit('player_move', { steps: steps, room: currentRoom }); }

function renderBoard() {
    document.querySelectorAll('.player-piece').forEach(e => e.remove());
    Object.keys(playerPositions).forEach(c => {
        const step = playerPositions[c], path = paths[c];
        if (step >= 0 && step < path.length) {
            const token = document.createElement('div');
            token.className = `player-piece piece-${c}`;
            token.style.gridRow = path[step][0]; token.style.gridColumn = path[step][1];
            document.getElementById('board').appendChild(token);
        }
    });
}

function getHexColor(c) { return {red:'#e74c3c', green:'#2ecc71', blue:'#3498db', yellow:'#f1c40f'}[c]; }
