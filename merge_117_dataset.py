import json
import os


BASE_FILE = r".\datasets\combined\unified_robot_dataset.json"
CALVIN_FILE = r".\datasets\combined\calvin_training_9.json"
OUTPUT_FILE = r".\datasets\combined\unified_robot_dataset_117.json"


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


print("=" * 70)
print("MERGING FINAL ROBOT DATASET")
print("=" * 70)


# Load existing unified dataset
base_data = load_json(BASE_FILE)

# Load CALVIN training data
calvin_data = load_json(CALVIN_FILE)


print("\nExisting unified dataset:", len(base_data))
print("CALVIN training dataset:", len(calvin_data))


# Make sure both are lists
if not isinstance(base_data, list):
    raise ValueError("unified_robot_dataset.json is not a list.")

if not isinstance(calvin_data, list):
    raise ValueError("calvin_training_9.json is not a list.")


# Check duplicate IDs
existing_ids = {
    record.get("id")
    for record in base_data
    if isinstance(record, dict)
}


new_records = []

for record in calvin_data:

    record_id = record.get("id")

    if record_id in existing_ids:
        print(f"⚠️ Duplicate skipped: {record_id}")
        continue

    new_records.append(record)


# Merge
final_data = base_data + new_records


# Save
with open(
    OUTPUT_FILE,
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        final_data,
        f,
        indent=4,
        ensure_ascii=False
    )


print("\n" + "=" * 70)
print("MERGE RESULT")
print("=" * 70)

print("Original records:", len(base_data))
print("New CALVIN records:", len(new_records))
print("Final records:", len(final_data))

print("\nSaved to:")
print(OUTPUT_FILE)

print("=" * 70)


# Verification
print("\n🔍 VERIFICATION")

source_counts = {}

for record in final_data:

    source = record.get("source", "UNKNOWN")

    source_counts[source] = (
        source_counts.get(source, 0) + 1
    )


print("\nRecords by source:")

for source, count in source_counts.items():
    print(f"{source}: {count}")


if len(final_data) == 117:
    print("\n✅ FINAL DATASET = 117 RECORDS")
else:
    print(
        f"\n⚠️ Final dataset contains "
        f"{len(final_data)} records."
    )

print("=" * 70)