import hmac
import hashlib

def verify_signature(secret: str, raw_body: bytes, signature_header: str | None) -> bool:
    if not secret or not signature_header:
        return False
    # Replicate присылает HMAC-SHA256(body) в заголовке X-Replicate-Signature
    digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    # Иногда провайдеры добавляют префикс 'sha256=' — поддержим оба случая
    expected_a = digest
    expected_b = f"sha256={digest}"
    return hmac.compare_digest(signature_header, expected_a) or hmac.compare_digest(signature_header, expected_b)
