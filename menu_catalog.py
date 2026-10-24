import math
import re
import unicodedata
import uuid
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import customer_orders
from google.api_core.exceptions import AlreadyExists, Conflict


MENU_COLLECTION = "menu_items"
DEFAULT_MENU_ITEMS = (
    {
        "id": "garden-margherita",
        "name": "Garden Margherita",
        "category": "Pizza",
        "description": "Slow tomato, basil, fior di latte",
        "price": 18.5,
        "available": True,
        "image": "",
    },
    {
        "id": "woodland-mushroom-pizza",
        "name": "Woodland Mushroom",
        "category": "Pizza",
        "description": "Wild mushrooms, thyme, aged mozzarella",
        "price": 21.0,
        "available": True,
        "image": "",
    },
    {
        "id": "verdant-smash",
        "name": "Verdant Smash Burger",
        "category": "Burgers",
        "description": "Grass-fed beef, sharp cheddar, garden pickle",
        "price": 17.5,
        "available": True,
        "image": "",
    },
    {
        "id": "crispy-garden-burger",
        "name": "Crispy Garden Burger",
        "category": "Burgers",
        "description": "Crispy chickpea patty, herb yogurt, greens",
        "price": 15.0,
        "available": True,
        "image": "",
    },
    {
        "id": "truffle-linguine",
        "name": "Truffle Mushroom Linguine",
        "category": "Pasta",
        "description": "Silky parmesan cream, wild mushroom, herbs",
        "price": 23.5,
        "available": True,
        "image": "",
    },
    {
        "id": "lemon-pappardelle",
        "name": "Lemon Garden Pappardelle",
        "category": "Pasta",
        "description": "Fresh lemon, peas, basil, pecorino",
        "price": 19.0,
        "available": True,
        "image": "",
    },
    {
        "id": "whipped-ricotta",
        "name": "Whipped Ricotta Toast",
        "category": "Starters",
        "description": "Grilled sourdough, honey, garden herbs",
        "price": 10.0,
        "available": True,
        "image": "",
    },
    {
        "id": "crispy-polenta",
        "name": "Crispy Polenta Bites",
        "category": "Starters",
        "description": "Golden polenta, tomato relish, parmesan",
        "price": 9.5,
        "available": True,
        "image": "",
    },
    {
        "id": "olive-oil-cake",
        "name": "Lemon Olive Oil Cake",
        "category": "Desserts",
        "description": "Whipped mascarpone, seasonal berries",
        "price": 9.0,
        "available": True,
        "image": "",
    },
    {
        "id": "dark-chocolate-mousse",
        "name": "Dark Chocolate Mousse",
        "category": "Desserts",
        "description": "70% cacao, sea salt, hazelnut crumble",
        "price": 10.5,
        "available": False,
        "image": "",
    },
    {
        "id": "garden-spritz",
        "name": "Garden Citrus Spritz",
        "category": "Drinks",
        "description": "Blood orange, rosemary, sparkling water",
        "price": 7.5,
        "available": True,
        "image": "",
    },
    {
        "id": "iced-matcha",
        "name": "Iced Matcha Cloud",
        "category": "Drinks",
        "description": "Stone-ground matcha, oat milk, soft foam",
        "price": 6.5,
        "available": True,
        "image": "",
    },
)


class MenuCatalogError(ValueError):
    pass


class MenuItemNotFoundError(LookupError):
    pass


def _collection():
    return customer_orders.get_firestore_client().collection(MENU_COLLECTION)


def food_name_slug(name):
    normalized = unicodedata.normalize("NFKD", name)
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", ascii_name).strip("-") or "food-item"


