import csv
import json
import random
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
ITEMS = [
    ("plate of food", "plate of food", "plates of food"),
    ("water bottle", "water bottle", "water bottles"),
    ("cold drink", "cold drink", "cold drinks"),
    ("burger", "burger", "burgers"),
    ("pizza", "pizza", "pizzas"),
    ("pasta", "pasta", "pastas"),
    ("coffee", "coffee", "coffees"),
    ("water", "water", "water"),
    ("menu", "menu", "menus"),
    ("food", "food", "food"),
    ("plate", "plate", "plates"),
    ("glass", "glass", "glasses"),
    ("drink", "drink", "drinks"),
]
QUANTITY_WORDS = {
    1: "one",
    2: "two",
    3: "three",
}
DELIVERY_STEPS = [
    "DETECT_OBJECT",
    "MOVE_TO_OBJECT",
    "PICK",
    "PLAN_ROUTE",
    "NAVIGATE_TO_TABLE",
    "PLACE",
    "CONFIRM_DELIVERY",
    "RETURN_TO_COUNTER",
]
TRAIN_TEST_FIELDS = [
    "id",
    "instruction",
    "expected_intent",
    "expected_validation",
    "expected_orders",
]
GOLD_FIELDS = TRAIN_TEST_FIELDS + ["expected_decomposition"]


def item_phrase(name, quantity):
    for item_name, singular, plural in ITEMS:
        if item_name == name:
            return singular if quantity == 1 else plural
    raise ValueError(f"Unsupported restaurant item: {name}")


def quantity_phrase(quantity, variant=0):
    if variant % 2:
        return str(quantity)
    return QUANTITY_WORDS[quantity]


def make_record(instruction, orders):
    normalized_orders = [
        {
            "table": table,
            "items": [
                {"name": name, "quantity": quantity}
                for name, quantity in items
            ],
        }
        for table, items in orders
    ]
    tables = [order["table"] for order in normalized_orders]
    if any(table is None for table in tables):
        validation = "MISSING_DESTINATION"
    elif any(not 1 <= table <= 4 for table in tables):
        validation = "INVALID_TABLE"
    else:
        validation = "VALID"
    return {
        "instruction": instruction,
        "expected_intent": "DELIVERY",
        "expected_validation": validation,
        "expected_orders": normalized_orders,
    }


def build_training_records():
    records = []
    verbs = ["Deliver", "Bring", "Serve", "Send", "Take"]
    single_templates = [
        "{verb} {quantity} {phrase} to Table {table}.",
        "{verb} {quantity} {phrase} for table number {table}.",
        "{verb} {quantity} {phrase} at Table {table}.",
        "{verb} {quantity} {phrase} to table {table}.",
    ]

    for item_index, (name, _, _) in enumerate(ITEMS):
        for variant, template in enumerate(single_templates):
            quantity = (item_index + variant) % 3 + 1
            table = (item_index + variant) % 4 + 1
            phrase = item_phrase(name, quantity)
            instruction = template.format(
                verb=verbs[(item_index + variant) % len(verbs)],
                quantity=quantity_phrase(quantity, item_index + variant),
                phrase=phrase,
                table=table,
            )
            records.append(make_record(
                instruction,
                [(table, [(name, quantity)])],
            ))

    for pair_index in range(14):
        first_name = ITEMS[pair_index % len(ITEMS)][0]
        second_name = ITEMS[(pair_index + 5) % len(ITEMS)][0]
        first_quantity = pair_index % 3 + 1
        second_quantity = (pair_index + 1) % 3 + 1
        table = pair_index % 4 + 1
        first_phrase = item_phrase(first_name, first_quantity)
        second_phrase = item_phrase(second_name, second_quantity)
        instruction = (
            f"{verbs[pair_index % len(verbs)]} "
            f"{quantity_phrase(first_quantity, pair_index)} {first_phrase} "
            f"and {quantity_phrase(second_quantity, pair_index + 1)} "
            f"{second_phrase} to Table {table}."
        )
        records.append(make_record(
            instruction,
            [(table, [
                (first_name, first_quantity),
                (second_name, second_quantity),
            ])],
        ))

    for pair_index in range(14):
        first_name = ITEMS[pair_index % len(ITEMS)][0]
        second_name = ITEMS[(pair_index + 5) % len(ITEMS)][0]
        first_quantity = pair_index % 3 + 1
        second_quantity = (pair_index + 1) % 3 + 1
        first_table = pair_index % 4 + 1
        second_table = first_table % 4 + 1
        first_phrase = item_phrase(first_name, first_quantity)
        second_phrase = item_phrase(second_name, second_quantity)
        instruction = (
            f"{verbs[(pair_index + 2) % len(verbs)]} "
            f"{quantity_phrase(first_quantity, pair_index)} {first_phrase} "
            f"to Table {first_table} and "
            f"{quantity_phrase(second_quantity, pair_index + 1)} "
            f"{second_phrase} to Table {second_table}."
        )
        records.append(make_record(
            instruction,
            [
                (first_table, [(first_name, first_quantity)]),
                (second_table, [(second_name, second_quantity)]),
            ],
        ))

    for index in range(10):
        name = ITEMS[index % len(ITEMS)][0]
        quantity = index % 3 + 1
        table = 5 + index
        phrase = item_phrase(name, quantity)
        instruction = (
            f"{verbs[index % len(verbs)]} "
            f"{quantity_phrase(quantity, index)} {phrase} to Table {table}."
        )
        records.append(make_record(
            instruction,
            [(table, [(name, quantity)])],
        ))

    for index in range(10):
        name = ITEMS[(index + 3) % len(ITEMS)][0]
        quantity = index % 3 + 1
        phrase = item_phrase(name, quantity)
        instruction = (
            f"{verbs[(index + 1) % len(verbs)]} "
            f"{quantity_phrase(quantity, index)} {phrase}."
        )
        records.append(make_record(
            instruction,
            [(None, [(name, quantity)])],
        ))

    return records


