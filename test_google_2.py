import random
import re
import httpx

user_agents = [
    "Mozilla/5.0 (webOS/1.4.5; U; en-US) AppleWebKit/532.2 (KHTML, like Gecko) Version/1.0 Safari/532.2 Pre/1.0",
    "Mozilla/5.0 (webOS/1.4.0; U; en-US) AppleWebKit/532.2 (KHTML, like Gecko) Version/1.0 Safari/532.2 Pre/1.0",
    "Mozilla/5.0 (webOS/1.3.5; U; en-US) AppleWebKit/532.2 (KHTML, like Gecko) Version/1.0 Safari/532.2 Pre/1.0",
    "Mozilla/5.0 (webOS/2.0.0; U; en-US) AppleWebKit/534.6 (KHTML, like Gecko) Version/1.0 Safari/534.6 Pre/2.0",
    "Mozilla/5.0 (webOS/2.1.0; U; en-US) AppleWebKit/534.6 (KHTML, like Gecko) Version/1.0 Safari/534.6 Pre/2.1",
    "Mozilla/5.0 (webOS/3.0.5; U; en-US) AppleWebKit/534.6 (KHTML, like Gecko) TouchPad/1.0",
    "Mozilla/5.0 (webOS/3.0.2; U; en-US) AppleWebKit/534.6 (KHTML, like Gecko) TouchPad/1.0",
    "Mozilla/5.0 (webOS/1.2.1; U; en-GB) AppleWebKit/532.2 (KHTML, like Gecko) Version/1.0 Safari/532.2 Pre/1.0",
    "Mozilla/5.0 (webOS/1.4.0; U; fr-FR) AppleWebKit/532.2 (KHTML, like Gecko) Version/1.0 Safari/532.2 Pre/1.0",
    "Mozilla/5.0 (webOS/1.4.1; U; de-DE) AppleWebKit/532.2 (KHTML, like Gecko) Version/1.0 Safari/532.2 Pre/1.0",
    "Mozilla/5.0 (webOS/1.3.1; U; en-US) AppleWebKit/532.2 (KHTML, like Gecko) Version/1.0 Safari/532.2 Pre/1.0",
    "Mozilla/5.0 (webOS/2.0.1; U; en-US) AppleWebKit/534.6 (KHTML, like Gecko) Version/1.0 Safari/534.6 Pre/2.0",
    "Mozilla/5.0 (webOS/1.4.5; U; en-US; Pixi) AppleWebKit/532.2 (KHTML, like Gecko) Version/1.0 Safari/532.2 Pre/1.0",
    "Mozilla/5.0 (webOS/1.4.5; U; en-US; Pre) AppleWebKit/532.2 (KHTML, like Gecko) Version/1.0 Safari/532.2 Pre/1.0",
]


def main():
    for ua in user_agents:
        print()
        print(ua)
        print("=" * len(ua))
        for query in ["spielzeug",]: #  "wohnung"]:
            search(query, ua)



def search(query, ua):
    url = f"https://www.google.com/search?q={query}&ucbcb=1"

    headers: dict[str, str] = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "User-Agent": ua,
    }

    cookies: dict[str, str] = {}

    # intro ..
    resp = httpx.get(url, headers=headers)
    print(f"[intro] {url}: {resp}")
    for k, v in resp.cookies.items():
        cookies[k] = v
        print(f"[intro] set cookie - '{k}': '{v}'")

    with open("test_google.html", "w") as f:
        f.write(resp.text)

    import pdb
    pdb.set_trace()
    x=1


    #if resp.status_code != 302:
    #    print(f"[intro] ERROR: expected 'Moved Temporarily' (HTTP 302), got HTTP {resp.status_code}")
    #    return 42
    # consent_url = resp.headers["Location"]
    # resp = httpx.post(consent_url, headers=headers)

    # match = re.search(r'<a href="(https://consent.google.com.*?)"', resp.text)
    # if not match:
    #     #print(f"ERROR: missing CONSENT URL, UA: {ua}")
    #     return 42

    # import pdb
    # pdb.set_trace()
    # href = match.group(1)
    # href = href.replace("&amp;", "&").replace("google.com/dl?", "google.com/ml?")
    # print(href)
    # # text = self._get_curl_cffi(href, headers=headers)

    # match = re.search('(<form action="https://consent.google.com/save".*?</form>)', resp.text)
    # if not match:
    #     print(f"ERROR: missing <form action .. </form>, UA: {ua}")
    #     return 42
    # form = match.group(1)
    # params = dict(re.findall(r'name="([^"]+)"\s+value="([^"]*)"', form))
    # resp = httpx.post(
    #     "https://consent.google.com/save",
    #     headers=headers,
    #     data=params,
    # )
    # print(text)

main()
