from fastapi import APIRouter

router = APIRouter(prefix="/skus", tags=["skus"])

# Пример эндпоинта просмотра SKU (заглушка, позже подключим БД)
@router.get("/{sku_code}")
async def get_sku_card(sku_code: str):
    return {"sku": sku_code, "status": "stub", "message": "SKU card placeholder"}
