from main import users_db

print("Diagnostic: users_db contents:")
for user in users_db:
    print(f"User: {user}")

print("\nDiagnostic: user with id=1:")
for user in users_db:
    if user["id"] == 1:
        print(f"Found user: {user}")
        break

print("\nDiagnostic: Looking for email field in user with id=1:")
for user in users_db:
    if user["id"] == 1:
        print(f"Email field exists: {'email' in user}")
        print(f"User data: {user}")
        break