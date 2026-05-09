# PyTorch Auto-Encoder Compress Features.
# ScikitLearn KMeans Cluster On Compressed Features To Create 4 Personas (Novice, Intermediate, Master, Hacker).

import pandas as pd
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
import pickle

class Autoencoder(nn.Module):
    def __init__(self, input_dim):
        super(Autoencoder, self).__init__()
        
        self.encoder = nn.Sequential(

            nn.Linear(input_dim, 8), nn.ReLU(),
            nn.Linear(8, 2) 
        )

        self.decoder = nn.Sequential(

            nn.Linear(2, 8), nn.ReLU(),
            nn.Linear(8, input_dim)
        )

    def forward(self, x):
        encoded = self.encoder(x)
        decoded = self.decoder(encoded)
        return encoded, decoded

def train_deep_clustering():
    try:
        df = pd.read_csv("ml/user_features.csv", index_col = "user_id")

    except FileNotFoundError:
        print("No Features Exist.")
        return

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(df.values)
    X_tensor = torch.FloatTensor(X_scaled)

    print("Training Deep Auto-Encoder...")

    model = Autoencoder(input_dim=X_scaled.shape[1])
    criterion = nn.MSELoss()
    optimizer = optim.Adam(model.parameters(), lr=0.01)

    for epoch in range(100):
        optimizer.zero_grad()
        encoded, decoded = model(X_tensor)
        loss = criterion(decoded, X_tensor)
        loss.backward()
        optimizer.step()

    with torch.no_grad():
        latent_features, _ = model(X_tensor)
    
    # K-Means Cluster.

    print("Clustering into : Novice, Intermediate, Master, Hacker...")
    kmeans = KMeans(n_clusters = 4, random_state = 42, n_init = 10)

    clusters = kmeans.fit_predict(latent_features.numpy())
    df['persona_cluster'] = clusters

    torch.save(model.state_dict(), "ml/autoencoder.pth")

    with open("ml/scaler.pkl", "wb") as f:
        pickle.dump(scaler, f)
        
    with open("ml/kmeans.pkl", "wb") as f:
        pickle.dump(kmeans, f)

    print("Models saved successfully!")
    df.to_csv("ml/clustered_users.csv")

if __name__ == "__main__":
    train_deep_clustering()