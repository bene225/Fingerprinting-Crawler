import asyncio
import socket

# Testet ob Verbindung zu stabilem Server möglich (Internet-Ausfall)
def check_internet(host : str = "8.8.8.8", port : int = 53, timeout : float = 3) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


async def wait_for_internet():
    while not check_internet():
        print("Kein Internet, naechster Versuch in 30 s")
        await asyncio.sleep(30)
