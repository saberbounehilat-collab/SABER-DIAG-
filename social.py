"""Sharing links for the public SABER ACTROS DZ storefront.

No tracking, API keys, or login are required for share buttons. Networks which
do not support website link submissions are supported via the phone's native
share sheet or by copying the link.
"""
from urllib.parse import urlencode, quote

SITE_URL = "https://saber-actros-dz.onrender.com"


def share_links(url: str, title: str, image_url: str = "") -> dict[str, str]:
    message = f"{title} — {url}"
    opts = lambda params: urlencode(params, quote_via=quote)
    links = {
        "url": url,
        "title": title,
        "whatsapp": "https://api.whatsapp.com/send?" + opts({"text": message}),
        "facebook": "https://www.facebook.com/sharer/sharer.php?" + opts({"u": url}),
        "telegram": "https://t.me/share/url?" + opts({"url": url, "text": title}),
        "x": "https://twitter.com/intent/tweet?" + opts({"text": title, "url": url}),
        "linkedin": "https://www.linkedin.com/sharing/share-offsite/?" + opts({"url": url}),
        "reddit": "https://www.reddit.com/submit?" + opts({"url": url, "title": title}),
        "email": "mailto:?" + opts({"subject": title, "body": message}),
    }
    if image_url:
        links["pinterest"] = "https://www.pinterest.com/pin/create/button/?" + opts({
            "url": url,
            "media": image_url,
            "description": title,
        })
    return links
