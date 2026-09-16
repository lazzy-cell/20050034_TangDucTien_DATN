"""Helpers for consistent server-side Firestore ID generation."""

from services.firebase_service import get_firestore


firestore_db = get_firestore()


def new_document_id(collection_name: str) -> str:
    """Generate a Firestore document ID without writing any data."""
    if not collection_name:
        raise ValueError("collection_name is required")
    return firestore_db.collection(collection_name).document().id


def new_document_ref(collection_name: str):
    """Return a new Firestore document reference with an auto-generated ID."""
    if not collection_name:
        raise ValueError("collection_name is required")
    return firestore_db.collection(collection_name).document()
