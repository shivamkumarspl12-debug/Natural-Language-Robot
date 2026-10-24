import json
import os

CUSTOM_FILE = "robot_dataset.json"

CALVIN_FILE = os.path.join(
    "datasets",
    "calvin",
    "calvin",
    "dataset",
    "calvin_debug",
    "calvin_debug_dataset",
    "validation",
    "lang_paraphrase-MiniLM-L3-v2",
    "calvin_robot_instructions.json"
)

OUTPUT_DIR = os.path.join("datasets", "combined")
OUTPUT_FILE = os.path.join(
    OUTPUT_DIR,
    "combined_robot_dataset.json"
)


def load_json(filename):
    with open(filename, "r", encoding="utf-8") as file:
        return json.load(file)


def main():

    print("=" * 60)
    print("DATASET MERGING")
    print("=" * 60)

    custom_data = load_json(CUSTOM_FILE)
    calvin_data = load_json(CALVIN_FILE)

    print(f"\nCustom records : {len(custom_data)}")
    print(f"CALVIN records : {len(calvin_data)}")

    combined = []

    # Custom dataset
    for record in custom_data:
        new_record = dict(record)
        new_record["source"] = "CUSTOM"
        combined.append(new_record)

    # CALVIN dataset
    for record in calvin_data:
        new_record = dict(record)
        new_record["source"] = "CALVIN"
        combined.append(new_record)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as file:
        json.dump(combined, file, indent=4)

    custom_count = sum(
        1 for record in combined
        if record["source"] == "CUSTOM"
    )

    calvin_count = sum(
        1 for record in combined
        if record["source"] == "CALVIN"
    )

    print("\n" + "=" * 60)
    print("MERGE COMPLETE")
    print("=" * 60)

    print(f"\nTotal records  : {len(combined)}")
    print(f"Custom records : {custom_count}")
    print(f"CALVIN records : {calvin_count}")

    print("\nOutput:")
    print(OUTPUT_FILE)


if __name__ == "__main__":
    main()