from firebase_config import initialize_firebase


firestore_db, realtime_db = initialize_firebase()


def get_firestore():
    return firestore_db


def get_realtime_db():
    return realtime_db