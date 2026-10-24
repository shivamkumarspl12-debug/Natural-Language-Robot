import json
from collections import Counter

# Load dataset
with open("robot_dataset.json", "r", encoding="utf-8") as file:
    dataset = json.load(file)

print("=" * 60)
print("ROBOT DATASET ANALYSIS")
print("=" * 60)

# Total records
print("\nTotal Records:", len(dataset))

# Objects
objects = Counter(
    record["object"]["name"]
    for record in dataset
)

print("\nObject Distribution:")
for name, count in objects.items():
    print(f"{name}: {count}")

# Colors
colors = Counter(
    record["object"]["color"]
    for record in dataset
)

print("\nColor Distribution:")
for color, count in colors.items():
    print(f"{color}: {count}")

# Targets
targets = Counter(
    record["target"]["name"]
    for record in dataset
)

print("\nTarget Distribution:")
for target, count in targets.items():
    print(f"{target}: {count}")

# Status
statuses = Counter(
    record["execution"]["status"]
    for record in dataset
)

print("\nExecution Status:")
for status, count in statuses.items():
    print(f"{status}: {count}")

# Failure types
failures = Counter(
    record["execution"]["failure"]
    for record in dataset
)

print("\nFailure Distribution:")
for failure, count in failures.items():
    print(f"{failure}: {count}")

# Execution time
times = [
    record["execution"]["time_seconds"]
    for record in dataset
]

average_time = sum(times) / len(times)

print(f"\nAverage Execution Time: {average_time:.2f} seconds")

# Retry count
retries = [
    record["execution"]["retry_count"]
    for record in dataset
]

average_retry = sum(retries) / len(retries)

print(f"Average Retry Count: {average_retry:.2f}")

print("\n" + "=" * 60)
print("DATASET ANALYSIS COMPLETED")
print("=" * 60)