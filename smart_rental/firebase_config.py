import firebase_admin
from firebase_admin import credentials, firestore, db


def initialize_firebase():

    # Kiểm tra Firebase đã được khởi tạo chưa
    if not firebase_admin._apps:

        cred = credentials.Certificate(
            "credentials/firebase-key.json"
        )

        firebase_admin.initialize_app(
            cred,
            {
                "databaseURL":
                "https://datn-smartrental-default-rtdb.asia-southeast1.firebasedatabase.app/"
            }
        )

    firestore_db = firestore.client()

    realtime_db = db.reference()

    return firestore_db, realtime_db