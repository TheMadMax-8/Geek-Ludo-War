import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score, classification_report

def evaluate_hacker_prediction():

    print("Evaluate Hacker Prediction Model...")
    try:
        df = pd.read_csv("ml/clustered_users.csv", index_col="user_id")
    except FileNotFoundError:
        print("No Clustered Data Exist.")
        return

    # Hack Success Rate > 40%.
    # Consider A Hacker.

    df['is_hacker'] = (df['hack_success_rate'] > 0.4).astype(int)

    # Does Coding Skills Predict Hacker Status?

    X = df[['total_solves', 'avg_solve_time', 'luck_mode_usage', 'frustration_skips']]
    Y = df['is_hacker']

    # Good Variance!

    if len(Y.unique()) < 2:
        print("Need More Successful As Well As Unsuccessful Hackers To Evaluate.")
        return

    trainX, testX, trainY, testY = train_test_split(X, Y, test_size = 0.3, random_state = 42)

    clf = RandomForestClassifier(random_state=42)
    clf.fit(trainX, trainY)
    predictY = clf.predict(testX)

    Accuracy = accuracy_score(testY, predictY)
    f1 = f1_score(testY, predictY, zero_division=0)
    report = classification_report(testY, predictY, zero_division = 0)

    print("\n--- Model Evaluation Results ---")
    print(f"Accuracy: {Accuracy:.2f}")
    print(f"F1 Score: {f1:.2f}")

    print("\nClassification Report:")
    print(report)
    
    with open("ml/evaluation_logs.txt", "w") as f:
        f.write(f"Accuracy: {Accuracy:.2f}\n")
        f.write(f"F1 Score: {f1:.2f}\n")
        f.write("---Classification Report---\n")
        f.write(report)

if __name__ == "__main__":
    evaluate_hacker_prediction()