import face_recognition
import os
import pickle

dataset_path = "dataset"

known_encodings = []
known_names = []

print("🔄 Training started...")

for folder in os.listdir(dataset_path):
    folder_path = os.path.join(dataset_path, folder)

    if not os.path.isdir(folder_path):
        continue

    for image_name in os.listdir(folder_path):
        image_path = os.path.join(folder_path, image_name)

        try:
            image = face_recognition.load_image_file(image_path)
            encodings = face_recognition.face_encodings(image)

            if len(encodings) > 0:
                known_encodings.append(encodings[0])
                known_names.append(folder)
                print(f"Encoded: {folder}")

        except Exception as e:
            print(f"Error: {image_name}")

# Save model
data = {
    "encodings": known_encodings,
    "names": known_names
}

with open("encodings.pkl", "wb") as f:
    pickle.dump(data, f)

print("✅ Training completed!")