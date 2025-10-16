import re
import httpx

# {
# 	"requestHeaders": {
# 		"headers": [
# 			{
# 				"name": "Accept",
# 				"value": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
# 			},
# 			{
# 				"name": "Accept-Encoding",
# 				"value": "gzip, deflate, br, zstd"
# 			},
# 			{
# 				"name": "Accept-Language",
# 				"value": "de,en;q=0.5"
# 			},
# 			{
# 				"name": "Alt-Used",
# 				"value": "www.google.com"
# 			},
# 			{
# 				"name": "Cache-Control",
# 				"value": "no-cache"
# 			},
# 			{
# 				"name": "Connection",
# 				"value": "keep-alive"
# 			},
# 			{
# 				"name": "Cookie",
# 				"value": "AEC=AaJma5s3bCc-NRnFbZm90kqV0g8MnVHJxFY5FQN6Bi33T8Ve0GqAh5PRz1U;
#                         __Secure-ENID=28.SE=eCdoFqZfWeE8e4oEptXNSbd-R2NrImYPpHH9EbRPBS1Q-3Gg0aLzasH-psfNMQNyvqxfTOuqFq2SlpaW_SGxb_7n7ixTJyKABJn3D1GIBYQ1cHy88NCdQwaR1pL8VBf6gLDXCdr9TI6TQ_s9u1jWMUVowQOVP4GCi0zkgkJWegabxjz41dhcptr8YAHI6QJc5ZhS7bn-1p-ISM714zXqiAAJ;
#                         SOCS=CAESNQgBEitib3FfaWRlbnRpdHlmcm9udGVuZHVpc2VydmVyXzIwMjUxMDE1LjA1X3AwGgJkZSADGgYIgOvAxwY"
# 			},
# 			{
# 				"name": "Host",
# 				"value": "www.google.com"
# 			},
# 			{
# 				"name": "Pragma",
# 				"value": "no-cache"
# 			},
# 			{
# 				"name": "Priority",
# 				"value": "u=0, i"
# 			},
# 			{
# 				"name": "Sec-Fetch-Dest",
# 				"value": "document"
# 			},
# 			{
# 				"name": "Sec-Fetch-Mode",
# 				"value": "navigate"
# 			},
# 			{
# 				"name": "Sec-Fetch-Site",
# 				"value": "cross-site"
# 			},
# 			{
# 				"name": "Sec-Fetch-User",
# 				"value": "?1"
# 			},
# 			{
# 				"name": "Sec-GPC",
# 				"value": "1"
# 			},
# 			{
# 				"name": "Upgrade-Insecure-Requests",
# 				"value": "1"
# 			},
# 			{
# 				"name": "User-Agent",
# 				"value": "Mozilla/5.0 (X11; Linux x86_64; rv:143.0) Gecko/20100101 Firefox/143.0"
# 			}
# 		]
# 	}
# }


def test_google():
    send_cookies = {
        "SOCS": "CAISAiAD",
    }
    keyword = "foo"
    google_base_url = f"https://www.google.com"
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:142.0) Gecko/20100101 Firefox/142.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        # "Accept-Language": "zh-CN,zh;q=0.9",
        "Accept-Language": "de-DE,zh;q=0.9",
    }

    ## INTRO

    # resp_intro = httpx.get(f"{google_base_url}/search?q={keyword}&sca_esv=922155461cbe86eb&emsg=SG_REL&sei=L9jwaKWdDNrTp84Pwu3E2AU", headers=headers, cookies=send_cookies)
    resp_intro = httpx.get(google_base_url, headers=headers, cookies=send_cookies)
    print(f"INTRO request: {resp_intro}")
    with open("test_google_INTRO.html", "w") as f:
        f.write(resp_intro.text)
    for name, value in resp_intro.cookies.items():
        send_cookies[name] = value
        print(f"INTRO COOKIE '{name}' : '{value}'")

    consent_url = re.search(r'<a href="(https://consent.google.com.*?)"', resp_intro.text)
    if not consent_url:
        print("ERROR: missing CONSENT URL")
        return 42
    consent_url = consent_url[1].replace("&amp;", "&")
    print(f"CONSENT URL: {consent_url}")

    # form = re.search('(<form action="https://consent.google.com/save".*?</form>)', resp_intro.text).group(1)
    # params = dict(re.findall(r'name="([^"]+)"\s+value="([^"]*)"', form))
    # for name, value in params.items():
    #     print(f"CONSENT FORM FIELD: '{name}' : '{value}'")

    #consent_url = "https://consent.google.com/save" #######  + consent_url[consent_url.index("?"):]
    #print(f"CONSENT URL: {consent_url}")

    resp_consent = httpx.post(consent_url, headers=headers, data=send_cookies, cookies=send_cookies)
    print(f"CONSENT response: {resp_consent}")

    with open("test_google_CONSENT.html", "w") as f:
        f.write(resp_consent.text)
    import pdb
    pdb.set_trace()

    for name, value in resp_consent.cookies.items():
        send_cookies[name] = value
        print(f"CONSENT COOKIE '{name}' : '{value}'")

    resp_query = httpx.get(f"{google_base_url}/search?q={keyword}", headers=headers, cookies=send_cookies)
    print(f"QUERY response: {resp_query}")
    with open("test_google_QUERY.html", "w") as f:
        f.write(resp_query.text)


test_google()
