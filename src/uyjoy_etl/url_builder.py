from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def build_listing_url(base_url: str, listing_path: str, page: int) -> str:
    """Listing path va page raqamidan to'g'ri OLX URL yasaydi."""

    split_path = urlsplit(listing_path)
    if split_path.scheme and split_path.netloc:
        scheme = split_path.scheme
        netloc = split_path.netloc
        path = split_path.path
        query = split_path.query
    else:
        base = urlsplit(base_url.rstrip("/"))
        scheme = base.scheme
        netloc = base.netloc
        raw_path, _, query = listing_path.strip().partition("?")
        path = "/" + raw_path.strip("/")

    normalized_path = path.rstrip("/") + "/"
    query_pairs = [
        (key, value)
        for key, value in parse_qsl(query, keep_blank_values=True)
        if key != "page"
    ]
    if page > 1:
        query_pairs.append(("page", str(page)))

    final_query = urlencode(query_pairs, doseq=True)
    return urlunsplit((scheme, netloc, normalized_path, final_query, ""))


def append_query_params(listing_path: str, extra_params: dict[str, str | int]) -> str:
    """Listing pathga qo'shimcha query filterlarni xavfsiz qo'shadi."""

    split_path = urlsplit(listing_path)
    query_pairs = parse_qsl(split_path.query, keep_blank_values=True)
    existing_keys = {key for key, _ in query_pairs}
    for key, value in extra_params.items():
        if key not in existing_keys:
            query_pairs.append((key, str(value)))

    query = urlencode(query_pairs, doseq=True)
    return urlunsplit(("", "", split_path.path, query, ""))
