import requests

headers_sem_ua = {"Accept": "application/json"}
headers_com_ua = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}

url = "https://dadosabertos.camara.leg.br/api/v2/deputados/123086/despesas"

r1 = requests.get(url, params={"itens": 5}, headers=headers_sem_ua, timeout=30)
print("SEM User-Agent de navegador:", r1.status_code, len(r1.json().get("dados", [])))

r2 = requests.get(url, params={"itens": 5}, headers=headers_com_ua, timeout=30)
print("COM User-Agent de navegador:", r2.status_code, len(r2.json().get("dados", [])))

# e sem headers nenhum
r3 = requests.get(url, params={"itens": 5}, timeout=30)
print("SEM headers nenhum:", r3.status_code, len(r3.json().get("dados", [])))