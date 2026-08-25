from bs4 import BeautifulSoup
import requests

url = "https://www.vlr.gg/"
response = requests.get(url)

print(response.status_code)


