import os
import json
import numpy as np

print("=" * 70)
print("CALVIN TRAINING DATA EXTRACTION")
print("=" * 70)

# Project root
project_root = os.getcwd()

# Automatically search for training annotation file
search_root = os.path.join(
    project_root,
    "datasets",
    "calvin"
)

calvin_file = None

for root, dirs, files in os.walk(search_root):
    for file in files:
        if file == "auto_lang_ann.npy" and "training" in root:
            calvin_file = os.path.join(root, file)
            break

    if calvin_file:
        break


if calvin_file is None:

    print("\n❌ Training annotation file not found.")

    print("\nSearching inside:")
    print(search_root)

    print("\nPlease run this command in PowerShell:")
    print(
        'Get-ChildItem ".\\datasets\\calvin" '
        '-Recurse -Filter "auto_lang_ann.npy"'
    )

    exit()


print("\n✅ CALVIN annotation file found:")
print(calvin_file)


# Load annotation data
data = np.load(
    calvin_file,
    allow_pickle=True
).item()


annotations = data["language"]["ann"]
tasks = data["language"]["task"]


print("\n" + "=" * 70)
print("LANGUAGE DATA")
print("=" * 70)

print("Annotations:", len(annotations))
print("Tasks:", len(tasks))


records = []


for i in range(len(annotations)):

    instruction = annotations[i]

    if i < len(tasks):
        task = tasks[i]
    else:
        task = "UNKNOWN"

    text = instruction.lower()

    # Detect color
    color = ""

    for c in ["red", "green", "blue", "yellow", "pink"]:
        if c in text:
            color = c
            break

    # Detect object
    obj = ""

    for o in ["block", "cube", "ball", "bottle"]:
        if o in text:
            obj = o
            break

    # Detect target
    target = ""

    for t in [
        "box",
        "container",
        "basket",
        "bin",
        "drawer",
        "slider",
        "cabinet",
        "table"
    ]:
        if t in text:
            target = t
            break

    # Detect actions
    actions = []

    if any(
        word in text
        for word in ["pick", "grab", "grasp", "lift"]
    ):
        actions.append("GRAB")

    if "lift" in text:
        actions.append("LIFT")

    if "put" in text or "place" in text:
        actions.append("RELEASE")

    if "slide down" in text:
        actions.append("SLIDE_DOWN")

    if "slide right" in text:
        actions.append("SLIDE_RIGHT")

    if not actions:
        actions.append("MANIPULATE")


    record = {
        "id": f"CALVIN_TRAIN_{i + 1:03d}",
        "instruction": instruction,
        "task_type": task,
        "object": obj,
        "color": color,
        "target": target,
        "actions": actions,
        "source": "CALVIN"
    }

    records.append(record)


    print(
        f"\n{i + 1}. {instruction}"
    )

    print("   Task:", task)
    print("   Object:", obj)
    print("   Color:", color)
    print("   Target:", target)
    print("   Actions:", actions)


# Output directory
output_dir = os.path.join(
    project_root,
    "datasets",
    "combined"
)

os.makedirs(
    output_dir,
    exist_ok=True
)


output_file = os.path.join(
    output_dir,
    "calvin_training_9.json"
)


with open(
    output_file,
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        records,
        f,
        indent=4,
        ensure_ascii=False
    )


print("\n" + "=" * 70)
print("✅ EXTRACTION COMPLETED")
print("=" * 70)

print("Records extracted:", len(records))

print("\nSaved to:")
print(output_file)

print("=" * 70)