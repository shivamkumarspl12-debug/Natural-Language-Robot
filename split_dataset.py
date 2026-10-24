import json
import random
import os
from collections import Counter

# -----------------------------
# Configuration
# -----------------------------

INPUT_FILE = "robot_dataset.json"

TRAIN_FILE = "train.json"
TEST_FILE = "test.json"

TRAIN_SIZE = 80
TEST_SIZE = 20

RANDOM_SEED = 42


# -----------------------------
# Load Dataset
# -----------------------------

with open(INPUT_FILE, "r", encoding="utf-8") as file:
    dataset = json.load(file)

print("=" * 60)
print("ROBOT DATASET TRAIN / TEST SPLIT")
print("=" * 60)

print(f"\nTotal records: {len(dataset)}")


# -----------------------------
# Shuffle Dataset
# -----------------------------

random.seed(RANDOM_SEED)

random.shuffle(dataset)


# -----------------------------
# Split Dataset
# -----------------------------

train_data = dataset[:TRAIN_SIZE]
test_data = dataset[TRAIN_SIZE:TRAIN_SIZE + TEST_SIZE]


# -----------------------------
# Save Files
# -----------------------------

with open(TRAIN_FILE, "w", encoding="utf-8") as file:
    json.dump(train_data, file, indent=4)

with open(TEST_FILE, "w", encoding="utf-8") as file:
    json.dump(test_data, file, indent=4)


# -----------------------------
# Statistics Function
# -----------------------------

def show_statistics(name, data):

    status = Counter(
        record["execution"]["status"]
        for record in data
    )

    failures = Counter(
        record["execution"]["failure"]
        for record in data
    )

    print(f"\n{name}")
    print("-" * 40)

    print(f"Records: {len(data)}")

    print("\nExecution Status:")

    for key, value in status.items():
        percentage = (value / len(data)) * 100
        print(f"{key}: {value} ({percentage:.1f}%)")

    print("\nFailures:")

    for key, value in failures.items():
        print(f"{key}: {value}")


# -----------------------------
# Display Statistics
# -----------------------------

show_statistics("TRAINING DATASET", train_data)

show_statistics("TESTING DATASET", test_data)


# -----------------------------
# Final Information
# -----------------------------

print("\n" + "=" * 60)

print("DATASET SPLIT COMPLETED")

print("=" * 60)

print(f"\nTraining records : {len(train_data)}")
print(f"Testing records  : {len(test_data)}")

print("\nFiles created:")
print(f"  {TRAIN_FILE}")
print(f"  {TEST_FILE}")

print("\nRandom seed:", RANDOM_SEED)

print("\nReady for parser/model evaluation!")