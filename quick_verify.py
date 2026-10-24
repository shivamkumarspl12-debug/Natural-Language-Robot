import json
from collections import Counter

FILE = r".\datasets\combined\unified_robot_dataset_116.json"

with open(FILE, "r", encoding="utf-8") as f:
    data = json.load(f)

print("=" * 60)
print("FINAL DATASET QUICK VERIFICATION")
print("=" * 60)

print("\nTotal Records:", len(data))

sources = Counter(
    str(x.get("source", "UNKNOWN"))
    for x in data
)

print("\nSources:")
for k, v in sources.items():
    print(f"  {k}: {v}")

tasks = Counter(
    str(x.get("task_type", "UNKNOWN"))
    for x in data
)

print("\nTask Types:")
for k, v in tasks.items():
    print(f"  {k}: {v}")

fields = [
    "instruction",
    "task_type",
    "object",
    "color",
    "target",
    "actions",
    "source"
]

print("\nEmpty Fields:")

for field in fields:

    count = 0

    for record in data:
        value = record.get(field)

        if value is None or value == "" or value == []:
            count += 1

    print(f"  {field}: {count}")

ids = [
    x.get("id")
    for x in data
]

duplicates = [
    item
    for item, count in Counter(ids).items()
    if count > 1
]

print("\nDuplicate IDs:", len(duplicates))

if duplicates:
    print("Duplicate ID list:")
    for item in duplicates:
        print(" ", item)
else:
    print("No duplicate IDs")

train = int(len(data) * 0.8)
test = len(data) - train

print("\nTrain/Test Split:")
print("  Training:", train)
print("  Testing :", test)

print("\n" + "=" * 60)

if len(data) == 116 and not duplicates:
    print("FINAL DATASET STATUS: VERIFIED")
else:
    print("FINAL DATASET STATUS: CHECK REQUIRED")

print("=" * 60)