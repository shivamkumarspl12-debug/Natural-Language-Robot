import copy
from datetime import datetime, timezone

from firebase_admin import firestore
from google.api_core.exceptions import Conflict


class MemorySnapshot:
    def __init__(self, value, document_id=None):
        self._value = value
        self.id = document_id
        self.exists = value is not None

    def to_dict(self):
        return copy.deepcopy(self._value)


class MemoryWriteResult:
    def __init__(self, update_time):
        self.update_time = update_time


class MemoryDocument:
    def __init__(self, collection, document_id):
        self.collection = collection
        self.document_id = document_id

    def create(self, value):
        if self.document_id in self.collection.store:
            raise Conflict("Document already exists.")

        created_at = datetime.now(timezone.utc)
        stored_value = copy.deepcopy(value)
        if value.get("created_at") is firestore.SERVER_TIMESTAMP:
            stored_value["created_at"] = created_at
        self.collection.store[self.document_id] = stored_value
        return MemoryWriteResult(created_at)

    def get(self, transaction=None):
        return MemorySnapshot(
            self.collection.store.get(self.document_id),
            self.document_id,
        )

    def update(self, values):
        if self.document_id not in self.collection.store:
            raise KeyError(self.document_id)
        self.collection.store[self.document_id].update(copy.deepcopy(values))

    def delete(self):
        self.collection.store.pop(self.document_id, None)


class MemoryTransaction:
    def update(self, document, values):
        document.update(values)


class MemoryAggregationResult:
    def __init__(self, alias, value):
        self.alias = alias
        self.value = value


class MemoryCountQuery:
    def __init__(self, store, alias):
        self.store = store
        self.alias = alias

    def get(self):
        return [[MemoryAggregationResult(self.alias, len(self.store))]]


class MemoryCollection:
    def __init__(self, store):
        self.store = store
        self._limit = None
        self._order_field = None
        self._direction = None
        self._filters = []

    def document(self, document_id):
        return MemoryDocument(self, document_id)

    def where(self, field, operator, value):
        self._filters.append((field, operator, value))
        return self

    def count(self, alias="count"):
        return MemoryCountQuery(self.store, alias)

    def order_by(self, field, direction=None):
        self._order_field = field
        self._direction = direction
        return self

    def limit(self, count):
        self._limit = count
        return self

    def stream(self):
        documents = [
            MemorySnapshot(value, document_id)
            for document_id, value in self.store.items()
        ]
        for field, operator, value in self._filters:
            comparisons = {
                ">=": lambda left: left >= value,
                ">": lambda left: left > value,
                "<=": lambda left: left <= value,
                "<": lambda left: left < value,
                "==": lambda left: left == value,
            }
            compare = comparisons[operator]
            documents = [
                snapshot
                for snapshot in documents
                if snapshot.to_dict().get(field) is not None
                and compare(snapshot.to_dict()[field])
            ]
        if self._order_field:
            documents.sort(
                key=lambda snapshot: snapshot.to_dict().get(self._order_field),
                reverse=self._direction == "DESCENDING",
            )
        if self._limit is not None:
            documents = documents[:self._limit]
        return documents


class MemoryFirestore:
    def __init__(self):
        self.collections = {}

    def collection(self, name):
        store = self.collections.setdefault(name, {})
        return MemoryCollection(store)

    def transaction(self):
        return MemoryTransaction()
