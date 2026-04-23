from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())  # run once, copy to .env