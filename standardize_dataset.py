import json

INPUT_FILE = "datasets/combined/combined_robot_dataset.json"
OUTPUT_FILE = "datasets/combined/standardized_robot_dataset.json"


def standardize_record(record):

    new_record = dict(record)

    source = record.get("source")

    if source == "CUSTOM":
        new_record["task_type"] = "PICK_AND_PLACE"

    elif source == "CALVIN":
        action = record.get("action_type")

        if action in ["GRAB", "LIFT"]:
            new_record["task_type"] = "MANIPULATION"

        elif action == "PLACE":
            new_record["task_type"] = "PLACEMENT"

        elif action == "SLIDE":
            new_record["task_type"] = "SLIDING"

        else:
            new_record["task_type"] = "OTHER"

    return new_record


def main():

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    standardized = [
        standardize_record(record)
        for record in data
    ]

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(standardized, f, indent=4)

    print("=" * 60)
    print("DATASET STANDARDIZATION COMPLETE")
    print("=" * 60)

    print(f"\nInput records : {len(data)}")
    print(f"Output records: {len(standardized)}")

    custom = sum(
        1 for x in standardized
        if x.get("source") == "CUSTOM"
    )

    calvin = sum(
        1 for x in standardized
        if x.get("source") == "CALVIN"
    )

    print(f"\nCUSTOM : {custom}")
    print(f"CALVIN : {calvin}")

    print("\nTask Types:")

    task_types = {}

    for record in standardized:
        task = record.get("task_type", "UNKNOWN")
        task_types[task] = task_types.get(task, 0) + 1

    for task, count in task_types.items():
        print(f"{task}: {count}")

    print("\nOutput:")
    print(OUTPUT_FILE)


if __name__ == "__main__":
    main()