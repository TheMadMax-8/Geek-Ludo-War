var myEditor = CodeMirror.fromTextArea(document.getElementById("code-editor"), {
    lineNumbers: true, mode: "python", theme: "dracula", lineWrapping: true
});

const socket = io();
let myColor = null;
let myTurn = false;
let currentRoom = null;
let currentQuestionId = null;

const paths = {
    'red': [[7, 2], [7, 3], [7, 4], [7, 5], [7, 6], [6, 7], [5, 7], [4, 7], [3, 7], [2, 7], [1, 7], [1, 8], [1, 9], [2, 9], [3, 9], [4, 9], [5, 9], [6, 9], [7, 10], [7, 11], [7, 12], [7, 13], [7, 14], [7, 15], [8, 15], [9, 15], [9, 14], [9, 13], [9, 12], [9, 11], [9, 10], [10, 9], [11, 9], [12, 9], [13, 9], [14, 9], [15, 9], [15, 8], [15, 7], [14, 7], [13, 7], [12, 7], [11, 7], [10, 7], [9, 6], [9, 5], [9, 4], [9, 3], [9, 2], [9, 1], [8, 1], [8, 2], [8, 3], [8, 4], [8, 5], [8, 6], [8, 7]],
    'green': [[2, 9], [3, 9], [4, 9], [5, 9], [6, 9], [7, 10], [7, 11], [7, 12], [7, 13], [7, 14], [7, 15], [8, 15], [9, 15], [9, 14], [9, 13], [9, 12], [9, 11], [9, 10], [10, 9], [11, 9], [12, 9], [13, 9], [14, 9], [15, 9], [15, 8], [15, 7], [14, 7], [13, 7], [12, 7], [11, 7], [10, 7], [9, 6], [9, 5], [9, 4], [9, 3], [9, 2], [9, 1], [8, 1], [7, 1], [7, 2], [7, 3], [7, 4], [7, 5], [7, 6], [6, 7], [5, 7], [4, 7], [3, 7], [2, 7], [1, 7], [1, 8], [2, 8], [3, 8], [4, 8], [5, 8], [6, 8], [7, 8]],
    'yellow': [[9, 14], [9, 13], [9, 12], [9, 11], [9, 10], [10, 9], [11, 9], [12, 9], [13, 9], [14, 9], [15, 9], [15, 8], [15, 7], [14, 7], [13, 7], [12, 7], [11, 7], [10, 7], [9, 6], [9, 5], [9, 4], [9, 3], [9, 2], [9, 1], [8, 1], [7, 1], [7, 2], [7, 3], [7, 4], [7, 5], [7, 6], [6, 7], [5, 7], [4, 7], [3, 7], [2, 7], [1, 7], [1, 8], [1, 9], [2, 9], [3, 9], [4, 9], [5, 9], [6, 9], [7, 10], [7, 11], [7, 12], [7, 13], [7, 14], [7, 15], [8, 15], [8, 14], [8, 13], [8, 12], [8, 11], [8, 10], [8, 9]],
    'blue': [[14, 7], [13, 7], [12, 7], [11, 7], [10, 7], [9, 6], [9, 5], [9, 4], [9, 3], [9, 2], [9, 1], [8, 1], [7, 1], [7, 2], [7, 3], [7, 4], [7, 5], [7, 6], [6, 7], [5, 7], [4, 7], [3, 7], [2, 7], [1, 7], [1, 8], [1, 9], [2, 9], [3, 9], [4, 9], [5, 9], [6, 9], [7, 10], [7, 11], [7, 12], [7, 13], [7, 14], [7, 15], [8, 15], [9, 15], [9, 14], [9, 13], [9, 12], [9, 11], [9, 10], [10, 9], [11, 9], [12, 9], [13, 9], [14, 9], [15, 9], [15, 8], [14, 8], [13, 8], [12, 8], [11, 8], [10, 8], [9, 8]]
};

let playerPositions = { 'red': -1, 'green': -1, 'yellow': -1, 'blue': -1 };

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

window.onload = function() {
    const savedName = localStorage.getItem('geek_ludo_name');
    const savedRoom = localStorage.getItem('geek_ludo_room');
    if(savedName) document.getElementById('player-name').value = savedName;
    if(savedRoom) document.getElementById('room-code').value = savedRoom;
}

function joinGame(selectedColor) {
    const name = document.getElementById('player-name').value;
    const room = document.getElementById('room-code').value;
    if(!name || !room) { alert("Please enter both Name and Room Code!"); return; }
    localStorage.setItem('geek_ludo_name', name);
    localStorage.setItem('geek_ludo_room', room);
    socket.emit('join_game', { name: name, color: selectedColor, room: room, user_id: USER_ID });
}