def build_gold_records():
    specifications = [
        ("Deliver two water bottles to Table 1.", [(1, [("water bottle", 2)])]),
        ("Bring one pizza to Table 2.", [(2, [("pizza", 1)])]),
        ("Serve three coffees at Table 3.", [(3, [("coffee", 3)])]),
        ("Send 2 burgers to table number 4.", [(4, [("burger", 2)])]),
        ("Take one plate of food to Table 1.", [(1, [("plate of food", 1)])]),
        ("Deliver three cold drinks to Table 2.", [(2, [("cold drink", 3)])]),
        ("Bring one glass to Table 3.", [(3, [("glass", 1)])]),
        ("Serve two plates at Table 4.", [(4, [("plate", 2)])]),
        ("Send one menu to Table 1.", [(1, [("menu", 1)])]),
        ("Take three drinks to Table 2.", [(2, [("drink", 3)])]),
        (
            "Bring two pizzas and one water bottle to Table 3.",
            [(3, [("pizza", 2), ("water bottle", 1)])],
        ),
        (
            "Serve one burger to Table 1 and two coffees to Table 4.",
            [(1, [("burger", 1)]), (4, [("coffee", 2)])],
        ),
        (
            "Deliver three pastas to Table 2 and one glass to Table 3.",
            [(2, [("pasta", 3)]), (3, [("glass", 1)])],
        ),
        (
            "Send one water and two plates of food to Table 4.",
            [(4, [("water", 1), ("plate of food", 2)])],
        ),
        (
            "Take two cold drinks to Table 1 and one menu to Table 2.",
            [(1, [("cold drink", 2)]), (2, [("menu", 1)])],
        ),
        ("Deliver one burger to Table 5.", [(5, [("burger", 1)])]),
        ("Bring two coffees to Table 8.", [(8, [("coffee", 2)])]),
        ("Serve one pizza.", [(None, [("pizza", 1)])]),
        ("Send two water bottles.", [(None, [("water bottle", 2)])]),
        ("Take three plates of food.", [(None, [("plate of food", 3)])]),
    ]
    return [make_record(instruction, orders) for instruction, orders in specifications]


def write_csv(filename, records, fields, include_decomposition=False):
    path = DATA_DIR / filename
    with path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=fields)
        writer.writeheader()
        for row_number, record in enumerate(records, start=1):
            row = {
                "id": row_number,
                "instruction": record["instruction"],
                "expected_intent": record["expected_intent"],
                "expected_validation": record["expected_validation"],
                "expected_orders": json.dumps(
                    record["expected_orders"],
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            }
            if include_decomposition:
                decompositions = []
                if record["expected_validation"] == "VALID":
                    for order in record["expected_orders"]:
                        for item in order["items"]:
                            for unit in range(1, item["quantity"] + 1):
                                decompositions.append({
                                    "table": order["table"],
                                    "item": item["name"],
                                    "unit": unit,
                                    "steps": DELIVERY_STEPS,
                                })
                row["expected_decomposition"] = json.dumps(
                    decompositions,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            writer.writerow(row)


def split_records(records):
    randomizer = random.Random(42)
    groups = {}
    for record in records:
        groups.setdefault(record["expected_validation"], []).append(record)
    train_records = []
    test_records = []
    for group in groups.values():
        randomizer.shuffle(group)
        train_count = int(len(group) * 0.8)
        train_records.extend(group[:train_count])
        test_records.extend(group[train_count:])
    randomizer.shuffle(train_records)
    randomizer.shuffle(test_records)
    return train_records, test_records


def main():
    DATA_DIR.mkdir(exist_ok=True)
    records = build_training_records()
    if len(records) != 100:
        raise RuntimeError(f"Expected 100 train/test records, got {len(records)}.")

    train_records, test_records = split_records(records)
    gold_records = build_gold_records()
    if len(gold_records) != 20:
        raise RuntimeError(f"Expected 20 gold records, got {len(gold_records)}.")

    write_csv("restaurant_train.csv", train_records, TRAIN_TEST_FIELDS)
    write_csv("restaurant_test.csv", test_records, TRAIN_TEST_FIELDS)
    write_csv(
        "restaurant_gold_evaluation.csv",
        gold_records,
        GOLD_FIELDS,
        include_decomposition=True,
    )
    print(
        "Generated restaurant_train.csv (80), restaurant_test.csv (20), "
        "and restaurant_gold_evaluation.csv (20)."
    )


if __name__ == "__main__":
    main()
