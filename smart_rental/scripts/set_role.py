import firebase_admin
from firebase_admin import credentials, auth

cred = credentials.Certificate(
    "credentials/firebase-key.json"
)

firebase_admin.initialize_app(cred)


ADMIN_EMAIL = "admin@smartrental.local"


user = auth.get_user_by_email(ADMIN_EMAIL)

auth.set_custom_user_claims(
    user.uid,
    {
        "role": "landlord"
    }
)

print("Admin UID:", user.uid)
print("Role: landlord")