function startGame() {
    if(!currentRoom) return;
    socket.emit('start_game', { room: currentRoom });
}

socket.on('join_error', (data) => {
    document.getElementById('lobby-status').innerText = data.message;
});

socket.on('join_success', (data) => {
    myColor = data.color;
    currentRoom = data.room;
    document.getElementById('lobby-waiting-area').style.display = 'block';
    document.getElementById('start-btn').style.display = data.started ? 'none' : 'block';
    document.getElementById('lobby-status').style.color = "#2ecc71";
    document.getElementById('lobby-status').innerText = `✅ Joined Room ${currentRoom}. Waiting...`;
    if (data.started) document.getElementById('lobby-modal').style.display = 'none';
});

socket.on('game_started', (data) => {
    document.getElementById('lobby-modal').style.display = 'none';
    alert("🚀 " + data.message);
});

socket.on('update_player_list', (data) => {
    const sidebarList = document.getElementById('player-list');
    const lobbyList = document.getElementById('lobby-player-list');
    sidebarList.innerHTML = ""; 
    if(lobbyList) lobbyList.innerHTML = "";
    data.players.forEach(p => {
        const item = document.createElement('div');
        item.style.marginBottom = "5px";
        item.style.fontWeight = "bold";
        if (p.online) item.style.color = getHexColor(p.color);
        else { item.style.color = "#7f8c8d"; item.innerText = "(OFFLINE) "; }
        const isMe = (p.name === document.getElementById('player-name').value && p.color === myColor);
        item.innerText += `● ${p.name.toUpperCase()} (${p.color.toUpperCase()}) ${isMe ? "(YOU)" : ""}`;
        sidebarList.appendChild(item.cloneNode(true));
        if(lobbyList) lobbyList.appendChild(item.cloneNode(true));
    });
});

socket.on('sync_state', (data) => {
    for (let color in data.positions) { playerPositions[color] = data.positions[color]; }
    renderBoard();
});

socket.on('turn_change', (data) => {
    const activeColor = data.active_color;
    const bar = document.getElementById('turn-indicator');
    bar.innerText = `ROOM ${currentRoom} | TURN: ${activeColor.toUpperCase()}`;
    bar.style.backgroundColor = getHexColor(activeColor);
    if (activeColor === myColor) {
        myTurn = true;
        document.getElementById('roll-btn').disabled = false;
        document.getElementById('roll-btn').style.backgroundColor = '#27ae60';
        document.getElementById('roll-btn').innerText = "⚔️ YOUR TURN";
    } else {
        myTurn = false;
        document.getElementById('roll-btn').disabled = true;
        document.getElementById('roll-btn').style.backgroundColor = 'grey';
        document.getElementById('roll-btn').innerText = `WAITING FOR ${activeColor.toUpperCase()}`;
    }
});

socket.on('animate_move', (data) => {
    const color = data.color;
    const stepsToTake = Math.abs(data.total_steps_moved);
    const direction = data.total_steps_moved > 0 ? 1 : -1;
    let stepsAnimated = 0;
    function stepLoop() {
        playerPositions[color] += direction;
        if(playerPositions[color] < -1) playerPositions[color] = -1;
        renderBoard();
        stepsAnimated++;
        if (stepsAnimated < stepsToTake) setTimeout(stepLoop, 300);
        else if(color === myColor && playerPositions[color] >= paths[color].length - 1) alert("🎉 YOU WIN! 🎉");
    }
    stepLoop();
});

socket.on('checkpoint_alert', (data) => { alert(data.message); });

socket.on('hack_phase_start', (data) => {
    if (myColor === data.victim_color) {
        document.getElementById('turn-indicator').innerText = "🛡️ DEFENDING... PLAYERS ARE REVIEWING YOUR CODE";
        document.getElementById('turn-indicator').style.backgroundColor = "#e74c3c";
        return; 
    }
    const interface = document.getElementById('hack-interface');
    document.getElementById('hack-msg').innerHTML = `<strong style="color:${getHexColor(data.victim_color)}">${data.victim_name.toUpperCase()}</strong> has submitted. Can you break it?`;
    document.getElementById('victim-code-display').value = data.code;
    document.getElementById('hack-q-text').innerText = data.question_text;
    document.getElementById('hack-sample-in').innerText = data.sample_input; 
    document.getElementById('hack-sample-out').innerText = data.sample_output; 
    document.getElementById('hack-input-data').value = "";
    document.getElementById('hack-expected-data').value = "";
    interface.style.display = 'flex';
});

