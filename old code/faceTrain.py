import cv2
import os
import numpy as np

# Dataset path
dataset_path = "dataset"

faces = []
labels = []
label_map = {}

current_id = 0

# Loop through each student folder
for folder in os.listdir(dataset_path):
    folder_path = os.path.join(dataset_path, folder)

    if not os.path.isdir(folder_path):
        continue

    # Assign ID to each student
    label_map[current_id] = folder

    # Loop through images
    for image_name in os.listdir(folder_path):
        image_path = os.path.join(folder_path, image_name)

        # Read image in grayscale
        img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)

        if img is None:
            continue

        # Resize to fixed size (IMPORTANT)
        img = cv2.resize(img, (200, 200))

        faces.append(img)
        labels.append(current_id)

    current_id += 1

# Convert labels to numpy array
labels = np.array(labels)

# Create LBPH recognizer
recognizer = cv2.face.LBPHFaceRecognizer_create()

# Train model
recognizer.train(faces, labels)

# Save trained model
recognizer.save("trained_model.yml")

# Save label mapping
np.save("labels.npy", label_map)

print("Model trained successfully!")