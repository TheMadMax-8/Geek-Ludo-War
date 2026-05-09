import numpy as np
import json
import os
import pandas as pd

# Active Interventions To Reward Agent Later.
ACTIVE_INTERVENTIONS = {}

class FlowAgent:
    def __init__(self, actions=None):
        self.actions = actions if actions else [0, 1, 2]
        self.q_table_file = "ml/q_table.json"
        self.q_table = self.load_q_table()
        self.learning_rate = 0.1
        self.discount_factor = 0.9
        self.exploration_rate = 0.2

    def load_q_table(self):
        if os.path.exists(self.q_table_file):
            with open(self.q_table_file, 'r') as f:
                return json.load(f)
        return {}

    def save_q_table(self):
        os.makedirs(os.path.dirname(self.q_table_file), exist_ok=True)
        with open(self.q_table_file, 'w') as f:
            json.dump(self.q_table, f)

    def get_state_key(self, persona_cluster, frustration_level):
        return f"{persona_cluster}_{frustration_level}"

    def choose_action(self, state):
        if state not in self.q_table:
            self.q_table[state] = {str(a): 0.0 for a in self.actions}

        if np.random.uniform(0, 1) < self.exploration_rate:
            return np.random.choice(self.actions)
        else:
            q_values = self.q_table[state]
            return int(max(q_values, key=q_values.get))

    def update_q_value(self, state, action, reward, next_state):
        if state not in self.q_table:
            self.q_table[state] = {str(a): 0.0 for a in self.actions}
        if next_state not in self.q_table:
            self.q_table[next_state] = {str(a): 0.0 for a in self.actions}

        str_action = str(action)
        current_q = self.q_table[state][str_action]
        max_next_q = max(self.q_table[next_state].values())
        
        new_q = current_q + self.learning_rate * (reward + self.discount_factor * max_next_q - current_q)
        self.q_table[state][str_action] = new_q
        self.save_q_table()

        print(f"\n🧠 [RL AGENT LEARNING]")
        print(f"State: {state} | Action: {action} | Reward: {reward}")
        print(f"Q-Value Shift: {current_q:.4f} ➡️ {new_q:.4f}")
        print("-" * 30)

def get_user_cluster(user_id):
    csv_path = "ml/clustered_users.csv"
    if not os.path.exists(csv_path):
        return 0 
    try:
        df = pd.read_csv(csv_path)
        if user_id in df['user_id'].values:
            return int(df.loc[df['user_id'] == user_id, 'persona_cluster'].values[0])
    except Exception as e:
        print(f"Error reading ML clusters: {e}")
    return 0 

def get_cognitive_flow_adjustment(user_id, frustration_skips):
    agent = FlowAgent()
    user_persona = get_user_cluster(user_id)
    
    frustration_level = "HIGH" if frustration_skips > 2 else "LOW"
    state = agent.get_state_key(user_persona, frustration_level)
    action = agent.choose_action(state)
    
    ACTIVE_INTERVENTIONS[user_id] = {"state": state, "action": action}
    
    if action == 1:
        return {"luck_boost": True, "penalty_reduction": False}
    
    elif action == 2:
        return {"luck_boost": False, "penalty_reduction": True}
    
    return {"luck_boost": False, "penalty_reduction": False}

def reward_agent(user_id, user_succeeded, next_frustration_skips):
   
    if user_id not in ACTIVE_INTERVENTIONS:
        return 

    past_memory = ACTIVE_INTERVENTIONS[user_id]
    agent = FlowAgent()
    
    # Calculate Reward
    # +1 :- Cognitive Flow Achieved (User Succeeded).
    # -1 :- Frustration Wall (User Failed).

    reward = 1.0 if user_succeeded else -1.0 
    
    user_persona = get_user_cluster(user_id)
    next_state = agent.get_state_key(user_persona, "HIGH" if next_frustration_skips > 2 else "LOW")
    
    agent.update_q_value(past_memory["state"], past_memory["action"], reward, next_state)
    del ACTIVE_INTERVENTIONS[user_id]