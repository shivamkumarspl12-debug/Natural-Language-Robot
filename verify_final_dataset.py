import json
from collections import Counter


FILE = r".\datasets\combined\unified_robot_dataset_117.json"


def safe_value(value):
    """
    Convert dictionaries/lists into a hashable readable string
    for statistics.
    """

    if value is None:
        return ""

    if isinstance(value, dict):
        return json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False
        )

    if isinstance(value, list):
        return ", ".join(
            str(item)
            for item in value
        )

    return str(value)


def is_empty(value):
    if value is None:
        return True

    if value == "":
        return True

    if value == []:
        return True

    if isinstance(value, dict) and not value:
        return True

    return False


print("=" * 70)
print("FINAL DATASET VERIFICATION")
print("=" * 70)


# ------------------------------------------------------------
# LOAD DATASET
# ------------------------------------------------------------

with open(
    FILE,
    "r",
    encoding="utf-8"
) as f:

    data = json.load(f)


print("\nTotal Records:", len(data))


# ------------------------------------------------------------
# SOURCE
# ------------------------------------------------------------

sources = Counter(
    safe_value(
        record.get("source", "UNKNOWN")
    )
    for record in data
)

print("\n" + "=" * 70)
print("1. DATA SOURCE")
print("=" * 70)

for source, count in sources.items():
    print(f"{source}: {count}")


# ------------------------------------------------------------
# TASK TYPE
# ------------------------------------------------------------

task_types = Counter(
    safe_value(
        record.get("task_type", "UNKNOWN")
    )
    for record in data
)

print("\n" + "=" * 70)
print("2. TASK TYPES")
print("=" * 70)

for task, count in task_types.most_common():
    print(f"{task}: {count}")


# ------------------------------------------------------------
# OBJECT
# ------------------------------------------------------------

objects = Counter()

for record in data:

    value = record.get("object", "")

    if not is_empty(value):
        objects[safe_value(value)] += 1


print("\n" + "=" * 70)
print("3. OBJECTS")
print("=" * 70)

for obj, count in objects.most_common():
    print(f"{obj}: {count}")


# ------------------------------------------------------------
# COLOR
# ------------------------------------------------------------

colors = Counter()

for record in data:

    value = record.get("color", "")

    if not is_empty(value):
        colors[safe_value(value)] += 1


print("\n" + "=" * 70)
print("4. COLORS")
print("=" * 70)

for color, count in colors.most_common():
    print(f"{color}: {count}")


# ------------------------------------------------------------
# TARGET
# ------------------------------------------------------------

targets = Counter()

for record in data:

    value = record.get("target", "")

    if not is_empty(value):
        targets[safe_value(value)] += 1


print("\n" + "=" * 70)
print("5. TARGETS")
print("=" * 70)

for target, count in targets.most_common():
    print(f"{target}: {count}")


# ------------------------------------------------------------
# ACTIONS
# ------------------------------------------------------------

actions = Counter()

for record in data:

    record_actions = record.get(
        "actions",
        []
    )

    if isinstance(record_actions, list):

        for action in record_actions:
            actions[safe_value(action)] += 1

    elif not is_empty(record_actions):

        actions[safe_value(record_actions)] += 1


print("\n" + "=" * 70)
print("6. ACTIONS")
print("=" * 70)

for action, count in actions.most_common():
    print(f"{action}: {count}")


# ------------------------------------------------------------
# MISSING FIELDS
# ------------------------------------------------------------

required_fields = [
    "instruction",
    "task_type",
    "object",
    "color",
    "target",
    "actions",
    "source"
]

missing_counts = Counter()


for record in data:

    for field in required_fields:

        if field not in record:
            missing_counts[field] += 1

        elif is_empty(record[field]):
            missing_counts[field] += 1


print("\n" + "=" * 70)
print("7. MISSING / EMPTY FIELDS")
print("=" * 70)

for field in required_fields:

    print(
        f"{field}: "
        f"{missing_counts.get(field, 0)} empty"
    )


# ------------------------------------------------------------
# FIELD TYPE CHECK
# ------------------------------------------------------------

print("\n" + "=" * 70)
print("8. FIELD TYPE CHECK")
print("=" * 70)

for field in required_fields:

    types = Counter(
        type(record.get(field)).__name__
        for record in data
        if field in record
    )

    print(f"\n{field}:")
    for field_type, count in types.items():
        print(
            f"  {field_type}: {count}"
        )


# ------------------------------------------------------------
# DUPLICATE IDS
# ------------------------------------------------------------

ids = [
    record.get("id")
    for record in data
]

id_counts = Counter(ids)

duplicates = {
    record_id: count
    for record_id, count in id_counts.items()
    if count > 1
}


print("\n" + "=" * 70)
print("9. DUPLICATE IDs")
print("=" * 70)

if duplicates:

    print("❌ Duplicate IDs found:")

    for record_id, count in duplicates.items():
        print(
            record_id,
            "→",
            count
        )

else:

    print("✅ No duplicate IDs")


# ------------------------------------------------------------
# TRAIN / TEST SPLIT
# ------------------------------------------------------------

total = len(data)

train_size = int(
    total * 0.8
)

test_size = total - train_size


print("\n" + "=" * 70)
print("10. TRAIN / TEST SPLIT")
print("=" * 70)

print("Total:", total)
print("Training:", train_size)
print("Testing:", test_size)


# ------------------------------------------------------------
# FINAL SUMMARY
# ------------------------------------------------------------

print("\n" + "=" * 70)
print("FINAL SUMMARY")
print("=" * 70)

print(
    "Total Records:",
    total
)

print(
    "CUSTOM:",
    sources.get("CUSTOM", 0)
)

print(
    "CALVIN:",
    sources.get("CALVIN", 0)
)


if total == 116:

    print(
        "\n✅ FINAL DATASET VERIFIED: "
        "116 RECORDS"
    )

else:

    print(
        f"\n⚠️ Dataset contains "
        f"{total} records."
    )


if not duplicates:

    print(
        "✅ IDs are unique"
    )

else:

    print(
        "❌ Duplicate IDs detected"
    )


print("=" * 70)