def _normalize_item(document):
    value = document.to_dict()
    if not isinstance(value, dict):
        raise MenuCatalogError("A menu item document is not a valid object.")

    name = value.get("name")
    category = value.get("category")
    description = value.get("description", "")
    available = value.get("available", value.get("availability", True))
    image = value.get("image", value.get("image_path", ""))
    try:
        price = float(value.get("price"))
    except (TypeError, ValueError) as error:
        raise MenuCatalogError("A menu item has an invalid price.") from error
    if (
        not isinstance(name, str)
        or not name.strip()
        or not isinstance(category, str)
        or not category.strip()
        or not isinstance(description, str)
        or not isinstance(available, bool)
        or not isinstance(image, str)
        or not math.isfinite(price)
    ):
        raise MenuCatalogError("A menu item document has invalid fields.")

    return {
        "id": document.id,
        "name": name.strip(),
        "price": price,
        "description": description.strip(),
        "category": category.strip(),
        "available": available,
        "image": image.strip(),
    }


def list_menu_items(seed_defaults=False):
    collection = _collection()
    documents = list(collection.stream())
    if not documents and seed_defaults:
        for item in DEFAULT_MENU_ITEMS:
            try:
                collection.document(item["id"]).create({
                    key: value for key, value in item.items() if key != "id"
                })
            except (AlreadyExists, Conflict):
                continue
        documents = list(collection.stream())

    items = [_normalize_item(document) for document in documents]
    return sorted(items, key=lambda item: (item["category"].casefold(), item["name"].casefold()))


def get_menu_item(item_id):
    snapshot = _collection().document(item_id).get()
    if not snapshot.exists:
        raise MenuItemNotFoundError(item_id)
    return _normalize_item(snapshot)


def validate_menu_item(data):
    if not isinstance(data, dict):
        raise MenuCatalogError("A menu item JSON object is required.")

    name = data.get("name")
    description = data.get("description", "")
    category = data.get("category")
    available = data.get("available")
    image = data.get("image", "")
    try:
        amount = Decimal(str(data.get("price")))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise MenuCatalogError("Enter a valid item price.") from error

    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
        raise MenuCatalogError("Item name must contain 1 to 80 characters.")
    if not isinstance(description, str) or len(description.strip()) > 500:
        raise MenuCatalogError("Description must be 500 characters or fewer.")
    if not isinstance(category, str) or not 1 <= len(category.strip()) <= 40:
        raise MenuCatalogError("Category must contain 1 to 40 characters.")
    if (
        isinstance(data.get("price"), bool)
        or not amount.is_finite()
        or not 0 < amount <= 9999
    ):
        raise MenuCatalogError("Price must be greater than 0 and at most 9999.")
    rounded_price = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if amount != rounded_price:
        raise MenuCatalogError("Price can have at most two decimal places.")
    if not isinstance(available, bool):
        raise MenuCatalogError("Availability must be true or false.")
    if available and not image:
        raise MenuCatalogError("An item-specific food image is required for available menu items.")
    if not isinstance(image, str) or (
        image
        and not re.fullmatch(
            r"uploads/[A-Za-z0-9][A-Za-z0-9_.-]*\.(?:jpg|jpeg|png|webp)",
            image,
            re.IGNORECASE,
        )
    ):
        raise MenuCatalogError("Image must be a valid local uploads path.")
    if image:
        image_filename = image.rsplit("/", 1)[-1].rsplit(".", 1)[0].lower()
        name_slug = food_name_slug(name.strip())
        if image_filename != name_slug and not image_filename.startswith(f"{name_slug}-"):
            raise MenuCatalogError("Image filename must match the menu item name.")

    return {
        "name": name.strip(),
        "price": float(rounded_price),
        "description": description.strip(),
        "category": category.strip(),
        "available": available,
        "image": image,
    }


def create_menu_item(item):
    document_id = uuid.uuid4().hex
    _collection().document(document_id).create(item)
    return get_menu_item(document_id)


def update_menu_item(item_id, item):
    document = _collection().document(item_id)
    if not document.get().exists:
        raise MenuItemNotFoundError(item_id)
    document.update(item)
    return get_menu_item(item_id)


def delete_menu_item(item_id):
    document = _collection().document(item_id)
    if not document.get().exists:
        raise MenuItemNotFoundError(item_id)
    document.delete()
