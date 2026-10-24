import json
import re


# ---------------------------------------------------------
# CALVIN / NATURAL LANGUAGE → ROBOT ACTION MAPPING
# ---------------------------------------------------------

ACTION_MAP = {
    "pick up": "GRAB",
    "pickup": "GRAB",
    "pick": "GRAB",
    "grab": "GRAB",
    "grasp": "GRAB",
    "lift": "LIFT",

    "put": "PLACE",
    "place": "PLACE",
    "release": "RELEASE",

    "slide": "SLIDE",
    "move": "MOVE"
}


def detect_action(instruction):
    """
    Detect the main action from a natural-language instruction.
    """

    text = instruction.lower()

    # Check multi-word actions first
    if "pick up" in text:
        return "GRAB"

    if "pickup" in text:
        return "GRAB"

    # Single-word actions
    words = re.findall(r"\b[a-z]+\b", text)

    for word in words:
        if word in ACTION_MAP:
            return ACTION_MAP[word]

    # Custom pick-and-place style instructions
    if any(word in text for word in [
        "transfer",
        "take",
        "move"
    ]):
        return "MOVE"

    return "UNKNOWN"


def detect_task_type(record):

    # Already standardized
    if record.get("task_type"):
        return record["task_type"]

    # CALVIN
    if record.get("source") == "CALVIN":

        action = record.get("action_type")

        if action in ["GRAB", "LIFT"]:
            return "MANIPULATION"

        if action == "PLACE":
            return "PLACEMENT"

        if action == "SLIDE":
            return "SLIDING"

        return "OTHER"

    # CUSTOM
    return "PICK_AND_PLACE"


def generate_robot_actions(record):

    instruction = record.get("instruction", "").lower()
    task_type = detect_task_type(record)

    # -----------------------------------------------------
    # CUSTOM PICK AND PLACE
    # -----------------------------------------------------

    if task_type == "PICK_AND_PLACE":

        return [
            "DETECT",
            "MOVE_TO_OBJECT",
            "GRAB",
            "MOVE_TO_TARGET",
            "RELEASE"
        ]

    # -----------------------------------------------------
    # CALVIN MANIPULATION
    # -----------------------------------------------------

    if task_type == "MANIPULATION":

        action = record.get("action_type")

        if action == "LIFT":
            return [
                "DETECT",
                "MOVE_TO_OBJECT",
                "GRAB",
                "LIFT"
            ]

        if action == "GRAB":
            return [
                "DETECT",
                "MOVE_TO_OBJECT",
                "GRAB"
            ]

    # -----------------------------------------------------
    # CALVIN PLACEMENT
    # -----------------------------------------------------

    if task_type == "PLACEMENT":

        return [
            "MOVE_TO_TARGET",
            "RELEASE"
        ]

    # -----------------------------------------------------
    # CALVIN SLIDING
    # -----------------------------------------------------

    if task_type == "SLIDING":

        if "right" in instruction:
            slide_action = "SLIDE_RIGHT"

        elif "left" in instruction:
            slide_action = "SLIDE_LEFT"

        elif "up" in instruction:
            slide_action = "SLIDE_UP"

        elif "down" in instruction:
            slide_action = "SLIDE_DOWN"

        else:
            slide_action = "SLIDE"

        return [
            "DETECT",
            "MOVE_TO_OBJECT",
            slide_action
        ]

    return ["UNKNOWN"]


def process_dataset(input_file, output_file):

    with open(input_file, "r", encoding="utf-8") as file:
        data = json.load(file)

    processed = []

    for record in data:

        new_record = dict(record)

        new_record["detected_action"] = detect_action(
            record.get("instruction", "")
        )

        new_record["task_type"] = detect_task_type(record)

        new_record["robot_actions"] = generate_robot_actions(
            new_record
        )

        processed.append(new_record)

    with open(output_file, "w", encoding="utf-8") as file:
        json.dump(processed, file, indent=4)

    return processed


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------

if __name__ == "__main__":

    input_file = (
        "datasets/combined/"
        "standardized_robot_dataset.json"
    )

    output_file = (
        "datasets/combined/"
        "unified_robot_dataset.json"
    )

    print("=" * 60)
    print("UNIFIED ACTION MAPPER")
    print("=" * 60)

    data = process_dataset(
        input_file,
        output_file
    )

    print(f"\nProcessed records: {len(data)}")

    print("\nTask distribution:")

    task_counts = {}

    for record in data:

        task = record["task_type"]

        task_counts[task] = (
            task_counts.get(task, 0) + 1
        )

    for task, count in task_counts.items():
        print(f"{task}: {count}")

    print("\nSample records:")

    shown = 0

    for record in data:

        if record["source"] == "CALVIN":

            print("\nInstruction:")
            print(record["instruction"])

            print("Task type:")
            print(record["task_type"])

            print("Robot actions:")
            print(
                " → ".join(
                    record["robot_actions"]
                )
            )

            shown += 1

            if shown == 7:
                break

    print("\n" + "=" * 60)
    print("COMPLETE")
    print("=" * 60)

    print("\nOutput:")
    print(output_file)