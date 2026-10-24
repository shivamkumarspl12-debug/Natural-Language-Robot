import json
import random

# -----------------------------
# Configuration
# -----------------------------

objects = ["block", "cube", "ball", "bottle"]
colors = ["red", "green", "blue", "yellow"]
targets = ["box", "container", "basket", "bin"]

instructions = [
    "Pick up the {color} {object} and place it in the {target}",
    "Grab the {color} {object} and put it in the {target}",
    "Take the {color} {object} to the {target}",
    "Move the {color} {object} into the {target}",
    "Transfer the {color} {object} to the {target}",
    "Lift the {color} {object} and place it in the {target}"
]

failure_conditions = [
    "NONE",
    "OBJECT_NOT_DETECTED",
    "MOVE_FAILED",
    "GRAB_FAILED",
    "RELEASE_FAILED",
    "TIMEOUT",
    "UNEXPECTED_OBSTACLE"
]


# -----------------------------
# Generate Position
# -----------------------------

def generate_position():
    return {
        "x": round(random.uniform(0.10, 0.70), 2),
        "y": round(random.uniform(0.10, 0.50), 2),
        "z": round(random.uniform(0.02, 0.15), 2)
    }


# -----------------------------
# Generate One Record
# -----------------------------

def generate_record(record_id):

    obj = random.choice(objects)
    color = random.choice(colors)
    target = random.choice(targets)

    instruction_template = random.choice(instructions)

    instruction = instruction_template.format(
        color=color,
        object=obj,
        target=target
    )

    object_position = generate_position()
    target_position = generate_position()

    # Most records are successful
    status = random.choices(
        ["SUCCESS", "FAILED"],
        weights=[85, 15]
    )[0]

    if status == "SUCCESS":
        failure = "NONE"
        retry_count = random.choice([0, 0, 0, 1])
    else:
        failure = random.choice(failure_conditions[1:])
        retry_count = random.randint(1, 3)

    execution_time = round(random.uniform(3.0, 8.0), 2)

    record = {
        "id": record_id,

        "instruction": instruction,

        "object": {
            "name": obj,
            "color": color,
            "position": object_position
        },

        "target": {
            "name": target,
            "position": target_position
        },

        "actions": [
            "DETECT",
            "MOVE_TO_OBJECT",
            "GRAB",
            "MOVE_TO_TARGET",
            "RELEASE"
        ],

        "gripper": {
            "initial": "OPEN",
            "after_grab": "CLOSED",
            "final": "OPEN"
        },

        "execution": {
            "time_seconds": execution_time,
            "failure": failure,
            "retry_count": retry_count,
            "status": status
        }
    }

    return record


# -----------------------------
# Generate Dataset
# -----------------------------

dataset = []

for i in range(1, 101):
    dataset.append(generate_record(i))


# -----------------------------
# Save Dataset
# -----------------------------

with open("robot_dataset.json", "w", encoding="utf-8") as file:
    json.dump(dataset, file, indent=4)


print("=" * 50)
print("REAL-ROBOT STYLE DATASET GENERATED")
print("=" * 50)

print(f"Total records : {len(dataset)}")
print("File          : robot_dataset.json")

print("\nExample record:")
print(json.dumps(dataset[0], indent=4))

print("\nDataset generation completed successfully!")