import json

INPUT_FILE = r".\datasets\combined\unified_robot_dataset_117.json"
OUTPUT_FILE = r".\datasets\combined\unified_robot_dataset_116.json"

with open(INPUT_FILE, "r", encoding="utf-8") as f:
    data = json.load(f)

print("=" * 60)
print("FIXING DATASET IDs")
print("=" * 60)

used_ids = set()

for index, record in enumerate(data, start=1):

    old_id = record.get("id")

    # Keep CUSTOM IDs as they are if unique
    if record.get("source") == "CUSTOM":

        new_id = old_id

        if new_id in used_ids:
            new_id = f"CUSTOM_{index:03d}"

    else:
        # Give every CALVIN record a unique ID
        new_id = f"CALVIN_{index:03d}"

    record["id"] = new_id
    used_ids.add(new_id)

print("\nTotal records:", len(data))
print("Unique IDs:", len(used_ids))

with open(
    OUTPUT_FILE,
    "w",
    encoding="utf-8"
) as f:
    json.dump(
        data,
        f,
        indent=4,
        ensure_ascii=False
    )

print("\nSaved to:")
print(OUTPUT_FILE)

print("\n" + "=" * 60)

if len(data) == len(used_ids):
    print("DATASET ID STATUS: VERIFIED")
else:
    print("DATASET ID STATUS: CHECK REQUIRED")

print("=" * 60)