import socket

# Testet ob Verbindung zu stabilem Server möglich (Internet-Ausfall)
def check_internet(host : str = "8.8.8.8", port : int = 53, timeout : float = 3) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False
