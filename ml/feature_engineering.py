from dotenv import load_dotenv
load_dotenv()

import pandas as pd
from pymongo import MongoClient
import os
import numpy as np

MONGO_URI = os.environ.get("MONGO_URI")

if not MONGO_URI:
    MONGO_URI = "mongodb+srv://admin:password@cluster0.mongodb.net/geek_ludo_db"

def fetch_and_engineer_features():

    print("Fetch Raw Logs From Mongo DB..")
    client = MongoClient(MONGO_URI)
    db = client.geek_ludo_db
    logs = list(db.game_logs.find())
    
    if not logs:
        print("No Log! Invite someone to play a game.")
        return None

    user_stats = {}

    for log in logs:
        event = log.get("event_type")
        data = log.get("data", {})
        
        user_id = data.get("user_id") or data.get("hacker") or data.get("winner_user_id")
        if not user_id or user_id == 'anonymous':
            continue

        if user_id not in user_stats:
            user_stats[user_id] = {
                "total_solves": 0, "total_solve_time": 0, 
                "hack_attempts": 0, "hack_successes": 0,
                "luck_mode_usage": 0, "frustration_skips": 0
            }

        # Aggregation.

        if event == "gameplay" and data.get("action") == "solve_success":
            user_stats[user_id]["total_solves"] += 1
            user_stats[user_id]["total_solve_time"] += data.get("time_taken", 0)
            if data.get("luck_mode_enabled"):
                user_stats[user_id]["luck_mode_usage"] += 1
                
        elif event == "hack":
            if data.get("action") == "skip":
                user_stats[user_id]["frustration_skips"] += 1
            else:
                user_stats[user_id]["hack_attempts"] += 1
                if data.get("action") == "success":
                    user_stats[user_id]["hack_successes"] += 1


    df = pd.DataFrame.from_dict(user_stats, orient='index')
    
    # Feature Engineering.

    df['avg_solve_time'] = np.where(df['total_solves'] > 0, df['total_solve_time'] / df['total_solves'], 0)
    df['hack_success_rate'] = np.where(df['hack_attempts'] > 0, df['hack_successes'] / df['hack_attempts'], 0)

    final_features = df[['total_solves', 'avg_solve_time', 'hack_attempts', 'hack_success_rate', 'luck_mode_usage', 'frustration_skips']]
    
    # NaN -> 0.
    final_features = final_features.fillna(0)
    
    print(f"Extracted features for {len(final_features)} users.")
    final_features.to_csv("ml/user_features.csv", index_label = "user_id")
    return final_features

if __name__ == "__main__":
    fetch_and_engineer_features()