socket.on('hack_log', (data) => {
    const logDiv = document.getElementById('hack-logs');
    if(logDiv) logDiv.innerText = data.message;
    const notif = document.createElement('div');
    notif.innerText = data.message;
    notif.style.cssText = "position:fixed; top:50px; right:20px; background:rgba(0,0,0,0.8); color:white; padding:10px; z-index:5000; border-left: 4px solid #f1c40f;";
    document.body.appendChild(notif);
    setTimeout(() => notif.remove(), 3000);
});

socket.on('hack_phase_end', () => {
    document.getElementById('hack-interface').style.display = 'none';
    alert("🏁 Hack Phase Complete. Turn Switching.");
});

function submitHackVote(action) {
    const inputData = document.getElementById('hack-input-data').value;
    const expectedData = document.getElementById('hack-expected-data').value;
    if (action === 'hack' && (!inputData.trim() || !expectedData.trim())) {
        alert("Please provide BOTH Test Input and Expected Output!");
        return;
    }
    document.getElementById('hack-interface').style.display = 'none';
    socket.emit('submit_hack_attempt', { room: currentRoom, action: action, input: inputData, expected: expectedData });
}

async function openQuestion() {
    if(!myTurn) { alert("Not your turn!"); return; }
    const modal = document.getElementById('question-modal');
    const qText = document.getElementById('q-text');
    const sIn = document.getElementById('sample-in');
    const sOut = document.getElementById('sample-out');
    const consoleDiv = document.getElementById('console-output');
    modal.style.display = 'flex';
    qText.innerText = "Connecting...";
    consoleDiv.innerText = "Output will appear here...";
    myEditor.setValue("");
    setTimeout(() => { myEditor.refresh(); }, 100);
    try {
        const response = await fetch(`/get_question?sid=${socket.id}`);
        const data = await response.json();
        if (data.error) { qText.innerText = "Error: " + data.error; } 
        else {
            currentQuestionId = data.id;
            qText.innerText = "CHALLENGE #" + data.id + ": " + data.question;
            sIn.innerText = data.sample_input; 
            sOut.innerText = data.sample_output;
            myEditor.setValue("# Tip: Use input() to read values\n");
        }
    } catch (err) { qText.innerText = "Server Error"; }
}

function skipQuestion() {
    document.getElementById('question-modal').style.display = 'none';
    alert("⚠️ Mission Aborted! Penalty: -2 Steps.");
    socket.emit('player_move', { steps: -2, room: currentRoom });
}

async function runCode() {
    const userCode = myEditor.getValue();
    const selectedLang = document.getElementById('language-select').value;
    const consoleDiv = document.getElementById('console-output');
    consoleDiv.innerText = "Running Pretests...";
    consoleDiv.style.color = "yellow";
    try {
        const response = await fetch('/submit_code', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code: userCode, q_id: currentQuestionId, language: selectedLang })
        });
        const result = await response.json();
        if (result.success) {
            consoleDiv.innerText = "✅ PRETESTS PASSED! Initiating Hack Phase...";
            consoleDiv.style.color = "#00ff00"; 
            const useLuck = document.getElementById('mode-toggle').checked;
            let earnedSteps = useLuck ? Math.floor(Math.random() * 6) + 1 : 3;
            if (useLuck) alert(`🎲 DICE ROLLED: ${earnedSteps}`);
            setTimeout(() => {
                document.getElementById('question-modal').style.display = 'none';
                socket.emit('submission_success', { room: currentRoom, code: userCode, language: selectedLang, q_id: currentQuestionId, steps: earnedSteps });
                alert("⏳ Waiting for other players to verify your code...");
            }, 1000);
        } else {
            consoleDiv.innerText = result.output;
            consoleDiv.style.color = result.type === 'system' ? "orange" : "red";
            if (result.type !== 'system') {
                setTimeout(() => {
                    document.getElementById('question-modal').style.display = 'none';
                    alert("❌ Failed! Penalty: -3 Steps.");
                    socket.emit('player_move', { steps: -3, room: currentRoom });
                }, 2000);
            }
        }
    } catch (err) { consoleDiv.innerText = "Network Error!"; }
}

function renderBoard() {
    const board = document.getElementById('board');
    document.querySelectorAll('.player-piece').forEach(e => e.remove());
    ['red', 'green', 'yellow', 'blue'].forEach(color => {
        const step = playerPositions[color];
        const path = paths[color];
        if (step >= 0 && step < path.length) {
            const [r, c] = path[step];
            const token = document.createElement('div');
            token.className = `player-piece piece-${color}`;
            token.style.gridRow = r;
            token.style.gridColumn = c;
            board.appendChild(token);
        }
    });
}

function getHexColor(color) {
    const colors = {'red': '#e74c3c', 'green': '#2ecc71', 'blue': '#3498db', 'yellow': '#f1c40f'};
    return colors[color] || '#333';
}

function exitGame() { if(confirm("Are you sure you want to leave the game?")) window.location.href = "/"; }
