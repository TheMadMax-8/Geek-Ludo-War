import os
import csv

structure = {
    "templates": ["index.html"],
    "static": ["game.js", "style.css"],
    "logs": ["game_logs.csv", "hack_logs.csv", "session_logs.csv"],
    "data/raw": ["gameplay_raw.csv"],
    "data/processed": ["features.csv"],
    "data/survey": ["google_forms_responses.csv"],
    "ml/models": ["model.pkl"],
    "experiments": ["analysis_notebook.ipynb"]
}

headers = {
    "game_logs.csv": ["timestamp", "room_id", "player", "event_type", "data", "outcome"],
    "hack_logs.csv": ["timestamp", "room_id", "hacker", "victim", "question_id", "action", "success"],
    "session_logs.csv": ["timestamp", "room_id", "player", "action", "mode_preference"]
}

def create_structure():
    base_dir = os.getcwd()
    print(f"Building Geek Ludo Architecture in {base_dir}...")

    for folder, files in structure.items():
        path = os.path.join(base_dir, folder)
        os.makedirs(path, exist_ok=True)
        print(f"   Created: {folder}/")

        for file in files:
            file_path = os.path.join(path, file)
            if not os.path.exists(file_path):
                if file.endswith(".csv") and file in headers:
                    with open(file_path, 'w', newline='') as f:
                        writer = csv.writer(f)
                        writer.writerow(headers[file])
                    print(f"      Created (with headers): {file}")
                else:
                    with open(file_path, 'w') as f:
                        pass
                    print(f"      Created: {file}")
            else:
                print(f"      Exists: {file}")

    print("\nInfrastructure Ready.")

if __name__ == "__main__":
    create_structure()